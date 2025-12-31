# Frontend - Component Information

> **Last Updated**: 2025-12-31 12:36:00
> **Maintainer**: LLM Agent

---

## Folder Purpose
Contains the React-based frontend application for the Spot Optimizer platform, including UI components, API services, custom hooks, and utility functions for client and admin portals.

---

## Module Structure

| Subfolder | Module Type | Purpose | Components Count | Key Feature Prefixes |
|-----------|------------|---------|-----------------|---------------------|
| src/components/auth/ | Authentication UI | Login, signup, onboarding flows | 3 components | any-auth-* |
| src/components/dashboard/ | Dashboard UI | KPI cards, charts, activity feed | 3 components | client-home-* |
| src/components/clusters/ | Cluster Management | Cluster registry, details, actions | 2 components | client-cluster-* |
| src/components/templates/ | Templates UI | Node template management | 2 components | client-tmpl-* |
| src/components/policies/ | Policy UI | Optimization policy configuration | 1 component | client-pol-* |
| src/components/hibernation/ | Hibernation UI | Schedule management | 1 component | client-hib-* |
| src/components/audit/ | Audit UI | Audit logs and compliance | 1 component | client-audit-* |
| src/components/settings/ | Settings UI | Account and team settings | 2 components | client-set-* |
| src/components/admin/ | Admin UI | Admin dashboard, lab, health | 3 components | admin-* |
| src/services/ | API Clients | HTTP API communication services | 4 services | N/A |
| src/hooks/ | Custom Hooks | Reusable React hooks | 3 hooks | N/A |
| src/utils/ | Utilities | Formatters, validators, helpers | 2 utils | N/A |

---

## Component Table

| Subfolder | File Count | Status | Dependencies | Feature IDs |
|-----------|-----------|--------|--------------|-------------|
| src/components/auth/ | 0 | Pending | services/authService.js | any-auth-* |
| src/components/dashboard/ | 0 | Pending | services/metricsService.js | client-home-* |
| src/components/clusters/ | 0 | Pending | services/clusterService.js | client-cluster-* |
| src/components/templates/ | 0 | Pending | services/api.js | client-tmpl-* |
| src/components/policies/ | 0 | Pending | services/api.js | client-pol-* |
| src/components/hibernation/ | 0 | Pending | services/api.js | client-hib-* |
| src/components/audit/ | 0 | Pending | services/api.js | client-audit-* |
| src/components/settings/ | 0 | Pending | services/api.js | client-set-* |
| src/components/admin/ | 0 | Pending | services/api.js | admin-* |
| src/services/ | 0 | Pending | axios | N/A |
| src/hooks/ | 0 | Pending | React, services/ | N/A |
| src/utils/ | 0 | Pending | None | N/A |

---

## Recent Changes

### [2025-12-31 12:36:00] - Initial Frontend Structure Created
**Changed By**: LLM Agent
**Reason**: Create organized folder structure for React frontend components
**Impact**: Created frontend directory structure with component categories
**Files Modified**:
- Created frontend/src/components/auth/
- Created frontend/src/components/dashboard/
- Created frontend/src/components/clusters/
- Created frontend/src/components/templates/
- Created frontend/src/components/policies/
- Created frontend/src/components/hibernation/
- Created frontend/src/components/audit/
- Created frontend/src/components/settings/
- Created frontend/src/components/admin/
- Created frontend/src/services/
- Created frontend/src/hooks/
- Created frontend/src/utils/
- Created frontend/INFO.md (this file)
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
