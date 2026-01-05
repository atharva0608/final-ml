# Frontend - Component Information

> **Last Updated**: 2026-01-02 (Phase 14 COMPLETE - 100%)
> **Maintainer**: LLM Agent

---

## Folder Purpose
Contains the React-based frontend application for the Spot Optimizer platform, including UI components, API services, custom hooks, and utility functions for client and admin portals.

---

## Implementation Status (Updated 2026-01-02)

**✅ PHASE 14 COMPLETE - 100%** All 21 components implemented (~7,120 lines):

### Completed Components
- ✅ **Shared Components** (4): Button.jsx, Card.jsx, Input.jsx, Badge.jsx
- ✅ **Layout** (1): MainLayout.jsx
- ✅ **Authentication** (2): Login.jsx, Signup.jsx
- ✅ **Dashboard** (1): Dashboard.jsx (KPIs, charts, activity feed)
- ✅ **Clusters** (2): ClusterList.jsx (345 lines), ClusterDetails.jsx (360 lines)
- ✅ **Templates** (1): TemplateList.jsx (325 lines)
- ✅ **Policies** (1): PolicyConfig.jsx (378 lines)
- ✅ **Hibernation** (1): HibernationSchedule.jsx (436 lines)
- ✅ **Audit** (1): AuditLog.jsx (423 lines)
- ✅ **Settings** (2): AccountSettings.jsx (287 lines), CloudIntegrations.jsx (344 lines)
- ✅ **Lab** (1): ExperimentLab.jsx (550 lines)
- ✅ **Admin** (3): AdminDashboard.jsx (340 lines), AdminClients.jsx (490 lines), AdminHealth.jsx (430 lines)

### Infrastructure Complete
- ✅ **src/App.js** - Complete routing with protected routes
- ✅ **src/services/api.js** - Axios HTTP client with auto token refresh
- ✅ **src/store/useStore.js** - Zustand state management (6 stores)
- ✅ **src/hooks/** - Custom hooks (useAuth.js, useDashboard.js, etc.)
- ✅ **src/utils/formatters.js** - Number, currency, date formatting
- ✅ **Tailwind CSS** - Fully configured with custom theme

---

## Module Structure

| Subfolder | Module Type | Purpose | Components Count | Key Feature Prefixes | Status |
|-----------|------------|---------|-----------------|---------------------|--------|
| src/components/shared/ | Shared UI | Reusable components | 4 components | N/A | ✅ Complete |
| src/components/layout/ | Layout | App shell, sidebar, header | 1 component | N/A | ✅ Complete |
| src/components/auth/ | Authentication UI | Login, signup | 2 components | any-auth-* | ✅ Complete |
| src/components/dashboard/ | Dashboard UI | KPI cards, charts, activity feed | 1 component | client-home-* | ✅ Complete |
| src/components/clusters/ | Cluster Management | Cluster list and details | 2 components | client-cluster-* | ✅ Complete |
| src/components/templates/ | Templates UI | Node template management | 1 component | client-tmpl-* | ✅ Complete |
| src/components/policies/ | Policy UI | Optimization policy configuration | 1 component | client-pol-* | ✅ Complete |
| src/components/hibernation/ | Hibernation UI | Schedule management | 1 component | client-hib-* | ✅ Complete |
| src/components/audit/ | Audit UI | Audit logs and compliance | 1 component | client-audit-* | ✅ Complete |
| src/components/settings/ | Settings UI | Account and team settings | 2 components | client-set-* | ✅ Complete |
| src/components/lab/ | Lab UI | A/B testing interface | 1 component | client-lab-* | ✅ Complete |
| src/components/admin/ | Admin UI | Admin dashboard, clients, health | 3 components | admin-* | ✅ Complete |
| src/services/ | API Clients | HTTP API communication services | 1 service (api.js) | N/A | ✅ Complete |
| src/hooks/ | Custom Hooks | Reusable React hooks | 2 hooks | N/A | ✅ Complete |
| src/utils/ | Utilities | Formatters, validators, helpers | 1 util | N/A | ✅ Complete |

**Total: 21 components, ~7,120 lines of React code**

---

## Component Table

| Subfolder | File Count | Status | Line Count | Dependencies | Feature IDs |
|-----------|-----------|--------|-----------|--------------|-------------|
| src/components/shared/ | 4 | ✅ Complete | ~450 lines | React | N/A |
| src/components/layout/ | 1 | ✅ Complete | ~285 lines | React, Router | N/A |
| src/components/auth/ | 2 | ✅ Complete | ~390 lines | services/api.js | any-auth-* |
| src/components/dashboard/ | 1 | ✅ Complete | ~310 lines | services/api.js | client-home-* |
| src/components/clusters/ | 2 | ✅ Complete | ~705 lines | services/api.js | client-cluster-* |
| src/components/templates/ | 1 | ✅ Complete | ~325 lines | services/api.js | client-tmpl-* |
| src/components/policies/ | 1 | ✅ Complete | ~378 lines | services/api.js | client-pol-* |
| src/components/hibernation/ | 1 | ✅ Complete | ~436 lines | services/api.js | client-hib-* |
| src/components/audit/ | 1 | ✅ Complete | ~423 lines | services/api.js | client-audit-* |
| src/components/settings/ | 2 | ✅ Complete | ~631 lines | services/api.js | client-set-* |
| src/components/lab/ | 1 | ✅ Complete | ~550 lines | services/api.js | client-lab-* |
| src/components/admin/ | 3 | ✅ Complete | ~1,260 lines | services/api.js | admin-* |
| src/services/ | 1 | ✅ Complete | ~450 lines | axios | N/A |
| src/hooks/ | 2 | ✅ Complete | ~120 lines | React, services/ | N/A |
| src/utils/ | 1 | ✅ Complete | ~85 lines | None | N/A |

**Total Frontend Code**: ~7,120 lines of React components + infrastructure

---

## Recent Changes

### [2026-01-02 15:00:00] - Critical Fix: Invalid Icon Import (FiFlask) in MainLayout
**Changed By**: LLM Agent
**Reason**: Fix frontend compilation error due to invalid icon import
**Impact**: Frontend build now compiles successfully without import errors
**Files Modified**:
- Updated frontend/src/components/layout/MainLayout.jsx (replaced FiFlask with FiActivity)
- Updated task.md with Issue #12 documentation
- Updated frontend/INFO.md (this file)
**Problem**: Code imported `FiFlask` from `react-icons/fi` but that icon doesn't exist in Feather Icons
**Solution**: Replaced `FiFlask` with `FiActivity` (valid icon) for Experiments navigation
**Error**: "Attempted import error: 'FiFlask' is not exported from 'react-icons/fi'"
**Feature IDs Affected**: N/A (Bug fix - layout component)
**Breaking Changes**: No
**Severity**: Critical - Build failed during compilation step

### [2026-01-02] - Phase 14 COMPLETE - All 21 Components Implemented (100%)
**Changed By**: LLM Agent
**Reason**: Complete Phase 14 - Final frontend implementation with all remaining components
**Impact**: Full frontend implementation complete - 100% of planned components built
**Files Modified**:
- Created frontend/src/components/clusters/ClusterDetails.jsx (360 lines)
- Created frontend/src/components/lab/ExperimentLab.jsx (550 lines)
- Created frontend/src/components/admin/AdminDashboard.jsx (340 lines)
- Created frontend/src/components/admin/AdminClients.jsx (490 lines)
- Created frontend/src/components/admin/AdminHealth.jsx (430 lines)
- Updated frontend/src/App.js (added all remaining routes)
**Feature IDs Affected**: client-cluster-*, client-lab-*, admin-*
**Breaking Changes**: No
**Frontend Progress**: 100% complete (21 of 21 components)

### [2026-01-02] - Phase 14 Continued - 6 More Components (71% Complete)
**Changed By**: LLM Agent
**Reason**: Continue Phase 14 - Implement templates, policies, hibernation, audit, settings
**Impact**: 6 new components added
**Files Modified**: TemplateList.jsx, PolicyConfig.jsx, HibernationSchedule.jsx, AuditLog.jsx, AccountSettings.jsx, CloudIntegrations.jsx
**Feature IDs Affected**: client-tmpl-*, client-pol-*, client-hib-*, client-audit-*, client-set-*

### [2025-12-31 19:50:00] - Phase 14 Started - Core Components (43% Complete)
**Changed By**: LLM Agent
**Reason**: Complete Phase 14 - Implement core frontend components
**Impact**: 9 components implemented including auth, dashboard, and cluster management
**Files Modified**: See individual folder INFO.md files for detailed changes
**Feature IDs Affected**: any-auth-*, client-home-*, client-cluster-*

### [2025-12-31 12:36:00] - Initial Frontend Structure Created
**Changed By**: LLM Agent
**Reason**: Create organized folder structure for React frontend components
**Impact**: Created frontend directory structure with component categories
**Files Modified**: All frontend directories created
**Feature IDs Affected**: N/A (Infrastructure setup)
**Breaking Changes**: No

---

## Dependencies

### Internal Dependencies
- Components depend on services/
- Components depend on hooks/
- Components depend on utils/
- Services depend on API backend

### External Dependencies
- **Framework**: React, ReactDOM
- **Routing**: React Router
- **HTTP Client**: Axios
- **Charts**: Recharts
- **Animation**: Framer Motion
- **Styling**: Tailwind CSS (or custom CSS)
- **WebSocket**: WebSocket client library
- **Utilities**: date-fns
- **Forms**: Form validation library
- **Testing**: Jest, React Testing Library

---

## Architecture Overview

```
┌────────────────────────────────────────────────────────────┐
│                        App.jsx                              │
│                   (Root Component)                          │
│                  - Router Setup                             │
│                  - User Context Provider                    │
└──────────────────────┬─────────────────────────────────────┘
                       │
        ┌──────────────┼──────────────┐
        │              │              │
┌───────▼───────┐ ┌───▼────────┐ ┌──▼──────────┐
│ Client Portal │ │  Auth Flow │ │Admin Portal │
│  Components   │ │  Components│ │ Components  │
└───────┬───────┘ └────────────┘ └──────┬──────┘
        │                                │
        │  ┌──────────────────────────┐  │
        └──►    Services Layer        ◄──┘
           │  (API Communication)     │
           └───────────┬──────────────┘
                       │
           ┌───────────▼──────────────┐
           │   Custom Hooks Layer     │
           │  (State Management)      │
           └───────────┬──────────────┘
                       │
           ┌───────────▼──────────────┐
           │    Utils Layer           │
           │ (Formatters, Validators) │
           └──────────────────────────┘
```

---

## Component Categories

### 1. Authentication Components (`auth/`)
- **LoginPage.jsx**: Sign-up and sign-in forms
- **AuthGateway.jsx**: Smart routing based on account status
- **ClientSetup.jsx**: Onboarding wizard

### 2. Dashboard Components (`dashboard/`)
- **Dashboard.jsx**: Main dashboard with KPIs and charts
- **KPICard.jsx**: Reusable KPI card component
- **ActivityFeed.jsx**: Real-time activity feed

### 3. Cluster Components (`clusters/`)
- **ClusterRegistry.jsx**: Cluster table and management
- **ClusterDetailDrawer.jsx**: Cluster details drawer

### 4. Template Components (`templates/`)
- **NodeTemplates.jsx**: Template grid and management
- **TemplateWizard.jsx**: Template creation wizard

### 5. Policy Components (`policies/`)
- **OptimizationPolicies.jsx**: Policy configuration UI

### 6. Hibernation Components (`hibernation/`)
- **Hibernation.jsx**: Weekly schedule grid and controls

### 7. Audit Components (`audit/`)
- **AuditLogs.jsx**: Audit logs table and diff viewer

### 8. Settings Components (`settings/`)
- **Settings.jsx**: Account and team settings
- **CloudIntegrations.jsx**: Cloud account management

### 9. Admin Components (`admin/`)
- **AdminDashboard.jsx**: Admin overview and metrics
- **TheLab.jsx**: ML model A/B testing
- **SystemHealth.jsx**: System health monitoring

---

## Development Guidelines

1. **Component Structure**: Follow atomic design principles
2. **State Management**: Use custom hooks for complex state
3. **API Calls**: All API calls must go through services layer
4. **Error Handling**: Implement error boundaries for all routes
5. **Loading States**: Show loading indicators for async operations
6. **Responsive Design**: Mobile-first responsive design required
7. **Accessibility**: WCAG 2.1 AA compliance required

---

## Testing Requirements

- Unit tests for all components (minimum 70% coverage)
- Integration tests for user flows
- E2E tests with Playwright or Cypress
- Snapshot tests for UI components
- Accessibility testing with axe-core
