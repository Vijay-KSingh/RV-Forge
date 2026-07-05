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

renderDigest();
renderKPIs();
renderDS();
