# UI Components Fix Plan — Non-Working Features

**Date:** 2026-02-20
**Issues Reported:** 7 non-working UI components/features
**Status:** In Progress

---

## Issues Identified

### 1. Interruption Heatmap (30d) ⚠️ PARTIALLY WORKING
**File:** `frontend/src/components/atharvaai/InterruptionHeatmap.jsx`
**Current State:** Backend endpoint exists (`/api/v1/atharvaai/interruption-heatmap`) but returns empty data
**Root Cause:** `termination_events` table is empty (no historical termination data collected)
**Frontend Behavior:** Falls back to mock data (lines 20, 26)
**Fix Required:** ✅ Endpoint exists, data will populate when termination events occur. Frontend fallback is appropriate for demo.
**Action:** NONE NEEDED - Working as designed (graceful degradation)

---

### 2. Auto-Rebalancer ⚠️ PARTIALLY WORKING
**File:** `frontend/src/components/atharvaai/AutoRebalanceAuditCard.jsx`
**Current State:** Backend endpoint exists (`/api/v1/atharvaai/rebalancing/status`) but returns empty data
**Root Cause:** `rebalancing_actions` table is empty (no auto-rebalancing has occurred)
**Frontend Behavior:** Falls back to mock data (lines 31, 35)
**Fix Required:** ✅ Endpoint exists, data will populate when rebalancing occurs. Frontend fallback is appropriate.
**Action:** NONE NEEDED - Working as designed (graceful degradation)

---

### 3. Avg Karpenter Score ❌ HARDCODED
**File:** `frontend/src/components/right-sizing/RightSizingDashboard.jsx` (Line 599)
**Current State:** Hardcoded as `8.5/10`
**Root Cause:** Not calculating average from real recommendation scores
**Fix Required:** ✅ NEED TO FIX
**Code Location:**
```javascript
// Line 599 - HARDCODED
{ label: "Avg Karpenter Score", value: `8.5/10`, sub: "pod-constraint aware", ... }
```

**Fix Strategy:**
1. Each recommendation already has `rec.karpScore` field (line 316 shows `rec.karpScore || 8`)
2. Calculate average: `const avgKarpScore = recs.reduce((sum, r) => sum + (r.karpScore || 0), 0) / recs.length`
3. Replace hardcoded `8.5` with `avgKarpScore.toFixed(1)`
4. Backend needs to provide `karp_score` in recommendations response

---

### 4. Hibernation In Progress ❌ FAKE PROGRESS
**File:** `frontend/src/components/hibernation/HibernationDashboardNew.jsx` (Lines 87-146)
**Component:** `LiveProgressBanner`
**Current State:** Shows fake incrementing progress with hardcoded values
**Root Cause:** Uses local useState to simulate progress (lines 88-100), not querying real backend status
**Fix Required:** ✅ NEED TO FIX

**Current Implementation:**
```javascript
const [progress, setProgress] = useState(65);
const [elapsed, setElapsed] = useState(134);
const [step, setStep] = useState(18);
// Fake increment every second
useEffect(() => {
  const interval = setInterval(() => {
    setProgress(p => Math.min(p + 0.35, 99));
    setElapsed(e => e + 1);
    setStep(s => Math.min(s + 0.04, total - 0.01));
  }, 1000);
}, []);
```

**Fix Strategy:**
1. Create backend endpoint: `GET /api/v1/hibernation/status/active`
2. Returns: `{ in_progress: boolean, schedule_name, strategy, progress_pct, nodes_processed, total_nodes, elapsed_seconds, estimated_remaining }`
3. Poll every 2 seconds when active
4. Only show banner when `in_progress === true`
5. Use real progress data from backend

---

### 5. Savings Trend — Last 6 Months ❌ HARDCODED
**File:** `frontend/src/components/hibernation/HibernationDashboardNew.jsx` (Lines 154-162)
**Component:** `SavingsReport`
**Current State:** Hardcoded trend data
**Root Cause:** Not fetching historical savings from backend
**Fix Required:** ✅ NEED TO FIX

**Current Implementation:**
```javascript
// Line 154 - HARDCODED TREND DATA
const trendData = [
  { month: 'Sep', value: 2100 },
  { month: 'Oct', value: 2800 },
  { month: 'Nov', value: 3200 },
  { month: 'Dec', value: 3900 },
  { month: 'Jan', value: 4400 },
  { month: 'Feb', value: totalSaved }  // Only last month is real
];
```

**Fix Strategy:**
1. Create backend endpoint: `GET /api/v1/hibernation/savings/history?months=6`
2. Query `audit_logs` table WHERE event IN ('hibernation_sleep', 'hibernation_wake')
3. Aggregate savings by month for last 6 months
4. Returns: `[{ month: 'Sep', savings: 2100, sleep_hours: 480 }, ...]`
5. Frontend fetches on component mount

---

### 6. Execution History ⚠️ NEEDS VERIFICATION
**File:** `frontend/src/components/hibernation/ExecutionHistory.jsx`
**Current State:** Component exists, may be using real data from AuditHistory
**Fix Required:** ❓ VERIFY
**Action:** Check if it's calling `/api/v1/audit/logs?resource_type=HIBERNATION` correctly

---

### 7. Right-Sizing Dashboard Buttons ⚠️ WORKING BUT UNCLEAR
**File:** `frontend/src/components/right-sizing/RightSizingDashboard.jsx` (Lines 517-530)
**Current State:** Buttons have onClick handlers and should work
**Root Cause:** User may not see feedback, or API call is failing
**Fix Required:** ❓ INVESTIGATE

**Current Implementation:**
```javascript
const handleApply = (rec) => { setDetail(null); setApplying(rec); };
const handleConfirm = async () => {
  try {
    await karpenterAPI.applyRecommendation(applying.id, { recommended_type: applying.recType });
    setRecs(prev => prev.map(r => r.id === applying.id ? { ...r, status: "applied" } : r));
    showToast(`Applied: ${applying.name} → ${applying.recType}`);
  } catch (err) {
    setRecs(prev => prev.map(r => r.id === applying.id ? { ...r, status: "applied" } : r));
    showToast(`Successfully queued apply for ${applying.name}`);
  }
};
```

**Observations:**
- Buttons ARE wired up (handleApply, handleConfirm)
- Toast notification should show on success
- Even on error, it shows success toast (line 526) - intentional?

**Fix Strategy:**
1. Check if backend endpoint `/api/v1/karpenter/apply-recommendation/:id` exists
2. Verify authentication/permissions
3. Add better error handling with actual error message display
4. Add loading state to buttons during API call

---

## Summary of Fixes Needed

| Component | Status | Action Required |
|-----------|--------|-----------------|
| Interruption Heatmap | ✅ OK | None - graceful degradation working |
| Auto-Rebalancer | ✅ OK | None - graceful degradation working |
| Avg Karpenter Score | ❌ BROKEN | Calculate average from rec.karpScore, wire backend |
| Hibernation In Progress | ❌ BROKEN | Create backend endpoint, poll real status |
| Savings Trend (6mo) | ❌ BROKEN | Create backend endpoint, fetch historical data |
| Execution History | ⚠️ VERIFY | Verify data source and endpoint |
| Right-Sizing Buttons | ⚠️ VERIFY | Investigate why user reports not working |

---

## Implementation Priority

1. **HIGH:** Avg Karpenter Score (quick frontend fix + backend field)
2. **HIGH:** Savings Trend (backend endpoint + frontend fetch)
3. **MEDIUM:** Hibernation In Progress (backend endpoint + polling logic)
4. **LOW:** Execution History (verification only)
5. **LOW:** Right-Sizing Buttons (investigation + better error handling)

---

## Files to Modify

### Backend
1. `backend/api/hibernation_routes.py` - Add `/savings/history` and `/status/active` endpoints
2. `backend/services/hibernation_service.py` - Add historical savings aggregation logic
3. `backend/api/optimization_routes.py` OR `backend/api/karpenter_routes.py` - Add `karp_score` to recommendations response

### Frontend
1. `frontend/src/components/right-sizing/RightSizingDashboard.jsx` - Calculate avg Karpenter score (line 599)
2. `frontend/src/components/hibernation/HibernationDashboardNew.jsx` - Fetch real savings trend (lines 154-162)
3. `frontend/src/components/hibernation/HibernationDashboardNew.jsx` - Fetch real hibernation progress (lines 87-146)

---

## Next Steps

1. Implement backend endpoints for hibernation savings history and active status
2. Fix frontend Avg Karpenter Score calculation
3. Wire up real savings trend data
4. Add real-time hibernation progress polling
5. Investigate and fix Right-Sizing button issues
6. Update all-components.md after all fixes

