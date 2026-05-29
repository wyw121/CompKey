const API_BASE = 'http://127.0.0.1:8000';
const SOURCE_STORAGE_KEY = 'compkeyDemoSource';

function getSelectedSource() {
  return localStorage.getItem(SOURCE_STORAGE_KEY) || 'edgar';
}

function setSelectedSource(source) {
  localStorage.setItem(SOURCE_STORAGE_KEY, source);
}

function getSourceLabel(source) {
  return source === 'aol' ? 'AOL demo' : 'EDGAR demo';
}

function updateSourceUi() {
  const select = document.getElementById('demoSource');
  if (select) select.value = getSelectedSource();
}

function bindSourceSelector(onChange) {
  const select = document.getElementById('demoSource');
  if (!select) return;
  select.value = getSelectedSource();
  select.addEventListener('change', async () => {
    setSelectedSource(select.value);
    updateSourceUi();
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

async function loadHotKeywords() {
  clearError();
  const limit = Number(document.getElementById('limit').value);
  const windowDays = Number(document.getElementById('windowDays').value);
  try {
    const source = getSelectedSource();
    const url = `${API_BASE}/hot_keywords?limit=${limit}&window_days=${windowDays}&source=${encodeURIComponent(source)}`;
    const res = await fetch(url);
    if (!res.ok) {
      const txt = await res.text();
      return showError(`加载榜单失败（HTTP ${res.status}）：${txt || res.statusText}`);
    }
    const payload = await res.json();
    const items = Array.isArray(payload) ? payload : (payload.items || []);
    renderHotList(items, windowDays);
    const source = Array.isArray(payload) ? getSourceLabel(getSelectedSource()) : (payload.source || getSourceLabel(getSelectedSource()));
    const range = Array.isArray(payload)
      ? '未知'
      : `${payload.date_range?.start || '未知'} ~ ${payload.date_range?.end || '未知'}`;
    document.getElementById('dataSource').textContent = source;
    document.getElementById('dataRange').textContent = range;
    document.getElementById('updatedAt').textContent = new Date().toLocaleString();
  } catch (e) {
    showError(await classifyFetchFailure());
  }
}

function renderHotList(items, windowDays) {
  const div = document.getElementById('hotList');
  if (!items || items.length === 0) {
    div.innerHTML = '<p>当前暂无流行关键词数据。</p>';
    return;
  }
  let html = `<table><thead><tr><th>排名</th><th>关键词</th><th>最近${windowDays}天搜索量</th><th>前${windowDays}天搜索量</th><th>增长率</th><th>趋势</th></tr></thead><tbody>`;
  items.forEach((it, idx) => {
    const growth = Number(it.growth_pct);
    const growthLabel = Number(it.prev_freq) === 0 ? '新上榜' : `${growth.toFixed(1)}%`;
    html += `<tr>
      <td>${idx + 1}</td>
      <td>${escapeHtml(it.keyword)}</td>
      <td>${it.recent_freq}</td>
      <td>${it.prev_freq}</td>
      <td>${growthLabel}</td>
      <td><button class="trendBtn" data-keyword="${escapeHtml(it.keyword)}">查看</button></td>
    </tr>`;
  });
  html += '</tbody></table>';
  div.innerHTML = html;

  document.querySelectorAll('.trendBtn').forEach(btn => {
    btn.addEventListener('click', async (e) => {
      const kw = e.target.dataset.keyword;
      await showTrend(kw);
    });
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

    document.getElementById('trendPanel').style.display = 'block';
    document.getElementById('trendTitle').textContent = `趋势：${data.keyword}（近90天）`;

    const chart = echarts.init(document.getElementById('trendChart'));
    chart.setOption({
      xAxis: { type: 'category', data: data.series.map(x => x.date) },
      yAxis: { type: 'value' },
      series: [{ type: 'line', smooth: true, data: data.series.map(x => x.freq) }]
    });
  } catch (_) {
    showError(await classifyFetchFailure());
  }
}

function escapeHtml(s) {
  return (s + '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

document.getElementById('refreshBtn').addEventListener('click', loadHotKeywords);
bindSourceSelector(async () => {
  updateSourceUi();
  await loadHotKeywords();
});
updateSourceUi();
loadHotKeywords();
