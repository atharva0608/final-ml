# Cleanup Verification Checklist

**Date:** 2026-02-19
**Branch:** testinglocal

## Quick Stats

- **Lines Deleted:** 4,079 lines
- **Lines Modified:** 927 lines (changes.txt changelog)
- **Files Deleted:** 14 files
- **Directories Removed:** 2 directories
- **Net Impact:** -3,152 lines of code removed

## Pre-Deployment Verification Steps

### 1. Frontend Build Verification

```bash
cd frontend
npm install  # Ensure dependencies are up to date
npm run build  # Should complete without errors
```

**Expected Result:** Build completes successfully with no errors about missing modules.

### 2. Backend Import Verification

```bash
cd backend
python -c "from api import app; print('✅ Backend imports successful')"
```

**Expected Result:** No ImportError exceptions.

### 3. Critical Route Testing

Test these routes in the browser after starting the app:

- ✅ `/dashboard` - Main dashboard loads
- ✅ `/hibernation` - Hibernation dashboard (HibernationDashboardNew) loads
- ✅ `/right-sizing` - Right-sizing page (RightSizingNew) loads
- ✅ `/admin` - Admin dashboard loads (SUPER_ADMIN only)
- ✅ `/clusters` - Cluster list loads
- ✅ `/settings` - Settings page loads

### 4. Console Error Check

Open browser DevTools console and verify:
- ✅ No import/module errors
- ✅ No 404s for deleted components
- ✅ No failed API calls to deleted routes

### 5. Component Export Verification

```bash
# Verify index.js exports are correct
grep "HibernationDashboard" frontend/src/components/hibernation/index.js
```

**Expected Output:** `export { default as HibernationDashboard } from './HibernationDashboardNew';`

### 6. Git Status Verification

```bash
git status --short
```

**Expected Output:**
```
 D backend/services/hygiene_service_additions.py
 D backend/test_scanner_fix.py
 M changes.txt
 M frontend/src/App.js
 D frontend/src/components/admin/AdminAgentFleet.jsx
 D frontend/src/components/admin/AdminImpersonation.jsx
 D frontend/src/components/admin/AdminTenantDrilldown.jsx
 D frontend/src/components/hibernation/HibernationDashboard.jsx
 D frontend/src/components/hibernation/HibernationGrid.jsx
 D frontend/src/components/hibernation/HibernationSchedule.jsx
 D frontend/src/components/hibernation/HibernationScheduleV2.jsx
 D frontend/src/components/lab/ExperimentLab.jsx
 D frontend/src/components/policies/TagTemplateManager.jsx
 D frontend/src/pages/HibernationDashboard.jsx
 D frontend/src/pages/HibernationPage.jsx
 D test_scanner.py
```

## Rollback Plan (if issues found)

If any issues are discovered:

```bash
# Revert all deletions
git checkout -- .

# Or revert specific files
git checkout -- frontend/src/components/hibernation/HibernationDashboard.jsx
```

## Post-Cleanup Maintenance

### Unused Backend Routes to Review

These routes exist but have no frontend integration. Manual review needed:

1. **smart_tag_routes.py** - May be used by agents
2. **auto_tag_routes.py** - May be used by agents
3. **settings_routes.py** - settingsAPI never imported
4. **lab_routes.py** - ExperimentLab deleted, but route may be needed

### Documentation to Update

1. `documents/all-components.md` - Remove deleted component references
2. `documents/all-files.md` - Remove deleted file references
3. `frontend/src/components/INFO.md` - Update component counts

## Verification Sign-Off

- [ ] Frontend builds successfully
- [ ] Backend imports successfully
- [ ] All critical routes load in browser
- [ ] No console errors related to deleted components
- [ ] Git status shows expected deletions
- [ ] Component exports verified (index.js)

**Sign-Off:** _________________  
**Date:** _________________  
**Notes:** _________________
