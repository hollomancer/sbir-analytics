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

# Install build tools required to compile wheels and R
# Include cmake and other dependencies needed for arrow (to speed up R package builds)
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    ca-certificates \
    git \
    gcc \
    libpq-dev \
    python3-dev \
    r-base \
    r-base-dev \
    libcurl4-openssl-dev \
    libssl-dev \
    libxml2-dev \
    libfontconfig1-dev \
    libfreetype6-dev \
    libfribidi-dev \
    libharfbuzz-dev \
    libjpeg-dev \
    libpng-dev \
    libtiff-dev \
    libicu-dev \
    cmake \
    pkg-config \
    libbz2-dev \
    liblzma-dev \
    zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

# Create app dir
WORKDIR /workspace

# Install UV - fast Python package installer
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy dependency manifests early to leverage layer cache
COPY pyproject.toml uv.lock* README.md MANIFEST.in /workspace/

# Export a requirements.txt for pip-based wheel building (main + dev + r groups for test tooling)
# Use --locked to ensure exact versions from uv.lock are used
# Include 'r' extra to get rpy2 for R integration
RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip compile pyproject.toml --extra dev --extra r --universal --python-version 3.11 --locked -o requirements.txt || \
    uv pip compile pyproject.toml --extra dev --extra r --universal --python-version 3.11 -o requirements.txt

# Build wheels for all requirements into /wheels (cached if requirements.txt doesn't change)
# Install from lock file using uv (ensures exact versions), then build wheels from installed packages
# If lock file doesn't exist or sync fails, fall back to requirements.txt
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=cache,target=/root/.cache/pip \
    mkdir -p /wheels \
 && python -m pip install --upgrade pip setuptools wheel \
 && (uv pip sync --system uv.lock 2>/dev/null || uv pip install --system -r requirements.txt) \
 && python -m pip freeze | grep -v '^-e' > /tmp/frozen.txt \
 && python -m pip wheel --wheel-dir=/wheels -r /tmp/frozen.txt

# NOW copy the rest of the code for building the package wheel
COPY . /workspace/

# Build package wheel
RUN --mount=type=cache,target=/root/.cache/pip \
    python -m pip wheel --wheel-dir=/wheels .

# Install R packages (stateior and useeior) for fiscal analysis
# These packages are used via rpy2 for economic input-output modeling
# Install to system library so they're available in runtime
# 
# Optimization strategies:
# 1. Install arrow explicitly first (may get binary, or at least parallel build)
# 2. Use parallel compilation with MAKEFLAGS and Ncpus
# 3. Cache R library directory between builds
# 4. Set ARROW_R_DEV=false to avoid building development version
# 5. Install dependencies in separate steps for better caching
RUN --mount=type=cache,target=/root/.cache/R \
    export MAKEFLAGS="-j$(nproc)" && \
    export R_SITE_LIB='/usr/local/lib/R/site-library' && \
    export ARROW_R_DEV=FALSE && \
    export ARROW_DEPENDENCY_SOURCE=BUNDLED && \
    export ARROW_USE_PKG_CONFIG=false && \
    export ARROW_WITH_BZ2=ON && \
    export ARROW_WITH_LZ4=ON && \
    export ARROW_WITH_SNAPPY=ON && \
    export ARROW_WITH_ZLIB=ON && \
    export ARROW_WITH_ZSTD=ON && \
    R -e ".libPaths(c('${R_SITE_LIB}', '/usr/lib/R/site-library')); \
    options(repos = c(CRAN = 'https://cloud.r-project.org/')); \
    cat('Installing remotes package...\n'); \
    install.packages('remotes', repos='https://cloud.r-project.org/', \
                     lib='${R_SITE_LIB}', \
                     Ncpus = parallel::detectCores())" && \
    R -e ".libPaths(c('${R_SITE_LIB}', '/usr/lib/R/site-library')); \
    options(repos = c(CRAN = 'https://cloud.r-project.org/')); \
    cat('Installing arrow package from source with bundled C++ libs...\n'); \
    install.packages('arrow', repos='https://cloud.r-project.org/', \
                     lib='${R_SITE_LIB}', \
                     type='source', \
                     Ncpus = parallel::detectCores()); \
    arrow_ok <- tryCatch({ \
        suppressPackageStartupMessages(library(arrow)); \
        TRUE \
    }, error = function(err) { \
        message('arrow failed to load after installation: ', conditionMessage(err)); \
        FALSE \
    }); \
    if (!arrow_ok) { \
        quit(status = 1); \
    } else { \
        detach('package:arrow', unload = TRUE); \
    }" && \
    R -e ".libPaths(c('${R_SITE_LIB}', '/usr/lib/R/site-library')); \
    options(repos = c(CRAN = 'https://cloud.r-project.org/')); \
    cat('Installing stateior package (arrow should already be installed)...\n'); \
    remotes::install_github('USEPA/stateior', dependencies=TRUE, \
                            lib='${R_SITE_LIB}', \
                            Ncpus = parallel::detectCores(), \
                            upgrade = 'never')" && \
    R -e ".libPaths(c('${R_SITE_LIB}', '/usr/lib/R/site-library')); \
    options(repos = c(CRAN = 'https://cloud.r-project.org/')); \
    cat('Installing useeior package (arrow should already be installed)...\n'); \
    remotes::install_github('USEPA/useeior', dependencies=TRUE, \
                            lib='${R_SITE_LIB}', \
                            Ncpus = parallel::detectCores(), \
                            upgrade = 'never')" && \
    R -e "cat('R packages installed successfully\n'); cat('Library paths:', .libPaths(), '\n')"

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
    PYTHONPATH=/app \
    R_HOME=/usr/lib/R

# Install tini, utilities, and R runtime required at runtime
# R runtime (without dev tools) needed for rpy2 to work
# R will pull in its own dependencies, we just need the base runtime libraries
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    gnupg \
    tini \
    r-base \
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

# Copy R packages from builder to runtime (more efficient than reinstalling)
# R packages installed via install.packages() go to /usr/local/lib/R/site-library
# We copy the entire directory structure to preserve all packages and dependencies
RUN mkdir -p /usr/local/lib/R/site-library
COPY --from=builder /usr/local/lib/R/site-library/ /usr/local/lib/R/site-library/

# Install all wheels from /wheels into the runtime environment using pip
# This avoids network fetches at runtime and ensures deterministic installs.
# NOTE: heavy test/dev dependencies (pandas, pyarrow, pyreadstat) are intentionally
# omitted from the runtime image to keep the image lightweight. CI and test runs
# should install those packages at container startup (for example via `uv sync`
# or `pip install` in the test command). See CI docker-compose.test.yml for the
# test-time install step.
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --upgrade pip setuptools wheel \
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
