# GODMODESCANNER - Docker Deployment Guide

## 🚀 Quick Start

### Prerequisites
- Docker 20.10+
- Docker Compose 2.0+
- 4GB+ RAM available
- 10GB+ disk space

### Start the System

```bash
# Build and start all services
./scripts/docker_startup.sh up

# Or with monitoring stack (Prometheus + Grafana)
./scripts/docker_startup.sh up monitoring
```

### Check Status

```bash
# View service status
./scripts/docker_startup.sh status

# View logs
./scripts/docker_startup.sh logs

# View specific service logs
./scripts/docker_startup.sh logs supervisor
```

## 📦 Architecture

### Services

1. **Redis** - Message broker and agent registry
   - Port: 6379
   - Persistent storage with AOF

2. **Orchestrator** - Top-level coordinator
   - Manages supervisor lifecycle
   - Docker-in-Docker enabled

3. **Supervisor** - Agent lifecycle manager
   - Spawns and manages subordinate agents
   - Docker container spawning
   - Auto-scaling based on workload

4. **Agent Templates** - Dynamic agent containers
   - Transaction Monitor
   - Wallet Analyzer
   - Pattern Recognition
   - Sybil Detection
   - Risk Scoring
   - Alert Manager

5. **Prometheus** (optional) - Metrics collection
   - Port: 9090
   - Scrapes agent metrics

6. **Grafana** (optional) - Metrics visualization
   - Port: 3000
   - Default credentials: admin/admin

### Network

All services run on the `godmode_network` bridge network (172.28.0.0/16).

## 🔧 Operations

### Spawning Agents

```bash
# Spawn a transaction monitor
./scripts/docker_startup.sh spawn transaction_monitor

# Spawn a wallet analyzer
./scripts/docker_startup.sh spawn wallet_analyzer

# Spawn a pattern recognition agent
./scripts/docker_startup.sh spawn pattern_recognition
```

### Accessing Containers

```bash
# Open shell in supervisor
./scripts/docker_startup.sh shell supervisor

# Open shell in orchestrator
./scripts/docker_startup.sh shell orchestrator

# Open shell in Redis
docker exec -it godmode_redis redis-cli
```

### Viewing Logs

```bash
# All logs
./scripts/docker_startup.sh logs

# Specific service
./scripts/docker_startup.sh logs supervisor
./scripts/docker_startup.sh logs orchestrator
./scripts/docker_startup.sh logs redis
```

### Restarting Services

```bash
# Restart all services
./scripts/docker_startup.sh restart

# Restart specific service
docker-compose restart supervisor
```

### Stopping Services

```bash
# Stop all services
./scripts/docker_startup.sh down

# Stop and remove volumes
docker-compose down -v
```

## 🐳 Docker-in-Docker (DinD)

The supervisor and orchestrator have Docker socket access for dynamic agent spawning:

```yaml
volumes:
  - /var/run/docker.sock:/var/run/docker.sock
```

This enables:
- Dynamic container creation
- Container lifecycle management
- Resource isolation per agent
- Horizontal scaling

## 📊 Monitoring

### Enable Monitoring Stack

```bash
./scripts/docker_startup.sh monitoring
```

### Access Dashboards

- **Prometheus**: http://localhost:9090
- **Grafana**: http://localhost:3000 (admin/admin)

### Metrics Available

- Agent CPU/Memory usage
- Task processing rates
- Error rates
- Heartbeat status
- Container health

## 🔍 Troubleshooting

### Container Won't Start

```bash
# Check logs
docker-compose logs [service_name]

# Check container status
docker ps -a | grep godmode

# Rebuild image
docker-compose build --no-cache [service_name]
```

### Redis Connection Issues

```bash
# Test Redis connectivity
docker exec godmode_redis redis-cli ping

# Check Redis logs
docker-compose logs redis
```

### Agent Not Spawning

```bash
# Check supervisor logs
docker-compose logs supervisor

# Verify Docker socket access
docker exec godmode_supervisor docker ps

# Check Redis for spawn commands
docker exec godmode_redis redis-cli MONITOR
```

### Out of Memory

```bash
# Check container resource usage
docker stats

# Increase Docker memory limit in Docker Desktop settings
# Recommended: 4GB minimum, 8GB optimal
```

## 🧹 Cleanup

### Remove All Containers and Volumes

```bash
./scripts/docker_startup.sh clean
```

### Remove Specific Service

```bash
docker-compose rm -f [service_name]
```

### Prune Unused Resources

```bash
# Remove unused containers
docker container prune

# Remove unused images
docker image prune -a

# Remove unused volumes
docker volume prune
```

## 🔐 Security

### Environment Variables

Create `.env` file for sensitive data:

```bash
REDIS_PASSWORD=your_secure_password
GRAFANA_ADMIN_PASSWORD=your_admin_password
```

### Network Isolation

All services run on isolated bridge network. External access only through exposed ports.

### Volume Permissions

Ensure proper permissions on mounted volumes:

```bash
chmod -R 755 ./config
chmod -R 755 ./data
chmod -R 755 ./logs
```

## 📈 Scaling

### Horizontal Scaling

```bash
# Scale supervisor to 3 instances
docker-compose up -d --scale supervisor=3
```

### Vertical Scaling

Modify `docker-compose.yml`:

```yaml
services:
  supervisor:
    deploy:
      resources:
        limits:
          cpus: '2.0'
          memory: 2G
        reservations:
          cpus: '1.0'
          memory: 1G
```

## 🚀 Production Deployment

### Recommended Configuration

```yaml
services:
  redis:
    restart: always
    deploy:
      resources:
        limits:
          memory: 512M

  supervisor:
    restart: always
    deploy:
      replicas: 2
      resources:
        limits:
          cpus: '1.0'
          memory: 1G
```

### Health Checks

All services include health checks:

```bash
# View health status
docker-compose ps

# Check specific service health
docker inspect godmode_supervisor | jq '.[0].State.Health'
```

## 📚 Additional Resources

- [Docker Documentation](https://docs.docker.com/)
- [Docker Compose Reference](https://docs.docker.com/compose/compose-file/)
- [Redis Documentation](https://redis.io/documentation)
- [Prometheus Documentation](https://prometheus.io/docs/)
- [Grafana Documentation](https://grafana.com/docs/)

## 🆘 Support

For issues and questions:
1. Check logs: `./scripts/docker_startup.sh logs`
2. Verify status: `./scripts/docker_startup.sh status`
3. Review this documentation
4. Open an issue on GitHub
