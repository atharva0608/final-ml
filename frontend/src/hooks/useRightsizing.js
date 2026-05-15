import { useState, useEffect, useCallback, useMemo } from 'react';
import { optimizationAPI, clusterAPI, karpenterAPI } from '../services/api';

/**
 * Provides normalized rightsizing data: workload recommendations, node pool
 * recommendations, utilization metrics, cost impact summary, and chart data.
 *
 * Replaces the inline data-fetching and transformation logic in RightSizing.jsx.
 *
 * @param {string} clusterId
 */
const useRightsizing = (clusterId) => {
  const [rawRecommendations, setRawRecommendations] = useState([]);
  const [nodePools, setNodePools]                   = useState([]);
  const [utilization, setUtilization]               = useState(null);
  const [loading, setLoading]                       = useState(false);
  const [error, setError]                           = useState(null);

  const refetch = useCallback(() => {
    if (!clusterId) return;
    setLoading(true);
    setError(null);
    Promise.all([
      optimizationAPI.getEnrichedRightsizing(clusterId)
        .catch(() => optimizationAPI.getRightsizing(clusterId).catch(() => ({ data: [] }))),
      clusterAPI.getUtilization(clusterId).catch(() => ({ data: null })),
      karpenterAPI.getRecommendations(clusterId).catch(() => ({ data: [] })),
    ]).then(([rsRes, utilRes, poolsRes]) => {
      setRawRecommendations(rsRes.data?.recommendations || (Array.isArray(rsRes.data) ? rsRes.data : []));
      setUtilization(utilRes.data);
      setNodePools(
        poolsRes.data?.recommendations || poolsRes.data?.pools ||
        (Array.isArray(poolsRes.data) ? poolsRes.data : [])
      );
    }).catch(err => setError(err?.message || 'Failed to load rightsizing data'))
      .finally(() => setLoading(false));
  }, [clusterId]);

  useEffect(() => { refetch(); }, [refetch]);

  const recommendations = rawRecommendations;

  /** Aggregated cost impact across all recommendations */
  const costImpact = useMemo(() => {
    const totalSaving  = recommendations.reduce((s, r) => s + parseFloat(r.monthly_saving || r.savings_per_month || 0), 0);
    const totalCurrent = recommendations.reduce((s, r) => s + parseFloat(r.current_monthly_cost || r.monthly_cost_current || 0), 0);
    const savingPct    = totalCurrent > 0 ? Math.round((totalSaving / totalCurrent) * 100) : 0;
    return { totalSaving, totalCurrent, totalRecommended: totalCurrent - totalSaving, savingPct };
  }, [recommendations]);

  /** Summary counts */
  const summary = useMemo(() => ({
    workloads:   recommendations.length,
    optimizable: recommendations.filter(r => parseFloat(r.monthly_saving || r.savings_per_month || 0) > 0).length,
  }), [recommendations]);

  /** Top 8 workloads by saving for the cost chart */
  const chartData = useMemo(() =>
    [...recommendations]
      .sort((a, b) =>
        parseFloat(b.monthly_saving || b.savings_per_month || 0) -
        parseFloat(a.monthly_saving || a.savings_per_month || 0)
      )
      .slice(0, 8)
      .map(r => {
        const saving      = parseFloat(r.monthly_saving || r.savings_per_month || 0);
        const current     = parseFloat(r.current_monthly_cost || r.monthly_cost_current || 0);
        const recommended = parseFloat(r.recommended_monthly_cost || r.monthly_cost_recommended || current - saving || 0);
        return {
          name:        (r.workload || r.name || r.deployment_name || '').slice(0, 14),
          current,
          recommended,
        };
      }),
    [recommendations]
  );

  /** Normalized utilization metric accessors */
  const utilizationMetrics = useMemo(() => ({
    cpuPct:  utilization?.cpu_usage_pct  ?? utilization?.cpu_percent  ?? null,
    memPct:  utilization?.memory_usage_pct ?? utilization?.memory_percent ?? null,
    cpuUsed: utilization?.cpu_used_millicores ?? utilization?.cpu_actual ?? null,
    cpuReq:  utilization?.cpu_requested_millicores ?? utilization?.cpu_requested ?? null,
    memUsed: utilization?.memory_used_gi ?? utilization?.memory_actual ?? null,
    memReq:  utilization?.memory_requested_gi ?? utilization?.memory_requested ?? null,
    insight: utilization?.insight ?? null,
  }), [utilization]);

  return {
    recommendations,
    nodePools,
    utilization,
    utilizationMetrics,
    costImpact,
    summary,
    chartData,
    loading,
    error,
    refetch,
  };
};

export default useRightsizing;
