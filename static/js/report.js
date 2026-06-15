async function loadReport() {
  const c = document.getElementById('mdContainer');
  try {
    const resp = await fetch('/api/report/today');
    const data = await resp.json();
    if (!data.success) {
      c.innerHTML = `
        <div class="empty">
          <span class="empty__icon">∅</span>
          <div class="empty__title">${data.error || '简报未生成'}</div>
          <div class="empty__sub">点击右上角「重新生成」或先到首页「立即刷新」</div>
        </div>`;
      return;
    }
    c.innerHTML = `<article class="md-body">${marked.parse(data.content)}</article>`;
    document.getElementById('reportTime').textContent = new Date(data.generated_at).toLocaleString('zh-CN');
  } catch (e) {
    c.innerHTML = `<div class="empty"><span class="empty__icon">!</span><div class="empty__title">加载失败</div><div class="empty__sub">${e.message}</div></div>`;
  }
}

async function refreshReport() {
  const c = document.getElementById('mdContainer');
  c.innerHTML = `<div class="loading"><div class="spinner"></div><div>重新抓取并生成…</div></div>`;
  try {
    await fetch('/api/refresh', { method: 'POST' });
    await loadReport();
  } catch (e) {
    c.innerHTML = `<div class="empty"><span class="empty__icon">!</span><div class="empty__title">刷新失败</div></div>`;
  }
}

document.getElementById('btnRefresh').addEventListener('click', refreshReport);
loadReport();
