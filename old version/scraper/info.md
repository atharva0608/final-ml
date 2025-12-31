# Data Scraper Module

## Purpose

Web scraping and external data fetching utilities.

**Last Updated**: 2025-12-25
**Authority Level**: MEDIUM

---

## Files

### fetch_static_data.py
**Purpose**: Scrape and fetch static AWS data (pricing, instance types, regions)
**Lines**: ~500
**Key Functions**:
- `fetch_instance_types()` - Get all available EC2 instance types
- `fetch_pricing_data()` - Scrape AWS pricing information
- `fetch_region_data()` - Get AWS region and AZ information
- `fetch_spot_pricing_history()` - Historical spot prices
- `save_to_database()` - Store fetched data

**Data Sources**:
- AWS Pricing API
- AWS Service Quotas API
- Public AWS documentation
- AWS Cost Explorer API (if configured)

**Scraped Data**:
- Instance type specifications (CPU, memory, storage)
- On-demand pricing by region
- Spot pricing history
- Available regions and availability zones
- Instance family information

**Output**:
- Database tables (if direct insertion)
- CSV/JSON files (if file-based)
- Cached data for offline use

**Dependencies**:
- requests or httpx (HTTP client)
- beautifulsoup4 (HTML parsing, if needed)
- boto3 (AWS API)
- pandas (data manipulation)
- backend/database/models.py (if inserting to DB)

**Recent Changes**: None recent

### scheduler.py
**Purpose**: Schedule periodic data scraping jobs
**Lines**: ~50
**Key Components**:
- `DataScraperScheduler` - Main scheduler class
- Cron-like scheduling for fetch_static_data.py

**Schedule**:
- Daily: Fetch pricing updates (AWS prices change daily)
- Weekly: Fetch instance type catalog (rarely changes)
- Monthly: Fetch region data (rarely changes)

**Dependencies**:
- APScheduler or similar
- fetch_static_data.py

**Recent Changes**: None recent

---

## Scraping Workflow

```
Scheduler Triggers
   ↓
[fetch_static_data.py starts]
   ↓
[Fetch from AWS APIs]
   ├─ Pricing API
   ├─ EC2 DescribeInstanceTypes
   └─ Spot Price History
   ↓
[Parse and Transform Data]
   ↓
[Validate Data Quality]
   ↓
[Save to Database or Files]
   ↓
[Log Completion]
```

---

## Data Fetching

### Instance Types
```python
from scraper.fetch_static_data import fetch_instance_types

instance_types = fetch_instance_types(region='us-east-1')
# Returns: List of instance types with specs
```

### Pricing Data
```python
from scraper.fetch_static_data import fetch_pricing_data

pricing = fetch_pricing_data(
    instance_type='t3.medium',
    region='us-east-1'
)
# Returns: On-demand and spot pricing
```

---

## Dependencies

### Depends On:
- requests/httpx
- beautifulsoup4 (if web scraping)
- boto3 (AWS API)
- pandas
- APScheduler
- backend/database/models.py (optional)

### Depended By:
- ML model training (requires pricing data)
- Decision engine (uses instance specs)
- Cost prediction features

**Impact Radius**: MEDIUM (provides data for ML and cost analysis)

---

## Recent Changes

### 2025-12-25: Governance Structure Establishment
**Files Changed**: None (metadata only)
**Reason**: Document existing scraper functionality
**Impact**: No code changes, documentation baseline
**Reference**: `/index/recent_changes.md`

---

## Usage

### Manual Data Fetch
```bash
# Fetch all data
python scraper/fetch_static_data.py --all

# Fetch specific data type
python scraper/fetch_static_data.py --pricing
python scraper/fetch_static_data.py --instance-types
python scraper/fetch_static_data.py --regions
```

### Scheduled Scraping
```bash
# Start scheduler (runs in background)
python scraper/scheduler.py
```

---

## Data Storage

### Database Tables (if used)
- `instance_types` - Catalog of EC2 instance types
- `pricing_data` - Historical pricing data
- `regions` - AWS regions and AZs

### File Storage (if used)
```
data/
├── instance_types.csv
├── pricing_history.csv
└── regions.json
```

---

## Rate Limiting

### AWS API Limits
- Pricing API: ~100 requests/minute
- DescribeInstanceTypes: ~100 requests/minute
- Cost Explorer: ~5 requests/second

**Implementation**:
- Add delays between requests
- Use exponential backoff on rate limit errors
- Cache results to minimize API calls

---

## Known Issues

### None

Scraper module is stable as of 2025-12-25.

---

## TODO / Improvements

1. **Caching**: Implement Redis cache for frequently accessed data
2. **Incremental Updates**: Only fetch changed data, not full refresh
3. **Error Handling**: Better retry logic for failed scrapes
4. **Monitoring**: Add metrics for scrape success/failure rates

---

_Last Updated: 2025-12-25_
_Authority: MEDIUM - Data fetching_
