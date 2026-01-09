# Frontend-Backend Gap Analysis
**Date:** 2026-01-09
**Scope:** `frontend/src/services/api.js` vs `backend/api/*.py`

This document outlines the discrepancies found between the Frontend's expected API calls and the Backend's actual routes.

## Summary
| Category | Count | Description |
| :--- | :--- | :--- |
| **Real APIs** | 31+ | Endpoints that exist and are correctly linked (includes Mocked logic). |
| **Missing / Fake APIs** | 0 | Endpoints called by Frontend but **NOT** implemented in Backend. |
| **Zombie APIs** | 3 | Backend endpoints that exist but appear unused. |

## 1. Missing / Fake APIs (Frontend calls -> 404/Function Missing)
*None detected.* All core frontend API calls now have corresponding backend routes (validated 2026-01-09).

## 2. Real APIs (Verified Matches)
These endpoints are correctly implemented and linked.

*   **Auth**: Login, Signup, Me, Refresh, Change Password.
*   **Clusters**: List, Get, Update, Delete, Connect AWS.
*   **Admin**: List Clients, Toggle Client, Stats, Reset Password.
    *   *Note*: `listOrganizations` exists as `get_organizations` in `admin_routes.py`.
*   **Metrics**: Global, Cluster-specific.
*   **Lab**: Experiments CRUD.
*   **Policies**: CRUD.
*   **Policies**: CRUD.
*   **Hibernation**: Schedule Management.
*   **Settings**: Profile and Integrations (Logic is **Mocked** but routes exist).
*   **Accounts**: Validate and Set Default (Routes exist, validation logic is **Mocked**).

## 3. Operational Gaps (Backend Audit)
These are backend components that exist but are disconnected or simplified, affecting frontend data quality.

| Component | Status | Impact on Frontend |
| :--- | :--- | :--- |
| **Pricing Collector** | **Disconnected** | Pricing data in dashboards may be stale or empty (Worker task not registered). |
| **ML Model Server** | **Standalone** | Lab experiments use mocked prediction logic, not real-time inference. |
| **Metrics Service** | **Simplified** | Savings charts use hardcoded assumptions (70% spot discount), not real billing data. |
| **Admin Service (Billing)** | **Mocked Data** | Billing page displays static/mocked invoice data, not connected to Stripe/AWS Cost Explorer. |

## 4. Recommendations
1.  **Connect Pricing Worker**: Register `pricing_collector` tasks in `workers/app.py` to ensure fresh data.
2.  **Implement Real Logic**: Replace `SettingsService` and `AccountService` mock/stub logic with real implementations when ready.
