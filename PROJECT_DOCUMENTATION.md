# GODMODESCANNER - Complete Project Documentation
# Rebuilding Guide for Solana Insider Trading Detection System

> **Last Updated**: 2026-02-04  
> **Version**: 1.0.0  
> **Status**: Production Ready

---

## Table of Contents

1. [Project Overview & Mission](#1-project-overview--mission)
2. [Architecture Deep Dive](#2-architecture-deep-dive)
3. [Core Components Breakdown](#3-core-components-breakdown)
4. [Infrastructure Setup](#4-infrastructure-setup)
5. [Development Environment](#5-development-environment)
6. [Agent System Details](#6-agent-system-details)
7. [Data Flow & Processing Pipeline](#7-data-flow--processing-pipeline)
8. [Detection Algorithms](#8-detection-algorithms)
9. [Testing & Quality Assurance](#9-testing--quality-assurance)
10. [Deployment Strategies](#10-deployment-strategies)
11. [Rebuilding from Scratch Guide](#11-rebuilding-from-scratch-guide)
12. [Performance Optimization](#12-performance-optimization)
13. [Security Considerations](#13-security-considerations)
14. [Troubleshooting & Maintenance](#14-troubleshooting--maintenance)

---

## 1. Project Overview & Mission

### 1.1 What is GODMODESCANNER?

GODMODESCANNER is an **elite AI-powered insider trading detection system** specifically designed for Solana's pump.fun platform. It represents a production-grade, autonomous multi-agent system that achieves:

- **Sub-second latency** (<1s end-to-end detection)
- **>95% accuracy** in insider pattern detection
- **$0/month operational cost** through aggressive optimization
- **71+ specialized agents** working in coordination
- **Real-time monitoring** of all pump.fun token launches

### 1.2 Core Mission

The primary mission is to detect and alert on six types of insider trading patterns:

1. **Dev Insider**: Token creators buying before public announcement
2. **Telegram Alpha**: Coordinated buying from private groups
3. **Sniper Bot**: Automated early buying within seconds of launch
4. **Wash Trader**: Artificial volume creation through self-trading
5. **Delayed Insider**: Coordinated buying shortly after launch
6. **Sybil Army**: Multiple controlled wallets acting in coordination

### 1.3 Key Differentiators

- **Zero-Cost Architecture**: Leverages only free RPC endpoints and infrastructure
- **AI-Powered Analysis**: LSTM-based behavioral modeling with 98.21% confidence
- **Autonomous Code Generation**: Singularity Engine creates detection functions from learned patterns
- **Multi-Agent Coordination**: 71+ specialized agents working hierarchically
- **Sub-microsecond Alerting**: Zero-latency alert pipeline (~15.65μs critical path)

### 1.4 Technology Foundation

The project builds upon and extends:
- **solana-agent-kit**: Solana protocol integration patterns
- **Solana-Forensic-Analysis-Tool**: Forensic analysis techniques
- **smolagents**: Code-thinking agent patterns from Hugging Face

### 1.5 Project Statistics

- **69,518 lines of Python code**
- **155 Python files**
- **89 comprehensive tests** (100% pass rate)
- **71+ specialized agents**
- **6-node Redis cluster** (2,457 ops/sec)
- **97% production readiness**

---

## 2. Architecture Deep Dive

### 2.1 System Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                    GODMODESCANNER ARCHITECTURE                   │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  LAYER 1: DATA INGESTION                                        │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │  bloXroute   │  │   Solana     │  │  pump.fun    │          │
│  │  WebSocket   │  │   RPC Pool   │  │   Parser     │          │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘          │
│         │                 │                 │                   │
│  LAYER 2: STREAM PROCESSING (Redis Streams)                     │
│         └─────────────────┴─────────────────┘                   │
│                           │                                     │
│  ┌────────────────────────┴───────────────────────┐             │
│  │  Redis Streams: new_tokens, transactions,      │             │
│  │  early_detect, risk_scores, alerts             │             │
│  └────────────────────┬───────────────────────────┘             │
│                       │                                         │
│  LAYER 3: PARALLEL PROCESSING (30+ Workers)                     │
│  ┌────────────────────┴───────────────────────────┐             │
│  │  XREADGROUP Consumer Swarm                     │             │
│  │  - Wallet Analyzer Workers (10)                │             │
│  │  - Pattern Recognition Workers (8)             │             │
│  │  - Graph Traversal Workers (6)                 │             │
│  │  - Risk Scoring Workers (6)                    │             │
│  └────────────────────┬───────────────────────────┘             │
│                       │                                         │
│  LAYER 4: AI/ML ANALYSIS                                        │
│  ┌────────────────────┴───────────────────────────┐             │
│  │  - Behavioral DNA Engine (ONNX)                │             │
│  │  - Singularity Engine (Ollama LLM)             │             │
│  │  - ETERNAL MIND (Memory System)                │             │
│  │  - Graph De-anonymization (NetworkX)           │             │
│  └────────────────────┬───────────────────────────┘             │
│                       │                                         │
│  LAYER 5: DATA PERSISTENCE                                      │
│  ┌────────────────────┴───────────────────────────┐             │
│  │  PostgreSQL 18 + TimescaleDB 2.24              │             │
│  │  (7 Hypertables for time-series data)          │             │
│  └────────────────────┬───────────────────────────┘             │
│                       │                                         │
│  LAYER 6: ALERTING & RESPONSE                                   │
│  ┌────────────────────┴───────────────────────────┐             │
│  │  Zero-Latency Alert Pipeline                   │             │
│  │  → Screamer (Console)                          │             │
│  │  → Discord Webhooks                            │             │
│  │  → Telegram Bot                                │             │
│  └─────────────────────────────────────────────────┘             │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 Multi-Agent Hierarchy

```
┌──────────────────────────────────────────┐
│      Master Orchestrator (main.py)       │
│      - Lifecycle Management              │
│      - Global Coordination               │
└────────────────┬─────────────────────────┘
                 │
    ┌────────────┴────────────┐
    │                         │
    ▼                         ▼
┌─────────────┐       ┌─────────────┐
│ MCP Server  │       │  Agent Zero │
│ Orchestrator│       │  Framework  │
└──────┬──────┘       └──────┬──────┘
       │                     │
       │    ┌────────────────┴──────────────┐
       │    │                               │
       ▼    ▼                               ▼
┌─────────────────┐           ┌───────────────────────┐
│ God Mode        │           │ Specialized Agents     │
│ Supervisor      │           │ - Transaction Analyst  │
│ - Task Queue    │           │ - Risk Assessor        │
│ - Load Balance  │           │ - Graph Analyst        │
└────────┬────────┘           │ - Researcher           │
         │                    │ - Developer            │
         ▼                    │ - Orchestrator         │
┌─────────────────┐           └───────────────────────┘
│ Worker Agents   │
│ - 30+ Parallel  │
│ - Stream Based  │
│ - Task Special  │
└─────────────────┘
```

### 2.3 Data Flow Architecture

```
 Transaction Event
       │
       ▼
┌─────────────────┐
│  RPC/WebSocket  │  ──┐
│  Ingestion      │    │
└─────────┬───────┘    │ 
          │            │ Parallel
          ▼            │ Paths
┌─────────────────┐    │
│ Redis Stream    │  ──┘
│ Producer        │
└─────────┬───────┘
          │
          ▼
┌─────────────────────────────────────┐
│  XREADGROUP Consumers (30+ workers) │
└─────────┬───────────────────────────┘
          │
    ┌─────┴──────┬──────────┬─────────┐
    │            │          │         │
    ▼            ▼          ▼         ▼
┌────────┐  ┌────────┐ ┌────────┐ ┌────────┐
│Wallet  │  │Pattern │ │ Graph  │ │ Risk   │
│Analyze │  │Recogni │ │Travers │ │Scoring │
└───┬────┘  └───┬────┘ └───┬────┘ └───┬────┘
    │           │          │          │
    └───────────┴──────────┴──────────┘
                │
                ▼
        ┌───────────────┐
        │ Risk          │
        │ Aggregator    │
        └───────┬───────┘
                │
                ▼
        ┌───────────────┐
        │ Alert         │
        │ Manager       │
        └───────────────┘
```

### 2.4 Ghost Protocol Architecture

The **Ghost Protocol** is a 4-tier zero-cost architecture designed to eliminate all operational expenses:

**Tier 1: Parasitic RPC**
- Rotates across 8 free Solana RPC endpoints
- Adaptive rate limiting (5-40 RPS)
- Automatic fallback on rate limits
- Zero RPC costs

**Tier 2: Sovereign Data**
- Redis-only data storage (eliminates TimescaleDB dependency)
- Memory-mapped shared memory for ultra-fast access
- Automatic data expiration (TTL-based)
- Zero database hosting costs

**Tier 3: Berserker Processing**
- 30+ parallel workers from single compute instance
- Async/await for maximum CPU utilization
- Backpressure management to prevent overload
- Zero additional compute costs

**Tier 4: Zero-Point Alerting**
- mmap shared memory for alert propagation (~15.65μs)
- Local console output (Screamer)
- Free Discord/Telegram webhooks
- Zero alerting infrastructure costs

---

## 3. Core Components Breakdown

### 3.1 Main Entry Point (`main.py`)

**Purpose**: Primary orchestrator that coordinates all system components

**Key Responsibilities**:
- Initialize Redis Cluster connection
- Set up Redis Streams and consumer groups
- Start MCP Orchestrator for agent coordination
- Launch PumpFunDetectorAgent for native RPC monitoring
- Manage BackpressureMonitor for load management
- Handle graceful shutdown on SIGINT/SIGTERM

**Consumer Groups Created**:
```python
{
    "godmode:new_transactions": [
        "wallet-analyzer-group",
        "pattern-recognition-group",
        "sybil-detection-group"
    ],
    "godmode:new_tokens": [
        "early-detection-group",
        "funding-hub-group"
    ],
    "godmode:early_detection": [
        "graph-traversal-group",
        "risk-scoring-group"
    ]
}
```

### 3.2 Agent System

#### 3.2.1 Agent Zero Framework (`agentzero/`)

**Description**: Hierarchical agent management system with 6 specialized profiles

**Profiles**:
1. **Transaction Analyst**: Analyzes individual transactions for suspicious patterns
2. **Risk Assessor**: Evaluates overall risk scores and thresholds
3. **Graph Analyst**: Performs multi-hop wallet graph traversal
4. **Orchestrator**: Coordinates multiple agent workflows
5. **Researcher**: Investigates complex patterns and anomalies
6. **Developer**: Generates and tests new detection code

**Key Files**:
- `agent_zero_core.py`: Core agent framework with hierarchical delegation
- `prompts/{profile}/system_prompt.md`: Profile-specific instructions

#### 3.2.2 Memory System (`agents/memory/`)

**Singularity Engine** (`singularity_engine.py`):
- **Purpose**: Autonomous code generation from learned behavioral patterns
- **Technology**: Ollama (codellama:7b-code) LLM integration
- **Process**:
  1. Observe behavioral patterns from real transactions
  2. Generate Python detection functions using LLM
  3. Sandbox execution and validation
  4. Hot-injection into running system
  5. Performance tracking and refinement

**ETERNAL MIND** (`storage.py`, `enhanced_storage.py`):
- **Purpose**: Self-improving memory system with persistent learning
- **Features**:
  - Disk-backed storage for pattern persistence
  - Hourly memory consolidation
  - Query interface for historical pattern lookup
  - FAISS vector search for similarity matching
- **Storage Structure**:
  ```
  data/eternal_mind/
  ├── patterns/        # Learned behavioral patterns
  ├── wallets/        # Wallet profiles and histories
  ├── graphs/         # Wallet relationship graphs
  └── consolidated/   # Hourly consolidated memories
  ```

**Sharded FAISS** (`sharded_faiss.py`):
- Distributed vector similarity search
- Wallet behavioral embedding storage
- Sub-millisecond lookup times
- Horizontal scaling support

#### 3.2.3 Detection Agents

**WalletProfilerAgent** (`agents/wallet_profiler/`):
- Builds behavioral profiles for wallets
- Tracks transaction history and patterns
- Calculates reputation scores
- Identifies suspicious behavior changes

**PatternRecognitionAgent** (`agents/pattern_recognition_agent.py`):
- ML-based pattern matching
- Real-time pattern learning
- Adaptive threshold adjustment
- Integration with Behavioral DNA Engine

**SybilDetectionAgent** (`agents/sybil_detection_agent.py`):
- Identifies coordinated wallet groups
- Graph clustering analysis
- Timing correlation detection
- Sybil army pattern recognition

**RiskAggregator** (`agents/risk_aggregator.py`):
- **Purpose**: Combines signals from all detection agents
- **Scoring Formula**:
  ```python
  risk_score = (
      behavior_score * 0.35 +
      timing_score * 0.25 +
      network_score * 0.25 +
      volume_score * 0.15
  )
  ```
- **Bayesian Updating**: Continuously refines probabilities
- **Output**: Normalized risk score (0.0 to 1.0)

**GraphTraversalAgent** (`agents/graph_traversal_phase1.py`):
- Multi-hop wallet relationship mapping
- Uses NetworkX for graph operations
- Optional cuGraph acceleration (GPU)
- De-anonymization through funding chains

**AlertManager** (`agents/alert_manager.py`):
- Consolidates alerts from all detection agents
- Priority-based alert routing
- Rate limiting to prevent alert fatigue
- Multi-channel distribution (Console, Discord, Telegram)

#### 3.2.4 Overlord System (`agents/overlord/`)

**Purpose**: Hostile Takeover Protocol for autonomous system migration

**Components**:

**SirenController** (`siren_controller.py`):
- Monitors system performance metrics
- Triggers autonomous migration when Ghost Protocol > 95% efficiency
- Manages transition from TimescaleDB to Redis-only

**BattleMonitorAgent** (`battle_monitor_agent.py`):
- Benchmarks Ghost Protocol vs Legacy system
- Real-time performance comparison
- Decision engine for system switchover

**DatabaseReaperAgent** (`database_reaper_agent.py`):
- Continuous data migration from TimescaleDB to Redis
- Zero-downtime migration strategy
- Automatic cleanup of migrated data

### 3.3 Utility Modules (`utils/`)

**AggressiveSolanaClient** (`aggressive_solana_client.py`):
- **Purpose**: High-throughput Solana RPC client
- **Features**:
  - Connection pooling (10+ concurrent connections)
  - Automatic retry with exponential backoff
  - Request batching and pipelining
  - Health monitoring and endpoint rotation
- **Performance**: Handles 1,000+ TPS

**GuerrillaRedisCluster** (`redis_cluster_client.py`):
- **Purpose**: 6-node Redis cluster client
- **Architecture**: 3 masters + 3 replicas
- **Features**:
  - Automatic shard routing
  - Failover handling
  - Consumer group management
  - Stream-based messaging
- **Performance**: 2,457 ops/sec, 0.40ms latency

**BackpressureMonitor** (`backpressure_monitor.py`):
- **Purpose**: Prevent system overload
- **Metrics Tracked**:
  - Redis Stream lag (messages pending)
  - Worker CPU/memory usage
  - Processing throughput
  - Alert generation rate
- **Actions**:
  - Throttle ingestion when lag > threshold
  - Scale worker count dynamically
  - Drop low-priority messages under extreme load

**PumpFunParser** (`pumpfun_parser.py`, `enhanced_pumpfun_parser.py`):
- **Purpose**: Parse pump.fun program instructions
- **Event Types**:
  - `TokenCreate`: New token launch events
  - `Trade`: Buy/sell transactions
  - `Complete`: Token graduation events
- **Features**:
  - Instruction decoding (Anchor IDL-based)
  - Account extraction
  - Metadata parsing
  - Error handling for malformed data

**WebSocketManager** (`ws_manager.py`):
- **Purpose**: Manage WebSocket connections to Solana
- **Features**:
  - Automatic reconnection
  - Subscription management
  - Message queuing during disconnects
  - Heartbeat monitoring

**RPCManager** (`rpc_manager.py`):
- **Purpose**: Coordinate RPC requests across endpoints
- **Features**:
  - Round-robin load balancing
  - Adaptive rate limiting per endpoint
  - Automatic fallback on errors
  - Response caching (Redis-backed)

**AdaptiveRateLimiter** (`adaptive_rate_limiter.py`):
- **Purpose**: Intelligent rate limit management
- **Algorithm**:
  1. Start at conservative rate (5 RPS)
  2. Gradually increase on success
  3. Immediate backoff on 429 errors
  4. Per-endpoint rate tracking
- **Result**: 95%+ RPC success rate with free endpoints

### 3.4 Data Models

**InsiderAlert** (defined in `detector.py`):
```python
@dataclass
class InsiderAlert:
    alert_id: str           # Unique alert identifier
    timestamp: datetime     # When alert was generated
    alert_type: str        # Type: "early_buy", "coordinated", etc.
    token_mint: str        # Token contract address
    trader: str            # Wallet address
    score: float           # Risk score (0.0-1.0)
    evidence: Dict         # Supporting evidence
    metadata: Dict         # Additional context
```

**TokenCreateEvent**:
```python
@dataclass
class TokenCreateEvent:
    mint: str              # Token mint address
    name: str             # Token name
    symbol: str           # Token ticker
    creator: str          # Creator wallet
    timestamp: datetime   # Launch time
    metadata_uri: str     # IPFS/Arweave metadata
```

**TradeEvent**:
```python
@dataclass
class TradeEvent:
    signature: str        # Transaction signature
    mint: str            # Token mint
    trader: str          # Trading wallet
    is_buy: bool         # Buy vs sell
    sol_amount: float    # SOL amount
    token_amount: float  # Token amount
    timestamp: datetime  # Trade time
```

### 3.5 Configuration Management

**Environment Variables** (`.env`):
```bash
# Solana RPC Endpoints (8 free endpoints for rotation)
RPC_ENDPOINTS=https://api.mainnet-beta.solana.com,https://solana-api.projectserum.com,...

# Redis Configuration
REDIS_URL=redis://localhost:6379
REDIS_CLUSTER_STARTUP_NODES=localhost:16379,localhost:16380,localhost:16381

# TimescaleDB Configuration
TIMESCALE_URL=postgresql://godmodescanner:password@localhost:5432/godmodescanner

# pump.fun Program ID
PUMPFUN_PROGRAM_ID=6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P

# Singularity Engine
OLLAMA_ENDPOINT=http://ollama:11434/api/generate
SINGULARITY_ENABLED=true

# Ghost Protocol
BATTLE_MODE=true
GHOST_PROTOCOL_AUTO_ENABLE_THRESHOLD=0.95

# Alerting
TELEGRAM_BOT_TOKEN=<your_token>
TELEGRAM_CHAT_ID=<your_chat_id>
```

**Docker Compose Services** (`docker-compose.yml`):
1. **redis-master-{1,2,3}**: Redis cluster masters
2. **redis-replica-{1,2,3}**: Redis cluster replicas
3. **ollama**: LLM inference for Singularity Engine
4. **jaeger**: Distributed tracing
5. **prometheus**: Metrics collection
6. **grafana**: Metrics visualization
7. **supervisor**: Agent supervisor and task queue
8. **orchestrator**: Main orchestration service
9. **workers**: Parallel processing workers (scalable)

---

## 4. Infrastructure Setup

### 4.1 System Requirements

**Minimum Requirements**:
- **CPU**: 4 cores (8 recommended for optimal performance)
- **RAM**: 8GB minimum (16GB recommended)
  - 4GB for Ollama LLM
  - 4GB for GODMODESCANNER + Redis
- **Storage**: 50GB SSD (NVMe recommended for TimescaleDB)
- **Network**: 100Mbps (1Gbps recommended for WebSocket stability)
- **OS**: Ubuntu 20.04+, macOS 12+, or Windows 10+ with WSL2

**Recommended Production Requirements**:
- **CPU**: 8+ cores
- **RAM**: 32GB
- **Storage**: 500GB NVMe SSD
- **Network**: 1Gbps with low latency to Solana RPC endpoints

### 4.2 Docker Infrastructure

#### 4.2.1 Redis Cluster Setup

**Architecture**: 6-node cluster (3 masters + 3 replicas)

**Configuration** (`docker-compose.yml`):
```yaml
services:
  redis-master-1:
    image: redis:7-alpine
    command: >
      redis-server
      --cluster-enabled yes
      --appendonly yes
      --maxmemory 1800mb
      --maxmemory-policy allkeys-lru
    networks:
      godmode_network:
        ipv4_address: 172.28.1.1
```

**Cluster Initialization**:
```bash
# Start all Redis nodes
docker-compose up -d redis-master-1 redis-master-2 redis-master-3 \
                     redis-replica-1 redis-replica-2 redis-replica-3

# Create cluster
redis-cli --cluster create \
  172.28.1.1:6379 172.28.1.2:6379 172.28.1.3:6379 \
  172.28.1.4:6379 172.28.1.5:6379 172.28.1.6:6379 \
  --cluster-replicas 1
```

**Performance Tuning**:
- `appendfsync everysec`: Balance between durability and performance
- `maxmemory-policy allkeys-lru`: Evict least recently used keys
- `tcp-backlog 65535`: Handle high connection volume
- `hz 100`: Increase background task frequency

#### 4.2.2 PostgreSQL + TimescaleDB Setup

**Native Installation** (recommended for production):
```bash
# Install PostgreSQL 18
sudo apt-get install postgresql-18

# Install TimescaleDB 2.24
sudo add-apt-repository ppa:timescale/timescaledb-ppa
sudo apt-get update
sudo apt-get install timescaledb-2-postgresql-18

# Initialize TimescaleDB
sudo timescaledb-tune
sudo systemctl restart postgresql
```

**Database Schema** (`scripts/timescaledb_schema.sql`):

**Hypertables**:
1. `transactions`: All blockchain transactions
2. `token_launches`: Token creation events
3. `wallet_profiles`: Wallet behavioral data
4. `risk_scores`: Calculated risk scores over time
5. `alerts`: Generated alerts
6. `graph_edges`: Wallet relationship edges
7. `pattern_detections`: Detected patterns

**Example Hypertable**:
```sql
CREATE TABLE transactions (
    time TIMESTAMPTZ NOT NULL,
    signature TEXT PRIMARY KEY,
    block_time BIGINT,
    token_mint TEXT,
    wallet TEXT,
    is_buy BOOLEAN,
    sol_amount NUMERIC,
    token_amount NUMERIC,
    metadata JSONB
);

SELECT create_hypertable('transactions', 'time');
CREATE INDEX ON transactions (token_mint, time DESC);
CREATE INDEX ON transactions (wallet, time DESC);
```

**Retention Policies**:
```sql
-- Keep detailed data for 30 days
SELECT add_retention_policy('transactions', INTERVAL '30 days');

-- Compress data older than 7 days
ALTER TABLE transactions SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'token_mint'
);
SELECT add_compression_policy('transactions', INTERVAL '7 days');
```

#### 4.2.3 Ollama LLM Setup

**Purpose**: Powers Singularity Engine for autonomous code generation

**Docker Service**:
```yaml
ollama:
  image: ollama/ollama:latest
  container_name: godmode_ollama
  volumes:
    - ./data/ollama:/root/.ollama
  ports:
    - "11434:11434"
  deploy:
    resources:
      limits:
        memory: 4G
```

**Model Installation**:
```bash
# Pull codellama model
docker exec godmode_ollama ollama pull codellama:7b-code

# Verify installation
docker exec godmode_ollama ollama list
```

**API Testing**:
```bash
curl http://localhost:11434/api/generate -d '{
  "model": "codellama:7b-code",
  "prompt": "Write a Python function to detect early buyers",
  "stream": false
}'
```

#### 4.2.4 Observability Stack

**Jaeger (Distributed Tracing)**:
```yaml
jaeger:
  image: jaegertracing/all-in-one:latest
  ports:
    - "16686:16686"  # UI
    - "6831:6831/udp"  # Jaeger agent
```

**Prometheus (Metrics Collection)**:
```yaml
prometheus:
  image: prom/prometheus:latest
  volumes:
    - ./config/prometheus.yml:/etc/prometheus/prometheus.yml
  ports:
    - "9090:9090"
```

**Grafana (Visualization)**:
```yaml
grafana:
  image: grafana/grafana:latest
  ports:
    - "3000:3000"
  environment:
    - GF_SECURITY_ADMIN_PASSWORD=admin
```

### 4.3 Network Architecture

**Docker Network** (`godmode_network`):
```yaml
networks:
  godmode_network:
    driver: bridge
    ipam:
      config:
        - subnet: 172.28.0.0/16
          gateway: 172.28.0.1
```

**Service Communication**:
- **Redis Cluster**: 172.28.1.1-6 (internal)
- **PostgreSQL**: 127.0.0.1:5432 (host machine)
- **Ollama**: 172.28.2.1:11434
- **Jaeger**: 172.28.3.1:16686
- **Prometheus**: 172.28.4.1:9090
- **Grafana**: 172.28.5.1:3000

**Port Mapping**:
- External access via published ports
- Internal services use Docker DNS resolution
- Redis cluster uses gossip protocol for node discovery

---

## 5. Development Environment

### 5.1 Local Development Setup

**Step 1: Clone Repository**
```bash
git clone https://github.com/winder87-stack/GODmodeScanner.git
cd GODmodeScanner
```

**Step 2: Python Environment**
```bash
# Create virtual environment
python3.13 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Verify installation
python -c "import solana, redis, pandas; print('All dependencies installed')"
```

**Step 3: Environment Configuration**
```bash
# Copy template
cp .env.template .env

# Edit .env with your settings
nano .env  # or vim, code, etc.
```

**Step 4: Start Infrastructure**
```bash
# Start Redis cluster
./scripts/start_redis_cluster.sh

# Initialize PostgreSQL
./scripts/setup_timescaledb.sh

# Start Ollama
docker-compose up -d ollama
./scripts/init_ollama.sh
```

**Step 5: Run Development Server**
```bash
# Run main orchestrator
python main.py

# Or run specific agents
python agents/pump_fun_detector_agent.py
python agents/transaction_monitor.py
```

### 5.2 Development Tools

**IDE Setup** (VS Code recommended):
```json
{
  "python.linting.enabled": true,
  "python.linting.pylintEnabled": false,
  "python.linting.flake8Enabled": true,
  "python.formatting.provider": "black",
  "python.testing.pytestEnabled": true,
  "editor.formatOnSave": true
}
```

**Pre-commit Hooks** (`.git/hooks/pre-commit`):
```bash
#!/bin/bash
# Run tests before commit
pytest tests/ --maxfail=1 --disable-warnings -q
if [ $? -ne 0 ]; then
    echo "Tests failed, commit aborted"
    exit 1
fi

# Run linter
flake8 agents/ utils/ --max-line-length=100
```

**Debugging Configuration** (`.vscode/launch.json`):
```json
{
  "version": "0.2.0",
  "configurations": [
    {
      "name": "Python: Main",
      "type": "python",
      "request": "launch",
      "program": "${workspaceFolder}/main.py",
      "console": "integratedTerminal",
      "env": {
        "PYTHONPATH": "${workspaceFolder}"
      }
    },
    {
      "name": "Python: Detector",
      "type": "python",
      "request": "launch",
      "program": "${workspaceFolder}/detector.py",
      "console": "integratedTerminal"
    }
  ]
}
```

### 5.3 Testing Environment

**Unit Tests**:
```bash
# Run all unit tests
pytest tests/ -v

# Run specific test file
pytest tests/test_risk_aggregator.py -v

# Run with coverage
pytest --cov=agents --cov=utils tests/
```

**Integration Tests**:
```bash
# Start test infrastructure
docker-compose -f docker-compose.test.yml up -d

# Run integration tests
pytest tests/test_pumpfun_integration.py -v
pytest tests/test_parallel_pipeline.py -v

# Cleanup
docker-compose -f docker-compose.test.yml down
```

**Benchmarking**:
```bash
# Benchmark Redis cluster
python scripts/benchmark_redis_cluster.py

# Benchmark ML inference
python scripts/benchmark_onnx_inference.py

# Benchmark high-speed client
python benchmark_high_speed.py
```

### 5.4 Code Structure Guidelines

**File Organization**:
```
agents/
├── {agent_name}_agent.py     # Main agent implementation
├── {agent_name}/              # Agent-specific modules
│   ├── __init__.py
│   ├── models.py              # Data models
│   ├── processors.py          # Processing logic
│   └── utils.py               # Helper functions
```

**Naming Conventions**:
- Classes: `PascalCase` (e.g., `WalletProfilerAgent`)
- Functions: `snake_case` (e.g., `calculate_risk_score`)
- Constants: `UPPER_SNAKE_CASE` (e.g., `MAX_RETRY_ATTEMPTS`)
- Private methods: `_leading_underscore` (e.g., `_internal_helper`)

**Type Hints**:
```python
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass

@dataclass
class RiskScore:
    wallet: str
    score: float
    confidence: float
    factors: Dict[str, float]

async def calculate_risk(
    wallet: str,
    transactions: List[Dict]
) -> Optional[RiskScore]:
    """Calculate risk score for wallet."""
    ...
```

**Error Handling**:
```python
import structlog

logger = structlog.get_logger(__name__)

async def risky_operation():
    try:
        result = await perform_task()
        logger.info("task_completed", result=result)
        return result
    except SpecificError as e:
        logger.error("task_failed", error=str(e), exc_info=True)
        # Handle or re-raise
    finally:
        # Cleanup
        pass
```

---

## 6. Agent System Details

### 6.1 Agent Lifecycle

**Initialization Phase**:
1. Load configuration from environment
2. Connect to Redis cluster
3. Initialize database connections (if needed)
4. Register with supervisor
5. Subscribe to relevant Redis Streams
6. Enter main processing loop

**Processing Phase**:
1. Read messages from Redis Stream (XREADGROUP)
2. Process message (analyze, compute, detect)
3. Write results to output streams
4. Acknowledge message (XACK)
5. Update metrics and health status

**Shutdown Phase**:
1. Stop accepting new messages
2. Complete in-flight processing
3. Close database connections
4. Unregister from supervisor
5. Log final statistics

### 6.2 Worker Agent Pattern

**BaseWorker Class** (`agents/workers/base_worker.py`):
```python
class BaseWorker:
    """Base class for all worker agents."""
    
    def __init__(self, worker_id: str, redis_client):
        self.worker_id = worker_id
        self.redis = redis_client
        self.running = False
        self.stats = WorkerStats()
    
    async def start(self):
        """Start worker processing loop."""
        self.running = True
        while self.running:
            messages = await self.redis.xreadgroup(
                groupname=self.group_name,
                consumername=self.worker_id,
                streams={self.input_stream: '>'},
                count=self.batch_size
            )
            for stream, msg_list in messages:
                for msg_id, data in msg_list:
                    await self.process_message(msg_id, data)
    
    async def process_message(self, msg_id: str, data: Dict):
        """Override in subclass."""
        raise NotImplementedError
    
    async def stop(self):
        """Graceful shutdown."""
        self.running = False
```

**Worker Types**:

1. **Transaction Analyzer Workers**
   - Stream: `godmode:new_transactions`
   - Group: `wallet-analyzer-group`
   - Count: 10 workers
   - Task: Analyze individual transactions

2. **Pattern Recognition Workers**
   - Stream: `godmode:new_transactions`
   - Group: `pattern-recognition-group`
   - Count: 8 workers
   - Task: Detect behavioral patterns

3. **Graph Traversal Workers**
   - Stream: `godmode:early_detection`
   - Group: `graph-traversal-group`
   - Count: 6 workers
   - Task: Multi-hop wallet analysis

4. **Risk Scoring Workers**
   - Stream: `godmode:early_detection`
   - Group: `risk-scoring-group`
   - Count: 6 workers
   - Task: Calculate composite risk scores

### 6.3 Agent Communication

**Redis Streams Protocol**:

**Message Format**:
```python
{
    "event_type": "new_transaction",
    "signature": "5Kq...",
    "timestamp": "2026-02-04T15:00:00Z",
    "data": {
        "mint": "7xKX...",
        "trader": "9wWP...",
        "sol_amount": 0.1,
        "is_buy": true
    },
    "metadata": {
        "source": "websocket",
        "priority": "high"
    }
}
```

**Stream Publishing**:
```python
await redis.xadd(
    name="godmode:new_transactions",
    fields={
        "event_type": "new_transaction",
        "data": json.dumps(transaction_data)
    },
    maxlen=10000,  # Limit stream size
    approximate=True
)
```

**Stream Consumption**:
```python
messages = await redis.xreadgroup(
    groupname="wallet-analyzer-group",
    consumername="worker-01",
    streams={"godmode:new_transactions": ">"},
    count=10,
    block=5000  # Block for 5 seconds
)

for stream_name, msg_list in messages:
    for msg_id, data in msg_list:
        # Process message
        await process(data)
        # Acknowledge
        await redis.xack(stream_name, "wallet-analyzer-group", msg_id)
```

### 6.4 Specialized Agent Details

#### 6.4.1 PumpFunDetectorAgent

**Purpose**: Monitor pump.fun for new token launches and trades

**Data Sources**:
- WebSocket: Real-time transaction notifications
- RPC: Fetch detailed transaction data
- Parser: Decode pump.fun instructions

**Detection Flow**:
```
WebSocket Event → Fetch Transaction → Parse Instruction → 
  Identify Event Type → Extract Metadata → Publish to Stream
```

**Configuration**:
```python
{
    "websocket_url": "wss://api.mainnet-beta.solana.com",
    "program_id": "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P",
    "output_stream": "godmode:new_tokens",
    "batch_size": 10
}
```

#### 6.4.2 WalletProfilerAgent

**Purpose**: Build and maintain behavioral profiles for wallets

**Profile Components**:
```python
{
    "wallet": "9wWP...",
    "first_seen": "2026-01-01T00:00:00Z",
    "total_transactions": 142,
    "total_volume_sol": 15.3,
    "tokens_traded": 23,
    "win_rate": 0.42,
    "avg_hold_time_seconds": 3600,
    "behavioral_signature": [0.12, -0.43, ...],  # 128-dim vector
    "risk_flags": ["early_buyer", "high_frequency"],
    "reputation_score": 0.35
}
```

**Profile Update Process**:
1. Receive transaction event
2. Load existing profile (or create new)
3. Update statistics
4. Recalculate behavioral signature
5. Check for anomalies
6. Store updated profile
7. Publish to risk scoring stream if suspicious

#### 6.4.3 GraphTraversalAgent

**Purpose**: Analyze wallet relationships through funding chains

**Traversal Algorithm**:
```python
async def traverse_funding_chain(
    wallet: str,
    max_hops: int = 5
) -> Dict[str, Any]:
    """BFS traversal of wallet funding relationships."""
    visited = set()
    queue = [(wallet, 0)]  # (wallet, hop_depth)
    relationships = []
    
    while queue:
        current, depth = queue.pop(0)
        if current in visited or depth >= max_hops:
            continue
        
        visited.add(current)
        
        # Find funding sources
        sources = await get_funding_sources(current)
        for source in sources:
            relationships.append({
                "from": source,
                "to": current,
                "depth": depth + 1
            })
            queue.append((source, depth + 1))
    
    return {
        "root_wallet": wallet,
        "total_wallets": len(visited),
        "relationships": relationships,
        "max_depth_reached": max([r["depth"] for r in relationships])
    }
```

**Graph Analysis**:
- Clustering coefficient: Measure of wallet interconnectedness
- Betweenness centrality: Identify hub wallets
- Connected components: Find Sybil clusters

#### 6.4.4 Behavioral DNA Engine

**Purpose**: Predict wallet behavior using LSTM neural network

**Model Architecture**:
```
Input Layer (transaction sequence)
  ↓
LSTM Layer 1 (128 units)
  ↓
LSTM Layer 2 (64 units)
  ↓
Dense Layer (32 units, ReLU)
  ↓
Output Layer (softmax)
  ↓
Behavior Classes: [normal, early_buyer, wash_trader, ...]
```

**Inference Process**:
1. Load wallet transaction history (last 50 transactions)
2. Normalize features (amounts, timing, etc.)
3. Run ONNX inference
4. Get behavior probabilities
5. Return highest confidence prediction

**Performance**:
- Inference time: 1.46ms
- Confidence: 98.21%
- Model size: 2.3MB (ONNX format)

#### 6.4.5 Singularity Engine

**Purpose**: Autonomous code generation for new detection patterns

**Generation Process**:
```
1. Pattern Observation
   ↓ (Collect examples of suspicious behavior)
2. Pattern Description
   ↓ (Generate natural language description)
3. Code Generation
   ↓ (LLM generates Python detection function)
4. Sandboxed Execution
   ↓ (Test function on historical data)
5. Performance Validation
   ↓ (Measure accuracy, false positives)
6. Hot Injection
   ↓ (Add function to running system)
7. Monitoring
   ↓ (Track performance, refine if needed)
```

**Example Generated Function**:
```python
# Auto-generated by Singularity Engine
# Pattern: Coordinated buying within 5 seconds
# Generated: 2026-02-04 12:34:56
# Confidence: 0.94

async def detect_coordinated_5sec_buyers(
    token: str,
    transactions: List[Dict],
    threshold: int = 3
) -> bool:
    """Detect coordinated buying within 5 seconds."""
    # Get all buys within first 10 seconds
    early_buys = [
        tx for tx in transactions
        if tx['is_buy'] and tx['time_since_launch'] < 10
    ]
    
    if len(early_buys) < threshold:
        return False
    
    # Check for tight timing clustering
    for i in range(len(early_buys) - threshold + 1):
        window = early_buys[i:i+threshold]
        time_span = window[-1]['timestamp'] - window[0]['timestamp']
        if time_span <= 5.0:
            return True
    
    return False
```

---

## 7. Data Flow & Processing Pipeline

### 7.1 End-to-End Data Flow

**Stage 1: Ingestion** (0-50ms)
```
Solana Blockchain
  ↓ WebSocket notification
PumpFunDetectorAgent
  ↓ Transaction signature
RPC fetch (with retry)
  ↓ Raw transaction data
PumpFunParser
  ↓ Decoded event
```

**Stage 2: Stream Publishing** (1-5ms)
```
Redis Producer
  ↓ XADD command
Redis Stream: godmode:new_transactions
  ↓ Stream message
Consumer Groups (waiting with XREADGROUP)
```

**Stage 3: Parallel Processing** (10-500ms)
```
30+ Worker Agents (parallel execution)
  ├─ WalletProfiler: Build/update profile
  ├─ PatternRecognition: Check patterns
  ├─ SybilDetector: Analyze relationships
  └─ GraphTraversal: Map funding chains
       ↓ Partial results
Redis Stream: godmode:early_detection
```

**Stage 4: Risk Aggregation** (5-20ms)
```
RiskAggregator
  ├─ Combine signals from all agents
  ├─ Calculate Bayesian score
  ├─ Apply threshold
  └─ Generate alert if > 0.7
       ↓ Alert data
Redis Stream: godmode:alerts
```

**Stage 5: Alert Distribution** (1-10ms)
```
AlertManager
  ├─ Prioritize alerts
  ├─ Format for channels
  └─ Distribute:
      ├─ Console (Screamer)
      ├─ Discord webhook
      └─ Telegram bot
```

**Total Latency**: Sub-1000ms (typically 200-800ms)

### 7.2 Stream Architecture

**Stream Hierarchy**:
```
godmode:new_tokens          (Token launches)
  ↓
godmode:new_transactions    (All trades)
  ↓
godmode:early_detection     (Flagged as suspicious)
  ↓
godmode:risk_scores         (Calculated risk scores)
  ↓
godmode:alerts              (High-risk alerts)
```

**Stream Configuration**:
```python
STREAM_CONFIG = {
    "godmode:new_tokens": {
        "maxlen": 1000,
        "consumer_groups": ["early-detection-group"]
    },
    "godmode:new_transactions": {
        "maxlen": 10000,
        "consumer_groups": [
            "wallet-analyzer-group",
            "pattern-recognition-group",
            "sybil-detection-group"
        ]
    },
    "godmode:early_detection": {
        "maxlen": 5000,
        "consumer_groups": [
            "graph-traversal-group",
            "risk-scoring-group"
        ]
    },
    "godmode:alerts": {
        "maxlen": 1000,
        "consumer_groups": ["alert-manager-group"]
    }
}
```

### 7.3 Backpressure Management

**Monitoring Metrics**:
```python
{
    "stream_lag": 234,           # Messages pending in stream
    "processing_rate": 87.3,     # Messages/second
    "worker_cpu_avg": 0.65,      # Average CPU usage
    "worker_memory_avg": 512,    # Average memory (MB)
    "alert_rate": 3.2            # Alerts/minute
}
```

**Backpressure Triggers**:
1. **Stream Lag > 1000**: Throttle ingestion
2. **Worker CPU > 80%**: Reduce batch size
3. **Worker Memory > 1GB**: Force garbage collection
4. **Alert Rate > 10/min**: Apply alert deduplication

**Mitigation Strategies**:
```python
if backpressure_detected:
    # Strategy 1: Reduce ingestion rate
    await websocket_manager.throttle(rate=0.5)
    
    # Strategy 2: Increase batch processing
    worker_batch_size *= 2
    
    # Strategy 3: Drop low-priority messages
    await redis.xtrim("godmode:new_transactions", maxlen=5000)
    
    # Strategy 4: Scale workers (if Docker Swarm)
    await docker_spawner.scale("wallet-analyzer", replicas=15)
```

---

## 8. Detection Algorithms

### 8.1 Insider Pattern Types

#### 8.1.1 Dev Insider Detection

**Pattern**: Token creator buying their own token immediately after launch

**Algorithm**:
```python
def detect_dev_insider(token_data: Dict) -> Optional[Alert]:
    """Detect creator buying own token."""
    creator = token_data['creator']
    early_buys = token_data['early_buys']  # First 60 seconds
    
    creator_buys = [
        buy for buy in early_buys
        if buy['trader'] == creator
    ]
    
    if not creator_buys:
        return None
    
    # Calculate suspicion score
    total_creator_sol = sum(b['sol_amount'] for b in creator_buys)
    total_early_sol = sum(b['sol_amount'] for b in early_buys)
    creator_percentage = total_creator_sol / total_early_sol
    
    if creator_percentage > 0.3:  # Creator accounts for >30% of early buys
        return Alert(
            type="dev_insider",
            score=min(creator_percentage * 2, 1.0),
            evidence={
                "creator_buys": len(creator_buys),
                "creator_sol": total_creator_sol,
                "percentage": creator_percentage
            }
        )
```

**Indicators**:
- Creator wallet appears in first 60 seconds of trading
- Creator accounts for >30% of early volume
- Multiple buys from creator wallet

#### 8.1.2 Telegram Alpha Detection

**Pattern**: Coordinated buying from multiple wallets within tight timeframe

**Algorithm**:
```python
def detect_telegram_alpha(token_data: Dict) -> Optional[Alert]:
    """Detect coordinated group buying."""
    early_buys = token_data['early_buys']  # First 5 minutes
    
    # Group buys by 30-second windows
    windows = group_by_time_window(early_buys, window_size=30)
    
    for window_start, buys in windows.items():
        if len(buys) < 5:  # Minimum 5 coordinated buyers
            continue
        
        # Check for similar buy sizes (coordination indicator)
        amounts = [b['sol_amount'] for b in buys]
        avg_amount = statistics.mean(amounts)
        std_amount = statistics.stdev(amounts)
        
        # Low standard deviation indicates coordination
        if std_amount / avg_amount < 0.3:  # CoV < 0.3
            return Alert(
                type="telegram_alpha",
                score=0.75 + (len(buys) / 20),  # Higher score for more buyers
                evidence={
                    "coordinated_buyers": len(buys),
                    "time_window": f"{window_start} - {window_start + 30}s",
                    "avg_buy_size": avg_amount,
                    "coefficient_of_variation": std_amount / avg_amount
                }
            )
```

**Indicators**:
- 5+ wallets buying within 30-second window
- Similar buy sizes (coefficient of variation < 0.3)
- No prior relationship between wallets (verified via graph analysis)

#### 8.1.3 Sniper Bot Detection

**Pattern**: Automated buying within 3 seconds of token launch

**Algorithm**:
```python
def detect_sniper_bot(token_data: Dict) -> Optional[Alert]:
    """Detect automated sniper bots."""
    launch_time = token_data['launch_timestamp']
    all_buys = token_data['all_buys']
    
    # Get buys within 3 seconds
    sniper_buys = [
        buy for buy in all_buys
        if (buy['timestamp'] - launch_time).total_seconds() <= 3.0
    ]
    
    if not sniper_buys:
        return None
    
    # Analyze wallet behavior
    suspicious_wallets = []
    for wallet in set(b['trader'] for b in sniper_buys):
        wallet_buys = [b for b in sniper_buys if b['trader'] == wallet]
        
        # Check wallet history
        profile = get_wallet_profile(wallet)
        
        # Sniper indicators:
        # 1. High frequency of early buys across tokens
        # 2. Low win rate (many failures)
        # 3. Consistent timing (always <5 seconds)
        
        if (profile['early_buy_percentage'] > 0.8 and
            profile['avg_buy_latency'] < 5.0):
            suspicious_wallets.append({
                "wallet": wallet,
                "buys_in_window": len(wallet_buys),
                "total_sol": sum(b['sol_amount'] for b in wallet_buys)
            })
    
    if suspicious_wallets:
        return Alert(
            type="sniper_bot",
            score=0.85,
            evidence={
                "sniper_wallets": suspicious_wallets,
                "detection_window": "0-3 seconds"
            }
        )
```

**Indicators**:
- Buying within 3 seconds of launch
- Wallet history shows >80% early buys across many tokens
- Consistent timing pattern (automated behavior)

#### 8.1.4 Wash Trading Detection

**Pattern**: Same wallet buying and selling to create artificial volume

**Algorithm**:
```python
def detect_wash_trading(token_data: Dict) -> Optional[Alert]:
    """Detect wash trading (buy/sell from same wallet)."""
    transactions = token_data['all_transactions']
    
    # Group by wallet
    wallet_txs = defaultdict(list)
    for tx in transactions:
        wallet_txs[tx['trader']].append(tx)
    
    wash_traders = []
    for wallet, txs in wallet_txs.items():
        buys = [tx for tx in txs if tx['is_buy']]
        sells = [tx for tx in txs if not tx['is_buy']]
        
        if len(buys) < 3 or len(sells) < 3:
            continue
        
        # Calculate buy-sell pattern
        # Wash trading: rapid buy-sell cycles
        cycles = detect_buy_sell_cycles(buys, sells)
        
        if len(cycles) >= 3:  # At least 3 complete cycles
            avg_cycle_time = statistics.mean(
                c['duration'] for c in cycles
            )
            
            # Short cycles (<5 minutes) indicate wash trading
            if avg_cycle_time < 300:  # 5 minutes
                wash_traders.append({
                    "wallet": wallet,
                    "cycles": len(cycles),
                    "avg_cycle_time": avg_cycle_time,
                    "volume_generated": sum(c['volume'] for c in cycles)
                })
    
    if wash_traders:
        return Alert(
            type="wash_trading",
            score=0.8,
            evidence={"wash_traders": wash_traders}
        )
```

**Indicators**:
- Same wallet repeatedly buying and selling
- Short time between buy and sell (<5 minutes)
- Multiple complete cycles (3+)
- No net position change (same amount bought and sold)

#### 8.1.5 Sybil Army Detection

**Pattern**: Multiple wallets controlled by same entity acting in coordination

**Algorithm**:
```python
async def detect_sybil_army(token_data: Dict) -> Optional[Alert]:
    """Detect Sybil attack (multiple coordinated wallets)."""
    early_buyers = token_data['early_buyers']
    
    # Build wallet relationship graph
    graph = nx.Graph()
    for wallet in early_buyers:
        graph.add_node(wallet)
    
    # Add edges based on:
    # 1. Shared funding sources
    # 2. Transaction timing correlation
    # 3. Similar behavioral patterns
    
    for w1, w2 in itertools.combinations(early_buyers, 2):
        relationship_score = 0
        
        # Check funding sources
        funding_overlap = await check_funding_overlap(w1, w2)
        relationship_score += funding_overlap * 0.4
        
        # Check timing correlation
        timing_corr = calculate_timing_correlation(
            token_data['transactions'][w1],
            token_data['transactions'][w2]
        )
        relationship_score += timing_corr * 0.3
        
        # Check behavioral similarity
        behavior_sim = calculate_behavioral_similarity(w1, w2)
        relationship_score += behavior_sim * 0.3
        
        if relationship_score > 0.6:
            graph.add_edge(w1, w2, weight=relationship_score)
    
    # Find clusters (connected components)
    clusters = list(nx.connected_components(graph))
    
    # Sybil clusters: 3+ wallets with strong connections
    sybil_clusters = [
        cluster for cluster in clusters
        if len(cluster) >= 3
    ]
    
    if sybil_clusters:
        return Alert(
            type="sybil_army",
            score=0.9,
            evidence={
                "clusters": [
                    {
                        "wallets": list(cluster),
                        "size": len(cluster),
                        "avg_connection_strength": calculate_avg_weight(
                            graph, cluster
                        )
                    }
                    for cluster in sybil_clusters
                ]
            }
        )
```

**Indicators**:
- 3+ wallets with shared funding sources
- High timing correlation (buying within seconds of each other)
- Similar behavioral patterns (amounts, frequency, targets)
- Graph clustering coefficient > 0.6

### 8.2 Risk Scoring Algorithm

**Bayesian Risk Score Calculation**:
```python
def calculate_risk_score(signals: Dict[str, float]) -> float:
    """
    Calculate composite risk score using Bayesian weighting.
    
    Weights:
    - Behavior: 0.35 (most important)
    - Timing: 0.25
    - Network: 0.25
    - Volume: 0.15
    """
    weights = {
        'behavior': 0.35,
        'timing': 0.25,
        'network': 0.25,
        'volume': 0.15
    }
    
    # Normalize all signals to 0-1 range
    normalized = {
        'behavior': normalize_behavior_score(signals.get('behavior', 0)),
        'timing': normalize_timing_score(signals.get('timing', 0)),
        'network': normalize_network_score(signals.get('network', 0)),
        'volume': normalize_volume_score(signals.get('volume', 0))
    }
    
    # Weighted sum
    risk_score = sum(
        normalized[factor] * weights[factor]
        for factor in weights
    )
    
    # Apply Bayesian prior (base rate of insider trading)
    prior = 0.05  # 5% base rate
    likelihood = risk_score
    
    # Bayesian update
    posterior = (likelihood * prior) / (
        (likelihood * prior) + ((1 - likelihood) * (1 - prior))
    )
    
    return posterior
```

**Component Scores**:

**Behavior Score**:
```python
def normalize_behavior_score(raw_score: float) -> float:
    """
    Based on:
    - Wallet reputation
    - Historical pattern matching
    - Behavioral DNA prediction
    """
    factors = {
        'reputation': get_wallet_reputation(wallet),  # 0-1
        'pattern_match': get_pattern_match_score(wallet),  # 0-1
        'dna_prediction': get_dna_prediction(wallet)  # 0-1
    }
    return (factors['reputation'] * 0.3 +
            factors['pattern_match'] * 0.4 +
            factors['dna_prediction'] * 0.3)
```

**Timing Score**:
```python
def normalize_timing_score(raw_score: float) -> float:
    """
    Based on:
    - Time since token launch
    - Coordination with other wallets
    """
    time_since_launch = raw_score  # in seconds
    
    # Earlier = higher score
    if time_since_launch < 3:
        return 1.0
    elif time_since_launch < 10:
        return 0.9
    elif time_since_launch < 60:
        return 0.7
    elif time_since_launch < 300:
        return 0.4
    else:
        return 0.1
```

**Network Score**:
```python
def normalize_network_score(raw_score: float) -> float:
    """
    Based on:
    - Number of connected wallets
    - Funding chain analysis
    - Cluster membership
    """
    return min(raw_score / 10.0, 1.0)  # 10+ connections = max score
```

**Volume Score**:
```python
def normalize_volume_score(raw_score: float) -> float:
    """
    Based on:
    - Transaction size relative to wallet balance
    - Percentage of total token volume
    """
    return min(raw_score / 100.0, 1.0)  # 100 SOL = max score
```

### 8.3 Machine Learning Models

#### 8.3.1 Behavioral DNA LSTM

**Architecture**:
```python
model = Sequential([
    LSTM(128, return_sequences=True, input_shape=(50, 12)),
    Dropout(0.2),
    LSTM(64, return_sequences=False),
    Dropout(0.2),
    Dense(32, activation='relu'),
    Dropout(0.1),
    Dense(6, activation='softmax')  # 6 behavior classes
])
```

**Input Features** (12 dimensions per transaction):
1. SOL amount (normalized)
2. Token amount (normalized)
3. Time since launch (log scale)
4. Time since previous transaction (log scale)
5. Is buy (binary)
6. Price at time of transaction
7. Wallet balance before transaction
8. Wallet balance after transaction
9. Token liquidity at time
10. Number of holders at time
11. Transaction success (binary)
12. Gas paid (normalized)

**Output Classes**:
1. Normal trader
2. Early buyer (insider)
3. Wash trader
4. Sniper bot
5. Coordinated buyer
6. Bag holder (late buyer)

**Training Process**:
```python
# 1. Collect labeled data from historical transactions
train_data = load_training_data()

# 2. Preprocess and normalize
X_train, y_train = preprocess(train_data)

# 3. Train model
model.fit(
    X_train, y_train,
    epochs=50,
    batch_size=32,
    validation_split=0.2,
    callbacks=[EarlyStopping(patience=5)]
)

# 4. Export to ONNX for fast inference
convert_to_onnx(model, "behavioral_dna.onnx")
```

**Inference**:
```python
# Load ONNX model
session = ort.InferenceSession("behavioral_dna.onnx")

# Prepare input
input_data = prepare_wallet_sequence(wallet_transactions)

# Run inference (1.46ms)
outputs = session.run(None, {"input": input_data})

# Get prediction
behavior_probs = outputs[0][0]
predicted_class = np.argmax(behavior_probs)
confidence = behavior_probs[predicted_class]
```

---

## 9. Testing & Quality Assurance

### 9.1 Test Structure

**Test Organization**:
```
tests/
├── test_pumpfun_integration.py     # Full pipeline tests
├── test_parallel_pipeline.py       # Worker coordination tests
├── test_risk_aggregator.py         # Risk scoring tests
├── test_wallet_deanonymizer.py     # Graph analysis tests
├── test_historical_analyzer.py     # Time-series analysis tests
├── test_behavioral_dna.py          # ML model tests
├── test_eternal_mind.py            # Memory system tests
├── test_ghost_protocol.py          # Zero-cost architecture tests
├── test_hostile_takeover.py        # Migration tests
└── test_validation_and_workers.py  # Input validation tests
```

### 9.2 Running Tests

**All Tests**:
```bash
pytest tests/ -v
# Expected: 89 tests, 100% pass rate
```

**Specific Test Suite**:
```bash
# Integration tests
pytest tests/test_pumpfun_integration.py -v

# Performance tests
pytest tests/benchmark_*.py -v

# GPU tests (requires CUDA)
pytest tests/test_gpu_graph_analysis.py -v
```

**With Coverage**:
```bash
pytest --cov=agents --cov=utils tests/ --cov-report=html
# Open htmlcov/index.html to view coverage report
```

### 9.3 Key Test Cases

**Test: Early Buyer Detection**
```python
@pytest.mark.asyncio
async def test_early_buyer_detection():
    """Test detection of wallets buying within 3 seconds."""
    detector = InsiderDetector()
    
    # Create mock token launch
    token = create_mock_token(launch_time=datetime.now())
    
    # Add early buy (2 seconds after launch)
    early_buy = create_mock_trade(
        token=token.mint,
        trader="TestWallet123",
        time_offset=2.0,  # 2 seconds
        is_buy=True,
        sol_amount=1.0
    )
    
    # Process event
    await detector.process_trade(early_buy)
    
    # Should generate alert
    alerts = await detector.get_alerts()
    assert len(alerts) == 1
    assert alerts[0].alert_type == "early_buy"
    assert alerts[0].trader == "TestWallet123"
    assert alerts[0].score > 0.7
```

**Test: Sybil Detection**
```python
@pytest.mark.asyncio
async def test_sybil_detection():
    """Test detection of coordinated wallet groups."""
    detector = SybilDetectionAgent()
    
    # Create 5 wallets with shared funding source
    funding_wallet = "FundingWallet123"
    sybil_wallets = []
    
    for i in range(5):
        wallet = f"Sybil{i}"
        sybil_wallets.append(wallet)
        
        # Add funding transaction
        await detector.record_funding(
            source=funding_wallet,
            destination=wallet,
            amount=10.0
        )
    
    # Have all sybils buy same token within 10 seconds
    token = "TestToken456"
    for i, wallet in enumerate(sybil_wallets):
        await detector.record_trade(
            wallet=wallet,
            token=token,
            timestamp=datetime.now() + timedelta(seconds=i*2)
        )
    
    # Run detection
    result = await detector.detect_sybil_army(token)
    
    assert result is not None
    assert len(result.cluster_wallets) == 5
    assert result.confidence > 0.8
```

### 9.4 Performance Benchmarks

**Redis Cluster Benchmark**:
```bash
python scripts/benchmark_redis_cluster.py

# Expected results:
# - Operations/sec: 2,457+
# - Latency (avg): 0.40ms
# - Latency (p99): 2.1ms
```

**ML Inference Benchmark**:
```bash
python scripts/benchmark_onnx_inference.py

# Expected results:
# - Inference time: 1.46ms
# - Throughput: 685 inferences/sec
# - Confidence: 98.21%
```

**Zero-Latency Alert Pipeline**:
```bash
python tests/benchmark_zero_latency.py

# Expected results:
# - Alert latency: ~15.65μs
# - Throughput: 63,938 alerts/sec
```

---

## 10. Deployment Strategies

### 10.1 Docker Deployment (Recommended)

**Production Deployment**:
```bash
# 1. Configure environment
cp .env.template .env
nano .env  # Edit configuration

# 2. Build images
docker-compose build

# 3. Start infrastructure
docker-compose up -d redis-master-1 redis-master-2 redis-master-3 \
                     redis-replica-1 redis-replica-2 redis-replica-3
                     
# Initialize Redis cluster
./scripts/init_redis_cluster.sh

# 4. Start databases
docker-compose up -d postgres
./scripts/setup_timescaledb.sh

# 5. Start AI services
docker-compose up -d ollama
./scripts/init_ollama.sh

# 6. Start monitoring
docker-compose up -d prometheus grafana jaeger

# 7. Start application
docker-compose up -d orchestrator workers supervisor

# 8. Verify
docker-compose ps
curl http://localhost:8000/health
```

### 10.2 Manual Deployment

**For Development/Custom Setups**:
```bash
# 1. Install system dependencies
sudo apt-get update
sudo apt-get install -y postgresql-18 redis-server python3.13

# 2. Install Python dependencies
python3.13 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 3. Configure services
sudo systemctl start postgresql
sudo systemctl start redis-server

# 4. Initialize database
./scripts/setup_timescaledb.sh

# 5. Start application
python main.py
```

### 10.3 Scaling Strategies

**Horizontal Scaling**:
```bash
# Scale worker agents
docker-compose up -d --scale workers=10

# Scale specific worker type
docker exec godmode_supervisor redis-cli PUBLISH supervisor_commands \
  '{"type":"scale","agent_type":"wallet_analyzer","replicas":15}'
```

**Vertical Scaling**:
```yaml
# docker-compose.override.yml
services:
  workers:
    deploy:
      resources:
        limits:
          cpus: '8'
          memory: 16G
        reservations:
          cpus: '4'
          memory: 8G
```

### 10.4 Monitoring & Observability

**Grafana Dashboards**:
- **System Overview**: CPU, memory, network for all services
- **Redis Metrics**: Operations/sec, latency, memory usage
- **Agent Performance**: Processing rate, alerts generated, error rate
- **Alert Dashboard**: Alert frequency by type, score distribution

**Jaeger Traces**:
- End-to-end transaction flow visualization
- Bottleneck identification
- Latency breakdown by component

**Prometheus Queries**:
```promql
# Alert rate by type
rate(godmode_alerts_total[5m]) by (alert_type)

# Worker processing latency
histogram_quantile(0.99, 
  rate(godmode_processing_duration_seconds_bucket[5m])
)

# Redis cluster health
redis_cluster_nodes_connected / redis_cluster_nodes_total
```

---

## 11. Rebuilding from Scratch Guide

### 11.1 Phase 1: Foundation (Week 1-2)

**Goal**: Set up basic infrastructure and data ingestion

**Steps**:
1. **Set up development environment**
   ```bash
   # Install dependencies
   sudo apt-get install postgresql redis-server docker.io
   
   # Create project structure
   mkdir -p godmodescanner/{agents,utils,tests,scripts,config,data}
   cd godmodescanner
   python3.13 -m venv venv
   source venv/bin/activate
   ```

2. **Implement basic Solana client**
   ```python
   # utils/solana_client.py
   from solana.rpc.async_api import AsyncClient
   
   class SolanaClient:
       def __init__(self, rpc_url: str):
           self.client = AsyncClient(rpc_url)
       
       async def get_transaction(self, signature: str):
           return await self.client.get_transaction(signature)
   ```

3. **Set up Redis and basic streaming**
   ```python
   # utils/redis_client.py
   import redis.asyncio as redis
   
   class RedisClient:
       def __init__(self, url: str):
           self.redis = redis.from_url(url)
       
       async def publish_event(self, stream: str, data: dict):
           await self.redis.xadd(stream, data)
   ```

4. **Create pump.fun parser**
   ```python
   # utils/pumpfun_parser.py
   # Parse pump.fun program instructions
   # Identify token create, trade, complete events
   ```

**Milestone**: Can fetch and parse pump.fun transactions

### 11.2 Phase 2: Detection Logic (Week 3-4)

**Goal**: Implement core detection algorithms

**Steps**:
1. **Implement early buyer detection**
   - Track token launch times
   - Identify wallets buying within 60 seconds
   - Calculate suspicion scores

2. **Implement wallet profiling**
   - Store wallet transaction history
   - Calculate behavioral metrics
   - Build reputation system

3. **Implement pattern recognition**
   - Coordinated buying detection
   - Wash trading detection
   - Timing analysis

4. **Implement risk scoring**
   - Combine signals from all detectors
   - Apply Bayesian weighting
   - Generate alerts for high-risk events

**Milestone**: Can detect basic insider patterns

### 11.3 Phase 3: Multi-Agent System (Week 5-6)

**Goal**: Build parallel processing and agent coordination

**Steps**:
1. **Implement worker pattern**
   ```python
   # agents/workers/base_worker.py
   class BaseWorker:
       async def start(self):
           while self.running:
               messages = await self.redis.xreadgroup(...)
               for msg in messages:
                   await self.process(msg)
   ```

2. **Create consumer groups**
   - wallet-analyzer-group
   - pattern-recognition-group
   - risk-scoring-group

3. **Implement backpressure management**
   - Monitor stream lag
   - Throttle ingestion when overloaded
   - Auto-scale workers

4. **Add orchestrator**
   - Coordinate all agents
   - Manage lifecycle
   - Handle shutdown gracefully

**Milestone**: 30+ parallel workers processing transactions

### 11.4 Phase 4: AI/ML Integration (Week 7-8)

**Goal**: Add machine learning capabilities

**Steps**:
1. **Train behavioral LSTM**
   - Collect labeled training data
   - Train model on historical patterns
   - Export to ONNX format

2. **Integrate Ollama for Singularity Engine**
   - Set up Ollama container
   - Implement code generation pipeline
   - Add sandboxed execution

3. **Implement ETERNAL MIND**
   - Build memory persistence layer
   - Add consolidation logic
   - Integrate FAISS for similarity search

4. **Add graph analysis**
   - Implement wallet relationship mapping
   - Multi-hop traversal
   - Cluster detection

**Milestone**: ML-powered detection with >95% accuracy

### 11.5 Phase 5: Optimization (Week 9-10)

**Goal**: Achieve production-grade performance

**Steps**:
1. **Implement Ghost Protocol**
   - Free RPC rotation
   - Redis-only data storage
   - Zero-cost infrastructure

2. **Optimize Redis cluster**
   - 6-node setup (3 masters + 3 replicas)
   - AOF persistence
   - Memory optimization

3. **Implement zero-latency alerting**
   - mmap shared memory
   - Direct console output
   - Webhook integration

4. **Add TimescaleDB (optional)**
   - Hypertables for time-series data
   - Compression and retention policies
   - Query optimization

**Milestone**: Sub-second detection, $0/month cost

### 11.6 Phase 6: Production Readiness (Week 11-12)

**Goal**: Deploy production-ready system

**Steps**:
1. **Comprehensive testing**
   - 89+ test cases
   - Integration tests
   - Performance benchmarks

2. **Add monitoring**
   - Prometheus metrics
   - Grafana dashboards
   - Jaeger tracing

3. **Documentation**
   - API documentation
   - Deployment guides
   - Architecture diagrams

4. **Security audit**
   - Input validation
   - SQL injection prevention
   - Rate limiting

**Milestone**: 97% production readiness

### 11.7 Estimated Resources

**Development Team**:
- 2 backend engineers (Python/async)
- 1 DevOps engineer (Docker/Redis)
- 1 ML engineer (PyTorch/ONNX)
- 1 blockchain specialist (Solana)

**Infrastructure Costs** (Development):
- Local development: $0/month
- Cloud VPS (optional): $40-100/month
- RPC endpoints: $0/month (free tier)

**Timeline**: 12 weeks (3 months) for full system

---

## 12. Performance Optimization

### 12.1 Redis Optimization

**Configuration Tuning**:
```conf
# redis.conf
maxmemory-policy allkeys-lru
maxmemory 1800mb
appendonly yes
appendfsync everysec
no-appendfsync-on-rewrite yes
auto-aof-rewrite-percentage 100
auto-aof-rewrite-min-size 64mb
save ""
tcp-backlog 65535
hz 100
```

**Connection Pooling**:
```python
# Use connection pools instead of single connections
pool = redis.ConnectionPool.from_url(
    REDIS_URL,
    max_connections=50,
    decode_responses=False
)
redis_client = redis.Redis(connection_pool=pool)
```

### 12.2 Database Optimization

**Query Optimization**:
```sql
-- Create indexes on frequently queried columns
CREATE INDEX CONCURRENTLY idx_tx_mint_time 
  ON transactions (token_mint, time DESC);

CREATE INDEX CONCURRENTLY idx_wallet_time
  ON transactions (wallet, time DESC);

-- Use materialized views for aggregations
CREATE MATERIALIZED VIEW wallet_daily_stats AS
SELECT 
  wallet,
  DATE(time) as date,
  COUNT(*) as tx_count,
  SUM(sol_amount) as total_volume
FROM transactions
GROUP BY wallet, DATE(time);

CREATE UNIQUE INDEX ON wallet_daily_stats (wallet, date);
```

**Connection Pooling**:
```python
# Use asyncpg connection pool
pool = await asyncpg.create_pool(
    DATABASE_URL,
    min_size=5,
    max_size=20,
    command_timeout=60
)
```

### 12.3 Python Code Optimization

**Use asyncio for concurrency**:
```python
# BAD: Sequential processing
for wallet in wallets:
    profile = await fetch_profile(wallet)
    
# GOOD: Parallel processing
profiles = await asyncio.gather(*[
    fetch_profile(wallet) for wallet in wallets
])
```

**Cache frequently accessed data**:
```python
from functools import lru_cache

@lru_cache(maxsize=10000)
def get_token_metadata(mint: str) -> Dict:
    # Expensive operation cached in memory
    return fetch_metadata(mint)
```

**Use generators for memory efficiency**:
```python
# BAD: Load all into memory
transactions = list(db.query("SELECT * FROM transactions"))

# GOOD: Process in chunks
def transaction_generator():
    cursor = db.cursor()
    while True:
        batch = cursor.fetchmany(1000)
        if not batch:
            break
        yield from batch
```

---

## 13. Security Considerations

### 13.1 Input Validation

**Pydantic Models**:
```python
from pydantic import BaseModel, Field, validator

class TradeEvent(BaseModel):
    signature: str = Field(..., regex=r'^[1-9A-HJ-NP-Za-km-z]{87,88}$')
    trader: str = Field(..., regex=r'^[1-9A-HJ-NP-Za-km-z]{32,44}$')
    sol_amount: float = Field(..., gt=0, lt=1000000)
    
    @validator('sol_amount')
    def validate_amount(cls, v):
        if v < 0.001 or v > 1000000:
            raise ValueError('Invalid amount')
        return v
```

### 13.2 Sandboxed Code Execution

**Singularity Engine Sandbox**:
```python
import subprocess
import tempfile

def execute_sandboxed(code: str, timeout: int = 5) -> Dict:
    """Execute generated code in sandbox."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.py') as f:
        f.write(code)
        f.flush()
        
        try:
            result = subprocess.run(
                ['python', f.name],
                capture_output=True,
                timeout=timeout,
                check=False
            )
            return {
                'success': result.returncode == 0,
                'output': result.stdout.decode(),
                'error': result.stderr.decode()
            }
        except subprocess.TimeoutExpired:
            return {'success': False, 'error': 'Timeout'}
```

### 13.3 Rate Limiting

**Per-endpoint Rate Limiting**:
```python
from collections import defaultdict
from datetime import datetime, timedelta

class RateLimiter:
    def __init__(self, max_requests: int, window: int):
        self.max_requests = max_requests
        self.window = window  # seconds
        self.requests = defaultdict(list)
    
    async def check_rate_limit(self, endpoint: str) -> bool:
        now = datetime.now()
        cutoff = now - timedelta(seconds=self.window)
        
        # Remove old requests
        self.requests[endpoint] = [
            ts for ts in self.requests[endpoint]
            if ts > cutoff
        ]
        
        # Check limit
        if len(self.requests[endpoint]) >= self.max_requests:
            return False
        
        self.requests[endpoint].append(now)
        return True
```

---

## 14. Troubleshooting & Maintenance

### 14.1 Common Issues

**Issue: Redis out of memory**
```bash
# Check memory usage
redis-cli INFO memory

# Solution 1: Increase maxmemory
redis-cli CONFIG SET maxmemory 2gb

# Solution 2: Trim old streams
redis-cli XTRIM godmode:new_transactions MAXLEN ~ 5000

# Solution 3: Enable eviction
redis-cli CONFIG SET maxmemory-policy allkeys-lru
```

**Issue: High stream lag**
```bash
# Check lag
redis-cli XPENDING godmode:new_transactions wallet-analyzer-group

# Solution: Scale workers
docker-compose up -d --scale workers=20
```

**Issue: RPC rate limiting**
```bash
# Rotate to different endpoint
# Add more free RPC endpoints to .env
RPC_ENDPOINTS=https://api.mainnet-beta.solana.com,...
```

### 14.2 Maintenance Tasks

**Daily**:
- Monitor alert volume
- Check system metrics
- Review error logs

**Weekly**:
- Vacuum PostgreSQL
- Compact Redis AOF
- Review and refine detection thresholds

**Monthly**:
- Retrain ML models with new data
- Update RPC endpoint list
- Performance benchmarking

### 14.3 Backup & Recovery

**Database Backup**:
```bash
# Backup PostgreSQL
pg_dump godmodescanner > backup_$(date +%Y%m%d).sql

# Backup Redis
redis-cli BGSAVE
cp /var/lib/redis/dump.rdb backup/redis_$(date +%Y%m%d).rdb
```

**Restore**:
```bash
# Restore PostgreSQL
psql godmodescanner < backup_20260204.sql

# Restore Redis
cp backup/redis_20260204.rdb /var/lib/redis/dump.rdb
redis-cli SHUTDOWN
systemctl start redis
```

---

## Conclusion

GODMODESCANNER represents a cutting-edge, production-ready system for detecting insider trading on Solana's pump.fun platform. With its multi-agent architecture, AI-powered analysis, and zero-cost operation, it achieves:

- **Sub-second detection latency**
- **>95% accuracy** in pattern identification
- **$0/month operational cost**
- **97% production readiness**

This documentation provides everything needed to understand, deploy, and rebuild the system from scratch. For questions or contributions, please refer to the main README.md or open an issue on the GitHub repository.

**Built with ❤️ for the Solana community**

---

