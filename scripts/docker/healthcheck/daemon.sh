#!/bin/bash
# Dagster daemon healthcheck script
#
# This script checks if the Dagster daemon process is running.
#
# Exit codes:
#   0: Daemon is running
#   1: Daemon is not running

set -euo pipefail

# Check if dagster-daemon process exists
if pgrep -f "dagster-daemon" >/dev/null 2>&1; then
    exit 0
fi

# Alternative: Check via ps
if ps aux | grep -q '[d]agster-daemon'; then
    exit 0
fi

exit 1
