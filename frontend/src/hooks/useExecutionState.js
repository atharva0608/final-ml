import { useState, useEffect, useCallback, useMemo } from 'react';
import { ascpaiAPI, clusterAPI } from '../services/api';
import { normalizeExecutionState } from '../utils/normalizeState';

/**
 * Provides normalized execution state: rebalancing actions categorized by state,
 * agent/scaling actions, event timeline, and behavior profile analytics.
 *
 * Replaces duplicate data-fetching and transformation logic that previously
 * existed independently in ScalingActivity.jsx and EventTimeline.jsx.
 *
 * @param {string} clusterId
 */
const useExecutionState = (clusterId) => {
  const [rawRebalancing, setRawRebalancing] = useState([]);
  const [rawActions, setRawActions]         = useState([]);
  const [loading, setLoading]               = useState(false);
  const [error, setError]                   = useState(null);

  const refetch = useCallback(() => {
    if (!clusterId) return;
    setLoading(true);
    setError(null);
    Promise.all([
      ascpaiAPI.getRebalancingStatus(clusterId, 50).catch(() => ({ data: null })),
      clusterAPI.getAgentActions(clusterId, 50).catch(() => ({ data: [] })),
    ]).then(([rbRes, acRes]) => {
      const rb = rbRes.data?.actions
        || rbRes.data?.rebalancing_actions
        || (Array.isArray(rbRes.data) ? rbRes.data : []);
      setRawRebalancing(rb);
      const ac = acRes.data?.actions || (Array.isArray(acRes.data) ? acRes.data : []);
      setRawActions(ac);
    }).catch(err => setError(err?.message || 'Failed to load execution state'))
      .finally(() => setLoading(false));
  }, [clusterId]);

  useEffect(() => { refetch(); }, [refetch]);

  /** Rebalancing actions with normalized _state */
  const rebalancingActions = useMemo(() =>
    rawRebalancing.map(a => ({ ...a, _state: normalizeExecutionState(a) })),
    [rawRebalancing]
  );

  /** Agent actions with normalized _state */
  const agentActions = useMemo(() =>
    rawActions.map(a => ({ ...a, _state: normalizeExecutionState(a) })),
    [rawActions]
  );

  /** Rebalancing actions grouped by normalized state */
  const rebalancingByState = useMemo(() => ({
    active:     rebalancingActions.filter(a => a._state === 'RUNNING'),
    completed:  rebalancingActions.filter(a => a._state === 'COMPLETED'),
    blocked:    rebalancingActions.filter(a => a._state === 'BLOCKED'),
    scheduling: rebalancingActions.filter(a => a._state === 'PENDING'),
  }), [rebalancingActions]);

  /** Agent actions relevant to scaling operations (top 10) */
  const scalingActions = useMemo(() =>
    agentActions.filter(a =>
      ['scale_up', 'scale_down', 'rebalance', 'optimize', 'scaling'].some(t =>
        (a.action_type || a.type || '').toLowerCase().includes(t)
      )
    ).slice(0, 10),
    [agentActions]
  );

  /** Sorted event feed (most recent first, top 10) */
  const timeline = useMemo(() =>
    [...agentActions]
      .sort((a, b) => new Date(b.created_at || 0) - new Date(a.created_at || 0))
      .slice(0, 10),
    [agentActions]
  );

  /**
   * Action timing distribution:
   *   fast  = actions that completed in < 30s
   *   slow  = actions that took > 60s
   */
  const behaviorProfile = useMemo(() => {
    const withTiming = agentActions.filter(a =>
      a.duration_seconds != null || (a.created_at && (a.completed_at || a.updated_at))
    );
    const durations = withTiming.map(a => {
      if (a.duration_seconds != null) return a.duration_seconds;
      const ms = new Date(a.completed_at || a.updated_at) - new Date(a.created_at);
      return ms > 0 ? ms / 1000 : null;
    }).filter(d => d !== null);
    const total = durations.length || 1;
    const fast  = durations.filter(d => d < 30).length;
    const slow  = durations.filter(d => d > 60).length;
    return {
      fast, slow,
      total: durations.length,
      fastPct: Math.round(fast / total * 100),
      slowPct: Math.round(slow / total * 100),
    };
  }, [agentActions]);

  /**
   * Fallback time-series derived from agent action timestamps.
   * Used when clusterMetrics.history is unavailable.
   */
  const agentActionChartData = useMemo(() => {
    if (!agentActions.length) return [];
    const grouped = {};
    agentActions.forEach(a => {
      const d   = new Date(a.created_at || a.timestamp || Date.now());
      const key = d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
      if (!grouped[key]) grouped[key] = { time: key, events: 0 };
      grouped[key].events += 1;
    });
    return Object.values(grouped).slice(-12);
  }, [agentActions]);

  return {
    rebalancingActions,
    rebalancingByState,
    agentActions,
    scalingActions,
    timeline,
    behaviorProfile,
    agentActionChartData,
    loading,
    error,
    refetch,
  };
};

export default useExecutionState;
