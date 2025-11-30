#!/usr/bin/env bash
# Additional helper functions for GitHub Actions reporting
# Source this file to use these functions in your workflow

# Display a configuration block
# Usage: report_config <json_payload> [title]
report_config() {
    local json_payload="$1"
    local title="${2:-Configuration}"

    echo "### ⚙️ ${title}" >> $GITHUB_STEP_SUMMARY
    echo '```json' >> $GITHUB_STEP_SUMMARY
    echo "$json_payload" | jq '.' >> $GITHUB_STEP_SUMMARY || echo "$json_payload" >> $GITHUB_STEP_SUMMARY
    echo '```' >> $GITHUB_STEP_SUMMARY
    echo "" >> $GITHUB_STEP_SUMMARY
}

# Display execution details in a table
# Usage: report_execution_details <execution_name> <start_date> <state_machine> <region>
report_execution_details() {
    local execution_name="$1"
    local start_date="$2"
    local state_machine="$3"
    local region="$4"

    echo "### ✅ Step Functions Execution Started" >> $GITHUB_STEP_SUMMARY
    echo "" >> $GITHUB_STEP_SUMMARY
    echo "| Property | Value |" >> $GITHUB_STEP_SUMMARY
    echo "|----------|-------|" >> $GITHUB_STEP_SUMMARY
    echo "| **Execution Name** | \`$execution_name\` |" >> $GITHUB_STEP_SUMMARY
    echo "| **Started At** | $start_date |" >> $GITHUB_STEP_SUMMARY
    echo "| **State Machine** | $state_machine |" >> $GITHUB_STEP_SUMMARY
    echo "| **Region** | $region |" >> $GITHUB_STEP_SUMMARY
    echo "" >> $GITHUB_STEP_SUMMARY
}

# Display error details from a file or string
# Usage: report_error <error_content> [title]
report_error() {
    local error_content="$1"
    local title="${2:-Error Details}"

    echo "### ❌ ${title}" >> $GITHUB_STEP_SUMMARY
    echo '```' >> $GITHUB_STEP_SUMMARY
    echo "$error_content" >> $GITHUB_STEP_SUMMARY
    echo '```' >> $GITHUB_STEP_SUMMARY
    echo "" >> $GITHUB_STEP_SUMMARY
}

# Display log excerpt
# Usage: report_logs <log_content> [title] [lines]
report_logs() {
    local log_content="$1"
    local title="${2:-Recent Logs}"
    local lines="${3:-20}"

    echo "### 📋 ${title}" >> $GITHUB_STEP_SUMMARY
    echo '```' >> $GITHUB_STEP_SUMMARY
    echo "$log_content" | tail -${lines} >> $GITHUB_STEP_SUMMARY
    echo '```' >> $GITHUB_STEP_SUMMARY
    echo "" >> $GITHUB_STEP_SUMMARY
}

# Display a collapsible details section
# Usage: report_collapsible <title> <content>
report_collapsible() {
    local title="$1"
    local content="$2"

    echo "<details>" >> $GITHUB_STEP_SUMMARY
    echo "<summary>$title</summary>" >> $GITHUB_STEP_SUMMARY
    echo "" >> $GITHUB_STEP_SUMMARY
    echo '```' >> $GITHUB_STEP_SUMMARY
    echo "$content" >> $GITHUB_STEP_SUMMARY
    echo '```' >> $GITHUB_STEP_SUMMARY
    echo "</details>" >> $GITHUB_STEP_SUMMARY
    echo "" >> $GITHUB_STEP_SUMMARY
}

# Display file change summary
# Usage: report_file_changes <current_count> [previous_count]
report_file_changes() {
    local current_count="$1"
    local previous_count="${2:-0}"

    echo "### 📈 Changes" >> $GITHUB_STEP_SUMMARY
    echo "**Total files:** $current_count" >> $GITHUB_STEP_SUMMARY

    if [ "$previous_count" -gt 0 ]; then
        local diff=$((current_count - previous_count))
        if [ $diff -gt 0 ]; then
            echo "**Change:** +${diff} files" >> $GITHUB_STEP_SUMMARY
        elif [ $diff -lt 0 ]; then
            echo "**Change:** ${diff} files" >> $GITHUB_STEP_SUMMARY
        else
            echo "**Change:** No change" >> $GITHUB_STEP_SUMMARY
        fi
    fi
    echo "" >> $GITHUB_STEP_SUMMARY
}

# Display status badge
# Usage: report_status_badge <status> <message>
report_status_badge() {
    local status="$1"
    local message="$2"

    case "$status" in
        success)
            echo "✅ **Status:** SUCCESS - $message" >> $GITHUB_STEP_SUMMARY
            ;;
        failed|failure)
            echo "❌ **Status:** FAILED - $message" >> $GITHUB_STEP_SUMMARY
            ;;
        skipped|skip)
            echo "⏭️ **Status:** SKIPPED - $message" >> $GITHUB_STEP_SUMMARY
            ;;
        running)
            echo "⏳ **Status:** RUNNING - $message" >> $GITHUB_STEP_SUMMARY
            ;;
        *)
            echo "ℹ️ **Status:** $status - $message" >> $GITHUB_STEP_SUMMARY
            ;;
    esac
    echo "" >> $GITHUB_STEP_SUMMARY
}

# Display info note
# Usage: report_info <message>
report_info() {
    local message="$1"
    echo "> ℹ️ $message" >> $GITHUB_STEP_SUMMARY
    echo "" >> $GITHUB_STEP_SUMMARY
}

# Display warning note
# Usage: report_warning <message>
report_warning() {
    local message="$1"
    echo "> ⚠️ $message" >> $GITHUB_STEP_SUMMARY
    echo "" >> $GITHUB_STEP_SUMMARY
}

# Display a header section
# Usage: report_header <level> <emoji> <title>
report_header() {
    local level="$1"
    local emoji="$2"
    local title="$3"

    local prefix=""
    for ((i=1; i<=level; i++)); do
        prefix="${prefix}#"
    done

    if [ -n "$emoji" ]; then
        echo "${prefix} ${emoji} ${title}" >> $GITHUB_STEP_SUMMARY
    else
        echo "${prefix} ${title}" >> $GITHUB_STEP_SUMMARY
    fi
    echo "" >> $GITHUB_STEP_SUMMARY
}

# Export functions so they can be used by sourcing this file
export -f report_config
export -f report_execution_details
export -f report_error
export -f report_logs
export -f report_collapsible
export -f report_file_changes
export -f report_status_badge
export -f report_info
export -f report_warning
export -f report_header
