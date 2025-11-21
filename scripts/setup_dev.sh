#!/usr/bin/env bash
# Development Environment Setup Script
# Run this to set up or verify your development environment

set -e  # Exit on error

echo "🔧 SBIR Analytics - Development Environment Setup"
echo "=================================================="
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check Python version
echo "1️⃣  Checking Python version..."
REQUIRED_PYTHON="3.11"
PYTHON_VERSION=$(python3.11 --version 2>&1 | awk '{print $2}' | cut -d. -f1,2)

if [ "$PYTHON_VERSION" != "$REQUIRED_PYTHON" ]; then
    echo -e "${RED}❌ Error: Python 3.11 not found${NC}"
    echo "   Current: python3.11 --version shows: $(python3.11 --version 2>&1 || echo 'not found')"
    echo "   Required: Python 3.11.x"
    echo ""
    echo "Install Python 3.11:"
    echo "  brew install python@3.11"
    exit 1
else
    echo -e "${GREEN}✓ Python 3.11 found${NC}"
fi

# Check if virtual environment exists
echo ""
echo "2️⃣  Checking virtual environment..."
if [ ! -d ".venv" ]; then
    echo -e "${YELLOW}⚠️  Virtual environment not found. Creating...${NC}"
    python3.11 -m venv .venv
    echo -e "${GREEN}✓ Virtual environment created${NC}"
else
    # Check if venv uses correct Python
    VENV_PYTHON=$(.venv/bin/python --version 2>&1 | awk '{print $2}' | cut -d. -f1,2)
    if [ "$VENV_PYTHON" != "$REQUIRED_PYTHON" ]; then
        echo -e "${RED}❌ Virtual environment uses wrong Python version: $VENV_PYTHON${NC}"
        echo "   Recreating with Python 3.11..."
        rm -rf .venv
        python3.11 -m venv .venv
        echo -e "${GREEN}✓ Virtual environment recreated${NC}"
    else
        echo -e "${GREEN}✓ Virtual environment exists with correct Python${NC}"
    fi
fi

# Activate virtual environment
echo ""
echo "3️⃣  Activating virtual environment..."
source .venv/bin/activate

# Verify we're in the venv
if [ "$VIRTUAL_ENV" != "$(pwd)/.venv" ]; then
    echo -e "${RED}❌ Failed to activate virtual environment${NC}"
    exit 1
fi
echo -e "${GREEN}✓ Virtual environment activated${NC}"

# Install/update uv if needed
echo ""
echo "4️⃣  Checking uv package manager..."
if ! command -v uv &> /dev/null; then
    echo -e "${YELLOW}⚠️  uv not found. Installing...${NC}"
    pip install uv
fi
echo -e "${GREEN}✓ uv is available${NC}"

# Install dependencies
echo ""
echo "5️⃣  Installing dependencies..."
echo "   This may take a minute..."
uv sync --extra dev --extra r --extra paecter-local

# Verify installation
echo ""
echo "6️⃣  Verifying installation..."

# Check pytest
if ! python -m pytest --version &> /dev/null; then
    echo -e "${RED}❌ pytest not installed correctly${NC}"
    exit 1
fi
echo -e "${GREEN}✓ pytest installed${NC}"

# Check key dependencies
DEPS=("pydantic" "loguru" "neo4j" "pandas")
for dep in "${DEPS[@]}"; do
    if ! python -c "import $dep" 2>/dev/null; then
        echo -e "${RED}❌ $dep not installed${NC}"
        exit 1
    fi
done
echo -e "${GREEN}✓ Core dependencies installed${NC}"

# Print summary
echo ""
echo "=================================================="
echo -e "${GREEN}✅ Development environment ready!${NC}"
echo "=================================================="
echo ""
echo "Environment details:"
echo "  Python version: $(python --version)"
echo "  Python location: $(which python)"
echo "  pip version: $(pip --version | awk '{print $2}')"
echo "  pytest version: $(python -m pytest --version | head -1)"
echo ""
echo "Next steps:"
echo "  1. Activate the environment: source .venv/bin/activate"
echo "  2. Run tests: make test"
echo "  3. Start developing!"
echo ""
echo "To activate in future sessions:"
echo "  source .venv/bin/activate"
echo ""
