#!/usr/bin/env bash
# Shared GitHub Actions reporting utility for download status
# This script provides consistent reporting across all download jobs

set -e

# Usage: report-download-status.sh [options]
#
# Options:
#   --title <title>              Section title (e.g., "SBIR Awards Refresh Report")
#   --emoji <emoji>              Emoji for the title (e.g., "🎯")
#   --status <status>            Status: success, failed, skipped, running
#   --json-file <file>           JSON response file to display
#   --json-label <label>         Label for JSON section (default: "Response")
#   --message <message>          Additional message to display
#   --section-level <level>      Header level: 1-4 (default: 2)
#
# Example:
#   ./report-download-status.sh \
#     --title "SBIR Awards Download" \
#     --emoji "🎯" \
#     --status "success" \
#     --json-file response.json \
#     --message "Downloaded successfully"

# Default values
SECTION_LEVEL=2
JSON_LABEL="Response"
STATUS=""
TITLE=""
EMOJI=""
JSON_FILE=""
MESSAGE=""

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --title)
            TITLE="$2"
            shift 2
            ;;
        --emoji)
            EMOJI="$2"
            shift 2
            ;;
        --status)
            STATUS="$2"
            shift 2
            ;;
        --json-file)
            JSON_FILE="$2"
            shift 2
            ;;
        --json-label)
            JSON_LABEL="$2"
            shift 2
            ;;
        --message)
            MESSAGE="$2"
            shift 2
            ;;
        --section-level)
            SECTION_LEVEL="$2"
            shift 2
            ;;
        *)
            echo "Unknown option: $1" >&2
            exit 1
            ;;
    esac
done

# Generate header markdown prefix
HEADER_PREFIX=""
for ((i=1; i<=SECTION_LEVEL; i++)); do
    HEADER_PREFIX="${HEADER_PREFIX}#"
done

# Display title with emoji if provided
if [ -n "$TITLE" ]; then
    if [ -n "$EMOJI" ]; then
        echo "${HEADER_PREFIX} ${EMOJI} ${TITLE}" >> $GITHUB_STEP_SUMMARY
    else
        echo "${HEADER_PREFIX} ${TITLE}" >> $GITHUB_STEP_SUMMARY
    fi
    echo "" >> $GITHUB_STEP_SUMMARY
fi

# Display status if provided
if [ -n "$STATUS" ]; then
    case "$STATUS" in
        success)
            STATUS_EMOJI="✅"
            STATUS_TEXT="SUCCESS"
            ;;
        failed|failure)
            STATUS_EMOJI="❌"
            STATUS_TEXT="FAILED"
            ;;
        skipped|skip)
            STATUS_EMOJI="⏭️"
            STATUS_TEXT="SKIPPED"
            ;;
        running)
            STATUS_EMOJI="⏳"
            STATUS_TEXT="RUNNING"
            ;;
        *)
            STATUS_EMOJI="ℹ️"
            STATUS_TEXT="$STATUS"
            ;;
    esac

    echo "${STATUS_EMOJI} **Status:** ${STATUS_TEXT}" >> $GITHUB_STEP_SUMMARY
    echo "" >> $GITHUB_STEP_SUMMARY
fi

# Display message if provided
if [ -n "$MESSAGE" ]; then
    echo "$MESSAGE" >> $GITHUB_STEP_SUMMARY
    echo "" >> $GITHUB_STEP_SUMMARY
fi

# Display JSON file if provided
if [ -n "$JSON_FILE" ] && [ -f "$JSON_FILE" ]; then
    # Increase section level for subsection
    SUBSECTION_LEVEL=$((SECTION_LEVEL + 1))
    SUBSECTION_PREFIX=""
    for ((i=1; i<=SUBSECTION_LEVEL; i++)); do
        SUBSECTION_PREFIX="${SUBSECTION_PREFIX}#"
    done

    echo "${SUBSECTION_PREFIX} ${JSON_LABEL}" >> $GITHUB_STEP_SUMMARY
    echo '```json' >> $GITHUB_STEP_SUMMARY
    cat "$JSON_FILE" | jq '.' >> $GITHUB_STEP_SUMMARY || cat "$JSON_FILE" >> $GITHUB_STEP_SUMMARY
    echo '```' >> $GITHUB_STEP_SUMMARY
    echo "" >> $GITHUB_STEP_SUMMARY
fi
