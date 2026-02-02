#!/bin/bash
set -e

echo "🚀 Starting GODMODESCANNER Pump.fun Stream Integration..."

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# 1. Check Redis
echo -e "${YELLOW}🔴 Checking Redis...${NC}"
if ! redis-cli ping > /dev/null 2>&1; then
    echo "Starting Redis..."
    redis-server --daemonize yes
    sleep 2
fi
echo -e "${GREEN}✅ Redis is running${NC}"

# 2. Create consumer groups
echo -e "${YELLOW}📥 Creating consumer groups...${NC}"
redis-cli XGROUP CREATE godmode:new_transactions wallet-analyzer-group 0 MKSTREAM 2>/dev/null || true
redis-cli XGROUP CREATE godmode:new_transactions pattern-recognition-group 0 MKSTREAM 2>/dev/null || true
redis-cli XGROUP CREATE godmode:new_transactions sybil-detection-group 0 MKSTREAM 2>/dev/null || true
redis-cli XGROUP CREATE godmode:new_tokens token-tracker-group 0 MKSTREAM 2>/dev/null || true
echo -e "${GREEN}✅ Consumer groups ready${NC}"

# 3. Start Pump.fun stream producer
echo -e "${YELLOW}📡 Starting Pump.fun Stream Producer...${NC}"
python -m agents.pump_fun_stream_producer &
PRODUCER_PID=$!
echo -e "${GREEN}✅ Stream producer started (PID: $PRODUCER_PID)${NC}"

# 4. Wait and verify
sleep 5
echo ""
echo -e "${YELLOW}🔍 Verifying stream...${NC}"
STREAM_LEN=$(redis-cli XLEN godmode:new_transactions)
echo "Transactions stream length: $STREAM_LEN"

echo ""
echo -e "${GREEN}✅ Pump.fun stream integration is active!${NC}"
echo ""
echo "Monitor commands:"
echo "  redis-cli XLEN godmode:new_transactions     # Queue size"
echo "  redis-cli XLEN godmode:new_tokens           # New tokens"
echo "  redis-cli SUBSCRIBE godmode:heartbeat:pumpfun_stream  # Heartbeat"
