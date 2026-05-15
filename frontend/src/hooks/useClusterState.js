import { useState, useEffect, useCallback, useMemo } from 'react';
import { clusterAPI, metricAPI } from '../services/api';
import { normalizeNodeState } from '../utils/normalizeState';

/**
 * Provides normalized cluster state: nodes with _state tags, nodeStates counts,
 * capacity metrics, and metrics history.
 *
 * Replaces duplicate data-fetching logic that previously existed in
 * ScalingActivity.jsx and RightSizing.jsx.
 *
 * @param {string} clusterId
 */
const useClusterState = (clusterId) => {
  const [rawNodes, setRawNodes]           = useState([]);
  const [utilization, setUtilization]     = useState(null);
  const [clusterMetrics, setClusterMetrics] = useState(null);
  const [loading, setLoading]             = useState(false);
  const [error, setError]                 = useState(null);

  const refetch = useCallback(() => {
    if (!clusterId) return;
    setLoading(true);
    setError(null);
    Promise.all([
      clusterAPI.getNodes(clusterId).catch(() => ({ data: [] })),
      clusterAPI.getUtilization(clusterId).catch(() => ({ data: null })),
      metricAPI.getClusterMetrics(clusterId).catch(() => ({ data: null })),
    ]).then(([nodesRes, utilRes, metricsRes]) => {
      const raw = nodesRes.data?.nodes || (Array.isArray(nodesRes.data) ? nodesRes.data : []);
      setRawNodes(raw);
      setUtilization(utilRes.data);
      setClusterMetrics(metricsRes.data);
    }).catch(err => setError(err?.message || 'Failed to load cluster state'))
      .finally(() => setLoading(false));
  }, [clusterId]);

  useEffect(() => { refetch(); }, [refetch]);

  /** Nodes annotated with normalized _state field */
  const nodes = useMemo(() =>
    rawNodes.map(n => ({ ...n, _state: normalizeNodeState(n) })),
    [rawNodes]
  );

  /** Aggregated node state counts */
  const nodeStates = useMemo(() => ({
    active:       nodes.filter(n => n._state === 'ACTIVE').length,
    draining:     nodes.filter(n => n._state === 'DRAINING').length,
    provisioning: nodes.filter(n => n._state === 'PROVISIONING').length,
    blocked:      nodes.filter(n => n._state === 'BLOCKED').length,
    total:        nodes.length,
  }), [nodes]);

  /** Unified capacity / saturation metrics */
  const capacity = useMemo(() => ({
    // Saturation percentages
    cpu:      clusterMetrics?.cpu_usage_pct  ?? clusterMetrics?.cpu_usage  ?? null,
    memory:   clusterMetrics?.memory_usage_pct ?? clusterMetrics?.memory_usage ?? null,
    podPct:   clusterMetrics?.pod_count && clusterMetrics?.pod_capacity
      ? Math.round((clusterMetrics.pod_count / clusterMetrics.pod_capacity) * 100) : null,
    podLabel: clusterMetrics?.pod_count && clusterMetrics?.pod_capacity
      ? `${clusterMetrics.pod_count}/${clusterMetrics.pod_capacity}` : null,
    // Delta (available vs required)
    availCores:  clusterMetrics?.cpu_available ?? clusterMetrics?.available_cores ?? utilization?.cpu_available ?? null,
    availMem:    clusterMetrics?.memory_available_gb ?? clusterMetrics?.memory_available ?? utilization?.memory_available ?? null,
    reqCores:    clusterMetrics?.cpu_required ?? clusterMetrics?.required_cores ?? utilization?.cpu_requested_cores ?? null,
    reqMem:      clusterMetrics?.memory_required_gb ?? clusterMetrics?.memory_required ?? utilization?.memory_requested_gb ?? null,
    pendingPods: clusterMetrics?.pending_pods ?? null,
    // Utilization detail
    cpuUsed: utilization?.cpu_used_millicores ?? utilization?.cpu_actual ?? null,
    cpuReq:  utilization?.cpu_requested_millicores ?? utilization?.cpu_requested ?? null,
    memUsed: utilization?.memory_used_gi ?? utilization?.memory_actual ?? null,
    memReq:  utilization?.memory_requested_gi ?? utilization?.memory_requested ?? null,
    cpuPct:  utilization?.cpu_usage_pct ?? utilization?.cpu_percent ?? null,
    memPct:  utilization?.memory_usage_pct ?? utilization?.memory_percent ?? null,
    insight: utilization?.insight ?? null,
  }), [clusterMetrics, utilization]);

  /** Time-series from history if available; null means use action-derived fallback */
  const metricsHistory = useMemo(() => {
    if (!clusterMetrics?.history?.length) return null;
    return clusterMetrics.history.map(h => ({
      time:    new Date(h.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      nodes:   h.node_count ?? h.nodes ?? 0,
      pending: h.pending_pods ?? 0,
    }));
  }, [clusterMetrics]);

  return { nodes, nodeStates, capacity, utilization, clusterMetrics, metricsHistory, loading, error, refetch };
};

export default useClusterState;
