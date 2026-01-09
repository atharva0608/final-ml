/**
 * Dashboard Data Hook
 */
import { useState, useEffect } from 'react';
import { useMetricsStore } from '../store/useStore';
import { metricsAPI } from '../services/api';
import toast from 'react-hot-toast';

export const useDashboard = (clusterId = null) => {
  const [loading, setLoading] = useState(false);
  const {
    dashboardKPIs,
    costMetrics,
    instanceMetrics,
    costTimeSeries,
    setDashboardKPIs,
    setCostMetrics,
    setInstanceMetrics,
    setCostTimeSeries,
  } = useMetricsStore();

  const fetchDashboardData = async (startDate = null, endDate = null) => {
    setLoading(true);
    try {
      const params = {};
      if (clusterId) params.cluster_id = clusterId;
      if (startDate) params.start_date = startDate;
      if (endDate) params.end_date = endDate;

      // Fetch all metrics in parallel
      const [kpisRes, costRes, instancesRes, timeSeriesRes] = await Promise.all([
        metricsAPI.getDashboard(params),
        metricsAPI.getCost(params),
        metricsAPI.getInstances(params),
        metricsAPI.getCostTimeSeries(params),
      ]);

      setDashboardKPIs(kpisRes.data);
      setCostMetrics(costRes.data);
      setInstanceMetrics(instancesRes.data);
      setCostTimeSeries(timeSeriesRes.data);

      return { success: true };
    } catch (error) {
      const message = error.response?.data?.message || 'Failed to load dashboard data';
      toast.error(message);
      return { success: false, error: message };
    } finally {
      setLoading(false);
    }
  };

  const refreshDashboard = () => {
    return fetchDashboardData();
  };

  useEffect(() => {
    fetchDashboardData();
  }, [clusterId]);

  return {
    dashboardKPIs,
    costMetrics,
    instanceMetrics,
    costTimeSeries,
    loading,
    fetchDashboardData,
    refreshDashboard,
  };
};
