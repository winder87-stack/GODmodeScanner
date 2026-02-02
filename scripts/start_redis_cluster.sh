#!/bin/bash
# GUERRILLA REDIS CLUSTER - Native Deployment (Zero Docker Overhead)
# 6 Nodes: 3 Masters, 3 Replicas
# Ports: 16379-16384

echo "========================================"
echo "GUERRILLA REDIS CLUSTER STARTUP"
echo "========================================"

BASE_DIR="/a0/usr/projects/godmodescanner/projects/godmodescanner/data/redis_cluster"
BASE_PORT=16379

# Kill any existing Redis instances on cluster ports
echo "[1/5] Cleaning up existing instances..."
for i in {1..6}; do
    PORT=$((BASE_PORT + i - 1))
    redis-cli -p $PORT shutdown nosave 2>/dev/null
done
sleep 2

# Start 6 Redis instances with aggressive config
echo "[2/5] Launching 6 Redis nodes with aggressive config..."
for i in {1..6}; do
    PORT=$((BASE_PORT + i - 1))
    NODE_DIR="$BASE_DIR/node$i"
    
    # Create config file for this node
    cat > $NODE_DIR/redis.conf << REDEOF
port $PORT
cluster-enabled yes
cluster-config-file nodes-$i.conf
cluster-node-timeout 5000
appendonly yes
appendfilename "appendonly-$i.aof"
save ""
protected-mode no
logfile ""
loglevel warning
REDEOF
    
    # Start Redis instance
    redis-server $NODE_DIR/redis.conf &
    echo "  -> Node $i started on port $PORT"
done

sleep 3

# Verify all nodes are running
echo "[3/5] Verifying nodes are healthy..."
for i in {1..6}; do
    PORT=$((BASE_PORT + i - 1))
    if redis-cli -p $PORT ping > /dev/null 2>&1; then
        echo "  -> Node $i (port $PORT): ALIVE"
    else
        echo "  -> Node $i (port $PORT): FAILED TO START"
        exit 1
    fi
done

# Bootstrap the cluster
echo "[4/5] Bootstrapping Redis Cluster..."
redis-cli --cluster create \
    127.0.0.1:16379 \
    127.0.0.1:16380 \
    127.0.0.1:16381 \
    127.0.0.1:16382 \
    127.0.0.1:16383 \
    127.0.0.1:16384 \
    --cluster-replicas 1 \
    --cluster-yes

# Verify cluster status
echo "[5/5] Verifying Cluster Status..."
echo ""
echo "--- Cluster Nodes ---"
redis-cli -p 16379 cluster nodes | head -10

echo ""
echo "--- Cluster Info ---"
redis-cli -p 16379 cluster info | grep -E "cluster_state|cluster_slots_assigned|cluster_known_nodes"

echo ""
echo "========================================"
echo "GUERRILLA REDIS CLUSTER READY"
echo "========================================"
echo "Master nodes: 127.0.0.1:16379, 16380, 16381"
echo "Replica nodes: 127.0.0.1:16382, 16383, 16384"
echo ""
echo "Test connection: redis-cli -c -p 16379"
echo "========================================"
