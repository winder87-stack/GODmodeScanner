#!/bin/bash

################################################################################
# God Mode Supervisor - Startup Script
# 
# This script starts the God Mode Supervisor agent for GODMODESCANNER.
# The supervisor autonomously monitors and manages the entire infrastructure.
#
# Usage:
#   ./scripts/start_god_mode_supervisor.sh [start|stop|status|restart]
################################################################################

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
PROJECT_ROOT="/a0/usr/projects/godmodescanner/projects/godmodescanner"
SUPERVISOR_SCRIPT="${PROJECT_ROOT}/agents/god_mode_supervisor.py"
PID_FILE="${PROJECT_ROOT}/logs/god_mode_supervisor.pid"
LOG_FILE="${PROJECT_ROOT}/logs/god_mode_supervisor.log"
REDIS_PORT=16379

# Functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

check_prerequisites() {
    log_info "Checking prerequisites..."
    
    # Check if Redis cluster is running
    if ! redis-cli -p ${REDIS_PORT} PING > /dev/null 2>&1; then
        log_error "Redis cluster not running on port ${REDIS_PORT}"
        log_info "Start Redis cluster first: ./scripts/start_redis_cluster.sh"
        exit 1
    fi
    log_success "Redis cluster is running"
    
    # Check if supervisor script exists
    if [ ! -f "${SUPERVISOR_SCRIPT}" ]; then
        log_error "Supervisor script not found: ${SUPERVISOR_SCRIPT}"
        exit 1
    fi
    log_success "Supervisor script found"
    
    # Check if Agent Zero is initialized
    if [ ! -d "${PROJECT_ROOT}/agentzero" ]; then
        log_error "Agent Zero framework not initialized"
        exit 1
    fi
    log_success "Agent Zero framework initialized"
    
    # Check if .env file exists
    if [ ! -f "${PROJECT_ROOT}/.env" ]; then
        log_warning ".env file not found, using defaults"
    else
        log_success ".env file found"
    fi
    
    # Create logs directory if needed
    mkdir -p "${PROJECT_ROOT}/logs"
    
    log_success "All prerequisites met"
}

start_supervisor() {
    log_info "Starting God Mode Supervisor..."
    
    # Check if already running
    if [ -f "${PID_FILE}" ]; then
        PID=$(cat "${PID_FILE}")
        if ps -p ${PID} > /dev/null 2>&1; then
            log_warning "Supervisor already running (PID: ${PID})"
            return 0
        else
            log_warning "Stale PID file found, removing..."
            rm -f "${PID_FILE}"
        fi
    fi
    
    # Check prerequisites
    check_prerequisites
    
    # Start supervisor in background
    cd "${PROJECT_ROOT}"
    nohup python "${SUPERVISOR_SCRIPT}" >> "${LOG_FILE}" 2>&1 &
    SUPERVISOR_PID=$!
    
    # Save PID
    echo ${SUPERVISOR_PID} > "${PID_FILE}"
    
    # Wait a moment and verify it started
    sleep 2
    if ps -p ${SUPERVISOR_PID} > /dev/null 2>&1; then
        log_success "God Mode Supervisor started (PID: ${SUPERVISOR_PID})"
        log_info "Log file: ${LOG_FILE}"
        log_info "Monitor with: tail -f ${LOG_FILE}"
        
        # Show initial health check
        sleep 3
        show_status
    else
        log_error "Failed to start supervisor"
        log_info "Check logs: tail -f ${LOG_FILE}"
        rm -f "${PID_FILE}"
        exit 1
    fi
}

stop_supervisor() {
    log_info "Stopping God Mode Supervisor..."
    
    if [ ! -f "${PID_FILE}" ]; then
        log_warning "Supervisor not running (no PID file)"
        return 0
    fi
    
    PID=$(cat "${PID_FILE}")
    
    if ! ps -p ${PID} > /dev/null 2>&1; then
        log_warning "Supervisor not running (stale PID file)"
        rm -f "${PID_FILE}"
        return 0
    fi
    
    # Send SIGTERM for graceful shutdown
    log_info "Sending SIGTERM to PID ${PID}..."
    kill -TERM ${PID}
    
    # Wait for shutdown (max 30 seconds)
    for i in {1..30}; do
        if ! ps -p ${PID} > /dev/null 2>&1; then
            log_success "Supervisor stopped gracefully"
            rm -f "${PID_FILE}"
            return 0
        fi
        sleep 1
    done
    
    # Force kill if still running
    log_warning "Supervisor did not stop gracefully, forcing..."
    kill -9 ${PID}
    rm -f "${PID_FILE}"
    log_success "Supervisor stopped (forced)"
}

show_status() {
    log_info "God Mode Supervisor Status:"
    echo ""
    
    # Check if running
    if [ -f "${PID_FILE}" ]; then
        PID=$(cat "${PID_FILE}")
        if ps -p ${PID} > /dev/null 2>&1; then
            echo -e "${GREEN}● Running${NC} (PID: ${PID})"
            
            # Get process info
            CPU=$(ps -p ${PID} -o %cpu --no-headers | xargs)
            MEM=$(ps -p ${PID} -o %mem --no-headers | xargs)
            UPTIME=$(ps -p ${PID} -o etime --no-headers | xargs)
            
            echo "  CPU: ${CPU}%"
            echo "  Memory: ${MEM}%"
            echo "  Uptime: ${UPTIME}"
        else
            echo -e "${RED}● Stopped${NC} (stale PID file)"
        fi
    else
        echo -e "${RED}● Stopped${NC}"
    fi
    
    echo ""
    
    # Check Redis cluster
    if redis-cli -p ${REDIS_PORT} PING > /dev/null 2>&1; then
        echo -e "Redis Cluster: ${GREEN}● Running${NC}"
        
        # Get cluster info
        CLUSTER_SIZE=$(redis-cli -p ${REDIS_PORT} CLUSTER NODES | wc -l)
        echo "  Nodes: ${CLUSTER_SIZE}"
    else
        echo -e "Redis Cluster: ${RED}● Stopped${NC}"
    fi
    
    echo ""
    
    # Check latest health data
    if redis-cli -p ${REDIS_PORT} PING > /dev/null 2>&1; then
        log_info "Latest Health Data:"
        redis-cli -p ${REDIS_PORT} XREVRANGE godmode:system_health + - COUNT 1 2>/dev/null || echo "  No health data available"
    fi
    
    echo ""
    log_info "Log file: ${LOG_FILE}"
}

restart_supervisor() {
    log_info "Restarting God Mode Supervisor..."
    stop_supervisor
    sleep 2
    start_supervisor
}

# Main
case "${1:-start}" in
    start)
        start_supervisor
        ;;
    stop)
        stop_supervisor
        ;;
    status)
        show_status
        ;;
    restart)
        restart_supervisor
        ;;
    *)
        echo "Usage: $0 {start|stop|status|restart}"
        exit 1
        ;;
esac
