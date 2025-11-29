#!/usr/bin/env bash
# Remove deprecated GitHub Actions workflows
# These workflows have been consolidated into other workflows

set -euo pipefail

WORKFLOWS_DIR=".github/workflows"

echo "🧹 Removing deprecated GitHub Actions workflows..."

# List of deprecated workflows to remove
DEPRECATED_WORKFLOWS=(
    "docker-cache.yml"
    "static-analysis.yml"
    "usaspending-database-download.yml"
    "uspto-data-refresh.yml"
    "weekly-award-data-refresh.yml"
)

for workflow in "${DEPRECATED_WORKFLOWS[@]}"; do
    filepath="${WORKFLOWS_DIR}/${workflow}"
    if [ -f "$filepath" ]; then
        echo "  ❌ Removing: $workflow"
        rm "$filepath"
    else
        echo "  ⚠️  Not found: $workflow (already removed?)"
    fi
done

echo ""
echo "✅ Cleanup complete!"
echo ""
echo "Remaining workflows:"
ls -1 "${WORKFLOWS_DIR}"/*.yml | xargs -n1 basename
