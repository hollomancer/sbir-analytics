#!/bin/bash
# Local testing script for Lambda function

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# Test event payload
TEST_EVENT=$(cat <<EOF
{
  "force_refresh": false,
  "source_url": null,
  "s3_bucket": "sbir-etl-production-data",
  "neo4j_secret_name": null
}
EOF
)

log_info() {
    echo "[INFO] $1"
}

log_error() {
    echo "[ERROR] $1"
}

# Check if Docker is running
if ! docker info &> /dev/null; then
    log_error "Docker is not running. Please start Docker first."
    exit 1
fi

log_info "Building Lambda container image..."
cd "${PROJECT_ROOT}"
docker build -f docker/lambda/Dockerfile -t sbir-lambda-test:latest .

log_info "Testing Lambda handler locally..."
docker run --rm \
    -e AWS_ACCESS_KEY_ID="${AWS_ACCESS_KEY_ID:-test}" \
    -e AWS_SECRET_ACCESS_KEY="${AWS_SECRET_ACCESS_KEY:-test}" \
    -e AWS_DEFAULT_REGION="${AWS_DEFAULT_REGION:-us-east-1}" \
    -e S3_BUCKET="${S3_BUCKET:-sbir-etl-production-data}" \
    -v "${HOME}/.aws:/root/.aws:ro" \
    sbir-lambda-test:latest \
    python3 -c "
import json
import sys
sys.path.insert(0, '/var/task')
from src.lambda.weekly_refresh_handler import lambda_handler

event = json.loads('''${TEST_EVENT}''')
try:
    result = lambda_handler(event, None)
    print(json.dumps(result, indent=2))
except Exception as e:
    print(f'Error: {e}', file=sys.stderr)
    sys.exit(1)
"

log_info "Local test completed"

