"""
AWS API Rate Limiter

Redis-based rate limiter to prevent exceeding AWS API rate limits
when multiple users/workers call AWS APIs concurrently.

Per-account rate limiting with configurable calls-per-second limits.
"""
from redis import Redis
import logging

logger = logging.getLogger(__name__)


class RateLimitExceeded(Exception):
    """Raised when AWS API rate limit is exceeded"""
    pass


class AWSAPIRateLimiter:
    """
    Redis-based rate limiter for AWS API calls, per account.
    
    Uses a sliding window counter with 1-second granularity.
    Each account+API combination has its own rate limit.
    
    Usage:
        limiter = AWSAPIRateLimiter(redis, account_id="123", api_name="DescribeSpotPriceHistory")
        limiter.acquire()  # Raises RateLimitExceeded if over limit
        # ... make AWS API call ...
    """

    # Default rate limits per API (calls per second)
    DEFAULT_LIMITS = {
        "DescribeSpotPriceHistory": 20,
        "RunInstances": 5,  # dry-run counts against limit
        "DescribeInstances": 50,
        "ModifyInstanceAttribute": 5,
        "StopInstances": 5,
        "StartInstances": 5,
        "DescribeAutoScalingInstances": 20,
        "GetProducts": 10,  # Pricing API
    }

    def __init__(
        self,
        redis_client: Redis,
        account_id: str,
        api_name: str,
        calls_per_second: int | None = None
    ):
        self.redis = redis_client
        self.account_id = account_id
        self.api_name = api_name
        self.key = f"aws_rate:{account_id}:{api_name}"
        self.limit = calls_per_second or self.DEFAULT_LIMITS.get(api_name, 10)

    def acquire(self) -> bool:
        """
        Acquire a rate limit token. Raises RateLimitExceeded if over limit.
        
        Returns True if acquired successfully.
        """
        current = self.redis.incr(self.key)
        if current == 1:
            self.redis.expire(self.key, 1)  # 1-second sliding window
        
        if current > self.limit:
            logger.warning(
                f"AWS API rate limit exceeded: {self.api_name} "
                f"for account {self.account_id} ({current}/{self.limit}/s)"
            )
            raise RateLimitExceeded(
                f"AWS API {self.api_name} rate limit exceeded "
                f"({current}/{self.limit} calls/sec for account {self.account_id})"
            )
        
        return True

    def get_remaining(self) -> int:
        """Get remaining calls in current window"""
        current = int(self.redis.get(self.key) or 0)
        return max(0, self.limit - current)

    @classmethod
    def for_capacity_check(cls, redis_client: Redis, account_id: str) -> "AWSAPIRateLimiter":
        """Factory for RunInstances dry-run rate limiter"""
        return cls(redis_client, account_id, "RunInstances", calls_per_second=5)

    @classmethod
    def for_pricing(cls, redis_client: Redis, account_id: str) -> "AWSAPIRateLimiter":
        """Factory for Pricing API rate limiter"""
        return cls(redis_client, account_id, "GetProducts", calls_per_second=10)

    @classmethod
    def for_spot_history(cls, redis_client: Redis, account_id: str) -> "AWSAPIRateLimiter":
        """Factory for DescribeSpotPriceHistory rate limiter"""
        return cls(redis_client, account_id, "DescribeSpotPriceHistory", calls_per_second=20)
