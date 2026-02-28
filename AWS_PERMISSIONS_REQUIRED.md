# AWS IAM Permissions Required

## CLIENT SIDE Permissions (Cross-Account Assume Role)

These permissions are added to the CloudFormation template that clients deploy. The role created by the template allows the platform to assume it and access client resources.

### EC2 Permissions (Required)
```json
{
  "Effect": "Allow",
  "Action": [
    "ec2:DescribeInstances",
    "ec2:DescribeInstanceTypes",
    "ec2:DescribeInstanceStatus",
    "ec2:DescribeRegions",
    "ec2:DescribeAvailabilityZones",
    "ec2:DescribeVpcs",
    "ec2:DescribeSubnets",
    "ec2:DescribeSecurityGroups",
    "ec2:DescribeVolumes",
    "ec2:DescribeSnapshots",
    "ec2:DescribeImages",
    "ec2:DescribeKeyPairs",
    "ec2:DescribeTags",
    "ec2:DescribeSpotInstanceRequests",
    "ec2:DescribeReservedInstances",
    "ec2:RunInstances",
    "ec2:TerminateInstances",
    "ec2:StopInstances",
    "ec2:StartInstances",
    "ec2:ModifyInstanceAttribute",
    "ec2:CreateTags",
    "ec2:DeleteTags"
  ],
  "Resource": "*"
}
```

### EKS Permissions (Required for Kubernetes clusters)
```json
{
  "Effect": "Allow",
  "Action": [
    "eks:DescribeCluster",
    "eks:ListClusters",
    "eks:DescribeNodegroup",
    "eks:ListNodegroups",
    "eks:DescribeUpdate",
    "eks:ListUpdates",
    "eks:DescribeFargateProfile",
    "eks:ListFargateProfiles",
    "eks:AccessKubernetesApi"
  ],
  "Resource": "*"
}
```

### Auto Scaling Permissions (Required)
```json
{
  "Effect": "Allow",
  "Action": [
    "autoscaling:DescribeAutoScalingGroups",
    "autoscaling:DescribeAutoScalingInstances",
    "autoscaling:DescribeLaunchConfigurations",
    "autoscaling:DescribeScalingActivities",
    "autoscaling:DescribeTags",
    "autoscaling:UpdateAutoScalingGroup",
    "autoscaling:SetDesiredCapacity",
    "autoscaling:TerminateInstanceInAutoScalingGroup"
  ],
  "Resource": "*"
}
```

### CloudWatch Permissions (Required for metrics)
```json
{
  "Effect": "Allow",
  "Action": [
    "cloudwatch:GetMetricStatistics",
    "cloudwatch:ListMetrics",
    "cloudwatch:GetMetricData"
  ],
  "Resource": "*"
}
```

### IAM Permissions (Read-only, for validation)
```json
{
  "Effect": "Allow",
  "Action": [
    "iam:GetRole",
    "iam:GetInstanceProfile",
    "iam:ListAttachedRolePolicies"
  ],
  "Resource": "*"
}
```

### STS Permissions (Required)
```json
{
  "Effect": "Allow",
  "Action": [
    "sts:GetCallerIdentity"
  ],
  "Resource": "*"
}
```

### Cost Explorer Permissions (Optional, for cost tracking)
```json
{
  "Effect": "Allow",
  "Action": [
    "ce:GetCostAndUsage",
    "ce:GetCostForecast",
    "ce:GetReservationUtilization",
    "ce:GetSavingsPlansUtilization"
  ],
  "Resource": "*"
}
```

---

## PLATFORM SIDE Permissions (Platform AWS Account)

These are the permissions needed by the **platform's own IAM user/role** (not the client's assume role). The platform uses these credentials to fetch global AWS pricing data and instance catalog information.

### Pricing API Permissions (Required - Global Data)
```json
{
  "Effect": "Allow",
  "Action": [
    "pricing:GetProducts",
    "pricing:DescribeServices",
    "pricing:GetAttributeValues"
  ],
  "Resource": "*"
}
```

### EC2 Pricing Permissions (Required - Spot Price History)
```json
{
  "Effect": "Allow",
  "Action": [
    "ec2:DescribeSpotPriceHistory",
    "ec2:DescribeInstanceTypes",
    "ec2:DescribeInstanceTypeOfferings",
    "ec2:DescribeRegions",
    "ec2:DescribeAvailabilityZones"
  ],
  "Resource": "*"
}
```

### Service Quotas (Optional - for capacity planning)
```json
{
  "Effect": "Allow",
  "Action": [
    "servicequotas:GetServiceQuota",
    "servicequotas:ListServiceQuotas"
  ],
  "Resource": "*"
}
```

### STS (Required)
```json
{
  "Effect": "Allow",
  "Action": [
    "sts:GetCallerIdentity",
    "sts:AssumeRole"
  ],
  "Resource": "*"
}
```

---

## Trust Relationship for Client Role

The client's assume role must trust the platform account:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "AWS": "arn:aws:iam::<PLATFORM_ACCOUNT_ID>:root"
      },
      "Action": "sts:AssumeRole",
      "Condition": {
        "StringEquals": {
          "sts:ExternalId": "<UNIQUE_EXTERNAL_ID>"
        }
      }
    }
  ]
}
```

---

## Summary

| Scope | Who Uses | Purpose |
|-------|----------|---------|
| **Client Permissions** | Platform assumes client role | Access client's AWS resources (EC2, EKS, ASG, etc.) |
| **Platform Permissions** | Platform's own credentials | Fetch global AWS pricing data, spot price history, instance catalog |

The separation ensures:
- Platform credentials are **never exposed** to clients
- Client credentials are **never stored** in platform (only assume role ARN + external ID)
- Platform can fetch pricing data **independently** without client credentials
