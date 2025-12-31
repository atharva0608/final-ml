# Frontend Config Module

## Purpose

Application configuration files and constants.

**Last Updated**: 2025-12-25
**Authority Level**: MEDIUM

---

## Files

### api.jsx
**Purpose**: API configuration and endpoint definitions
**Lines**: ~30
**Key Exports**:
- `API_BASE_URL` - Base URL for API requests
- `API_ENDPOINTS` - Object with all API endpoint paths
- API configuration constants

**Configuration**:
```javascript
const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

const API_ENDPOINTS = {
  // Auth
  LOGIN: '/api/auth/login',
  LOGOUT: '/api/auth/logout',
  ME: '/api/auth/me',

  // Accounts
  ACCOUNTS: '/client/accounts',
  DISCONNECT_ACCOUNT: (id) => `/client/accounts/${id}`,

  // Onboarding
  CREATE_ONBOARDING: '/client/onboarding/create-request',
  VERIFY_CONNECTION: (requestId) => `/client/onboarding/verify-connection/${requestId}`,

  // Dashboard
  DASHBOARD: '/client/dashboard',

  // Instances
  INSTANCES: (accountId) => `/instances?account_id=${accountId}`,
};
```

**Usage**:
Centralized endpoint definitions prevent hardcoded URLs throughout the app.

**Dependencies**: Environment variables (Vite)

**Recent Changes**: None recent

---

## Configuration Management

### Environment Variables
Managed via `.env` files:
- `.env.development` - Local development
- `.env.production` - Production build
- `.env.staging` - Staging environment (if exists)

### Required Variables
```env
VITE_API_URL=http://localhost:8000
VITE_WS_URL=ws://localhost:8000/ws  # WebSocket URL
VITE_ENV=development
```

---

## Dependencies

### Depends On:
- Vite (import.meta.env)
- `.env` files

### Depended By:
- frontend/src/services/api.js (uses API_BASE_URL)
- Components making API calls

**Impact Radius**: MEDIUM (affects API configuration)

---

## Recent Changes

### 2025-12-25: Governance Structure Establishment
**Files Changed**: None (metadata only)
**Reason**: Document existing config
**Impact**: No code changes, documentation baseline
**Reference**: `/index/recent_changes.md`

---

## Usage

### Import Configuration
```javascript
import { API_BASE_URL, API_ENDPOINTS } from '../config/api';

// Use in API calls
const url = `${API_BASE_URL}${API_ENDPOINTS.LOGIN}`;
```

### Adding New Endpoint
1. Add to `API_ENDPOINTS` object in api.jsx
2. Use in api.js or components
3. Update this info.md

---

## Known Issues

### None

Config module is stable as of 2025-12-25.

---

_Last Updated: 2025-12-25_
_Authority: MEDIUM - Configuration_
