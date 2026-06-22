function escapeHtml(s){if(s==null)return'';return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#39;');}

async function loadReport() {
  const c = document.getElementById('mdContainer');
  const userSendkey = localStorage.getItem('pms_sendkey') || '';
  const url = userSendkey
    ? `/api/report/today?sendkey=${encodeURIComponent(userSendkey)}`
    : '/api/report/today';
  try {
    const resp = await fetch(url);
    const data = await resp.json();
    if (!data.success) {
      c.innerHTML = `
        <div class="empty">
          <span class="empty__icon">∅</span>
          <div class="empty__title">${escapeHtml(data.error || '简报未生成')}</div>
          <div class="empty__sub">点击右上角「重新生成」或先到首页「立即刷新」</div>
        </div>`;
      return;
    }
    let html = '';
    // 令牌方案：个性化简报区块
    if (data.personalized && data.personalized.news_list && data.personalized.news_list.length > 0) {
      const p = data.personalized;
      html += `<div style="background: var(--surface-2, #f5f5f5); border-left: 3px solid var(--gold, #c9a86a); border-radius: 4px; padding: 16px 20px; margin-bottom: 24px;">
        <div style="font-size: 13px; color: var(--gold, #c9a86a); margin-bottom: 8px; letter-spacing: 0.05em;">📌 你的关注板块</div>
        <div style="font-size: 15px; margin-bottom: 12px;">${escapeHtml(p.sectors.join(' · '))}</div>
        <div style="font-size: 13px; color: var(--ink-3, #999); margin-bottom: 12px;">共 ${escapeHtml(String(p.count))} 条匹配资讯</div>
        <ul style="list-style: none; padding: 0; margin: 0;">
          ${p.news_list.slice(0, 5).map(n => `<li style="padding: 4px 0; font-size: 13px;">· ${escapeHtml(n.title || '')}</li>`).join('')}
        </ul>
      </div>`;
    }
    html += `<article class="md-body">${marked.parse(data.content)}</article>`;
    c.innerHTML = html;
    document.getElementById('reportTime').textContent = new Date(data.generated_at).toLocaleString('zh-CN');
  } catch (e) {
    c.innerHTML = `<div class="empty"><span class="empty__icon">!</span><div class="empty__title">加载失败</div><div class="empty__sub">${escapeHtml(e.message)}</div></div>`;
  }
}

async function refreshReport() {
  const c = document.getElementById('mdContainer');
  c.innerHTML = `<div class="loading"><div class="spinner"></div><div>重新抓取并生成…</div></div>`;
  try {
    const userSendkey = localStorage.getItem('pms_sendkey') || '';
    await fetch('/api/refresh', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ sendkey: userSendkey })
    });
    await loadReport();
  } catch (e) {
    c.innerHTML = `<div class="empty"><span class="empty__icon">!</span><div class="empty__title">刷新失败</div></div>`;
  }
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', () => {
    document.getElementById('btnRefresh').addEventListener('click', refreshReport);
    loadReport();
  });
} else {
  document.getElementById('btnRefresh').addEventListener('click', refreshReport);
  loadReport();
}
