# Repository Cleanup Plan
**Date**: 2025-12-02
**Goal**: Make mumbai_price_predictor.py the source of truth, remove duplicates

## Files to REMOVE (Duplicates/Old/Unwanted)

### Backend Duplicates
- `backend/backend.py` (OLD 355KB) → Keep `backend_simple.py`
- `backend/repositories.py` (old, unused)
- `backend/smart_emergency_fallback.py` (old complexity)
- `backend/exceptions.py` (old, unused)
- `backend/decision_api.py` (old)
- `backend/decision_engines/` (OLD directory - plural)

### ML Model Duplicates
- `backend/ml_models/price_predictor.py` (duplicate)
- `backend/ml_models/stability_ranker.py` (duplicate)
- `scripts/train_and_backtest.py` (consolidate into mumbai_price_predictor.py)

### Database Duplicates
- `database/schema.sql` (OLD 82KB) → Keep `schema_simple.sql`
- `database/migrations/` (old migrations)
- `database/fix_collation.sql` (old)

### Test/Old Files
- `test_imports.py`
- `old-version/` (entire directory)

## Files to KEEP

### Backend (Core)
- `backend/backend_simple.py` → Will rename to `backend.py`
- `backend/decision_engine/` (singular - NEW)
  - engine_enhanced.py
  - filtering.py
  - scoring.py
  - engine.py
  - __init__.py
- `backend/executor/`
  - aws_agentless.py
  - base.py
  - __init__.py
- `backend/ml_models/`
  - mumbai_price_predictor.py (SOURCE OF TRUTH)
  - __init__.py

### Database
- `database/schema_simple.sql` → Will rename to `schema.sql`

### Scripts
- `scripts/deploy_simple.sh` → Will rename to `deploy.sh`
- Other scripts (setup.sh, install.sh, etc.)

### Documentation
- All .md files
- README.md

## Renaming Plan

1. `backend/backend_simple.py` → `backend/backend.py`
2. `database/schema_simple.sql` → `database/schema.sql`
3. `scripts/deploy_simple.sh` → `scripts/deploy.sh`

## Final Structure

```
final-ml/
├── backend/
│   ├── backend.py (renamed from backend_simple.py)
│   ├── decision_engine/
│   │   ├── engine_enhanced.py
│   │   ├── filtering.py
│   │   ├── scoring.py
│   │   ├── engine.py
│   │   └── __init__.py
│   ├── executor/
│   │   ├── aws_agentless.py
│   │   ├── base.py
│   │   └── __init__.py
│   └── ml_models/
│       ├── mumbai_price_predictor.py (SOURCE OF TRUTH)
│       └── __init__.py
├── database/
│   └── schema.sql (renamed from schema_simple.sql)
├── scripts/
│   ├── deploy.sh (renamed from deploy_simple.sh)
│   └── [other scripts]
└── docs/
    └── [documentation]
```
