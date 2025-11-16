#!/bin/bash
# Build Lambda layer for Python dependencies

set -e

LAYER_DIR="lambda/layers/python-dependencies"
OUTPUT_DIR="/tmp/lambda-layer"
PYTHON_VERSION="3.11"

echo "Building Lambda layer for Python dependencies..."

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
echo "  --layer-name sbir-etl-python-dependencies \\"
echo "  --zip-file fileb:///tmp/python-dependencies-layer.zip \\"
echo "  --compatible-runtimes python${PYTHON_VERSION}"

