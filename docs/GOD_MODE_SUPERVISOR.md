# God Mode Supervisor - Autonomous System Orchestration

**Version**: 1.0.0  
**Created**: 2026-01-25  
**Agent**: God Mode Supervisor (Master Orchestrator)

---

## Overview

The **God Mode Supervisor** is the master orchestrator agent for GODMODESCANNER that autonomously monitors and manages the entire infrastructure using Agent Zero's hierarchical agent framework.

### Key Capabilities

✅ **System Health Monitoring**
- Monitors 6-node Guerrilla Redis Cluster
- Tracks 30+ parallel worker threads
- Checks queue depths across 4 Redis Streams
- Publishes health metrics every 60 seconds

✅ **Auto-Scaling**
- Detects when risk_scores queue exceeds 1000 items
- Spawns 1-5 additional risk_assessor instances
- Uses Agent Zero orchestrator profile for coordination
- Verifies new instances connect and begin processing

✅ **Infrastructure Management**
- Detects RPC rate limiting (429 errors)
- Delegates to developer agent for endpoint rotation
- Updates .env configuration dynamically
- Broadcasts config updates via Redis pub/sub

✅ **Maintenance Scheduling**
- Triggers memory cleanup every hour
- Prunes FAISS vector storage (entries >7 days)
- Generates cleanup reports
- Publishes metrics to system_health stream

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                  God Mode Supervisor                        │
│              (Master Orchestrator Agent)                    │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌──────────────────────────────────────────────────────┐  │
│  │         Monitoring Loop (60s interval)               │  │
│  │                                                      │  │
│  │  1. Check system health (godmode:system_health)     │  │
│  │  2. Check queue depths (4 Redis Streams)            │  │
│  │  3. Auto-scale if needed (queue > 1000)             │  │
│  │  4. Handle rate limiting (429 errors)               │  │
│  │  5. Schedule memory cleanup (hourly)                │  │
│  │  6. Publish supervisor heartbeat                    │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐  │
│  │        Agent Zero Subordinate Delegation             │  │
│  │                                                      │  │
│  │  • Orchestrator → Auto-scale risk_assessors         │  │
│  │  • Developer → Handle RPC rate limiting             │  │
│  │  • Developer → Memory cleanup (memory_curator)      │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐  │
│  │              Monitored Resources                     │  │
│  │                                                      │  │
│  │  • Redis Cluster: 6 nodes (3 masters, 3 replicas)   │  │
│  │  • Workers: 30+ parallel threads                    │  │
│  │  • Streams: 4 primary queues                        │  │
│  │  • Agents: 47+ specialized agents                   │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

---

## Configuration

### Environment Variables

The supervisor reads configuration from `.env`:

```bash
# Redis Configuration
REDIS_URL=redis://127.0.0.1:16379

# RPC Endpoints (for rate limit handling)
RPC_ENDPOINTS=https://api.mainnet-beta.solana.com,https://solana-api.projectserum.com,https://rpc.ankr.com/solana

# Monitoring Settings (optional)
CHECK_INTERVAL=60  # Seconds between health checks
QUEUE_THRESHOLD=1000  # Auto-scale threshold
MEMORY_CLEANUP_INTERVAL=3600  # 1 hour
```

### Supervisor Settings

You can customize the supervisor behavior by modifying `agents/god_mode_supervisor.py`:

```python
class GodModeSupervisor:
    def __init__(self, config_path: Optional[str] = None):
        # Monitoring interval (seconds)
        self.check_interval = 60

        # Auto-scale threshold (messages in queue)
        self.queue_threshold = 1000

        # Memory cleanup interval (seconds)
        self.memory_cleanup_interval = 3600  # 1 hour
```

---

## Usage

### Starting the Supervisor

#### Method 1: Direct Execution

```bash
cd /a0/usr/projects/godmodescanner/projects/godmodescanner
python agents/god_mode_supervisor.py
```

#### Method 2: Using Startup Script

```bash
cd /a0/usr/projects/godmodescanner/projects/godmodescanner
./scripts/start_god_mode_supervisor.sh
```

#### Method 3: Docker Deployment

```bash
docker-compose up god-mode-supervisor
```

### Stopping the Supervisor

```bash
# Graceful shutdown (Ctrl+C)
!!:s^C

# Or send SIGTERM
kill -TERM <pid>
```

---

## Monitoring

### Health Checks

The supervisor publishes health data to `godmode:system_health` stream:

```bash
# Read latest health data
redis-cli XREVRANGE godmode:system_health + - COUNT 1
```

**Output**:
```json
{
  "supervisor": "god_mode",
  "status": "healthy",
  "timestamp": "2026-01-25T14:45:00Z",
  "queue_depths": {
    "godmode:new_transactions": 523,
    "godmode:new_tokens": 45,
    "godmode:risk_scores": 892,
    "godmode:alerts": 12
  },
  "health": {
    "redis_cluster": "healthy",
    "workers": 30,
    "agents": 47
  }
}
```

### Logs

The supervisor uses structured logging (JSON format):

```bash
# View logs
tail -f logs/god_mode_supervisor.log
```

**Example log entries**:

```json
{"event": "god_mode_supervisor_initialized", "timestamp": "2026-01-25T14:45:00Z", "level": "info"}
{"event": "redis_connected", "url": "redis://127.0.0.1:16379", "timestamp": "2026-01-25T14:45:01Z", "level": "info"}
{"event": "monitoring_loop_started", "timestamp": "2026-01-25T14:45:02Z", "level": "info"}
{"event": "system_health_checked", "health": {"status": "healthy"}, "timestamp": "2026-01-25T14:46:02Z", "level": "info"}
{"event": "queue_depths_checked", "depths": {"godmode:risk_scores": 1250}, "timestamp": "2026-01-25T14:46:03Z", "level": "info"}
{"event": "risk_queue_threshold_exceeded", "current": 1250, "threshold": 1000, "timestamp": "2026-01-25T14:46:03Z", "level": "warning"}
{"event": "auto_scaling_risk_assessors", "current": 3, "target": 5, "timestamp": "2026-01-25T14:46:04Z", "level": "info"}
```

---

## Auto-Scaling Behavior

### Trigger Conditions

The supervisor auto-scales risk_assessor agents when:

1. **Queue Depth Exceeds Threshold**
   - Stream: `godmode:risk_scores`
   - Consumer Group: `risk-aggregator-group`
   - Threshold: 1000 pending messages

2. **Calculation**
   ```python
   # Each instance can handle ~200 messages
   additional_needed = (queue_depth - threshold) // 200
   additional_needed = max(1, min(additional_needed, 5))  # 1-5 instances
   ```

### Scaling Process

```
1. Supervisor detects queue_depth = 1250 (exceeds 1000)
2. Calculates: (1250 - 1000) // 200 = 1 additional instance
3. Spawns orchestrator subordinate agent
4. Orchestrator uses swarm_manager to spawn risk_assessor worker
5. New worker connects to risk-aggregator-group
6. Worker begins processing messages
7. Supervisor verifies worker status
8. Reports completion with new instance ID
```

### Example Auto-Scale Log

```json
{
  "event": "auto_scale_completed",
  "result": {
    "action": "spawned_risk_assessor",
    "instance_id": "risk_assessor_004",
    "consumer_group": "risk-aggregator-group",
    "status": "healthy",
    "messages_processed": 0,
    "startup_time_ms": 1250
  },
  "timestamp": "2026-01-25T14:46:10Z",
  "level": "info"
}
```

---

## Rate Limit Handling

### Detection

The supervisor detects RPC rate limiting through:

1. **Log Analysis** (production)
   - Parses agent logs for "429" errors
   - Identifies failing RPC endpoint

2. **Health Metrics** (current)
   - Reads from `godmode:system_health` stream
   - Checks for rate_limit_errors field

### Response Process

```
1. Supervisor detects 429 errors from endpoint A
2. Spawns developer subordinate agent
3. Developer agent:
   a. Reads RPC_ENDPOINTS from .env
   b. Identifies failing endpoint
   c. Rotates to next endpoint in list
   d. Updates .env file
   e. Publishes config_update to godmode:control
4. All agents receive config_update
5. Agents switch to new RPC endpoint
6. Developer monitors for 60 seconds
7. Confirms 429 errors stopped
8. Reports success to supervisor
```

### Example Rate Limit Log

```json
{
  "event": "rate_limit_detected",
  "endpoint": "https://api.mainnet-beta.solana.com",
  "timestamp": "2026-01-25T14:50:00Z",
  "level": "warning"
}
{
  "event": "rate_limit_handled",
  "result": {
    "action": "switched_rpc_endpoint",
    "old_endpoint": "https://api.mainnet-beta.solana.com",
    "new_endpoint": "https://solana-api.projectserum.com",
    "agents_updated": 47,
    "verification_time_seconds": 60,
    "errors_stopped": true
  },
  "timestamp": "2026-01-25T14:51:15Z",
  "level": "info"
}
```

---

## Memory Cleanup

### Schedule

The supervisor triggers memory cleanup every hour:

- **Interval**: 3600 seconds (1 hour)
- **Target**: FAISS vector storage at `data/memory/`
- **Retention**: 7 days

### Cleanup Process

```
1. Supervisor checks time since last cleanup
2. If >= 1 hour, spawns developer subordinate
3. Developer agent (acting as memory_curator):
   a. Connects to FAISS vector storage
   b. Queries all memory entries with metadata
   c. Filters entries older than 7 days
   d. Deletes identified entries
   e. Compacts FAISS index
   f. Generates cleanup report
   g. Publishes metrics to godmode:system_health
4. Supervisor updates last_cleanup_time
5. Reports completion
```

### Cleanup Report

```json
{
  "cleanup_id": "cleanup_1706198700",
  "timestamp": "2026-01-25T15:45:00Z",
  "total_entries_before": 125000,
  "entries_deleted": 35000,
  "total_entries_after": 90000,
  "space_reclaimed_mb": 450.5,
  "cleanup_duration_seconds": 12.3,
  "retention_days": 7,
  "status": "success"
}
```

---

## Agent Zero Integration

### Subordinate Profiles

The supervisor delegates to three Agent Zero profiles:

#### 1. **Orchestrator** (Auto-Scaling)

```python
await self.orchestrator.call_subordinate(
    profile="orchestrator",
    message="""
    Spawn 2 additional risk_assessor agents.
    Consumer group: risk-aggregator-group
    Stream: godmode:risk_scores
    """,
    reset=True
)
```

#### 2. **Developer** (Rate Limit Handling)

```python
await self.orchestrator.call_subordinate(
    profile="developer",
    message="""
    Handle RPC rate limiting.
    Failing endpoint: https://api.mainnet-beta.solana.com
    Action: Switch to next RPC endpoint immediately.
    """,
    reset=True
)
```

#### 3. **Developer** (Memory Cleanup)

```python
await self.orchestrator.call_subordinate(
    profile="developer",
    message="""
    Prune FAISS vector storage.
    Retention: 7 days
    Location: data/memory/
    """,
    reset=True
)
```

### Hierarchical Coordination

```
God Mode Supervisor (Master)
├── Orchestrator Subordinate
│   └── Swarm Manager
│       └── Risk Assessor Workers (1-5)
├── Developer Subordinate (RPC)
│   └── Config Manager
│       └── Agent Config Updates (47)
└── Developer Subordinate (Memory)
    └── Memory Curator
        └── FAISS Cleanup
```

---

## Performance Metrics

### Monitoring Overhead

| Metric | Value |
|--------|-------|
| Check Interval | 60 seconds |
| CPU Usage | <5% |
| Memory Usage | ~100 MB |
| Redis Queries/Check | 10-15 |
| Latency/Check | <500ms |

### Auto-Scaling Performance

| Metric | Value |
|--------|-------|
| Detection Latency | <60 seconds |
| Spawn Time | 1-3 seconds |
| Verification Time | 5-10 seconds |
| Total Response Time | <75 seconds |

### Rate Limit Response

| Metric | Value |
|--------|-------|
| Detection Latency | <60 seconds |
| Endpoint Switch Time | 2-5 seconds |
| Agent Update Time | 10-20 seconds |
| Verification Time | 60 seconds |
| Total Response Time | <90 seconds |

---

## Troubleshooting

### Issue: Supervisor Not Starting

**Symptoms**:
- Initialization fails
- Redis connection error

**Solution**:
```bash
# Check Redis cluster status
redis-cli -p 16379 CLUSTER INFO

# Verify .env configuration
cat .env | grep REDIS_URL

# Check Redis connectivity
redis-cli -u redis://127.0.0.1:16379 PING
```

### Issue: Auto-Scaling Not Triggering

**Symptoms**:
- Queue depth exceeds 1000
- No new workers spawned

**Solution**:
```bash
# Check queue depth manually
redis-cli XPENDING godmode:risk_scores risk-aggregator-group

# Verify supervisor logs
tail -f logs/god_mode_supervisor.log | grep auto_scale

# Check orchestrator agent status
redis-cli HGETALL agent:orchestrator:status
```

### Issue: Rate Limit Handling Fails

**Symptoms**:
- 429 errors persist
- RPC endpoint not switching

**Solution**:
```bash
# Check current RPC endpoint
cat .env | grep RPC_ENDPOINTS

# Verify developer agent logs
tail -f logs/developer_agent.log | grep rate_limit

# Manually switch endpoint
vi .env  # Update RPC_ENDPOINTS
redis-cli PUBLISH godmode:control '{"command": "config_update", "parameters": {"rpc_endpoint": "..."}}'  
```

---

## Production Deployment

### Prerequisites

- [ ] Redis Cluster running (6 nodes)
- [ ] TimescaleDB configured
- [ ] All 47+ agents deployed
- [ ] 30+ workers running
- [ ] Agent Zero framework initialized

### Deployment Steps

1. **Configure Environment**
   ```bash
   cp .env.example .env
   vi .env  # Update REDIS_URL, RPC_ENDPOINTS
   ```

2. **Start Redis Cluster**
   ```bash
   ./scripts/start_redis_cluster.sh
   ```

3. **Deploy Workers**
   ```bash
   ./scripts/start_parallel_swarm.sh
   ```

4. **Start Supervisor**
   ```bash
   ./scripts/start_god_mode_supervisor.sh
   ```

5. **Verify Health**
   ```bash
   redis-cli XREVRANGE godmode:system_health + - COUNT 1
   ```

### Monitoring Setup

```bash
# Prometheus metrics
curl http://localhost:9090/metrics

# Grafana dashboard
http://localhost:3000/d/godmodescanner

# Jaeger tracing
http://localhost:16686
```

---

## Advanced Configuration

### Custom Auto-Scaling Logic

Modify `check_queue_depths()` to add custom scaling logic:

```python
async def check_queue_depths(self) -> Dict[str, int]:
    # Add custom streams
    streams = [
        "godmode:new_transactions",
        "godmode:custom_stream",  # Your stream
    ]

    # Add custom threshold logic
    if queue_depths["godmode:custom_stream"] > 500:
        await self.auto_scale_custom_agent()
```

### Custom Subordinate Delegation

Add new subordinate profiles:

```python
async def handle_custom_task(self):
    result = await self.orchestrator.call_subordinate(
        profile="researcher",  # Use researcher profile
        message="""
        Investigate suspicious wallet cluster.
        Cluster ID: cluster_abc123
        """,
        reset=True
    )
```

---

## API Reference

### GodModeSupervisor Class

```python
class GodModeSupervisor:
    async def initialize() -> bool
    async def check_system_health() -> Dict
    async def check_queue_depths() -> Dict[str, int]
    async def auto_scale_risk_assessors(current: int, target: int)
    async def handle_rate_limit_spike(endpoint: str)
    async def schedule_memory_cleanup()
    async def monitor_and_respond()
    async def start()
    async def stop()
```

---

## FAQ

**Q: How often does the supervisor check system health?**  
A: Every 60 seconds by default. Configurable via `self.check_interval`.

**Q: What happens if the supervisor crashes?**  
A: Workers continue processing independently. Restart the supervisor to resume orchestration.

**Q: Can I run multiple supervisors?**  
A: Not recommended. Use one supervisor per GODMODESCANNER deployment.

**Q: How do I customize auto-scaling thresholds?**  
A: Modify `self.queue_threshold` in `__init__()` method.

**Q: Does the supervisor require Agent Zero?**  
A: Yes. It uses Agent Zero's hierarchical framework for subordinate delegation.

---

## Support

- **Documentation**: `/docs/API_SPEC.md`
- **Issues**: GitHub Issues
- **Logs**: `logs/god_mode_supervisor.log`

---

**Version**: 1.0.0  
**Last Updated**: 2026-01-25  
**Maintained By**: GODMODESCANNER Development Team  
**License**: MIT
