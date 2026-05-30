const API_BASE = 'http://127.0.0.1:8000'
const SOURCE_STORAGE_KEY = 'compkeyDemoSource';
const SOURCE_OPTIONS = [
  { value: 'p4', label: 'P4 主库' },
  { value: 'aol', label: 'AOL demo' },
];
let sourceCatalog = {};
let volumeChartInstance = null;
let resultChartInstance = null;
let currentResultItems = [];
let expandedResultTrend = null;
let volumeLoadSeq = 0;

function normalizeSource(source) {
  const key = String(source || 'p4').trim().toLowerCase();
  return ['p4', 'aol'].includes(key) ? key : 'p4';
}

function getSourceMeta(source) {
  return sourceCatalog[normalizeSource(source)] || {
    source: normalizeSource(source),
    label: getSourceLabel(source),
    description: '',
  };
}

async function loadSourceCatalog() {
  try {
    const res = await fetch(`${API_BASE}/sources`);
    if (!res.ok) return;
    const payload = await res.json();
    sourceCatalog = {};
    for (const item of payload.items || []) {
      sourceCatalog[item.source] = item;
    }
    renderSourceSelector();
    updateSourceUi();
  } catch (_) {
    sourceCatalog = {};
    renderSourceSelector();
  }
}

function renderSourceSelector() {
  const select = document.getElementById('demoSourceTop');
  if (!select) return;
  const options = SOURCE_OPTIONS
    .map(item => {
      const meta = sourceCatalog[item.value];
      return {
        value: item.value,
        label: meta?.label || item.label,
      };
    });
  select.innerHTML = options.map(item => `<option value="${escapeHtml(item.value)}">${escapeHtml(item.label)}</option>`).join('');
  select.value = getSelectedSource();
}

function updateSourceCards() {
  const current = getSelectedSource();
  const meta = getSourceMeta(current);
  const badge = document.getElementById('currentSourceLabel');
  const badgeCard = document.getElementById('currentSourceLabelCard');
  const desc = document.getElementById('currentSourceDesc');
  if (badge) badge.textContent = meta.label || getSourceLabel(current);
  if (badgeCard) badgeCard.textContent = meta.label || getSourceLabel(current);
  if (desc) desc.textContent = meta.description || '暂无说明';
}

function updateVolumeSummary(payload) {
  const totalEl = document.getElementById('totalVolumeCount');
  const activeEl = document.getElementById('activeDaysCount');
  const peakEl = document.getElementById('peakDateLabel');
  if (totalEl) totalEl.textContent = String(payload?.total_volume ?? '--');
  if (activeEl) activeEl.textContent = String(payload?.active_days ?? '--');
  if (peakEl) peakEl.textContent = payload?.peak_day || '--';
}

function disposeVolumeChart() {
  if (volumeChartInstance) {
    volumeChartInstance.dispose();
    volumeChartInstance = null;
  }
}

function renderVolumeChart(payload) {
  const box = document.getElementById('dataVolumeChart');
  const status = document.getElementById('volumeStatus');
  if (!box) return;
  disposeVolumeChart();
  updateVolumeSummary(payload);
  if (!payload || !Array.isArray(payload.series) || payload.series.length === 0) {
    box.innerHTML = '<div class="empty-state">暂无可展示的数据量趋势。</div>';
    if (status) status.textContent = '无数据';
    return;
  }

  if (status) status.textContent = `${payload.source || '数据源'} · ${payload.date_range?.start || '--'} ~ ${payload.date_range?.end || '--'}`;

  const chart = echarts.init(box);
  volumeChartInstance = chart;
  const dates = payload.series.map(item => item.date);
  const volumes = payload.series.map(item => item.total_volume || 0);
  chart.setOption({
    grid: { left: 48, right: 24, top: 26, bottom: 44 },
    tooltip: { trigger: 'axis' },
    xAxis: {
      type: 'category',
      data: dates,
      axisLabel: { color: '#6b7280' },
      axisLine: { lineStyle: { color: '#d5dbe7' } },
    },
    yAxis: {
      type: 'value',
      axisLabel: { color: '#6b7280' },
      splitLine: { lineStyle: { color: '#eef2f7' } },
    },
    series: [{
      type: 'line',
      data: volumes,
      smooth: true,
      symbol: 'circle',
      symbolSize: 7,
      lineStyle: { width: 3, color: '#111827' },
      itemStyle: { color: '#111827' },
      areaStyle: { color: 'rgba(17, 24, 39, 0.08)' },
    }],
  });
  requestAnimationFrame(() => {
    if (volumeChartInstance) volumeChartInstance.resize();
  });
}

async function loadVolumeTrend() {
  const box = document.getElementById('dataVolumeChart');
  const status = document.getElementById('volumeStatus');
  if (!box) return;
  const loadSeq = ++volumeLoadSeq;
  disposeVolumeChart();
  box.innerHTML = '<div class="empty-state">加载中...</div>';
  if (status) status.textContent = '加载中...';
  try {
    const source = getSelectedSource();
    const res = await fetch(`${API_BASE}/source_volume?source=${encodeURIComponent(source)}`);
    if (loadSeq !== volumeLoadSeq || source !== getSelectedSource()) return;
    if (!res.ok) {
      const txt = await res.text();
      box.innerHTML = `<div class="empty-state">数据量趋势加载失败：${escapeHtml(txt || res.statusText)}</div>`;
      if (status) status.textContent = '加载失败';
      updateVolumeSummary(null);
      return;
    }
    const payload = await res.json();
    renderVolumeChart(payload);
  } catch (err) {
    if (loadSeq !== volumeLoadSeq) return;
    box.innerHTML = '<div class="empty-state">数据量趋势加载失败</div>';
    if (status) status.textContent = '加载失败';
    updateVolumeSummary(null);
  }
}

function setQuickCount(count) {
  const el = document.getElementById('quickSeedCount');
  if (el) el.textContent = String(count);
}

function setResultCount(count) {
  const el = document.getElementById('resultCount');
  if (el) el.textContent = String(count);
}

function setLastUpdated() {
  const el = document.getElementById('lastUpdated');
  if (el) el.textContent = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

function getSelectedSource() {
  return normalizeSource(localStorage.getItem(SOURCE_STORAGE_KEY));
}

function setSelectedSource(source) {
  localStorage.setItem(SOURCE_STORAGE_KEY, normalizeSource(source));
}

function getSourceLabel(source) {
  if (source === 'aol') return 'AOL demo';
  return 'P4 主库';
}

function updateSourceUi() {
  const select = document.getElementById('demoSourceTop');
  if (!select) return;
  const current = getSelectedSource();
  select.value = current;
  updateSourceCards();
}

function bindSourceSelector(onChange) {
  const select = document.getElementById('demoSourceTop');
  if (!select) return;
  select.value = getSelectedSource();
  select.addEventListener('change', async () => {
    setSelectedSource(select.value);
    updateSourceUi();
    volumeLoadSeq += 1;
    disposeVolumeChart();
    currentResultItems = [];
    expandedResultTrend = null;
    const results = document.getElementById('results');
    if (results) results.innerHTML = '';
    setResultCount(0);
    if (typeof onChange === 'function') {
      await onChange(select.value);
    }
    currentResultItems = [];
    expandedResultTrend = null;
    if (results) results.innerHTML = '';
    setResultCount(0);
    setTimeout(() => setResultCount(0), 0);
  });
}

async function loadQuickSeeds() {
  const box = document.getElementById('quickSeeds');
  if (!box) return;
  box.innerHTML = '<span class="muted">加载中...</span>';
  try {
    const source = getSelectedSource();
    const res = await fetch(`${API_BASE}/seed_suggestions?limit=12&source=${encodeURIComponent(source)}`);
    if (!res.ok) {
      const txt = await res.text();
      box.innerHTML = `<span class="muted" style="color:#b42318">快捷热词加载失败：${escapeHtml(txt || res.statusText)}</span>`;
      setQuickCount(0);
      return;
    }
    const payload = await res.json();
    const items = Array.isArray(payload) ? payload : (payload.items || []);
    if (!items.length) {
      box.innerHTML = '<span class="muted">暂无可用热词</span>';
      setQuickCount(0);
      return;
    }
    box.innerHTML = items.map(it => `
      <button class="quickSeedBtn" data-seed="${escapeHtml(it.seed)}">
        ${escapeHtml(it.seed)}
      </button>
    `).join('');
    setQuickCount(items.length);
    box.querySelectorAll('.quickSeedBtn').forEach(btn => {
      btn.addEventListener('click', async () => {
        const seed = btn.dataset.seed || '';
        document.getElementById('seedInput').value = seed;
        await runSearch(seed);
      });
    });
    setLastUpdated();
  } catch (err) {
    box.innerHTML = '<span class="muted" style="color:#b42318">快捷热词加载失败</span>';
    setQuickCount(0);
  }
}

function showError(message) {
  const box = document.getElementById('errorBox');
  if (!box) return alert(message);
  box.style.display = 'block';
  box.textContent = message;
}

function clearError() {
  const box = document.getElementById('errorBox');
  if (!box) return;
  box.style.display = 'none';
  box.textContent = '';
}

async function classifyFetchFailure(originalError) {
  // 1) 离线网络
  if (navigator && navigator.onLine === false) {
    return '网络失败：当前设备离线，请检查网络连接后重试。';
  }
  // 2) 后端可达性探测（no-cors 可用于区分“完全不可达”）
  try {
    await fetch(`${API_BASE}/health`, { mode: 'no-cors', cache: 'no-store' });
    // 能探测到后端网络路径，大概率是 CORS 或浏览器安全策略
    return '跨域被阻止：前端已访问到后端地址，但浏览器拒绝跨域响应。请确认后端已启用 CORS 且允许 http://127.0.0.1:8001。';
  } catch (_) {
    return '后端未启动或不可达：请确认 API 服务运行在 http://127.0.0.1:8000。';
  }
}

async function runSearch(seedOverride) {
  clearError();
  const seed = (seedOverride ?? document.getElementById('seedInput').value).trim();
  if (!seed) return showError('请输入种子词后再查询。');
  try {
    const source = getSelectedSource();
    const res = await fetch(`${API_BASE}/recommend?seed=${encodeURIComponent(seed)}&top=20&source=${encodeURIComponent(source)}`);
    if (!res.ok) {
      const txt = await res.text();
      return showError(`查询失败（HTTP ${res.status}）：${txt || res.statusText}`);
    }
    const data = await res.json();
    currentResultItems = Array.isArray(data) ? data : [];
    expandedResultTrend = null;
    renderResults(currentResultItems);
    setResultCount(Array.isArray(data) ? data.length : 0);
    setLastUpdated();
  } catch (err) {
    showError(await classifyFetchFailure(err));
  }
}

document.getElementById('searchBtn').addEventListener('click', async () => {
  await runSearch();
});

function renderResults(items) {
  const div = document.getElementById('results');
  if (!items || items.length === 0) {
    div.innerHTML = '<div class="empty-state">未找到候选词。</div>';
    return;
  }
  let html = '<table><thead><tr><th>候选词</th><th>竞争度</th><th>频次</th><th>PMI</th><th>趋势</th></tr></thead><tbody>';
  for (const it of items) {
    const cand = it.candidate;
    html += `<tr><td><strong>${escapeHtml(cand)}</strong></td><td>${Number(it.competition).toFixed(3)}</td><td>${it.freq}</td><td>${Number(it.pmi).toFixed(3)}</td><td><button class="row-action trendBtn" data-keyword="${escapeHtml(cand)}">查看趋势</button></td></tr>`;
    if (expandedResultTrend && expandedResultTrend.keyword === cand) {
      const growth = expandedResultTrend.data;
      const trendStart = growth.series && growth.series.length ? growth.series[0].date : '';
      const trendEnd = growth.series && growth.series.length ? growth.series[growth.series.length - 1].date : '';
      html += `
        <tr class="inline-detail">
          <td colspan="5" class="inline-detail-cell">
            <div class="inline-detail-card">
              <div class="inline-detail-head">
                <div>
                  <div class="inline-detail-title">趋势：${escapeHtml(growth.keyword)}</div>
                  <div class="inline-detail-subtitle">趋势区间 ${trendStart || '—'} ~ ${trendEnd || '—'} · 最近 90 天走势</div>
                </div>
                <button class="row-action closeTrendBtn" data-close-keyword="${escapeHtml(cand)}">关闭</button>
              </div>
              <div id="inlineResultTrendChart" class="chart-shell"></div>
            </div>
          </td>
        </tr>
      `;
    }
  }
  html += '</tbody></table>';
  div.innerHTML = html;
  document.querySelectorAll('.trendBtn').forEach(b => b.addEventListener('click', async (e) => {
    const kw = e.target.dataset.keyword;
    await showTrend(kw);
  }));
  document.querySelectorAll('.closeTrendBtn').forEach(btn => {
    btn.addEventListener('click', () => {
      expandedResultTrend = null;
      renderResults(currentResultItems);
    });
  });
  if (expandedResultTrend && document.getElementById('inlineResultTrendChart')) {
    drawInlineResultTrend(expandedResultTrend.data);
  }
}

function drawInlineResultTrend(data) {
  const chartEl = document.getElementById('inlineResultTrendChart');
  if (!chartEl || !data || !data.series || !data.series.length) return;
  if (resultChartInstance) {
    resultChartInstance.dispose();
    resultChartInstance = null;
  }
  resultChartInstance = echarts.init(chartEl);
  resultChartInstance.setOption({
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
    expandedResultTrend = { keyword, data };
    renderResults(currentResultItems);
  } catch (err) {
    return showError(await classifyFetchFailure(err));
  }
}

window.addEventListener('resize', () => {
  if (volumeChartInstance) volumeChartInstance.resize();
  if (resultChartInstance) resultChartInstance.resize();
});

function escapeHtml(s) {
  return (s+'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

bindSourceSelector(async () => {
  updateSourceUi();
  document.getElementById('results').innerHTML = '';
  currentResultItems = [];
  expandedResultTrend = null;
  await loadQuickSeeds();
  await loadVolumeTrend();
});

window.addEventListener('resize', () => {
  if (volumeChartInstance) volumeChartInstance.resize();
});

(async () => {
  await loadSourceCatalog();
  updateSourceUi();
  await loadQuickSeeds();
  await loadVolumeTrend();
})();
