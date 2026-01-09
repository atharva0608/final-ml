# 📜 Change Ledger
**Active Tracking of Significant Codebase Modifications**

| Date | Component | Change Type | Description |
| :--- | :--- | :--- | :--- |
| **2026-01-09** | **Backend / Settings** | `Feature` | Implemented `Settings` module (Routes, Service, Schemas, Mocks). Fixed Frontend 404s. |
| **2026-01-09** | **Backend / Admin** | `Feature` | Implemented `get_billing_info` and `get_dashboard_stats` endpoints. |
| **2026-01-09** | **Backend / Account** | `Fix` | Added `validate` and `set-default` endpoints to resolve Frontend gaps. |
| **2026-01-09** | **Frontend / Admin** | `Refactor` | Converted `AdminBilling` and `AdminDashboard` to use real API calls instead of hardcoded data. |
| **2026-01-09** | **Docs / Catalog** | `Update` | Updated `02_backend_catalog.md` and `01_frontend_catalog.md` to 100% coverage. |
| **2026-01-09** | **Docs / Gap Analysis** | `New` | Created `03_frontend_backend_gap_analysis.md`. |
| **2026-01-09** | **Docs / Catalog** | `Sync` | Synchronized Agent and Config IDs in `02_backend_catalog.md` with user-provided `missing.txt` definitions. |
| **2026-01-09** | **Infrastructure / Git** | `Fix` | **CRITICAL**: Reverted changes on `ecc-Tech-Dev-ML-OPs/ml-AURA`. Moved all new work to `atharva0608/final-ml` (Commit `b20bce1`). |
| **2026-01-09** | **Infrastructure / File Sys** | `Refactor` | Flattened repository structure. Removed `final-ml/new-version` nesting. All project files now in root. |
| **2026-01-09** | **Docs / Catalog** | `Update` | Added 17 missing components to `02_backend_catalog.md` (Package markers, Context Docs, Internal INFOs, Root Assets) per user audit. |
| **2026-01-09** | **Docs / Catalog** | `Comprehensive` | Added 8 FE components (Onboarding, Admin Lab) to `01_frontend_catalog.md` and 23 INFO.md/Project docs to `02_backend_catalog.md` per user's detailed audit. Total files now cataloged: ~240. |
| **2026-01-09** | **Frontend / Admin** | `Fix` | Added missing React imports (`useEffect`, icons, recharts) to `AdminBilling.jsx` and `AdminDashboard.jsx`. |
| **2026-01-09** | **Backend / API** | `Feature` | Created `health_routes.py` with `/health/system` endpoint for system health monitoring. |
| **2026-01-09** | **Backend / API** | `Feature` | Created `optimization_routes.py` with `/optimization/rightsizing/{id}` endpoint for resize recommendations. |
| **2026-01-09** | **Frontend / Shared** | `Feature` | Created `EmptyState.jsx` component for graceful no-data handling. |
| **2026-01-09** | **Backend / API** | `Update` | Registered `health_router` and `optimization_router` in `backend/api/__init__.py`. |
| **2026-01-09** | **Docs / Catalog** | `Verify` | Confirmed all items from `missing.txt` are present in catalogs: Agent components, config files, stub status tracked. |
| **2026-01-09** | **Frontend / RightSizing** | `Refactor` | Removed mock data arrays. Now fetches from `/optimization/rightsizing/{id}`. Added empty state handling with `EmptyState` component. |
| **2026-01-09** | **Frontend / AdminHealth** | `Refactor` | Replaced 60-line `mockHealth` object with real API call to `/health/system`. |
| **2026-01-09** | **Frontend / Dashboard** | `Refactor` | Replaced mock activity feed with real `/audit/logs` API call. Uses `costTimeSeries` from `useDashboard` hook. |
| **2026-01-09** | **Frontend / Hibernation** | `Refactor` | Removed hardcoded `HOURLY_COST_AVG`. Fetches dynamic cost from `/metrics/cluster/{id}`. |
| **2026-01-09** | **Frontend / API** | `Feature` | Added `optimizationAPI` and `healthAPI` definitions to `api.js`. |
| **2026-01-09** | **Backend / Core** | `Fix` | Fixed `health_service.py`: Replaced wrong `app.` imports with `backend.` (4 occurrences). Removed orphaned `OptimizationJob` references. Backend now starts successfully. |
| **2026-01-09** | **Frontend / API** | `Fix` | Added missing `getDashboardStats` and `getBilling` methods to `adminAPI` in `api.js`. |
| **2026-01-09** | **Frontend / Admin** | `Fix` | Added styled error state UI to `AdminDashboard.jsx` and `AdminBilling.jsx` instead of blank page on API failure. |
| **2026-01-09** | **Backend / Workers** | `Feature` | Added Celery Beat schedule to `app.py`: discovery scan (5 min), pricing collector (10 min), optimization analysis (15 min). |
| **2026-01-09** | **Backend / Services** | `Fix` | Updated `ClusterService.discover_clusters()` to trigger discovery worker task asynchronously and return existing clusters from DB instead of empty list. |
| **2026-01-09** | **Backend / Core** | `Fix` | Fixed `action_executor.py`: Replaced wrong `app.` imports with `backend.`, implemented dynamic AMI lookup from existing instance instead of hardcoded `ami-12345678`. |
| **2026-01-09** | **Backend / Models** | `Fix` | Added `DISCOVERED` value to `ClusterStatus` enum in `cluster.py` and migrated DB to include new enum value. |
| **2026-01-09** | **Frontend / Admin** | `Fix` | Fixed `AdminHealth.jsx` to use `healthAPI` from `api.js` with correct base URL instead of relative fetch. |
| **2026-01-09** | **Frontend / Admin** | `Improve` | Modified `AdminDashboard.jsx` and `AdminBilling.jsx` to show full layout with KPI cards even when API fails - data sections use graceful fallback values. |
| **2026-01-09** | **Backend / Admin** | `Fix` | Replaced hardcoded mocked data in `admin_service.get_dashboard_stats` (MRR, charts, feed) with real calculations (MRR derived from platform cost) and empty list fallbacks. |
| **2026-01-09** | **Frontend / Admin** | `Feature` | Updated `AdminLab.jsx` to fetch real experiments from `labAPI` instead of hardcoded data. |
| **2026-01-09** | **Frontend / Client** | `Fix` | Updated `Dashboard.jsx` to use real `clusterAPI.listClusters` for Cluster Map and real `costTimeSeries` for Savings Projection (removing fake fallbacks). |
| **2026-01-09** | **Backend / Admin** | `Fix` | Resolved 500 Error in Admin Dashboard by syncing `PlatformStats` schema with `admin_service` implementation and adding missing fields. |
| **2026-01-09** | **Frontend / Client** | `Fix` | Fixed `TypeError: h.map is not a function` in `Dashboard.jsx` by correctly accessing `response.data.clusters` from the `ClusterList` API response. |
| **2026-01-09** | **Frontend / Admin** | `Fix` | Fixed potential empty data issue in `AdminLab.jsx` by correcting `response.data.items` to `response.data.experiments` matching `ExperimentList` schema. |
| **2026-01-09** | **Backend / Core** | `Fix` | Resolved recursing 500 Errors by standardizing Enums (`InstanceLifecycle`, `ExperimentStatus`) to uppercase and adding missing `DRAFT` status in Lab Service. |
| **2026-01-09** | **Backend / Lab** | `Fix` | Fixed `AttributeError: Account.user_id` in `lab_service.py` by implementing correct `_get_user_org` helper and filtering by `Account.organization_id`. |
| **2026-01-09** | **Backend / Lab** | `Fix` | Resolved `AttributeError: 'ExperimentFilter' object has no attribute 'cluster_id'` by adding missing fields to Pydantic model. |
| **2026-01-09** | **Docs / Catalog** | `Update` | Updated `02_backend_catalog.md` to reflect "Real" implementation status of `ClusterService` (Discovery), `ActionExecutor` (Spot Rep), and removal of zombies (`Pricing`, `Rightsizer`). |
| **2026-01-09** | **Docs / Audit** | `Update` | Deep audit of `backend/`: Identified `PricingCollector` worker disconnection, `MLModelServer`/`BinPacker` as standalone modules, and `SettingsService` as in-memory mock. Updated catalog statuses. |
| **2026-01-09** | **Backend / Lab** | `Fix` | Resolved `InvalidRequestError` in `list_experiments` by adding missing `cluster_id` FK/relationship to `LabExperiment` model and patching DB schema. |
| **2026-01-09** | **Docs / Frontend** | `Update` | Refined `01_frontend_catalog.md` and Gap Analysis. Annotated mocked/simplified components and added public assets (`index.html`, `manifest.json`). Confirmed 100% file coverage. |
| **2026-01-09** | **Backend / Worker** | `Fix` | Connected `PricingCollector` to Celery app. Registered `collect_spot_prices` (Every 10m) and `collect_ondemand_prices` (Daily). Updated Catalogs. |
| **2026-01-09** | **Backend / API** | `Critical Fix` | Populated empty `health_routes.py` and `optimization_routes.py` with implementation logic. Registered routes in `api/__init__.py`. |
| **2026-01-09** | **Backend / Services** | `Critical Fix` | Implemented real AWS `boto3` logic in `AccountService` (verify_connection) and `ClusterService` (discover_clusters). |
| **2026-01-09** | **Backend / Workers** | `Critical Fix` | Configured `workers/app.py` schedule. Fixed `discovery.py` to alias `run_discovery` for Celery task compatibility. |
| **2026-01-09** | **Frontend / RightSizing** | `Critical Fix` | Updated `RightSizing.jsx` to fetch real recommendations from `/optimization/rightsizing/ALL`. Fixed syntax errors. |
| **2026-01-09** | **Frontend / Build** | `Critical Fix` | Fixed `Attempted import error: 'api' is not exported` by adding named export in `services/api.js`. |
| **2026-01-09** | **Backend / Workers** | `Critical Fix` | Fixed Worker Crash: Renamed `celery_app` to `app` in `workers/app.py` to match `__init__.py` export. Added `include` for task modules. |
| **2026-01-09** | **Backend / API** | `Critical Fix` | Fixed `ImportError` in `health_routes.py` by replacing missing `get_current_active_superuser` with `require_super_admin`. |
| **2026-01-09** | **Backend / Health** | `Critical Fix` | Fixed `ModuleNotFoundError` in `health_service.py` by correcting Celery app import to `from backend.workers import app`. |
| **2026-01-09** | **Backend / Services** | `Critical Fix` | Fixed `ImportError` in `account_service.py` by restoring missing `get_account_service` factory function. |
| **2026-01-09** | **Backend / Schemas** | `Fix` | Resolved Pydantic warning `Field "model_id" has conflict` in `lab_schemas.py` by adding `protected_namespaces` config. |
| **2026-01-09** | **Frontend / Admin** | `Fix` | Fixed `ReferenceError: loading is not defined` in `AdminHealth.jsx` by adding missing state variables. Rebuilt frontend container. |
| **2026-01-09** | **Backend / Health** | `Perf` | Optimized `/health/system` by skipping AWS connectivity check when credentials are missing, reducing latency for local dev. |
