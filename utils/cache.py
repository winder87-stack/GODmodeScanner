"""Caching system for reducing API calls and improving performance."""

from typing import Dict, Any, Optional
from datetime import datetime, timedelta
import json
import hashlib
from pathlib import Path


class Cache:
    """In-memory and disk-based caching system."""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize cache.

        Args:
            config: Cache configuration
        """
        self.config = config or {
            'cache_dir': '/a0/usr/projects/godmodescanner/data/cache',
            'default_ttl_seconds': 300,
            'max_memory_items': 1000,
            'enable_disk_cache': True
        }

        self.memory_cache: Dict[str, tuple[Any, datetime]] = {}
        self.cache_dir = Path(self.config['cache_dir'])
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        self.hits = 0
        self.misses = 0

    def _generate_key(self, *args, **kwargs) -> str:
        """Generate cache key from arguments.

        Returns:
            Cache key hash
        """
        key_data = json.dumps({'args': args, 'kwargs': kwargs}, sort_keys=True)
        return hashlib.sha256(key_data.encode()).hexdigest()

    def get(self, key: str) -> Optional[Any]:
        """Get value from cache.

        Args:
            key: Cache key

        Returns:
            Cached value or None if not found/expired
        """
        # Check memory cache
        if key in self.memory_cache:
            value, expiry = self.memory_cache[key]
            if datetime.now() < expiry:
                self.hits += 1
                return value
            else:
                del self.memory_cache[key]

        # Check disk cache
        if self.config['enable_disk_cache']:
            cache_file = self.cache_dir / f"{key}.json"
            if cache_file.exists():
                try:
                    data = json.loads(cache_file.read_text())
                    expiry = datetime.fromisoformat(data['expiry'])
                    if datetime.now() < expiry:
                        self.hits += 1
                        return data['value']
                    else:
                        cache_file.unlink()
                except Exception:
                    pass

        self.misses += 1
        return None

    def set(self, key: str, value: Any, ttl_seconds: Optional[int] = None):
        """Set value in cache.

        Args:
            key: Cache key
            value: Value to cache
            ttl_seconds: Time to live in seconds
        """
        ttl = ttl_seconds or self.config['default_ttl_seconds']
        expiry = datetime.now() + timedelta(seconds=ttl)

        # Store in memory cache
        if len(self.memory_cache) < self.config['max_memory_items']:
            self.memory_cache[key] = (value, expiry)

        # Store in disk cache
        if self.config['enable_disk_cache']:
            cache_file = self.cache_dir / f"{key}.json"
            cache_data = {
                'value': value,
                'expiry': expiry.isoformat()
            }
            cache_file.write_text(json.dumps(cache_data))

    def delete(self, key: str):
        """Delete value from cache.

        Args:
            key: Cache key
        """
        if key in self.memory_cache:
            del self.memory_cache[key]

        cache_file = self.cache_dir / f"{key}.json"
        if cache_file.exists():
            cache_file.unlink()

    def clear(self):
        """Clear all cache."""
        self.memory_cache.clear()

        if self.config['enable_disk_cache']:
            for cache_file in self.cache_dir.glob("*.json"):
                cache_file.unlink()

    def get_statistics(self) -> Dict[str, Any]:
        """Get cache statistics.

        Returns:
            Statistics dictionary
        """
        total_requests = self.hits + self.misses
        hit_rate = self.hits / max(total_requests, 1)

        return {
            'hits': self.hits,
            'misses': self.misses,
            'hit_rate': hit_rate,
            'memory_items': len(self.memory_cache),
            'disk_items': len(list(self.cache_dir.glob("*.json")))
        }
