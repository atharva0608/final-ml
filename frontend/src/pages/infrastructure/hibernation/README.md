# Hibernation Components Documentation

## Overview

The Hibernation feature allows automated sleep/wake cycles for Kubernetes clusters to reduce costs during non-business hours. This directory contains all frontend components for managing hibernation schedules.

## Architecture

### Component Hierarchy

```
HibernationDashboard (Main)
├── StatusBanner (Real-time status)
├── ScheduleModal
│   ├── StrategySelector (Step 2)
│   └── ScheduleBuilder (Step 4)
│       └── ScheduleCalendar
├── ExecutionHistory
├── ConflictDetectionModal
├── CostAnalyticsDashboard
├── NotificationSettings
└── EmergencyControls
```

### Data Flow

```
User Action → Component → hibernationApi → Backend API → Celery Worker → Kubernetes/AWS
                                              ↓
                                           Database
                                              ↓
                                        SSE Events → StatusBanner
```

## Components

### 1. HibernationDashboard

**Purpose**: Main dashboard showing all hibernation schedules

**Features**:
- Weekly summary (sleep hours, savings, active/paused counts)
- Active schedules list with strategy badges
- Paused schedules section
- Action buttons (Pause/Resume, Edit, History, Delete)
- Empty state

**Props**: None (standalone page)

**Usage**:
```javascript
import { HibernationDashboard } from './components/hibernation';

<HibernationDashboard />
```

### 2. ScheduleModal

**Purpose**: Multi-step wizard for creating/editing schedules

**Features**:
- 4-step wizard (Basic Info → Strategy → Clusters → Schedule)
- Progress indicator
- Form validation
- Integration with sub-components

**Props**:
- `isOpen` (boolean): Show/hide modal
- `onClose` (function): Callback when closed
- `schedule` (object): Existing schedule for edit mode
- `clusters` (array): Available clusters

**Usage**:
```javascript
<ScheduleModal
  isOpen={isOpen}
  onClose={(refresh) => { setIsOpen(false); if (refresh) loadSchedules(); }}
  schedule={editingSchedule}
  clusters={clusters}
/>
```

### 3. StrategySelector

**Purpose**: Display and select hibernation strategy

**Features**:
- Strategy cards with icons, descriptions
- Savings %, wake time, risk level
- Recommended badge
- Dynamic loading from API with fallback

**Props**:
- `selected` (string): Currently selected strategy
- `onSelect` (function): Callback when strategy selected

**Strategies**:
- **NAMESPACE_SLEEP**: Scale workload replicas to 0 (80% savings, 2min wake, low risk)
- **NUCLEAR**: Terminate worker nodes (70% savings, 5min wake, medium risk)
- **SNAPSHOT_RESTORE**: Full cluster shutdown (95% savings, 15min wake, high risk)

### 4. ScheduleBuilder

**Purpose**: Build schedule matrix with calendar integration

**Features**:
- Interactive calendar
- Timezone selector
- Pre-warm time configuration
- Schedule tips

**Props**:
- `scheduleMatrix` (string): 168-character binary string
- `onChange` (function): Callback when matrix changes
- `timezone` (string): Selected timezone
- `onTimezoneChange` (function): Timezone change callback
- `preWarmMinutes` (number): Pre-warm time
- `onPreWarmChange` (function): Pre-warm change callback

### 5. ScheduleCalendar

**Purpose**: Visual weekly calendar with hourly granularity

**Features**:
- Week view (7 days × 24 hours grid)
- Compact view (progress bars per day)
- Click to toggle sleep/awake states
- Quick action buttons (templates)
- Hover tooltips
- Stats summary

**Props**:
- `schedule` (object): Schedule with schedule_matrix
- `editable` (boolean): Allow editing cells
- `onChange` (function): Callback when matrix changes

**Matrix Format**:
- 168-character string (7 days × 24 hours)
- '0' = Awake, '1' = Sleeping
- Example: `"000000000011111111110000000000..."` (Mon 0-9am awake, 10am-6pm sleep, etc.)

### 6. ExecutionHistory

**Purpose**: Timeline of all hibernation actions

**Features**:
- Action cards (Sleep/Wake/Prewarm)
- Status badges (Success/Error/In Progress)
- Duration and cost saved
- Filter by action type and time range
- Auto-refresh every 30s

**Props**:
- `scheduleId` (string, optional): Filter to specific schedule
- `limit` (number): Max entries to show

### 7. StatusBanner

**Purpose**: Real-time status using Server-Sent Events

**Features**:
- Live status indicator
- Active action displays
- Progress spinners
- Error messages
- SSE connection management

**Props**: None (standalone component)

**SSE Endpoint**: `GET /api/v1/sse/hibernation`

### 8. ConflictDetectionModal

**Purpose**: Show schedule conflicts before creation

**Features**:
- Conflict cards with severity (Critical/Warning/Info)
- Affected clusters and time windows
- Recommendations
- Prevent save on critical conflicts

**Props**:
- `isOpen` (boolean): Show/hide modal
- `onClose` (function): Close callback
- `conflicts` (array): Conflict objects
- `onConfirm` (function): Proceed despite warnings

**Conflict Types**:
- OVERLAPPING_SLEEP
- OVERLAPPING_WAKE
- RAPID_TRANSITIONS
- CLUSTER_OVERLOAD

### 9. CostAnalyticsDashboard

**Purpose**: Detailed hibernation cost analytics

**Features**:
- Summary cards (Total Saved, Projections, Sleep Hours, ROI)
- View modes (By Savings, By Schedule, By Cluster)
- Efficiency tracking
- Insights and recommendations

**Props**: None (standalone page)

### 10. NotificationSettings

**Purpose**: Configure hibernation event notifications

**Features**:
- Email notifications (multiple recipients)
- Slack webhooks
- Custom webhooks with HMAC
- PagerDuty integration
- Event filtering per channel
- Test notification sending

**Props**: None (standalone page)

**Event Types**:
- sleep_started
- sleep_completed
- wake_started
- wake_completed
- errors
- conflicts

### 11. EmergencyControls

**Purpose**: Manual overrides and panic button

**Features**:
- Panic button (wake all + pause all)
- Manual cluster wake/sleep
- Schedule pause/resume
- Confirmation dialogs
- Safety guidelines

**Props**: None (standalone page)

## API Integration

All components use the `hibernationApi` service:

```javascript
import { hibernationApi } from '../../services/hibernationApi';

// List schedules
await hibernationApi.listSchedules({ cluster_id, is_active, page, page_size });

// Get schedule
await hibernationApi.getSchedule(id);

// Create schedule
await hibernationApi.createSchedule(data);

// Update schedule
await hibernationApi.updateSchedule(id, data);

// Delete schedule
await hibernationApi.deleteSchedule(id);

// Toggle active
await hibernationApi.toggleSchedule(id, isActive);

// Compare strategies
await hibernationApi.compareStrategies();

// Estimate savings
await hibernationApi.estimateSavings(id);
```

## Helper Functions

### generateScheduleMatrix(preset)

Generate 168-hour binary matrix from preset:
- `weekends`: Sleep Sat-Sun all day
- `nights`: Sleep Mon-Fri 00:00-08:00 and 18:00-00:00
- `business_hours`: Awake Mon-Fri 09:00-17:00, sleep rest

**Example**:
```javascript
import { generateScheduleMatrix } from '../../services/hibernationApi';

const matrix = generateScheduleMatrix('weekends');
// Returns: "0000...1111...0000" (168 chars)
```

### formatTimeUntil(targetTime)

Format relative time until target:
- Returns "Now" if past
- Returns "Xd Yh" or "Xh Ym" or "Ym"

## Styling

All components use Tailwind CSS utility classes:
- Colors: blue (primary), purple (sleep), green (awake), red (error)
- Shadows: `shadow`, `shadow-lg`, `shadow-xl`
- Animations: `animate-pulse`, `animate-spin`
- Gradients: `from-X-500 to-X-600`

## State Management

Components manage local state with `useState` and load data on mount with `useEffect`:

```javascript
const [data, setData] = useState([]);
const [loading, setLoading] = useState(true);

useEffect(() => {
  loadData();
}, []);

const loadData = async () => {
  try {
    setLoading(true);
    const response = await hibernationApi.listSchedules();
    setData(response.data);
  } catch (error) {
    console.error('Failed to load:', error);
  } finally {
    setLoading(false);
  }
};
```

## Testing

### Component Testing (Jest + React Testing Library)

```javascript
import { render, screen, fireEvent } from '@testing-library/react';
import { HibernationDashboard } from './components/hibernation';

test('renders dashboard', () => {
  render(<HibernationDashboard />);
  expect(screen.getByText('Hibernation Schedules')).toBeInTheDocument();
});
```

### Integration Testing

Test full workflow:
1. Create schedule
2. Verify in list
3. Edit schedule
4. Pause/Resume
5. Delete schedule

## Performance

- SSE auto-reconnect on disconnect
- Debounced calendar cell updates
- Lazy loading for history (pagination)
- Memoized strategy cards
- Auto-refresh intervals (30s for history)

## Error Handling

All API calls wrapped in try/catch:
```javascript
try {
  await hibernationApi.createSchedule(data);
  onClose(true);
} catch (err) {
  setError(err.response?.data?.message || 'Failed to save schedule');
}
```

## Browser Support

- Chrome/Edge: Full support
- Firefox: Full support
- Safari: Full support (SSE supported)

## Future Enhancements

- [ ] Drag-to-select on calendar
- [ ] Schedule templates library
- [ ] Multi-select clusters with bulk actions
- [ ] Historical cost trend charts
- [ ] Predicted vs actual savings comparison
- [ ] Mobile responsive optimizations
- [ ] Dark mode support
- [ ] Export schedules as JSON/YAML
- [ ] Import schedules from file
- [ ] Schedule diff viewer for conflicts

## Troubleshooting

### SSE not connecting
- Check CORS headers on backend
- Verify `/api/v1/sse/hibernation` endpoint exists
- Check browser console for errors

### Calendar not updating
- Ensure `onChange` prop is passed
- Check `editable` prop is true
- Verify matrix format (168 chars, 0/1 only)

### Schedule creation fails
- Validate cluster_ids exist
- Check schedule_matrix length === 168
- Verify strategy is valid enum value

## Support

For issues or questions:
1. Check API logs: `docker logs spot-optimizer-backend`
2. Check Celery logs: `docker logs spot-optimizer-celery-worker`
3. Verify database: `docker exec spot-optimizer-postgres psql -U postgres -d spot_optimizer`
4. Check Redis cache: `docker exec spot-optimizer-redis redis-cli KEYS "hibernation:*"`
