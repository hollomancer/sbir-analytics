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

IMAGE_NAME        ?= sbir-etl:latest
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

.PHONY: docker-up-prod
docker-up-prod: env-check ## Start the production stack (profile=prod)
	@$(call info,Starting production stack (profile: prod))
	$(call run,$(COMPOSE) --profile prod up -d --build)
	$(call run,$(COMPOSE) --profile prod ps)

.PHONY: docker-up-cet-staging
docker-up-cet-staging: env-check ## Start CET staging stack (profile=cet-staging)
	@$(call info,Starting CET staging stack (profile: cet-staging))
	$(call run,$(COMPOSE) --profile cet-staging up -d --build)
	$(call run,$(COMPOSE) --profile cet-staging ps)

.PHONY: docker-up-tools
docker-up-tools: env-check ## Start the tools profile (debug helpers)
	@$(call info,Starting tools container (profile: tools))
	$(call run,$(COMPOSE) --profile tools up -d --build)
	$(call run,$(COMPOSE) --profile tools ps)

.PHONY: docker-down
docker-down: ## Stop all services and remove volumes
	@set -euo pipefail; \
	 $(call info,Stopping all services and removing volumes); \
	 $(call print-cmd,$(COMPOSE) down --remove-orphans --volumes); \
	 STATUS=0; \
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
docker-test: env-check ## Run containerised CI tests (profile=ci-test)
	@set -euo pipefail; \
	 $(call info,Running containerised tests (profile: ci-test)); \
	 $(call print-cmd,$(COMPOSE) --profile ci-test up --abort-on-container-exit --build); \
	 STATUS=0; \
	 if ! $(COMPOSE) --profile ci-test up --abort-on-container-exit --build; then STATUS=$$?; fi; \
	 $(call print-cmd,$(COMPOSE) --profile ci-test down --remove-orphans --volumes); \
	 $(COMPOSE) --profile ci-test down --remove-orphans --volumes || true; \
	 if [ $$STATUS -eq 0 ]; then \
	   $(call success,Tests passed); \
	 else \
	   $(call error,Tests failed (exit $$STATUS)); \
	   $(call warn,View logs with: make docker-logs SERVICE=test-runner); \
	 fi; \
	 exit $$STATUS

.PHONY: docker-e2e
docker-e2e: env-check ## Run full end-to-end test suite (profile=e2e)
	@set -euo pipefail; \
	 $(call info,Running E2E tests (profile: e2e)); \
	 $(call print-cmd,$(COMPOSE) --profile e2e up --build --abort-on-container-exit neo4j-e2e e2e-orchestrator); \
	 STATUS=0; \
	 if ! $(COMPOSE) --profile e2e up --build --abort-on-container-exit neo4j-e2e e2e-orchestrator 2>&1; then STATUS=$$?; fi; \
	 if [ "$(QUIET)" != "1" ]; then printf "$(BLUE)➤$(RESET) E2E tests completed with exit code %s\n" "$$STATUS"; fi; \
	 if [ $$STATUS -ne 0 ]; then \
	   $(call error,E2E tests failed with exit code $$STATUS); \
	   $(call info,Showing recent logs from failed containers...); \
	   $(COMPOSE) --profile e2e logs --tail=50 e2e-orchestrator 2>&1 || true; \
	   $(COMPOSE) --profile e2e logs --tail=20 neo4j-e2e 2>&1 || true; \
	 else \
	   $(call success,E2E tests passed – containers left running for inspection); \
	 fi; \
	 $(call warn,Use 'make docker-logs SERVICE=e2e-orchestrator' to view orchestrator logs); \
	 $(call warn,Use 'make docker-e2e-clean' to tear down when finished); \
	 exit $$STATUS

.PHONY: docker-e2e-clean
docker-e2e-clean: ## Tear down the E2E environment
	@set -euo pipefail; \
	 if [ "$(QUIET)" != "1" ]; then printf "$(BLUE)➤$(RESET) Cleaning up E2E test environment\n"; fi; \
	 printf "$(GRAY)$ %s$(RESET)\n" "$(COMPOSE) --profile e2e down --remove-orphans --volumes"; \
	 STATUS=0; \
	 if ! $(COMPOSE) --profile e2e down --remove-orphans --volumes; then STATUS=$$?; fi; \
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
docker-e2e-debug: env-check ## Open an interactive shell in the E2E orchestrator
	@$(call info,Opening interactive shell in e2e orchestrator)
	$(call run,$(COMPOSE) --profile e2e run --rm e2e-orchestrator sh)

# -----------------------------------------------------------------------------
# Neo4j helpers                                                                   
# -----------------------------------------------------------------------------

.PHONY: neo4j-up
neo4j-up: env-check ## Start the standalone Neo4j profile
	$(call info,Starting standalone Neo4j (profile: neo4j-standalone))
	$(call run,$(COMPOSE) --profile neo4j-standalone up -d --build)

.PHONY: neo4j-down
neo4j-down: ## Stop the standalone Neo4j profile
	$(call info,Stopping Neo4j (profile: neo4j-standalone))
	$(call run,$(COMPOSE) --profile neo4j-standalone down --remove-orphans --volumes)

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
	 if $(COMPOSE) --profile neo4j-standalone exec neo4j \
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
	$(call run,poetry run python scripts/transition/transition_mvp_run.py)
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

.PHONY: docker-build docker-buildx docker-push docker-up-dev docker-up-prod \
	docker-up-cet-staging docker-up-tools docker-down docker-rebuild docker-test \
	docker-e2e docker-e2e-clean docker-e2e-minimal docker-e2e-standard \
	docker-e2e-large docker-e2e-edge-cases docker-e2e-debug docker-logs \
	docker-exec env-check docker-check docker-check-install neo4j-up \
	neo4j-down neo4j-reset neo4j-check transition-mvp-run transition-mvp-clean
