"""
Redis Client Module - Redis connection and utility functions
"""
import redis
from typing import Optional
import os


def get_redis_client() -> redis.Redis:
    """
    Get Redis client instance
    
    Returns:
        Redis client
    """
    return redis.Redis(
        host=os.getenv("REDIS_HOST", "redis"),
        port=int(os.getenv("REDIS_PORT", "6379")),
        db=int(os.getenv("REDIS_DB", "0")),
        decode_responses=True,
        socket_connect_timeout=5,
        socket_timeout=5,
    )


def get_redis_pool(max_connections: int = 50) -> redis.ConnectionPool:
    """
    Get Redis connection pool
    
    Args:
        max_connections: Maximum connections in pool
        
    Returns:
        Redis connection pool
    """
    return redis.ConnectionPool(
        host=os.getenv("REDIS_HOST", "redis"),
        port=int(os.getenv("REDIS_PORT", "6379")),
        db=int(os.getenv("REDIS_DB", "0")),
        decode_responses=True,
        max_connections=max_connections,
    )
