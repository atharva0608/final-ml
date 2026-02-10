# Automation Guide — AI/ML Execution Control

> **Status**: Specification Complete — Ready for Implementation
> **Priority**: Medium (post-core JIT deployment)
> **Estimated Effort**: 2–3 days (backend + frontend + testing)

---

## 1. Overview

The automation settings control whether the ML system can **execute** optimization recommendations or only **suggest** them. Two independent toggles live on the Organization model:

| Setting | Column | Default | Effect when OFF |
|:--------|:-------|:--------|:----------------|
| **Automation Enabled** | `automation_enabled` | `TRUE` | ML only provides recommendations, never executes |
| **Require Approval** | `automation_requires_approval` | `TRUE` | ML-recommended actions execute automatically without human review |

**Decision Matrix**:

| automation_enabled | automation_requires_approval | Behavior |
|:--:|:--:|:---|
| OFF | — | ML produces recommendations only. No execution. |
| ON | ON | ML suggests action → System creates approval ticket → Admin approves → Action executes |
| ON | OFF | ML suggests action → Action executes automatically (with full logging) |

---

## 2. Backend Implementation

### 2.1 Data Model (Organization table)

```sql
ALTER TABLE organizations
  ADD COLUMN automation_enabled            BOOLEAN DEFAULT TRUE,
  ADD COLUMN automation_requires_approval  BOOLEAN DEFAULT TRUE,
  ADD COLUMN automation_config             JSONB   DEFAULT '{}';
```

### 2.2 AutomationService

| Method | Purpose |
|:-------|:--------|
| `get_settings(org_id)` | Returns current automation toggles |
| `update_settings(org_id, data)` | Persists toggle changes (ORG_ADMIN only) |
| `should_require_approval(org_id, feature_id, resource_count, estimated_cost)` | Decision gate called by optimization/hygiene workers |

### 2.3 API Endpoints

| Method | Path | Auth | Description |
|:-------|:-----|:-----|:------------|
| `GET` | `/api/v1/settings/automation` | ORG_ADMIN | Retrieve current settings |
| `PUT` | `/api/v1/settings/automation` | ORG_ADMIN | Update settings |

### 2.4 Execution Flow (ML-Initiated Actions)

```python
def execute_ml_recommended_action(self, action, feature_id, org_id):
    automation_service = AutomationService(self.db)
    requires_approval = automation_service.should_require_approval(
        org_id=org_id,
        feature_id=feature_id,
        resource_count=len(action.resources),
        estimated_cost=action.estimated_cost
    )
    if requires_approval:
        approval_service = ApprovalService(self.db)
        ticket = approval_service.create_system_ticket(
            feature_id=feature_id,
            reason="ML-recommended optimization",
            resources=action.resources,
            estimated_savings=action.estimated_savings
        )
        return {"status": "pending_approval", "ticket_id": ticket.id}
    else:
        result = self.execute_action(action, feature_id)
        self._log_auto_execution(org_id, feature_id, action, result)
        self._notify_stakeholders(org_id, action, result)
        return {"status": "executed", "result": result}
```

---

## 3. Frontend Component

**File**: `frontend/src/components/settings/AutomationSettings.jsx`

| UI Element | Behavior |
|:-----------|:---------|
| **Automation Enabled** toggle | Master switch. When OFF, approval toggle is greyed out. |
| **Require Approval** toggle | Disabled unless automation is enabled. Default badge: "Enabled (Safer)". |
| **Warning banner** | Appears when approval is disabled: "Autonomous Mode Active: ML-recommended actions will execute automatically without human approval." |
| **How It Works** info card | Explains the 3 modes in plain language. |

---

## 4. Integration with JIT Approval System

### Hybrid Approval Model

| Action Origin | Approval Path |
|:--------------|:-------------|
| **Manual** (user-initiated) | Always uses JIT approval system — feature-specific, time-bound tickets |
| **Automated** (ML-initiated) | Checks `automation_requires_approval` → YES: system ticket → NO: auto-execute with logging |

### Unified Ticket Creation

System tickets created by automation use `ApprovalType.SYSTEM_CLEANUP` and carry metadata:
- `feature_id` — which ML action triggered it
- `resources` — list of affected resource IDs
- `estimated_savings` — projected monthly savings
- `initiated_by` — "ML_ENGINE"

---

## 5. Security Considerations

| Concern | Mitigation |
|:--------|:-----------|
| **Authorization** | Only ORG_ADMIN can change automation settings; org-wide scope |
| **Audit** | All setting changes logged with who/when; auto-executed actions logged with full details |
| **Safety Default** | `automation_requires_approval = TRUE`; fail-safe if settings undefined |
| **Thresholds** | Future: cost and resource-count thresholds for auto-execution |

---

## 6. Testing Checklist

- [ ] ORG_ADMIN can access automation settings page
- [ ] Non-admin users cannot access settings
- [ ] Toggle switches update database correctly
- [ ] ML actions respect `automation_requires_approval` setting
- [ ] Auto-executed actions are logged
- [ ] System tickets created when approval required
- [ ] Settings persist after browser refresh
- [ ] Disabled automation shows greyed-out approval toggle

---

## 7. Migration

```python
# Alembic migration
def upgrade():
    op.add_column('organizations',
        sa.Column('automation_enabled', sa.Boolean(), default=True))
    op.add_column('organizations',
        sa.Column('automation_requires_approval', sa.Boolean(), default=True))
    op.add_column('organizations',
        sa.Column('automation_config', sa.JSON(), default={}))
    op.execute("""
        UPDATE organizations
        SET automation_enabled = TRUE,
            automation_requires_approval = TRUE,
            automation_config = '{}'
        WHERE automation_enabled IS NULL
    """)
```

---

**Last Updated**: 2026-02-10
**Naming Convention**: Uses "Approvals" (not "Tickets") per Global Naming Synchronization.
