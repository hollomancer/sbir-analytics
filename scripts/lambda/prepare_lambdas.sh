#!/bin/bash
# Prepare Lambda functions by copying common module into each function directory

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Preparing Lambda functions..."

# List of Lambda function directories that need the common module
FUNCTIONS=(
    "download_csv"
    "download_uspto"
    "validate_dataset"
    "profile_inputs"
    "enrichment_checks"
    "reset_neo4j"
    "smoke_checks"
)

# Copy common module into each function directory
for func in "${FUNCTIONS[@]}"; do
    func_dir="${SCRIPT_DIR}/${func}"
    if [ -d "${func_dir}" ]; then
        echo "  Copying common module to ${func}..."
        rm -rf "${func_dir}/common"
        cp -r "${SCRIPT_DIR}/common" "${func_dir}/"
    else
        echo "  WARNING: Function directory not found: ${func_dir}"
    fi
done

echo "Lambda functions prepared successfully"
