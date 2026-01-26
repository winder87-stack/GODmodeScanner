"""WebSocket simulator for pump.fun transactions."""

import asyncio
import random
import time
from dataclasses import dataclass
from typing import List, Optional
import json

@dataclass
class PumpFunTransaction:
    """Simulated pump.fun transaction."""
    signature: str
    wallet_address: str
    token_address: str
    timestamp_ns: int
    amount_sol: float
    token_amount: float
    transaction_type: str  # 'buy', 'sell', 'create'

    @classmethod
    def generate_random(cls, sequence: int) -> 'PumpFunTransaction':
        """Generate a random simulated transaction."""
        # Generate random Solana addresses
        wallet = ''.join(random.choices('123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz', k=44))
        token = ''.join(random.choices('123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz', k=44))

        tx_type = random.choice(['buy', 'sell', 'create'])

        return cls(
            signature=f"{random.randint(1, 18446744073709551615):064x}",
            wallet_address=wallet,
            token_address=token,
            timestamp_ns=time.time_ns(),
            amount_sol=random.uniform(0.01, 10.0),
            token_amount=random.uniform(1000, 1000000),
            transaction_type=tx_type
        )


class WebSocketSimulator:
    """Simulates real-time WebSocket connection to pump.fun."""

    def __init__(self, transactions_per_second: int = 100):
        self.transactions_per_second = transactions_per_second
        self.running = False
        self.transaction_callback = None
        self.latency_samples: List[int] = []

    def set_callback(self, callback):
        """Set callback for new transactions."""
        self.transaction_callback = callback

    async def start(self, duration_seconds: Optional[int] = None):
        """Start the WebSocket simulator.

        Args:
            duration_seconds: Run for N seconds, or None for infinite
        """
        self.running = True
        start_time = time.time()
        sequence = 0

        interval = 1.0 / self.transactions_per_second

        try:
            while self.running:
                # Check duration limit
                if duration_seconds and (time.time() - start_time) >= duration_seconds:
                    break

                # Generate transaction
                tx = PumpFunTransaction.generate_random(sequence)
                sequence += 1

                # Simulate WebSocket receive latency (random 10-100 us)
                ws_latency = random.randint(10, 100)
                await asyncio.sleep(ws_latency / 1_000_000)

                # Call callback
                if self.transaction_callback:
                    receive_time = time.time_ns()
                    self.transaction_callback(tx, receive_time)

                # Wait for next transaction
                await asyncio.sleep(interval)

        except asyncio.CancelledError:
            pass
        finally:
            self.running = False

    def stop(self):
        """Stop the simulator."""
        self.running = False


if __name__ == "__main__":
    async def test_simulator():
        simulator = WebSocketSimulator(transactions_per_second=10)

        def on_transaction(tx, receive_time):
            print(f"Transaction: {tx.transaction_type} {tx.amount_sol} SOL")
            print(f"  Wallet: {tx.wallet_address[:20]}...")
            print(f"  Token: {tx.token_address[:20]}...")

        simulator.set_callback(on_transaction)
        await simulator.start(duration_seconds=1)

    asyncio.run(test_simulator())
