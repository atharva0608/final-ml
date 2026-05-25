import { useState, useEffect, useCallback, useMemo } from 'react';
import { clusterAPI, optimizeAPI } from '../services/api';

/**
 * Builds a namespace-safe PlanNode map from provision list + raw nodes.
 * Keys: `prov:{prov_node_name}` for provision nodes, `node:{node_name}` for existing.
 * This eliminates the silent fallback bug where mv.to_node could be either namespace.
 */
function buildPlanNodeMap(provisionList, rawNodes, keepNodes) {
  const map = new Map();
  for (const p of (provisionList || [])) {
    const id = `prov:${p.prov_node_name}`;
    map.set(id, { id, type: 'provision', ref: p.prov_node_name, meta: p });
  }
  for (const n of (rawNodes || [])) {
    const id = `node:${n.node_name}`;
    if (!map.has(id)) map.set(id, { id, type: 'existing', ref: n.node_name, meta: n });
  }
  // Keep nodes are valid pod destinations (consolidation targets).
  // Add them so pods_leaving entries pointing at kept nodes resolve correctly.
  for (const k of (keepNodes || [])) {
    const name = typeof k === 'string' ? k : k.node_name;
    const id = `node:${name}`;
    if (!map.has(id)) {
      const meta = typeof k === 'string' ? { node_name: name } : k;
      map.set(id, { id, type: 'existing', ref: name, meta });
    }
  }
  return map;
}

/**
 * Shared hook: cluster list, selection, cluster execution plan, and raw node metrics.
 * Single source of truth — components never fetch these endpoints directly.
 */
const useClusters = () => {
  const [clusters, setClusters]           = useState([]);
  const [selectedId, setSelectedId]       = useState('');
  const [clusterListError, setError]      = useState(null);
  const [clusterPlan, setClusterPlan]     = useState(null);
  const [clusterPlanLoading, setClusterPlanLoading] = useState(false);
  const [rawNodes, setRawNodes]           = useState([]);
  const [rawNodesLoading, setRawNodesLoading] = useState(false);
  const [consolidData, setConsolidData]   = useState(null);

  useEffect(() => {
    clusterAPI.list()
      .then(res => {
        const list = res.data?.clusters || res.data || [];
        setClusters(list);
        if (list.length > 0) setSelectedId(list[0].id);
      })
      .catch(err => setError(err?.message || 'Failed to load clusters'));
  }, []);

  const refreshClusterPlan = useCallback((id) => {
    if (!id) return;
    setClusterPlanLoading(true);
    optimizeAPI.getClusterExecutionPlan(id)
      .then(res => setClusterPlan(res.data?.data ?? res.data))
      .catch(() => setClusterPlan(null))
      .finally(() => setClusterPlanLoading(false));
  }, []);

  const refreshRawNodes = useCallback((id) => {
    if (!id) return;
    setRawNodesLoading(true);
    optimizeAPI.getNodeBinPacking(id)
      .then(res => {
        const d = res.data?.data ?? res.data;
        setRawNodes(d?.nodes ?? []);
        setConsolidData(d?.consolidation_candidates ?? null);
      })
      .catch(() => { setRawNodes([]); setConsolidData(null); })
      .finally(() => setRawNodesLoading(false));
  }, []);

  useEffect(() => {
    if (selectedId) {
      refreshClusterPlan(selectedId);
      refreshRawNodes(selectedId);
    } else {
      setClusterPlan(null);
      setRawNodes([]);
      setConsolidData(null);
    }
  }, [selectedId, refreshClusterPlan, refreshRawNodes]);

  const provisionList = clusterPlan?.provision_nodes ?? [];

  // Prefer backend-authoritative plan_status; fall back to client-side derivation
  // so the field works with older backend versions too.
  const planCompleteness = (clusterPlanLoading && !clusterPlan) ? 'loading'
    : clusterPlan === null                           ? 'none'
    : clusterPlan.plan_status                        ? clusterPlan.plan_status
    : provisionList.length === 0                     ? 'no_action'
    : provisionList.every(p => p.instance_type != null) ? 'resolved'
    : provisionList.some(p => p.instance_type != null)  ? 'partial'
    :                                                  'draft';

  const keepNodeList = clusterPlan?.keep_nodes ?? [];

  const planNodeMap = useMemo(
    () => buildPlanNodeMap(provisionList, rawNodes, keepNodeList),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [clusterPlan, rawNodes]
  );

  return {
    clusters, selectedId, setSelectedId, clusterListError,
    clusterPlan, clusterPlanLoading, refreshClusterPlan,
    rawNodes, rawNodesLoading, consolidData, refreshRawNodes,
    planCompleteness, planNodeMap,
  };
};

export default useClusters;
