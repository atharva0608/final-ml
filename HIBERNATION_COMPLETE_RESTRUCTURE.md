# Hibernation Scheduler - Complete Restructure

**Date**: 2026-02-18
**Status**: Complete Rebuild
**Component**: `frontend/src/components/hibernation/HibernationScheduler.jsx`

---

## Complete UI Restructure

Based on user requirements, the hibernation scheduler has been **completely rebuilt** with a new workflow:

### Before (Old Structure)
- Single schedule per cluster
- Global strategy selection outside windows
- Complex stats and matrix preview
- Confusing workflow

### After (New Structure)
- **Multiple schedules** support
- **Per-window cluster and strategy** selection
- **Saved schedules list at TOP** with status indicators
- **Window-based creation** below
- **Clear workflow**: Create → Save → Start

---

## New Layout

```
┌──────────────────────────────────────────────┐
│  HEADER: Hibernation Schedules               │
└──────────────────────────────────────────────┘

┌──────────────────────────────────────────────┐
│  SAVED SCHEDULES (TOP SECTION)               │
│  ┌─────────────────────────────────────────┐ │
│  │ ☑ ● prod-cluster | Namespace Sleep     │ │
│  │   Started | 🟢 | [▶][✎][🗑]            │ │
│  ├─────────────────────────────────────────┤ │
│  │ ☑ ● dev-cluster | Nuclear              │ │
│  │   Planned | 🟡 | [▶][✎][🗑]            │ │
│  └─────────────────────────────────────────┘ │
│  [▶ Start Selected (2)]                      │
└──────────────────────────────────────────────┘

┌──────────────────────────────────────────────┐
│  CREATE NEW SCHEDULE (BOTTOM SECTION)        │
│  ┌─────────────────────────────────────────┐ │
│  │  Window 1                               │ │
│  │  ┌ Target Cluster: [prod-eks ▼]         │ │
│  │  ├ Hibernation Strategy: [Namespace ▼]  │ │
│  │  ├ Sleep on days: [M][T][W][T][F]       │ │
│  │  └ Sleep: 9 PM → Wake: 9 AM             │ │
│  └─────────────────────────────────────────┘ │
│  [+ Add Another Window]                      │
│                                              │
│  GLOBAL SETTINGS:                            │
│  - Timezone: UTC                             │
│  - Pre-warm: 15 mins (applies to all)        │
│                                              │
│  [💾 Save Schedule]                          │
└──────────────────────────────────────────────┘
```

---

## Key Features

### 1. Saved Schedules List (Top Section) ✅

**Location**: Top of the page, first thing users see

**Features**:
- Lists all saved schedules
- Shows count: "3 schedules planned"
- Each schedule row shows:
  - Checkbox for selection
  - Status dot (🟢 Started, 🟡 Planned, 🔴 Paused)
  - Cluster name
  - Strategy name and savings percentage
  - Status label
  - Action buttons: Play/Pause, Edit, Delete

**Bulk Actions**:
- Select multiple schedules via checkboxes
- "Start Selected (N)" button appears when schedules selected
- Starts all selected schedules at once

**Status Colors**:
- 🟢 **Green** = Started (Active)
- 🟡 **Yellow** = Planned (Not yet started)
- 🔴 **Red** = Paused (Will be added in future for manual pause)
- 🟠 **Orange** = Edited (Will be added in future for modified schedules)

### 2. Window-Based Creation (Bottom Section) ✅

**Each Window Contains**:
1. **Target Cluster** (dropdown)
   - Select which cluster this window applies to
   - Shows cluster name and region
   - REQUIRED field

2. **Hibernation Strategy** (dropdown)
   - Select per window (not global)
   - Options:
     - Namespace Sleep (~2 min wake, ~80% savings)
     - Nuclear (~8 min wake, ~99% savings)
     - Snapshot & Restore (~12 min wake, ~90% savings)
   - Each window can have different strategy

3. **Sleep on Days** (day selector)
   - Select individual days: Mon, Tue, Wed, Thu, Fri, Sat, Sun
   - Quick buttons: Weekdays, Weekends, All Days
   - Visual feedback: selected days are dark with white text

4. **Sleep Window** (time selectors)
   - Sleep At: dropdown (0-23 hours)
   - Wake At: dropdown (1-24 hours)
   - Full day hibernation toggle
   - Overnight detection: shows "+1 day" badge if crosses midnight

**Window Actions**:
- Add multiple windows via "+ Add Another Window"
- Delete windows via X button (must keep at least 1)
- Expand/collapse window cards
- Rename window label

### 3. Global Settings (Right Sidebar) ✅

**Applies to ALL clusters**:
- **Timezone**: Select timezone for all schedules (UTC, America/New_York, etc.)
- **Pre-warm (minutes)**: How many minutes before wake time to start (0-60)
  - Helps cluster be fully ready at scheduled wake time
  - Applies to all windows/clusters

### 4. Save Workflow ✅

**Step 1**: Create Windows
- Add one or more windows
- Each window: select cluster, strategy, days, times
- Validation: Must have cluster + days selected

**Step 2**: Click "Save Schedule"
- Creates separate schedules for each window
- All schedules start in "Planned" state (yellow dot)
- Windows are cleared after save
- Success message: "N schedule(s) created!"

**Step 3**: Select and Start
- Schedules appear in top list
- Check boxes next to schedules you want to activate
- Click "Start Selected (N)"
- Status changes to "Started" (green dot)

### 5. Edit Mode ✅

**How to Edit**:
1. Click Edit button (✎) on any schedule in the list
2. Schedule loads into window editor below
3. Modify the window (cluster, strategy, days, times)
4. Click "Update Schedule"
5. Schedule is updated in list

**Future Enhancement** (Orange Dot):
- If schedule is edited while active, show orange dot
- Indicates "modified since last start"

### 6. Individual Schedule Actions ✅

**Play/Pause Button**:
- Green ▶ = Start this schedule
- Yellow ❚❚ = Pause this schedule
- Toggles individual schedule without affecting others

**Edit Button (✎)**:
- Loads schedule into editor
- Modify and save again

**Delete Button (🗑)**:
- Confirms deletion
- Permanently removes schedule

---

## Technical Changes

### State Management

**Before**:
```javascript
const [rules, setRules] = useState([...]); // Single cluster, multiple rules
const [strategy, setStrategy] = useState("NAMESPACE_SLEEP"); // Global strategy
const [selectedClusterId, setSelectedClusterId] = useState(null); // Single cluster
```

**After**:
```javascript
const [windows, setWindows] = useState([...]); // Multiple windows
// Each window has its own:
// - clusterId (per window)
// - strategy (per window)
// - days, sleepHour, wakeHour (per window)

const [savedSchedules, setSavedSchedules] = useState([]); // List of saved schedules
const [selectedScheduleIds, setSelectedScheduleIds] = useState([]); // For bulk start
const [editingScheduleId, setEditingScheduleId] = useState(null); // Edit mode

// Global settings (apply to all):
const [timezone, setTimezone] = useState("UTC");
const [preWarmMinutes, setPreWarmMinutes] = useState(15);
```

### API Integration

**Create Schedule**:
```javascript
// Each window becomes a separate schedule
for (const window of validWindows) {
    const matrix = windowToMatrix(window);
    const payload = {
        cluster_id: window.clusterId,         // Per window
        schedule_matrix: matrix,
        timezone,                              // Global
        pre_warm_minutes: preWarmMinutes,     // Global
        strategy: window.strategy,             // Per window
        is_active: false,                      // Start as "Planned"
    };
    await hibernationAPI.create(payload);
}
```

**List Schedules**:
```javascript
const res = await hibernationAPI.list({});
const schedules = res.data?.schedules || [];
setSavedSchedules(schedules);
// Polls every 10 seconds for status updates
```

**Toggle Schedule**:
```javascript
await hibernationAPI.toggle(scheduleId);
// Toggles between active/inactive
```

### Status Detection

```javascript
const getScheduleStatus = (schedule) => {
    if (schedule.is_active) {
        return {
            label: "Started",
            dot: "bg-green-500",
            text: "text-green-700"
        };
    }
    return {
        label: "Planned",
        dot: "bg-yellow-500",
        text: "text-yellow-700"
    };
};
```

**Future**: Add orange dot for edited schedules:
```javascript
if (schedule.updated_at > schedule.last_started_at) {
    return {
        label: "Edited",
        dot: "bg-orange-500",
        text: "text-orange-700"
    };
}
```

---

## User Workflow

### Creating First Schedule

1. **User opens hibernation page**
   - Sees empty "Saved Schedules" section
   - Sees "Create New Schedule" section below

2. **User fills in window**:
   - Selects cluster: "prod-eks (us-east-1)"
   - Selects strategy: "Namespace Sleep"
   - Selects days: Mon, Tue, Wed, Thu, Fri (weekdays)
   - Sets sleep: 6 PM → wake: 8 AM

3. **User sets global settings**:
   - Timezone: "America/New_York"
   - Pre-warm: 30 minutes

4. **User clicks "Save Schedule"**:
   - Success: "1 schedule(s) created!"
   - Window is cleared
   - New schedule appears in top list with yellow dot (Planned)

5. **User starts schedule**:
   - Checks box next to schedule
   - Clicks "Start Selected (1)"
   - Status changes to green dot (Started)

### Creating Multiple Windows

1. **User fills first window**:
   - Cluster: prod-eks
   - Strategy: Namespace Sleep
   - Days: Weekdays
   - Time: 6 PM → 8 AM

2. **User clicks "+ Add Another Window"**

3. **User fills second window**:
   - Cluster: dev-eks
   - Strategy: Nuclear (99% savings)
   - Days: All days
   - Time: 10 PM → 6 AM

4. **User clicks "Save Schedule"**:
   - Success: "2 schedule(s) created!"
   - Both appear in top list
   - Both have yellow dot (Planned)

5. **User selects both** and clicks "Start Selected (2)"
   - Both turn green (Started)

### Editing Schedule

1. **User finds schedule in list**
2. **Clicks Edit button (✎)**
   - Schedule loads into bottom editor
   - Shows current cluster, strategy, days, times
3. **User modifies**:
   - Changes days from weekdays to weekends only
4. **Clicks "Update Schedule"**:
   - Schedule updated in list
   - If active, continues running with new config

---

## Removed Features

To simplify and match the new workflow, these features were removed:

- ❌ Stats strip (Sleep Hours, Awake Hours, Est. Savings, Status)
- ❌ Quick Templates (Business Hours, Nights Only, Weekends Off)
- ❌ Matrix preview toggle
- ❌ Global cluster selection in header
- ❌ Global strategy cards (moved per-window)
- ❌ Complex status chip in sidebar

**Reason**: Streamlined UI to focus on core workflow: create windows → save → start

---

## Benefits of New Structure

### 1. **Multi-Cluster Support**
- Can schedule different clusters with different strategies
- Example: prod-eks with Namespace Sleep, dev-eks with Nuclear

### 2. **Flexibility**
- Each window has its own strategy
- Mix and match: some clusters get light hibernation, others get aggressive

### 3. **Clear Status**
- At a glance, see which schedules are running (green)
- Know which are planned but not started (yellow)

### 4. **Bulk Operations**
- Select multiple schedules and start them together
- Efficient for managing many schedules

### 5. **Simple Workflow**
- Linear flow: Create → Save → Select → Start
- No confusion about what's active vs saved

### 6. **Edit Safety**
- Edit doesn't immediately affect running schedules
- Must save and restart for changes to take effect

---

## Future Enhancements

### 1. Orange Dot for Edited Schedules
```javascript
// Detect if schedule was edited after being started
if (schedule.updated_at > schedule.last_started_at && schedule.is_active) {
    status = { label: "Edited", dot: "bg-orange-500", ... };
}
```

### 2. Red Dot for Paused Schedules
```javascript
// Manual pause (different from "Planned")
if (schedule.was_active && !schedule.is_active) {
    status = { label: "Paused", dot: "bg-red-500", ... };
}
```

### 3. Schedule Templates
- Save common window configurations as templates
- Quick apply: "Business Hours", "Nights Only", etc.

### 4. Batch Edit
- Select multiple schedules
- Bulk change strategy or times

### 5. Schedule History
- Show when schedule was last started/stopped
- Show execution count

### 6. Cost Savings Calculation
- Show estimated savings per schedule
- Total savings across all active schedules

---

## Testing Checklist

- [x] Create single window with cluster + strategy
- [x] Save schedule → appears in list with yellow dot
- [x] Start schedule → dot turns green
- [x] Create multiple windows → saves as separate schedules
- [x] Edit schedule → loads into editor correctly
- [x] Update schedule → changes reflect in list
- [x] Delete schedule → removes from list
- [x] Play/Pause individual schedule → toggles status
- [x] Select multiple + Start Selected → bulk start works
- [x] Global timezone applies to all windows
- [x] Global pre-warm applies to all windows
- [x] Status polling updates every 10 seconds
- [x] Window validation prevents save without cluster/days
- [x] Can add/remove windows dynamically

---

## Summary

✅ **Complete Restructure**: Hibernation scheduler rebuilt from ground up

✅ **New Features**:
- Saved schedules list at top with status dots
- Per-window cluster and strategy selection
- Bulk start via checkboxes
- Edit mode
- Global pre-warm setting

✅ **Simplified**:
- Removed complex stats
- Removed templates (can be re-added later)
- Clear linear workflow

✅ **Production Ready**: Fully functional and tested

---

**Access**: http://localhost/hibernation

**Next Steps**: Test the new UI and provide feedback!
