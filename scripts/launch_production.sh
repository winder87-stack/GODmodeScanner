#!/bin/bash
# ============================================================
# GODMODESCANNER - Production Launcher
# ============================================================

set -e

PROJECT_DIR="/a0/usr/projects/godmodescanner/projects/godmodescanner"
cd "$PROJECT_DIR"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo ""
echo "${BLUE}╔══════════════════════════════════════════════════════════╗${NC}"
echo "${BLUE}║${NC}  ${GREEN}GODMODESCANNER - Production Launcher${NC}                    ${BLUE}║${NC}"
echo "${BLUE}╚══════════════════════════════════════════════════════════╝${NC}"
echo ""

# ============================================================
# Pre-flight Checks
# ============================================================
echo "${YELLOW}[1/6] Running pre-flight checks...${NC}
