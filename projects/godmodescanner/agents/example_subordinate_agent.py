#!/usr/bin/env python3
"""
Example Subordinate Agent

Demonstrates how to create a subordinate agent using BaseAgent class.
This agent processes messages from Redis channels and reports metrics.
"""

import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from agents.base_agent import BaseAgent


class ExampleAgent(BaseAgent):
    """Example subordinate agent implementation"""

    def __init__(self, redis_url: str = "redis://localhost:6379"):
        super().__init__(
            agent_type="example_agent",
            redis_url=redis_url,
            heartbeat_interval=30
        )

        # Agent-specific state
        self.processed_count = 0

    async def agent_initialize(self) -> bool:
        """Initialize agent-specific resources"""
        try:
            # Subscribe to channels
            await self.subscribe_to_channels(["example_channel", "test_channel"])

            self.logger.info("Example agent initialized")
            return True

        except Exception as e:
            self.logger.error(f"Failed to initialize: {e}")
            return False

    async def process_message(self, channel: str, message: dict) -> bool:
        """Process incoming message"""
        try:
            self.logger.info(f"Processing message from {channel}: {message}")

            # Simulate processing
            await asyncio.sleep(0.1)

            # Increment counter
            self.processed_count += 1

            # Publish result to output channel
            result = {
                "agent_id": self.agent_id,
                "processed_count": self.processed_count,
                "input_channel": channel,
                "message": message
            }

            await self.publish_message("example_output", result)

            return True

        except Exception as e:
            self.logger.error(f"Error processing message: {e}")
            return False


if __name__ == "__main__":
    # Create and run agent
    agent = ExampleAgent()

    try:
        asyncio.run(agent.start())
    except KeyboardInterrupt:
        print("Agent terminated by user")
