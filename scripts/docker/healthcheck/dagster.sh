#!/bin/bash
# Dagster webserver healthcheck script
#
# This script checks if the Dagster webserver is ready by querying the
# /server_info endpoint. It respects environment variables for configuration.
#
# Environment variables:
#   HEALTHCHECK_PORT: Port to check (default: 3000)
#   HEALTHCHECK_PATH: Healthcheck path (default: /server_info)
#
# Exit codes:
#   0: Dagster webserver is healthy
#   1: Webserver is not ready

set -euo pipefail

PORT="${HEALTHCHECK_PORT:-3000}"
PATH="${HEALTHCHECK_PATH:-/server_info}"
HOST="${HEALTHCHECK_HOST:-localhost}"

URL="http://${HOST}:${PORT}${PATH}"

if command -v curl >/dev/null 2>&1; then
    if curl -fsS --max-time 3 "$URL" >/dev/null 2>&1; then
        exit 0
    fi
fi

# Fallback: Check if port is listening
if command -v nc >/dev/null 2>&1 || command -v netcat >/dev/null 2>&1; then
    if nc -z "$HOST" "$PORT" 2>/dev/null || netcat -z "$HOST" "$PORT" 2>/dev/null; then
        exit 0
    fi
fi

exit 1
