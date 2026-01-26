#!/usr/bin/env python3
"""TimescaleDB Setup Script for GODMODESCANNER

Supports two modes:
1. Direct connection to existing PostgreSQL/TimescaleDB
2. Generate credentials and manual setup instructions
"""

import os
import sys
import secrets
import string

def generate_secure_password(length=32):
    """Generate a secure random password"""
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))

def check_postgresql_available():
    """Check if PostgreSQL is directly accessible"""
    try:
        import psycopg2
        # Try common connection methods
        conn_params = [
            {'host': 'localhost', 'port': 5432, 'user': 'postgres', 'password': 'postgres', 'database': 'postgres'},
            {'host': 'localhost', 'port': 5432, 'user': 'postgres', 'password': '', 'database': 'postgres'},
            {'host': '127.0.0.1', 'port': 5432, 'user': 'postgres', 'password': 'postgres', 'database': 'postgres'},
        ]
        
        for params in conn_params:
            try:
                conn = psycopg2.connect(**params)
                conn.close()
                return True, params
            except Exception:
                continue
        return False, None
    except ImportError:
        return False, None

def setup_database_direct(pg_params, db_name, db_user, db_pass):
    """Setup database with direct PostgreSQL access"""
    import psycopg2
    
    print(f"🔧 Setting up TimescaleDB for GODMODESCANNER...")
    
    # Connect to postgres database
    conn = psycopg2.connect(**pg_params)
    conn.autocommit = True
    cursor = conn.cursor()
    
    # Drop existing objects
    cursor.execute(f"DROP DATABASE IF EXISTS {db_name};")
    cursor.execute(f"DROP USER IF EXISTS {db_user};")
    
    # Create user
    cursor.execute(f"CREATE USER {db_user} WITH PASSWORD '{db_pass}';")
    print(f"  ✓ User '{db_user}' created")
    
    # Create database
    cursor.execute(f"CREATE DATABASE {db_name} OWNER {db_user};")
    print(f"  ✓ Database '{db_name}' created")
    
    # Connect to the new database
    conn.close()
    conn = psycopg2.connect(**{**pg_params, 'database': db_name})
    conn.autocommit = True
    cursor = conn.cursor()
    
    # Enable TimescaleDB
    cursor.execute("CREATE EXTENSION IF NOT EXISTS timescaledb;")
    print(f"  ✓ TimescaleDB extension enabled")
    
    # Grant permissions
    cursor.execute("GRANT ALL ON SCHEMA public TO {};".format(db_user))
    cursor.execute("ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO {};".format(db_user))
    cursor.execute("ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO {};".format(db_user))
    print(f"  ✓ Permissions configured")
    
    cursor.close()
    conn.close()
    
    return True

def generate_manual_setup_sql(db_name, db_user, db_pass):
    """Generate SQL for manual database setup"""
    return f"""
-- TimescaleDB Setup SQL for GODMODESCANNER
-- Run this as a PostgreSQL superuser (e.g., postgres)

-- Create user
DROP DATABASE IF EXISTS {db_name};
DROP USER IF EXISTS {db_user};
CREATE USER {db_user} WITH PASSWORD '{db_pass}';

-- Create database
CREATE DATABASE {db_name} OWNER {db_user};
\c {db_name}

-- Enable TimescaleDB
CREATE EXTENSION IF NOT EXISTS timescaledb;

-- Grant permissions
GRANT ALL ON SCHEMA public TO {db_user};
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO {db_user};
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO {db_user};
"""

def main():
    print("=" * 60)
    print("🔧 GODMODESCANNER TimescaleDB Setup")
    print("=" * 60)
    print()
    
    # Configuration
    db_name = "godmodescanner"
    db_user = "godmodescanner"
    
    # Get password from env or generate new one
    db_pass = os.getenv('TIMESCALEDB_PASSWORD', generate_secure_password())
    
    print(f"📊 Configuration:")
    print(f"   Database: {db_name}")
    print(f"   User:     {db_user}")
    print()
    
    # Check if PostgreSQL is directly accessible
    pg_available, pg_params = check_postgresql_available()
    
    if pg_available:
        print("✅ Direct PostgreSQL access detected")
        try:
            setup_database_direct(pg_params, db_name, db_user, db_pass)
            print()
            print("✅ TimescaleDB setup complete!")
        except Exception as e:
            print(f"❌ Direct setup failed: {e}")
            pg_available = False
    
    if not pg_available:
        print("⚠️  PostgreSQL not directly accessible")
        print()
        print("📝 Manual Setup Instructions:")
        print("-" * 40)
        
        # Generate SQL
        sql = generate_manual_setup_sql(db_name, db_user, db_pass)
        print("Run the following SQL as postgres user:")
        print()
        print(sql)
        
        print("-" * 40)
        print()
        print("Then add these lines to your pg_hba.conf for Docker access:")
        print()
        print('host    {}    {}    172.17.0.0/16    scram-sha-256'.format(db_name, db_user))
        print()
        print("And restart PostgreSQL:")
        print("  sudo systemctl restart postgresql")
        print()
    
    # Output credentials
    print("=" * 60)
    print("✅ TimescaleDB Configuration Complete")
    print("=" * 60)
    print()
    print("Add to your .env file:")
    print()
    print(f"TIMESCALEDB_HOST=172.17.0.1")
    print(f"TIMESCALEDB_PORT=5432")
    print(f"TIMESCALEDB_USER={db_user}")
    print(f"TIMESCALEDB_PASSWORD={db_pass}")
    print(f"TIMESCALEDB_DATABASE={db_name}")
    print()
    print("Or set environment variables:")
    print(f"  export TIMESCALEDB_PASSWORD={db_pass}")
    print()
    
    # Save to .env file if possible
    env_file = '/a0/usr/projects/godmodescanner/projects/godmodescanner/.env'
    if os.path.exists(env_file):
        with open(env_file, 'r') as f:
            content = f.read()
        
        # Update or add TimescaleDB settings
        lines = content.split('\n')
        updated_lines = []
        found = False
        
        for line in lines:
            if line.startswith('TIMESCALEDB_'):
                continue
            updated_lines.append(line)
        
        updated_lines.extend([
            f'TIMESCALEDB_HOST=172.17.0.1',
            f'TIMESCALEDB_PORT=5432',
            f'TIMESCALEDB_USER={db_user}',
            f'TIMESCALEDB_PASSWORD={db_pass}',
            f'TIMESCALEDB_DATABASE={db_name}',
        ])
        
        with open(env_file, 'w') as f:
            f.write('\n'.join(updated_lines))
        
        print(f"✅ Updated {env_file}")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
