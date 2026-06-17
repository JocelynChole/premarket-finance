/* ============================================================
   盘前财经资讯研判智能体 - 首页逻辑
   ============================================================ */

const state = {
  allNews: [],
  filters: {
    sector: 'all',
    sentiment: 'all',
    date: 'all',
    minImportance: 0,
    search: '',
  },
};

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

// ============== 时钟 + 倒计时 ==============
function pad(n) { return n.toString().padStart(2, '0'); }

function updateClock() {
  const now = new Date();
  const h = pad(now.getHours());
  const m = pad(now.getMinutes());
  const s = pad(now.getSeconds());
  const dateStr = `${now.getFullYear()}/${pad(now.getMonth() + 1)}/${pad(now.getDate())}`;
  $('#liveClock').textContent = `${h}:${m}:${s}`;
  $('#liveDate').textContent = dateStr;
}

function updateCountdown() {
  const now = new Date();
  const target = new Date(now);
  target.setHours(9, 30, 0, 0);
  if (now >= target) {
    $('#cdLabel').textContent = '已开盘 · 今日盘前窗口已关闭';
    $('#cdH').textContent = '00';
    $('#cdM').textContent = '00';
    $('#cdS').textContent = '00';
    return;
  }
  const diff = Math.floor((target - now) / 1000);
  const h = Math.floor(diff / 3600);
  const m = Math.floor((diff % 3600) / 60);
  const s = diff % 60;
  $('#cdH').textContent = pad(h);
  $('#cdM').textContent = pad(m);
  $('#cdS').textContent = pad(s);
}

setInterval(() => { updateClock(); updateCountdown(); }, 1000);
updateClock(); updateCountdown();

// ============== 数据加载 ==============

async function loadNews() {
  try {
    const resp = await fetch('/api/news');
    const data = await resp.json();
    if (data.success === false && data.error) {
      showEmpty(data.error);
      return;
    }
    state.allNews = data.news_list || [];
    renderAll(data);
  } catch (err) {
    showEmpty('加载失败：' + err.message);
  }
}

async function refreshNews() {
  const grid = $('#newsGrid');
  const heat = $('#heatmap');
  grid.innerHTML = `<div class="loading"><div class="spinner"></div><div>正在抓取并分析财经资讯…</div></div>`;
  heat.innerHTML = `<div class="loading" style="grid-column: 1/-1;"><div class="spinner"></div><div>计算板块热度…</div></div>`;
  try {
    // 如果用户已订阅（localStorage 里有 sendkey），附带发到后端
    // 后端会额外推送给该用户一次
    const userSendkey = localStorage.getItem('pms_sendkey') || '';
    const resp = await fetch('/api/refresh', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ sendkey: userSendkey })
    });
    const data = await resp.json();
    if (data.success) {
      state.allNews = data.news_list || [];
      renderAll(data);
      // 提示用户：如果是订阅用户，微信会收到推送
      if (userSendkey && data.personal_push) {
        if (data.personal_push.success) {
          flash('✅ 微信推送成功，请检查微信', true);
        } else {
          flash('微信推送失败：' + (data.personal_push.message || '未知错误'), false);
        }
      }
    } else {
      showEmpty(data.error || '刷新失败，请先启动 china-finance-rss 服务');
    }
  } catch (err) {
    showEmpty('刷新失败：' + err.message);
  }
}

function showEmpty(msg) {
  $('#newsGrid').innerHTML = `
    <div class="empty" style="grid-column: 1/-1;">
      <span class="empty__icon">∅</span>
      <div class="empty__title">暂无今日资讯</div>
      <div class="empty__sub">${msg || '请点击右上角「立即刷新」开始首次抓取'}</div>
    </div>`;
  $('#heatmap').innerHTML = `
    <div class="empty" style="grid-column: 1/-1;">
      <span class="empty__icon">⊕</span>
      <div class="empty__title">板块热度待生成</div>
      <div class="empty__sub">完成抓取后这里将显示 12 板块的热力分布</div>
    </div>`;
}

// ============== 渲染 ==============

function renderAll(data) {
  renderStats(data);
  renderHeatmap(data);
  applyFilters();
}

function renderStats(data) {
  const news = data.news_list || [];
  const bullish = news.filter(n => n.sentiment === '利好').length;
  const bearish = news.filter(n => n.sentiment === '利空').length;

  $('#statCount').textContent = news.length;

  // 板块数
  const sectorSet = new Set();
  news.forEach(n => (n.sectors || []).forEach(s => sectorSet.add(s)));
  const sectorArr = Array.from(sectorSet).filter(s => s !== '其他');
  $('#statSectors').textContent = sectorArr.length || 0;
  $('#statSectorList').textContent = sectorArr.slice(0, 3).join(' · ') || '—';

  // 情绪
  const total = bullish + bearish;
  if (total === 0) {
    $('#statSentiment').textContent = '—';
    $('#statSentiment').className = 'stat__value';
  } else if (bullish > bearish * 1.5) {
    $('#statSentiment').textContent = '↑ 乐观';
    $('#statSentiment').className = 'stat__value stat__value--bull';
    $('#statSentimentSub').textContent = `利好 ${bullish} / 利空 ${bearish}`;
  } else if (bearish > bullish * 1.5) {
    $('#statSentiment').textContent = '↓ 谨慎';
    $('#statSentiment').className = 'stat__value stat__value--bear';
    $('#statSentimentSub').textContent = `利空 ${bearish} / 利好 ${bullish}`;
  } else {
    $('#statSentiment').textContent = '→ 中性';
    $('#statSentiment').className = 'stat__value';
    $('#statSentimentSub').textContent = `利好 ${bullish} / 利空 ${bearish}`;
  }

  // 更新于
  if (data.analyzed_at) {
    const t = new Date(data.analyzed_at);
    $('#statTime').textContent = `${pad(t.getHours())}:${pad(t.getMinutes())}`;
  } else {
    $('#statTime').textContent = '—';
  }

  // 副标题
  $('#statSubtitle').textContent = news.length > 0
    ? `基于 ${news.length} 条预测类资讯`
    : '请先点击刷新';
}

function renderHeatmap(data) {
  const news = data.news_list || [];
  const sectorCount = {};
  news.forEach(n => (n.sectors || []).forEach(s => {
    if (s !== '其他') sectorCount[s] = (sectorCount[s] || 0) + 1;
  }));

  const sectors = Object.entries(sectorCount).sort((a, b) => b[1] - a[1]);
  if (sectors.length === 0) {
    $('#heatmap').innerHTML = `
      <div class="empty" style="grid-column: 1/-1;">
        <span class="empty__icon">⊕</span>
        <div class="empty__title">无板块数据</div>
        <div class="empty__sub">完成抓取后这里将显示 12 板块的热力分布</div>
      </div>`;
    return;
  }

  const max = sectors[0][1];
  $('#heatmap').innerHTML = sectors.map(([name, count]) => {
    const heatStrength = Math.min(count / Math.max(max, 1), 1) * 0.5 + 0.08;
    return `
      <div class="heatmap__cell" data-sector="${name}"
           style="--heat-color: var(--gold); --heat-strength: ${heatStrength};">
        <div class="heatmap__name">${name}</div>
        <div class="heatmap__count">${count}</div>
      </div>
    `;
  }).join('');

  $$('#heatmap .heatmap__cell').forEach(cell => {
    cell.addEventListener('click', () => {
      const sector = cell.dataset.sector;
      if (state.filters.sector === sector) {
        state.filters.sector = 'all';
        cell.classList.remove('is-active');
      } else {
        state.filters.sector = sector;
        $$('#heatmap .heatmap__cell').forEach(c => c.classList.remove('is-active'));
        cell.classList.add('is-active');
      }
      applyFilters();
    });
  });
}

// ============== 资讯流 ==============

function applyFilters() {
  // 计算前一日/当日的日期字符串（与后端无关，仅前端过滤）
  const now = new Date();
  const padN = (n) => String(n).padStart(2, '0');
  const todayStr    = `${now.getFullYear()}-${padN(now.getMonth() + 1)}-${padN(now.getDate())}`;
  const yestDate    = new Date(now.getTime() - 24 * 3600 * 1000);
  const yestStr     = `${yestDate.getFullYear()}-${padN(yestDate.getMonth() + 1)}-${padN(yestDate.getDate())}`;

  const filtered = state.allNews.filter(news => {
    if (state.filters.sector !== 'all' && !(news.sectors || []).includes(state.filters.sector)) return false;
    if (state.filters.sentiment !== 'all' && news.sentiment !== state.filters.sentiment) return false;
    if ((news.importance_score || 0) < state.filters.minImportance) return false;
    if (state.filters.date !== 'all' && news.pub_date) {
      if (state.filters.date === 'today'     && news.pub_date !== todayStr) return false;
      if (state.filters.date === 'yesterday' && news.pub_date !== yestStr)  return false;
    }
    if (state.filters.search) {
      const q = state.filters.search.toLowerCase();
      const text = `${news.title || ''} ${news.content || ''}`.toLowerCase();
      if (!text.includes(q)) return false;
    }
    return true;
  });
  renderNews(filtered);
}

function renderNews(newsList) {
  const container = $('#newsGrid');
  if (newsList.length === 0) {
    container.innerHTML = `
      <div class="empty" style="grid-column: 1/-1;">
        <span class="empty__icon">∅</span>
        <div class="empty__title">没有符合条件的资讯</div>
        <div class="empty__sub">试着调整板块 / 情绪 / 重要度筛选</div>
      </div>`;
    return;
  }

  container.innerHTML = newsList.map((news, i) => {
    const sentClass = news.sentiment === '利好' ? 'news-card--bull'
                    : news.sentiment === '利空' ? 'news-card--bear'
                    : 'news-card--neutral';
    const sectorTags = (news.sectors || []).slice(0, 3).map(s =>
      `<span class="tag tag--gold">${s}</span>`).join('');
    const importance = news.importance_score || 0;
    const filledBars = Math.min(10, Math.max(0, importance));
    const highBars = importance >= 8 ? 'is-high' : (importance < 4 ? 'is-low' : '');
    const bars = Array.from({ length: 10 }, (_, k) =>
      `<span class="score__bar ${k < filledBars ? 'score__bar--filled ' + highBars : ''}"></span>`
    ).join('');

    // 使用新时间字段
    const tf = formatTimeFields(news);
    const dateLabel = tf.date ? `<span class="news-card__date">${tf.date}</span> ` : '';
    const timeLabel = tf.time ? `<span>${tf.time}</span>` : '<span>--</span>';
    const weekdayLabel = tf.weekday ? `<span class="news-card__weekday">${tf.weekday}</span>` : '';

    return `
      <article class="news-card ${sentClass}" data-date="${tf.date}">
        <div class="news-card__meta">
          <span class="dot">●</span>
          ${dateLabel}
          ${timeLabel}
          ${weekdayLabel}
          <span>·</span>
          <span>${news.source || ''}</span>
          <span style="margin-left: auto;" class="score">
            <span class="score__bars">${bars}</span>
            <span>${importance}/10</span>
          </span>
        </div>
        <h3 class="news-card__title">${escapeHtml(news.title || '')}</h3>
        <div class="news-card__tags">
          ${sectorTags}
          ${news.news_type ? `<span class="tag tag--ghost">${news.news_type}</span>` : ''}
          ${news.var_type && news.var_type !== '既定事实' && news.var_type !== '非A股' ? `<span class="tag tag--ghost">${news.var_type}</span>` : ''}
        </div>
        <p class="news-card__summary">${escapeHtml(truncate(news.content || news.summary || '', 220))}</p>
        <div class="news-card__footer">
          <span class="news-card__advice">${news.advice || news.sentiment || '—'}</span>
          ${news.link ? `<a class="news-card__link" href="${news.link}" target="_blank" rel="noopener">查看原文</a>` : ''}
        </div>
      </article>
    `;
  }).join('');
}

function formatTime(pubTime) {
  if (!pubTime) return '';
  try {
    // 处理 RFC 822 格式
    if (pubTime.includes('GMT')) {
      const d = new Date(pubTime);
      if (!isNaN(d.getTime())) {
        return `${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
      }
    }
    // 已经是 YYYY-MM-DD HH:MM:SS
    const m = pubTime.match(/(\d{4})[-\/](\d{2})[-\/](\d{2})\s+(\d{2}):(\d{2})/);
    if (m) return `${m[2]}-${m[3]} ${m[4]}:${m[5]}`;
    return pubTime.substring(0, 16);
  } catch (e) { return pubTime; }
}

// 优先使用后端已解析的字段；若缺失再用 pub_time 字符串解析
function formatTimeFields(news) {
  if (news.pub_display) {
    return {
      date:      news.pub_date        || '',
      time:      news.pub_time_of_day || '',
      weekday:   news.pub_weekday     || '',
      display:   news.pub_display,
    };
  }
  return {
    date:    '',
    time:    formatTime(news.pub_time),
    weekday: '',
    display: formatTime(news.pub_time),
  };
}

function truncate(s, n) {
  if (!s) return '';
  return s.length > n ? s.substring(0, n) + '…' : s;
}

function escapeHtml(s) {
  if (s == null) return '';
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

// ============== 事件绑定 ==============

$('#btnRefresh').addEventListener('click', refreshNews);

$$('.pill[data-sentiment]').forEach(btn => {
  btn.addEventListener('click', () => {
    $$('.pill[data-sentiment]').forEach(b => b.classList.remove('is-active'));
    btn.classList.add('is-active');
    state.filters.sentiment = btn.dataset.sentiment;
    applyFilters();
  });
});

$$('.pill[data-date]').forEach(btn => {
  btn.addEventListener('click', () => {
    $$('.pill[data-date]').forEach(b => b.classList.remove('is-active'));
    btn.classList.add('is-active');
    state.filters.date = btn.dataset.date;
    applyFilters();
  });
});

$$('.pill[data-min-imp]').forEach(btn => {
  btn.addEventListener('click', () => {
    $$('.pill[data-min-imp]').forEach(b => b.classList.remove('is-active'));
    btn.classList.add('is-active');
    state.filters.minImportance = parseInt(btn.dataset.minImp, 10);
    applyFilters();
  });
});

let searchTimer;
$('#searchInput').addEventListener('input', (e) => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(() => {
    state.filters.search = e.target.value.trim();
    applyFilters();
  }, 200);
});

// 启动
document.addEventListener('DOMContentLoaded', () => {
  const now = new Date();
  $('#heroDate').textContent = `${now.getFullYear()}年${now.getMonth() + 1}月${now.getDate()}日 · ${['星期日','星期一','星期二','星期三','星期四','星期五','星期六'][now.getDay()]}`;
  loadNews();
});
