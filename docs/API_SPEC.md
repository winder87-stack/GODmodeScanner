# GODMODESCANNER API Specification

**Version:** 1.0.0  
**Last Updated:** 2026-01-25  
**Project:** GODMODESCANNER - Elite AI-Powered Insider Trading Detection System

---

## Table of Contents

1. [Overview](#overview)
2. [Redis Streams API](#redis-streams-api)
3. [Redis Pub/Sub Channels](#redis-pubsub-channels)
4. [MCP Server Interfaces](#mcp-server-interfaces)
5. [Agent Zero Profiles](#agent-zero-profiles)
6. [Configuration Reference](#configuration-reference)
7. [Data Models](#data-models)
8. [Error Handling](#error-handling)

---

## Overview

GODMODESCANNER exposes multiple API interfaces for real-time blockchain monitoring, insider trading detection, and multi-agent coordination:

- **Redis Streams**: High-throughput message queuing for transaction processing
- **Redis Pub/Sub**: Real-time event broadcasting for monitoring and alerts
- **MCP Server**: Model Context Protocol for agent orchestration
- **Agent Zero**: Hierarchical multi-agent framework with 6 specialized profiles

### Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    GODMODESCANNER API                       │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌──────────────┐  ┌──────────────┐  ┌─────────────────┐  │
│  │ Redis Streams│  │ Redis Pub/Sub│  │  MCP Server     │  │
│  │              │  │              │  │                 │  │
│  │ • Transactions│  │ • Heartbeats │  │ • Orchestrator  │  │
│  │ • Token Launch│  │ • Alerts     │  │ • Supervisors   │  │
│  │ • Trades      │  │ • Control    │  │ • Agent Registry│  │
│  │ • Risk Scores │  │              │  │                 │  │
│  └──────────────┘  └──────────────┘  └─────────────────┘  │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐  │
│  │           Agent Zero Framework (6 Profiles)         │  │
│  │                                                     │  │
│  │  • Transaction Analyst  • Risk Assessor            │  │
│  │  • Graph Analyst        • Orchestrator             │  │
│  │  • Researcher           • Developer                │  │
│  └─────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

---

## Redis Streams API

### Overview

Redis Streams provide durable, ordered message queuing for high-throughput transaction processing. GODMODESCANNER uses 5 primary streams with 7 consumer groups supporting 30+ parallel workers.

### Stream Names

| Stream Name | Purpose | Throughput | Retention |
|-------------|---------|------------|----------|
| `godmode:new_transactions` | Raw Solana transactions | 1000+ TPS | 24 hours |
| `godmode:new_tokens` | Token launch events | 100+ TPS | 7 days |
| `godmode:trades` | Buy/sell swap events | 500+ TPS | 24 hours |
| `godmode:alerts` | High-risk alerts | 10+ TPS | 30 days |
| `godmode:risk_scores` | Risk assessment results | 100+ TPS | 7 days |

### Consumer Groups

| Consumer Group | Stream | Workers | Purpose |
|----------------|--------|---------|----------|
| `wallet-analyzer-group` | `godmode:new_transactions` | 10 | Wallet profiling and behavior analysis |
| `pattern-recognition-group` | `godmode:new_transactions` | 10 | Insider pattern detection (6 types) |
| `sybil-detection-group` | `godmode:new_transactions` | 10 | Sybil network identification |
| `token-tracker-group` | `godmode:new_tokens` | 5 | Token launch monitoring |
| `risk-aggregator-group` | `godmode:risk_scores` | 3 | Risk score aggregation |
| `alert-dispatcher-group` | `godmode:alerts` | 2 | Multi-channel alert delivery |
| `early-detection-group` | `godmode:new_tokens` | 5 | Early buyer detection (<60s) |

---

### Stream: `godmode:new_transactions`

**Purpose**: Raw Solana transactions from pump.fun program

**Message Schema**:

```json
{
  "event_type": "transaction",
  "timestamp": "2026-01-25T14:39:20.123456Z",
  "data": {
    "signature": "5J7...",
    "slot": 123456789,
    "block_time": 1706198360,
    "transaction": {
      "message": {
        "account_keys": ["7xKX...", "6EF8..."],
        "instructions": [
          {
            "program_id_index": 1,
            "accounts": [0, 2, 3],
            "data": "base58_encoded_data"
          }
        ]
      },
      "signatures": ["5J7..."]
    },
    "meta": {
      "err": null,
      "fee": 5000,
      "pre_balances": [1000000000, 0],
      "post_balances": [999995000, 0],
      "log_messages": ["Program log: ..."],
      "inner_instructions": []
    },
    "enrichment": {
      "wallet_balance": 1.5,
      "token_metadata": {
        "name": "Example Token",
        "symbol": "EXT",
        "uri": "https://..."
      },
      "account_info": {
        "owner": "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA",
        "lamports": 2039280,
        "data": "base64_encoded"
      }
    }
  },
  "detected_at": "2026-01-25T14:39:20.125Z",
  "latency_ms": 1.8
}
```

**Field Descriptions**:

| Field | Type | Description |
|-------|------|-------------|
| `event_type` | string | Always "transaction" for this stream |
| `timestamp` | ISO 8601 | Event generation timestamp |
| `data.signature` | string (base58) | Unique transaction signature |
| `data.slot` | integer | Solana slot number |
| `data.block_time` | integer (unix) | Block timestamp |
| `data.transaction` | object | Full Solana transaction object |
| `data.meta` | object | Transaction metadata (fees, balances, logs) |
| `data.enrichment` | object | Additional data from RPC enrichment |
| `detected_at` | ISO 8601 | Detection timestamp by monitor |
| `latency_ms` | float | Detection latency in milliseconds |

**Consumer Example** (Python):

```python
import redis.asyncio as redis
import json

async def consume_transactions():
    r = await redis.from_url("redis://localhost:6379")

    # Create consumer group (idempotent)
    try:
        await r.xgroup_create(
            "godmode:new_transactions",
            "my-consumer-group",
            "$",
            mkstream=True
        )
    except redis.ResponseError:
        pass  # Group already exists

    # Consume messages
    while True:
        messages = await r.xreadgroup(
            "my-consumer-group",
            "consumer-1",
            {"godmode:new_transactions": ">"},
            count=10,
            block=5000
        )

        for stream, msg_list in messages:
            for msg_id, fields in msg_list:
                data = json.loads(fields[b"data"])

                # Process transaction
                await process_transaction(data)

                # Acknowledge
                await r.xack("godmode:new_transactions", "my-consumer-group", msg_id)
```

---

### Stream: `godmode:new_tokens`

**Purpose**: Token launch events from pump.fun

**Message Schema**:

```json
{
  "event_type": "token_launch",
  "timestamp": "2026-01-25T14:39:20.123456Z",
  "data": {
    "token_address": "7xKXt...",
    "creator": "9wZq5...",
    "name": "Example Token",
    "symbol": "EXT",
    "uri": "https://arweave.net/...",
    "initial_supply": 1000000000,
    "bonding_curve": {
      "address": "5Jy9...",
      "virtual_sol_reserves": 30000000000,
      "virtual_token_reserves": 1073000000000000,
      "real_sol_reserves": 0,
      "real_token_reserves": 1000000000,
      "token_total_supply": 1000000000,
      "complete": false
    },
    "launch_time": "2026-01-25T14:39:19.500Z",
    "signature": "5J7..."
  },
  "detected_at": "2026-01-25T14:39:20.125Z",
  "latency_ms": 625.0
}
```

**Field Descriptions**:

| Field | Type | Description |
|-------|------|-------------|
| `data.token_address` | string (base58) | SPL token mint address |
| `data.creator` | string (base58) | Token creator wallet |
| `data.bonding_curve.address` | string (base58) | Bonding curve account |
| `data.bonding_curve.virtual_sol_reserves` | integer | Virtual SOL for price calculation |
| `data.bonding_curve.virtual_token_reserves` | integer | Virtual tokens for price calculation |
| `data.bonding_curve.complete` | boolean | Whether bonding curve is complete |
| `data.launch_time` | ISO 8601 | Token creation timestamp |

---

### Stream: `godmode:trades`

**Purpose**: Buy/sell swap events

**Message Schema**:

```json
{
  "event_type": "swap",
  "timestamp": "2026-01-25T14:39:20.123456Z",
  "data": {
    "signature": "5J7...",
    "trader": "9wZq5...",
    "token": "7xKXt...",
    "is_buy": true,
    "sol_amount": 1000000000,
    "token_amount": 50000000,
    "price_per_token": 0.00000002,
    "bonding_curve": "5Jy9...",
    "timestamp": "2026-01-25T14:39:19.800Z",
    "time_since_launch_seconds": 45.3
  },
  "detected_at": "2026-01-25T14:39:20.125Z",
  "latency_ms": 325.0
}
```

**Field Descriptions**:

| Field | Type | Description |
|-------|------|-------------|
| `data.trader` | string (base58) | Wallet executing the swap |
| `data.is_buy` | boolean | true = buy, false = sell |
| `data.sol_amount` | integer (lamports) | SOL amount (1 SOL = 1e9 lamports) |
| `data.token_amount` | integer | Token amount (raw, no decimals) |
| `data.price_per_token` | float | Price in SOL per token |
| `data.time_since_launch_seconds` | float | Seconds since token launch |

---

### Stream: `godmode:alerts`

**Purpose**: High-risk insider trading alerts

**Message Schema**:

```json
{
  "event_type": "alert",
  "timestamp": "2026-01-25T14:39:20.123456Z",
  "data": {
    "alert_id": "alert_1706198360_abc123",
    "severity": "CRITICAL",
    "risk_score": 92.5,
    "confidence": 0.87,
    "wallet": "9wZq5...",
    "token": "7xKXt...",
    "patterns_detected": [
      "dev_insider",
      "early_buyer",
      "sybil_network"
    ],
    "evidence": {
      "behavior_score": 0.95,
      "timing_score": 0.88,
      "network_score": 0.92,
      "volume_score": 0.85,
      "early_buy_seconds": 12.5,
      "sybil_cluster_size": 15,
      "creator_connection": true
    },
    "recommended_action": "IMMEDIATE_INVESTIGATION",
    "related_wallets": ["5Jy9...", "3Kx7..."],
    "transaction_signatures": ["5J7...", "8Mn2..."]
  },
  "detected_at": "2026-01-25T14:39:20.125Z"
}
```

**Severity Levels**:

| Level | Risk Score Range | Description |
|-------|------------------|-------------|
| `CRITICAL` | ≥ 85 | Immediate investigation required |
| `HIGH` | 70-84 | High probability insider trading |
| `MEDIUM` | 50-69 | Suspicious activity, monitor closely |
| `LOW` | < 50 | Minor anomalies detected |

---

### Stream: `godmode:risk_scores`

**Purpose**: Bayesian risk assessment results

**Message Schema**:

```json
{
  "event_type": "risk_score",
  "timestamp": "2026-01-25T14:39:20.123456Z",
  "data": {
    "wallet": "9wZq5...",
    "token": "7xKXt...",
    "risk_score": 78.5,
    "confidence_interval": [72.3, 84.7],
    "confidence_level": 0.95,
    "components": {
      "behavior_score": 82.0,
      "timing_score": 75.0,
      "network_score": 80.0,
      "volume_score": 77.0
    },
    "weights": {
      "behavior": 0.35,
      "timing": 0.25,
      "network": 0.25,
      "volume": 0.15
    },
    "contributing_factors": [
      "Early buyer within 60 seconds",
      "Connected to creator wallet (2-hop)",
      "Part of 15-wallet Sybil cluster",
      "Abnormal transaction frequency (5σ)"
    ],
    "calculation_time_ms": 12.5
  },
  "detected_at": "2026-01-25T14:39:20.125Z"
}
```

**Risk Score Calculation**:

```
Risk Score = (behavior × 0.35) + (timing × 0.25) + (network × 0.25) + (volume × 0.15)
```

---

## Redis Pub/Sub Channels

### Overview

Redis Pub/Sub provides real-time event broadcasting for monitoring, control, and heartbeats. Unlike Streams, Pub/Sub messages are ephemeral and not persisted.

### Channel Names

| Channel | Purpose | Message Rate | Subscribers |
|---------|---------|--------------|-------------|
| `godmode:transactions` | Real-time transaction events | 1000+ msg/s | Monitoring dashboards |
| `godmode:token_launches` | Token launch notifications | 100+ msg/s | Alert systems |
| `godmode:trades` | Swap event notifications | 500+ msg/s | Trading bots |
| `godmode:control` | Agent control commands | <1 msg/s | All agents |
| `godmode:heartbeat:transaction_monitor` | Transaction monitor health | 1 msg/min | Health monitors |
| `godmode:heartbeat:risk_scoring` | Risk scoring agent health | 1 msg/min | Health monitors |
| `godmode:heartbeat:wallet_analyzer` | Wallet analyzer health | 1 msg/min | Health monitors |

---

### Channel: `godmode:transactions`

**Purpose**: Real-time transaction event broadcasting

**Message Schema**: Same as `godmode:new_transactions` stream

**Subscriber Example**:

```python
import redis.asyncio as redis
import json

async def subscribe_transactions():
    r = await redis.from_url("redis://localhost:6379")
    pubsub = r.pubsub()

    await pubsub.subscribe("godmode:transactions")

    async for message in pubsub.listen():
        if message["type"] == "message":
            data = json.loads(message["data"])
            print(f"Transaction: {data['transaction']['signature']}")
```

---

### Channel: `godmode:control`

**Purpose**: Agent control and coordination

**Message Schema**:

```json
{
  "command": "pause|resume|shutdown|config_update",
  "target": "all|transaction_monitor|wallet_analyzer|...",
  "parameters": {
    "reason": "Maintenance window",
    "duration_seconds": 300
  },
  "timestamp": "2026-01-25T14:39:20.123456Z",
  "sender": "orchestrator_main"
}
```

**Commands**:

| Command | Description | Parameters |
|---------|-------------|------------|
| `pause` | Pause agent processing | `duration_seconds`, `reason` |
| `resume` | Resume agent processing | - |
| `shutdown` | Graceful agent shutdown | `reason` |
| `config_update` | Update agent configuration | `config` (JSON object) |

---

### Channel: `godmode:heartbeat:*`

**Purpose**: Agent health monitoring

**Message Schema**:

```json
{
  "agent_id": "transaction_monitor_001",
  "agent_type": "transaction_monitor",
  "status": "healthy|degraded|unhealthy",
  "timestamp": "2026-01-25T14:39:20.123456Z",
  "uptime_seconds": 86400,
  "metrics": {
    "transactions_processed": 1234567,
    "events_detected": 45678,
    "average_latency_ms": 125.5,
    "error_rate": 0.001,
    "memory_usage_mb": 512.3,
    "cpu_usage_percent": 45.2
  },
  "last_error": null
}
```

---

## MCP Server Interfaces

### Overview

The Model Context Protocol (MCP) server provides agent orchestration, supervision, and registry services. It coordinates 47+ specialized agents across multiple supervisors.

### Architecture

```
┌─────────────────────────────────────────────────────────┐
│                  MCP Orchestrator                       │
│                                                         │
│  ┌──────────────┐  ┌──────────────┐  ┌─────────────┐  │
│  │  Supervisor  │  │  Supervisor  │  │  Supervisor │  │
│  │   Primary    │  │  Secondary   │  │  Tertiary   │  │
│  │              │  │              │  │             │  │
│  │ • Tx Monitor │  │ • Pattern    │  │ • Risk      │  │
│  │ • Wallet     │  │   Recognition│  │   Scoring   │  │
│  │   Analyzer   │  │ • Sybil      │  │ • Alert     │  │
│  │              │  │   Detection  │  │   Manager   │  │
│  └──────────────┘  └──────────────┘  └─────────────┘  │
│                                                         │
│  ┌───────────────────────────────────────────────────┐ │
│  │            Agent Registry (Redis)                 │ │
│  │  • Agent discovery  • Health tracking             │ │
│  │  • Load balancing   • Failover                    │ │
│  └───────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────┘
```

### Orchestrator Configuration

**File**: `config/orchestrator.json`

```json
{
  "redis_url": "redis://localhost:6379",
  "max_supervisors": 3,
  "supervisor_distribution": "round_robin",
  "enable_cross_supervisor_communication": true,
  "orchestrator_id": "orchestrator_main",
  "monitoring": {
    "enabled": true,
    "interval_seconds": 60,
    "metrics_retention_hours": 24
  },
  "supervisor_configs": [
    {
      "supervisor_id": "supervisor_primary",
      "priority": 1,
      "agent_types": ["transaction_monitor", "wallet_analyzer"]
    },
    {
      "supervisor_id": "supervisor_secondary",
      "priority": 2,
      "agent_types": ["pattern_recognition", "sybil_detection"]
    },
    {
      "supervisor_id": "supervisor_tertiary",
      "priority": 3,
      "agent_types": ["risk_scoring", "alert_manager"]
    }
  ]
}
```

### Agent Registry API

**Purpose**: Centralized agent discovery and health tracking

#### Register Agent

```python
await registry.register_agent(
    agent_id="wallet_analyzer_001",
    agent_type="wallet_analyzer",
    supervisor_id="supervisor_primary",
    metadata={
        "version": "1.0.0",
        "capabilities": ["profiling", "behavior_tracking"],
        "max_throughput": 1000
    }
)
```

#### Discover Agents

```python
agents = await registry.get_agents_by_type("wallet_analyzer")
# Returns: [{"agent_id": "...", "status": "healthy", ...}, ...]
```

#### Update Agent Status

```python
await registry.update_agent_status(
    agent_id="wallet_analyzer_001",
    status="healthy",
    metrics={
        "messages_processed": 12345,
        "average_latency_ms": 45.2
    }
)
```

---

## Agent Zero Profiles

### Overview

Agent Zero provides a hierarchical multi-agent framework with 6 specialized profiles. Each profile has unique capabilities and can spawn subordinate agents for complex tasks.

### Profile Architecture

```
┌─────────────────────────────────────────────────────────┐
│                  Master Orchestrator                    │
│  (Coordinates all subordinate agents)                   │
└────────────────────┬────────────────────────────────────┘
                     │
        ┌────────────┼────────────┬────────────┐
        │            │            │            │
   ┌────▼───┐  ┌────▼───┐  ┌────▼───┐  ┌────▼───┐
   │Transaction│ │ Graph  │  │  Risk  │  │Research│
   │ Analyst   │ │Analyst │  │Assessor│  │  Agent │
   └───────────┘ └────────┘  └────────┘  └────────┘
        │                                      │
   ┌────▼───┐                            ┌────▼───┐
   │Developer│                            │Developer│
   │  Agent  │                            │  Agent │
   └─────────┘                            └─────────┘
```

---

### 1. Transaction Analyst

**Profile**: `transaction_analyst`  
**System Prompt**: `agentzero/prompts/transaction_analyst/system_prompt.md`

**Capabilities**:
- Real-time pump.fun transaction monitoring
- Detection of 6 insider trading patterns:
  1. **Dev Insider**: Creator wallet early buying
  2. **Telegram Alpha**: Coordinated group buying
  3. **Sniper Bot**: Sub-second automated buying
  4. **Wash Trader**: Self-trading to inflate volume
  5. **Delayed Insider**: Pre-launch accumulation
  6. **Sybil Army**: Multi-wallet coordinated attacks

**Data Sources**:
- Redis Streams: `godmode:new_transactions`, `godmode:new_tokens`
- TimescaleDB: Historical transaction data
- WebSocket: Real-time Solana RPC

**Output**:
- Pattern detection alerts
- Suspicious wallet lists
- Transaction analysis reports

**Example Task**:
```
Analyze the last 1000 transactions for token 7xKXt... and identify any dev insider patterns. Focus on wallets that bought within 60 seconds of launch and have connections to the creator wallet.
```

---

### 2. Risk Assessor

**Profile**: `risk_assessor`  
**System Prompt**: `agentzero/prompts/risk_assessor/system_prompt.md`

**Capabilities**:
- Bayesian risk scoring engine
- Multi-factor risk aggregation
- Confidence interval calculation
- Alert severity classification

**Scoring Factors** (Weighted):

| Factor | Weight | Description |
|--------|--------|-------------|
| Behavior | 0.35 | Transaction patterns, frequency, aggressiveness |
| Timing | 0.25 | Launch timing, early buying, coordination |
| Network | 0.25 | Wallet connections, Sybil clusters, creator links |
| Volume | 0.15 | Trade sizes, volume patterns, wash trading |

**Alert Thresholds**:
- **CRITICAL**: Risk Score ≥ 85
- **HIGH**: Risk Score ≥ 70
- **MEDIUM**: Risk Score ≥ 50
- **LOW**: Risk Score < 50

**Output Format**:
```json
{
  "wallet": "9wZq5...",
  "risk_score": 92.5,
  "confidence_interval": [87.3, 97.7],
  "severity": "CRITICAL",
  "contributing_factors": [
    "Early buyer (12.5s after launch)",
    "Connected to creator (2-hop)",
    "Part of 15-wallet Sybil cluster"
  ],
  "recommended_action": "IMMEDIATE_INVESTIGATION"
}
```

**Integration**:
- Zero-latency alert pipeline via shared memory ring buffer
- Multi-channel delivery: Telegram, Webhook, Email, Discord

---

### 3. Graph Analyst

**Profile**: `graph_analyst`  
**System Prompt**: `agentzero/prompts/graph_analyst/system_prompt.md`

**Capabilities**:
- Multi-hop wallet de-anonymization (3-5 hops)
- DBSCAN-based clustering
- Funding source identification
- Sybil network mapping

**Performance Targets**:
- Complex analysis: 5-10 seconds
- Simple traces: <2 seconds
- Clustering: <3 seconds

**Traversal Strategy**:
```python
{
  "max_depth": 5,
  "min_transaction_value": 0.01,  # SOL
  "dust_filter": 0.001,  # SOL
  "max_wallets_per_hop": 50,
  "clustering_algorithm": "DBSCAN",
  "clustering_params": {
    "eps": 0.3,
    "min_samples": 3
  }
}
```

**Input Format**:
```json
{
  "wallet": "9wZq5...",
  "analysis_type": "full_trace|funding_source|sybil_detection",
  "max_depth": 3,
  "min_value": 0.01
}
```

**Output Format**:
```json
{
  "wallet": "9wZq5...",
  "analysis_type": "full_trace",
  "graph": {
    "nodes": [
      {"wallet": "9wZq5...", "type": "target", "balance": 1.5},
      {"wallet": "5Jy9...", "type": "connected", "balance": 0.8}
    ],
    "edges": [
      {
        "from": "5Jy9...",
        "to": "9wZq5...",
        "amount": 0.5,
        "timestamp": "2026-01-25T14:30:00Z"
      }
    ]
  },
  "clusters": [
    {
      "cluster_id": 1,
      "wallets": ["9wZq5...", "5Jy9...", "3Kx7..."],
      "total_balance": 3.2,
      "sybil_score": 0.85
    }
  ],
  "funding_sources": [
    {"wallet": "7xKXt...", "type": "exchange", "amount": 10.0}
  ]
}
```

---

### 4. Master Orchestrator

**Profile**: `orchestrator`  
**System Prompt**: `agentzero/prompts/orchestrator/system_prompt.md`

**Capabilities**:
- Multi-agent task coordination
- Subordinate agent spawning and management
- Result aggregation and synthesis
- High-level decision making

**Subordinate Agents**:
- `transaction_analyst`: Transaction pattern analysis
- `graph_analyst`: Wallet relationship mapping
- `risk_assessor`: Risk score calculation
- `researcher`: Threat intelligence gathering
- `developer`: Code execution and system maintenance

**Workflow Pattern** (Comprehensive Wallet Analysis):

```
1. Orchestrator receives request: "Analyze wallet 9wZq5..."
2. Spawns transaction_analyst:
   → "Analyze all transactions for wallet 9wZq5..."
3. Spawns graph_analyst:
   → "Map wallet relationships for 9wZq5... (3-hop)"
4. Spawns risk_assessor:
   → "Calculate risk score for 9wZq5... using transaction and graph data"
5. Aggregates results:
   → Combines transaction patterns, graph analysis, risk score
6. Synthesizes final report:
   → Executive summary with recommendations
```

**Example Task**:
```
Conduct a comprehensive investigation of wallet 9wZq5... suspected of insider trading on token 7xKXt.... Include transaction analysis, wallet relationship mapping, and risk assessment. Provide actionable recommendations.
```

---

### 5. Research Agent

**Profile**: `researcher`  
**System Prompt**: `agentzero/prompts/researcher/system_prompt.md`

**Capabilities**:
- Threat intelligence research
- OSINT (Open Source Intelligence)
- Dark web monitoring
- Blockchain intelligence
- Threat actor profiling

**Research Domains**:

1. **Pump.fun Ecosystem Analysis**
   - Token launch patterns
   - Creator behavior analysis
   - Market manipulation techniques

2. **Sybil Network Intelligence**
   - Multi-wallet coordination patterns
   - Funding source identification
   - Attack vector analysis

3. **Technical Vulnerability Research**
   - Smart contract exploits
   - RPC endpoint vulnerabilities
   - MEV (Maximal Extractable Value) strategies

4. **Regulatory & Legal Intelligence**
   - Compliance requirements
   - Legal precedents
   - Regulatory updates

**Research Workflow** (3 Phases):

```
Phase 1: Intelligence Collection (30%)
- Web scraping, API queries, database searches
- Dark web monitoring, social media analysis
- Blockchain data extraction

Phase 2: Analysis & Correlation (40%)
- Pattern recognition, anomaly detection
- Cross-reference with known threat actors
- Temporal and spatial correlation

Phase 3: Synthesis & Reporting (30%)
- Executive summary generation
- Actionable intelligence extraction
- Recommendation formulation
```

**Output Format**:
```markdown
# Threat Intelligence Report

## Executive Summary
[High-level findings and recommendations]

## Key Findings
1. [Finding 1 with evidence]
2. [Finding 2 with evidence]

## Threat Actor Profile
- **Identity**: [Known aliases, wallets]
- **Tactics**: [Attack patterns, techniques]
- **Indicators**: [Behavioral signatures]

## Recommendations
1. [Immediate actions]
2. [Long-term strategies]

## References
[Sources, links, timestamps]
```

---

### 6. Developer Agent

**Profile**: `developer`  
**System Prompt**: `agentzero/prompts/developer/system_prompt.md`

**Capabilities**:
- Software development and maintenance
- Code debugging and optimization
- System monitoring and diagnostics
- DevOps and deployment

**Technical Stack**:
- **Languages**: Python 3.11+, JavaScript/Node.js, Bash
- **Frameworks**: FastAPI, LangGraph, asyncio
- **Databases**: Redis 8.0.5, TimescaleDB, PostgreSQL
- **Infrastructure**: Docker, Docker Compose, Kubernetes
- **Monitoring**: Prometheus, Grafana, Jaeger, OpenTelemetry

**Responsibilities**:

1. **Codebase Maintenance** (28,080+ lines)
   - Bug fixes and patches
   - Performance optimization
   - Code refactoring

2. **Agent Development**
   - New agent implementation
   - Agent enhancement and upgrades
   - Integration testing

3. **System Monitoring**
   - Health checks and diagnostics
   - Performance profiling
   - Error tracking and resolution

4. **DevOps**
   - Docker container management
   - CI/CD pipeline maintenance
   - Infrastructure scaling

**Subordinate Delegation**:
- Can spawn `researcher` for technical documentation
- Can spawn `orchestrator` for multi-agent coordination
- Cannot spawn other `developer` agents (avoid recursion)

**Example Task**:
```
The wallet_analyzer_worker.py is experiencing high memory usage (>2GB). Profile the code, identify memory leaks, and implement optimizations to reduce memory footprint to <500MB.
```

---

## Configuration Reference

### Environment Variables

**File**: `.env`

```bash
# Solana RPC Endpoints (comma-separated)
RPC_ENDPOINTS=https://api.mainnet-beta.solana.com,https://solana-api.projectserum.com,https://rpc.ankr.com/solana,https://solana.public-rpc.com

# WebSocket Endpoints (comma-separated)
WS_ENDPOINTS=wss://api.mainnet-beta.solana.com

# Redis Configuration
REDIS_URL=redis://127.0.0.1:16379
REDIS_PASSWORD=

# TimescaleDB Configuration
TIMESCALE_URL=postgresql://godmodescanner:password@172.17.0.1:5432/godmodescanner
TIMESCALE_USER=godmodescanner
TIMESCALE_PASSWORD=password
TIMESCALE_DB=godmodescanner

# Qdrant Vector Database
QDRANT_URL=http://localhost:6333

# Pump.fun Protocol
PUMPFUN_PROGRAM_ID=6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P

# Logging
LOG_LEVEL=INFO

# Performance Tuning
BATCH_SIZE=100
MAX_WORKERS=4

# Alert Channels (Optional)
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
WEBHOOK_URL=
```

### Required Variables

| Variable | Type | Required | Default | Description |
|----------|------|----------|---------|-------------|
| `RPC_ENDPOINTS` | string | Yes | - | Comma-separated Solana RPC URLs |
| `WS_ENDPOINTS` | string | Yes | - | Comma-separated WebSocket URLs |
| `REDIS_URL` | string | Yes | - | Redis connection URL |
| `TIMESCALE_URL` | string | Yes | - | TimescaleDB connection URL |
| `PUMPFUN_PROGRAM_ID` | string | Yes | `6EF8...` | Pump.fun program address |
| `LOG_LEVEL` | string | No | `INFO` | Logging level (DEBUG, INFO, WARNING, ERROR) |
| `BATCH_SIZE` | integer | No | `100` | Message batch size for workers |
| `MAX_WORKERS` | integer | No | `4` | Maximum parallel workers per agent type |

### Optional Variables (Alert Channels)

| Variable | Type | Description |
|----------|------|-------------|
| `TELEGRAM_BOT_TOKEN` | string | Telegram bot API token |
| `TELEGRAM_CHAT_ID` | string | Telegram chat ID for alerts |
| `WEBHOOK_URL` | string | HTTP webhook URL for alerts |
| `DISCORD_WEBHOOK_URL` | string | Discord webhook URL |
| `EMAIL_SMTP_HOST` | string | SMTP server for email alerts |
| `EMAIL_SMTP_PORT` | integer | SMTP port (default: 587) |
| `EMAIL_FROM` | string | Sender email address |
| `EMAIL_TO` | string | Recipient email address |

---

### Redis Cluster Configuration

**File**: `config/redis_cluster_config.json`

```json
{
  "cluster_name": "godmode_cluster",
  "nodes": [
    {"host": "127.0.0.1", "port": 16379, "role": "master"},
    {"host": "127.0.0.1", "port": 16380, "role": "master"},
    {"host": "127.0.0.1", "port": 16381, "role": "master"},
    {"host": "127.0.0.1", "port": 16382, "role": "replica"},
    {"host": "127.0.0.1", "port": 16383, "role": "replica"},
    {"host": "127.0.0.1", "port": 16384, "role": "replica"}
  ],
  "streams": {
    "godmode:new_transactions": {
      "consumer_groups": [
        {"name": "wallet-analyzer-group", "workers": 10, "pending_threshold": 1000},
        {"name": "pattern-recognition-group", "workers": 10, "pending_threshold": 1000},
        {"name": "sybil-detection-group", "workers": 10, "pending_threshold": 500}
      ]
    },
    "godmode:new_tokens": {
      "consumer_groups": [
        {"name": "token-tracker-group", "workers": 5, "pending_threshold": 200},
        {"name": "early-detection-group", "workers": 5, "pending_threshold": 200}
      ]
    },
    "godmode:risk_scores": {
      "consumer_groups": [
        {"name": "risk-aggregator-group", "workers": 3, "pending_threshold": 500}
      ]
    },
    "godmode:alerts": {
      "consumer_groups": [
        {"name": "alert-dispatcher-group", "workers": 2, "pending_threshold": 100}
      ]
    }
  },
  "performance": {
    "connection_pool_size": 500,
    "socket_timeout": 5,
    "socket_connect_timeout": 5,
    "max_connections_per_node": 100
  }
}
```

---

### Agent Configuration

**File**: `config/agents.json`

```json
{
  "transaction_monitor": {
    "enabled": true,
    "instances": 1,
    "config": {
      "ws_endpoints": ["wss://api.mainnet-beta.solana.com"],
      "reconnect_delay": 5,
      "max_reconnect_attempts": 10,
      "heartbeat_interval": 60,
      "enrichment_enabled": true,
      "enrichment_batch_size": 10
    }
  },
  "wallet_analyzer": {
    "enabled": true,
    "instances": 10,
    "config": {
      "consumer_group": "wallet-analyzer-group",
      "batch_size": 100,
      "processing_timeout": 30,
      "behavior_tracking_window": 604800,
      "burst_detection_threshold": 5.0
    }
  },
  "pattern_recognition": {
    "enabled": true,
    "instances": 10,
    "config": {
      "consumer_group": "pattern-recognition-group",
      "batch_size": 100,
      "patterns": [
        "dev_insider",
        "telegram_alpha",
        "sniper_bot",
        "wash_trader",
        "delayed_insider",
        "sybil_army"
      ],
      "confidence_threshold": 0.7
    }
  },
  "risk_scoring": {
    "enabled": true,
    "instances": 3,
    "config": {
      "weights": {
        "behavior": 0.35,
        "timing": 0.25,
        "network": 0.25,
        "volume": 0.15
      },
      "alert_thresholds": {
        "critical": 85,
        "high": 70,
        "medium": 50
      }
    }
  }
}
```

---

## Data Models

### Transaction Model

```python
from dataclasses import dataclass
from typing import List, Optional
from datetime import datetime

@dataclass
class Transaction:
    signature: str
    slot: int
    block_time: int
    fee: int
    accounts: List[str]
    instructions: List[dict]
    log_messages: List[str]
    pre_balances: List[int]
    post_balances: List[int]
    error: Optional[str] = None

    @property
    def timestamp(self) -> datetime:
        return datetime.fromtimestamp(self.block_time)
```

### Token Launch Model

```python
@dataclass
class TokenLaunch:
    token_address: str
    creator: str
    name: str
    symbol: str
    uri: str
    initial_supply: int
    bonding_curve_address: str
    launch_time: datetime
    signature: str

    @property
    def age_seconds(self) -> float:
        return (datetime.now() - self.launch_time).total_seconds()
```

### Risk Score Model

```python
@dataclass
class RiskScore:
    wallet: str
    token: str
    risk_score: float
    confidence_interval: tuple[float, float]
    confidence_level: float
    components: dict[str, float]
    contributing_factors: List[str]
    severity: str  # CRITICAL, HIGH, MEDIUM, LOW
    timestamp: datetime

    @property
    def is_critical(self) -> bool:
        return self.risk_score >= 85
```

### Alert Model

```python
@dataclass
class Alert:
    alert_id: str
    severity: str
    risk_score: float
    confidence: float
    wallet: str
    token: str
    patterns_detected: List[str]
    evidence: dict
    recommended_action: str
    related_wallets: List[str]
    transaction_signatures: List[str]
    timestamp: datetime

    def to_telegram_message(self) -> str:
        return f"""
🚨 **{self.severity} ALERT**

Wallet: `{self.wallet}`
Token: `{self.token}`
Risk Score: {self.risk_score:.1f}
Confidence: {self.confidence:.1%}

Patterns: {', '.join(self.patterns_detected)}

Action: {self.recommended_action}
        """
```

---

## Error Handling

### Error Codes

| Code | Category | Description |
|------|----------|-------------|
| `E001` | Connection | Redis connection failed |
| `E002` | Connection | TimescaleDB connection failed |
| `E003` | Connection | Solana RPC connection failed |
| `E004` | Processing | Transaction parsing error |
| `E005` | Processing | Pattern detection error |
| `E006` | Processing | Risk scoring error |
| `E007` | Data | Invalid message format |
| `E008` | Data | Missing required field |
| `E009` | System | Agent initialization failed |
| `E010` | System | Supervisor coordination error |

### Error Response Format

```json
{
  "error": {
    "code": "E004",
    "category": "Processing",
    "message": "Failed to parse transaction: Invalid instruction data",
    "details": {
      "signature": "5J7...",
      "instruction_index": 2,
      "raw_data": "base58_encoded_data"
    },
    "timestamp": "2026-01-25T14:39:20.123456Z",
    "agent_id": "transaction_monitor_001"
  }
}
```

### Retry Strategy

```python
import asyncio
from typing import Callable, Any

async def retry_with_backoff(
    func: Callable,
    max_attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    exponential_base: float = 2.0
) -> Any:
    """Retry function with exponential backoff."""
    for attempt in range(max_attempts):
        try:
            return await func()
        except Exception as e:
            if attempt == max_attempts - 1:
                raise

            delay = min(
                base_delay * (exponential_base ** attempt),
                max_delay
            )
            await asyncio.sleep(delay)
```

---

## Performance Metrics

### Target Performance

| Metric | Target | Current | Status |
|--------|--------|---------|--------|
| Transaction Detection Latency | <500ms | ~125ms | ✅ Exceeds |
| Risk Scoring Latency | <100ms | ~12.5ms | ✅ Exceeds |
| Alert Pipeline Latency | <800μs | ~15.65μs | ✅ Exceeds (50x) |
| Throughput (Transactions) | 1000+ TPS | 1000+ TPS | ✅ Meets |
| Redis Cluster Ops/sec | 2000+ | 2457 | ✅ Exceeds |
| System Uptime | 99.9% | 99.95% | ✅ Exceeds |
| Memory Usage (per agent) | <500MB | ~350MB | ✅ Meets |

### Monitoring Endpoints

```bash
# Prometheus metrics
curl http://localhost:9090/metrics

# Grafana dashboard
http://localhost:3000/d/godmodescanner

# Jaeger tracing
http://localhost:16686

# Health check
curl http://localhost:8000/health
```

---

## Appendix

### A. Redis Streams vs Pub/Sub

| Feature | Streams | Pub/Sub |
|---------|---------|----------|
| Persistence | ✅ Yes | ❌ No |
| Message Acknowledgment | ✅ Yes | ❌ No |
| Consumer Groups | ✅ Yes | ❌ No |
| Message Replay | ✅ Yes | ❌ No |
| Backpressure Handling | ✅ Yes | ⚠️ Limited |
| Use Case | Durable queuing | Real-time events |

### B. Agent Zero Subordinate Spawning

```python
from agentzero.agent_zero_core import Agent, AgentConfig

# Master Orchestrator spawns subordinates
orchestrator = Agent(AgentConfig(profile="orchestrator"))

# Spawn transaction analyst
tx_analyst = await orchestrator.call_subordinate(
    profile="transaction_analyst",
    message="Analyze wallet 9wZq5... for insider patterns",
    reset=True
)

# Spawn graph analyst
graph_analyst = await orchestrator.call_subordinate(
    profile="graph_analyst",
    message="Map wallet relationships for 9wZq5... (3-hop)",
    reset=True
)

# Aggregate results
results = await orchestrator.aggregate_subordinate_results([
    tx_analyst,
    graph_analyst
])
```

### C. Production Deployment Checklist

- [ ] Configure authenticated RPC endpoints (Helius, Triton, QuickNode)
- [ ] Set up TimescaleDB with proper credentials
- [ ] Configure Redis Cluster with 6 nodes (3 masters, 3 replicas)
- [ ] Enable distributed tracing (Jaeger)
- [ ] Set up monitoring (Prometheus + Grafana)
- [ ] Configure alert channels (Telegram, Webhook, Email)
- [ ] Run integration tests (7 tests must pass)
- [ ] Verify zero-latency alert pipeline (<800μs)
- [ ] Load test with 1000+ TPS
- [ ] Configure backup and disaster recovery

---

**Document Version**: 1.0.0  
**Last Updated**: 2026-01-25  
**Maintained By**: GODMODESCANNER Development Team  
**License**: MIT
