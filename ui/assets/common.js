const PAGE_SIZE = 25;

const API = {
  summary: '/api/summary',
  hits: (page = 1, limit = PAGE_SIZE) => `/api/hits/recent?limit=${limit}&offset=${(page - 1) * limit}`,
  alerts: (page = 1, limit = PAGE_SIZE) => `/api/alerts/recent?limit=${limit}&offset=${(page - 1) * limit}`,
  pages: (limit = 100) => `/api/pages/recent?limit=${limit}`,
  targets: '/api/targets',
  watchlist: '/api/watchlist',
  extracted: (limit = 150) => `/api/extracted/recent?limit=${limit}`,
};

const NAV = [
  { key: 'overview',      href: '/',                        label: 'Overview',          section: 'overview' },
  { key: 'hits',          href: '/ui/hits.html',            label: 'Hits',              section: 'overview' },
  { key: 'alerts',        href: '/ui/alerts.html',          label: 'Alerts',            section: 'overview' },
  { key: 'pages',         href: '/ui/pages.html',           label: 'Pages',             section: 'overview' },
  { key: 'targets',       href: '/ui/targets.html',         label: 'Targets',           section: 'analysis' },
  { key: 'watchlist',     href: '/ui/watchlist.html',       label: 'Watchlist',         section: 'analysis' },
  { key: 'investigation', href: '/ui/investigation.html',   label: 'Investigation',     section: 'analysis' },
  { key: 'graph',         href: '/ui/graph.html',           label: 'Graph',             section: 'analysis' },
  { key: 'analytics',     href: '/ui/analytics.html',       label: 'Analytics',         section: 'analysis' },
  { key: 'rl-dashboard',      href: '/ui/rl_dashboard.html',      label: 'Ransomware.live',   section: 'tracking' },
  { key: 'ransomware-groups', href: '/ui/ransomware_groups.html', label: 'Ransomware Groups', section: 'tracking' },
  { key: 'victims',           href: '/ui/victims.html',           label: 'Victims',           section: 'tracking' },
  { key: 'crypto-wallet',     href: '/ui/crypto_wallet.html',     label: 'Crypto Wallet',     section: 'tracking' },
  { key: 'telegram',          href: '/ui/telegram.html',          label: 'Telegram',          section: 'tracking' },
  { key: 'incidents',         href: '/ui/incidents.html',         label: 'Incidents',         section: 'tracking' },
];

const $ = (s) => document.querySelector(s);
const $$ = (s) => Array.from(document.querySelectorAll(s));

const THEME_KEY = 'dm_ui_theme';
function getSavedTheme() {
  const saved = localStorage.getItem(THEME_KEY);
  return saved === 'light' ? 'light' : 'dark';
}
function applyTheme(theme = getSavedTheme()) {
  document.documentElement.setAttribute('data-theme', theme);
  const label = theme === 'light' ? 'Light Mode: ON' : 'Dark Mode: ON';
  const btn = document.getElementById('themeToggleBtn');
  if (btn) btn.textContent = label;
}
function toggleTheme() {
  const next = getSavedTheme() === 'dark' ? 'light' : 'dark';
  localStorage.setItem(THEME_KEY, next);
  applyTheme(next);
  window.dispatchEvent(new Event('resize'));
}


function escapeHtml(v) {
  return String(v ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

async function getJson(url) {
  const res = await fetch(url, { cache: 'no-store' });
  if (!res.ok) throw new Error(`${url} -> HTTP ${res.status}`);
  return await res.json();
}

function nowStr() { return new Date().toLocaleString('ko-KR'); }
function fmtDate(v) {
  if (!v) return '-';
  const d = new Date(v);
  if (Number.isNaN(d.getTime())) return String(v);
  return d.toLocaleString('ko-KR');
}
function fmtAgo(v) {
  if (!v) return '-';
  const d = new Date(v).getTime();
  if (Number.isNaN(d)) return '-';
  const sec = Math.floor((Date.now() - d) / 1000);
  if (sec < 60) return `${sec}초 전`;
  if (sec < 3600) return `${Math.floor(sec / 60)}분 전`;
  if (sec < 86400) return `${Math.floor(sec / 3600)}시간 전`;
  return `${Math.floor(sec / 86400)}일 전`;
}
function normalizeEvidence(path) {
  if (!path) return '';
  if (/^https?:\/\//i.test(path)) return path;
  return '/' + String(path).replace(/^\/+/, '').replace(/^\.\/+/, '').replace(/^app\//, '');
}
function pickStatusClass(status) {
  const s = String(status ?? '').toLowerCase();
  if (s.includes('sent') || s.includes('success') || s === 'ok' || s === 'true') return 'ok';
  if (s.includes('fail') || s.includes('error') || s === 'false') return 'fail';
  if (s.includes('pending') || s.includes('queue')) return 'warn';
  return 'other';
}
function countBy(items, key) {
  return items.reduce((a, it) => {
    const k = String(it?.[key] ?? 'unknown').trim() || 'unknown';
    a[k] = (a[k] || 0) + 1;
    return a;
  }, {});
}
function groupBy(items, key) {
  return items.reduce((a, it) => {
    const k = String(it?.[key] ?? '').trim() || 'unknown';
    (a[k] ||= []).push(it);
    return a;
  }, {});
}
function topEntries(obj, limit = 5) {
  return Object.entries(obj).sort((a,b) => b[1]-a[1]).slice(0, limit);
}
function uniqueValues(items, key) {
  return [...new Set(items.map(x => String(x?.[key] ?? '').trim()).filter(Boolean))].sort();
}
function qsParam(name) { return new URL(location.href).searchParams.get(name); }
function safeIncludes(hay, needle) { return String(hay ?? '').toLowerCase().includes(String(needle ?? '').toLowerCase()); }
function setUpdated(text) { const el = $('#updatedAt'); if (el) el.textContent = `Last update: ${text}`; }
function markActiveNav(pageKey) {
  $$('.nav-link').forEach(a => a.classList.toggle('active', a.dataset.page === pageKey));
}

function sidebarHtml(pageKey) {
  const navBySection = (section) =>
    NAV.filter(x => x.section === section)
       .map(x => `<a class="nav-link ${pageKey === x.key ? 'active' : ''}" data-page="${x.key}" href="${x.href}">${x.label}</a>`)
       .join('');
  return `
    <aside class="sidebar">
      <div class="brand">
        <div class="brand-mark">D</div>
        <div>
          <div class="brand-title">Darkweb Monitor</div>
          <div class="brand-sub">Intel Operations Console</div>
        </div>
      </div>

      <div class="nav-group">
        <div class="nav-title">Overview</div>
        <div class="nav">${navBySection('overview')}</div>
      </div>

      <div class="nav-group">
        <div class="nav-title">Analysis</div>
        <div class="nav">${navBySection('analysis')}</div>
      </div>

      <div class="nav-group">
        <div class="nav-title">Tracking</div>
        <div class="nav">${navBySection('tracking')}</div>
      </div>

      <div class="status-card">
        <div class="card-title">시스템 상태</div>
        <div class="status-row"><span class="dot ok"></span><span>API Connected</span></div>
        <div class="status-row"><span class="dot purple"></span><span id="updatedAt">Last update: -</span></div>
      </div>

      <div class="filter-card" id="sidebarExtra"></div>
    </aside>`;
}

function pageHtml({ pageKey, heroEyebrow, heroTitle, heroDesc, heroMeta = [], actionHtml = '', mainHtml = '', sidebarExtra = '' }) {
  return `
  <div class="bg-grid"></div>
  <div class="shell">
    ${sidebarHtml(pageKey)}
    <main class="main">
      <section class="hero">
        <div>
          <div class="eyebrow">${escapeHtml(heroEyebrow)}</div>
          <h1>${escapeHtml(heroTitle)}</h1>
          <p>${escapeHtml(heroDesc)}</p>
          ${heroMeta.length ? `<div class="hero-meta">${heroMeta.map(x => `<span class="pill">${escapeHtml(x)}</span>`).join('')}</div>` : ''}
        </div>
        <div class="actions"><button class="btn ghost" id="themeToggleBtn" type="button">Dark Mode</button>${actionHtml}</div>
      </section>
      ${mainHtml}
    </main>
  </div>`;
}

function installPage(config) {
  document.body.innerHTML = pageHtml(config);
  const extra = $('#sidebarExtra');
  if (extra) {
    extra.innerHTML = config.sidebarExtra || '<div class="card-title">Guide</div><div class="mini-desc">페이지를 전환해도 시각적 골조는 유지하고, 읽기 전용 분석 화면만 분리했다.</div>';
  }
  markActiveNav(config.pageKey);
  applyTheme();
  const themeBtn = document.getElementById('themeToggleBtn');
  if (themeBtn) themeBtn.addEventListener('click', toggleTheme);
}

function roundRect(ctx, x, y, w, h, r) {
  const rr = Math.min(r, w / 2, h / 2);
  ctx.beginPath();
  ctx.moveTo(x + rr, y);
  ctx.arcTo(x + w, y, x + w, y + h, rr);
  ctx.arcTo(x + w, y + h, x, y + h, rr);
  ctx.arcTo(x, y + h, x, y, rr);
  ctx.arcTo(x, y, x + w, y, rr);
  ctx.closePath();
}
function wrapCenterText(ctx, text, cx, y, maxW, lineH) {
  const words = String(text).split(/\s+/);
  let line = ''; const lines = [];
  for (const word of words) {
    const test = line ? line + ' ' + word : word;
    if (ctx.measureText(test).width > maxW && line) { lines.push(line); line = word; } else { line = test; }
  }
  if (line) lines.push(line);
  const off = ((lines.length - 1) * lineH) / 2;
  lines.slice(0, 2).forEach((ln, i) => ctx.fillText(ln, cx, y - off + i * lineH));
}
function drawBars(canvasId, labels, values, colors) {
  const canvas = document.getElementById(canvasId);
  if (!canvas) return;
  const ctx = canvas.getContext("2d");

  const cssWidth = canvas.parentElement.clientWidth || 520;
  const cssHeight = 280;
  const ratio = window.devicePixelRatio || 1;
  const isLight = document.documentElement.getAttribute('data-theme') === 'light';

  canvas.style.width = cssWidth + "px";
  canvas.style.height = cssHeight + "px";
  canvas.width = Math.floor(cssWidth * ratio);
  canvas.height = Math.floor(cssHeight * ratio);

  ctx.setTransform(1, 0, 0, 1, 0, 0);
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  ctx.setTransform(ratio, 0, 0, ratio, 0, 0);

  const width = cssWidth;
  const height = cssHeight;
  const pad = { top: 24, right: 18, bottom: 42, left: 18 };
  const chartW = width - pad.left - pad.right;
  const chartH = height - pad.top - pad.bottom;
  const max = Math.max(...values, 1);

  const chartText = isLight ? '#0f172a' : '#edf2ff';
  const chartMuted = isLight ? '#111827' : '#9db0d6';
  const gridColor = isLight ? 'rgba(15,23,42,.18)' : 'rgba(255,255,255,.08)';

  ctx.strokeStyle = gridColor;
  ctx.lineWidth = 1;
  for (let i = 0; i <= 4; i++) {
    const y = pad.top + (chartH / 4) * i;
    ctx.beginPath();
    ctx.moveTo(pad.left, y);
    ctx.lineTo(width - pad.right, y);
    ctx.stroke();
  }

  const count = Math.max(labels.length, 1);
  const gap = Math.max(12, Math.floor(chartW * 0.04));
  const barW = Math.max(18, Math.floor((chartW - gap * (count - 1)) / count));

  labels.forEach((label, i) => {
    const x = pad.left + i * (barW + gap);
    const barH = (values[i] / max) * (chartH - 14);
    const y = pad.top + chartH - barH;
    const pair = colors[i % colors.length];

    const grad = ctx.createLinearGradient(0, y, 0, y + barH);
    grad.addColorStop(0, pair[0]);
    grad.addColorStop(1, pair[1]);

    roundRect(ctx, x, y, barW, barH, 14);
    ctx.fillStyle = grad;
    ctx.fill();

    ctx.fillStyle = chartText;
    ctx.font = "700 12px Inter, sans-serif";
    ctx.textAlign = "center";
    ctx.fillText(String(values[i]), x + barW / 2, Math.max(14, y - 8));

    ctx.fillStyle = chartMuted;
    ctx.font = "600 12px Inter, sans-serif";
    wrapCenterText(ctx, label, x + barW / 2, height - 18, barW + 14, 12);
  });
}

function renderMetricCards(el, items) {
  el.innerHTML = items.map(it => `
    <article class="metric">
      <div class="metric-label">${escapeHtml(it.label)}</div>
      <div class="metric-value">${escapeHtml(it.value)}</div>
      <div class="metric-foot">${escapeHtml(it.foot || '')}</div>
    </article>`).join('');
}

function evidenceLinks(row = {}) {
  const links = [
    row.screenshot_path ? `<a class="pill link" target="_blank" href="${escapeHtml(normalizeEvidence(row.screenshot_path))}">Screenshot</a>` : '',
    row.text_dump_path ? `<a class="pill link" target="_blank" href="${escapeHtml(normalizeEvidence(row.text_dump_path))}">Text dump</a>` : '',
    row.raw_html_path ? `<a class="pill link" target="_blank" href="${escapeHtml(normalizeEvidence(row.raw_html_path))}">Raw HTML</a>` : '',
  ].filter(Boolean);
  return links.length ? links.join('') : '<span class="muted">증거 파일 없음</span>';
}

function fillSelect(el, values, placeholder = '전체') {
  if (!el) return;
  const current = el.value;
  el.innerHTML = `<option value="">${escapeHtml(placeholder)}</option>` + values.map(v => `<option value="${escapeHtml(v)}">${escapeHtml(v)}</option>`).join('');
  if (values.includes(current)) el.value = current;
}

function attachRefresh(handler) {
  const btns = ['#refreshBtn', '#heroRefreshBtn'].map(s => $(s)).filter(Boolean);
  btns.forEach(btn => btn.addEventListener('click', handler));
}

async function guardedLoad(fn) {
  try { setUpdated('loading...'); await fn(); setUpdated(nowStr()); }
  catch (err) { console.error(err); setUpdated('failed'); const box = $('#errorBox'); if (box) { box.classList.remove('hidden'); box.textContent = err.message || String(err); } }
}


const STORE_KEYS = {
  selectedHit: 'dm_selected_hit',
  selectedHitState: 'dm_selected_hit_state',
};

function saveSelectedHit(hit) {
  if (!hit) return;
  sessionStorage.setItem(STORE_KEYS.selectedHit, String(hit.id));
  sessionStorage.setItem(STORE_KEYS.selectedHitState, JSON.stringify({
    id: hit.id,
    matched_value: hit.matched_value || '',
    watch_type: hit.watch_type || '',
    label: hit.label || '',
    url: hit.url || '',
    target_id: hit.target_id || '',
    page_id: hit.page_id || '',
    last_seen_at: hit.last_seen_at || hit.first_seen_at || '',
  }));
}
function loadSelectedHitId() {
  return sessionStorage.getItem(STORE_KEYS.selectedHit) || '';
}
function loadSelectedHitState() {
  try { return JSON.parse(sessionStorage.getItem(STORE_KEYS.selectedHitState) || 'null'); }
  catch { return null; }
}
function hitIsRecent(hit, hours = 24) {
  const ts = new Date(hit?.last_seen_at || hit?.first_seen_at || 0).getTime();
  if (!ts) return false;
  return (Date.now() - ts) <= hours * 3600 * 1000;
}
function buildHitFlags(hit, rows = [], alerts = []) {
  const sameValue = rows.filter(x => String(x.matched_value || '').toLowerCase() === String(hit?.matched_value || '').toLowerCase());
  const samePage = rows.filter(x => String(x.page_id || '') === String(hit?.page_id || '') && String(hit?.page_id || '') !== '');
  const relatedAlerts = alerts.filter(a => String(a.hit_id || '') === String(hit?.id || '') || String(a.matched_value || '').toLowerCase() === String(hit?.matched_value || '').toLowerCase() || String(a.url || '') === String(hit?.url || ''));
  const hasFail = relatedAlerts.some(a => ['fail','error'].some(k => String(a.status || '').toLowerCase().includes(k)));
  const flags = [];
  if (sameValue.length > 1) flags.push({ cls: 'flag-repeat', text: `REPEATED ${sameValue.length}` });
  if (samePage.length > 1) flags.push({ cls: 'flag-multi', text: `MULTI ${samePage.length}` });
  if (hitIsRecent(hit)) flags.push({ cls: 'flag-new', text: 'NEW' });
  if (hasFail) flags.push({ cls: 'flag-fail', text: 'FAIL' });
  if (hit?.target_id) flags.push({ cls: 'flag-target', text: `TARGET ${hit.target_id}` });
  return flags;
}
function renderFlagBadges(flags = []) {
  if (!flags.length) return '';
  return `<div class="flag-row">${flags.map(f => `<span class="badge ${escapeHtml(f.cls)}">${escapeHtml(f.text)}</span>`).join('')}</div>`;
}
function renderSelectedBanner(hit, extraActions = '') {
  if (!hit) return '';
  return `
    <div class="selected-banner">
      <div class="selected-main">
        <div class="mini-kicker">Selected Hit</div>
        <div class="selected-title">${escapeHtml(hit.matched_value || '-')}</div>
        <div class="selected-sub">${escapeHtml(hit.watch_type || '-')} · ${escapeHtml(hit.label || '-')} · ${escapeHtml(hit.url || '-')}</div>
      </div>
      <div class="quick-links">${extraActions}</div>
    </div>`;
}
function gotoInvestigation(hit) {
  if (!hit) return;
  saveSelectedHit(hit);
  location.href = `/ui/investigation.html?hit=${encodeURIComponent(hit.id)}`;
}


function buildGraphDataset(hits = [], alerts = [], targets = []) {
  const nodes = [];
  const links = [];
  const nodeMap = new Map();
  const addNode = (id, kind, label, meta = {}) => {
    if (nodeMap.has(id)) return nodeMap.get(id);
    const node = { id, kind, label, degree: 0, ...meta };
    nodeMap.set(id, node);
    nodes.push(node);
    return node;
  };
  const addLink = (source, target, kind, weight = 1) => {
    if (!source || !target || source === target) return;
    const key = [source, target, kind].sort().join('|');
    const found = links.find(x => x.key === key);
    if (found) { found.weight += weight; return; }
    links.push({ key, source, target, kind, weight });
  };

  hits.forEach(hit => {
    const hitNode = addNode(`hit:${hit.id}`, 'hit', `#${hit.id}`, { hit });
    const iocValue = String(hit.matched_value || '').trim();
    const iocType = String(hit.watch_type || '').trim();
    const url = String(hit.url || '').trim();
    const targetId = String(hit.target_id || '').trim();

    if (iocValue) {
      addNode(`ioc:${iocValue.toLowerCase()}`, 'ioc', iocValue, { hitCount: 0 });
      addLink(hitNode.id, `ioc:${iocValue.toLowerCase()}`, 'matched');
    }
    if (iocType) {
      addNode(`type:${iocType.toLowerCase()}`, 'type', iocType);
      addLink(hitNode.id, `type:${iocType.toLowerCase()}`, 'typed');
    }
    if (url) {
      addNode(`url:${url}`, 'url', url);
      addLink(hitNode.id, `url:${url}`, 'seen_on');
    }
    if (targetId) {
      const target = targets.find(t => String(t.id) === targetId);
      addNode(`target:${targetId}`, 'target', target?.label || target?.name || `Target ${targetId}`);
      addLink(hitNode.id, `target:${targetId}`, 'belongs_to');
    }
  });

  alerts.forEach(alert => {
    const hitId = String(alert.hit_id || '').trim();
    if (hitId && nodeMap.has(`hit:${hitId}`)) {
      addNode(`alert:${alert.id}`, 'alert', `${alert.channel || 'alert'} #${alert.id}`, { alert });
      addLink(`hit:${hitId}`, `alert:${alert.id}`, 'alerted');
    }
  });

  links.forEach(link => {
    if (nodeMap.has(link.source)) nodeMap.get(link.source).degree += 1;
    if (nodeMap.has(link.target)) nodeMap.get(link.target).degree += 1;
  });

  const repeated = {};
  hits.forEach(hit => {
    const key = String(hit.matched_value || '').trim().toLowerCase();
    if (!key) return;
    repeated[key] = (repeated[key] || 0) + 1;
  });
  nodes.forEach(n => {
    if (n.kind === 'ioc') n.repeatCount = repeated[String(n.label || '').trim().toLowerCase()] || 0;
  });

  return { nodes, links };
}

function relationColor(kind) {
  const map = {
    ioc: '#5ad1ff',
    url: '#5bf0bf',
    target: '#ffbe5c',
    type: '#9d8bff',
    hit: '#edf2ff',
    alert: '#ff8a9a',
  };
  return map[kind] || '#cbd8f3';
}