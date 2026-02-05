# Tag Management System - Deployment Issues

**Status:** TROUBLESHOOTING - Frontend not updating

## Current Problem

Tag Management was added to:
- ✅ MainLayout.jsx sidebar navigation (line 25)
- ✅ App.js routes
- ✅ Frontend rebuilt successfully

But user reports it's **still not visible** in the sidebar after:
- 2 frontend rebuilds
- Container restarts
- Hard browser refresh

## Additional Codebase Findings (Likely Causes)

1. **SUPER_ADMIN users never see the client sidebar**
   - `MainLayout.jsx` uses `adminNavigation` when `user.role` is `SUPER_ADMIN` / `super_admin`.
   - `Tag Management` only exists in the **client** `navigation` list, **not** in admin navigation.
   - Result: If the user is SUPER_ADMIN, the Tag Management link will **never appear** even though the route exists.

2. **SUPER_ADMIN auto-redirects to `/admin`**
   - `App.js` `PublicRoute` forces SUPER_ADMIN users to `/admin`.
   - This keeps them in the admin nav (which does not include Tag Management).

3. **Admin UI explicitly hides “Client View”**
   - The sidebar shows a banner: “Client View Hidden – Use Clients page to impersonate users.”
   - That implies Tag Management is only visible after impersonating a non-super-admin user.

4. **No role-based hiding for non-admins**
   - Tag Management appears for all non-super-admin roles, but backend endpoints require ORG_ADMIN.
   - Members/Team Leads will see the link but may hit 403s on create/update/delete.

## Troubleshooting Steps

### Step 1: Verify Container Has New Code
Checking if built JavaScript contains "Tag Management" text

### Step 2: Force Container Recreation
Stopping, removing, and recreating frontend container to ensure fresh start

### Step 3: Browser Cache
User needs to:
1. Hard refresh (Ctrl+Shift+R / Cmd+Shift+R)
2. Or clear browser cache
3. Or try incognito/private window

## Next Actions

If still not visible after container recreation:
1. Check if volume mount is overriding built files
2. Verify nginx is serving from correct directory
3. Check for JavaScript compilation errors

If visible only for non-admins:
1. Confirm the user is **not** SUPER_ADMIN
2. If SUPER_ADMIN, impersonate a client user (Admin → Clients)
3. Consider adding Tag Management to `adminNavigation` if admins should see it

---

**Investigating now...**
