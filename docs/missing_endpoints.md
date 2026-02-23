# Resource Hygiene — Missing API Endpoints

After rewriting the Resource Hygiene UI (`CleanupDashboard.jsx`) to match the new `changelogic.md` design, the frontend now relies almost entirely on the `/api/v1/hygiene/scan` and `/api/v1/hygiene/total-cost` endpoints to render its categories, metrics, and tables. 

The existing `hygieneAPI` supports the core functionality (bulk tagging, authorization, resource deletion/termination). However, below are the missing backend capabilities based on the ideal scope of the robust UI design:

## 1. Tag Health History / Trend
- **Current State:** The UI shows a single snapshot gauge ("Tag Health 100%").
- **Missing Capability:** There is no endpoint that returns the historical trend of tag compliance (e.g., how the percentage changed over the last 30 days).
- **Proposed Endpoint:** `GET /api/v1/hygiene/tag-health-history` returning an array of `{ date, percentage, untagged_count }`.

## 2. Potential Savings Trend
- **Current State:** `hygiene_schemas.py` defines `previous_savings` and `savings_trend_percent`, but `/api/v1/hygiene/scan` does not actively compute cross-scan historical deltas for these properties.
- **Missing Capability:** We need to persist scan results or compute the delta between the current potential savings and last week's potential savings.
- **Proposed Solution:** Enhance the backend `HygieneService.scan_resources` logic to query historical scan snapshots from the database and populate the `previous_savings` and `savings_trend_percent` fields accurately.

## 3. Advanced Filtering Values
- **Current State:** Filtering by `Region` is supported by the API.
- **Missing Capability:** The frontend UI can filter by `status` (Safe to Delete, Risk, Orphaned, etc.) natively in memory, but if the resource list grows to massive scales (10,000+ resources), this text-based/status-based filtering should be handled server-side.
- **Proposed Endpoint Update:** Add `status` and `search` query parameters to `GET /api/v1/hygiene/scan`.
