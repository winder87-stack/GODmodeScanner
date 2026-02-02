#!/bin/bash
# =============================================================================
# GODMODESCANNER TimescaleDB Setup Script
# =============================================================================
# This script provides TimescaleDB database setup for GODMODESCANNER
# Supports: Python-based setup (recommended) or manual SQL generation
# =============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_SCRIPT="${SCRIPT_DIR}/setup_timescaledb.py"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║     GODMODESCANNER TimescaleDB Setup                      ║${NC}"
echo -e "${BLUE}╚══════════════════════════════════════════════════════════════╝${NC}"
echo

# Check if Python script exists
if [ -f "${PYTHON_SCRIPT}" ]; then
    echo -e "${GREEN}▶ Using Python-based setup...${NC}"
    echo
    python "${PYTHON_SCRIPT}"
else
    echo -e "${YELLOW}⚠ Python script not found, generating manual setup...${NC}"
    echo
    
    # Generate credentials
    DB_NAME="godmodescanner"
    DB_USER="godmodescanner"
    DB_PASS=$(openssl rand -base64 32 2>/dev/null || echo "change_this_password")
    
    echo "=============================================="
    echo "⚠️ Manual TimescaleDB Setup Required"
    echo "=============================================="
    echo
    echo "Run the following SQL as postgres user:"
    echo "----------------------------------------------"
    cat << SQL

-- Create user
DROP DATABASE IF EXISTS ${DB_NAME};
DROP USER IF EXISTS ${DB_USER};
CREATE USER ${DB_USER} WITH PASSWORD '${DB_PASS}';

-- Create database
CREATE DATABASE ${DB_NAME} OWNER ${DB_USER};
\c ${DB_NAME}

-- Enable TimescaleDB
CREATE EXTENSION IF NOT EXISTS timescaledb;

-- Grant permissions
GRANT ALL ON SCHEMA public TO ${DB_USER};
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO ${DB_USER};
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO ${DB_USER};

SQL
    echo "----------------------------------------------"
    echo
    echo "Add to pg_hba.conf for Docker access:"
    echo "  host    ${DB_NAME}    ${DB_USER}    172.17.0.0/16    scram-sha-256"
    echo
    echo "Add to your .env file:"
    echo "  TIMESCALEDB_HOST=172.17.0.1"
    echo "  TIMESCALEDB_PORT=5432"
    echo "  TIMESCALEDB_USER=${DB_USER}"
    echo "  TIMESCALEDB_PASSWORD=${DB_PASS}"
    echo "  TIMESCALEDB_DATABASE=${DB_NAME}"
fi

# Final instructions
echo
if [ -f "${SCRIPT_DIR}/init_timescaledb.py" ]; then
    echo -e "${GREEN}▶ After database setup, initialize the schema:${NC}"
    echo "  python ${SCRIPT_DIR}/init_timescaledb.py"
fi

exit 0
