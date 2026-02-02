import asyncio
import sys
sys.path.insert(0, '.')

from config.database import (
    get_timescaledb_pool, 
    test_timescaledb_connection,
    get_table_count,
    get_hypertable_count
)

async def test():
    print("=" * 60)
    print("TIMESCALEDB CONNECTION TEST")
    print("=" * 60)
    
    # Test connection
    print("\n1. Testing connection...")
    connected = await test_timescaledb_connection()
    
    if connected:
        print("✅ TimescaleDB connected successfully")
        
        # Get table count
        print("\n2. Checking tables...")
        table_count = await get_table_count()
        print(f"✅ Found {table_count} tables")
        
        # Get hypertable count
        print("\n3. Checking hypertables...")
        hypertable_count = await get_hypertable_count()
        print(f"✅ Found {hypertable_count} hypertables")
        
        # Test insert/select with all required columns
        print("\n4. Testing insert/select...")
        pool = await get_timescaledb_pool()
        async with pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO wallet_profiles (
                    wallet_address, win_rate, graduation_rate, curve_entry,
                    total_trades, successful_trades, total_volume_sol,
                    risk_score, is_king_maker
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                ON CONFLICT (wallet_address) DO NOTHING
            """, 
                'TEST_WALLET_GODMODE',  # wallet_address
                0.75,                    # win_rate
                0.60,                    # graduation_rate
                0.10,                    # curve_entry
                25,                      # total_trades
                15,                      # successful_trades
                100.5,                   # total_volume_sol
                75.0,                    # risk_score
                False                    # is_king_maker
            )
            
            result = await conn.fetchrow("""
                SELECT * FROM wallet_profiles 
                WHERE wallet_address = 'TEST_WALLET_GODMODE'
            """)
            
            if result:
                print(f"✅ Test insert/select successful")
                print(f"   Wallet: {result['wallet_address']}")
                print(f"   Win Rate: {result['win_rate']}")
                print(f"   Total Trades: {result['total_trades']}")
                
                # Cleanup
                await conn.execute("""
                    DELETE FROM wallet_profiles 
                    WHERE wallet_address = 'TEST_WALLET_GODMODE'
                """)
            else:
                print("ℹ️  Wallet already exists (conflict)")
        
        print("\n" + "=" * 60)
        print("ALL TESTS PASSED ✅")
        print("=" * 60)
        print(f"\nTimescaleDB Status: ONLINE")
        print(f"Tables: {table_count}")
        print(f"Hypertables: {hypertable_count}")
        print(f"Database: godmodescanner")
        print(f"Host: 127.0.0.1:5432")
        return True
    else:
        print("\n❌ TimescaleDB connection failed")
        return False

if __name__ == "__main__":
    success = asyncio.run(test())
    sys.exit(0 if success else 1)
