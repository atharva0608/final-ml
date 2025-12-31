# AWS IAM Policy for Spot Optimizer

This document provides the comprehensive IAM policy required for Spot Optimizer to function with full capabilities when using **Access Keys** connection method.

## 📋 Quick Setup Guide

### Step 1: Create IAM User
1. Go to AWS Console → IAM → Users → Create User
2. User name: `spot-optimizer-api` (or your preferred name)
3. Enable **Access key - Programmatic access**

### Step 2: Attach Policy
1. Copy the JSON policy below
2. Create a new inline policy or custom managed policy
3. Paste the JSON
4. Attach to the user

### Step 3: Get Credentials
1. Download the Access Key ID and Secret Access Key
2. Use these credentials in the Spot Optimizer UI

---

## 🔐 Complete IAM Policy (Copy & Paste)

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "EC2DiscoveryAndMonitoring",
      "Effect": "Allow",
      "Action": [
        "ec2:Describe*",
        "autoscaling:Describe*",
        "eks:DescribeCluster",
        "eks:ListClusters",
        "eks:DescribeNodegroup"
      ],
      "Resource": "*",
      "Comment": "Required for discovering EC2 instances, ASGs, and EKS clusters"
    },
    {
      "Sid": "CloudWatchMetrics",
      "Effect": "Allow",
      "Action": [
        "cloudwatch:GetMetricStatistics",
        "cloudwatch:ListMetrics"
      ],
      "Resource": "*",
      "Comment": "Required for retrieving CPU, memory, and network metrics"
    },
    {
      "Sid": "SpotInstanceOptimization",
      "Effect": "Allow",
      "Action": [
        "ec2:RunInstances",
        "ec2:TerminateInstances",
        "ec2:StopInstances",
        "ec2:StartInstances",
        "ec2:CreateTags",
        "ec2:DeleteTags",
        "ec2:RequestSpotInstances",
        "ec2:CancelSpotInstanceRequests",
        "ec2:CreateSnapshot",
        "ec2:DeleteSnapshot"
      ],
      "Resource": "*",
      "Comment": "Required for launching, terminating, and managing spot instances"
    },
    {
      "Sid": "AutoScalingManagement",
      "Effect": "Allow",
      "Action": [
        "autoscaling:SetDesiredCapacity",
        "autoscaling:TerminateInstanceInAutoScalingGroup",
        "autoscaling:AttachInstances",
        "autoscaling:DetachInstances",
        "autoscaling:UpdateAutoScalingGroup"
      ],
      "Resource": "*",
      "Comment": "Required for managing ASG instances during optimization"
    },
    {
      "Sid": "PassRoleForEC2Instances",
      "Effect": "Allow",
      "Action": "iam:PassRole",
      "Resource": "*",
      "Condition": {
        "StringLike": {
          "iam:PassedToService": "ec2.amazonaws.com"
        }
      },
      "Comment": "CRITICAL: Required for launching instances with IAM roles (e.g., EKS worker nodes)"
    },
    {
      "Sid": "SpotServiceLinkedRole",
      "Effect": "Allow",
      "Action": "iam:CreateServiceLinkedRole",
      "Resource": "arn:aws:iam::*:role/aws-service-role/spot.amazonaws.com/AWSServiceRoleForEC2Spot",
      "Condition": {
        "StringLike": {
          "iam:AWSServiceName": "spot.amazonaws.com"
        }
      },
      "Comment": "Required for creating Spot service-linked role if it doesn't exist"
    },
    {
      "Sid": "PricingAndCostExplorer",
      "Effect": "Allow",
      "Action": [
        "pricing:GetProducts",
        "ce:GetCostAndUsage"
      ],
      "Resource": "*",
      "Comment": "Required for calculating cost savings and spot pricing"
    }
  ]
}
```

---

## 📖 Permission Breakdown

### Why Each Permission is Required

#### 1. **EC2Discovery** (Read-Only)
- `ec2:Describe*` - List all EC2 instances, volumes, snapshots
- `autoscaling:Describe*` - Discover Auto Scaling Groups
- `eks:*` - Identify EKS clusters and node groups

**Used by:** Initial discovery worker, dashboard metrics

---

#### 2. **CloudWatchMetrics** (Read-Only)
- `cloudwatch:GetMetricStatistics` - Retrieve CPU/Memory usage
- `cloudwatch:ListMetrics` - List available metrics

**Used by:** Lab mode instance utilization monitoring

---

#### 3. **SpotInstanceOptimization** (Write Operations)
- `ec2:RunInstances` - Launch new spot instances
- `ec2:TerminateInstances` - Terminate old instances
- `ec2:CreateTags` - Tag instances with "ManagedBy: SpotOptimizer"
- `ec2:RequestSpotInstances` - Request spot capacity

**Used by:** Optimization engine, spot switching logic

---

#### 4. **AutoScalingManagement** (Write Operations)
- `autoscaling:SetDesiredCapacity` - Adjust ASG size
- `autoscaling:AttachInstances` - Attach new spot instance to ASG
- `autoscaling:DetachInstances` - Remove old instance from ASG

**Used by:** ASG-aware optimization workflow

---

#### 5. **PassRoleForEC2** (Critical)
- `iam:PassRole` - Pass instance profile to new EC2 instances

**Why Critical:** When launching a new spot instance (especially EKS worker nodes), the optimizer must attach the same IAM instance profile as the original instance. Without this, new nodes will launch without permissions and fail to join the cluster.

**Example Failure:**
```
Error: Not authorized to perform iam:PassRole on resource: arn:aws:iam::123456789012:role/EKS-WorkerNode-Role
```

---

#### 6. **ServiceLinkedRole**
- `iam:CreateServiceLinkedRole` - Create AWS Spot service-linked role

**Why Required:** The first time you use Spot instances in an account, AWS requires a service-linked role. This permission allows Spot Optimizer to create it automatically.

---

#### 7. **PricingAndCost** (Read-Only)
- `pricing:GetProducts` - Retrieve on-demand and spot pricing
- `ce:GetCostAndUsage` - Calculate actual spend

**Used by:** Savings calculator, dashboard cost metrics

---

## 🚨 Common Permission Errors

### Error 1: `iam:PassRole` Denied
**Symptom:** Instances launch but fail immediately
**Solution:** Add the `PassRoleForEC2Instances` statement

### Error 2: Spot Requests Fail
**Symptom:** `User is not authorized to use service-linked role`
**Solution:** Add the `ServiceLinkedRole` statement

### Error 3: Discovery Incomplete
**Symptom:** Dashboard shows 0 instances despite having EC2 resources
**Solution:** Ensure `ec2:Describe*` permissions are present

---

## 🔒 Security Best Practices

### 1. Use Least Privilege (Not Recommended for Prod)
While the above policy uses `Resource: "*"` for simplicity, you can restrict it:

```json
{
  "Sid": "RestrictedEC2Actions",
  "Effect": "Allow",
  "Action": ["ec2:RunInstances", "ec2:TerminateInstances"],
  "Resource": [
    "arn:aws:ec2:*:*:instance/*",
    "arn:aws:ec2:*:*:volume/*",
    "arn:aws:ec2:*:*:network-interface/*"
  ],
  "Condition": {
    "StringEquals": {
      "ec2:ResourceTag/ManagedBy": "SpotOptimizer"
    }
  }
}
```

### 2. Rotate Credentials Regularly
- Rotate Access Keys every 90 days
- Use AWS Secrets Manager for automated rotation

### 3. Enable CloudTrail
- Monitor all API calls made by the IAM user
- Set up alerts for suspicious activity

### 4. Use IAM Role Instead (Recommended)
For production workloads, prefer **CloudFormation-based IAM Role** connection method over access keys.

---

## 🏗️ Multi-Account Architecture (Future)

For managing multiple AWS accounts:

1. **Option A:** Create separate IAM users in each account
2. **Option B:** Use IAM Roles with cross-account trust (recommended)
   - Create role in Account B: `SpotOptimizerRole`
   - Trust policy allows Account A to assume it
   - Main credentials in Account A can assume roles in B, C, D...

---

## 📞 Support

If you encounter permission errors:
1. Check CloudTrail logs for the specific denied action
2. Add the missing permission to the policy
3. Test in Lab mode first before enabling in production

---

## 📜 Change Log

- **2025-12-23:** Initial comprehensive policy created
- Added EKS support permissions
- Added CloudWatch metrics for Lab mode
- Clarified iam:PassRole critical requirement
