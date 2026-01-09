# Frontend-Backend Gap Analysis
**Date:** 2026-01-09
**Scope:** `frontend/src/services/api.js` vs `backend/api/*.py`

This document outlines the discrepancies found between the Frontend's expected API calls and the Backend's actual routes.

## Summary
| Category | Count | Description |
| :--- | :--- | :--- |
| **Real APIs** | 25+ | Endpoints that exist and are correctly linked. |
| **Missing / Fake APIs** | 6 | Endpoints called by Frontend but **NOT** implemented in Backend. |
| **Zombie APIs** | 3 | Backend endpoints that exist but appear unused. |

## 1. Missing / Fake APIs (Frontend calls -> 404/Function Missing)
These are critical gaps where the Frontend calls an endpoint that does not exist in the defined backend routes.

| Frontend Method | Expected URL | Status | Fix Required |
| :--- | :--- | :--- | :--- |
| `accountAPI.validate(id)` | `POST /api/v1/accounts/{id}/validate` | **MISSING** | Implement logic to validate AWS credentials/role on demand. |
| `accountAPI.setDefault(id)` | `POST /api/v1/accounts/{id}/set-default` | **MISSING** | Implement "Default Account" logic in User model and API. |
| `settingsAPI.getProfile()` | `GET /api/v1/settings/profile` | **MISSING** | `settings_routes.py` does not exist. Use `auth_routes.me` or create new route? |
| `settingsAPI.updateProfile()` | `PATCH /api/v1/settings/profile` | **MISSING** | No endpoint to update user profile details. |
| `settingsAPI.getIntegrations()` | `GET /api/v1/settings/integrations` | **MISSING** | No Integrations model or service exists. |
| `settingsAPI.addIntegration()` | `POST /api/v1/settings/integrations` | **MISSING** | No Integrations model or service exists. |

## 2. Real APIs (Verified Matches)
These endpoints are correctly implemented and linked.

*   **Auth**: Login, Signup, Me, Refresh, Change Password.
*   **Clusters**: List, Get, Update, Delete, Connect AWS.
*   **Admin**: List Clients, Toggle Client, Stats, Reset Password.
    *   *Note*: `listOrganizations` exists as `get_organizations` in `admin_routes.py`.
*   **Metrics**: Global, Cluster-specific.
*   **Lab**: Experiments CRUD.
*   **Policies**: CRUD.
*   **Hibernation**: Schedule Management.

## 3. Recommendations
1.  **Implement Settings Routes**: Create `backend/api/settings_routes.py` to handle Profile and Integrations, or remove them from Frontend if out of scope.
2.  **Fix Account Routes**: Add `validate` and `set_default` endpoints to `backend/api/account_routes.py`.
3.  **Clean up Frontend**: If "Integrations" feature is not planned for v1, remove `settingsAPI.getIntegrations` calls from Frontend.
