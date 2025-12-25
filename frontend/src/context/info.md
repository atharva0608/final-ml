# Frontend Context Module

## Purpose

React Context providers for global state management.

**Last Updated**: 2025-12-25
**Authority Level**: HIGH

---

## Files

### AuthContext.jsx ⭐ CRITICAL
**Purpose**: Authentication state management across the application
**Lines**: ~120
**Key Components**:
- `AuthContext` - React Context for auth state
- `AuthProvider` - Context provider component
- `useAuth` - Custom hook for consuming auth state

**State Managed**:
- `user` - Current user object (null if not logged in)
- `token` - JWT access token
- `isAuthenticated` - Boolean auth status
- `loading` - Loading state during auth checks

**Methods Provided**:
- `login(username, password)` - Authenticate user
- `logout()` - Clear auth state and redirect
- `checkAuth()` - Verify token validity

**Persistence**:
- Token stored in localStorage: `'access_token'`
- Auto-restore on app reload
- Auto-logout on token expiration

**Dependencies**:
- React (createContext, useState, useEffect, useContext)
- frontend/src/services/api.js (for login API call)
- react-router-dom (for navigation)

**Recent Changes**:
- 2025-12-23: Updated to support multi-account routing

### ModelContext.jsx
**Purpose**: ML model and experiment state management
**Lines**: ~90
**Key Components**:
- `ModelContext` - Context for ML-related state
- `ModelProvider` - Provider component
- `useModel` - Hook for accessing model state

**State Managed**:
- `experiments` - List of ML experiments
- `selectedExperiment` - Currently selected experiment
- `models` - Available ML models
- `predictions` - Recent predictions

**Methods Provided**:
- `loadExperiments()` - Fetch experiments from API
- `selectExperiment(id)` - Set active experiment
- `runPrediction(data)` - Execute ML prediction

**Dependencies**:
- React
- frontend/src/services/api.js

**Recent Changes**: None recent

### __init__.js (if exists)
**Purpose**: Barrel exports for contexts

---

## Context Usage Pattern

```
App.jsx
  ↓
<AuthProvider>
  <ModelProvider>
    <Router>
      <Routes>
        {/* All routes have access to auth and model state */}
      </Routes>
    </Router>
  </ModelProvider>
</AuthProvider>
```

---

## Authentication Flow

```
User Logs In
   ↓
[AuthContext.login()]
   ↓
[API call to /api/auth/login]
   ↓
[Receive JWT token]
   ↓
[Update AuthContext state]
   ↓
[Save token to localStorage]
   ↓
[All components re-render with user data]
```

---

## Dependencies

### Depends On:
- React (Context API, Hooks)
- frontend/src/services/api.js
- react-router-dom
- localStorage (browser API)

### Depended By:
- **CRITICAL**: App.jsx (providers wrap entire app)
- All components using `useAuth()` or `useModel()`
- Protected routes (check isAuthenticated)
- Navigation components (show user info)

**Impact Radius**: CRITICAL (affects entire app state)

---

## Recent Changes

### 2025-12-25: Governance Structure Establishment
**Files Changed**: None (metadata only)
**Reason**: Document existing context providers
**Impact**: No code changes, documentation baseline
**Reference**: `/index/recent_changes.md`

### 2025-12-23: AuthContext Multi-Account Support
**Files Changed**: AuthContext.jsx
**Reason**: Support routing based on account status
**Impact**: Added account state to auth context
**Reference**: Legacy documentation

---

## Usage

### Consuming AuthContext
```javascript
import { useAuth } from '../context/AuthContext';

function MyComponent() {
  const { user, isAuthenticated, logout } = useAuth();

  if (!isAuthenticated) {
    return <Navigate to="/login" />;
  }

  return (
    <div>
      <p>Welcome, {user.username}</p>
      <button onClick={logout}>Logout</button>
    </div>
  );
}
```

### Consuming ModelContext
```javascript
import { useModel } from '../context/ModelContext';

function ExperimentDashboard() {
  const { experiments, loadExperiments, selectExperiment } = useModel();

  useEffect(() => {
    loadExperiments();
  }, []);

  return (
    <ul>
      {experiments.map(exp => (
        <li key={exp.id} onClick={() => selectExperiment(exp.id)}>
          {exp.name}
        </li>
      ))}
    </ul>
  );
}
```

---

## Protected Route Pattern

```javascript
import { useAuth } from '../context/AuthContext';
import { Navigate } from 'react-router-dom';

function ProtectedRoute({ children }) {
  const { isAuthenticated, loading } = useAuth();

  if (loading) return <div>Loading...</div>;

  return isAuthenticated ? children : <Navigate to="/login" />;
}
```

---

## Known Issues

### None

Context module is stable as of 2025-12-25.

---

## TODO / Improvements

1. **Persist Model State**: Consider persisting selected experiment to localStorage
2. **Error Handling**: Add error state to contexts
3. **TypeScript**: Migrate to TypeScript for type safety

---

_Last Updated: 2025-12-25_
_Authority: HIGH - Global state management_
