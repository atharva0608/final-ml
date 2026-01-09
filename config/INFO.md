# Configuration - Component Information

> **Last Updated**: 2025-12-31 12:36:00
> **Maintainer**: LLM Agent

---

## Folder Purpose
Contains configuration files for database connections, Redis cache, Celery task queue, and other system-wide settings. All configurations support environment variable overrides for different deployment environments (development, staging, production).

---

## Component Table

| File Name | Config Type | Purpose | Environment Variables | Dependencies |
|-----------|------------|---------|----------------------|--------------|
| database.py | Database | PostgreSQL connection configuration | DATABASE_URL, DB_POOL_SIZE | SQLAlchemy |
| redis.py | Cache | Redis connection and cache settings | REDIS_URL, REDIS_MAX_CONNECTIONS | redis-py |
| celery.py | Task Queue | Celery worker and broker configuration | CELERY_BROKER_URL, CELERY_RESULT_BACKEND | Celery |

---

## Recent Changes

### [2025-12-31 12:36:00] - Initial Config Structure Created
**Changed By**: LLM Agent
**Reason**: Create organized folder structure for configuration files
**Impact**: Created config directory for centralized configuration management
**Files Modified**:
- Created config/
- Created config/INFO.md (this file)
**Feature IDs Affected**: N/A (Infrastructure setup)
**Breaking Changes**: No

---

## Dependencies

### Internal Dependencies
- Used by all backend services
- Imported by backend/core/api_gateway.py
- Used by background workers

### External Dependencies
- **Database**: PostgreSQL 13+
- **Cache**: Redis 6+
- **Task Queue**: Celery 5+
- **Connection Pooling**: psycopg2, redis-py

---

## Configuration Files Overview

### 1. database.py (Planned)
```python
# Purpose: Database connection management
# Features:
# - SQLAlchemy engine configuration
# - Connection pooling
# - Read replica support (optional)
# - Automatic retry on connection failure
# - Transaction management

# Environment Variables:
# - DATABASE_URL: PostgreSQL connection string
# - DB_POOL_SIZE: Connection pool size (default: 20)
# - DB_MAX_OVERFLOW: Max overflow connections (default: 10)
# - DB_POOL_TIMEOUT: Connection timeout (default: 30)
# - DB_ECHO: Log SQL queries (default: False)
```

### 2. redis.py (Planned)
```python
# Purpose: Redis cache and pub/sub configuration
# Features:
# - Redis connection pool
# - Cache key prefixing
# - TTL management
# - Pub/Sub channels for WebSocket
# - Rate limiting configuration

# Environment Variables:
# - REDIS_URL: Redis connection string
# - REDIS_MAX_CONNECTIONS: Max pool size (default: 50)
# - REDIS_DECODE_RESPONSES: Decode responses (default: True)
# - REDIS_SOCKET_TIMEOUT: Socket timeout (default: 5)
```

### 3. celery.py (Planned)
```python
# Purpose: Celery task queue configuration
# Features:
# - Broker configuration (Redis)
# - Result backend configuration
# - Task routing
# - Worker concurrency settings
# - Beat scheduler configuration
# - Task serialization

# Environment Variables:
# - CELERY_BROKER_URL: Broker connection string
# - CELERY_RESULT_BACKEND: Result backend connection string
# - CELERY_WORKER_CONCURRENCY: Worker threads (default: 4)
# - CELERY_TASK_SERIALIZER: Serialization format (default: json)
```

---

## Environment-Specific Configuration

### Development:
- `DATABASE_URL`: Local PostgreSQL instance
- `REDIS_URL`: Local Redis instance
- `CELERY_BROKER_URL`: Local Redis instance
- Verbose logging enabled
- SQL query echo enabled

### Staging:
- `DATABASE_URL`: Staging PostgreSQL instance
- `REDIS_URL`: Staging Redis cluster
- `CELERY_BROKER_URL`: Staging Redis cluster
- Moderate logging
- SQL query echo disabled

### Production:
- `DATABASE_URL`: Production PostgreSQL instance with SSL
- `REDIS_URL`: Production Redis cluster with persistence
- `CELERY_BROKER_URL`: Production Redis cluster
- Minimal logging (errors only)
- SQL query echo disabled
- Connection pooling optimized for high load

---

## Security Guidelines

1. **Never commit credentials**: Use environment variables only
2. **SSL/TLS**: Always use SSL for database and Redis in production
3. **Connection Limits**: Set appropriate pool sizes to prevent exhaustion
4. **Timeouts**: Configure reasonable timeouts to prevent hanging connections
5. **Secrets Management**: Use AWS Secrets Manager or Vault for production secrets

---

## Configuration Loading Priority

1. Environment variables (highest priority)
2. `.env` file (development only)
3. Default values in config files (lowest priority)

---

## Testing Requirements

- Unit tests for configuration loading
- Validation tests for environment variables
- Connection tests for database and Redis
- Celery worker connectivity tests
- Configuration override tests
