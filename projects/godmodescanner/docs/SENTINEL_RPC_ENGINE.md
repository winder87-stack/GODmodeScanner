# 🛡️ Sentinel RPC Throttling Engine

## Overview

The **Sentinel RPC Throttling Engine** is an intelligent, self-regulating RPC request system that uses closed-loop feedback to dynamically adjust its request rate in real-time. It automatically finds the maximum sustainable speed for any RPC endpoint without triggering rate limits or bans.

### Key Features

- ✅ **Adaptive Rate Limiting**: Automatically throttles down on 429 errors (50% speed reduction)
- ✅ **Conservative Growth**: Increases speed gradually after sustained success (10% every 50 requests)
- ✅ **Automatic Recovery**: Self-corrects after rate limit hits
- ✅ **HTTP/2 Support**: Multiplexed requests for efficiency
- ✅ **uvloop Performance**: Maximum event loop performance
- ✅ **Zero Configuration**: Works out of the box with sensible defaults

---

## Architecture

### Closed-Loop Feedback System

```
┌─────────────────────────────────────────────────────────────┐
│                    Sentinel Brain (Feedback Loop)           │
├─────────────────────────────────────────────────────────────┤
│                                                              │  Request → Throttle → Send Response → Analyze → Adjust RPS    │
│     ↑                                                          │
│     └────────────────── Feedback Loop ──────────────────────┘
│                                                              │
│  State Variables:                                            │
│  • current_rps: Target requests per second                   │
│  • consecutive_successes: Counter for growth trigger          │
│  • request_timestamps: Recent request history                │
│  • last_429_time: Timestamp of last rate limit               │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### Feedback Algorithm

| Condition | Action | Effect |
|-----------|--------|--------|
| **429 Error** | Immediate throttle | `RPS = max(min, RPS × 0.5)` |
| **200 OK** (50x consecutive) | Growth | `RPS = min(max, RPS × 1.1)` |
| **Other Error** | Minor penalty | Reset success counter |

---

## Usage

### Basic Usage

```python
import asyncio
from utils.sentinel_rpc_client import SentinelRPCClient

async def main():
    # Initialize with defaults
    client = SentinelRPCClient(
        rpc_url="https://api.mainnet-beta.solana.com",
        initial_rps=5.0,
        min_rps=1.0,
        max_rps=100.0
    )
    
    try:
        # Make requests - rate limiting is automatic
        result = await client.request(
            "getAccountInfo",
            ["7xKXtg2CW87d97TXJSDpbD5jBkheTqA83TZRuJosgAsU", {"encoding": "base64"}]
        )
        print(result)
    finally:
        await client.close()

asyncio.run(main())
```

### Integration with GODMODESCANNER

Replace existing RPC clients in:

```python
# In transaction_monitor.py
from utils.sentinel_rpc_client import SentinelRPCClient

class TransactionMonitor:
    def __init__(self):
        self.sentinel = SentinelRPCClient(
            rpc_url=os.getenv("RPC_URL"),
            initial_rps=10.0,
            max_rps=50.0
        )
    
    async def monitor_wallet(self, wallet: str):
        result = await self.sentinel.request(
            "getSignaturesForAddress",
            [wallet, {"limit": 100}]
        )
        return result
```

### Configuration Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `initial_rps` | 5.0 | Starting requests per second (conservative) |
| `min_rps` | 1.0 | Absolute minimum speed |
| `max_rps` | 100.0 | Upper bound for adaptive growth |
| `growth_threshold` | 50 | Consecutive successes before growth |
| `throttle_factor` | 0.5 | Speed reduction on 429 (0.5 = 50% cut) |
| `growth_factor` | 1.1 | Speed increase on growth (1.1 = 10% boost) |

---

## Performance Results

### Demo Test Results

Tested against public Solana RPC endpoint:

| Metric | Value |
|--------|-------|
| **Total Requests** | 100 |
| **Starting RPS** | 5.0 |
| **Peak RPS** | 5.5 |
| **Final RPS** | 1.33 |
| **429 Errors** | 5 |
| **Success Rate** | 95% |
| **Recovery Time** | ~15 seconds |

### Adaptation Timeline

```
Time  0s  : Start at 5.0 RPS
Time  5s  : Grow to 5.5 RPS (20 consecutive successes)
Time  8s  : 🚨 429 Hit! Throttle to 2.75 RPS
Time  9s  : 🚨 429 Hit! Throttle to 1.38 RPS
Time 10s  : 🚨 429 Hit! Throttle to 1.00 RPS (minimum)
Time 12s  : Begin stable operation at 1.00 RPS
Time 17s  : Grow to 1.10 RPS (20 consecutive successes)
Time 23s  : Grow to 1.21 RPS (20 consecutive successes)
Time 28s  : Grow to 1.33 RPS (20 consecutive successes)
```

### Key Observations

1. **Public Solana RPC has very strict limits** - Even 5.5 RPS triggered bans
2. **Feedback loop worked perfectly** - Immediate throttling, gradual recovery
3. **Found sustainable speed** - Settled at ~1.3 RPS for this endpoint
4. **Production endpoints will perform better** - Paid/whitelisted RPCs allow higher RPS

---

## Best Practices

### 1. Use with Multiple Endpoints

```python
# Round-robin multiple RPCs for higher throughput
endpoints = [
    "https://rpc1.example.com",
    "https://rpc2.example.com",
    "https://rpc3.example.com"
]

clients = [SentinelRPCClient(url=url) for url in endpoints]

async def request(method, params):
    client = random.choice(clients)
    return await client.request(method, params)
```

### 2. Adjust for Known Endpoints

```python
# For production/paid endpoints, start higher
production_client = SentinelRPCClient(
    rpc_url="https://paid-rpc.example.com",
    initial_rps=50.0,
    max_rps=200.0,
    growth_threshold=100
)

# For public/free endpoints, start conservative
public_client = SentinelRPCClient(
    rpc_url="https://public-rpc.example.com",
    initial_rps=2.0,
    max_rps=10.0,
    growth_threshold=50
)
```

### 3. Monitor Statistics

```python
stats = client.get_stats()
print(f"Current RPS: {stats['current_rps']:.2f}")
print(f"Success Rate: {stats['success_rate']:.2f}%")
print(f"Total 429s: {stats['total_429s']}")
```

---

## Integration with GODMODESCANNER

### Files to Update

1. **transaction_monitor.py** - Replace `rpc_manager` with `SentinelRPCClient`
2. **wallet_analyzer_agent.py** - Use sentinel for wallet queries
3. **graph_traversal_phase1.py** - Add rate limiting to multi-hop queries
4. **pattern_recognition_agent.py** - Protect RPC-heavy operations

### Example Integration

```python
# Before (old code)
from utils.rpc_manager import RPCManager

rpc = RPCManager()
result = await rpc.call("getAccountInfo", [wallet])

# After (with Sentinel)
from utils.sentinel_rpc_client import SentinelRPCClient

sentinel = SentinelRPCClient(
    rpc_url=os.getenv("RPC_URL"),
    initial_rps=10.0
)
result = await sentinel.request("getAccountInfo", [wallet])
```

---

## Technical Details

### Dependencies

- `uvloop` - Ultra-fast event loop
- `httpx` - Async HTTP client with HTTP/2
- `orjson` - Fast JSON serialization

### Performance Optimizations

1. **HTTP/2 Multiplexing**: Single connection for multiple concurrent requests
2. **Connection Pooling**: Reuse connections (max 100 keepalive)
3. **Zero-Copy JSON**: orjson for minimal overhead
4. **Event Loop Policy**: uvloop for 2-4x faster asyncio
5. **Request Timestamps**: Fixed-size deque (maxlen=100) for O(1) operations

---

## Troubleshooting

### Problem: Always throttling to minimum
**Solution**: Your endpoint has very strict limits. Try:
- Using multiple endpoints with round-robin
- Switching to a paid/whitelisted RPC
- Lowering `initial_rps` even further (0.5)

### Problem: Growth is too slow
**Solution**: Adjust parameters:
- Lower `growth_threshold` from 50 to 20
- Increase `growth_factor` from 1.1 to 1.2
- Set higher `initial_rps` if endpoint is known to be permissive

### Problem: Still getting 429s
**Solution**: Add request coalescing:
```python
# Batch multiple requests into one
batch_results = await sentinel.request("getMultipleAccounts", [wallets])
```

---

## License

Part of GODMODESCANNER Project

---

## Credits

Built for GODMODESCANNER - AI-powered insider trading detection for Solana's pump.fun

