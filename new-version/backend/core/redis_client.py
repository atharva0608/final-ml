import os
import redis
from backend.core.config import settings

def get_redis_client():
    """
    Get a Redis client connection
    """
    return redis.from_url(
        os.getenv("REDIS_URL", "redis://redis:6379/0"),
        decode_responses=True
    )
