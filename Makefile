# Makefile - Consolidated Container build / dev / test helpers for sbir-etl
#
# This Makefile has been updated to use the consolidated Docker Compose configuration
# with profile-based service management, eliminating duplication and standardizing patterns.
#
# Usage:
#   make help
#   make docker-check        # Check if Docker is running
#   make docker-build
#   make docker-up-dev
#   make docker-up-prod
#   make docker-up-cet-staging
#   make docker-down
#   make docker-test
#   make docker-e2e
#   make docker-logs SERVICE=app
#   make docker-exec SERVICE=app CMD="sh"
#
# Override defaults with environment variables, for example:
#   make docker-build IMAGE_NAME=myregistry/myimage:tag
#
# Enable verbose output:
#   make docker-test VERBOSE=1

SHELL := /bin/sh

# Configurable variables (can be overridden on the make command line)
IMAGE_NAME ?= sbir-etl:latest
DOCKER_REGISTRY ?=
DOCKER_TAG ?= latest
BUILD_CONTEXT ?= .
DOCKERFILE ?= Dockerfile

# Consolidated compose file with profile-based configuration
COMPOSE_FILE ?= docker-compose.yml

# Compose command (supports 'docker compose' or 'docker-compose' depending on environment)
DOCKER_COMPOSE ?= docker compose

# Default service to tail logs or exec into
SERVICE ?= dagster-webserver

# Number of seconds to wait for containers to be healthy before reporting
STARTUP_TIMEOUT ?= 120

# Verbosity control - set VERBOSE=1 to see detailed command output
VERBOSE ?= 0
ifeq ($(VERBOSE),1)
    VERBOSE_FLAG :=
    VERBOSE_ECHO := @echo
else
    VERBOSE_FLAG := @
    VERBOSE_ECHO := @
endif

.PHONY: help docker-build docker-buildx docker-up-dev docker-up-prod docker-up-cet-staging docker-down docker-rebuild docker-test docker-e2e docker-logs docker-exec docker-push env-check

help:
	@printf "\nMakefile targets for consolidated container workflow\n\n"
	@printf "Build Targets:\n"
	@printf "  make docker-build         Build image locally (multi-stage Dockerfile)\n"
	@printf "  make docker-buildx        Build with buildx (multi-platform support)\n\n"
	@printf "Environment Targets:\n"
	@printf "  make docker-up-dev        Start development stack (profile: dev)\n"
	@printf "  make docker-up-prod       Start production stack (profile: prod)\n"
	@printf "  make docker-up-cet-staging Start CET staging stack (profile: cet-staging)\n"
	@printf "  make docker-up-tools      Start tools container (profile: tools)\n"
	@printf "  make docker-check         Check if Docker is running\n"
	@printf "  make docker-down          Stop all services and remove volumes\n"
	@printf "  make docker-rebuild       Rebuild images and restart dev stack\n\n"
	@printf "Testing Targets:\n"
	@printf "  make docker-test          Run containerized tests (profile: ci-test)\n"
	@printf "  make docker-e2e           Run E2E tests (profile: e2e)\n"
	@printf "  make docker-e2e-minimal   Run minimal E2E tests (fastest)\n"
	@printf "  make docker-e2e-standard  Run standard E2E tests\n"
	@printf "  make docker-e2e-large     Run large dataset E2E tests\n"
	@printf "  make docker-e2e-clean     Clean up E2E test environment\n"
	@printf "  make docker-test VERBOSE=1 Enable verbose command output\n\n"
	@printf "Pipeline Targets:\n"
	@printf "  make cet-pipeline-dev     Run CET pipeline on dev stack\n"
	@printf "  make transition-mvp-run   Run Transition Detection MVP locally\n"
	@printf "  make transition-mvp-clean Clean Transition MVP artifacts\n\n"
	@printf "Utility Targets:\n"
	@printf "  make docker-logs          Tail logs for service (SERVICE=%s)\n" "$(SERVICE)"
	@printf "  make docker-exec          Exec into running container (SERVICE=%s)\n" "$(SERVICE)"
	@printf "  make docker-push          Tag and push image to registry\n"
	@printf "  make env-check            Verify .env exists and configuration\n\n"
	@printf "Neo4j Targets:\n"
	@printf "  make neo4j-up             Start standalone Neo4j (profile: neo4j-standalone)\n"
	@printf "  make neo4j-down           Stop Neo4j and remove volumes\n"
	@printf "  make neo4j-reset          Reset Neo4j with fresh volumes\n"
	@printf "  make neo4j-check          Check Neo4j health\n\n"
	@printf "Validation Targets:\n"
	@printf "  make validate-compose     Validate consolidated compose configuration\n\n"

# ---------------------------
# Build targets
# ---------------------------

docker-build:
	@echo "🔨 Building Docker image: $(IMAGE_NAME)"
	$(VERBOSE_FLAG)DOCKER_BUILDKIT=1 docker build -t $(IMAGE_NAME) -f $(DOCKERFILE) $(BUILD_CONTEXT)

docker-buildx:
	@echo "🔨 Building Docker image with buildx (multi-platform)"
	$(VERBOSE_FLAG)docker buildx build --load -t $(IMAGE_NAME) -f $(DOCKERFILE) $(BUILD_CONTEXT)

# ---------------------------
# Environment targets (profile-based)
# ---------------------------

docker-up-dev: env-check
	@echo "🚀 Starting development stack (profile: dev)"
	$(VERBOSE_FLAG)$(DOCKER_COMPOSE) --profile dev -f $(COMPOSE_FILE) up -d --build
	@echo "⏳ Waiting up to $(STARTUP_TIMEOUT)s for services to become healthy..."
	$(VERBOSE_FLAG)$(DOCKER_COMPOSE) --profile dev -f $(COMPOSE_FILE) ps

docker-up-prod: env-check
	@echo "🚀 Starting production stack (profile: prod)"
	$(VERBOSE_FLAG)$(DOCKER_COMPOSE) --profile prod -f $(COMPOSE_FILE) up -d --build
	$(VERBOSE_FLAG)$(DOCKER_COMPOSE) --profile prod -f $(COMPOSE_FILE) ps

docker-up-cet-staging: env-check
	@echo "🚀 Starting CET staging stack (profile: cet-staging)"
	$(VERBOSE_FLAG)$(DOCKER_COMPOSE) --profile cet-staging -f $(COMPOSE_FILE) up -d --build
	$(VERBOSE_FLAG)$(DOCKER_COMPOSE) --profile cet-staging -f $(COMPOSE_FILE) ps

docker-up-tools: env-check
	@echo "🚀 Starting tools container (profile: tools)"
	$(VERBOSE_FLAG)$(DOCKER_COMPOSE) --profile tools -f $(COMPOSE_FILE) up -d --build
	$(VERBOSE_FLAG)$(DOCKER_COMPOSE) --profile tools -f $(COMPOSE_FILE) ps

docker-down:
	@echo "🛑 Stopping all services and removing volumes"
	$(VERBOSE_FLAG)$(DOCKER_COMPOSE) -f $(COMPOSE_FILE) down --remove-orphans --volumes; \
	status=$$?; \
	if [ $$status -eq 0 ]; then \
		echo "✅ Services stopped and cleaned up successfully"; \
	else \
		echo "⚠️  Service cleanup completed with warnings (exit code: $$status)"; \
		echo "💡 This may be normal if no services were running"; \
	fi

docker-check:
	@echo "🔍 Checking Docker availability..."
	@if command -v docker >/dev/null 2>&1; then \
		if docker info >/dev/null 2>&1; then \
			echo "✅ Docker is running and accessible"; \
			docker --version; \
			docker compose version; \
		else \
			echo "❌ Docker daemon is not running"; \
			echo "💡 Start Docker Desktop or run: open -a Docker"; \
			exit 1; \
		fi \
	else \
		echo "❌ Docker is not installed"; \
		exit 1; \
	fi

docker-rebuild: docker-down docker-build docker-up-dev
	@echo "🔄 Rebuilt and restarted dev stack"

# ---------------------------
# Pipeline execution targets
# ---------------------------

cet-pipeline-dev: env-check docker-up-dev
	@echo "🔬 Running CET full pipeline job on development stack"
	@$(DOCKER_COMPOSE) --profile dev -f $(COMPOSE_FILE) run --rm etl-runner-dev -- \
		poetry run dagster job execute -f src/definitions.py -j cet_full_pipeline_job

# ---------------------------
# Testing targets (profile-based)
# ---------------------------

docker-test: env-check
	@echo "🧪 Running containerized tests (profile: ci-test)"
	@echo "📦 Building and starting test containers..."
	$(VERBOSE_FLAG)$(DOCKER_COMPOSE) --profile ci-test -f $(COMPOSE_FILE) up --abort-on-container-exit --build; \
	status=$$?; \
	echo "🧹 Tearing down test containers..."; \
	$(VERBOSE_FLAG)$(DOCKER_COMPOSE) --profile ci-test -f $(COMPOSE_FILE) down --remove-orphans --volumes; \
	if [ $$status -eq 0 ]; then \
		echo "✅ Tests passed!"; \
	else \
		echo "❌ Tests failed with exit code $$status"; \
		echo "💡 Check logs with: make docker-logs SERVICE=test-runner"; \
	fi; \
	exit $$status

docker-e2e: env-check
	@echo "🧪 Running E2E tests (profile: e2e)"
	@echo "🏗️  Building and starting E2E environment..."
	$(VERBOSE_FLAG)$(DOCKER_COMPOSE) --profile e2e -f $(COMPOSE_FILE) up --build --abort-on-container-exit; \
	status=$$?; \
	echo "📊 E2E tests completed with exit code: $$status"; \
	if [ $$status -eq 0 ]; then \
		echo "✅ E2E tests passed!"; \
		echo "🔍 Containers kept running for artifact inspection"; \
	else \
		echo "❌ E2E tests failed"; \
	fi; \
	echo "💡 Use 'make docker-logs SERVICE=e2e-orchestrator' to view logs"; \
	echo "💡 Use 'make docker-e2e-clean' to clean up when done"; \
	exit $$status

docker-e2e-clean:
	@echo "🧹 Cleaning up E2E test environment and volumes"
	$(VERBOSE_FLAG)$(DOCKER_COMPOSE) --profile e2e -f $(COMPOSE_FILE) down --remove-orphans --volumes; \
	status=$$?; \
	if [ $$status -eq 0 ]; then \
		echo "✅ E2E environment cleaned up successfully"; \
	else \
		echo "⚠️  E2E cleanup completed with warnings (exit code: $$status)"; \
		echo "💡 This may be normal if no E2E containers were running"; \
	fi

# E2E test scenarios with different configurations
docker-e2e-minimal: env-check
	@echo "🧪 Running minimal E2E tests (fastest)"
	@E2E_TEST_SCENARIO=minimal $(MAKE) docker-e2e

docker-e2e-standard: env-check
	@echo "🧪 Running standard E2E tests"
	@E2E_TEST_SCENARIO=standard $(MAKE) docker-e2e

docker-e2e-large: env-check
	@echo "🧪 Running large dataset E2E tests"
	@E2E_TEST_SCENARIO=large $(MAKE) docker-e2e

docker-e2e-edge-cases: env-check
	@echo "🧪 Running edge case E2E tests"
	@E2E_TEST_SCENARIO=edge-cases $(MAKE) docker-e2e

# Interactive E2E debugging
docker-e2e-debug: env-check
	@echo "🔍 Starting E2E environment for interactive debugging"
	@$(DOCKER_COMPOSE) --profile e2e -f $(COMPOSE_FILE) run --rm e2e-orchestrator sh

# ---------------------------
# Neo4j targets (profile-based)
# ---------------------------

neo4j-up: env-check
	@echo "🗄️  Starting standalone Neo4j (profile: neo4j-standalone)"
	@$(DOCKER_COMPOSE) --profile neo4j-standalone -f $(COMPOSE_FILE) up -d --build
	@echo "⏳ Neo4j starting (give it a few seconds to become healthy)"

neo4j-down:
	@echo "🛑 Stopping Neo4j"
	@$(DOCKER_COMPOSE) --profile neo4j-standalone -f $(COMPOSE_FILE) down --remove-orphans --volumes

neo4j-reset: neo4j-down
	@echo "🔄 Resetting Neo4j with fresh volumes"
	-@docker volume rm neo4j_data neo4j_logs neo4j_import 2>/dev/null || true
	@echo "🗄️  Starting fresh Neo4j..."
	@$(MAKE) neo4j-up

neo4j-check: env-check
	@echo "🔍 Running Neo4j health check"
	@$(DOCKER_COMPOSE) --profile neo4j-standalone -f $(COMPOSE_FILE) exec neo4j \
		cypher-shell -u $${NEO4J_USER:-neo4j} -p $${NEO4J_PASSWORD:-password} 'RETURN 1' >/dev/null 2>&1 \
		&& echo "✅ Neo4j is healthy" || echo "❌ Neo4j health check failed"

neo4j-backup:
	@echo "💾 Running Neo4j backup"
	@mkdir -p $${BACKUP_DIR:-backups/neo4j} || true
	@BACKUP_DIR=$${BACKUP_DIR:-backups/neo4j} DB_NAME=$${DB_NAME:-neo4j} $${SHELL} scripts/neo4j/backup.sh

neo4j-restore:
	@if [ -z "$${BACKUP_PATH:-}" ]; then \
	  echo "❌ Please provide BACKUP_PATH=/path/to/dump to restore"; exit 2; \
	fi
	@echo "📥 Restoring Neo4j from $${BACKUP_PATH}"
	@$${SHELL} scripts/neo4j/restore.sh --backup-path "$${BACKUP_PATH}"

# ---------------------------
# Logs / exec helpers
# ---------------------------

docker-logs:
	@echo "📋 Tailing logs for service: $(SERVICE)"
	@$(DOCKER_COMPOSE) -f $(COMPOSE_FILE) logs -f --tail=200 $(SERVICE)

docker-exec:
	@CMD=$${CMD:-sh}; \
	echo "🔧 Executing in service $(SERVICE): $$CMD"; \
	$(DOCKER_COMPOSE) -f $(COMPOSE_FILE) exec $(SERVICE) sh -c "$$CMD"

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
	echo "🏷️  Tagging image $(IMAGE_NAME) -> $$TARGET"; \
	docker tag $(IMAGE_NAME) $$TARGET; \
	echo "📤 Pushing $$TARGET"; \
	docker push $$TARGET

# ---------------------------
# Transition MVP (local runner)
# ---------------------------

transition-mvp-run:
	@echo "🔬 Running Transition Detection MVP locally..."
	@mkdir -p data/processed reports/validation
	@poetry run python scripts/transition/transition_mvp_run.py

transition-mvp-clean:
	@echo "🧹 Cleaning Transition MVP artifacts..."
	-@rm -f data/processed/vendor_resolution.parquet data/processed/vendor_resolution.ndjson data/processed/vendor_resolution.checks.json
	-@rm -f data/processed/transitions.parquet data/processed/transitions.ndjson data/processed/transitions.checks.json
	-@rm -f data/processed/transitions_evidence.ndjson
	-@rm -f data/processed/contracts_sample.parquet data/processed/contracts_sample.csv data/processed/contracts_sample.checks.json
	-@rm -f reports/validation/transition_mvp.json

# Transition MVP gated helpers
transition-mvp-run-gated:
	@$(MAKE) transition-mvp-run
	@poetry run python scripts/transition_mvp_gate.py --check-only
	@echo "✅ Transition MVP gated run succeeded"

transition-audit-export:
	@echo "📊 Exporting precision audit sample CSV..."
	@mkdir -p reports/validation
	@poetry run python scripts/transition/transition_precision_audit.py --export-csv reports/validation/vendor_resolution_audit_sample.csv

transition-audit-import:
	@if [ -z "$${CSV}" ]; then echo "❌ Provide CSV=path/to/labeled.csv"; exit 2; fi
	@THRESHOLD=$${THRESHOLD:-0.80}; \
	poetry run python scripts/transition/transition_precision_audit.py --import-csv "$$CSV" --threshold "$$THRESHOLD"

# ---------------------------
# Migration and validation targets
# ---------------------------

migrate-compose:
	@echo "🔄 Migrating Docker Compose configuration to consolidated format"
	@python scripts/docker/migrate_compose_configs.py --validate --test-profiles --migrate

validate-compose:
	@echo "✅ Validating consolidated Docker Compose configuration"
	@python scripts/docker/migrate_compose_configs.py --validate --test-profiles

# ---------------------------
# Environment / safety checks
# ---------------------------

env-check:
	@if [ ! -f .env ]; then \
	  echo "❌ .env file not found. Copy .env.example to .env and set required values"; \
	  echo "   💡 cp .env.example .env"; \
	  exit 1; \
	else \
	  echo "✅ .env found"; \
	fi

# ---------------------------
# Benchmarks
# ---------------------------

benchmark-transition-detection:
	@echo "📊 Running transition detection benchmark..."
	@poetry run python scripts/performance/benchmark_transition_detection.py --save-as-baseline

# ---------------------------
# Profile information and help
# ---------------------------

show-profiles:
	@echo "📋 Available Docker Compose profiles:"
	@echo "   dev              Development environment with bind mounts and live reload"
	@echo "   prod             Production environment with named volumes"
	@echo "   cet-staging      CET staging environment with artifacts and bind mounts"
	@echo "   ci-test          CI testing environment with ephemeral containers"
	@echo "   e2e              E2E testing environment optimized for MacBook Air"
	@echo "   e2e-full         E2E testing with additional DuckDB service"
	@echo "   neo4j-standalone Standalone Neo4j database for debugging"
	@echo "   tools            Lightweight tools container for debugging"
	@echo ""
	@echo "💡 Usage examples:"
	@echo "   docker compose --profile dev up --build"
	@echo "   docker compose --profile prod up --build"
	@echo "   docker compose --profile cet-staging up --build"
	@echo "   docker compose --profile ci-test up --build"
	@echo "   docker compose --profile e2e up --build"
	@echo ""
	@echo "🔧 Set COMPOSE_PROFILES in .env to automatically activate profiles"

# ---------------------------
# Convenience aliases and phony targets
# ---------------------------

.PHONY: help docker-build docker-buildx docker-up-dev docker-up-prod docker-up-cet-staging docker-up-tools docker-check docker-down docker-rebuild docker-test docker-e2e docker-e2e-clean docker-e2e-minimal docker-e2e-standard docker-e2e-large docker-e2e-edge-cases docker-e2e-debug docker-logs docker-exec docker-push env-check cet-pipeline-dev transition-mvp-run transition-mvp-clean transition-mvp-run-gated transition-audit-export transition-audit-import neo4j-up neo4j-down neo4j-reset neo4j-check neo4j-backup neo4j-restore migrate-compose validate-compose benchmark-transition-detection show-profiles

# Note: This Makefile uses the consolidated Docker Compose configuration
# with profile-based service management. Key features:
# - All environments use --profile flags with a single docker-compose.yml
# - Eliminated duplicate compose file variables and fragmentation
# - Standardized service names across all profiles
# - Added validation targets for compose configuration
# - Improved help documentation with profile information
# - Maintained backward compatibility for all existing make targets
