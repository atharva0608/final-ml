# Frontend Components Lab Module

## Purpose

Experimental and ML-focused components for lab/research features.

**Last Updated**: 2025-12-25
**Authority Level**: MEDIUM

---

## Files

### ModelExperiments.jsx
**Purpose**: ML experiment tracking and management interface
**Lines**: ~650
**Key Features**:
- List of ML experiments
- Experiment details viewer
- Metrics visualization
- Create new experiment
- Compare experiments

**API Calls**:
- GET /experiments (list experiments)
- POST /experiments (create)
- GET /experiments/{id} (details)
- PUT /experiments/{id} (update)

**Dependencies**:
- React
- frontend/src/services/api.js
- Chart library (for metrics visualization)
- frontend/src/context/ModelContext

**Recent Changes**:
- 2025-12-23: Updated experiment comparison UI

### ModelGovernance.jsx
**Purpose**: ML model governance and versioning interface
**Lines**: ~650
**Key Features**:
- Model registry view
- Version management
- Model approval workflow
- Performance tracking
- Model deployment status

**Governance Features**:
- Model versioning
- Approval gates (dev → staging → production)
- Performance metrics per version
- Rollback capability

**API Calls**:
- GET /models (list models)
- POST /models/register (register new model)
- PUT /models/{id}/approve (approval workflow)
- GET /models/{id}/metrics (performance data)

**Dependencies**:
- React
- frontend/src/services/api.js
- frontend/src/context/ModelContext

**Recent Changes**:
- 2025-12-23: Enhanced approval workflow UI

### LabInstanceDetails.jsx
**Purpose**: Detailed view of instances used for ML experiments
**Lines**: ~400
**Key Features**:
- Instance hardware specs
- Running experiments on instance
- Resource utilization graphs
- Experiment logs
- Instance control (start/stop)

**Displays**:
- CPU, memory, GPU usage
- Network I/O
- Experiment status
- Logs and outputs

**Dependencies**:
- React
- frontend/src/services/api.js
- Chart library

**Recent Changes**:
- 2025-12-23: Added GPU utilization tracking

### DecisionLog.jsx
**Purpose**: Log of automated decision engine actions
**Lines**: ~150
**Key Features**:
- Decision history timeline
- Decision rationale display
- Filter by decision type
- Export decision logs

**Decision Types**:
- Instance optimization recommendations
- Cost-saving actions
- Risk assessments
- Automated actions taken

**Dependencies**:
- React
- frontend/src/services/api.js

**Recent Changes**: None recent

### PipelineVisualizer.jsx
**Purpose**: Visual representation of ML pipelines
**Lines**: ~180
**Key Features**:
- DAG (Directed Acyclic Graph) visualization
- Pipeline stage status
- Data flow visualization
- Error highlighting

**Visualizes**:
- Data ingestion → Processing → Model training → Deployment
- Pipeline dependencies
- Success/failure states

**Dependencies**:
- React
- Graph visualization library (e.g., react-flow, vis.js)

**Recent Changes**: None recent

### ShadowGraph.jsx
**Purpose**: Shadow deployment comparison visualizer
**Lines**: ~220
**Key Features**:
- Compare live model vs shadow model
- Prediction comparison
- Performance diff visualization
- A/B test results

**Use Case**:
Testing new ML model versions in parallel with production without affecting users.

**Dependencies**:
- React
- Chart library
- frontend/src/services/api.js

**Recent Changes**: None recent

### DragDropUpload.jsx
**Purpose**: File upload component with drag-and-drop
**Lines**: ~260
**Key Features**:
- Drag and drop file upload
- Multi-file support
- Upload progress bar
- File type validation
- Preview uploaded files

**Accepted File Types**:
- CSV (datasets)
- JSON (configurations)
- Python files (training scripts)
- Model files (.pkl, .h5, .pt)

**Dependencies**:
- React
- react-dropzone (likely)

**Recent Changes**: None recent

---

## Lab Components Usage Pattern

```
Lab Dashboard
  ↓
  ├─ ModelExperiments (experiment tracking)
  ├─ ModelGovernance (model versioning)
  ├─ LabInstanceDetails (resource monitoring)
  ├─ DecisionLog (decision history)
  ├─ PipelineVisualizer (pipeline view)
  ├─ ShadowGraph (A/B testing)
  └─ DragDropUpload (file uploads)
```

---

## Dependencies

### Depends On:
- React
- frontend/src/services/api.js
- frontend/src/context/ModelContext
- Chart libraries (recharts, Chart.js, or similar)
- Graph visualization (react-flow, vis.js)
- react-dropzone (for uploads)

### Depended By:
- Lab dashboard page
- ML/research features
- Data science workflows

**Impact Radius**: MEDIUM (ML features only)

---

## Recent Changes

### 2025-12-25: Governance Structure Establishment
**Files Changed**: None (metadata only)
**Reason**: Document existing Lab components
**Impact**: No code changes, documentation baseline
**Reference**: `/index/recent_changes.md`

### 2025-12-23: Multiple Component Updates
**Files Changed**: ModelExperiments.jsx, ModelGovernance.jsx, LabInstanceDetails.jsx
**Reason**: UI/UX improvements for experiment tracking
**Impact**: Better user experience for ML workflows
**Reference**: Legacy documentation

---

## Known Issues

### None

Lab components are stable as of 2025-12-25.

---

_Last Updated: 2025-12-25_
_Authority: MEDIUM - ML/Lab features_
