# Backend Component Reference

| ID (Current File, Type, Backend Ref, Schema Ref, Frontend Ref, Action Type, Count, API) | Description |
|-----------------------------------------------------------------------------------------------|-------------|
| `(backend/api/auth_routes.py, API Router, -, backend/schemas/auth_schemas.py, Login.jsx, Auth, 1, /auth/*)` | **Auth Routes**: Handles Signup, Login, Token Refresh, Password Management, and Logout. |
| `(backend/api/cluster_routes.py, API Router, backend/services/cluster_service.py, backend/schemas/cluster_schemas.py, ClusterList.jsx, Management, 1, /clusters/*)` | **Cluster Routes**: CRUD operations for Clusters, Discovery, AWS Connection, and Agent Heartbeats. |
| `(backend/services/auth_service.py, Service, backend/models/user.py, backend/schemas/auth_schemas.py, -, Logic, 1, -)` | **Auth Service**: Business logic for user authentication, password hashing, and token generation. |
| `(backend/services/cluster_service.py, Service, backend/models/cluster.py, backend/schemas/cluster_schemas.py, -, Logic, 1, -)` | **Cluster Service**: Business logic for cluster registration, AWS STS assumption, and agent command generation. |
| `(backend/models/user.py, Model, -, -, -, Database, 1, -)` | **User Model**: SQLAlchemy model for User entity (email, password_hash, role, etc.). |
| `(backend/models/cluster.py, Model, -, -, -, Database, 1, -)` | **Cluster Model**: SQLAlchemy model for Cluster entity including status, stats, and AWS metadata. |
| `(backend/models/cluster_policy.py, Model, -, backend/schemas/policy_schemas.py, -, Database, 1, -)` | **ClusterPolicy Model**: SQLAlchemy model for storing detailed optimization configuration (JSONB). |
| `(backend/core/dependencies.py, Utility, -, -, -, Security, 1, -)` | **Dependencies**: FastAPI dependencies for User Authentication (`get_current_user`) and Database Sessions (`get_db`). |
| `(backend/workers/tasks/optimization.py, Worker, -, -, -, Background Job, 1, -)` | **Optimization Worker**: Celery task for running spot instance optimization logic. |
