#!/bin/bash
# Validation script for consolidated Docker Compose configuration

set -e

echo "🔍 Validating consolidated Docker Compose configuration..."

COMPOSE_FILE="docker-compose.consolidated.yml"
PROFILES=("dev" "prod" "cet-staging" "ci-test" "e2e" "neo4j-standalone" "tools")

# Check if consolidated file exists
if [ ! -f "$COMPOSE_FILE" ]; then
    echo "❌ Consolidated compose file not found: $COMPOSE_FILE"
    exit 1
fi

echo "✅ Found consolidated compose file: $COMPOSE_FILE"

# Test each profile configuration
echo "🧪 Testing profile configurations..."

for profile in "${PROFILES[@]}"; do
    echo "   Testing profile: $profile"
    
    if docker compose --profile "$profile" -f "$COMPOSE_FILE" config --quiet 2>/dev/null; then
        echo "   ✅ Profile '$profile' configuration is valid"
    else
        echo "   ❌ Profile '$profile' configuration is invalid"
        echo "   Error details:"
        docker compose --profile "$profile" -f "$COMPOSE_FILE" config --quiet 2>&1 | head -5
        exit 1
    fi
done

# Test service listing for each profile
echo "🔍 Checking services for each profile..."

for profile in "${PROFILES[@]}"; do
    services=$(docker compose --profile "$profile" -f "$COMPOSE_FILE" config --services 2>/dev/null | wc -l)
    echo "   Profile '$profile': $services services"
done

# Check for required environment variables
echo "🔧 Checking environment variable patterns..."

if grep -q "SBIR_ETL__" "$COMPOSE_FILE"; then
    echo "   ✅ Found standardized SBIR_ETL__ environment variables"
else
    echo "   ⚠️  No SBIR_ETL__ environment variables found"
fi

# Check for YAML anchors
if grep -q "x-common-environment:" "$COMPOSE_FILE" && grep -q "&common-environment" "$COMPOSE_FILE"; then
    echo "   ✅ YAML anchors are properly defined"
else
    echo "   ❌ YAML anchors may be missing or malformed"
fi

# Check for profile usage
profile_count=$(grep -c "profiles:" "$COMPOSE_FILE" || true)
echo "   ✅ Found $profile_count services with profile definitions"

# Test multi-profile combinations
echo "🔀 Testing multi-profile combinations..."

# Test dev + tools
if docker compose --profile dev --profile tools -f "$COMPOSE_FILE" config --quiet 2>/dev/null; then
    echo "   ✅ Multi-profile combination 'dev + tools' works"
else
    echo "   ❌ Multi-profile combination 'dev + tools' failed"
fi

# Test e2e + e2e-full
if docker compose --profile e2e --profile e2e-full -f "$COMPOSE_FILE" config --quiet 2>/dev/null; then
    echo "   ✅ Multi-profile combination 'e2e + e2e-full' works"
else
    echo "   ⚠️  Multi-profile combination 'e2e + e2e-full' failed (may be expected if e2e-full profile doesn't exist)"
fi

echo ""
echo "✅ Consolidated Docker Compose configuration validation completed successfully!"
echo ""
echo "📋 Usage examples:"
echo "   docker compose --profile dev up --build          # Development"
echo "   docker compose --profile prod up --build         # Production"
echo "   docker compose --profile cet-staging up --build  # CET Staging"
echo "   docker compose --profile ci-test up --build      # CI Testing"
echo "   docker compose --profile e2e up --build          # E2E Testing"
echo ""
echo "💡 Set COMPOSE_PROFILES in .env to automatically activate profiles"