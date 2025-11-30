# syntax=docker/dockerfile:1.4
#
# Multi-stage Dockerfile for sbir-analytics
#
# Usage:
#   # Standard build (no R):
#   docker build -t sbir-analytics:latest .
#
#   # Build with R support (uses pre-built r-base image):
#   docker build --build-arg BASE_IMAGE=ghcr.io/hollomancer/sbir-analytics-r-base:latest \
#                --build-arg WITH_R=true -t sbir-analytics:r .
#
ARG PYTHON_VERSION=3.11.9
ARG BASE_IMAGE=python:${PYTHON_VERSION}-slim-bookworm
ARG WITH_R=false

########################################################################
# Python dependencies stage: build wheels
########################################################################
FROM python:${PYTHON_VERSION}-slim-bookworm AS python-deps

ARG UV_VERSION=0.5.11
ARG WITH_R=false

ENV PIP_NO_CACHE_DIR=1 \
    PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive

WORKDIR /workspace

# Install build dependencies
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
    && rm -rf /var/lib/apt/lists/*

# Install UV
RUN curl -LsSf https://astral.sh/uv/${UV_VERSION}/install.sh | sh && \
    mv /root/.local/bin/uv /usr/local/bin/uv

# Copy dependency files
COPY pyproject.toml uv.lock* README.md MANIFEST.in /workspace/

# Build wheels
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=cache,target=/root/.cache/pip \
    mkdir -p /wheels \
    && python -m pip install --upgrade pip setuptools wheel \
    && if [ "$WITH_R" = "true" ]; then \
        uv export --extra dev --extra cloud --extra r --no-hashes --no-editable --format requirements-txt -o requirements.txt; \
    else \
        uv export --extra dev --extra cloud --no-hashes --no-editable --format requirements-txt -o requirements.txt; \
    fi \
    && sed -i '/^\.$/d' requirements.txt \
    && RPY2_CFFI_MODE=ABI python -m pip wheel --wheel-dir=/wheels -r requirements.txt

########################################################################
# Builder stage: build application wheel
########################################################################
FROM python-deps AS builder

COPY . /workspace/

RUN --mount=type=cache,target=/root/.cache/pip \
    python -m pip wheel --wheel-dir=/wheels .

########################################################################
# Runtime stage
########################################################################
FROM ${BASE_IMAGE} AS runtime

ARG WITH_R=false
ARG SBIR_UID=1000
ARG SBIR_GID=1000

ENV PATH=/usr/local/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app

# Install runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    tini \
    && rm -rf /var/lib/apt/lists/*

# Set R_HOME if R is available
ENV R_HOME=${WITH_R:+/usr/lib/R}

# Create app user
RUN groupadd -g ${SBIR_GID} sbir \
 && useradd -m -u ${SBIR_UID} -g ${SBIR_GID} -s /bin/sh sbir

WORKDIR /app

# Copy and deduplicate wheels
COPY --from=builder /wheels /wheels
COPY scripts/docker/dedupe_wheels.py /tmp/dedupe_wheels.py
RUN python3 /tmp/dedupe_wheels.py && rm /tmp/dedupe_wheels.py

# Install wheels
RUN pip install --upgrade pip setuptools wheel \
 && pip install --no-cache-dir /wheels/*.whl \
 && rm -rf /wheels

# Install gosu
ARG GOSU_VERSION=1.14
RUN ARCH="$(dpkg --print-architecture)" && \
    curl -fsSL -o /usr/local/bin/gosu "https://github.com/tianon/gosu/releases/download/${GOSU_VERSION}/gosu-${ARCH}" && \
    chmod +x /usr/local/bin/gosu

# Copy application
COPY . /app
RUN mkdir -p /app/logs /app/data /app/reports /app/config /app/metrics \
 && chmod -R +x /app/scripts/docker 2>/dev/null || true \
 && chown -R sbir:sbir /app

EXPOSE 3000

ENTRYPOINT ["/usr/bin/tini", "--", "/app/scripts/docker/entrypoint.sh"]
CMD ["dagster-webserver"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
  CMD python -c "import src" || exit 1

USER sbir
