# SBIR ETL consolidated Makefile (rebuilt 2025-10-31)
# ----------------------------------------------------
# Goals of this rebuild
#   * Always show the commands being executed (unless QUIET=1)
#   * Give friendly, colourised status messages for each major step
#   * Keep the commands that the team actually relies on today
#   * Remain shell-agnostic (POSIX /bin/bash) and avoid external helpers
#   * Provide easily discoverable help via `make help`

SHELL := /bin/bash
.DEFAULT_GOAL := help
MAKEFLAGS += --warn-undefined-variables

# -----------------------------------------------------------------------------
# Configuration (overridable)
# -----------------------------------------------------------------------------

IMAGE_NAME        ?= sbir-analytics:latest
DOCKER_REGISTRY   ?=
DOCKER_TAG        ?= latest
BUILD_CONTEXT     ?= .
DOCKERFILE        ?= Dockerfile
COMPOSE_FILE      ?= docker-compose.yml
DOCKER_COMPOSE    ?= docker compose
SERVICE           ?= dagster-webserver
STARTUP_TIMEOUT   ?= 120
QUIET             ?= 0

COMPOSE := $(DOCKER_COMPOSE) -f $(COMPOSE_FILE)

# -----------------------------------------------------------------------------
# Colours + helpers
# -----------------------------------------------------------------------------

RESET  := \033[0m
BLUE   := \033[34m
GREEN  := \033[32m
YELLOW := \033[33m
RED    := \033[31m
GRAY   := \033[90m

info = if [ "$(QUIET)" != "1" ]; then printf "$(BLUE)➤$(RESET) %s\n" "$(1)"; fi
success = if [ "$(QUIET)" != "1" ]; then printf "$(GREEN)✔$(RESET) %s\n" "$(1)"; fi
warn = if [ "$(QUIET)" != "1" ]; then printf "$(YELLOW)⚠$(RESET) %s\n" "$(1)"; fi
failure = if [ "$(QUIET)" != "1" ]; then printf "$(RED)✖$(RESET) %s\n" "$(1)"; fi
print-cmd = if [ "$(QUIET)" != "1" ]; then printf "$(GRAY)$$ %s$(RESET)\n" "$(strip $(1))"; fi

define run
	@if [ "$(QUIET)" != "1" ]; then printf "$(GRAY)$$ %s$(RESET)\n" "$(strip $(1))"; fi
	@set -euo pipefail; $(1)
endef

# -----------------------------------------------------------------------------
# Help
# -----------------------------------------------------------------------------

.PHONY: help
help: ## Show this help message
	@awk 'BEGIN {FS = ":.*##"; printf "\nAvailable targets\n------------------\n"} \
	     /^[a-zA-Z0-9_.-]+:.*##/ {printf "\033[36m%-24s\033[0m %s\n", $$1, $$2}' \
	     $(MAKEFILE_LIST)

# -----------------------------------------------------------------------------
# Safety checks
# -----------------------------------------------------------------------------

.PHONY: env-check
env-check: ## Ensure a local .env file is present
	@set -euo pipefail; \
	 if [ ! -f .env ]; then \
	   printf "$(RED)✖$(RESET) .env file not found. Copy .env.example → .env and update credentials.\n"; \
	   exit 1; \
	 else \
	   printf "$(GREEN)✔$(RESET) .env found\n"; \
	 fi

.PHONY: docker-check
docker-check: ## Verify Docker CLI and daemon availability
	@set -euo pipefail; \
	 if ! command -v docker >/dev/null 2>&1; then \
	   printf "$(RED)✖$(RESET) Docker CLI not found. Install Docker Desktop from https://www.docker.com/products/docker-desktop\n"; \
	   exit 1; \
	 fi; \
	 printf "$(BLUE)➤$(RESET) Docker CLI detected: %s\n" "$$(docker --version)"; \
	 if docker info >/dev/null 2>&1; then \
	   printf "$(GREEN)✔$(RESET) Docker daemon is running and accessible\n"; \
	   if docker compose version >/dev/null 2>&1; then \
	     printf "$(GREEN)✔$(RESET) docker compose available\n"; \
	   else \
	     printf "$(YELLOW)⚠$(RESET) docker compose plugin not detected\n"; \
	   fi; \
	 else \
	   printf "$(RED)✖$(RESET) Docker daemon is not running or not accessible\n"; \
	   printf "$(YELLOW)⚠$(RESET) Start Docker Desktop or run: open -a Docker\n"; \
	   exit 1; \
	 fi

.PHONY: docker-check-install
docker-check-install: ## Quick check for Docker CLI only
	@set -euo pipefail; \
	 if command -v docker >/dev/null 2>&1; then \
	   printf "$(GREEN)✔$(RESET) Docker CLI detected: %s\n" "$$(docker --version)"; \
	 else \
	   printf "$(RED)✖$(RESET) Docker CLI not found\n"; \
	   exit 1; \
	 fi

.PHONY: docker-check-prerequisites
docker-check-prerequisites: ## Check all prerequisites for Docker development setup
	@$(call info,Checking Docker development prerequisites)
	$(call run,./scripts/docker/check-prerequisites.sh)

.PHONY: docker-verify
docker-verify: env-check ## Verify Docker setup is working correctly
	@$(call info,Verifying Docker setup)
	@set -euo pipefail; \
	 $(call info,Checking Neo4j connectivity...); \
	 if $(COMPOSE) --profile dev exec -T neo4j \
	    cypher-shell -u $${NEO4J_USER:-neo4j} -p $${NEO4J_PASSWORD:-test} 'RETURN 1' >/dev/null 2>&1; then \
	   $(call success,Neo4j is accessible at bolt://localhost:7687); \
	 else \
	   $(call failure,Neo4j is not accessible); \
	   $(call warn,Check logs with: make docker-logs SERVICE=neo4j); \
	   exit 1; \
	 fi; \
	 $(call info,Checking Dagster UI...); \
	 if curl -fsS --max-time 3 http://localhost:3000/server_info >/dev/null 2>&1; then \
	   $(call success,Dagster UI is accessible at http://localhost:3000); \
	 else \
	   $(call failure,Dagster UI is not accessible); \
	   $(call warn,Check logs with: make docker-logs SERVICE=dagster-webserver); \
	   exit 1; \
	 fi; \
	 $(call info,Checking service status...); \
	 if $(COMPOSE) --profile dev ps --format json 2>/dev/null | grep -q '"State":"running"'; then \
	   $(call success,All services are running); \
	 else \
	   $(call warn,Some services may not be running); \
	   $(call info,Run 'make docker-logs' to see service status); \
	 fi; \
	 echo ""; \
	 $(call success,✓ Docker setup verification passed!); \
	 echo ""; \
	 echo "  • Dagster UI: http://localhost:3000"; \
	 echo "  • Neo4j Browser: http://localhost:7474"; \
	 echo "  • View logs: make docker-logs SERVICE=<name>"

# -----------------------------------------------------------------------------
# Local Development (New)
# -----------------------------------------------------------------------------

.PHONY: install
install: ## Install the full local development stack with uv
	@$(call info,Installing the full local development stack)
	$(call run,uv sync --extra stack-dev)

.PHONY: install-core
install-core: ## Install only the reusable sbir-etl library dependencies
	@$(call info,Installing core sbir-etl dependencies)
	$(call run,uv sync)

.PHONY: doctor
doctor: ## Verify the local Python development environment
	@$(call info,Checking local development environment)
	@command -v uv >/dev/null 2>&1 || { \
	  printf "$(RED)✖$(RESET) uv is not installed\n"; \
	  exit 1; \
	}
	$(call run,uv run --no-sync python -c 'import sys; assert sys.version_info.major == 3 and 11 <= sys.version_info.minor < 13')
	$(call run,uv run --no-sync python -c 'import dagster; import pytest; import sbir_analytics; import sbir_etl; import sbir_graph; import sbir_ml')
	$(call run,uv run --no-sync ruff --version)
	$(call run,uv run --no-sync mypy --version)
	@$(call success,Development environment is ready)

.PHONY: test
test: ## Run all tests
	@$(call info,Running tests)
	$(call run,uv run pytest -v --cov=sbir_etl --cov=packages/sbir-analytics/sbir_analytics --cov=packages/sbir-ml/sbir_ml --cov=packages/sbir-graph/sbir_graph)

.PHONY: test-unit
test-unit: ## Run unit tests only
	@$(call info,Running unit tests)
	$(call run,uv run pytest tests/unit/ -v)

.PHONY: test-smoke
test-smoke: ## Run a fast, data-free onboarding smoke test
	@$(call info,Running onboarding smoke tests)
	$(call run,uv run pytest -n 0 tests/unit/test_models.py tests/unit/assets/test_asset_discovery.py -v)

.PHONY: test-integration
test-integration: ## Run integration tests only
	@$(call info,Running integration tests)
	$(call run,uv run pytest tests/integration/ -v)

.PHONY: test-functional
test-functional: ## Run functional pipeline tests
	@$(call info,Running functional tests)
	$(call run,uv run pytest tests/functional/ -v)

.PHONY: test-transition
test-transition: ## Test transition detection pipeline
	@$(call info,Testing transition pipeline)
	$(call run,uv run pytest tests/functional/test_pipelines.py::TestTransitionPipeline -v)

.PHONY: test-cet
test-cet: ## Test CET classification pipeline
	@$(call info,Testing CET pipeline)
	$(call run,uv run pytest tests/functional/test_pipelines.py::TestCETPipeline -v)

.PHONY: test-fiscal
test-fiscal: ## Test fiscal returns pipeline
	@$(call info,Testing fiscal pipeline)
	$(call run,uv run pytest tests/functional/test_pipelines.py::TestFiscalPipeline -v)

.PHONY: test-modernbert
test-modernbert: ## Test ModernBert pipeline
	@$(call info,Testing ModernBert pipeline)
	$(call run,uv run pytest tests/functional/test_pipelines.py::TestModernBertPipeline -v)

.PHONY: lint
lint: ## Run linting and type checking
	@$(call info,Running linting and type checking)
	$(call run,uv run ruff check .)
	$(call run,uv run mypy sbir_etl/)

.PHONY: lint-boundaries
lint-boundaries: ## Enforce package and archive dependency boundaries
	@$(call info,Checking architecture boundaries)
	$(call run,uv run python scripts/ci/check_architecture_boundaries.py)
	$(call run,uv run python scripts/ci/check_tier_boundaries.py)
	$(call run,uv run python scripts/ci/check_file_sizes.py)
	$(call run,uv run python scripts/ci/check_removed_src_references.py)
	$(call run,uv run python scripts/ci/validate_study_manifests.py)

.PHONY: docs-check
docs-check: ## Check docs, agent files, spec registry, stale commands, and old code references
	@$(call info,Running repository hygiene checks)
	$(call run,uv run python scripts/ci/check_removed_src_references.py)

.PHONY: format
format: ## Format code
	@$(call info,Formatting code)
	$(call run,uv run ruff format .)
	$(call run,uv run ruff check --fix .)

.PHONY: dev
dev: ## Run Dagster dev server locally
	@$(call info,Starting Dagster dev server)
	$(call run,uv run dagster dev -m sbir_analytics.definitions)

.PHONY: install-ml
install-ml: ## Install ML/notebook dependencies (jupyter + first-party packages)
	@$(call info,Installing ML dependencies)
	$(call run,uv sync --extra stack-dev --group notebooks)

.PHONY: install-fiscal
install-fiscal: ## Verify BEA API key is set for fiscal analysis
	@$(call info,Checking BEA API key for fiscal analysis)
	@if [ -z "$$BEA_API_KEY" ]; then \
		echo "⚠️  BEA_API_KEY not set. Register at https://apps.bea.gov/API/signup/"; \
	else \
		echo "✓ BEA_API_KEY is configured"; \
	fi

.PHONY: notebook
notebook: install-ml ## Start Jupyter Lab for ML analysis (Cloud-Native)
	@$(call info,Starting Jupyter Lab)
	@mkdir -p notebooks
	$(call run,uv run --group notebooks jupyter lab --notebook-dir=notebooks)

.PHONY: setup-ml
setup-ml: env-check ## Configure environment for ML (HuggingFace)
	@$(call info,Configuring ML environment)
	@$(call info,This will prompt for a HuggingFace Token.)
	@if ! grep -q "HF_TOKEN" .env; then \
		echo "HF_TOKEN=" >> .env; \
		$(call warn,Added HF_TOKEN to .env. Please edit it to add your HuggingFace token.); \
	else \
		$(call success,HF_TOKEN already present in .env); \
	fi

.PHONY: sample-data
sample-data: ## Generate sample data for local development
	@$(call info,Generating sample data)
	$(call run,uv run python scripts/dev/generate_sample_data.py)

.PHONY: setup-local
setup-local: env-check ## Configure environment for local development
	@$(call info,Configuring local environment)
	@$(call info,You can now generate sample data with: make sample-data)

# -----------------------------------------------------------------------------
# Build + publish
# -----------------------------------------------------------------------------

.PHONY: docker-build
docker-build: ## Build the application Docker image (BuildKit)
	@$(call info,Building Docker image $(IMAGE_NAME))
	$(call run,DOCKER_BUILDKIT=1 docker build -t $(IMAGE_NAME) -f $(DOCKERFILE) $(BUILD_CONTEXT))
	@$(call success,Image $(IMAGE_NAME) ready)

.PHONY: docker-buildx
docker-buildx: ## Build the image using docker buildx (multi-platform)
	@$(call info,Building Docker image with buildx: $(IMAGE_NAME))
	$(call run,docker buildx build --load -t $(IMAGE_NAME) -f $(DOCKERFILE) $(BUILD_CONTEXT))
	@$(call success,Image $(IMAGE_NAME) built via buildx)

.PHONY: docker-push
docker-push: docker-build ## Push the tagged image to DOCKER_REGISTRY (set DOCKER_REGISTRY first)
	@if [ -z "$(DOCKER_REGISTRY)" ]; then \
	  printf "$(RED)✖$(RESET) DOCKER_REGISTRY is not set. Usage: make docker-push DOCKER_REGISTRY=ghcr.io/myorg\n"; \
	  exit 1; \
	fi
	@set -euo pipefail; \
	 TARGET="$(DOCKER_REGISTRY)/$${IMAGE_NAME%%:*}:$(DOCKER_TAG)"; \
	 printf "$(BLUE)➤$(RESET) Tagging image $(IMAGE_NAME) → %s\n" "$$TARGET"; \
	 docker tag $(IMAGE_NAME) "$$TARGET"; \
	 printf "$(BLUE)➤$(RESET) Pushing %s\n" "$$TARGET"; \
	 docker push "$$TARGET"

# -----------------------------------------------------------------------------
# Environment lifecycle
# -----------------------------------------------------------------------------

.PHONY: docker-up-dev
docker-up-dev: env-check ## Start the development stack (profile=dev)
	@$(call info,Starting development stack (profile: dev))
	$(call run,$(COMPOSE) --profile dev up -d --build)
	$(call run,$(COMPOSE) --profile dev ps)
	@$(call success,Development stack ready)


.PHONY: docker-up-tools
docker-up-tools: env-check ## Start the tools container (profile=dev)
	@$(call info,Starting tools container (profile: dev))
	$(call run,$(COMPOSE) --profile dev up -d tools)
	$(call run,$(COMPOSE) --profile dev ps tools)

.PHONY: docker-down
docker-down: ## Stop all services and remove volumes
	@$(call info,Stopping all services and removing volumes)
	$(call print-cmd,$(COMPOSE) down --remove-orphans --volumes)
	@STATUS=0; \
	if ! $(COMPOSE) down --remove-orphans --volumes; then STATUS=$$?; fi; \
	if [ $$STATUS -eq 0 ]; then \
		$(call success,Services stopped and cleaned up); \
	else \
		$(call warn,Cleanup exited with code $$STATUS (this can happen if nothing was running)); \
	fi; \
	exit $$STATUS

.PHONY: docker-rebuild
docker-rebuild: docker-down docker-build docker-up-dev ## Rebuild the image and restart the dev stack
	@$(call success,Development stack rebuilt and restarted)

# -----------------------------------------------------------------------------
# Logs & shell access
# -----------------------------------------------------------------------------

.PHONY: docker-logs
docker-logs: ## Tail logs for SERVICE (default dagster-webserver)
	@set -euo pipefail
	$(call info,Tailing logs for service: $(SERVICE))
	$(call print-cmd,$(COMPOSE) logs -f --tail=200 $(SERVICE))
	@$(COMPOSE) logs -f --tail=200 $(SERVICE)

.PHONY: docker-exec
docker-exec: ## Execute CMD (default sh) in SERVICE
	@CMD=$${CMD:-sh}; \
	 $(call info,Executing in service $(SERVICE): $$CMD); \
	 $(call run,$(COMPOSE) exec $(SERVICE) sh -c "$$CMD")

# -----------------------------------------------------------------------------
# Testing & E2E
# -----------------------------------------------------------------------------

.PHONY: docker-test
docker-test: env-check ## Run containerised CI tests (profile=ci)
	@set -euo pipefail; \
	 $(call info,Running containerised tests (profile: ci)); \
	 $(call print-cmd,$(COMPOSE) --profile ci up --abort-on-container-exit --build); \
	 STATUS=0; \
	 if ! $(COMPOSE) --profile ci up --abort-on-container-exit --build; then STATUS=$$?; fi; \
	 $(call print-cmd,$(COMPOSE) --profile ci down --remove-orphans --volumes); \
	 $(COMPOSE) --profile ci down --remove-orphans --volumes || true; \
	 if [ $$STATUS -eq 0 ]; then \
	   $(call success,Tests passed); \
	 else \
	   $(call failure,Tests failed (exit $$STATUS)); \
	   $(call warn,View logs with: make docker-logs SERVICE=app); \
	 fi; \
	 exit $$STATUS

.PHONY: docker-e2e
docker-e2e: env-check ## Run full end-to-end test suite (profile=ci)
	@set -euo pipefail; \
	 $(call info,Running E2E tests (profile: ci)); \
	 $(call print-cmd,$(COMPOSE) --profile ci up --build --abort-on-container-exit neo4j app); \
	 STATUS=0; \
	 if ! $(COMPOSE) --profile ci up --build --abort-on-container-exit neo4j app 2>&1; then STATUS=$$?; fi; \
	 if [ "$(QUIET)" != "1" ]; then printf "$(BLUE)➤$(RESET) E2E tests completed with exit code %s\n" "$$STATUS"; fi; \
	 if [ $$STATUS -ne 0 ]; then \
	   $(call failure,E2E tests failed with exit code $$STATUS); \
	   $(call info,Showing recent logs from failed containers...); \
	   $(COMPOSE) --profile ci logs --tail=50 app 2>&1 || true; \
	   $(COMPOSE) --profile ci logs --tail=20 neo4j 2>&1 || true; \
	 else \
	   $(call success,E2E tests passed – containers left running for inspection); \
	 fi; \
	 $(call warn,Use 'make docker-logs SERVICE=app' to view test logs); \
	 $(call warn,Use 'make docker-e2e-clean' to tear down when finished); \
	 exit $$STATUS

.PHONY: docker-e2e-clean
docker-e2e-clean: ## Tear down the E2E environment
	@set -euo pipefail; \
	 if [ "$(QUIET)" != "1" ]; then printf "$(BLUE)➤$(RESET) Cleaning up E2E test environment\n"; fi; \
	 printf "$(GRAY)$ %s$(RESET)\n" "$(COMPOSE) --profile ci down --remove-orphans --volumes"; \
	 STATUS=0; \
	 if ! $(COMPOSE) --profile ci down --remove-orphans --volumes; then STATUS=$$?; fi; \
	 if [ $$STATUS -eq 0 ]; then \
	   if [ "$(QUIET)" != "1" ]; then printf "$(GREEN)✔$(RESET) %s\n" "E2E environment cleaned up successfully"; fi; \
	 else \
	   if [ "$(QUIET)" != "1" ]; then printf "$(YELLOW)⚠$(RESET) %s\n" "Cleanup exited with code $$STATUS (likely nothing was running)"; fi; \
	 fi; \
	 exit $$STATUS

.PHONY: docker-e2e-minimal
docker-e2e-minimal: env-check ## Run the minimal (fast) E2E scenario
	@$(call info,Running minimal E2E scenario)
	@E2E_TEST_SCENARIO=minimal $(MAKE) docker-e2e

.PHONY: docker-e2e-standard
docker-e2e-standard: env-check ## Run the standard E2E scenario
	@$(call info,Running standard E2E scenario)
	@E2E_TEST_SCENARIO=standard $(MAKE) docker-e2e

.PHONY: docker-e2e-large
docker-e2e-large: env-check ## Run the large dataset E2E scenario
	@$(call info,Running large dataset E2E scenario)
	@E2E_TEST_SCENARIO=large $(MAKE) docker-e2e

.PHONY: docker-e2e-edge-cases
docker-e2e-edge-cases: env-check ## Run the edge-case E2E scenario
	@$(call info,Running edge-case E2E scenario)
	@E2E_TEST_SCENARIO=edge-cases $(MAKE) docker-e2e

.PHONY: docker-e2e-debug
docker-e2e-debug: env-check ## Open an interactive shell in the CI test container
	@$(call info,Opening interactive shell in CI test container)
	$(call run,$(COMPOSE) --profile ci run --rm app sh)

# -----------------------------------------------------------------------------
# Neo4j helpers
# -----------------------------------------------------------------------------

.PHONY: neo4j-up
neo4j-up: env-check ## Start Neo4j only (profile=dev)
	$(call info,Starting Neo4j (profile: dev))
	$(call run,$(COMPOSE) --profile dev up -d neo4j)

.PHONY: neo4j-down
neo4j-down: ## Stop Neo4j (profile=dev)
	$(call info,Stopping Neo4j (profile: dev))
	$(call run,$(COMPOSE) --profile dev stop neo4j)

.PHONY: neo4j-reset
neo4j-reset: neo4j-down ## Reset Neo4j with fresh volumes
	$(call info,Removing Neo4j volumes)
	-@docker volume rm neo4j_data neo4j_logs neo4j_import >/dev/null 2>&1 || true
	$(call info,Bringing Neo4j back up)
	@$(MAKE) neo4j-up

.PHONY: neo4j-check
neo4j-check: env-check ## Run the Neo4j health check
	$(call info,Checking Neo4j health via cypher-shell)
	@set -euo pipefail; \
	 if $(COMPOSE) --profile dev exec neo4j \
	    cypher-shell -u $${NEO4J_USER:-neo4j} -p $${NEO4J_PASSWORD:-password} 'RETURN 1' >/dev/null 2>&1; then \
	   $(call success,Neo4j responded successfully); \
	 else \
	   $(call failure,Neo4j health check failed); \
	  exit 1; \
	 fi

# -----------------------------------------------------------------------------
# Function-specific pipeline runs
# -----------------------------------------------------------------------------

.PHONY: transition-run
transition-run: ## Run transition detection pipeline
	@$(call info,Running transition detection)
	$(call run,uv run dagster job execute -m sbir_analytics.definitions -j transition_mvp_job)
	@$(call success,Transition detection completed)

.PHONY: cet-run
cet-run: ## Run CET classification pipeline
	@$(call info,Running CET classification)
	$(call run,uv run dagster job execute -m sbir_analytics.definitions_ml -j cet_full_pipeline_job)
	@$(call success,CET classification completed)

.PHONY: fiscal-run
fiscal-run: ## Run fiscal returns analysis (BEA API)
	@$(call info,Running fiscal returns analysis)
	$(call run,uv run dagster job execute -m sbir_analytics.definitions_ml -j fiscal_returns_mvp_job)
	@$(call success,Fiscal returns analysis completed)

.PHONY: modernbert-run
modernbert-run: ## Run ModernBert embeddings and similarity
	@$(call info,Running ModernBert analysis)
	$(call run,uv run dagster job execute -m sbir_analytics.definitions_ml -j modernbert_job)
	@$(call success,ModernBert analysis completed)

# -----------------------------------------------------------------------------
# Legacy artifact cleanup
# -----------------------------------------------------------------------------

.PHONY: transition-mvp-clean
transition-mvp-clean: ## Clean up Transition MVP artifacts
	@$(call info,Cleaning up Transition MVP artifacts)
	@set -euo pipefail; \
	 FILES="data/processed/contracts_sample.* data/processed/vendor_resolution.* data/processed/transitions.* data/processed/transitions_evidence.* reports/validation/transition_mvp.json"; \
	 if ls $$FILES >/dev/null 2>&1; then \
	   rm -f $$FILES; \
	   $(call success,Transition MVP artifacts cleaned); \
	 else \
	   $(call warn,No Transition MVP artifacts found to clean); \
	 fi

# -----------------------------------------------------------------------------
# Convenience targets
# -----------------------------------------------------------------------------

.PHONY: logs-all
logs-all: ## Show logs from all running containers
	@$(call info,Showing logs from all containers)
	$(call run,$(COMPOSE) logs -f)

.PHONY: ps
ps: ## Show running containers
	@$(call info,Listing running containers)
	$(call run,$(COMPOSE) ps)

.PHONY: clean-all
clean-all: ## Remove this project's containers and Compose volumes
	@$(call info,Cleaning project Docker resources)
	@set -euo pipefail; \
	 $(call run,$(COMPOSE) down --remove-orphans --volumes); \
	 $(call success,Project containers and Compose volumes cleaned)

.PHONY: shell
shell: env-check ## Drop into a shell in the app container
	@$(call info,Opening shell in app container)
	$(call run,$(COMPOSE) --profile dev run --rm app sh)

.PHONY: db-shell
db-shell: env-check ## Drop into Neo4j cypher-shell
	@$(call info,Opening Neo4j cypher-shell)
	@set -euo pipefail; \
	 $(COMPOSE) --profile dev exec neo4j \
	   cypher-shell -u $${NEO4J_USER:-neo4j} -p $${NEO4J_PASSWORD:-password}

.PHONY: validate-config
validate-config: ## Validate docker-compose.yml and .env files
	@$(call info,Validating docker-compose.yml)
	@set -euo pipefail; \
	 if ! $(COMPOSE) config >/dev/null 2>&1; then \
	   $(call failure,docker-compose.yml validation failed); \
	   $(COMPOSE) config; \
	   exit 1; \
	 fi; \
	 $(call success,docker-compose.yml is valid); \
	 if [ -f .env ]; then \
	   $(call info,Checking .env file); \
	   if grep -q "^[^#].*=" .env; then \
	     $(call success,.env file contains configuration); \
	   else \
	     $(call warn,.env file exists but appears empty); \
	   fi; \
	 else \
	   $(call warn,.env file not found - copy from .env.example); \
	 fi

.PHONY: validate
validate: lint test ## Run linting, type checking, and tests
	@$(call success,All validation checks passed)

# -----------------------------------------------------------------------------
# Tailscale-only self-hosted server profile
# -----------------------------------------------------------------------------

SERVER_COMPOSE_FILE ?= docker-compose.server.yml
SERVER_ENV_FILE     ?= .env.server
SERVER_COMPOSE       = $(DOCKER_COMPOSE) -f $(SERVER_COMPOSE_FILE) --env-file $(SERVER_ENV_FILE)
SERVER_PYTHON_BASE_IMAGE ?= ghcr.io/hollomancer/sbir-analytics-python-base:latest

.PHONY: server-env-check
server-env-check: ## Ensure .env.server exists
	@set -euo pipefail; \
	 if [ ! -f $(SERVER_ENV_FILE) ]; then \
	   printf "$(RED)✖$(RESET) $(SERVER_ENV_FILE) not found. Copy .env.server.example → $(SERVER_ENV_FILE).\n"; \
	   exit 1; \
	 else \
	   printf "$(GREEN)✔$(RESET) $(SERVER_ENV_FILE) found\n"; \
	 fi

.PHONY: server-check
server-check: ## Validate server prerequisites (Docker, storage, ports, Tailscale, bindings)
	@$(call info,Checking Tailscale-only server prerequisites)
	$(call run,SERVER_ENV_FILE=$(SERVER_ENV_FILE) ./scripts/server/check-prerequisites.sh)

.PHONY: server-base-image
server-base-image: server-check ## Build the native Python base image from source
	@$(call info,Building the native Python base image)
	# Built locally rather than pulled. This used to try `docker pull` first and
	# only build when the pull failed, which meant "missing manifest for this
	# architecture" was the sole trigger. Since build-images.yml was retired
	# nothing republishes ghcr.io/.../sbir-analytics-python-base:latest, so the
	# pull always succeeded and pinned this host to a base image that will never
	# be refreshed again. Building from Dockerfile.python-base keeps the base in
	# step with the repository; Docker's layer cache makes repeat builds cheap,
	# so only a real change to the base's inputs costs the full build.
	$(call run,docker build -f Dockerfile.python-base -t $(SERVER_PYTHON_BASE_IMAGE) .)
	@$(call success,Native Python base image is ready)

.PHONY: server-rebuild
server-rebuild: server-env-check ## Rebuild base + app images from source and restart the stack
	@$(call warn,This recreates containers: any in-flight Dagster run will be killed)
	@$(call info,Rebuilding the native Python base image (pulling its upstream base))
	# --pull refreshes the upstream image Dockerfile.python-base builds FROM, so
	# a scheduled rebuild picks up base-OS and interpreter security updates
	# rather than rebuilding on top of an increasingly old cached layer.
	$(call run,docker build --pull -f Dockerfile.python-base -t $(SERVER_PYTHON_BASE_IMAGE) .)
	@$(call info,Rebuilding the application images)
	$(call run,$(SERVER_COMPOSE) --profile server build --pull)
	@$(call info,Restarting the stack on the new images)
	$(call run,$(SERVER_COMPOSE) --profile server up -d --wait --wait-timeout 300)
	$(call run,$(SERVER_COMPOSE) --profile server ps)
	@$(call success,Server stack rebuilt. Run 'docker image prune' to reclaim superseded layers)

.PHONY: server-up
server-up: server-base-image ## Preflight and start the always-on server stack (profile=server)
	@$(call info,Starting server stack (profile: server))
	$(call run,$(SERVER_COMPOSE) --profile server up -d --build --wait --wait-timeout 300)
	$(call run,$(SERVER_COMPOSE) --profile server ps)
	@$(call success,Server stack ready (localhost-only; expose via 'make server-tailscale-up'))

.PHONY: server-down
server-down: server-env-check ## Stop the server stack (PRESERVES volumes/data)
	@$(call info,Stopping server stack (data volumes preserved))
	$(call run,$(SERVER_COMPOSE) --profile server down --remove-orphans)
	@$(call success,Server stack stopped; volumes and bind-mounted data preserved)

.PHONY: server-status
server-status: server-env-check ## Show server stack status
	@$(call info,Server stack status)
	$(call run,$(SERVER_COMPOSE) --profile server ps)

.PHONY: server-health
server-health: server-env-check ## Run health checks (env, deps, Neo4j) inside the running stack
	@$(call info,Checking server stack health)
	$(call run,$(SERVER_COMPOSE) --profile server ps)
	$(call run,$(SERVER_COMPOSE) --profile server exec -T dagster-code-server python /app/scripts/e2e_health_check.py --profile server)

.PHONY: server-logs
server-logs: server-env-check ## Tail server logs for SERVICE (default dagster-webserver)
	@$(call info,Tailing server logs for service: $(SERVICE))
	@$(SERVER_COMPOSE) --profile server logs -f --tail=200 $(SERVICE)

.PHONY: server-backup
server-backup: server-env-check ## Dump Neo4j to $(SERVER_BACKUP_DIR) (default ./backups)
	@$(call info,Backing up Neo4j)
	$(call run,SERVER_ENV_FILE=$(SERVER_ENV_FILE) COMPOSE_FILE=$(SERVER_COMPOSE_FILE) ./scripts/server/backup.sh)

.PHONY: server-tailscale-up
server-tailscale-up: server-env-check ## Configure persistent Tailscale Serve routes
	@$(call info,Configuring Tailscale Serve routes)
	$(call run,SERVER_ENV_FILE=$(SERVER_ENV_FILE) ./scripts/server/tailscale-serve.sh up)

.PHONY: server-tailscale-status
server-tailscale-status: ## Show Tailscale Serve configuration
	@$(call info,Tailscale Serve status)
	$(call run,./scripts/server/tailscale-serve.sh status)

.PHONY: server-tailscale-down
server-tailscale-down: server-env-check ## Remove ONLY the managed SBIR Tailscale Serve routes
	@$(call info,Removing SBIR Tailscale Serve routes)
	$(call run,SERVER_ENV_FILE=$(SERVER_ENV_FILE) ./scripts/server/tailscale-serve.sh down)

.PHONY: server-validate-config
server-validate-config: server-env-check ## Validate docker-compose.server.yml
	@$(call info,Validating $(SERVER_COMPOSE_FILE))
	@set -euo pipefail; \
	 if ! $(SERVER_COMPOSE) --profile server config >/dev/null 2>&1; then \
	   $(call failure,$(SERVER_COMPOSE_FILE) validation failed); \
	   $(SERVER_COMPOSE) --profile server config; \
	   exit 1; \
	 fi; \
	 $(call success,$(SERVER_COMPOSE_FILE) is valid)

.PHONY: ci-local
ci-local: ## Run CI checks locally (mimics GitHub Actions)
	@$(call info,Running CI checks locally)
	@set -euo pipefail; \
	 $(MAKE) validate; \
	 $(call info,Running secret scan); \
	 if command -v python3 >/dev/null 2>&1; then \
	   python3 scripts/ci/scan_secrets.py || exit_code=$$?; \
	   if [ "$${exit_code:-0}" != "0" ]; then \
	     $(call failure,Secret scan failed); \
	     exit $$exit_code; \
	   fi; \
	 else \
	   $(call warn,Python3 not found, skipping secret scan); \
	 fi; \
	 $(call success,CI checks completed)
