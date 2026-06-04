/* ═══ NSE Volatility Scanner — Dashboard App ═══ */

// ─── State ───
let scanData = null;
let autoRefreshTimer = null;
let countdownTimer = null;
let countdownSeconds = 0;
let isScanning = false;
let currentSort = { key: 'combined_score', dir: 'desc' };

// ─── Init ───
document.addEventListener('DOMContentLoaded', () => {
  setupFilters();
  setupTableSort();
  // Auto-load last scan on page load
  loadLastScan();
});

// ─── API Calls ───
async function triggerScan() {
  if (isScanning) return;
  setScanning(true);
  try {
    const resp = await fetch('/api/scan?force=true');
    if (!resp.ok) throw new Error(`Scan failed: ${resp.status}`);
    scanData = await resp.json();
    renderAll(scanData);
    resetCountdown();
  } catch (e) {
    showError(e.message);
  } finally {
    setScanning(false);
  }
}

async function loadLastScan() {
  try {
    const resp = await fetch('/api/last-scan');
    if (!resp.ok) return;
    const data = await resp.json();
    if (data.signals && data.signals.length > 0) {
      scanData = data;
      renderAll(scanData);
    }
  } catch (e) { /* silent */ }
}

// ─── Render All ───
function renderAll(data) {
  if (!data) return;
  renderMarketOverview(data.market_overview);
  renderSignalsTable(data.signals);
  renderNews(data.news);
  renderScanInfo(data);
  updateLastScanTime(data.scan_timestamp);
  hideLoading();

  if (data.errors && data.errors.length > 0) {
    console.warn('Scan errors:', data.errors);
  }
}

// ─── Market Overview ───
function renderMarketOverview(mo) {
  if (!mo) return;
  setPrice('nifty50', mo.nifty50_price, mo.nifty50_pct_change);
  setPrice('banknifty', mo.bank_nifty_price, mo.bank_nifty_pct_change);

  const vixPriceEl = document.getElementById('vix-price');
  const vixChangeEl = document.getElementById('vix-change');
  if (vixPriceEl) vixPriceEl.textContent = mo.india_vix ? mo.india_vix.toFixed(2) : '—';
  if (vixChangeEl) {
    vixChangeEl.textContent = mo.india_vix_pct_change ? `${mo.india_vix_pct_change > 0 ? '+' : ''}${mo.india_vix_pct_change.toFixed(2)}%` : '—';
    vixChangeEl.className = 'market-card-change ' + (mo.india_vix_pct_change > 0 ? 'negative' : 'positive'); // VIX up = bad
  }

  const trendEl = document.getElementById('trend-status');
  if (trendEl) {
    trendEl.textContent = mo.trend_filter;
    trendEl.className = 'trend-status ' + (mo.trend_filter === 'BULLISH' ? 'bullish' : mo.trend_filter === 'BEARISH' ? 'bearish' : 'neutral-trend');
  }
  const mktStatusEl = document.getElementById('market-status');
  if (mktStatusEl) mktStatusEl.textContent = `Market: ${mo.market_status}`;
}

function setPrice(id, price, pctChange) {
  const priceEl = document.getElementById(`${id}-price`);
  const changeEl = document.getElementById(`${id}-change`);
  if (priceEl) priceEl.textContent = price ? formatNum(price) : '—';
  if (changeEl) {
    changeEl.textContent = pctChange != null ? `${pctChange > 0 ? '+' : ''}${pctChange.toFixed(2)}%` : '—';
    changeEl.className = 'market-card-change ' + (pctChange > 0 ? 'positive' : pctChange < 0 ? 'negative' : '');
  }
}

// ─── Signals Table ───
function renderSignalsTable(signals) {
  if (!signals || signals.length === 0) {
    document.getElementById('signals-table').style.display = 'none';
    document.getElementById('empty-state').style.display = 'block';
    document.getElementById('error-state').style.display = 'none';
    document.getElementById('signal-count').textContent = '0 signals';
    return;
  }

  // Apply filters
  const filtered = applyFilters(signals);
  // Apply sort
  const sorted = applySort(filtered);

  document.getElementById('signals-table').style.display = 'table';
  document.getElementById('empty-state').style.display = 'none';
  document.getElementById('error-state').style.display = 'none';
  document.getElementById('signal-count').textContent = `${sorted.length} signals`;

  // Populate sectors dropdown
  populateSectors(signals);

  const tbody = document.getElementById('signals-tbody');
  tbody.innerHTML = sorted.map(s => `
    <tr class="signal-row signal-row-${s.signal_type.toLowerCase()}">
      <td>${s.rank}</td>
      <td><span class="td-symbol">${s.symbol}</span><span class="td-company">${s.company || ''}</span></td>
      <td>₹${formatNum(s.cmp)}</td>
      <td class="${s.pct_change > 0 ? 'td-positive' : s.pct_change < 0 ? 'td-negative' : ''}">${s.pct_change > 0 ? '+' : ''}${s.pct_change.toFixed(2)}%</td>
      <td>${s.atr_pct.toFixed(2)}%</td>
      <td class="${s.volume_spike > 2 ? 'td-positive' : ''}">${s.volume_spike.toFixed(1)}×</td>
      <td class="${s.gap_pct > 0 ? 'td-positive' : s.gap_pct < 0 ? 'td-negative' : ''}">${s.gap_pct > 0 ? '+' : ''}${s.gap_pct.toFixed(2)}%</td>
      <td class="${s.rsi > 70 ? 'td-negative' : s.rsi < 30 ? 'td-positive' : ''}">${s.rsi.toFixed(1)}</td>
      <td>${renderAIBadge(s.direction, s.materiality, s.headline)}</td>
      <td>${renderScore(s.combined_score)}</td>
      <td>${renderSignalBadge(s.signal_type)}</td>
      <td>₹${formatNum(s.entry)}</td>
      <td class="td-negative">₹${formatNum(s.stop_loss)}</td>
      <td class="td-positive">₹${formatNum(s.target)}</td>
      <td class="${s.rr_ratio >= 2 ? 'td-positive' : ''}">${s.rr_ratio.toFixed(1)}</td>
      <td>${s.quantity}</td>
      <td>${renderFlags(s.flags)}</td>
    </tr>
  `).join('');
}

function renderAIBadge(dir, mat, headline) {
  if (!dir || dir === 'NEUTRAL' && mat === 0) return '<span style="color:var(--text-muted)">—</span>';
  const cls = dir === 'BULLISH' ? 'td-positive' : dir === 'BEARISH' ? 'td-negative' : '';
  const tooltip = headline ? `title="${escHtml(headline)}"` : '';
  return `<span class="${cls}" ${tooltip} style="cursor:help">${dir.slice(0, 4)} ${(mat * 10).toFixed(1)}</span>`;
}

function renderScore(score) {
  const pct = Math.min(score / 10 * 100, 100);
  const cls = score >= 7 ? 'score-high' : score >= 4 ? 'score-mid' : 'score-low';
  return `<span class="score-bar ${cls}"><span class="score-bar-fill" style="width:${pct * 0.5}px"></span>${score.toFixed(1)}</span>`;
}

function renderSignalBadge(type) {
  const cls = type === 'BUY' ? 'signal-buy' : type === 'SELL' ? 'signal-sell' : 'signal-watch';
  return `<span class="signal-badge ${cls}">${type}</span>`;
}

function renderFlags(flags) {
  if (!flags || flags.length === 0) return '<span style="color:var(--text-muted)">—</span>';
  return flags.map(f => {
    const cls = f.includes('RSI') ? 'flag-info' : '';
    return `<span class="flag-badge ${cls}">${f}</span>`;
  }).join('');
}

// ─── News ───
function renderNews(news) {
  const list = document.getElementById('news-list');
  const countEl = document.getElementById('news-count');
  if (!news || news.length === 0) {
    list.innerHTML = '<div class="news-empty">No news available</div>';
    countEl.textContent = '0 headlines';
    return;
  }
  countEl.textContent = `${news.length} headlines`;
  list.innerHTML = news.slice(0, 20).map(n => `
    <div class="news-item">
      <span class="news-time">${formatNewsTime(n.published)}</span>
      <span class="news-source">${n.source || ''}</span>
      <span class="news-headline">
        ${n.link ? `<a href="${n.link}" target="_blank" rel="noopener">${escHtml(n.headline)}</a>` : escHtml(n.headline)}
        ${n.direction ? `<span class="flag-badge ${n.direction === 'BULLISH' ? 'td-positive' : n.direction === 'BEARISH' ? 'td-negative' : ''}">${n.symbol} | ${n.direction}</span>` : ''}
      </span>
    </div>
  `).join('');
}

// ─── Scan Info ───
function renderScanInfo(data) {
  const scannedEl = document.getElementById('stocks-scanned');
  const durEl = document.getElementById('scan-duration');
  if (scannedEl) scannedEl.textContent = `${data.stocks_scanned || 0} stocks`;
  if (durEl) durEl.textContent = `${((data.scan_duration_ms || 0) / 1000).toFixed(1)}s scan`;
}

// ─── Filters ───
function setupFilters() {
  const scoreRange = document.getElementById('filter-min-score');
  const rrRange = document.getElementById('filter-min-rr');
  const refreshRange = document.getElementById('filter-refresh');
  const signalSelect = document.getElementById('filter-signal');
  const sectorSelect = document.getElementById('filter-sector');

  scoreRange.addEventListener('input', e => {
    document.getElementById('min-score-value').textContent = parseFloat(e.target.value).toFixed(1);
    rerender();
  });
  rrRange.addEventListener('input', e => {
    document.getElementById('min-rr-value').textContent = parseFloat(e.target.value).toFixed(1);
    rerender();
  });
  refreshRange.addEventListener('input', e => {
    document.getElementById('refresh-value').textContent = e.target.value;
    resetCountdown();
  });
  signalSelect.addEventListener('change', rerender);
  sectorSelect.addEventListener('change', rerender);
}

function applyFilters(signals) {
  const minScore = parseFloat(document.getElementById('filter-min-score').value);
  const minRR = parseFloat(document.getElementById('filter-min-rr').value);
  const signalType = document.getElementById('filter-signal').value;
  const sector = document.getElementById('filter-sector').value;

  return signals.filter(s => {
    if (s.combined_score < minScore) return false;
    if (s.rr_ratio < minRR) return false;
    if (signalType !== 'all' && s.signal_type !== signalType) return false;
    if (sector !== 'all' && s.sector !== sector) return false;
    return true;
  });
}

function populateSectors(signals) {
  const sel = document.getElementById('filter-sector');
  const current = sel.value;
  const sectors = [...new Set(signals.map(s => s.sector).filter(Boolean))].sort();
  const opts = '<option value="all">All Sectors</option>' + sectors.map(s => `<option value="${s}">${s}</option>`).join('');
  sel.innerHTML = opts;
  sel.value = current || 'all';
}

function rerender() {
  if (scanData && scanData.signals) renderSignalsTable(scanData.signals);
}

// ─── Table Sort ───
function setupTableSort() {
  document.querySelectorAll('.signals-table th[data-sort]').forEach(th => {
    th.addEventListener('click', () => {
      const key = th.dataset.sort;
      if (currentSort.key === key) {
        currentSort.dir = currentSort.dir === 'asc' ? 'desc' : 'asc';
      } else {
        currentSort = { key, dir: 'desc' };
      }
      document.querySelectorAll('.signals-table th').forEach(t => t.classList.remove('sorted-asc', 'sorted-desc'));
      th.classList.add(currentSort.dir === 'asc' ? 'sorted-asc' : 'sorted-desc');
      rerender();
    });
  });
}

function applySort(signals) {
  const { key, dir } = currentSort;
  return [...signals].sort((a, b) => {
    let va = a[key], vb = b[key];
    if (typeof va === 'string') { va = va.toLowerCase(); vb = (vb || '').toLowerCase(); }
    if (va < vb) return dir === 'asc' ? -1 : 1;
    if (va > vb) return dir === 'asc' ? 1 : -1;
    return 0;
  });
}

// ─── Status & Countdown ───
function setScanning(active) {
  isScanning = active;
  const btn = document.getElementById('btn-scan');
  const dot = document.getElementById('status-dot');
  const text = document.getElementById('status-text');
  if (active) {
    btn.classList.add('loading');
    btn.innerHTML = '<svg class="spin" width="16" height="16" viewBox="0 0 16 16"><circle cx="8" cy="8" r="6" stroke="currentColor" stroke-width="2" fill="none" stroke-dasharray="30" stroke-dashoffset="10"/></svg> Scanning...';
    dot.className = 'status-dot scanning';
    text.textContent = 'Scanning...';
    document.getElementById('loading-skeleton').style.display = 'block';
  } else {
    btn.classList.remove('loading');
    btn.innerHTML = '<svg width="16" height="16" viewBox="0 0 16 16" fill="none"><path d="M1 8a7 7 0 0114 0A7 7 0 011 8zm7-3v3l2 2" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg> Scan Now';
    dot.className = 'status-dot';
    text.textContent = 'Ready';
  }
}

function hideLoading() {
  document.getElementById('loading-skeleton').style.display = 'none';
}

function showError(msg) {
  document.getElementById('signals-table').style.display = 'none';
  document.getElementById('empty-state').style.display = 'none';
  document.getElementById('error-state').style.display = 'block';
  document.getElementById('error-message').textContent = msg;
  document.getElementById('loading-skeleton').style.display = 'none';
  const dot = document.getElementById('status-dot');
  dot.className = 'status-dot error';
}

function updateLastScanTime(ts) {
  const el = document.getElementById('last-scan-time');
  if (!ts) { el.textContent = '—'; return; }
  try {
    const d = new Date(ts);
    el.textContent = `Last: ${d.toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit' })}`;
  } catch { el.textContent = '—'; }
}

function resetCountdown() {
  clearInterval(countdownTimer);
  clearTimeout(autoRefreshTimer);
  const mins = parseInt(document.getElementById('filter-refresh').value);
  countdownSeconds = mins * 60;
  const cdEl = document.getElementById('countdown-value');

  countdownTimer = setInterval(() => {
    countdownSeconds--;
    if (countdownSeconds <= 0) {
      clearInterval(countdownTimer);
      triggerScan();
      return;
    }
    const m = Math.floor(countdownSeconds / 60);
    const s = countdownSeconds % 60;
    cdEl.textContent = `${m}:${s.toString().padStart(2, '0')}`;
  }, 1000);
}

// ─── Helpers ───
function formatNum(n) {
  if (n == null || isNaN(n)) return '—';
  return n.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function formatNewsTime(ts) {
  if (!ts) return '';
  try {
    const d = new Date(ts);
    if (isNaN(d)) return ts.slice(0, 16);
    return d.toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit' });
  } catch { return ts; }
}

function escHtml(s) {
  const d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
}
