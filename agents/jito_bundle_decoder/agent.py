"""
Jito Bundle Decoder Agent
Monitors Jito tip accounts to detect insider MEV transactions
"""

import asyncio
import structlog
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from datetime import datetime
from solana.rpc.async_api import AsyncClient
from solders.pubkey import Pubkey

logger = structlog.get_logger()

# Jito tip accounts (mainnet-beta)
JITO_TIP_ACCOUNTS = [
    "96gYZGLnJYVFmbjzopPSU6QiEV5fGqZNyN9nmNhvrZU5",
    "HFqU5x63VTqvQss8hp11i4wVV8bD44PvwucfZ2bU7gRe",
    "Cw8CFyM9FkoMi7K7Crf6HNQqf4uEMzpKw6QNghXLvLkY",
    "ADaUMid9yfUytqMBgopwjb2DTLSokTSzL1zt6iGPaS49",
    "DfXygSm4jCyNCybVYYK6DwvWqjKee8pbDmJGcLWNDXjh",
    "ADuUkR4vqLUMWXxW9gh6D6L8pMSawimctcNZ5pGwDcEt",
    "DttWaMuVvTiduZRnguLF7jNxTgiMBZ1hyAumKUiL2KRL",
    "3AVi9Tg9Uo68tJfuvoKvqKNWKkC5wPdSSdeBnizKZ6jT"
]

PUMP_FUN_PROGRAM = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
RAYDIUM_AMM_PROGRAM = "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8"


@dataclass
class JitoBundleSignal:
    """Represents a detected Jito bundle insider signal"""
    wallet: str
    token: str
    tip_amount_sol: float
    swap_amount_sol: float
    signature: str
    timestamp: int
    confidence: float
    priority: str
    bundle_position: int


class JitoBundleDecoderAgent:
    """Monitor Jito tip payments to detect insider bundle transactions"""
    
    def __init__(self, rpc_client: AsyncClient, redis_client, eternal_mind=None, config: Optional[Dict] = None):
        self.rpc = rpc_client
        self.redis = redis_client
        self.eternal_mind = eternal_mind
        self.config = config or {}
        
        self.tip_accounts = [Pubkey.from_string(addr) for addr in JITO_TIP_ACCOUNTS]
        self.processed_signatures = set()
        self.processed_signatures_max = 100000
        
        self.metrics = {'bundles_detected': 0, 'signals_published': 0, 'avg_detection_latency_ms': 0.0}
        
        logger.info("JitoBundleDecoderAgent initialized", tip_accounts=len(self.tip_accounts))
    
    async def start(self):
        """Start monitoring all Jito tip accounts"""
        logger.info("Starting Jito Bundle Decoder...")
        tasks = [asyncio.create_task(self._monitor_tip_account(account)) for account in self.tip_accounts]
        tasks.append(asyncio.create_task(self._poll_recent_signatures()))
        await asyncio.gather(*tasks, return_exceptions=True)
    
    async def _monitor_tip_account(self, tip_account: Pubkey):
        """Monitor a single Jito tip account"""
        while True:
            try:
                signatures = await self.rpc.get_signatures_for_address(tip_account, limit=50)
                
                for sig_info in signatures.value:
                    sig_str = str(sig_info.signature)
                    if sig_str in self.processed_signatures:
                        continue
                    
                    self.processed_signatures.add(sig_str)
                    
                    if len(self.processed_signatures) > self.processed_signatures_max:
                        to_remove = list(self.processed_signatures)[:10000]
                        for s in to_remove:
                            self.processed_signatures.discard(s)
                    
                    asyncio.create_task(self._process_signature(sig_info, tip_account))
                
                await asyncio.sleep(0.5)
            except Exception as e:
                logger.error("Error monitoring tip account", account=str(tip_account), error=str(e))
                await asyncio.sleep(5)
    
    async def _poll_recent_signatures(self):
        """Backup polling mechanism"""
        while True:
            try:
                for tip_account in self.tip_accounts:
                    signatures = await self.rpc.get_signatures_for_address(tip_account, limit=20)
                    for sig_info in signatures.value:
                        sig_str = str(sig_info.signature)
                        if sig_str not in self.processed_signatures:
                            self.processed_signatures.add(sig_str)
                            asyncio.create_task(self._process_signature(sig_info, tip_account))
                await asyncio.sleep(2)
            except Exception as e:
                logger.error("Error in signature polling", error=str(e))
                await asyncio.sleep(10)
    
    async def _process_signature(self, sig_info, tip_account: Pubkey):
        """Process a single signature"""
        start_time = datetime.utcnow()
        try:
            tx = await self.rpc.get_transaction(sig_info.signature, max_supported_transaction_version=0)
            if not tx.value:
                return
            
            tip_amount = self._extract_tip_amount(tx.value, tip_account)
            if tip_amount < 0.001:
                return
            
            bundle_sender = self._extract_bundle_sender(tx.value)
            swap_data = await self._extract_bundled_swap(tx.value)
            
            if not swap_data:
                return
            
            confidence = self._calculate_confidence(tip_amount, swap_data)
            
            signal = JitoBundleSignal(
                wallet=bundle_sender,
                token=swap_data['token'],
                tip_amount_sol=tip_amount,
                swap_amount_sol=swap_data['amount'],
                signature=str(sig_info.signature),
                timestamp=tx.value.block_time or int(datetime.utcnow().timestamp()),
                confidence=confidence,
                priority='CRITICAL' if confidence >= 0.90 else 'HIGH',
                bundle_position=swap_data.get('position', 0)
            )
            
            await self._publish_signal(signal)
            await self._store_pattern(signal)
            
            self.metrics['bundles_detected'] += 1
            latency = (datetime.utcnow() - start_time).total_seconds() * 1000
            self.metrics['avg_detection_latency_ms'] = self.metrics['avg_detection_latency_ms'] * 0.9 + latency * 0.1
            
            logger.info("JITO_BUNDLE_DETECTED", wallet=bundle_sender, token=swap_data['token'], tip=tip_amount, confidence=confidence)
        except Exception as e:
            logger.error("Error processing signature", sig=str(sig_info.signature), error=str(e))
    
    def _extract_tip_amount(self, transaction, tip_account: Pubkey) -> float:
        """Extract SOL tip amount"""
        pre_balances = transaction.meta.pre_balances
        post_balances = transaction.meta.post_balances
        account_keys = transaction.transaction.message.account_keys
        
        for i, account in enumerate(account_keys):
            if str(account) == str(tip_account):
                tip_lamports = post_balances[i] - pre_balances[i]
                return max(0, tip_lamports / 1e9)
        return 0.0
    
    def _extract_bundle_sender(self, transaction) -> str:
        """Extract fee payer"""
        return str(transaction.transaction.message.account_keys[0])
    
    async def _extract_bundled_swap(self, transaction) -> Optional[Dict[str, Any]]:
        """Extract swap instruction"""
        instructions = transaction.transaction.message.instructions
        account_keys = transaction.transaction.message.account_keys
        
        for idx, instruction in enumerate(instructions):
            program_id = str(account_keys[instruction.program_id_index])
            if program_id == PUMP_FUN_PROGRAM:
                return self._decode_pump_fun_swap(instruction, transaction, idx)
            if program_id == RAYDIUM_AMM_PROGRAM:
                return self._decode_raydium_swap(instruction, transaction, idx)
        return None
    
    def _decode_pump_fun_swap(self, instruction, transaction, position: int) -> Optional[Dict]:
        """Decode Pump.fun swap"""
        try:
            accounts = instruction.accounts
            account_keys = transaction.transaction.message.account_keys
            data = instruction.data
            
            if len(accounts) < 2:
                return None
            
            mint = str(account_keys[accounts[1]])
            amount_sol = 0.0
            if len(data) >= 16:
                amount_lamports = int.from_bytes(bytes(data[8:16]), 'little')
                amount_sol = amount_lamports / 1e9
            
            return {'token': mint, 'amount': amount_sol, 'dex': 'pump_fun', 'position': position}
        except Exception as e:
            logger.debug("Failed to decode pump.fun swap", error=str(e))
            return None
    
    def _decode_raydium_swap(self, instruction, transaction, position: int) -> Optional[Dict]:
        """Decode Raydium swap"""
        try:
            accounts = instruction.accounts
            account_keys = transaction.transaction.message.account_keys
            if len(accounts) < 5:
                return None
            mint = str(account_keys[accounts[4]])
            return {'token': mint, 'amount': 0.0, 'dex': 'raydium', 'position': position}
        except Exception as e:
            logger.debug("Failed to decode raydium swap", error=str(e))
            return None
    
    def _calculate_confidence(self, tip_amount: float, swap_data: Dict) -> float:
        """Calculate confidence score"""
        base_confidence = 0.50
        
        if tip_amount >= 1.0:
            base_confidence += 0.40
        elif tip_amount >= 0.5:
            base_confidence += 0.35
        elif tip_amount >= 0.1:
            base_confidence += 0.25
        elif tip_amount >= 0.05:
            base_confidence += 0.15
        elif tip_amount >= 0.01:
            base_confidence += 0.05
        
        swap_amount = swap_data.get('amount', 0)
        if swap_amount >= 10.0:
            base_confidence += 0.10
        elif swap_amount >= 5.0:
            base_confidence += 0.07
        elif swap_amount >= 1.0:
            base_confidence += 0.03
        
        if swap_data.get('position', 0) == 0:
            base_confidence += 0.05
        
        return min(0.99, base_confidence)
    
    async def _publish_signal(self, signal: JitoBundleSignal):
        """Publish to Redis stream"""
        await self.redis.xadd(
            'godmode:jito_signals',
            {
                'type': 'JITO_BUNDLE_DETECTED',
                'wallet': signal.wallet,
                'token': signal.token,
                'tip_amount_sol': str(signal.tip_amount_sol),
                'swap_amount_sol': str(signal.swap_amount_sol),
                'signature': signal.signature,
                'timestamp': str(signal.timestamp),
                'confidence': str(signal.confidence),
                'priority': signal.priority,
                'bundle_position': str(signal.bundle_position)
            }
        )
        self.metrics['signals_published'] += 1
    
    async def _store_pattern(self, signal: JitoBundleSignal):
        """Store in ETERNAL MIND"""
        await self.redis.hincrby(f"jito:user:{signal.wallet}", "total_bundles", 1)
        await self.redis.hset(
            f"jito:user:{signal.wallet}",
            mapping={
                'last_tip': str(signal.tip_amount_sol),
                'last_token': signal.token,
                'last_timestamp': str(signal.timestamp)
            }
        )
        
        current_tips = await self.redis.hget(f"jito:user:{signal.wallet}", "total_tips_sol")
        current_tips = float(current_tips or 0)
        new_total = current_tips + signal.tip_amount_sol
        
        await self.redis.hset(f"jito:user:{signal.wallet}", "total_tips_sol", str(new_total))
        await self.redis.zadd("jito:leaderboard:by_tips", {signal.wallet: new_total})
    
    async def get_metrics(self) -> Dict[str, Any]:
        return self.metrics.copy()
    
    async def get_top_jito_users(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get top Jito users by tips"""
        top_users = await self.redis.zrevrange("jito:leaderboard:by_tips", 0, limit - 1, withscores=True)
        results = []
        for wallet, total_tips in top_users:
            profile = await self.redis.hgetall(f"jito:user:{wallet}")
            results.append({
                'wallet': wallet.decode() if isinstance(wallet, bytes) else wallet,
                'total_tips_sol': total_tips,
                'total_bundles': int(profile.get(b'total_bundles', 0)),
                'last_token': profile.get(b'last_token', b'').decode()
            })
        return results
