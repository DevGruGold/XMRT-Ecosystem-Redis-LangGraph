"""
Redis Cache Manager for XMRT-Ecosystem

This module provides intelligent caching capabilities for AI model responses,
decision outcomes, and computational results to enhance system performance.
"""

import json
import logging
import time
from typing import Any, Dict, List, Optional, Union
from datetime import datetime, timedelta
import redis
import asyncio
import aioredis
from dataclasses import dataclass, asdict
from enum import Enum

from ..shared.exceptions import CacheError, ConfigurationError
from ..shared.utils import serialize_data, deserialize_data
from .config.redis_config import RedisConfig


class CacheStrategy(Enum):
    """Cache strategies for different types of data"""
    LRU = "lru"
    LFU = "lfu"
    TTL = "ttl"
    PERSISTENT = "persistent"


@dataclass
class CacheEntry:
    """Represents a cache entry with metadata"""
    key: str
    value: Any
    created_at: datetime
    expires_at: Optional[datetime]
    access_count: int = 0
    last_accessed: Optional[datetime] = None
    strategy: CacheStrategy = CacheStrategy.TTL


class CacheManager:
    """
    Intelligent cache manager for XMRT-Ecosystem
    
    Provides smart caching strategies for AI model responses, decision outcomes,
    and computational results with automatic cleanup and optimization.
    """
    
    def __init__(self, config: RedisConfig):
        self.config = config
        self.redis_client = None
        self.async_redis_client = None
        self.logger = logging.getLogger(__name__)
        
        # Cache statistics
        self.stats = {
            'hits': 0,
            'misses': 0,
            'sets': 0,
            'deletes': 0,
            'evictions': 0
        }
        
        # Cache namespaces for different data types
        self.namespaces = {
            'ai_responses': 'ai:responses:',
            'decisions': 'ai:decisions:',
            'computations': 'compute:',
            'sessions': 'sessions:',
            'metrics': 'metrics:',
            'workflows': 'workflows:'
        }
    
    async def initialize(self):
        """Initialize Redis connections"""
        try:
            # Synchronous client for blocking operations
            self.redis_client = redis.Redis(
                host=self.config.host,
                port=self.config.port,
                db=self.config.database,
                password=self.config.password,
                decode_responses=True,
                socket_timeout=self.config.socket_timeout,
                socket_connect_timeout=self.config.connect_timeout
            )
            
            # Asynchronous client for non-blocking operations
            self.async_redis_client = await aioredis.from_url(
                f"redis://{self.config.host}:{self.config.port}/{self.config.database}",
                password=self.config.password,
                decode_responses=True
            )
            
            # Test connections
            await self.async_redis_client.ping()
            self.redis_client.ping()
            
            self.logger.info("Redis cache manager initialized successfully")
            
        except Exception as e:
            self.logger.error(f"Failed to initialize Redis cache manager: {e}")
            raise ConfigurationError(f"Redis connection failed: {e}")
    
    def _build_key(self, namespace: str, key: str) -> str:
        """Build a namespaced cache key"""
        prefix = self.namespaces.get(namespace, f"{namespace}:")
        return f"{self.config.key_prefix}{prefix}{key}"
    
    async def set(
        self,
        namespace: str,
        key: str,
        value: Any,
        ttl: Optional[int] = None,
        strategy: CacheStrategy = CacheStrategy.TTL
    ) -> bool:
        """
        Set a value in the cache with specified strategy
        
        Args:
            namespace: Cache namespace (ai_responses, decisions, etc.)
            key: Cache key
            value: Value to cache
            ttl: Time to live in seconds
            strategy: Caching strategy to use
            
        Returns:
            True if successful, False otherwise
        """
        try:
            cache_key = self._build_key(namespace, key)
            
            # Create cache entry with metadata
            entry = CacheEntry(
                key=cache_key,
                value=value,
                created_at=datetime.utcnow(),
                expires_at=datetime.utcnow() + timedelta(seconds=ttl) if ttl else None,
                strategy=strategy
            )
            
            # Serialize the data
            serialized_data = serialize_data(asdict(entry))
            
            # Set in Redis with appropriate TTL
            if ttl and strategy != CacheStrategy.PERSISTENT:
                await self.async_redis_client.setex(cache_key, ttl, serialized_data)
            else:
                await self.async_redis_client.set(cache_key, serialized_data)
            
            # Update statistics
            self.stats['sets'] += 1
            
            self.logger.debug(f"Cached {cache_key} with strategy {strategy.value}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to set cache key {key}: {e}")
            raise CacheError(f"Cache set operation failed: {e}")
    
    async def get(self, namespace: str, key: str) -> Optional[Any]:
        """
        Get a value from the cache
        
        Args:
            namespace: Cache namespace
            key: Cache key
            
        Returns:
            Cached value or None if not found
        """
        try:
            cache_key = self._build_key(namespace, key)
            
            # Get from Redis
            serialized_data = await self.async_redis_client.get(cache_key)
            
            if serialized_data is None:
                self.stats['misses'] += 1
                return None
            
            # Deserialize and extract value
            entry_data = deserialize_data(serialized_data)
            entry = CacheEntry(**entry_data)
            
            # Check if expired (for manual TTL management)
            if entry.expires_at and datetime.utcnow() > entry.expires_at:
                await self.delete(namespace, key)
                self.stats['misses'] += 1
                return None
            
            # Update access metadata
            entry.access_count += 1
            entry.last_accessed = datetime.utcnow()
            
            # Update in Redis (for LFU strategy)
            if entry.strategy == CacheStrategy.LFU:
                updated_data = serialize_data(asdict(entry))
                await self.async_redis_client.set(cache_key, updated_data)
            
            self.stats['hits'] += 1
            return entry.value
            
        except Exception as e:
            self.logger.error(f"Failed to get cache key {key}: {e}")
            self.stats['misses'] += 1
            return None
    
    async def delete(self, namespace: str, key: str) -> bool:
        """Delete a key from the cache"""
        try:
            cache_key = self._build_key(namespace, key)
            result = await self.async_redis_client.delete(cache_key)
            
            if result:
                self.stats['deletes'] += 1
                self.logger.debug(f"Deleted cache key {cache_key}")
            
            return bool(result)
            
        except Exception as e:
            self.logger.error(f"Failed to delete cache key {key}: {e}")
            return False
    
    async def exists(self, namespace: str, key: str) -> bool:
        """Check if a key exists in the cache"""
        try:
            cache_key = self._build_key(namespace, key)
            return bool(await self.async_redis_client.exists(cache_key))
        except Exception as e:
            self.logger.error(f"Failed to check existence of cache key {key}: {e}")
            return False
    
    async def clear_namespace(self, namespace: str) -> int:
        """Clear all keys in a namespace"""
        try:
            pattern = self._build_key(namespace, "*")
            keys = await self.async_redis_client.keys(pattern)
            
            if keys:
                deleted = await self.async_redis_client.delete(*keys)
                self.stats['deletes'] += deleted
                self.logger.info(f"Cleared {deleted} keys from namespace {namespace}")
                return deleted
            
            return 0
            
        except Exception as e:
            self.logger.error(f"Failed to clear namespace {namespace}: {e}")
            return 0
    
    async def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        try:
            # Get Redis info
            redis_info = await self.async_redis_client.info()
            
            # Calculate hit rate
            total_requests = self.stats['hits'] + self.stats['misses']
            hit_rate = (self.stats['hits'] / total_requests * 100) if total_requests > 0 else 0
            
            return {
                'cache_stats': self.stats,
                'hit_rate_percent': round(hit_rate, 2),
                'redis_memory_used': redis_info.get('used_memory_human', 'N/A'),
                'redis_connected_clients': redis_info.get('connected_clients', 0),
                'redis_total_commands_processed': redis_info.get('total_commands_processed', 0)
            }
            
        except Exception as e:
            self.logger.error(f"Failed to get cache stats: {e}")
            return self.stats
    
    async def cleanup_expired(self) -> int:
        """Clean up expired cache entries"""
        try:
            cleaned = 0
            
            # Get all keys with our prefix
            pattern = f"{self.config.key_prefix}*"
            keys = await self.async_redis_client.keys(pattern)
            
            for key in keys:
                try:
                    serialized_data = await self.async_redis_client.get(key)
                    if serialized_data:
                        entry_data = deserialize_data(serialized_data)
                        entry = CacheEntry(**entry_data)
                        
                        # Check if expired
                        if entry.expires_at and datetime.utcnow() > entry.expires_at:
                            await self.async_redis_client.delete(key)
                            cleaned += 1
                            
                except Exception as e:
                    self.logger.warning(f"Failed to process key {key} during cleanup: {e}")
                    continue
            
            if cleaned > 0:
                self.stats['evictions'] += cleaned
                self.logger.info(f"Cleaned up {cleaned} expired cache entries")
            
            return cleaned
            
        except Exception as e:
            self.logger.error(f"Failed to cleanup expired entries: {e}")
            return 0
    
    async def close(self):
        """Close Redis connections"""
        try:
            if self.async_redis_client:
                await self.async_redis_client.close()
            if self.redis_client:
                self.redis_client.close()
            
            self.logger.info("Redis cache manager connections closed")
            
        except Exception as e:
            self.logger.error(f"Error closing Redis connections: {e}")


# Convenience functions for common caching operations
async def cache_ai_response(
    cache_manager: CacheManager,
    model: str,
    prompt: str,
    response: str,
    ttl: int = 3600
) -> bool:
    """Cache an AI model response"""
    key = f"{model}:{hash(prompt)}"
    return await cache_manager.set('ai_responses', key, response, ttl)


async def get_cached_ai_response(
    cache_manager: CacheManager,
    model: str,
    prompt: str
) -> Optional[str]:
    """Get a cached AI model response"""
    key = f"{model}:{hash(prompt)}"
    return await cache_manager.get('ai_responses', key)


async def cache_decision(
    cache_manager: CacheManager,
    decision_id: str,
    decision_data: Dict[str, Any],
    ttl: int = 86400
) -> bool:
    """Cache a decision outcome"""
    return await cache_manager.set('decisions', decision_id, decision_data, ttl)


async def get_cached_decision(
    cache_manager: CacheManager,
    decision_id: str
) -> Optional[Dict[str, Any]]:
    """Get a cached decision"""
    return await cache_manager.get('decisions', decision_id)

