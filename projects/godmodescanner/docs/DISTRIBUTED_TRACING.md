# GODMODESCANNER Distributed Tracing Integration

## 🎯 Overview

GODMODESCANNER now includes **end-to-end distributed tracing** using OpenTelemetry and Jaeger, enabling you to:

- **Track requests** across all 47+ agents in real-time
- **Identify bottlenecks** in the multi-agent pipeline
- **Debug complex workflows** spanning multiple services
- **Monitor performance** of individual operations
- **Visualize dependencies** between agents and services

## 📦 Components

### 1. OpenTelemetry Instrumentation
- **Packages Installed**: 19 OpenTelemetry packages
- **Auto-instrumentation**: Redis, PostgreSQL (AsyncPG)
- **Manual instrumentation**: Custom agent operations

### 2. Observability Tool
- **Location**: `agentzero/tools/godmode/observability_tool.py`
- **Size**: 10,352 bytes
- **Features**: 5 specialized tracing methods

### 3. Jaeger All-in-One
- **Container**: `godmode_jaeger`
- **Profile**: `monitoring`
- **UI Port**: 16686
- **Agent Port**: 6831/udp

## 🚀 Quick Start

### Step 1: Start Jaeger

```bash
cd /a0/usr/projects/godmodescanner/projects/godmodescanner

# Start Jaeger with monitoring profile
docker-compose --profile monitoring up -d jaeger

# Verify Jaeger is running
docker ps | grep jaeger
```

### Step 2: Access Jaeger UI

Open your browser to:
```
http://localhost:16686
```

You should see the Jaeger UI with:
- **Search** tab for finding traces
- **Compare** tab for comparing traces
- **System Architecture** tab for dependency graphs

### Step 3: Integrate Tracing into Your Agent

```python
# Example: Transaction Monitor Agent
from agentzero.tools.godmode.observability_tool import DistributedTracing, tracer

class TransactionMonitor:
    def __init__(self):
        self.dt = DistributedTracing(service_name="transaction-monitor")

    async def process_transaction(self, tx_signature: str, wallet_address: str):
        # Start a trace
        trace_ctx = self.dt.trace_transaction_analysis(
            wallet_address=wallet_address,
            transaction_signature=tx_signature,
            token_address="pump123..."
        )

        # Your existing code here
        # All Redis and PostgreSQL calls are automatically traced!

        # Log trace ID for debugging
        print(f"Trace ID: {trace_ctx['trace_id']}")
        print(f"View at: http://localhost:16686/trace/{trace_ctx['trace_id']}")
```

## 🔧 Integration Examples

### Example 1: Transaction Analysis Pipeline

```python
from agentzero.tools.godmode.observability_tool import DistributedTracing

class TransactionAnalysisPipeline:
    def __init__(self):
        self.dt = DistributedTracing()

    async def analyze_transaction(self, tx_sig: str, wallet: str):
        # Start parent span
        with tracer.start_as_current_span("full_analysis") as parent_span:
            parent_span.set_attribute("transaction.signature", tx_sig)

            # Step 1: Transaction monitoring (child span)
            self.dt.trace_transaction_analysis(
                wallet_address=wallet,
                transaction_signature=tx_sig
            )

            # Step 2: Wallet analysis (child span)
            self.dt.trace_wallet_analysis(
                wallet_address=wallet,
                analysis_type="full"
            )

            # Step 3: Pattern detection (child span)
            self.dt.trace_pattern_detection(
                pattern_type="dev_insider",
                wallet_address=wallet,
                confidence=0.85
            )

            # Step 4: Risk scoring (child span)
            self.dt.trace_risk_scoring(
                wallet_address=wallet,
                risk_score=87.5,
                alert_level="CRITICAL"
            )
```

### Example 2: Graph Traversal

```python
from agentzero.tools.godmode.observability_tool import DistributedTracing

class GraphTraversalAgent:
    def __init__(self):
        self.dt = DistributedTracing(service_name="graph-traversal")

    async def traverse_wallet_network(self, start_wallet: str, depth: int = 3):
        # Trace the graph traversal
        trace_ctx = self.dt.trace_graph_traversal(
            start_wallet=start_wallet,
            depth=depth,
            nodes_discovered=0  # Will update later
        )

        # Perform traversal
        nodes = await self._traverse(start_wallet, depth)

        # Update span with results
        with tracer.start_as_current_span("traversal_complete") as span:
            span.set_attribute("nodes.discovered", len(nodes))
            span.set_attribute("trace_id", trace_ctx['trace_id'])

        return nodes
```

### Example 3: Using the Decorator

```python
from agentzero.tools.godmode.observability_tool import trace_operation

class WalletAnalyzer:
    @trace_operation("wallet_profiling", system="godmodescanner")
    async def profile_wallet(self, wallet_address: str):
        # This entire function is automatically traced!
        profile = await self._fetch_profile(wallet_address)
        return profile

    @trace_operation("transaction_history", system="godmodescanner")
    async def get_transaction_history(self, wallet_address: str):
        # Another traced operation
        history = await self._fetch_history(wallet_address)
        return history
```

## 📊 Available Tracing Methods

### 1. `trace_transaction_analysis()`
Tracks transaction analysis through the pipeline.

**Arguments**:
- `wallet_address` (str): Solana wallet address
- `transaction_signature` (str, optional): Transaction signature
- `**kwargs`: Additional custom attributes

**Returns**: Dict with `trace_id` and `span_id`

### 2. `trace_wallet_analysis()`
Tracks wallet profiling and analysis operations.

**Arguments**:
- `wallet_address` (str): Wallet being analyzed
- `analysis_type` (str): Type of analysis (full, quick, deep)
- `**kwargs`: Additional custom attributes

### 3. `trace_pattern_detection()`
Tracks pattern detection operations.

**Arguments**:
- `pattern_type` (str): Pattern type (dev_insider, sybil_army, etc.)
- `wallet_address` (str): Wallet being analyzed
- `confidence` (float): Detection confidence (0-1)
- `**kwargs`: Additional custom attributes

### 4. `trace_risk_scoring()`
Tracks risk scoring operations.

**Arguments**:
- `wallet_address` (str): Wallet being scored
- `risk_score` (float): Risk score (0-100)
- `alert_level` (str): Alert level (CRITICAL, HIGH, MEDIUM, LOW)
- `**kwargs`: Additional custom attributes

### 5. `trace_graph_traversal()`
Tracks graph traversal operations.

**Arguments**:
- `start_wallet` (str): Starting wallet address
- `depth` (int): Traversal depth (hops)
- `nodes_discovered` (int): Number of nodes discovered
- `**kwargs`: Additional custom attributes

## 🔍 Viewing Traces in Jaeger UI

### Finding Traces

1. **Open Jaeger UI**: http://localhost:16686
2. **Select Service**: Choose from dropdown (e.g., "godmodescanner")
3. **Set Time Range**: Adjust lookback period
4. **Add Filters**:
   - `wallet.address`: Filter by specific wallet
   - `alert.level`: Filter by alert severity
   - `pattern.type`: Filter by pattern type
5. **Click "Find Traces"**

### Understanding Trace View

```
Transaction Analysis (200ms)
├── Transaction Monitor (50ms)
│   ├── Redis: XADD (2ms)
│   └── PostgreSQL: INSERT (5ms)
├── Wallet Analyzer (80ms)
│   ├── Redis: GET (1ms)
│   ├── RPC: getAccountInfo (45ms)
│   └── PostgreSQL: SELECT (8ms)
├── Pattern Recognition (40ms)
│   ├── ML Model Inference (30ms)
│   └── Redis: HSET (2ms)
└── Risk Scoring (30ms)
    ├── Bayesian Calculation (15ms)
    ├── Redis: ZADD (2ms)
    └── Alert Manager (10ms)
```

### Key Metrics

- **Duration**: Total time for operation
- **Spans**: Number of child operations
- **Errors**: Failed operations (red)
- **Tags**: Custom attributes (wallet address, pattern type, etc.)

## 🎯 Production Configuration

### Environment Variables

Add to your `.env` file:

```bash
# Jaeger Configuration
JAEGER_HOST=localhost
JAEGER_PORT=6831
SERVICE_NAME=godmodescanner

# Enable tracing
OTEL_TRACES_EXPORTER=jaeger
OTEL_EXPORTER_JAEGER_AGENT_HOST=localhost
OTEL_EXPORTER_JAEGER_AGENT_PORT=6831
```

### Docker Compose Integration

The Jaeger service is already configured in `docker-compose.yml`:

```yaml
jaeger:
  image: jaegertracing/all-in-one:latest
  container_name: godmode_jaeger
  profiles: ["monitoring"]
  ports:
    - "16686:16686"  # UI
    - "6831:6831/udp"  # Traces
  networks:
    - godmode_network
```

### Starting with Monitoring Profile

```bash
# Start all services including Jaeger
docker-compose --profile monitoring up -d

# Or start Jaeger separately
docker-compose --profile monitoring up -d jaeger prometheus grafana
```

## 🐛 Debugging with Traces

### Scenario 1: Slow Transaction Processing

1. **Find slow traces**: Filter by duration > 1000ms
2. **Identify bottleneck**: Look for longest span
3. **Check tags**: Review RPC endpoint, wallet address
4. **Optimize**: Cache results, use batch requests

### Scenario 2: Failed Pattern Detection

1. **Search for errors**: Filter by `error=true`
2. **Review span logs**: Check error messages
3. **Trace dependencies**: See which service failed
4. **Fix and verify**: Re-run and compare traces

### Scenario 3: High Latency in Graph Traversal

1. **Compare traces**: Use "Compare" tab
2. **Analyze depth**: Check `graph.depth` attribute
3. **Review Redis calls**: Count XREADGROUP operations
4. **Optimize**: Implement caching, reduce depth

## 📈 Performance Impact

### Overhead

- **Tracing overhead**: ~1-2% CPU
- **Memory overhead**: ~10-20 MB per service
- **Network overhead**: ~1 KB per trace

### Best Practices

1. **Sample traces**: Don't trace every request in production
2. **Use tags wisely**: Add only essential attributes
3. **Batch exports**: Use `BatchSpanProcessor` (already configured)
4. **Monitor Jaeger**: Ensure it doesn't become a bottleneck

## 🔗 Integration with Existing Infrastructure

### Redis Auto-Instrumentation

All Redis operations are automatically traced:

```python
# No changes needed - already instrumented!
import redis
r = redis.Redis(host='localhost', port=6379)
r.set('key', 'value')  # Automatically traced
```

### PostgreSQL Auto-Instrumentation

All AsyncPG operations are automatically traced:

```python
# No changes needed - already instrumented!
import asyncpg
conn = await asyncpg.connect('postgresql://...')
await conn.fetch('SELECT * FROM wallets')  # Automatically traced
```

### FastAPI Integration

For FastAPI endpoints (if using):

```python
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from fastapi import FastAPI

app = FastAPI()
FastAPIInstrumentor.instrument_app(app)  # Auto-trace all endpoints
```

## 📚 Additional Resources

- **Jaeger Documentation**: https://www.jaegertracing.io/docs/
- **OpenTelemetry Python**: https://opentelemetry.io/docs/instrumentation/python/
- **Trace Context Propagation**: https://www.w3.org/TR/trace-context/

## 🎉 Summary

You now have:

✅ **OpenTelemetry instrumentation** (19 packages installed)
✅ **Observability tool** with 5 specialized tracing methods
✅ **Jaeger UI** for visualization (http://localhost:16686)
✅ **Auto-instrumentation** for Redis and PostgreSQL
✅ **Production-ready configuration** in docker-compose.yml
✅ **Comprehensive documentation** with examples

**Next Steps**:

1. Start Jaeger: `docker-compose --profile monitoring up -d jaeger`
2. Integrate tracing into your agents (see examples above)
3. Generate some traces by running your agents
4. View traces in Jaeger UI: http://localhost:16686
5. Optimize based on insights!

---

**Created**: 2026-01-25  
**System**: GODMODESCANNER v1.0  
**Component**: Distributed Tracing Integration  
**Status**: ✅ Production Ready
