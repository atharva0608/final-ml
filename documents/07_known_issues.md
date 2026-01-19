# Known Issues & Limitations
**Last Updated:** 2026-01-19

This document tracks known limitations, pending implementations, and technical debt in the codebase.

## Backend Limitations

### Core Execution Logic
*   **Action Executor** (`backend/core/action_executor.py`):
    *   `_execute_right_size`: Logic is currently a stub (returns simulated success). Needs to implement instance stop/change-type/start workflow.
    *   `_execute_consolidation`: Logic is currently a stub. Needs to implement node cordon/drain/terminate workflow.
    *   `_execute_scale_down` / `_execute_scale_up`: ASG scaling logic is pending implementation.
    *   `_execute_spot_replacement`: Mostly implemented but requires robust waiter logic for instance launch and proper Kubernetes node draining integration.

### Cost & Metrics
*   **Metrics Service** (`backend/services/metrics_service.py`):
    *   `_calculate_savings`: Savings calculation currently assumes a flat **70% discount** for Spot instances compared to On-Demand. This should be updated to use real pricing data delta from `pricing_collector`.

### Service Layer
*   **Settings Service** (`backend/services/settings_service.py`):
    *   Integrations (Slack, PagerDuty) are currently stored in an in-memory dictionary (`_MOCK_INTEGRATIONS_DB`). Needs proper database table implementation.

## Frontend Limitations
*   **Billing Page**: The billing history and plan details are currently using mock data. Needs implementation against Stripe or similar provider.
