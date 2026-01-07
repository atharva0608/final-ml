# Feature Mapping

## 1. Authentication & Security
- **User Registration**: Sign up with email/password validation (uppercase, number, symbol).
- **Secure Login**: JWT-based authentication with Access and Refresh tokens.
- **Role-Based Access Control (RBAC)**: Strict separation between `CLIENT` and `SUPER_ADMIN`.
- **Password Management**: Change password functionality.

## 2. Cluster Management
- **Cluster List**: View all managed clusters with high-level metrics (Cost, Node Count).
- **AWS Integration**: Connect EKS clusters using secure IAM Role Assumption (STS).
- **Agentless Onboarding**: Discover clusters without installing an agent first.
- **Health Monitoring**: Real-time heartbeat tracking from connected agents.

## 3. Cost Optimization Configuration
- **Policy Management**: Granular control over optimization strategies.
- **Karpenter Integration**:
    - **Aggressive Consolidation**: Toggle for high-density packing.
    - **Drift Detection**: Auto-correction of configuration drift.
    - **TTL Settings**: Control node lifetime.
- **Scheduling**: Define maintenance windows or "Always On" optimization.

## 4. Admin Command Center
- **Global Dashboard**: Aggregated metrics for all clients (Revenue, Managed Nodes).
- **System Configuration**: Global "Safe Mode" and Risk Parameter tuning.
- **Lab Access**: Experimental features (Model Registry, Risk Maps).
- **Billing Management**: Plan configuration and MRR tracking.

## 5. Workload Efficiency (Rightsizing)
- **Utilization Analysis**: Compare Requested vs. Used resources.
- **Recommendations**: AI-driven suggestions for CPU/Memory requests.
- **One-Click Fix**: Apply recommendations directly to Kubernetes deployments.

## 6. Audit & Governance
- **Activity Log**: Chronological log of all actions (Login, Policy Change, Optimization).
- **Automated Event Tagging**: Distinct visual badges for system-triggered actions (e.g., Karpenter Scaling).
