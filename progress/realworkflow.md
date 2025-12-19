# Workflow Analysis - Feature Mapping & API Documentation

This document provides a comprehensive analysis of features mentioned in the workflow documentation and their current implementation status, including debugging tags for easy troubleshooting.

---

## Table 1: Features Mentioned in workflow.txt

| Feature | Working Status | API Used | Is Expected API | Component Type | Expected Behavior on Click/Refresh | Similar Components (Same Data) | File Name(s) | Tags |
|---------|---------------|----------|----------------|----------------|-----------------------------------|-------------------------------|--------------|------|
| **Login - Sign In** | ✅ Working | `/api/auth/login` | Yes | Form with action button | Submit credentials, navigate to role-based dashboard (Admin/Client/Lab) | N/A | `LoginPage.jsx` | `auth, login, button, authentication, access-control` |
| **Login - Sign Up** | ✅ Working | `/api/auth/register` | Yes | Form with action button | Create new client account, onboarding process | Add Client (Client Management) | `LoginPage.jsx` | `auth, signup, button, onboarding, client-creation` |
| **Active Instances (Live Operations)** | ✅ Working | `/api/admin/system/overview` | Expected: `/api/metrics/active-instances` | Data display card, real-time | Auto-refresh every 30s, shows platform-wide instance count | Node Fleet - Total Active Nodes, Client Dashboard - Total Nodes | `LiveOperations.jsx` | `metrics, data-display, real-time, instances, monitoring` |
| **Risk Detected (Live Operations)** | ✅ Working | `/api/admin/system/overview` | Expected: `/api/metrics/risk-detected` | Data display card, real-time | Auto-refresh every 30s, counts rebalance/termination notices in 24h | N/A | `LiveOperations.jsx` | `metrics, data-display, real-time, risk, alerts, termination` |
| **Cost Savings (Live Operations)** | ✅ Working | `/api/admin/system/overview` | Expected: `/api/metrics/cost-savings` | Data display card, real-time | Auto-refresh every 30s, on-demand vs current cost comparison | Node Fleet - Total Monthly Saving, Client Dashboard - Savings | `LiveOperations.jsx` | `metrics, data-display, real-time, cost, savings, financial` |
| **Optimizations (Live Operations)** | ✅ Working | `/api/admin/system/overview` | Expected: `/api/metrics/optimizations` | Data display card, real-time | Auto-refresh every 30s, counts total ML switching actions | N/A | `LiveOperations.jsx` | `metrics, data-display, real-time, ml-decisions, switches` |
| **Decision Pipeline Funnel** | ✅ Working | `/api/admin/system/overview` | Expected: `/api/pipeline/funnel` | Interactive data visualization, real-time | Auto-refresh every 30s, shows ML pool selection process | N/A | `LiveOperations.jsx` | `visualization, data-display, real-time, ml-pipeline, funnel` |
| **Pipeline Status** | ✅ Working | `/api/admin/system/overview` | Expected: `/api/pipeline/status` | Data display with status badges | Auto-refresh every 30s, monitors backend component health | System Monitor - Component Health | `LiveOperations.jsx` | `monitoring, data-display, real-time, health-check, components` |
| **System Load (Live Operations)** | ✅ Working | `/api/admin/system/overview` | Expected: `/api/metrics/system-load` | Progress bar, real-time | Auto-refresh, tracks request volume and I/O load | N/A | `LiveOperations.jsx` | `metrics, data-display, real-time, performance, load` |
| **Total Monthly Saving (Node Fleet)** | ✅ Working | `/api/admin/clients` | Expected: `/api/clients/savings` | Data display card | Refresh on navigation, same as Cost Savings | Live Operations - Cost Savings | `NodeFleet.jsx` | `metrics, data-display, cost, savings, financial` |
| **Total Active Nodes (Node Fleet)** | ✅ Working | `/api/admin/clients` | Expected: `/api/clients/nodes-count` | Data display card | Refresh on navigation, same as Active Instances | Live Operations - Active Instances | `NodeFleet.jsx` | `metrics, data-display, instances, monitoring` |
| **Optimisation Rate (Node Fleet)** | ⚠️ Needs Definition | Not implemented | Expected: `/api/metrics/optimization-rate` | Data display card | Should calculate optimization percentage | N/A | `NodeFleet.jsx` | `metrics, data-display, ml-performance, rate` |
| **Client List (Node Fleet)** | ✅ Working | `/api/admin/clients` | Yes | Clickable client cards | Click to open client-specific dashboard | Client Management - Client List | `NodeFleet.jsx` (ClientCard, ClientMasterView) | `data-display, clients, navigation, clickable` |
| **System Monitor - Component Cards** | ✅ Working | `/api/admin/system/overview` + `/api/admin/components/{component}/logs` | Expected: `/api/components/{id}/status` | Data display with metrics | Shows uptime, latency, recent logs (5 normal, 10 on state change) | N/A | `SystemMonitor.jsx` (ComponentCard) | `monitoring, data-display, health-check, logs, real-time` |
| **Model Management - Dropdown View** | ✅ Working | `/api/admin/ml-models/sessions` | Expected: `/api/models/list` | Dropdown menu | View all uploaded, graduated, and current models | N/A | `ModelContext.jsx`, `Controls.jsx` | `control, dropdown, models, selection` |
| **Upload Model** | ✅ Working | `/api/admin/ml-models/upload` | Yes | Drag-drop upload area + action button | Upload new model files, add to system | Lab - Model Upload | `Controls.jsx`, `DragDropUpload.jsx` | `control, button, upload, models, drag-drop` |
| **Manual Override - Disable Spot/Force On-Demand** | ✅ Working | `api.setSpotMarketStatus()` | Expected: `/api/admin/override/spot-market` | Action button with confirmation + progress bar | Platform-wide revert to on-demand for maintenance, shows 100% progress when done | Client - Force On-Demand | `Controls.jsx` | `control, button, action, override, on-demand, termination, maintenance` |
| **Re-compute Risk Scores** | ❌ Not Implemented | Expected: `/api/admin/recompute-risk` | Expected: `/api/admin/recompute-risk` | Action button | Trigger periodic risk score recalculation and rebalancing | N/A | Not in current code | `control, button, action, ml, risk, computation` |
| **Client Management - Add Client** | ✅ Working | `/api/v1/admin/users` (POST) | Expected: `/api/admin/clients/create` | Action button + modal | Create new client with credentials and dashboard assignment | Sign Up, Onboarding | `ClientManagement.jsx` (ClientCreateModal) | `control, button, action, clients, creation, onboarding` |
| **Admin Profile** | ❌ Not Implemented | Expected: `/api/admin/profile` (PUT) | Expected: `/api/admin/profile` | Form + action button | Update admin username/password | N/A | Not in current code | `control, form, button, admin, profile, authentication, security` |
| **Client Dashboard - Fleet Topology** | ❌ Not Implemented | Expected: `/api/client/{id}/topology` | Expected: `/api/client/{id}/topology` | Interactive visualization with 2 modes | Shows cluster monitoring structure | N/A | Not in current code | `visualization, data-display, client-specific, topology, clusters` |
| **Fleet Topology - Cycle View** | ❌ Not Implemented | Expected: `/api/client/{id}/clusters` | Expected: `/api/client/{id}/clusters` | Animated rotating banner | Rotates through clusters showing cluster→engine→nodes flow | N/A | Not in current code | `visualization, animation, client-specific, clusters, rotation` |
| **Fleet Topology - Live View** | ❌ Not Implemented | Expected: `/api/client/{id}/live-switches` (WebSocket) | Expected: `/api/client/{id}/live-switches` (WebSocket) | Animated real-time display | Shows live switching animations, multiple clusters/nodes scaling | N/A | Not in current code | `visualization, animation, real-time, client-specific, switches, websocket` |
| **Client Dashboard - Cost Savings Overview** | ❌ Not Implemented | Expected: `/api/client/{id}/savings-overview` | Expected: `/api/client/{id}/savings-overview` | Interactive chart with 2 modes | Graph showing on-demand vs spot pricing comparison | Live Operations - Cost Savings | Not in current code | `visualization, data-display, chart, client-specific, cost, savings, financial` |
| **Clusters View - Instance Detail Popup** | ❌ Not Implemented | Expected: `/api/client/instances/{id}/switch-history` | Yes (exists in apiClient) | Interactive graph + options | Shows switching history graph and 5 alternate pools with pricing | N/A | Not in current code | `visualization, data-display, instances, history, pools` |
| **Instance - Force On-Demand (Instance-Level)** | ❌ Not Implemented | Expected: `/api/client/instances/{id}/force-on-demand` | Expected: `/api/client/instances/{id}/force-on-demand` | Action button with duration selector | Force single instance to on-demand with time duration | Manual Override (Admin) | Not in current code | `control, button, action, instances, on-demand, termination, duration` |
| **Cluster - Force On-Demand (Cluster-wide)** | ❌ Not Implemented | Expected: `/api/client/clusters/{id}/force-on-demand` | Expected: `/api/client/clusters/{id}/force-on-demand` | Action button with duration selector | Force all instances in cluster to on-demand | Instance Force On-Demand | Not in current code | `control, button, action, clusters, on-demand, termination, duration, cluster-wide` |
| **Client - Force On-Demand (Client-wide)** | ❌ Not Implemented | Expected: `/api/client/{id}/force-on-demand-all` | Expected: `/api/client/{id}/force-on-demand-all` | Action button with duration selector | Force all instances across all clusters to on-demand | Cluster Force On-Demand | Not in current code | `control, button, action, clients, on-demand, termination, duration, client-wide` |
| **Unregistered Instances - Apply with Progress** | ⚠️ Missing Progress | Expected: `/api/governance/instances/apply` | Expected: `/api/governance/instances/apply` | Action button with progress bar | Terminate unauthorized instances, show real-time progress | Manual Override Progress | `NodeFleet.jsx` | `control, button, action, instances, termination, cleanup, progress` |
| **Volumes - Management** | ⚠️ Mock Data | Expected: `/api/storage/unmapped-volumes` | Expected: `/api/storage/unmapped-volumes` | Data table + cleanup | Lists/deletes unattached volumes | Unregistered Instances | `NodeFleet.jsx` (UnmappedVolumes) | `data-display, storage, volumes, cleanup` |
| **Snapshots - Management** | ⚠️ Mock Data | Expected: `/api/storage/ami-snapshots` | Expected: `/api/storage/ami-snapshots` | Data table + cleanup | Lists/deletes unused snapshots | Volumes | `NodeFleet.jsx` (AmiSnapshots) | `data-display, storage, snapshots, cleanup` |

---

## Table 2: Production-Grade Improvements & Technical Debt

This table consolidates all architectural upgrades, missing APIs, frontend/backend wiring issues, ML model enhancements, and database schema changes needed for production readiness.

| Category | Item | Priority | Status | Current State | Required State | Expected API/Component | Files Affected | Estimated Effort | Dependencies | Tags |
|----------|------|----------|--------|---------------|----------------|----------------------|----------------|------------------|--------------|------|
| **ARCHITECTURE** | Event-Driven System | 🔴 HIGH | ❌ Not Started | Polling every 5 minutes via scheduler | Real-time Kubernetes event stream | `backend/watchers/k8s_event_stream.py` | `scheduler.py` (deprecate), `workers/optimizer_worker.py` (new), `config/redis.yaml` (new) | 2-3 weeks | Redis, Kubernetes Python client | `architecture, event-driven, real-time, performance` |
| **ARCHITECTURE** | WebSocket for Live Updates | 🔴 HIGH | ❌ Not Started | Polling APIs every 30s | WebSocket server for real-time push | `/ws/client/{id}/live-switches` | `backend/websocket/`, `frontend/src/hooks/useWebSocket.jsx` | 1-2 weeks | WebSocket library (e.g., Socket.io) | `websocket, real-time, live-updates` |
| **ML MODEL** | Performance-Based Optimization | 🟡 MEDIUM | ❌ Not Started | Cost + Stability scoring only | Add latency, throughput, error rate | `backend/pipelines/metric_ingestor.py`, `/api/metrics/performance` | `ml_models/scoring.py`, `logic/decision_engine.py`, `pipelines/metric_ingestor.py` (new) | 3-4 weeks | Prometheus/Datadog integration | `ml, performance, metrics, optimization` |
| **ML MODEL** | Enhanced Scoring Formula | 🟡 MEDIUM | ❌ Not Started | `cost_score + stability_score` | Add performance & capacity scores | Updated model formula in `scoring.py` | `ml_models/scoring.py` | 1 week | Metric ingestion pipeline | `ml, scoring, algorithm` |
| **SAFETY** | Pod Disruption Budget Awareness | 🔴 HIGH | ❌ Not Started | Basic drain logic | Check PDB before draining nodes | `backend/logic/safe_drain.py`, Kubernetes PDB API | `logic/safe_drain.py` (new), `executor/node_drainer.py` | 2 weeks | Kubernetes Python client >= 28.0.0 | `safety, pdb, kubernetes, zero-downtime` |
| **SAFETY** | Constraint Solver (OR-Tools) | 🔴 HIGH | ❌ Not Started | Custom heuristic bin-packer | Google OR-Tools linear programming | `backend/logic/constraint_solver.py` | `logic/constraint_solver.py` (new), `decision_engine/optimizer.py` | 2 weeks | `ortools==9.6.2534` | `optimization, constraint-solver, bin-packing` |
| **MONITORING** | Hybrid Agent Architecture | 🟢 LOW | ❌ Not Started | AWS API only (agentless) | DaemonSet for container metrics | `agents/daemonset/metric_collector.py`, `/api/agent/metrics` | `agents/daemonset/` (new), `k8s/daemonset-agent.yaml` (new), Backend API endpoints | 4-5 weeks | Docker API access, DaemonSet deployment | `monitoring, agents, metrics, daemonset` |
| **API - MISSING** | `/api/metrics/active-instances` | 🟡 MEDIUM | ❌ Missing | Using `/api/admin/system/overview` | Dedicated endpoint for active instances | GET `/api/metrics/active-instances` | `backend/api/metrics_routes.py` (new or update) | 1 day | N/A | `api, metrics, instances` |
| **API - MISSING** | `/api/metrics/risk-detected` | 🟡 MEDIUM | ❌ Missing | Using `/api/admin/system/overview` | Dedicated endpoint for risk count | GET `/api/metrics/risk-detected` | `backend/api/metrics_routes.py` | 1 day | N/A | `api, metrics, risk` |
| **API - MISSING** | `/api/metrics/cost-savings` | 🟡 MEDIUM | ❌ Missing | Using `/api/admin/system/overview` | Dedicated endpoint for savings | GET `/api/metrics/cost-savings` | `backend/api/metrics_routes.py` | 1 day | Cost calculation logic | `api, metrics, cost, savings` |
| **API - MISSING** | `/api/metrics/optimization-rate` | 🔴 HIGH | ❌ Missing | Not defined | Calculate & return optimization rate | GET `/api/metrics/optimization-rate` | `backend/api/metrics_routes.py`, calculation logic | 2 days | Define optimization rate formula | `api, metrics, optimization` |
| **API - MISSING** | `/api/pipeline/funnel` | 🟡 MEDIUM | ❌ Missing | Using `/api/admin/system/overview` | Real-time pipeline funnel data | GET `/api/pipeline/funnel` | `backend/api/pipeline_routes.py` (new) | 2 days | ML pipeline metrics | `api, pipeline, ml, funnel` |
| **API - MISSING** | `/api/pipeline/status` | 🟡 MEDIUM | ❌ Missing | Using `/api/admin/system/overview` | Pipeline component status | GET `/api/pipeline/status` | `backend/api/pipeline_routes.py` | 1 day | Component health checks | `api, pipeline, monitoring` |
| **API - MISSING** | `/api/admin/recompute-risk` | 🔴 HIGH | ❌ Missing | No endpoint | Trigger risk recalculation | POST `/api/admin/recompute-risk` | `backend/api/admin_routes.py`, ML job trigger | 3 days | ML inference service | `api, admin, ml, risk` |
| **API - MISSING** | `/api/admin/profile` | 🟢 LOW | ❌ Missing | No endpoint | Update admin credentials | PUT `/api/admin/profile` | `backend/api/admin_routes.py` | 1 day | Auth system | `api, admin, profile, auth` |
| **API - MISSING** | `/api/client/{id}/topology` | 🟡 MEDIUM | ❌ Missing | No endpoint | Client cluster topology | GET `/api/client/{id}/topology` | `backend/api/client_routes.py` | 2 days | Cluster data aggregation | `api, client, topology, clusters` |
| **API - MISSING** | `/api/client/{id}/live-switches` (WebSocket) | 🔴 HIGH | ❌ Missing | No WebSocket | Real-time switch events | WebSocket `/ws/client/{id}/live-switches` | `backend/websocket/client_events.py` (new) | 1 week | WebSocket server | `api, websocket, real-time, switches` |
| **API - MISSING** | `/api/client/{id}/savings-overview` | 🟡 MEDIUM | ❌ Missing | No endpoint | Client savings chart data | GET `/api/client/{id}/savings-overview?mode=total\|cluster` | `backend/api/client_routes.py` | 2 days | Cost tracking queries | `api, client, savings, charts` |
| **API - MISSING** | `/api/client/instances/{id}/force-on-demand` | 🔴 HIGH | ❌ Missing | No endpoint | Force instance to on-demand | POST `/api/client/instances/{id}/force-on-demand` `{duration_hours}` | `backend/api/instance_routes.py`, executor | 3 days | Instance manager integration | `api, instances, on-demand, force` |
| **API - MISSING** | `/api/client/clusters/{id}/force-on-demand` | 🔴 HIGH | ❌ Missing | No endpoint | Force cluster to on-demand | POST `/api/client/clusters/{id}/force-on-demand` `{duration_hours}` | `backend/api/cluster_routes.py` (new), executor | 3 days | Batch instance operations | `api, clusters, on-demand, force` |
| **API - MISSING** | `/api/client/{id}/force-on-demand-all` | 🟡 MEDIUM | ❌ Missing | No endpoint | Force all client instances | POST `/api/client/{id}/force-on-demand-all` `{duration_hours}` | `backend/api/client_routes.py`, executor | 3 days | Cluster + instance operations | `api, clients, on-demand, force, batch` |
| **API - MISSING** | `/api/governance/instances/apply` | 🟡 MEDIUM | ❌ Missing | No endpoint | Apply flagged instance actions | POST `/api/governance/instances/apply` `{flagged_instances}` | `backend/api/governance_routes.py` (new), executor | 2 days | Termination logic | `api, governance, termination, cleanup` |
| **API - MISSING** | `/api/storage/unmapped-volumes` | 🟡 MEDIUM | ❌ Missing | Mock data | List unattached volumes | GET `/api/storage/unmapped-volumes` | `backend/api/storage_routes.py` (new), AWS EBS integration | 2 days | AWS EBS API | `api, storage, volumes, cleanup` |
| **API - MISSING** | `/api/storage/volumes/cleanup` | 🟡 MEDIUM | ❌ Missing | Mock data | Delete flagged volumes | POST `/api/storage/volumes/cleanup` `{volume_ids}` | `backend/api/storage_routes.py`, AWS executor | 2 days | AWS EBS deletion | `api, storage, volumes, deletion` |
| **API - MISSING** | `/api/storage/ami-snapshots` | 🟡 MEDIUM | ❌ Missing | Mock data | List unused snapshots | GET `/api/storage/ami-snapshots` | `backend/api/storage_routes.py`, AWS snapshot query | 2 days | AWS snapshot API | `api, storage, snapshots, cleanup` |
| **API - MISSING** | `/api/storage/snapshots/cleanup` | 🟡 MEDIUM | ❌ Missing | Mock data | Delete flagged snapshots | POST `/api/storage/snapshots/cleanup` `{snapshot_ids}` | `backend/api/storage_routes.py`, AWS executor | 2 days | AWS snapshot deletion | `api, storage, snapshots, deletion` |
| **API - MISSING** | `/api/metrics/performance` | 🟡 MEDIUM | ❌ Missing | No endpoint | Application performance metrics | GET `/api/metrics/performance?instance_id={id}` | `backend/api/metrics_routes.py`, Prometheus integration | 1 week | Prometheus/Datadog setup | `api, metrics, performance, prometheus` |
| **API - NOT IN APICLIENT** | `api.getSystemOverview()` | 🔴 HIGH | ⚠️ Missing | Called but not defined in apiClient | Add to APIClient class | Method in `apiClient.jsx` | `frontend/src/services/apiClient.jsx` | 1 hour | N/A | `api-client, frontend, missing-method` |
| **API - NOT IN APICLIENT** | `api.getComponentLogs()` | 🔴 HIGH | ⚠️ Missing | Called but not defined | Add to APIClient class | Method in `apiClient.jsx` | `frontend/src/services/apiClient.jsx` | 1 hour | N/A | `api-client, frontend, missing-method` |
| **API - NOT IN APICLIENT** | `api.getUnauthorizedInstances()` | 🟡 MEDIUM | ⚠️ Missing | Called but not defined | Add to APIClient class | Method in `apiClient.jsx` | `frontend/src/services/apiClient.jsx` | 1 hour | N/A | `api-client, frontend, missing-method` |
| **API - NOT IN APICLIENT** | `api.getActivityFeed()` | 🟡 MEDIUM | ⚠️ Missing | Called but not defined | Add to APIClient class | Method in `apiClient.jsx` | `frontend/src/services/apiClient.jsx` | 1 hour | N/A | `api-client, frontend, missing-method` |
| **API - NOT IN APICLIENT** | `api.getClients()` | 🔴 HIGH | ⚠️ Missing | Called but not defined (different from getAllClients) | Add to APIClient class | Method in `apiClient.jsx` | `frontend/src/services/apiClient.jsx` | 1 hour | N/A | `api-client, frontend, missing-method` |
| **API - NOT IN APICLIENT** | `api.getUsers()` | 🔴 HIGH | ⚠️ Missing | Called but not defined | Add to APIClient class | Method in `apiClient.jsx` | `frontend/src/services/apiClient.jsx` | 1 hour | N/A | `api-client, frontend, missing-method` |
| **API - NOT IN APICLIENT** | `api.createUser()` | 🔴 HIGH | ⚠️ Missing | Called but not defined | Add to APIClient class | Method in `apiClient.jsx` | `frontend/src/services/apiClient.jsx` | 1 hour | N/A | `api-client, frontend, missing-method` |
| **API - NOT IN APICLIENT** | `api.updateUser()` | 🔴 HIGH | ⚠️ Missing | Called but not defined | Add to APIClient class | Method in `apiClient.jsx` | `frontend/src/services/apiClient.jsx` | 1 hour | N/A | `api-client, frontend, missing-method` |
| **API - NOT IN APICLIENT** | `api.setSpotMarketStatus()` | 🔴 HIGH | ⚠️ Missing | Called but not defined | Add to APIClient class | Method in `apiClient.jsx` | `frontend/src/services/apiClient.jsx` | 1 hour | Backend `/api/admin/override/spot-market` | `api-client, frontend, missing-method` |
| **API - NOT IN APICLIENT** | `api.getOnboardingTemplate()` | 🟡 MEDIUM | ⚠️ Missing | Called but not defined | Add to APIClient class | Method in `apiClient.jsx` | `frontend/src/services/apiClient.jsx` | 1 hour | N/A | `api-client, frontend, missing-method` |
| **API - NOT IN APICLIENT** | `api.getDiscoveryStatus()` | 🟡 MEDIUM | ⚠️ Missing | Called but not defined | Add to APIClient class | Method in `apiClient.jsx` | `frontend/src/services/apiClient.jsx` | 1 hour | N/A | `api-client, frontend, missing-method` |
| **API - NOT IN APICLIENT** | `api.getExperimentLogs()` | 🟡 MEDIUM | ⚠️ Missing | Called but not defined | Add to APIClient class | Method in `apiClient.jsx` | `frontend/src/services/apiClient.jsx` | 1 hour | N/A | `api-client, frontend, missing-method, lab` |
| **API - NOT IN APICLIENT** | `api.getModels()` | 🟡 MEDIUM | ⚠️ Missing | Called but not defined | Add to APIClient class | Method in `apiClient.jsx` | `frontend/src/services/apiClient.jsx` | 1 hour | N/A | `api-client, frontend, missing-method, models` |
| **FRONTEND** | Fleet Topology Component | 🔴 HIGH | ❌ Not Implemented | No component | Create topology visualization | `frontend/src/components/FleetTopology.jsx` | New component file | 1-2 weeks | WebSocket, topology API | `frontend, visualization, components, topology` |
| **FRONTEND** | Cycle View Animation | 🟡 MEDIUM | ❌ Not Implemented | No animation | Rotating cluster banner | Part of FleetTopology component | `FleetTopology.jsx` | 3 days | Topology data | `frontend, animation, visualization` |
| **FRONTEND** | Live View WebSocket Integration | 🔴 HIGH | ❌ Not Implemented | No live updates | Real-time switch animations | `useWebSocket` hook, FleetTopology | `hooks/useWebSocket.jsx`, `FleetTopology.jsx` | 1 week | WebSocket server | `frontend, websocket, real-time, animation` |
| **FRONTEND** | Cost Savings Overview Chart | 🟡 MEDIUM | ❌ Not Implemented | No component | 2-mode savings chart | `frontend/src/components/CostSavingsChart.jsx` | New component | 3 days | Savings API | `frontend, visualization, charts, savings` |
| **FRONTEND** | Resource Distribution Chart | ⚠️ Mock Data | Mock data only | Real API connection | Cluster-specific resource distribution | Update `ResourceDistributionChart` in NodeFleet | `NodeFleet.jsx` | 2 days | Resource distribution API | `frontend, charts, data-wiring` |
| **FRONTEND** | Instance Detail Modal | ❌ Not Implemented | No modal | Full instance detail popup | Switch history graph + alternate pools + force on-demand | `frontend/src/components/InstanceDetailModal.jsx` | New modal component | 1 week | Instance APIs | `frontend, modal, components, instances` |
| **FRONTEND** | Force On-Demand UI (3 levels) | ❌ Not Implemented | No UI | Instance/Cluster/Client level controls | Duration selector + confirmation + progress | Part of InstanceDetailModal, Cluster view, Client view | Multiple components | 1 week | Force on-demand APIs | `frontend, control, on-demand, ui` |
| **FRONTEND** | Progress Bar for Batch Operations | ⚠️ Partial | Limited progress feedback | Real-time WebSocket progress | Live progress for terminations, migrations | `frontend/src/components/ProgressModal.jsx` | New shared component | 3 days | WebSocket for progress updates | `frontend, progress, ui, websocket` |
| **FRONTEND** | Admin Profile Component | ❌ Not Implemented | No component | Profile management form | Username/password change form | `frontend/src/components/AdminProfile.jsx` | New component | 2 days | Admin profile API | `frontend, components, admin, profile` |
| **FRONTEND** | Clusters View (Client Dashboard) | ❌ Not Implemented | No view | Full cluster management UI | Cluster list → Instance list → Instance details | `frontend/src/pages/ClustersView.jsx` | New page component | 1-2 weeks | Cluster APIs, instance APIs | `frontend, pages, clusters, client` |
| **BACKEND** | Component Health Check System | ⚠️ Partial | Basic health checks | Customized per-component checks | Each component has role-specific health logic | `backend/monitoring/health_checks.py` | Update health check logic per component | 1 week | Component-specific metrics | `backend, monitoring, health-checks` |
| **BACKEND** | WebSocket Server | ❌ Not Implemented | No WebSocket | Real-time event broadcasting | Socket.io or native WebSocket server | `backend/websocket/server.py` (new) | New WebSocket module | 1 week | WebSocket library | `backend, websocket, real-time` |
| **BACKEND** | Redis Task Queue | ❌ Not Implemented | No queue | Event-driven task processing | Redis queue for optimization tasks | `backend/workers/` (new), Redis setup | Queue system + workers | 1 week | Redis server | `backend, queue, redis, workers` |
| **BACKEND** | Prometheus Integration | ❌ Not Implemented | No integration | Metric ingestion pipeline | Pull metrics from Prometheus API | `backend/pipelines/metric_ingestor.py` (new) | New pipeline module | 1-2 weeks | Prometheus server access | `backend, metrics, prometheus, integration` |
| **BACKEND** | Kubernetes Event Watcher | ❌ Not Implemented | Scheduled polling | Real-time K8s API stream | Watch pod events continuously | `backend/watchers/k8s_event_stream.py` (new) | New watcher module | 1 week | Kubernetes Python client | `backend, kubernetes, event-driven, watcher` |
| **BACKEND** | Safe Drain Logic (PDB-aware) | ❌ Not Implemented | Basic drain | Check PDB before draining | PDB-aware node draining | `backend/logic/safe_drain.py` (new) | New safety module | 1 week | Kubernetes PDB API | `backend, safety, kubernetes, pdb` |
| **BACKEND** | Constraint Solver Module | ❌ Not Implemented | Heuristic packing | OR-Tools linear programming | Optimal pod placement solver | `backend/logic/constraint_solver.py` (new) | New optimization module | 2 weeks | Google OR-Tools library | `backend, optimization, constraint-solver` |
| **BACKEND** | Force On-Demand Executor | ❌ Not Implemented | No implementation | Instance/Cluster/Client level forcing | Batch force-to-on-demand with timers | `backend/executor/force_ondemand.py` (new) | New executor module | 1 week | AWS instance control | `backend, executor, on-demand` |
| **BACKEND** | Storage Cleanup Logic | ⚠️ Mock Data | No real implementation | EBS volume & snapshot management | Query and delete unused storage | `backend/storage/cleanup.py` (new) | New storage module | 1 week | AWS EBS & snapshot APIs | `backend, storage, cleanup, aws` |
| **BACKEND** | Governance System | ⚠️ Partial | Basic unauthorized instance detection | Full flagging & termination workflow | Apply flagged actions with progress | `backend/governance/instance_manager.py` (update) | Update governance logic | 3 days | Executor integration | `backend, governance, instances` |
| **DATABASE** | Instance Metrics Time-Series Table | ❌ Missing | No table | Store performance metrics | `instance_metrics` table with timestamp index | Schema update in `database/schema.sql` | New table schema | 1 day | TimescaleDB or similar | `database, schema, metrics, time-series` |
| **DATABASE** | Optimization Rate Calculation | ❌ Missing | No definition | Define and store optimization rate | Logic + storage for optimization rate | `database/views/optimization_rate.sql` (new) | View or materialized view | 2 days | Define rate formula | `database, views, metrics` |
| **DATABASE** | Client Policies Table | ⚠️ Not Persisted | Client -side only | Persist policy toggles | `client_policies` table | Schema update | New table | 1 day | N/A | `database, schema, clients, policies` |
| **DATABASE** | Force On-Demand Overrides Table | ❌ Missing | No table | Track temporary overrides | `instance_overrides` table with expiry | Schema update | New table | 1 day | Timer/cron for expiry | `database, schema, instances, overrides` |
| **DATABASE** | Cost Tracking Enhancement | ⚠️ Partial | Basic cost tracking | Detailed cost breakdowns | Enhanced cost tracking with cluster/client granularity | Update `cost_tracking` table | Schema update | 2 days | Cost calculation logic | `database, schema, cost, financial` |
| **ML ENGINE** | Performance Score Integration | ❌ Not Implemented | Not in model | Add to scoring function | Latency, throughput, error rate inputs | Update `ml_models/scoring.py` | Model retraining + deployment | 2-3 weeks | Prometheus data pipeline | `ml, model, performance, scoring` |
| **ML ENGINE** | Capacity Score Integration | ❌ Not Implemented | Not in model | Add to scoring function | CPU/Memory availability inputs | Update `ml_models/scoring.py` | Model retraining | 1 week | Metric data | `ml, model, capacity, scoring` |
| **ML ENGINE** | Enhanced Model Formula | ❌ Not Implemented | 2-factor formula | 4-factor weighted formula | cost + stability + performance + capacity | Model code update | Code change + testing | 1 week | All metrics available | `ml, model, algorithm, formula` |
| **TESTING** | Event-Driven Canary Deployment | ❌ Not Planned | No testing strategy | Canary on 10% clusters | Test Phase 1 changes safely | Testing plan + monitoring | Testing infrastructure | 1 week | Production-like environment | `testing, canary, deployment` |
| **TESTING** | A/B Testing Framework | ❌ Not Planned | No A/B testing | Compare old vs new logic | Parallel cluster testing | Testing framework | Infrastructure + metrics | 2 weeks | Duplicate test environments | `testing, ab-testing, comparison` |
| **TESTING** | Chaos Engineering Suite | ❌ Not Planned | No chaos tests | Simulate node failures | Verify PDB compliance under failure | Chaos testing tools | Test suite | 1 week | Chaos Mesh or similar | `testing, chaos-engineering, reliability` |
| **SECURITY** | Agent Security Audit | ❌ Not Started | No agents yet | Penetration testing | Agent → HQ communication audit | Security audit plan | External audit | 2 weeks | Security team | `security, audit, agents, penetration-testing` |
| **SECURITY** | API Authentication Enhancement | ⚠️ Basic | JWT tokens | Role-based fine-grained auth | RBAC for all endpoints | Auth middleware update | Multiple backend files | 1 week | Auth library | `security, authentication, rbac` |
| **DOCUMENTATION** | API Documentation (OpenAPI) | ⚠️ Partial | Some endpoints documented | Full OpenAPI/Swagger spec | Auto-generated API docs | `swagger.yaml` or decorators | Documentation setup | 3 days | Swagger/OpenAPI tools | `documentation, api, openapi` |
| **DOCUMENTATION** | Deployment Runbook | ⚠️ Basic | Basic deploy script | Comprehensive runbook | Production deployment guide | `docs/deployment.md` | New documentation | 2 days | N/A | `documentation, deployment, operations` |
| **DEVOPS** | Monitoring Dashboard Setup | ⚠️ Partial | Basic monitoring | Grafana dashboards for all metrics | Production monitoring | Grafana dashboards | Dashboard configs | 1 week | Grafana + Prometheus | `devops, monitoring, grafana, observability` |
| **DEVOPS** | Alerting Rules | ⚠️ Limited | Basic alerts | Comprehensive alerting | PagerDuty/Slack integration | Alert configs | Alert rule configs | 3 days | PagerDuty or similar | `devops, alerting, monitoring` |

---

## Summary of Improvements Needed

### Critical Path (Must-Have for Production)

**Priority 🔴 HIGH** (11-13 weeks total):

1. **Event-Driven Architecture** (2-3 weeks) - Reduces latency from 5min to <1sec
2. **Missing API Methods in APIClient** (1 day) - Fix frontend → backend wiring
3. **WebSocket Implementation** (2 weeks) - Real-time updates for Live View
4. **Pod Disruption Budget Awareness** (2 weeks) - Zero-downtime guarantee
5. **Constraint Solver** (2 weeks) - Optimal pod placement
6. **Force On-Demand Implementation** (2 weeks) - 3-level on-demand controls
7. **Missing Metric APIs** (1 week) - Standardize metric endpoints
8. **Fleet Topology UI** (1-2 weeks) - Core client dashboard feature

### Medium Priority (Nice-to-Have)

**Priority 🟡 MEDIUM** (8-10 weeks total):

1. **Performance-Based Optimization** (3-4 weeks) - ML model enhancement
2. **Client Dashboard Enhancements** (3 weeks) - Savings charts, resource distribution
3. **Storage Cleanup** (2 weeks) - Volumes & snapshots management
4. **Governance Workflow** (1 week) - Full flagging & termination
5. **Database Schema Updates** (1 week) - Support new features

### Low Priority (Future Enhancements)

**Priority 🟢 LOW** (6-8 weeks total):

1. **Hybrid Agent Architecture** (4-5 weeks) - Container-level metrics
2. **Admin Profile** (1 week) - Password management
3. **Testing Infrastructure** (4 weeks) - Canary, A/B testing, chaos engineering
4. **Documentation & DevOps** (2 weeks) - Runbooks, dashboards, alerts

---

## Quick Wins (Can Complete in 1 Week)

| Item | Effort | Impact | Category |
|------|--------|--------|----------|
| Add missing methods to `apiClient.jsx` | 1 day | 🔴 HIGH - Fixes current broken features | Frontend |
| Create missing metric API endpoints | 3 days | 🔴 HIGH - Standardizes API structure | Backend API |
| Define optimization rate formula | 1 day | 🟡 MEDIUM - Completes dashboard metric | Backend Logic |
| Admin Profile UI + API | 2 days | 🟢 LOW - Nice UX improvement | Frontend + Backend |
| Client policies persistence | 1 day | 🟡 MEDIUM - Data not saved currently | Database |
| Progress bar component | 1 day | 🟡 MEDIUM - Better UX for long operations | Frontend |

---

## Dependencies Graph

```
Event-Driven System
    ├─→ Redis Setup (prerequisite)
    ├─→ Kubernetes Watcher (core)
    └─→ Worker System (consumes queue)

Performance Optimization
    ├─→ Prometheus Integration (prerequisite)
    ├─→ Metric Ingestion Pipeline (prerequisite)
    └─→ ML Model Enhancement (depends on metrics)

WebSocket Live Updates
    ├─→ WebSocket Server (prerequisite)
    ├─→ Event-Driven System (provides events)
    └─→ Frontend Integration (consumes updates)

Force On-Demand Feature
    ├─→ Backend APIs (3 endpoints)
    ├─→ Frontend UI (3 levels)
    ├─→ Database Schema (overrides table)
    └─→ Progress Feedback (WebSocket)

Safety Guardrails
    ├─→ PDB Awareness (critical)
    ├─→ Constraint Solver (optimization)
    └─→ Safe Drain Logic (combines both)
```

---

## Estimated Total Effort

| Phase | Duration | Team Size Assumption |
|-------|----------|---------------------|
| **Critical Path (HIGH Priority)** | 11-13 weeks | 2-3 developers |
| **Medium Priority** | 8-10 weeks | 1-2 developers (parallel or sequential) |
| **Low Priority** | 6-8 weeks | 1 developer (after critical path) |
| **Total (Everything)** | 25-31 weeks | With parallelization: ~16-20 weeks |

**Realistic Production Timeline**: 4-5 months with a team of 3 developers working in parallel.
