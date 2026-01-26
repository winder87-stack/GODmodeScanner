"""Database Connection Pool for GODMODESCANNER

Singleton pattern with retry logic, health monitoring, and optimized pool settings.
"""

import os
import asyncio
import logging
import asyncpg
from typing import Optional
from contextlib import asynccontextmanager
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class DatabasePool:
    """Singleton async database connection pool for TimescaleDB.
    
    Features:
    - Singleton pattern with get_instance()
    - Retry logic with exponential backoff (5 attempts)
    - Connection configuration: statement_timeout=30s, lock_timeout=10s
    - Health monitoring task running every 30 seconds
    - Pool settings: min_size=2, max_size=10, max_idle=300, max_lifetime=3600
    """
    
    _instance: Optional['DatabasePool'] = None
    _lock: asyncio.Lock = asyncio.Lock()
    
    def __init__(self):
        self._pool: Optional[asyncpg.Pool] = None
        self._initialized: bool = False
        self._health_task: Optional[asyncio.Task] = None
        self._health_check_interval: int = 30
        self._stop_event: asyncio.Event = asyncio.Event()
        
        # Connection configuration
        self._host: str = os.getenv('TIMESCALEDB_HOST', '172.17.0.1')
        self._port: int = int(os.getenv('TIMESCALEDB_PORT', '5432'))
        self._database: str = os.getenv('TIMESCALEDB_DATABASE', 'godmodescanner')
        self._user: str = os.getenv('TIMESCALEDB_USER', 'godmodescanner')
        self._password: str = os.getenv('TIMESCALEDB_PASSWORD', '')
        
        # Pool settings
        self._min_size: int = 2
        self._max_size: int = 10
        self._max_idle: int = 300  # seconds
        self._max_lifetime: int = 3600  # seconds
        
        # Connection timeouts
        self._statement_timeout: int = 30  # seconds
        self._lock_timeout: int = 10  # seconds
        
        # Health metrics
        self._health_metrics: dict = {
            'last_check': None,
            'status': 'unknown',
            'pool_size': 0,
            'connections_acquired': 0,
            'connections_returned': 0,
            'check_count': 0,
            'error_count': 0,
        }
    
    @classmethod
    async def get_instance(cls) -> 'DatabasePool':
        """Get singleton instance of DatabasePool."""
        if cls._instance is None:
            async with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
                    await cls._instance.initialize()
        return cls._instance
    
    async def initialize(self) -> None:
        """Initialize the connection pool with retry logic."""
        if self._initialized:
            return
            
        if not self._password:
            raise ValueError(
                "TIMESCALEDB_PASSWORD environment variable is required. "
                "Set it before initializing the database pool."
            )
        
        max_retries = 5
        base_delay = 1.0  # seconds
        
        for attempt in range(max_retries):
            try:
                logger.info(
                    f"Initializing database pool (attempt {attempt + 1}/{max_retries})..."
                )
                
                self._pool = await asyncpg.create_pool(
                    host=self._host,
                    port=self._port,
                    database=self._database,
                    user=self._user,
                    password=self._password,
                    min_size=self._min_size,
                    max_size=self._max_size,
                    max_inactive_connection_lifetime=self._max_lifetime,
                    command_timeout=self._statement_timeout,
                )
                
                # Test the connection
                async with self._pool.acquire() as conn:
                    await self._configure_connection(conn)
                    result = await conn.fetchval("SELECT 1")
                    if result != 1:
                        raise ValueError("Database connection test failed")
                
                self._initialized = True
                logger.info("Database pool initialized successfully")
                
                # Start health monitoring
                self._start_health_monitor()
                
                return
                
            except (asyncpg.PostgresError, OSError, asyncio.TimeoutError) as e:
                logger.warning(
                    f"Database connection attempt {attempt + 1} failed: {e}"
                )
                
                if attempt < max_retries - 1:
                    # Exponential backoff
                    delay = base_delay * (2 ** attempt)
                    logger.info(f"Retrying in {delay} seconds...")
                    await asyncio.sleep(delay)
                else:
                    logger.error(
                        f"Failed to initialize database pool after {max_retries} attempts"
                    )
                    raise
    
    async def _configure_connection(self, conn: asyncpg.Connection) -> None:
        """Configure connection with timeouts and row_factory."""
        # Set statement timeout
        await conn.execute(
            f"SET statement_timeout = {self._statement_timeout * 1000};",
        )
        
        # Set lock timeout
        await conn.execute(
            f"SET lock_timeout = {self._lock_timeout * 1000};",
        )
        
        # Set timezone to UTC
        await conn.execute("SET timezone = 'UTC';")
        
        # Enable extended query protocol
        await conn.execute("SET cursor_tuple_fraction = 1.0;")
        
        logger.debug("Connection configured with timeouts")
    
    def _start_health_monitor(self) -> None:
        """Start the background health monitoring task."""
        if self._health_task is not None:
            return
            
        self._health_task = asyncio.create_task(self._health_monitor())
        logger.info(f"Health monitor started (interval: {self._health_check_interval}s)")
    
    async def _health_monitor(self) -> None:
        """Periodic health checks every 30 seconds."""
        while not self._stop_event.is_set():
            try:
                await asyncio.sleep(self._health_check_interval)
                
                if self._pool is None:
                    continue
                    
                # Check pool status
                pool_size = self._pool.get_size()
                idle_count = self._pool.get_idle_size()
                
                # Test connection
                try:
                    async with self._pool.acquire() as conn:
                        result = await conn.fetchval("SELECT 1")
                        if result == 1:
                            self._health_metrics['status'] = 'healthy'
                        else:
                            self._health_metrics['status'] = 'degraded'
                except Exception as e:
                    logger.warning(f"Health check failed: {e}")
                    self._health_metrics['status'] = 'unhealthy'
                    self._health_metrics['error_count'] += 1
                
                # Update metrics
                self._health_metrics['last_check'] = datetime.now(timezone.utc).isoformat()
                self._health_metrics['pool_size'] = pool_size
                self._health_metrics['idle_connections'] = idle_count
                self._health_metrics['check_count'] += 1
                
                logger.debug(
                    f"Health check: status={self._health_metrics['status']}, "
                    f"pool_size={pool_size}, idle={idle_count}"
                )
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Health monitor error: {e}")
                self._health_metrics['error_count'] += 1
        
        logger.info("Health monitor stopped")
    
    async def close(self) -> None:
        """Close all connections and cleanup."""
        logger.info("Closing database pool...")
        
        # Stop health monitor
        self._stop_event.set()
        if self._health_task is not None:
            self._health_task.cancel()
            try:
                await self._health_task
            except asyncio.CancelledError:
                pass
        
        # Close pool
        if self._pool is not None:
            await self._pool.close()
            self._pool = None
            
        self._initialized = False
        
        # Reset singleton
        DatabasePool._instance = None
        
        logger.info("Database pool closed")
    
    @asynccontextmanager
    async def acquire(self):
        """Acquire a connection from the pool."""
        if self._pool is None:
            raise RuntimeError(
                "Database pool not initialized. Call initialize() first."
            )
        
        async with self._pool.acquire() as conn:
            await self._configure_connection(conn)
            self._health_metrics['connections_acquired'] += 1
            try:
                yield conn
            finally:
                self._health_metrics['connections_returned'] += 1
    
    async def fetch(self, query: str, *args) -> list:
        """Execute a SELECT query and return all rows."""
        async with self.acquire() as conn:
            return await conn.fetch(query, *args)
    
    async def fetchrow(self, query: str, *args) -> Optional[asyncpg.Record]:
        """Execute a SELECT query and return one row."""
        async with self.acquire() as conn:
            return await conn.fetchrow(query, *args)
    
    async def fetchval(self, query: str, *args) -> any:
        """Execute a SELECT query and return a single value."""
        async with self.acquire() as conn:
            return await conn.fetchval(query, *args)
    
    async def execute(self, query: str, *args) -> str:
        """Execute an INSERT, UPDATE, or DELETE query."""
        async with self.acquire() as conn:
            return await conn.execute(query, *args)
    
    async def executemany(self, query: str, args_list: list) -> None:
        """Execute a query multiple times with different arguments."""
        async with self.acquire() as conn:
            await conn.executemany(query, args_list)
    
    async def get_health_metrics(self) -> dict:
        """Get current health metrics."""
        if self._pool:
            self._health_metrics['pool_size'] = self._pool.get_size()
            self._health_metrics['idle_connections'] = self._pool.get_idle_size()
        
        return {
            **self._health_metrics,
            'initialized': self._initialized,
            'config': {
                'host': self._host,
                'port': self._port,
                'database': self._database,
                'user': self._user,
                'min_size': self._min_size,
                'max_size': self._max_size,
                'statement_timeout': self._statement_timeout,
                'lock_timeout': self._lock_timeout,
            }
        }
    
    @property
    def is_initialized(self) -> bool:
        """Check if the pool is initialized."""
        return self._initialized
    
    @property
    def pool(self) -> Optional[asyncpg.Pool]:
        """Get the underlying pool (for advanced use)."""
        return self._pool


# Convenience function
async def get_db_pool() -> DatabasePool:
    """Get the database pool singleton instance."""
    return await DatabasePool.get_instance()


# Example usage
if __name__ == "__main__":
    import sys
    
    async def main():
        print("=" * 60)
        print("Testing Database Pool")
        print("=" * 60)
        
        try:
            pool = await DatabasePool.get_instance()
            print(f"Pool initialized: min={pool._min_size}, max={pool._max_size}")
            
            # Test query
            result = await pool.fetchval("SELECT 1")
            print(f"Test query result: {result}")
            
            # Get health metrics
            metrics = await pool.get_health_metrics()
            print(f"Health status: {metrics['status']}")
            
            # Close pool
            await pool.close()
            print("Pool closed")
            
        except Exception as e:
            print(f"Error: {e}")
            sys.exit(1)
    
    asyncio.run(main())
