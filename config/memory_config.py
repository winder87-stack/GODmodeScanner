"""
Memory Persistence Configuration for GODMODESCANNER
Ensures all memories persist across container restarts
"""

import os
from pathlib import Path

# Base storage paths - these MUST match Docker volume mounts
STORAGE_CONFIG = {
    # Primary persistent storage (mapped to host /home/ink/godmodescanner/data/)
    'MEMORY_PATH': '/data/memory',
    'REDIS_PATH': '/data/redis',
    'GRAPH_PATH': '/data/graph_data',
    'MODELS_PATH': '/data/models',
    'KNOWLEDGE_PATH': '/data/knowledge',
    'LOGS_PATH': '/var/log/godmodescanner',

    # Fallback paths (if /data not mounted)
    'FALLBACK_MEMORY_PATH': '/a0/usr/projects/godmodescanner/projects/godmodescanner/data/memory',
    'FALLBACK_REDIS_PATH': '/a0/usr/projects/godmodescanner/projects/godmodescanner/data/redis',
}

def get_storage_path(key: str) -> str:
    """Get storage path with fallback to project directory."""
    primary = STORAGE_CONFIG.get(key)
    fallback_key = f'FALLBACK_{key}'
    fallback = STORAGE_CONFIG.get(fallback_key, primary)

    # Check if primary path exists and is writable
    if primary:
        path = Path(primary)
        if path.exists():
            test_file = path / '.write_test'
            try:
                test_file.write_text('test')
                test_file.unlink()
                return primary
            except:
                pass

    # Return fallback if primary not available
    return fallback if fallback else primary

def ensure_directories():
    """Ensure all storage directories exist."""
    dirs_to_create = [
        get_storage_path('MEMORY_PATH'),
        f"{get_storage_path('MEMORY_PATH')}/patterns",
        f"{get_storage_path('MEMORY_PATH')}/insights",
        f"{get_storage_path('MEMORY_PATH')}/wallets",
        f"{get_storage_path('MEMORY_PATH')}/rules",
        get_storage_path('REDIS_PATH'),
        get_storage_path('GRAPH_PATH'),
        get_storage_path('MODELS_PATH'),
        get_storage_path('KNOWLEDGE_PATH'),
        get_storage_path('LOGS_PATH'),
    ]

    for dir_path in dirs_to_create:
        Path(dir_path).mkdir(parents=True, exist_ok=True)

    return len(dirs_to_create)

# Environment variable overrides (set in docker-compose.yml or .env)
def load_from_env():
    """Load storage paths from environment variables."""
    env_mappings = {
        'MEMORY_STORAGE_PATH': 'MEMORY_PATH',
        'REDIS_DATA_DIR': 'REDIS_PATH',
        'GRAPH_DATA_PATH': 'GRAPH_PATH',
        'MODELS_PATH': 'MODELS_PATH',
        'KNOWLEDGE_PATH': 'KNOWLEDGE_PATH',
        'LOG_PATH': 'LOGS_PATH',
    }

    for env_var, config_key in env_mappings.items():
        value = os.getenv(env_var)
        if value:
            STORAGE_CONFIG[config_key] = value

# Initialize on module load
load_from_env()
