# Frontend Services Module

## Purpose

API client and external service integrations for frontend.

**Last Updated**: 2025-12-25
**Authority Level**: HIGH

---

## Files

### api.js ⭐ PRIMARY
**Purpose**: Main API client with Axios configuration and interceptors
**Lines**: ~500
**Key Features**:
- Base Axios instance with default config
- Request/response interceptors
- Authentication token injection
- Error handling and retry logic
- API endpoint functions

**Base Configuration**:
```javascript
baseURL: import.meta.env.VITE_API_URL || 'http://localhost:8000'
timeout: 30000 (30 seconds)
headers: { 'Content-Type': 'application/json' }
```

**Request Interceptor**:
- Automatically attaches JWT token from localStorage
- Adds Authorization header: `Bearer <token>`

**Response Interceptor**:
- Handles 401 Unauthorized → Redirect to /login
- Handles 403 Forbidden → Show error
- Handles 500 Server Error → Show error toast

**API Functions**:
- `login(username, password)` - User authentication
- `getAccounts()` - Fetch connected accounts (GET /client/accounts)
- `disconnectAccount(accountId)` - Disconnect AWS account (DELETE)
- `createOnboarding(data)` - Start onboarding (POST)
- `verifyConnection(requestId, data)` - Verify CloudFormation/credentials
- `getInstances(accountId)` - Fetch EC2 instances
- `getDashboardData()` - Fetch dashboard metrics

**Dependencies**:
- axios
- react-router-dom (for navigation)
- Frontend AuthContext

**Recent Changes**:
- 2025-12-25: No changes (governance baseline)

### api.jsx (LEGACY)
**Purpose**: Old API client (likely deprecated)
**Lines**: ~5
**Status**: ⚠️ May be unused, check for removal
**Recent Changes**: None

### apiClient.jsx
**Purpose**: Alternative API client (possibly for specific features)
**Lines**: ~600
**Status**: May duplicate api.js functionality
**Note**: Review for consolidation opportunity

**Dependencies**: axios, possibly different configuration

**Recent Changes**: None recent

### __init__.js (if exists)
**Purpose**: Barrel exports for services

---

## API Request Flow

```
React Component
   ↓
[Call api.js function]
   ↓
[Request Interceptor]
   - Attach JWT token
   ↓
[Send HTTP Request]
   ↓
[Receive Response]
   ↓
[Response Interceptor]
   - Handle 401/403/500
   ↓
[Return Data to Component]
```

---

## Authentication Flow

```
User Enters Credentials
   ↓
[api.login(username, password)]
   ↓
POST /api/auth/login
   ↓
[Receive JWT token]
   ↓
[Store token in localStorage]
   ↓
[All subsequent requests include token]
```

---

## Dependencies

### Depends On:
- axios (HTTP client)
- react-router-dom (navigation)
- frontend/src/context/AuthContext.jsx (authentication state)
- Environment variables (VITE_API_URL)

### Depended By:
- **CRITICAL**: All React components making API calls
- frontend/src/pages/* (all page components)
- frontend/src/components/* (all data-fetching components)

**Impact Radius**: CRITICAL (used by entire frontend)

---

## Recent Changes

### 2025-12-25: Governance Structure Establishment
**Files Changed**: None (metadata only)
**Reason**: Document existing API client
**Impact**: No code changes, documentation baseline
**Reference**: `/index/recent_changes.md`

---

## Usage

### Basic API Call
```javascript
import api from '../services/api';

// In component
useEffect(() => {
  const fetchData = async () => {
    try {
      const response = await api.get('/client/accounts');
      setAccounts(response.data);
    } catch (error) {
      console.error('Failed to fetch accounts:', error);
    }
  };
  fetchData();
}, []);
```

### Login Example
```javascript
import { login } from '../services/api';

const handleLogin = async (username, password) => {
  try {
    const response = await login(username, password);
    localStorage.setItem('access_token', response.data.access_token);
    navigate('/client');
  } catch (error) {
    setError('Invalid credentials');
  }
};
```

---

## Error Handling

### Standard Error Responses
```javascript
try {
  await api.get('/some-endpoint');
} catch (error) {
  if (error.response) {
    // Server responded with error
    console.error('Status:', error.response.status);
    console.error('Data:', error.response.data);
  } else if (error.request) {
    // Request made but no response
    console.error('Network error');
  } else {
    // Something else happened
    console.error('Error:', error.message);
  }
}
```

---

## Environment Configuration

### Development
```env
VITE_API_URL=http://localhost:8000
```

### Production
```env
VITE_API_URL=https://api.production.com
```

---

## Known Issues

### None

Services module is stable as of 2025-12-25.

---

## TODO / Improvements

1. **Code Consolidation**: Review api.js, api.jsx, and apiClient.jsx for duplication
2. **TypeScript**: Consider migration to TypeScript for type safety
3. **Request Cancellation**: Implement AbortController for request cancellation
4. **Retry Logic**: Add exponential backoff for failed requests

---

_Last Updated: 2025-12-25_
_Authority: HIGH - Core API integration_
