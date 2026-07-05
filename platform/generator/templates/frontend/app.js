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
      <div class="kpi">
        <div class="kpi-name">${escapeHtml(k.name)}</div>
        <div class="kpi-domain">${escapeHtml(k.domain || '')} · ${escapeHtml(k.unit || '')}</div>
        <div class="kpi-formula">${escapeHtml(k.formula)}</div>
      </div>
    `).join('');
  } catch (e) {}
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

renderDigest();
renderKPIs();
renderDS();
