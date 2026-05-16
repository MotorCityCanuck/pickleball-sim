#!/bin/bash
# Development Environment Setup Script for Pickleball Simulation Platform

set -e  # Exit on error

echo "🏓 Pickleball Simulation Platform - Development Setup"
echo "======================================================"
echo ""

# Color codes for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Check if running in WSL
if grep -qi microsoft /proc/version 2>/dev/null; then
    echo "${YELLOW}ℹ️  WSL/Ubuntu environment detected${NC}"
    IS_WSL=true
else
    IS_WSL=false
fi

# Step 1: Check prerequisites
echo "📋 Step 1: Checking prerequisites..."

if ! command -v docker &> /dev/null; then
    echo "${RED}❌ Docker not found. Please install Docker Desktop.${NC}"
    exit 1
fi
echo "${GREEN}✓${NC} Docker found"

if ! command -v python3 &> /dev/null; then
    echo "${RED}❌ Python3 not found. Please install Python 3.11+${NC}"
    exit 1
fi
PYTHON_VERSION=$(python3 --version | cut -d' ' -f2)
echo "${GREEN}✓${NC} Python $PYTHON_VERSION found"

# Step 2: Copy environment file
echo ""
echo "📋 Step 2: Setting up environment variables..."
if [ ! -f .env ]; then
    cp env.example .env
    echo "${GREEN}✓${NC} Created .env from env.example"
    echo "${YELLOW}⚠️  Please review and update .env with your settings${NC}"
else
    echo "${YELLOW}ℹ️  .env already exists, skipping...${NC}"
fi

# Step 3: Start PostgreSQL
echo ""
echo "📋 Step 3: Starting PostgreSQL via Docker..."
if docker ps | grep -q pickleball_postgres; then
    echo "${YELLOW}ℹ️  PostgreSQL already running${NC}"
else
    docker-compose up -d postgres
    echo "${GREEN}✓${NC} PostgreSQL started"
    echo "⏳ Waiting for PostgreSQL to be ready..."
    sleep 5
fi

# Step 4: Create Python virtual environment
echo ""
echo "📋 Step 4: Setting up Python virtual environment..."
cd backend
if [ ! -d "venv" ]; then
    python3 -m venv venv
    echo "${GREEN}✓${NC} Virtual environment created"
else
    echo "${YELLOW}ℹ️  Virtual environment already exists${NC}"
fi

# Step 5: Install Python dependencies
echo ""
echo "📋 Step 5: Installing Python dependencies..."
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
echo "${GREEN}✓${NC} Python dependencies installed"

# Step 6: Check ORM schema utilities
echo ""
echo "📋 Step 6: Checking ORM schema utilities..."
if [ ! -f "scripts/recreate_db_from_orm.py" ]; then
    echo "${YELLOW}⚠️  ORM recreation script not created yet${NC}"
    echo "   Next implementation step: create backend/scripts/recreate_db_from_orm.py"
else
    echo "${GREEN}✓${NC} ORM recreation script found"
fi

# Step 7: Summary
echo ""
echo "======================================================"
echo "${GREEN}✅ Development environment setup complete!${NC}"
echo ""
echo "📝 Next steps:"
echo "   1. Review and update .env file if needed"
echo "   2. cd backend"
echo "   3. source venv/bin/activate"
if [ ! -f "backend/scripts/recreate_db_from_orm.py" ]; then
    echo "   4. Create backend/scripts/recreate_db_from_orm.py"
    echo "   5. Create backend/scripts/export_schema_from_orm.py"
    echo "   6. Run ORM consistency tests"
else
    echo "   4. Recreate database: python scripts/recreate_db_from_orm.py"
    echo "   5. Export reference SQL: python scripts/export_schema_from_orm.py"
fi
echo ""
echo "📚 Documentation:"
echo "   - Quick Start: docs_QUICK_START_GUIDE.md"
echo "   - Master Index: docs_MASTER_DOCUMENT_INDEX.md"
echo "   - Database Design: database/Pickleball_Simulation_Database_Design_v3.md"
echo ""
echo "🐳 Docker commands:"
echo "   - View logs: docker-compose logs -f postgres"
echo "   - Stop services: docker-compose down"
echo "   - Restart: docker-compose restart postgres"
echo ""
