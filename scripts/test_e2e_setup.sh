#!/bin/bash
# Test script to validate E2E setup without using Makefile

set -e

echo "🧪 Testing E2E Docker Compose Setup"
echo "===================================="

# Check if .env exists
if [ ! -f .env ]; then
    echo "⚠️  .env file not found. Creating from example..."
    cp .env.example .env
    echo "✅ Created .env from example"
else
    echo "✅ .env file exists"
fi

# Validate Docker Compose configuration
echo ""
echo "🔍 Validating Docker Compose configuration..."
if docker compose -f docker-compose.yml -f docker/docker-compose.e2e.yml config --quiet; then
    echo "✅ E2E Docker Compose configuration is valid"
else
    echo "❌ E2E Docker Compose configuration has errors"
    exit 1
fi

# Test that we can build the configuration
echo ""
echo "🏗️  Testing configuration build..."
docker compose -f docker-compose.yml -f docker/docker-compose.e2e.yml config > /tmp/e2e-compose-test.yml
if [ -s /tmp/e2e-compose-test.yml ]; then
    echo "✅ Configuration builds successfully"
    rm /tmp/e2e-compose-test.yml
else
    echo "❌ Configuration build failed"
    exit 1
fi

# Check if scripts are executable
echo ""
echo "🔧 Checking script permissions..."
if [ -x scripts/run_e2e_tests.py ]; then
    echo "✅ E2E test runner is executable"
else
    echo "⚠️  Making E2E test runner executable..."
    chmod +x scripts/run_e2e_tests.py
    echo "✅ Fixed E2E test runner permissions"
fi

if [ -x scripts/e2e_health_check.py ]; then
    echo "✅ E2E health check is executable"
else
    echo "⚠️  Making E2E health check executable..."
    chmod +x scripts/e2e_health_check.py
    echo "✅ Fixed E2E health check permissions"
fi

# Test Python scripts syntax
echo ""
echo "🐍 Testing Python script syntax..."
if python -m py_compile scripts/run_e2e_tests.py; then
    echo "✅ E2E test runner syntax is valid"
else
    echo "❌ E2E test runner has syntax errors"
    exit 1
fi

if python -m py_compile scripts/e2e_health_check.py; then
    echo "✅ E2E health check syntax is valid"
else
    echo "❌ E2E health check has syntax errors"
    exit 1
fi

# Check documentation
echo ""
echo "📚 Checking documentation..."
if [ -f docs/testing/e2e-testing-guide.md ]; then
    echo "✅ E2E testing guide exists"
else
    echo "❌ E2E testing guide missing"
    exit 1
fi

echo ""
echo "🎉 All E2E setup tests passed!"
echo ""
echo "Next steps:"
echo "1. Configure your .env file with proper Neo4j credentials"
echo "2. Run E2E tests with:"
echo "   docker compose -f docker-compose.yml -f docker/docker-compose.e2e.yml up --build"
echo "3. Or use the direct commands:"
echo "   E2E_TEST_SCENARIO=minimal docker compose -f docker-compose.yml -f docker/docker-compose.e2e.yml up --build"
echo ""