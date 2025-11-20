#!/bin/bash
# Build Lambda layer for Python dependencies

set -e

# Get script directory and project root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
LAYER_DIR="${PROJECT_ROOT}/lambda/layers/python-dependencies"
OUTPUT_DIR="/tmp/lambda-layer"
PYTHON_VERSION="3.11"

echo "Building Lambda layer for Python dependencies..."

# Verify requirements file exists
if [ ! -f "${LAYER_DIR}/requirements.txt" ]; then
    echo "ERROR: Requirements file not found at: ${LAYER_DIR}/requirements.txt"
    exit 1
fi

# Create output directory structure
mkdir -p "${OUTPUT_DIR}/python/lib/python${PYTHON_VERSION}/site-packages"

# Install dependencies to the layer directory
pip install -r "${LAYER_DIR}/requirements.txt" -t "${OUTPUT_DIR}/python/lib/python${PYTHON_VERSION}/site-packages"

# Create zip file
cd "${OUTPUT_DIR}"
zip -r /tmp/python-dependencies-layer.zip python/

echo "Layer built: /tmp/python-dependencies-layer.zip"
echo ""
echo "To upload to AWS:"
echo "aws lambda publish-layer-version \\"
echo "  --layer-name sbir-analytics-python-dependencies \\"
echo "  --zip-file fileb:///tmp/python-dependencies-layer.zip \\"
echo "  --compatible-runtimes python${PYTHON_VERSION}"

