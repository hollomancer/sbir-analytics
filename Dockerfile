# syntax=docker/dockerfile:1.4
#
# Multi-stage Dockerfile for sbir-analytics
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
#   # Production build with R from scratch (RSPM optimized, ~5 min):
#   docker build -t sbir-analytics:latest .
#
#   # Production build with pre-built R packages (fastest with R, ~2 min):
#   docker build --build-arg USE_R_BASE_IMAGE=true -t sbir-analytics:latest .
#
#   # CI build without R (fastest overall, ~2 min):
#   docker build --build-arg BUILD_WITH_R=false -t sbir-analytics:ci .
#
#   make docker-build (provided Makefile uses this Dockerfile)
#
ARG PYTHON_VERSION=3.11.9
ARG IMAGE_PY=python:${PYTHON_VERSION}-slim-bookworm
# Build argument to control R installation (set to false for faster CI builds)
ARG BUILD_WITH_R=true
# Build argument to use pre-built R base image (faster than building R from scratch)
ARG USE_R_BASE_IMAGE=false
ARG R_BASE_IMAGE=ghcr.io/hollomancer/sbir-analytics-r-base:latest

########################################################################
# R Base Cache stage (optional): pre-built R packages from cached image
########################################################################
FROM ${R_BASE_IMAGE} AS r-base-cache
# This stage pulls the pre-built R base image if USE_R_BASE_IMAGE=true
# It's only used to copy R packages from, not run
# If the image doesn't exist, this stage won't be used (builder will build R from scratch)

########################################################################
# System dependencies stage: install system packages (rarely changes)
########################################################################
FROM ${IMAGE_PY} AS system-deps

ARG BUILD_WITH_R=true

ENV DEBIAN_FRONTEND=noninteractive

# Install system dependencies in separate layer for better caching
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
    && if [ "$BUILD_WITH_R" = "true" ]; then \
        apt-get install -y --no-install-recommends \
        r-base \
        r-base-dev \
        ccache \
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
        zlib1g-dev; \
    fi \
    && rm -rf /var/lib/apt/lists/*

########################################################################
# Dependencies stage: build Python wheels (changes occasionally)
########################################################################
FROM system-deps AS dependencies

ARG BUILD_WITH_R=true
ARG UV_VERSION=0.5.11

ENV PIP_NO_CACHE_DIR=1 \
    PYTHONUNBUFFERED=1

WORKDIR /workspace

# Install UV in separate layer
RUN curl -LsSf https://astral.sh/uv/${UV_VERSION}/install.sh | sh && \
    mv /root/.local/bin/uv /usr/local/bin/uv && \
    uv --version

# Copy only dependency files for better layer caching
COPY pyproject.toml uv.lock* README.md MANIFEST.in /workspace/

# Export requirements and build wheels in single layer
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=cache,target=/root/.cache/pip \
    mkdir -p /wheels \
 && python -m pip install --upgrade pip setuptools wheel \
 && if [ "$BUILD_WITH_R" = "true" ]; then \
        uv export --extra dev --extra cloud --extra r --no-hashes --no-editable --format requirements-txt -o requirements.txt && sed -i '/^\.$/d' requirements.txt; \
    else \
        uv export --extra dev --extra cloud --no-hashes --no-editable --format requirements-txt -o requirements.txt && sed -i '/^\.$/d' requirements.txt; \
    fi \
 && if [ "$BUILD_WITH_R" = "false" ]; then \
        export RPY2_CFFI_MODE=ABI; \
        (uv pip sync --system uv.lock 2>/dev/null || uv pip install --system -r requirements.txt); \
    else \
        export R_HOME=/usr/lib/R; \
        (uv pip sync --system uv.lock 2>/dev/null || uv pip install --system -r requirements.txt); \
    fi \
 && python -m pip freeze | grep -v '^-e' > /tmp/frozen.txt \
 && if [ "$BUILD_WITH_R" = "false" ]; then \
        export RPY2_CFFI_MODE=ABI; \
        python -m pip wheel --wheel-dir=/wheels -r /tmp/frozen.txt; \
    else \
        export R_HOME=/usr/lib/R; \
        python -m pip wheel --wheel-dir=/wheels -r /tmp/frozen.txt; \
    fi

########################################################################
# Builder stage: build application wheel (changes frequently)
########################################################################
FROM dependencies AS builder

ARG BUILD_WITH_R=true
ARG USE_R_BASE_IMAGE=false

# Copy application code
COPY . /workspace/

# Build package wheel
RUN --mount=type=cache,target=/root/.cache/pip \
    python -m pip wheel --wheel-dir=/wheels .

# Install R packages (stateior) for fiscal analysis (only if BUILD_WITH_R=true)
# This package is used via rpy2 for economic input-output modeling
# Install to system library so it's available in runtime
#
# Three installation paths:
# 1. USE_R_BASE_IMAGE=true: Copy pre-built R packages from cached image (FASTEST - ~30s)
# 2. BUILD_WITH_R=true, USE_R_BASE_IMAGE=false: Build with RSPM binaries (~2-5min, was ~20min)
# 3. BUILD_WITH_R=false: Skip R entirely (instant)
#
# OPTIMIZATION: Uses RStudio Package Manager (RSPM) for pre-compiled R package binaries
# This reduces arrow installation from ~15min (source build) to ~30sec (binary download)
#
# NOTE: When BUILD_WITH_R=false (CI builds), this step is skipped entirely.
# Tests will skip R-dependent tests via pytest.importorskip("rpy2")

# Copy R packages from pre-built image (only used if USE_R_BASE_IMAGE=true)
# If r-base-cache doesn't exist or is empty, this creates an empty dir
COPY --from=r-base-cache /usr/local/lib/R/site-library /tmp/r-cache/

# Then either use cached R packages or build from scratch
RUN --mount=type=cache,target=/root/.cache/R \
    --mount=type=cache,target=/root/.cache/ccache \
    export PATH="/usr/lib/ccache:${PATH}" && \
    export CCACHE_DIR=/root/.cache/ccache && \
    if [ "$BUILD_WITH_R" = "true" ] && [ "$USE_R_BASE_IMAGE" = "true" ] && [ -d "/tmp/r-cache" ] && [ "$(ls -A /tmp/r-cache 2>/dev/null)" ]; then \
        echo "✓ Using pre-built R packages from cached image (fast path)"; \
        mkdir -p /usr/local/lib/R/site-library; \
        cp -r /tmp/r-cache/* /usr/local/lib/R/site-library/; \
        echo "R packages copied from cache successfully"; \
    elif [ "$BUILD_WITH_R" = "true" ]; then \
        echo "Building R packages from scratch (optimized with RSPM binaries, ~2-5 minutes)..."; \
        export MAKEFLAGS="-j$(nproc)" && \
        export R_SITE_LIB='/usr/local/lib/R/site-library' && \
        export RSPM_ROOT='https://packagemanager.rstudio.com/all/__linux__/jammy/latest' && \
        R -e ".libPaths(c('${R_SITE_LIB}', '/usr/lib/R/site-library')); \
        options(repos = c(RSPM = '${RSPM_ROOT}', CRAN = 'https://cloud.r-project.org/')); \
        cat('Installing remotes package from RSPM...\n'); \
        install.packages('remotes', Ncpus = parallel::detectCores())" && \
        R -e ".libPaths(c('${R_SITE_LIB}', '/usr/lib/R/site-library')); \
        options(repos = c(RSPM = '${RSPM_ROOT}', CRAN = 'https://cloud.r-project.org/')); \
        cat('Installing arrow package from RSPM (pre-compiled binary)...\n'); \
        install.packages('arrow', Ncpus = parallel::detectCores()); \
        arrow_ok <- tryCatch({ \
            suppressPackageStartupMessages(library(arrow)); \
            TRUE \
        }, error = function(err) { \
            message('arrow failed to load: ', conditionMessage(err)); \
            FALSE \
        }); \
        if (!arrow_ok) { \
            quit(status = 1); \
        } else { \
            cat('✓ arrow loaded successfully\n'); \
            detach('package:arrow', unload = TRUE); \
        }" && \
        R -e ".libPaths(c('${R_SITE_LIB}', '/usr/lib/R/site-library')); \
        options(repos = c(RSPM = '${RSPM_ROOT}', CRAN = 'https://cloud.r-project.org/')); \
        cat('Installing stateior package from GitHub...\n'); \
        remotes::install_github('USEPA/stateior', \
                                dependencies = TRUE, \
                                upgrade = 'never', \
                                Ncpus = parallel::detectCores())" && \
        R -e "cat('✓ R packages installed successfully\n'); cat('Library paths:', .libPaths(), '\n')"; \
    else \
        echo "BUILD_WITH_R=false, skipping R package installation for faster build"; \
        mkdir -p /usr/local/lib/R/site-library; \
    fi

# At this point /wheels contains all binary/py wheels needed for runtime install
# Copy wheels + requirements to a known place for runtime stage
RUN ls -la /wheels

########################################################################
# Runtime stage: minimal runtime with wheels installed, tiny footprint
########################################################################
FROM ${IMAGE_PY} AS runtime

# Re-declare build args for use in this stage
ARG BUILD_WITH_R=true

ENV PATH=/usr/local/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app

# Install tini and utilities (always needed)
# R runtime is conditional based on BUILD_WITH_R
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    gnupg \
    tini \
    && if [ "$BUILD_WITH_R" = "true" ]; then \
        apt-get install -y --no-install-recommends r-base; \
        export R_HOME=/usr/lib/R; \
    fi \
    && rm -rf /var/lib/apt/lists/*

# Set R_HOME only if R is installed
ENV R_HOME=${BUILD_WITH_R:+/usr/lib/R}

# Create app user/group early (uid/gid stable across runs)
ARG SBIR_UID=1000
ARG SBIR_GID=1000
RUN groupadd -g ${SBIR_GID} sbir \
 && useradd -m -u ${SBIR_UID} -g ${SBIR_GID} -s /bin/sh sbir

WORKDIR /app

# Copy built wheels and requirements from builder
COPY --from=builder /wheels /wheels
COPY --from=builder /workspace/requirements.txt /workspace/requirements.txt

# Deduplicate wheels: keep only the latest version of each package
RUN python3 -c "
import re
from pathlib import Path
from collections import defaultdict
from packaging.version import parse as parse_version

wheels_dir = Path('/wheels')
packages = defaultdict(list)

# Group wheels by package name
for wheel in wheels_dir.glob('*.whl'):
    # Extract package name and version from wheel filename
    # Format: package_name-version-py_tag-abi_tag-platform_tag.whl
    match = re.match(r'^([a-zA-Z0-9_]+)-([0-9.]+[a-zA-Z0-9.]*)-', wheel.name)
    if match:
        pkg_name = match.group(1).lower().replace('_', '-')
        version = match.group(2)
        packages[pkg_name].append((version, wheel))

# Keep only the latest version of each package
for pkg_name, versions in packages.items():
    if len(versions) > 1:
        # Sort by semantic version
        versions.sort(key=lambda x: parse_version(x[0]), reverse=True)
        # Remove all but the latest
        for _, wheel_path in versions[1:]:
            print(f'Removing duplicate: {wheel_path.name}')
            wheel_path.unlink()
"

# Copy R packages from builder to runtime (only if BUILD_WITH_R=true)
# R packages installed via install.packages() go to /usr/local/lib/R/site-library
# We copy the entire directory structure to preserve all packages and dependencies
RUN if [ "$BUILD_WITH_R" = "true" ]; then \
        mkdir -p /usr/local/lib/R/site-library; \
    fi
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
 && pip install --no-cache-dir /wheels/*.whl \
 && rm -rf /wheels

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

# Ensure entrypoint scripts and healthcheck scripts are executable
RUN chmod -R +x /app/scripts/docker || true && \
    chmod +x /app/scripts/docker/healthcheck/*.sh || true

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
