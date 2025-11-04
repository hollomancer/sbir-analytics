#!/bin/bash
# Validation script for consolidated Docker Compose configuration

set -e

echo "🔍 Validating consolidated Docker Compose configuration..."

COMPOSE_FILE="docker-compose.yml"
PROFILES=("dev" "ci")

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

# Test dev + ci (should work as services are shared)
if docker compose --profile dev --profile ci -f "$COMPOSE_FILE" config --quiet 2>/dev/null; then
    echo "   ✅ Multi-profile combination 'dev + ci' works"
else
    echo "   ⚠️  Multi-profile combination 'dev + ci' failed (may be expected)"
fi

echo ""
echo "✅ Consolidated Docker Compose configuration validation completed successfully!"
echo ""
echo "📋 Usage examples:"
echo "   docker compose --profile dev up --build          # Development"
echo "   docker compose --profile ci up --build           # CI Testing"
echo ""
echo "💡 Set COMPOSE_PROFILES in .env to automatically activate profiles"