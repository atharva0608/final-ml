# Backend Auth Module

## Purpose

Authentication utilities including JWT token management, password hashing, and dependency injection for protected routes.

**Last Updated**: 2025-12-25
**Authority Level**: CRITICAL

---

## Files

### jwt.py ⭐ PROTECTED
**Purpose**: JWT token creation and validation
**Lines**: ~120
**Key Functions**:
- `create_access_token(data: dict, expires_delta: Optional[timedelta])` - Generate JWT tokens
- `verify_token(token: str)` - Validate and decode JWT tokens
- `get_current_user(token: str)` - Extract user from token

**Protected Behavior**:
- Token expiration: **24 hours** (NEVER change without approval)
- Algorithm: HS256
- Secret: From environment variable `JWT_SECRET_KEY`

**Dependencies**:
- python-jose library
- datetime, timedelta
- Environment variables

**Recent Changes**:
- 2025-11-26: Fixed token expiration from 5 minutes to 24 hours ⚠️ CRITICAL FIX
**Reference**: `/progress/regression_guard.md#1`, `/progress/fixed_issues_log.md`

**⚠️ WARNING**: This is a protected zone. See regression guard before modifications.

### password.py
**Purpose**: Password hashing and verification utilities
**Lines**: ~30
**Key Functions**:
- `hash_password(password: str)` - Hash password using bcrypt
- `verify_password(plain_password: str, hashed_password: str)` - Verify password

**Security**:
- Algorithm: bcrypt with salt
- Rounds: 12 (configurable)
- Never stores plaintext passwords

**Dependencies**: passlib[bcrypt]
**Recent Changes**: None recent

### dependencies.py
**Purpose**: FastAPI dependency injection for authentication
**Lines**: ~80
**Key Functions**:
- `get_current_user(token: str = Depends(oauth2_scheme))` - Extract authenticated user
- `get_current_active_user(current_user: User = Depends(get_current_user))` - Verify user is active
- `require_role(required_role: str)` - Role-based access control decorator

**Dependencies**:
- FastAPI OAuth2PasswordBearer
- jwt.py functions
- database models

**Recent Changes**: None recent

### __init__.py
**Purpose**: Package initialization and exports
**Exports**: All authentication utilities

---

## Authentication Flow

```
Client Request
   ↓
[Check Authorization header]
   ↓
[Extract JWT token]
   ↓
[Verify token signature] (jwt.py)
   ↓
[Decode token payload]
   ↓
[Query user from database]
   ↓
[Verify user is_active]
   ↓
[Return User object to route]
```

See: `/scenarios/auth_flow.md` for complete flow

---

## Critical Behaviors

### Token Expiration
**Current Value**: 24 hours
**History**: Was 5 minutes (caused frequent logouts)
**Fixed**: 2025-11-26
**NEVER modify** without reading regression guard

### Password Security
- **Hashing**: bcrypt with automatic salt
- **Verification**: Constant-time comparison
- **Storage**: Only hashed passwords in database
- **Never** store or log plaintext passwords

---

## Dependencies

### Depends On:
- python-jose[cryptography]
- passlib[bcrypt]
- FastAPI OAuth2PasswordBearer
- backend/database/models.py (User model)
- Environment: JWT_SECRET_KEY

### Depended By:
- **CRITICAL**: All protected API routes
- backend/api/auth.py (login endpoint)
- All routes using `@require_role` decorator

**Impact Radius**: CRITICAL (breaks all authentication if modified incorrectly)

---

## Recent Changes

### 2025-12-25: Governance Structure Establishment
**Files Changed**: None (metadata only)
**Reason**: Document existing auth utilities
**Impact**: No code changes, documentation baseline
**Reference**: `/index/recent_changes.md`

### 2025-11-26: Token Expiration Fix ⚠️ CRITICAL
**Files Changed**: jwt.py (line ~45)
**Reason**: Users were logged out after 5 minutes (bug)
**Impact**: Tokens now expire after 24 hours
**Reference**: `/progress/fixed_issues_log.md`, `/progress/regression_guard.md#1`

---

## Usage

### Protecting Routes
```python
from backend.auth.dependencies import get_current_active_user
from backend.database.models import User

@router.get("/protected")
def protected_route(current_user: User = Depends(get_current_active_user)):
    return {"user": current_user.username}
```

### Role-Based Access
```python
from backend.auth.dependencies import require_role

@router.get("/admin-only")
@require_role("admin")
def admin_route(current_user: User = Depends(get_current_active_user)):
    return {"message": "Admin access granted"}
```

---

## Security Considerations

1. **Token Secret**: MUST be stored in environment variable, NEVER in code
2. **HTTPS Only**: Tokens should only be transmitted over HTTPS in production
3. **Token Storage**: Client should use HTTP-only cookies or secure localStorage
4. **Password Strength**: Enforce minimum requirements in frontend and backend
5. **Rate Limiting**: Implement login attempt rate limiting (TODO)

---

## Known Issues

### None

Authentication system is stable as of 2025-12-25.

---

## Testing

### Test Token Creation
```python
from backend.auth.jwt import create_access_token

token = create_access_token({"sub": "testuser"})
assert token is not None
```

### Test Password Hashing
```python
from backend.auth.password import hash_password, verify_password

hashed = hash_password("SecurePass123")
assert verify_password("SecurePass123", hashed) == True
assert verify_password("WrongPass", hashed) == False
```

---

_Last Updated: 2025-12-25_
_Authority: CRITICAL - Core authentication_
