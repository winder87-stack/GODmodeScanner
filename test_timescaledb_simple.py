import asyncio
import sys
sys.path.insert(0, '.')

from config.database import get_timescaledb_pool, test_timescaledb_connection

async def test():
    print("=" * 60)
    print("TIMESCALEDB CONNECTION TEST - FINAL")
    print("=" * 60)
    
    # Test connection
    print("\n1. Testing connection...")
    connected = await test_timescaledb_connection()
    
    if connected:
        print("✅ TimescaleDB connected successfully")
        
        # Get table count
        print("\n2. Checking tables...")
        pool = await get_timescaledb_pool()
        async with pool.acquire() as conn:
            tables = await conn.fetch("""
                SELECT table_name FROM information_schema.tables 
                WHERE table_schema = 'public' ORDER BY table_name
            """)
            print(f"✅ Found {len(tables)} tables:")
            for t in tables:
                print(f"   - {t['table_name']}")
            
            # Check hypertables
            print("\n3. Checking hypertables...")
            hypertables = await conn.fetch("""
                SELECT hypertable_name FROM timescaledb_information.hypertables
            """)
            print(f"✅ Found {len(hypertables)} hypertables:")
            for h in hypertables:
                print(f"   - {h['hypertable_name']}")
            
            # Simple test query
            print("\n4. Testing query execution...")
            result = await conn.fetchval("SELECT COUNT(*) FROM wallet_profiles")
            print(f"✅ Query successful: {result} rows in wallet_profiles")
        
        print("\n" + "=" * 60)
        print("TIMESCALEDB IS ONLINE ✅")
        print("=" * 60)
        print(f"\nStatus: OPERATIONAL")
        print(f"Database: godmodescanner")
        print(f"Host: 127.0.0.1:5432")
        print(f"Tables: {len(tables)}")
        print(f"Hypertables: {len(hypertables)}")
        print(f"Extension: timescaledb 2.24.0")
        return True
    else:
        print("\n❌ TimescaleDB connection failed")
        return False

if __name__ == "__main__":
    success = asyncio.run(test())
    sys.exit(0 if success else 1)
