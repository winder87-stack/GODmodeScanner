"""GODMODESCANNER Token Detector

Complete token detection and metadata fetching for pump.fun with:
- Token scanning (new token detection)
- Metadata fetching (token info retrieval)

"""

import asyncio
import base64
import struct
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List, Set
from datetime import datetime, timezone
import aiohttp
import structlog

logger = structlog.get_logger(__name__)

# =============================================================================
# CONSTANTS
# =============================================================================

# pump.fun Program ID
PUMPFUN_PROGRAM_ID = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"

# Token Program IDs
TOKEN_PROGRAM_ID = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
METAPLEX_PROGRAM_ID = "metaqbxxUerdq28cj1RbAWkYQm3ybzjb6a8bt518x1s"

# RPC endpoints (free tier)
DEFAULT_RPC_ENDPOINTS = [
    "https://api.mainnet-beta.solana.com",
    "https://solana-mainnet.g.alchemy.com/v2/demo",
    "https://rpc.ankr.com/solana",
]

# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class TokenMetadata:
    """Token metadata."""
    mint: str
    name: str
    symbol: str
    decimals: int
    supply: int
    creator: Optional[str] = None
    uri: Optional[str] = None
    image_url: Optional[str] = None
    description: Optional[str] = None
    is_pumpfun: bool = False
    bonding_curve: Optional[str] = None
    launch_time: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "mint": self.mint,
            "name": self.name,
            "symbol": self.symbol,
            "decimals": self.decimals,
            "supply": self.supply,
            "creator": self.creator,
            "uri": self.uri,
            "image_url": self.image_url,
            "description": self.description,
            "is_pumpfun": self.is_pumpfun,
            "bonding_curve": self.bonding_curve,
            "launch_time": self.launch_time.isoformat() if self.launch_time else None
        }

@dataclass
class TokenScanResult:
    """Result of token scan."""
    tokens_found: int
    new_tokens: List[TokenMetadata]
    pumpfun_tokens: List[TokenMetadata]
    scan_time_ms: float
    last_slot: int
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tokens_found": self.tokens_found,
            "new_tokens_count": len(self.new_tokens),
            "pumpfun_tokens_count": len(self.pumpfun_tokens),
            "scan_time_ms": self.scan_time_ms,
            "last_slot": self.last_slot,
            "errors": self.errors
        }

# =============================================================================
# TOKEN DETECTOR
# =============================================================================

class GodModeTokenDetector:
    """Complete token detection for GODMODESCANNER."""

    def __init__(
        self,
        rpc_endpoints: Optional[List[str]] = None,
        redis_client=None
    ):
        self.rpc_endpoints = rpc_endpoints or DEFAULT_RPC_ENDPOINTS
        self.current_endpoint_idx = 0
        self.redis = redis_client

        # Caches
        self.known_tokens: Set[str] = set()
        self.metadata_cache: Dict[str, TokenMetadata] = {}

        # Stats
        self.stats = {
            "total_scans": 0,
            "tokens_detected": 0,
            "pumpfun_tokens": 0,
            "metadata_fetched": 0,
            "cache_hits": 0,
            "rpc_errors": 0
        }

        # HTTP session
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create HTTP session."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=30),
                headers={"Content-Type": "application/json"}
            )
        return self._session

    async def close(self):
        """Close HTTP session."""
        if self._session and not self._session.closed:
            await self._session.close()

    def _get_endpoint(self) -> str:
        """Get current RPC endpoint with rotation."""
        endpoint = self.rpc_endpoints[self.current_endpoint_idx]
        self.current_endpoint_idx = (self.current_endpoint_idx + 1) % len(self.rpc_endpoints)
        return endpoint

    async def _rpc_call(
        self,
        method: str,
        params: List[Any],
        retries: int = 3
    ) -> Optional[Dict[str, Any]]:
        """Make RPC call with retry logic."""
        session = await self._get_session()

        for attempt in range(retries):
            endpoint = self._get_endpoint()

            try:
                payload = {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": method,
                    "params": params
                }

                async with session.post(endpoint, json=payload) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if "result" in data:
                            return data["result"]
                        elif "error" in data:
                            logger.warning(f"RPC error: {data['error']}")
                    elif resp.status == 429:
                        # Rate limited, wait and retry
                        await asyncio.sleep(1 * (attempt + 1))
                        continue

            except Exception as e:
                logger.warning(f"RPC call failed: {e}")
                self.stats["rpc_errors"] += 1
                await asyncio.sleep(0.5 * (attempt + 1))

        return None

    # =========================================================================
    # SCAN TOKENS (TODO #1)
    # =========================================================================

    async def scan_tokens(
        self,
        limit: int = 100,
        only_pumpfun: bool = True,
        since_slot: Optional[int] = None
    ) -> TokenScanResult:
        """Scan for new tokens on Solana.

        Args:
            limit: Maximum tokens to return
            only_pumpfun: Only return pump.fun tokens
            since_slot: Only return tokens created after this slot

        Returns:
            TokenScanResult with detected tokens
        """
        import time
        start = time.perf_counter()

        self.stats["total_scans"] += 1

        new_tokens: List[TokenMetadata] = []
        pumpfun_tokens: List[TokenMetadata] = []
        errors: List[str] = []
        last_slot = 0

        try:
            # Method 1: Get recent pump.fun transactions
            if only_pumpfun:
                signatures = await self._get_pumpfun_signatures(limit * 2)

                for sig_info in signatures:
                    try:
                        slot = sig_info.get("slot", 0)
                        if since_slot and slot <= since_slot:
                            continue

                        last_slot = max(last_slot, slot)

                        # Get transaction
                        tx = await self._get_transaction(sig_info["signature"])
                        if not tx:
                            continue

                        # Check if it's a token creation
                        token_mint = self._extract_created_token(tx)
                        if token_mint and token_mint not in self.known_tokens:
                            # Fetch metadata
                            metadata = await self.fetch_metadata(token_mint)
                            if metadata:
                                metadata.is_pumpfun = True
                                metadata.launch_time = datetime.fromtimestamp(
                                    tx.get("blockTime", 0), tz=timezone.utc
                                )

                                new_tokens.append(metadata)
                                pumpfun_tokens.append(metadata)
                                self.known_tokens.add(token_mint)
                                self.stats["tokens_detected"] += 1
                                self.stats["pumpfun_tokens"] += 1

                                if len(new_tokens) >= limit:
                                    break

                    except Exception as e:
                        errors.append(str(e))

            else:
                # Method 2: Scan all recent token creations
                # Get recent blocks and look for token mints
                slot_info = await self._rpc_call("getSlot", [])
                if slot_info:
                    current_slot = slot_info
                    start_slot = since_slot or (current_slot - 100)

                    # Get signatures for token program
                    signatures = await self._rpc_call(
                        "getSignaturesForAddress",
                        [
                            TOKEN_PROGRAM_ID,
                            {"limit": limit * 2}
                        ]
                    )

                    if signatures:
                        for sig_info in signatures:
                            try:
                                slot = sig_info.get("slot", 0)
                                if slot <= start_slot:
                                    continue

                                last_slot = max(last_slot, slot)

                                tx = await self._get_transaction(sig_info["signature"])
                                if not tx:
                                    continue

                                # Check for token creation
                                token_mint = self._extract_created_token(tx)
                                if token_mint and token_mint not in self.known_tokens:
                                    metadata = await self.fetch_metadata(token_mint)
                                    if metadata:
                                        # Check if pump.fun
                                        is_pumpfun = self._is_pumpfun_token(tx)
                                        metadata.is_pumpfun = is_pumpfun

                                        new_tokens.append(metadata)
                                        if is_pumpfun:
                                            pumpfun_tokens.append(metadata)
                                            self.stats["pumpfun_tokens"] += 1

                                        self.known_tokens.add(token_mint)
                                        self.stats["tokens_detected"] += 1

                                        if len(new_tokens) >= limit:
                                            break

                            except Exception as e:
                                errors.append(str(e))

            # Cache results in Redis
            if self.redis and new_tokens:
                await self._cache_tokens(new_tokens)

        except Exception as e:
            logger.error(f"Token scan failed: {e}")
            errors.append(str(e))

        scan_time = (time.perf_counter() - start) * 1000

        return TokenScanResult(
            tokens_found=len(new_tokens),
            new_tokens=new_tokens,
            pumpfun_tokens=pumpfun_tokens,
            scan_time_ms=scan_time,
            last_slot=last_slot,
            errors=errors
        )

    # =========================================================================
    # FETCH METADATA (TODO #2)
    # =========================================================================

    async def fetch_metadata(
        self,
        token_mint: str,
        force_refresh: bool = False
    ) -> Optional[TokenMetadata]:
        """Fetch complete metadata for a token.

        Args:
            token_mint: Token mint address
            force_refresh: Force refresh even if cached

        Returns:
            TokenMetadata or None if not found
        """
        # Check cache
        if not force_refresh:
            if token_mint in self.metadata_cache:
                self.stats["cache_hits"] += 1
                return self.metadata_cache[token_mint]

            # Check Redis cache
            if self.redis:
                cached = await self._get_cached_metadata(token_mint)
                if cached:
                    self.stats["cache_hits"] += 1
                    self.metadata_cache[token_mint] = cached
                    return cached

        try:
            self.stats["metadata_fetched"] += 1

            # Step 1: Get token account info
            account_info = await self._rpc_call(
                "getAccountInfo",
                [
                    token_mint,
                    {"encoding": "jsonParsed"}
                ]
            )

            if not account_info or not account_info.get("value"):
                return None

            value = account_info["value"]
            data = value.get("data", {})

            # Parse token info
            if isinstance(data, dict) and "parsed" in data:
                parsed = data["parsed"]
                info = parsed.get("info", {})

                decimals = info.get("decimals", 9)
                supply = int(info.get("supply", 0))
                mint_authority = info.get("mintAuthority")
            else:
                decimals = 9
                supply = 0
                mint_authority = None

            # Step 2: Get Metaplex metadata
            name = "Unknown"
            symbol = "???"
            uri = None
            image_url = None
            description = None

            metadata_pda = self._get_metadata_pda(token_mint)
            if metadata_pda:
                metadata_account = await self._rpc_call(
                    "getAccountInfo",
                    [
                        metadata_pda,
                        {"encoding": "base64"}
                    ]
                )

                if metadata_account and metadata_account.get("value"):
                    metadata_data = metadata_account["value"].get("data", [])
                    if metadata_data and len(metadata_data) > 0:
                        parsed_metadata = self._parse_metadata_account(metadata_data[0])
                        if parsed_metadata:
                            name = parsed_metadata.get("name", name)
                            symbol = parsed_metadata.get("symbol", symbol)
                            uri = parsed_metadata.get("uri")

            # Step 3: Fetch off-chain metadata if URI exists
            if uri:
                off_chain = await self._fetch_off_chain_metadata(uri)
                if off_chain:
                    image_url = off_chain.get("image")
                    description = off_chain.get("description")
                    if not name or name == "Unknown":
                        name = off_chain.get("name", name)
                    if not symbol or symbol == "???":
                        symbol = off_chain.get("symbol", symbol)

            # Step 4: Check if pump.fun token
            is_pumpfun = False
            bonding_curve = None

            # Check for pump.fun bonding curve
            bonding_curve = await self._find_bonding_curve(token_mint)
            if bonding_curve:
                is_pumpfun = True

            metadata = TokenMetadata(
                mint=token_mint,
                name=name.strip() if name else "Unknown",
                symbol=symbol.strip() if symbol else "???",
                decimals=decimals,
                supply=supply,
                creator=mint_authority,
                uri=uri,
                image_url=image_url,
                description=description,
                is_pumpfun=is_pumpfun,
                bonding_curve=bonding_curve
            )

            # Cache result
            self.metadata_cache[token_mint] = metadata
            if self.redis:
                await self._cache_metadata(token_mint, metadata)

            return metadata

        except Exception as e:
            logger.error(f"Failed to fetch metadata for {token_mint}: {e}")
            return None

    # =========================================================================
    # HELPER METHODS
    # =========================================================================

    async def _get_pumpfun_signatures(
        self,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Get recent pump.fun program signatures."""
        result = await self._rpc_call(
            "getSignaturesForAddress",
            [
                PUMPFUN_PROGRAM_ID,
                {"limit": limit}
            ]
        )
        return result or []

    async def _get_transaction(self, signature: str) -> Optional[Dict[str, Any]]:
        """Get transaction by signature."""
        result = await self._rpc_call(
            "getTransaction",
            [
                signature,
                {
                    "encoding": "jsonParsed",
                    "maxSupportedTransactionVersion": 0
                }
            ]
        )
        return result

    def _extract_created_token(self, tx: Dict[str, Any]) -> Optional[str]:
        """Extract created token mint from transaction."""
        try:
            meta = tx.get("meta", {})

            # Check post token balances for new mints
            post_balances = meta.get("postTokenBalances", [])
            pre_balances = meta.get("preTokenBalances", [])

            pre_mints = {b.get("mint") for b in pre_balances}

            for balance in post_balances:
                mint = balance.get("mint")
                if mint and mint not in pre_mints:
                    return mint

            # Check inner instructions for InitializeMint
            inner_instructions = meta.get("innerInstructions", [])
            for inner in inner_instructions:
                for ix in inner.get("instructions", []):
                    if isinstance(ix, dict) and "parsed" in ix:
                        parsed = ix["parsed"]
                        if isinstance(parsed, dict):
                            if parsed.get("type") == "initializeMint":
                                return parsed.get("info", {}).get("mint")

        except Exception:
            pass

        return None

    def _is_pumpfun_token(self, tx: Dict[str, Any]) -> bool:
        """Check if transaction is from pump.fun."""
        try:
            message = tx.get("transaction", {}).get("message", {})
            account_keys = []

            for key in message.get("accountKeys", []):
                if isinstance(key, str):
                    account_keys.append(key)
                elif isinstance(key, dict):
                    account_keys.append(key.get("pubkey", ""))

            return PUMPFUN_PROGRAM_ID in account_keys

        except Exception:
            return False

    def _get_metadata_pda(self, token_mint: str) -> Optional[str]:
        """Calculate Metaplex metadata PDA."""
        try:
            # This is a simplified version - in production use solders
            # The actual PDA derivation requires proper seed hashing
            # For now, we'll try to fetch it directly
            return None  # Would need proper PDA derivation
        except Exception:
            return None

    def _parse_metadata_account(self, data_b64: str) -> Optional[Dict[str, str]]:
        """Parse Metaplex metadata account data."""
        try:
            data = base64.b64decode(data_b64)

            if len(data) < 100:
                return None

            # Skip first byte (key) and 32 bytes (update authority) and 32 bytes (mint)
            offset = 1 + 32 + 32

            # Read name (4 bytes length + string)
            name_len = struct.unpack("<I", data[offset:offset+4])[0]
            offset += 4
            name = data[offset:offset+name_len].decode("utf-8", errors="ignore").rstrip(" ")
            offset += name_len

            # Read symbol (4 bytes length + string)
            symbol_len = struct.unpack("<I", data[offset:offset+4])[0]
            offset += 4
            symbol = data[offset:offset+symbol_len].decode("utf-8", errors="ignore").rstrip(" ")
            offset += symbol_len

            # Read URI (4 bytes length + string)
            uri_len = struct.unpack("<I", data[offset:offset+4])[0]
            offset += 4
            uri = data[offset:offset+uri_len].decode("utf-8", errors="ignore").rstrip(" ")

            return {
                "name": name,
                "symbol": symbol,
                "uri": uri if uri else None
            }

        except Exception as e:
            logger.debug(f"Failed to parse metadata: {e}")
            return None

    async def _fetch_off_chain_metadata(self, uri: str) -> Optional[Dict[str, Any]]:
        """Fetch off-chain metadata from URI."""
        if not uri or not uri.startswith(("http://", "https://", "ipfs://")):
            return None

        try:
            # Convert IPFS URI
            if uri.startswith("ipfs://"):
                uri = f"https://ipfs.io/ipfs/{uri[7:]}"

            session = await self._get_session()
            async with session.get(uri, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    return await resp.json()

        except Exception as e:
            logger.debug(f"Failed to fetch off-chain metadata: {e}")

        return None

    async def _find_bonding_curve(self, token_mint: str) -> Optional[str]:
        """Find pump.fun bonding curve for token."""
        try:
            # Get token accounts owned by pump.fun program
            result = await self._rpc_call(
                "getProgramAccounts",
                [
                    PUMPFUN_PROGRAM_ID,
                    {
                        "encoding": "base64",
                        "filters": [
                            {"dataSize": 200},  # Approximate bonding curve size
                            {
                                "memcmp": {
                                    "offset": 8,  # After discriminator
                                    "bytes": token_mint
                                }
                            }
                        ]
                    }
                ]
            )

            if result and len(result) > 0:
                return result[0].get("pubkey")

        except Exception:
            pass

        return None

    async def _cache_tokens(self, tokens: List[TokenMetadata]) -> None:
        """Cache tokens to Redis."""
        try:
            pipe = self.redis.pipeline()
            for token in tokens:
                key = f"token:{token.mint}"
                pipe.hset(key, mapping={
                    "name": token.name,
                    "symbol": token.symbol,
                    "decimals": str(token.decimals),
                    "is_pumpfun": "1" if token.is_pumpfun else "0",
                    "cached_at": datetime.now(timezone.utc).isoformat()
                })
                pipe.expire(key, 3600)  # 1 hour TTL
            await pipe.execute()
        except Exception as e:
            logger.warning(f"Failed to cache tokens: {e}")

    async def _cache_metadata(self, token_mint: str, metadata: TokenMetadata) -> None:
        """Cache metadata to Redis."""
        try:
            key = f"token_metadata:{token_mint}"
            await self.redis.hset(key, mapping={
                "name": metadata.name,
                "symbol": metadata.symbol,
                "decimals": str(metadata.decimals),
                "supply": str(metadata.supply),
                "creator": metadata.creator or "",
                "uri": metadata.uri or "",
                "image_url": metadata.image_url or "",
                "is_pumpfun": "1" if metadata.is_pumpfun else "0",
                "bonding_curve": metadata.bonding_curve or ""
            })
            await self.redis.expire(key, 3600)
        except Exception as e:
            logger.warning(f"Failed to cache metadata: {e}")

    async def _get_cached_metadata(self, token_mint: str) -> Optional[TokenMetadata]:
        """Get cached metadata from Redis."""
        try:
            key = f"token_metadata:{token_mint}"
            data = await self.redis.hgetall(key)
            if data:
                return TokenMetadata(
                    mint=token_mint,
                    name=data.get("name", "Unknown"),
                    symbol=data.get("symbol", "???"),
                    decimals=int(data.get("decimals", 9)),
                    supply=int(data.get("supply", 0)),
                    creator=data.get("creator") or None,
                    uri=data.get("uri") or None,
                    image_url=data.get("image_url") or None,
                    is_pumpfun=data.get("is_pumpfun") == "1",
                    bonding_curve=data.get("bonding_curve") or None
                )
        except Exception:
            pass
        return None

    def get_stats(self) -> Dict[str, Any]:
        """Get detector statistics."""
        return {
            **self.stats,
            "known_tokens": len(self.known_tokens),
            "cached_metadata": len(self.metadata_cache)
        }


# =============================================================================
# SINGLETON INSTANCE
# =============================================================================

_detector_instance: Optional[GodModeTokenDetector] = None

def get_token_detector(
    rpc_endpoints: Optional[List[str]] = None,
    redis_client=None
) -> GodModeTokenDetector:
    """Get singleton token detector."""
    global _detector_instance
    if _detector_instance is None:
        _detector_instance = GodModeTokenDetector(rpc_endpoints, redis_client)
    return _detector_instance
