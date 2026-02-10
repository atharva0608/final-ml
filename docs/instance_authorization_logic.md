# Instance Authorization Logic - Resource Hygiene

## Overview

The Resource Hygiene feature now shows **ALL instances** in the account, categorized into **Authorized** (managed/expected) and **Unauthorized** (potential wastage) sections.

---

## Instance Categories

### 1. ✅ AUTHORIZED - Cluster Nodes (Managed by Spot Optimizer)

**Criteria**: Instance ID exists in `instances` table (linked to a cluster)

**Status**: `ACTIVE`
**Reason**: "Managed by Spot Optimizer (Cluster Node)"
**Cost**: `$0.00` (not counted as wastage)
**Metadata**: `Managed: true`, `ManagedBy: "Spot Optimizer"`

**Example**:
```json
{
  "id": "i-0abc123def456",
  "name": "eks-node-1a",
  "type": "INSTANCE",
  "status": "ACTIVE",
  "region": "us-east-1",
  "cost_per_month": 0.0,
  "reason": "Managed by Spot Optimizer (Cluster Node)",
  "metadata": {
    "InstanceType": "m5.large",
    "State": "running",
    "Managed": true,
    "ManagedBy": "Spot Optimizer"
  },
  "is_compliant": true
}
```

**Frontend Display**:
- Section: **"Authorized Resources"** or **"Managed Instances"**
- Icon: ✅ Green checkmark
- Badge: "Managed"
- Action: None (these are expected resources)

---

### 2. ⚠️ UNAUTHORIZED - Marked for Review

**Criteria**:
- Not in cluster database
- Tagged with `spot-optimizer:review=true`

**Status**: `UNAUTHORIZED`
**Reason**: "Not managed by Spot Optimizer (Marked for review)"
**Cost**: `$XXX.XX` (counted as potential wastage)
**Metadata**: `Managed: false`

**Example**:
```json
{
  "id": "i-0xyz789abc123",
  "name": "legacy-app-server",
  "type": "INSTANCE",
  "status": "UNAUTHORIZED",
  "region": "us-east-1",
  "cost_per_month": 87.60,
  "reason": "Not managed by Spot Optimizer (Marked for review)",
  "metadata": {
    "InstanceType": "t3.large",
    "State": "running",
    "Managed": false
  },
  "is_compliant": false
}
```

**Frontend Display**:
- Section: **"Unauthorized Resources"** or **"Potential Wastage"**
- Icon: ⚠️ Yellow warning
- Badge: "Review Needed"
- Action: "Terminate" or "Authorize"
- **Counted in total savings**

---

### 3. 🏷️ NOT_COMPLIANT - Missing Required Tags

**Criteria**:
- Not in cluster database
- Missing required organization tags
- NOT marked for review

**Status**: `NOT_COMPLIANT`
**Reason**: "Not managed (Missing tags: Environment, Owner)"
**Cost**: `$0.00` (NOT counted as wastage)
**Metadata**: `Managed: false`, `missing_tags: ["Environment", "Owner"]`

**Example**:
```json
{
  "id": "i-0def456ghi789",
  "name": "test-instance",
  "type": "INSTANCE",
  "status": "NOT_COMPLIANT",
  "region": "us-east-1",
  "cost_per_month": 0.0,
  "reason": "Not managed (Missing tags: Environment, Owner)",
  "metadata": {
    "InstanceType": "t3.micro",
    "State": "running",
    "Managed": false
  },
  "is_compliant": false,
  "missing_tags": ["Environment", "Owner"]
}
```

**Frontend Display**:
- Section: **"Compliance Issues"** or **"Untagged Resources"**
- Icon: 🏷️ Tag icon
- Badge: "Fix Tags"
- Action: "Add Tags" (opens tag editor)
- **NOT counted in savings** (legitimate workload, just needs tagging)

---

### 4. ✅ ACTIVE - External Workload (Properly Tagged)

**Criteria**:
- Not in cluster database
- Has all required tags
- NOT marked for review

**Status**: `ACTIVE`
**Reason**: "Not managed (Properly tagged external workload)"
**Cost**: `$0.00` (NOT counted as wastage)
**Metadata**: `Managed: false`

**Example**:
```json
{
  "id": "i-0jkl012mno345",
  "name": "prod-api-server",
  "type": "INSTANCE",
  "status": "ACTIVE",
  "region": "us-east-1",
  "cost_per_month": 0.0,
  "reason": "Not managed (Properly tagged external workload)",
  "metadata": {
    "InstanceType": "c5.xlarge",
    "State": "running",
    "Managed": false
  },
  "is_compliant": true
}
```

**Frontend Display**:
- Section: **"Authorized Resources"** or **"External Workloads"**
- Icon: ✅ Green checkmark
- Badge: "External"
- Action: None or "Import to Spot Optimizer"
- **NOT counted in savings** (legitimate workload managed elsewhere)

---

## Savings Calculation

### Counted as Savings (Wastage):
- ✅ UNAUTHORIZED instances with `spot-optimizer:review=true`

### NOT Counted as Savings:
- ❌ Cluster nodes (managed workload)
- ❌ Compliant external workloads (properly tagged)
- ❌ Non-compliant instances (just need tagging)

**Formula**:
```python
total_savings = sum(
    instance.cost_per_month
    for instance in instances
    if instance.status == CleanupStatus.UNAUTHORIZED
)
```

---

## Frontend Implementation Guide

### Filtering by Management Status:

```javascript
// Managed by Spot Optimizer
const managedInstances = resources.filter(
  r => r.type === 'INSTANCE' && r.metadata?.Managed === true
);

// Not managed (external workloads)
const unmanagedInstances = resources.filter(
  r => r.type === 'INSTANCE' && r.metadata?.Managed === false
);

// Potential wastage (needs review)
const wastageInstances = resources.filter(
  r => r.type === 'INSTANCE' && r.status === 'UNAUTHORIZED'
);

// Compliance issues (needs tagging)
const complianceIssues = resources.filter(
  r => r.type === 'INSTANCE' && r.status === 'NOT_COMPLIANT'
);
```

### Display Sections:

```jsx
<Section title="Managed Instances" icon="✅">
  {managedInstances.map(inst => (
    <InstanceCard
      instance={inst}
      badge="Managed"
      color="green"
      actions={[]} // No actions needed
    />
  ))}
</Section>

<Section title="Potential Wastage" icon="⚠️">
  {wastageInstances.map(inst => (
    <InstanceCard
      instance={inst}
      badge="Review Needed"
      color="yellow"
      actions={['Terminate', 'Authorize']}
    />
  ))}
</Section>

<Section title="External Workloads" icon="🔗">
  {unmanagedInstances.filter(i => i.is_compliant).map(inst => (
    <InstanceCard
      instance={inst}
      badge="External"
      color="blue"
      actions={['Import to Spot Optimizer']}
    />
  ))}
</Section>

<Section title="Compliance Issues" icon="🏷️">
  {complianceIssues.map(inst => (
    <InstanceCard
      instance={inst}
      badge="Fix Tags"
      color="orange"
      actions={['Add Tags']}
    />
  ))}
</Section>
```

---

## Opt-In Workflow for Wastage Detection

### For Customers to Mark Instances for Review:

1. **Manual Tagging** (AWS Console or CLI):
   ```bash
   aws ec2 create-tags \
     --resources i-0abc123 \
     --tags Key=spot-optimizer:review,Value=true
   ```

2. **Bulk Tagging via Spot Optimizer UI**:
   - Navigate to "External Workloads" section
   - Select instances
   - Click "Mark for Review"
   - System adds `spot-optimizer:review=true` tag

3. **Automatic Detection Rules** (Future Enhancement):
   - Instances idle > 14 days → Auto-tag for review
   - Instances with high CPU/memory waste → Auto-tag
   - Instances in dev/test without recent usage → Auto-tag

---

## Benefits of This Approach

### 1. ✅ Full Visibility
- Shows **ALL** instances (managed + unmanaged)
- Clear distinction between authorized and unauthorized

### 2. ✅ Conservative by Default
- Only counts as wastage what customer explicitly marks
- Respects external workloads managed by other teams

### 3. ✅ Accurate Savings
- No inflation by counting legitimate workloads
- Savings match customer expectations

### 4. ✅ Compliance Tracking
- Separates wastage from tagging issues
- Helps enforce organizational tagging policies

### 5. ✅ Actionable Insights
- Managed: "Keep as-is"
- Unauthorized: "Terminate or authorize"
- Non-compliant: "Fix tags"
- External: "Import or ignore"

---

## Migration Notes

### Backwards Compatibility
- Existing authorized/unauthorized detection still works
- No database schema changes required
- No API breaking changes

### Customer Communication
```
Subject: New Instance Visibility in Resource Hygiene

We've enhanced the Resource Hygiene dashboard to show ALL instances:

- ✅ Managed Instances: Your cluster nodes (authorized)
- ⚠️ Potential Wastage: Instances you mark for review
- 🏷️ Compliance Issues: Instances missing required tags
- 🔗 External Workloads: Properly tagged instances managed elsewhere

To mark an instance for wastage review, add tag:
  spot-optimizer:review=true

This gives you full visibility while keeping savings calculations accurate.
```

---

## Testing Scenarios

### Scenario 1: EKS Cluster with External Database
- **Expected**: EKS nodes show as "Managed", RDS instance shows as "External Workload"
- **Savings**: $0 (both are legitimate)

### Scenario 2: Forgotten Test Instance
- **Setup**: Tag with `spot-optimizer:review=true`
- **Expected**: Shows in "Potential Wastage" with cost
- **Savings**: Instance monthly cost

### Scenario 3: Untagged Instances
- **Expected**: Shows in "Compliance Issues", NOT wastage
- **Action**: Customer adds required tags
- **Savings**: $0 (not wastage)

### Scenario 4: Multi-Team Account
- **Team A**: Uses Spot Optimizer (managed)
- **Team B**: Uses Terraform (external, properly tagged)
- **Expected**: Both show as authorized, zero conflict

---

**Document Date**: 2026-02-10
**Status**: ✅ Implemented
**API Version**: v1
