# Intelligence Modules - Component Information

> **Last Updated**: 2025-12-31 12:36:00
> **Maintainer**: LLM Agent

---

## Folder Purpose
Contains AI/ML optimization modules including Spot optimization, bin packing, right-sizing, ML model server, risk tracking, and model validation.

---

## Component Table

| File Name | Module ID | Purpose | Key Functions | Dependencies | Status |
|-----------|-----------|---------|---------------|--------------|--------|
| spot_optimizer.py | MOD-SPOT-01 | Spot instance selection and optimization | select_best_instance(), detect_opportunities(), get_savings_projection() | Redis (spot prices), risk_tracker.py | Pending |
| bin_packer.py | MOD-PACK-01 | Pod consolidation and bin packing | analyze_fragmentation(), generate_migration_plan() | models/cluster.py, Kubernetes API | Pending |
| rightsizer.py | MOD-SIZE-01 | Resource right-sizing recommendations | analyze_resource_usage(), generate_resize_recommendations() | Prometheus metrics, models/instance.py | Pending |
| ml_model_server.py | MOD-AI-01 | ML model inference and management | predict_interruption_risk(), promote_model_to_production() | scikit-learn, models/ml_model.py | Pending |
| risk_tracker.py | SVC-RISK-GLB | Global risk tracking (Hive Mind) | flag_risky_pool(), check_pool_risk() | Redis (risk flags) | Pending |
| model_validator.py | MOD-VAL-01 | ML model and template validation | validate_template_compatibility(), validate_ml_model() | Docker (sandbox), models/node_template.py | Pending |

---

## Recent Changes

### [2025-12-31 12:36:00] - Initial Modules Structure Created
**Changed By**: LLM Agent
**Reason**: Create organized folder structure for intelligence modules
**Impact**: Created backend/modules/ directory for AI/ML modules
**Files Modified**:
- Created backend/modules/
- Created backend/modules/INFO.md (this file)
**Feature IDs Affected**: N/A (Infrastructure setup)
**Breaking Changes**: No

---

## Dependencies

### Internal Dependencies
- `backend/models/` - Database models
- `backend/utils/` - Helper functions
- Redis - For real-time data (prices, risk flags)

### External Dependencies
- **ML Libraries**: scikit-learn, pandas, numpy
- **AWS SDK**: boto3 (for Spot Advisor data)
- **Monitoring**: Prometheus client (for metrics)
- **Container**: Docker (for model validation sandbox)

---

## Module Responsibilities

### spot_optimizer.py (MOD-SPOT-01):
**Purpose**: Spot instance selection and waste detection

**Key Functions**:
- `select_best_instance()`:
  - Queries Redis for current Spot prices
  - Queries risk_tracker for flagged pools
  - Filters out risky pools
  - Scores: (Price * 0.6) + (Risk * 0.4)
  - Returns sorted candidate list

- `detect_opportunities()`:
  - Finds On-Demand instances with <30% utilization
  - Identifies Spot replacement candidates
  - Calculates potential savings
  - Returns opportunity list

- `get_savings_projection()`:
  - Simulates Spot replacement
  - Calculates bin packing savings
  - Returns projection chart data

**Data Sources**:
- Redis: `spot_prices:{region}:{instance_type}` (TTL: 5 minutes)
- Redis: `RISK:{region}:{az}:{instance_type}` (TTL: 30 minutes)
- Database: `interruption_rates` table

---

### bin_packer.py (MOD-PACK-01):
**Purpose**: Pod consolidation and node optimization

**Key Functions**:
- `analyze_fragmentation()`:
  - Calculates node utilization (CPU, memory)
  - Identifies underutilized nodes
  - Finds consolidation opportunities
  - Returns fragmentation report

- `generate_migration_plan()`:
  - Creates pod migration plan JSON
  - Respects PodDisruptionBudgets
  - Minimizes disruption
  - Returns migration plan with target nodes

**Algorithm**: Best-fit decreasing bin packing

---

### rightsizer.py (MOD-SIZE-01):
**Purpose**: Resource right-sizing recommendations

**Key Functions**:
- `analyze_resource_usage()`:
  - Queries Prometheus for 14-day metrics
  - Compares resource requests vs actual usage
  - Identifies over-provisioned workloads
  - Returns usage analysis

- `generate_resize_recommendations()`:
  - Suggests smaller instance types
  - Calculates potential savings
  - Provides confidence score
  - Returns recommendations list

**Data Sources**:
- Prometheus: CPU/memory usage over 14 days
- Database: `instance_specs` table

---

### ml_model_server.py (MOD-AI-01):
**Purpose**: ML model inference and lifecycle management

**Key Functions**:
- `predict_interruption_risk()`:
  - Loads trained model from file
  - Prepares feature vector: (instance_type, AZ, price_history, hour, day)
  - Returns interruption probability (0-1)
  - Caches predictions in Redis

- `promote_model_to_production()`:
  - Updates ml_models table status (testing → production)
  - Broadcasts Redis event for hot reload
  - Validates model contract (input/output schema)
  - Returns promotion result

**Model Contract**:
- Input: `{instance_type, az, price_history[], hour, day}`
- Output: `{risk_score: float[0-1], confidence: float}`

---

### risk_tracker.py (SVC-RISK-GLB):
**Purpose**: Global risk tracking system (Hive Mind)

**Key Functions**:
- `flag_risky_pool()`:
  - Sets Redis key: `RISK:{region}:{az}:{instance_type}` = "DANGER"
  - TTL: 30 minutes
  - Increments interruption counter
  - Triggers immediate rebalancing for affected clusters

- `check_pool_risk()`:
  - Queries Redis for risk flags
  - Returns risk status (SAFE, WARNING, DANGER)
  - Used by MOD-SPOT-01 to filter candidates

**Critical**: Powers the Hive Mind - when Client A experiences interruption, ALL clients avoid that pool

---

### model_validator.py (MOD-VAL-01):
**Purpose**: Validation for templates and ML models

**Key Functions**:
- `validate_template_compatibility()`:
  - Checks instance family vs architecture (x86_64 vs ARM64)
  - Validates disk type and size
  - Returns warnings list

- `validate_ml_model()`:
  - Spins up Docker sandbox
  - Loads model and tests with sample input
  - Verifies output contract
  - Validates model file integrity
  - Returns validation result

**Security**: ML model validation runs in isolated Docker container

---

## Data Flow

```
┌─────────────────────────────────────────────────────────┐
│ Event: Spot Interruption Warning from Client A          │
└───────────────────┬─────────────────────────────────────┘
                    │
    ┌───────────────▼────────────────┐
    │ SVC-RISK-GLB.flag_risky_pool() │
    │ Redis: RISK:us-east-1a:c5.xlarge = DANGER │
    └───────────────┬────────────────┘
                    │
        ┌───────────┴────────────┐
        │                        │
┌───────▼────────┐   ┌──────────▼───────────┐
│ Client A:       │   │ Client B,C,D:        │
│ Immediate       │   │ Avoid risky pool     │
│ rebalancing     │   │ (milliseconds)       │
└─────────────────┘   └──────────────────────┘
```

---

## Testing Requirements

- Unit tests for all functions with mocked data
- Integration tests with live Redis instance
- ML model validation tests
- Performance tests (latency < 100ms for predictions)
- Load tests (handle 1000 concurrent requests)
