const API_BASE = 'http://127.0.0.1:8000';
const SOURCE_STORAGE_KEY = 'compkeyDemoSource';
const SOURCE_OPTIONS = [
  { value: 'p4', label: 'P4 主库' },
  { value: 'aol', label: 'AOL demo' },
];

let sourceCatalog = {};
let currentHotItems = [];
let currentWindowDays = 7;
let expandedTrend = null;
let chartInstance = null;

function normalizeSource(source) {
  const key = String(source || 'p4').trim().toLowerCase();
  return SOURCE_OPTIONS.some(item => item.value === key) ? key : 'p4';
}

function dateFromIso(value) {
  if (!value) return null;
  const [y, m, d] = String(value).split('-').map(Number);
  if (!y || !m || !d) return null;
  return new Date(y, m - 1, d);
}

function isoFromDate(date) {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, '0');
  const d = String(date.getDate()).padStart(2, '0');
  return `${y}-${m}-${d}`;
}

function addDays(date, days) {
  const next = new Date(date);
  next.setDate(next.getDate() + days);
  return next;
}

function diffDaysInclusive(startIso, endIso) {
  const start = dateFromIso(startIso);
  const end = dateFromIso(endIso);
  if (!start || !end) return 0;
  return Math.max(1, Math.round((end - start) / 86400000) + 1);
}

function ensureSourceOptions() {
  const select = document.getElementById('demoSource');
  if (!select) return;
  const allowed = new Set(SOURCE_OPTIONS.map(item => item.value));
  Array.from(select.options).forEach(opt => {
    if (!allowed.has(opt.value)) opt.remove();
  });
  for (const item of SOURCE_OPTIONS) {
    if (![...select.options].some(opt => opt.value === item.value)) {
      const opt = document.createElement('option');
      opt.value = item.value;
      opt.textContent = item.label;
      select.appendChild(opt);
    }
  }
}

function getSelectedSource() {
  return normalizeSource(localStorage.getItem(SOURCE_STORAGE_KEY));
}

function setSelectedSource(source) {
  localStorage.setItem(SOURCE_STORAGE_KEY, normalizeSource(source));
}

function getSourceLabel(source) {
  const item = SOURCE_OPTIONS.find(x => x.value === normalizeSource(source));
  return item ? item.label : 'P4 主库';
}

function getSourceMeta(source) {
  return sourceCatalog[normalizeSource(source)] || {
    source: normalizeSource(source),
    label: getSourceLabel(source),
    description: '',
    date_start: '',
    date_end: '',
    time_series_rows: 0,
  };
}

function setDateControlBounds(source) {
  const meta = getSourceMeta(source);
  const startInput = document.getElementById('startDate');
  const endInput = document.getElementById('endDate');
  if (!startInput || !endInput) return;

  const minDate = meta.date_start || '';
  const maxDate = meta.date_end || '';
  startInput.min = minDate;
  startInput.max = maxDate;
  endInput.min = minDate;
  endInput.max = maxDate;

  if (!minDate || !maxDate) {
    startInput.value = '';
    endInput.value = '';
    return;
  }

  const max = dateFromIso(maxDate);
  const min = dateFromIso(minDate);
  const defaultStart = max && min ? (addDays(max, -6) < min ? min : addDays(max, -6)) : min;
  startInput.value = isoFromDate(defaultStart || min);
  endInput.value = maxDate;
}

function updateSourceUi() {
  const select = document.getElementById('demoSource');
  if (!select) return;
  const current = getSelectedSource();
  select.value = current;
  const meta = getSourceMeta(current);
  const label = document.getElementById('dataSource');
  const desc = document.getElementById('sourceDescription');
  const badge = document.getElementById('currentSourceLabel');
  if (label) label.textContent = meta.label || getSourceLabel(current);
  if (badge) badge.textContent = meta.label || getSourceLabel(current);
  if (desc) desc.textContent = meta.description || '暂无说明';
}

function syncDateInputs() {
  const startInput = document.getElementById('startDate');
  const endInput = document.getElementById('endDate');
  if (!startInput || !endInput) return;
  if (startInput.value && endInput.value && startInput.value > endInput.value) {
    endInput.value = startInput.value;
  }
}

function bindSourceSelector(onChange) {
  const select = document.getElementById('demoSource');
  if (!select) return;
  ensureSourceOptions();
  select.value = getSelectedSource();
  select.addEventListener('change', async () => {
    setSelectedSource(select.value);
    updateSourceUi();
    setDateControlBounds(select.value);
    expandedTrend = null;
    await loadHotKeywords();
    if (typeof onChange === 'function') {
      await onChange(select.value);
    }
  });
}

function showError(message) {
  const box = document.getElementById('errorBox');
  box.style.display = 'block';
  box.textContent = message;
}

function clearError() {
  const box = document.getElementById('errorBox');
  box.style.display = 'none';
  box.textContent = '';
}

async function classifyFetchFailure() {
  if (navigator && navigator.onLine === false) {
    return '网络失败：当前设备离线，请检查网络连接后重试。';
  }
  try {
    await fetch(`${API_BASE}/health`, { mode: 'no-cors', cache: 'no-store' });
    return '跨域被阻止：请确认后端 CORS 允许 http://127.0.0.1:8001。';
  } catch (_) {
    return '后端未启动或不可达：请确认 API 服务运行在 http://127.0.0.1:8000。';
  }
}

async function loadSourceCatalog() {
  try {
    const res = await fetch(`${API_BASE}/sources`);
    if (!res.ok) return;
    const payload = await res.json();
    sourceCatalog = {};
    for (const item of payload.items || []) {
      if (!SOURCE_OPTIONS.some(x => x.value === item.source)) continue;
      sourceCatalog[item.source] = item;
    }
  } catch (_) {
    sourceCatalog = {};
  }
}

function disposeInlineChart() {
  if (chartInstance) {
    chartInstance.dispose();
    chartInstance = null;
  }
}

function updateTopMeta(payload, selectedSource) {
  const meta = getSourceMeta(selectedSource);
  const sourceLabel = Array.isArray(payload) ? meta.label : (payload.source || meta.label);
  const range = Array.isArray(payload)
    ? '未知'
    : `${payload.date_range?.start || '未知'} ~ ${payload.date_range?.end || '未知'}`;
  const comparisonRange = Array.isArray(payload)
    ? '未知'
    : `${payload.comparison_range?.start || '未知'} ~ ${payload.comparison_range?.end || '未知'}`;

  document.getElementById('dataSource').textContent = sourceLabel;
  document.getElementById('sourceDescription').textContent = meta.description || '暂无说明';
  document.getElementById('dataRange').textContent = range;
  document.getElementById('comparisonRange').textContent = comparisonRange;
  document.getElementById('updatedAt').textContent = new Date().toLocaleString();
}

async function loadHotKeywords() {
  clearError();
  const limit = Number(document.getElementById('limit').value);
  const startDate = document.getElementById('startDate').value;
  const endDate = document.getElementById('endDate').value;
  if (!startDate || !endDate) {
    showError('请先选择开始日期和结束日期。');
    return;
  }
  if (startDate > endDate) {
    showError('开始日期不能晚于结束日期。');
    return;
  }

  try {
    const selectedSource = getSelectedSource();
    const url = `${API_BASE}/hot_keywords?limit=${limit}&start_date=${encodeURIComponent(startDate)}&end_date=${encodeURIComponent(endDate)}&source=${encodeURIComponent(selectedSource)}`;
    const res = await fetch(url);
    if (!res.ok) {
      const txt = await res.text();
      return showError(`加载榜单失败（HTTP ${res.status}）：${txt || res.statusText}`);
    }
    const payload = await res.json();
    const items = Array.isArray(payload) ? payload : (payload.items || []);
    currentHotItems = items;
    currentWindowDays = diffDaysInclusive(startDate, endDate);
    renderHotList(items, currentWindowDays);
    updateTopMeta(payload, selectedSource);
  } catch (e) {
    showError(await classifyFetchFailure());
  }
}

function renderHotList(items, windowDays) {
  disposeInlineChart();
  const div = document.getElementById('hotList');
  if (!items || items.length === 0) {
    div.innerHTML = '<div class="empty-state">当前所选时间范围内暂无可展示的热词数据。</div>';
    return;
  }

  let html = '<table><thead><tr><th>排名</th><th>关键词</th><th>当前窗口搜索量</th><th>前一窗口搜索量</th><th>增长率</th><th>趋势</th></tr></thead><tbody>';
  items.forEach((it, idx) => {
    const growth = Number(it.growth_pct);
    const growthLabel = Number(it.prev_freq) === 0 ? '新上榜' : `${growth.toFixed(1)}%`;
    html += `
      <tr>
        <td><strong>${idx + 1}</strong></td>
        <td><strong>${escapeHtml(it.keyword)}</strong></td>
        <td>${it.recent_freq}</td>
        <td>${it.prev_freq}</td>
        <td>${growthLabel}</td>
        <td><button class="row-action trendBtn" data-keyword="${escapeHtml(it.keyword)}">查看趋势</button></td>
      </tr>
    `;

    if (expandedTrend && expandedTrend.keyword === it.keyword) {
      const trend = expandedTrend.data;
      const trendStart = trend.series && trend.series.length ? trend.series[0].date : '';
      const trendEnd = trend.series && trend.series.length ? trend.series[trend.series.length - 1].date : '';
      html += `
        <tr class="inline-detail">
          <td colspan="6" class="inline-detail-cell">
            <div class="inline-detail-card">
              <div class="inline-detail-head">
                <div>
                  <div class="inline-detail-title">趋势：${escapeHtml(trend.keyword)}</div>
                  <div class="inline-detail-subtitle">
                    趋势区间 ${trendStart || '—'} ~ ${trendEnd || '—'} · 最近 90 天走势
                  </div>
                </div>
                <button class="row-action closeTrendBtn" data-close-keyword="${escapeHtml(it.keyword)}">关闭</button>
              </div>
              <div id="inlineTrendChart" class="chart-shell"></div>
            </div>
          </td>
        </tr>
      `;
    }
  });
  html += '</tbody></table>';
  div.innerHTML = html;

  document.querySelectorAll('.trendBtn').forEach(btn => {
    btn.addEventListener('click', async (e) => {
      const kw = e.target.dataset.keyword;
      await showTrend(kw);
    });
  });

  document.querySelectorAll('.closeTrendBtn').forEach(btn => {
    btn.addEventListener('click', () => {
      expandedTrend = null;
      renderHotList(currentHotItems, currentWindowDays);
    });
  });

  if (expandedTrend && document.getElementById('inlineTrendChart')) {
    drawInlineTrend(expandedTrend.data);
  }
}

function drawInlineTrend(data) {
  const chartEl = document.getElementById('inlineTrendChart');
  if (!chartEl || !data || !data.series || !data.series.length) return;
  disposeInlineChart();
  chartInstance = echarts.init(chartEl);
  chartInstance.setOption({
    grid: { left: 44, right: 24, top: 24, bottom: 40 },
    tooltip: { trigger: 'axis' },
    xAxis: { type: 'category', data: data.series.map(x => x.date), axisLabel: { color: '#6b7280' }, axisLine: { lineStyle: { color: '#d5dbe7' } } },
    yAxis: { type: 'value', axisLabel: { color: '#6b7280' }, splitLine: { lineStyle: { color: '#eef2f7' } } },
    series: [{ type: 'line', smooth: true, data: data.series.map(x => x.freq), symbol: 'circle', symbolSize: 6, lineStyle: { width: 2, color: '#111827' }, itemStyle: { color: '#111827' }, areaStyle: { color: 'rgba(17, 24, 39, 0.06)' } }]
  });
}

async function showTrend(keyword) {
  clearError();
  try {
    const source = getSelectedSource();
    const res = await fetch(`${API_BASE}/trend?keyword=${encodeURIComponent(keyword)}&days=90&source=${encodeURIComponent(source)}`);
    if (!res.ok) {
      const txt = await res.text();
      return showError(`趋势请求失败（HTTP ${res.status}）：${txt || res.statusText}`);
    }
    const data = await res.json();
    if (!data.has_time_data || !data.series || data.series.length === 0) {
      return showError(data.note || '该关键词暂无可解析时间戳数据，无法绘制真实时间轴。');
    }

    expandedTrend = { keyword, data };
    renderHotList(currentHotItems, currentWindowDays);
  } catch (_) {
    showError(await classifyFetchFailure());
  }
}

function escapeHtml(s) {
  return (s + '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

document.getElementById('refreshBtn').addEventListener('click', loadHotKeywords);
document.getElementById('startDate').addEventListener('change', syncDateInputs);
document.getElementById('endDate').addEventListener('change', syncDateInputs);

bindSourceSelector(async () => {
  updateSourceUi();
  await loadHotKeywords();
});

(async () => {
  ensureSourceOptions();
  await loadSourceCatalog();
  updateSourceUi();
  setDateControlBounds(getSelectedSource());
  await loadHotKeywords();
})();
