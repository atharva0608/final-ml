# Frontend-Backend Gap Analysis
**Date:** 2026-01-12 (Last Updated)
**Scope:** `frontend/src/services/api.js` vs `backend/api/*.py`

This document outlines the discrepancies found between the Frontend's expected API calls and the Backend's actual routes.

## Summary
| Category | Count | Description |
| :--- | :--- | :--- |
| **Real APIs** | 37+ | Endpoints that exist and are correctly linked (includes Mocked logic). Cleanup API with multi-region scanning added. |
| **Missing / Fake APIs** | 0 | Endpoints called by Frontend but **NOT** implemented in Backend. |
| **Zombie APIs** | 1 | Backend endpoints that exist but appear unused. |

## 1. Missing / Fake APIs (Frontend calls -> 404/Function Missing)
*None detected.* All core frontend API calls now have corresponding backend routes (validated 2026-01-12).

## 2. Real APIs (Verified Matches)

### Core APIs
*   **Auth**: Login, Signup, Me, Refresh, Change Password.
*   **Clusters**: List, Get, Update, Delete, Connect AWS, Discovery.
*   **Admin**: List Clients, Toggle Client, Stats, Reset Password.
*   **Metrics**: Global, Cluster-specific.
*   **Lab**: Experiments CRUD.
*   **Policies**: CRUD + Toggle.
*   **Hibernation**: Schedule Management.
*   **Audit**: Activity logs.

### Newly Implemented APIs (2026-01-12)
*   **Accounts**: Link, Validate, Set Default, **Disconnect** (NEW), List.
*   **Billing**: Create Portal Session, Webhook, Status (NEW).
*   **Onboarding**: Get State, AWS Link, Verify (+ triggers discovery), Skip.
*   **Optimization**: Rightsizing recommendations.
*   **Health**: System health status.
*   **Cleanup**: **Resource Hygiene** (NEW) - Multi-region AWS scanning for orphaned resources (GET /scan/{account_id}), Execute cleanup actions (POST /action/{account_id}).

### Status Notes
| Feature | Backend Status | Notes |
| :--- | :--- | :--- |
| Account Disconnect | **Real** | Strips credentials, sets status to DISCONNECTED, preserves history. |
| Connection Health | **Real** | `last_sync_at`, `sync_status`, `sync_error` tracked by discovery worker. |
| Billing Portal | **Partial** | Stripe integration scaffolded, requires API key config. |
| Platform Identity | **Real** | NEW: Admin AWS credential management with STS verification. |
| Settings | **Mocked** | Profile/Integrations use in-memory mock. |

## 3. Resolved Gaps (2026-01-12)

| Component | Previous Status | New Status |
| :--- | :--- | :--- |
| **AccountService** | Mock Logic | **Real**: boto3 STS assume_role verification |
| **ClusterService** | Fake Discovery | **Real**: EKS list_clusters + describe_cluster |
| **Onboarding→Discovery** | Disconnected | **Real**: /verify creates Account + triggers discovery |
| **PricingCollector** | Zombie | **Connected**: via pricing_task Celery worker |
| **SpotAdvisorScraper** | Zombie | **Connected**: via pricing_task Celery worker |

## 4. Remaining Zombie APIs
| Component | Status | Reason |
| :--- | :--- | :--- |
| **ML Model Server** | **Standalone** | Implemented but not integrated into prediction flow. |

## 5. Recommendations
1. ~~Connect Pricing Worker~~ ✅ Done
2. ~~Implement Account Validation~~ ✅ Done
3. **Configure Stripe Keys**: Add `STRIPE_SECRET_KEY` to `.env` for billing.
4. **Connect ML Model Server**: Wire predictions into Lab experiments.
