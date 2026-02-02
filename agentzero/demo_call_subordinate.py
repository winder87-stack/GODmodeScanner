#!/usr/bin/env python3
"""
Agent Zero call_subordinate Feature Demo

Demonstrates hierarchical agent management and task delegation
for GODMODESCANNER insider trading detection system.
"""

import asyncio
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from agentzero.agent_zero_core import Agent, AgentConfig, AgentContext


class CallSubordinateDemo:
    """Demonstrates call_subordinate feature with practical examples"""

    def __init__(self):
        # Initialize master orchestrator agent
        config = AgentConfig(
            profile="orchestrator",
            memory_subdir="demo/master",
            redis_host="localhost",
            redis_port=6379,
            timescaledb_host="172.17.0.1",
            timescaledb_port=5432
        )

        context = AgentContext()
        self.master_agent = Agent(0, config, context)

        print("🚀 GODMODESCANNER call_subordinate Demo")
        print("=" * 60)
        print()

    async def demo_1_basic_subordinate(self):
        """Demo 1: Basic subordinate call with transaction analysis"""
        print("📋 Demo 1: Basic Subordinate Call")
        print("-" * 60)

        wallet = "7xKXtg2CW87d97TXJSDpbD5jBkheTqA83TZRuJosgAsU"

        print(f"Task: Analyze wallet {wallet[:8]}...{wallet[-8:]}")
        print(f"Profile: transaction_analyst")
        print(f"Reset: True (new subordinate)")
        print()

        result = await self.master_agent.call_subordinate(
            message=f"""
            Analyze wallet {wallet} for insider trading patterns.

            Check for:
            - Dev Insider patterns
            - Telegram Alpha leaks
            - Sniper Bot activity
            - Wash Trading

            Return: pattern_type, confidence, evidence
            """,
            profile="transaction_analyst",
            reset=True
        )

        print("✅ Result:")
        print(result)
        print()
        print("=" * 60)
        print()

    async def demo_2_multi_step_analysis(self):
        """Demo 2: Multi-step analysis with different subordinates"""
        print("📋 Demo 2: Multi-Step Analysis")
        print("-" * 60)

        wallet = "9WzDXwBbmkg8ZTbNMqUxvQRAyrZzDsGYdLVL9zYtAWWM"

        print(f"Task: Comprehensive wallet investigation")
        print(f"Wallet: {wallet[:8]}...{wallet[-8:]}")
        print()

        # Step 1: Transaction Analysis
        print("Step 1/3: Transaction Analysis (transaction_analyst)")
        tx_result = await self.master_agent.call_subordinate(
            message=f"Analyze recent transactions for wallet {wallet}",
            profile="transaction_analyst",
            reset=True
        )
        print(f"  ✓ Completed: {len(tx_result)} chars")
        print()

        # Step 2: Graph Traversal
        print("Step 2/3: Graph Traversal (graph_analyst)")
        graph_result = await self.master_agent.call_subordinate(
            message=f"Perform 3-hop graph traversal from {wallet}",
            profile="graph_analyst",
            reset=True
        )
        print(f"  ✓ Completed: {len(graph_result)} chars")
        print()

        # Step 3: Risk Scoring
        print("Step 3/3: Risk Scoring (risk_assessor)")
        risk_result = await self.master_agent.call_subordinate(
            message=f"""
            Calculate risk score for {wallet}.

            Transaction Analysis: {tx_result[:100]}...
            Graph Analysis: {graph_result[:100]}...

            Output: risk_score, alert_level, confidence_interval
            """,
            profile="risk_assessor",
            reset=True
        )
        print(f"  ✓ Completed: {len(risk_result)} chars")
        print()

        print("📊 Final Results:")
        print(f"  • Transaction Analysis: {len(tx_result)} chars")
        print(f"  • Graph Analysis: {len(graph_result)} chars")
        print(f"  • Risk Score: {len(risk_result)} chars")
        print()
        print("=" * 60)
        print()

    async def demo_3_iterative_refinement(self):
        """Demo 3: Iterative refinement with reset=False"""
        print("📋 Demo 3: Iterative Refinement (reset=False)")
        print("-" * 60)

        wallet = "5Q544fKrFoe6tsEbD7S8EmxGTJYAKtTVhAW5Q5pge4j1"

        print(f"Task: Iterative wallet analysis")
        print(f"Wallet: {wallet[:8]}...{wallet[-8:]}")
        print()

        # Initial analysis
        print("Call 1: Initial analysis (reset=True)")
        result1 = await self.master_agent.call_subordinate(
            message=f"Start analyzing wallet {wallet}",
            profile="transaction_analyst",
            reset=True  # New subordinate
        )
        print(f"  ✓ Completed: {len(result1)} chars")
        print()

        # Detailed follow-up
        print("Call 2: Detailed analysis (reset=False)")
        result2 = await self.master_agent.call_subordinate(
            message="Now analyze the last 24 hours in detail",
            profile="transaction_analyst",
            reset=False  # Continue with same subordinate
        )
        print(f"  ✓ Completed: {len(result2)} chars")
        print()

        # Pattern detection
        print("Call 3: Pattern detection (reset=False)")
        result3 = await self.master_agent.call_subordinate(
            message="What insider patterns did you detect?",
            profile="transaction_analyst",
            reset=False  # Still same subordinate
        )
        print(f"  ✓ Completed: {len(result3)} chars")
        print()

        print("📊 Iterative Results:")
        print(f"  • Initial: {len(result1)} chars")
        print(f"  • Detailed: {len(result2)} chars")
        print(f"  • Patterns: {len(result3)} chars")
        print(f"  • Same subordinate used for all 3 calls")
        print()
        print("=" * 60)
        print()

    async def demo_4_hierarchical_chain(self):
        """Demo 4: Hierarchical chain (subordinate spawns subordinate)"""
        print("📋 Demo 4: Hierarchical Chain")
        print("-" * 60)

        wallet = "DYw8jCTfwHNRJhhmFcbXvVDTqWMEVFBX6ZKUmG5CNSKK"

        print(f"Task: Deep investigation with subordinate orchestrator")
        print(f"Wallet: {wallet[:8]}...{wallet[-8:]}")
        print()

        print("Master Orchestrator → Subordinate Orchestrator → Specialized Agents")
        print()

        result = await self.master_agent.call_subordinate(
            message=f"""
            Investigate wallet {wallet} thoroughly:

            1. Use transaction_analyst subordinate for pattern detection
            2. Use graph_analyst subordinate for network mapping
            3. Use risk_assessor subordinate for final scoring
            4. Aggregate all results into comprehensive report

            Coordinate these subordinates and provide executive summary.
            """,
            profile="orchestrator",  # Subordinate orchestrator
            reset=True
        )

        print("✅ Hierarchical Result:")
        print(f"  • Master Agent-0 (orchestrator)")
        print(f"    └─ Subordinate Agent-1 (orchestrator)")
        print(f"       ├─ Agent-2 (transaction_analyst)")
        print(f"       ├─ Agent-3 (graph_analyst)")
        print(f"       └─ Agent-4 (risk_assessor)")
        print()
        print(f"  Result: {len(result)} chars")
        print()
        print("=" * 60)
        print()

    async def demo_5_parallel_execution(self):
        """Demo 5: Parallel subordinate execution"""
        print("📋 Demo 5: Parallel Execution")
        print("-" * 60)

        wallets = [
            "7xKXtg2CW87d97TXJSDpbD5jBkheTqA83TZRuJosgAsU",
            "9WzDXwBbmkg8ZTbNMqUxvQRAyrZzDsGYdLVL9zYtAWWM",
            "5Q544fKrFoe6tsEbD7S8EmxGTJYAKtTVhAW5Q5pge4j1"
        ]

        print(f"Task: Analyze {len(wallets)} wallets in parallel")
        print()

        # Create parallel tasks
        tasks = [
            self.master_agent.call_subordinate(
                message=f"Analyze wallet {wallet} for insider patterns",
                profile="transaction_analyst",
                reset=True
            )
            for wallet in wallets
        ]

        print(f"Spawning {len(tasks)} subordinates in parallel...")
        results = await asyncio.gather(*tasks)

        print("✅ Parallel Results:")
        for i, (wallet, result) in enumerate(zip(wallets, results), 1):
            print(f"  {i}. {wallet[:8]}...{wallet[-8:]}: {len(result)} chars")

        print()
        print(f"Total: {len(results)} wallets analyzed concurrently")
        print()
        print("=" * 60)
        print()

    async def run_all_demos(self):
        """Run all demonstration scenarios"""
        try:
            await self.demo_1_basic_subordinate()
            await asyncio.sleep(1)

            await self.demo_2_multi_step_analysis()
            await asyncio.sleep(1)

            await self.demo_3_iterative_refinement()
            await asyncio.sleep(1)

            await self.demo_4_hierarchical_chain()
            await asyncio.sleep(1)

            await self.demo_5_parallel_execution()

            print("🎉 All Demos Completed Successfully!")
            print()
            print("📚 Next Steps:")
            print("  1. Review docs/CALL_SUBORDINATE_GUIDE.md")
            print("  2. Implement call_subordinate in your agents")
            print("  3. Test with different profiles and scenarios")
            print("  4. Monitor performance and optimize")
            print()

        except Exception as e:
            print(f"❌ Demo failed: {e}")
            import traceback
            traceback.print_exc()


if __name__ == "__main__":
    demo = CallSubordinateDemo()
    asyncio.run(demo.run_all_demos())
