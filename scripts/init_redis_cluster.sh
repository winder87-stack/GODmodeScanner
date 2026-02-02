#!/bin/bash
# =============================================================================
# GODMODESCANNER Redis AOF-Only Cluster Initialization Script
# =============================================================================
# This script initializes the 6-node Redis cluster after containers start.
# Run this ONCE after docker-compose up to create the cluster topology.
#
# Usage:
#   ./scripts/init_redis_cluster.sh
#
# Prerequisites:
#   - All 6 Redis containers must be running and healthy
#   - Docker network must be configured with static IPs
# =============================================================================

set -e

# Colors for output
RED='[0;31m'
GREEN='[0;32m'
YELLOW='[1;33m'
BLUE='[0;34m'
NC='[0m' # No Color

echo -e "${BLUE}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║     GODMODESCANNER Redis AOF-Only Cluster Initialization     ║${NC}"
echo -e "${BLUE}╚══════════════════════════════════════════════════════════════╝${NC}"
echo ""

# Cluster node IPs (from docker-compose.yml)
MASTER_1="172.28.1.1:6379"
MASTER_2="172.28.1.2:6379"
MASTER_3="172.28.1.3:6379"
REPLICA_1="172.28.1.4:6379"
REPLICA_2="172.28.1.5:6379"
REPLICA_3="172.28.1.6:6379"

ALL_NODES="$MASTER_1 $MASTER_2 $MASTER_3 $REPLICA_1 $REPLICA_2 $REPLICA_3"

# =============================================================================
# Step 1: Check if containers are running
# =============================================================================
echo -e "${YELLOW}[1/5] Checking Redis containers...${NC}"

CONTAINERS=("godmode_redis_m1" "godmode_redis_m2" "godmode_redis_m3" 
            "godmode_redis_r1" "godmode_redis_r2" "godmode_redis_r3")

for container in "${CONTAINERS[@]}"; do
    if docker ps --format '{{.Names}}' | grep -q "^${container}$"; then
        echo -e "  ${GREEN}✓${NC} $container is running"
    else
        echo -e "  ${RED}✗${NC} $container is NOT running"
        echo -e "${RED}ERROR: Please start all containers first with: docker-compose up -d${NC}"
        exit 1
    fi
done

# =============================================================================
# Step 2: Wait for Redis to be ready
# =============================================================================
echo ""
echo -e "${YELLOW}[2/5] Waiting for Redis nodes to be ready...${NC}"

for container in "${CONTAINERS[@]}"; do
    echo -n "  Waiting for $container... "
    for i in {1..30}; do
        if docker exec $container redis-cli ping 2>/dev/null | grep -q PONG; then
            echo -e "${GREEN}ready${NC}"
            break
        fi
        if [ $i -eq 30 ]; then
            echo -e "${RED}timeout${NC}"
            exit 1
        fi
        sleep 1
    done
done

# =============================================================================
# Step 3: Check if cluster already exists
# =============================================================================
echo ""
echo -e "${YELLOW}[3/5] Checking existing cluster state...${NC}"

CLUSTER_INFO=$(docker exec godmode_redis_m1 redis-cli cluster info 2>/dev/null || echo "cluster_state:fail")

if echo "$CLUSTER_INFO" | grep -q "cluster_state:ok"; then
    echo -e "  ${GREEN}✓${NC} Cluster already initialized and healthy"
    echo ""
    echo -e "${BLUE}Cluster Status:${NC}"
    docker exec godmode_redis_m1 redis-cli cluster info | head -10
    echo ""
    echo -e "${GREEN}No action needed. Cluster is operational.${NC}"
    exit 0
else
    echo -e "  ${YELLOW}!${NC} Cluster not yet initialized"
fi

# =============================================================================
# Step 4: Create the cluster
# =============================================================================
echo ""
echo -e "${YELLOW}[4/5] Creating Redis cluster...${NC}"
echo -e "  Masters: $MASTER_1, $MASTER_2, $MASTER_3"
echo -e "  Replicas: $REPLICA_1, $REPLICA_2, $REPLICA_3"
echo ""

# Create cluster with 1 replica per master
docker exec godmode_redis_m1 redis-cli --cluster create     $MASTER_1 $MASTER_2 $MASTER_3     $REPLICA_1 $REPLICA_2 $REPLICA_3     --cluster-replicas 1     --cluster-yes

if [ $? -eq 0 ]; then
    echo ""
    echo -e "  ${GREEN}✓${NC} Cluster created successfully!"
else
    echo -e "  ${RED}✗${NC} Cluster creation failed"
    exit 1
fi

# =============================================================================
# Step 5: Verify cluster health
# =============================================================================
echo ""
echo -e "${YELLOW}[5/5] Verifying cluster health...${NC}"

sleep 3  # Wait for cluster to stabilize

CLUSTER_INFO=$(docker exec godmode_redis_m1 redis-cli cluster info)

if echo "$CLUSTER_INFO" | grep -q "cluster_state:ok"; then
    echo -e "  ${GREEN}✓${NC} Cluster state: OK"
else
    echo -e "  ${RED}✗${NC} Cluster state: FAIL"
    exit 1
fi

# Check slots
SLOTS_OK=$(echo "$CLUSTER_INFO" | grep "cluster_slots_ok" | cut -d: -f2)
if [ "$SLOTS_OK" -eq 16384 ]; then
    echo -e "  ${GREEN}✓${NC} All 16384 slots assigned"
else
    echo -e "  ${YELLOW}!${NC} Only $SLOTS_OK slots assigned"
fi

# Check nodes
KNOWN_NODES=$(echo "$CLUSTER_INFO" | grep "cluster_known_nodes" | cut -d: -f2)
echo -e "  ${GREEN}✓${NC} Known nodes: $KNOWN_NODES"

# =============================================================================
# Summary
# =============================================================================
echo ""
echo -e "${GREEN}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║           Redis AOF-Only Cluster Ready!                      ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${BLUE}Cluster Topology:${NC}"
echo "  ┌─────────────────────────────────────────────────────────┐"
echo "  │  Master 1 (172.28.1.1) ←→ Replica 1 (172.28.1.4)       │"
echo "  │  Master 2 (172.28.1.2) ←→ Replica 2 (172.28.1.5)       │"
echo "  │  Master 3 (172.28.1.3) ←→ Replica 3 (172.28.1.6)       │"
echo "  └─────────────────────────────────────────────────────────┘"
echo ""
echo -e "${BLUE}Performance Targets:${NC}"
echo "  • Write throughput: 100,000+ ops/sec"
echo "  • AOF rewrite latency: <100ms"
echo "  • Failover time: <1s"
echo ""
echo -e "${BLUE}Connection Info:${NC}"
echo "  REDIS_MODE=cluster"
echo "  REDIS_CLUSTER_NODES=172.28.1.1:6379,172.28.1.2:6379,172.28.1.3:6379"
echo ""
echo -e "${BLUE}Useful Commands:${NC}"
echo "  # Check cluster status"
echo "  docker exec godmode_redis_m1 redis-cli cluster info"
echo ""
echo "  # Check node roles"
echo "  docker exec godmode_redis_m1 redis-cli cluster nodes"
echo ""
echo "  # Monitor AOF rewrite"
echo "  docker exec godmode_redis_m1 redis-cli info persistence"
echo ""
