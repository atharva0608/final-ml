# Cluster Onboarding Implementation Guide

## Overview
Agent-based cluster connection flow for CLIENT users only (similar to CAST AI approach).

## User Flow

### Step 1: Provider Selection
- User selects K8s provider (EKS, AKS, GKE, OpenShift, kOps, Other)
- User enters cluster name
- Click "Generate Script"

### Step 2: Agent Installation
- System generates Helm/kubectl installation script
- User copies and runs script in their terminal
- Script installs read-only monitoring agent
- User clicks "I ran the script"

### Step 3: Verification & Costs
- System verifies agent connection
- User provides resource costs (CPU/h, Memory/h)
- Cluster is now connected and monitored

## Backend API Endpoints Needed

### 1. Generate Installation Script
```
POST /api/v1/clusters/generate-install-script
```

**Request:**
```json
{
  "provider": "eks",
  "cluster_name": "my-production-cluster"
}
```

**Response:**
```json
{
  "cluster_id": "uuid-here",
  "script": "kubectl apply -f https://spotoptimizer.com/agent/install.yaml\nkubectl set env deployment/spot-agent CLUSTER_ID=uuid-here -n spot-system"
}
```

**Script Template:**
```bash
# Create namespace
kubectl create namespace spot-optimizer-system

# Create service account with read-only permissions
kubectl apply -f - <<EOF
apiVersion: v1
kind: ServiceAccount
metadata:
  name: spot-optimizer-agent
  namespace: spot-optimizer-system
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: spot-optimizer-reader
rules:
- apiGroups: [""]
  resources: ["nodes", "pods", "services", "namespaces"]
  verbs: ["get", "list", "watch"]
- apiGroups: ["apps"]
  resources: ["deployments", "daemonsets", "statefulsets"]
  verbs: ["get", "list", "watch"]
- apiGroups: ["batch"]
  resources: ["jobs", "cronjobs"]
  verbs: ["get", "list", "watch"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: spot-optimizer-reader-binding
subjects:
- kind: ServiceAccount
  name: spot-optimizer-agent
  namespace: spot-optimizer-system
roleRef:
  kind: ClusterRole
  name: spot-optimizer-reader
  apiGroup: rbac.authorization.k8s.io
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: spot-optimizer-agent
  namespace: spot-optimizer-system
spec:
  replicas: 1
  selector:
    matchLabels:
      app: spot-optimizer-agent
  template:
    metadata:
      labels:
        app: spot-optimizer-agent
    spec:
      serviceAccountName: spot-optimizer-agent
      containers:
      - name: agent
        image: spotoptimizer/agent:latest
        env:
        - name: CLUSTER_ID
          value: "{cluster_id}"
        - name: API_ENDPOINT
          value: "https://api.spotoptimizer.com"
        - name: API_KEY
          value: "{api_key}"
EOF

echo "✅ Spot Optimizer Agent installed successfully!"
echo "Cluster ID: {cluster_id}"
```

### 2. Verify Connection
```
POST /api/v1/clusters/{cluster_id}/verify-connection
```

**Response:**
```json
{
  "connected": true,
  "agent_version": "1.0.0",
  "last_heartbeat": "2026-01-07T10:30:00Z",
  "nodes_discovered": 5,
  "pods_discovered": 45
}
```

### 3. Update Resource Costs
```
POST /api/v1/clusters/{cluster_id}/resource-costs
```

**Request:**
```json
{
  "cpu_cost": 3.56,
  "memory_cost": 1.27,
  "ingress_cost": null,
  "egress_cost": null,
  "storage_cost": null
}
```

**Response:**
```json
{
  "success": true,
  "cluster_id": "uuid-here",
  "costs_updated": true
}
```

## AWS STS Assume Role for Monitoring

**Purpose:** Read-only access to AWS resources for cost calculation and optimization recommendations.

### IAM Role Setup

**Trust Policy:**
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "AWS": "arn:aws:iam::SPOTOPTIMIZER_ACCOUNT:root"
      },
      "Action": "sts:AssumeRole",
      "Condition": {
        "StringEquals": {
          "sts:ExternalId": "${EXTERNAL_ID}"
        }
      }
    }
  ]
}
```

**Permissions Policy (Read-Only):**
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "ec2:Describe*",
        "eks:Describe*",
        "eks:List*",
        "autoscaling:Describe*",
        "cloudwatch:GetMetricStatistics",
        "cloudwatch:ListMetrics",
        "pricing:GetProducts"
      ],
      "Resource": "*"
    }
  ]
}
```

### Backend Implementation

**When cluster is connected:**
1. Agent sends cluster metadata
2. Backend detects AWS provider
3. System prompts user to create IAM role
4. User provides Role ARN + External ID
5. Backend uses STS AssumeRole to access AWS read-only

**Code Example:**
```python
import boto3

def assume_role_for_monitoring(role_arn, external_id):
    sts_client = boto3.client('sts')

    assumed_role = sts_client.assume_role(
        RoleArn=role_arn,
        RoleSessionName='SpotOptimizerMonitoring',
        ExternalId=external_id,
        DurationSeconds=3600
    )

    credentials = assumed_role['Credentials']

    # Create read-only clients
    ec2_client = boto3.client(
        'ec2',
        aws_access_key_id=credentials['AccessKeyId'],
        aws_secret_access_key=credentials['SecretAccessKey'],
        aws_session_token=credentials['SessionToken']
    )

    return ec2_client
```

## Database Schema Updates

### clusters table
```sql
ALTER TABLE clusters ADD COLUMN provider VARCHAR(50);
ALTER TABLE clusters ADD COLUMN agent_version VARCHAR(20);
ALTER TABLE clusters ADD COLUMN last_heartbeat TIMESTAMP;
ALTER TABLE clusters ADD COLUMN cpu_cost_per_hour DECIMAL(10,4);
ALTER TABLE clusters ADD COLUMN memory_cost_per_hour DECIMAL(10,4);
ALTER TABLE clusters ADD COLUMN aws_role_arn VARCHAR(255);
ALTER TABLE clusters ADD COLUMN aws_external_id VARCHAR(64);
```

## Security Considerations

1. **Agent is Read-Only:** No write access to cluster resources
2. **AWS Role is Read-Only:** No modification permissions
3. **External ID:** Prevents confused deputy problem
4. **HTTPS Only:** All agent communication encrypted
5. **API Key Authentication:** Each agent has unique key
6. **Heartbeat Monitoring:** Detect and alert on stale agents

## Next Steps

1. ✅ Frontend modal created (ClusterConnectModal.jsx)
2. 🔲 Create backend API endpoints
3. 🔲 Build agent Docker image
4. 🔲 Implement heartbeat monitoring
5. 🔲 Add AWS STS assume role flow
6. 🔲 Test end-to-end connection flow
