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
error = if [ "$(QUIET)" != "1" ]; then printf "$(RED)✖$(RESET) %s\n" "$(1)"; fi
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
	   $(call error,Neo4j is not accessible); \
	   $(call warn,Check logs with: make docker-logs SERVICE=neo4j); \
	   exit 1; \
	 fi; \
	 $(call info,Checking Dagster UI...); \
	 if curl -fsS --max-time 3 http://localhost:3000/server_info >/dev/null 2>&1; then \
	   $(call success,Dagster UI is accessible at http://localhost:3000); \
	 else \
	   $(call error,Dagster UI is not accessible); \
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
install: ## Install dependencies with uv
	@$(call info,Installing dependencies)
	$(call run,uv sync)

.PHONY: test
test: ## Run all tests
	@$(call info,Running tests)
	$(call run,uv run pytest -v --cov=src)

.PHONY: lint
lint: ## Run linting and type checking
	@$(call info,Running linting and type checking)
	$(call run,uv run ruff check .)
	$(call run,uv run mypy src/)

.PHONY: format
format: ## Format code
	@$(call info,Formatting code)
	$(call run,uv run black .)
	$(call run,uv run ruff check --fix .)

.PHONY: dev
dev: ## Run Dagster dev server locally
	@$(call info,Starting Dagster dev server)
	$(call run,uv run dagster dev -m src.definitions)

.PHONY: install-ml
install-ml: ## Install ML dependencies (jupyter, matplotlib, etc.)
	@$(call info,Installing ML dependencies)
	$(call run,uv sync --extra ml)

.PHONY: notebook
notebook: install-ml ## Start Jupyter Lab for ML analysis
	@$(call info,Starting Jupyter Lab)
	@mkdir -p notebooks
	$(call run,uv run --extra ml jupyter lab --notebook-dir=notebooks)

.PHONY: setup-local
setup-local: env-check ## Configure environment for local development (no cloud)
	@$(call info,Configuring local environment)
	@if ! grep -q "SBIR_ETL__EXTRACTION__SBIR__USE_S3_FIRST" .env; then \
		echo "SBIR_ETL__EXTRACTION__SBIR__USE_S3_FIRST=false" >> .env; \
		echo "SBIR_ETL__EXTRACTION__SAM_GOV__USE_S3_FIRST=false" >> .env; \
		$(call success,Added local configuration to .env); \
	else \
		$(call warn,Local configuration already present in .env); \
	fi

.PHONY: setup-cloud
setup-cloud: env-check ## Configure environment for cloud development
	@$(call info,Configuring cloud environment)
	@$(call info,This will enable S3 usage. Ensure you have AWS credentials configured.)
	@if ! grep -q "SBIR_ETL__EXTRACTION__SBIR__USE_S3_FIRST" .env; then \
		echo "SBIR_ETL__EXTRACTION__SBIR__USE_S3_FIRST=true" >> .env; \
		echo "SBIR_ETL__EXTRACTION__SAM_GOV__USE_S3_FIRST=true" >> .env; \
		$(call success,Added cloud configuration to .env); \
	else \
		sed -i '' 's/SBIR_ETL__EXTRACTION__SBIR__USE_S3_FIRST=false/SBIR_ETL__EXTRACTION__SBIR__USE_S3_FIRST=true/g' .env; \
		sed -i '' 's/SBIR_ETL__EXTRACTION__SAM_GOV__USE_S3_FIRST=false/SBIR_ETL__EXTRACTION__SAM_GOV__USE_S3_FIRST=true/g' .env; \
		$(call success,Updated .env to use S3); \
	fi

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
	   $(call error,Tests failed (exit $$STATUS)); \
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
	   $(call error,E2E tests failed with exit code $$STATUS); \
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
	   $(call error,Neo4j health check failed); \
	  exit 1; \
	 fi

# -----------------------------------------------------------------------------
# Transition MVP
# -----------------------------------------------------------------------------

.PHONY: transition-mvp-run
transition-mvp-run: ## Run the Transition MVP pipeline locally (no Dagster required)
	@$(call info,Running Transition MVP pipeline)
	$(call run,uv run sbir-cli transition mvp)
	@$(call success,Transition MVP pipeline completed)

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

## docker-logs SERVICE=name: Tail logs (default SERVICE=dagster-webserver)
## docker-exec SERVICE=name CMD="sh -lc 'command'": Execute a command inside a container
## docker-rebuild: Stop everything, rebuild the image, and restart the dev stack
## docker-check / docker-check-install: Docker diagnostics
## docker-e2e-* targets: Convenience wrappers around docker-e2e

.PHONY: logs-all
logs-all: ## Show logs from all running containers
	@$(call info,Showing logs from all containers)
	$(call run,$(COMPOSE) logs -f)

.PHONY: ps
ps: ## Show running containers
	@$(call info,Listing running containers)
	$(call run,$(COMPOSE) ps)

.PHONY: clean-all
clean-all: ## Clean all artifacts, containers, and volumes
	@$(call info,Cleaning all Docker artifacts)
	@set -euo pipefail; \
	 $(call run,$(COMPOSE) down --remove-orphans --volumes); \
	 $(call run,docker system prune -f --volumes || true); \
	 $(call success,All artifacts cleaned)

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
	   $(call error,docker-compose.yml validation failed); \
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

.PHONY: ci-local
ci-local: ## Run CI checks locally (mimics GitHub Actions)
	@$(call info,Running CI checks locally)
	@set -euo pipefail; \
	 $(MAKE) validate; \
	 $(call info,Running secret scan); \
	 if command -v python3 >/dev/null 2>&1; then \
	   python3 scripts/ci/scan_secrets.py || exit_code=$$?; \
	   if [ "$${exit_code:-0}" != "0" ]; then \
	     $(call error,Secret scan failed); \
	     exit $$exit_code; \
	   fi; \
	 else \
	   $(call warn,Python3 not found, skipping secret scan); \
	 fi; \
	 $(call success,CI checks completed)

.PHONY: docker-build docker-buildx docker-push docker-up-dev docker-up-tools docker-down docker-rebuild docker-test \
	docker-e2e docker-e2e-clean docker-e2e-minimal docker-e2e-standard \
	docker-e2e-large docker-e2e-edge-cases docker-e2e-debug docker-logs \
	docker-exec env-check docker-check docker-check-install docker-check-prerequisites docker-verify neo4j-up \
	neo4j-down neo4j-reset neo4j-check transition-mvp-run transition-mvp-clean \
	logs-all ps clean-all shell db-shell validate-config validate ci-local
