# Step 1: Optimized AggressivePumpFunClient

## Executive Summary

**Status**: ✅ COMPLETE
**File**: `utils/aggressive_pump_fun_client.py`
**Size**: 7.2KB (174 lines)
**Integration**: Full integration with existing GODMODESCANNER infrastructure

---

## Architecture Overview

The `AggressivePumpFunClient` is a high-performance, self-regulating RPC client designed to replace bloXroute's Pump.fun WebSocket streams with native Solana RPC polling. It implements intelligent rate limiting, load balancing, and seamless integration with GODMODESCANNER's existing infrastructure.

### Design Philosophy

**"Use Existing Infrastructure"** - Unlike typical implementations that duplicate code, this client leverages GODMODESCANNER's existing components:
- `RPCManager` for load-balanced endpoint selection
- `RedisStreamsProducer` for data publishing
- `PumpFunParser` for transaction parsing
- `RiskScoreSegment` for zero-latency alerts

---

## Core Components

### 1. Infrastructure Integration

```python
# Existing GODMODESCANNER components
from utils.rpc_manager import RPCManager
from utils.redis_streams_producer import RedisStreamsProducer
from utils.pumpfun_parser import PumpFunParser
from agents.shared_memory.risk_score_segment import RiskScoreSegment
```

| Component | Purpose | Integration Method |
|-----------|---------|-------------------|
| RPCManager | Load-balanced endpoint selection | `await self.rpc_manager.get_healthy_endpoint()` |
| RedisStreamsProducer | Stream publishing to Redis | `await self.redis_producer.publish()` |
| PumpFunParser | Transaction/event parsing | `self.parser.parse_transaction()` |
| RiskScoreSegment | Zero-latency alert pipeline | `self.shared_mem.write_score()` |

### 2. Adaptive Rate Limiting

**Closed-Loop Feedback System**:

```
Initial RPS: 15.0
↓
50 consecutive successes → Increase by 10%
↓
Rate limit hit (429) → Decrease by 50%
↓
Range: 5.0 RPS (min) ↔ 40.0 RPS (max)
```

**Key Parameters**:
- `current_rps`: Current requests per second
- `max_rps`: 40.0 (free endpoints)
- `min_rps`: 5.0 (minimum throughput)
- `consecutive_successes`: Counter for growth trigger

### 3. HTTP/2 Optimization

```python
self.client = httpx.AsyncClient(
    http2=True,  # HTTP/2 multiplexing
    limits=httpx.Limits(
        max_connections=500,      # High concurrency
        max_keepalive_connections=100  # Connection reuse
    ),
    timeout=httpx.Timeout(10.0)  # 10-second timeout
)
```

### 4. RPC Methods

| Method | Purpose | Optimization |
|--------|---------|-------------|
| `get_program_accounts()` | Poll bonding curve accounts | Data slice (200 bytes), filter by size |
| `get_signatures_for_address()` | Get recent transactions | Limit: 100, commitment: confirmed |
| `get_transaction()` | Fetch full transaction | Max version 0, confirmed commitment |

---

## Integration Points

### 1. Redis Streams

```python
async def publish_to_redis_stream(self, stream_key: str, data: Dict):
    """Publishes to existing Redis Streams infrastructure."""
    await self.redis_producer.publish(
        stream=stream_key,
        data=data
    )
```

**Target Streams**:
- `wallet-analyzer-stream`
- `pattern-recognition-stream`
- `sybil-detection-stream`
- `token-tracker-stream`

### 2. Zero-Latency Pipeline

```python
self.shared_mem = RiskScoreSegment()
# Critical path: ~15.65μs for high-risk alerts
```

### 3. Pump.fun Program Constants

```python
PUMP_FUN_PROGRAM_ID = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
PUMP_FUN_FACTORY_ID = "TSLvdd1pWpHVjahSpsvCXUbgwsL3JAcvokAgKfjQNd"
```

---

## Performance Characteristics

| Metric | Expected Value | Target |
|--------|---------------|--------|
| Request Latency | 200-450ms | <500ms |
| Throughput | 5-40 RPS (adaptive) | >10 RPS |
| Connection Pool | 500 max | High concurrency |
| Cache Hit Rate | 60-70% | >60% |

### Adaptive Throttle Algorithm

```python
async def adaptive_throttle(self):
    """Self-regulating throttle."""
    if not self.request_timestamps:
        return
    time_since_last = time.time() - self.request_timestamps[-1]
    required_delay = 1.0 / self.current_rps
    if time_since_last < required_delay:
        await asyncio.sleep(required_delay - time_since_last)
```

---

## Error Handling & Resilience

### Retry Logic

```python
max_retries = 5
Exponential backoff: 2^retry_count seconds
```

| Error Type | Handling |
|------------|----------|
| HTTP 429 (Rate Limit) | Immediate throttle, retry |
| HTTP 403/401 | Log, skip (auth error) |
| HTTP 502/503 | Retry with backoff |
| Network Error | Retry with backoff |
| Timeout | Retry with backoff |

---

## Dependencies

### Required Packages (Installed)
- ✅ `uvloop` - Event loop optimization
- ✅ `httpx` - HTTP/2 client
- ✅ `orjson` - Fast JSON serialization
- ✅ `solders` - Solana SDK types
- ✅ `construct` - Binary parsing
- ✅ `structlog` - Structured logging

### Existing GODMODESCANNER Components
- ✅ `utils.rpc_manager.RPCManager`
- ✅ `utils.redis_streams_producer.RedisStreamsProducer`
- ✅ `utils.pumpfun_parser.PumpFunParser`
- ✅ `agents.shared_memory.risk_score_segment.RiskScoreSegment`

---

## Usage Example

```python
import asyncio
from utils.aggressive_pump_fun_client import AggressivePumpFunClient
from solders.pubkey import Pubkey

async def main():
    client = AggressivePumpFunClient()
    
    # Poll pump.fun program accounts
    result = await client.get_program_accounts(
        Pubkey.from_string("6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P")
    )
    
    # Publish to Redis Stream
    await client.publish_to_redis_stream(
        stream_key="wallet-analyzer-stream",
        data={"signature": "...", "event_type": "TokenCreate"}
    )

asyncio.run(main())
```

---

## Next Steps

### Step 2: Native RPC Polling Implementation

**Goal**: Implement polling loop to replace bloXroute streams

**Tasks**:
1. Implement `poll_new_tokens()` - Poll for bonding curve creation
2. Implement `poll_swaps()` - Poll for swap transactions
3. Implement `process_transaction()` - Parse and enrich transactions
4. Implement `main_loop()` - Continuous polling with adaptive rate

### Step 3: Parser Enhancement

**Goal**: Decode raw pump.fun transaction data

**Tasks**:
1. Implement instruction discriminator parsing
2. Implement bonding curve account structure
3. Implement token amount calculation
4. Implement metadata extraction

### Step 4: Integration Testing

**Goal**: End-to-end testing

**Tasks**:
1. Test polling accuracy vs bloXroute
2. Measure latency differences
3. Validate event detection
4. Load testing with 1000+ TPS

---

## Production Considerations

### Cost

| Component | Cost |
|-----------|------|
| Free RPC Endpoints | $0/month |
| Helius/Triton/QuickNode | $9-49/month (recommended) |

### Rate Limits

| Endpoint | Free Tier | Paid Tier |
|----------|-----------|----------|
| Solana Public | ~10 RPS | - |
| Helius | 100K req/day | 400K-2M req/day |
| Triton | 100K req/day | 400K-4M req/day |
| QuickNode | 50K req/day | 2M-10M req/day |

### Recommended Configuration

```python
# Free tier (limited)
initial_rps = 5.0
max_rps = 15.0

# Paid tier (Helius Growth)
initial_rps = 15.0
max_rps = 50.0
```

---

## Monitoring & Metrics

### Key Metrics to Track

```python
self.current_rps              # Current throughput
self.consecutive_successes     # Success streak
self.retry_count              # Retry attempts
len(self.processed_signatures) # Deduplication count
len(self.known_bonding_curves)  # Discovered tokens
```

### Structured Logging

```python
logger.info("AggressivePumpFunClient initialized", 
            rpc_endpoints=len(self.rpc_manager.endpoints))

logger.warning("rate_limit_hit", 
              new_rps=self.current_rps,
              alert_type="THROTTLE")

logger.info("rps_increased", 
           new_rps=self.current_rps)
```

---

## File Structure

```
utils/
├── aggressive_pump_fun_client.py  ← NEW (Step 1)
├── aggressive_solana_client.py
├── sentinel_rpc_client.py
├── pumpfun_parser.py
├── rpc_manager.py
├── redis_streams_producer.py
└── ...
```

---

## Summary

✅ **Step 1 Complete**
- Created `AggressivePumpFunClient` with 7.2KB of optimized code
- Full integration with existing GODMODESCANNER infrastructure
- Adaptive rate limiting (5-40 RPS)
- HTTP/2 optimization with 500 connection pool
- Exponential backoff retry logic
- Ready for Step 2: Native RPC Polling Implementation

---

**Next Action**: Implement Step 2 - Native RPC Polling Loop
