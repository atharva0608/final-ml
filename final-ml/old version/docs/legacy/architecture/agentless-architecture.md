# Agentless Architecture: How It Works & What You Need

**Version**: 3.0.0
**Last Updated**: 2025-12-02

---

## Table of Contents

1. [Overview](#overview)
2. [What "Agentless" Means](#what-agentless-means)
3. [How Agentlessness is Achieved](#how-agentlessness-is-achieved)
4. [What's Required on Client Instances](#whats-required-on-client-instances)
5. [Backend Server Requirements](#backend-server-requirements)
6. [IAM Permissions Deep Dive](#iam-permissions-deep-dive)
7. [Network Requirements](#network-requirements)
8. [Security Considerations](#security-considerations)
9. [Comparison: Agent vs Agentless](#comparison-agent-vs-agentless)
10. [Limitations and Trade-offs](#limitations-and-trade-offs)
11. [Migration Path: Adding Agents Later](#migration-path-adding-agents-later)

---

## Overview

CAST-AI Mini uses an **agentless architecture**, meaning there is **no custom software running on your managed EC2 instances**. All monitoring, decision-making, and orchestration happens from a centralized backend server using AWS APIs.

This document explains:
- How we achieve agentlessness
- What you need on client instances (spoiler: almost nothing!)
- What the backend server requires
- Security and network considerations

---

## What "Agentless" Means

### Traditional Agent-Based Approach

```
┌─────────────────────────┐
│   Your EC2 Instance     │
│                         │
│  ┌──────────────────┐   │
│  │  Custom Agent    │   │
│  │  - Collects data │   │
│  │  - Reports health│   │
│  │  - Executes cmds │   │
│  └──────────────────┘   │
│          ▲               │
│          │ HTTP/gRPC     │
└──────────┼───────────────┘
           │
           ▼
    ┌─────────────┐
    │   Backend   │
    └─────────────┘
```

**Problems**:
- Must install and maintain agent on every instance
- Agent can crash or fail
- Agent uses CPU/memory resources
- Version compatibility issues
- Security surface area (agent credentials, API keys)

### CAST-AI Mini Agentless Approach

```
┌─────────────────────────┐
│   Your EC2 Instance     │
│                         │
│   [NO CUSTOM SOFTWARE]  │
│                         │
│   Standard AWS only:    │
│   - CloudWatch Agent*   │
│   - SSM Agent*          │
│   - (both optional)     │
└─────────────────────────┘
           ▲
           │ AWS SDK Calls
           │ (EC2, CloudWatch)
           │
    ┌──────┴──────┐
    │   Backend   │
    │  (AWS SDK)  │
    └─────────────┘
```

**Benefits**:
- Zero maintenance on client instances
- No custom software to debug
- No credentials on instances
- Lower resource usage
- Simpler security model

---

## How Agentlessness is Achieved

### 1. Instance State Monitoring

**How**: AWS EC2 API (`DescribeInstances`, `DescribeInstanceStatus`)

**What We Get**:
- Instance state (running, stopped, terminated)
- Instance type, AZ, subnet
- Lifecycle (spot or on-demand)
- Tags, security groups, VPC info

**No Agent Needed**: This is all available via AWS API

### 2. Usage Metrics Collection

**How**: AWS CloudWatch API (`GetMetricStatistics`, `GetMetricData`)

**What We Get**:
- **CPU Utilization**: Always available (EC2 default metrics)
- **Network In/Out**: Always available (EC2 default metrics)
- **Disk I/O**: Available if detailed monitoring enabled
- **Memory Utilization**: Requires CloudWatch Agent on instance*

**No Custom Agent Needed**: Standard AWS CloudWatch Agent (optional for memory)

### 3. Spot Price Monitoring

**How**: AWS EC2 API (`DescribeSpotPriceHistory`)

**What We Get**:
- Current spot prices for all instance types
- Historical price data (up to 90 days)
- Prices per AZ and pool

**No Agent Needed**: All via AWS API

### 4. Instance Lifecycle Management

**How**: AWS EC2 API (`RunInstances`, `TerminateInstances`)

**What We Do**:
- Launch new instances when switching
- Terminate old instances after switch
- Wait for state transitions

**No Agent Needed**: Direct AWS API calls

### 5. Decision Making

**How**: Backend service with ML model

**What Happens**:
- All data collected via AWS APIs
- ML model predicts future prices
- Decision engine evaluates options
- Actions executed via AWS SDK

**No Agent Needed**: Everything in backend

---

## What's Required on Client Instances

### Minimal Requirements

✅ **Nothing** if you only want CPU and network metrics

✅ **Standard AWS CloudWatch Agent** (optional) if you want memory metrics

### Optional Enhancements

#### CloudWatch Agent for Memory Metrics

**Why**: AWS doesn't provide memory metrics by default

**Installation**:
```bash
# Download CloudWatch Agent
wget https://s3.amazonaws.com/amazoncloudwatch-agent/ubuntu/amd64/latest/amazon-cloudwatch-agent.deb

# Install
sudo dpkg -i amazon-cloudwatch-agent.deb

# Configure (simple config for memory only)
cat > /opt/aws/amazon-cloudwatch-agent/etc/config.json <<EOF
{
  "metrics": {
    "namespace": "CWAgent",
    "metrics_collected": {
      "mem": {
        "measurement": [
          {
            "name": "mem_used_percent",
            "rename": "MemoryUtilization"
          }
        ],
        "metrics_collection_interval": 60
      }
    }
  }
}
EOF

# Start agent
sudo /opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl \
    -a fetch-config \
    -m ec2 \
    -s \
    -c file:/opt/aws/amazon-cloudwatch-agent/etc/config.json
```

**Cost**: ~$0.30/month for 1 custom metric (MemoryUtilization)

#### Systems Manager (SSM) Agent

**Why**: Allows remote management without SSH

**Installation**: Usually pre-installed on AWS AMIs

**Benefit**: Backend can optionally use SSM for advanced operations (future feature)

### What You DON'T Need

❌ Custom CAST-AI agent
❌ Additional monitoring tools
❌ Third-party agents
❌ Special credentials or API keys on instances
❌ Incoming network connections (no open ports required)

---

## Backend Server Requirements

### Infrastructure

The backend server can run on:
- EC2 instance (recommended with IAM instance profile)
- ECS/Fargate
- On-premises server with AWS credentials
- Your laptop (for testing)

### Software Dependencies

```bash
# System packages
- Python 3.12+
- MySQL 8.0 (via Docker or managed RDS)
- Node.js 20.x (for frontend)
- Nginx (for frontend serving)

# Python packages (see backend/requirements.txt)
- Flask (web framework)
- boto3 (AWS SDK)
- PyMySQL (database)
- scikit-learn (ML model)
- numpy, pandas (data processing)
```

### AWS Credentials

The backend needs AWS credentials with permissions to:
- Describe and manage EC2 instances
- Read CloudWatch metrics
- Fetch spot price history

**Options**:

1. **IAM Instance Profile** (recommended)
   ```bash
   # Attach IAM role to EC2 instance running backend
   # No credentials in config files!
   ```

2. **Environment Variables**
   ```bash
   export AWS_ACCESS_KEY_ID=AKIA...
   export AWS_SECRET_ACCESS_KEY=...
   export AWS_REGION=us-east-1
   ```

3. **AWS Credentials File**
   ```bash
   # ~/.aws/credentials
   [default]
   aws_access_key_id = AKIA...
   aws_secret_access_key = ...
   ```

### Resource Requirements

**Minimum**:
- 2 vCPU
- 4 GB RAM
- 20 GB disk
- 1 Mbps network

**Recommended**:
- 2-4 vCPU
- 8 GB RAM
- 50 GB disk
- 10 Mbps network

**Scalability**: Can manage dozens of instances on these specs

---

## IAM Permissions Deep Dive

### Required IAM Policy

The backend server (or its IAM role) needs these permissions:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "InstanceManagement",
      "Effect": "Allow",
      "Action": [
        "ec2:DescribeInstances",
        "ec2:DescribeInstanceStatus",
        "ec2:DescribeInstanceTypes",
        "ec2:RunInstances",
        "ec2:TerminateInstances"
      ],
      "Resource": "*"
    },
    {
      "Sid": "InstanceTagging",
      "Effect": "Allow",
      "Action": [
        "ec2:CreateTags",
        "ec2:DeleteTags"
      ],
      "Resource": "arn:aws:ec2:*:*:instance/*",
      "Condition": {
        "StringEquals": {
          "ec2:CreateAction": "RunInstances"
        }
      }
    },
    {
      "Sid": "NetworkDiscovery",
      "Effect": "Allow",
      "Action": [
        "ec2:DescribeAvailabilityZones",
        "ec2:DescribeSubnets",
        "ec2:DescribeSecurityGroups",
        "ec2:DescribeVpcs"
      ],
      "Resource": "*"
    },
    {
      "Sid": "SpotPricing",
      "Effect": "Allow",
      "Action": [
        "ec2:DescribeSpotPriceHistory"
      ],
      "Resource": "*"
    },
    {
      "Sid": "CloudWatchMetrics",
      "Effect": "Allow",
      "Action": [
        "cloudwatch:GetMetricStatistics",
        "cloudwatch:GetMetricData",
        "cloudwatch:ListMetrics"
      ],
      "Resource": "*"
    }
  ]
}
```

### Permission Justification

| Permission | Why Needed | Frequency |
|------------|------------|-----------|
| `DescribeInstances` | Get current instance state | Every 5-10 min |
| `DescribeInstanceStatus` | Check instance health | Every 5-10 min |
| `RunInstances` | Launch new instances when switching | Rare (only during switches) |
| `TerminateInstances` | Terminate old instances after switch | Rare (only during switches) |
| `CreateTags` | Tag new instances for tracking | Rare (only during switches) |
| `DescribeSpotPriceHistory` | Fetch current and historical spot prices | Every 5 min |
| `GetMetricStatistics` | Read CloudWatch metrics (CPU, memory, network) | Every 5-10 min |
| `DescribeAvailabilityZones` | Find available AZs for instance type | Once per decision cycle |

### Security Best Practices

1. **Use IAM Instance Profile** instead of access keys
2. **Least Privilege**: Only grant permissions above, nothing more
3. **Resource Tags**: Optionally restrict to instances with specific tags
4. **CloudTrail**: Enable for audit logging of all EC2 API calls
5. **Region Restriction**: Limit to specific regions in policy

**Example: Restrict to Tagged Instances**:
```json
{
  "Condition": {
    "StringEquals": {
      "ec2:ResourceTag/ManagedBy": "CAST-AI-Mini"
    }
  }
}
```

---

## Network Requirements

### Backend Server

**Outbound** (must allow):
- HTTPS (443) to AWS API endpoints:
  - `ec2.{region}.amazonaws.com`
  - `monitoring.{region}.amazonaws.com`
  - `*.amazonaws.com` (recommended for simplicity)

**Inbound** (optional, for UI):
- HTTP (80) from your network
- HTTPS (443) from your network (if using TLS)

### Client Instances

**Outbound** (optional, for CloudWatch Agent):
- HTTPS (443) to `monitoring.{region}.amazonaws.com`

**Inbound**: ❌ None required from backend

**Key Point**: Backend never connects TO instances. All communication is via AWS APIs.

### VPC Considerations

**Client Instances**:
- Can be in private subnets (no internet access required*)
- \*Unless CloudWatch Agent is used, then needs NAT Gateway or VPC endpoint

**Backend Server**:
- Must reach AWS API endpoints (public internet or VPC endpoints)
- Option 1: Public subnet with internet access
- Option 2: Private subnet with NAT Gateway
- Option 3: Private subnet with VPC endpoints for EC2 and CloudWatch

**Cross-AZ**: Backend can manage instances in any AZ within the region

**Cross-Region**: Currently not supported (future enhancement)

---

## Security Considerations

### Threat Model

**Attack Surface**:
1. Backend server (primary target)
2. Database (MySQL)
3. AWS credentials
4. Frontend dashboard

**NOT at risk**:
- Client instances (no custom software to exploit)
- Network traffic to instances (backend doesn't connect to them)

### Security Measures

#### 1. Backend Server

✅ Run with least-privilege IAM role
✅ No AWS access keys in code or config
✅ Database credentials in environment variables only
✅ Enable OS firewall (ufw/iptables)
✅ Regular security updates
✅ Monitor logs for anomalies

#### 2. Database

✅ Strong passwords
✅ Docker network isolation or RDS security groups
✅ No public access (bind to localhost or private IP)
✅ Regular backups
✅ Encrypted at rest (RDS) or encrypted volumes (Docker)

#### 3. AWS Credentials

✅ IAM instance profile (no keys in files)
✅ MFA for IAM users managing the role
✅ Rotate access keys regularly if using them
✅ Monitor with CloudTrail and GuardDuty

#### 4. Frontend Dashboard

✅ Rate limiting via Nginx
✅ HTTPS recommended for production
✅ Authentication (implement user login)
✅ Security headers (CSP, HSTS, etc.)

### Compliance

**Data Handling**:
- No sensitive data stored on client instances
- All data in centralized database (easier to secure)
- Audit trail via CloudTrail
- GDPR/CCPA: Easier to manage data deletion (central DB only)

**Instance Isolation**:
- Client instances remain isolated
- No cross-instance communication required
- No shared secrets or keys

---

## Comparison: Agent vs Agentless

### Agentless (Current CAST-AI Mini)

**Pros**:
✅ Zero maintenance on client instances
✅ No custom software to debug or update
✅ Lower security surface area
✅ No credentials on instances
✅ Works with any EC2 instance (no prerequisites)
✅ Simpler architecture

**Cons**:
❌ Slightly delayed metrics (CloudWatch delay: 1-5 minutes)
❌ Limited to AWS-provided metrics
❌ Can't collect custom application metrics
❌ No immediate interruption signals (rely on AWS metadata service)

**Best For**:
- Single-instance or small deployments
- When you want minimal operational overhead
- When security/compliance is critical
- When managing standard workloads

### Agent-Based (Future Option)

**Pros**:
✅ Real-time metrics (sub-second granularity)
✅ Custom application metrics
✅ Immediate interruption signals
✅ Can execute custom pre/post switch scripts
✅ Application-aware decisions

**Cons**:
❌ Must install and maintain agent on every instance
❌ Agent can fail or crash
❌ Uses instance resources (CPU, memory, disk)
❌ Credentials or tokens needed on instances
❌ Version compatibility management
❌ Larger security surface area

**Best For**:
- Large multi-instance deployments
- When you need real-time metrics
- When you need application-aware orchestration
- When you have ops team to manage agents

### Hybrid Approach (Future)

You could run both:
- Agentless by default
- Optional agent for instances that need real-time metrics
- Decision engine works with both via unified Executor interface

---

## Limitations and Trade-offs

### Current Limitations

1. **Metric Delay**
   - CloudWatch metrics delayed by 1-5 minutes
   - Decision cycles use slightly stale data
   - **Mitigation**: Use 5-10 minute decision intervals to smooth out delays

2. **Memory Metrics**
   - Require CloudWatch Agent on instances
   - **Mitigation**: Optional; system works without memory metrics

3. **No Application Metrics**
   - Can't monitor app-specific metrics (request rate, queue depth, etc.)
   - **Mitigation**: Use CPU/network as proxies

4. **No Custom Pre/Post Scripts**
   - Can't run custom commands before/after switch
   - **Mitigation**: Use AMI snapshots or launch templates with user data

5. **Single Region**
   - Can't manage instances across regions
   - **Mitigation**: Run separate backend per region

### Trade-off Analysis

| Factor | Agentless | Agent-Based | Winner |
|--------|-----------|-------------|--------|
| Simplicity | ★★★★★ | ★★☆☆☆ | Agentless |
| Maintenance | ★★★★★ | ★☆☆☆☆ | Agentless |
| Security | ★★★★★ | ★★★☆☆ | Agentless |
| Metric Freshness | ★★★☆☆ | ★★★★★ | Agent |
| Custom Metrics | ★☆☆☆☆ | ★★★★★ | Agent |
| Cost | ★★★★★ | ★★★☆☆ | Agentless |
| Scalability | ★★★★☆ | ★★★★★ | Tie |

**Verdict**: Agentless wins for 80% of use cases. Agents make sense for <20% with very specific needs.

---

## Migration Path: Adding Agents Later

If you start agentless and later want agents, the architecture supports it:

### Step 1: Implement AgentBasedExecutor

```python
class AgentBasedExecutor(Executor):
    def get_usage_metrics(self, instance_id, window_minutes):
        # Query agent API instead of CloudWatch
        agent_url = f"http://{instance_ip}:8080/metrics"
        response = requests.get(agent_url)
        return response.json()

    # Other methods same as AgentlessExecutor
```

### Step 2: Deploy Agent to Instances

- Package agent as binary or Python script
- Install via user data or Systems Manager
- Agent reports to backend via HTTPS

### Step 3: Switch Executor in Backend

```python
# backend/backend.py
if config.USE_AGENT:
    executor = AgentBasedExecutor()
else:
    executor = AWSAgentlessExecutor()

# Decision engine uses same interface
decision = decision_engine.decide(executor=executor, ...)
```

### Step 4: Gradual Rollout

- Start with agentless for all instances
- Install agent on select instances (tag: `agent=true`)
- Backend detects tag and uses agent executor for those
- Gradually expand to more instances
- Keep agentless as fallback if agent fails

**Key**: Decision logic never changes. Only Executor swaps.

---

## Conclusion

CAST-AI Mini's agentless architecture provides:
- **Simplicity**: No custom software on instances
- **Security**: Minimal attack surface, centralized credentials
- **Reliability**: No agents to fail or maintain
- **Cost-Effectiveness**: Lower operational overhead

**Trade-off**: Slightly delayed metrics, fewer custom options

**For most use cases**, the agentless approach is simpler, more secure, and easier to operate. If you later need real-time metrics or custom orchestration, the architecture supports adding agents without rewriting the core decision logic.

---

## FAQ

**Q: Can I use this with Kubernetes?**
A: Not currently. This phase focuses on standalone EC2. K8s support planned for future.

**Q: Does this work with Auto Scaling Groups?**
A: Not automatically. You'd manage each instance independently. ASG integration is a future enhancement.

**Q: What if AWS CloudWatch is down?**
A: Decision engine uses cached data or skips that cycle. System is resilient to transient AWS API failures.

**Q: Can I monitor on-premises VMs?**
A: No. Agentless approach requires AWS APIs. For on-prem, you'd need an agent.

**Q: What about spot interruption warnings?**
A: AWS provides 2-minute warnings via instance metadata. Backend polls instance metadata (available via AWS API). Future enhancement: subscribe to EC2 interruption warnings via EventBridge.

**Q: Do I need CloudWatch detailed monitoring?**
A: No. Basic monitoring (5-minute intervals) is sufficient. Detailed (1-minute) is optional for faster decisions.

**Q: Can I manage instances in multiple AWS accounts?**
A: Yes, with cross-account IAM roles. Configure backend with AssumeRole permissions.

---

**For more details, see**:
- [Master Session Memory](master-session-memory.md) - Complete design doc
- [README](../README.md) - Quick start guide
- [IAM Policy Examples](#iam-permissions-deep-dive) - Security configuration

---

**Version**: 3.0.0
**Last Updated**: 2025-12-02
