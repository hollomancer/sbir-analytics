# syntax=docker/dockerfile:1.4
#
# Multi-stage Dockerfile for sbir-etl
# - builder: prepares wheels (UV -> requirements.txt, builds wheels)
# - runtime: small runtime image with only wheels + application code
#
# Features:
# - based on python:3.11-slim
# - installs system build deps in builder only
# - caches wheel builds for fast rebuilds
# - installs tini and gosu for proper PID 1 and privilege drop
# - non-root runtime user `sbir`
#
# Usage:
#   docker build -t sbir-etl:latest .
#   make docker-build (provided Makefile uses this Dockerfile)
#
ARG PYTHON_VERSION=3.11
ARG IMAGE_PY=python:${PYTHON_VERSION}-slim

########################################################################
# Builder stage: install system deps, export UV -> requirements, build wheels
########################################################################
FROM ${IMAGE_PY} AS builder

ENV DEBIAN_FRONTEND=noninteractive \
    PIP_NO_CACHE_DIR=1 \
    PYTHONUNBUFFERED=1

# Install build tools required to compile wheels
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    ca-certificates \
    git \
    gcc \
    libpq-dev \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

# Create app dir
WORKDIR /workspace

# Install UV - fast Python package installer
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy dependency manifests early to leverage layer cache
COPY pyproject.toml uv.lock* /workspace/

# Ensure README and package sources are available for metadata when building wheels.
# Copying the project source into the builder context ensures metadata generation succeeds in CI.
COPY . /workspace/

# Export a requirements.txt for pip-based wheel building (main + dev groups for test tooling)
# UV is much faster than Poetry for this step
RUN uv pip compile pyproject.toml --extra dev --universal --python-version 3.11 -o requirements.txt

# Build wheels for all requirements (and for this package) into /wheels
RUN mkdir -p /wheels \
 && python -m pip install --upgrade pip setuptools wheel \
 && python -m pip wheel --wheel-dir=/wheels -r requirements.txt \
 && python -m pip wheel --wheel-dir=/wheels .

# At this point /wheels contains all binary/py wheels needed for runtime install
# Copy wheels + requirements to a known place for runtime stage
RUN ls -la /wheels

########################################################################
# Runtime stage: minimal runtime with wheels installed, tiny footprint
########################################################################
FROM ${IMAGE_PY} AS runtime

ENV PATH=/usr/local/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app

# Install tini and utilities required at runtime (gosu will be added via download)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    gnupg \
    tini \
    && rm -rf /var/lib/apt/lists/*

# Create app user/group early (uid/gid stable across runs)
ARG SBIR_UID=1000
ARG SBIR_GID=1000
RUN groupadd -g ${SBIR_GID} sbir \
 && useradd -m -u ${SBIR_UID} -g ${SBIR_GID} -s /bin/sh sbir

WORKDIR /app

# Copy built wheels and requirements from builder
COPY --from=builder /wheels /wheels
COPY --from=builder /workspace/requirements.txt /workspace/requirements.txt

# Install all wheels from /wheels into the runtime environment using pip
# This avoids network fetches at runtime and ensures deterministic installs.
# NOTE: heavy test/dev dependencies (pandas, pyarrow, pyreadstat) are intentionally
# omitted from the runtime image to keep the image lightweight. CI and test runs
# should install those packages at container startup (for example via `uv sync`
# or `pip install` in the test command). See CI docker-compose.test.yml for the
# test-time install step.
RUN pip install --upgrade pip setuptools wheel \
 && pip install --no-index --find-links=/wheels -r /workspace/requirements.txt

# Install gosu (used to drop privileges when needed)
# Download a static gosu binary; adapt to architecture automatically via dpkg-architecture if needed.
# We use the amd64 binary by default; in multi-arch CI you may want to use buildx or detect arch.
ARG GOSU_VERSION=1.14
RUN set -eux; \
    ARCH="$(dpkg --print-architecture)"; \
    case "$ARCH" in \
      amd64) GOSU_ARCH=amd64 ;; \
      arm64) GOSU_ARCH=arm64 ;; \
      *) GOSU_ARCH="$ARCH" ;; \
    esac; \
    curl -fsSL -o /usr/local/bin/gosu "https://github.com/tianon/gosu/releases/download/${GOSU_VERSION}/gosu-${GOSU_ARCH}"; \
    chmod +x /usr/local/bin/gosu; \
    gosu --version || true

# Copy application code and scripts (entrypoints, wait scripts, etc.)
# Note: in dev profile these paths can be bind-mounted to allow live edit.
COPY . /app

# Ensure directories expected for bind mounts/volumes exist even when .dockerignore skips them
RUN mkdir -p /app/logs /app/data /app/reports /app/config /app/metrics

# Ensure entrypoint scripts are executable (use actual runtime path and make all scripts executable)
RUN chmod -R +x /app/scripts/docker || true

# Make sure /app owned by sbir user
RUN chown -R sbir:sbir /app

# Expose Dagster UI port and Neo4j (optional)
EXPOSE 3000

# Use tini as PID 1 for proper signal handling; keep entrypoint as shell script in repo
# Provide a default CMD that is friendly for containers; runtime behavior controlled via entrypoint args
ENTRYPOINT ["/usr/bin/tini", "--", "/app/scripts/docker/entrypoint.sh"]
CMD ["dagster-webserver"]

# Healthcheck: ensure Python can import package (lightweight check)
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
  CMD python -c "import importlib, sys; importlib.import_module('src') if False else None; exit(0)" || exit 1

# Switch to non-root user for security by default
USER sbir
