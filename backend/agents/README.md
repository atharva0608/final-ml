# Multi-Agent AI System for Spot Optimizer

## Overview

This directory contains a complete 8-agent autonomous architecture for intelligent spot instance optimization and cluster management. Each agent has a specific role and operates deterministically with strict input/output contracts.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Agent Orchestrator                        │
│                (Coordinates all 8 agents)                    │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
        ┌───────────────────┴───────────────────┐
        │                                       │
        ▼                                       ▼
┌──────────────────┐                 ┌──────────────────┐
│ Global           │                 │ Event            │
│ Intelligence     │                 │ Monitoring       │
│ Agent            │                 │ Agent            │
│ (Scheduled)      │                 │ (Continuous)     │
└────────┬─────────┘                 └──────────────────┘
         │
         ▼
┌──────────────────┐
│ Capacity         │
│ Validator        │
│ Agent            │
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ Decision         │
│ Engine           │
│ Agent            │
└────────┬─────────┘
         │
         ├──────────────────────────┐
         │                          │
         ▼                          ▼
┌──────────────────┐      ┌──────────────────┐
│ Rightsizing      │      │ Cooldown         │
│ Agent            │      │ Controller       │
│ (If needed)      │      │ Agent            │
└──────────────────┘      └────────┬─────────┘
                                   │
                                   ▼
                         ┌──────────────────┐
                         │ Substitute       │
                         │ Manager          │
                         │ Agent            │
                         └────────┬─────────┘
                                  │
                                  ▼
                         ┌──────────────────┐
                         │ Cluster          │
                         │ Execution        │
                         │ Agent            │
                         └──────────────────┘
```

## The 8 Agents

### 1. Global Intelligence Agent (ASCP.AI Core)

**Purpose:** Generate region-wide spot pool intelligence for all tenants.

**Inputs:**
- Region
- Spot price data
- On-demand price data
- Interruption rates
- Blacklist
- Historical features

**Outputs:**
- Ranked pool list (max 50)
- Risk probability per pool
- Predicted savings
- Composite score

**Hard Rules:**
1. Remove pools with interruption_rate > 10%
2. Remove blacklisted pools
3. Reject pools with predicted risk > 0.45
4. Composite score = (savings × 0.4) - (risk × 0.6)
5. Sort descending by composite_score

**File:** `global_intelligence_agent.py`

---

### 2. Decision Engine Agent (Policy Brain)

**Purpose:** Final authority for cluster node placement decisions.

**Inputs:**
- Cluster ID
- Mode (manual/auto)
- Global ranked pools
- Node template
- Karpenter constraints
- Cluster state
- Cooldown records
- Recent actions

**Outputs:**
- **Manual mode:** Top 3 candidates (best_balanced, max_savings, most_stable)
- **Auto mode:** Selected pool or FALLBACK decision

**Decision Workflow:**
1. Filter by node_template
2. Intersect with karpenter_constraints
3. Apply diversity rules (max 40% same family)
4. Reject pools in cooldown
5. Reject low-quality pools

**File:** `decision_engine_agent.py`

---

### 3. Rightsizing Agent

**Purpose:** Workload efficiency analysis.

**Inputs:**
- Cluster ID
- Pod metrics (168-hour window)
- Instance cost data
- Global ranked pools

**Outputs:**
- Resizing recommendations with:
  - Controller name
  - Current vs recommended instance
  - Confidence (HIGH/MEDIUM/LOW)
  - Monthly savings
  - Risk probability

**Analysis Logic:**
1. Group metrics by controller
2. Compute P95 CPU and memory
3. Detect oversized (P95 < 50%) or undersized (P95 > 95%)
4. Add 20% safety buffer
5. Map to valid instance types
6. Enrich with ML risk scores

**File:** `rightsizing_agent.py`

---

### 4. Cluster Execution Agent

**Purpose:** Apply approved decisions to Kubernetes.

**Inputs:**
- Cluster ID
- Action (patch_nodepool/fallback/revert)
- Selected pool

**Outputs:**
- Execution status (SUCCESS/FAILED)
- Timestamp

**Workflow:**
1. Connect via SigV4 token
2. Fetch NodePool CRD
3. Patch instance-type and capacity-type
4. Log action
5. Return status

**File:** `cluster_execution_agent.py`

---

### 5. Event Monitoring Agent

**Purpose:** React to termination and rebalance notices.

**Inputs:**
- Event type (rebalance_notice/termination_notice)
- Cluster ID
- Instance type
- Availability zone

**Outputs:**
- Event handled status
- Substitute activated
- Blacklist applied

**Logic:**

**Rebalance Notice:**
- Prewarm substitute
- Evaluate early switch

**Termination Notice:**
- Cordon and drain node
- Promote substitute
- Blacklist pool for 24h
- Trigger re-ranking

**File:** `event_monitoring_agent.py`

---

### 6. Substitute Manager Agent

**Purpose:** Manage safety fallback nodes.

**Inputs:**
- Cluster state
- Stress level (normal/elevated)
- Candidate pools

**Outputs:**
- Substitute type (spot/ondemand)
- Instance type
- Availability zone

**Logic:**

**Normal Stress:**
- Choose cheapest low-risk Spot from different family + AZ

**Elevated Stress:**
- Choose smallest On-Demand safe instance

**Constraint:** Never allow same family as failed instance

**File:** `substitute_manager_agent.py`

---

### 7. Capacity Validator Agent

**Purpose:** Batch-validate spot capacity.

**Inputs:**
- Region
- Candidate pools

**Outputs:**
- Validated pools
- Unavailable pools

**Logic:**
- Validate capacity once per cycle
- Cache results (10-minute TTL)
- Mark pools unavailable if validation fails

**File:** `capacity_validator_agent.py`

---

### 8. Cooldown Controller Agent

**Purpose:** Enforce anti-flapping rules.

**Inputs:**
- Cluster ID
- Recent actions
- Proposed pool (optional)

**Outputs:**
- Cooldown active status
- Reason
- Remaining minutes

**Rules:**
1. Prevent switching within 60 minutes
2. Prevent reuse of same pool within 120 minutes

**File:** `cooldown_controller_agent.py`

---

## Orchestration Order

The agents execute in this order:

1. **GlobalIntelligenceAgent** (scheduled every 30 seconds)
2. **CapacityValidator** (filter available pools)
3. **DecisionEngine** (select optimal pool)
4. **RightsizingAgent** (if needed for analysis)
5. **CooldownController** (prevent flapping)
6. **SubstituteManager** (if triggered by event)
7. **ClusterExecutionAgent** (apply changes)
8. **EventMonitoringAgent** (continuous monitoring)

## API Endpoints

### Optimization Pipeline

```bash
POST /api/v1/ai-agents/{cluster_id}/optimize
{
  "mode": "auto",  # or "manual"
  "force_refresh": false
}
```

**Manual Mode Response:**
```json
{
  "cluster_id": "abc123",
  "mode": "manual",
  "candidates": [
    {
      "label": "best_balanced",
      "instance_type": "m5.xlarge",
      "az": "us-east-1a",
      "risk_prob": 0.12,
      "predicted_savings": 0.87,
      "decision_confidence": 0.95
    }
  ]
}
```

**Auto Mode Response:**
```json
{
  "cluster_id": "abc123",
  "mode": "auto",
  "action": "ALLOW",
  "selected_pool": {
    "instance_type": "m5.xlarge",
    "az": "us-east-1a"
  },
  "reason": "Selected best candidate with composite_score=0.81"
}
```

### Rightsizing Analysis

```bash
POST /api/v1/ai-agents/{cluster_id}/rightsizing
{
  "analysis_window_hours": 168
}
```

**Response:**
```json
{
  "cluster_id": "abc123",
  "recommendations": [
    {
      "controller": "deployment-web",
      "current_instance": "m5.2xlarge",
      "recommended_instance": "m5.large",
      "confidence": "HIGH",
      "monthly_savings": 312.00,
      "risk_prob": 0.15,
      "diversity_ok": true
    }
  ]
}
```

### Interruption Event Handling

```bash
POST /api/v1/ai-agents/events/interruption
{
  "cluster_id": "abc123",
  "event_type": "termination_notice",
  "instance_type": "m5.large",
  "az": "us-east-1a"
}
```

### Agent Health Status

```bash
GET /api/v1/ai-agents/health
```

**Response:**
```json
{
  "orchestrator": "AgentOrchestrator",
  "version": "1.0.0",
  "agents": {
    "global_intelligence": {"name": "GlobalIntelligence", "status": "active"},
    "capacity_validator": {"name": "CapacityValidator", "status": "active"},
    ...
  }
}
```

## Configuration

Configuration is managed via `config.py`:

```python
from backend.agents.config import get_agent_config

config = get_agent_config()
```

**Environment Variables:**

```bash
# LLM Settings
LLM_PROVIDER=openai
LLM_MODEL=gpt-4
LLM_API_KEY=your-api-key
OPENAI_API_KEY=your-api-key

# Feature Flags
ENABLE_AUTO_EXECUTION=true
```

**Key Configuration Options:**

| Setting | Default | Description |
|---------|---------|-------------|
| `max_interruption_rate` | 0.10 | Max 10% interruption rate |
| `max_risk_prob` | 0.45 | Max 45% risk probability |
| `min_savings_threshold` | 0.02 | Min 2% savings |
| `max_same_family_ratio` | 0.40 | Max 40% same instance family |
| `cooldown_switch_minutes` | 60 | Wait 60 min between switches |
| `cooldown_reuse_minutes` | 120 | Wait 120 min before pool reuse |
| `blacklist_duration_hours` | 24 | Blacklist pools for 24 hours |

## Usage Examples

### Example 1: Run Optimization in Manual Mode

```python
from backend.services.agent_service import AgentService

agent_service = AgentService(db=db_session)

results = await agent_service.run_optimization_for_cluster(
    cluster_id="prod-cluster-1",
    mode="manual",
    force_refresh=True
)

# Review candidates
for candidate in results['stages']['decision_engine']['data']['candidates']:
    print(f"{candidate['label']}: {candidate['instance_type']}")
```

### Example 2: Generate Rightsizing Recommendations

```python
results = await agent_service.generate_rightsizing_recommendations(
    cluster_id="prod-cluster-1",
    analysis_window_hours=168
)

for rec in results['data']['recommendations']:
    if rec['confidence'] == 'HIGH':
        print(f"High confidence: {rec['current_instance']} → {rec['recommended_instance']}")
        print(f"Savings: ${rec['monthly_savings']}/month")
```

### Example 3: Handle Interruption Event

```python
results = await agent_service.handle_interruption_event(
    cluster_id="prod-cluster-1",
    event_type="termination_notice",
    instance_type="m5.large",
    az="us-east-1a"
)

if results['data']['substitute_activated']:
    print(f"Substitute activated: {results['data']['substitute']}")
```

## Testing

Run agent tests:

```bash
pytest backend/tests/test_agents.py -v
```

Test individual agents:

```bash
pytest backend/tests/test_agents.py::test_global_intelligence_agent -v
pytest backend/tests/test_agents.py::test_decision_engine_agent -v
```

## Monitoring

Monitor agent execution:

1. **Agent Health:** GET `/api/v1/ai-agents/health`
2. **Cluster Status:** GET `/api/v1/ai-agents/status/{cluster_id}`
3. **Audit Logs:** Query `audit_logs` table for agent actions
4. **Redis Keys:**
   - `risky_pools` - Blacklisted pools
   - `cooldown:{cluster_id}` - Cooldown records
   - `global_pools:{cluster_id}` - Cached pool rankings
   - `optimization_results:{cluster_id}` - Latest results

## Troubleshooting

### Agent Execution Failures

**Issue:** Pipeline fails at a specific stage

**Solution:**
1. Check agent health: GET `/api/v1/ai-agents/health`
2. Review input data validation errors in logs
3. Verify Redis connectivity
4. Check LLM API key if using AI-powered agents

### No Recommendations Returned

**Issue:** Decision engine returns empty candidate list

**Solution:**
1. Check blacklist: `redis-cli SMEMBERS risky_pools`
2. Review interruption rates (may be too high)
3. Verify node template constraints aren't too restrictive
4. Check cooldown records: `redis-cli HGETALL cooldown:{cluster_id}`

### Cooldown Preventing Execution

**Issue:** Cooldown controller blocks all actions

**Solution:**
1. Check recent actions timestamp
2. Clear cooldown if needed: `redis-cli DEL cooldown:{cluster_id}`
3. Adjust cooldown timings in config

## Production Deployment

**Requirements:**
- Python 3.11+
- Redis 6+
- PostgreSQL 13+
- (Optional) LLM API key for AI-powered features

**Environment Setup:**
```bash
# Install dependencies
pip install -r requirements.txt

# Set environment variables
export LLM_PROVIDER=openai
export OPENAI_API_KEY=your-key
export ENABLE_AUTO_EXECUTION=true

# Run migrations
alembic upgrade head

# Start backend
uvicorn main:app --host 0.0.0.0 --port 8000
```

**Celery Integration:**

For scheduled execution, add to `backend/workers/app.py`:

```python
from backend.services.agent_service import AgentService

@celery_app.task(name="run_global_intelligence")
def run_global_intelligence():
    """Run global intelligence agent for all regions"""
    # Implementation here
    pass
```

## Future Enhancements

- [ ] Add support for local LLMs (Ollama, LLaMA)
- [ ] Implement agent-to-agent communication bus
- [ ] Add reinforcement learning for decision optimization
- [ ] Implement multi-region coordination
- [ ] Add predictive scaling based on workload patterns
- [ ] Integrate with cost anomaly detection
- [ ] Add explainability module for agent decisions

## License

Copyright © 2026 Spot Optimizer Platform. All rights reserved.
