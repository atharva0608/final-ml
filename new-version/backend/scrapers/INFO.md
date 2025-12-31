# Scrapers - Component Information

> **Last Updated**: 2025-12-31 12:36:00
> **Maintainer**: LLM Agent

---

## Folder Purpose
Contains data collection services for scraping AWS Spot Advisor data and real-time Spot/On-Demand pricing information.

---

## Component Table

| File Name | Scraper ID | Schedule | Purpose | Data Source | Status |
|-----------|-----------|----------|---------|-------------|--------|
| spot_advisor_scraper.py | SVC-SCRAPE-01 | Every 6 hours | Scrape Spot interruption frequency data | AWS Spot Advisor API | Pending |
| pricing_collector.py | SVC-PRICE-01 | Every 5 minutes | Collect real-time Spot and On-Demand prices | AWS Price List API | Pending |

---

## Recent Changes

### [2025-12-31 12:36:00] - Initial Scrapers Structure Created
**Changed By**: LLM Agent
**Reason**: Create organized folder structure for data collection services
**Impact**: Created backend/scrapers/ directory for AWS data scrapers
**Files Modified**:
- Created backend/scrapers/
- Created backend/scrapers/INFO.md (this file)
**Feature IDs Affected**: N/A (Infrastructure setup)
**Breaking Changes**: No

---

## Dependencies

### Internal Dependencies
- `backend/models/` - Database models
- Redis - For caching pricing data

### External Dependencies
- **AWS SDK**: boto3
- **HTTP Client**: requests
- **Task Queue**: Celery (for scheduling)

---

## Scraper Responsibilities

### spot_advisor_scraper.py (SVC-SCRAPE-01):
**Purpose**: Collect Spot interruption frequency data from AWS

**Schedule**: Every 6 hours (Celery Beat)

**Data Source**: AWS Spot Advisor API

**Process**:
1. Fetch interruption frequency data for all regions
2. Parse frequency buckets: <5%, 5-10%, 10-15%, 15-20%, >20%
3. Store in `interruption_rates` table
4. Update timestamp for each entry

**Data Structure**:
```python
{
    "instance_type": "c5.xlarge",
    "region": "us-east-1",
    "az": "us-east-1a",
    "frequency_bucket": "5-10%",
    "last_updated": "2025-12-31T12:00:00Z"
}
```

**Storage**: Database table `interruption_rates`

**Used By**: MOD-SPOT-01 (Spot Optimizer)

---

### pricing_collector.py (SVC-PRICE-01):
**Purpose**: Collect real-time Spot and On-Demand pricing

**Schedule**: Every 5 minutes (Celery Beat)

**Data Sources**:
- AWS Price List API (On-Demand prices)
- AWS EC2 DescribeSpotPriceHistory API (Spot prices)

**Process**:
1. Fetch current Spot prices for all instance types in all regions
2. Fetch On-Demand prices from Price List API
3. Store in Redis with 5-minute TTL
4. Calculate average Spot price (last 1 hour)

**Redis Keys**:
```
spot_prices:{region}:{instance_type} = {
    "current": 0.0416,
    "average_1h": 0.0420,
    "timestamp": "2025-12-31T12:00:00Z"
}

ondemand_prices:{region}:{instance_type} = {
    "price": 0.085,
    "timestamp": "2025-12-31T12:00:00Z"
}
```

**TTL**: 5 minutes (300 seconds)

**Used By**: MOD-SPOT-01 (Spot Optimizer), Services (cost calculations)

---

## Data Quality Checks

### spot_advisor_scraper.py:
- Validate frequency bucket values
- Ensure all regions are covered
- Log missing data warnings
- Retry on API failure (max 3 retries)
- Alert if data is stale (> 12 hours)

### pricing_collector.py:
- Validate price values (> 0)
- Check for price anomalies (sudden spikes)
- Ensure all instance types are covered
- Log API rate limiting warnings
- Retry on API failure (max 3 retries)
- Alert if prices are stale (> 10 minutes)

---

## Performance Optimization

### Batch Processing:
- Fetch prices in batches (100 instance types at a time)
- Use concurrent requests for multiple regions
- Implement exponential backoff for rate limiting

### Caching Strategy:
- Cache responses in Redis
- Use short TTL for real-time data (5 minutes)
- Use longer TTL for static data (1 hour)
- Implement cache warming on startup

### Error Handling:
- Graceful degradation if API unavailable
- Use cached data if fresh data unavailable
- Log all failures for debugging
- Send alerts for persistent failures

---

## Monitoring and Alerting

- Track scraper execution duration
- Alert if execution time > 2 minutes
- Monitor API response times
- Track cache hit rates
- Alert if cache hit rate < 80%
- Monitor Redis memory usage
- Alert if data freshness > 10 minutes

---

## Rate Limiting

### AWS API Rate Limits:
- **Price List API**: 10 requests/second
- **DescribeSpotPriceHistory**: 20 requests/second
- **Spot Advisor API**: 5 requests/second

### Implementation:
- Token bucket algorithm
- Retry with exponential backoff
- Request throttling

---

## Data Lifecycle

### Spot Pricing Data (Redis):
- **TTL**: 5 minutes
- **Update Frequency**: Every 5 minutes
- **Retention**: None (ephemeral)

### Interruption Rates (Database):
- **Update Frequency**: Every 6 hours
- **Retention**: 90 days
- **Cleanup**: Automated job removes old data

---

## Testing Requirements

- Unit tests with mocked API responses
- Integration tests with live AWS APIs
- Rate limiting tests
- Error handling tests
- Cache invalidation tests
- Data quality validation tests
