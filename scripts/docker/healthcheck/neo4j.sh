#!/bin/bash
# Neo4j healthcheck script
#
# This script checks if Neo4j is ready to accept connections by executing
# a simple Cypher query. It uses environment variables for credentials.
#
# Environment variables:
#   NEO4J_USER: Neo4j username (default: neo4j)
#   NEO4J_PASSWORD: Neo4j password (default: password)
#   NEO4J_URI: Neo4j connection URI (default: bolt://localhost:7687)
#
# Exit codes:
#   0: Neo4j is healthy and ready
#   1: Neo4j is not ready or query failed

set -euo pipefail

NEO4J_USER="${NEO4J_USER:-neo4j}"
NEO4J_PASSWORD="${NEO4J_PASSWORD:-password}"
NEO4J_URI="${NEO4J_URI:-bolt://localhost:7687}"

# Extract host and port from URI if needed (for docker exec scenarios)
# Default to localhost if running inside container
HOST="${NEO4J_URI%%:*}"

# Try cypher-shell first (if available in container)
if command -v cypher-shell >/dev/null 2>&1; then
    if cypher-shell -u "$NEO4J_USER" -p "$NEO4J_PASSWORD" "RETURN 1" >/dev/null 2>&1; then
        exit 0
    fi
fi

# Fallback: Check if HTTP endpoint responds
if command -v curl >/dev/null 2>&1; then
    HTTP_URL="http://localhost:7474"
    if curl -fsS --max-time 3 "$HTTP_URL" >/dev/null 2>&1; then
        exit 0
    fi
fi

# Last resort: Check if bolt port is listening
if command -v nc >/dev/null 2>&1 || command -v netcat >/dev/null 2>&1; then
    PORT="7687"
    if nc -z localhost "$PORT" 2>/dev/null || netcat -z localhost "$PORT" 2>/dev/null; then
        exit 0
    fi
fi

exit 1
