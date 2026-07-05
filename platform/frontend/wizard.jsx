const { useState, useEffect, useReducer, useRef, useCallback, useMemo } = React;

const API = ''; // same-origin

// ─── API helpers ─────────────────────────────────────────────────────
async function api(path, opts) {
  const r = await fetch(API + path, opts);
  if (!r.ok) {
    const text = await r.text().catch(() => '');
    throw new Error(`${r.status} ${text || r.statusText}`);
  }
  return r.json();
}
const apiGet = (p) => api(p);
const apiPost = (p, body) => api(p, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body),
});

// ─── Initial manifest ────────────────────────────────────────────────
const SCHEMA_VERSION = '1.0.0';

const initialManifest = () => ({
  schema_version: SCHEMA_VERSION,
  manifest_id: null, // assigned by backend on first save
  customer: {
    company_name: '',
    industry: '',
    contact_email: '',
    primary_use_case: '',
  },
  capabilities: [],
  deployment: 'localhost',
  infra_ownership: 'self_managed',
  cloud_region: 'us-east-1',
  data_sources: [],
  audiences: [],
  kpis: [],
  observability: {
    tier: 'standard',
    log_retention_days: 30,
    audit_retention_days: 365,
    metrics_backend: 'prometheus',
    traces_backend: 'tempo',
    alert_channels: [],
    enable_data_lineage: false,
    enable_query_audit: true,
    enable_cost_tracking: false,
  },
  rbac: {
    sso_provider: 'none',
    mfa_required: true,
    roles: [
      { id: 'admin', name: 'Administrator', description: 'Full access',
        column_policies: [], row_policies: [], capabilities: [],
        can_export: true, can_share: true, requires_approval_for: [] },
      { id: 'viewer', name: 'Viewer', description: 'Read-only access',
        column_policies: [], row_policies: [], capabilities: [],
        can_export: true, can_share: false, requires_approval_for: [] },
    ],
    default_role_id: 'viewer',
    approval_chain: [],
  },
  custom_requests: [],
  branding: {
    app_name: '',
    primary_color: '#6ce5b1',
    accent_color: '#9d8df1',
  },
  feature_flags: {},
});

// ─── Steps definition ────────────────────────────────────────────────
const STEPS = [
  { id: 'customer',     label: 'Customer & capabilities' },
  { id: 'deployment',   label: 'Deployment topology' },
  { id: 'datasources',  label: 'Data sources & secrets' },
  { id: 'audience',     label: 'Audience & KPIs' },
  { id: 'observability', label: 'Observability' },
  { id: 'rbac',         label: 'Access control' },
  { id: 'custom',       label: 'Custom requests' },
  { id: 'review',       label: 'Review' },
  { id: 'build',        label: 'Build & launch' },
];

const CAPABILITIES = [
  { id: 'ai_dashboard',           label: 'AI Dashboard',          desc: 'KPI dashboards with AI commentary' },
  { id: 'nl_query',               label: 'Natural Language Query', desc: 'Ask questions in plain English' },
  { id: 'anomaly_detection',      label: 'Anomaly Detection',     desc: 'Auto-flag unusual patterns' },
  { id: 'time_series_forecasting', label: 'Time-series Forecasting', desc: 'Predict future trends' },
  { id: 'fraud_detection',        label: 'Fraud Detection',       desc: 'Surface suspicious transactions' },
  { id: 'churn_prediction',       label: 'Churn Prediction',      desc: 'Identify at-risk customers' },
  { id: 'revenue_forecasting',    label: 'Revenue Forecasting',   desc: 'Project revenue scenarios' },
  { id: 'document_intelligence',  label: 'Document Intelligence', desc: 'Q&A grounded in your PDFs' },
  { id: 'proactive_insights',     label: 'Proactive Insights',    desc: 'Daily/weekly digest of what changed' },
  { id: 'what_if_simulation',     label: 'What-if Simulation',    desc: 'Model scenarios and outcomes' },
  { id: 'executive_summary',      label: 'Executive Summary',     desc: 'Auto-generated narrative briefs' },
  { id: 'agentic_workflows',      label: 'Agentic Workflows',     desc: 'Multi-step AI workflows' },
];

// Derive a generated app's folder name from its output path.
const appIdFromPath = (p) => (p || '').replace(/[\\/]+$/, '').split(/[\\/]/).pop();

// ─── Top-level App ───────────────────────────────────────────────────
function App() {
  const [manifest, setManifest] = useState(initialManifest);
  const [stepIdx, setStepIdx] = useState(0);
  const [catalog, setCatalog] = useState({ kpis: null, audiences: null, dataSources: null });
  const [savedManifestId, setSavedManifestId] = useState(null);
  const [build, setBuild] = useState({ id: null, events: [], status: 'idle', outputPath: null, progress: 0 });
  const [run, setRun] = useState({ status: 'idle', urls: null, error: null }); // idle|launching|running|error

  // Load catalogs once
  useEffect(() => {
    (async () => {
      try {
        const [k, a, d] = await Promise.all([
          apiGet('/api/catalog/kpis'),
          apiGet('/api/catalog/audiences'),
          apiGet('/api/catalog/data_source_kinds'),
        ]);
        setCatalog({ kpis: k, audiences: a, dataSources: d });
      } catch (e) {
        console.error('Catalog load failed', e);
      }
    })();
  }, []);

  // Updater shortcut
  const update = useCallback((patch) => {
    setManifest((m) => typeof patch === 'function' ? patch(m) : { ...m, ...patch });
  }, []);

  const step = STEPS[stepIdx];
  const goNext = () => setStepIdx((i) => Math.min(i + 1, STEPS.length - 1));
  const goPrev = () => setStepIdx((i) => Math.max(i - 1, 0));

  const saveManifest = async () => {
    const payload = { ...manifest };
    if (!payload.branding.app_name && payload.customer.company_name) {
      payload.branding = { ...payload.branding, app_name: `${payload.customer.company_name} Insights` };
    }
    const res = await apiPost('/api/manifests', { manifest: payload });
    setSavedManifestId(res.manifest_id);
    setManifest((m) => ({ ...m, manifest_id: res.manifest_id }));
    return res.manifest_id;
  };

  const startBuild = async () => {
    let mid = savedManifestId;
    if (!mid) mid = await saveManifest();
    setBuild({ id: null, events: [], status: 'starting', outputPath: null, progress: 0 });
    const res = await apiPost('/api/builds', { manifest_id: mid });
    setBuild((b) => ({ ...b, id: res.build_id, status: 'running' }));
  };

  // Launch the generated app natively (no Docker) and collect its URLs.
  const runApp = async () => {
    const appId = appIdFromPath(build.outputPath);
    if (!appId) return;
    setRun({ status: 'launching', urls: null, error: null });
    try {
      const res = await apiPost(`/api/apps/${appId}/run`, {});
      setRun({ status: 'running', urls: res, error: null });
    } catch (e) {
      setRun({ status: 'error', urls: null, error: String(e.message || e) });
    }
  };

  const stopApp = async () => {
    const appId = appIdFromPath(build.outputPath);
    if (!appId) return;
    try { await apiPost(`/api/apps/${appId}/stop`, {}); } catch {}
    setRun({ status: 'idle', urls: null, error: null });
  };

  // WebSocket subscription for live build progress
  useEffect(() => {
    if (!build.id) return;
    const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const url = `${proto}//${window.location.host}/ws/builds/${build.id}`;
    const ws = new WebSocket(url);
    ws.onmessage = (evt) => {
      const data = JSON.parse(evt.data);
      if (data.final) {
        setBuild((b) => ({ ...b, status: data.status, outputPath: data.output_path }));
        return;
      }
      setBuild((b) => ({
        ...b,
        events: [...b.events, data],
        progress: typeof data.progress_pct === 'number' ? data.progress_pct : b.progress,
      }));
    };
    ws.onerror = () => setBuild((b) => ({ ...b, status: 'error' }));
    return () => { try { ws.close(); } catch {} };
  }, [build.id]);

  // Validation per step (drives the Next button)
  const stepValid = useMemo(() => {
    switch (step.id) {
      case 'customer':    return manifest.customer.company_name.trim().length > 0 && manifest.capabilities.length > 0;
      case 'deployment':  return !!manifest.deployment;
      case 'datasources': return manifest.data_sources.length > 0;
      case 'audience':    return manifest.audiences.length > 0 && manifest.kpis.length > 0;
      case 'observability': return !!manifest.observability.tier;
      case 'rbac':        return manifest.rbac.roles.length >= 1;
      case 'custom':      return true;
      case 'review':      return true;
      case 'build':       return true;
      default:            return true;
    }
  }, [step, manifest]);

  // Render
  return (
    <div className="app">
      <div className="top">
        <div className="brand">
          <div className="brand-mark">F</div>
          <span>Forge</span>
          <span className="brand-tag">— generate analytics applications</span>
        </div>
        <div className="top-actions">
          {savedManifestId && <span className="mono" style={{fontSize: 11}}>{savedManifestId}</span>}
        </div>
      </div>
      <div className="shell">
        <aside className="sidebar">
          <h3>Steps</h3>
          <div className="steplist">
            {STEPS.map((s, i) => (
              <div key={s.id}
                   className={`step ${i === stepIdx ? 'active' : ''} ${i < stepIdx ? 'done' : ''}`}
                   onClick={() => i < stepIdx && setStepIdx(i)}>
                <div className="num">{i + 1}</div>
                <div>{s.label}</div>
              </div>
            ))}
          </div>
        </aside>
        <main className="main">
          {step.id === 'customer' &&
            <StepCustomer manifest={manifest} update={update} />}
          {step.id === 'deployment' &&
            <StepDeployment manifest={manifest} update={update} />}
          {step.id === 'datasources' &&
            <StepDataSources manifest={manifest} update={update} catalog={catalog.dataSources}
                             saveManifest={saveManifest} savedManifestId={savedManifestId} />}
          {step.id === 'audience' &&
            <StepAudience manifest={manifest} update={update}
                          kpiCatalog={catalog.kpis} audienceCatalog={catalog.audiences} />}
          {step.id === 'observability' &&
            <StepObservability manifest={manifest} update={update} />}
          {step.id === 'rbac' &&
            <StepRBAC manifest={manifest} update={update} />}
          {step.id === 'custom' &&
            <StepCustom manifest={manifest} update={update} />}
          {step.id === 'review' &&
            <StepReview manifest={manifest} />}
          {step.id === 'build' &&
            <StepBuild build={build} startBuild={startBuild} manifest={manifest}
                       run={run} runApp={runApp} stopApp={stopApp} />}

          <div className="actions">
            <button className="btn btn-secondary" onClick={goPrev} disabled={stepIdx === 0}>← Back</button>
            {step.id !== 'build' &&
              <button className="btn btn-primary" onClick={goNext} disabled={!stepValid}>
                Next →
              </button>}
          </div>
        </main>
      </div>
    </div>
  );
}

// ─── Step 1: Customer & capabilities ────────────────────────────────
function StepCustomer({ manifest, update }) {
  const toggle = (id) => {
    const has = manifest.capabilities.includes(id);
    update({ capabilities: has ? manifest.capabilities.filter(c => c !== id) : [...manifest.capabilities, id] });
  };
  return (
    <>
      <header className="step-header">
        <div className="step-eyebrow">Step 1 of 9</div>
        <h1 className="step-title">Tell us about the customer</h1>
        <div className="step-desc">Who this app is for, and what they want it to do.</div>
      </header>
      <div className="card">
        <h4>Customer details</h4>
        <div className="row">
          <div className="field">
            <label>Company name *</label>
            <input value={manifest.customer.company_name}
                   onChange={(e) => update({ customer: { ...manifest.customer, company_name: e.target.value }})}
                   placeholder="Acme Corp" />
          </div>
          <div className="field">
            <label>Industry</label>
            <input value={manifest.customer.industry}
                   onChange={(e) => update({ customer: { ...manifest.customer, industry: e.target.value }})}
                   placeholder="retail, finance, healthcare…" />
          </div>
        </div>
        <div className="row">
          <div className="field">
            <label>Contact email</label>
            <input type="email" value={manifest.customer.contact_email}
                   onChange={(e) => update({ customer: { ...manifest.customer, contact_email: e.target.value }})}
                   placeholder="cto@acme.com" />
          </div>
          <div className="field">
            <label>Primary use case</label>
            <input value={manifest.customer.primary_use_case}
                   onChange={(e) => update({ customer: { ...manifest.customer, primary_use_case: e.target.value }})}
                   placeholder="forecasting & anomaly alerts" />
          </div>
        </div>
      </div>
      <div className="card">
        <h4>Capabilities to enable</h4>
        <div className="help">Each capability ships as a self-contained module. Pick the ones the customer needs — you can always add more later.</div>
        <div className="chip-grid" style={{marginTop: 14}}>
          {CAPABILITIES.map(c => {
            const on = manifest.capabilities.includes(c.id);
            return (
              <div key={c.id} className={`chip ${on ? 'on' : ''}`} onClick={() => toggle(c.id)}>
                <div className="chip-title">
                  <span className="check">{on ? '✓' : ''}</span>
                  {c.label}
                </div>
                <div className="chip-desc">{c.desc}</div>
              </div>
            );
          })}
        </div>
      </div>
    </>
  );
}

// ─── Step 2: Deployment ─────────────────────────────────────────────
function StepDeployment({ manifest, update }) {
  const targets = [
    { id: 'localhost',   label: 'Localhost (demo)', desc: 'Run on a single machine via docker-compose' },
    { id: 'cloud_aws',   label: 'AWS',              desc: 'EKS + RDS + S3 — Terraform skeleton generated' },
    { id: 'cloud_azure', label: 'Azure',            desc: 'AKS + Postgres Flexible — Terraform skeleton' },
    { id: 'cloud_gcp',   label: 'Google Cloud',     desc: 'GKE + Cloud SQL — Terraform skeleton' },
    { id: 'on_prem',     label: 'On-premise',       desc: 'Customer-managed Kubernetes cluster' },
    { id: 'hybrid',      label: 'Hybrid',           desc: 'Mixed cloud + on-prem' },
  ];
  const owners = [
    { id: 'self_managed',  label: 'Self-managed',  desc: 'Customer runs and operates' },
    { id: 'fully_managed', label: 'Fully managed', desc: 'We run and operate as SaaS' },
    { id: 'co_managed',    label: 'Co-managed',    desc: 'Shared operational responsibility' },
  ];
  return (
    <>
      <header className="step-header">
        <div className="step-eyebrow">Step 2 of 9</div>
        <h1 className="step-title">Where will it run?</h1>
        <div className="step-desc">Choose deployment target and operational model. The generator emits the matching IaC skeleton.</div>
      </header>
      <div className="card">
        <h4>Deployment target</h4>
        <div className="chip-grid" style={{marginTop: 14}}>
          {targets.map(t => (
            <div key={t.id}
                 className={`chip ${manifest.deployment === t.id ? 'on' : ''}`}
                 onClick={() => update({ deployment: t.id })}>
              <div className="chip-title">
                <span className="check">{manifest.deployment === t.id ? '✓' : ''}</span>
                {t.label}
              </div>
              <div className="chip-desc">{t.desc}</div>
            </div>
          ))}
        </div>
      </div>
      <div className="card">
        <h4>Operational model</h4>
        <div className="chip-grid" style={{marginTop: 14}}>
          {owners.map(t => (
            <div key={t.id}
                 className={`chip ${manifest.infra_ownership === t.id ? 'on' : ''}`}
                 onClick={() => update({ infra_ownership: t.id })}>
              <div className="chip-title">
                <span className="check">{manifest.infra_ownership === t.id ? '✓' : ''}</span>
                {t.label}
              </div>
              <div className="chip-desc">{t.desc}</div>
            </div>
          ))}
        </div>
      </div>
      {manifest.deployment.startsWith('cloud') && (
        <div className="card">
          <h4>Region</h4>
          <div className="field">
            <input value={manifest.cloud_region}
                   onChange={(e) => update({ cloud_region: e.target.value })}
                   placeholder="us-east-1" />
            <div className="help">e.g. us-east-1, eu-west-1, ap-south-1</div>
          </div>
        </div>
      )}
    </>
  );
}

// ─── Step 3: Data sources ───────────────────────────────────────────
function StepDataSources({ manifest, update, catalog, saveManifest, savedManifestId }) {
  const [pickerOpen, setPickerOpen] = useState(false);
  const [secretModal, setSecretModal] = useState(null); // { dsId, name, description }

  const addSource = (kind) => {
    const id = `ds_${Math.random().toString(36).substring(2, 10)}`;
    const ds = catalog?.find((c) => c.kind === kind);
    const newDs = {
      id,
      name: `${kind}_source`,
      kind,
      auth_method: ds?.auth?.[0] || 'password',
      connection_template: '',
      secret_ref: '',
      schema_hint: null,
      refresh_schedule: '0 */6 * * *',
      description: '',
    };
    update({ data_sources: [...manifest.data_sources, newDs] });
    setPickerOpen(false);
  };

  const removeSource = (id) =>
    update({ data_sources: manifest.data_sources.filter((d) => d.id !== id) });

  const updateSource = (id, patch) =>
    update({ data_sources: manifest.data_sources.map((d) => (d.id === id ? { ...d, ...patch } : d)) });

  const openSecretFor = async (ds) => {
    if (!savedManifestId) await saveManifest();
    setSecretModal({ dsId: ds.id, name: '', value: '', description: '' });
  };

  const submitSecret = async () => {
    const mid = savedManifestId || (await saveManifest());
    const sm = secretModal;
    const res = await apiPost(`/api/manifests/${mid}/secrets`, {
      name: sm.name || `${sm.dsId}_secret`,
      value: sm.value,
      description: sm.description,
    });
    updateSource(sm.dsId, { secret_ref: res.secret_ref });
    setSecretModal(null);
  };

  return (
    <>
      <header className="step-header">
        <div className="step-eyebrow">Step 3 of 9</div>
        <h1 className="step-title">Connect data sources</h1>
        <div className="step-desc">Pick the systems the app should pull data from. Secrets are stored encrypted on the platform — never in the manifest.</div>
      </header>
      <div className="banner banner-info">
        <strong>How secrets work:</strong> when you fill in a password or API key, the platform encrypts it with Fernet and replaces it in the manifest with a <code>secret_ref</code>. The generated app reads via that ref. The raw value never appears in logs, configs, or the manifest file.
      </div>
      {!pickerOpen && (
        <div style={{marginBottom: 14}}>
          <button className="btn-add" onClick={() => setPickerOpen(true)}>+ Add data source</button>
        </div>
      )}
      {pickerOpen && (
        <div className="card">
          <h4>Pick a source type</h4>
          <div className="ds-grid">
            {(catalog || []).map((c) => (
              <div key={c.kind} className="ds-tile" onClick={() => addSource(c.kind)}>
                <div className="ds-tile-name">{c.label}</div>
                <div className="ds-tile-auth">{c.auth.join(' · ')}</div>
              </div>
            ))}
          </div>
          <div style={{marginTop: 14}}>
            <button className="btn-link" onClick={() => setPickerOpen(false)}>Cancel</button>
          </div>
        </div>
      )}
      {manifest.data_sources.map((ds) => {
        const cat = catalog?.find((c) => c.kind === ds.kind);
        return (
          <div key={ds.id} className="ds-config">
            <div className="ds-config-head">
              <div>
                <span className="name">{cat?.label || ds.kind}</span>
                <span style={{color: 'var(--text-muted)', fontSize: 11, marginLeft: 8}} className="mono">{ds.id}</span>
              </div>
              <button className="btn-x" onClick={() => removeSource(ds.id)}>×</button>
            </div>
            <div className="row">
              <div className="field">
                <label>Display name</label>
                <input value={ds.name} onChange={(e) => updateSource(ds.id, { name: e.target.value })} />
              </div>
              <div className="field">
                <label>Auth method</label>
                <select value={ds.auth_method} onChange={(e) => updateSource(ds.id, { auth_method: e.target.value })}>
                  {(cat?.auth || ['password']).map((a) => <option key={a} value={a}>{a}</option>)}
                </select>
              </div>
            </div>
            <div className="field">
              <label>Connection template (use placeholders, NEVER literal secrets)</label>
              <input value={ds.connection_template}
                     onChange={(e) => updateSource(ds.id, { connection_template: e.target.value })}
                     placeholder="postgresql://user:{{PWD}}@host:5432/db" />
            </div>
            <div className="field">
              <label>Secret reference</label>
              <div style={{display: 'flex', gap: 8}}>
                <input value={ds.secret_ref} readOnly placeholder="not set"
                       style={{fontFamily: "'JetBrains Mono', monospace", fontSize: 12, flex: 1}} />
                <button className="btn btn-secondary" onClick={() => openSecretFor(ds)}>
                  {ds.secret_ref ? 'Update secret' : 'Add secret'}
                </button>
              </div>
              <div className="help">Refs look like <code>secret://forge/&lt;manifest&gt;/&lt;name&gt;</code>. The actual value lives encrypted.</div>
            </div>
            <div className="field">
              <label>Description</label>
              <input value={ds.description}
                     onChange={(e) => updateSource(ds.id, { description: e.target.value })}
                     placeholder="What lives in this source?" />
            </div>
          </div>
        );
      })}
      {secretModal && (
        <SecretModal
          state={secretModal}
          setState={setSecretModal}
          onSubmit={submitSecret}
          onCancel={() => setSecretModal(null)}
        />
      )}
    </>
  );
}

function SecretModal({ state, setState, onSubmit, onCancel }) {
  return (
    <div style={{position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.6)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 100}}>
      <div className="card" style={{width: 'min(440px, 90vw)', margin: 0}}>
        <h4>Store a secret</h4>
        <div className="help">This will be encrypted at rest. The manifest will only contain the reference.</div>
        <div className="field" style={{marginTop: 14}}>
          <label>Name</label>
          <input value={state.name} onChange={(e) => setState({...state, name: e.target.value})}
                 placeholder="db_password" />
        </div>
        <div className="field">
          <label>Value</label>
          <input type="password" value={state.value} onChange={(e) => setState({...state, value: e.target.value})}
                 placeholder="••••••••••" />
        </div>
        <div className="field">
          <label>Description (optional)</label>
          <input value={state.description} onChange={(e) => setState({...state, description: e.target.value})} />
        </div>
        <div style={{display: 'flex', gap: 8, justifyContent: 'flex-end', marginTop: 8}}>
          <button className="btn btn-secondary" onClick={onCancel}>Cancel</button>
          <button className="btn btn-primary" disabled={!state.value} onClick={onSubmit}>Save secret</button>
        </div>
      </div>
    </div>
  );
}

// ─── Step 4: Audience & KPIs ────────────────────────────────────────
function StepAudience({ manifest, update, kpiCatalog, audienceCatalog }) {
  const allKpis = useMemo(() => {
    if (!kpiCatalog) return [];
    const out = [];
    for (const [domainId, dom] of Object.entries(kpiCatalog.domains || {})) {
      for (const k of dom.kpis) out.push({ ...k, domain: domainId, domain_label: dom.label, icon: dom.icon });
    }
    return out;
  }, [kpiCatalog]);

  const toggleAudience = (a) => {
    const has = manifest.audiences.find((x) => x.id === a.id);
    if (has) {
      update({ audiences: manifest.audiences.filter((x) => x.id !== a.id) });
    } else {
      // Add audience and auto-select its default KPIs
      const next = [...manifest.audiences, {
        id: a.id, name: a.name, description: a.description,
        default_kpi_ids: a.default_kpi_ids,
        suggested_questions: a.suggested_questions,
      }];
      const newKpis = [...manifest.kpis];
      for (const kid of a.default_kpi_ids) {
        if (!newKpis.find((k) => k.id === kid)) {
          const cat = allKpis.find((x) => x.id === kid);
          if (cat) newKpis.push(toKPIDef(cat));
        }
      }
      update({ audiences: next, kpis: newKpis });
    }
  };

  const toggleKpi = (kpi) => {
    const has = manifest.kpis.find((k) => k.id === kpi.id);
    if (has) update({ kpis: manifest.kpis.filter((k) => k.id !== kpi.id) });
    else update({ kpis: [...manifest.kpis, toKPIDef(kpi)] });
  };

  const filterText = useState('');
  const [filter, setFilter] = useState('');

  return (
    <>
      <header className="step-header">
        <div className="step-eyebrow">Step 4 of 9</div>
        <h1 className="step-title">Audience & metrics</h1>
        <div className="step-desc">Pick personas (each unlocks a tailored dashboard) and the metrics they care about. Adding an audience auto-selects its default KPIs.</div>
      </header>
      <div className="card">
        <h4>Target audiences</h4>
        <div className="chip-grid" style={{marginTop: 14}}>
          {(audienceCatalog?.audiences || []).map((a) => {
            const on = manifest.audiences.find((x) => x.id === a.id);
            return (
              <div key={a.id} className={`chip ${on ? 'on' : ''}`} onClick={() => toggleAudience(a)}>
                <div className="chip-title"><span className="check">{on ? '✓' : ''}</span>{a.name}</div>
                <div className="chip-desc">{a.description}</div>
              </div>
            );
          })}
        </div>
      </div>
      <div className="card">
        <h4>KPI catalog · {manifest.kpis.length} selected</h4>
        <div className="field" style={{marginTop: 8}}>
          <input placeholder="Filter KPIs (e.g. revenue, churn, latency)…"
                 value={filter} onChange={(e) => setFilter(e.target.value)} />
        </div>
        {Object.entries(kpiCatalog?.domains || {}).map(([dId, dom]) => {
          const visible = dom.kpis.filter((k) =>
            !filter || k.name.toLowerCase().includes(filter.toLowerCase()) ||
                       (k.description || '').toLowerCase().includes(filter.toLowerCase()));
          if (visible.length === 0) return null;
          return (
            <div key={dId} className="kpi-domain">
              <div className="kpi-domain-label">
                <span>{dom.icon} {dom.label}</span>
                <span className="count">{visible.length} metrics</span>
              </div>
              <div className="kpi-list">
                {visible.map((k) => {
                  const on = !!manifest.kpis.find((x) => x.id === k.id);
                  return (
                    <div key={k.id} className={`kpi-item ${on ? 'on' : ''}`}
                         onClick={() => toggleKpi({ ...k, domain: dId })}>
                      <div className="kpi-item-name">
                        <span>{k.name}</span>
                        <span style={{color: on ? 'var(--accent)' : 'var(--text-muted)'}}>{on ? '✓' : '+'}</span>
                      </div>
                      <div className="kpi-item-formula">{k.formula}</div>
                      <div className="kpi-item-meta">
                        <span className="kpi-tag">{k.unit}</span>
                        <span className="kpi-tag">{k.chart_type}</span>
                        {k.higher_is_better === false && <span className="kpi-tag">lower=better</span>}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          );
        })}
      </div>
    </>
  );
}

function toKPIDef(catalogKpi) {
  return {
    id: catalogKpi.id,
    name: catalogKpi.name,
    domain: catalogKpi.domain,
    formula: catalogKpi.formula,
    unit: catalogKpi.unit,
    higher_is_better: catalogKpi.higher_is_better !== false,
    chart_type: catalogKpi.chart_type || 'line',
    target_value: catalogKpi.target_value || null,
    alert_threshold_pct: catalogKpi.alert_threshold_pct || null,
    refresh_cadence: catalogKpi.refresh_cadence || 'daily',
    audiences: [],
  };
}

// ─── Step 5: Observability ──────────────────────────────────────────
function StepObservability({ manifest, update }) {
  const tiers = [
    { id: 'basic',     label: 'Basic',     desc: 'Logs only · 7-day retention' },
    { id: 'standard',  label: 'Standard',  desc: 'Logs + metrics + traces · Prometheus + Grafana + Loki bundled' },
    { id: 'advanced',  label: 'Advanced',  desc: 'Standard + audit log + data lineage + cost tracking' },
    { id: 'regulated', label: 'Regulated', desc: 'Advanced + immutable audit + approval workflows · for SOC 2 / HIPAA' },
  ];
  const obs = manifest.observability;
  const setObs = (patch) => update({ observability: { ...obs, ...patch }});

  return (
    <>
      <header className="step-header">
        <div className="step-eyebrow">Step 5 of 9</div>
        <h1 className="step-title">Observability tier</h1>
        <div className="step-desc">More observability = more cost and more confidence. Pick what fits the customer's risk profile.</div>
      </header>
      <div className="card">
        <h4>Tier</h4>
        <div className="chip-grid" style={{marginTop: 14}}>
          {tiers.map((t) => (
            <div key={t.id} className={`chip ${obs.tier === t.id ? 'on' : ''}`}
                 onClick={() => setObs({ tier: t.id })}>
              <div className="chip-title"><span className="check">{obs.tier === t.id ? '✓' : ''}</span>{t.label}</div>
              <div className="chip-desc">{t.desc}</div>
            </div>
          ))}
        </div>
      </div>
      <div className="card">
        <h4>Retention & destinations</h4>
        <div className="row">
          <div className="field">
            <label>Log retention (days)</label>
            <input type="number" value={obs.log_retention_days}
                   onChange={(e) => setObs({ log_retention_days: parseInt(e.target.value) || 0 })} />
          </div>
          <div className="field">
            <label>Audit retention (days)</label>
            <input type="number" value={obs.audit_retention_days}
                   onChange={(e) => setObs({ audit_retention_days: parseInt(e.target.value) || 0 })} />
          </div>
        </div>
        <div className="row">
          <div className="field">
            <label>Metrics backend</label>
            <select value={obs.metrics_backend}
                    onChange={(e) => setObs({ metrics_backend: e.target.value })}>
              <option value="prometheus">Prometheus</option>
              <option value="datadog">Datadog</option>
              <option value="cloudwatch">CloudWatch</option>
              <option value="azure_monitor">Azure Monitor</option>
            </select>
          </div>
          <div className="field">
            <label>Tracing backend</label>
            <select value={obs.traces_backend}
                    onChange={(e) => setObs({ traces_backend: e.target.value })}>
              <option value="tempo">Grafana Tempo</option>
              <option value="jaeger">Jaeger</option>
              <option value="datadog">Datadog</option>
              <option value="x-ray">AWS X-Ray</option>
              <option value="none">None</option>
            </select>
          </div>
        </div>
        <div className="field">
          <label>Alert channels</label>
          <input placeholder="slack:#data-alerts, email:ops@acme.com"
                 value={(obs.alert_channels || []).join(', ')}
                 onChange={(e) => setObs({
                   alert_channels: e.target.value.split(',').map((s) => s.trim()).filter(Boolean) })} />
        </div>
        <div className="field" style={{display: 'flex', gap: 18, flexWrap: 'wrap'}}>
          <Toggle label="Data lineage tracking" value={obs.enable_data_lineage}
                  onChange={(v) => setObs({ enable_data_lineage: v })} />
          <Toggle label="Query audit log" value={obs.enable_query_audit}
                  onChange={(v) => setObs({ enable_query_audit: v })} />
          <Toggle label="Cost tracking" value={obs.enable_cost_tracking}
                  onChange={(v) => setObs({ enable_cost_tracking: v })} />
        </div>
      </div>
    </>
  );
}

function Toggle({ label, value, onChange }) {
  return (
    <label style={{display: 'inline-flex', gap: 8, alignItems: 'center', cursor: 'pointer'}}>
      <input type="checkbox" checked={value} onChange={(e) => onChange(e.target.checked)} />
      <span>{label}</span>
    </label>
  );
}

// ─── Step 6: RBAC ───────────────────────────────────────────────────
function StepRBAC({ manifest, update }) {
  const rbac = manifest.rbac;
  const setRbac = (patch) => update({ rbac: { ...rbac, ...patch }});
  const updateRole = (id, patch) =>
    setRbac({ roles: rbac.roles.map((r) => (r.id === id ? { ...r, ...patch } : r)) });
  const addRole = () => {
    const id = `role_${Math.random().toString(36).substring(2, 8)}`;
    setRbac({ roles: [...rbac.roles, { id, name: 'New Role', description: '', column_policies: [],
                                         row_policies: [], capabilities: [], can_export: true,
                                         can_share: false, requires_approval_for: [] }] });
  };
  const removeRole = (id) =>
    setRbac({ roles: rbac.roles.filter((r) => r.id !== id) });

  return (
    <>
      <header className="step-header">
        <div className="step-eyebrow">Step 6 of 9</div>
        <h1 className="step-title">Access control</h1>
        <div className="step-desc">Define roles and policies down to the row and column. Policies are enforced at query rewrite time — they cannot be bypassed by the app.</div>
      </header>
      <div className="card">
        <h4>Authentication</h4>
        <div className="row">
          <div className="field">
            <label>SSO provider</label>
            <select value={rbac.sso_provider} onChange={(e) => setRbac({ sso_provider: e.target.value })}>
              <option value="none">None (basic auth)</option>
              <option value="azure_ad">Azure AD / Entra</option>
              <option value="okta">Okta</option>
              <option value="google">Google Workspace</option>
              <option value="saml">SAML 2.0 (generic)</option>
            </select>
          </div>
          <div className="field" style={{display: 'flex', alignItems: 'center', paddingTop: 24}}>
            <Toggle label="Require MFA" value={rbac.mfa_required}
                    onChange={(v) => setRbac({ mfa_required: v })} />
          </div>
        </div>
      </div>
      <div className="card">
        <h4>Roles</h4>
        <div className="help">Each role can have column policies (mask/redact/hash specific columns) and row policies (filter rows by user attributes).</div>
        {rbac.roles.map((role) => (
          <RoleEditor key={role.id} role={role}
                      onChange={(patch) => updateRole(role.id, patch)}
                      onRemove={() => removeRole(role.id)} />
        ))}
        <button className="btn-add" onClick={addRole}>+ Add role</button>
      </div>
    </>
  );
}

function RoleEditor({ role, onChange, onRemove }) {
  const addColPol = () =>
    onChange({ column_policies: [...role.column_policies, { column_pattern: '', action: 'mask', mask_pattern: '***' }] });
  const updColPol = (i, patch) =>
    onChange({ column_policies: role.column_policies.map((p, j) => (j === i ? { ...p, ...patch } : p)) });
  const rmColPol = (i) =>
    onChange({ column_policies: role.column_policies.filter((_, j) => j !== i) });

  const addRowPol = () =>
    onChange({ row_policies: [...role.row_policies, { table_pattern: '*', where_expression: '' }] });
  const updRowPol = (i, patch) =>
    onChange({ row_policies: role.row_policies.map((p, j) => (j === i ? { ...p, ...patch } : p)) });
  const rmRowPol = (i) =>
    onChange({ row_policies: role.row_policies.filter((_, j) => j !== i) });

  return (
    <div className="role-card">
      <div className="role-head">
        <div style={{display: 'flex', gap: 8, alignItems: 'center'}}>
          <input value={role.name} onChange={(e) => onChange({ name: e.target.value })}
                 style={{fontWeight: 600, padding: '6px 10px', minWidth: 180}} />
          <span className="mono" style={{color: 'var(--text-muted)', fontSize: 11}}>{role.id}</span>
        </div>
        <button className="btn-x" onClick={onRemove}>×</button>
      </div>
      <div className="field">
        <label>Description</label>
        <input value={role.description} onChange={(e) => onChange({ description: e.target.value })} />
      </div>
      <div className="field">
        <label>Column policies</label>
        {role.column_policies.map((pol, i) => (
          <div key={i} className="policy-row">
            <input placeholder="column_pattern (e.g. *.salary)"
                   value={pol.column_pattern}
                   onChange={(e) => updColPol(i, { column_pattern: e.target.value })} />
            <select value={pol.action} onChange={(e) => updColPol(i, { action: e.target.value })}>
              <option value="allow">allow</option>
              <option value="deny">deny</option>
              <option value="mask">mask</option>
              <option value="hash">hash</option>
              <option value="redact">redact</option>
            </select>
            <input placeholder="mask pattern (if mask)"
                   value={pol.mask_pattern || ''}
                   onChange={(e) => updColPol(i, { mask_pattern: e.target.value })} />
            <button className="btn-x" onClick={() => rmColPol(i)}>×</button>
          </div>
        ))}
        <button className="btn-link" onClick={addColPol}>+ Column policy</button>
      </div>
      <div className="field">
        <label>Row policies</label>
        {role.row_policies.map((pol, i) => (
          <div key={i} className="policy-row" style={{gridTemplateColumns: '1fr 2fr auto auto'}}>
            <input placeholder="table_pattern" value={pol.table_pattern}
                   onChange={(e) => updRowPol(i, { table_pattern: e.target.value })} />
            <input placeholder="WHERE clause (use ${user.attribute})"
                   value={pol.where_expression}
                   onChange={(e) => updRowPol(i, { where_expression: e.target.value })} />
            <span></span>
            <button className="btn-x" onClick={() => rmRowPol(i)}>×</button>
          </div>
        ))}
        <button className="btn-link" onClick={addRowPol}>+ Row policy</button>
      </div>
      <div className="field" style={{display: 'flex', gap: 18, flexWrap: 'wrap'}}>
        <Toggle label="Can export" value={role.can_export} onChange={(v) => onChange({ can_export: v })} />
        <Toggle label="Can share" value={role.can_share} onChange={(v) => onChange({ can_share: v })} />
      </div>
    </div>
  );
}

// ─── Step 7: Custom requests ────────────────────────────────────────
function StepCustom({ manifest, update }) {
  const add = () => update({ custom_requests: [
    ...manifest.custom_requests, { title: '', description: '', priority: 'nice_to_have' }] });
  const upd = (i, patch) => update({
    custom_requests: manifest.custom_requests.map((c, j) => (j === i ? { ...c, ...patch } : c))
  });
  const rm = (i) => update({ custom_requests: manifest.custom_requests.filter((_, j) => j !== i) });
  return (
    <>
      <header className="step-header">
        <div className="step-eyebrow">Step 7 of 9</div>
        <h1 className="step-title">Custom requests</h1>
        <div className="step-desc">Anything that didn't fit the templates. These get captured as feature-flag stubs in the generated app, with TODOs in the README.</div>
      </header>
      <div className="card">
        {manifest.custom_requests.map((req, i) => (
          <div key={i} className="ds-config">
            <div className="ds-config-head">
              <span className="name">Request #{i + 1}</span>
              <button className="btn-x" onClick={() => rm(i)}>×</button>
            </div>
            <div className="row">
              <div className="field">
                <label>Title</label>
                <input value={req.title} onChange={(e) => upd(i, { title: e.target.value })} />
              </div>
              <div className="field">
                <label>Priority</label>
                <select value={req.priority} onChange={(e) => upd(i, { priority: e.target.value })}>
                  <option value="must_have">Must have</option>
                  <option value="nice_to_have">Nice to have</option>
                  <option value="future">Future</option>
                </select>
              </div>
            </div>
            <div className="field">
              <label>Description</label>
              <textarea value={req.description} onChange={(e) => upd(i, { description: e.target.value })} />
            </div>
          </div>
        ))}
        <button className="btn-add" onClick={add}>+ Add request</button>
      </div>
    </>
  );
}

// ─── Step 8: Review ─────────────────────────────────────────────────
function StepReview({ manifest }) {
  return (
    <>
      <header className="step-header">
        <div className="step-eyebrow">Step 8 of 9</div>
        <h1 className="step-title">Review</h1>
        <div className="step-desc">Quick summary before we generate. You can still go back and tweak anything.</div>
      </header>
      <div className="review-grid">
        <Tile label="Customer"            value={manifest.customer.company_name || '—'} />
        <Tile label="Industry"            value={manifest.customer.industry || '—'} />
        <Tile label="Capabilities"        value={`${manifest.capabilities.length} enabled`} />
        <Tile label="Deployment"          value={manifest.deployment} />
        <Tile label="Operational model"   value={manifest.infra_ownership.replace(/_/g, ' ')} />
        <Tile label="Data sources"        value={`${manifest.data_sources.length} configured`} />
        <Tile label="Audiences"           value={`${manifest.audiences.length} personas`} />
        <Tile label="KPIs"                value={`${manifest.kpis.length} metrics`} />
        <Tile label="Observability tier"  value={manifest.observability.tier} />
        <Tile label="Roles"               value={`${manifest.rbac.roles.length} roles`} />
        <Tile label="SSO"                 value={manifest.rbac.sso_provider} />
        <Tile label="Custom requests"     value={`${manifest.custom_requests.length} items`} />
      </div>
      <div className="divider"></div>
      <details>
        <summary style={{cursor: 'pointer', color: 'var(--text-dim)'}}>Show full manifest JSON</summary>
        <pre style={{marginTop: 14, padding: 14, background: 'var(--panel-2)',
                     borderRadius: 8, overflow: 'auto', fontSize: 11, maxHeight: 360}}>
{JSON.stringify(manifest, null, 2)}
        </pre>
      </details>
    </>
  );
}

function Tile({ label, value }) {
  return (
    <div className="review-tile">
      <div className="review-label">{label}</div>
      <div className="review-value">{value}</div>
    </div>
  );
}

// ─── Step 9: Build ──────────────────────────────────────────────────
function StepBuild({ build, startBuild, manifest, run, runApp, stopApp }) {
  const consoleRef = useRef(null);
  const [allLive, setAllLive] = useState(false);
  useEffect(() => {
    if (consoleRef.current) consoleRef.current.scrollTop = consoleRef.current.scrollHeight;
  }, [build.events.length]);
  // Reset the "all live" gate whenever a run stops/restarts.
  useEffect(() => { if (run.status !== 'running') setAllLive(false); }, [run.status]);

  const isDone = build.status === 'done';
  const isRunning = build.status === 'running' || build.status === 'starting';
  const appId = appIdFromPath(build.outputPath);

  return (
    <>
      <header className="step-header">
        <div className="step-eyebrow">Step 9 of 9</div>
        <h1 className="step-title">Generate the application</h1>
        <div className="step-desc">The wizard will hand the manifest to the generator. You'll watch each step happen in real time.</div>
      </header>

      {build.status === 'idle' && (
        <div className="card" style={{textAlign: 'center', padding: 40}}>
          <h3 style={{marginBottom: 12}}>Ready to forge {manifest.customer.company_name || 'this app'}</h3>
          <p style={{color: 'var(--text-dim)', marginBottom: 20}}>
            We'll generate a self-contained package with backend, frontend, IaC, observability, RBAC, and CI/CD.
          </p>
          <button className="btn btn-primary" onClick={startBuild} style={{padding: '14px 28px', fontSize: 15}}>
            🔨 Forge it
          </button>
        </div>
      )}

      {build.status !== 'idle' && (
        <div className="card">
          <div className="build-bar">
            <div className="build-bar-fill" style={{width: `${build.progress}%`}}></div>
          </div>
          <div className="build-console" ref={consoleRef}>
            {build.events.length === 0 && (
              <div className="build-line"><span className="stamp">···</span><span>Connecting…</span></div>
            )}
            {build.events.map((ev, i) => {
              const t = (ev.ts || '').slice(11, 19);
              const cls = ev.status === 'ok' ? 'lvl-ok' : (ev.status === 'error' ? 'lvl-error' : 'lvl-started');
              return (
                <div key={i} className="build-line">
                  <span className="stamp">[{t}]</span>
                  <span className={cls}>{ev.step.padEnd(15)}</span>
                  <span style={{color: 'var(--text)'}}>{ev.message}</span>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {isDone && (
        <div className="card final">
          <h2>✅ Application generated</h2>

          {run.status !== 'running' && (
            <>
              <p style={{color: 'var(--text-dim)', maxWidth: 560, margin: '0 auto 6px'}}>
                Your customer-tailored package is ready. Launch it right here — Forge
                will start the backend and frontend for you and hand back a live URL.
                No Docker required.
              </p>
              <div style={{margin: '18px 0'}}>
                <button className="btn btn-primary" onClick={runApp}
                        disabled={run.status === 'launching'}
                        style={{padding: '14px 28px', fontSize: 15}}>
                  {run.status === 'launching' ? '⏳ Starting the app…' : '▶ Build & run it'}
                </button>
              </div>
              {run.status === 'error' && (
                <div className="banner banner-warn" style={{textAlign: 'left'}}>
                  <strong>Couldn't start the app.</strong>
                  <pre style={{whiteSpace: 'pre-wrap', fontSize: 11, marginTop: 8}}>{run.error}</pre>
                </div>
              )}
            </>
          )}

          {run.status === 'running' && run.urls && (
            <div style={{textAlign: 'left'}}>
              <p style={{color: 'var(--text-dim)', textAlign: 'center', margin: '0 auto 12px'}}>
                Your application is coming online — watch each component boot up and start
                exchanging data:
              </p>
              <LiveTopology appId={appId} onAllLive={() => setAllLive(true)} />

              <div style={{textAlign: 'center', marginTop: 18}}>
                <a className="url-pill" href={run.urls.frontend_url} target="_blank" rel="noopener"
                   style={{display: 'inline-block', textDecoration: 'none'}}>
                  {run.urls.frontend_url} ↗
                </a>
                <p style={{color: 'var(--text-muted)', fontSize: 12, marginTop: 12}}>
                  Frontend: <a href={run.urls.frontend_url} target="_blank" rel="noopener">{run.urls.frontend_url}</a>
                  {'  ·  '}
                  API: <a href={run.urls.health_url} target="_blank" rel="noopener">{run.urls.backend_url}</a>
                  {'  ·  '}
                  <a onClick={stopApp} style={{cursor: 'pointer'}}>■ Stop</a>
                </p>
              </div>

              {allLive
                ? <VerifyPanel appId={appId} />
                : <div className="help" style={{textAlign: 'center', marginTop: 10}}>
                    Verification unlocks once every component is live…
                  </div>}
            </div>
          )}

          <details style={{marginTop: 18, textAlign: 'left'}}>
            <summary style={{cursor: 'pointer', color: 'var(--text-muted)', fontSize: 12}}>
              Prefer Docker? (needs Docker Desktop running)
            </summary>
            <div className="url-pill" style={{marginTop: 10}}>
              cd {build.outputPath || 'generated_apps/…'}
              <br />
              docker-compose up --build
            </div>
          </details>
        </div>
      )}

      {build.status === 'error' && (
        <div className="banner banner-warn">
          <strong>Build failed.</strong> Check the console above. The most common cause is a missing template file
          — re-running usually resolves it once the platform is restarted.
        </div>
      )}
    </>
  );
}

// ─── Live animated topology ─────────────────────────────────────────
const TOPO_ORDER = ['frontend', 'backend', 'data', 'intelligence'];
const NODE_POS = {
  frontend:     { x: 24,  y: 110, w: 152, h: 82 },
  backend:      { x: 244, y: 110, w: 152, h: 82 },
  data:         { x: 462, y: 26,  w: 158, h: 78 },
  intelligence: { x: 462, y: 198, w: 158, h: 78 },
};
const DEFAULT_COMPS = [
  { id: 'frontend',     label: 'Web UI',          icon: '🖥️', status: 'starting' },
  { id: 'backend',      label: 'API service',     icon: '⚙️', status: 'starting' },
  { id: 'data',         label: 'Data & catalogs', icon: '🗄️', status: 'starting' },
  { id: 'intelligence', label: 'Insights engine', icon: '✨', status: 'starting' },
];
const TOPO_LINKS = [
  { source: 'frontend', target: 'backend',      d: 'M176,151 L244,151' },
  { source: 'backend',  target: 'data',         d: 'M396,140 L462,65'  },
  { source: 'backend',  target: 'intelligence', d: 'M396,162 L462,237' },
];

function LiveTopology({ appId, onAllLive }) {
  const [topo, setTopo] = useState(null);
  const [revealed, setRevealed] = useState(0);

  // Poll the real topology probe — node/link status reflects live health checks.
  useEffect(() => {
    if (!appId) return;
    let alive = true, timer;
    const poll = async () => {
      try {
        const t = await apiGet(`/api/apps/${appId}/topology`);
        if (!alive) return;
        setTopo(t);
        if (t.all_live && onAllLive) onAllLive();
      } catch (e) { /* keep trying while it boots */ }
      if (alive) timer = setTimeout(poll, 1200);
    };
    poll();
    return () => { alive = false; clearTimeout(timer); };
  }, [appId]);

  // Staggered reveal so components visibly "build" one after another.
  useEffect(() => {
    const timers = TOPO_ORDER.map((_, i) =>
      setTimeout(() => setRevealed((r) => Math.max(r, i + 1)), 450 * (i + 1)));
    return () => timers.forEach(clearTimeout);
  }, []);

  const comps = topo?.components || DEFAULT_COMPS;
  const linkActive = (s, t) =>
    !!(topo?.links || []).find((l) => l.source === s && l.target === t && l.active);

  return (
    <div className="topo-wrap">
      <div className="topo-title">
        <span>⚡ Live architecture</span>
      </div>
      <svg className="topo-svg" viewBox="0 0 644 300" preserveAspectRatio="xMidYMid meet">
        {TOPO_LINKS.map((l) => (
          <path key={`${l.source}>${l.target}`}
                className={`flow-line ${linkActive(l.source, l.target) ? 'active' : ''}`}
                d={l.d} />
        ))}
        {TOPO_ORDER.map((id, i) => {
          if (i >= revealed) return null;
          const c = comps.find((x) => x.id === id) || {};
          const p = NODE_POS[id];
          const live = c.status === 'live';
          return (
            <g key={id} className="node-g node-appear">
              <rect className={`node-box ${live ? 'live' : 'starting'}`}
                    x={p.x} y={p.y} width={p.w} height={p.h} rx="13" />
              <text className="node-icon" x={p.x + 26} y={p.y + p.h / 2 + 7} textAnchor="middle">{c.icon}</text>
              <text className="node-label" x={p.x + 50} y={p.y + p.h / 2 - 4}>{c.label}</text>
              <text className={`node-state ${live ? 'live' : 'starting'}`} x={p.x + 50} y={p.y + p.h / 2 + 14}>
                {live ? '● live' : '◌ starting…'}
              </text>
            </g>
          );
        })}
      </svg>
      <div className="topo-legend">
        <span className="k"><span className="legend-swatch"></span> animated link = data flowing</span>
        <span className="k">◌ starting · ● live</span>
      </div>
    </div>
  );
}

// ─── Golden-dataset verification ────────────────────────────────────
function VerifyPanel({ appId }) {
  const [state, setState] = useState({ status: 'idle', result: null, error: null });

  const runVerify = async () => {
    setState({ status: 'running', result: null, error: null });
    try {
      const res = await apiPost(`/api/apps/${appId}/verify`, {});
      setState({ status: 'done', result: res, error: null });
    } catch (e) {
      setState({ status: 'error', result: null, error: String(e.message || e) });
    }
  };

  const r = state.result;
  return (
    <div className="card" style={{marginTop: 16}}>
      <div className="verify-head">
        <div>
          <h4 style={{margin: 0}}>Demo run verification</h4>
          <div className="help">Runs a golden-dataset check against the live app to prove it
            behaves <em>correctly</em> — right KPIs, no secret leakage, NL query returns the
            expected answer — not just that it started.</div>
        </div>
        <button className="btn btn-primary" onClick={runVerify} disabled={state.status === 'running'}>
          {state.status === 'running'
            ? <span><span className="spin"></span> Verifying…</span>
            : '✓ Run demo verification'}
        </button>
      </div>

      {r && (
        <>
          <div className={`verify-summary ${r.ok ? 'ok' : 'bad'}`} style={{marginTop: 14}}>
            {r.ok
              ? `✅ Verified — all ${r.total} golden checks passed. Your application runs correctly.`
              : `⚠ ${r.passed}/${r.total} checks passed — see the failures below.`}
          </div>
          <div className="verify-list">
            {r.checks.map((c, i) => (
              <div key={i} className={`verify-row ${c.passed ? 'ok' : 'bad'}`}>
                <div className={`verify-badge ${c.passed ? 'ok' : 'bad'}`}>{c.passed ? '✓' : '✕'}</div>
                <div>
                  <div className="verify-name">{c.name}</div>
                  {c.detail && <div className="verify-detail">{c.detail}</div>}
                  {!c.passed &&
                    <div className="verify-diff">expected {JSON.stringify(c.expected)} · got {JSON.stringify(c.actual)}</div>}
                </div>
              </div>
            ))}
          </div>
        </>
      )}

      {state.status === 'error' &&
        <div className="banner banner-warn" style={{marginTop: 12}}>{state.error}</div>}
    </div>
  );
}

ReactDOM.createRoot(document.getElementById('root')).render(<App />);
