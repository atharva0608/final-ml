# Frontend Pages Module

## Purpose

Full-page React components (route destinations).

**Last Updated**: 2025-12-25
**Authority Level**: MEDIUM

---

## Files

### SystemMonitor.jsx
**Purpose**: System monitoring dashboard page
**Lines**: ~550
**Route**: Likely `/system-monitor` or `/admin/system`

**Key Features**:
- Real-time system health monitoring
- Backend service status
- Database connection status
- API endpoint health checks
- Resource utilization metrics

**Components Used**:
- Dashboard layout
- Status indicators
- Metric charts
- Health check cards

**API Calls**:
- GET /api/system/health
- GET /api/system/metrics
- WebSocket connection for real-time updates

**Dependencies**:
- React
- frontend/src/layouts/DashboardLayout.jsx
- frontend/src/services/api.js
- Chart library (e.g., recharts)

**Recent Changes**: None recent

---

## Page Routing

```
App.jsx Routes:
  └─ /system-monitor → SystemMonitor.jsx
```

Note: Most pages are likely in `/frontend/src/components/` instead of `/frontend/src/pages/`. This folder appears to only contain system-level pages.

---

## Dependencies

### Depends On:
- React, React Router
- frontend/src/layouts/
- frontend/src/services/api.js
- Chart libraries

### Depended By:
- App.jsx (route definitions)
- Navigation components (links to pages)

**Impact Radius**: LOW (isolated pages)

---

## Recent Changes

### 2025-12-25: Governance Structure Establishment
**Files Changed**: None (metadata only)
**Reason**: Document existing pages
**Impact**: No code changes, documentation baseline
**Reference**: `/index/recent_changes.md`

---

## Usage

### Adding New Page
1. Create new `.jsx` file in this folder
2. Define page component
3. Add route in `App.jsx`
4. Add navigation link (if needed)
5. Update this info.md

### Example Page Structure
```javascript
import DashboardLayout from '../layouts/DashboardLayout';

export default function MyNewPage() {
  return (
    <DashboardLayout>
      <h1>My New Page</h1>
      {/* Page content */}
    </DashboardLayout>
  );
}
```

---

## Known Issues

### None

Pages module is stable as of 2025-12-25.

---

_Last Updated: 2025-12-25_
_Authority: MEDIUM - Page components_
