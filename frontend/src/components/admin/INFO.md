# Admin Components - Component Information

> **Last Updated**: 2025-12-31 12:36:00
> **Maintainer**: LLM Agent

## Folder Purpose
Admin portal UI including dashboard, lab for A/B testing, and system health monitoring.

## Planned Components
- **AdminDashboard.jsx**: Admin overview (admin-dash-kpi-reuse-indep-view-global, admin-client-list-unique-indep-view-reg)
- **TheLab.jsx**: ML model A/B testing (admin-lab-form-reuse-dep-submit-live, admin-lab-chart-unique-indep-view-abtest)
- **SystemHealth.jsx**: System health monitoring (admin-health-traffic-unique-indep-view-workers)

## APIs Used
- GET /admin/clients
- GET /admin/stats
- GET /admin/health
- POST /admin/impersonate
- POST /lab/parallel
- POST /lab/graduate
- WS /lab/stream/{id}

## Schemas
- SCHEMA-ADMIN-ClientList
- SCHEMA-ADMIN-Stats
- SCHEMA-LAB-ABTestConfig
- SCHEMA-LAB-ABResults
