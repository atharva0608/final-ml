/* eslint-disable react-hooks/rules-of-hooks */
/**
 * usePermission Hook
 *
 * Checks if user has permission for a specific feature.
 * Returns permission status, loading state, and feature metadata.
 *
 * Features:
 * - Caches permission results in sessionStorage
 * - Auto-polls every 3 seconds when request is pending
 * - Auto-polls every 10 seconds when approved (to detect expiration)
 */
import { useState, useEffect, useCallback } from 'react';
import { permissionAPI } from '../services/api';
import { useAuthStore } from '../store/useStore';

const ADMIN_ROLES = ['org_admin', 'super_admin', 'ORG_ADMIN', 'SUPER_ADMIN'];

// Cache key generator
const getCacheKey = (featureId, resourceId) =>
  `permission_${featureId}_${resourceId || 'global'}`;

export const usePermission = (featureId, resourceId = null) => {
  // Admin bypass — org_admin and super_admin always have full access
  const user = useAuthStore(state => state.user);
  const isAdmin = user && ADMIN_ROLES.includes(user.role);

  // Call the hook unconditionally to satisfy Rules of Hooks
  const permissionCheck = usePermissionCheck(featureId, resourceId, isAdmin);

  if (isAdmin) {
    return {
      hasPermission: true,
      loading: false,
      feature: null,
      ticket: null,
      expiresAt: null,
      reason: 'Admin privileges',
      pending: false,
      refresh: () => { },
    };
  }

  return permissionCheck;
};

/**
 * Internal hook that runs the actual permission check.
 * Only called for non-admin users.
 */
const usePermissionCheck = (featureId, resourceId = null, isAdmin = false) => {
  // Skip logic if user is admin (called unconditionally but returns early)
  if (isAdmin) {
    return {
      hasPermission: false, // Will be overridden by admin check
      loading: false,
      feature: null,
      ticket: null,
      expiresAt: null,
      reason: '',
      pending: false,
      refresh: () => { },
    };
  }
  // Try to load from cache synchronously to prevent flicker
  const getInitialState = () => {
    if (!featureId) {
      return {
        hasPermission: false,
        loading: false,
        feature: null,
        ticket: null,
        expiresAt: null,
        reason: '',
        pending: false,
      };
    }

    try {
      const cacheKey = getCacheKey(featureId, resourceId);
      const cached = sessionStorage.getItem(cacheKey);
      if (cached) {
        const cachedData = JSON.parse(cached);
        const cacheAge = Date.now() - cachedData.timestamp;

        // Use cache for initial state if recent enough
        let cacheTTL = 60000; // 1 minute for denied (no polling)
        if (cachedData.state.pending) cacheTTL = 2000; // 2 seconds for pending (fast polling)
        else if (cachedData.state.hasPermission) cacheTTL = 300000; // 5 minutes for approved (trust ticket, rely on events)

        if (cacheAge < cacheTTL) {
          return { ...cachedData.state, loading: false };
        }
      }
    } catch (e) {
      console.error('[usePermission] Failed to load initial cache:', e);
    }

    return {
      hasPermission: false,
      loading: true,
      feature: null,
      ticket: null,
      expiresAt: null,
      reason: '',
      pending: false,
    };
  };

  const [state, setState] = useState(getInitialState());

  const checkPermission = useCallback(async (useCache = true) => {
    if (!featureId) return;

    try {
      // Check cache first
      if (useCache) {
        const cacheKey = getCacheKey(featureId, resourceId);
        const cached = sessionStorage.getItem(cacheKey);
        if (cached) {
          const cachedData = JSON.parse(cached);
          const cacheAge = Date.now() - cachedData.timestamp;

          // Different cache TTLs based on state:
          // - Pending: 2 seconds (fast polling active)
          // - Approved: 5 minutes (trust ticket, event-driven updates)
          // - Denied: 1 minute (no polling, event-driven updates)
          let cacheTTL = 60000; // 1 minute default
          if (cachedData.state.pending) {
            cacheTTL = 2000; // 2 seconds for pending
          } else if (cachedData.state.hasPermission) {
            cacheTTL = 300000; // 5 minutes for approved
          }

          if (cacheAge < cacheTTL) {
            console.log(`[usePermission] Using cached permission for ${featureId} (age: ${Math.round(cacheAge / 1000)}s):`, cachedData.state);
            setState({
              ...cachedData.state,
              loading: false,
            });
            return;
          }
        }
      }

      console.log(`[usePermission] Fetching fresh permission for ${featureId}`);
      setState(prev => ({ ...prev, loading: true }));

      const response = await permissionAPI.check(featureId, resourceId);

      const newState = {
        hasPermission: response.data.allowed,
        loading: false,
        feature: response.data.feature,
        ticket: response.data.ticket,
        expiresAt: response.data.expires_at,
        reason: response.data.reason,
        pending: response.data.pending || false,
      };

      // Only update state if something actually changed (prevents unnecessary re-renders)
      const hasChanged =
        state.hasPermission !== newState.hasPermission ||
        state.pending !== newState.pending ||
        state.reason !== newState.reason ||
        state.expiresAt !== newState.expiresAt;

      if (hasChanged) {
        console.log(`[usePermission] Permission changed for ${featureId}:`, {
          allowed: newState.hasPermission,
          pending: newState.pending,
          reason: newState.reason
        });
        setState(newState);
      } else {
        // Silently update loading state without logging
        setState(prev => ({ ...prev, loading: false }));
      }

      // Cache the result
      const cacheKey = getCacheKey(featureId, resourceId);
      sessionStorage.setItem(cacheKey, JSON.stringify({
        state: newState,
        timestamp: Date.now(),
      }));

    } catch (error) {
      console.error('[usePermission] Permission check failed:', error);
      setState({
        hasPermission: false,
        loading: false,
        feature: null,
        ticket: null,
        expiresAt: null,
        reason: 'Error checking permissions',
        pending: false,
      });
    }
  }, [featureId, resourceId]);

  // Listen for approval status changes from other components
  useEffect(() => {
    const handleApprovalChange = (event) => {
      // Force immediate refresh without cache when an approval changes
      console.log('[usePermission] Approval status changed, forcing refresh:', event.detail);
      checkPermission(false);
    };

    window.addEventListener('approval:changed', handleApprovalChange);
    return () => window.removeEventListener('approval:changed', handleApprovalChange);
  }, [checkPermission]);

  // Listen for NEW permission requests (instant "Pending" state)
  useEffect(() => {
    const handlePermissionRequest = (event) => {
      const { feature_id, resource_id, status } = event.detail;

      // Only update if this is for OUR feature
      if (feature_id === featureId) {
        console.log('[usePermission] Request created instantly - showing pending');

        // Optimistic update: Immediately show pending state
        setState(prev => ({
          ...prev,
          hasPermission: false,
          pending: true,
          reason: 'Request pending approval',
          loading: false
        }));

        // Clear cache so next check gets fresh data
        const cacheKey = getCacheKey(featureId, resourceId);
        sessionStorage.removeItem(cacheKey);
      }
    };

    window.addEventListener('permission:requested', handlePermissionRequest);
    return () => window.removeEventListener('permission:requested', handlePermissionRequest);
  }, [featureId, resourceId]);

  // Check for expiration without polling (only when approved with expiry)
  useEffect(() => {
    if (!state.hasPermission || !state.expiresAt) return;

    const expiresAt = new Date(state.expiresAt);
    const now = new Date();
    const timeUntilExpiry = expiresAt - now;

    if (timeUntilExpiry <= 0) {
      // Already expired, refresh immediately
      checkPermission(false);
      return;
    }

    // Set timeout to refresh when it expires
    const timeout = setTimeout(() => {
      console.log(`[usePermission] Ticket expired for ${featureId}, refreshing...`);
      checkPermission(false);
    }, timeUntilExpiry);

    return () => clearTimeout(timeout);
  }, [state.hasPermission, state.expiresAt, featureId, checkPermission]);

  // Connect to SSE stream for real-time updates (NO POLLING!)
  useEffect(() => {
    const token = localStorage.getItem('access_token');
    if (!token) return;

    const apiUrl = process.env.REACT_APP_API_URL || 'http://localhost:8000';
    // EventSource doesn't support custom headers, so pass token as query parameter
    const eventSource = new EventSource(`${apiUrl}/api/v1/permissions/stream?token=${encodeURIComponent(token)}`);

    eventSource.onopen = () => {
      console.log('[usePermission] SSE connected - backend will push updates');
    };

    eventSource.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);

        if (data.event === 'permission:changed') {
          // Backend pushed a permission change
          console.log('[usePermission] Backend pushed permission change:', data.data);

          // Only update if it's for THIS feature
          if (data.data.feature_id === featureId) {
            const { action, status } = data.data;

            // Optimistic instant update based on action
            if (action === 'approved') {
              console.log('[usePermission] Instantly showing approved state');
              setState(prev => ({
                ...prev,
                hasPermission: true,
                pending: false,
                reason: 'Active JIT ticket',
                loading: false,
                expiresAt: data.data.expires_at
              }));
            } else if (action === 'revoked' || action === 'rejected') {
              console.log('[usePermission] Instantly showing denied state');
              setState(prev => ({
                ...prev,
                hasPermission: false,
                pending: false,
                reason: 'Access revoked',
                loading: false
              }));
            }

            // Also refresh from backend to get full data
            setTimeout(() => checkPermission(false), 100);
          }
        }
      } catch (e) {
        console.error('[usePermission] SSE parse error:', e);
      }
    };

    eventSource.onerror = (error) => {
      console.error('[usePermission] SSE error, will auto-reconnect:', error);
    };

    // Cleanup
    return () => {
      eventSource.close();
      console.log('[usePermission] SSE disconnected');
    };
  }, [featureId, checkPermission]);

  // Initial check only (NO POLLING!)
  useEffect(() => {
    checkPermission();
  }, [featureId, resourceId]);

  return {
    ...state,
    refresh: () => checkPermission(false), // Force refresh without cache
  };
};

export default usePermission;
