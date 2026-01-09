# Frontend Component Reference

| ID (Current File, Type, Backend Ref, Schema Ref, Frontend Ref, Action Type, Count, API) | Description |
|-----------------------------------------------------------------------------------------------|-------------|
| `(frontend/src/components/auth/Login.jsx, Component, backend/api/auth_routes.py, backend/schemas/auth_schemas.py, -, User Action, 1, POST /auth/login)` | **Login Page**: Handles user authentication, credential validation, and token storage. Redirects based on user role. |
| `(frontend/src/components/clusters/ClusterList.jsx, Component, backend/api/cluster_routes.py, backend/schemas/cluster_schemas.py, -, View/Action, 1, GET /clusters)` | **Cluster List**: Displays paginated list of clusters with status, region, and cost metrics. Includes "Connect Cluster" action. |
| `(frontend/src/components/clusters/ClusterDetails.jsx, Component, backend/api/cluster_routes.py, backend/schemas/cluster_schemas.py, ClusterList.jsx, View, 1, GET /clusters/{id})` | **Cluster Details**: Detailed view of a specific cluster including instance list, health status, and agent details. |
| `(frontend/src/components/clusters/ClusterConnectModal.jsx, Component, backend/api/cluster_routes.py, backend/schemas/cluster_schemas.py, ClusterList.jsx, User Action, 1, POST /clusters/connect-aws)` | **Connect Modal**: UI for connecting new clusters via AWS STS or manual agent installation. |
| `(frontend/src/components/policies/PolicyConfig.jsx, Component, backend/api/policy_routes.py, backend/schemas/policy_schemas.py, ClusterList.jsx, Configuration, 1, POST /policies)` | **Policy Config**: Configuration form for Node Scaling, Karpenter settings, and scheduling policies. |
| `(frontend/src/components/admin/AdminDashboard.jsx, Component, backend/api/admin_routes.py, -, MainLayout.jsx, Dashboard, 1, GET /admin/stats)` | **Admin Command Center**: Global KPIs, Live Activity Feed, and System Health overview for Super Admins. |
| `(frontend/src/components/admin/AdminLab.jsx, Component, -, -, AdminDashboard.jsx, Experimental, 1, -)` | **The Lab**: Experimental features like Model Registry and Global Risk Map. |
| `(frontend/src/components/admin/AdminConfig.jsx, Component, -, -, AdminDashboard.jsx, Configuration, 1, -)` | **System Config**: Global system settings, Safe Mode toggle, and Risk Parameters. |
| `(frontend/src/components/shared/StatsCard.jsx, Component, -, -, -, UI Element, Many, -)` | **Stats Card**: Reusable UI component for displaying KPI metrics with trends. |
| `(frontend/src/components/layout/MainLayout.jsx, Component, -, -, -, Layout, 1, -)` | **Main Layout**: Application shell with Role-Based Sidebar navigation (Admin vs Client). |
