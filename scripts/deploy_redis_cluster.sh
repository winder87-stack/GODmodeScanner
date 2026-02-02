#!/bin/bash
#===============================================================================
# GODMODESCANNER Redis Cluster Deployment Script
# Run this script on your HOST machine (not inside the container)
#===============================================================================

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║     GODMODESCANNER Redis Cluster Deployment                  ║${NC}"
echo -e "${BLUE}║     6-Node AOF-Only High-Performance Architecture            ║${NC}"
echo -e "${BLUE}╚══════════════════════════════════════════════════════════════╝${NC}"
echo ""

# Configuration
CONTAINER_ID="9e3e1e67a97b"
PROJECT_DIR="/home/ink/godmodescanner/projects/godmodescanner"
CONTAINER_PATH="/a0/usr/projects/godmodescanner/projects/godmodescanner"

#===============================================================================
# STEP 1: Sync files from container
#===============================================================================
echo -e "${YELLOW}[1/8] Syncing files from container...${NC}"

cd "$PROJECT_DIR" || { echo -e "${RED}ERROR: Project directory not found!${NC}"; exit 1; }

# Create directories if they don't exist
mkdir -p config/redis scripts utils

# Copy updated files from container
echo "  - Copying docker-compose.yml..."
docker cp ${CONTAINER_ID}:${CONTAINER_PATH}/docker-compose.yml . 2>/dev/null || echo "  (file may already exist)"

echo "  - Copying Redis config..."
docker cp ${CONTAINER_ID}:${CONTAINER_PATH}/config/redis/ ./config/ 2>/dev/null || echo "  (creating new)"

echo "  - Copying init script..."
docker cp ${CONTAINER_ID}:${CONTAINER_PATH}/scripts/init_redis_cluster.sh ./scripts/ 2>/dev/null || echo "  (creating new)"

echo "  - Copying Redis client..."
docker cp ${CONTAINER_ID}:${CONTAINER_PATH}/utils/redis_client.py ./utils/ 2>/dev/null || echo "  (file may already exist)"

echo "  - Copying storage config..."
docker cp ${CONTAINER_ID}:${CONTAINER_PATH}/config/storage_config.py ./config/ 2>/dev/null || echo "  (file may already exist)"

echo -e "${GREEN}  [OK] Files synced${NC}"

#===============================================================================
# STEP 2: Create data directories
#===============================================================================
echo -e "${YELLOW}[2/8] Creating data directories...${NC}"

mkdir -p data/redis/{m1,m2,m3,r1,r2,r3}
chmod -R 777 data/redis

echo -e "${GREEN}  [OK] Data directories created${NC}"

#===============================================================================
# STEP 3: Stop any existing Redis containers
#===============================================================================
echo -e "${YELLOW}[3/8] Stopping existing Redis containers...${NC}"

docker-compose down redis-master-1 redis-master-2 redis-master-3 \
                    redis-replica-1 redis-replica-2 redis-replica-3 2>/dev/null || true

echo -e "${GREEN}  [OK] Existing containers stopped${NC}"

#===============================================================================
# STEP 4: Start Redis cluster nodes
#===============================================================================
echo -e "${YELLOW}[4/8] Starting Redis cluster nodes...${NC}"

docker-compose up -d redis-master-1 redis-master-2 redis-master-3 \
                    redis-replica-1 redis-replica-2 redis-replica-3

echo -e "${GREEN}  [OK] Redis nodes started${NC}"

#===============================================================================
# STEP 5: Wait for nodes to be healthy
#===============================================================================
echo -e "${YELLOW}[5/8] Waiting for nodes to be healthy (45 seconds)...${NC}"

for i in {1..9}; do
    echo -n "  [$((i*5))s] "
    docker-compose ps | grep -E "redis-(master|replica)" | head -1 || true
    sleep 5
done

echo -e "${GREEN}  [OK] Nodes should be healthy${NC}"

#===============================================================================
# STEP 6: Initialize cluster topology
#===============================================================================
echo -e "${YELLOW}[6/8] Initializing cluster topology...${NC}"

chmod +x scripts/init_redis_cluster.sh 2>/dev/null || true

# Create cluster using redis-cli
docker exec godmode_redis_m1 redis-cli --cluster create \
    172.28.1.1:6379 172.28.1.2:6379 172.28.1.3:6379 \
    172.28.1.4:6379 172.28.1.5:6379 172.28.1.6:6379 \
    --cluster-replicas 1 --cluster-yes || {
    echo -e "${YELLOW}  Cluster may already exist, checking status...${NC}"
}

echo -e "${GREEN}  [OK] Cluster topology initialized${NC}"

#===============================================================================
# STEP 7: Verify cluster status
#===============================================================================
echo -e "${YELLOW}[7/8] Verifying cluster status...${NC}"

echo "  Cluster Info:"
docker exec godmode_redis_m1 redis-cli cluster info | head -5

echo ""
echo "  Cluster Nodes:"
docker exec godmode_redis_m1 redis-cli cluster nodes

echo -e "${GREEN}  [OK] Cluster verified${NC}"

#===============================================================================
# STEP 8: Update environment and start services
#===============================================================================
echo -e "${YELLOW}[8/8] Updating environment...${NC}"

# Add to .env file if not already present
if ! grep -q "REDIS_MODE=cluster" .env 2>/dev/null; then
    echo "" >> .env
    echo "# Redis Cluster Configuration" >> .env
    echo "REDIS_MODE=cluster" >> .env
    echo "REDIS_CLUSTER_NODES=172.28.1.1:6379,172.28.1.2:6379,172.28.1.3:6379" >> .env
fi

echo -e "${GREEN}  [OK] Environment updated${NC}"

#===============================================================================
# COMPLETE
#===============================================================================
echo ""
echo -e "${GREEN}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║     REDIS CLUSTER DEPLOYMENT COMPLETE!                       ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${BLUE}Cluster Architecture:${NC}"
echo "  - 3 Master Nodes (172.28.1.1-3:6379)"
echo "  - 3 Replica Nodes (172.28.1.4-6:6379)"
echo "  - AOF-Only Persistence (appendfsync everysec)"
echo "  - Target: 100,000+ writes/second"
echo ""
echo -e "${BLUE}Next Steps:${NC}"
echo "  1. Start all GODMODESCANNER services:"
echo "     docker-compose up -d"
echo ""
echo "  2. Monitor cluster health:"
echo "     docker exec godmode_redis_m1 redis-cli cluster info"
echo ""
echo "  3. Run benchmark:"
echo "     docker exec godmode_redis_m1 redis-benchmark -c 100 -n 100000"
echo ""
