"use strict";

function ownKeys(e, r) { var t = Object.keys(e); if (Object.getOwnPropertySymbols) { var o = Object.getOwnPropertySymbols(e); r && (o = o.filter(function (r) { return Object.getOwnPropertyDescriptor(e, r).enumerable; })), t.push.apply(t, o); } return t; }
function _objectSpread(e) { for (var r = 1; r < arguments.length; r++) { var t = null != arguments[r] ? arguments[r] : {}; r % 2 ? ownKeys(Object(t), !0).forEach(function (r) { _defineProperty(e, r, t[r]); }) : Object.getOwnPropertyDescriptors ? Object.defineProperties(e, Object.getOwnPropertyDescriptors(t)) : ownKeys(Object(t)).forEach(function (r) { Object.defineProperty(e, r, Object.getOwnPropertyDescriptor(t, r)); }); } return e; }
function _defineProperty(e, r, t) { return (r = _toPropertyKey(r)) in e ? Object.defineProperty(e, r, { value: t, enumerable: !0, configurable: !0, writable: !0 }) : e[r] = t, e; }
function _toPropertyKey(t) { var i = _toPrimitive(t, "string"); return "symbol" == typeof i ? i : i + ""; }
function _toPrimitive(t, r) { if ("object" != typeof t || !t) return t; var e = t[Symbol.toPrimitive]; if (void 0 !== e) { var i = e.call(t, r || "default"); if ("object" != typeof i) return i; throw new TypeError("@@toPrimitive must return a primitive value."); } return ("string" === r ? String : Number)(t); }
function asyncGeneratorStep(n, t, e, r, o, a, c) { try { var i = n[a](c), u = i.value; } catch (n) { return void e(n); } i.done ? t(u) : Promise.resolve(u).then(r, o); }
function _asyncToGenerator(n) { return function () { var t = this, e = arguments; return new Promise(function (r, o) { var a = n.apply(t, e); function _next(n) { asyncGeneratorStep(a, r, o, _next, _throw, "next", n); } function _throw(n) { asyncGeneratorStep(a, r, o, _next, _throw, "throw", n); } _next(void 0); }); }; }
var {
  useState,
  useEffect,
  useReducer,
  useRef,
  useCallback,
  useMemo
} = React;
var API = ''; // same-origin

// ─── API helpers ─────────────────────────────────────────────────────
function api(_x, _x2) {
  return _api.apply(this, arguments);
}
function _api() {
  _api = _asyncToGenerator(function* (path, opts) {
    var r = yield fetch(API + path, opts);
    if (!r.ok) {
      var text = yield r.text().catch(() => '');
      throw new Error("".concat(r.status, " ").concat(text || r.statusText));
    }
    return r.json();
  });
  return _api.apply(this, arguments);
}
var apiGet = p => api(p);
var apiPost = (p, body) => api(p, {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json'
  },
  body: JSON.stringify(body)
});

// ─── Initial manifest ────────────────────────────────────────────────
var SCHEMA_VERSION = '1.0.0';
var initialManifest = () => ({
  schema_version: SCHEMA_VERSION,
  manifest_id: null,
  // assigned by backend on first save
  customer: {
    company_name: '',
    industry: '',
    contact_email: '',
    primary_use_case: ''
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
    enable_cost_tracking: false
  },
  rbac: {
    sso_provider: 'none',
    mfa_required: true,
    roles: [{
      id: 'admin',
      name: 'Administrator',
      description: 'Full access',
      column_policies: [],
      row_policies: [],
      capabilities: [],
      can_export: true,
      can_share: true,
      requires_approval_for: []
    }, {
      id: 'viewer',
      name: 'Viewer',
      description: 'Read-only access',
      column_policies: [],
      row_policies: [],
      capabilities: [],
      can_export: true,
      can_share: false,
      requires_approval_for: []
    }],
    default_role_id: 'viewer',
    approval_chain: []
  },
  custom_requests: [],
  branding: {
    app_name: '',
    primary_color: '#6ce5b1',
    accent_color: '#9d8df1'
  },
  feature_flags: {}
});

// ─── Steps definition ────────────────────────────────────────────────
var STEPS = [{
  id: 'customer',
  label: 'Customer & capabilities'
}, {
  id: 'deployment',
  label: 'Deployment topology'
}, {
  id: 'datasources',
  label: 'Data sources & secrets'
}, {
  id: 'audience',
  label: 'Audience & KPIs'
}, {
  id: 'observability',
  label: 'Observability'
}, {
  id: 'rbac',
  label: 'Access control'
}, {
  id: 'custom',
  label: 'Custom requests'
}, {
  id: 'review',
  label: 'Review'
}, {
  id: 'build',
  label: 'Build & launch'
}];
var CAPABILITIES = [{
  id: 'ai_dashboard',
  label: 'AI Dashboard',
  desc: 'KPI dashboards with AI commentary'
}, {
  id: 'nl_query',
  label: 'Natural Language Query',
  desc: 'Ask questions in plain English'
}, {
  id: 'anomaly_detection',
  label: 'Anomaly Detection',
  desc: 'Auto-flag unusual patterns'
}, {
  id: 'time_series_forecasting',
  label: 'Time-series Forecasting',
  desc: 'Predict future trends'
}, {
  id: 'fraud_detection',
  label: 'Fraud Detection',
  desc: 'Surface suspicious transactions'
}, {
  id: 'churn_prediction',
  label: 'Churn Prediction',
  desc: 'Identify at-risk customers'
}, {
  id: 'revenue_forecasting',
  label: 'Revenue Forecasting',
  desc: 'Project revenue scenarios'
}, {
  id: 'document_intelligence',
  label: 'Document Intelligence',
  desc: 'Q&A grounded in your PDFs'
}, {
  id: 'proactive_insights',
  label: 'Proactive Insights',
  desc: 'Daily/weekly digest of what changed'
}, {
  id: 'what_if_simulation',
  label: 'What-if Simulation',
  desc: 'Model scenarios and outcomes'
}, {
  id: 'executive_summary',
  label: 'Executive Summary',
  desc: 'Auto-generated narrative briefs'
}, {
  id: 'agentic_workflows',
  label: 'Agentic Workflows',
  desc: 'Multi-step AI workflows'
}];

// Derive a generated app's folder name from its output path.
var appIdFromPath = p => (p || '').replace(/[\\/]+$/, '').split(/[\\/]/).pop();

// ─── Top-level App ───────────────────────────────────────────────────
function App() {
  var [manifest, setManifest] = useState(initialManifest);
  var [stepIdx, setStepIdx] = useState(0);
  var [catalog, setCatalog] = useState({
    kpis: null,
    audiences: null,
    dataSources: null
  });
  var [savedManifestId, setSavedManifestId] = useState(null);
  var [build, setBuild] = useState({
    id: null,
    events: [],
    status: 'idle',
    outputPath: null,
    progress: 0
  });
  var [run, setRun] = useState({
    status: 'idle',
    urls: null,
    error: null
  }); // idle|launching|running|error

  // Load catalogs once
  useEffect(() => {
    _asyncToGenerator(function* () {
      try {
        var [k, a, d] = yield Promise.all([apiGet('/api/catalog/kpis'), apiGet('/api/catalog/audiences'), apiGet('/api/catalog/data_source_kinds')]);
        setCatalog({
          kpis: k,
          audiences: a,
          dataSources: d
        });
      } catch (e) {
        console.error('Catalog load failed', e);
      }
    })();
  }, []);

  // Updater shortcut
  var update = useCallback(patch => {
    setManifest(m => typeof patch === 'function' ? patch(m) : _objectSpread(_objectSpread({}, m), patch));
  }, []);
  var step = STEPS[stepIdx];
  var goNext = () => setStepIdx(i => Math.min(i + 1, STEPS.length - 1));
  var goPrev = () => setStepIdx(i => Math.max(i - 1, 0));
  var saveManifest = /*#__PURE__*/function () {
    var _ref2 = _asyncToGenerator(function* () {
      var payload = _objectSpread({}, manifest);
      if (!payload.branding.app_name && payload.customer.company_name) {
        payload.branding = _objectSpread(_objectSpread({}, payload.branding), {}, {
          app_name: "".concat(payload.customer.company_name, " Insights")
        });
      }
      var res = yield apiPost('/api/manifests', {
        manifest: payload
      });
      setSavedManifestId(res.manifest_id);
      setManifest(m => _objectSpread(_objectSpread({}, m), {}, {
        manifest_id: res.manifest_id
      }));
      return res.manifest_id;
    });
    return function saveManifest() {
      return _ref2.apply(this, arguments);
    };
  }();
  var startBuild = /*#__PURE__*/function () {
    var _ref3 = _asyncToGenerator(function* () {
      var mid = savedManifestId;
      if (!mid) mid = yield saveManifest();
      setBuild({
        id: null,
        events: [],
        status: 'starting',
        outputPath: null,
        progress: 0
      });
      var res = yield apiPost('/api/builds', {
        manifest_id: mid
      });
      setBuild(b => _objectSpread(_objectSpread({}, b), {}, {
        id: res.build_id,
        status: 'running'
      }));
    });
    return function startBuild() {
      return _ref3.apply(this, arguments);
    };
  }();

  // Launch the generated app natively (no Docker) and collect its URLs.
  var runApp = /*#__PURE__*/function () {
    var _ref4 = _asyncToGenerator(function* () {
      var appId = appIdFromPath(build.outputPath);
      if (!appId) return;
      setRun({
        status: 'launching',
        urls: null,
        error: null
      });
      try {
        var res = yield apiPost("/api/apps/".concat(appId, "/run"), {});
        setRun({
          status: 'running',
          urls: res,
          error: null
        });
      } catch (e) {
        setRun({
          status: 'error',
          urls: null,
          error: String(e.message || e)
        });
      }
    });
    return function runApp() {
      return _ref4.apply(this, arguments);
    };
  }();
  var stopApp = /*#__PURE__*/function () {
    var _ref5 = _asyncToGenerator(function* () {
      var appId = appIdFromPath(build.outputPath);
      if (!appId) return;
      try {
        yield apiPost("/api/apps/".concat(appId, "/stop"), {});
      } catch (_unused) {}
      setRun({
        status: 'idle',
        urls: null,
        error: null
      });
    });
    return function stopApp() {
      return _ref5.apply(this, arguments);
    };
  }();

  // WebSocket subscription for live build progress
  useEffect(() => {
    if (!build.id) return;
    var proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    var url = "".concat(proto, "//").concat(window.location.host, "/ws/builds/").concat(build.id);
    var ws = new WebSocket(url);
    ws.onmessage = evt => {
      var data = JSON.parse(evt.data);
      if (data.final) {
        setBuild(b => _objectSpread(_objectSpread({}, b), {}, {
          status: data.status,
          outputPath: data.output_path
        }));
        return;
      }
      setBuild(b => _objectSpread(_objectSpread({}, b), {}, {
        events: [...b.events, data],
        progress: typeof data.progress_pct === 'number' ? data.progress_pct : b.progress
      }));
    };
    ws.onerror = () => setBuild(b => _objectSpread(_objectSpread({}, b), {}, {
      status: 'error'
    }));
    return () => {
      try {
        ws.close();
      } catch (_unused2) {}
    };
  }, [build.id]);

  // Validation per step (drives the Next button)
  var stepValid = useMemo(() => {
    switch (step.id) {
      case 'customer':
        return manifest.customer.company_name.trim().length > 0 && manifest.capabilities.length > 0;
      case 'deployment':
        return !!manifest.deployment;
      case 'datasources':
        return manifest.data_sources.length > 0;
      case 'audience':
        return manifest.audiences.length > 0 && manifest.kpis.length > 0;
      case 'observability':
        return !!manifest.observability.tier;
      case 'rbac':
        return manifest.rbac.roles.length >= 1;
      case 'custom':
        return true;
      case 'review':
        return true;
      case 'build':
        return true;
      default:
        return true;
    }
  }, [step, manifest]);

  // Render
  return /*#__PURE__*/React.createElement("div", {
    className: "app"
  }, /*#__PURE__*/React.createElement("div", {
    className: "top"
  }, /*#__PURE__*/React.createElement("div", {
    className: "brand"
  }, /*#__PURE__*/React.createElement("div", {
    className: "brand-mark"
  }, "F"), /*#__PURE__*/React.createElement("span", null, "Forge"), /*#__PURE__*/React.createElement("span", {
    className: "brand-tag"
  }, "\u2014 generate analytics applications")), /*#__PURE__*/React.createElement("div", {
    className: "top-actions"
  }, savedManifestId && /*#__PURE__*/React.createElement("span", {
    className: "mono",
    style: {
      fontSize: 11
    }
  }, savedManifestId))), /*#__PURE__*/React.createElement("div", {
    className: "shell"
  }, /*#__PURE__*/React.createElement("aside", {
    className: "sidebar"
  }, /*#__PURE__*/React.createElement("h3", null, "Steps"), /*#__PURE__*/React.createElement("div", {
    className: "steplist"
  }, STEPS.map((s, i) => /*#__PURE__*/React.createElement("div", {
    key: s.id,
    className: "step ".concat(i === stepIdx ? 'active' : '', " ").concat(i < stepIdx ? 'done' : ''),
    onClick: () => i < stepIdx && setStepIdx(i)
  }, /*#__PURE__*/React.createElement("div", {
    className: "num"
  }, i + 1), /*#__PURE__*/React.createElement("div", null, s.label))))), /*#__PURE__*/React.createElement("main", {
    className: "main"
  }, step.id === 'customer' && /*#__PURE__*/React.createElement(StepCustomer, {
    manifest: manifest,
    update: update
  }), step.id === 'deployment' && /*#__PURE__*/React.createElement(StepDeployment, {
    manifest: manifest,
    update: update
  }), step.id === 'datasources' && /*#__PURE__*/React.createElement(StepDataSources, {
    manifest: manifest,
    update: update,
    catalog: catalog.dataSources,
    saveManifest: saveManifest,
    savedManifestId: savedManifestId
  }), step.id === 'audience' && /*#__PURE__*/React.createElement(StepAudience, {
    manifest: manifest,
    update: update,
    kpiCatalog: catalog.kpis,
    audienceCatalog: catalog.audiences
  }), step.id === 'observability' && /*#__PURE__*/React.createElement(StepObservability, {
    manifest: manifest,
    update: update
  }), step.id === 'rbac' && /*#__PURE__*/React.createElement(StepRBAC, {
    manifest: manifest,
    update: update
  }), step.id === 'custom' && /*#__PURE__*/React.createElement(StepCustom, {
    manifest: manifest,
    update: update
  }), step.id === 'review' && /*#__PURE__*/React.createElement(StepReview, {
    manifest: manifest
  }), step.id === 'build' && /*#__PURE__*/React.createElement(StepBuild, {
    build: build,
    startBuild: startBuild,
    manifest: manifest,
    run: run,
    runApp: runApp,
    stopApp: stopApp
  }), /*#__PURE__*/React.createElement("div", {
    className: "actions"
  }, /*#__PURE__*/React.createElement("button", {
    className: "btn btn-secondary",
    onClick: goPrev,
    disabled: stepIdx === 0
  }, "\u2190 Back"), step.id !== 'build' && /*#__PURE__*/React.createElement("button", {
    className: "btn btn-primary",
    onClick: goNext,
    disabled: !stepValid
  }, "Next \u2192")))));
}

// ─── Step 1: Customer & capabilities ────────────────────────────────
function StepCustomer(_ref6) {
  var {
    manifest,
    update
  } = _ref6;
  var toggle = id => {
    var has = manifest.capabilities.includes(id);
    update({
      capabilities: has ? manifest.capabilities.filter(c => c !== id) : [...manifest.capabilities, id]
    });
  };
  return /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("header", {
    className: "step-header"
  }, /*#__PURE__*/React.createElement("div", {
    className: "step-eyebrow"
  }, "Step 1 of 9"), /*#__PURE__*/React.createElement("h1", {
    className: "step-title"
  }, "Tell us about the customer"), /*#__PURE__*/React.createElement("div", {
    className: "step-desc"
  }, "Who this app is for, and what they want it to do.")), /*#__PURE__*/React.createElement("div", {
    className: "card"
  }, /*#__PURE__*/React.createElement("h4", null, "Customer details"), /*#__PURE__*/React.createElement("div", {
    className: "row"
  }, /*#__PURE__*/React.createElement("div", {
    className: "field"
  }, /*#__PURE__*/React.createElement("label", null, "Company name *"), /*#__PURE__*/React.createElement("input", {
    value: manifest.customer.company_name,
    onChange: e => update({
      customer: _objectSpread(_objectSpread({}, manifest.customer), {}, {
        company_name: e.target.value
      })
    }),
    placeholder: "Acme Corp"
  })), /*#__PURE__*/React.createElement("div", {
    className: "field"
  }, /*#__PURE__*/React.createElement("label", null, "Industry"), /*#__PURE__*/React.createElement("input", {
    value: manifest.customer.industry,
    onChange: e => update({
      customer: _objectSpread(_objectSpread({}, manifest.customer), {}, {
        industry: e.target.value
      })
    }),
    placeholder: "retail, finance, healthcare\u2026"
  }))), /*#__PURE__*/React.createElement("div", {
    className: "row"
  }, /*#__PURE__*/React.createElement("div", {
    className: "field"
  }, /*#__PURE__*/React.createElement("label", null, "Contact email"), /*#__PURE__*/React.createElement("input", {
    type: "email",
    value: manifest.customer.contact_email,
    onChange: e => update({
      customer: _objectSpread(_objectSpread({}, manifest.customer), {}, {
        contact_email: e.target.value
      })
    }),
    placeholder: "cto@acme.com"
  })), /*#__PURE__*/React.createElement("div", {
    className: "field"
  }, /*#__PURE__*/React.createElement("label", null, "Primary use case"), /*#__PURE__*/React.createElement("input", {
    value: manifest.customer.primary_use_case,
    onChange: e => update({
      customer: _objectSpread(_objectSpread({}, manifest.customer), {}, {
        primary_use_case: e.target.value
      })
    }),
    placeholder: "forecasting & anomaly alerts"
  })))), /*#__PURE__*/React.createElement("div", {
    className: "card"
  }, /*#__PURE__*/React.createElement("h4", null, "Capabilities to enable"), /*#__PURE__*/React.createElement("div", {
    className: "help"
  }, "Each capability ships as a self-contained module. Pick the ones the customer needs \u2014 you can always add more later."), /*#__PURE__*/React.createElement("div", {
    className: "chip-grid",
    style: {
      marginTop: 14
    }
  }, CAPABILITIES.map(c => {
    var on = manifest.capabilities.includes(c.id);
    return /*#__PURE__*/React.createElement("div", {
      key: c.id,
      className: "chip ".concat(on ? 'on' : ''),
      onClick: () => toggle(c.id)
    }, /*#__PURE__*/React.createElement("div", {
      className: "chip-title"
    }, /*#__PURE__*/React.createElement("span", {
      className: "check"
    }, on ? '✓' : ''), c.label), /*#__PURE__*/React.createElement("div", {
      className: "chip-desc"
    }, c.desc));
  }))));
}

// ─── Step 2: Deployment ─────────────────────────────────────────────
function StepDeployment(_ref7) {
  var {
    manifest,
    update
  } = _ref7;
  var targets = [{
    id: 'localhost',
    label: 'Localhost (demo)',
    desc: 'Run on a single machine via docker-compose'
  }, {
    id: 'cloud_aws',
    label: 'AWS',
    desc: 'EKS + RDS + S3 — Terraform skeleton generated'
  }, {
    id: 'cloud_azure',
    label: 'Azure',
    desc: 'AKS + Postgres Flexible — Terraform skeleton'
  }, {
    id: 'cloud_gcp',
    label: 'Google Cloud',
    desc: 'GKE + Cloud SQL — Terraform skeleton'
  }, {
    id: 'on_prem',
    label: 'On-premise',
    desc: 'Customer-managed Kubernetes cluster'
  }, {
    id: 'hybrid',
    label: 'Hybrid',
    desc: 'Mixed cloud + on-prem'
  }];
  var owners = [{
    id: 'self_managed',
    label: 'Self-managed',
    desc: 'Customer runs and operates'
  }, {
    id: 'fully_managed',
    label: 'Fully managed',
    desc: 'We run and operate as SaaS'
  }, {
    id: 'co_managed',
    label: 'Co-managed',
    desc: 'Shared operational responsibility'
  }];
  return /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("header", {
    className: "step-header"
  }, /*#__PURE__*/React.createElement("div", {
    className: "step-eyebrow"
  }, "Step 2 of 9"), /*#__PURE__*/React.createElement("h1", {
    className: "step-title"
  }, "Where will it run?"), /*#__PURE__*/React.createElement("div", {
    className: "step-desc"
  }, "Choose deployment target and operational model. The generator emits the matching IaC skeleton.")), /*#__PURE__*/React.createElement("div", {
    className: "card"
  }, /*#__PURE__*/React.createElement("h4", null, "Deployment target"), /*#__PURE__*/React.createElement("div", {
    className: "chip-grid",
    style: {
      marginTop: 14
    }
  }, targets.map(t => /*#__PURE__*/React.createElement("div", {
    key: t.id,
    className: "chip ".concat(manifest.deployment === t.id ? 'on' : ''),
    onClick: () => update({
      deployment: t.id
    })
  }, /*#__PURE__*/React.createElement("div", {
    className: "chip-title"
  }, /*#__PURE__*/React.createElement("span", {
    className: "check"
  }, manifest.deployment === t.id ? '✓' : ''), t.label), /*#__PURE__*/React.createElement("div", {
    className: "chip-desc"
  }, t.desc))))), /*#__PURE__*/React.createElement("div", {
    className: "card"
  }, /*#__PURE__*/React.createElement("h4", null, "Operational model"), /*#__PURE__*/React.createElement("div", {
    className: "chip-grid",
    style: {
      marginTop: 14
    }
  }, owners.map(t => /*#__PURE__*/React.createElement("div", {
    key: t.id,
    className: "chip ".concat(manifest.infra_ownership === t.id ? 'on' : ''),
    onClick: () => update({
      infra_ownership: t.id
    })
  }, /*#__PURE__*/React.createElement("div", {
    className: "chip-title"
  }, /*#__PURE__*/React.createElement("span", {
    className: "check"
  }, manifest.infra_ownership === t.id ? '✓' : ''), t.label), /*#__PURE__*/React.createElement("div", {
    className: "chip-desc"
  }, t.desc))))), manifest.deployment.startsWith('cloud') && /*#__PURE__*/React.createElement("div", {
    className: "card"
  }, /*#__PURE__*/React.createElement("h4", null, "Region"), /*#__PURE__*/React.createElement("div", {
    className: "field"
  }, /*#__PURE__*/React.createElement("input", {
    value: manifest.cloud_region,
    onChange: e => update({
      cloud_region: e.target.value
    }),
    placeholder: "us-east-1"
  }), /*#__PURE__*/React.createElement("div", {
    className: "help"
  }, "e.g. us-east-1, eu-west-1, ap-south-1"))));
}

// ─── Step 3: Data sources ───────────────────────────────────────────
function StepDataSources(_ref8) {
  var {
    manifest,
    update,
    catalog,
    saveManifest,
    savedManifestId
  } = _ref8;
  var [pickerOpen, setPickerOpen] = useState(false);
  var [secretModal, setSecretModal] = useState(null); // { dsId, name, description }

  var addSource = kind => {
    var _ds$auth;
    var id = "ds_".concat(Math.random().toString(36).substring(2, 10));
    var ds = catalog === null || catalog === void 0 ? void 0 : catalog.find(c => c.kind === kind);
    var newDs = {
      id,
      name: "".concat(kind, "_source"),
      kind,
      auth_method: (ds === null || ds === void 0 || (_ds$auth = ds.auth) === null || _ds$auth === void 0 ? void 0 : _ds$auth[0]) || 'password',
      connection_template: '',
      secret_ref: '',
      schema_hint: null,
      refresh_schedule: '0 */6 * * *',
      description: ''
    };
    update({
      data_sources: [...manifest.data_sources, newDs]
    });
    setPickerOpen(false);
  };
  var removeSource = id => update({
    data_sources: manifest.data_sources.filter(d => d.id !== id)
  });
  var updateSource = (id, patch) => update({
    data_sources: manifest.data_sources.map(d => d.id === id ? _objectSpread(_objectSpread({}, d), patch) : d)
  });
  var openSecretFor = /*#__PURE__*/function () {
    var _ref9 = _asyncToGenerator(function* (ds) {
      if (!savedManifestId) yield saveManifest();
      setSecretModal({
        dsId: ds.id,
        name: '',
        value: '',
        description: ''
      });
    });
    return function openSecretFor(_x3) {
      return _ref9.apply(this, arguments);
    };
  }();
  var submitSecret = /*#__PURE__*/function () {
    var _ref10 = _asyncToGenerator(function* () {
      var mid = savedManifestId || (yield saveManifest());
      var sm = secretModal;
      var res = yield apiPost("/api/manifests/".concat(mid, "/secrets"), {
        name: sm.name || "".concat(sm.dsId, "_secret"),
        value: sm.value,
        description: sm.description
      });
      updateSource(sm.dsId, {
        secret_ref: res.secret_ref
      });
      setSecretModal(null);
    });
    return function submitSecret() {
      return _ref10.apply(this, arguments);
    };
  }();
  return /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("header", {
    className: "step-header"
  }, /*#__PURE__*/React.createElement("div", {
    className: "step-eyebrow"
  }, "Step 3 of 9"), /*#__PURE__*/React.createElement("h1", {
    className: "step-title"
  }, "Connect data sources"), /*#__PURE__*/React.createElement("div", {
    className: "step-desc"
  }, "Pick the systems the app should pull data from. Secrets are stored encrypted on the platform \u2014 never in the manifest.")), /*#__PURE__*/React.createElement("div", {
    className: "banner banner-info"
  }, /*#__PURE__*/React.createElement("strong", null, "How secrets work:"), " when you fill in a password or API key, the platform encrypts it with Fernet and replaces it in the manifest with a ", /*#__PURE__*/React.createElement("code", null, "secret_ref"), ". The generated app reads via that ref. The raw value never appears in logs, configs, or the manifest file."), !pickerOpen && /*#__PURE__*/React.createElement("div", {
    style: {
      marginBottom: 14
    }
  }, /*#__PURE__*/React.createElement("button", {
    className: "btn-add",
    onClick: () => setPickerOpen(true)
  }, "+ Add data source")), pickerOpen && /*#__PURE__*/React.createElement("div", {
    className: "card"
  }, /*#__PURE__*/React.createElement("h4", null, "Pick a source type"), /*#__PURE__*/React.createElement("div", {
    className: "ds-grid"
  }, (catalog || []).map(c => /*#__PURE__*/React.createElement("div", {
    key: c.kind,
    className: "ds-tile",
    onClick: () => addSource(c.kind)
  }, /*#__PURE__*/React.createElement("div", {
    className: "ds-tile-name"
  }, c.label), /*#__PURE__*/React.createElement("div", {
    className: "ds-tile-auth"
  }, c.auth.join(' · '))))), /*#__PURE__*/React.createElement("div", {
    style: {
      marginTop: 14
    }
  }, /*#__PURE__*/React.createElement("button", {
    className: "btn-link",
    onClick: () => setPickerOpen(false)
  }, "Cancel"))), manifest.data_sources.map(ds => {
    var cat = catalog === null || catalog === void 0 ? void 0 : catalog.find(c => c.kind === ds.kind);
    return /*#__PURE__*/React.createElement("div", {
      key: ds.id,
      className: "ds-config"
    }, /*#__PURE__*/React.createElement("div", {
      className: "ds-config-head"
    }, /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("span", {
      className: "name"
    }, (cat === null || cat === void 0 ? void 0 : cat.label) || ds.kind), /*#__PURE__*/React.createElement("span", {
      style: {
        color: 'var(--text-muted)',
        fontSize: 11,
        marginLeft: 8
      },
      className: "mono"
    }, ds.id)), /*#__PURE__*/React.createElement("button", {
      className: "btn-x",
      onClick: () => removeSource(ds.id)
    }, "\xD7")), /*#__PURE__*/React.createElement("div", {
      className: "row"
    }, /*#__PURE__*/React.createElement("div", {
      className: "field"
    }, /*#__PURE__*/React.createElement("label", null, "Display name"), /*#__PURE__*/React.createElement("input", {
      value: ds.name,
      onChange: e => updateSource(ds.id, {
        name: e.target.value
      })
    })), /*#__PURE__*/React.createElement("div", {
      className: "field"
    }, /*#__PURE__*/React.createElement("label", null, "Auth method"), /*#__PURE__*/React.createElement("select", {
      value: ds.auth_method,
      onChange: e => updateSource(ds.id, {
        auth_method: e.target.value
      })
    }, ((cat === null || cat === void 0 ? void 0 : cat.auth) || ['password']).map(a => /*#__PURE__*/React.createElement("option", {
      key: a,
      value: a
    }, a))))), /*#__PURE__*/React.createElement("div", {
      className: "field"
    }, /*#__PURE__*/React.createElement("label", null, "Connection template (use placeholders, NEVER literal secrets)"), /*#__PURE__*/React.createElement("input", {
      value: ds.connection_template,
      onChange: e => updateSource(ds.id, {
        connection_template: e.target.value
      }),
      placeholder: "postgresql://user:{{PWD}}@host:5432/db"
    })), /*#__PURE__*/React.createElement("div", {
      className: "field"
    }, /*#__PURE__*/React.createElement("label", null, "Secret reference"), /*#__PURE__*/React.createElement("div", {
      style: {
        display: 'flex',
        gap: 8
      }
    }, /*#__PURE__*/React.createElement("input", {
      value: ds.secret_ref,
      readOnly: true,
      placeholder: "not set",
      style: {
        fontFamily: "'JetBrains Mono', monospace",
        fontSize: 12,
        flex: 1
      }
    }), /*#__PURE__*/React.createElement("button", {
      className: "btn btn-secondary",
      onClick: () => openSecretFor(ds)
    }, ds.secret_ref ? 'Update secret' : 'Add secret')), /*#__PURE__*/React.createElement("div", {
      className: "help"
    }, "Refs look like ", /*#__PURE__*/React.createElement("code", null, "secret://forge/<manifest>/<name>"), ". The actual value lives encrypted.")), /*#__PURE__*/React.createElement("div", {
      className: "field"
    }, /*#__PURE__*/React.createElement("label", null, "Description"), /*#__PURE__*/React.createElement("input", {
      value: ds.description,
      onChange: e => updateSource(ds.id, {
        description: e.target.value
      }),
      placeholder: "What lives in this source?"
    })));
  }), secretModal && /*#__PURE__*/React.createElement(SecretModal, {
    state: secretModal,
    setState: setSecretModal,
    onSubmit: submitSecret,
    onCancel: () => setSecretModal(null)
  }));
}
function SecretModal(_ref11) {
  var {
    state,
    setState,
    onSubmit,
    onCancel
  } = _ref11;
  return /*#__PURE__*/React.createElement("div", {
    style: {
      position: 'fixed',
      inset: 0,
      background: 'rgba(0,0,0,0.6)',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      zIndex: 100
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "card",
    style: {
      width: 'min(440px, 90vw)',
      margin: 0
    }
  }, /*#__PURE__*/React.createElement("h4", null, "Store a secret"), /*#__PURE__*/React.createElement("div", {
    className: "help"
  }, "This will be encrypted at rest. The manifest will only contain the reference."), /*#__PURE__*/React.createElement("div", {
    className: "field",
    style: {
      marginTop: 14
    }
  }, /*#__PURE__*/React.createElement("label", null, "Name"), /*#__PURE__*/React.createElement("input", {
    value: state.name,
    onChange: e => setState(_objectSpread(_objectSpread({}, state), {}, {
      name: e.target.value
    })),
    placeholder: "db_password"
  })), /*#__PURE__*/React.createElement("div", {
    className: "field"
  }, /*#__PURE__*/React.createElement("label", null, "Value"), /*#__PURE__*/React.createElement("input", {
    type: "password",
    value: state.value,
    onChange: e => setState(_objectSpread(_objectSpread({}, state), {}, {
      value: e.target.value
    })),
    placeholder: "\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u2022"
  })), /*#__PURE__*/React.createElement("div", {
    className: "field"
  }, /*#__PURE__*/React.createElement("label", null, "Description (optional)"), /*#__PURE__*/React.createElement("input", {
    value: state.description,
    onChange: e => setState(_objectSpread(_objectSpread({}, state), {}, {
      description: e.target.value
    }))
  })), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      gap: 8,
      justifyContent: 'flex-end',
      marginTop: 8
    }
  }, /*#__PURE__*/React.createElement("button", {
    className: "btn btn-secondary",
    onClick: onCancel
  }, "Cancel"), /*#__PURE__*/React.createElement("button", {
    className: "btn btn-primary",
    disabled: !state.value,
    onClick: onSubmit
  }, "Save secret"))));
}

// ─── Step 4: Audience & KPIs ────────────────────────────────────────
function StepAudience(_ref12) {
  var {
    manifest,
    update,
    kpiCatalog,
    audienceCatalog
  } = _ref12;
  var allKpis = useMemo(() => {
    if (!kpiCatalog) return [];
    var out = [];
    for (var [domainId, dom] of Object.entries(kpiCatalog.domains || {})) {
      for (var k of dom.kpis) out.push(_objectSpread(_objectSpread({}, k), {}, {
        domain: domainId,
        domain_label: dom.label,
        icon: dom.icon
      }));
    }
    return out;
  }, [kpiCatalog]);
  var toggleAudience = a => {
    var has = manifest.audiences.find(x => x.id === a.id);
    if (has) {
      update({
        audiences: manifest.audiences.filter(x => x.id !== a.id)
      });
    } else {
      // Add audience and auto-select its default KPIs
      var next = [...manifest.audiences, {
        id: a.id,
        name: a.name,
        description: a.description,
        default_kpi_ids: a.default_kpi_ids,
        suggested_questions: a.suggested_questions
      }];
      var newKpis = [...manifest.kpis];
      var _loop = function _loop(kid) {
        if (!newKpis.find(k => k.id === kid)) {
          var cat = allKpis.find(x => x.id === kid);
          if (cat) newKpis.push(toKPIDef(cat));
        }
      };
      for (var kid of a.default_kpi_ids) {
        _loop(kid);
      }
      update({
        audiences: next,
        kpis: newKpis
      });
    }
  };
  var toggleKpi = kpi => {
    var has = manifest.kpis.find(k => k.id === kpi.id);
    if (has) update({
      kpis: manifest.kpis.filter(k => k.id !== kpi.id)
    });else update({
      kpis: [...manifest.kpis, toKPIDef(kpi)]
    });
  };
  var filterText = useState('');
  var [filter, setFilter] = useState('');
  return /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("header", {
    className: "step-header"
  }, /*#__PURE__*/React.createElement("div", {
    className: "step-eyebrow"
  }, "Step 4 of 9"), /*#__PURE__*/React.createElement("h1", {
    className: "step-title"
  }, "Audience & metrics"), /*#__PURE__*/React.createElement("div", {
    className: "step-desc"
  }, "Pick personas (each unlocks a tailored dashboard) and the metrics they care about. Adding an audience auto-selects its default KPIs.")), /*#__PURE__*/React.createElement("div", {
    className: "card"
  }, /*#__PURE__*/React.createElement("h4", null, "Target audiences"), /*#__PURE__*/React.createElement("div", {
    className: "chip-grid",
    style: {
      marginTop: 14
    }
  }, ((audienceCatalog === null || audienceCatalog === void 0 ? void 0 : audienceCatalog.audiences) || []).map(a => {
    var on = manifest.audiences.find(x => x.id === a.id);
    return /*#__PURE__*/React.createElement("div", {
      key: a.id,
      className: "chip ".concat(on ? 'on' : ''),
      onClick: () => toggleAudience(a)
    }, /*#__PURE__*/React.createElement("div", {
      className: "chip-title"
    }, /*#__PURE__*/React.createElement("span", {
      className: "check"
    }, on ? '✓' : ''), a.name), /*#__PURE__*/React.createElement("div", {
      className: "chip-desc"
    }, a.description));
  }))), /*#__PURE__*/React.createElement("div", {
    className: "card"
  }, /*#__PURE__*/React.createElement("h4", null, "KPI catalog \xB7 ", manifest.kpis.length, " selected"), /*#__PURE__*/React.createElement("div", {
    className: "field",
    style: {
      marginTop: 8
    }
  }, /*#__PURE__*/React.createElement("input", {
    placeholder: "Filter KPIs (e.g. revenue, churn, latency)\u2026",
    value: filter,
    onChange: e => setFilter(e.target.value)
  })), Object.entries((kpiCatalog === null || kpiCatalog === void 0 ? void 0 : kpiCatalog.domains) || {}).map(_ref13 => {
    var [dId, dom] = _ref13;
    var visible = dom.kpis.filter(k => !filter || k.name.toLowerCase().includes(filter.toLowerCase()) || (k.description || '').toLowerCase().includes(filter.toLowerCase()));
    if (visible.length === 0) return null;
    return /*#__PURE__*/React.createElement("div", {
      key: dId,
      className: "kpi-domain"
    }, /*#__PURE__*/React.createElement("div", {
      className: "kpi-domain-label"
    }, /*#__PURE__*/React.createElement("span", null, dom.icon, " ", dom.label), /*#__PURE__*/React.createElement("span", {
      className: "count"
    }, visible.length, " metrics")), /*#__PURE__*/React.createElement("div", {
      className: "kpi-list"
    }, visible.map(k => {
      var on = !!manifest.kpis.find(x => x.id === k.id);
      return /*#__PURE__*/React.createElement("div", {
        key: k.id,
        className: "kpi-item ".concat(on ? 'on' : ''),
        onClick: () => toggleKpi(_objectSpread(_objectSpread({}, k), {}, {
          domain: dId
        }))
      }, /*#__PURE__*/React.createElement("div", {
        className: "kpi-item-name"
      }, /*#__PURE__*/React.createElement("span", null, k.name), /*#__PURE__*/React.createElement("span", {
        style: {
          color: on ? 'var(--accent)' : 'var(--text-muted)'
        }
      }, on ? '✓' : '+')), /*#__PURE__*/React.createElement("div", {
        className: "kpi-item-formula"
      }, k.formula), /*#__PURE__*/React.createElement("div", {
        className: "kpi-item-meta"
      }, /*#__PURE__*/React.createElement("span", {
        className: "kpi-tag"
      }, k.unit), /*#__PURE__*/React.createElement("span", {
        className: "kpi-tag"
      }, k.chart_type), k.higher_is_better === false && /*#__PURE__*/React.createElement("span", {
        className: "kpi-tag"
      }, "lower=better")));
    })));
  })));
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
    audiences: []
  };
}

// ─── Step 5: Observability ──────────────────────────────────────────
function StepObservability(_ref14) {
  var {
    manifest,
    update
  } = _ref14;
  var tiers = [{
    id: 'basic',
    label: 'Basic',
    desc: 'Logs only · 7-day retention'
  }, {
    id: 'standard',
    label: 'Standard',
    desc: 'Logs + metrics + traces · Prometheus + Grafana + Loki bundled'
  }, {
    id: 'advanced',
    label: 'Advanced',
    desc: 'Standard + audit log + data lineage + cost tracking'
  }, {
    id: 'regulated',
    label: 'Regulated',
    desc: 'Advanced + immutable audit + approval workflows · for SOC 2 / HIPAA'
  }];
  var obs = manifest.observability;
  var setObs = patch => update({
    observability: _objectSpread(_objectSpread({}, obs), patch)
  });
  return /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("header", {
    className: "step-header"
  }, /*#__PURE__*/React.createElement("div", {
    className: "step-eyebrow"
  }, "Step 5 of 9"), /*#__PURE__*/React.createElement("h1", {
    className: "step-title"
  }, "Observability tier"), /*#__PURE__*/React.createElement("div", {
    className: "step-desc"
  }, "More observability = more cost and more confidence. Pick what fits the customer's risk profile.")), /*#__PURE__*/React.createElement("div", {
    className: "card"
  }, /*#__PURE__*/React.createElement("h4", null, "Tier"), /*#__PURE__*/React.createElement("div", {
    className: "chip-grid",
    style: {
      marginTop: 14
    }
  }, tiers.map(t => /*#__PURE__*/React.createElement("div", {
    key: t.id,
    className: "chip ".concat(obs.tier === t.id ? 'on' : ''),
    onClick: () => setObs({
      tier: t.id
    })
  }, /*#__PURE__*/React.createElement("div", {
    className: "chip-title"
  }, /*#__PURE__*/React.createElement("span", {
    className: "check"
  }, obs.tier === t.id ? '✓' : ''), t.label), /*#__PURE__*/React.createElement("div", {
    className: "chip-desc"
  }, t.desc))))), /*#__PURE__*/React.createElement("div", {
    className: "card"
  }, /*#__PURE__*/React.createElement("h4", null, "Retention & destinations"), /*#__PURE__*/React.createElement("div", {
    className: "row"
  }, /*#__PURE__*/React.createElement("div", {
    className: "field"
  }, /*#__PURE__*/React.createElement("label", null, "Log retention (days)"), /*#__PURE__*/React.createElement("input", {
    type: "number",
    value: obs.log_retention_days,
    onChange: e => setObs({
      log_retention_days: parseInt(e.target.value) || 0
    })
  })), /*#__PURE__*/React.createElement("div", {
    className: "field"
  }, /*#__PURE__*/React.createElement("label", null, "Audit retention (days)"), /*#__PURE__*/React.createElement("input", {
    type: "number",
    value: obs.audit_retention_days,
    onChange: e => setObs({
      audit_retention_days: parseInt(e.target.value) || 0
    })
  }))), /*#__PURE__*/React.createElement("div", {
    className: "row"
  }, /*#__PURE__*/React.createElement("div", {
    className: "field"
  }, /*#__PURE__*/React.createElement("label", null, "Metrics backend"), /*#__PURE__*/React.createElement("select", {
    value: obs.metrics_backend,
    onChange: e => setObs({
      metrics_backend: e.target.value
    })
  }, /*#__PURE__*/React.createElement("option", {
    value: "prometheus"
  }, "Prometheus"), /*#__PURE__*/React.createElement("option", {
    value: "datadog"
  }, "Datadog"), /*#__PURE__*/React.createElement("option", {
    value: "cloudwatch"
  }, "CloudWatch"), /*#__PURE__*/React.createElement("option", {
    value: "azure_monitor"
  }, "Azure Monitor"))), /*#__PURE__*/React.createElement("div", {
    className: "field"
  }, /*#__PURE__*/React.createElement("label", null, "Tracing backend"), /*#__PURE__*/React.createElement("select", {
    value: obs.traces_backend,
    onChange: e => setObs({
      traces_backend: e.target.value
    })
  }, /*#__PURE__*/React.createElement("option", {
    value: "tempo"
  }, "Grafana Tempo"), /*#__PURE__*/React.createElement("option", {
    value: "jaeger"
  }, "Jaeger"), /*#__PURE__*/React.createElement("option", {
    value: "datadog"
  }, "Datadog"), /*#__PURE__*/React.createElement("option", {
    value: "x-ray"
  }, "AWS X-Ray"), /*#__PURE__*/React.createElement("option", {
    value: "none"
  }, "None")))), /*#__PURE__*/React.createElement("div", {
    className: "field"
  }, /*#__PURE__*/React.createElement("label", null, "Alert channels"), /*#__PURE__*/React.createElement("input", {
    placeholder: "slack:#data-alerts, email:ops@acme.com",
    value: (obs.alert_channels || []).join(', '),
    onChange: e => setObs({
      alert_channels: e.target.value.split(',').map(s => s.trim()).filter(Boolean)
    })
  })), /*#__PURE__*/React.createElement("div", {
    className: "field",
    style: {
      display: 'flex',
      gap: 18,
      flexWrap: 'wrap'
    }
  }, /*#__PURE__*/React.createElement(Toggle, {
    label: "Data lineage tracking",
    value: obs.enable_data_lineage,
    onChange: v => setObs({
      enable_data_lineage: v
    })
  }), /*#__PURE__*/React.createElement(Toggle, {
    label: "Query audit log",
    value: obs.enable_query_audit,
    onChange: v => setObs({
      enable_query_audit: v
    })
  }), /*#__PURE__*/React.createElement(Toggle, {
    label: "Cost tracking",
    value: obs.enable_cost_tracking,
    onChange: v => setObs({
      enable_cost_tracking: v
    })
  }))));
}
function Toggle(_ref15) {
  var {
    label,
    value,
    onChange: _onChange
  } = _ref15;
  return /*#__PURE__*/React.createElement("label", {
    style: {
      display: 'inline-flex',
      gap: 8,
      alignItems: 'center',
      cursor: 'pointer'
    }
  }, /*#__PURE__*/React.createElement("input", {
    type: "checkbox",
    checked: value,
    onChange: e => _onChange(e.target.checked)
  }), /*#__PURE__*/React.createElement("span", null, label));
}

// ─── Step 6: RBAC ───────────────────────────────────────────────────
function StepRBAC(_ref16) {
  var {
    manifest,
    update
  } = _ref16;
  var rbac = manifest.rbac;
  var setRbac = patch => update({
    rbac: _objectSpread(_objectSpread({}, rbac), patch)
  });
  var updateRole = (id, patch) => setRbac({
    roles: rbac.roles.map(r => r.id === id ? _objectSpread(_objectSpread({}, r), patch) : r)
  });
  var addRole = () => {
    var id = "role_".concat(Math.random().toString(36).substring(2, 8));
    setRbac({
      roles: [...rbac.roles, {
        id,
        name: 'New Role',
        description: '',
        column_policies: [],
        row_policies: [],
        capabilities: [],
        can_export: true,
        can_share: false,
        requires_approval_for: []
      }]
    });
  };
  var removeRole = id => setRbac({
    roles: rbac.roles.filter(r => r.id !== id)
  });
  return /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("header", {
    className: "step-header"
  }, /*#__PURE__*/React.createElement("div", {
    className: "step-eyebrow"
  }, "Step 6 of 9"), /*#__PURE__*/React.createElement("h1", {
    className: "step-title"
  }, "Access control"), /*#__PURE__*/React.createElement("div", {
    className: "step-desc"
  }, "Define roles and policies down to the row and column. Policies are enforced at query rewrite time \u2014 they cannot be bypassed by the app.")), /*#__PURE__*/React.createElement("div", {
    className: "card"
  }, /*#__PURE__*/React.createElement("h4", null, "Authentication"), /*#__PURE__*/React.createElement("div", {
    className: "row"
  }, /*#__PURE__*/React.createElement("div", {
    className: "field"
  }, /*#__PURE__*/React.createElement("label", null, "SSO provider"), /*#__PURE__*/React.createElement("select", {
    value: rbac.sso_provider,
    onChange: e => setRbac({
      sso_provider: e.target.value
    })
  }, /*#__PURE__*/React.createElement("option", {
    value: "none"
  }, "None (basic auth)"), /*#__PURE__*/React.createElement("option", {
    value: "azure_ad"
  }, "Azure AD / Entra"), /*#__PURE__*/React.createElement("option", {
    value: "okta"
  }, "Okta"), /*#__PURE__*/React.createElement("option", {
    value: "google"
  }, "Google Workspace"), /*#__PURE__*/React.createElement("option", {
    value: "saml"
  }, "SAML 2.0 (generic)"))), /*#__PURE__*/React.createElement("div", {
    className: "field",
    style: {
      display: 'flex',
      alignItems: 'center',
      paddingTop: 24
    }
  }, /*#__PURE__*/React.createElement(Toggle, {
    label: "Require MFA",
    value: rbac.mfa_required,
    onChange: v => setRbac({
      mfa_required: v
    })
  })))), /*#__PURE__*/React.createElement("div", {
    className: "card"
  }, /*#__PURE__*/React.createElement("h4", null, "Roles"), /*#__PURE__*/React.createElement("div", {
    className: "help"
  }, "Each role can have column policies (mask/redact/hash specific columns) and row policies (filter rows by user attributes)."), rbac.roles.map(role => /*#__PURE__*/React.createElement(RoleEditor, {
    key: role.id,
    role: role,
    onChange: patch => updateRole(role.id, patch),
    onRemove: () => removeRole(role.id)
  })), /*#__PURE__*/React.createElement("button", {
    className: "btn-add",
    onClick: addRole
  }, "+ Add role")));
}
function RoleEditor(_ref17) {
  var {
    role,
    onChange: _onChange2,
    onRemove
  } = _ref17;
  var addColPol = () => _onChange2({
    column_policies: [...role.column_policies, {
      column_pattern: '',
      action: 'mask',
      mask_pattern: '***'
    }]
  });
  var updColPol = (i, patch) => _onChange2({
    column_policies: role.column_policies.map((p, j) => j === i ? _objectSpread(_objectSpread({}, p), patch) : p)
  });
  var rmColPol = i => _onChange2({
    column_policies: role.column_policies.filter((_, j) => j !== i)
  });
  var addRowPol = () => _onChange2({
    row_policies: [...role.row_policies, {
      table_pattern: '*',
      where_expression: ''
    }]
  });
  var updRowPol = (i, patch) => _onChange2({
    row_policies: role.row_policies.map((p, j) => j === i ? _objectSpread(_objectSpread({}, p), patch) : p)
  });
  var rmRowPol = i => _onChange2({
    row_policies: role.row_policies.filter((_, j) => j !== i)
  });
  return /*#__PURE__*/React.createElement("div", {
    className: "role-card"
  }, /*#__PURE__*/React.createElement("div", {
    className: "role-head"
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      gap: 8,
      alignItems: 'center'
    }
  }, /*#__PURE__*/React.createElement("input", {
    value: role.name,
    onChange: e => _onChange2({
      name: e.target.value
    }),
    style: {
      fontWeight: 600,
      padding: '6px 10px',
      minWidth: 180
    }
  }), /*#__PURE__*/React.createElement("span", {
    className: "mono",
    style: {
      color: 'var(--text-muted)',
      fontSize: 11
    }
  }, role.id)), /*#__PURE__*/React.createElement("button", {
    className: "btn-x",
    onClick: onRemove
  }, "\xD7")), /*#__PURE__*/React.createElement("div", {
    className: "field"
  }, /*#__PURE__*/React.createElement("label", null, "Description"), /*#__PURE__*/React.createElement("input", {
    value: role.description,
    onChange: e => _onChange2({
      description: e.target.value
    })
  })), /*#__PURE__*/React.createElement("div", {
    className: "field"
  }, /*#__PURE__*/React.createElement("label", null, "Column policies"), role.column_policies.map((pol, i) => /*#__PURE__*/React.createElement("div", {
    key: i,
    className: "policy-row"
  }, /*#__PURE__*/React.createElement("input", {
    placeholder: "column_pattern (e.g. *.salary)",
    value: pol.column_pattern,
    onChange: e => updColPol(i, {
      column_pattern: e.target.value
    })
  }), /*#__PURE__*/React.createElement("select", {
    value: pol.action,
    onChange: e => updColPol(i, {
      action: e.target.value
    })
  }, /*#__PURE__*/React.createElement("option", {
    value: "allow"
  }, "allow"), /*#__PURE__*/React.createElement("option", {
    value: "deny"
  }, "deny"), /*#__PURE__*/React.createElement("option", {
    value: "mask"
  }, "mask"), /*#__PURE__*/React.createElement("option", {
    value: "hash"
  }, "hash"), /*#__PURE__*/React.createElement("option", {
    value: "redact"
  }, "redact")), /*#__PURE__*/React.createElement("input", {
    placeholder: "mask pattern (if mask)",
    value: pol.mask_pattern || '',
    onChange: e => updColPol(i, {
      mask_pattern: e.target.value
    })
  }), /*#__PURE__*/React.createElement("button", {
    className: "btn-x",
    onClick: () => rmColPol(i)
  }, "\xD7"))), /*#__PURE__*/React.createElement("button", {
    className: "btn-link",
    onClick: addColPol
  }, "+ Column policy")), /*#__PURE__*/React.createElement("div", {
    className: "field"
  }, /*#__PURE__*/React.createElement("label", null, "Row policies"), role.row_policies.map((pol, i) => /*#__PURE__*/React.createElement("div", {
    key: i,
    className: "policy-row",
    style: {
      gridTemplateColumns: '1fr 2fr auto auto'
    }
  }, /*#__PURE__*/React.createElement("input", {
    placeholder: "table_pattern",
    value: pol.table_pattern,
    onChange: e => updRowPol(i, {
      table_pattern: e.target.value
    })
  }), /*#__PURE__*/React.createElement("input", {
    placeholder: "WHERE clause (use ${user.attribute})",
    value: pol.where_expression,
    onChange: e => updRowPol(i, {
      where_expression: e.target.value
    })
  }), /*#__PURE__*/React.createElement("span", null), /*#__PURE__*/React.createElement("button", {
    className: "btn-x",
    onClick: () => rmRowPol(i)
  }, "\xD7"))), /*#__PURE__*/React.createElement("button", {
    className: "btn-link",
    onClick: addRowPol
  }, "+ Row policy")), /*#__PURE__*/React.createElement("div", {
    className: "field",
    style: {
      display: 'flex',
      gap: 18,
      flexWrap: 'wrap'
    }
  }, /*#__PURE__*/React.createElement(Toggle, {
    label: "Can export",
    value: role.can_export,
    onChange: v => _onChange2({
      can_export: v
    })
  }), /*#__PURE__*/React.createElement(Toggle, {
    label: "Can share",
    value: role.can_share,
    onChange: v => _onChange2({
      can_share: v
    })
  })));
}

// ─── Step 7: Custom requests ────────────────────────────────────────
function StepCustom(_ref18) {
  var {
    manifest,
    update
  } = _ref18;
  var add = () => update({
    custom_requests: [...manifest.custom_requests, {
      title: '',
      description: '',
      priority: 'nice_to_have'
    }]
  });
  var upd = (i, patch) => update({
    custom_requests: manifest.custom_requests.map((c, j) => j === i ? _objectSpread(_objectSpread({}, c), patch) : c)
  });
  var rm = i => update({
    custom_requests: manifest.custom_requests.filter((_, j) => j !== i)
  });
  return /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("header", {
    className: "step-header"
  }, /*#__PURE__*/React.createElement("div", {
    className: "step-eyebrow"
  }, "Step 7 of 9"), /*#__PURE__*/React.createElement("h1", {
    className: "step-title"
  }, "Custom requests"), /*#__PURE__*/React.createElement("div", {
    className: "step-desc"
  }, "Anything that didn't fit the templates. These get captured as feature-flag stubs in the generated app, with TODOs in the README.")), /*#__PURE__*/React.createElement("div", {
    className: "card"
  }, manifest.custom_requests.map((req, i) => /*#__PURE__*/React.createElement("div", {
    key: i,
    className: "ds-config"
  }, /*#__PURE__*/React.createElement("div", {
    className: "ds-config-head"
  }, /*#__PURE__*/React.createElement("span", {
    className: "name"
  }, "Request #", i + 1), /*#__PURE__*/React.createElement("button", {
    className: "btn-x",
    onClick: () => rm(i)
  }, "\xD7")), /*#__PURE__*/React.createElement("div", {
    className: "row"
  }, /*#__PURE__*/React.createElement("div", {
    className: "field"
  }, /*#__PURE__*/React.createElement("label", null, "Title"), /*#__PURE__*/React.createElement("input", {
    value: req.title,
    onChange: e => upd(i, {
      title: e.target.value
    })
  })), /*#__PURE__*/React.createElement("div", {
    className: "field"
  }, /*#__PURE__*/React.createElement("label", null, "Priority"), /*#__PURE__*/React.createElement("select", {
    value: req.priority,
    onChange: e => upd(i, {
      priority: e.target.value
    })
  }, /*#__PURE__*/React.createElement("option", {
    value: "must_have"
  }, "Must have"), /*#__PURE__*/React.createElement("option", {
    value: "nice_to_have"
  }, "Nice to have"), /*#__PURE__*/React.createElement("option", {
    value: "future"
  }, "Future")))), /*#__PURE__*/React.createElement("div", {
    className: "field"
  }, /*#__PURE__*/React.createElement("label", null, "Description"), /*#__PURE__*/React.createElement("textarea", {
    value: req.description,
    onChange: e => upd(i, {
      description: e.target.value
    })
  })))), /*#__PURE__*/React.createElement("button", {
    className: "btn-add",
    onClick: add
  }, "+ Add request")));
}

// ─── Step 8: Review ─────────────────────────────────────────────────
function StepReview(_ref19) {
  var {
    manifest
  } = _ref19;
  return /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("header", {
    className: "step-header"
  }, /*#__PURE__*/React.createElement("div", {
    className: "step-eyebrow"
  }, "Step 8 of 9"), /*#__PURE__*/React.createElement("h1", {
    className: "step-title"
  }, "Review"), /*#__PURE__*/React.createElement("div", {
    className: "step-desc"
  }, "Quick summary before we generate. You can still go back and tweak anything.")), /*#__PURE__*/React.createElement("div", {
    className: "review-grid"
  }, /*#__PURE__*/React.createElement(Tile, {
    label: "Customer",
    value: manifest.customer.company_name || '—'
  }), /*#__PURE__*/React.createElement(Tile, {
    label: "Industry",
    value: manifest.customer.industry || '—'
  }), /*#__PURE__*/React.createElement(Tile, {
    label: "Capabilities",
    value: "".concat(manifest.capabilities.length, " enabled")
  }), /*#__PURE__*/React.createElement(Tile, {
    label: "Deployment",
    value: manifest.deployment
  }), /*#__PURE__*/React.createElement(Tile, {
    label: "Operational model",
    value: manifest.infra_ownership.replace(/_/g, ' ')
  }), /*#__PURE__*/React.createElement(Tile, {
    label: "Data sources",
    value: "".concat(manifest.data_sources.length, " configured")
  }), /*#__PURE__*/React.createElement(Tile, {
    label: "Audiences",
    value: "".concat(manifest.audiences.length, " personas")
  }), /*#__PURE__*/React.createElement(Tile, {
    label: "KPIs",
    value: "".concat(manifest.kpis.length, " metrics")
  }), /*#__PURE__*/React.createElement(Tile, {
    label: "Observability tier",
    value: manifest.observability.tier
  }), /*#__PURE__*/React.createElement(Tile, {
    label: "Roles",
    value: "".concat(manifest.rbac.roles.length, " roles")
  }), /*#__PURE__*/React.createElement(Tile, {
    label: "SSO",
    value: manifest.rbac.sso_provider
  }), /*#__PURE__*/React.createElement(Tile, {
    label: "Custom requests",
    value: "".concat(manifest.custom_requests.length, " items")
  })), /*#__PURE__*/React.createElement("div", {
    className: "divider"
  }), /*#__PURE__*/React.createElement("details", null, /*#__PURE__*/React.createElement("summary", {
    style: {
      cursor: 'pointer',
      color: 'var(--text-dim)'
    }
  }, "Show full manifest JSON"), /*#__PURE__*/React.createElement("pre", {
    style: {
      marginTop: 14,
      padding: 14,
      background: 'var(--panel-2)',
      borderRadius: 8,
      overflow: 'auto',
      fontSize: 11,
      maxHeight: 360
    }
  }, JSON.stringify(manifest, null, 2))));
}
function Tile(_ref20) {
  var {
    label,
    value
  } = _ref20;
  return /*#__PURE__*/React.createElement("div", {
    className: "review-tile"
  }, /*#__PURE__*/React.createElement("div", {
    className: "review-label"
  }, label), /*#__PURE__*/React.createElement("div", {
    className: "review-value"
  }, value));
}

// ─── Step 9: Build ──────────────────────────────────────────────────
function StepBuild(_ref21) {
  var {
    build,
    startBuild,
    manifest,
    run,
    runApp,
    stopApp
  } = _ref21;
  var consoleRef = useRef(null);
  var [allLive, setAllLive] = useState(false);
  useEffect(() => {
    if (consoleRef.current) consoleRef.current.scrollTop = consoleRef.current.scrollHeight;
  }, [build.events.length]);
  // Reset the "all live" gate whenever a run stops/restarts.
  useEffect(() => {
    if (run.status !== 'running') setAllLive(false);
  }, [run.status]);
  var isDone = build.status === 'done';
  var isRunning = build.status === 'running' || build.status === 'starting';
  var appId = appIdFromPath(build.outputPath);
  return /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("header", {
    className: "step-header"
  }, /*#__PURE__*/React.createElement("div", {
    className: "step-eyebrow"
  }, "Step 9 of 9"), /*#__PURE__*/React.createElement("h1", {
    className: "step-title"
  }, "Generate the application"), /*#__PURE__*/React.createElement("div", {
    className: "step-desc"
  }, "The wizard will hand the manifest to the generator. You'll watch each step happen in real time.")), build.status === 'idle' && /*#__PURE__*/React.createElement("div", {
    className: "card",
    style: {
      textAlign: 'center',
      padding: 40
    }
  }, /*#__PURE__*/React.createElement("h3", {
    style: {
      marginBottom: 12
    }
  }, "Ready to forge ", manifest.customer.company_name || 'this app'), /*#__PURE__*/React.createElement("p", {
    style: {
      color: 'var(--text-dim)',
      marginBottom: 20
    }
  }, "We'll generate a self-contained package with backend, frontend, IaC, observability, RBAC, and CI/CD."), /*#__PURE__*/React.createElement("button", {
    className: "btn btn-primary",
    onClick: startBuild,
    style: {
      padding: '14px 28px',
      fontSize: 15
    }
  }, "\uD83D\uDD28 Forge it")), build.status !== 'idle' && /*#__PURE__*/React.createElement("div", {
    className: "card"
  }, /*#__PURE__*/React.createElement("div", {
    className: "build-bar"
  }, /*#__PURE__*/React.createElement("div", {
    className: "build-bar-fill",
    style: {
      width: "".concat(build.progress, "%")
    }
  })), /*#__PURE__*/React.createElement("div", {
    className: "build-console",
    ref: consoleRef
  }, build.events.length === 0 && /*#__PURE__*/React.createElement("div", {
    className: "build-line"
  }, /*#__PURE__*/React.createElement("span", {
    className: "stamp"
  }, "\xB7\xB7\xB7"), /*#__PURE__*/React.createElement("span", null, "Connecting\u2026")), build.events.map((ev, i) => {
    var t = (ev.ts || '').slice(11, 19);
    var cls = ev.status === 'ok' ? 'lvl-ok' : ev.status === 'error' ? 'lvl-error' : 'lvl-started';
    return /*#__PURE__*/React.createElement("div", {
      key: i,
      className: "build-line"
    }, /*#__PURE__*/React.createElement("span", {
      className: "stamp"
    }, "[", t, "]"), /*#__PURE__*/React.createElement("span", {
      className: cls
    }, ev.step.padEnd(15)), /*#__PURE__*/React.createElement("span", {
      style: {
        color: 'var(--text)'
      }
    }, ev.message));
  }))), isDone && /*#__PURE__*/React.createElement("div", {
    className: "card final"
  }, /*#__PURE__*/React.createElement("h2", null, "\u2705 Application generated"), run.status !== 'running' && /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("p", {
    style: {
      color: 'var(--text-dim)',
      maxWidth: 560,
      margin: '0 auto 6px'
    }
  }, "Your customer-tailored package is ready. Launch it right here \u2014 Forge will start the backend and frontend for you and hand back a live URL. No Docker required."), /*#__PURE__*/React.createElement("div", {
    style: {
      margin: '18px 0'
    }
  }, /*#__PURE__*/React.createElement("button", {
    className: "btn btn-primary",
    onClick: runApp,
    disabled: run.status === 'launching',
    style: {
      padding: '14px 28px',
      fontSize: 15
    }
  }, run.status === 'launching' ? '⏳ Starting the app…' : '▶ Build & run it')), run.status === 'error' && /*#__PURE__*/React.createElement("div", {
    className: "banner banner-warn",
    style: {
      textAlign: 'left'
    }
  }, /*#__PURE__*/React.createElement("strong", null, "Couldn't start the app."), /*#__PURE__*/React.createElement("pre", {
    style: {
      whiteSpace: 'pre-wrap',
      fontSize: 11,
      marginTop: 8
    }
  }, run.error))), run.status === 'running' && run.urls && /*#__PURE__*/React.createElement("div", {
    style: {
      textAlign: 'left'
    }
  }, /*#__PURE__*/React.createElement("p", {
    style: {
      color: 'var(--text-dim)',
      textAlign: 'center',
      margin: '0 auto 12px'
    }
  }, "Your application is coming online \u2014 watch each component boot up and start exchanging data:"), /*#__PURE__*/React.createElement(LiveTopology, {
    appId: appId,
    onAllLive: () => setAllLive(true)
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      textAlign: 'center',
      marginTop: 18
    }
  }, /*#__PURE__*/React.createElement("a", {
    className: "url-pill",
    href: run.urls.frontend_url,
    target: "_blank",
    rel: "noopener",
    style: {
      display: 'inline-block',
      textDecoration: 'none'
    }
  }, run.urls.frontend_url, " \u2197"), /*#__PURE__*/React.createElement("p", {
    style: {
      color: 'var(--text-muted)',
      fontSize: 12,
      marginTop: 12
    }
  }, "Frontend: ", /*#__PURE__*/React.createElement("a", {
    href: run.urls.frontend_url,
    target: "_blank",
    rel: "noopener"
  }, run.urls.frontend_url), '  ·  ', "API: ", /*#__PURE__*/React.createElement("a", {
    href: run.urls.health_url,
    target: "_blank",
    rel: "noopener"
  }, run.urls.backend_url), '  ·  ', /*#__PURE__*/React.createElement("a", {
    onClick: stopApp,
    style: {
      cursor: 'pointer'
    }
  }, "\u25A0 Stop"))), allLive ? /*#__PURE__*/React.createElement(VerifyPanel, {
    appId: appId
  }) : /*#__PURE__*/React.createElement("div", {
    className: "help",
    style: {
      textAlign: 'center',
      marginTop: 10
    }
  }, "Verification unlocks once every component is live\u2026")), /*#__PURE__*/React.createElement("details", {
    style: {
      marginTop: 18,
      textAlign: 'left'
    }
  }, /*#__PURE__*/React.createElement("summary", {
    style: {
      cursor: 'pointer',
      color: 'var(--text-muted)',
      fontSize: 12
    }
  }, "Prefer Docker? (needs Docker Desktop running)"), /*#__PURE__*/React.createElement("div", {
    className: "url-pill",
    style: {
      marginTop: 10
    }
  }, "cd ", build.outputPath || 'generated_apps/…', /*#__PURE__*/React.createElement("br", null), "docker-compose up --build"))), build.status === 'error' && /*#__PURE__*/React.createElement("div", {
    className: "banner banner-warn"
  }, /*#__PURE__*/React.createElement("strong", null, "Build failed."), " Check the console above. The most common cause is a missing template file \u2014 re-running usually resolves it once the platform is restarted."));
}

// ─── Live animated topology ─────────────────────────────────────────
var TOPO_ORDER = ['frontend', 'backend', 'data', 'intelligence'];
var NODE_POS = {
  frontend: {
    x: 24,
    y: 110,
    w: 152,
    h: 82
  },
  backend: {
    x: 244,
    y: 110,
    w: 152,
    h: 82
  },
  data: {
    x: 462,
    y: 26,
    w: 158,
    h: 78
  },
  intelligence: {
    x: 462,
    y: 198,
    w: 158,
    h: 78
  }
};
var DEFAULT_COMPS = [{
  id: 'frontend',
  label: 'Web UI',
  icon: '🖥️',
  status: 'starting'
}, {
  id: 'backend',
  label: 'API service',
  icon: '⚙️',
  status: 'starting'
}, {
  id: 'data',
  label: 'Data & catalogs',
  icon: '🗄️',
  status: 'starting'
}, {
  id: 'intelligence',
  label: 'Insights engine',
  icon: '✨',
  status: 'starting'
}];
var TOPO_LINKS = [{
  source: 'frontend',
  target: 'backend',
  d: 'M176,151 L244,151'
}, {
  source: 'backend',
  target: 'data',
  d: 'M396,140 L462,65'
}, {
  source: 'backend',
  target: 'intelligence',
  d: 'M396,162 L462,237'
}];
function LiveTopology(_ref22) {
  var {
    appId,
    onAllLive
  } = _ref22;
  var [topo, setTopo] = useState(null);
  var [revealed, setRevealed] = useState(0);

  // Poll the real topology probe — node/link status reflects live health checks.
  useEffect(() => {
    if (!appId) return;
    var alive = true,
      timer;
    var _poll = /*#__PURE__*/function () {
      var _ref23 = _asyncToGenerator(function* () {
        try {
          var t = yield apiGet("/api/apps/".concat(appId, "/topology"));
          if (!alive) return;
          setTopo(t);
          if (t.all_live && onAllLive) onAllLive();
        } catch (e) {/* keep trying while it boots */}
        if (alive) timer = setTimeout(_poll, 1200);
      });
      return function poll() {
        return _ref23.apply(this, arguments);
      };
    }();
    _poll();
    return () => {
      alive = false;
      clearTimeout(timer);
    };
  }, [appId]);

  // Staggered reveal so components visibly "build" one after another.
  useEffect(() => {
    var timers = TOPO_ORDER.map((_, i) => setTimeout(() => setRevealed(r => Math.max(r, i + 1)), 450 * (i + 1)));
    return () => timers.forEach(clearTimeout);
  }, []);
  var comps = (topo === null || topo === void 0 ? void 0 : topo.components) || DEFAULT_COMPS;
  var linkActive = (s, t) => !!((topo === null || topo === void 0 ? void 0 : topo.links) || []).find(l => l.source === s && l.target === t && l.active);
  return /*#__PURE__*/React.createElement("div", {
    className: "topo-wrap"
  }, /*#__PURE__*/React.createElement("div", {
    className: "topo-title"
  }, /*#__PURE__*/React.createElement("span", null, "\u26A1 Live architecture")), /*#__PURE__*/React.createElement("svg", {
    className: "topo-svg",
    viewBox: "0 0 644 300",
    preserveAspectRatio: "xMidYMid meet"
  }, TOPO_LINKS.map(l => /*#__PURE__*/React.createElement("path", {
    key: "".concat(l.source, ">").concat(l.target),
    className: "flow-line ".concat(linkActive(l.source, l.target) ? 'active' : ''),
    d: l.d
  })), TOPO_ORDER.map((id, i) => {
    if (i >= revealed) return null;
    var c = comps.find(x => x.id === id) || {};
    var p = NODE_POS[id];
    var live = c.status === 'live';
    return /*#__PURE__*/React.createElement("g", {
      key: id,
      className: "node-g node-appear"
    }, /*#__PURE__*/React.createElement("rect", {
      className: "node-box ".concat(live ? 'live' : 'starting'),
      x: p.x,
      y: p.y,
      width: p.w,
      height: p.h,
      rx: "13"
    }), /*#__PURE__*/React.createElement("text", {
      className: "node-icon",
      x: p.x + 26,
      y: p.y + p.h / 2 + 7,
      textAnchor: "middle"
    }, c.icon), /*#__PURE__*/React.createElement("text", {
      className: "node-label",
      x: p.x + 50,
      y: p.y + p.h / 2 - 4
    }, c.label), /*#__PURE__*/React.createElement("text", {
      className: "node-state ".concat(live ? 'live' : 'starting'),
      x: p.x + 50,
      y: p.y + p.h / 2 + 14
    }, live ? '● live' : '◌ starting…'));
  })), /*#__PURE__*/React.createElement("div", {
    className: "topo-legend"
  }, /*#__PURE__*/React.createElement("span", {
    className: "k"
  }, /*#__PURE__*/React.createElement("span", {
    className: "legend-swatch"
  }), " animated link = data flowing"), /*#__PURE__*/React.createElement("span", {
    className: "k"
  }, "\u25CC starting \xB7 \u25CF live")));
}

// ─── Golden-dataset verification ────────────────────────────────────
function VerifyPanel(_ref24) {
  var {
    appId
  } = _ref24;
  var [state, setState] = useState({
    status: 'idle',
    result: null,
    error: null
  });
  var runVerify = /*#__PURE__*/function () {
    var _ref25 = _asyncToGenerator(function* () {
      setState({
        status: 'running',
        result: null,
        error: null
      });
      try {
        var res = yield apiPost("/api/apps/".concat(appId, "/verify"), {});
        setState({
          status: 'done',
          result: res,
          error: null
        });
      } catch (e) {
        setState({
          status: 'error',
          result: null,
          error: String(e.message || e)
        });
      }
    });
    return function runVerify() {
      return _ref25.apply(this, arguments);
    };
  }();
  var r = state.result;
  return /*#__PURE__*/React.createElement("div", {
    className: "card",
    style: {
      marginTop: 16
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "verify-head"
  }, /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("h4", {
    style: {
      margin: 0
    }
  }, "Demo run verification"), /*#__PURE__*/React.createElement("div", {
    className: "help"
  }, "Runs a golden-dataset check against the live app to prove it behaves ", /*#__PURE__*/React.createElement("em", null, "correctly"), " \u2014 right KPIs, no secret leakage, NL query returns the expected answer \u2014 not just that it started.")), /*#__PURE__*/React.createElement("button", {
    className: "btn btn-primary",
    onClick: runVerify,
    disabled: state.status === 'running'
  }, state.status === 'running' ? /*#__PURE__*/React.createElement("span", null, /*#__PURE__*/React.createElement("span", {
    className: "spin"
  }), " Verifying\u2026") : '✓ Run demo verification')), r && /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("div", {
    className: "verify-summary ".concat(r.ok ? 'ok' : 'bad'),
    style: {
      marginTop: 14
    }
  }, r.ok ? "\u2705 Verified \u2014 all ".concat(r.total, " golden checks passed. Your application runs correctly.") : "\u26A0 ".concat(r.passed, "/").concat(r.total, " checks passed \u2014 see the failures below.")), /*#__PURE__*/React.createElement("div", {
    className: "verify-list"
  }, r.checks.map((c, i) => /*#__PURE__*/React.createElement("div", {
    key: i,
    className: "verify-row ".concat(c.passed ? 'ok' : 'bad')
  }, /*#__PURE__*/React.createElement("div", {
    className: "verify-badge ".concat(c.passed ? 'ok' : 'bad')
  }, c.passed ? '✓' : '✕'), /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
    className: "verify-name"
  }, c.name), c.detail && /*#__PURE__*/React.createElement("div", {
    className: "verify-detail"
  }, c.detail), !c.passed && /*#__PURE__*/React.createElement("div", {
    className: "verify-diff"
  }, "expected ", JSON.stringify(c.expected), " \xB7 got ", JSON.stringify(c.actual))))))), state.status === 'error' && /*#__PURE__*/React.createElement("div", {
    className: "banner banner-warn",
    style: {
      marginTop: 12
    }
  }, state.error));
}
ReactDOM.createRoot(document.getElementById('root')).render(/*#__PURE__*/React.createElement(App, null));