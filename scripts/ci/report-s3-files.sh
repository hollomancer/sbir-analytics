#!/usr/bin/env bash
# Shared utility to report S3 files in GitHub Actions
# This script provides consistent S3 file listing across all download jobs

set -e

# Usage: report-s3-files.sh [options]
#
# Options:
#   --title <title>              Section title (e.g., "Downloaded Files")
#   --s3-bucket <bucket>         S3 bucket name (required)
#   --s3-prefix <prefix>         S3 prefix to list (required)
#   --tail <N>                   Show last N files (default: 10)
#   --recursive                  List files recursively (default: true)
#   --human-readable             Show human-readable sizes (default: true)
#   --summarize                  Show summary statistics (default: false)
#   --section-level <level>      Header level: 1-4 (default: 3)
#   --no-code-block              Don't wrap output in code block
#   --message <message>          Message to display before listing
#
# Example:
#   ./report-s3-files.sh \
#     --title "SBIR Files" \
#     --s3-bucket sbir-etl-production-data \
#     --s3-prefix raw/awards/ \
#     --tail 5

# Default values
SECTION_LEVEL=3
TAIL_COUNT=10
RECURSIVE=true
HUMAN_READABLE=true
SUMMARIZE=false
USE_CODE_BLOCK=true
TITLE=""
S3_BUCKET=""
S3_PREFIX=""
MESSAGE=""

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --title)
            TITLE="$2"
            shift 2
            ;;
        --s3-bucket)
            S3_BUCKET="$2"
            shift 2
            ;;
        --s3-prefix)
            S3_PREFIX="$2"
            shift 2
            ;;
        --tail)
            TAIL_COUNT="$2"
            shift 2
            ;;
        --recursive)
            RECURSIVE=true
            shift
            ;;
        --human-readable)
            HUMAN_READABLE=true
            shift
            ;;
        --summarize)
            SUMMARIZE=true
            shift
            ;;
        --section-level)
            SECTION_LEVEL="$2"
            shift 2
            ;;
        --no-code-block)
            USE_CODE_BLOCK=false
            shift
            ;;
        --message)
            MESSAGE="$2"
            shift 2
            ;;
        *)
            echo "Unknown option: $1" >&2
            exit 1
            ;;
    esac
done

# Validate required parameters
if [ -z "$S3_BUCKET" ]; then
    echo "Error: --s3-bucket is required" >&2
    exit 1
fi

if [ -z "$S3_PREFIX" ]; then
    echo "Error: --s3-prefix is required" >&2
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

# Display message if provided
if [ -n "$MESSAGE" ]; then
    echo "$MESSAGE" >> $GITHUB_STEP_SUMMARY
    echo "" >> $GITHUB_STEP_SUMMARY
fi

# Start code block if enabled
if [ "$USE_CODE_BLOCK" = true ]; then
    echo '```' >> $GITHUB_STEP_SUMMARY
fi

# Build aws s3 ls command
S3_CMD="aws s3 ls s3://${S3_BUCKET}/${S3_PREFIX}"

if [ "$RECURSIVE" = true ]; then
    S3_CMD="${S3_CMD} --recursive"
fi

if [ "$HUMAN_READABLE" = true ]; then
    S3_CMD="${S3_CMD} --human-readable"
fi

if [ "$SUMMARIZE" = true ]; then
    S3_CMD="${S3_CMD} --summarize"
fi

# Execute command and capture output
if eval "$S3_CMD | tail -${TAIL_COUNT}" >> $GITHUB_STEP_SUMMARY 2>&1; then
    : # Success
else
    echo "No files found in s3://${S3_BUCKET}/${S3_PREFIX}" >> $GITHUB_STEP_SUMMARY
fi

# End code block if enabled
if [ "$USE_CODE_BLOCK" = true ]; then
    echo '```' >> $GITHUB_STEP_SUMMARY
fi

echo "" >> $GITHUB_STEP_SUMMARY
