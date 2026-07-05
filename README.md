# Forge

> A wizard-driven platform that generates customer-tailored AI analytics applications, with a full ML stack underneath: ensemble anomaly detection, multi-model forecasting with auto-selection, drift-triggered retraining, MLflow experiment tracking, and Airflow orchestration.

You feed Forge nine answers. It hands you back a self-contained, runnable app
configured for that customer — backend, frontend, IaC, observability, RBAC,
CI/CD — plus a production-grade ML pipeline that keeps it healthy over time.

---

## Quick start

```bash
# Generate the demo dataset (730-day revenue series with an injected anomaly)
make seed-data

# Bring up the FULL stack: postgres, mlflow, airflow, forge-api
make up

# Wait ~60 seconds on first boot (Airflow init + MLflow migrations)
make ps
```

Then open in your browser:

| URL | What you see |
|---|---|
| http://localhost:8800 | **The Forge wizard** — design an app in 9 steps |
| http://localhost:8080 | **Airflow** — DAGs running on schedule (login: `forge` / `forge_demo`) |
| http://localhost:5500 | **MLflow** — every model fit, every experiment tracked |

To run **only the unit tests** (no docker required, just python):

```bash
make test          # platform + ML stack + ML API endpoints
```

### Run without Docker (just the wizard + API)

No Docker? Run the platform API and wizard natively. `run.sh` creates a
virtualenv on first launch, installs the pinned deps from `requirements.txt`,
and serves on :8800:

```bash
make dev           # or:  ./run.sh
make dev-core      # core-only — skips the heavy ML libraries
```

Then open http://localhost:8800. This path runs the wizard, generator, insights
engine and all `/api/ml/*` endpoints. Airflow (:8080) and MLflow (:5500) still
require the Docker stack (`make up`).

Verified on CPython 3.14 (Windows + Linux). The launcher forces UTF-8 IO so logs
never crash on a non-UTF-8 console.

### Configuration & security

Copy `.env.example` to `.env` to configure the platform. Safe demo defaults mean
zero config is required locally. Key switches for a locked-down deployment:

| Variable | Default | Purpose |
|---|---|---|
| `FORGE_API_KEY` | _(empty → open)_ | When set, every `/api/*` request must send `X-API-Key` or `Authorization: Bearer`. The UI shell, `/health` and websockets stay open. |
| `FORGE_ALLOWED_ORIGINS` | `*` | CORS allowlist. With `*`, credentialed CORS is force-disabled (spec-compliant). Set explicit origins in prod. |
| `FORGE_MASTER_KEY` | _(auto-generated)_ | Fernet key for the secret store. Set explicitly in prod and keep it stable. |
| `FORGE_MAX_SERIES_POINTS` | `200000` | Upper bound on time-series request bodies (DoS guard). |
| `FORGE_HEALTH_VERBOSE` | `false` | When false, `/health` omits internal absolute paths. |

User-supplied identifiers (`manifest_id`, `customer_id`, `kpi_id`, secret names)
and `artifact_dir` are validated to block path-traversal before any filesystem
access. See `platform/backend/forge/config.py`.

---

## What's in the box

### The platform (the part that generates apps)

| Piece | What it does |
|---|---|
| **9-step wizard** (`platform/frontend/`) | React SPA, live build console via WebSocket |
| **Manifest** (`platform/backend/forge/manifest.py`) | Pydantic schema, the single source of truth |
| **Generator** (`platform/backend/forge/generator.py`) | Pure function — manifest → customer package |
| **Secret manager** (`platform/backend/forge/secret_manager.py`) | Fernet-encrypted at rest, never in the manifest |
| **Catalogs** (`platform/catalogs/`) | 60+ KPIs across 7 domains, 7 audience templates |
| **RBAC engine** (`platform/backend/forge/intelligence/rbac.py`) | Row + column policies, query rewriting |
| **Insights engine** (`platform/backend/forge/intelligence/insights.py`) | Z-score + IQR anomalies, what-if, explain-this |

### The ML stack (`platform/backend/forge_ml/`)

| Module | What it does |
|---|---|
| `features/pipeline.py` | Feature engineering: lags (1/7/14/28), rolling stats (mean/std/min/max), differences, EMA, calendar (dow/dom/week/month/etc.), Fourier seasonality (weekly + yearly). 41 features by default; schema locked at fit time for serving consistency. |
| `models/anomaly/ensemble.py` | **AnomalyEnsemble**: Isolation Forest + XGBoost classifier (when labels exist) + statistical (z-score + IQR). Score fusion + voting. |
| `models/forecasting/ensemble.py` | **AutoML forecasting**: XGBoost, CatBoost, ARIMA, SARIMA, Prophet, Holt-Winters. Walk-forward backtest picks the winner per series by MAPE. |
| `drift/detector.py` | **PSI + KS + ADWIN**. Corroborated drift (both PSI and KS must agree, to avoid small-sample false positives). Returns `should_retrain` flag. |
| `registry/mlflow_registry.py` | Wraps MLflow: experiment logging, model registration, stage transitions (`Staging` → `Production`). Opt-in via `MLFLOW_TRACKING_URI`. |
| `ingestion/adapters.py` | Source/sink adapters: Postgres (with `INSERT…ON CONFLICT` upsert), Snowflake, DuckDB (default local store), CSV. |
| `orchestration/trainer.py` | The high-level entry point Airflow calls: `train_anomaly_detector()` and `train_forecaster()`. Handles features → fit → log → register. |

### The orchestration layer (`platform/airflow/dags/`)

| DAG | Schedule | What it does |
|---|---|---|
| `forge_ingestion` | hourly | Pulls each configured source into the DuckDB feature store |
| `forge_training` | daily | Trains anomaly + forecast models for every (customer, KPI) |
| `forge_drift_check` | hourly | Compares recent window vs reference; **triggers retraining when drift is major** |
| `forge_predict` | daily | Runs the production model, writes forecasts back to the feature store |

All four DAGs are config-driven — adding a new KPI to monitor or a new data
source means editing JSON in `platform/airflow/config/`, not changing code.

---

## What you'll see at the URLs

### http://localhost:8800 — Forge wizard

Walk through the 9 steps to design an analytics app. Pick capabilities (anomaly detection, forecasting, etc.), pick KPIs from the catalog, add data sources, define audiences, set up RBAC. Hit "Forge it" and watch 12 generation steps stream by. Result: a complete `generated_apps/<slug>/` directory with backend, frontend, docker-compose, IaC, the works.

### http://localhost:8080 — Airflow

You'll see four DAGs unpaused and on schedule. The first time they run:

1. **forge_ingestion** picks up `data/raw/demo_revenue.csv` and loads it into DuckDB at `data/forge.duckdb`.
2. **forge_training** runs the auto-selection: backtests all 6 forecasting models, picks the winner, logs everything to MLflow, registers the model, persists the joblib bundle.
3. **forge_drift_check** runs PSI/KS on the recent window vs the training reference. If drift is major, it triggers `forge_training` to retrain. If not, no-op.
4. **forge_predict** loads the production model, produces fresh forecasts, scores recent points for anomalies, writes results back.

### http://localhost:5500 — MLflow

Every backtest fold and every model fit shows up here. Filter by experiment to see e.g. `forge.demo.forecast` — there'll be a run per training cycle. Open a run to see:

- Metrics: `winning_mape`, `winning_rmse`, `n_train_rows`, `duration_seconds`
- Params: `winning_model`, `runner_up`, candidate models, fold settings
- Artifacts: `scoreboard.json` (per-model backtest scores), `forecast.json` (the actual predictions)

The model registry tab shows `forge_demo_revenue_forecast` and `forge_demo_revenue_anomaly` with versions in Staging.

---

## API surface

The platform exposes (FastAPI on :8800):

### Wizard / generator
- `GET  /api/catalog/kpis`, `/audiences`, `/data_source_kinds`
- `POST /api/manifests` — save a manifest
- `POST /api/manifests/{mid}/secrets` — store an encrypted secret
- `POST /api/builds` — start a generation
- `WS   /ws/builds/{bid}` — live build progress

### Insights (the original engine)
- `POST /api/insights/preview` — anomaly detection on a series
- `POST /api/insights/simulate` — what-if simulation
- `POST /api/explain` — provenance narrator

### **ML (the new stack)**
- `POST /api/ml/forecast` — one-shot autoselect-and-forecast
- `POST /api/ml/train/forecast` — train + register a forecast model
- `POST /api/ml/train/anomaly` — train + register an anomaly ensemble
- `POST /api/ml/anomaly/score` — score history with a registered model
- `POST /api/ml/drift/check` — PSI/KS-corroborated drift report

Try it:

```bash
curl -X POST http://localhost:8800/api/ml/forecast \
  -H 'Content-Type: application/json' \
  -d '{
    "history": [
      {"timestamp": "2024-01-01", "value": 100},
      {"timestamp": "2024-01-02", "value": 102}
    ],
    "horizon": 14,
    "candidate_models": ["arima", "sarima", "holt_winters", "xgboost"]
  }'
```

(Give it ≥60 points for a meaningful backtest.)

---

## Trusted OSS only

This repo uses no proprietary or vendor-locked technology. Everything is permissively licensed:

| Capability | Library | License |
|---|---|---|
| Web framework | FastAPI | MIT |
| Validation | Pydantic | MIT |
| Anomaly: tree-based | Isolation Forest (scikit-learn) | BSD-3 |
| Anomaly: supervised | XGBoost | Apache-2.0 |
| Forecasting: GBM | XGBoost, CatBoost | Apache-2.0 |
| Forecasting: classical | statsmodels (ARIMA/SARIMA/HW) | BSD-3 |
| Forecasting: holiday-aware | Prophet | MIT |
| Drift: PSI/KS | scipy + numpy | BSD-3 |
| Drift: streaming | ADWIN (in-tree reimplementation) | this repo |
| Experiment tracking | MLflow | Apache-2.0 |
| Orchestration | Apache Airflow | Apache-2.0 |
| Local feature store | DuckDB | MIT |
| Postgres driver | psycopg2 | LGPL |
| Snowflake adapter | snowflake-connector-python | Apache-2.0 |
| Encryption | cryptography (Fernet) | Apache-2.0/BSD-3 |
| HTTP client | httpx, websockets | BSD-3, BSD-3 |

---

## What's real vs. what's stubbed (honest)

### Fully implemented and tested
- The **manifest, validation, secret manager, generator, all 60 KPIs, all 7 audiences, the RBAC engine, the original insights engine** (anomaly detection / what-if / explain), the **wizard UI** with all 9 steps and live WebSocket build console.
- The **complete ML stack**: feature pipeline (41 features), anomaly ensemble (IForest + XGBoost + statistical with score fusion), forecasting auto-selection (6 models with walk-forward backtest), corroborated drift detection (PSI + KS + ADWIN), MLflow registry wrapper, ingestion adapters (Postgres/Snowflake/DuckDB/CSV), training orchestrator.
- All **4 Airflow DAGs** with task-mapped dynamic specs.
- The **full docker-compose stack** wiring postgres + mlflow + airflow + forge-api.
- **All 5 ML stack tests pass** (`make test-ml`). **All 3 ML API tests pass** (`make test-ml-api`). **All 6 platform tests pass** (`make test-platform`).

### Real but skeletal (would need iteration for production)
- **Terraform.** A real `main.tf` is generated; `terraform plan` works. We don't auto-`apply` because that requires real cloud creds.
- **CI/CD.** GitHub Actions YAML with quality gates is generated; `terraform apply` is intentionally not wired.
- **Generated NL-query engine.** Customer apps' `/api/ask` returns a structured answer with citations, but the actual SQL synthesis pipeline (the `forge.intelligence.catalog` module) is the platform's reference implementation — wiring it into generated apps is a clean hookup that's not yet automated.

### Stubbed (interfaces exist, implementations don't)
- **Voice / mobile** clients
- **Document-grounded RAG** over PDFs (capability is in the wizard catalog; pipeline isn't built)
- **Approval workflow runtime** (manifest fields exist, runtime doesn't)
- **First-party Workday / SAP / Databricks adapters** beyond the documented `SourceAdapter` interface

---

## File map

```
forge/
├── README.md                    ← you are here
├── Makefile                     ← top-level CLI: make help
├── docker/
│   ├── compose.yml              ← the full stack
│   ├── Dockerfile.api
│   ├── Dockerfile.airflow
│   ├── Dockerfile.mlflow
│   ├── postgres-init.sh
│   └── requirements-api.txt
├── platform/
│   ├── airflow/
│   │   ├── dags/                ← 4 DAGs
│   │   │   ├── forge_ingestion.py
│   │   │   ├── forge_training.py
│   │   │   ├── forge_drift_check.py
│   │   │   └── forge_predict.py
│   │   └── config/              ← edit JSON to change what's monitored
│   ├── backend/
│   │   ├── forge/               ← the platform (wizard + generator)
│   │   │   ├── manifest.py
│   │   │   ├── generator.py
│   │   │   ├── secret_manager.py
│   │   │   ├── api.py
│   │   │   └── intelligence/
│   │   └── forge_ml/            ← the ML stack
│   │       ├── features/pipeline.py
│   │       ├── models/anomaly/ensemble.py
│   │       ├── models/forecasting/ensemble.py
│   │       ├── drift/detector.py
│   │       ├── registry/mlflow_registry.py
│   │       ├── ingestion/adapters.py
│   │       └── orchestration/trainer.py
│   ├── catalogs/
│   ├── frontend/                ← wizard UI
│   └── generator/templates/     ← what gets baked into customer apps
├── data/
│   ├── generate_demo_data.py
│   ├── raw/   processed/   features/   models/
├── generated_apps/              ← generator output
├── test_e2e_inproc.py
├── test_ml.py
└── test_ml_api.py
```

---

## Common operations

```bash
# Add a new KPI to retrain each day
$EDITOR platform/airflow/config/training_specs.json

# Add a new data source to ingestion
$EDITOR platform/airflow/config/ingestion_specs.json

# Trigger a DAG manually
docker compose -f docker/compose.yml exec airflow-scheduler \
  airflow dags trigger forge_training

# Inspect the feature store
docker compose -f docker/compose.yml exec forge-api \
  python -c "import duckdb; print(duckdb.connect('/data/forge.duckdb').execute('SHOW TABLES').df())"
```
