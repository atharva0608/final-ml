# Scenario Files

## Purpose

Business logic and user flow descriptions. Explains the "why" behind implementations, not just the "what".

**Last Updated**: 2025-12-25
**Authority Level**: MEDIUM-HIGH

---

## Files

### auth_flow.md
**Purpose**: Complete authentication and routing flow documentation
**Status**: AUTHORITATIVE

**Covers**:
- Login flow (step-by-step)
- AuthGateway routing logic
- Token management (24-hour expiration)
- Edge cases (invalid credentials, token expiration, disabled accounts)
- Security considerations
- API endpoints

**Key Sections**:
- Happy Path (successful login)
- AuthGateway Routing (account-based navigation)
- Edge Cases (failures and errors)
- Security (password hashing, JWT, session management)
- Testing scenarios

**Referenced By**:
- `/index/feature_index.md#authentication`
- `/backend/api/info.md#auth.py`
- `/frontend/src/components/info.md#AuthGateway`

**Recent Changes**:
- **2025-12-25**: Initial creation for governance
**Reason**: Document authentication patterns
**Impact**: Provides authoritative reference for auth flows

---

### client_onboarding_flow.md
**Purpose**: AWS account connection workflows (both methods)
**Status**: AUTHORITATIVE

**Covers**:
- CloudFormation method (IAM role) - 6 steps
- Credentials method (access keys) - 3 steps
- Resource discovery process
- Frontend polling mechanism
- Empty states and edge cases
- Status transitions
- Security considerations

**Key Sections**:
1. **Flow: CloudFormation Method**
   - Step 1: Create onboarding request
   - Step 2: Generate CloudFormation template
   - Step 3: User creates stack in AWS
   - Step 4: Verify connection
   - Step 5: Resource discovery (background)
   - Step 6: Frontend polling

2. **Flow: Credentials Method**
   - Step 1: User enters credentials
   - Step 2: Validate credentials
   - Step 3-6: Same as CloudFormation

3. **Empty States & Edge Cases**
   - No instances found
   - Discovery failure
   - Duplicate AWS account (security)

**Referenced By**:
- `/index/feature_index.md#aws-onboarding`
- `/backend/api/info.md#onboarding_routes.py`
- `/frontend/src/components/info.md#ClientSetup`

**Recent Changes**:
- **2025-12-25**: Added security section (duplicate account prevention)
- **2025-12-25**: Added polling step documentation

**Reason**: Document complete onboarding flow with recent security fixes
**Impact**: Provides step-by-step reference for onboarding

---

## Scenario File Format

### Standard Structure

```markdown
# [Scenario Name] Flow

## Purpose
[What this scenario describes]

## User Story
As a [role], I want to [action] so that [benefit]

## Happy Path
[Step-by-step successful flow]

## Edge Cases
[Failure scenarios and handling]

## Security Considerations
[Security notes and requirements]

## API Endpoints
[Relevant endpoints with examples]

## Testing Scenarios
[How to test this flow]

## Known Issues
[Current problems]

## Historical Issues (Fixed)
[Past problems with references]
```

---

## When to Create New Scenarios

Create a new scenario file when:
1. **New major feature** with user-facing flow
2. **Complex workflow** with multiple steps
3. **Multiple components** interacting
4. **Security-critical** operations
5. **Frequently asked** "how does X work?"

**Examples**:
- `account_deletion_flow.md` - If deletion becomes complex
- `multi_region_discovery_flow.md` - When multi-region support added
- `notification_flow.md` - When email notifications implemented

---

## When to Update Existing Scenarios

Update when:
1. **Behavior changes** (e.g., status transitions modified)
2. **New edge case** discovered
3. **Security fix** changes flow
4. **API contract** changes
5. **Bug fix** changes expected behavior

**Update Format**:
```markdown
## Recent Changes

### YYYY-MM-DD: [Change description]
**Files Changed**: [list]
**Reason**: [why]
**Impact**: [what changed]
**Reference**: [link to fix log]
```

---

## Recent Changes

### 2025-12-25: Initial Scenario Creation
**Files Created**: 2 scenario files
- auth_flow.md
- client_onboarding_flow.md

**Reason**: Establish scenario documentation for governance
**Impact**: Provides "why" documentation for major flows
**Reference**: Initial governance structure

---

## Dependencies

**Requires**:
- Understanding of backend APIs
- Understanding of frontend components
- Knowledge of business requirements

**Required By**:
- LLM sessions (understand intent)
- New developers (onboarding)
- Feature planning (ensure consistency)

---

## Usage

### For LLM Sessions

```
When modifying authentication:
1. Read auth_flow.md
2. Understand current behavior
3. Identify what will change
4. Update auth_flow.md after change
```

### For New Features

```
When adding new feature:
1. Check if scenario file exists
2. If not, create new scenario file
3. Document expected behavior
4. Reference from feature_index.md
```

---

_Last Updated: 2025-12-25_
_Authority: MEDIUM-HIGH - Explains business logic_
