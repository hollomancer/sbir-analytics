#!/bin/bash
# Dagster daemon healthcheck script
#
# This script checks if the Dagster daemon process is running.
#
# Exit codes:
#   0: Daemon is running
#   1: Daemon is not running

set -euo pipefail

# Use Dagster's heartbeat-backed liveness check. The slim runtime image does
# not include procps utilities such as pgrep or ps.
if command -v dagster-daemon >/dev/null 2>&1 && \
    dagster-daemon liveness-check >/dev/null 2>&1; then
    exit 0
fi

exit 1
