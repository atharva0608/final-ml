import { useState, useCallback, useEffect } from 'react';
import { placementPolicyAPI } from '../services/api';
import toast from 'react-hot-toast';

export const usePlacementPolicySummary = (clusterId) => {
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const fetchSummary = useCallback(async () => {
    if (!clusterId) return;
    setLoading(true);
    setError(null);
    try {
      const response = await placementPolicyAPI.getSummary(clusterId);
      setSummary(response.data);
    } catch (err) {
      const msg = err.response?.data?.message || 'Failed to fetch placement policy summary';
      setError(msg);
      toast.error(msg);
    } finally {
      setLoading(false);
    }
  }, [clusterId]);

  useEffect(() => {
    fetchSummary();
  }, [fetchSummary]);

  return { summary, loading, error, refresh: fetchSummary };
};

export const usePlacementPolicies = (clusterId, initialFilters = {}) => {
  const [policies, setPolicies] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [filters, setFilters] = useState({
    page: 1,
    page_size: 20,
    ...initialFilters
  });

  const fetchPolicies = useCallback(async () => {
    if (!clusterId) return;
    setLoading(true);
    setError(null);
    try {
      const response = await placementPolicyAPI.list(clusterId, filters);
      setPolicies(response.data.items || []);
      setTotal(response.data.total || 0);
    } catch (err) {
      const msg = err.response?.data?.message || 'Failed to fetch placement policies';
      setError(msg);
      toast.error(msg);
    } finally {
      setLoading(false);
    }
  }, [clusterId, filters]);

  useEffect(() => {
    fetchPolicies();
  }, [fetchPolicies]);

  const updateFilters = (newFilters) => {
    setFilters(prev => ({ ...prev, ...newFilters, page: newFilters.page || 1 }));
  };

  const generatePolicies = async () => {
    try {
      await placementPolicyAPI.generate(clusterId);
      toast.success('Placement policy generation triggered');
    } catch (err) {
      toast.error(err.response?.data?.message || 'Failed to trigger generation');
    }
  };

  return { 
    policies, 
    total, 
    loading, 
    error, 
    filters, 
    updateFilters, 
    refresh: fetchPolicies,
    generatePolicies 
  };
};

export const usePlacementPolicyDetail = (clusterId, workloadId) => {
  const [policy, setPolicy] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const fetchDetail = useCallback(async () => {
    if (!clusterId || !workloadId) return;
    setLoading(true);
    setError(null);
    try {
      const response = await placementPolicyAPI.getDetail(clusterId, workloadId);
      setPolicy(response.data);
    } catch (err) {
      const msg = err.response?.data?.message || 'Failed to fetch policy detail';
      setError(msg);
      // Let component handle the error display
    } finally {
      setLoading(false);
    }
  }, [clusterId, workloadId]);

  useEffect(() => {
    fetchDetail();
  }, [fetchDetail]);

  return { policy, loading, error, refresh: fetchDetail };
};
