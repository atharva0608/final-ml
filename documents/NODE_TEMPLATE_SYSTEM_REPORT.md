# Node Template System — Full Audit Report

> Covers: Design · Database Schema · API Endpoints · Live Enforcement · What Works · What Doesn't · Gap Analysis · Honest Assessment

---

## Executive Summary

The Node Template system is **~60% implemented**. It has a clean, well-designed 3-layer architecture (model → version → cluster mapping), a complete frontend UI with 28 editable fields, and full CRUD API endpoints. However, only **~40% of the constraint fields actually influence real decisions**. Several fields — including `optimization_policy`, `savings_threshold`, `risk_threshold`, `workload_scope`, and `substitute_strategy` — are stored in the database but never read by the backend decision engine. The validation endpoint is a hardcoded stub.

**Bottom line:** Assigning a Node Template to a cluster will filter `allowed_families`, `excluded_families`, `allowed_zones`, and `architectures` in real pool selection. Everything else is silently ignored.

---

## Table of Contents

1. [System Design Intent](#1-system-design-intent)
2. [Database Model (3-Layer Design)](#2-database-model-3-layer-design)
3. [Constraint Specification (Full Schema)](#3-constraint-specification-full-schema)
4. [API Endpoints](#4-api-endpoints)
5. [Where Templates Are Actually Enforced](#5-where-templates-are-actually-enforced)
6. [Where Templates Are Silently Ignored](#6-where-templates-are-silently-ignored)
7. [Per-Constraint Enforcement Matrix](#7-per-constraint-enforcement-matrix)
8. [Frontend UI](#8-frontend-ui)
9. [The Broken Validation Endpoint](#9-the-broken-validation-endpoint)
10. [Honest Assessment: What Works vs What Doesn't](#10-honest-assessment-what-works-vs-what-doesnt)
11. [Recommended Fixes](#11-recommended-fixes)
12. [File Reference Map](#12-file-reference-map)

---

## 1. System Design Intent

A Node Template is meant to be a **governance contract** that constrains what kinds of EC2 instances the auto-rebalancer and right-sizer are allowed to provision for a cluster. The design intent is:

> "As a platform engineer, I want to say: this cluster may only use AMD64 instances, from the m-family or c-family, with at most 32 vCPUs, in us-east-1a or us-east-1b, and only pick spot if savings exceed 10%."

Templates are **versioned** (so changes are auditable and reversible) and assigned per-cluster via a mapping table (so different clusters can have different policies).

The design is correct and clean. The enforcement is incomplete.

---

## 2. Database Model (3-Layer Design)

**File:** `backend/models/node_template.py` (84 lines)

Three tables form a complete versioned-assignment system:

### Table 1: `node_templates` — Identity

```python
class NodeTemplate(Base):
    __tablename__ = "node_templates"

    id         = Column(UUID, primary_key=True, default=uuid4)
    name       = Column(String, nullable=False, unique=True)
    scope      = Column(Enum("GLOBAL", "CLUSTER"), default="GLOBAL")
    created_by = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    versions = relationship("NodeTemplateVersion", back_populates="template")
    mappings = relationship("ClusterTemplateMapping", back_populates="template")
```

`scope` distinguishes global templates (available to any cluster) from cluster-scoped ones.

---

### Table 2: `node_template_versions` — Immutable Constraint Envelope

```python
class NodeTemplateVersion(Base):
    __tablename__ = "node_template_versions"

    id             = Column(UUID, primary_key=True, default=uuid4)
    template_id    = Column(UUID, ForeignKey("node_templates.id"), nullable=False)
    version_number = Column(Integer, nullable=False)
    status         = Column(Enum("DRAFT", "ACTIVE", "ARCHIVED"), default="DRAFT")
    constraints_json = Column(JSONB)          # ← The entire constraint spec lives here

    # Relationships
    template = relationship("NodeTemplate", back_populates="versions")
    mappings = relationship("ClusterTemplateMapping", back_populates="version")
```

`constraints_json` is a JSONB blob — it stores ALL constraint fields as a single document. This means constraints are **not individually indexed or validated at the DB layer**.

**Versioning model:**
- Creating a template auto-creates Version 1 (status=ACTIVE)
- Creating a new version auto-activates it and archives the previous
- Old versions are preserved (full audit trail)
- Only ACTIVE versions can be assigned to clusters

---

### Table 3: `cluster_template_mappings` — Assignment Registry

```python
class ClusterTemplateMapping(Base):
    __tablename__ = "cluster_template_mappings"

    id          = Column(UUID, primary_key=True, default=uuid4)
    cluster_id  = Column(String, ForeignKey("clusters.id"), nullable=False, index=True)
    template_id = Column(UUID, ForeignKey("node_templates.id"), nullable=False)
    version_id  = Column(UUID, ForeignKey("node_template_versions.id"), nullable=False)
    is_default  = Column(Boolean, default=False)
    assigned_at = Column(DateTime, default=datetime.utcnow)

    # UNIQUE constraint: only one default per cluster
    __table_args__ = (UniqueConstraint("cluster_id", "is_default",
                      name="uq_cluster_default_template"),)

    # Relationships
    template = relationship("NodeTemplate", back_populates="mappings")
    version  = relationship("NodeTemplateVersion", back_populates="mappings")
```

**Key design decisions:**
- `is_default=True` — the enforcement paths only ever read the default mapping
- A cluster can have multiple template assignments but only one default
- Assignment is at the VERSION level (not just template) — pinned to exact constraint spec
- When a cluster has no default mapping → all templates are globally unconstrained

---

## 3. Constraint Specification (Full Schema)

**File:** `backend/schemas/node_template_schemas.py` (98 lines)

### Pydantic Schema (Backend-Validated Fields)

```python
class NodeTemplateConstraints(BaseModel):

    # Architecture
    architectures: List[str] = ["amd64"]
    # Valid values: "amd64", "arm64", "x86_64"

    # vCPU bounds
    min_vcpu: int = Field(default=2, ge=1)
    max_vcpu: int = Field(default=64, ge=1)

    # Memory bounds (GiB)
    min_memory: float = Field(default=4.0, ge=0.5)
    max_memory: float = Field(default=256.0, ge=0.5)

    # Instance family filter
    allowed_families: List[str] = []         # Empty = allow all families
    excluded_families: List[str] = ["metal", "g", "p", "trn", "inf", "i"]
    # Common exclusions: GPU (g/p), Trainium (trn), Inferentia (inf), storage-opt (i), bare metal

    # Availability zone filter
    allowed_zones: List[str] = []            # Empty = allow all AZs
    cross_az_rebalance: bool = True          # Allow moving between AZs

    # Policy
    optimization_policy: str = "COST_FIRST"
    # Options: "COST_FIRST", "NO_DOWNTIME_FIRST", "BALANCED"

    savings_threshold: float = Field(default=5.0, ge=0.0, le=100.0)
    # Minimum savings % required to recommend a change
```

**10 fields defined here.** These are the only fields with server-side Pydantic validation.

---

### Frontend-Only Fields (Stored in constraints_json but NOT in schema)

These 8 fields are sent by the frontend, stored in the JSONB blob, but **never validated by Pydantic and never enforced by any backend service**:

```javascript
// frontend/src/pages/NodeTemplates.jsx — DEFAULT_CONSTRAINTS (lines 16-34)
{
    workload_scope:       'STATELESS_ONLY',  // 'STATELESS_ONLY' | 'MIXED'
    stateful_protected:   true,              // bool
    risk_threshold:       10.0,              // max interruption % (0-100)
    allow_spot:           true,              // bool
    allow_ondemand:       true,              // bool
    substitute_strategy:  'PREWARMED',       // 'PREWARMED' | 'ON_DEMAND' | 'DISABLED'
    // Legacy field name aliases:
    min_memory_gb:        4.0,              // same as min_memory
    max_memory_gb:        256.0,            // same as max_memory
}
```

These fields appear in the constraint editor UI, can be saved, and are visible when reading back a template. They do nothing.

---

## 4. API Endpoints

**File:** `backend/api/node_template_routes.py` (310 lines)

### Global Template Registry

| Method | Path | Auth | Lines | Status |
|--------|------|------|-------|--------|
| `GET` | `/api/v1/node-templates` | `get_current_user` | 32–55 | ✅ Working |
| `POST` | `/api/v1/node-templates` | `RequireAccess("EXECUTION")` | 57–90 | ✅ Working |
| `DELETE` | `/api/v1/node-templates/{id}` | `RequireAccess("EXECUTION")` | 291–310 | ✅ Working |

**GET** returns all templates with `version_count` and `cluster_count` (attachment count).

**POST** body:
```json
{
  "name": "production-standard",
  "scope": "GLOBAL",
  "constraints": {
    "architectures": ["amd64"],
    "min_vcpu": 2,
    "max_vcpu": 16,
    "allowed_families": ["m5", "m6i", "c5", "c6i"],
    "excluded_families": ["metal", "g", "p"]
  }
}
```
Auto-creates Version 1 with status=ACTIVE.

---

### Template Versioning

| Method | Path | Auth | Lines | Status |
|--------|------|------|-------|--------|
| `GET` | `/api/v1/node-templates/{id}/versions` | `get_current_user` | 92–106 | ✅ Working |
| `POST` | `/api/v1/node-templates/{id}/versions` | `RequireAccess("EXECUTION")` | 108–141 | ✅ Working |

**POST new version** auto-activates the new version and archives the previous ACTIVE version.

---

### Cluster Assignment

| Method | Path | Auth | Lines | Status |
|--------|------|------|-------|--------|
| `GET` | `/api/v1/clusters/{id}/node-template/active` | `get_current_user` | 145–186 | ✅ Working |
| `POST` | `/api/v1/clusters/{id}/node-template/assign` | `RequireAccess("EXECUTION")` | 188–252 | ✅ Working |

**GET active mapping** returns:
```json
{
  "template_id": "...",
  "template_name": "production-standard",
  "version_number": 2,
  "version_status": "ACTIVE",
  "assigned_at": "2026-04-01T10:30:00Z",
  "constraints": { ... }
}
```

**POST assign** payload:
```json
{
  "template_id": "...",
  "version_id": "..."
}
```
Revokes the previous `is_default=True` mapping and creates a new one. Previous mapping record is kept (audit trail).

---

### Validation (BROKEN)

| Method | Path | Auth | Lines | Status |
|--------|------|------|-------|--------|
| `POST` | `/api/v1/node-templates/validate` | `get_current_user` | 254–289 | ❌ Stub |

**What it should do:** Query the instance catalog, count how many pools satisfy the constraints, return a realistic preview.

**What it actually does:**
```python
# backend/api/node_template_routes.py lines 275–289
candidates = 24                    # HARDCODED
if len(payload.allowed_families) == 1:
    candidates = 4                 # HARDCODED
is_valid = candidates >= 5         # Always True unless 1 allowed family
estimated_savings_pct = 68.5       # HARDCODED — always 68.5%
sample_instances = ["c6i.xlarge", "m5.large", "r6g.large"]  # HARDCODED
```

The UI shows a "68.5% savings" preview for every template regardless of what constraints you set. This is misleading.

---

## 5. Where Templates Are Actually Enforced

### 5.1 Pool Ranking Service — PRIMARY ENFORCEMENT PATH

**File:** `backend/services/pool_ranking_service.py` lines 2244–2262

This is the **most important enforcement point** — called from the auto-rebalancer's primary pool selection loop.

```python
# pool_ranking_service.py: rank_pools_for_node() method
# Lines 2244–2262

if include_dynamic_filters:
    try:
        _ctm = self.db.query(ClusterTemplateMapping).filter_by(
            cluster_id=cluster_id,
            is_default=True
        ).first()

        if _ctm and _ctm.version and _ctm.version.constraints_json:
            _tc = _ctm.version.constraints_json
            if isinstance(_tc, dict):
                # ✅ allowed_families enforced
                _af = _tc.get('allowed_families') or []
                if _af:
                    allowed_families = list(_af)

                # ✅ excluded_families enforced
                _ef = _tc.get('excluded_families')
                if _ef:
                    excluded_families = list(_ef)

                # ✅ allowed_zones enforced
                _az_list = _tc.get('allowed_zones') or []
                if _az_list:
                    allowed_zones = list(_az_list)

                # ✅ cross_az_rebalance enforced
                cross_az_rebalance = bool(_tc.get('cross_az_rebalance', True))
    except Exception:
        pass   # ⚠️ SILENT FALLBACK — constraints dropped on any DB error
```

**Constraints enforced here:** `allowed_families`, `excluded_families`, `allowed_zones`, `cross_az_rebalance`

**How they're applied (downstream in the method):**

```python
# Lines 2337–2395: Filter candidate pools

for pool in candidate_pools:
    family = pool['instance_type'].split('.')[0]   # "m5", "c6i", etc.

    # Whitelist check
    if allowed_families and family not in allowed_families:
        continue   # ← Pool excluded

    # Blacklist check
    if family in excluded_families:
        continue   # ← Pool excluded

    # AZ check
    if allowed_zones and pool['az'] not in allowed_zones:
        continue   # ← Pool excluded

    # Cross-AZ check (if disabled: must stay in same AZ as source)
    if not cross_az_rebalance and pool['az'] != source_az:
        continue   # ← Pool excluded

    filtered_pools.append(pool)
```

**Called from auto-rebalancer:**
- Primary path: `auto_rebalancer.py:971–985` — `rank_pools_for_node(include_dynamic_filters=True)`
- Fallback path: `auto_rebalancer.py:5133–5148` — same call with same flag
- Both paths use `include_dynamic_filters=True` → template enforcement is ACTIVE in both

---

### 5.2 Auto-Rebalancer — Architecture Constraint Only

**File:** `backend/workers/tasks/auto_rebalancer.py` lines 1088–1122

The auto-rebalancer independently enforces the `architectures` constraint on top of what pool ranking does:

```python
# Lines 1091–1099: Load template architecture constraint
_ctm = db.query(ClusterTemplateMapping).filter(
    ClusterTemplateMapping.cluster_id == action.cluster_id,
    ClusterTemplateMapping.is_default == True
).first()

_template_archs = set()
if _ctm and _ctm.version and _ctm.version.constraints_json:
    _tc = _ctm.version.constraints_json
    if isinstance(_tc, dict) and 'architecture' in _tc:
        _template_archs = set(_tc['architecture'])   # ✅ ENFORCED

# Lines 1104–1122: Apply architecture filter
if _template_archs:
    _has_arm = bool(_template_archs & {'arm64'})
    _has_amd = bool(_template_archs & {'amd64', 'x86_64'})
    if _has_arm and not _has_amd:
        _want_arm = True    # ARM64 only → Graviton instances only
    elif _has_amd and not _has_arm:
        _want_arm = False   # AMD64 only → x86 instances only
    # Both → no filter (mixed arch allowed)
```

**Note:** The key read here is `'architecture'` (singular) not `'architectures'` (plural). The schema uses `architectures` (plural). This is a **key name mismatch** — if the frontend sends `architectures: ["amd64"]`, this code reads `architecture` and finds nothing. It only works if the constraints_json was manually written with the singular key.

---

### 5.3 Right-Sizing Service — Full Constraint Filter

**File:** `backend/services/rightsizing_service.py` lines 692–731

This is the **most complete** constraint enforcement — checks vCPU, memory, and family constraints:

```python
# Lines 692–698: Load template
active_mapping = db.query(ClusterTemplateMapping).filter_by(
    cluster_id=cluster_id, is_default=True
).first()

template_constraints = {}
if active_mapping and active_mapping.version_id:
    version = db.query(NodeTemplateVersion).get(active_mapping.version_id)
    if version and version.constraints_json:
        template_constraints = version.constraints_json

# Lines 700–731: Apply constraints to right-sizing recommendations
if template_constraints:
    template_filtered = []
    for rec in filtered_recs:
        proposed_family = proposed_type.split('.')[0]

        min_v = template_constraints.get("min_vcpu", 1)
        max_v = template_constraints.get("max_vcpu", 256)
        min_m = template_constraints.get("min_memory_gb",  # tries both field names
                template_constraints.get("min_memory", 1))
        max_m = template_constraints.get("max_memory_gb",
                template_constraints.get("max_memory", 1024))
        allowed  = template_constraints.get("allowed_families", [])
        excluded = template_constraints.get("excluded_families", [])

        # ✅ Enforce vCPU bounds
        if not (min_v <= proposed_vcpu <= max_v):
            continue

        # ✅ Enforce memory bounds
        if not (min_m <= proposed_memory_gb <= max_m):
            continue

        # ✅ Enforce allowed_families whitelist
        if allowed and proposed_family not in allowed:
            continue

        # ✅ Enforce excluded_families blacklist
        if proposed_family in excluded:
            continue

        template_filtered.append(rec)

    logger.info(f"Template enforcement: {len(filtered_recs)} → {len(template_filtered)} "
                f"recommendations after constraint filter")
```

**Constraints enforced:** `min_vcpu`, `max_vcpu`, `min_memory`, `max_memory`, `allowed_families`, `excluded_families`

---

### 5.4 Which Code Paths Call These Enforcement Points?

```
User enables auto_rebalance or auto_rightsizing
          │
          ▼
auto_rebalancer.py (30s cycle)
  ├─ Primary pool selection
  │    └─ rank_pools_for_node(include_dynamic_filters=True)
  │         └─ ✅ Loads template: allowed_families, excluded_families, allowed_zones
  │
  ├─ Architecture check (direct)
  │    └─ ✅ Loads template: architectures (⚠️ key name mismatch)
  │
  └─ Auto-rightsizing path
       └─ rightsizing_service.generate_recommendations()
            └─ ✅ Loads template: vCPU, memory, families
```

---

## 6. Where Templates Are Silently Ignored

### 6.1 `rank_pools_for_size()` — Secondary Pool Selection

**File:** `backend/services/pool_ranking_service.py:2056+`

This is the fallback pool selection method called in some paths. It does NOT load templates. If the primary `rank_pools_for_node()` path fails and this gets called, template constraints are bypassed.

### 6.2 Emergency Rebalancer — No Template Awareness

**File:** `backend/workers/tasks/emergency_rebalancer.py`

Emergency rebalancing decisions make no reference to `ClusterTemplateMapping`. When an emergency triggers (e.g., mass spot interruption), replacement pools are selected without template filters.

**Impact:** During an emergency, the rebalancer might select instance families that the template explicitly excluded.

### 6.3 Cost Calculator — Template-Blind

**File:** `backend/workers/tasks/cost_calculator.py`

Cost calculations don't account for template constraints. Savings projections shown in the UI may include pools that would be filtered by the template.

### 6.4 Decision Engine Agent — Legacy, Not Integrated

**File:** `backend/agents/decision_engine_agent.py` lines 260–277

Has a `_matches_template()` method designed for template filtering:
```python
def _matches_template(self, instance_type: str, template: Dict) -> bool:
    allowed_families = template.get('allowed_families', [])
    if allowed_families and instance_type.split('.')[0] not in allowed_families:
        return False
    allowed_sizes = template.get('allowed_sizes', [])
    if allowed_sizes and instance_type.split('.')[-1] not in allowed_sizes:
        return False
    excluded = template.get('excluded_instance_types', [])
    if instance_type in excluded:
        return False
    return True
```

This method exists but is not called from any active code path. The legacy agent system is not integrated with the current auto-rebalancer.

### 6.5 ML Template Filter Module — Designed but Not Wired

**File:** `ml_model/decision_engine/08_template_filter.py` lines 92–144

A complete `apply_template_filter()` function exists in the ML model directory:
```python
def apply_template_filter(candidate_pools: List[Dict], template: Dict) -> List[Dict]:
    whitelist   = template.get("instance_families", [])
    blacklist   = set(template.get("blacklisted_pools", []))
    max_vcpu    = template.get("max_vcpu", 0)
    max_memory  = template.get("max_memory_gb", 0)
    # ... filter logic
    return filtered
```

This function is never called by any backend service or worker. It exists as a standalone ML pipeline filter.

---

## 7. Per-Constraint Enforcement Matrix

| Constraint Field | In Schema | In DB | Auto-Rebalancer | Pool Ranking | Rightsizing | Emergency | Notes |
|---|:---:|:---:|:---:|:---:|:---:|:---:|---|
| `architectures` | ✅ | ✅ | ✅ Partial | ✅ Indirect | — | ❌ | ⚠️ Key name bug: reads `'architecture'` not `'architectures'` |
| `allowed_families` | ✅ | ✅ | — | ✅ **ENFORCED** | ✅ **ENFORCED** | ❌ | Primary enforcement path |
| `excluded_families` | ✅ | ✅ | — | ✅ **ENFORCED** | ✅ **ENFORCED** | ❌ | Primary enforcement path |
| `allowed_zones` | ✅ | ✅ | — | ✅ **ENFORCED** | ❌ | ❌ | AZ filter works in pool ranking |
| `cross_az_rebalance` | ✅ | ✅ | — | ✅ **ENFORCED** | ❌ | ❌ | Controls same-AZ preference |
| `min_vcpu` | ✅ | ✅ | ❌ | ✅ Indirect | ✅ **ENFORCED** | ❌ | Via node resource floor in pool ranking |
| `max_vcpu` | ✅ | ✅ | ❌ | ✅ Filtered | ✅ **ENFORCED** | ❌ | |
| `min_memory` | ✅ | ✅ | ❌ | ✅ Via node floor | ✅ **ENFORCED** | ❌ | |
| `max_memory` | ✅ | ✅ | ❌ | ✅ Filtered | ✅ **ENFORCED** | ❌ | |
| `optimization_policy` | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ | **NEVER ENFORCED** — UI only |
| `savings_threshold` | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ | **NEVER ENFORCED** — UI only |
| `workload_scope` | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ | Not in schema, not enforced |
| `stateful_protected` | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ | Not in schema, not enforced |
| `risk_threshold` | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ | Not in schema, not enforced |
| `allow_spot` | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ | Not in schema, not enforced |
| `allow_ondemand` | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ | Not in schema, not enforced |
| `substitute_strategy` | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ | Not in schema, not enforced |

**Legend:**
- ✅ = Enforced
- ❌ = Not enforced / ignored
- — = Not applicable to this path
- ⚠️ = Partially working with caveat

---

## 8. Frontend UI

### 8.1 NodeTemplateTab (Cluster Detail — Read Display)

**File:** `frontend/src/components/clusters/NodeTemplateTab.jsx` (186 lines)

This tab appears in the Cluster Details view under "Node Template". It shows the currently assigned template and its constraints.

**What it displays:**
- Template name and version number
- Workload Scope (from `workload_scope` field)
- Policy Objective (`optimization_policy`)
- Max Interruption Risk (`risk_threshold` %)
- Min Expected Savings (`savings_threshold` %)
- vCPU bounds (min/max)
- Memory bounds (min/max)
- Provisioning Strategy (`substitute_strategy`)

**What it allows:**
- Dropdown to select from available global templates
- "Set as Cluster Default" button → calls `nodeTemplateAPI.assignToCluster()`

**Status:** Fully functional for assignment. Read-only display — no inline editing.

---

### 8.2 NodeTemplates Page (Global Registry)

**File:** `frontend/src/pages/NodeTemplates.jsx` (~68 KB)

The full template management page with 3 tabs:

#### Tab 1: Editor
A constraint editor with 28 fields:

```javascript
const DEFAULT_CONSTRAINTS = {
    // Architecture
    architectures: ['amd64'],

    // Compute bounds
    min_vcpu: 2,       max_vcpu: 64,
    min_memory: 4.0,   max_memory: 256.0,

    // Instance family filters
    allowed_families: [],
    excluded_families: ['metal', 'g', 'p', 'trn', 'inf', 'i'],

    // Availability zone
    allowed_zones: [],
    cross_az_rebalance: true,

    // Policy (stored but not enforced)
    optimization_policy: 'COST_FIRST',
    savings_threshold: 5.0,
    risk_threshold: 10.0,

    // Lifecycle (stored but not enforced)
    allow_spot: true,
    allow_ondemand: true,
    workload_scope: 'STATELESS_ONLY',
    stateful_protected: true,
    substitute_strategy: 'PREWARMED',
};
```

**UI elements:**
- Architecture multi-select chips (amd64, arm64)
- vCPU/memory range sliders
- Instance family selector (common families: m5, m6i, c5, c6i, r5, etc.)
- Exclusion family chips (GPU, metal, etc.)
- AZ multi-select (populated from cluster's region)
- Policy dropdown (COST_FIRST / NO_DOWNTIME_FIRST / BALANCED)
- Risk threshold slider (0–100%)
- Savings threshold slider (0–100%)
- Spot/OD toggle switches
- Workload scope selector
- Substitute strategy selector

#### Tab 2: Impact Preview
Calls `POST /api/v1/node-templates/validate` → displays:
- "24 candidate pools" (hardcoded)
- "68.5% estimated savings" (hardcoded)
- 3 sample instance types (hardcoded)

**This is misleading** — the preview shows fake data regardless of what constraints are set.

#### Tab 3: Audit
Shows version history — list of all versions with status badges (DRAFT, ACTIVE, ARCHIVED) and creation timestamps.

---

### 8.3 Frontend API Calls

**File:** `frontend/src/services/api.js` lines 211–225

```javascript
export const nodeTemplateAPI = {
    // Global Registry CRUD
    getGlobalTemplates:   ()                           => api.get('/api/v1/node-templates'),
    createGlobalTemplate: (data)                       => api.post('/api/v1/node-templates', data),
    deleteGlobalTemplate: (id)                         => api.delete(`/api/v1/node-templates/${id}`),

    // Version management
    getVersions:          (templateId)                 => api.get(`/api/v1/node-templates/${templateId}/versions`),
    createVersion:        (templateId, data)           => api.post(`/api/v1/node-templates/${templateId}/versions`, data),

    // Cluster assignment
    getActiveMapping:     (clusterId)                  => api.get(`/api/v1/clusters/${clusterId}/node-template/active`),
    assignToCluster:      (clusterId, templateId, versionId) =>
                              api.post(`/api/v1/clusters/${clusterId}/node-template/assign`,
                                       { template_id: templateId, version_id: versionId }),

    // Validation (broken stub)
    validate:             (data)                       => api.post('/api/v1/node-templates/validate', data),
};
```

---

## 9. The Broken Validation Endpoint

**File:** `backend/api/node_template_routes.py` lines 254–289

This is the most significant gap for user experience. The full implementation:

```python
@router.post("/validate")
def validate_template(payload: NodeTemplateConstraints, ...):
    """Validates constraints and returns candidate pool preview."""

    # ❌ HARDCODED — should query actual instance catalog
    candidates = 24
    if len(payload.allowed_families) == 1:
        candidates = 4

    is_valid = candidates >= 5    # Always True unless exactly 1 allowed_family

    # ❌ HARDCODED — should compute from Redis market_view_cache
    estimated_savings_pct = 68.5

    # ❌ HARDCODED — should come from actual pool query
    sample_instances = ["c6i.xlarge", "m5.large", "r6g.large"]

    return {
        "valid": is_valid,
        "candidate_pool_count": candidates,
        "estimated_savings_pct": estimated_savings_pct,
        "sample_instances": sample_instances,
        "warnings": []
    }
```

**What should be here:**
```python
# Correct implementation would:
# 1. Load market_view_cache:{region} from Redis
# 2. Apply the submitted constraints as filters
# 3. Count matching pools
# 4. Return real savings estimate from filtered pool set
# 5. Warn if constraints are too restrictive (< 5 pools)
```

---

## 10. Honest Assessment: What Works vs What Doesn't

### What Works (Active in Production)

**Template CRUD:**
All create/read/update/delete operations work correctly. Templates are properly versioned. Cluster assignments are properly stored. The audit trail (version history) works.

**Pool Selection Filtering:**
When a template is assigned to a cluster and `allowed_families` / `excluded_families` / `allowed_zones` are set, pool ranking service WILL enforce these. Every real auto-rebalancer cycle uses `include_dynamic_filters=True`, so these constraints are live.

**Example:** If you set `allowed_families: ["m6i", "c6i"]` on cluster X, the auto-rebalancer will NEVER recommend a `t3.large` or `r5.xlarge` for that cluster. This works today.

**Right-Sizing Filtering:**
Right-sizing proposals will be filtered against `min_vcpu`, `max_vcpu`, `min_memory`, `max_memory`, `allowed_families`, and `excluded_families`. This is fully enforced with logging.

---

### What Doesn't Work (Silent No-Ops)

**`optimization_policy` — Completely Ignored:**
Setting `NO_DOWNTIME_FIRST` vs `COST_FIRST` has zero effect on the auto-rebalancer's decision algorithm. The field is stored and displayed but no code path reads it.

**`savings_threshold` — Completely Ignored:**
Setting a minimum 15% savings threshold has no effect. The rebalancer will still recommend a pool saving 3%.

**`risk_threshold` — Completely Ignored:**
Setting a maximum 10% interruption risk has no effect. The rebalancer uses `risk_ceiling_percent` from `ClusterOptimizationSettings`, not from the template.

**`workload_scope`, `allow_spot`, `allow_ondemand`, `substitute_strategy` — Completely Ignored:**
All stored, none enforced.

**Architecture Constraint — Partially Broken:**
The key name mismatch (`'architecture'` vs `'architectures'`) means this constraint may not be read correctly depending on how the template was originally created.

**Validation Endpoint — Misleading:**
Shows `68.5%` savings for every template regardless of how restrictive the constraints are.

**Emergency Rebalancer — Template-Blind:**
During real emergencies (mass spot interruption), template constraints are bypassed.

---

### Overall Implementation Score

| Dimension | Score | Notes |
|-----------|-------|-------|
| Data model | 9/10 | Clean 3-layer versioned design |
| CRUD API | 9/10 | All operations work correctly |
| Frontend UI | 8/10 | Beautiful, complete, but shows fake validation |
| Pool family filtering | 8/10 | Works in primary path, silent fallback on error |
| vCPU/memory filtering | 7/10 | Works in rightsizing, indirect in pool ranking |
| Architecture filtering | 4/10 | Key name bug, emergency bypass |
| Policy enforcement | 0/10 | Stored only, never read |
| Validation preview | 0/10 | Hardcoded stub |
| Emergency coverage | 0/10 | Templates bypassed |
| **Overall** | **~6/10** | Core filtering works, policy layer missing |

---

## 11. Recommended Fixes

### Fix 1 — Key Name Bug (Quick Fix)
**File:** `backend/workers/tasks/auto_rebalancer.py:1099`

```python
# BROKEN — reads 'architecture' (singular)
if isinstance(_tc, dict) and 'architecture' in _tc:
    _template_archs = set(_tc['architecture'])

# FIX — read both to handle either format
if isinstance(_tc, dict):
    _arch_val = _tc.get('architectures') or _tc.get('architecture') or []
    if _arch_val:
        _template_archs = set(_arch_val)
```

---

### Fix 2 — Real Validation Endpoint (Medium effort)
**File:** `backend/api/node_template_routes.py:254–289`

Replace the stub with:
```python
from backend.services.pool_ranking_service import PoolRankingService

@router.post("/validate")
def validate_template(payload: NodeTemplateConstraints, db=Depends(get_db), redis=Depends(get_redis)):
    # Load market_view_cache for the user's region
    region = "ap-south-1"   # or from query param
    raw = redis.get(f"market_view_cache:{region}")
    pools = json.loads(raw) if raw else []

    # Apply constraints
    allowed  = set(payload.allowed_families) if payload.allowed_families else None
    excluded = set(payload.excluded_families or [])

    filtered = [
        p for p in pools
        if (not allowed or p['instance_type'].split('.')[0] in allowed)
        and p['instance_type'].split('.')[0] not in excluded
        and p.get('vcpu', 0) >= payload.min_vcpu
        and p.get('vcpu', 0) <= payload.max_vcpu
        and p.get('memory_gb', 0) >= payload.min_memory
        and p.get('memory_gb', 0) <= payload.max_memory
    ]

    savings_vals = [p.get('savings_pct', 0) for p in filtered if p.get('savings_pct')]
    avg_savings = sum(savings_vals) / len(savings_vals) if savings_vals else 0
    sample = [p['instance_type'] for p in filtered[:3]]

    return {
        "valid": len(filtered) >= 5,
        "candidate_pool_count": len(filtered),
        "estimated_savings_pct": round(avg_savings, 1),
        "sample_instances": sample,
        "warnings": ["Very restrictive — fewer than 5 pools match"] if len(filtered) < 5 else []
    }
```

---

### Fix 3 — Enforce `risk_threshold` (Medium effort)

Connect template's `risk_threshold` to the pool ranking filter:

```python
# In pool_ranking_service.py rank_pools_for_node() template loading block:
_rt = _tc.get('risk_threshold')
if _rt is not None:
    risk_ceiling = float(_rt) / 100.0   # Convert % to 0-1 scale
    # Apply: filter out pools where risk_probability > risk_ceiling
```

---

### Fix 4 — Enforce `savings_threshold` (Small effort)

```python
# In pool_ranking_service.py, after family/zone filter:
_st = _tc.get('savings_threshold', 5.0)
filtered_pools = [p for p in filtered_pools
                  if p.get('savings_pct', 0) >= _st]
```

---

### Fix 5 — Add Silent Fallback Logging

```python
# pool_ranking_service.py:2261–2262
except Exception as e:
    logger.warning(f"Template constraint load failed for cluster {cluster_id}: {e} "
                   f"— proceeding without template filters")
    # (currently: bare `pass` with no logging)
```

---

## 12. File Reference Map

| Purpose | File | Key Lines |
|---------|------|-----------|
| DB Models | `backend/models/node_template.py` | 1–84 (all) |
| Pydantic Schema | `backend/schemas/node_template_schemas.py` | 1–98 (all) |
| API Routes | `backend/api/node_template_routes.py` | 32–310 (all) |
| Stub validation | `backend/api/node_template_routes.py` | 254–289 |
| Pool Ranking Enforcement | `backend/services/pool_ranking_service.py` | 2244–2262, 2337–2395 |
| Right-Sizing Enforcement | `backend/services/rightsizing_service.py` | 692–731 |
| Auto-Rebalancer Architecture | `backend/workers/tasks/auto_rebalancer.py` | 1088–1122 |
| Auto-Rebalancer Pool Call | `backend/workers/tasks/auto_rebalancer.py` | 971–985, 5133–5148 |
| Legacy Agent Filter | `backend/agents/decision_engine_agent.py` | 260–277 |
| ML Filter (unused) | `ml_model/decision_engine/08_template_filter.py` | 92–144 |
| Frontend Tab | `frontend/src/components/clusters/NodeTemplateTab.jsx` | 1–186 (all) |
| Frontend Page | `frontend/src/pages/NodeTemplates.jsx` | 16–34 (defaults), all |
| Frontend API | `frontend/src/services/api.js` | 211–225 |

---

*Document generated: 2026-04-03*
*Source files audited: 12 backend files + 3 frontend files*
