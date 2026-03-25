# API Testing Commands — Complete Reference

> **Base URL:** `http://localhost:8000`
> **User:** `ath@gmail.com` / `Atharva@123`
> **Container:** `spot-optimizer-backend`

---

## Quick Setup — Enter Container & Set Auth Token

```bash
# Step 1: Enter the running backend container
docker exec -it spot-optimizer-backend bash

# Step 2: Set base URL variable
BASE_URL="http://localhost:8000"

# Step 3: Login and capture token
TOKEN=$(curl -s -X POST $BASE_URL/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"ath@gmail.com","password":"Atharva@123"}' \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('access_token',''))")
echo "Token: $TOKEN"
```

> All subsequent commands assume you are **inside the container** and `$TOKEN` and `$BASE_URL` are set.

---

## Table of Contents

1. [Authentication](#1-authentication)
2. [Users & Preferences](#2-users--preferences)
3. [Clusters](#3-clusters)
4. [Agents](#4-agents)
5. [AI Agents](#5-ai-agents)
6. [ASCP.AI / ML Engine](#6-ascpai--ml-engine)
7. [Metrics & Dashboard](#7-metrics--dashboard)
8. [Pod Metrics](#8-pod-metrics)
9. [Multi-Cluster Fleet](#9-multi-cluster-fleet)
10. [Optimization](#10-optimization)
11. [Optimizer Coordinator](#11-optimizer-coordinator)
12. [Decision Engine](#12-decision-engine)
13. [Hibernation](#13-hibernation)
14. [Karpenter](#14-karpenter)
15. [Node Templates](#15-node-templates)
16. [Pool Rotation](#16-pool-rotation)
17. [Policies](#17-policies)
18. [Organization](#18-organization)
19. [Teams](#19-teams)
20. [Roles & Permissions](#20-roles--permissions)
21. [Approvals & JIT Access](#21-approvals--jit-access)
22. [Governance](#22-governance)
23. [Billing](#23-billing)
24. [Audit Logs](#24-audit-logs)
25. [Worker / DaemonSet](#25-worker--daemonset)
26. [Actions (Router)](#26-actions-router)
27. [Health](#27-health)
28. [Installer Scripts](#28-installer-scripts)
29. [WebSocket](#29-websocket)
30. [🟠 AWS-Side Data Endpoints](#-aws-side-data-endpoints)
    - [AWS Accounts](#aws-accounts)
    - [Onboarding / CloudFormation](#onboarding--cloudformation)
    - [Cloud Hygiene (Orphaned Resources)](#cloud-hygiene-orphaned-resources)
    - [RDS Optimization](#rds-optimization)
    - [Reserved Instances (RI)](#reserved-instances-ri)
    - [S3 Storage Optimization](#s3-storage-optimization)
    - [Data Transfer Cost Analysis](#data-transfer-cost-analysis)

---

## 1. Authentication

| Method | Endpoint | Description | Source |
|--------|----------|-------------|--------|
| POST | `/api/v1/auth/signup` | Register new user | `auth_routes.py` |
| POST | `/api/v1/auth/login` | Login, returns JWT tokens | `auth_routes.py` |
| POST | `/api/v1/auth/refresh` | Refresh access token | `auth_routes.py` |
| GET | `/api/v1/auth/me` | Get current user profile | `auth_routes.py` |
| POST | `/api/v1/auth/change-password` | Change password | `auth_routes.py` |
| PUT | `/api/v1/auth/profile` | Update profile info | `auth_routes.py` |
| POST | `/api/v1/auth/logout` | Logout marker | `auth_routes.py` |
| POST | `/api/v1/auth/invitation-response` | Accept/decline invitation | `auth_routes.py` |

```bash
# Signup new user
curl -s -X POST $BASE_URL/api/v1/auth/signup \
  -H "Content-Type: application/json" \
  -d '{"email":"ath@gmail.com","password":"Atharva@123","full_name":"Atharva"}' | python3 -m json.tool

# Login
curl -s -X POST $BASE_URL/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"ath@gmail.com","password":"Atharva@123"}' | python3 -m json.tool

# Refresh token (replace REFRESH_TOKEN)
curl -s -X POST $BASE_URL/api/v1/auth/refresh \
  -H "Content-Type: application/json" \
  -d '{"refresh_token":"REFRESH_TOKEN"}' | python3 -m json.tool

# Get current user profile
curl -s -X GET $BASE_URL/api/v1/auth/me \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool

# Change password
curl -s -X POST $BASE_URL/api/v1/auth/change-password \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"current_password":"Atharva@123","new_password":"Atharva@456"}' | python3 -m json.tool

# Update profile
curl -s -X PUT $BASE_URL/api/v1/auth/profile \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"full_name":"Atharva Pudale"}' | python3 -m json.tool

# Logout
curl -s -X POST $BASE_URL/api/v1/auth/logout \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
```

---

## 2. Users & Preferences

| Method | Endpoint | Description | Source |
|--------|----------|-------------|--------|
| PATCH | `/api/v1/users/me` | Update full_name | `user_routes.py` |
| POST | `/api/v1/users/{user_id}/permissions` | Update direct permissions for a user | `user_routes.py` |
| PATCH | `/api/v1/users/me/preferences` | Update dashboard preferences | `user_routes.py` |
| GET | `/api/v1/users/me/preferences` | Get current user preferences | `user_routes.py` |

```bash
# Update name
curl -s -X PATCH $BASE_URL/api/v1/users/me \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"full_name":"Atharva Pudale"}' | python3 -m json.tool

# Get preferences
curl -s -X GET $BASE_URL/api/v1/users/me/preferences \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool

# Update preferences
curl -s -X PATCH $BASE_URL/api/v1/users/me/preferences \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"theme":"dark","layout":"compact"}' | python3 -m json.tool
```

---

## 3. Clusters

| Method | Endpoint | Description | Source |
|--------|----------|-------------|--------|
| GET | `/api/v1/clusters` | List all clusters | `cluster_routes.py` |
| POST | `/api/v1/clusters` | Register new cluster | `cluster_routes.py` |
| GET | `/api/v1/clusters/{cluster_id}` | Get cluster details | `cluster_routes.py` |
| PATCH | `/api/v1/clusters/{cluster_id}` | Update cluster | `cluster_routes.py` |
| DELETE | `/api/v1/clusters/{cluster_id}` | Delete cluster | `cluster_routes.py` |
| POST | `/api/v1/clusters/discover` | Trigger discovery scan | `cluster_routes.py` |
| POST | `/api/v1/clusters/connect` | Connect via STS (agentless) | `cluster_routes.py` |
| POST | `/api/v1/clusters/verify/{cluster_id}` | Verify cluster connection | `cluster_routes.py` |
| PATCH | `/api/v1/clusters/{cluster_id}/auto-rebalance` | Toggle auto-rebalancing | `cluster_routes.py` |
| POST | `/api/v1/clusters/install-script` | Register and get Helm credentials | `cluster_routes.py` |
| GET | `/api/v1/clusters/{cluster_id}/nodes` | Get nodes/instances for cluster | `cluster_routes.py` |
| POST | `/api/v1/clusters/{cluster_id}/costs` | Update resource costs | `cluster_routes.py` |
| POST | `/api/v1/clusters/{cluster_id}/auto-install` | Auto-install agent via AWS role | `cluster_routes.py` |
| POST | `/api/v1/clusters/{cluster_id}/update-agent` | Re-deploy/update agent | `cluster_routes.py` |
| POST | `/api/v1/clusters/{cluster_id}/fallback` | Handle spot interruption fallback | `cluster_routes.py` |

```bash
# List all clusters
curl -s -X GET $BASE_URL/api/v1/clusters \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool

# List clusters with filters
curl -s -X GET "$BASE_URL/api/v1/clusters?page=1&per_page=10&status=active" \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool

# Get specific cluster (replace CLUSTER_ID)
curl -s -X GET $BASE_URL/api/v1/clusters/CLUSTER_ID \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool

# Trigger discovery scan
curl -s -X POST $BASE_URL/api/v1/clusters/discover \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{}' | python3 -m json.tool

# Get cluster nodes
curl -s -X GET $BASE_URL/api/v1/clusters/CLUSTER_ID/nodes \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool

# Toggle auto-rebalance
curl -s -X PATCH $BASE_URL/api/v1/clusters/CLUSTER_ID/auto-rebalance \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"enabled":true}' | python3 -m json.tool

# Delete cluster
curl -s -X DELETE $BASE_URL/api/v1/clusters/CLUSTER_ID \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
```

---

## 4. Agents

| Method | Endpoint | Description | Source |
|--------|----------|-------------|--------|
| POST | `/api/v1/agents/register` | Register agent on startup | `agent_routes.py` |
| POST | `/api/v1/agents/deregister` | Deregister agent on shutdown | `agent_routes.py` |
| POST | `/api/v1/agents/heartbeat` | Send heartbeat, mark cluster ACTIVE | `agent_routes.py` |
| GET | `/api/v1/agents/actions/pending` | Poll for pending K8s commands | `agent_routes.py` |
| POST | `/api/v1/agents/actions/{action_id}/result` | Report action result | `agent_routes.py` |
| POST | `/api/v1/agents/spot-interruption` | Receive spot termination notice | `agent_routes.py` |
| POST | `/api/v1/agents/rebalance-recommendation` | Receive rebalance event | `agent_routes.py` |
| GET | `/api/v1/agents/orchestrator/{cluster_id}/pending-commands` | Orchestrator polls for commands | `agent_routes.py` |
| POST | `/api/v1/agents/orchestrator/{cluster_id}/command-result` | Orchestrator reports result | `agent_routes.py` |

```bash
# Register agent
curl -s -X POST $BASE_URL/api/v1/agents/register \
  -H "Content-Type: application/json" \
  -d '{"cluster_id":"CLUSTER_ID","agent_version":"1.0.0","node_name":"node-1"}' | python3 -m json.tool

# Send heartbeat
curl -s -X POST $BASE_URL/api/v1/agents/heartbeat \
  -H "Content-Type: application/json" \
  -d '{"cluster_id":"CLUSTER_ID","status":"healthy"}' | python3 -m json.tool

# Poll pending actions (agent uses its own token)
curl -s -X GET "$BASE_URL/api/v1/agents/actions/pending?cluster_id=CLUSTER_ID" \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool

# Orchestrator poll for pending commands
curl -s -X GET $BASE_URL/api/v1/agents/orchestrator/CLUSTER_ID/pending-commands \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
```

---

## 5. AI Agents

| Method | Endpoint | Description | Source |
|--------|----------|-------------|--------|
| POST | `/api/v1/ai-agents/{cluster_id}/optimize` | Run full multi-agent optimization pipeline | `ai_agent_routes.py` |
| POST | `/api/v1/ai-agents/{cluster_id}/rightsizing` | Generate rightsizing recommendations | `ai_agent_routes.py` |
| POST | `/api/v1/ai-agents/events/interruption` | Handle spot interruption event | `ai_agent_routes.py` |
| GET | `/api/v1/ai-agents/health` | Health of all 8 AI agents | `ai_agent_routes.py` |
| GET | `/api/v1/ai-agents/status/{cluster_id}` | AI agent execution status | `ai_agent_routes.py` |

```bash
# AI agents health check
curl -s -X GET $BASE_URL/api/v1/ai-agents/health \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool

# AI agent status for cluster
curl -s -X GET $BASE_URL/api/v1/ai-agents/status/CLUSTER_ID \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool

# Run full optimization pipeline
curl -s -X POST $BASE_URL/api/v1/ai-agents/CLUSTER_ID/optimize \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{}' | python3 -m json.tool

# Generate rightsizing recommendations
curl -s -X POST $BASE_URL/api/v1/ai-agents/CLUSTER_ID/rightsizing \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{}' | python3 -m json.tool
```

---

## 6. ASCP.AI / ML Engine

| Method | Endpoint | Description | Source |
|--------|----------|-------------|--------|
| GET | `/api/v1/ascpai/clusters/{cluster_id}/effective-configuration` | Get unified cluster config | `ascpai_routes.py` |
| POST | `/api/v1/ascpai/pools/rankings` | Get ML-ranked spot pools (8-step pipeline) | `ascpai_routes.py` |
| GET | `/api/v1/ascpai/blacklist` | Get all globally flagged risky pools | `ascpai_routes.py` |
| GET | `/api/v1/ascpai/blacklist/check` | Check if instance_type+AZ is blacklisted | `ascpai_routes.py` |
| GET | `/api/v1/ascpai/rebalancing/status` | Get auto-rebalancing action status | `ascpai_routes.py` |

```bash
# Get effective cluster configuration
curl -s -X GET $BASE_URL/api/v1/ascpai/clusters/CLUSTER_ID/effective-configuration \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool

# Get ML-ranked spot pools
curl -s -X POST $BASE_URL/api/v1/ascpai/pools/rankings \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"cluster_id":"CLUSTER_ID","region":"us-east-1","instance_types":["t3.medium","m5.large"]}' | python3 -m json.tool

# Get global blacklist
curl -s -X GET $BASE_URL/api/v1/ascpai/blacklist \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool

# Check if specific pool is blacklisted
curl -s -X GET "$BASE_URL/api/v1/ascpai/blacklist/check?instance_type=t3.medium&availability_zone=us-east-1a" \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool

# Get rebalancing status
curl -s -X GET $BASE_URL/api/v1/ascpai/rebalancing/status \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
```

---

## 7. Metrics & Dashboard

| Method | Endpoint | Description | Source |
|--------|----------|-------------|--------|
| GET | `/api/v1/metrics/dashboard` | Get dashboard KPIs (costs, instances, savings) | `metrics_routes.py` |
| GET | `/api/v1/metrics/cost` | Detailed cost breakdown | `metrics_routes.py` |
| GET | `/api/v1/metrics/instances` | Instance counts by state/lifecycle/arch | `metrics_routes.py` |
| GET | `/api/v1/metrics/cost/timeseries` | Daily cost data for charts | `metrics_routes.py` |
| GET | `/api/v1/metrics/cluster/{cluster_id}` | Metrics for specific cluster | `metrics_routes.py` |
| GET | `/api/v1/metrics/cluster/{cluster_id}/utilization` | CPU/memory utilization history (7 days) | `metrics_routes.py` |

```bash
# Dashboard KPIs
curl -s -X GET $BASE_URL/api/v1/metrics/dashboard \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool

# Cost breakdown
curl -s -X GET $BASE_URL/api/v1/metrics/cost \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool

# Instance counts
curl -s -X GET $BASE_URL/api/v1/metrics/instances \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool

# Daily cost timeseries
curl -s -X GET "$BASE_URL/api/v1/metrics/cost/timeseries?days=30" \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool

# Cluster-specific metrics
curl -s -X GET $BASE_URL/api/v1/metrics/cluster/CLUSTER_ID \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool

# Cluster utilization (7 days)
curl -s -X GET $BASE_URL/api/v1/metrics/cluster/CLUSTER_ID/utilization \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
```

---

## 8. Pod Metrics

| Method | Endpoint | Description | Source |
|--------|----------|-------------|--------|
| POST | `/api/v1/pod-metrics/batch` | Submit batch pod metrics from DaemonSet | `pod_metrics_routes.py` |
| GET | `/api/v1/pod-metrics` | Query pod metrics with filters | `pod_metrics_routes.py` |
| DELETE | `/api/v1/pod-metrics/cleanup` | Delete metrics older than retention | `pod_metrics_routes.py` |
| GET | `/api/v1/pod-metrics/right-sizing/recommendations` | Workload right-sizing recommendations | `pod_metrics_routes.py` |

```bash
# Query pod metrics
curl -s -X GET "$BASE_URL/api/v1/pod-metrics?cluster_id=CLUSTER_ID&limit=20" \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool

# Right-sizing recommendations from pod data
curl -s -X GET "$BASE_URL/api/v1/pod-metrics/right-sizing/recommendations?cluster_id=CLUSTER_ID" \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
```

---

## 9. Multi-Cluster Fleet

| Method | Endpoint | Description | Source |
|--------|----------|-------------|--------|
| GET | `/api/v1/multi-cluster/summary` | Fleet-wide aggregation (spot/OD counts, savings) | `multi_cluster_routes.py` |
| GET | `/api/v1/multi-cluster/actions` | Fleet-wide recent rebalancing/optimization actions | `multi_cluster_routes.py` |

```bash
# Fleet-wide summary
curl -s -X GET $BASE_URL/api/v1/multi-cluster/summary \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool

# Fleet actions
curl -s -X GET $BASE_URL/api/v1/multi-cluster/actions \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
```

---

## 10. Optimization

| Method | Endpoint | Description | Source |
|--------|----------|-------------|--------|
| GET | `/api/v1/optimization/rightsizing/{cluster_id}` | Get resize recommendations | `optimization_routes.py` |
| POST | `/api/v1/optimization/rightsizing/batch-apply` | Apply right-sizing to multiple instances | `optimization_routes.py` |
| GET | `/api/v1/optimization/savings/realized` | Cumulative realized savings | `optimization_routes.py` |
| POST | `/api/v1/optimization/apply/{instance_id}/validated` | Apply right-sizing with blacklist validation | `optimization_routes.py` |

```bash
# Get right-sizing recommendations for cluster
curl -s -X GET $BASE_URL/api/v1/optimization/rightsizing/CLUSTER_ID \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool

# Realized savings
curl -s -X GET $BASE_URL/api/v1/optimization/savings/realized \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool

# Apply validated right-sizing to specific instance
curl -s -X POST $BASE_URL/api/v1/optimization/apply/INSTANCE_ID/validated \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"target_instance_type":"t3.medium"}' | python3 -m json.tool
```

---

## 11. Optimizer Coordinator

| Method | Endpoint | Description | Source |
|--------|----------|-------------|--------|
| GET | `/api/v1/optimizer/status/{cluster_id}` | Optimizer phase, capabilities, cooldown | `optimizer_coordinator_routes.py` |
| POST | `/api/v1/optimizer/evaluate/{cluster_id}` | Manually trigger optimization evaluation | `optimizer_coordinator_routes.py` |
| GET | `/api/v1/optimizer/proposals/{cluster_id}` | List rightsizing proposals | `optimizer_coordinator_routes.py` |
| POST | `/api/v1/optimizer/proposals/{proposal_id}/approve` | Approve and execute proposal | `optimizer_coordinator_routes.py` |
| POST | `/api/v1/optimizer/proposals/{proposal_id}/reject` | Reject a proposal | `optimizer_coordinator_routes.py` |
| GET | `/api/v1/optimizer/comparison/{proposal_id}` | Option A vs B vs C EV comparison | `optimizer_coordinator_routes.py` |

```bash
# Optimizer status
curl -s -X GET $BASE_URL/api/v1/optimizer/status/CLUSTER_ID \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool

# Manually trigger evaluation
curl -s -X POST $BASE_URL/api/v1/optimizer/evaluate/CLUSTER_ID \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{}' | python3 -m json.tool

# List proposals for cluster
curl -s -X GET $BASE_URL/api/v1/optimizer/proposals/CLUSTER_ID \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool

# Approve proposal
curl -s -X POST $BASE_URL/api/v1/optimizer/proposals/PROPOSAL_ID/approve \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{}' | python3 -m json.tool

# Comparison breakdown
curl -s -X GET $BASE_URL/api/v1/optimizer/comparison/PROPOSAL_ID \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
```

---

## 12. Decision Engine

| Method | Endpoint | Description | Source |
|--------|----------|-------------|--------|
| POST | `/api/v1/decision/rank-for-node` | Top ranked pools for a specific node | `decision_routes.py` |
| POST | `/api/v1/decision/rank-for-template` | Top ranked pools for a template spec | `decision_routes.py` |
| POST | `/api/v1/decision/report-termination` | Report spot interruption, blacklist pool | `decision_routes.py` |
| POST | `/api/v1/decision/report-launch-failure` | Report launch failure, auto-blacklist | `decision_routes.py` |
| GET | `/api/v1/decision/blacklist` | Return global blacklist for region | `decision_routes.py` |

```bash
# Get ranked pools for a node
curl -s -X POST $BASE_URL/api/v1/decision/rank-for-node \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"cluster_id":"CLUSTER_ID","node_id":"NODE_ID","region":"us-east-1"}' | python3 -m json.tool

# Global blacklist for a region
curl -s -X GET "$BASE_URL/api/v1/decision/blacklist?region=us-east-1" \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool

# Report spot termination
curl -s -X POST $BASE_URL/api/v1/decision/report-termination \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"instance_type":"t3.medium","availability_zone":"us-east-1a","region":"us-east-1"}' | python3 -m json.tool
```

---

## 13. Hibernation

| Method | Endpoint | Description | Source |
|--------|----------|-------------|--------|
| GET | `/api/v1/hibernation/schedules` | List hibernation schedules | `hibernation_routes.py` |
| POST | `/api/v1/hibernation/schedules` | Create new schedule | `hibernation_routes.py` |
| GET | `/api/v1/hibernation/schedules/{schedule_id}` | Get specific schedule | `hibernation_routes.py` |
| PUT | `/api/v1/hibernation/schedules/{schedule_id}` | Update schedule | `hibernation_routes.py` |
| DELETE | `/api/v1/hibernation/schedules/{schedule_id}` | Delete schedule | `hibernation_routes.py` |
| POST | `/api/v1/hibernation/schedules/{schedule_id}/toggle` | Activate or pause schedule | `hibernation_routes.py` |
| GET | `/api/v1/hibernation/strategies/compare` | Compare all strategies | `hibernation_routes.py` |
| GET | `/api/v1/hibernation/schedules/{schedule_id}/savings` | Estimate savings for schedule | `hibernation_routes.py` |
| GET | `/api/v1/hibernation/savings/history` | Historical savings trend | `hibernation_routes.py` |
| GET | `/api/v1/hibernation/status/active` | Active hibernation op status | `hibernation_routes.py` |
| POST | `/api/v1/hibernation/emergency/sleep` | Immediately hibernate clusters | `hibernation_routes.py` |
| POST | `/api/v1/hibernation/emergency/wake` | Immediately wake clusters | `hibernation_routes.py` |
| POST | `/api/v1/hibernation/emergency/temp-hibernate` | Temporarily hibernate for N hours | `hibernation_routes.py` |

```bash
# List schedules
curl -s -X GET $BASE_URL/api/v1/hibernation/schedules \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool

# Create schedule
curl -s -X POST $BASE_URL/api/v1/hibernation/schedules \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name":"Night Schedule","cluster_ids":["CLUSTER_ID"],"sleep_cron":"0 22 * * *","wake_cron":"0 8 * * *","timezone":"UTC"}' | python3 -m json.tool

# Compare strategies
curl -s -X GET $BASE_URL/api/v1/hibernation/strategies/compare \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool

# Savings history
curl -s -X GET $BASE_URL/api/v1/hibernation/savings/history \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool

# Active hibernation status
curl -s -X GET $BASE_URL/api/v1/hibernation/status/active \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool

# Emergency sleep (all clusters)
curl -s -X POST $BASE_URL/api/v1/hibernation/emergency/sleep \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"cluster_ids":["CLUSTER_ID"]}' | python3 -m json.tool

# Emergency wake
curl -s -X POST $BASE_URL/api/v1/hibernation/emergency/wake \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"cluster_ids":["CLUSTER_ID"]}' | python3 -m json.tool

# Temp hibernate for 2 hours
curl -s -X POST $BASE_URL/api/v1/hibernation/emergency/temp-hibernate \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"cluster_ids":["CLUSTER_ID"],"hours":2}' | python3 -m json.tool
```

---

## 14. Karpenter

| Method | Endpoint | Description | Source |
|--------|----------|-------------|--------|
| GET | `/api/v1/karpenter/status` | Karpenter deployment status overview | `karpenter_routes.py` |
| GET | `/api/v1/karpenter/config` | Get Karpenter config for cluster | `karpenter_routes.py` |
| POST | `/api/v1/karpenter/config` | Save wizard config for clusters | `karpenter_routes.py` |
| PATCH | `/api/v1/karpenter/config/{cluster_id}` | Update config, sync automation toggles | `karpenter_routes.py` |
| POST | `/api/v1/karpenter/deploy` | Deploy Karpenter to clusters | `karpenter_routes.py` |
| POST | `/api/v1/karpenter/toggle/{cluster_id}` | Pause/resume Karpenter | `karpenter_routes.py` |
| GET | `/api/v1/karpenter/activity` | Recent optimization events | `karpenter_routes.py` |

```bash
# Karpenter status
curl -s -X GET $BASE_URL/api/v1/karpenter/status \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool

# Get Karpenter config
curl -s -X GET "$BASE_URL/api/v1/karpenter/config?cluster_id=CLUSTER_ID" \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool

# Karpenter activity
curl -s -X GET $BASE_URL/api/v1/karpenter/activity \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool

# Toggle Karpenter on cluster
curl -s -X POST $BASE_URL/api/v1/karpenter/toggle/CLUSTER_ID \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"action":"pause"}' | python3 -m json.tool
```

---

## 15. Node Templates

| Method | Endpoint | Description | Source |
|--------|----------|-------------|--------|
| GET | `/api/v1/node-templates` | List all node templates | `node_template_routes.py` |
| POST | `/api/v1/node-templates` | Create node template (V1 auto-created) | `node_template_routes.py` |
| GET | `/api/v1/node-templates/{template_id}/versions` | List all versions of a template | `node_template_routes.py` |
| POST | `/api/v1/node-templates/{template_id}/versions` | Draft new template version | `node_template_routes.py` |
| GET | `/api/v1/clusters/{cluster_id}/node-template/active` | Get active template for cluster | `node_template_routes.py` |
| POST | `/api/v1/clusters/{cluster_id}/node-template/assign` | Assign template to cluster | `node_template_routes.py` |

```bash
# List node templates
curl -s -X GET $BASE_URL/api/v1/node-templates \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool

# Create node template
curl -s -X POST $BASE_URL/api/v1/node-templates \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name":"production-template","instance_types":["m5.large","m5.xlarge"],"spot_percentage":80}' | python3 -m json.tool

# Get active template for cluster
curl -s -X GET $BASE_URL/api/v1/clusters/CLUSTER_ID/node-template/active \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
```

---

## 16. Pool Rotation

| Method | Endpoint | Description | Source |
|--------|----------|-------------|--------|
| GET | `/api/v1/pool-rotation/status/{cluster_id}` | Pool rotation status for cluster | `pool_rotation_routes.py` |
| POST | `/api/v1/pool-rotation/check/{cluster_id}` | Manually trigger rotation check | `pool_rotation_routes.py` |
| POST | `/api/v1/pool-rotation/force/{cluster_id}` | Force immediate rotation (admin) | `pool_rotation_routes.py` |
| GET | `/api/v1/pool-rotation/status` | Rotation status for all clusters | `pool_rotation_routes.py` |
| GET | `/api/v1/pool-rotation/notifications/{cluster_id}` | Recent rotation notifications | `pool_rotation_routes.py` |
| DELETE | `/api/v1/pool-rotation/notifications/{cluster_id}` | Clear rotation notifications | `pool_rotation_routes.py` |

```bash
# Pool rotation status for cluster
curl -s -X GET $BASE_URL/api/v1/pool-rotation/status/CLUSTER_ID \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool

# All clusters rotation status (admin)
curl -s -X GET $BASE_URL/api/v1/pool-rotation/status \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool

# Trigger rotation check
curl -s -X POST $BASE_URL/api/v1/pool-rotation/check/CLUSTER_ID \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{}' | python3 -m json.tool

# Get rotation notifications
curl -s -X GET $BASE_URL/api/v1/pool-rotation/notifications/CLUSTER_ID \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
```

---

## 17. Policies

| Method | Endpoint | Description | Source |
|--------|----------|-------------|--------|
| POST | `/api/v1/policies` | Create optimization policy | `policy_routes.py` |
| GET | `/api/v1/policies` | List policies | `policy_routes.py` |
| GET | `/api/v1/policies/{policy_id}` | Get policy by ID | `policy_routes.py` |
| GET | `/api/v1/policies/cluster/{cluster_id}` | Active policy for cluster | `policy_routes.py` |
| PATCH | `/api/v1/policies/{policy_id}` | Update policy | `policy_routes.py` |
| DELETE | `/api/v1/policies/{policy_id}` | Delete policy | `policy_routes.py` |

```bash
# List policies
curl -s -X GET $BASE_URL/api/v1/policies \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool

# Get active policy for cluster
curl -s -X GET $BASE_URL/api/v1/policies/cluster/CLUSTER_ID \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool

# Create policy
curl -s -X POST $BASE_URL/api/v1/policies \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name":"prod-policy","max_spot_percentage":80,"min_on_demand":2,"cluster_id":"CLUSTER_ID"}' | python3 -m json.tool
```

---

## 18. Organization

| Method | Endpoint | Description | Source |
|--------|----------|-------------|--------|
| GET | `/api/v1/organization/members` | List all org members | `organization_routes.py` |
| POST | `/api/v1/organization/members` | Add new member (Org Admin) | `organization_routes.py` |
| GET | `/api/v1/organization/invitations` | List pending invitations | `organization_routes.py` |
| DELETE | `/api/v1/organization/members/{user_id}` | Remove member | `organization_routes.py` |
| PATCH | `/api/v1/organization/members/{user_id}` | Update member role | `organization_routes.py` |
| POST | `/api/v1/organization/invitations/{token}/accept` | Accept invitation via token | `organization_routes.py` |
| GET | `/api/v1/organization/connection-info` | Get AWS External ID and account ID | `organization_routes.py` |
| POST | `/api/v1/organization/connection-info/regenerate` | Regenerate External ID | `organization_routes.py` |

```bash
# List org members
curl -s -X GET $BASE_URL/api/v1/organization/members \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool

# List pending invitations
curl -s -X GET $BASE_URL/api/v1/organization/invitations \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool

# Add new member
curl -s -X POST $BASE_URL/api/v1/organization/members \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"email":"newuser@gmail.com","role":"MEMBER"}' | python3 -m json.tool

# Get AWS connection info / External ID
curl -s -X GET $BASE_URL/api/v1/organization/connection-info \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
```

---

## 19. Teams

| Method | Endpoint | Description | Source |
|--------|----------|-------------|--------|
| GET | `/api/v1/teams/invites` | Get pending invitations for current user | `team_routes.py` |
| GET | `/api/v1/teams/` | List teams for current user | `team_routes.py` |
| POST | `/api/v1/teams/` | Create a team | `team_routes.py` |
| PUT | `/api/v1/teams/{team_id}/rename` | Rename a team | `team_routes.py` |
| POST | `/api/v1/teams/{team_id}/assign` | Assign member to team | `team_routes.py` |
| POST | `/api/v1/teams/{team_id}/remove` | Remove member from team | `team_routes.py` |
| POST | `/api/v1/teams/{team_id}/invite` | Invite user to platform and team | `team_routes.py` |
| GET | `/api/v1/teams/{team_id}` | Get team details with members | `team_routes.py` |
| PUT | `/api/v1/teams/{team_id}/governance` | Update team governance rules | `team_routes.py` |
| GET | `/api/v1/teams/{team_id}/stats` | Get team statistics | `team_routes.py` |
| PUT | `/api/v1/teams/{team_id}/members/{member_id}/permissions` | Update member granular permissions | `team_routes.py` |
| GET | `/api/v1/teams/{team_id}/approvers` | Get approvers for team | `team_routes.py` |
| GET | `/api/v1/teams/my-teams/approvers` | Get approvers for current user's team | `team_routes.py` |

```bash
# List my teams
curl -s -X GET $BASE_URL/api/v1/teams/ \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool

# Create team
curl -s -X POST $BASE_URL/api/v1/teams/ \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name":"DevOps Team"}' | python3 -m json.tool

# Get team details
curl -s -X GET $BASE_URL/api/v1/teams/TEAM_ID \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool

# Get my team's approvers
curl -s -X GET $BASE_URL/api/v1/teams/my-teams/approvers \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool

# Get pending invites
curl -s -X GET $BASE_URL/api/v1/teams/invites \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
```

---

## 20. Roles & Permissions

| Method | Endpoint | Description | Source |
|--------|----------|-------------|--------|
| GET | `/api/v1/roles/permissions` | List all system permissions | `role_routes.py` |
| GET | `/api/v1/roles` | List all roles (system + custom) | `role_routes.py` |
| GET | `/api/v1/roles/{role_id}` | Get single role by ID | `role_routes.py` |
| POST | `/api/v1/roles` | Create custom role (Org Admin) | `role_routes.py` |
| PUT | `/api/v1/roles/{role_id}` | Update custom role | `role_routes.py` |
| DELETE | `/api/v1/roles/{role_id}` | Delete custom role | `role_routes.py` |
| POST | `/api/v1/roles/assign` | Assign role to user | `role_routes.py` |
| POST | `/api/v1/roles/seed` | Seed default permissions/roles | `role_routes.py` |
| POST | `/api/v1/permissions/check` | Check user permission for feature | `permission_routes.py` |
| GET | `/api/v1/permissions/my-features` | List all accessible features | `permission_routes.py` |
| POST | `/api/v1/permissions/{user_id}/revoke-feature/{feature_id}` | Revoke all JIT tickets for user+feature | `permission_routes.py` |
| GET | `/api/v1/permissions/feature-registry` | Get complete feature registry | `permission_routes.py` |

```bash
# List all roles
curl -s -X GET $BASE_URL/api/v1/roles \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool

# List all permissions
curl -s -X GET $BASE_URL/api/v1/roles/permissions \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool

# Get my accessible features
curl -s -X GET $BASE_URL/api/v1/permissions/my-features \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool

# Check permission for feature
curl -s -X POST $BASE_URL/api/v1/permissions/check \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"feature":"cluster.delete"}' | python3 -m json.tool

# Feature registry
curl -s -X GET $BASE_URL/api/v1/permissions/feature-registry \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
```

---

## 21. Approvals & JIT Access

| Method | Endpoint | Description | Source |
|--------|----------|-------------|--------|
| POST | `/api/v1/approvals` | Submit new access request | `approval_routes.py` |
| GET | `/api/v1/approvals` | List approvals visible to current user | `approval_routes.py` |
| POST | `/api/v1/approvals/delegate` | Admin: grant access to multiple users | `approval_routes.py` |
| GET | `/api/v1/approvals/active-window` | Check active execution window | `approval_routes.py` |
| POST | `/api/v1/approvals/jit-request` | Submit JIT feature access request | `approval_routes.py` |
| GET | `/api/v1/approvals/my-jit-approvals` | Get all active JIT approvals for current user | `approval_routes.py` |
| POST | `/api/v1/approvals/{approval_id}/approve` | Approve JIT request | `approval_routes.py` |
| POST | `/api/v1/approvals/{approval_id}/reject` | Reject JIT request | `approval_routes.py` |
| POST | `/api/v1/approvals/{approval_id}/revoke` | Revoke active approval | `approval_routes.py` |
| POST | `/api/v1/approvals/{approval_id}/accept` | Accept delegated grant | `approval_routes.py` |

```bash
# List my approvals
curl -s -X GET $BASE_URL/api/v1/approvals \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool

# My active JIT approvals
curl -s -X GET $BASE_URL/api/v1/approvals/my-jit-approvals \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool

# Check active execution window
curl -s -X GET $BASE_URL/api/v1/approvals/active-window \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool

# Submit JIT request
curl -s -X POST $BASE_URL/api/v1/approvals/jit-request \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"feature_id":"cluster.delete","reason":"Need to clean up test cluster","duration_hours":2}' | python3 -m json.tool

# Approve a JIT request
curl -s -X POST $BASE_URL/api/v1/approvals/APPROVAL_ID/approve \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"comment":"Approved for cleanup"}' | python3 -m json.tool
```

---

## 22. Governance

| Method | Endpoint | Description | Source |
|--------|----------|-------------|--------|
| GET | `/api/v1/governance/policies` | Get governance policies | `governance_routes.py` |
| PATCH | `/api/v1/governance/policies` | Update governance policies (Org Admin) | `governance_routes.py` |
| POST | `/api/v1/governance/run-autopilot` | Manually trigger automated governance | `governance_routes.py` |

```bash
# Get governance policies
curl -s -X GET $BASE_URL/api/v1/governance/policies \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool

# Trigger governance autopilot
curl -s -X POST $BASE_URL/api/v1/governance/run-autopilot \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"account_id":"AWS_ACCOUNT_ID"}' | python3 -m json.tool
```

---

## 23. Billing

| Method | Endpoint | Description | Source |
|--------|----------|-------------|--------|
| POST | `/api/v1/billing/create-portal-session` | Create Stripe billing portal session | `billing_routes.py` |
| POST | `/api/v1/billing/webhook/stripe` | Stripe webhook handler | `billing_routes.py` |
| GET | `/api/v1/billing/status` | Get subscription/billing status | `billing_routes.py` |
| GET | `/api/v1/billing/costs/summary` | Cost summary by period | `billing_routes.py` |

```bash
# Get billing status
curl -s -X GET $BASE_URL/api/v1/billing/status \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool

# Cost summary (month/week/day/quarter)
curl -s -X GET "$BASE_URL/api/v1/billing/costs/summary?period=month" \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
```

---

## 24. Audit Logs

| Method | Endpoint | Description | Source |
|--------|----------|-------------|--------|
| GET | `/api/v1/audit` | Get audit logs (filtered, paginated) | `audit_routes.py` |
| GET | `/api/v1/audit/logs` | Alias for `/audit` | `audit_routes.py` |
| GET | `/api/v1/audit/{audit_id}` | Get specific audit log entry | `audit_routes.py` |
| GET | `/api/v1/audit/retention/settings` | Get audit retention policy | `audit_routes.py` |
| PUT | `/api/v1/audit/retention/settings` | Update retention policy days | `audit_routes.py` |
| POST | `/api/v1/audit/integrity/verify` | Verify log integrity via checksums | `audit_routes.py` |

```bash
# Get audit logs (paginated)
curl -s -X GET "$BASE_URL/api/v1/audit?page=1&per_page=20" \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool

# Get audit logs with filters
curl -s -X GET "$BASE_URL/api/v1/audit?user_email=ath@gmail.com&action=LOGIN" \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool

# Get retention settings
curl -s -X GET $BASE_URL/api/v1/audit/retention/settings \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool

# Verify audit integrity
curl -s -X POST $BASE_URL/api/v1/audit/integrity/verify \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{}' | python3 -m json.tool
```

---

## 25. Worker / DaemonSet

| Method | Endpoint | Description | Source |
|--------|----------|-------------|--------|
| POST | `/api/v1/worker/spot-interruption` | Receive spot termination alert | `worker_routes.py` |
| POST | `/api/v1/worker/register-node` | Register DaemonSet node | `worker_routes.py` |
| POST | `/api/v1/worker/heartbeat` | Update worker heartbeat timestamp | `worker_routes.py` |
| POST | `/api/v1/worker/node-metrics` | Receive node CPU/memory metrics | `worker_routes.py` |

```bash
# Register node from DaemonSet
curl -s -X POST $BASE_URL/api/v1/worker/register-node \
  -H "Content-Type: application/json" \
  -d '{"cluster_id":"CLUSTER_ID","node_name":"ip-10-0-1-1","instance_type":"t3.medium","availability_zone":"us-east-1a","lifecycle":"spot"}' | python3 -m json.tool

# Worker heartbeat
curl -s -X POST $BASE_URL/api/v1/worker/heartbeat \
  -H "Content-Type: application/json" \
  -d '{"cluster_id":"CLUSTER_ID","node_name":"ip-10-0-1-1"}' | python3 -m json.tool
```

---

## 26. Actions (Router)

| Method | Endpoint | Description | Source |
|--------|----------|-------------|--------|
| GET | `/api/v1/actions/poll` | Agent polls for pending actions | `routers/actions.py` |
| POST | `/api/v1/actions/{action_id}/result` | Agent reports action result | `routers/actions.py` |
| POST | `/api/v1/actions/` | Create new action for cluster | `routers/actions.py` |
| GET | `/api/v1/actions/{action_id}` | Get action details | `routers/actions.py` |

```bash
# Poll pending actions for cluster
curl -s -X GET "$BASE_URL/api/v1/actions/poll?cluster_id=CLUSTER_ID" \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool

# Get action details
curl -s -X GET $BASE_URL/api/v1/actions/ACTION_ID \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
```

---

## 27. Health

| Method | Endpoint | Description | Source |
|--------|----------|-------------|--------|
| GET | `/health` | Basic health check | `api_gateway.py` |
| GET | `/health/detailed` | Detailed health (DB + Redis) | `api_gateway.py` |
| GET | `/api/v1/health/system` | Full system health (super admin) | `health_routes.py` |

```bash
# Basic health check
curl -s -X GET $BASE_URL/health | python3 -m json.tool

# Detailed health (DB + Redis status)
curl -s -X GET $BASE_URL/health/detailed | python3 -m json.tool

# System health (admin only)
curl -s -X GET $BASE_URL/api/v1/health/system \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
```

---

## 28. Installer Scripts

| Method | Endpoint | Description | Source |
|--------|----------|-------------|--------|
| GET | `/api/installer/linux` | Generate Linux installer shell script | `installer_routes.py` |
| GET | `/api/installer/macos` | Generate macOS installer shell script | `installer_routes.py` |

```bash
# Get Linux installer script
curl -s -X GET "$BASE_URL/api/installer/linux?cluster_id=CLUSTER_ID&token=AGENT_TOKEN" | bash

# Get macOS installer script
curl -s -X GET "$BASE_URL/api/installer/macos?cluster_id=CLUSTER_ID&token=AGENT_TOKEN"
```

---

## 29. WebSocket

| Method | Endpoint | Description | Source |
|--------|----------|-------------|--------|
| WS | `/ws/cluster/{cluster_id}` | Real-time agent communication | `api_gateway.py` |

```bash
# Test WebSocket (requires wscat or websocat inside container)
# Install wscat if needed: npm install -g wscat
wscat -c "ws://localhost:8000/ws/cluster/CLUSTER_ID" \
  -H "Authorization: Bearer $TOKEN"
```

---

---

## 🟠 AWS-Side Data Endpoints

> These endpoints pull live data from or manage AWS services directly (EC2, RDS, S3, RI, CloudFormation, etc.).

---

### AWS Accounts

> Manages AWS account linking to the platform via IAM Cross-Account Role.

| Method | Endpoint | Description | Source |
|--------|----------|-------------|--------|
| GET | `/api/v1/accounts` | List linked AWS accounts | `account_routes.py` |
| POST | `/api/v1/accounts` | Link new AWS account | `account_routes.py` |
| GET | `/api/v1/accounts/{account_id}` | Get account details | `account_routes.py` |
| DELETE | `/api/v1/accounts/{account_id}` | Unlink AWS account | `account_routes.py` |
| POST | `/api/v1/accounts/{account_id}/validate` | Validate IAM credentials/permissions | `account_routes.py` |
| POST | `/api/v1/accounts/{account_id}/set-default` | Set account as org default | `account_routes.py` |
| POST | `/api/v1/accounts/{account_id}/disconnect` | Disconnect (strips credentials) | `account_routes.py` |

```bash
# List all linked AWS accounts
curl -s -X GET $BASE_URL/api/v1/accounts \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool

# Get specific account details
curl -s -X GET $BASE_URL/api/v1/accounts/ACCOUNT_ID \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool

# Link new AWS account
curl -s -X POST $BASE_URL/api/v1/accounts \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"aws_account_id":"123456789012","role_arn":"arn:aws:iam::123456789012:role/SpotOptimizerRole","alias":"production"}' | python3 -m json.tool

# Validate account IAM permissions
curl -s -X POST $BASE_URL/api/v1/accounts/ACCOUNT_ID/validate \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{}' | python3 -m json.tool

# Set account as default
curl -s -X POST $BASE_URL/api/v1/accounts/ACCOUNT_ID/set-default \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{}' | python3 -m json.tool
```

---

### Onboarding / CloudFormation

> Sets up the AWS IAM Role via CloudFormation StackSet for cross-account access.

| Method | Endpoint | Description | Source |
|--------|----------|-------------|--------|
| GET | `/api/v1/onboarding/state` | Current onboarding state | `onboarding_routes.py` |
| GET | `/api/v1/onboarding/aws-link` | Get CloudFormation deep-link URL | `onboarding_routes.py` |
| GET | `/api/v1/onboarding/template` | Download CloudFormation YAML | `onboarding_routes.py` |
| POST | `/api/v1/onboarding/verify` | Verify AWS role, create account, trigger discovery | `onboarding_routes.py` |
| POST | `/api/v1/onboarding/skip` | Skip onboarding temporarily | `onboarding_routes.py` |
| POST | `/api/v1/onboarding/reset` | Reset onboarding state | `onboarding_routes.py` |
| POST | `/api/v1/onboarding/authorize` | Authorize discovered resource (with tag policy) | `onboarding_routes.py` |

```bash
# Get current onboarding state
curl -s -X GET $BASE_URL/api/v1/onboarding/state \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool

# Get CloudFormation deep-link URL
curl -s -X GET $BASE_URL/api/v1/onboarding/aws-link \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool

# Download CloudFormation template
curl -s -X GET $BASE_URL/api/v1/onboarding/template \
  -H "Authorization: Bearer $TOKEN" > cloudformation_template.yaml
echo "Template saved to cloudformation_template.yaml"

# Verify AWS role after CloudFormation stack created
curl -s -X POST $BASE_URL/api/v1/onboarding/verify \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"aws_account_id":"123456789012","role_arn":"arn:aws:iam::123456789012:role/SpotOptimizerRole","external_id":"YOUR_EXTERNAL_ID"}' | python3 -m json.tool

# Skip onboarding
curl -s -X POST $BASE_URL/api/v1/onboarding/skip \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{}' | python3 -m json.tool
```

---

### Cloud Hygiene (Orphaned Resources)

> Scans for and removes orphaned/unused AWS resources to reduce cost waste.

| Method | Endpoint | Description | Source |
|--------|----------|-------------|--------|
| GET | `/api/v1/hygiene/scan/{account_id}` | Scan for orphaned EBS, EIP, snapshots, etc. | `hygiene_routes.py` |
| GET | `/api/v1/hygiene/check-dependencies` | Pre-flight check before deletion | `hygiene_routes.py` |
| POST | `/api/v1/hygiene/action` | Execute Terminate/Delete/Release action | `hygiene_routes.py` |
| GET | `/api/v1/hygiene/discover` | Discover resources by type | `hygiene_routes.py` |
| GET | `/api/v1/hygiene/total-cost` | Total cost of all discovered resources | `hygiene_routes.py` |
| GET | `/api/v1/hygiene/scan-history` | Historical scan trend (sparkline) | `hygiene_routes.py` |

```bash
# Scan for orphaned resources in an AWS account
curl -s -X GET $BASE_URL/api/v1/hygiene/scan/ACCOUNT_ID \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool

# Discover resources by type
curl -s -X GET "$BASE_URL/api/v1/hygiene/discover?resource_type=ebs_volume&account_id=ACCOUNT_ID" \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool

# Get total cost of orphaned resources
curl -s -X GET "$BASE_URL/api/v1/hygiene/total-cost?account_id=ACCOUNT_ID" \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool

# Check dependencies before deleting
curl -s -X GET "$BASE_URL/api/v1/hygiene/check-dependencies?resource_id=vol-0123456789&resource_type=ebs_volume" \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool

# Execute hygiene action (delete/release/terminate)
curl -s -X POST $BASE_URL/api/v1/hygiene/action \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"resource_id":"vol-0123456789","resource_type":"ebs_volume","action":"Delete","account_id":"ACCOUNT_ID"}' | python3 -m json.tool

# Scan history trend
curl -s -X GET $BASE_URL/api/v1/hygiene/scan-history \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
```

---

### RDS Optimization

> Analyzes AWS RDS instances for Multi-AZ redundancy cost optimization.

| Method | Endpoint | Description | Source |
|--------|----------|-------------|--------|
| GET | `/api/v1/rds/overview` | RDS optimization overview | `rds_routes.py` |
| POST | `/api/v1/rds/analyze` | Trigger RDS Multi-AZ analysis | `rds_routes.py` |

```bash
# RDS optimization overview
curl -s -X GET $BASE_URL/api/v1/rds/overview \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool

# Trigger RDS analysis (Org Admin only)
curl -s -X POST $BASE_URL/api/v1/rds/analyze \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"account_id":"ACCOUNT_ID","region":"us-east-1"}' | python3 -m json.tool
```

---

### Reserved Instances (RI)

> Analyzes AWS EC2 Reserved Instance utilization and provides actionable recommendations.

| Method | Endpoint | Description | Source |
|--------|----------|-------------|--------|
| GET | `/api/v1/ri/overview` | RI health overview for dashboard | `ri_routes.py` |
| GET | `/api/v1/ri/list` | List all RIs with utilization data | `ri_routes.py` |
| GET | `/api/v1/ri/{ri_id}/recommendations` | Recommendations for specific RI | `ri_routes.py` |
| POST | `/api/v1/ri/analyze` | Trigger RI utilization analysis | `ri_routes.py` |
| POST | `/api/v1/ri/{ri_id}/action/{action_type}` | Execute RI action (sell/modify/convert/monitor) | `ri_routes.py` |
| GET | `/api/v1/ri/savings-plans/overview` | Savings Plans health overview | `ri_routes.py` |
| POST | `/api/v1/ri/savings-plans/analyze` | Trigger Savings Plans analysis | `ri_routes.py` |
| GET | `/api/v1/ri/unified-coverage` | Unified RI + Savings Plans coverage | `ri_routes.py` |

```bash
# RI health overview
curl -s -X GET $BASE_URL/api/v1/ri/overview \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool

# List all Reserved Instances with utilization
curl -s -X GET $BASE_URL/api/v1/ri/list \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool

# Unified RI + Savings Plans coverage report
curl -s -X GET $BASE_URL/api/v1/ri/unified-coverage \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool

# Savings Plans overview
curl -s -X GET $BASE_URL/api/v1/ri/savings-plans/overview \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool

# Trigger RI analysis (Org Admin only)
curl -s -X POST $BASE_URL/api/v1/ri/analyze \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"account_id":"ACCOUNT_ID","region":"us-east-1"}' | python3 -m json.tool

# Get recommendations for specific RI
curl -s -X GET $BASE_URL/api/v1/ri/RI_ID/recommendations \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool

# Execute RI action (sell / modify / convert / monitor)
curl -s -X POST $BASE_URL/api/v1/ri/RI_ID/action/monitor \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{}' | python3 -m json.tool
```

---

### S3 Storage Optimization

> Analyzes S3 bucket storage classes and recommends tiering strategies (Intelligent-Tiering, Glacier, etc.).

| Method | Endpoint | Description | Source |
|--------|----------|-------------|--------|
| GET | `/api/v1/s3/overview` | S3 storage optimization overview | `s3_routes.py` |
| POST | `/api/v1/s3/analyze` | Trigger S3 tiering analysis (Org Admin) | `s3_routes.py` |

```bash
# S3 optimization overview
curl -s -X GET $BASE_URL/api/v1/s3/overview \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool

# Trigger S3 tiering analysis (Org Admin only)
curl -s -X POST $BASE_URL/api/v1/s3/analyze \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"account_id":"ACCOUNT_ID","region":"us-east-1"}' | python3 -m json.tool
```

---

### Data Transfer Cost Analysis

> Analyzes AWS cross-region, cross-AZ, and internet data transfer costs with optimization recommendations.

| Method | Endpoint | Description | Source |
|--------|----------|-------------|--------|
| GET | `/api/v1/transfer/overview` | Data Transfer optimization overview | `transfer_routes.py` |
| POST | `/api/v1/transfer/analyze` | Trigger data transfer cost analysis (Org Admin) | `transfer_routes.py` |

```bash
# Data transfer overview
curl -s -X GET $BASE_URL/api/v1/transfer/overview \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool

# Trigger transfer cost analysis (Org Admin only)
curl -s -X POST $BASE_URL/api/v1/transfer/analyze \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"account_id":"ACCOUNT_ID","region":"us-east-1"}' | python3 -m json.tool
```

---

## Tag Management

### Tag Policies

| Method | Endpoint | Description | Source |
|--------|----------|-------------|--------|
| GET | `/api/v1/tags/policies/` | List all tag policies | `tag_policy_routes.py` |
| POST | `/api/v1/tags/policies/` | Create tag policy (Admin) | `tag_policy_routes.py` |
| PUT | `/api/v1/tags/policies/{policy_id}` | Update tag policy | `tag_policy_routes.py` |
| DELETE | `/api/v1/tags/policies/{policy_id}` | Delete tag policy | `tag_policy_routes.py` |
| PATCH | `/api/v1/tags/policies/{policy_id}/toggle` | Toggle policy active status | `tag_policy_routes.py` |

```bash
# List all tag policies
curl -s -X GET $BASE_URL/api/v1/tags/policies/ \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool

# Create tag policy
curl -s -X POST $BASE_URL/api/v1/tags/policies/ \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name":"require-env-tag","required_keys":["Environment","Owner","CostCenter"],"enforcement_level":"warn"}' | python3 -m json.tool

# Toggle policy
curl -s -X PATCH $BASE_URL/api/v1/tags/policies/POLICY_ID/toggle \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"active":true}' | python3 -m json.tool
```

### Tag Resources

| Method | Endpoint | Description | Source |
|--------|----------|-------------|--------|
| GET | `/api/v1/tags/resources/{resource_type}/{resource_id}` | Get current tags + suggestions | `tag_management_routes.py` |
| POST | `/api/v1/tags/resources/{resource_type}/{resource_id}` | Update tags on a resource | `tag_management_routes.py` |
| POST | `/api/v1/tags/resources/bulk` | Apply tags to multiple resources | `tag_management_routes.py` |

```bash
# Get tags and suggestions for a cluster
curl -s -X GET $BASE_URL/api/v1/tags/resources/cluster/CLUSTER_ID \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool

# Update tags on resource
curl -s -X POST $BASE_URL/api/v1/tags/resources/cluster/CLUSTER_ID \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"tags":{"Environment":"production","Owner":"ath@gmail.com","CostCenter":"engineering"}}' | python3 -m json.tool

# Bulk tag multiple resources
curl -s -X POST $BASE_URL/api/v1/tags/resources/bulk \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"resources":[{"type":"cluster","id":"CLUSTER_ID_1"},{"type":"cluster","id":"CLUSTER_ID_2"}],"tags":{"Environment":"production"}}' | python3 -m json.tool
```

### Tag Automation Rules

| Method | Endpoint | Description | Source |
|--------|----------|-------------|--------|
| GET | `/api/v1/tags/automation/rules` | List all automation rules | `tag_automation_routes.py` |
| POST | `/api/v1/tags/automation/rules` | Create automation rule (Admin) | `tag_automation_routes.py` |
| PUT | `/api/v1/tags/automation/rules/{rule_id}` | Update rule | `tag_automation_routes.py` |
| DELETE | `/api/v1/tags/automation/rules/{rule_id}` | Delete rule | `tag_automation_routes.py` |
| PATCH | `/api/v1/tags/automation/rules/{rule_id}/toggle` | Toggle rule enabled | `tag_automation_routes.py` |
| GET | `/api/v1/tags/automation/log` | Get paginated automation execution log | `tag_automation_routes.py` |

```bash
# List automation rules
curl -s -X GET $BASE_URL/api/v1/tags/automation/rules \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool

# Get automation log
curl -s -X GET "$BASE_URL/api/v1/tags/automation/log?page=1&per_page=20" \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
```

### Tag Compliance

| Method | Endpoint | Description | Source |
|--------|----------|-------------|--------|
| GET | `/api/v1/tags/compliance/summary` | Aggregate compliance summary | `tag_compliance_routes.py` |
| GET | `/api/v1/tags/compliance/resources` | List compliance resources with filtering | `tag_compliance_routes.py` |
| GET | `/api/v1/tags/compliance/heatmap` | Per-tag-key coverage percentages | `tag_compliance_routes.py` |

```bash
# Compliance summary
curl -s -X GET $BASE_URL/api/v1/tags/compliance/summary \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool

# Compliance heatmap
curl -s -X GET $BASE_URL/api/v1/tags/compliance/heatmap \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool

# Compliance resources list
curl -s -X GET "$BASE_URL/api/v1/tags/compliance/resources?status=non_compliant" \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
```

### Tag Scoring

| Method | Endpoint | Description | Source |
|--------|----------|-------------|--------|
| GET | `/api/v1/tags/scoring/config` | Get scoring config for org | `tag_scoring_routes.py` |
| PUT | `/api/v1/tags/scoring/config` | Save/update scoring config | `tag_scoring_routes.py` |
| GET | `/api/v1/tags/scoring/preview` | Preview scoring without saving | `tag_scoring_routes.py` |

```bash
# Get scoring config
curl -s -X GET $BASE_URL/api/v1/tags/scoring/config \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool

# Preview scoring
curl -s -X GET $BASE_URL/api/v1/tags/scoring/preview \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
```

---

## Admin (Super Admin Only)

| Method | Endpoint | Description | Source |
|--------|----------|-------------|--------|
| GET | `/api/v1/admin/organizations` | List all organizations | `admin_routes.py` |
| POST | `/api/v1/admin/organizations/{org_id}/toggle` | Toggle org active status | `admin_routes.py` |
| GET | `/api/v1/admin/clients` | List all client users | `admin_routes.py` |
| GET | `/api/v1/admin/clients/{client_id}` | Get client details | `admin_routes.py` |
| POST | `/api/v1/admin/clients/{client_id}/toggle` | Toggle client active status | `admin_routes.py` |
| POST | `/api/v1/admin/clients/{client_id}/reset-password` | Reset client password | `admin_routes.py` |
| GET | `/api/v1/admin/stats` | Platform-wide stats | `admin_routes.py` |
| GET | `/api/v1/admin/health` | Platform health metrics | `admin_routes.py` |
| GET | `/api/v1/admin/billing` | Billing info | `admin_routes.py` |
| GET | `/api/v1/admin/dashboard` | Admin dashboard stats | `admin_routes.py` |
| GET | `/api/v1/admin/agent-fleet` | All agents across all orgs | `admin_routes.py` |
| GET | `/api/v1/admin/config/{key}` | Get system config value | `admin_routes.py` |
| PATCH | `/api/v1/admin/config` | Update system config | `admin_routes.py` |
| GET | `/api/v1/admin/platform/connection` | Platform AWS connection status | `admin_routes.py` |
| POST | `/api/v1/admin/impersonate` | Impersonate an organization | `admin_routes.py` |

```bash
# Admin dashboard
curl -s -X GET $BASE_URL/api/v1/admin/dashboard \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool

# Platform-wide stats
curl -s -X GET $BASE_URL/api/v1/admin/stats \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool

# List all organizations
curl -s -X GET $BASE_URL/api/v1/admin/organizations \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool

# All agents across all orgs
curl -s -X GET $BASE_URL/api/v1/admin/agent-fleet \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool

# Platform AWS connection status
curl -s -X GET $BASE_URL/api/v1/admin/platform/connection \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool

# Admin health metrics
curl -s -X GET $BASE_URL/api/v1/admin/health \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
```

---

## Database Quick Checks (via Docker)

```bash
# Open psql inside postgres container
docker exec -it spot-optimizer-postgres psql -U postgres -d spot_optimizer

# Count records in key tables
docker exec -it spot-optimizer-postgres psql -U postgres -d spot_optimizer \
  -c "SELECT 'users' as tbl, COUNT(*) FROM users UNION ALL SELECT 'clusters', COUNT(*) FROM clusters UNION ALL SELECT 'instances', COUNT(*) FROM instances UNION ALL SELECT 'audit_logs', COUNT(*) FROM audit_logs;"

# Check all users
docker exec -it spot-optimizer-postgres psql -U postgres -d spot_optimizer \
  -c "SELECT id, email, full_name, is_active, created_at FROM users ORDER BY created_at DESC LIMIT 20;"

# Check clusters
docker exec -it spot-optimizer-postgres psql -U postgres -d spot_optimizer \
  -c "SELECT id, name, status, region, account_id, created_at FROM clusters ORDER BY created_at DESC LIMIT 20;"
```

---

## Redis Quick Checks (via Docker)

```bash
# Open redis-cli inside redis container
docker exec -it spot-optimizer-redis redis-cli

# Check all keys matching blacklist pattern
docker exec -it spot-optimizer-redis redis-cli KEYS "*blacklist*"

# Check all keys matching cluster pattern
docker exec -it spot-optimizer-redis redis-cli KEYS "*cluster*"

# Get all keys (be careful in production)
docker exec -it spot-optimizer-redis redis-cli KEYS "*"

# Get a specific key value
docker exec -it spot-optimizer-redis redis-cli GET "KEY_NAME"

# Check Redis memory info
docker exec -it spot-optimizer-redis redis-cli INFO memory
```

---

## One-Liner Docker Exec Test Commands

> Use these from your **host machine** (no need to enter the container).

```bash
# Health check from host
docker exec spot-optimizer-backend curl -s http://localhost:8000/health | python3 -m json.tool

# Login from host and print token
docker exec spot-optimizer-backend curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"ath@gmail.com","password":"Atharva@123"}' | python3 -m json.tool

# Get dashboard metrics (replace TOKEN)
docker exec spot-optimizer-backend curl -s -X GET http://localhost:8000/api/v1/metrics/dashboard \
  -H "Authorization: Bearer TOKEN" | python3 -m json.tool

# List clusters (replace TOKEN)
docker exec spot-optimizer-backend curl -s -X GET http://localhost:8000/api/v1/clusters \
  -H "Authorization: Bearer TOKEN" | python3 -m json.tool

# Check backend logs
docker logs spot-optimizer-backend --tail 100

# Follow backend logs live
docker logs spot-optimizer-backend -f

# Check all running containers
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
```

---

*Generated: 2026-03-25 | Total Endpoints: ~220+ HTTP + 1 WebSocket*
