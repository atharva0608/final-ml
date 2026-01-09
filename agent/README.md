# Kubernetes Agent

The Kubernetes Agent is a lightweight, containerized service that runs within your Kubernetes cluster to collect metrics, execute optimization actions, and maintain real-time communication with the ML-powered cloud optimization backend.

## Architecture Overview

The agent consists of four main components:

### 1. Metrics Collector (`collector.py`)
- Collects pod metrics (CPU, memory, status) from Kubernetes Metrics Server
- Collects node metrics (capacity, allocatable resources)
- Monitors cluster events
- Batches and sends metrics to backend for ML analysis
- Runs continuously with configurable collection intervals

### 2. Action Actuator (`actuator.py`)
- Polls backend for optimization actions
- Executes actions on Kubernetes resources:
  - Pod eviction
  - Node cordoning/uncordoning
  - Node draining
  - Deployment scaling
  - Resource labeling
- Verifies actions using HMAC signatures
- Reports execution results back to backend

### 3. Heartbeat Sender (`heartbeat.py`)
- Sends periodic heartbeat to backend
- Provides HTTP health check endpoints (`/healthz`, `/readyz`)
- Monitors agent system resources (CPU, memory, disk)
- Tracks component health status

### 4. WebSocket Client (`websocket_client.py`)
- Maintains real-time bidirectional communication with backend
- Receives real-time action commands
- Handles configuration updates
- Automatic reconnection with exponential backoff
- Message buffering during disconnections

### Main Entry Point (`main.py`)
- Orchestrates all components
- Handles agent registration/deregistration
- Manages graceful shutdown
- Monitors and restarts failed components

## Prerequisites

### Kubernetes Cluster Requirements
- Kubernetes version 1.20 or higher
- Metrics Server installed and running
- Sufficient RBAC permissions (see below)

### Backend Requirements
- Backend API URL and WebSocket URL
- API key for authentication
- Secret key for action verification
- Cluster ID assigned by backend

## Installation

### Option 1: Helm Installation (Recommended)

```bash
# Add the Helm repository
helm repo add ml-optimizer https://charts.ml-optimizer.com
helm repo update

# Create namespace
kubectl create namespace ml-optimizer

# Create secret with credentials
kubectl create secret generic agent-credentials \
  --namespace ml-optimizer \
  --from-literal=api-key=YOUR_API_KEY \
  --from-literal=secret-key=YOUR_SECRET_KEY

# Install the agent
helm install ml-agent ml-optimizer/kubernetes-agent \
  --namespace ml-optimizer \
  --set cluster.id=YOUR_CLUSTER_ID \
  --set backend.url=https://api.ml-optimizer.com \
  --set backend.wsUrl=wss://api.ml-optimizer.com/ws
```

### Option 2: Manual Installation

#### Step 1: Create Namespace

```bash
kubectl create namespace ml-optimizer
```

#### Step 2: Create Service Account and RBAC

```yaml
# serviceaccount.yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: ml-agent
  namespace: ml-optimizer
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: ml-agent
rules:
  # Read cluster resources
  - apiGroups: [""]
    resources: ["nodes", "pods", "events", "namespaces"]
    verbs: ["get", "list", "watch"]

  # Read deployments
  - apiGroups: ["apps"]
    resources: ["deployments", "replicasets", "statefulsets"]
    verbs: ["get", "list", "watch"]

  # Update deployments for scaling
  - apiGroups: ["apps"]
    resources: ["deployments"]
    verbs: ["update", "patch"]

  # Pod eviction
  - apiGroups: [""]
    resources: ["pods/eviction"]
    verbs: ["create"]

  # Node management
  - apiGroups: [""]
    resources: ["nodes"]
    verbs: ["update", "patch"]

  # Read metrics
  - apiGroups: ["metrics.k8s.io"]
    resources: ["nodes", "pods"]
    verbs: ["get", "list"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: ml-agent
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: ml-agent
subjects:
  - kind: ServiceAccount
    name: ml-agent
    namespace: ml-optimizer
```

Apply the RBAC configuration:

```bash
kubectl apply -f serviceaccount.yaml
```

#### Step 3: Create Secret

```bash
kubectl create secret generic agent-credentials \
  --namespace ml-optimizer \
  --from-literal=api-key=YOUR_API_KEY \
  --from-literal=secret-key=YOUR_SECRET_KEY
```

#### Step 4: Deploy Agent

```yaml
# deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: ml-agent
  namespace: ml-optimizer
  labels:
    app: ml-agent
spec:
  replicas: 1
  selector:
    matchLabels:
      app: ml-agent
  template:
    metadata:
      labels:
        app: ml-agent
    spec:
      serviceAccountName: ml-agent
      containers:
        - name: agent
          image: ml-optimizer/kubernetes-agent:latest
          imagePullPolicy: Always
          ports:
            - name: http
              containerPort: 8080
              protocol: TCP
          env:
            - name: BACKEND_URL
              value: "https://api.ml-optimizer.com"
            - name: BACKEND_WS_URL
              value: "wss://api.ml-optimizer.com/ws"
            - name: CLUSTER_ID
              value: "YOUR_CLUSTER_ID"
            - name: API_KEY
              valueFrom:
                secretKeyRef:
                  name: agent-credentials
                  key: api-key
            - name: SECRET_KEY
              valueFrom:
                secretKeyRef:
                  name: agent-credentials
                  key: secret-key
            - name: COLLECTION_INTERVAL
              value: "60"
            - name: ACTION_POLL_INTERVAL
              value: "10"
          livenessProbe:
            httpGet:
              path: /healthz
              port: http
            initialDelaySeconds: 30
            periodSeconds: 10
            timeoutSeconds: 5
            failureThreshold: 3
          readinessProbe:
            httpGet:
              path: /readyz
              port: http
            initialDelaySeconds: 15
            periodSeconds: 5
            timeoutSeconds: 3
            failureThreshold: 3
          resources:
            requests:
              cpu: 100m
              memory: 256Mi
            limits:
              cpu: 500m
              memory: 512Mi
          securityContext:
            runAsNonRoot: true
            runAsUser: 1000
            readOnlyRootFilesystem: true
            allowPrivilegeEscalation: false
            capabilities:
              drop:
                - ALL
---
apiVersion: v1
kind: Service
metadata:
  name: ml-agent
  namespace: ml-optimizer
  labels:
    app: ml-agent
spec:
  type: ClusterIP
  ports:
    - port: 8080
      targetPort: http
      protocol: TCP
      name: http
  selector:
    app: ml-agent
```

Apply the deployment:

```bash
kubectl apply -f deployment.yaml
```

## Configuration

### Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `BACKEND_URL` | Yes | - | Backend API URL (e.g., https://api.ml-optimizer.com) |
| `BACKEND_WS_URL` | Yes | - | Backend WebSocket URL (e.g., wss://api.ml-optimizer.com/ws) |
| `API_KEY` | Yes | - | API key for authentication |
| `SECRET_KEY` | Yes | - | Secret key for HMAC verification |
| `CLUSTER_ID` | Yes | - | Unique cluster identifier |
| `AGENT_ID` | No | auto-generated | Unique agent identifier |
| `COLLECTION_INTERVAL` | No | 60 | Metrics collection interval in seconds |
| `ACTION_POLL_INTERVAL` | No | 10 | Action polling interval in seconds |
| `BATCH_SIZE` | No | 100 | Metrics batch size for sending |

## RBAC Permissions

The agent requires the following permissions:

### Read-Only Permissions
- **Nodes**: List, get, watch node information and metrics
- **Pods**: List, get, watch pod information and metrics
- **Events**: List, get, watch cluster events
- **Deployments**: List, get, watch deployment information

### Write Permissions
- **Pod Eviction**: Create pod eviction requests
- **Node Updates**: Update node labels and schedulable status
- **Deployment Updates**: Update deployment replicas and images

### Metrics Access
- **metrics.k8s.io**: Access to Metrics Server API for pod and node metrics

## Verification

### 1. Check Agent Status

```bash
# Check pod status
kubectl get pods -n ml-optimizer

# Check logs
kubectl logs -n ml-optimizer deployment/ml-agent -f

# Check health endpoints
kubectl port-forward -n ml-optimizer deployment/ml-agent 8080:8080

# In another terminal
curl http://localhost:8080/healthz
curl http://localhost:8080/readyz
curl http://localhost:8080/metrics
```

### 2. Verify Metrics Collection

Check the logs for metrics collection:

```bash
kubectl logs -n ml-optimizer deployment/ml-agent | grep "Collected metrics"
```

Expected output:
```
2024-01-15 10:30:00 - collector - INFO - Collected metrics for 50 pods
2024-01-15 10:30:00 - collector - INFO - Collected metrics for 3 nodes
2024-01-15 10:30:00 - collector - INFO - Successfully sent 150 metrics to backend
```

### 3. Verify Backend Connection

Check heartbeat and registration:

```bash
kubectl logs -n ml-optimizer deployment/ml-agent | grep -E "registered|heartbeat"
```

Expected output:
```
2024-01-15 10:25:00 - main - INFO - Agent registered successfully
2024-01-15 10:25:30 - heartbeat - DEBUG - Heartbeat sent successfully
```

### 4. Verify WebSocket Connection

```bash
kubectl logs -n ml-optimizer deployment/ml-agent | grep -i websocket
```

Expected output:
```
2024-01-15 10:25:00 - websocket_client - INFO - WebSocket connection established
2024-01-15 10:25:30 - websocket_client - DEBUG - Received ping
```

## Troubleshooting

### Agent Not Starting

**Symptom**: Pod is in CrashLoopBackOff

**Solutions**:
1. Check if required environment variables are set:
   ```bash
   kubectl describe pod -n ml-optimizer -l app=ml-agent
   ```

2. Verify secrets exist:
   ```bash
   kubectl get secret agent-credentials -n ml-optimizer
   ```

3. Check logs for configuration errors:
   ```bash
   kubectl logs -n ml-optimizer -l app=ml-agent
   ```

### Metrics Not Collected

**Symptom**: No metrics in logs

**Solutions**:
1. Verify Metrics Server is running:
   ```bash
   kubectl get deployment metrics-server -n kube-system
   kubectl top nodes  # Should return node metrics
   ```

2. Check RBAC permissions:
   ```bash
   kubectl auth can-i list pods.metrics.k8s.io --as=system:serviceaccount:ml-optimizer:ml-agent
   ```

3. Verify agent can access Metrics API:
   ```bash
   kubectl logs -n ml-optimizer -l app=ml-agent | grep -i "metrics"
   ```

### Cannot Connect to Backend

**Symptom**: "Failed to register with backend" or connection errors

**Solutions**:
1. Verify backend URL is accessible from cluster:
   ```bash
   kubectl run -it --rm debug --image=curlimages/curl --restart=Never -- \
     curl -v https://api.ml-optimizer.com/health
   ```

2. Check API key is correct:
   ```bash
   kubectl get secret agent-credentials -n ml-optimizer -o jsonpath='{.data.api-key}' | base64 -d
   ```

3. Verify network policies allow outbound connections

### Actions Not Executing

**Symptom**: Actions received but not executed

**Solutions**:
1. Check HMAC signature verification:
   ```bash
   kubectl logs -n ml-optimizer -l app=ml-agent | grep -i signature
   ```

2. Verify RBAC permissions for actions:
   ```bash
   kubectl auth can-i create pods/eviction --as=system:serviceaccount:ml-optimizer:ml-agent
   kubectl auth can-i patch nodes --as=system:serviceaccount:ml-optimizer:ml-agent
   ```

3. Check action execution logs:
   ```bash
   kubectl logs -n ml-optimizer -l app=ml-agent | grep -i "executing action"
   ```

### High Memory Usage

**Symptom**: Agent pod using excessive memory

**Solutions**:
1. Reduce batch size:
   ```yaml
   env:
     - name: BATCH_SIZE
       value: "50"  # Reduce from default 100
   ```

2. Increase collection interval:
   ```yaml
   env:
     - name: COLLECTION_INTERVAL
       value: "120"  # Increase from default 60
   ```

3. Increase resource limits:
   ```yaml
   resources:
     limits:
       memory: 1Gi
   ```

## Security Considerations

1. **API Keys**: Store API keys in Kubernetes Secrets, never in ConfigMaps or code
2. **RBAC**: Use least privilege principle - only grant necessary permissions
3. **Network Policies**: Restrict agent network access to backend only
4. **Pod Security**: Run as non-root user with read-only root filesystem
5. **HMAC Verification**: All actions are verified with HMAC signatures
6. **TLS**: Use TLS for all backend communication (HTTPS/WSS)

## Monitoring

### Metrics Exposed

The agent exposes metrics on `/metrics` endpoint:

- **System Metrics**: CPU, memory, disk usage
- **Component Health**: Status of collector, actuator, websocket
- **Network**: Bytes sent/received

### Prometheus Integration

```yaml
# ServiceMonitor for Prometheus Operator
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: ml-agent
  namespace: ml-optimizer
spec:
  selector:
    matchLabels:
      app: ml-agent
  endpoints:
    - port: http
      path: /metrics
      interval: 30s
```

## Upgrading

### Zero-Downtime Upgrade

```bash
# Update image version
kubectl set image deployment/ml-agent \
  agent=ml-optimizer/kubernetes-agent:v1.1.0 \
  -n ml-optimizer

# Monitor rollout
kubectl rollout status deployment/ml-agent -n ml-optimizer

# Rollback if needed
kubectl rollout undo deployment/ml-agent -n ml-optimizer
```

## Uninstalling

### Helm

```bash
helm uninstall ml-agent -n ml-optimizer
kubectl delete namespace ml-optimizer
```

### Manual

```bash
kubectl delete deployment ml-agent -n ml-optimizer
kubectl delete service ml-agent -n ml-optimizer
kubectl delete clusterrolebinding ml-agent
kubectl delete clusterrole ml-agent
kubectl delete serviceaccount ml-agent -n ml-optimizer
kubectl delete namespace ml-optimizer
```

## Support

- **Documentation**: https://docs.ml-optimizer.com
- **Issues**: https://github.com/ml-optimizer/kubernetes-agent/issues
- **Email**: support@ml-optimizer.com

## License

Copyright (c) 2024 ML Optimizer. All rights reserved.
