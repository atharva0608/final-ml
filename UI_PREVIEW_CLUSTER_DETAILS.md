# Cluster Details Page - UI Preview

## Updated Overview Tab Layout

```
┌─────────────────────────────────────────────────────────────────────┐
│  Cluster Name: spot-demo-1                    [Instant Rebalance]  │
│  ap-south-1 • AWS                              [Refresh] [✕]       │
├─────────────────────────────────────────────────────────────────────┤
│  [Overview] [AtharvaAI] [Rightsizing] [Node Template] [Activity]   │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │  Status Overview                                             │  │
│  ├─────────────────────────────────────────────────────────────┤  │
│  │  Status: [ACTIVE]    Cluster ID: 27dd2ba...                 │  │
│  │  Created: 2024-01-15  Last Heartbeat: 2024-02-26 06:45     │  │
│  └─────────────────────────────────────────────────────────────┘  │
│                                                                      │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │  🔄 Utilization                                    ← NEW     │  │
│  ├─────────────────────────────────────────────────────────────┤  │
│  │                                                               │  │
│  │   6.0%          121.1%         2            2       0.01/0.23│  │
│  │   CPU           Memory         Pods         Nodes   Avg CPU/ │  │
│  │   Utilization   Utilization                         Mem      │  │
│  │   0.01 cores    0.23 GB                            cores/GB  │  │
│  │                                                       per pod  │  │
│  └─────────────────────────────────────────────────────────────┘  │
│                                                                      │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │  💾 Workload Classification                       ← NEW     │  │
│  ├─────────────────────────────────────────────────────────────┤  │
│  │  Workload Type    PVC Pods           StatefulSet Pods       │  │
│  │  [STATELESS]      0 / 2              0 / 2                  │  │
│  │                   Pods with PVCs     StatefulSet workloads   │  │
│  │                                                               │  │
│  │  ┌──────────────────────────────────────────────────────┐   │  │
│  │  │ Analysis: All workloads are stateless - safe for    │   │  │
│  │  │ aggressive spot optimization                         │   │  │
│  │  │                                                       │   │  │
│  │  │ Spot Optimization: ✅ Recommended                    │   │  │
│  │  └──────────────────────────────────────────────────────┘   │  │
│  └─────────────────────────────────────────────────────────────┘  │
│                                                                      │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │  🔍 Cluster Metrics                                          │  │
│  ├─────────────────────────────────────────────────────────────┤  │
│  │  Total Instances: 2    Spot: 1    On-Demand: 1              │  │
│  │  Monthly Cost: $145.44  Savings: $72.80  Avg CPU: 6%        │  │
│  └─────────────────────────────────────────────────────────────┘  │
│                                                                      │
│  ... (rest of existing sections) ...                                │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Color Scheme Reference

### Utilization Metrics
```
┌─────────────────────────────────────────────────────────────────┐
│  6.0%          121.1%         2            2       0.01 / 0.23  │
│  ████           ████          ████         ████    ████         │
│  Blue-600      Purple-600    Green-600   Orange-  Indigo-600   │
│  (#2563EB)     (#9333EA)     (#16A34A)   600      (#4F46E5)    │
│                                           (#EA580C)             │
└─────────────────────────────────────────────────────────────────┘
```

### Workload Type Badges
```
[STATELESS]  → Green-600  (#16A34A)  ✅ Safe for spot
[STATEFUL]   → Red-600    (#DC2626)  ⚠️  Use caution
[MIXED]      → Yellow-600 (#CA8A04)  🔶 Selective optimization
[UNKNOWN]    → Gray-500   (#6B7280)  ❓ No data
```

---

## Responsive Layout

### Desktop (>= 1024px)
- 5 columns for Utilization metrics
- 3 columns for Workload Classification
- Side-by-side cards in grid layout

### Tablet (768px - 1023px)
- 5 columns for Utilization (wraps nicely)
- 3 columns for Workload Classification
- Stacked cards with full width

### Mobile (<= 767px)
- 2 columns for Utilization (2-2-1 layout)
- 1 column for Workload Classification
- Vertical stacking

---

## Interactive States

### Loading State
```
┌─────────────────────────────────────┐
│  🔄 Utilization                     │
├─────────────────────────────────────┤
│  [Spinning loader animation]        │
│  Loading utilization data...        │
└─────────────────────────────────────┘
```

### Error State
```
┌─────────────────────────────────────┐
│  🔄 Utilization                     │
├─────────────────────────────────────┤
│  ⚠️  Failed to load utilization    │
│  [Retry Button]                     │
└─────────────────────────────────────┘
```

### No Data State
```
┌─────────────────────────────────────┐
│  🔄 Utilization                     │
├─────────────────────────────────────┤
│  ℹ️  No utilization data available │
│  Agent may not be installed         │
└─────────────────────────────────────┘
```

---

## Example Data Scenarios

### Scenario 1: Stateless Cluster (Web App)
```
Workload Type: [STATELESS] (Green)
PVC Pods: 0 / 15
StatefulSet Pods: 0 / 15
Analysis: All workloads are stateless - safe for aggressive spot optimization
Spot Optimization: ✅ Recommended
```

### Scenario 2: Stateful Cluster (Database)
```
Workload Type: [STATEFUL] (Red)
PVC Pods: 8 / 8
StatefulSet Pods: 8 / 8
Analysis: Cluster has stateful workloads (PVCs/StatefulSets) - use caution with spot
Spot Optimization: ⚠️  Use with caution
```

### Scenario 3: Mixed Workload (Microservices + DB)
```
Workload Type: [MIXED] (Yellow)
PVC Pods: 3 / 12
StatefulSet Pods: 3 / 12
Analysis: Cluster has both stateful and stateless workloads - selective optimization
Spot Optimization: 🔶 Recommended for stateless pods
```

### Scenario 4: New Cluster (No Metrics)
```
Workload Type: [UNKNOWN] (Gray)
PVC Pods: 0 / 0
StatefulSet Pods: 0 / 0
Analysis: Unable to determine workload type - no pod data available
Spot Optimization: ❓ Install agent first
```

---

## Animation Details

### On Page Load
1. Fade-in animation (300ms) for each card
2. Number count-up animation for metrics (500ms)
3. Badge color transition (200ms)

### On Refresh
1. Spinning refresh icon
2. Pulse animation on updating cards
3. Smooth number transitions

### Hover Effects
- Card shadow increases (elevation)
- Metrics slightly enlarge (scale: 1.02)
- Cursor: pointer on clickable elements

---

## Accessibility Features

- ✅ ARIA labels on all metrics
- ✅ Color contrast ratio > 4.5:1 (WCAG AA)
- ✅ Keyboard navigation support
- ✅ Screen reader announcements
- ✅ Focus indicators on interactive elements
- ✅ Semantic HTML (section, article, h3 headings)

---

## Performance Metrics

### Initial Load
- Time to Interactive: < 2s
- First Contentful Paint: < 1s
- Largest Contentful Paint: < 2.5s

### Data Refresh
- API call: ~50ms
- UI update: ~100ms
- Total refresh: < 200ms

---

## Browser Compatibility

| Browser | Version | Status |
|---------|---------|--------|
| Chrome | ≥90 | ✅ Fully supported |
| Firefox | ≥88 | ✅ Fully supported |
| Safari | ≥14 | ✅ Fully supported |
| Edge | ≥90 | ✅ Fully supported |
| Mobile Safari | ≥14 | ✅ Fully supported |
| Chrome Mobile | ≥90 | ✅ Fully supported |

---

## CSS Classes Used

### Utilization Section
```css
.text-3xl      /* 30px font for main metrics */
.font-bold     /* 700 font weight */
.text-blue-600 /* CPU color */
.text-purple-600 /* Memory color */
.text-green-600  /* Pod count color */
.text-orange-600 /* Node count color */
.text-indigo-600 /* Average color */
.text-sm       /* 14px for labels */
.text-xs       /* 12px for secondary text */
.text-gray-600 /* Label color */
```

### Workload Classification
```css
.bg-gray-50    /* Analysis box background */
.rounded-lg    /* 8px border radius */
.p-3           /* 12px padding */
.text-sm       /* 14px for description */
.font-semibold /* 600 font weight for numbers */
```

---

## Integration Points

### Dependencies
- Requires agent to be installed and sending pod metrics
- Uses `pod_metrics` table for real-time data
- Leverages `workload_inspector.py` for classification

### Data Flow
```
Agent DaemonSet → POST /api/v1/pod-metrics/batch
                ↓
        pod_metrics table
                ↓
GET /api/v1/clusters/{id}/utilization ← Frontend
GET /api/v1/clusters/{id}/workload-type
                ↓
        ClusterDetails.jsx
                ↓
    Rendered UI sections
```

---

## Testing Checklist

- [x] Backend endpoints return correct data
- [x] Frontend components render without errors
- [x] Loading states display properly
- [x] Error handling works (404, 500)
- [x] Responsive layout on all screen sizes
- [x] Color scheme matches design system
- [x] Accessibility compliance (WCAG AA)
- [x] Performance benchmarks met
- [x] Cross-browser compatibility verified
- [ ] User acceptance testing (UAT)
- [ ] Documentation updated

---

## Next Steps

1. **User Testing** - Gather feedback on UI clarity
2. **Performance Monitoring** - Track API response times
3. **Feature Enhancement** - Add historical trend charts
4. **Documentation** - Update user guide with screenshots

