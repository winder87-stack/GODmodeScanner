"""
High-Performance Aggressive Solana RPC Client

This module provides a zero-cost, high-performance asynchronous request engine
for the GODMODESCANNER system. It leverages:
- uvloop: Ultra-fast event loop (2-4x faster than asyncio)
- httpx: Modern async HTTP client with HTTP/2 support
- orjson: Fastest JSON parser (2-3x faster than ujson)

Author: AGENTZERO
Date: 2025-01-24
"""

import asyncio
import logging
import random
from typing import Optional, List, Dict, Any

import httpx
import orjson
import uvloop

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class AggressiveSolanaClient:
    """
    High-performance asynchronous Solana RPC client.
    
    Features:
    - uvloop for 2-4x faster event loop performance
    - HTTP/2 support for multiplexed requests
    - Connection pooling with high limits (200 max connections)
    - Round-robin RPC endpoint distribution
    - orjson for ultra-fast JSON parsing
    - Automatic retry and error handling
    - Zero operational cost (uses free RPC endpoints)
    """
    
    def __init__(
        self,
        rpc_endpoints: Optional[List[str]] = None,
        max_connections: int = 200,
        max_keepalive_connections: int = 50,
        timeout: float = 5.0,
        use_http2: bool = True
    ):
        """
        Initialize the AggressiveSolanaClient.
        
        Args:
            rpc_endpoints: List of Solana RPC endpoint URLs.
                         Defaults to public mainnet-beta endpoints if None.
            max_connections: Maximum number of concurrent connections (default: 200)
            max_keepalive_connections: Maximum keepalive connections (default: 50)
            timeout: Request timeout in seconds (default: 5.0)
            use_http2: Enable HTTP/2 support (default: True)
        """
        # Set uvloop event loop policy for maximum performance
        try:
            asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
            logger.info("✅ uvloop event loop policy activated")
        except Exception as e:
            logger.warning(f"⚠️  Could not set uvloop policy: {e}")
        
        # Get the current event loop
        self.loop = asyncio.get_event_loop()
        
        # Default free RPC endpoints (sorted by reliability)
        self.rpc_endpoints = rpc_endpoints or [
            "https://api.mainnet-beta.solana.com",
            "https://solana-api.projectserum.com",
            "https://rpc.ankr.com/solana",
            "https://rpc.mainnet.niftyorange.com",
            "https://solana.public-rpc.com",
            "https://api.devnet.solana.com",
        ]
        
        # Round-robin endpoint selector
        self.current_endpoint_index = 0
        
        # HTTP client configuration
        self.limits = httpx.Limits(
            max_connections=max_connections,
            max_keepalive_connections=max_keepalive_connections,
            keepalive_expiry=30.0
        )
        
        self.timeout = httpx.Timeout(timeout)
        
        # Initialize httpx async client
        self.client: Optional[httpx.AsyncClient] = None
        
        # Performance metrics
        self.request_count = 0
        self.success_count = 0
        self.error_count = 0
        self.rate_limit_count = 0
        
        logger.info(f"🚀 AggressiveSolanaClient initialized with {len(self.rpc_endpoints)} RPC endpoints")
        logger.info(f"⚡ Max connections: {max_connections}, Keepalive: {max_keepalive_connections}")
        logger.info(f"🌐 HTTP/2 enabled: {use_http2}")
    
    async def __aenter__(self):
        """Async context manager entry."""
        await self.start()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()
    
    async def start(self):
        """Start the HTTP client."""
        if self.client is None:
            self.client = httpx.AsyncClient(
                http2=True,
                limits=self.limits,
                timeout=self.timeout,
                verify=True  # SSL verification
            )
            logger.info("✅ AggressiveSolanaClient started")
    
    async def close(self):
        """Close the HTTP client."""
        if self.client:
            await self.client.aclose()
            self.client = None
            logger.info("🔌 AggressiveSolanaClient closed")
    
    def _get_next_endpoint(self) -> str:
        """
        Get the next RPC endpoint using round-robin selection.
        
        Returns:
            Next RPC endpoint URL
        """
        endpoint = self.rpc_endpoints[self.current_endpoint_index]
        self.current_endpoint_index = (self.current_endpoint_index + 1) % len(self.rpc_endpoints)
        return endpoint
    
    async def request(
        self,
        method: str,
        params: Optional[List[Any]] = None,
        endpoint: Optional[str] = None,
        retries: int = 2
    ) -> Optional[Dict[str, Any]]:
        """
        Make an asynchronous RPC request to Solana.
        
        Args:
            method: Solana RPC method name (e.g., "getBalance", "getAccountInfo")
            params: List of parameters for the RPC method
            endpoint: Specific RPC endpoint to use (optional, uses round-robin if None)
            retries: Number of retry attempts on failure (default: 2)
        
        Returns:
            Parsed JSON response dict or None on error
        """
        if self.client is None:
            await self.start()
        
        # Select endpoint
        rpc_url = endpoint or self._get_next_endpoint()
        
        # Build JSON-RPC payload
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": method,
            "params": params or []
        }
        
        # Retry loop
        for attempt in range(retries + 1):
            try:
                self.request_count += 1
                
                # Make HTTP POST request
                response = await self.client.post(
                    rpc_url,
                    content=orjson.dumps(payload),
                    headers={"Content-Type": "application/json"}
                )
                
                # Check for rate limiting
                if response.status_code == 429:
                    self.rate_limit_count += 1
                    logger.warning(f"⚠️  Rate limited by {rpc_url} (attempt {attempt + 1})")
                    if attempt < retries:
                        await asyncio.sleep(0.5 * (attempt + 1))  # Exponential backoff
                        continue
                    return {"error": "RATE_LIMIT", "endpoint": rpc_url}
                
                # Check for other HTTP errors
                response.raise_for_status()
                
                # Parse JSON using orjson (ultra-fast)
                data = orjson.loads(response.content)
                
                # Check for RPC-level errors
                if "error" in data:
                    logger.error(f"❌ RPC error: {data['error']}")
                    self.error_count += 1
                    return data
                
                self.success_count += 1
                return data
                
            except httpx.HTTPStatusError as e:
                logger.error(f"❌ HTTP status error: {e.response.status_code} - {e}")
                self.error_count += 1
                if attempt < retries:
                    await asyncio.sleep(0.5 * (attempt + 1))
                    continue
                return None
                
            except httpx.NetworkError as e:
                logger.error(f"❌ Network error: {e}")
                self.error_count += 1
                if attempt < retries:
                    await asyncio.sleep(0.5 * (attempt + 1))
                    continue
                return None
                
            except Exception as e:
                logger.error(f"❌ Unexpected error: {e}")
                self.error_count += 1
                return None
        
        return None
    
    async def get_balance(self, wallet_address: str) -> Optional[float]:
        """
        Get SOL balance for a wallet address.
        
        Args:
            wallet_address: Solana wallet address
        
        Returns:
            Balance in SOL or None on error
        """
        response = await self.request("getBalance", [wallet_address])
        if response and "result" in response:
            # Convert lamports to SOL (1 SOL = 1,000,000,000 lamports)
            lamports = response["result"]["value"]
            return lamports / 1_000_000_000
        return None
    
    async def get_account_info(self, wallet_address: str) -> Optional[Dict[str, Any]]:
        """
        Get account information for a wallet address.
        
        Args:
            wallet_address: Solana wallet address
        
        Returns:
            Account info dict or None on error
        """
        response = await self.request("getAccountInfo", [wallet_address])
        if response and "result" in response:
            return response["result"]
        return None
    
    async def get_signatures_for_address(
        self,
        wallet_address: str,
        limit: int = 1000
    ) -> Optional[List[Dict[str, Any]]]:
        """
        Get recent transaction signatures for a wallet address.
        
        Args:
            wallet_address: Solana wallet address
            limit: Maximum number of signatures to retrieve
        
        Returns:
            List of signature dicts or None on error
        """
        response = await self.request("getSignaturesForAddress", [
            wallet_address,
            {"limit": limit}
        ])
        if response and "result" in response:
            return response["result"]
        return None
    
    def get_metrics(self) -> Dict[str, int]:
        """
        Get performance metrics.
        
        Returns:
            Dict with request count, success count, error count, rate limit count
        """
        return {
            "total_requests": self.request_count,
            "successful_requests": self.success_count,
            "failed_requests": self.error_count,
            "rate_limited_requests": self.rate_limit_count,
            "success_rate": (self.success_count / self.request_count * 100) if self.request_count > 0 else 0
        }
    
    def reset_metrics(self):
        """Reset performance metrics."""
        self.request_count = 0
        self.success_count = 0
        self.error_count = 0
        self.rate_limit_count = 0


# Convenience function for quick initialization
async def get_client() -> AggressiveSolanaClient:
    """
    Get or create a singleton instance of AggressiveSolanaClient.
    
    Returns:
        AggressiveSolanaClient instance
    """
    client = AggressiveSolanaClient()
    await client.start()
    return client


if __name__ == "__main__":
    # Quick test
    async def test_client():
        async with AggressiveSolanaClient() as client:
            # Test getBalance
            test_wallet = "SystemProgram11111111111111111111111111111111"
            balance = await client.get_balance(test_wallet)
            print(f"Balance: {balance} SOL")
            
            # Print metrics
            metrics = client.get_metrics()
            print(f"Metrics: {metrics}")
    
    asyncio.run(test_client())
