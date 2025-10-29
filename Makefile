# Makefile - Container build / dev / test helpers for sbir-etl
#
# Usage:
#   make help
#   make docker-build
#   make docker-up-dev
#   make docker-down
#   make docker-test
#   make docker-logs SERVICE=app
#   make docker-exec SERVICE=app CMD="sh"
#
# Override defaults with environment variables, for example:
#   make docker-build IMAGE_NAME=myregistry/myimage:tag

SHELL := /bin/sh

# Configurable variables (can be overridden on the make command line)
IMAGE_NAME ?= sbir-etl:latest
DOCKER_REGISTRY ?=
DOCKER_TAG ?= latest
BUILD_CONTEXT ?= .
DOCKERFILE ?= Dockerfile

# Compose files / overlays
COMPOSE_BASE ?= docker-compose.yml
COMPOSE_DEV ?= docker/docker-compose.dev.yml
COMPOSE_TEST ?= docker/docker-compose.test.yml
COMPOSE_E2E ?= docker/docker-compose.e2e.yml
COMPOSE_CET_STAGING ?= docker-compose.cet-staging.yml

# Compose command (supports 'docker compose' or 'docker-compose' depending on environment)
DOCKER_COMPOSE ?= docker compose

# Default service to tail logs or exec into
SERVICE ?= app

# Number of seconds to wait for containers to be healthy before reporting
STARTUP_TIMEOUT ?= 120

.PHONY: help docker-build docker-buildx docker-up-dev docker-up-prod docker-down docker-rebuild docker-test docker-logs docker-exec docker-push env-check

help:
	@printf "\nMakefile targets for container workflow\n\n"
	@printf "  make docker-build      Build image locally (multi-stage Dockerfile assumed)\n"
	@printf "  make docker-buildx     Build with buildx (useful for multi-platform)\n"
	@printf "  make docker-up-dev     Start development compose stack (dev profile, bind mounts)\n"
	@printf "  make docker-up-prod    Start production-like compose stack (no bind mounts)\n"
	@printf "  make cet-staging-up    Start CET staging compose stack (staging overlay)\n"
	@printf "  make cet-staging-down  Stop CET staging stack and remove anonymous volumes\n"
	@printf "  make docker-down       Stop compose stack and remove anonymous volumes\n"
	@printf "  make docker-rebuild    Rebuild images and restart dev stack\n"
	@printf "  make docker-test       Run containerized tests via the test compose profile\n"
	@printf "  make docker-e2e        Run E2E tests in optimized environment (MacBook Air friendly)\n"
	@printf "  make docker-e2e-clean  Clean up E2E test environment and volumes\n"
	@printf "  make transition-mvp-run  Run Transition Detection MVP locally (shim, pandas)\n"
	@printf "  make transition-mvp-clean Clean Transition MVP artifacts (data/processed, reports)\n"
	@printf "  make docker-logs       Tail logs for a service (SERVICE=%s)\n" "$(SERVICE)"
	@printf "  make docker-exec       Exec into a running container (SERVICE=%s, CMD='sh')\n" "$(SERVICE)"
	@printf "  make docker-push       Tag and push image to registry (DOCKER_REGISTRY must be set)\n"
	@printf "  make env-check         Verify .env exists and warn if missing\n\n"

# ---------------------------
# Build targets
# ---------------------------

docker-build:
	@echo "Building Docker image: $(IMAGE_NAME)"
	@DOCKER_BUILDKIT=1 docker build -t $(IMAGE_NAME) -f $(DOCKERFILE) $(BUILD_CONTEXT)

docker-buildx:
	@echo "Building Docker image with buildx (multi-platform / cache optional)"
	# Example: adjust --platform and cache options as needed
	@docker buildx build --load -t $(IMAGE_NAME) -f $(DOCKERFILE) $(BUILD_CONTEXT)

# ---------------------------
# Compose / runtime targets
# ---------------------------

docker-up-dev: env-check
	@echo "Starting development compose stack (dev profile)"
	@$(DOCKER_COMPOSE) --project-directory $(CURDIR) --env-file $(CURDIR)/.env --profile dev -f $(COMPOSE_BASE) -f $(COMPOSE_DEV) up -d --build
	@echo "Waiting up to $(STARTUP_TIMEOUT)s for services to become healthy..."
	@$(DOCKER_COMPOSE) --project-directory $(CURDIR) --env-file $(CURDIR)/.env ps

# ---------------------------------------------------------------------------
# CET pipeline helper (run the full CET job on the dev stack)
# ---------------------------------------------------------------------------
# Usage:
#   make cet-pipeline-dev
# This will ensure the dev compose stack is up and then execute the CET full
# pipeline job inside the `app` service container. Adjust the app service name
# or command as needed for your local development setup.
.PHONY: cet-pipeline-dev
cet-pipeline-dev: env-check docker-up-dev
	@echo "Running CET full pipeline job on development stack (cet_full_pipeline_job)"
	@$(DOCKER_COMPOSE) --project-directory $(CURDIR) --env-file $(CURDIR)/.env -f $(COMPOSE_BASE) -f $(COMPOSE_DEV) run --rm app sh -c "poetry run dagster job execute -f src/definitions.py -j cet_full_pipeline_job"

docker-up-prod: env-check
	@echo "Starting production-like compose stack (no dev overlays)"
	@$(DOCKER_COMPOSE) --project-directory $(CURDIR) --env-file $(CURDIR)/.env -f $(COMPOSE_BASE) up -d --build
	@$(DOCKER_COMPOSE) --project-directory $(CURDIR) --env-file $(CURDIR)/.env ps

# ---------------------------
# CET staging convenience
# ---------------------------

.PHONY: cet-staging-up cet-staging-down

cet-staging-up: env-check
	@echo "Starting CET staging compose stack"
	@$(DOCKER_COMPOSE) --project-directory $(CURDIR) --env-file $(CURDIR)/.env -f $(COMPOSE_CET_STAGING) up -d --build
	@$(DOCKER_COMPOSE) --project-directory $(CURDIR) --env-file $(CURDIR)/.env -f $(COMPOSE_CET_STAGING) ps

cet-staging-down:
	@echo "Stopping CET staging compose stack"
	@$(DOCKER_COMPOSE) --env-file .env -f $(COMPOSE_CET_STAGING) down --remove-orphans

docker-down:
	@echo "Stopping compose stack and removing anonymous volumes"
	@$(DOCKER_COMPOSE) --env-file .env -f $(COMPOSE_BASE) down --remove-orphans

docker-rebuild: docker-down docker-build docker-up-dev
	@echo "Rebuilt and restarted dev stack"

# ---------------------------
# Test / CI targets
# ---------------------------

docker-test: env-check
	@echo "Running containerized tests using test compose"
	@if [ -f "$(COMPOSE_TEST)" ]; then \
	  $(DOCKER_COMPOSE) --project-directory $(CURDIR) --env-file $(CURDIR)/.env -f $(COMPOSE_BASE) -f $(COMPOSE_TEST) up --abort-on-container-exit --build; \
	  status=$$?; \
	  echo "Tearing down test containers..."; \
	  $(DOCKER_COMPOSE) --project-directory $(CURDIR) --env-file $(CURDIR)/.env -f $(COMPOSE_BASE) -f $(COMPOSE_TEST) down --remove-orphans --volumes; \
	  exit $$status; \
	else \
	  echo "No test compose overlay found at $(COMPOSE_TEST)"; exit 2; \
	fi

# ---------------------------
# E2E Testing targets
# ---------------------------

docker-e2e: env-check
	@echo "Running E2E tests in optimized environment (MacBook Air friendly)"
	@if [ -f "$(COMPOSE_E2E)" ]; then \
	  echo "Starting E2E test environment..."; \
	  $(DOCKER_COMPOSE) --project-directory $(CURDIR) --env-file $(CURDIR)/.env -f $(COMPOSE_BASE) -f $(COMPOSE_E2E) up --build --abort-on-container-exit; \
	  status=$$?; \
	  echo "E2E tests completed with exit code: $$status"; \
	  echo "Keeping containers running for artifact inspection..."; \
	  echo "Use 'make docker-e2e-clean' to clean up when done"; \
	  exit $$status; \
	else \
	  echo "No E2E compose overlay found at $(COMPOSE_E2E)"; exit 2; \
	fi

docker-e2e-clean:
	@echo "Cleaning up E2E test environment and volumes"
	@$(DOCKER_COMPOSE) --project-directory $(CURDIR) --env-file $(CURDIR)/.env -f $(COMPOSE_BASE) -f $(COMPOSE_E2E) down --remove-orphans --volumes
	@echo "E2E environment cleaned up"

# E2E test scenarios
docker-e2e-minimal: env-check
	@echo "Running minimal E2E tests (fastest)"
	@E2E_TEST_SCENARIO=minimal $(MAKE) docker-e2e

docker-e2e-standard: env-check
	@echo "Running standard E2E tests"
	@E2E_TEST_SCENARIO=standard $(MAKE) docker-e2e

docker-e2e-large: env-check
	@echo "Running large dataset E2E tests"
	@E2E_TEST_SCENARIO=large $(MAKE) docker-e2e

docker-e2e-edge-cases: env-check
	@echo "Running edge case E2E tests"
	@E2E_TEST_SCENARIO=edge-cases $(MAKE) docker-e2e

# Interactive E2E debugging
docker-e2e-debug: env-check
	@echo "Starting E2E environment for interactive debugging"
	@$(DOCKER_COMPOSE) --project-directory $(CURDIR) --env-file $(CURDIR)/.env -f $(COMPOSE_BASE) -f $(COMPOSE_E2E) run --rm e2e-orchestrator sh

# ---------------------------
# Logs / exec helpers
# ---------------------------

docker-logs:
	@echo "Tailing logs for service: $(SERVICE)"
	@$(DOCKER_COMPOSE) --project-directory $(CURDIR) --env-file $(CURDIR)/.env -f $(COMPOSE_BASE) logs -f --tail=200 $(SERVICE)

docker-exec:
	@CMD=${CMD:-sh}; \
	echo "Executing in service $(SERVICE): $$CMD"; \
	$(DOCKER_COMPOSE) --project-directory $(CURDIR) --env-file $(CURDIR)/.env -f $(COMPOSE_BASE) exec --user root $(SERVICE) sh -c "$$CMD"

# ---------------------------
# Registry / publish
# ---------------------------

docker-push: env-check
ifndef DOCKER_REGISTRY
	$(error DOCKER_REGISTRY is not set. Example: DOCKER_REGISTRY=ghcr.io/myorg)
endif
	@REPO=$(DOCKER_REGISTRY); \
	TAG=$(DOCKER_TAG); \
	TARGET="$${REPO}/$${IMAGE_NAME%%:*}:$${TAG}"; \
	echo "Tagging image $(IMAGE_NAME) -> $$TARGET"; \
	docker tag $(IMAGE_NAME) $$TARGET; \
	echo "Pushing $$TARGET"; \
	docker push $$TARGET

# ---------------------------
# Benchmarks
# ---------------------------

.PHONY: benchmark-transition-detection

benchmark-transition-detection:
	@echo "Running transition detection benchmark..."
	@poetry run python scripts/benchmark_transition_detection.py --save-as-baseline

# ---------------------------
# Transition MVP (local runner)
# ---------------------------

.PHONY: transition-mvp-run transition-mvp-clean

transition-mvp-run:
	@echo "Running Transition Detection MVP locally (shimmed)..."
	@mkdir -p data/processed reports/validation
	@poetry run python scripts/transition_mvp_run.py


transition-mvp-clean:
	@echo "Cleaning Transition MVP artifacts..."
	-@rm -f data/processed/vendor_resolution.parquet data/processed/vendor_resolution.ndjson data/processed/vendor_resolution.checks.json
	-@rm -f data/processed/transitions.parquet data/processed/transitions.ndjson data/processed/transitions.checks.json
	-@rm -f data/processed/transitions_evidence.ndjson
	-@rm -f data/processed/contracts_sample.parquet data/processed/contracts_sample.csv data/processed/contracts_sample.checks.json
	-@rm -f reports/validation/transition_mvp.json

# Transition MVP (gated helpers)
.PHONY: transition-mvp-run-gated transition-audit-export transition-audit-import

transition-mvp-run-gated:
	@$(MAKE) transition-mvp-run
	@python - <<'PY'
import json, sys
from pathlib import Path
summary_path = Path("reports/validation/transition_mvp.json")
if not summary_path.exists():
    print(f"Validation summary not found at {summary_path}", file=sys.stderr)
    sys.exit(2)
data = json.loads(summary_path.read_text(encoding="utf-8"))
gates = data.get("gates", {})
cs = gates.get("contracts_sample", {}) or {}
vr = gates.get("vendor_resolution", {}) or {}
failures = []
if not cs.get("passed", False):
    failures.append("contracts_sample coverage gate failed")
if not vr.get("passed", False):
    failures.append("vendor_resolution rate gate failed")
if failures:
    for f in failures:
        print(f"ERROR: {f}", file=sys.stderr)
    sys.exit(1)
print("Validation gates passed.")
PY
	@python - <<'PY'
import json, sys
from pathlib import Path
p = Path("data/processed/transitions_evidence.checks.json")
if not p.exists():
    print(f"Evidence checks JSON not found at {p}", file=sys.stderr)
    sys.exit(2)
data = json.loads(p.read_text(encoding="utf-8"))
comp = data.get("completeness") or {}
if not comp.get("complete", False):
    print(f"ERROR: Evidence completeness gate failed: {comp}", file=sys.stderr)
    sys.exit(1)
print("Evidence completeness gate passed.")
PY
	@echo "✓ Transition MVP gated run succeeded"

transition-audit-export:
	@echo "Exporting precision audit sample CSV..."
	@mkdir -p reports/validation
	@poetry run python scripts/transition_precision_audit.py --export-csv reports/validation/vendor_resolution_audit_sample.csv

transition-audit-import:
	@if [ -z "${CSV}" ]; then echo "Provide CSV=path/to/labeled.csv"; exit 2; fi
	@THRESHOLD=$${THRESHOLD:-0.80}; \
	poetry run python scripts/transition_precision_audit.py --import-csv "$$CSV" --threshold "$$THRESHOLD"

# ---------------------------
# Environment / safety checks
# ---------------------------

env-check:
	@if [ ! -f .env ]; then \
	  echo "*** .env file not found. Copy .env.example to .env and set required values (NEO4J_USER, NEO4J_PASSWORD, etc.)"; \
	  echo "    cp .env.example .env"; \
	  exit 1; \
	else \
	  echo ".env found"; \
	fi

# ---------------------------
# Neo4j helpers
# ---------------------------

neo4j-up: env-check
	@echo "Starting Neo4j (profile neo4j) using docker/neo4j.compose.override.yml"
	@$(DOCKER_COMPOSE) --project-directory $(CURDIR) --env-file $(CURDIR)/.env -f docker-compose.yml -f docker/neo4j.compose.override.yml --profile neo4j up -d --build
	@echo "Neo4j started (give it a few seconds to become healthy)"

neo4j-down:
	@echo "Stopping Neo4j (profile neo4j)"
	@$(DOCKER_COMPOSE) --project-directory $(CURDIR) --env-file $(CURDIR)/.env -f docker-compose.yml -f docker/neo4j.compose.override.yml --profile neo4j down --remove-orphans --volumes

neo4j-reset: neo4j-down
	@echo "Resetting Neo4j named volumes (neo4j_data, neo4j_logs, neo4j_import)"
	-@docker volume rm neo4j_data neo4j_logs neo4j_import 2>/dev/null || true
	@echo "Volumes removed (if they existed). Starting fresh Neo4j..."
	@$(MAKE) neo4j-up

neo4j-backup:
	@echo "Running Neo4j backup script"
	@mkdir -p ${BACKUP_DIR:-backups/neo4j} || true
	@BACKUP_DIR=${BACKUP_DIR:-backups/neo4j} DB_NAME=${DB_NAME:-neo4j} ${SHELL} scripts/neo4j/backup.sh

neo4j-restore:
	@if [ -z "${BACKUP_PATH:-}" ]; then \
	  echo "Please provide BACKUP_PATH=/path/to/dump to restore"; exit 2; \
	fi
	@echo "Restoring Neo4j from ${BACKUP_PATH}"
	@${SHELL} scripts/neo4j/restore.sh --backup-path "${BACKUP_PATH}"

neo4j-check:
	@echo "Running Neo4j health check"
	@$(DOCKER_COMPOSE) --project-directory $(CURDIR) --env-file $(CURDIR)/.env -f docker-compose.yml -f docker/neo4j.compose.override.yml --profile neo4j run --rm neo4j sh -c "cypher-shell -u ${NEO4J_USER:-neo4j} -p ${NEO4J_PASSWORD:-password} 'RETURN 1' >/dev/null 2>&1 || exit 1"
	@echo "Neo4j health check completed (exit code 0 indicates healthy)"

.PHONY: neo4j-up neo4j-down neo4j-reset neo4j-backup neo4j-restore neo4j-check

# ---------------------------
# Convenience aliases
# ---------------------------

.PHONY: help docker-build docker-buildx docker-up-dev docker-up-prod cet-staging-up cet-staging-down docker-down docker-rebuild docker-test docker-e2e docker-e2e-clean docker-e2e-minimal docker-e2e-standard docker-e2e-large docker-e2e-edge-cases docker-e2e-debug docker-logs docker-exec docker-push env-check transition-mvp-run transition-mvp-clean transition-mvp-run-gated transition-audit-export transition-audit-import
