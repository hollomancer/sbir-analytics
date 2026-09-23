#!/usr/bin/env bash
# Legacy local validation helper for an SBIR awards refresh.
# The live download is now sbir_awards_download_job on the self-hosted server; this script
# remains useful for an explicit download-and-validation rehearsal in a dev checkout.

set -euo pipefail

# Configuration
DATA_PATH="${DATA_PATH:-data/raw/sbir/award_data.csv}"
METADATA_DIR="${METADATA_DIR:-reports/awards_data_refresh}"
COMPANY_DIR="${COMPANY_DIR:-data/raw/sbir}"
COMPANY_SCHEMA_PATH="${COMPANY_SCHEMA_PATH:-docs/data/sbir_company_columns.json}"
SCHEMA_PATH="${SCHEMA_PATH:-docs/data/sbir_awards_columns.json}"
DEFAULT_SOURCE_URL="https://data.www.sbir.gov/mod_awarddatapublic/award_data.csv"
SOURCE_URL="${SOURCE_URL:-$DEFAULT_SOURCE_URL}"

echo "======================================"
echo "SBIR Awards Refresh Validation - Local Run"
echo "======================================"
echo ""
echo "Configuration:"
echo "  Data source: $SOURCE_URL"
echo "  Data path: $DATA_PATH"
echo "  Metadata dir: $METADATA_DIR"
echo ""

# Step 1: Download SBIR awards CSV
echo "==> Step 1: Downloading SBIR awards CSV..."
mkdir -p "$(dirname "$DATA_PATH")"
curl --retry 5 --retry-delay 5 --fail --location --compressed "$SOURCE_URL" -o "$DATA_PATH"
echo "✓ Downloaded to $DATA_PATH"
echo ""

# Step 2: Validate dataset and emit metadata
echo "==> Step 2: Validating dataset..."
python scripts/data/awards_refresh_validation.py \
  --csv-path "$DATA_PATH" \
  --schema-path "$SCHEMA_PATH" \
  --metadata-dir "$METADATA_DIR" \
  --summary-path "$METADATA_DIR/latest.md" \
  --source-url "$SOURCE_URL"
echo "✓ Validation complete"
echo ""

# Step 3: Profile award and company inputs
echo "==> Step 3: Profiling inputs..."
python scripts/data/profile_sbir_inputs.py \
  --award-csv "$DATA_PATH" \
  --company-dir "$COMPANY_DIR" \
  --company-schema-path "$COMPANY_SCHEMA_PATH" \
  --output-json "$METADATA_DIR/inputs_profile.json" \
  --output-md "$METADATA_DIR/inputs_profile.md"
echo "✓ Profiling complete"
echo ""

# Step 4: Install dependencies (if needed)
if ! command -v uv &> /dev/null; then
    echo "==> Installing UV..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.cargo/bin:$PATH"
fi

echo "==> Step 4: Installing project dependencies..."
uv sync --extra stack-dev
echo "✓ Dependencies installed"
echo ""

# Step 5: Run SBIR ingestion validation
echo "==> Step 5: Running ingestion validation..."
uv run python scripts/data/run_sbir_ingestion_checks.py \
  --csv-path "$DATA_PATH" \
  --duckdb-path "$METADATA_DIR/ingestion.duckdb" \
  --table-name "sbir_awards_refresh" \
  --pass-rate-threshold 0.95 \
  --output-dir "$METADATA_DIR" \
  --report-json "$METADATA_DIR/sbir_validation_report.json" \
  --summary-md "$METADATA_DIR/ingestion_summary.md"
echo "✓ Ingestion validation complete"
echo ""

# Step 6: Run company enrichment coverage
echo "==> Step 6: Running enrichment coverage..."
uv run python scripts/data/run_sbir_enrichment_check.py \
  --awards-csv "$DATA_PATH" \
  --company-dir "$COMPANY_DIR" \
  --output-json "$METADATA_DIR/enrichment_summary.json" \
  --output-md "$METADATA_DIR/enrichment_summary.md"
echo "✓ Enrichment check complete"
echo ""

# Step 7: Run integration tests
echo "==> Step 7: Running integration tests..."
SBIR_E2E_AWARD_CSV="$DATA_PATH" uv run pytest \
  tests/integration/test_sbir_ingestion_assets.py \
  --maxfail=1 --disable-warnings -q
echo "✓ Integration tests passed"
echo ""

echo "======================================"
echo "✅ Workflow complete!"
echo "======================================"
echo ""
echo "Generated artifacts in: $METADATA_DIR"
echo ""
echo "Review:"
echo "  - Validation summary: $METADATA_DIR/latest.md"
echo "  - Input profile: $METADATA_DIR/inputs_profile.md"
echo "  - Ingestion summary: $METADATA_DIR/ingestion_summary.md"
echo "  - Enrichment summary: $METADATA_DIR/enrichment_summary.md"
echo ""
