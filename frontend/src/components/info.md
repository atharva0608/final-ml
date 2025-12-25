# Frontend Components Module

## Purpose

Reusable React components for the application UI with complete button/function documentation.

**Last Updated**: 2025-12-25 (Enhanced with comprehensive button/API mappings)
**Authority Level**: HIGH

---

## 1. ClientSetup.jsx ⭐ PRIMARY ONBOARDING COMPONENT

**Purpose**: AWS account connection wizard and account management
**Lines**: ~945
**Route**: `/onboarding/setup`
**Status**: ACTIVE DEVELOPMENT

### Component Structure

```
ClientSetup
├─ Account List View (if connected accounts exist)
│  ├─ Connected Accounts Table
│  ├─ Add Account Button
│  └─ Disconnect Buttons
│
└─ Onboarding Flow (if showOnboarding=true)
   ├─ Connection Method Selection
   ├─ CloudFormation Flow (4 steps)
   └─ Credentials Flow (3 steps)
```

---

### 🔘 BUTTONS & FUNCTIONS

#### Button: "Add Account"
**Location**: Line ~346
**OnClick**: `handleAddAccount`
**Purpose**: Show onboarding flow to add new AWS account
**State Changes**:
```javascript
setShowOnboarding(true)
setConnectionMethod('cloudformation')
setCurrentStep(1)
```
**API Calls**: None (UI only)
**Database**: None

---

#### Button: "Disconnect" (for each account)
**Location**: Line ~406
**OnClick**: `handleDisconnect(account.id)`
**Purpose**: Remove AWS account connection
**Function**: `handleDisconnect` (line ~270)

**Complete Flow**:
```javascript
1. User clicks "Disconnect" on account card
   ↓
2. Confirmation dialog: "Are you sure you want to disconnect..."
   ↓
3. If confirmed:
   → API: DELETE /client/accounts/{account_id}
   → Backend deletes from `accounts` table
   → Backend cascades to `instances` table
   → Backend cascades to `experiment_logs` table
   ↓
4. Success:
   → Shows alert: "AWS account disconnected successfully"
   → Calls checkConnectedAccounts() to refresh list
   ↓
5. Error:
   → Shows alert with error message
```

**API Endpoint**: `DELETE /client/accounts/{account_id}`
**Backend File**: `backend/api/client_routes.py:84-143`
**Database Tables**:
- `accounts` (DELETE WHERE id = account_id AND user_id = current_user.id)
- `instances` (CASCADE DELETE)
- `experiment_logs` (CASCADE DELETE via FK)

**Response**:
```json
{
  "success": true,
  "message": "AWS account disconnected successfully",
  "account_id": "123456789012"
}
```

**Error Handling**:
- 404: Account not found
- 403: Not owned by current user
- Network error: Connection failed

---

#### Button: "Start CloudFormation Setup"
**Location**: Line ~468
**OnClick**: Sets `connectionMethod='cloudformation'`, advances to step 1
**Function**: `createOnboardingRequest` (line ~38)

**Complete Flow**:
```javascript
1. User clicks "Start CloudFormation Setup"
   ↓
2. createOnboardingRequest() called
   → API: POST /client/onboarding/create
   → Backend creates pending account record
   → Backend generates secure external_id (UUID)
   ↓
3. Response received:
   {
     "id": "pending-abc123",
     "external_id": "random-uuid",
     "status": "pending"
   }
   ↓
4. State updated:
   → setAccountId("pending-abc123")
   → setExternalId("random-uuid")
   → setCurrentStep(2)
   ↓
5. UI advances to "Download CloudFormation Template" step
```

**API Endpoint**: `POST /client/onboarding/create`
**Backend File**: `backend/api/onboarding_routes.py:40-92`
**Database Tables**:
- `accounts` (INSERT with status='pending', account_id='pending-{random}')

---

#### Button: "Download CloudFormation Template"
**Location**: Line ~779
**OnClick**: `downloadTemplate()`
**Function**: `downloadTemplate` (line ~54)

**Complete Flow**:
```javascript
1. User clicks "Download CloudFormation Template"
   ↓
2. downloadTemplate() called
   → API: GET /client/onboarding/template/{accountId}
   → Backend generates CloudFormation JSON template
   → Template includes:
     - IAM Role with AssumeRole trust policy
     - ExternalId from previous step
     - EC2 permissions (Describe*, Stop, Start, Modify)
     - CloudWatch permissions (GetMetricStatistics)
   ↓
3. Response received:
   {
     "template": { CloudFormation JSON }
   }
   ↓
4. Creates blob and triggers browser download:
   → Filename: "spot-optimizer-role.json"
   → Content: CloudFormation template
   ↓
5. State updated:
   → setCurrentStep(3)
   ↓
6. UI shows instructions to deploy in AWS Console
```

**API Endpoint**: `GET /client/onboarding/template/{account_id}`
**Backend File**: `backend/api/onboarding_routes.py:274-451`
**Database Tables**: `accounts` (READ to get external_id)

**CloudFormation Template Structure**:
```json
{
  "AWSTemplateFormatVersion": "2010-09-09",
  "Resources": {
    "SpotOptimizerRole": {
      "Type": "AWS::IAM::Role",
      "Properties": {
        "AssumeRolePolicyDocument": {
          "Statement": [{
            "Effect": "Allow",
            "Principal": {"AWS": "arn:aws:iam::PLATFORM_ACCOUNT:root"},
            "Action": "sts:AssumeRole",
            "Condition": {
              "StringEquals": {"sts:ExternalId": "UNIQUE_EXTERNAL_ID"}
            }
          }]
        },
        "Policies": [{
          "PolicyName": "SpotOptimizerAccess",
          "PolicyDocument": {
            "Statement": [
              {"Effect": "Allow", "Action": ["ec2:Describe*"], "Resource": "*"},
              {"Effect": "Allow", "Action": ["ec2:StopInstances", "ec2:StartInstances"], "Resource": "*"},
              {"Effect": "Allow", "Action": ["cloudwatch:GetMetricStatistics"], "Resource": "*"}
            ]
          }
        }]
      }
    }
  },
  "Outputs": {
    "RoleARN": {
      "Description": "Role ARN to paste in the platform",
      "Value": {"Fn::GetAtt": ["SpotOptimizerRole", "Arn"]}
    }
  }
}
```

---

#### Button: "Verify Connection"
**Location**: Line ~833
**OnClick**: `verifyConnection()`
**Function**: `verifyConnection` (line ~84)

**Complete Flow**:
```javascript
1. User enters Role ARN from AWS CloudFormation outputs
   → roleArn = "arn:aws:iam::123456789012:role/SpotOptimizerRole"
   ↓
2. User clicks "Verify Connection"
   ↓
3. verifyConnection() called
   → Validates roleArn is not empty
   → setVerificationStatus('checking')
   → setVerificationMessage('Verifying connection...')
   ↓
4. API call:
   → API: POST /client/onboarding/{accountId}/verify
   → Request: { "role_arn": "arn:aws:iam::..." }
   → Backend calls AWS STS AssumeRole with external_id
   → Backend extracts real AWS Account ID from assumed role
   → Backend performs GLOBAL UNIQUENESS CHECK ⚠️ CRITICAL
   → If account_id already exists for different user → 409 Conflict
   → Backend updates `accounts` record:
     - account_id = real AWS account ID (e.g., "123456789012")
     - role_arn = provided role ARN
     - status = 'connected'
   → Backend triggers discovery_worker in background
   ↓
5. Success Response:
   {
     "status": "connected",
     "account_id": "123456789012",
     "message": "Connection verified successfully"
   }
   ↓
6. State updated:
   → setVerificationStatus('connected')
   → setVerificationMessage('✅ Connected! Discovering resources...')
   → setCurrentStep(4)
   → startPollingAccountStatus() initiated
   ↓
7. Discovery worker runs in background:
   → Discovers EC2 instances in all regions
   → Creates records in `instances` table
   → Updates account status: 'connected' → 'active'
   → Triggers health checks
   ↓
8. Polling detects status='active':
   → Shows "✅ Account fully activated!"
   → Auto-redirect to /client dashboard (via AuthGateway)
```

**API Endpoint**: `POST /client/onboarding/{account_id}/verify`
**Backend File**: `backend/api/onboarding_routes.py:453-587`
**Database Tables**:
- `accounts` (UPDATE SET account_id, role_arn, status='connected')
- Background: `instances` (INSERT discovered instances)

**Security**:
- ⚠️ **PROTECTED ZONE**: Global uniqueness check prevents account takeover
- ExternalID prevents confused deputy attack
- Ownership verification (user_id matches)

**Error Handling**:
- Role ARN empty → Alert
- AssumeRole fails → "Failed to assume role. Check the Role ARN and ExternalID"
- Account already connected to different user → HTTP 409: "Account already connected"
- Network error → Connection failed message

**Reference**:
- `/progress/regression_guard.md#2` - Protected zone
- `/progress/fixed_issues_log.md#P-2025-12-25-001` - Security fix

---

#### Button: "Check Discovery Status"
**Location**: Line ~877
**OnClick**: `checkDiscoveryStatus()`
**Function**: `checkDiscoveryStatus` (line ~169)

**Complete Flow**:
```javascript
1. User clicks "Check Discovery Status"
   ↓
2. checkDiscoveryStatus() called
   → API: GET /client/onboarding/{accountId}/discovery
   → Backend queries `accounts` table for status
   → Backend counts instances discovered
   ↓
3. Response:
   {
     "status": "active",
     "instances_discovered": 23,
     "discovery_progress": 100,
     "message": "Discovery complete"
   }
   ↓
4. State updated:
   → setDiscoveryStatus(response)
   → Shows progress/completion message
```

**API Endpoint**: `GET /client/onboarding/{account_id}/discovery`
**Backend File**: `backend/api/onboarding_routes.py:589-680`
**Database Tables**:
- `accounts` (READ status)
- `instances` (COUNT)

---

#### Button: "Connect with Access Keys"
**Location**: Line ~689
**OnClick**: `connectWithAccessKeys()`
**Function**: `connectWithAccessKeys` (line ~126)

**Complete Flow**:
```javascript
1. User enters:
   → Account Name: "Production AWS"
   → AWS Access Key ID: "AKIAIOSFODNN7EXAMPLE"
   → AWS Secret Access Key: "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
   → Region: "us-east-1"
   ↓
2. User clicks "Connect with Access Keys"
   ↓
3. connectWithAccessKeys() called
   → Validates all fields are filled
   ↓
4. API call:
   → API: POST /client/onboarding/connect/credentials
   → Request: {
       "account_name": "Production AWS",
       "aws_access_key_id": "AKIA...",
       "aws_secret_access_key": "wJal...",
       "region": "us-east-1"
     }
   → Backend calls AWS STS GetCallerIdentity to verify credentials
   → Backend extracts real AWS Account ID
   → Backend performs GLOBAL UNIQUENESS CHECK ⚠️ CRITICAL
   → Backend ENCRYPTS credentials with AES-256 (Fernet)
   → Backend creates `accounts` record:
     - account_id = real AWS account ID
     - aws_access_key_id = encrypted
     - aws_secret_access_key = encrypted
     - connection_method = 'access_keys'
     - status = 'connected'
   → Backend triggers discovery_worker in background
   ↓
5. Success Response:
   {
     "account_id": "123456789012",
     "status": "connected",
     "message": "AWS account connected successfully"
   }
   ↓
6. State updated:
   → setVerificationMessage('✅ Connected! Discovering resources...')
   → startPollingAccountStatus() initiated
   ↓
7. Same discovery flow as CloudFormation method
```

**API Endpoint**: `POST /client/onboarding/connect/credentials`
**Backend File**: `backend/api/onboarding_routes.py:94-272`
**Database Tables**:
- `accounts` (INSERT with encrypted credentials)
- Background: `instances` (INSERT discovered instances)

**Security**:
- ⚠️ **PROTECTED ZONE**: Global uniqueness check
- Credentials encrypted with AES-256 before storage
- Decrypted only when needed for AWS API calls

**Reference**: `/progress/regression_guard.md#2`, `/backend/utils/crypto.py`

---

#### Function: `startPollingAccountStatus()` (AUTOMATIC)
**Location**: Line ~162
**Trigger**: After connection success (CloudFormation or Credentials)
**Purpose**: Poll account status every 3 seconds until discovery complete

**Complete Flow**:
```javascript
1. Called automatically after account status='connected'
   ↓
2. Clear any existing polling interval
   ↓
3. Start new interval (3000ms = 3 seconds):
   → API: GET /client/accounts
   → Filter to find current account
   → Check status
   ↓
4. If status='active':
   → Discovery complete!
   → clearInterval(intervalId)
   → setVerificationMessage('✅ Account fully activated!')
   → Stop polling
   ↓
5. If status='connected':
   → Still discovering...
   → setVerificationMessage('🔄 Discovering resources... (Xs elapsed)')
   → Continue polling
   ↓
6. Max attempts: 60 (60 × 3 seconds = 3 minutes timeout)
   ↓
7. Cleanup on component unmount:
   → useEffect cleanup clears interval
   → Prevents memory leaks
```

**API Endpoint**: `GET /client/accounts`
**Backend File**: `backend/api/client_routes.py:41-81`
**Database Tables**: `accounts` (READ)

**Frontend Code** (line ~162-220):
```javascript
const startPollingAccountStatus = () => {
  if (pollingIntervalId) clearInterval(pollingIntervalId);

  let attempts = 0;
  const maxAttempts = 60; // 3 minutes

  const intervalId = setInterval(async () => {
    attempts++;
    try {
      const response = await api.get('/client/accounts');
      if (response.data && response.data.length > 0) {
        const account = response.data[0];
        if (account.status === 'active') {
          clearInterval(intervalId);
          setPollingIntervalId(null);
          setVerificationMessage(`✅ Account fully activated!`);
        } else if (account.status === 'connected') {
          setVerificationMessage(`🔄 Discovering resources... (${attempts * 3}s elapsed)`);
        }
      }
    } catch (error) {
      console.error('Polling error:', error);
    }

    if (attempts >= maxAttempts) {
      clearInterval(intervalId);
      setPollingIntervalId(null);
    }
  }, 3000); // Poll every 3 seconds

  setPollingIntervalId(intervalId);
};
```

**Cleanup** (line ~311-317):
```javascript
useEffect(() => {
  return () => {
    if (pollingIntervalId) {
      clearInterval(pollingIntervalId);
    }
  };
}, [pollingIntervalId]);
```

**Recent Enhancement**: 2025-12-25
**Reference**: `/progress/fixed_issues_log.md#P-2025-12-25-002`

---

#### Function: `checkConnectedAccounts()` (AUTOMATIC)
**Location**: Line ~235
**Trigger**: On component mount
**Purpose**: Load existing connected accounts

**API Endpoint**: `GET /client/accounts`
**Backend File**: `backend/api/client_routes.py:41-81`
**Database Tables**: `accounts` (WHERE user_id = current_user.id)

---

### State Variables

```javascript
// Account list
const [connectedAccounts, setConnectedAccounts] = useState([])
const [isLoadingAccounts, setIsLoadingAccounts] = useState(true)

// Onboarding flow
const [showOnboarding, setShowOnboarding] = useState(false)
const [connectionMethod, setConnectionMethod] = useState('cloudformation')
const [currentStep, setCurrentStep] = useState(1)

// CloudFormation method
const [accountId, setAccountId] = useState(null) // "pending-abc123"
const [externalId, setExternalId] = useState('') // UUID
const [roleArn, setRoleArn] = useState('') // User input

// Credentials method
const [accessKey, setAccessKey] = useState('')
const [secretKey, setSecretKey] = useState('')
const [region, setRegion] = useState('us-east-1')

// Status tracking
const [verificationStatus, setVerificationStatus] = useState('pending')
const [verificationMessage, setVerificationMessage] = useState('')
const [pollingIntervalId, setPollingIntervalId] = useState(null)
```

---

### Dependencies

**Imports**:
```javascript
import { useState, useEffect } from 'react';
import { Cloud, Copy, CheckCircle, XCircle, Download, RefreshCw, Server } from 'lucide-react';
import api from '../services/api';
```

**API Service** (`services/api.js`):
- `api.createOnboardingRequest()` → POST /client/onboarding/create
- `api.getOnboardingTemplate(id)` → GET /client/onboarding/template/{id}
- `api.verifyOnboarding(id, roleArn)` → POST /client/onboarding/{id}/verify
- `api.connectWithCredentials(data)` → POST /client/onboarding/connect/credentials
- `api.get('/client/accounts')` → GET /client/accounts
- `api.delete(\`/client/accounts/${id}\`)` → DELETE /client/accounts/{id}

**Backend Files**:
- `backend/api/onboarding_routes.py` (main logic)
- `backend/api/client_routes.py` (account management)
- `backend/workers/discovery_worker.py` (background discovery)
- `backend/utils/crypto.py` (credential encryption)

**Database Tables**:
- `accounts` (primary)
- `instances` (discovered resources)
- `experiment_logs` (cascade delete)

---

### UI Sections

**Account List View** (lines ~332-438):
- Table showing connected accounts
- Columns: Account Name, AWS ID, Region, Status, Instances, Actions
- Status badges with colors
- Disconnect button per row
- "Add Account" button

**Connection Method Selection** (lines ~448-530):
- Toggle between CloudFormation and Credentials
- Description of each method
- "Start" buttons for each

**CloudFormation Flow** (lines ~532-888):
- Step 1: Create onboarding request
- Step 2: Download template
- Step 3: Deploy in AWS (external)
- Step 4: Enter Role ARN and verify
- Step 5: Discovery status polling

**Credentials Flow** (lines ~648-723):
- Form for access keys
- Region selector
- "Connect" button

---

## 2. AuthGateway.jsx ⭐ SMART ROUTING

**Purpose**: Automatic routing based on account connection status
**Lines**: ~48
**Route**: Wrapper component (used in App.jsx routing)
**Created**: 2025-12-25

### Component Logic

```javascript
useEffect(() => {
  const checkAccounts = async () => {
    try {
      const res = await api.get('/client/accounts');

      if (res.data && res.data.length > 0) {
        // Has accounts → ensure not on setup page
        if (window.location.pathname === '/onboarding/setup') {
          navigate('/client');
        }
      } else {
        // No accounts → ensure on setup page
        if (window.location.pathname !== '/onboarding/setup') {
          navigate('/onboarding/setup');
        }
      }
    } catch (err) {
      console.error("Auth check failed", err);
    } finally {
      setLoading(false);
    }
  };

  checkAccounts();
}, [navigate]);
```

### Routing Logic

```
User navigates to /client
   ↓
AuthGateway mounts
   ↓
API: GET /client/accounts
   ↓
   ├─ accounts.length > 0
   │    ↓
   │  Allow access to /client (render children)
   │
   └─ accounts.length === 0
        ↓
      Redirect to /onboarding/setup
```

**API Endpoint**: `GET /client/accounts`
**Backend File**: `backend/api/client_routes.py:41-81`
**Database Tables**: `accounts`

**Usage in App.jsx**:
```javascript
<Route path="/client" element={
  <AuthGateway>
    <ClientDashboard />
  </AuthGateway>
} />
```

---

## 3. LoginPage.jsx - AUTHENTICATION

**Purpose**: User login and registration
**Lines**: ~202
**Route**: `/login`

### 🔘 BUTTONS & FUNCTIONS

#### Button: "Sign In" / "Sign Up" (Toggle)
**Location**: Lines ~97-110
**OnClick**: Toggles `isLogin` state
**Purpose**: Switch between login and signup forms

#### Button: "Login" / "Register" (Submit)
**Location**: Line ~177
**Type**: `submit`
**OnSubmit**: `handleSubmit` (line ~18)

**Login Flow**:
```javascript
1. User enters username and password
   ↓
2. Clicks "Login" button (form submit)
   ↓
3. handleSubmit() called
   → Prevents default form submission
   → setError('')
   → setLoading(true)
   ↓
4. API call (if isLogin=true):
   → API: POST /auth/login
   → Request: { username, password } (OAuth2PasswordRequestForm)
   → Backend verifies password with bcrypt
   → Backend generates JWT token (24-hour expiration)
   ↓
5. Success Response:
   {
     "access_token": "eyJhbGc...",
     "token_type": "bearer",
     "user": {
       "id": "uuid",
       "username": "user@example.com",
       "email": "user@example.com",
       "role": "client"
     }
   }
   ↓
6. AuthContext updated:
   → Stores token in localStorage
   → Sets user state
   ↓
7. Navigation:
   → if (user.role === 'client') → AuthGateway logic
   → if (user.role === 'admin') → /admin
```

**API Endpoint**: `POST /auth/login`
**Backend File**: `backend/api/auth.py`
**Database Tables**: `users` (SELECT WHERE username = ? OR email = ?)

**Security**:
- Password never sent in plaintext (bcrypt verification on backend)
- JWT token with 24-hour expiration ⚠️ PROTECTED
- Token stored in localStorage (consider HTTP-only cookie for production)

---

## 4. Other Components (Summary)

### NodeFleet.jsx
**Purpose**: EC2 instance fleet visualization
**Lines**: ~811
**Key Features**: Instance cards, filters, optimization recommendations

### ClientManagement.jsx
**Purpose**: Admin client management
**Lines**: ~431
**Requires**: Admin role

### LiveOperations.jsx
**Purpose**: Real-time operation feed
**Lines**: ~271
**Features**: WebSocket updates, operation status

### Controls.jsx
**Purpose**: System control panel
**Lines**: ~238
**Features**: Manual operations, settings

### ErrorBoundary.jsx
**Purpose**: React error boundary
**Lines**: ~36
**Usage**: Catches component errors

### InstanceFlowAnimation.jsx
**Purpose**: Instance state flow visualization
**Lines**: ~528
**Features**: Animated state transitions

---

## Component Dependency Map

```
App.jsx
├─ AuthGateway (checks accounts)
│  ├─ API: GET /client/accounts
│  └─ DB: accounts table
│
├─ LoginPage
│  ├─ API: POST /auth/login
│  └─ DB: users table
│
├─ ClientSetup
│  ├─ API: POST /client/onboarding/*
│  ├─ API: GET /client/accounts
│  ├─ API: DELETE /client/accounts/{id}
│  ├─ DB: accounts, instances
│  └─ Worker: discovery_worker.py
│
└─ ClientDashboard (wrapped in AuthGateway)
   ├─ API: GET /client/dashboard
   ├─ DB: accounts, instances, experiment_logs
   └─ Components: NodeFleet, LiveOperations, etc.
```

---

## Recent Changes

### 2025-12-25: Comprehensive Enhancement
**Reason**: Document all buttons, functions, API connections, database operations
**Impact**: Complete component documentation for frontend-to-backend flow
**Reference**: Smart repository enhancement

### 2025-12-25: Multi-Account Features
**Files Changed**: ClientSetup.jsx, AuthGateway.jsx (new)
**Features Added**:
- Account list view with disconnect
- Live status polling (3-second intervals)
- Smart routing based on account status
**Reference**: `/progress/fixed_issues_log.md`

---

_Last Updated: 2025-12-25 (Comprehensive Enhancement)_
_Authority: HIGH - Complete frontend component reference_
