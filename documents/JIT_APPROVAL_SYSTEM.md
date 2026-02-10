# Just-In-Time (JIT) Approval System

## Overview

Your application implements a **production-grade JIT Feature Escalation model** that enforces time-bound access control for sensitive operations. This system follows enterprise security best practices for privilege escalation and audit compliance.

## System Architecture

### 1. **Default-Deny Interception**

Every critical operation in the application is protected by the permission layer:

- **ProtectedButton Component**: Wraps sensitive actions with automatic permission checking
- **usePermission Hook**: Validates permissions in real-time before allowing actions
- **Permission API**: Backend validation ensures no bypass attempts succeed
- **Global Event System**: `governance:required` event triggers modal for access requests

### 2. **Feature Registry**

Centralized registry with 100+ protected features defined in `backend/core/feature_registry.py`:

```python
Feature(
    id="compute:terminate",
    name="Terminate Instances",
    category=FeatureCategory.COMPUTE,
    permission_slug="compute:terminate:any",
    requires_approval=True,
    max_duration_hours=4,
    default_duration_hours=1,
    min_approver_role="TEAM_LEAD",
    risk_level="HIGH",
    requires_reason=True,
    supports_resource_scope=True
)
```

**Key Features Registered:**
- **Compute Operations**: Terminate, Stop, Reboot, Scale instances
- **Storage Management**: Delete volumes, snapshots, modify EBS
- **Database Actions**: Stop/Delete RDS instances
- **Cloud Integration**: Connect/Disconnect AWS accounts
- **Hygiene Operations**: Execute cleanup actions
- **Governance Controls**: Hibernation, automation settings
- **Team Management**: Invite, promote, remove users
- **Security**: MFA, SSO, session management

### 3. **Approval Workflow**

#### **Request Flow (Members)**

1. Member clicks a protected button (e.g., "Terminate Instance")
2. System checks permission via `usePermission` hook
3. If denied, modal opens with feature details pre-filled
4. Member provides justification and requests duration (1-72 hours)
5. Request routed to appropriate approver (Team Lead or Org Admin)
6. Status: `PENDING`

#### **Approval Flow (Team Leads/Admins)**

1. Approver sees request in their queue
2. Reviews justification, duration, and risk level
3. Approves or rejects with one click
4. Upon approval:
   - Status changes to `APPROVED_ACTIVE`
   - `expires_at` timestamp calculated
   - User notified of active window
   - ActiveWindowBanner appears at top of UI

#### **Delegation Flow (Admins Only)**

1. Admin opens "Grant Access" modal
2. Selects multiple recipients from team list
3. Chooses access type:
   - **Full Access Window**: Time-bound permission for all actions
   - **Specific Action**: Permission for one specific resource operation
4. Sets duration and justification
5. Creates parent approval + child approvals for each recipient
6. Recipients receive grants with status `PENDING_CONSENT`
7. Recipients must explicitly accept to activate

### 4. **Active Window Management**

#### **Active Window Banner**
- Displays at top of screen when user has active permission
- Shows countdown timer until expiration
- Polls backend every 60 seconds for status updates
- Automatically disappears when window expires

#### **Automatic Revocation**
- Backend validates `expires_at` on every protected API call
- If expired, returns `403 Forbidden`
- Frontend hook clears permission state immediately
- Button returns to "locked" state without page refresh

### 5. **Role-Based Access Control**

| Role | Capabilities | Approval Authority |
|------|-------------|-------------------|
| **SUPER_ADMIN** | Full system access, no approvals needed | Can approve all requests |
| **ORG_ADMIN** | Can delegate grants, bypass approvals with justification | Can approve all org requests |
| **CLIENT** | Equivalent to ORG_ADMIN | Can approve all org requests |
| **TEAM_LEAD** | Can request OR grant access to team members | Can approve team requests |
| **MEMBER** | Can request access only | Cannot approve |

### 6. **Security Features**

#### **Audit Trail**
- Every approval request logged with:
  - Requester ID and role
  - Feature ID and resource scope
  - Justification text
  - Approver ID (if approved)
  - Timestamps: created, approved, activated, expired
  - Duration requested vs granted

#### **Resource Scoping**
- Approvals can be scoped to specific resources
- Example: Permission to terminate only `i-12345abc`, not all instances
- Prevents privilege creep and over-authorization

#### **Risk Levels**
- **LOW**: Read-only operations (view clusters, audit logs)
- **MEDIUM**: Non-destructive changes (stop instances, edit configs)
- **HIGH**: Destructive or sensitive operations (delete resources, disconnect accounts)
- **CRITICAL**: System-wide changes (bypass approvals, manage MFA)

#### **Duration Controls**
- Each feature has `max_duration_hours` limit
- Default durations pre-configured per feature
- Slider UI prevents requests beyond maximum
- Backend validates duration on approval creation

### 7. **UI Components**

#### **Approvals Page** (`/approvals`)

**Admin View:**
- **Pending Requests Queue**: All requests awaiting approval
- **Active Grants**: Currently active time windows across organization
- **Statistics Dashboard**: Counts of pending, active, awaiting consent

**Team Lead View:**
- **Incoming Requests**: Team member requests needing approval
- **Active Team Access**: Currently active permissions in team
- **My Outgoing Requests**: Personal requests to Org Admin

**Member View:**
- **My Requests**: Personal request history and status
- **Pending Grants Alert**: Highlighted section for grants awaiting consent

#### **TicketRequestModal**

Two modes with distinct UI:
- **Green Theme (Grant Mode)**: Admin/Team Lead granting access to others
- **Indigo Theme (Request Mode)**: Member requesting access from approver

Features:
- Multi-recipient selection for bulk grants
- Resource discovery with AWS API integration
- Duration slider (1-72 hours)
- Reason categories: Maintenance, Incident, Cost Optimization, Testing
- Mandatory justification text field

#### **ProtectedButton**

Automatically wraps sensitive actions:
```jsx
<ProtectedButton
  featureId="compute:terminate"
  resourceId="i-12345abc"
  onClick={handleTerminate}
>
  Terminate Instance
</ProtectedButton>
```

States:
- **Loading**: Checking permissions
- **Unlocked**: Permission granted, shows checkmark icon
- **Locked**: Permission required, shows lock icon, opens modal on click

### 8. **Backend Architecture**

#### **ApprovalService** (`backend/services/approval_service.py`)

Key Methods:
- `create_approval()`: Member submits request
- `create_jit_request()`: Request with feature registry validation
- `approve()`: Approver activates request
- `revoke()`: Immediate termination of active window
- `get_active_window()`: Check if user has global access
- `check_specific_permission()`: Validate action-specific access
- `create_delegated_approvals()`: Admin bulk grant
- `accept_grant()`: User accepts delegated grant
- `reject_grant()`: User declines grant

#### **Permission Routes** (`backend/api/permission_routes.py`)

- `POST /api/v1/approvals` - Create request
- `POST /api/v1/approvals/delegate` - Admin bulk grant
- `POST /api/v1/approvals/jit-request` - Feature-specific request
- `POST /api/v1/approvals/{id}/approve` - Approve request
- `POST /api/v1/approvals/{id}/revoke` - Revoke active grant
- `POST /api/v1/approvals/{id}/accept` - Accept delegated grant
- `GET /api/v1/approvals/active-window` - Check user's active window

### 9. **Production Readiness**

✅ **Enterprise Features Implemented:**

1. **Time-Bound Access**: All permissions have automatic expiration
2. **Audit Compliance**: Complete trail of who requested what, when, why
3. **Four-Eyes Principle**: Separation between requester and approver
4. **Resource Isolation**: Permissions can be scoped to specific resources
5. **Role Hierarchy**: Proper delegation from Admin → Team Lead → Member
6. **Real-Time Updates**: Polling ensures UI reflects backend state
7. **Cascading Revocation**: Revoking parent grant revokes all children
8. **Feature Registry**: Centralized permission definitions
9. **Risk Classification**: Actions categorized by potential impact
10. **Reason Tracking**: Mandatory justification for compliance

### 10. **Recent UI Improvements**

✅ **Professional Design Applied:**
- Removed all emojis from UI components
- Replaced gradient headers with solid color themes
- Updated color scheme to match main application (Indigo/Green)
- Improved button styling with React Icons
- Consistent border radius (rounded-lg) across components
- Professional typography with proper font weights
- Enhanced spacing and padding for better readability
- Icon-based visual hierarchy instead of decorative emojis

✅ **Components Updated:**
- `TicketRequestModal.jsx`: Professional two-mode modal with icon-based UI
- `ActiveWindowBanner.jsx`: Clean banner with shield icon and timer
- `Approvals.jsx`: Enterprise-grade table with role-based views

### 11. **Testing the System**

1. **As Member**: Login and click any "Terminate" button
2. **Intercept**: Permission modal should open automatically
3. **Request**: Fill justification, select duration, submit
4. **As Team Lead/Admin**: See request in queue
5. **Approve**: Click approve button
6. **Verify**: Member sees ActiveWindowBanner appear
7. **Execute**: Member can now perform protected action
8. **Expiration**: Wait for duration to pass, banner disappears
9. **Blocked**: Attempt action again, permission denied

### 12. **Configuration**

Feature definitions are centralized in `backend/core/feature_registry.py`. To add new protected features:

```python
FEATURE_REGISTRY["my-new-feature"] = Feature(
    id="my-new-feature",
    name="My Feature Name",
    description="What this feature does",
    category=FeatureCategory.COMPUTE,
    permission_slug="my:permission",
    requires_approval=True,
    max_duration_hours=4,
    default_duration_hours=1,
    min_approver_role="TEAM_LEAD",
    risk_level="HIGH",
    requires_reason=True,
    supports_resource_scope=True,
    ui_icon="icon-name",
    ui_color="blue"
)
```

Then wrap the UI button:
```jsx
<ProtectedButton featureId="my-new-feature" onClick={handleAction}>
  My Action
</ProtectedButton>
```

## Summary

Your JIT approval system is **production-ready** and implements enterprise-grade security patterns. It provides:

- ✅ Default-deny security model
- ✅ Time-bound privilege escalation
- ✅ Complete audit trail
- ✅ Role-based approval routing
- ✅ Resource-scoped permissions
- ✅ Real-time permission enforcement
- ✅ Professional, emoji-free UI
- ✅ Comprehensive feature registry (100+ features)
- ✅ Automatic expiration and revocation

The system is fully functional and ready for enterprise deployment.
