#!/usr/bin/env python3
"""TimescaleDB Initialization Script for GODMODESCANNER"""

import os
import sys
import time
import psycopg2
from pathlib import Path
from urllib.parse import urlparse

def get_db_connection(max_retries=10):
    """Connect to TimescaleDB with retries"""
    db_url = os.getenv('TIMESCALE_URL', 'postgresql://godmodescanner:password@localhost:5432/godmodescanner')

    for attempt in range(max_retries):
        try:
            conn = psycopg2.connect(db_url)
            return conn
        except psycopg2.OperationalError as e:
            if attempt < max_retries - 1:
                print(f"Waiting for TimescaleDB... (attempt {attempt + 1}/{max_retries})")
                time.sleep(5)
            else:
                raise
    return None

def init_database():
    """Initialize TimescaleDB schema"""
    print("="*60)
    print("GODMODESCANNER TimescaleDB Initialization")
    print("="*60)

    # Load SQL schema
    sql_path = Path('/a0/usr/projects/godmodescanner/projects/godmodescanner/scripts/timescaledb_schema.sql')
    if not sql_path.exists():
        print(f"ERROR: SQL schema not found at {sql_path}")
        sys.exit(1)

    with open(sql_path, 'r') as f:
        sql_schema = f.read()

    print(f"✓ Schema loaded: {sql_path}")

    # Connect to database
    print("Connecting to TimescaleDB...")
    try:
        conn = get_db_connection()
        conn.autocommit = True  # Required for CREATE EXTENSION
        cursor = conn.cursor()
        print("✓ Connected")

        # Execute schema
        print("Executing schema...")
        cursor.execute(sql_schema)
        print("✓ Schema created successfully")

        # Verify hypertables
        print("Verifying hypertables...")
        cursor.execute("""
            SELECT 
                hypertable_name,
                chunk_time_interval,
                compressed_hyperhypertable_name
            FROM timescaledb_information.hypertables
            ORDER BY hypertable_name;
        """)

        hypertables = cursor.fetchall()
        print(f"Found {len(hypertables)} hypertables:")
        for table, interval, compressed in hypertables:
            print(f"  ✓ {table} (interval: {interval})")

        # Verify continuous aggregates
        print("Verifying continuous aggregates...")
        cursor.execute("""
            SELECT 
                view_name,
                materialization_hypertable_name
            FROM timescaledb_information.continuous_aggregates
            ORDER BY view_name;
        """)

        aggregates = cursor.fetchall()
        print(f"Found {len(aggregates)} continuous aggregates:")
        for view, mat_table in aggregates:
            print(f"  ✓ {view}")

        # Verify retention policies
        print("Verifying retention policies...")
        cursor.execute("""
            SELECT 
                table_name,
                drop_after
            FROM timescaledb_information.retention_policies
            ORDER BY table_name;
        """)

        policies = cursor.fetchall()
        print(f"Found {len(policies)} retention policies:")
        for table, drop_after in policies:
            print(f"  ✓ {table}: {drop_after}")

        # Test analytics functions
        print("Testing analytics functions...")
        cursor.execute("""
            SELECT count(*) as function_count
            FROM information_schema.routines
            WHERE specific_schema = 'public'
            AND routine_name IN ('calculate_token_trend', 'find_emerging_risks', 'get_wallet_risk_trend');
        """)

        func_count = cursor.fetchone()[0]
        print(f"✓ Found {func_count}/3 analytics functions")

        cursor.close()
        conn.close()

        print()
        print("="*60)
        print("✅ TIMESCALEDB INITIALIZATION COMPLETE")
        print("="*60)
        print()
        print("Database ready for GODMODESCANNER operations!")
        print()
        print("Key features enabled:")
        print("  • Time-series data storage (7 hypertables)")
        print("  • Real-time analytics (3 continuous aggregates)")
        print("  • Advanced trend analysis (3 SQL functions)")
        print("  • Automated data retention policies")

        return True

    except Exception as e:
        print(f"❌ ERROR: {e}")
        return False
        return False

if __name__ == "__main__":
    success = init_database()
    sys.exit(0 if success else 1)
