/**
 * usePermission Hook
 *
 * Checks if user has permission for a specific feature.
 * Returns permission status, loading state, and feature metadata.
 */
import { useState, useEffect } from 'react';
import { permissionAPI } from '../services/api';

export const usePermission = (featureId, resourceId = null) => {
  const [state, setState] = useState({
    hasPermission: false,
    loading: true,
    feature: null,
    ticket: null,
    expiresAt: null,
    reason: '',
  });

  useEffect(() => {
    let mounted = true;

    const checkPermission = async () => {
      try {
        setState(prev => ({ ...prev, loading: true }));

        const response = await permissionAPI.check(featureId, resourceId);

        if (mounted) {
          setState({
            hasPermission: response.data.allowed,
            loading: false,
            feature: response.data.feature,
            ticket: response.data.ticket,
            expiresAt: response.data.expires_at,
            reason: response.data.reason,
          });
        }
      } catch (error) {
        if (mounted) {
          console.error('Permission check failed:', error);
          setState({
            hasPermission: false,
            loading: false,
            feature: null,
            ticket: null,
            expiresAt: null,
            reason: 'Error checking permissions',
          });
        }
      }
    };

    if (featureId) {
      checkPermission();
    }

    return () => {
      mounted = false;
    };
  }, [featureId, resourceId]);

  return state;
};

export default usePermission;
