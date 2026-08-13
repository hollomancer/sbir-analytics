# syntax=docker/dockerfile:1.7
#
# SBIR Analytics production image
#
# The application environment is synchronized against the committed uv.lock.
# `uv sync --locked` rejects manifest drift and never updates the lock during a
# build. The pinned uv bootstrap and isolated package build tools sit outside
# that application lock contract.

ARG PYTHON_IMAGE=python:3.11.9-slim-bookworm@sha256:8fb099199b9f2d70342674bd9dbccd3ed03a258f26bbd1d556822c6dfc60c317

FROM ${PYTHON_IMAGE} AS runtime-base

ARG UV_VERSION=0.11.2

ENV DEBIAN_FRONTEND=noninteractive \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

# Runtime scripts and health checks use curl and netcat. uv itself is pinned by
# version here; the application environment is installed from uv.lock below.
RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        gosu \
        netcat-openbsd \
    && rm -rf /var/lib/apt/lists/* \
    && python -m pip install "uv==${UV_VERSION}" \
    && groupadd --system sbir \
    && useradd --system --gid sbir --home-dir /app --no-create-home --shell /bin/sh sbir

# Install locked dependencies before copying source. Workspace metadata is
# enough for uv to select the `server` extra, while `--no-install-workspace`
# keeps first-party packages out of this environment. Source-only changes
# therefore reuse this layer and the Chromium layer below.
COPY pyproject.toml uv.lock README.md ./
COPY packages/sbir-analytics/pyproject.toml packages/sbir-analytics/README.md ./packages/sbir-analytics/
COPY packages/sbir-graph/pyproject.toml ./packages/sbir-graph/
COPY packages/sbir-ml/pyproject.toml packages/sbir-ml/README.md ./packages/sbir-ml/

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --extra server --no-editable \
        --no-install-project --no-install-workspace

# Browser automation is a locked Python dependency; this step installs only its
# matching Chromium binary and OS libraries.
RUN playwright install --with-deps chromium \
    && chmod -R a+rX /opt/pw-browsers \
    && rm -rf /var/lib/apt/lists/*

# Copy the complete workspace and install its first-party packages as ordinary
# wheels. PYTHONPATH intentionally keeps the historical repo-root `sbir_etl`
# import behavior; the three packages below resolve from the installed wheels
# unless the development Compose profile explicitly mounts live source paths.
COPY sbir_etl/ ./sbir_etl/
COPY packages/ ./packages/

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --extra server --no-editable

COPY scripts/ ./scripts/
COPY config/ ./config/
COPY specs/phase-iii-census/ ./specs/phase-iii-census/
COPY specs/phase3-notice-corpus-fusion/ ./specs/phase3-notice-corpus-fusion/
COPY studies/phase-iii-census/ ./studies/phase-iii-census/
COPY workspace.server.yaml ./workspace.server.yaml
COPY data/reference/ ./data/reference/

RUN mkdir -p data logs reports artifacts dagster_home \
    && chown -R sbir:sbir /app

# Compose's CI profile adds test dependencies at image-build time. It never
# mutates the environment when the test container starts.
FROM runtime-base AS test

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --extra server --extra dev --no-editable

CMD ["pytest", "-m", "fast", "-q"]

FROM runtime-base AS runtime

CMD ["dagster", "job", "list", "-m", "sbir_analytics.definitions"]
