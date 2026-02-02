"""
Database Configuration for GODMODESCANNER

TimescaleDB connection pool and utilities
"""

import asyncpg
import structlog
from typing import Optional

logger = structlog.get_logger()

# TimescaleDB connection pool
_timescaledb_pool: Optional[asyncpg.Pool] = None

async def get_timescaledb_pool() -> asyncpg.Pool:
    """Get or create TimescaleDB connection pool"""
    global _timescaledb_pool
    
    if _timescaledb_pool is None:
        try:
            # Use peer authentication via postgres user
            _timescaledb_pool = await asyncpg.create_pool(
                host='127.0.0.1',
                port=5432,
                database='godmodescanner',
                user='postgres',  # Using postgres user with peer auth
                password='',      # Empty for peer/trust auth
                min_size=2,
                max_size=10,
                command_timeout=60
            )
            logger.info("TimescaleDB pool created successfully")
        except Exception as e:
            logger.error(f"TimescaleDB connection failed: {e}")
            raise
    
    return _timescaledb_pool

async def test_timescaledb_connection() -> bool:
    """Test TimescaleDB connectivity"""
    try:
        pool = await get_timescaledb_pool()
        async with pool.acquire() as conn:
            version = await conn.fetchval('SELECT version()')
            logger.info(f"TimescaleDB connected: {version[:50]}...")
            return True
    except Exception as e:
        logger.error(f"TimescaleDB test failed: {e}")
        return False

async def get_table_count() -> int:
    """Get number of tables in database"""
    pool = await get_timescaledb_pool()
    async with pool.acquire() as conn:
        result = await conn.fetchval("""
            SELECT COUNT(*) 
            FROM information_schema.tables 
            WHERE table_schema = 'public'
        """)
        return result

async def get_hypertable_count() -> int:
    """Get number of TimescaleDB hypertables"""
    pool = await get_timescaledb_pool()
    async with pool.acquire() as conn:
        result = await conn.fetchval("""
            SELECT COUNT(*) 
            FROM timescaledb_information.hypertables
        """)
        return result
