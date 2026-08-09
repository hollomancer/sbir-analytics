# syntax=docker/dockerfile:1.7
#
# SBIR Analytics production image
#
# Python dependencies come exclusively from uv.lock. Update the lockfile and
# this image together; `uv sync --frozen` refuses an out-of-date lock.

ARG PYTHON_IMAGE=python:3.11.9-slim-bookworm@sha256:8fb099199b9f2d70342674bd9dbccd3ed03a258f26bbd1d556822c6dfc60c317

FROM ${PYTHON_IMAGE} AS runtime

ARG UV_VERSION=0.11.2

ENV DEBIAN_FRONTEND=noninteractive \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

# Runtime scripts and health checks use curl and netcat. UV itself is pinned;
# every application dependency is resolved from the committed lockfile below.
RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        netcat-openbsd \
    && rm -rf /var/lib/apt/lists/* \
    && python -m pip install "uv==${UV_VERSION}"

# Copy the complete Python workspace before syncing so first-party packages are
# installed as ordinary wheels rather than relying on broad hand-maintained
# `pip install` ranges or PYTHONPATH-only imports.
COPY pyproject.toml uv.lock README.md ./
COPY sbir_etl/ ./sbir_etl/
COPY packages/ ./packages/

RUN uv sync --frozen --no-dev --extra server --no-editable

# Browser automation is a locked Python dependency; this step installs only its
# matching Chromium binary and OS libraries.
RUN playwright install --with-deps chromium \
    && chmod -R a+rX /opt/pw-browsers \
    && rm -rf /var/lib/apt/lists/*

COPY scripts/ ./scripts/
COPY config/ ./config/
COPY specs/phase-iii-census/ ./specs/phase-iii-census/
COPY specs/phase3-notice-corpus-fusion/ ./specs/phase3-notice-corpus-fusion/
COPY studies/phase-iii-census/ ./studies/phase-iii-census/
COPY workspace.server.yaml ./workspace.server.yaml
COPY data/reference/ ./data/reference/

RUN mkdir -p data logs reports artifacts dagster_home

CMD ["dagster", "job", "list", "-m", "sbir_analytics.definitions"]
