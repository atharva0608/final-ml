# Frontend Layouts Module

## Purpose

Reusable layout components that provide consistent structure across pages.

**Last Updated**: 2025-12-25
**Authority Level**: MEDIUM

---

## Files

### DashboardLayout.jsx
**Purpose**: Main dashboard layout wrapper with navigation and structure
**Lines**: ~400
**Key Features**:
- **Sidebar Navigation**: Left sidebar with menu items
- **Top Header**: User info, notifications, logout
- **Main Content Area**: Where page content renders
- **Responsive Design**: Mobile-friendly collapsible sidebar

**Layout Structure**:
```
┌─────────────────────────────────────┐
│  Header (User, Notifications)       │
├──────┬──────────────────────────────┤
│      │                              │
│ Side │  Main Content Area           │
│ bar  │  {children}                  │
│      │                              │
└──────┴──────────────────────────────┘
```

**Navigation Items**:
- Dashboard (/)
- Accounts (/accounts)
- Instances (/instances)
- Experiments (/experiments)
- Settings (/settings)
- System Monitor (/system-monitor) - Admin only

**Props**:
- `children` - Page content to render
- `title` (optional) - Page title for header

**State Managed**:
- Sidebar collapsed/expanded
- Active menu item
- Mobile menu open/closed

**Dependencies**:
- React
- react-router-dom (Link, useLocation)
- frontend/src/context/AuthContext (for user info)
- CSS/Tailwind for styling

**Recent Changes**:
- 2025-12-23: Updated navigation for multi-account support

---

## Layout Usage Pattern

```javascript
import DashboardLayout from '../layouts/DashboardLayout';

export default function MyPage() {
  return (
    <DashboardLayout title="My Page">
      <div>
        {/* Your page content here */}
      </div>
    </DashboardLayout>
  );
}
```

---

## Dependencies

### Depends On:
- React
- react-router-dom
- frontend/src/context/AuthContext
- Styling framework (Tailwind CSS or similar)

### Depended By:
- **CRITICAL**: All dashboard pages
- ClientDashboard component
- Admin pages
- Settings pages

**Impact Radius**: MEDIUM-HIGH (affects all dashboard pages)

---

## Recent Changes

### 2025-12-25: Governance Structure Establishment
**Files Changed**: None (metadata only)
**Reason**: Document existing layout
**Impact**: No code changes, documentation baseline
**Reference**: `/index/recent_changes.md`

### 2025-12-23: Multi-Account Navigation
**Files Changed**: DashboardLayout.jsx
**Reason**: Add account switcher to navigation
**Impact**: Users can switch between multiple AWS accounts
**Reference**: Legacy documentation

---

## Component Features

### Responsive Behavior
- **Desktop** (>1024px): Sidebar always visible
- **Tablet** (768px-1024px): Collapsible sidebar
- **Mobile** (<768px): Hidden sidebar, hamburger menu

### User Menu
- Display username
- Role indicator (Client/Admin)
- Logout button
- Account dropdown (if multiple accounts)

### Navigation Highlighting
Active route highlighted based on `useLocation()` hook

---

## Known Issues

### None

Layouts module is stable as of 2025-12-25.

---

_Last Updated: 2025-12-25_
_Authority: MEDIUM - Layout structure_
