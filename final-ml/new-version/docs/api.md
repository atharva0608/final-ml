# API Reference

| ID (Current File, Method, Path, Summary, Auth Required, Frontend Ref) | Details |
|----------------------------------------------------------------------------------------|---------|
| `(backend/api/auth_routes.py, POST, /auth/login, User Login, No, Login.jsx)` | Authenticates user with email/password and returns JWT access/refresh tokens. |
| `(backend/api/auth_routes.py, POST, /auth/signup, User Signup, No, Signup.jsx)` | Registers a new user account and returns valid tokens. |
| `(backend/api/cluster_routes.py, GET, /clusters, List Clusters, Yes, ClusterList.jsx)` | Returns paginated list of clusters filtered by account, region, or status. |
| `(backend/api/cluster_routes.py, POST, /clusters/connect-aws, Connect AWS Cluster, Yes, ClusterConnectModal.jsx)` | Connects an EKS cluster using an invalid AWS IAM Role ARN (Agentless). |
| `(backend/api/cluster_routes.py, GET, /clusters/{id}, Get Cluster, Yes, ClusterDetails.jsx)` | Retrieves detailed information for a specific cluster. |
| `(backend/api/cluster_routes.py, POST, /clusters/{id}/heartbeat, Agent Heartbeat, Yes (Agent), Agent)` | Endpoint for Kubernetes Agent to report health status (every 60s). |
| `(backend/api/policy_routes.py, GET, /policies/{cluster_id}, Get Policy, Yes, PolicyConfig.jsx)` | Retrieves current optimization policy for a cluster. |
| `(backend/api/policy_routes.py, POST, /policies, Update Policy, Yes, PolicyConfig.jsx)` | Updates/Creates optimization policy including Karpenter settings. |
