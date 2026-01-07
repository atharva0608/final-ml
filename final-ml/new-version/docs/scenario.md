# Application Scenarios

## Scenario 1: Onboarding a New Client
**Actor**: New User (DevOps Engineer)
**Goal**: Connect an AWS EKS cluster to Spot Optimizer.
**Steps**:
1.  **Signup**: User registers via `/auth/signup`.
2.  **Dashboard**: User lands on the empty dashboard and clicks "Connect Cluster".
3.  **Connection**: User selects "Agentless (AWS STS)" and provides the IAM Role ARN.
4.  **Verification**: System assumes the role, lists clusters, and user selects "production-eks".
5.  **Success**: Cluster appears in the list with status `ACTIVE` (or `DISCOVERED`).

## Scenario 2: Configuring Cost Optimization
**Actor**: Platform Admin
**Goal**: Enable Karpenter-driven consolidation to reduce costs.
**Steps**:
1.  **Selection**: User clicks on "Configure Policy" for the target cluster.
2.  **Navigation**: Selects the "Karpenter" tab.
3.  **Configuration**:
    - Switches "Aggressive Consolidation" to **ON**.
    - Sets "TTL for Empty Nodes" to **30 seconds**.
    - Enables "Drift Detection".
4.  **Save**: User saves the policy.
5.  **Effect**: The backend stores this config in `cluster_policies` (JSONB). The Agent (when connected) will pull this config and apply it to the cluster CRDs.

## Scenario 3: Admin Monitoring
**Actor**: Super Admin
**Goal**: Monitor global platform health.
**Steps**:
1.  **Login**: Admin logs in with `admin@spotoptimizer.com`.
2.  **Routing**: System detects `SUPER_ADMIN` role and routes to `/admin`.
3.  **Observation**: Admin views the "Command Center" showing Total Active Clients, Managed EC2 count, and Platform Revenue.
4.  **Action**: Admin can toggle "Global Safe Mode" in System Configuration if a critical bug is detected.

## Scenario 4: Workload Rightsizing
**Actor**: Client User
**Goal**: Optimize specific deployment requests.
**Steps**:
1.  **Analysis**: User navigates to "Workload Efficiency" page.
2.  **Review**: Sees a table of deployments where "Request" > "Usage".
3.  **Action**: Clicks "Apply Recommendation" for `nginx-frontend`.
4.  **Result**: System generates a patch to update the Deployment resource with lower CPU/Memory requests.
