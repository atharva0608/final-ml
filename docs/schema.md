# Schema Reference

| ID (Current File, Type, Backend Ref, Schema Ref, Frontend Ref, Action Type, Count, API) | Description |
|-----------------------------------------------------------------------------------------------|-------------|
| `(backend/schemas/auth_schemas.py, Schema, backend/api/auth_routes.py, -, Login.jsx, Validation, 1, -)` | **Auth Schemas**: `LoginRequest`, `SignupRequest`, `TokenResponse`, `LoginResponse`, `UserContext`. |
| `(backend/schemas/cluster_schemas.py, Schema, backend/api/cluster_routes.py, -, ClusterList.jsx, Validation, 1, -)` | **Cluster Schemas**: `ClusterCreate`, `ClusterResponse`, `AWSConnectRequest`, `ClusterList`, `InstanceInfo`. |
| `(backend/schemas/policy_schemas.py, Schema, backend/api/policy_routes.py, -, PolicyConfig.jsx, Validation, 1, -)` | **Policy Schemas**: `PolicyConfig`, `KarpenterSettings`, `PolicyCreate`, `PolicyUpdate`. |
| `(backend/schemas/common_schemas.py, Schema, -, -, -, Validation, 1, -)` | **Common Schemas**: Shared Pydantic models (e.g., `ErrorResponse`, `PaginationDefaults`). |
