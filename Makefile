# Forge — top-level Makefile.
# Use this as your one-stop CLI for the whole platform.

.PHONY: help up up-light down restart logs ps test test-platform test-ml test-ml-api \
        seed-data clean nuke airflow-ui mlflow-ui forge-ui

help:           ## Show this help
	@echo ""
	@echo "Forge Platform — common commands"
	@echo "================================"
	@grep -E '^[a-zA-Z_-]+:.*?##' $(MAKEFILE_LIST) | awk -F':.*?##' '{printf "  \033[1;36m%-18s\033[0m %s\n", $$1, $$2}'
	@echo ""

# ── Bring the stack up / down ──────────────────────────────────────

up:             ## Bring up the FULL stack (postgres + mlflow + airflow + forge-api)
	docker compose -f docker/compose.yml up --build -d
	@echo ""
	@echo "✓ Stack starting. URLs:"
	@echo "  Forge wizard:  http://localhost:8800"
	@echo "  Airflow:       http://localhost:8080  (forge / forge_demo)"
	@echo "  MLflow:        http://localhost:5500"
	@echo ""
	@echo "Wait ~60s on first boot (Airflow init), then check 'make ps'"

up-light:       ## Bring up only forge-api (no Airflow / MLflow) — faster boot
	docker compose -f docker/compose.yml up --build -d postgres forge-api

dev:            ## Run the API + wizard natively (no Docker) — sets up venv on first run
	./run.sh

dev-core:       ## Native run with only core deps (no ML libraries)
	./run.sh --core

fabric-up:      ## Start the data-fabric DBs (postgres + mysql + mongo)
	docker compose -f docker/fabric/compose.yml up -d

fabric-down:    ## Stop the data-fabric DBs (preserves volumes)
	docker compose -f docker/fabric/compose.yml down

fabric-ps:      ## Show data-fabric DB status/health
	docker compose -f docker/fabric/compose.yml ps

retail-data:    ## Generate the 10M-row global retail warehouse (SQLite on G:)
	python data/generate_retail_global.py

test-retail:    ## Run the live global-retail scenario tests (10M rows)
	cd platform/backend && PYTHONPATH=. python ../../test_retail_global.py

down:           ## Stop everything (preserves volumes)
	docker compose -f docker/compose.yml down

restart:        ## Restart all services
	docker compose -f docker/compose.yml restart

logs:           ## Tail logs from all services
	docker compose -f docker/compose.yml logs -f --tail=50

logs-api:       ## Tail forge-api logs only
	docker compose -f docker/compose.yml logs -f forge-api

logs-airflow:   ## Tail airflow logs
	docker compose -f docker/compose.yml logs -f airflow-scheduler airflow-webserver

ps:             ## Show running containers + their health
	docker compose -f docker/compose.yml ps

# ── Tests ─────────────────────────────────────────────────────────

test: test-platform test-ml test-ml-api  ## Run ALL tests

test-platform:  ## Test the original platform (manifest, generator, RBAC, insights)
	cd platform/backend && PYTHONPATH=. python ../../test_e2e_inproc.py

test-ml:        ## Test the ML stack (features, anomaly, forecast, drift, trainer)
	cd platform/backend && PYTHONPATH=. python ../../test_ml.py

test-ml-api:    ## Test the ML HTTP endpoints in-process
	cd platform/backend && PYTHONPATH=. python ../../test_ml_api.py

# ── Data + setup ──────────────────────────────────────────────────

seed-data:      ## Generate synthetic demo data (revenue time series)
	python data/generate_demo_data.py

# ── UI shortcuts ──────────────────────────────────────────────────

airflow-ui:     ## Open the Airflow UI
	@command -v open >/dev/null && open http://localhost:8080 || \
	 command -v xdg-open >/dev/null && xdg-open http://localhost:8080 || \
	 echo "Open http://localhost:8080 in a browser"

mlflow-ui:      ## Open the MLflow UI
	@command -v open >/dev/null && open http://localhost:5500 || \
	 command -v xdg-open >/dev/null && xdg-open http://localhost:5500 || \
	 echo "Open http://localhost:5500 in a browser"

forge-ui:       ## Open the Forge wizard UI
	@command -v open >/dev/null && open http://localhost:8800 || \
	 command -v xdg-open >/dev/null && xdg-open http://localhost:8800 || \
	 echo "Open http://localhost:8800 in a browser"

# ── Cleanup ───────────────────────────────────────────────────────

clean:          ## Remove generated apps and intermediate data
	rm -rf generated_apps/* data/processed/* data/features/* data/models/*
	@echo "✓ Cleaned"

nuke:           ## Stop stack AND wipe volumes (postgres / mlflow / airflow data)
	docker compose -f docker/compose.yml down -v
	rm -rf .forge_secrets .forge_manifests
	rm -rf platform/backend/.forge_secrets platform/backend/.forge_manifests
	@echo "✓ Stack and all volumes destroyed."
