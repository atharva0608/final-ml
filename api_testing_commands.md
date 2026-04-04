# Spot Optimizer Platform API Testing Commands

This guide provides `docker exec` commands to test the platform APIs directly from the backend container (`spot-optimizer-backend`). You can copy and paste these commands into your terminal.

## Step 1: Authentication & Token Retrieval

First, authenticate with the provided credentials (`ath@gmail.com` / `Atharva@123`) to get the JWT access token and export it as an environment variable in your current terminal session.

```bash
# Get the access token and export it
export TOKEN=$(docker exec spot-optimizer-backend curl -s -X POST "http://localhost:8000/api/v1/auth/login" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=ath@gmail.com&password=Atharva@123" | md5sum | cut -d' ' -f1) # Note: we use python to extract the actual token cleanly

export TOKEN=$(docker exec spot-optimizer-backend python -c '
import urllib.request, urllib.parse, json;
data = urllib.parse.urlencode({"username": "ath@gmail.com", "password": "Atharva@123"}).encode();
req = urllib.request.Request("http://localhost:8000/api/v1/auth/login", data=data, method="POST");
rsp = urllib.request.urlopen(req);
print(json.loads(rsp.read().decode())["access_token"])
')

# Verify the token
echo $TOKEN
```

---

## Table 1: General Platform APIs & Dashboards

These APIs fetch data from the internal PostgreSQL database or Redis cache regarding platform metrics, clusters, and saved settings. Replace `{id}` or `{cluster_id}` with an actual ID from the first `GET /api/v1/clusters` response.

| Endpoint | Description | Source Component / Route | Docker Exec Curl Command |
|----------|-------------|----------------------------|---------------------------|
| **Get All Clusters** | Lists all clusters onboarded | `backend/api/clusters.py` | `docker exec spot-optimizer-backend curl -s -X GET "http://localhost:8000/api/v1/clusters" -H "Authorization: Bearer $TOKEN"` |
| **Get Cluster Details** | Fetches detailed info for a cluster | `backend/api/clusters.py` | `docker exec spot-optimizer-backend curl -s -X GET "http://localhost:8000/api/v1/clusters/{cluster_id}" -H "Authorization: Bearer $TOKEN"` |
| **Get Cluster Nodes** | Fetches active nodes for a cluster | `backend/api/clusters.py` | `docker exec spot-optimizer-backend curl -s -X GET "http://localhost:8000/api/v1/clusters/{cluster_id}/nodes/detailed" -H "Authorization: Bearer $TOKEN"` |
| **Dashboard Metrics** | High-level cost and savings KPIs | `backend/api/metrics.py` | `docker exec spot-optimizer-backend curl -s -X GET "http://localhost:8000/api/v1/metrics/dashboard" -H "Authorization: Bearer $TOKEN"` |
| **Trends Chart** | 30-day savings & spot trends | `backend/api/metrics.py` | `docker exec spot-optimizer-backend curl -s -X GET "http://localhost:8000/api/v1/multi-cluster/trends" -H "Authorization: Bearer $TOKEN"` |
| **Agent Fleet Status** | DaemonSet health across fleet | `backend/api/admin.py` | `docker exec spot-optimizer-backend curl -s -X GET "http://localhost:8000/api/v1/admin/agent-fleet" -H "Authorization: Bearer $TOKEN"` |
| **Tenant List** | View all organizations/tenants | `backend/api/admin.py` | `docker exec spot-optimizer-backend curl -s -X GET "http://localhost:8000/api/v1/admin/organizations" -H "Authorization: Bearer $TOKEN"` |
| **Audit Logs** | Recent activity feed | `backend/api/audit.py` | `docker exec spot-optimizer-backend curl -s -X GET "http://localhost:8000/api/v1/audit/logs" -H "Authorization: Bearer $TOKEN"` |
| **Pending Approvals** | Actions awaiting manual approval | `backend/api/approvals.py` | `docker exec spot-optimizer-backend curl -s -X GET "http://localhost:8000/api/v1/approvals/" -H "Authorization: Bearer $TOKEN"` |

---

## Table 2: Agent Driven / ML APIs (ASCP.AI)

These APIs expose the Decision Engine (DE), predictive ML rankings, rebalancing actions, and disruption heatmaps.

| Endpoint | Description | Source Component / Route | Docker Exec Curl Command |
|----------|-------------|----------------------------|---------------------------|
| **Pool Rankings** | ML-driven fleet-wide pool scores | `backend/api/ascpai_routes.py` | `docker exec spot-optimizer-backend curl -s -X POST "http://localhost:8000/api/v1/ascpai/pools/rankings" -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" -d '{}'` |
| **Rebalance Audit Status** | Recent rebalance/fallback history | `backend/api/ascpai_routes.py` | `docker exec spot-optimizer-backend curl -s -X GET "http://localhost:8000/api/v1/ascpai/rebalancing/status?cluster_id={cluster_id}" -H "Authorization: Bearer $TOKEN"` |
| **Spot Volatility** | Interruption rates by AZ | `backend/api/ascpai_routes.py` | `docker exec spot-optimizer-backend curl -s -X GET "http://localhost:8000/api/v1/ascpai/volatility/status" -H "Authorization: Bearer $TOKEN"` |
| **Node Alternatives** | ML ranking for a specific node | `backend/api/ascpai_routes.py` | `docker exec spot-optimizer-backend curl -s -X GET "http://localhost:8000/api/v1/ascpai/clusters/{cluster_id}/nodes/{node_id}/alternatives" -H "Authorization: Bearer $TOKEN"` |
| **Global Intelligence** | Region-wide insights panel | `backend/api/ascpai_routes.py` | `docker exec spot-optimizer-backend curl -s -X GET "http://localhost:8000/api/v1/ascpai/v3/global-intelligence/status" -H "Authorization: Bearer $TOKEN"` |
| **Node Status** | Diagnostics (active cooldowns, risk, EV) | `backend/api/ascpai_routes.py` | `docker exec spot-optimizer-backend curl -s -X GET "http://localhost:8000/api/v1/ascpai/clusters/{cluster_id}/nodes/{node_id}/status" -H "Authorization: Bearer $TOKEN"` |
| **Savings Velocity** | Cluster-level savings forecast | `backend/api/ascpai_routes.py` | `docker exec spot-optimizer-backend curl -s -X GET "http://localhost:8000/api/v1/ascpai/savings-velocity" -H "Authorization: Bearer $TOKEN"` |

---

## Table 3: AWS Data Integration APIs

These APIs either directly proxy to AWS (like AWS Cost Explorer or EC2 Pricing) or trigger AWS-specific background actions. They involve real-time fetching from the cloud provider side.

| Endpoint | Description | Source Component / Route | Docker Exec Curl Command |
|----------|-------------|----------------------------|---------------------------|
| **AWS Cluster Utilization** | CPU/Mem usage from raw AWS CloudWatch / K8s Metrics API | `backend/api/clusters.py` | `docker exec spot-optimizer-backend curl -s -X GET "http://localhost:8000/api/v1/clusters/{cluster_id}/utilization" -H "Authorization: Bearer $TOKEN"` |
| **Market View / Spot Price History**| Directly fetches spot vs on-demand price gap for AZs | `backend/api/ascpai_routes.py` | `docker exec spot-optimizer-backend curl -s -X GET "http://localhost:8000/api/v1/ascpai/clusters/{cluster_id}/market-view" -H "Authorization: Bearer $TOKEN"` |
| **Verify AWS Connection** | Validates the AWS IAM Role ARN for cross-account trust | `backend/api/onboarding.py` | `docker exec spot-optimizer-backend curl -s -X POST "http://localhost:8000/api/v1/onboarding/verify" -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" -d '{"role_arn": "arn:aws:iam::123456789012:role/spot-optimizer-role", "region": "ap-south-1"}'` |
| **Agent Registration** | Simulates Spot Agent daemonset connecting from K8s to register | `backend/api/agents.py` | `docker exec spot-optimizer-backend curl -s -X POST "http://localhost:8000/api/v1/agents/register" -H "X-Agent-Auth: YOUR_AGENT_TOKEN_HERE" -H "Content-Type: application/json" -d '{"cluster_id": "{cluster_id}", "nodes": [{"name": "ip-10-0-1-5", "instance_id": "i-1234abcd"}]}'` |
| **Pool Audit (Dry Run Check)** | Triggers EC2 Dry Run capacity check to AWS | `backend/api/ascpai_routes.py` | `docker exec spot-optimizer-backend curl -s -X GET "http://localhost:8000/api/v1/ascpai/clusters/{cluster_id}/nodes/{node_id}/pool-audit" -H "Authorization: Bearer $TOKEN"` |

### How to use:
1. SSH into the machine or navigate to the directory where Docker Compose is running.
2. Ensure the backend container is running: `docker ps | grep spot-optimizer-backend`.
3. Run the export `TOKEN=...` snippet above.
4. Pick any command, replace parameters like `{cluster_id}` with real values (e.g. `cluster-123` or your UUID), and hit enter.
