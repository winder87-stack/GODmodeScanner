# GODMODESCANNER Makefile
# Simplifies common Docker operations

.PHONY: help build up down restart logs status clean shell spawn monitoring test

# Default target
.DEFAULT_GOAL := help

# Colors
RED := [0;31m
GREEN := [0;32m
YELLOW := [1;33m
BLUE := [0;34m
NC := [0m # No Color

# Variables
COMPOSE := docker-compose
PROJECT := godmodescanner

help: ## Show this help message
@echo "$(BLUE)GODMODESCANNER - Docker Operations$(NC)"
@echo ""
@echo "$(YELLOW)Available targets:$(NC)"
@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  $(GREEN)%-20s$(NC) %s\n", $$1, $$2}'
@echo ""
@echo "$(YELLOW)Examples:$(NC)"
@echo "  make build          # Build all images"
@echo "  make up             # Start all services"
@echo "  make logs           # View all logs"
@echo "  make spawn TYPE=tx  # Spawn transaction monitor"

build: ## Build all Docker images
@echo "$(YELLOW)🔨 Building Docker images...$(NC)"
$(COMPOSE) build
@echo "$(GREEN)✅ Build complete$(NC)"

build-nc: ## Build all images without cache
@echo "$(YELLOW)🔨 Building Docker images (no cache)...$(NC)"
$(COMPOSE) build --no-cache
@echo "$(GREEN)✅ Build complete$(NC)"

up: ## Start all services
@echo "$(YELLOW)🚀 Starting GODMODESCANNER...$(NC)"
$(COMPOSE) build
$(COMPOSE) up -d
@echo "$(GREEN)✅ Services started$(NC)"
@make status

down: ## Stop all services
@echo "$(YELLOW)🛑 Stopping GODMODESCANNER...$(NC)"
$(COMPOSE) down
@echo "$(GREEN)✅ Services stopped$(NC)"

restart: ## Restart all services
@echo "$(YELLOW)🔄 Restarting GODMODESCANNER...$(NC)"
$(COMPOSE) restart
@echo "$(GREEN)✅ Services restarted$(NC)"

logs: ## Show logs for all services
$(COMPOSE) logs -f

logs-supervisor: ## Show supervisor logs
$(COMPOSE) logs -f supervisor

logs-orchestrator: ## Show orchestrator logs
$(COMPOSE) logs -f orchestrator

logs-redis: ## Show Redis logs
$(COMPOSE) logs -f redis

status: ## Show service status
@echo "$(YELLOW)📊 Service Status:$(NC)"
@$(COMPOSE) ps
@echo ""
@echo "$(YELLOW)🔍 Container Health:$(NC)"
@docker ps --filter "name=godmode" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

shell: ## Open shell in supervisor (use SERVICE=name for other services)
@echo "$(YELLOW)🐚 Opening shell in $(or $(SERVICE),supervisor)...$(NC)"
$(COMPOSE) exec $(or $(SERVICE),supervisor) /bin/bash

shell-redis: ## Open Redis CLI
@echo "$(YELLOW)🐚 Opening Redis CLI...$(NC)"
docker exec -it godmode_redis redis-cli

spawn: ## Spawn agent (use TYPE=transaction_monitor, wallet_analyzer, etc.)
@echo "$(YELLOW)🎯 Spawning $(or $(TYPE),transaction_monitor) agent...$(NC)"
docker exec godmode_redis redis-cli PUBLISH supervisor_commands '{"type":"spawn","agent_type":"$(or $(TYPE),transaction_monitor)"}'
@echo "$(GREEN)✅ Spawn command sent$(NC)"

monitoring: ## Start with monitoring stack (Prometheus + Grafana)
@echo "$(YELLOW)📊 Starting with monitoring stack...$(NC)"
$(COMPOSE) --profile monitoring up -d
@echo "$(GREEN)✅ Monitoring stack started$(NC)"
@echo "$(YELLOW)📊 Prometheus: http://localhost:9090$(NC)"
@echo "$(YELLOW)📈 Grafana: http://localhost:3000 (admin/admin)$(NC)"

clean: ## Remove all containers and volumes
@echo "$(RED)🧹 Cleaning up...$(NC)"
@read -p "Are you sure? This will remove all data! (y/N) " -n 1 -r; \
echo; \
if [[ $$REPLY =~ ^[Yy]$$ ]]; then \
$(COMPOSE) down -v; \
echo "$(GREEN)✅ Cleanup complete$(NC)"; \
else \
echo "$(YELLOW)⚠️  Cleanup cancelled$(NC)"; \
fi

clean-all: ## Remove containers, volumes, and images
@echo "$(RED)🧹 Deep cleaning...$(NC)"
@read -p "Are you sure? This will remove everything! (y/N) " -n 1 -r; \
echo; \
if [[ $$REPLY =~ ^[Yy]$$ ]]; then \
$(COMPOSE) down -v --rmi all; \
echo "$(GREEN)✅ Deep cleanup complete$(NC)"; \
else \
echo "$(YELLOW)⚠️  Cleanup cancelled$(NC)"; \
fi

test: ## Run tests
@echo "$(YELLOW)🧪 Running tests...$(NC)"
python -m pytest tests/ -v
@echo "$(GREEN)✅ Tests complete$(NC)"

test-docker: ## Run tests in Docker
@echo "$(YELLOW)🧪 Running tests in Docker...$(NC)"
$(COMPOSE) exec supervisor python -m pytest /app/tests/ -v
@echo "$(GREEN)✅ Tests complete$(NC)"

prune: ## Prune unused Docker resources
@echo "$(YELLOW)🧹 Pruning unused Docker resources...$(NC)"
docker system prune -f
@echo "$(GREEN)✅ Prune complete$(NC)"

ps: ## Show running containers
@docker ps --filter "name=godmode" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

top: ## Show container resource usage
@docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.NetIO}}"

inspect: ## Inspect service (use SERVICE=name)
@echo "$(YELLOW)🔍 Inspecting $(or $(SERVICE),supervisor)...$(NC)"
$(COMPOSE) exec $(or $(SERVICE),supervisor) env

network: ## Show network information
@echo "$(YELLOW)🌐 Network Information:$(NC)"
@docker network inspect godmode_network | jq '.[0].Containers'

volumes: ## Show volume information
@echo "$(YELLOW)💾 Volume Information:$(NC)"
@docker volume ls --filter "name=godmodescanner"

backup: ## Backup data volumes
@echo "$(YELLOW)💾 Backing up data...$(NC)"
@mkdir -p backups
@docker run --rm -v godmodescanner_redis_data:/data -v $(PWD)/backups:/backup alpine tar czf /backup/redis_backup_$$(date +%Y%m%d_%H%M%S).tar.gz -C /data .
@echo "$(GREEN)✅ Backup complete$(NC)"

restore: ## Restore data from backup (use BACKUP=filename)
@echo "$(YELLOW)💾 Restoring data from $(BACKUP)...$(NC)"
@docker run --rm -v godmodescanner_redis_data:/data -v $(PWD)/backups:/backup alpine tar xzf /backup/$(BACKUP) -C /data
@echo "$(GREEN)✅ Restore complete$(NC)"

dev: ## Start in development mode (local code mounting)
@echo "$(YELLOW)🔧 Starting in development mode...$(NC)"
$(COMPOSE) -f docker-compose.yml -f docker-compose.dev.yml up -d
@echo "$(GREEN)✅ Development mode started$(NC)"

prod: ## Start in production mode
@echo "$(YELLOW)🚀 Starting in production mode...$(NC)"
$(COMPOSE) -f docker-compose.yml -f docker-compose.prod.yml up -d
@echo "$(GREEN)✅ Production mode started$(NC)"

scale: ## Scale service (use SERVICE=name COUNT=n)
@echo "$(YELLOW)📈 Scaling $(SERVICE) to $(COUNT) instances...$(NC)"
$(COMPOSE) up -d --scale $(SERVICE)=$(COUNT)
@echo "$(GREEN)✅ Scaling complete$(NC)"

health: ## Check service health
@echo "$(YELLOW)🏥 Checking service health...$(NC)"
@for service in $$(docker ps --filter "name=godmode" --format "{{.Names}}"); do \
echo "Checking $$service..."; \
docker inspect $$service | jq '.[0].State.Health // "No health check"'; \
done

update: ## Pull latest images and restart
@echo "$(YELLOW)🔄 Updating images...$(NC)"
$(COMPOSE) pull
$(COMPOSE) up -d
@echo "$(GREEN)✅ Update complete$(NC)"

version: ## Show version information
@echo "$(BLUE)GODMODESCANNER Version Information$(NC)"
@echo "Docker: $$(docker --version)"
@echo "Docker Compose: $$(docker-compose --version)"
@echo "Python: $$(python --version)"
