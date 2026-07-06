const API_BASE = (window.FORGE_API_BASE || 'http://localhost:8000');

async function fetchJSON(path, opts) {
  const res = await fetch(API_BASE + path, opts);
  if (!res.ok) throw new Error(res.status);
  return res.json();
}

function escapeHtml(str) {
  return String(str || '').replace(/[&<>"']/g, m => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[m]
  ));
}

async function renderDigest() {
  try {
    const d = await fetchJSON('/api/insights/digest');
    const el = document.getElementById('digest');
    let html = '';
    for (const sec of (d.sections || [])) {
      html += `<div class="digest-section"><h3>${escapeHtml(sec.title)}</h3><ul>`;
      for (const b of (sec.bullets || [])) html += `<li>${escapeHtml(b)}</li>`;
      html += '</ul></div>';
    }
    el.innerHTML = html;
  } catch (e) {
    document.getElementById('digest').innerHTML =
      '<p class="muted">Backend not yet running. Start it with <code>docker-compose up</code>.</p>';
  }
}

async function renderKPIs() {
  try {
    const kpis = await fetchJSON('/api/kpis');
    const el = document.getElementById('kpis');
    el.innerHTML = kpis.map(k => `
      <div class="kpi kpi-clickable" data-kpi-id="${escapeHtml(k.id)}" role="button" tabindex="0">
        <div class="kpi-name">${escapeHtml(k.name)} <span class="kpi-arrow">→</span></div>
        <div class="kpi-domain">${escapeHtml(k.domain || '')} · ${escapeHtml(k.unit || '')}</div>
        <div class="kpi-formula">${escapeHtml(k.formula)}</div>
      </div>
    `).join('');
  } catch (e) {}
}

// Clicking (or Enter/Space on) a KPI card opens its detail screen via the URL hash.
const kpisEl = document.getElementById('kpis');
if (kpisEl) {
  const openFromCard = (card) => {
    const id = card && card.getAttribute('data-kpi-id');
    if (id) location.hash = 'kpi/' + encodeURIComponent(id);
  };
  kpisEl.addEventListener('click', (e) => openFromCard(e.target.closest('.kpi-clickable')));
  kpisEl.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' || e.key === ' ') {
      const card = e.target.closest('.kpi-clickable');
      if (card) { e.preventDefault(); openFromCard(card); }
    }
  });
}

async function renderDS() {
  try {
    const ds = await fetchJSON('/api/datasources');
    const el = document.getElementById('ds');
    el.innerHTML = ds.map(d => `
      <div class="ds">
        <div><strong>${escapeHtml(d.name)}</strong> <span class="muted">${escapeHtml(d.description || '')}</span></div>
        <div class="ds-kind">${escapeHtml(d.kind)}</div>
      </div>
    `).join('');
  } catch (e) {}
}

document.getElementById('askBtn').addEventListener('click', async () => {
  const q = document.getElementById('q').value.trim();
  if (!q) return;
  const out = document.getElementById('answer');
  out.classList.add('show');
  out.textContent = 'Thinking…';
  try {
    const role = document.getElementById('role').value;
    const r = await fetchJSON('/api/ask', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question: q, role_id: role }),
    });
    out.innerHTML = `<div>${escapeHtml(r.answer)}</div>` +
      (r.citations && r.citations.length
        ? `<div style="margin-top:10px;font-size:12px;color:#6b7280">Sources: ${
            r.citations.map(c => escapeHtml(c.source)).join(', ')}</div>`
        : '');
  } catch (e) {
    out.textContent = 'Backend not reachable: ' + e.message;
  }
});

// ── Excel / CSV upload ──────────────────────────────────────────────
const fileInput = document.getElementById('fileInput');
const fileLabel = document.getElementById('fileLabel');
const uploadBtn = document.getElementById('uploadBtn');
const uploadStatus = document.getElementById('uploadStatus');
const uploadResult = document.getElementById('uploadResult');

function fmtNum(n) {
  if (typeof n !== 'number' || !isFinite(n)) return String(n);
  return Math.abs(n) >= 1000 ? n.toLocaleString(undefined, { maximumFractionDigits: 2 })
                             : String(Math.round(n * 100) / 100);
}

if (fileInput) {
  fileInput.addEventListener('change', () => {
    const f = fileInput.files[0];
    fileLabel.textContent = f ? f.name : 'Choose an .xlsx or .csv file…';
    uploadBtn.disabled = !f;
    uploadStatus.textContent = '';
  });

  uploadBtn.addEventListener('click', async () => {
    const f = fileInput.files[0];
    if (!f) return;
    uploadBtn.disabled = true;
    uploadStatus.textContent = 'Uploading & parsing…';
    uploadResult.innerHTML = '';
    try {
      const body = new FormData();
      body.append('file', f);
      const res = await fetch(API_BASE + '/api/upload', { method: 'POST', body });
      if (!res.ok) {
        let msg = res.status;
        try { msg = (await res.json()).detail || msg; } catch (e) {}
        throw new Error(msg);
      }
      const d = await res.json();
      renderUpload(d);
      uploadStatus.textContent = '';
    } catch (e) {
      uploadStatus.innerHTML = `<span class="upload-error">Upload failed: ${escapeHtml(e.message)}</span>`;
    } finally {
      uploadBtn.disabled = false;
    }
  });
}

function renderUpload(d) {
  const cols = d.columns || [];
  const rows = d.preview_rows || [];
  const summary = d.numeric_summary || [];

  const summaryHtml = summary.length ? `
    <div class="upload-summary">
      ${summary.map(s => `
        <div class="stat">
          <div class="stat-col">${escapeHtml(s.column)}</div>
          <div class="stat-nums">
            <span>avg <strong>${fmtNum(s.avg)}</strong></span>
            <span>sum <strong>${fmtNum(s.sum)}</strong></span>
            <span>min ${fmtNum(s.min)}</span>
            <span>max ${fmtNum(s.max)}</span>
          </div>
        </div>`).join('')}
    </div>` : '';

  const tableHtml = `
    <div class="table-wrap">
      <table class="data-table">
        <thead><tr>${cols.map(c => `<th>${escapeHtml(c)}</th>`).join('')}</tr></thead>
        <tbody>
          ${rows.map(r => `<tr>${cols.map((_, i) => `<td>${escapeHtml(r[i])}</td>`).join('')}</tr>`).join('')}
        </tbody>
      </table>
    </div>`;

  uploadResult.innerHTML = `
    <div class="upload-meta"><strong>${escapeHtml(d.filename)}</strong>
      · ${d.row_count} rows × ${d.column_count} columns
      ${rows.length < d.row_count ? `<span class="muted">(showing first ${rows.length})</span>` : ''}
    </div>
    ${summaryHtml}
    ${tableHtml}`;
}

// ── KPI drill-down screen (hash router) ─────────────────────────────
const mainEl = document.querySelector('main');
const detailEl = document.getElementById('detailView');

function lineChart(series) {
  const w = 640, h = 220, pad = 34;
  const vals = series.map(p => p.v);
  const min = Math.min(...vals), max = Math.max(...vals);
  const span = (max - min) || 1;
  const x = i => pad + (i * (w - 2 * pad)) / Math.max(1, series.length - 1);
  const y = v => h - pad - ((v - min) / span) * (h - 2 * pad);
  const pts = series.map((p, i) => `${x(i)},${y(p.v)}`).join(' ');
  const area = `${pad},${h - pad} ${pts} ${x(series.length - 1)},${h - pad}`;
  const dots = series.map((p, i) =>
    `<circle cx="${x(i)}" cy="${y(p.v)}" r="3" class="ch-dot"><title>${escapeHtml(p.t)}: ${p.v}</title></circle>`).join('');
  const labels = series.map((p, i) =>
    `<text x="${x(i)}" y="${h - 12}" class="ch-label">${escapeHtml(p.t)}</text>`).join('');
  return `
    <svg class="chart" viewBox="0 0 ${w} ${h}" preserveAspectRatio="xMidYMid meet">
      <polygon points="${area}" class="ch-area" />
      <polyline points="${pts}" class="ch-line" />
      ${dots}${labels}
    </svg>`;
}

async function renderKpiDetail(id) {
  detailEl.innerHTML = '<div class="card"><p class="muted">Loading…</p></div>';
  detailEl.hidden = false;
  if (mainEl) mainEl.hidden = true;
  window.scrollTo(0, 0);
  try {
    const d = await fetchJSON('/api/kpis/' + encodeURIComponent(id));
    const k = d.kpi || {};
    const up = d.delta_pct >= 0;
    const better = k.higher_is_better !== false ? up : !up;
    const arrow = up ? '▲' : '▼';
    detailEl.innerHTML = `
      <div class="detail-head">
        <a class="back" href="#">← Back to dashboard</a>
      </div>
      <section class="card">
        <div class="detail-title">
          <h1>${escapeHtml(k.name)}</h1>
          <span class="pill">${escapeHtml(k.domain || '')} · ${escapeHtml(k.unit || '')}</span>
        </div>
        <div class="detail-value">
          <div class="big">${d.current}</div>
          <div class="delta ${better ? 'good' : 'bad'}">${arrow} ${Math.abs(d.delta_pct)}%
            <span class="muted">vs previous period</span></div>
        </div>
        ${d.is_demo ? '<div class="demo-note">Showing a demo trend — connect a live data source to see real values.</div>' : ''}
        ${lineChart(d.series || [])}
      </section>
      <section class="card">
        <h2>Definition</h2>
        <div class="def-grid">
          <div><span class="def-k">Formula</span><code>${escapeHtml(k.formula || '')}</code></div>
          <div><span class="def-k">Unit</span>${escapeHtml(k.unit || '—')}</div>
          <div><span class="def-k">Domain</span>${escapeHtml(k.domain || '—')}</div>
          <div><span class="def-k">Chart type</span>${escapeHtml(k.chart_type || 'line')}</div>
          <div><span class="def-k">Direction</span>${k.higher_is_better === false ? 'lower is better' : 'higher is better'}</div>
          <div><span class="def-k">Refresh</span>${escapeHtml(k.refresh_cadence || 'daily')}</div>
          ${k.target_value != null ? `<div><span class="def-k">Target</span>${escapeHtml(String(k.target_value))}</div>` : ''}
        </div>
      </section>`;
  } catch (e) {
    detailEl.innerHTML = `<div class="detail-head"><a class="back" href="#">← Back</a></div>
      <div class="card"><p class="upload-error">Could not load KPI: ${escapeHtml(e.message)}</p></div>`;
  }
}

function showDashboard() {
  detailEl.hidden = true;
  detailEl.innerHTML = '';
  if (mainEl) mainEl.hidden = false;
}

function route() {
  const m = /^#kpi\/(.+)$/.exec(location.hash);
  if (m) renderKpiDetail(decodeURIComponent(m[1]));
  else showDashboard();
}
window.addEventListener('hashchange', route);

renderDigest();
renderKPIs();
renderDS();
route();
