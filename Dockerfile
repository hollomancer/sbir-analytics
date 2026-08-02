# syntax=docker/dockerfile:1.4
#
# SBIR Analytics ETL Image
# Lightweight image for ETL pipelines (no R, no ML)
#
# Used by: GitHub Actions ETL, local development
#
ARG BASE_IMAGE=ghcr.io/hollomancer/sbir-analytics-python-base:latest

FROM ${BASE_IMAGE} AS runtime

# Install ETL-specific dependencies
# boto3/cloudpathlib intentionally absent: the AWS data plane is retired
# (docs/deployment/aws-decommission-plan.md).
RUN pip install \
    "rapidfuzz>=3.0.0,<4.0.0" \
    "jellyfish>=1.0.0,<2.0.0" \
    "httpx>=0.27.0,<1.0.0" \
    "tenacity>=8.2.3,<10.0.0" \
    "fastapi>=0.115.0,<1.0.0" \
    "uvicorn>=0.30.0,<1.0.0" \
    "playwright>=1.47.0,<2.0.0"

# USPTO patent assignments are only reachable through browser automation since
# data.uspto.gov stopped serving them to plain HTTP clients (2026-06-18), so
# uspto_download_job needs a real Chromium on the server image.
ENV PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers
RUN playwright install --with-deps chromium && \
    chmod -R a+rX /opt/pw-browsers

# Copy application code
COPY sbir_etl/ /app/sbir_etl/
COPY packages/sbir-analytics/sbir_analytics/ /app/sbir_analytics/
COPY packages/sbir-graph/sbir_graph/ /app/sbir_graph/
COPY packages/sbir-ml/sbir_ml/ /app/sbir_ml/
COPY scripts/ /app/scripts/
COPY config/ /app/config/
COPY specs/phase-iii-census/ /app/specs/phase-iii-census/
COPY specs/phase3-notice-corpus-fusion/ /app/specs/phase3-notice-corpus-fusion/
COPY workspace.server.yaml /app/workspace.server.yaml
COPY data/reference/ /app/data/reference/
COPY pyproject.toml /app/

ENV PYTHONPATH=/app

# Create directories
RUN mkdir -p /app/data /app/logs /app/reports

CMD ["dagster", "job", "list", "-m", "sbir_analytics.definitions"]
