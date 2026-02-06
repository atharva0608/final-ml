# Known Issues & Limitations
**Last Updated:** 2026-02-06

This document tracks known limitations, pending implementations, and technical debt in the codebase.

## Backend Limitations

### Core Execution Logic
*   **Action Executor** (`backend/core/action_executor.py`):
    *   `_execute_right_size`: Logic is currently a stub (returns simulated success). Needs to implement instance stop/change-type/start workflow.
    *   `_execute_consolidation`: Logic is currently a stub. Needs to implement node cordon/drain/terminate workflow.
    *   `_execute_scale_down` / `_execute_scale_up`: ASG scaling logic is pending implementation.
    *   `_execute_spot_replacement`: Mostly implemented but requires robust waiter logic for instance launch and proper Kubernetes node draining integration.

### Cost & Metrics
*   **Metrics Service** (`backend/services/metrics_service.py`):
    *   `_calculate_savings`: Savings calculation currently assumes a flat **70% discount** for Spot instances compared to On-Demand. This should be updated to use real pricing data delta from `pricing_collector`.

### Service Layer
*   **Settings Service** (`backend/services/settings_service.py`):
    *   Integrations (Slack, PagerDuty) are currently stored in an in-memory dictionary (`_MOCK_INTEGRATIONS_DB`). Needs proper database table implementation.

### Cluster Discovery & Agent Injection
*   **Connect AWS Endpoint Mismatch**:
    *   Frontend client uses `/api/v1/clusters/connect-aws` but backend exposes `/api/v1/clusters/connect`. This breaks cluster add/connection if the UI flow is used.
*   **Agent Injection Fails for Agentless Connect** (`backend/services/cluster_service.py`, `backend/api/cluster_routes.py`):
    *   `connect_aws_cluster` creates a placeholder `Account` with **empty** `role_arn` and no `external_id`.  
    *   `auto_install_agent` requires a valid `account.role_arn` and will fail with: “Cluster must be associated with an AWS account with a valid role ARN”.
*   **Discovery Worker Skips Accounts Missing Role/External ID** (`backend/workers/tasks/discovery.py`):
    *   Discovery ignores accounts without `role_arn` or `external_id`, so clusters never get discovered and no data is fetched.
*   **Platform Credentials Required for Discovery & Injection** (`backend/workers/tasks/discovery.py`, `backend/services/agent_injector.py`):
    *   STS assume-role depends on platform credentials in `SystemConfig` or environment. If not configured, discovery and agent injection will fail.
*   ~~**Cluster List API Returns Placeholder Metrics** (`backend/services/cluster_service.py`):~~
    *   ~~`list_clusters` returns `node_count`, `spot_count`, and `monthly_cost` as **0** regardless of DB values, so UI KPIs appear empty.~~ ✅ **RESOLVED** - Now returns actual database values.
*   ~~**Cluster CA Data Not Stored** (`backend/models/cluster.py`, `backend/workers/tasks/discovery.py`, `backend/services/agent_injector.py`):~~
    *   ~~Agent injector requires base64 CA cert, but discovery does not persist CA data and the model has no CA field. Injection fails when CA data is missing.~~ ✅ **RESOLVED** - Added `ca_data` field to model and discovery now saves CA data.

## Frontend Limitations
*   **Billing Page**: The billing history and plan details are currently using mock data. Needs implementation against Stripe or similar provider.
*   **Cluster Add/Connect UI Missing**:
    *   No visible “Add Cluster” or “Connect AWS” flow in the UI (ClusterConnect modal not present). Cluster creation relies on background discovery only.
*   **Refresh Discovery Button Doesn’t Trigger Discovery** (`frontend/src/components/clusters/ClusterList.jsx`):
    *   “Refresh Discovery” only re-fetches `/clusters` list; it doesn’t kick off a new discovery scan. If the worker is down, data stays stale.
