#!/usr/bin/env bash
# Standardize GitHub Actions versions across all workflows

set -euo pipefail

WORKFLOWS_DIR=".github/workflows"

echo "🔧 Standardizing GitHub Actions versions..."

cd "$WORKFLOWS_DIR"

# Update checkout to v6
echo "  ✓ Updating actions/checkout to @v6"
sed -i '' 's/actions\/checkout@v4/actions\/checkout@v6/g' *.yml

# Update upload-artifact to v5
echo "  ✓ Updating actions/upload-artifact to @v5"
sed -i '' 's/actions\/upload-artifact@v4/actions\/upload-artifact@v5/g' *.yml

# Update download-artifact to v6
echo "  ✓ Updating actions/download-artifact to @v6"
sed -i '' 's/actions\/download-artifact@v4/actions\/download-artifact@v6/g' *.yml

# Update setup-python to v6
echo "  ✓ Updating actions/setup-python to @v6"
sed -i '' 's/actions\/setup-python@v5/actions\/setup-python@v6/g' *.yml

# Update setup-node to v6
echo "  ✓ Updating actions/setup-node to @v6"
sed -i '' 's/actions\/setup-node@v4/actions\/setup-node@v6/g' *.yml

# Update github-script to v8
echo "  ✓ Updating actions/github-script to @v8"
sed -i '' 's/actions\/github-script@v7/actions\/github-script@v8/g' *.yml

cd ../..

echo ""
echo "✅ Action versions standardized!"
echo ""
echo "Summary of changes:"
git diff --stat .github/workflows/
