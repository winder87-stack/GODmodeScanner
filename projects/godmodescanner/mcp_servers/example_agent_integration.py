#!/usr/bin/env python3
"""
Example: Integrating existing agent with MCP

This shows how to convert an existing GODMODESCANNER agent to use MCP.
"""

import asyncio
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mcp_servers.mcp_client import MCPAgentClient

class TransactionMonitorMCP:
    """
    Transaction Monitor agent with MCP integration

    This wraps the existing transaction_monitor.py logic with MCP client.
    """

    def __init__(self, agent_id: str = "tx_monitor_001"):
        self.agent_id = agent_id

        # Create MCP client
        self.mcp_client = MCPAgentClient(
            agent_id=agent_id,
            agent_type="transaction_monitor",
            capabilities=[
                "blockchain_monitoring",
                "transaction_parsing",
                "token_detection",
                "real_time_streaming"
            ],
            mcp_server_url=os.getenv('MCP_SERVER_URL', 'http://localhost:8000'),
            redis_url=os.getenv('REDIS_URL', 'redis://localhost:6379')
        )

    async def initialize(self):
        """Initialize the agent"""
        await self.mcp_client.initialize()
        print(f"✅ Transaction Monitor initialized: {self.agent_id}")

    async def process_task(self, payload: dict) -> dict:
        """
        Process a task

        This is where you integrate your existing agent logic.
        """
        task_type = payload.get('task_type')

        if task_type == 'monitor_token':
            return await self._monitor_token(payload)
        elif task_type == 'analyze_transaction':
            return await self._analyze_transaction(payload)
        else:
            return {'error': f'Unknown task type: {task_type}'}

    async def _monitor_token(self, payload: dict) -> dict:
        """
        Monitor a specific token for suspicious activity
        """
        token_address = payload.get('token_address')

        # Your existing monitoring logic here
        print(f"📊 Monitoring token: {token_address}")

        # Simulate monitoring
        await asyncio.sleep(1)

        # Publish event
        await self.mcp_client.publish_event(
            'token_monitored',
            {
                'token_address': token_address,
                'status': 'active'
            }
        )

        return {
            'status': 'monitoring',
            'token_address': token_address,
            'timestamp': '2026-01-24T15:30:00Z'
        }

    async def _analyze_transaction(self, payload: dict) -> dict:
        """
        Analyze a transaction for insider patterns
        """
        tx_signature = payload.get('tx_signature')

        # Your existing analysis logic here
        print(f"🔍 Analyzing transaction: {tx_signature}")

        # Simulate analysis
        await asyncio.sleep(0.5)

        # Delegate to wallet analyzer if needed
        wallet_address = payload.get('wallet_address')
        if wallet_address:
            delegation_result = await self.mcp_client.delegate_task(
                task_id=f"wallet_analysis_{wallet_address}",
                task_type="analyze_wallet",
                payload={'wallet_address': wallet_address},
                target_agent_type="wallet_analyzer",
                priority=8
            )
            print(f"📤 Delegated wallet analysis: {delegation_result}")

        return {
            'status': 'analyzed',
            'tx_signature': tx_signature,
            'risk_score': 0.75,
            'patterns_detected': ['early_buyer', 'coordinated_buying']
        }

    async def run(self):
        """Run the agent"""
        try:
            # Start listening for tasks
            await self.mcp_client.listen_for_tasks(
                task_handler=self.process_task,
                batch_size=10
            )
        except KeyboardInterrupt:
            print("
🛑 Shutting down...")
        finally:
            await self.mcp_client.close()


if __name__ == "__main__":
    async def main():
        agent = TransactionMonitorMCP()
        await agent.initialize()
        await agent.run()

    asyncio.run(main())
