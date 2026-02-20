# Integration Implementation Summary
## Node Templates ↔ AtharvaAI ↔ Right-Sizing Integration

**Implementation Date**: 2026-02-19
**Status**: Backend Complete (Tasks 1-6) | Frontend Pending (Tasks 7-8) | Verification Pending (Task 9)

---

## Overview

This integration connects three previously-siloed systems into a unified optimization pipeline:
1. **Node Templates** - Define allowed instance types per organization
2. **AtharvaAI ML Pool Optimizer** - Ranks best pools with ML scores
3. **Right-Sizing** - Recommends workload resizing with validation

---

## Completed Tasks (Backend)

### ✅ Task 1: Enhanced GET /api/v1/templates/options
**Files Modified**:
- `/backend/services/template_service.py` - Added `get_template_options()` method
- `/backend/api/template_routes.py` - Modified endpoint to call service

**Changes**:
- Returns enriched instance family data grouped by category
- Includes metadata: vCPU ranges, memory ranges, generation, architecture, burstable flag
- Instance families organized by: general_purpose, compute_optimized, memory_optimized, storage_optimized, accelerated_computing
- Replaces hardcoded static list with structured service response

**New Response Structure**:
```json
{
  "architectures": [...],
  "disk_types": [...],
  "strategies": [...],
  "instance_families": {
    "general_purpose": [
      {"family": "m5", "arch": ["x86_64"], "generation": 5, "vcpu_range": "2-96", ...}
    ],
    ...
  },
  "sizes": [...],
  "interruption_tolerance_levels": [...]
}
```

---

### ✅ Task 2: Added GET /api/v1/templates/default + Modified Rankings Endpoint
**Files Modified**:
- `/backend/services/template_service.py` - Added `get_default_template(user_id)` method
- `/backend/api/template_routes.py` - Added `/default` endpoint (placed BEFORE `/{template_id}` route)
- `/backend/api/atharvaai_routes.py` - Modified `get_pool_rankings()` to accept optional `template_id` parameter
- `/frontend/src/services/api.js` - Added `getDefault()` and `getRankingsForTemplate()` methods

**Key Features**:
- GET `/api/v1/templates/default` returns user's default template or 404
- POST `/api/v1/atharvaai/pools/rankings` now accepts `template_id` query parameter
- Backend fetches template from DB when `template_id` provided (instead of requiring body template)
- Returns `template_applied: {id, name}` in response when template used
- Maintains backward compatibility (body-based template still works)

**Frontend API Methods Added**:
```javascript
templateAPI.getDefault()
atharvaaiAPI.getRankingsForTemplate(templateId, region, limit)
```

---

### ✅ Task 3: Added GET /api/v1/atharvaai/blacklist/check
**Files Modified**:
- `/backend/api/atharvaai_routes.py` - Added `/blacklist/check` endpoint
- `/frontend/src/services/api.js` - Added `checkBlacklist()` method

**Functionality**:
- Checks if specific instance_type + AZ combination is in Redis `risky_pools` set
- Returns blacklist status, risk score, reason, TTL
- Used by Right-Sizing to validate recommendations before display
- Gracefully handles Redis connection failures (returns blacklisted: false with warning)

**Response Structure**:
```json
{
  "instance_type": "m5.xlarge",
  "az": "us-east-1a",
  "blacklisted": true,
  "risk_score": 5,
  "reason": "Recent spot interruption detected",
  "expires_in_seconds": 43200
}
```

---

### ✅ Task 4: Created GET /api/v1/pod-metrics/rightsizing/enriched
**Files Modified**:
- `/backend/api/pod_metrics_routes.py` - Added `/rightsizing/enriched` endpoint + schemas
- `/frontend/src/services/api.js` - Added `getEnrichedRightsizing()` method

**Core Integration Endpoint**:
- Extends existing rightsizing recommendations with template validation + AtharvaAI data
- Validates each recommendation against Node Template constraints (if template_id provided)
- Checks AtharvaAI blacklist for each recommended pool (if check_blacklist=True)
- Attempts to fetch AtharvaAI ML score from Redis cache
- Returns availability confidence from Spot Advisor data

**New Schemas**:
```python
class TemplateCompliance(BaseModel):
    compliant: bool
    violations: List[str] = []

class BlacklistStatus(BaseModel):
    checked: bool
    blacklisted: bool
    risk_score: int = 0
    reason: Optional[str] = None

class EnrichedRightSizingRecommendation(BaseModel):
    # All base recommendation fields +
    template_compliance: Optional[TemplateCompliance] = None
    blacklist_status: Optional[BlacklistStatus] = None
    atharva_score: Optional[float] = None
    availability_confidence: Optional[str] = None
```

**Query Parameters**:
- `cluster_id` (required)
- `analysis_window_hours` (default: 168)
- `min_data_points` (default: 100)
- `template_id` (optional)
- `check_blacklist` (default: True)

---

### ✅ Task 5: Created POST /api/v1/optimization/apply/{instance_id}/validated
**Files Modified**:
- `/backend/api/optimization_routes.py` - Added `/apply/{instance_id}/validated` endpoint
- `/frontend/src/services/api.js` - Added `applyRightsizingValidated()` method

**Real-Time Validation**:
1. **Blacklist Check**: Verifies target pool not in Redis `risky_pools` set
2. **Template Compliance**: Validates target instance family against user's default template
3. **409 Conflict Response**: Returns structured error if validation fails
4. **Audit Logging**: Creates `RIGHTSIZING_APPLIED_VALIDATED` event
5. **Instance Tagging**: Tags EC2 instance for agent processing

**Error Response Format**:
```json
{
  "error": "POOL_BLACKLISTED" | "TEMPLATE_VIOLATION",
  "message": "Human-readable error message",
  "suggestion": "Remediation suggestion"
}
```

---

### ✅ Task 6: Added Cache Invalidation on Template Save
**Files Modified**:
- `/backend/services/template_service.py` - Added `_invalidate_atharva_cache(user_id)` method

**Implementation**:
- Invalidates Redis cache keys matching `atharva_rankings:{user_id}:*`
- Called after `create_template()`, `update_template()`, `set_default()`
- Prevents serving stale ML rankings filtered by old template
- Gracefully handles Redis connection failures (logs warning, doesn't crash)

**Cache Invalidation Logic**:
```python
def _invalidate_atharva_cache(self, user_id: str):
    try:
        r = redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)
        cache_pattern = f"atharva_rankings:{user_id}:*"
        keys = r.keys(cache_pattern)
        if keys:
            r.delete(*keys)
    except Exception as e:
        logger.warning(f"Failed to invalidate AtharvaAI cache: {e}")
```

---

## Pending Tasks (Frontend)

### ⏳ Task 7: Frontend - AtharvaAI Template Integration
**Files to Modify**:
- `/frontend/src/components/atharvaai/PoolRankings.jsx`
- `/frontend/src/store/useAtharvaStore.js`

**Required Changes**:
1. Auto-load default template on mount using `templateAPI.getDefault()`
2. Add template selector dropdown showing all org templates
3. Show `template_applied` badge in table header
4. Re-fetch rankings when template selection changes
5. Update rankings API call to pass `template_id` parameter

**Implementation Notes**:
- Use `useEffect()` to fetch default template on component mount
- Handle 404 gracefully (no default template set)
- Template selector should show: "Filtering by: [template name]" or "No template filter"
- Visual badge: "Filtered by: Production Template" in table header

---

### ⏳ Task 8: Frontend - Right-Sizing Enriched Recommendations UI
**Files to Modify**:
- `/frontend/src/components/right-sizing/ManualRightSizing.jsx`
- `/frontend/src/components/templates/TemplateBuilder.jsx`
- `/frontend/src/components/templates/TemplateList.jsx`

**Part A - ManualRightSizing.jsx**:
1. Replace API call with enriched endpoint
2. Add "Pool Health" column showing:
   - Orange warning badge "⚠ Blacklisted" (if blacklisted)
   - Green badge "AtharvaAI: 8.7" (if ML score exists)
   - Grey text "Not scored" (if no score)
3. Add template compliance indicators:
   - Green checkmark ✓ (compliant)
   - Grey badge "Template violation" with tooltip (non-compliant)
4. Dim rows with template violations (opacity: 0.7)
5. Replace Apply button handler with validated endpoint
6. Add 409 error handling with toast messages

**Part B - TemplateList.jsx**:
1. Add "Last used by AtharvaAI" timestamp (requires DB column)
2. Add "Test in AtharvaAI" button navigating to `/atharvaai?template_id={id}`

**Part C - TemplateBuilder.jsx**:
1. Replace hardcoded instance family checkboxes with data from `templateAPI.getOptions()`
2. Render families grouped by category (general_purpose, compute_optimized, etc.)
3. Show metadata per family: arch badge, vCPU range, memory range, generation
4. Show "burstable" warning tag on t-family instances

---

### ⏳ Task 9: Database Migration + Full Verification
**Files to Check**:
- `/backend/models/node_template.py`

**Database Changes Required**:
Add usage tracking columns to `node_templates` table:
- `last_used_by_atharva_at` (DateTime, nullable)
- `atharva_rankings_count` (Integer, default=0)

**Migration Steps**:
```bash
cd backend
alembic revision --autogenerate -m "add template usage tracking columns"
alembic upgrade head
```

**Verification Checklist**:

**Backend Endpoints**:
- [ ] GET `/api/v1/templates/options` - enriched instance family data
- [ ] GET `/api/v1/templates/default` - default template or 404
- [ ] GET `/api/v1/templates` - still works, includes usage_stats if columns added
- [ ] POST `/api/v1/templates` - creates + invalidates cache
- [ ] PUT `/api/v1/templates/{id}` - updates + invalidates cache
- [ ] POST `/api/v1/atharvaai/pools/rankings` - body template still works
- [ ] POST `/api/v1/atharvaai/pools/rankings?template_id=X` - fetches from DB
- [ ] GET `/api/v1/atharvaai/blacklist/check?instance_type=X&az=Y` - returns status
- [ ] GET `/api/v1/pod-metrics/rightsizing` - original endpoint still works
- [ ] GET `/api/v1/pod-metrics/rightsizing/enriched?cluster_id=X` - enriched data
- [ ] POST `/api/v1/optimization/apply/{id}/validated` - validates before applying

**Frontend Verification**:
- [ ] AtharvaAI page auto-loads default template
- [ ] Template selector dropdown works
- [ ] Rankings update when template changes
- [ ] ManualRightSizing shows Pool Health column
- [ ] Blacklisted recommendations show warning
- [ ] Template violations shown with tooltip
- [ ] Apply button handles 409 errors
- [ ] TemplateBuilder loads families from API
- [ ] "Test in AtharvaAI" button works from TemplateList

**Integration Verification**:
- [ ] Create template with "no t-family" → Right-Sizing flags t3 recommendations
- [ ] Manually add pool to Redis blacklist → Right-Sizing shows warning
- [ ] Update template → AtharvaAI cache invalidated
- [ ] Apply blacklisted pool → 409 Conflict returned

**Container Restart**:
```bash
docker-compose down
docker-compose up --build -d
```

---

## New API Endpoints Summary

| Endpoint | Method | Purpose | Parameters |
|----------|--------|---------|------------|
| `/api/v1/templates/options` | GET | Enhanced instance family options | - |
| `/api/v1/templates/default` | GET | Get user's default template | - |
| `/api/v1/atharvaai/pools/rankings` | POST | ML pool rankings (now accepts template_id) | `template_id`, `region`, `limit` |
| `/api/v1/atharvaai/blacklist/check` | GET | Check specific pool blacklist status | `instance_type`, `az` |
| `/api/v1/pod-metrics/rightsizing/enriched` | GET | Template + blacklist validated recommendations | `cluster_id`, `template_id`, `check_blacklist` |
| `/api/v1/optimization/apply/{id}/validated` | POST | Apply with real-time validation | `target_instance_type`, `target_az` |

---

## Modified Files List

### Backend Files (6 files):
1. `/backend/api/template_routes.py` - Added `/default` endpoint, enhanced `/options`
2. `/backend/services/template_service.py` - Added 3 methods: `get_default_template()`, `get_template_options()`, `_invalidate_atharva_cache()`
3. `/backend/api/atharvaai_routes.py` - Added `/blacklist/check`, modified rankings to accept `template_id`
4. `/backend/api/pod_metrics_routes.py` - Added `/rightsizing/enriched` endpoint + 3 new schemas
5. `/backend/api/optimization_routes.py` - Added `/apply/{id}/validated` endpoint
6. `/backend/models/node_template.py` - (Pending: Add usage tracking columns)

### Frontend Files (1 file):
1. `/frontend/src/services/api.js` - Added 6 new API methods:
   - `templateAPI.getDefault()`
   - `atharvaaiAPI.getRankingsForTemplate()`
   - `atharvaaiAPI.checkBlacklist()`
   - `optimizationAPI.getEnrichedRightsizing()`
   - `optimizationAPI.applyRightsizingValidated()`

### Frontend Files (Pending - 3 files):
1. `/frontend/src/components/atharvaai/PoolRankings.jsx` - Template integration
2. `/frontend/src/components/right-sizing/ManualRightSizing.jsx` - Enriched recommendations UI
3. `/frontend/src/components/templates/TemplateBuilder.jsx` - Dynamic instance families
4. `/frontend/src/components/templates/TemplateList.jsx` - Usage stats + "Test in AtharvaAI" button

---

## Database Schema Changes

### Required Migration:
```sql
-- Add usage tracking columns to node_templates table
ALTER TABLE node_templates
ADD COLUMN last_used_by_atharva_at TIMESTAMP NULL;

ALTER TABLE node_templates
ADD COLUMN atharva_rankings_count INTEGER DEFAULT 0;
```

---

## Redis Keys Used

| Key Pattern | Purpose | TTL |
|-------------|---------|-----|
| `risky_pools` | Set of blacklisted instance_type:az combos | 12h |
| `risky_pool_meta:{pool_key}` | Blacklist metadata (reason, timestamp) | 12h |
| `atharva_score:{pool_key}` | Cached ML scores per pool | 5m |
| `atharva_rankings:{user_id}:*` | Cached rankings per user/template | 5m |

---

## Data Flow Diagram

```
User creates/updates Node Template
    ↓
template_service.create_template()
    ↓
Redis: DELETE atharva_rankings:{user_id}:*
    ↓
User requests AtharvaAI rankings
    ↓
atharvaai_routes.get_pool_rankings(template_id=X)
    ↓
Fetch template from DB
    ↓
Filter pools by template.families
    ↓
Check Redis risky_pools set
    ↓
ML score ranking
    ↓
Cache result: atharva_rankings:{user_id}:{template_id}:{region}
    ↓
Return ranked pools with template_applied metadata
    ↓
Frontend displays rankings with "Filtered by: {template.name}" badge
    ↓
User views Right-Sizing recommendations
    ↓
pod_metrics_routes.get_enriched_rightsizing_recommendations()
    ↓
Fetch base recommendations
    ↓
For each recommendation:
  - Check template compliance
  - Check Redis blacklist
  - Fetch AtharvaAI score
    ↓
Return enriched recommendations
    ↓
Frontend shows Pool Health column + compliance indicators
    ↓
User clicks "Apply" on recommendation
    ↓
optimization_routes.apply_rightsizing_validated()
    ↓
Validate against:
  1. Redis blacklist
  2. Default template families
    ↓
If validation fails → 409 Conflict
If validation passes → Tag instance + Audit log
```

---

## Testing Instructions

### Backend Testing:

1. **Test Template Options Endpoint**:
```bash
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/v1/templates/options
```

2. **Test Default Template**:
```bash
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/v1/templates/default
```

3. **Test Rankings with Template ID**:
```bash
curl -X POST -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/api/v1/atharvaai/pools/rankings?template_id=TEMPLATE_ID&region=ap-south-1&limit=10"
```

4. **Test Blacklist Check**:
```bash
curl -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/api/v1/atharvaai/blacklist/check?instance_type=m5.xlarge&az=us-east-1a"
```

5. **Test Enriched Right-Sizing**:
```bash
curl -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/api/v1/pod-metrics/rightsizing/enriched?cluster_id=CLUSTER_ID&template_id=TEMPLATE_ID"
```

6. **Test Validated Apply**:
```bash
curl -X POST -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/api/v1/optimization/apply/INSTANCE_ID/validated?target_instance_type=m5.large&target_az=us-east-1a"
```

### Integration Testing:

1. **Template + Rankings Integration**:
   - Create a template excluding t-family instances
   - Verify rankings exclude t-family pools
   - Update template to allow t-family
   - Verify cache invalidated (old rankings gone)
   - Verify new rankings include t-family pools

2. **Blacklist + Right-Sizing Integration**:
   - Manually add pool to Redis: `SADD risky_pools "m5.xlarge:us-east-1a"`
   - Fetch enriched right-sizing recommendations
   - Verify recommendation shows blacklisted: true
   - Try to apply → should return 409 Conflict

3. **Template + Right-Sizing Integration**:
   - Set default template excluding c-family
   - Fetch enriched recommendations
   - If c-family recommended → should show template_compliance: {compliant: false}
   - Try to apply c-family → should return 409 TEMPLATE_VIOLATION

---

## Known Limitations

1. **Pod-based Right-Sizing**: Current enriched endpoint is designed for instance-based recommendations. Pod-based recommendations need instance type mapping logic to validate against templates.

2. **Organization vs User ID**: Current implementation uses `user_id` for template ownership. If multi-user organizations need shared templates, this should be refactored to use `organization_id`.

3. **Redis Dependency**: Blacklist and cache features gracefully degrade if Redis is unavailable, but core functionality (validation) is skipped.

4. **Template Usage Tracking**: Requires DB migration to track when templates are used by AtharvaAI. Currently not implemented.

---

## Next Steps

1. **Complete Frontend Tasks 7-8**: Implement UI components for template integration
2. **Create DB Migration**: Add usage tracking columns to node_templates table
3. **Run Full Verification**: Execute all checklist items from Task 9
4. **Update Documentation**: Update all-components.md with new endpoints
5. **Performance Testing**: Verify enriched endpoint performance with large datasets
6. **End-to-End Testing**: Test complete user journey from template creation to validated apply

---

## Success Metrics

- ✅ All 6 backend tasks completed (100%)
- ⏳ Frontend tasks pending (0/2)
- ⏳ Verification pending (0/1)
- **Total Progress**: 67% (6/9 tasks)

**Backend Implementation**: COMPLETE ✅
**Frontend Implementation**: PENDING ⏳
**Full System Integration**: PENDING ⏳
