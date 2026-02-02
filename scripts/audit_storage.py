#!/usr/bin/env python3
"""
Storage Audit - Diagnose memory mapping and persistence issues.
Run inside Docker container to verify storage configuration.
"""

import os
import json
from pathlib import Path
from datetime import datetime

def audit_storage():
    print("=" * 60)
    print("🔍 GODMODESCANNER STORAGE AUDIT")
    print(f"   Timestamp: {datetime.utcnow().isoformat()}")
    print("=" * 60)

    results = {
        'timestamp': datetime.utcnow().isoformat(),
        'issues': [],
        'warnings': [],
        'ok': []
    }

    # === 1. Check expected storage directories ===
    print("\n📁 CHECKING STORAGE DIRECTORIES")
    print("-" * 40)

    expected_dirs = [
        '/data',
        '/data/memory',
        '/data/memory/patterns',
        '/data/memory/insights',
        '/data/memory/wallets',
        '/data/memory/rules',
        '/data/redis',
        '/data/graph_data',
        '/data/models',
        '/data/knowledge',
        '/a0/usr/projects/godmodescanner/projects/godmodescanner/data',
        '/a0/usr/projects/godmodescanner/projects/godmodescanner/data/memory'
    ]

    for dir_path in expected_dirs:
        path = Path(dir_path)
        if path.exists():
            # Check if writable
            test_file = path / '.write_test'
            try:
                test_file.write_text('test')
                test_file.unlink()
                writable = True
            except:
                writable = False

            # Count files
            file_count = len(list(path.glob('*'))) if path.is_dir() else 0

            status = "✅" if writable else "⚠️ READ-ONLY"
            print(f"  {status} {dir_path}")
            print(f"      Files: {file_count}, Writable: {writable}")

            if writable:
                results['ok'].append(f"{dir_path} exists and writable")
            else:
                results['warnings'].append(f"{dir_path} is read-only")
        else:
            print(f"  ❌ {dir_path} - MISSING")
            results['issues'].append(f"{dir_path} does not exist")

    # === 2. Check Docker volume mounts ===
    print("\n🐳 CHECKING DOCKER MOUNTS")
    print("-" * 40)

    try:
        with open('/proc/mounts', 'r') as f:
            mounts = f.read()

        data_mounts = [line for line in mounts.split('\n') if '/data' in line or 'godmodescanner' in line]

        if data_mounts:
            print("  Found mounts:")
            for mount in data_mounts[:10]:
                print(f"    {mount[:100]}")
                results['ok'].append(f"Mount found")
        else:
            print("  ⚠️ No /data mounts found - data may not persist!")
            results['issues'].append("No /data volume mounts detected")
    except Exception as e:
        print(f"  ❌ Could not read mounts: {e}")
        results['warnings'].append(f"Could not read /proc/mounts: {e}")

    # === 3. Check Redis persistence ===
    print("\n🔴 CHECKING REDIS PERSISTENCE")
    print("-" * 40)

    redis_paths = [
        '/data/redis/dump.rdb',
        '/data/redis/appendonly.aof',
        '/var/lib/redis/dump.rdb',
        '/a0/usr/projects/godmodescanner/projects/godmodescanner/data/redis/dump.rdb',
        '/a0/usr/projects/godmodescanner/projects/godmodescanner/dump.rdb',
        '/a0/usr/projects/godmodescanner/projects/godmodescanner/appendonlydir'
    ]

    redis_found = False
    for rdb_path in redis_paths:
        path = Path(rdb_path)
        if path.exists():
            if path.is_file():
                size_mb = path.stat().st_size / 1024 / 1024
                mtime = datetime.fromtimestamp(path.stat().st_mtime)
                print(f"  ✅ {rdb_path}")
                print(f"      Size: {size_mb:.2f} MB, Modified: {mtime}")
            else:
                file_count = len(list(path.glob('*')))
                print(f"  ✅ {rdb_path} (directory with {file_count} files)")
            redis_found = True
            results['ok'].append(f"Redis persistence at {rdb_path}")

    if not redis_found:
        print("  ⚠️ No Redis persistence files found!")
        results['warnings'].append("No Redis RDB/AOF files found")

    # === 4. Check environment variables ===
    print("\n🔧 CHECKING ENVIRONMENT VARIABLES")
    print("-" * 40)

    env_vars = [
        'MEMORY_STORAGE_PATH',
        'REDIS_DATA_DIR',
        'DATA_DIR',
        'PERSISTENT_STORAGE_PATH',
        'TIMESCALEDB_HOST',
        'REDIS_HOST'
    ]

    for var in env_vars:
        value = os.getenv(var)
        if value:
            print(f"  ✅ {var} = {value}")
            results['ok'].append(f"{var} is set")
        else:
            print(f"  ⚠️ {var} = (not set)")
            results['warnings'].append(f"{var} not set")

    # === 5. Check memory files ===
    print("\n🧠 CHECKING MEMORY FILES")
    print("-" * 40)

    memory_dirs = [
        '/data/memory',
        '/a0/usr/projects/godmodescanner/projects/godmodescanner/data/memory'
    ]

    total_memories = 0
    for mem_dir in memory_dirs:
        path = Path(mem_dir)
        if path.exists():
            files = list(path.rglob('*.json*'))
            total_memories += len(files)
            print(f"  📂 {mem_dir}: {len(files)} memory files")

            if files:
                recent = sorted(files, key=lambda f: f.stat().st_mtime, reverse=True)[:3]
                for f in recent:
                    print(f"      - {f.name} ({f.stat().st_size} bytes)")

    if total_memories == 0:
        print("  ⚠️ No memory files found (may be fresh install)")
        results['warnings'].append("No persisted memories found")
    else:
        results['ok'].append(f"Found {total_memories} memory files")

    # === 6. Summary ===
    print("\n" + "=" * 60)
    print("📊 AUDIT SUMMARY")
    print("=" * 60)
    print(f"  ✅ OK: {len(results['ok'])}")
    print(f"  ⚠️ Warnings: {len(results['warnings'])}")
    print(f"  ❌ Issues: {len(results['issues'])}")

    if results['issues']:
        print("\n🚨 CRITICAL ISSUES TO FIX:")
        for issue in results['issues']:
            print(f"  - {issue}")

    if results['warnings']:
        print("\n⚠️ WARNINGS:")
        for warning in results['warnings']:
            print(f"  - {warning}")

    # Save report
    report_path = Path('/tmp/storage_audit_report.json')
    with open(report_path, 'w') as f:
        json.dump(results, f, indent=2)
    print(f"\n📄 Full report saved to: {report_path}")

    return results

if __name__ == "__main__":
    audit_storage()
