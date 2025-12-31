# Backend Pipelines Module

## Purpose

Optimization pipelines for different deployment types (standalone, Kubernetes, clusters).

**Last Updated**: 2025-12-25
**Authority Level**: MEDIUM-HIGH

---

## Files

### standalone_optimizer.py
**Purpose**: Optimization pipeline for standalone EC2 instances
**Lines**: ~250
**Key Functions**:
- `optimize_standalone_instance()` - Main optimization entry point
- `analyze_utilization()` - Analyze CPU/memory usage
- `recommend_resize()` - Suggest instance type changes
- `recommend_schedule()` - Start/stop scheduling recommendations

**Optimization Strategies**:
- Right-sizing based on utilization
- Stop/start scheduling for non-production
- Reserved Instance recommendations
- Spot Instance opportunities

**Dependencies**:
- backend/decision_engine/
- backend/executor/
- backend/database/models.py

**Recent Changes**:
- 2025-12-23: Enhanced utilization analysis

### linear_optimizer.py
**Purpose**: Linear programming-based optimization for cost minimization
**Lines**: ~1,000
**Key Components**:
- `LinearOptimizer` - Main optimizer class
- Linear programming formulation
- Constraint handling
- Solution interpreter

**Optimization Objective**:
Minimize: Total Cost
Subject to:
- Performance constraints (CPU, memory thresholds)
- Availability constraints (uptime requirements)
- Budget constraints
- Regional constraints

**Algorithm**: Likely uses scipy.optimize or PuLP library

**Use Cases**:
- Multi-instance portfolio optimization
- Budget allocation across instances
- Cost-performance trade-off analysis

**Dependencies**:
- scipy or PuLP (linear programming)
- numpy
- backend/database/models.py
- backend/decision_engine/scoring.py

**Recent Changes**: None recent

### kubernetes_optimizer.py
**Purpose**: Kubernetes cluster optimization (node and pod optimization)
**Lines**: ~550
**Key Features**:
- Node pool optimization
- Pod resource request/limit optimization
- Cluster autoscaling recommendations
- Multi-cluster cost optimization

**Optimization Areas**:
1. **Node Optimization**
   - Right-size node instance types
   - Optimize node count
   - Spot/on-demand mix

2. **Pod Optimization**
   - Resource request optimization
   - Vertical Pod Autoscaler (VPA) recommendations
   - Horizontal Pod Autoscaler (HPA) tuning

3. **Cost Optimization**
   - Reserved capacity planning
   - Spot instance integration
   - Multi-AZ cost balancing

**Dependencies**:
- kubernetes Python client
- backend/decision_engine/
- backend/database/models.py

**Recent Changes**: None recent

### cluster_optimizer.py
**Purpose**: General cluster optimization (non-Kubernetes clusters)
**Lines**: ~400
**Key Functions**:
- `optimize_cluster_size()` - Cluster size optimization
- `optimize_node_distribution()` - Node placement optimization
- `analyze_cluster_utilization()` - Cluster-wide utilization analysis

**Supported Cluster Types**:
- EMR (Elastic MapReduce)
- ECS (Elastic Container Service)
- Custom clusters

**Optimization Strategies**:
- Cluster size right-sizing
- Instance type mix optimization
- Spot instance integration
- Cost-aware workload scheduling

**Dependencies**:
- boto3 (for AWS cluster APIs)
- backend/decision_engine/
- backend/database/models.py

**Recent Changes**: None recent

### __init__.py
**Purpose**: Package initialization and exports
**Exports**: All optimizer classes

---

## Pipeline Selection

```
Instance/Deployment Type Detection
   ↓
   ├─ Standalone EC2 → standalone_optimizer.py
   ├─ Kubernetes → kubernetes_optimizer.py
   ├─ ECS/EMR Cluster → cluster_optimizer.py
   └─ Cost Optimization → linear_optimizer.py
```

---

## Dependencies

### Depends On:
- scipy/PuLP (linear programming)
- kubernetes Python client
- boto3
- backend/decision_engine/
- backend/executor/
- backend/database/models.py

### Depended By:
- backend/api/ (optimization endpoints)
- backend/jobs/waste_scanner.py
- Frontend optimization dashboard

**Impact Radius**: MEDIUM-HIGH (core optimization logic)

---

## Recent Changes

### 2025-12-25: Governance Structure Establishment
**Files Changed**: None (metadata only)
**Reason**: Document existing pipelines
**Impact**: No code changes, documentation baseline
**Reference**: `/index/recent_changes.md`

### 2025-12-23: Standalone Optimizer Enhancement
**Files Changed**: standalone_optimizer.py
**Reason**: Improve utilization analysis accuracy
**Impact**: Better optimization recommendations
**Reference**: Legacy documentation

---

## Usage

### Standalone Instance Optimization
```python
from backend.pipelines.standalone_optimizer import optimize_standalone_instance

result = optimize_standalone_instance(instance_id)
# Returns: recommendations with cost savings
```

### Linear Optimization Example
```python
from backend.pipelines.linear_optimizer import LinearOptimizer

optimizer = LinearOptimizer(instances, constraints)
solution = optimizer.solve()
# Returns: optimal instance configuration
```

### Kubernetes Optimization
```python
from backend.pipelines.kubernetes_optimizer import KubernetesOptimizer

k8s_opt = KubernetesOptimizer(cluster_config)
recommendations = k8s_opt.optimize_cluster()
```

---

## Known Issues

### None

Pipelines module is stable as of 2025-12-25.

---

_Last Updated: 2025-12-25_
_Authority: MEDIUM-HIGH - Optimization algorithms_
