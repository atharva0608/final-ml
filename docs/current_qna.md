# Current State Q&A

This document contains questions and answers about the current state of the Spot Optimizer application architecture, features, and implementation details.

---

## Q1: What is the Agent Injection architecture and how does it work?

### Overview
Agent Injection is the automated process of deploying the Spot Optimizer monitoring agent into customer EKS clusters. This allows the platform to collect real-time metrics, monitor cluster health, and execute optimization actions without manual intervention.

### Architecture Components

#### 1. **Backend Service** (`AgentInjectorService`)
- **Location**: `backend/services/agent_injector.py`
- **Purpose**: Orchestrates the entire injection process
- **Key Configuration**:
  - Agent Image: `atharva608/spot-optimizer-agent:latest`
  - Namespace: `spot-optimizer`
  - Access Policy: `AmazonEKSClusterAdminPolicy`

#### 2. **API Endpoint**
- **Endpoint**: `POST /api/v1/clusters/{clusterId}/auto-install`
- **Location**: `backend/api/cluster_routes.py`
- **Flow**:
  1. Validates cluster exists and has AWS account with `role_arn`
  2. Generates/retrieves cluster API key for agent authentication
  3. Triggers background Celery task: `inject_agent_task.delay(cluster_id)`
  4. Returns `202 Accepted` with task ID

#### 3. **Background Worker**
- **Task**: `workers.agent.inject_agent`
- **Type**: Celery asynchronous task
- **Timeout**: Configurable (default: 5 minutes)

---

### Injection Process (4 Steps)

#### **Step 1: Cross-Account Role Assumption**

**Purpose**: Gain temporary AWS credentials to access the customer's EKS cluster.

**Process**:
```python
# Uses STS AssumeRole with:
# - Customer's role ARN (e.g., arn:aws:iam::123456789012:role/SpotOptimizerRole)
# - External ID (for security)
# - Platform credentials (from SystemConfig table)

response = sts_client.assume_role(
    RoleArn=role_arn,
    RoleSessionName='SpotOptimizerAgentInjector',
    ExternalId=external_id,
    DurationSeconds=3600  # 1 hour
)
```

**Credentials Obtained**:
- `AccessKeyId`
- `SecretAccessKey`
- `SessionToken`

**Security Note**: These temporary credentials are scoped to the customer's role and expire after 1 hour.

---

#### **Step 2: EKS Access Entry Creation**

**Purpose**: Grant the backend IAM principal (our platform) permission to manage the customer's EKS cluster.

**Process**:
```python
eks_client.create_access_entry(
    clusterName=cluster_name,
    principalArn=self.backend_role_arn,  # e.g., arn:aws:iam::654654204633:user/ml-project
    type='STANDARD'
)

# Then associate cluster admin policy
eks_client.associate_access_policy(
    clusterName=cluster_name,
    principalArn=self.backend_role_arn,
    policyArn='arn:aws:eks::aws:cluster-access-policy/AmazonEKSClusterAdminPolicy',
    accessScope={'type': 'cluster'}
)
```

**Key Details**:
- **Principal**: The backend's IAM identity (auto-detected via STS GetCallerIdentity)
- **Policy**: Grants cluster-wide admin permissions
- **Idempotent**: Handles `ResourceInUseException` if entry already exists

**Critical Fix Applied**: The access entry is created for the **backend IAM principal**, not the assumed role. This is why Step 3 must use backend credentials.

---

#### **Step 3: Kubernetes Authentication Token Generation**

**Purpose**: Generate a bearer token that authenticates the backend to the Kubernetes API.

**Process**:
```python
# IMPORTANT: Uses BACKEND credentials, NOT assumed role credentials
backend_credentials = self._get_backend_credentials(region)

# Creates a presigned STS GetCallerIdentity URL
sts_client = boto3.client('sts',
    aws_access_key_id=backend_credentials['access_key'],
    aws_secret_access_key=backend_credentials['secret_key'],
    aws_session_token=backend_credentials.get('session_token'),  # None for static creds
    region_name=region
)

url = signer.generate_presigned_url(
    params={
        'method': 'GET',
        'url': f'https://sts.{region}.amazonaws.com/?Action=GetCallerIdentity&Version=2011-06-15',
        'headers': {'x-k8s-aws-id': cluster_name}
    },
    expires_in=60
)

# Encode as Kubernetes token
token = 'k8s-aws-v1.' + base64.urlsafe_b64encode(url.encode('utf-8')).decode('utf-8').rstrip('=')
```

**Why Backend Credentials?**
- The EKS access entry was created for the backend IAM principal
- The token must contain the same IAM identity as the access entry
- If we used assumed role credentials, Kubernetes would reject the token (401 Unauthorized)

**Token Format**: `k8s-aws-v1.<base64-encoded-presigned-url>`

---

#### **Step 4: Deploy Agent Manifests**

**Purpose**: Create all necessary Kubernetes resources for the agent.

**Kubernetes Resources Created**:

1. **Namespace**: `spot-optimizer`
   ```yaml
   apiVersion: v1
   kind: Namespace
   metadata:
     name: spot-optimizer
   ```

2. **Secret**: `spot-agent-secret`
   ```yaml
   apiVersion: v1
   kind: Secret
   metadata:
     name: spot-agent-secret
   stringData:
     API_KEY: "<cluster-api-key>"
   ```

3. **ConfigMap**: `spot-agent-config`
   ```yaml
   apiVersion: v1
   kind: ConfigMap
   metadata:
     name: spot-agent-config
   data:
     BACKEND_URL: "https://backend.example.com"  # HTTP for heartbeats
     BACKEND_WS_URL: "wss://backend.example.com/ws/cluster/{id}"  # WebSocket for real-time
     CLUSTER_ID: "uuid-of-cluster"
   ```

4. **ServiceAccount**: `spot-agent-sa`
   ```yaml
   apiVersion: v1
   kind: ServiceAccount
   metadata:
     name: spot-agent-sa
   ```

5. **ClusterRole**: `spot-agent-role`
   ```yaml
   apiVersion: rbac.authorization.k8s.io/v1
   kind: ClusterRole
   metadata:
     name: spot-agent-role
   rules:
   - apiGroups: [""]
     resources: ["nodes", "pods", "namespaces"]
     verbs: ["get", "list", "watch"]
   - apiGroups: [""]
     resources: ["pods"]
     verbs: ["delete"]
   - apiGroups: ["metrics.k8s.io"]
     resources: ["nodes", "pods"]
     verbs: ["get", "list"]
   - apiGroups: ["batch"]
     resources: ["jobs"]
     verbs: ["create", "delete", "get", "list"]
   ```

6. **ClusterRoleBinding**: `spot-agent-binding`
   ```yaml
   apiVersion: rbac.authorization.k8s.io/v1
   kind: ClusterRoleBinding
   metadata:
     name: spot-agent-binding
   subjects:
   - kind: ServiceAccount
     name: spot-agent-sa
     namespace: spot-optimizer
   roleRef:
     kind: ClusterRole
     name: spot-agent-role
     apiGroup: rbac.authorization.k8s.io
   ```

   **Note**: Uses `RbacV1Subject` (not `V1Subject`) for Kubernetes client v29 compatibility.

7. **DaemonSet**: `spot-agent`
   ```yaml
   apiVersion: apps/v1
   kind: DaemonSet
   metadata:
     name: spot-agent
     namespace: spot-optimizer
   spec:
     selector:
       matchLabels:
         app: spot-agent
     template:
       metadata:
         labels:
           app: spot-agent
       spec:
         serviceAccountName: spot-agent-sa
         hostNetwork: true
         tolerations:
         - operator: Exists  # Run on all nodes including tainted ones
         containers:
         - name: agent
           image: atharva608/spot-optimizer-agent:latest
           imagePullPolicy: Always
           env:
           - name: API_KEY
             valueFrom:
               secretKeyRef:
                 name: spot-agent-secret
                 key: API_KEY
           - name: BACKEND_URL
             valueFrom:
               configMapKeyRef:
                 name: spot-agent-config
                 key: BACKEND_URL
           - name: BACKEND_WS_URL
             valueFrom:
               configMapKeyRef:
                 name: spot-agent-config
                 key: BACKEND_WS_URL
           - name: CLUSTER_ID
             valueFrom:
               configMapKeyRef:
                 name: spot-agent-config
                 key: CLUSTER_ID
           - name: NODE_NAME
             valueFrom:
               fieldRef:
                 fieldPath: spec.nodeName
           - name: HOST_PROC
             value: /host/proc
           resources:
             requests:
               cpu: 50m
               memory: 64Mi
             limits:
               cpu: 200m
               memory: 256Mi
           volumeMounts:
           - name: host-proc
             mountPath: /host/proc
             readOnly: true
         volumes:
         - name: host-proc
           hostPath:
             path: /proc
   ```

**Deployment Strategy**: DaemonSet ensures one agent pod runs on every node in the cluster.

---

### Agent Functionality

Once deployed, each agent pod:

1. **Sends Heartbeats** (every 30 seconds)
   - Endpoint: `POST /api/v1/agents/heartbeat`
   - Updates `clusters.last_heartbeat` timestamp
   - Includes health metrics and component status

2. **Collects Metrics**
   - Node resource utilization (CPU, memory, disk)
   - Pod metrics via Kubernetes Metrics API
   - Network I/O statistics
   - Process-level metrics from `/host/proc`

3. **Executes Actions**
   - Pod deletion (for cleanup/optimization)
   - Job creation (for batch operations)
   - Real-time command execution via WebSocket

4. **Health Monitoring**
   - HTTP endpoints: `/healthz`, `/readyz`, `/metrics`
   - Kubernetes liveness and readiness probes
   - Component health tracking (collector, actuator, websocket)

---

### Security Considerations

1. **Cross-Account Trust**:
   - Customer creates IAM role with trust policy allowing platform to assume it
   - External ID prevents confused deputy problem
   - Role has minimal EKS permissions

2. **API Key Authentication**:
   - Each cluster has unique API key
   - Stored in Kubernetes Secret (not visible to pods)
   - Validated on every heartbeat and WebSocket connection

3. **RBAC Least Privilege**:
   - Agent ServiceAccount has minimal required permissions
   - Read-only access to most resources
   - Write access limited to specific actions (pod deletion, job creation)

4. **Network Security**:
   - TLS/SSL for all HTTP communications
   - WSS (WebSocket Secure) for real-time connections
   - Backend URL configurable per environment

---

### Error Handling & Fixes Applied

**Issue 1: 401 Unauthorized (Fixed)**
- **Cause**: Token generated with assumed role credentials instead of backend credentials
- **Fix**: Generate token using backend IAM credentials matching the access entry principal
- **Code**: `backend_credentials = self._get_backend_credentials(region)`

**Issue 2: ImagePullBackOff (Fixed)**
- **Cause**: Agent image didn't exist in Docker Hub
- **Fix**: Built and pushed image to `atharva608/spot-optimizer-agent:latest`
- **Verification**: `docker pull atharva608/spot-optimizer-agent:latest`

**Issue 3: V1Subject AttributeError (Fixed)**
- **Cause**: Kubernetes client v29 renamed `V1Subject` to `RbacV1Subject`
- **Fix**: Updated code to use `k8s_client.RbacV1Subject`
- **Line**: `agent_injector.py:482`

**Issue 4: ConfigMap URL Mismatch (Fixed)**
- **Cause**: BACKEND_URL was set to WebSocket URL, but heartbeat needs HTTP
- **Fix**: Added separate `BACKEND_URL` (HTTP) and `BACKEND_WS_URL` (WebSocket)
- **Impact**: Agents can now send heartbeats successfully

---

### Frontend Integration

**Button**: "Activate Optimization" (shown when `cluster.status === 'DISCOVERED'`)

**Location**: `frontend/src/components/clusters/ClusterList.jsx:567`

**Click Handler**:
```javascript
async (e) => {
  e.stopPropagation();
  try {
    toast.loading('Injecting agent into cluster...', { id: 'inject-' + cluster.id });
    await clusterAPI.autoInstallAgent(cluster.id);
    toast.success('Agent injected successfully! Cluster is now active.', { id: 'inject-' + cluster.id });
    fetchClusters();
  } catch (error) {
    toast.error('Failed to inject agent: ' + (error.response?.data?.detail || error.message), { id: 'inject-' + cluster.id });
  }
}
```

**Status Transitions**:
- `DISCOVERED` → (Agent Injection) → `ACTIVE`
- Once heartbeats start arriving, cluster shows as "online"

---

### Monitoring & Verification

**Check Agent Deployment**:
```bash
kubectl get pods -n spot-optimizer
kubectl logs -f <pod-name> -n spot-optimizer
```

**Check Heartbeats in Database**:
```sql
SELECT name, status, last_heartbeat, agent_installed
FROM clusters
WHERE id = '<cluster-id>';
```

**Check Backend Logs**:
```bash
docker logs -f spot-optimizer-backend | grep heartbeat
```

**Expected Result**:
- Pods in `Running` state
- `last_heartbeat` updating every 30 seconds
- Cluster status = `ACTIVE`
- Frontend shows cluster as "online"

---

### File Locations

- **Service**: `backend/services/agent_injector.py`
- **API Route**: `backend/api/cluster_routes.py`
- **Worker Task**: `backend/workers/tasks/agent.py`
- **Agent Code**: `agent/` directory
- **Agent Dockerfile**: `agent/Dockerfile`
- **Frontend Button**: `frontend/src/components/clusters/ClusterList.jsx`
- **Agent Routes**: `backend/api/agent_routes.py` (heartbeat endpoint)

---

