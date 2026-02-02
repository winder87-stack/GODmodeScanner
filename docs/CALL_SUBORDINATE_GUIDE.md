# Agent Zero call_subordinate Feature Guide

## 🎯 Overview

The `call_subordinate()` feature enables **hierarchical agent management** in GODMODESCANNER, allowing agents to spawn and delegate tasks to specialized subordinate agents.

### Key Capabilities
- ✅ **Profile-based spawning**: Create subordinates with specific expertise
- ✅ **Task delegation**: Offload specialized work to subordinates
- ✅ **Context isolation**: Each subordinate has its own memory/context
- ✅ **Hierarchical chains**: Subordinates can spawn their own subordinates
- ✅ **Session management**: Reset or continue existing subordinate sessions

---

## 📚 API Reference

### Method Signature

```python
async def call_subordinate(
    self,
    message: str,
    profile: str = "",
    reset: bool = True
) -> str:
    """
    Call a subordinate agent with a specific profile

    Args:
        message: Task instruction for subordinate
        profile: Agent profile (transaction_analyst, risk_assessor, graph_analyst, etc.)
        reset: Create new subordinate (True) or continue existing (False)

    Returns:
        str: Result from subordinate agent
    """
```

### Available Profiles

1. **`transaction_analyst`** - Blockchain transaction analysis
   - Detects 6 insider trading patterns
   - Monitors pump.fun transactions
   - Identifies suspicious behavior

2. **`risk_assessor`** - Bayesian risk scoring
   - Calculates risk scores (0-100)
   - Assigns alert levels (CRITICAL, HIGH, MEDIUM, LOW)
   - Provides confidence intervals

3. **`graph_analyst`** - Multi-hop wallet traversal
   - Performs 3-5 hop wallet de-anonymization
   - DBSCAN clustering
   - Sybil network mapping

4. **`orchestrator`** - Task coordination
   - Breaks down complex tasks
   - Coordinates multiple subordinates
   - Aggregates results

5. **`researcher`** - Threat intelligence
   - OSINT gathering
   - Dark web monitoring
   - Blockchain intelligence

6. **`developer`** - Code development
   - Maintains 28,080+ line codebase
   - Implements new features
   - Debugging and optimization

---

## 💡 Usage Examples

### Example 1: Basic Subordinate Call

```python
from agentzero.agent_zero_core import Agent, AgentConfig, AgentContext

class MasterAgent:
    def __init__(self):
        config = AgentConfig(
            profile="orchestrator",
            redis_host="localhost",
            redis_port=6379
        )
        context = AgentContext()
        self.agent = Agent(0, config, context)

    async def analyze_wallet(self, wallet_address: str):
        # Delegate to transaction analyst subordinate
        result = await self.agent.call_subordinate(
            message=f"Analyze wallet {wallet_address} for insider trading patterns",
            profile="transaction_analyst",
            reset=True  # Create new subordinate
        )

        print(f"Analysis result: {result}")
        return result
```

### Example 2: Multi-Step Analysis with Different Subordinates

```python
class ComprehensiveAnalyzer:
    def __init__(self):
        config = AgentConfig(profile="orchestrator")
        context = AgentContext()
        self.agent = Agent(0, config, context)

    async def full_wallet_investigation(self, wallet: str):
        # Step 1: Transaction analysis
        tx_analysis = await self.agent.call_subordinate(
            message=f"Analyze recent transactions for wallet {wallet}",
            profile="transaction_analyst",
            reset=True
        )

        # Step 2: Graph traversal
        graph_analysis = await self.agent.call_subordinate(
            message=f"Perform 3-hop graph traversal starting from {wallet}",
            profile="graph_analyst",
            reset=True
        )

        # Step 3: Risk scoring
        risk_score = await self.agent.call_subordinate(
            message=f"Calculate risk score for {wallet} based on: {tx_analysis}",
            profile="risk_assessor",
            reset=True
        )

        return {
            "wallet": wallet,
            "transaction_analysis": tx_analysis,
            "graph_analysis": graph_analysis,
            "risk_score": risk_score
        }
```

### Example 3: Continuing Existing Subordinate Session

```python
class InteractiveAnalyzer:
    def __init__(self):
        config = AgentConfig(profile="orchestrator")
        context = AgentContext()
        self.agent = Agent(0, config, context)

    async def iterative_analysis(self, wallet: str):
        # First call - create subordinate
        initial = await self.agent.call_subordinate(
            message=f"Start analyzing wallet {wallet}",
            profile="transaction_analyst",
            reset=True  # New subordinate
        )

        # Follow-up call - continue with same subordinate
        detailed = await self.agent.call_subordinate(
            message="Now analyze the last 24 hours in detail",
            profile="transaction_analyst",
            reset=False  # Continue existing subordinate
        )

        # Another follow-up
        patterns = await self.agent.call_subordinate(
            message="What patterns did you detect?",
            profile="transaction_analyst",
            reset=False  # Still same subordinate
        )

        return {"initial": initial, "detailed": detailed, "patterns": patterns}
```

### Example 4: Hierarchical Chain (Subordinate spawns subordinate)

```python
class HierarchicalOrchestrator:
    def __init__(self):
        config = AgentConfig(profile="orchestrator")
        context = AgentContext()
        self.agent = Agent(0, config, context)

    async def deep_investigation(self, wallet: str):
        # Master orchestrator delegates to subordinate orchestrator
        result = await self.agent.call_subordinate(
            message=f"""
            Investigate wallet {wallet} thoroughly:
            1. Use transaction_analyst subordinate for pattern detection
            2. Use graph_analyst subordinate for network mapping
            3. Use risk_assessor subordinate for final scoring
            4. Aggregate all results into comprehensive report
            """,
            profile="orchestrator",  # Subordinate orchestrator
            reset=True
        )

        # The subordinate orchestrator will spawn its own subordinates!
        return result
```

### Example 5: Real-World GODMODESCANNER Integration

```python
from agentzero.agent_zero_core import Agent, AgentConfig, AgentContext
from agents.transaction_monitor import TransactionMonitor
from utils.redis_streams_producer import RedisStreamsProducer

class GODMODESCANNEROrchestrator:
    def __init__(self):
        config = AgentConfig(
            profile="orchestrator",
            redis_host="localhost",
            redis_port=6379,
            timescaledb_host="172.17.0.1",
            timescaledb_port=5432
        )
        context = AgentContext()
        self.agent = Agent(0, config, context)
        self.redis_producer = RedisStreamsProducer()

    async def process_suspicious_transaction(self, tx_data: dict):
        wallet = tx_data["wallet_address"]
        tx_sig = tx_data["signature"]

        # Step 1: Quick pattern check
        pattern_check = await self.agent.call_subordinate(
            message=f"""
            Analyze transaction {tx_sig} for wallet {wallet}.
            Check for these patterns:
            - Dev Insider
            - Telegram Alpha
            - Sniper Bot
            - Wash Trader
            Return: pattern_type, confidence
            """,
            profile="transaction_analyst",
            reset=True
        )

        # If high confidence, do deep analysis
        if "confidence: 0.8" in pattern_check.lower():
            # Step 2: Graph analysis
            network = await self.agent.call_subordinate(
                message=f"""
                Perform 3-hop graph traversal from {wallet}.
                Identify:
                - Funding sources
                - Connected wallets
                - Sybil clusters
                """,
                profile="graph_analyst",
                reset=True
            )

            # Step 3: Risk scoring
            risk = await self.agent.call_subordinate(
                message=f"""
                Calculate risk score for {wallet}.
                Input data:
                - Pattern: {pattern_check}
                - Network: {network}

                Output: risk_score, alert_level, confidence_interval
                """,
                profile="risk_assessor",
                reset=True
            )

            # Publish to Redis Streams for alert pipeline
            await self.redis_producer.publish(
                stream="godmode:high_risk_alerts",
                data={
                    "wallet": wallet,
                    "transaction": tx_sig,
                    "pattern": pattern_check,
                    "network": network,
                    "risk": risk
                }
            )

            return {
                "status": "HIGH_RISK",
                "pattern": pattern_check,
                "network": network,
                "risk": risk
            }

        return {"status": "LOW_RISK", "pattern": pattern_check}
```

---

## 🔧 Advanced Patterns

### Pattern 1: Parallel Subordinate Execution

```python
import asyncio

class ParallelOrchestrator:
    async def parallel_analysis(self, wallets: list[str]):
        # Spawn multiple subordinates in parallel
        tasks = [
            self.agent.call_subordinate(
                message=f"Analyze wallet {wallet}",
                profile="transaction_analyst",
                reset=True
            )
            for wallet in wallets
        ]

        # Wait for all to complete
        results = await asyncio.gather(*tasks)

        return dict(zip(wallets, results))
```

### Pattern 2: Conditional Subordinate Selection

```python
class AdaptiveOrchestrator:
    async def adaptive_analysis(self, wallet: str, analysis_type: str):
        # Select subordinate based on analysis type
        profile_map = {
            "quick": "transaction_analyst",
            "deep": "graph_analyst",
            "risk": "risk_assessor",
            "research": "researcher"
        }

        profile = profile_map.get(analysis_type, "transaction_analyst")

        result = await self.agent.call_subordinate(
            message=f"Perform {analysis_type} analysis on {wallet}",
            profile=profile,
            reset=True
        )

        return result
```

### Pattern 3: Subordinate Result Aggregation

```python
class AggregatingOrchestrator:
    async def aggregate_insights(self, wallet: str):
        # Collect insights from multiple subordinates
        insights = {}

        # Transaction patterns
        insights["patterns"] = await self.agent.call_subordinate(
            message=f"Detect patterns for {wallet}",
            profile="transaction_analyst",
            reset=True
        )

        # Network analysis
        insights["network"] = await self.agent.call_subordinate(
            message=f"Map network for {wallet}",
            profile="graph_analyst",
            reset=True
        )

        # Risk assessment
        insights["risk"] = await self.agent.call_subordinate(
            message=f"Assess risk for {wallet}",
            profile="risk_assessor",
            reset=True
        )

        # Aggregate with researcher subordinate
        final_report = await self.agent.call_subordinate(
            message=f"""
            Create comprehensive report for {wallet}:

            Patterns: {insights['patterns']}
            Network: {insights['network']}
            Risk: {insights['risk']}

            Synthesize into executive summary.
            """,
            profile="researcher",
            reset=True
        )

        return final_report
```

---

## 🎯 Best Practices

### 1. **Use `reset=True` for Independent Tasks**
```python
# Good: Each wallet gets fresh analysis
for wallet in wallets:
    result = await agent.call_subordinate(
        message=f"Analyze {wallet}",
        profile="transaction_analyst",
        reset=True  # Fresh subordinate each time
    )
```

### 2. **Use `reset=False` for Iterative Refinement**
```python
# Good: Build on previous context
result1 = await agent.call_subordinate(
    message="Analyze wallet ABC",
    profile="transaction_analyst",
    reset=True  # Initial analysis
)

result2 = await agent.call_subordinate(
    message="Now focus on the last 24 hours",
    profile="transaction_analyst",
    reset=False  # Continue with context
)
```

### 3. **Choose Appropriate Profiles**
```python
# Good: Match profile to task
await agent.call_subordinate(
    message="Calculate Bayesian risk score",
    profile="risk_assessor",  # Correct profile
    reset=True
)

# Bad: Wrong profile for task
await agent.call_subordinate(
    message="Calculate Bayesian risk score",
    profile="developer",  # Wrong profile!
    reset=True
)
```

### 4. **Provide Clear Instructions**
```python
# Good: Specific, actionable instructions
await agent.call_subordinate(
    message="""
    Analyze wallet 7xKXtg2CW87d97TXJSDpbD5jBkheTqA83TZRuJosgAsU:
    1. Check last 100 transactions
    2. Detect insider patterns
    3. Return: pattern_type, confidence, evidence
    """,
    profile="transaction_analyst",
    reset=True
)

# Bad: Vague instructions
await agent.call_subordinate(
    message="Check this wallet",  # Too vague!
    profile="transaction_analyst",
    reset=True
)
```

---

## 🔍 Debugging

### Enable Verbose Logging

```python
import logging

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("agent_zero")

# You'll see:
# 🤖 Agent-0 spawned subordinate Agent-1 with profile: transaction_analyst
```

### Check Subordinate Status

```python
# Check if subordinate exists
subordinate = agent.get_data(agent.DATA_NAME_SUBORDINATE)
if subordinate:
    print(f"Subordinate exists: Agent-{subordinate.number}")
    print(f"Profile: {subordinate.config.profile}")
else:
    print("No subordinate spawned yet")
```

---

## 📊 Performance Considerations

### Memory Usage
- Each subordinate has its own memory directory
- Use `reset=True` sparingly for long-running sessions
- Clean up subordinates when done

### Execution Time
- Subordinate spawning: ~10-50ms
- Task execution: Depends on complexity
- Parallel execution recommended for multiple subordinates

### Resource Limits
- Maximum subordinate depth: Configurable (default: 5 levels)
- Memory per subordinate: ~10-50 MB
- Redis connections: 1 per subordinate

---

## 🎉 Summary

The `call_subordinate()` feature enables:

✅ **Hierarchical agent management**  
✅ **Specialized task delegation**  
✅ **Context isolation**  
✅ **Multi-level orchestration**  
✅ **Flexible session management**

**Next Steps**:
1. Review the examples above
2. Choose appropriate profiles for your tasks
3. Implement subordinate calls in your agents
4. Test with `reset=True` and `reset=False`
5. Monitor performance and optimize

---

**Created**: 2026-01-25  
**System**: GODMODESCANNER v1.0  
**Component**: Agent Zero call_subordinate Feature  
**Status**: ✅ Production Ready
