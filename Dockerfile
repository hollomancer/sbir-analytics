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
RUN pip install \
    "boto3>=1.34.0,<2.0.0" \
    "cloudpathlib[s3]>=0.23.0,<1.0.0" \
    "rapidfuzz>=3.0.0,<4.0.0" \
    "jellyfish>=1.0.0,<2.0.0" \
    "httpx>=0.27.0,<1.0.0" \
    "tenacity>=8.2.3,<10.0.0" \
    "typer>=0.12.0,<1.0.0" \
    "rich>=13.7.0,<15.0.0"

# Copy application code
COPY sbir_etl/ /app/sbir_etl/
COPY packages/sbir-analytics/sbir_analytics/ /app/sbir_analytics/
COPY packages/sbir-graph/sbir_graph/ /app/sbir_graph/
COPY packages/sbir-ml/sbir_ml/ /app/sbir_ml/
COPY packages/sbir-rag/sbir_rag/ /app/sbir_rag/
COPY scripts/ /app/scripts/
COPY config/ /app/config/
COPY migrations/ /app/migrations/
COPY pyproject.toml /app/

ENV PYTHONPATH=/app

# Create directories
RUN mkdir -p /app/data /app/logs /app/reports

CMD ["dagster", "job", "list", "-m", "sbir_analytics.definitions"]
