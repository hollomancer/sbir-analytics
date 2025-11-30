#!/usr/bin/env bash
# Shared utility to generate markdown tables for GitHub Actions
# This script provides consistent table formatting across all reporting

set -e

# Usage: format-summary-table.sh [options] <row1> <row2> ...
#
# Options:
#   --title <title>              Section title
#   --headers <header1,header2>  Table headers (comma-separated)
#   --section-level <level>      Header level: 1-4 (default: 2)
#
# Row format: Each row should be pipe-separated values
# Example:
#   ./format-summary-table.sh \
#     --title "Download Summary" \
#     --headers "Dataset,Status,Size" \
#     "SBIR|success|150 MB" \
#     "USPTO|failed|0 MB"
#
# Advanced usage with JSON parsing:
#   You can also pipe JSON data:
#   echo '{"dataset":"SBIR","status":"success","size":"150 MB"}' | \
#     ./format-summary-table.sh --title "Download Summary" --headers "Dataset,Status,Size" --from-json

# Default values
SECTION_LEVEL=2
TITLE=""
HEADERS=""
FROM_JSON=false
ROWS=()

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --title)
            TITLE="$2"
            shift 2
            ;;
        --headers)
            HEADERS="$2"
            shift 2
            ;;
        --section-level)
            SECTION_LEVEL="$2"
            shift 2
            ;;
        --from-json)
            FROM_JSON=true
            shift
            ;;
        *)
            # Assume it's a row
            ROWS+=("$1")
            shift
            ;;
    esac
done

# Validate headers
if [ -z "$HEADERS" ]; then
    echo "Error: --headers is required" >&2
    exit 1
fi

# Generate header markdown prefix
HEADER_PREFIX=""
for ((i=1; i<=SECTION_LEVEL; i++)); do
    HEADER_PREFIX="${HEADER_PREFIX}#"
done

# Display title if provided
if [ -n "$TITLE" ]; then
    echo "${HEADER_PREFIX} ${TITLE}" >> $GITHUB_STEP_SUMMARY
    echo "" >> $GITHUB_STEP_SUMMARY
fi

# Convert comma-separated headers to pipe-separated
IFS=',' read -ra HEADER_ARRAY <<< "$HEADERS"
HEADER_ROW="| "
SEPARATOR_ROW="| "

for header in "${HEADER_ARRAY[@]}"; do
    HEADER_ROW="${HEADER_ROW}${header} | "
    SEPARATOR_ROW="${SEPARATOR_ROW}-------- | "
done

# Output table header
echo "$HEADER_ROW" >> $GITHUB_STEP_SUMMARY
echo "$SEPARATOR_ROW" >> $GITHUB_STEP_SUMMARY

# Output rows
for row in "${ROWS[@]}"; do
    # Convert pipe-separated row to markdown table format
    IFS='|' read -ra ROW_ARRAY <<< "$row"
    ROW_TEXT="| "
    for cell in "${ROW_ARRAY[@]}"; do
        ROW_TEXT="${ROW_TEXT}${cell} | "
    done
    echo "$ROW_TEXT" >> $GITHUB_STEP_SUMMARY
done

echo "" >> $GITHUB_STEP_SUMMARY
