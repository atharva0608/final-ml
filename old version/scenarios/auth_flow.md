# Authentication Flow

## Purpose

Describes the complete authentication and authorization flow.

**Last Updated**: 2025-12-25

---

## User Stories

### As a Client User
- I want to log in with my credentials
- I want my session to persist for 24 hours
- I want to be redirected to the appropriate page based on my account state

### As an Admin User
- I want to log in and access admin dashboard
- I want my session to be secure

---

## Happy Path

### Login Flow

```
1. User navigates to /login
   ↓
2. User enters username + password
   ↓
3. Frontend sends POST /api/auth/login
   {
     "username": "user@example.com",
     "password": "********"
   }
   ↓
4. Backend validates credentials
   - Queries `users` table
   - Verifies password hash (bcrypt)
   ↓
5. Backend generates JWT token
   - Expiration: 24 hours
   - Payload: {"sub": username, "exp": timestamp}
   - Signed with HS256
   ↓
6. Backend returns token
   {
     "access_token": "eyJ...",
     "token_type": "bearer",
     "user": {
       "username": "user@example.com",
       "role": "client"
     }
   }
   ↓
7. Frontend stores token
   - localStorage: 'access_token'
   - Or HTTP-only cookie (if configured)
   ↓
8. Frontend redirects based on role
   - Client role → AuthGateway check
   - Admin role → Admin dashboard
```

### AuthGateway Routing (Client Role Only)

```
User role: client
   ↓
AuthGateway component mounts
   ↓
GET /client/accounts
   ↓
Response received
   ├─ accounts.length > 0
   │    ↓
   │  Navigate to /client (dashboard)
   │
   └─ accounts.length === 0
        ↓
      Navigate to /onboarding/setup
```

See: `/index/feature_index.md#authgateway`

---

## Edge Cases

### Invalid Credentials

```
User enters wrong password
   ↓
Backend verifies password hash
   ↓
Hash doesn't match
   ↓
Return HTTP 401 Unauthorized
   {
     "detail": "Incorrect username or password"
   }
   ↓
Frontend shows error message
```

### Token Expiration

```
User logged in 25 hours ago
   ↓
Frontend makes API request with expired token
   ↓
Backend verifies JWT signature
   ↓
Token expired (exp claim > current time)
   ↓
Return HTTP 401 Unauthorized
   ↓
Frontend redirects to /login
```

### Account Locked/Disabled

```
User attempts login
   ↓
Backend finds user in database
   ↓
User.is_active == False
   ↓
Return HTTP 403 Forbidden
   {
     "detail": "Account is disabled"
   }
   ↓
Frontend shows "Contact administrator"
```

---

## Security Considerations

### Password Storage

- **Hashing**: bcrypt with salt
- **Rounds**: 12 (configurable)
- **Never** store plaintext passwords

### Token Security

- **Algorithm**: HS256 (HMAC-SHA256)
- **Secret**: Stored in environment variable `JWT_SECRET_KEY`
- **Expiration**: 24 hours (fixed P-2025-11-26)
- **Transmission**: HTTPS only (in production)

### Session Management

- **Storage**: localStorage or HTTP-only cookies
- **SameSite**: Strict or Lax (CSRF protection)
- **Secure**: True (HTTPS only)

---

## API Endpoints

### POST /api/auth/login

**Request**:
```json
{
  "username": "user@example.com",
  "password": "SecurePassword123"
}
```

**Response (Success - HTTP 200)**:
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "user": {
    "id": "123",
    "username": "user@example.com",
    "email": "user@example.com",
    "role": "client"
  }
}
```

**Response (Failure - HTTP 401)**:
```json
{
  "detail": "Incorrect username or password"
}
```

### GET /api/auth/me

**Headers**:
```
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

**Response (HTTP 200)**:
```json
{
  "id": "123",
  "username": "user@example.com",
  "email": "user@example.com",
  "role": "client",
  "created_at": "2025-01-01T00:00:00Z"
}
```

**Response (Unauthorized - HTTP 401)**:
```json
{
  "detail": "Not authenticated"
}
```

### POST /api/auth/logout

**Implementation**: Client-side only (delete token from storage)

---

## Frontend Implementation

### AuthContext

**Location**: `frontend/src/context/AuthContext.jsx`

**Responsibilities**:
- Store user state
- Store token
- Provide login/logout functions
- Persist across page reloads

### API Interceptor

**Location**: `frontend/src/services/api.js`

**Responsibilities**:
- Attach Authorization header to all requests
- Handle 401 responses (redirect to login)
- Refresh token (if implemented)

---

## Testing Scenarios

### Test 1: Successful Login (Client)

1. Navigate to /login
2. Enter valid client credentials
3. Click "Login"
4. Verify redirect to AuthGateway
5. If accounts exist → verify redirect to /client
6. If no accounts → verify redirect to /onboarding/setup

### Test 2: Successful Login (Admin)

1. Navigate to /login
2. Enter valid admin credentials
3. Click "Login"
4. Verify redirect to / (admin dashboard)

### Test 3: Invalid Credentials

1. Navigate to /login
2. Enter invalid password
3. Click "Login"
4. Verify error message displayed
5. Verify user remains on login page

### Test 4: Token Expiration

1. Login successfully
2. Wait 25 hours (or mock token expiration)
3. Make API request
4. Verify 401 response
5. Verify redirect to /login

### Test 5: Protected Route Access

1. Navigate directly to /client (without login)
2. Verify redirect to /login
3. After login, verify redirect back to /client

---

## Known Issues

### None

Authentication system is stable as of 2025-12-25.

---

## Historical Issues (Fixed)

### Token Expiration Too Short (P-2025-11-26)

**Problem**: Tokens expired after 5 minutes
**Impact**: Users logged out frequently
**Fix**: Changed expiration to 24 hours
**Reference**: `/progress/fixed_issues_log.md` (historical)

---

_Last Updated: 2025-12-25_
