import asyncio
import time
import structlog
from typing import Dict, List, Set
from datetime import datetime

from utils.aggressive_pump_fun_client import AggressivePumpFunClient
from utils.pumpfun_parser import PumpFunParser, EventType, TradeEvent
from agents.shared_memory.risk_score_segment import RiskScoreSegment

logger = structlog.get_logger()

class PumpFunDetectorAgent:
    """
    MCP-coordinated agent for detecting pump.fun activity.
    Integrates with GODMODESCANNER's existing multi-agent architecture.
    """
    
    def __init__(self):
        self.client = AggressivePumpFunClient()
        self.parser = PumpFunParser()
        self.shared_mem = RiskScoreSegment()
        
        # State tracking
        self.known_bonding_curves: Set[str] = set()
        self.processed_signatures: Set[str] = set()
        
        # Performance metrics
        self.metrics = {
            'new_tokens_detected': 0,
            'swaps_processed': 0,
            'alerts_triggered': 0,
            'uptime_seconds': 0
        }
        
        self.start_time = time.time()
        logger.info("PumpFunDetectorAgent initialized")

    async def monitor_for_new_tokens(self):
        """
        Continuously polls for new bonding curve accounts.
        Publishes to Redis Streams for parallel worker processing.
        """
        logger.info("monitor_new_tokens_started")
        
        while True:
            try:
                # Poll for program accounts
                accounts = await self.client.get_program_accounts(
                )
                
                new_curves = set()
                
                if accounts and 'result' in accounts:
                    current_curves = {acc['pubkey'] for acc in accounts['result']}
                    new_curves = current_curves - self.known_bonding_curves
                    
                    if new_curves:
                        logger.info("new_tokens_detected", 
                                   count=len(new_curves),
                                   curves=list(new_curves)[:5])  # Log first 5
                        
                        for curve_addr in new_curves:
                            # Publish to Redis for parallel processing by existing workers
                            await self.client.publish_to_redis_stream(
                                stream_key="wallet-analyzer-stream",
                                data={
                                    'event_type': 'NEW_TOKEN_LAUNCH',
                                    'bonding_curve': curve_addr,
                                    'timestamp': datetime.utcnow().isoformat(),
                                    'source': 'pump_fun_detector'
                                }
                            )
                            
                            # Trigger early detection workflow
                            await self.handle_new_token_launch(curve_addr)
                            
                            self.metrics['new_tokens_detected'] += 1
                        
                        self.known_bonding_curves.update(new_curves)
                
                # Adaptive polling interval based on activity
                await asyncio.sleep(3 if new_curves else 5)
                
            except Exception as e:
                logger.error("monitor_new_tokens_error", error=str(e))
                await asyncio.sleep(10)

    async def monitor_for_swaps(self):
        """
        Monitors for swap transactions.
        Uses getSignaturesForAddress for efficient polling.
        """
        logger.info("monitor_swaps_started")
        
        while True:
            try:
                # Get recent signatures
                signatures = await self.client.get_signatures_for_address(
                    address=self.client.PUMP_FUN_PROGRAM_ID,
                    limit=100
                )
                
                if signatures and 'result' in signatures:
                    for sig_info in reversed(signatures['result']):
                        signature = sig_info['signature']
                        
                        # Deduplication
                        if signature in self.processed_signatures:
                            continue
                        
                        # Fetch full transaction
                        tx = await self.client.get_transaction(signature)
                        
                        if tx and 'result' in tx and tx['result']:
                            # Process transaction and publish to Redis
                            await self.process_transaction(tx['result'], signature)
                            
                        self.processed_signatures.add(signature)
                        self.metrics['swaps_processed'] += 1
                
                # Aggressive polling for swaps (2 seconds)
                await asyncio.sleep(2)
                
            except Exception as e:
                logger.error("monitor_swaps_error", error=str(e))
                await asyncio.sleep(10)

    async def process_transaction(self, transaction: Dict, signature: str):
        """
        Parses transaction and publishes to Redis for parallel processing.
        Triggers existing wallet analyzer, pattern recognition, and risk scoring agents.
        """
        try:
            # Use your existing PumpFunParser - returns list of event objects
            events = self.parser.parse_transaction(transaction)
            
            if not events:
                return
            
            # Process each event
            for event in events:
                # Convert event object to dict
                event_data = event.to_dict() if hasattr(event, 'to_dict') else event
                
                event_type = event_data.get('event_type')
                
                # Handle TradeEvent (Buy/Sell)
                if event_type in (EventType.BUY, EventType.SELL):
                    user_address = event_data.get('trader')
                    mint_address = event_data.get('token_mint')
                    sol_amount = event_data.get('sol_amount', 0)
                    token_amount = event_data.get('token_amount', 0)
                    is_buy = (event_type == EventType.BUY)
                    
                    # Publish to wallet analyzer stream
                    await self.client.publish_to_redis_stream(
                        stream_key="wallet-analyzer-stream",
                        data={
                            'signature': signature,
                            'userAddress': user_address,
                            'mintAddress': mint_address,
                            'solAmount': sol_amount,
                            'tokenAmount': token_amount,
                            'isBuy': is_buy,
                            'timestamp': datetime.utcnow().isoformat(),
                            'program': 'pump_fun',
                            'event_type': 'SWAP',
                            'time_since_creation': event_data.get('time_since_creation_seconds', 0),
                            'is_creator': event_data.get('is_creator', False)
                        }
                    )
                    
                    # Check for high-value transactions (early detection)
                    if sol_amount > 10_000_000_000:  # 10 SOL
                        logger.warning("large_swap_detected",
                                      user=user_address,
                                      sol_amount=sol_amount / 1e9,
                                      mint=mint_address)
                        
                        # Write to zero-latency alert pipeline (15.65μs)
                        self.shared_mem.write_alert({
                            'type': 'LARGE_SWAP',
                            'user': user_address,
                            'mint': mint_address,
                            'amount': sol_amount,
                            'timestamp': time.time()
                        })
                        
                        self.metrics['alerts_triggered'] += 1
                    
                    # Publish to pattern recognition stream
                    await self.client.publish_to_redis_stream(
                        stream_key="pattern-recognition-stream",
                        data={
                            'signature': signature,
                            'userAddress': user_address,
                            'mintAddress': mint_address,
                            'solAmount': sol_amount,
                            'isBuy': is_buy,
                            'timestamp': datetime.utcnow().isoformat(),
                            'event_type': 'SWAP'
                        }
                    )
                    
                    logger.debug("transaction_processed",
                                signature=signature,
                                user=user_address,
                                sol_amount=sol_amount / 1e9)
                
                # Handle TokenCreateEvent
                elif event_type == EventType.TOKEN_CREATE:
                    creator = event_data.get('creator')
                    token_mint = event_data.get('token_mint')
                    initial_buy = event_data.get('initial_buy_sol', 0)
                    
                    await self.client.publish_to_redis_stream(
                        stream_key="wallet-analyzer-stream",
                        data={
                            'event_type': 'TOKEN_CREATE',
                            'signature': signature,
                            'creator': creator,
                            'token_mint': token_mint,
                            'initial_buy_sol': initial_buy,
                            'timestamp': datetime.utcnow().isoformat(),
                            'source': 'pump_fun_detector'
                        }
                    )
            
        except Exception as e:
            logger.error("process_transaction_error",
                        error=str(e),
                        signature=signature)

    async def handle_new_token_launch(self, bonding_curve_address: str):
        """
        Early detection trigger - integrates with existing graph analysis.
        """
        logger.info("early_detection_triggered", 
                   curve=bonding_curve_address)
        
        # Publish to specialized stream for immediate analysis
        await self.client.publish_to_redis_stream(
            stream_key="wallet-analyzer-stream",
            data={
                'event_type': 'EARLY_TOKEN_LAUNCH',
                'bonding_curve': bonding_curve_address,
                'timestamp': datetime.utcnow().isoformat(),
                'priority': 'HIGH'
            }
        )
        
        # This will be picked up by your existing agents:
        # - Wallet Analyzer Worker (funding source check)
        # - Graph Traversal Phase 1 (creator wallet analysis)
        # - Funding Hub Identifier (source tracking)
        # - Risk Scoring Agent (immediate risk assessment)

    async def log_metrics(self):
        """Logs performance metrics every 60 seconds."""
        while True:
            await asyncio.sleep(60)
            self.metrics['uptime_seconds'] = int(time.time() - self.start_time)
            logger.info("agent_metrics", **self.metrics)

    async def stop(self):
        """Stop the detector and cleanup."""
        logger.info("PumpFunDetectorAgent stopping")
        # Graceful shutdown handled by asyncio.CancelledError in run()
    
    async def run(self):
        """Starts all monitoring tasks with graceful shutdown."""
        logger.info("PumpFunDetectorAgent starting")
        
        try:
            await asyncio.gather(
                self.monitor_for_new_tokens(),
                self.monitor_for_swaps(),
                self.log_metrics()  # Periodic metrics logging
            )
        except asyncio.CancelledError:
            logger.info("PumpFunDetectorAgent shutting down gracefully")
        except Exception as e:
            logger.error("PumpFunDetectorAgent crashed", error=str(e))
            raise


# Main entry point
async def main():
    agent = PumpFunDetectorAgent()
    await agent.run()


if __name__ == "__main__":
    asyncio.run(main())
