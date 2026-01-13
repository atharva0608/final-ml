# Frontend-Backend Gap Analysis
**Date:** 2026-01-13 (Last Updated)
**Scope:** `frontend/src/services/api.js` vs `backend/api/*.py`

This document outlines the discrepancies found between the Frontend's expected API calls and the Backend's actual routes.

## Summary
| Category | Count | Description |
| :--- | :--- | :--- |
| **Real APIs** | 40+ | Endpoints that exist and are correctly linked (includes Mocked logic). |
| **Missing / Fake APIs** | 0 | Endpoints called by Frontend but **NOT** implemented in Backend. |
| **Zombie APIs** | 1 | Backend endpoints that exist but appear unused. |

## 1. Missing / Fake APIs (Frontend calls -> 404/Function Missing)
*None detected.* All core frontend API calls now have corresponding backend routes (validated 2026-01-13).

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

### Newly Implemented APIs (2026-01-13)
*   **Governance**: Get Policies, Update Policies, Run Autopilot (NEW - Feature 4).
*   **Cleanup / Dependencies**: `check-dependencies` pre-flight verification (NEW - Feature 1).
*   **Cleanup / Tag Compliance**: `is_compliant`, `missing_tags`, `untagged_waste_cost` in scan results (NEW - Feature 2).
*   **Approvals**: Pending request management (List, Approve, Reject) - Feature 3.

### Previously Implemented APIs (2026-01-12)
*   **Accounts**: Link, Validate, Set Default, Disconnect, List.
*   **Billing**: Create Portal Session, Webhook, Status.
*   **Onboarding**: Get State, AWS Link, Verify (+ triggers discovery), Skip.
*   **Cleanup**: Resource Hygiene scanning and action execution (Multi-Region).
*   **Templates**: CloudFormation template listing and download.

### Status Notes
| Feature | Backend Status | Notes |
| :--- | :--- | :--- |
| **Governance (Autopilot)** | **Real** | NEW: Policy-as-Code auto-cleanup with "System Autopilot" actor. |
| **Dependency Check** | **Real** | NEW: Pre-flight verification for Snapshots (AMI refs), SGs (ENI refs), Volumes (attachments). |
| **Tag Compliance** | **Real** | NEW: `Organization.required_tags` checked during scan, `is_compliant` + `missing_tags` returned. |
| **Cleanup** | **Real** | Full implementation with parallel scanning, caching, tag compliance, dependency checks. |
| **Approvals** | **Real** | Four-Eyes approval workflow for Members and Strict Mode. |

## 3. Resolved Gaps (2026-01-13)

| Component | Previous Status | New Status |
| :--- | :--- | :--- |
| **Governance** | Not Implemented | **Real**: GovernanceService + API routes for policy management |
| **Dependency Check** | Not Implemented | **Real**: CleanupService.check_dependencies() + API endpoint |
| **Tag Compliance** | Not Implemented | **Real**: is_compliant, missing_tags enrichment during scan |
| **Approval Workflow** | Already Implemented | ✅ Verified working |

## 4. Remaining Zombie APIs
| Component | Status | Reason |
| :--- | :--- | :--- |
| **ML Model Server** | **Standalone** | Implemented but not integrated into prediction flow. |

## 5. Recommendations
1. ~~Implement Dependency Check~~ ✅ Done (2026-01-13)
2. ~~Implement Tag Compliance~~ ✅ Done (2026-01-13)
3. ~~Implement Governance Service~~ ✅ Done (2026-01-13)
4. **Configure Stripe Keys**: Add `STRIPE_SECRET_KEY` to `.env` for billing.
5. **Connect ML Model Server**: Wire predictions into Lab experiments.
6. **Schedule Autopilot Worker**: Add Celery beat task for periodic governance runs.
