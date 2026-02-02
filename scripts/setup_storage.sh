#!/bin/bash
# Setup persistent storage directories on HOST machine
# Run this on your HOST (not inside Docker container)

set -e

echo "🔧 GODMODESCANNER STORAGE SETUP"
echo "================================"

# Get project root - adjust this path for your system
PROJECT_ROOT="${1:-/home/ink/godmodescanner}"
DATA_ROOT="${PROJECT_ROOT}/data"

echo "📁 Creating directory structure at: ${DATA_ROOT}"

# Create all required directories
mkdir -p "${DATA_ROOT}/memory/patterns"
mkdir -p "${DATA_ROOT}/memory/insights"
mkdir -p "${DATA_ROOT}/memory/wallets"
mkdir -p "${DATA_ROOT}/memory/rules"
mkdir -p "${DATA_ROOT}/redis"
mkdir -p "${DATA_ROOT}/redis-cluster/node1"
mkdir -p "${DATA_ROOT}/redis-cluster/node2"
mkdir -p "${DATA_ROOT}/redis-cluster/node3"
mkdir -p "${DATA_ROOT}/redis-cluster/node4"
mkdir -p "${DATA_ROOT}/redis-cluster/node5"
mkdir -p "${DATA_ROOT}/redis-cluster/node6"
mkdir -p "${DATA_ROOT}/graph_data"
mkdir -p "${DATA_ROOT}/models"
mkdir -p "${DATA_ROOT}/knowledge"
mkdir -p "${PROJECT_ROOT}/logs"

# Set permissions (allow Docker to write)
chmod -R 777 "${DATA_ROOT}"
chmod -R 777 "${PROJECT_ROOT}/logs"

echo "✅ Directory structure created:"
find "${DATA_ROOT}" -type d | head -25

# Create .gitkeep files to preserve structure in git
find "${DATA_ROOT}" -type d -empty -exec touch {}/.gitkeep \;

echo ""
echo "📊 Storage Summary:"
echo "   Memory Path:    ${DATA_ROOT}/memory"
echo "   Redis Path:     ${DATA_ROOT}/redis"
echo "   Graph Path:     ${DATA_ROOT}/graph_data"
echo "   Models Path:    ${DATA_ROOT}/models"
echo "   Knowledge Path: ${DATA_ROOT}/knowledge"
echo "   Logs Path:      ${PROJECT_ROOT}/logs"

echo ""
echo "✅ Storage setup complete!"
echo ""
echo "Next steps:"
echo "  1. Copy .env.persistence to your project root"
echo "  2. Restart Docker containers: docker-compose down && docker-compose up -d"
echo "  3. Verify mounts: docker exec godmode_scanner ls -la /data/memory"
echo "  4. Run audit: docker exec godmode_scanner python scripts/audit_storage.py"
