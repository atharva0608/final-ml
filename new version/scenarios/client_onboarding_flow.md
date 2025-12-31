# Client Onboarding Flow

## Purpose

Complete AWS account connection workflow for both CloudFormation and Credentials methods.

**Last Updated**: 2025-12-25

---

## User Story

As a client user, I want to connect my AWS account so that the system can discover and optimize my EC2 instances.

---

## Prerequisites

- User has logged in as role: `client`
- User has AWS account with EC2 instances (or empty account for testing)
- User has either:
  - AWS Access Key + Secret Key, OR
  - Ability to create CloudFormation stack

---

## Connection Methods

### Method 1: CloudFormation (IAM Role) - RECOMMENDED

**Pros**:
- More secure (no long-lived credentials)
- Follows AWS best practices
- External ID adds extra security layer

**Cons**:
- Requires CloudFormation stack creation
- More steps for user

### Method 2: Access Keys (Credentials) - FASTER

**Pros**:
- Faster onboarding (no CloudFormation)
- Direct validation

**Cons**:
- Long-lived credentials stored
- Must be rotated periodically

---

## Flow: CloudFormation Method

### Step 1: Create Onboarding Request

```
User clicks "Connect AWS Account"
   ↓
Selects "CloudFormation" tab
   ↓
Frontend calls POST /onboarding/create
   ↓
Backend generates:
   - Unique External ID: "spot-optimizer-{uuid}"
   - Placeholder account record (status: pending)
   ↓
Returns:
   {
     "id": "account-uuid",
     "external_id": "spot-optimizer-abc123",
     "status": "pending_setup"
   }
```

**Backend Implementation**: `backend/api/onboarding_routes.py:41`

### Step 2: Generate CloudFormation Template

```
Frontend calls GET /onboarding/template/{account_id}
   ↓
Backend generates CloudFormation template
   - IAM Role with trust policy
   - External ID: {from step 1}
   - Permissions: EC2, CloudWatch, Pricing
   ↓
Returns template JSON
   ↓
Frontend displays:
   - Copy button for template
   - Instructions for AWS Console
```

**Backend Implementation**: `backend/api/onboarding_routes.py:274`

**Template Structure**:
```json
{
  "AWSTemplateFormatVersion": "2010-09-09",
  "Resources": {
    "SpotOptimizerRole": {
      "Type": "AWS::IAM::Role",
      "Properties": {
        "RoleName": "SpotOptimizerCrossAccountRole",
        "AssumeRolePolicyDocument": {
          "Statement": [{
            "Effect": "Allow",
            "Principal": {"AWS": "arn:aws:iam::OUR_ACCOUNT:root"},
            "Action": "sts:AssumeRole",
            "Condition": {
              "StringEquals": {
                "sts:ExternalId": "spot-optimizer-abc123"
              }
            }
          }]
        },
        "Policies": [...]
      }
    }
  }
}
```

### Step 3: User Creates CloudFormation Stack

```
User opens AWS Console
   ↓
Navigates to CloudFormation
   ↓
Creates new stack
   ↓
Uploads template (from step 2)
   ↓
Stack creation completes
   ↓
User copies Role ARN from Outputs tab
   Example: arn:aws:iam::123456789012:role/SpotOptimizerCrossAccountRole
```

**User Action**: External to our system

### Step 4: Verify Connection

```
User pastes Role ARN into frontend
   ↓
Frontend calls POST /onboarding/{account_id}/verify
   {
     "role_arn": "arn:aws:iam::123456789012:role/SpotOptimizerCrossAccountRole"
   }
   ↓
Backend assumes role using STS
   - RoleArn: {from request}
   - ExternalId: {from step 1}
   ↓
If successful:
   - Get AWS Account ID from assumed credentials
   - Check global uniqueness (P-2025-12-25-001 fix)
   - Update account record:
     * account_id: {real AWS account ID}
     * role_arn: {from request}
     * connection_method: "iam_role"
     * status: "connected"
   - Trigger discovery worker (background)
   ↓
Return success:
   {
     "status": "connected",
     "aws_account_id": "123456789012",
     "message": "Credentials verified! Scanning resources..."
   }
```

**Backend Implementation**: `backend/api/onboarding_routes.py:453`

**Security Check** (NEW: 2025-12-25):
```python
# Global uniqueness check
existing = db.query(Account).filter(
    Account.account_id == aws_account_id,
    Account.id != account.id
).first()

if existing and existing.user_id != current_user.id:
    raise HTTPException(409, "Account already connected to different user")
```

### Step 5: Resource Discovery (Background)

```
discovery_worker.run_initial_discovery() triggered
   ↓
Assume IAM role
   ↓
Call EC2 DescribeInstances API
   ↓
For each instance found:
   - Create or update Instance record
   - Extract tags for cluster identification
   - Set auth_status (authorized/unauthorized)
   ↓
Update account status: "active"
   ↓
Trigger health checks (P-2025-12-25-002 fix)
   ↓
Discovery complete
```

**Backend Implementation**: `backend/workers/discovery_worker.py:229`

### Step 6: Frontend Polling

```
Frontend starts polling (every 3 seconds)
   ↓
GET /client/accounts
   ↓
Check account.status:
   - "connected" → Show "Discovering... ({elapsed}s)"
   - "active" → Show "Complete! Account activated"
   - "failed" → Show error message
   ↓
Stop polling when:
   - status === "active" (success)
   - attempts > 60 (3 minutes timeout)
```

**Frontend Implementation**: `frontend/src/components/ClientSetup.jsx:162`

---

## Flow: Credentials Method

### Step 1: User Enters Credentials

```
User selects "Access Keys" tab
   ↓
Enters:
   - Access Key ID
   - Secret Access Key
   - Region (default: us-east-1)
   ↓
Clicks "Connect"
```

### Step 2: Validate Credentials

```
Frontend calls POST /onboarding/connect/credentials
   {
     "access_key": "AKIAIOSFODNN7EXAMPLE",
     "secret_key": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
     "region": "us-east-1"
   }
   ↓
Backend validates with AWS STS GetCallerIdentity
   ↓
If successful:
   - Get AWS Account ID
   - Encrypt credentials (AES-256)
   - Check global uniqueness (P-2025-12-25-001 fix)
   - UPSERT account record:
     * If exists for this user → update
     * If new → create
     * If exists for OTHER user → HTTP 409
   - Set status: "connected"
   - Trigger discovery worker
   ↓
Return success
```

**Backend Implementation**: `backend/api/onboarding_routes.py:94`

**UPSERT Logic**:
```python
# Check global uniqueness first
global_existing = db.query(Account).filter(
    Account.account_id == aws_account_id
).first()

if global_existing:
    if global_existing.user_id != current_user.id:
        # Security: Prevent takeover
        raise HTTPException(409, "Account belongs to different user")

    # Re-connection: Update existing
    account = global_existing
    account.aws_access_key_id = encrypted_access_key
    account.aws_secret_access_key = encrypted_secret_key
    account.status = "connected"
else:
    # Check for pending placeholder
    pending = db.query(Account).filter(
        Account.user_id == current_user.id,
        Account.account_id.like('pending-%')
    ).first()

    if pending:
        # Upgrade placeholder
        pending.account_id = aws_account_id
        pending.aws_access_key_id = encrypted_access_key
        # ...
    else:
        # Create new
        account = Account(...)
        db.add(account)
```

### Step 3-6: Same as CloudFormation

Discovery worker, polling, and completion are identical.

---

## Empty States & Edge Cases

### No AWS Instances Found

```
Discovery completes
   ↓
account.status = "active"
BUT instance count = 0
   ↓
Dashboard shows:
   - "0 Instances Discovered"
   - "Add instances to your AWS account to begin optimization"
   - Still shows account as "Connected"
```

**Behavior**: Not an error, just empty data

### Discovery Failure

```
Discovery worker encounters error
   (e.g., invalid permissions, network failure)
   ↓
account.status = "failed"
   account.account_metadata = {
     "last_error": "AccessDenied: Missing ec2:DescribeInstances permission"
   }
   ↓
Frontend shows:
   - Error message
   - "Check IAM permissions" link
   - Option to retry
```

**Error Handling**: `backend/workers/discovery_worker.py:338`

### Duplicate AWS Account (Security)

```
User A: Connected AWS Account 123456789012
   ↓
User B: Attempts to connect same account
   ↓
Backend uniqueness check detects conflict
   ↓
HTTP 409 Conflict:
   {
     "detail": "AWS account 123456789012 is already connected to a different user."
   }
   ↓
Frontend shows:
   "This AWS account is already managed by another user in this system."
```

**Security Fix**: P-2025-12-25-001

---

## Testing Scenarios

### Test 1: CloudFormation Happy Path

1. Login as client
2. Click "Connect AWS Account"
3. Select CloudFormation tab
4. Copy template
5. Create stack in AWS
6. Copy Role ARN
7. Paste ARN and verify
8. Wait for discovery
9. Verify dashboard shows instances

### Test 2: Credentials Happy Path

1. Login as client
2. Click "Connect AWS Account"
3. Select "Access Keys" tab
4. Enter valid credentials
5. Click "Connect"
6. Wait for discovery
7. Verify dashboard shows instances

### Test 3: Invalid Credentials

1. Select "Access Keys" tab
2. Enter invalid secret key
3. Click "Connect"
4. Verify error: "Invalid AWS credentials"

### Test 4: Duplicate Account Prevention

1. User A connects AWS Account X
2. User B attempts to connect same account
3. Verify HTTP 409 error
4. Verify User B cannot access

### Test 5: Discovery Timeout

1. Connect account with slow network
2. Watch polling progress
3. Verify timeout after 3 minutes
4. Verify message: "Discovery taking longer than expected"

---

## Status Transitions

```
[Initial State]
   ↓
pending (CloudFormation only - after create request)
   ↓
connected (after credential validation)
   ↓
   ├─ active (discovery succeeded)
   └─ failed (discovery failed)
```

**Authority**: `/index/feature_index.md#resource-discovery`

---

## API Endpoints Summary

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/onboarding/create` | POST | Create onboarding request (CloudFormation) |
| `/onboarding/template/{id}` | GET | Get CloudFormation template |
| `/onboarding/{id}/verify` | POST | Verify IAM role connection |
| `/onboarding/connect/credentials` | POST | Connect with access keys |
| `/onboarding/{id}/discovery` | GET | Check discovery status |
| `/client/accounts` | GET | List connected accounts (for polling) |

---

## Known Issues

### None

Onboarding flows are stable as of 2025-12-25.

---

## Historical Issues (Fixed)

### P-2025-12-25-001: Account Takeover Vulnerability

CloudFormation flow lacked uniqueness check. Fixed by adding global check.

**Reference**: `/progress/fixed_issues_log.md#P-2025-12-25-001`

---

_Last Updated: 2025-12-25_
