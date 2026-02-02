#!/bin/bash
# GODMODESCANNER - Parallel Processing Swarm Startup Script
# This script starts the parallel processing pipeline with Redis Streams

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
VENV_PATH="$PROJECT_ROOT/venv"

# Swarm configuration
WALLET_ANALYZER_WORKERS=${WALLET_ANALYZER_WORKERS:-10}
PATTERN_RECOGNITION_WORKERS=${PATTERN_RECOGNITION_WORKERS:-10}
SYBIL_DETECTION_WORKERS=${SYBIL_DETECTION_WORKERS:-10}
REDIS_URL=${REDIS_URL:-"redis://localhost:6379"}

# PIDs file
PIDS_FILE="/tmp/godmodescanner_swarm_pids.txt"

# Logging
LOG_DIR="$PROJECT_ROOT/logs"
mkdir -p "$LOG_DIR"

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

log_step() {
    echo -e "${BLUE}[STEP]${NC} $1"
}

# Check if Redis is running
check_redis() {
    log_step "Checking Redis connection..."
    if redis-cli -u "$REDIS_URL" ping > /dev/null 2>&1; then
        log_info "Redis is running at $REDIS_URL"
        return 0
    else
        log_error "Redis is not running at $REDIS_URL"
        return 1
    fi
}

# Create Redis Streams consumer groups
create_consumer_groups() {
    log_step "Creating Redis Streams consumer groups..."
    
    # Streams
    STREAM_TRANSACTIONS="godmode:new_transactions"
    STREAM_TOKEN_LAUNCHES="godmode:token_launches"
    STREAM_TRADES="godmode:trades"
    STREAM_ALERTS="godmode:alerts"
    STREAM_RISK_SCORES="godmode:risk_scores"
    
    # Groups
    WALLET_ANALYZER_GROUP="wallet-analyzer-group"
    PATTERN_RECOGNITION_GROUP="pattern-recognition-group"
    SYBIL_DETECTION_GROUP="sybil-detection-group"
    RISK_SCORING_GROUP="risk-scoring-group"
    ALERT_MANAGER_GROUP="alert-manager-group"
    
    # Create groups (ignore errors if already exist)
    redis-cli -u "$REDIS_URL" XGROUP CREATE "$STREAM_TRANSACTIONS" "$WALLET_ANALYZER_GROUP" 0 MKSTREAM 2>/dev/null || true
    redis-cli -u "$REDIS_URL" XGROUP CREATE "$STREAM_TRANSACTIONS" "$PATTERN_RECOGNITION_GROUP" 0 MKSTREAM 2>/dev/null || true
    redis-cli -u "$REDIS_URL" XGROUP CREATE "$STREAM_TRANSACTIONS" "$SYBIL_DETECTION_GROUP" 0 MKSTREAM 2>/dev/null || true
    redis-cli -u "$REDIS_URL" XGROUP CREATE "$STREAM_TOKEN_LAUNCHES" "$WALLET_ANALYZER_GROUP" 0 MKSTREAM 2>/dev/null || true
    redis-cli -u "$REDIS_URL" XGROUP CREATE "$STREAM_TRADES" "$WALLET_ANALYZER_GROUP" 0 MKSTREAM 2>/dev/null || true
    redis-cli -u "$REDIS_URL" XGROUP CREATE "$STREAM_ALERTS" "$ALERT_MANAGER_GROUP" 0 MKSTREAM 2>/dev/null || true
    redis-cli -u "$REDIS_URL" XGROUP CREATE "$STREAM_RISK_SCORES" "$ALERT_MANAGER_GROUP" 0 MKSTREAM 2>/dev/null || true
    redis-cli -u "$REDIS_URL" XGROUP CREATE "$STREAM_TRADES" "$RISK_SCORING_GROUP" 0 MKSTREAM 2>/dev/null || true
    
    log_info "Consumer groups created successfully"
}

# Start Transaction Monitor with Streams
start_transaction_monitor() {
    log_step "Starting Transaction Monitor (Streams)..."
    cd "$PROJECT_ROOT"
    
    source "$VENV_PATH/bin/activate"
    nohup python -m agents.transaction_monitor_streams > "$LOG_DIR/transaction_monitor_streams.log" 2>&1 &
    TM_PID=$!
    
    echo "$TM_PID" >> "$PIDS_FILE"
    log_info "Transaction Monitor started with PID $TM_PID"
}

# Start Wallet Analyzer Workers
start_wallet_analyzer_workers() {
    log_step "Starting $WALLET_ANALYZER_WORKERS Wallet Analyzer workers..."
    cd "$PROJECT_ROOT"
    
    source "$VENV_PATH/bin/activate"
    
    for i in $(seq 1 $WALLET_ANALYZER_WORKERS); do
        nohup python -c "
import asyncio
import sys
sys.path.insert(0, '.');
from utils.swarm_manager import start_worker_swarm
asyncio.run(start_worker_swarm('wallet-analyzer', '$REDIS_URL', count=1, offset=$i))
" > "$LOG_DIR/wallet_analyzer_worker_$i.log" 2>&1 &
        PID=$!
        echo "$PID" >> "$PIDS_FILE"
        log_info "Wallet Analyzer worker $i started with PID $PID"
    done
}

# Start Pattern Recognition Workers
start_pattern_recognition_workers() {
    log_step "Starting $PATTERN_RECOGNITION_WORKERS Pattern Recognition workers..."
    cd "$PROJECT_ROOT"
    
    source "$VENV_PATH/bin/activate"
    
    for i in $(seq 1 $PATTERN_RECOGNITION_WORKERS); do
        nohup python -c "
import asyncio
import sys
sys.path.insert(0, '.');
from utils.swarm_manager import start_worker_swarm
asyncio.run(start_worker_swarm('pattern-recognition', '$REDIS_URL', count=1, offset=$i))
" > "$LOG_DIR/pattern_recognition_worker_$i.log" 2>&1 &
        PID=$!
        echo "$PID" >> "$PIDS_FILE"
        log_info "Pattern Recognition worker $i started with PID $PID"
    done
}

# Start Sybil Detection Workers
start_sybil_detection_workers() {
    log_step "Starting $SYBIL_DETECTION_WORKERS Sybil Detection workers..."
    cd "$PROJECT_ROOT"
    
    source "$VENV_PATH/bin/activate"
    
    for i in $(seq 1 $SYBIL_DETECTION_WORKERS); do
        nohup python -c "
import asyncio
import sys
sys.path.insert(0, '.');
from utils.swarm_manager import start_worker_swarm
asyncio.run(start_worker_swarm('sybil-detection', '$REDIS_URL', count=1, offset=$i))
" > "$LOG_DIR/sybil_detection_worker_$i.log" 2>&1 &
        PID=$!
        echo "$PID" >> "$PIDS_FILE"
        log_info "Sybil Detection worker $i started with PID $PID"
    done
}

# Start Backpressure Monitor
start_backpressure_monitor() {
    log_step "Starting Backpressure Monitor..."
    cd "$PROJECT_ROOT"
    
    source "$VENV_PATH/bin/activate"
    nohup python -m utils.backpressure_monitor --redis-url "$REDIS_URL" > "$LOG_DIR/backpressure_monitor.log" 2>&1 &
    BPM_PID=$!
    
    echo "$BPM_PID" >> "$PIDS_FILE"
    log_info "Backpressure Monitor started with PID $BPM_PID"
}

# Show swarm status
show_status() {
    log_step "Swarm Status:"
    echo ""
    echo "Redis URL: $REDIS_URL"
    echo "Wallet Analyzer Workers: $WALLET_ANALYZER_WORKERS"
    echo "Pattern Recognition Workers: $PATTERN_RECOGNITION_WORKERS"
    echo "Sybil Detection Workers: $SYBIL_DETECTION_WORKERS"
    echo ""
    echo "Total Processes: $(wc -l < "$PIDS_FILE")"
    echo "PIDs File: $PIDS_FILE"
    echo "Log Directory: $LOG_DIR"
    echo ""
    echo "Log Files:"
    ls -la "$LOG_DIR" | grep -E "(transaction_monitor|wallet_analyzer|pattern_recognition|sybil_detection|backpressure)" | awk '{print "  " $9}'
    echo ""
}

# Cleanup function
cleanup() {
    log_warn "Stopping swarm..."
    if [ -f "$PIDS_FILE" ]; then
        while read pid; do
            kill $pid 2>/dev/null || true
        done < "$PIDS_FILE"
        rm -f "$PIDS_FILE"
        log_info "Swarm stopped"
    fi
}

# Trap signals
trap cleanup SIGINT SIGTERM

# Main function
main() {
    echo ""
    echo "╔═══════════════════════════════════════════════════════════╗"
    echo "║  GODMODESCANNER - Parallel Processing Swarm Startup      ║"
    echo "╚═══════════════════════════════════════════════════════════╝"
    echo ""
    
    # Clear PIDs file
    > "$PIDS_FILE"
    
    # Check Redis
    if ! check_redis; then
        log_error "Redis is not available. Please start Redis first."
        exit 1
    fi
    
    # Create consumer groups
    create_consumer_groups
    
    # Start components
    start_transaction_monitor
    start_wallet_analyzer_workers
    start_pattern_recognition_workers
    start_sybil_detection_workers
    start_backpressure_monitor
    
    # Show status
    show_status
    
    log_info "Swarm started successfully!"
    echo ""
    log_info "Monitor logs: tail -f $LOG_DIR/*.log"
    log_info "Stop swarm: kill \$(cat $PIDS_FILE)"
    echo ""
    
    # Wait for processes
    wait
}

# Run main
main
