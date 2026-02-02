#!/bin/bash
# GUERRILLA REDIS CLUSTER - Stop Script
# Gracefully stops all 6 Redis Cluster nodes

echo "========================================"
echo "GUERRILLA REDIS CLUSTER STOP"
echo "========================================"

BASE_PORT=16379

# Gracefully shutdown all nodes
echo "Shutting down Redis Cluster nodes..."
for i in {1..6}; do
    PORT=$((BASE_PORT + i - 1))
    echo "  -> Stopping node on port $PORT..."
    redis-cli -p $PORT shutdown nosave 2>/dev/null
done

sleep 2

# Verify all nodes are stopped
echo "Verifying shutdown..."
STOPPED=0
for i in {1..6}; do
    PORT=$((BASE_PORT + i - 1))
    if ! redis-cli -p $PORT ping > /dev/null 2>&1; then
        echo "  -> Node $i (port $PORT): STOPPED"
        ((STOPPED++))
    else
        echo "  -> Node $i (port $PORT): STILL RUNNING"
    fi
done

echo ""
echo "========================================"
echo "Cluster Status: $STOPPED/6 nodes stopped"
echo "========================================"

if [ $STOPPED -eq 6 ]; then
    echo "All Redis Cluster nodes stopped successfully."
    exit 0
else
    echo "Some nodes may still be running. Check manually."
    exit 1
fi
