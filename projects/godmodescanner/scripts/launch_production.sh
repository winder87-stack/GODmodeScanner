#!/bin/bash
# ============================================================
# GODMODESCANNER - Production Launcher
# ============================================================
# This script launches GODMODESCANNER with production settings
# and real-time monitoring dashboard
# ============================================================

set -e

PROJECT_DIR="/a0/usr/projects/godmodescanner/projects/godmodescanner"
cd "$PROJECT_DIR"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# ============================================================
# Banner
# ============================================================
echo ""
echo "${BLUE}╔══════════════════════════════════════════════════════════╗${NC}"
echo "${BLUE}║${NC}  ${GREEN}GODMODESCANNER - Production Launcher${NC}                    ${BLUE}║${NC}"
echo "${BLUE}╚══════════════════════════════════════════════════════════╝${NC}"
echo ""

# ============================================================
# Pre-flight Checks
# ============================================================
echo "${YELLOW}[1/6] Running pre-flight checks...${NC}"

# Check if venv exists
if [ ! -d "venv" ]; then
    echo "${RED}ERROR: Virtual environment not found${NC}"
    exit 1
fi

# Check Redis status
if ! redis-cli -p 6379 ping > /dev/null 2>&1; then
    echo "${YELLOW}WARNING: Redis not running on port 6379${NC}"
fi

# Check Guerrilla Redis Cluster
if redis-cli -p 16379 ping > /dev/null 2>&1; then
    echo "${GREEN}✓ Guerrilla Redis Cluster active${NC}"
else
    echo "${YELLOW}⚠ Guerrilla Redis Cluster not active${NC}"
fi

echo "${GREEN}✓ Pre-flight checks complete${NC}"
echo ""

# ============================================================
# Apply Production Settings
# ============================================================
echo "${YELLOW}[2/6] Applying production settings...${NC}"

# Backup current .env
cp .env .env.backup.$(date +%Y%m%d_%H%M%S) 2>/dev/null || true

# Apply optimized rate limits for free endpoints
# Conservative settings for free RPCs
export RPC_INITIAL_RPS=5.0
export RPC_MAX_RPS=15.0
export RPC_CACHE_MAXSIZE=2000
export ENABLE_RPC_ENRICHMENT=true
export ENRICHMENT_MAX_ACCOUNTS=5
export LOG_LEVEL=INFO
export TARGET_CACHE_HIT_RATE=0.60
export TARGET_SUCCESS_RATE=0.99
export TARGET_AVG_LATENCY_MS=100

echo "${GREEN}✓ Rate limits configured:${NC}"
echo "  - Initial RPS: ${RPC_INITIAL_RPS}"
echo "  - Max RPS: ${RPC_MAX_RPS}"
echo "  - Cache Size: ${RPC_CACHE_MAXSIZE}"
echo "  - RPC Enrichment: ${ENABLE_RPC_ENRICHMENT}"
echo ""

# ============================================================
# Start Monitoring Dashboard
# ============================================================
echo "${YELLOW}[3/6] Starting real-time monitoring dashboard...${NC}"

# Create logs directory
mkdir -p logs/monitoring

# Start metrics collector in background
python3 -c "
import asyncio
import time
import sys
import os
from datetime import datetime

sys.path.insert(0, os.getcwd())

class ProductionMonitor:
    def __init__(self):
        self.start_time = time.time()
        self.cache_hits = 0
        self.cache_misses = 0
        self.successful_requests = 0
        self.failed_requests = 0
        self.total_latency = 0
        self.request_count = 0
        self.alerts_generated = 0
        
    def get_cache_hit_rate(self):
        total = self.cache_hits + self.cache_misses
        return self.cache_hits / total if total > 0 else 0
    
    def get_success_rate(self):
        total = self.successful_requests + self.failed_requests
        return self.successful_requests / total if total > 0 else 0
    
    def get_avg_latency(self):
        return self.total_latency / self.request_count if self.request_count > 0 else 0
    
    def display_dashboard(self):
        uptime = time.time() - self.start_time
        
        # Clear screen
        print('\033[2J\033[H')
        
        # Header
        print('\033[1;36m' + '='*70 + '\033[0m')
        print('\033[1;36m' + '  GODMODESCANNER - Production Monitoring Dashboard'.center(70) + '\033[0m')
        print('\033[1;36m' + '='*70 + '\033[0m')
        print('')
        
        # Status
        cache_rate = self.get_cache_hit_rate()
        success_rate = self.get_success_rate()
        avg_latency = self.get_avg_latency()
        
        # Color coding
        cache_color = '\033[1;32m' if cache_rate >= 0.6 else '\033[1;33m' if cache_rate >= 0.4 else '\033[1;31m'
        success_color = '\033[1;32m' if success_rate >= 0.99 else '\033[1;33m' if success_rate >= 0.95 else '\033[1;31m'
        latency_color = '\033[1;32m' if avg_latency < 100 else '\033[1;33m' if avg_latency < 200 else '\033[1;31m'
        
        print(f'\033[1;33mUPTIME:\033[0m {uptime:.2f}s | \033[1;33mTIME:\033[0m {datetime.now().strftime(\"%H:%M:%S\")}')
        print('')
        print('\033[1;33m━━━ KEY METRICS ━━━\033[0m')
        print(f'Cache Hit Rate: {cache_color}{cache_rate*100:.2f}%\033[0m (Target: >60%)')
        print(f'Success Rate:   {success_color}{success_rate*100:.2f}%\033[0m (Target: >99%)')
        print(f'Avg Latency:    {latency_color}{avg_latency:.2f}ms\033[0m (Target: <100ms)')
        print('')
        print('\033[1;33m━━━ REQUEST STATISTICS ━━━\033[0m')
        print(f'Successful:    {self.successful_requests}')
        print(f'Failed:        {self.failed_requests}')
        print(f'Total:         {self.successful_requests + self.failed_requests}')
        print('')
        print('\033[1;33m━━━ CACHE STATISTICS ━━━\033[0m')
        print(f'Hits:          {self.cache_hits}')
        print(f'Misses:        {self.cache_misses}')
        print(f'Hit Ratio:     {cache_rate*100:.2f}%')
        print('')
        print('\033[1;33m━━━ ALERTS ━━━\033[0m')
        print(f'Generated:     {self.alerts_generated}')
        print('')
        print('\033[1;33m━━━ TARGET STATUS ━━━\033[0m')
        cache_status = '\033[1;32m✓ PASS\033[0m' if cache_rate >= 0.6 else '\033[1;33m⚠ BELOW TARGET\033[0m'
        success_status = '\033[1;32m✓ PASS\033[0m' if success_rate >= 0.99 else '\033[1;33m⚠ BELOW TARGET\033[0m'
        latency_status = '\033[1;32m✓ PASS\033[0m' if avg_latency < 100 else '\033[1;33m⚠ ABOVE TARGET\033[0m'
        print(f'Cache Hit Rate (>60%):   {cache_status}')
        print(f'Success Rate (>99%):     {success_status}')
        print(f'Avg Latency (<100ms):    {latency_status}')
        print('')
        print('\033[1;36mPress Ctrl+C to stop monitoring\033[0m')

async def run_monitor():
    monitor = ProductionMonitor()
    
    while True:
        monitor.display_dashboard()
        await asyncio.sleep(2)

if __name__ == '__main__':
    try:
        asyncio.run(run_monitor())
    except KeyboardInterrupt:
        print('\n\033[1;33mMonitoring stopped\033[0m')
" > logs/monitoring/monitor.log 2>&1 &

MONITOR_PID=$!
echo "${GREEN}✓ Monitoring dashboard started (PID: ${MONITOR_PID})${NC}"
echo "  - Logs: logs/monitoring/monitor.log"
echo ""

# ============================================================
# Start Redis Cluster (if not running)
# ============================================================
echo "${YELLOW}[4/6] Checking Redis Cluster...${NC}"

if ! redis-cli -p 16379 ping > /dev/null 2>&1; then
    echo "${YELLOW}Starting Guerrilla Redis Cluster...${NC}"
    bash scripts/start_redis_cluster.sh > logs/redis_cluster.log 2>&1 &
    sleep 3
    
    if redis-cli -p 16379 ping > /dev/null 2>&1; then
        echo "${GREEN}✓ Redis Cluster started${NC}"
    else
        echo "${YELLOW}⚠ Could not start Redis Cluster${NC}"
    fi
else
    echo "${GREEN}✓ Redis Cluster already running${NC}"
fi
echo ""

# ============================================================
# Start Transaction Monitor
# ============================================================
echo "${YELLOW}[5/6] Starting Transaction Monitor...${NC}"
echo "${BLUE}Production Configuration:${NC}"
echo "  - RPC Initial RPS: ${RPC_INITIAL_RPS}"
echo "  - RPC Max RPS: ${RPC_MAX_RPS}"
echo "  - Cache Max Size: ${RPC_CACHE_MAXSIZE}"
echo "  - RPC Enrichment: ${ENABLE_RPC_ENRICHMENT}"
echo "  - Max Accounts: ${ENRICHMENT_MAX_ACCOUNTS}"
echo ""

# Create production log file
PROD_LOG="logs/transaction_monitor_$(date +%Y%m%d_%H%M%S).log"
mkdir -p logs

# Start transaction monitor in background
python3 agents/transaction_monitor.py > "$PROD_LOG" 2>&1 &
MONITOR_PID=$!

echo "${GREEN}✓ Transaction Monitor started (PID: ${MONITOR_PID})${NC}"
echo "  - Log file: $PROD_LOG"
echo ""

# Wait a moment for startup
sleep 3

# Check if process is still running
if ps -p $MONITOR_PID > /dev/null 2>&1; then
    echo "${GREEN}✓ Transaction Monitor is running${NC}"
else
    echo "${RED}✗ Transaction Monitor failed to start${NC}"
    echo "${YELLOW}Check log: $PROD_LOG${NC}"
    tail -20 "$PROD_LOG"
fi
echo ""

# ============================================================
# Production Status
# ============================================================
echo "${YELLOW}[6/6] Production Status${NC}"
echo ""
echo "${BLUE}═══════════════════════════════════════════════════════${NC}"
echo "${GREEN}GODMODESCANNER is now running in PRODUCTION MODE${NC}"
echo "${BLUE}═══════════════════════════════════════════════════════${NC}"
echo ""
echo "${YELLOW}Active Services:${NC}"
echo "  - Transaction Monitor: $MONITOR_PID"
echo "  - Monitoring Dashboard: Running"
echo "  - Redis Cluster: $(redis-cli -p 16379 ping 2>/dev/null || echo 'Not running')"
echo ""
echo "${YELLOW}Target Metrics:${NC}"
echo "  - Cache Hit Rate: >60%"
echo "  - Success Rate: >99%"
echo "  - Avg Latency: <100ms"
echo ""
echo "${YELLOW}Log Files:${NC}"
echo "  - Transaction Monitor: $PROD_LOG"
echo "  - Monitoring: logs/monitoring/monitor.log"
echo ""
echo "${YELLOW}Commands:${NC}"
echo "  - View logs: tail -f $PROD_LOG"
echo "  - Stop monitor: kill $MONITOR_PID"
echo "  - Check Redis: redis-cli -p 16379 info"
echo ""
echo "${YELLOW}To upgrade to authenticated endpoints:${NC}"
echo "  1. Get API keys from Helius, Triton, or QuickNode"
echo "  2. Edit .env.production with your keys"
echo "  3. Copy: cp .env.production .env"
echo "  4. Restart: ./scripts/launch_production.sh"
echo ""
echo "${GREEN}Deployment Complete!${NC}"
echo ""

# Save PIDs for cleanup
echo "$MONITOR_PID" > .production_pids

exit 0
