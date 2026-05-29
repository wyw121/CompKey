const API_BASE = 'http://127.0.0.1:8000'
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
  if (!select) return;
  const current = getSelectedSource();
  select.value = current;
  const label = document.getElementById('currentSourceLabel');
  if (label) label.textContent = getSourceLabel(current);
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

async function loadQuickSeeds() {
  const box = document.getElementById('quickSeeds');
  if (!box) return;
  box.innerHTML = '<span style="color:#888">加载中...</span>';
  try {
    const source = getSelectedSource();
    const res = await fetch(`${API_BASE}/seed_suggestions?limit=12&source=${encodeURIComponent(source)}`);
    if (!res.ok) {
      const txt = await res.text();
      box.innerHTML = `<span style="color:#b91c1c">快捷热词加载失败：${escapeHtml(txt || res.statusText)}</span>`;
      return;
    }
    const payload = await res.json();
    const items = Array.isArray(payload) ? payload : (payload.items || []);
    if (!items.length) {
      box.innerHTML = '<span style="color:#888">暂无可用热词</span>';
      return;
    }
    box.innerHTML = items.map(it => `
      <button class="quickSeedBtn" data-seed="${escapeHtml(it.seed)}" style="padding:6px 10px;border:1px solid #ddd;background:#fafafa;border-radius:16px;cursor:pointer">
        ${escapeHtml(it.seed)}
      </button>
    `).join('');
    box.querySelectorAll('.quickSeedBtn').forEach(btn => {
      btn.addEventListener('click', async () => {
        const seed = btn.dataset.seed || '';
        document.getElementById('seedInput').value = seed;
        await runSearch(seed);
      });
    });
  } catch (err) {
    box.innerHTML = '<span style="color:#b91c1c">快捷热词加载失败</span>';
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
    renderResults(data);
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
    div.innerHTML = '<p>未找到候选词。</p>';
    return;
  }
  let html = '<table><thead><tr><th>候选词</th><th>竞争度</th><th>频次</th><th>PMI</th><th>趋势</th></tr></thead><tbody>';
  for (const it of items) {
    html += `<tr><td>${escapeHtml(it.candidate)}</td><td>${it.competition.toFixed(3)}</td><td>${it.freq}</td><td>${it.pmi.toFixed(3)}</td><td><button class="trendBtn" data-keyword="${escapeHtml(it.candidate)}">查看趋势</button></td></tr>`;
  }
  html += '</tbody></table>';
  div.innerHTML = html;
  document.querySelectorAll('.trendBtn').forEach(b => b.addEventListener('click', async (e) => {
    const kw = e.target.dataset.keyword;
    await showTrend(kw);
  }));
}

async function showTrend(keyword) {
  clearError();
  let data;
  try {
    const source = getSelectedSource();
    const res = await fetch(`${API_BASE}/trend?keyword=${encodeURIComponent(keyword)}&days=90&source=${encodeURIComponent(source)}`);
    if (!res.ok) {
      const txt = await res.text();
      return showError(`趋势请求失败（HTTP ${res.status}）：${txt || res.statusText}`);
    }
    data = await res.json();
  } catch (err) {
    return showError(await classifyFetchFailure(err));
  }

  if (!data.has_time_data || !data.series || data.series.length === 0) {
    return showError(data.note || '该关键词暂无可解析时间戳数据，无法绘制真实时间轴。');
  }

  document.getElementById('trendModal').style.display = 'block';
  const nonZero = data.series.filter(x => Number(x.freq) > 0).length;
  document.getElementById('trendTitle').innerText = `趋势：${data.keyword}（近90天，非零点 ${nonZero}）`;
  const chart = echarts.init(document.getElementById('trendChart'));
  const dates = data.series.map(x => x.date);
  const freqs = data.series.map(x => x.freq);
  const option = {
    xAxis: { type: 'category', data: dates },
    yAxis: { type: 'value' },
    series: [{ type: 'line', data: freqs, smooth: true }]
  };
  chart.setOption(option);
}

document.getElementById('closeTrend').addEventListener('click', () => {
  document.getElementById('trendModal').style.display = 'none';
});

function escapeHtml(s) {
  return (s+'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

bindSourceSelector(async () => {
  updateSourceUi();
  document.getElementById('results').innerHTML = '';
  await loadQuickSeeds();
});
updateSourceUi();
loadQuickSeeds();
