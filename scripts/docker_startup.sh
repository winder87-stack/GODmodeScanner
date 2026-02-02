#!/bin/bash
# GODMODESCANNER Docker Startup Script
# Builds images and starts the multi-agent system

set -e  # Exit on error

echo "="*80
echo "🚀 GODMODESCANNER - Docker Deployment"
echo "="*80
echo ""

# Colors for output
RED='[0;31m'
GREEN='[0;32m'
YELLOW='[1;33m'
NC='[0m' # No Color

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    echo -e "${RED}❌ Docker is not running. Please start Docker first.${NC}"
    exit 1
fi

echo -e "${GREEN}✅ Docker is running${NC}"

# Check if docker-compose is available
if ! command -v docker-compose &> /dev/null; then
    echo -e "${YELLOW}⚠️  docker-compose not found, using 'docker compose' instead${NC}"
    COMPOSE_CMD="docker compose"
else
    COMPOSE_CMD="docker-compose"
fi

# Parse command line arguments
MODE=${1:-"up"}  # Default to 'up'
PROFILE=${2:-""}  # Optional profile (e.g., 'monitoring')

case $MODE in
    build)
        echo -e "${YELLOW}🔨 Building Docker images...${NC}"
        $COMPOSE_CMD build --no-cache
        echo -e "${GREEN}✅ Build complete${NC}"
        ;;

    up)
        echo -e "${YELLOW}🚀 Starting GODMODESCANNER services...${NC}"

        # Build images first
        echo -e "${YELLOW}🔨 Building images...${NC}"
        $COMPOSE_CMD build

        # Start services
        if [ -n "$PROFILE" ]; then
            echo -e "${YELLOW}📊 Starting with profile: $PROFILE${NC}"
            $COMPOSE_CMD --profile $PROFILE up -d
        else
            $COMPOSE_CMD up -d
        fi

        echo -e "${GREEN}✅ Services started${NC}"
        echo ""
        echo -e "${YELLOW}📋 Running services:${NC}"
        $COMPOSE_CMD ps
        echo ""
        echo -e "${GREEN}🎯 GODMODESCANNER is now running!${NC}"
        echo -e "${YELLOW}📊 View logs: ./scripts/docker_startup.sh logs${NC}"
        echo -e "${YELLOW}🔍 Check status: ./scripts/docker_startup.sh status${NC}"
        ;;

    down)
        echo -e "${YELLOW}🛑 Stopping GODMODESCANNER services...${NC}"
        $COMPOSE_CMD down
        echo -e "${GREEN}✅ Services stopped${NC}"
        ;;

    restart)
        echo -e "${YELLOW}🔄 Restarting GODMODESCANNER services...${NC}"
        $COMPOSE_CMD restart
        echo -e "${GREEN}✅ Services restarted${NC}"
        ;;

    logs)
        SERVICE=${2:-""}
        if [ -n "$SERVICE" ]; then
            echo -e "${YELLOW}📝 Showing logs for $SERVICE...${NC}"
            $COMPOSE_CMD logs -f $SERVICE
        else
            echo -e "${YELLOW}📝 Showing all logs...${NC}"
            $COMPOSE_CMD logs -f
        fi
        ;;

    status)
        echo -e "${YELLOW}📊 Service Status:${NC}"
        $COMPOSE_CMD ps
        echo ""
        echo -e "${YELLOW}🔍 Container Health:${NC}"
        docker ps --filter "name=godmode" --format "table {{.Names}}	{{.Status}}	{{.Ports}}"
        ;;

    clean)
        echo -e "${RED}🧹 Cleaning up containers, volumes, and images...${NC}"
        read -p "Are you sure? This will remove all data! (y/N) " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            $COMPOSE_CMD down -v --rmi all
            echo -e "${GREEN}✅ Cleanup complete${NC}"
        else
            echo -e "${YELLOW}⚠️  Cleanup cancelled${NC}"
        fi
        ;;

    shell)
        SERVICE=${2:-"supervisor"}
        echo -e "${YELLOW}🐚 Opening shell in $SERVICE...${NC}"
        $COMPOSE_CMD exec $SERVICE /bin/bash
        ;;

    spawn)
        AGENT_TYPE=${2:-"transaction_monitor"}
        echo -e "${YELLOW}🎯 Spawning $AGENT_TYPE agent...${NC}"

        # Send spawn command via Redis
        docker exec godmode_redis redis-cli PUBLISH supervisor_commands "{"type":"spawn","agent_type":"$AGENT_TYPE"}"

        echo -e "${GREEN}✅ Spawn command sent${NC}"
        ;;

    monitoring)
        echo -e "${YELLOW}📊 Starting with monitoring stack (Prometheus + Grafana)...${NC}"
        $COMPOSE_CMD --profile monitoring up -d
        echo -e "${GREEN}✅ Monitoring stack started${NC}"
        echo -e "${YELLOW}📊 Prometheus: http://localhost:9090${NC}"
        echo -e "${YELLOW}📈 Grafana: http://localhost:3000 (admin/admin)${NC}"
        ;;

    help|--help|-h)
        echo "GODMODESCANNER Docker Startup Script"
        echo ""
        echo "Usage: $0 [command] [options]"
        echo ""
        echo "Commands:"
        echo "  build              Build Docker images"
        echo "  up [profile]       Start services (optional: monitoring profile)"
        echo "  down               Stop services"
        echo "  restart            Restart services"
        echo "  logs [service]     Show logs (optional: specific service)"
        echo "  status             Show service status"
        echo "  clean              Remove all containers, volumes, and images"
        echo "  shell [service]    Open shell in service (default: supervisor)"
        echo "  spawn [type]       Spawn new agent (default: transaction_monitor)"
        echo "  monitoring         Start with monitoring stack"
        echo "  help               Show this help message"
        echo ""
        echo "Examples:"
        echo "  $0 up                    # Start all services"
        echo "  $0 up monitoring         # Start with Prometheus + Grafana"
        echo "  $0 logs supervisor       # Show supervisor logs"
        echo "  $0 spawn wallet_analyzer # Spawn wallet analyzer agent"
        echo "  $0 shell orchestrator    # Open shell in orchestrator"
        ;;

    *)
        echo -e "${RED}❌ Unknown command: $MODE${NC}"
        echo "Run '$0 help' for usage information"
        exit 1
        ;;
esac
