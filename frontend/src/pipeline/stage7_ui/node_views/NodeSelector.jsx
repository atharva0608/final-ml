import React, { useState, useEffect } from 'react';
import { FiSearch, FiCpu, FiServer, FiArrowRight, FiZap, FiCheckCircle, FiRefreshCw, FiAlertCircle, FiTrendingDown, FiAlertTriangle } from 'react-icons/fi';
import useClusters from '../../../hooks/useClusters';
import { optimizeAPI } from '../../../services/api';

const LIFECYCLE_LABEL = {
  running:   { label: 'Running',   cls: 'bg-emerald-50 text-emerald-700 border-emerald-200' },
  cordoned:  { label: 'Cordoned', cls: 'bg-amber-50  text-amber-700  border-amber-200' },
  draining:  { label: 'Draining', cls: 'bg-red-50    text-red-700    border-red-200' },
};

function lcMeta(lc) {
  return LIFECYCLE_LABEL[lc] || { label: lc || 'Unknown', cls: 'bg-gray-100 text-gray-600 border-gray-200' };
}

function deriveOptTarget(node, engineIntent, keepReason) {
  // engineIntent: 'keep' | 'drain' | 'replace' | null
  // The engine's plan always takes precedence — never suggest spot migration
  // for a node the engine is keeping (it runs OD-required workloads like
  // Redis, Postgres, anchors, or is the minimum OD baseline).

  if (node.lifecycle_state === 'draining') {
    return { action: 'Terminating', color: 'text-red-700', bg: 'bg-red-50 border-red-200', detail: 'Drain in progress — pods migrating away.' };
  }
  if (node.lifecycle_state === 'cordoned') {
    return { action: 'Cordoned', color: 'text-amber-700', bg: 'bg-amber-50 border-amber-200', detail: 'Node marked unschedulable — no new pods will land here.' };
  }

  // Engine says KEEP → this node hosts OD-required workloads or is an AZ spread anchor.
  if (engineIntent === 'keep') {
    if (keepReason === 'az_spread') {
      return { action: 'AZ Anchor — Keeping', color: 'text-teal-700', bg: 'bg-teal-50 border-teal-200', detail: 'Kept to maintain minimum AZ spread. Pods from consolidated nodes will bin-pack onto this node.' };
    }
    return { action: 'OD Anchor — Keeping', color: 'text-orange-700', bg: 'bg-orange-50 border-orange-200', detail: 'Engine has classified this node as an OD anchor — it hosts workloads that must remain on on-demand (DB, Redis, orchestration controllers). It will not be migrated to spot.' };
  }

  // Engine says REPLACE → being swapped for a bin-packed spot/OD node.
  if (engineIntent === 'replace') {
    return { action: 'Replacing → New Node', color: 'text-blue-700', bg: 'bg-blue-50 border-blue-200', detail: 'Engine is replacing this node with a bin-packed equivalent. Pods are being rescheduled to the provisioned target node.' };
  }

  // Engine says TERMINATE → fully draining, pods consolidate onto existing nodes.
  if (engineIntent === 'drain') {
    return { action: 'Terminating — Consolidating', color: 'text-red-700', bg: 'bg-red-50 border-red-200', detail: 'Engine is draining this node. Pods will move to existing nodes — no replacement node needed.' };
  }

  // No engine opinion yet — fall back to heuristic (only for spot nodes or truly unknown nodes).
  const cpuBuf = node.cpu_buffer_pct ?? 100;
  const memBuf = node.mem_buffer_pct ?? 100;
  const capType = (node.capacity_type || '').toLowerCase();
  const isOD = capType === 'on_demand' || capType === 'on-demand' || capType === 'ondemand';

  if (node.is_overloaded) {
    return { action: 'Scale Up / Redistribute', color: 'text-red-600', bg: 'bg-red-50 border-red-200', detail: `CPU or memory > 85% — redistribute pods or add capacity.` };
  }
  // Only suggest spot migration when engine has no plan AND node is OD AND heavily underused.
  // This should rarely happen once the cluster plan is loaded.
  if (cpuBuf > 80 && memBuf > 80 && isOD) {
    return { action: 'Candidate: Consolidate', color: 'text-blue-700', bg: 'bg-blue-50 border-blue-200', detail: `${Math.round(cpuBuf)}% CPU + ${Math.round(memBuf)}% mem free — underutilised OD node. Engine plan not yet loaded; run a cluster scan to get the engine recommendation.` };
  }
  if (cpuBuf > 70 && memBuf > 70) {
    return { action: 'Consolidate', color: 'text-indigo-700', bg: 'bg-indigo-50 border-indigo-200', detail: `${Math.round(cpuBuf)}% CPU + ${Math.round(memBuf)}% mem free — underutilised; candidate for workload consolidation.` };
  }
  return { action: 'Optimal', color: 'text-green-700', bg: 'bg-green-50 border-green-200', detail: 'Utilisation is healthy — no immediate action needed.' };
}

function CapBar({ label, pct, color = 'bg-blue-400' }) {
  const cl = Math.min(100, Math.max(0, pct ?? 0));
  const barCls = cl > 85 ? 'bg-red-400' : cl > 70 ? 'bg-amber-400' : color;
  return (
    <div className="flex items-center gap-2">
      <span className="text-[10px] text-gray-500 w-10 flex-shrink-0 font-medium">{label}</span>
      <div className="flex-1 h-1.5 bg-gray-100 rounded-full overflow-hidden">
        <div className={`h-full rounded-full ${barCls}`} style={{ width: `${cl}%` }} />
      </div>
      <span className="text-[10px] font-mono text-gray-700 w-8 text-right flex-shrink-0">{Math.round(cl)}%</span>
    </div>
  );
}

export default function NodeSelector() {
  const {
    clusters, selectedId: clusterId, setSelectedId: setClusterId, clusterListError,
    clusterPlan, clusterPlanLoading, refreshClusterPlan,
    rawNodes, rawNodesLoading, consolidData, refreshRawNodes,
    planCompleteness, planNodeMap,
  } = useClusters();
  const [searchTerm, setSearchTerm] = useState('');
  const [desiredSearch, setDesiredSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('all');
  const [planActionFilter, setPlanActionFilter] = useState('all');
  const [expandedRows, setExpandedRows] = useState({});
  const [nodePlans, setNodePlans] = useState({});
  const [planLoading, setPlanLoading] = useState({});
  const [viewMode, setViewMode] = useState('desired'); // 'desired' | 'current'

  useEffect(() => { setExpandedRows({}); setNodePlans({}); }, [clusterId]);

  const toggleRow = (id) => {
    setExpandedRows(prev => {
      const next = { ...prev, [id]: !prev[id] };
      if (next[id] && !nodePlans[id]) {
        setPlanLoading(p => ({ ...p, [id]: true }));
        optimizeAPI.getNodeExecutionPlan(id, clusterId)
          .then(res => setNodePlans(p => ({ ...p, [id]: res.data?.data ?? res.data })))
          .catch(() => setNodePlans(p => ({ ...p, [id]: null })))
          .finally(() => setPlanLoading(p => ({ ...p, [id]: false })));
      }
      return next;
    });
  };

  // Build fast-lookup sets from clusterPlan
  const drainSet = new Set((clusterPlan?.drain_nodes ?? []).map(d => d.node_name));
  // keep_nodes is now an array of objects; handle legacy string format too
  const _keepNodeRaw = clusterPlan?.keep_nodes ?? [];
  const keepSet = new Set(_keepNodeRaw.map(k => (typeof k === 'string' ? k : k.node_name)));
  const keepNodeMap = Object.fromEntries(
    _keepNodeRaw
      .filter(k => typeof k !== 'string')
      .map(k => [k.node_name, k])
  );
  const keepReasonMap = Object.fromEntries(
    _keepNodeRaw
      .filter(k => typeof k !== 'string')
      .map(k => [k.node_name, k.retention_reason || 'od_anchor'])
  );
  const drainMovements = Object.fromEntries(
    (clusterPlan?.drain_nodes ?? []).map(d => [d.node_name, d.pods_leaving ?? []])
  );
  const transitionType = Object.fromEntries(
    (clusterPlan?.drain_nodes ?? []).map(d => [d.node_name, d.transition_type ?? 'TERMINATE'])
  );
  const replacementSpec = Object.fromEntries(
    (clusterPlan?.drain_nodes ?? []).map(d => [d.node_name, d.replacement_spec ?? null])
  );
  const drainMeta = Object.fromEntries(
    (clusterPlan?.drain_nodes ?? []).map(d => [d.node_name, d])
  );
  const workloadClassMap = Object.fromEntries(
    (clusterPlan?.drain_nodes ?? []).map(d => [d.node_name, d.workload_class ?? 'stateless'])
  );
  const execStrategyMap = Object.fromEntries(
    (clusterPlan?.drain_nodes ?? []).map(d => [d.node_name, d.execution_strategy ?? 'ROLLING'])
  );
  const provisionList = clusterPlan?.provision_nodes ?? [];
  const planSummary = clusterPlan?.summary ?? null;

  const consolid = consolidData;

  const spotNodes    = rawNodes.filter(n => (n.capacity_type || '').toLowerCase() === 'spot');
  const odNodes      = rawNodes.filter(n => { const c = (n.capacity_type || '').toLowerCase(); return c === 'on_demand' || c === 'on-demand' || c === 'ondemand'; });
  const spotPct      = rawNodes.length ? Math.round(spotNodes.length / rawNodes.length * 100) : 0;
  const drainingCnt  = rawNodes.filter(n => n.lifecycle_state === 'draining').length;
  const cordonedCnt  = rawNodes.filter(n => n.lifecycle_state === 'cordoned').length;
  const overloadCnt  = rawNodes.filter(n => n.is_overloaded).length;
  // Include nodes the engine is actively draining (drainSet) even before K8s cordons them.
  // This prevents the "plan says TERMINATE but Termination Queue is empty" contradiction.
  const terminatingNodes = rawNodes.filter(n =>
    n.lifecycle_state === 'draining' ||
    n.lifecycle_state === 'cordoned' ||
    drainSet.has(n.node_name)
  );

  const engineDrainCnt = drainSet.size;
  const engineReplaceCnt = (clusterPlan?.drain_nodes ?? []).filter(d => d.transition_type === 'REPLACE').length;
  const engineTerminateCnt = (clusterPlan?.drain_nodes ?? []).filter(d => d.transition_type === 'TERMINATE').length;
  const filterCounts = { all: rawNodes.length, draining: drainingCnt, cordoned: cordonedCnt, overloaded: overloadCnt };

  const filtered = rawNodes.filter(n => {
    const matchText = !searchTerm ||
      (n.node_name || '').toLowerCase().includes(searchTerm.toLowerCase()) ||
      (n.instance_type || '').toLowerCase().includes(searchTerm.toLowerCase());
    const matchStatus =
      statusFilter === 'all'        ? true :
      statusFilter === 'draining'   ? n.lifecycle_state === 'draining' :
      statusFilter === 'cordoned'   ? n.lifecycle_state === 'cordoned' :
      statusFilter === 'overloaded' ? n.is_overloaded : true;
    const nn = n.node_name;
    const matchPlan =
      planActionFilter === 'all'       ? true :
      planActionFilter === 'replace'   ? transitionType[nn] === 'REPLACE' :
      planActionFilter === 'terminate' ? transitionType[nn] === 'TERMINATE' :
      planActionFilter === 'keep'      ? keepSet.has(nn) :
      planActionFilter === 'no_plan'   ? (!drainSet.has(nn) && !keepSet.has(nn)) : true;
    return matchText && matchStatus && matchPlan;
  });

  const estSavings = planSummary?.estimated_monthly_savings_usd ?? consolid?.est_savings_monthly_usd;
  const candCount  = consolid?.consolidation_candidates;

  // Filtered provision list for plan-view search
  const filteredProvList = provisionList.filter(p => {
    if (!desiredSearch) return true;
    const s = desiredSearch.toLowerCase();
    return (p.instance_type || '').toLowerCase().includes(s) ||
           (p.prov_node_name || '').toLowerCase().includes(s) ||
           (p.az || '').toLowerCase().includes(s);
  });

  // Build map: prov_node_name → [{pod_name, from_node, from_instance_type, from_capacity_type}]
  const provNodeSourceMap = {};
  (clusterPlan?.drain_nodes ?? []).forEach(drain => {
    (drain.pods_leaving ?? []).forEach(pod => {
      if (pod.is_new_node && pod.to_node) {
        if (!provNodeSourceMap[pod.to_node]) provNodeSourceMap[pod.to_node] = [];
        provNodeSourceMap[pod.to_node].push({
          pod_name: pod.pod_name,
          from_node: drain.node_name,
          from_instance_type: drain.current_instance_type,
          from_capacity_type: drain.current_capacity_type,
        });
      }
    });
  });

  // Group filteredProvList by AZ for the desired-state view
  const provByAz = {};
  filteredProvList.forEach(p => {
    const az = p.az || 'unknown';
    if (!provByAz[az]) provByAz[az] = [];
    provByAz[az].push(p);
  });
  const azList = Object.keys(provByAz).sort();

  // incomingPodsMap — pods being consolidated ONTO each kept node
  const incomingPodsMap = {};
  (clusterPlan?.drain_nodes ?? []).forEach(dn => {
    (dn.pods_leaving ?? []).forEach(pl => {
      if (!pl.is_new_node && pl.to_node) {
        if (!incomingPodsMap[pl.to_node]) incomingPodsMap[pl.to_node] = [];
        incomingPodsMap[pl.to_node].push({
          pod_name: pl.pod_name,
          from_node: dn.node_name,
          from_instance_type: dn.current_instance_type,
          workload_class: dn.workload_class,
        });
      }
    });
  });

  // Before → After topology stats
  const _isODCap   = c => { const ct = (c || '').toLowerCase(); return ct === 'on-demand' || ct === 'on_demand' || ct === 'ondemand'; };
  const _isSpotCap = c => (c || '').toLowerCase() === 'spot';
  const beforeODCnt    = rawNodes.filter(n => _isODCap(n.capacity_type)).length;
  const beforeSpotCnt  = rawNodes.filter(n => _isSpotCap(n.capacity_type)).length;
  const beforeTotalPods = rawNodes.reduce((s, n) => s + (n.pod_count || 0), 0);
  const afterODCnt  = [...keepSet].filter(name => _isODCap(keepNodeMap[name]?.capacity_type)).length
                    + provisionList.filter(p => _isODCap(p.capacity_type)).length;
  const afterSpotCnt = [...keepSet].filter(name => _isSpotCap(keepNodeMap[name]?.capacity_type)).length
                     + provisionList.filter(p => _isSpotCap(p.capacity_type)).length;
  const afterTotalPods = [...keepSet].reduce((s, name) => {
    const km = keepNodeMap[name]; const rn = rawNodes.find(r => r.node_name === name);
    return s + (km?.pod_count || rn?.pod_count || 0) + (incomingPodsMap[name] || []).length;
  }, 0) + provisionList.reduce((s, p) => s + (p.pod_count || (p.pods || []).length || 0), 0);

  return (
    <div className="min-h-full bg-gray-50 p-6 text-gray-900">
      <div className="max-w-[1500px] mx-auto space-y-6">

        {/* Header */}
        <div className="flex justify-between items-start">
          <div>
            <div className="flex items-center gap-3">
              <div className="p-2 bg-indigo-50 rounded-lg"><FiServer className="w-5 h-5 text-indigo-600" /></div>
              <h1 className="text-xl font-bold text-gray-900 m-0">Node Selection</h1>
            </div>
            <p className="text-xs text-gray-500 mt-2">Live node inventory — capacity type, resource utilisation, and consolidation candidates.</p>
          </div>
          <div className="flex items-center gap-3">
            <select
              value={clusterId || ''}
              onChange={e => setClusterId(e.target.value)}
              className="text-xs border border-gray-300 rounded px-2 py-1.5 bg-white"
            >
              {clusters.map(c => <option key={c.id} value={c.id}>{c.name || c.id}</option>)}
            </select>
            <button
              onClick={() => { refreshRawNodes(clusterId); refreshClusterPlan(clusterId); }}
              disabled={rawNodesLoading || clusterPlanLoading}
              className="px-3 py-1.5 bg-white border border-gray-300 hover:bg-gray-50 text-gray-700 text-xs font-semibold rounded shadow-sm flex items-center gap-1.5"
            >
              <FiRefreshCw className={`w-3.5 h-3.5 ${(rawNodesLoading || clusterPlanLoading) ? 'animate-spin' : ''}`} />
              Refresh
            </button>
          </div>
        </div>

        {/* Summary Strip */}
        <div className="bg-white border border-gray-200 border-l-4 border-l-indigo-500 p-5 rounded-r-lg shadow-sm">
          <h3 className="text-sm font-bold text-gray-800 mb-4 flex items-center gap-2">
            <FiCpu className="text-indigo-500 w-4 h-4" />
            Cluster Snapshot
          </h3>
          <div className="grid grid-cols-3 md:grid-cols-6 gap-6">
            <div>
              <p className="text-[10px] text-gray-500 mb-1 uppercase tracking-wider font-bold">Total Nodes</p>
              <p className="text-2xl font-bold text-gray-900 tracking-tight">{rawNodes.length || '—'}</p>
            </div>
            <div>
              <p className="text-[10px] text-gray-500 mb-1 uppercase tracking-wider font-bold">Spot Nodes</p>
              <p className="text-2xl font-bold text-indigo-600 tracking-tight">{spotNodes.length || '—'}</p>
            </div>
            <div>
              <p className="text-[10px] text-gray-500 mb-1 uppercase tracking-wider font-bold">On-Demand Nodes</p>
              <p className="text-2xl font-bold text-orange-600 tracking-tight">{odNodes.length || '—'}</p>
            </div>
            <div>
              <p className="text-[10px] text-gray-500 mb-1 uppercase tracking-wider font-bold">Draining / Terminating</p>
              <p className={`text-2xl font-bold tracking-tight ${drainingCnt > 0 ? 'text-red-600' : 'text-gray-400'}`}>{drainingCnt}</p>
            </div>
            {clusterPlanLoading && (
            <div>
              <p className="text-[10px] text-gray-500 mb-1 uppercase tracking-wider font-bold">Engine Plan</p>
              <p className="text-sm font-semibold text-gray-400 tracking-tight animate-pulse">Loading…</p>
            </div>
            )}
            {!clusterPlanLoading && keepSet.size > 0 && (
            <div>
              <p className="text-[10px] text-gray-500 mb-1 uppercase tracking-wider font-bold">
                {clusterPlan?.plan_status === 'az_spread' ? 'Kept (AZ Spread)' : 'Kept (OD Anchors)'}
              </p>
              <p className={`text-2xl font-bold tracking-tight ${clusterPlan?.plan_status === 'az_spread' ? 'text-teal-600' : 'text-amber-600'}`}>{keepSet.size}</p>
            </div>
            )}
            {engineReplaceCnt > 0 && (
            <div>
              <p className="text-[10px] text-gray-500 mb-1 uppercase tracking-wider font-bold">Replacing</p>
              <p className="text-2xl font-bold text-orange-600 tracking-tight">{engineReplaceCnt}</p>
            </div>
            )}
            {engineTerminateCnt > 0 && (
            <div>
              <p className="text-[10px] text-gray-500 mb-1 uppercase tracking-wider font-bold">Terminating</p>
              <p className="text-2xl font-bold text-gray-700 tracking-tight">{engineTerminateCnt}</p>
            </div>
            )}
            {provisionList.length > 0 && (
            <div>
              <p className="text-[10px] text-gray-500 mb-1 uppercase tracking-wider font-bold">New Nodes</p>
              <p className="text-2xl font-bold text-indigo-600 tracking-tight">{provisionList.length}</p>
            </div>
            )}
            <div>
              <p className="text-[10px] text-gray-500 mb-1 uppercase tracking-wider font-bold">Consolidation Candidates</p>
              <p className="text-2xl font-bold text-gray-900 tracking-tight">
                {candCount != null ? candCount : <span className="text-xs text-gray-400 font-normal">Pending</span>}
              </p>
            </div>
            <div>
              <p className="text-[10px] text-gray-500 mb-1 uppercase tracking-wider font-bold">Est. Monthly Savings</p>
              <p className="text-2xl font-bold text-emerald-600 tracking-tight">
                {estSavings != null ? `$${Math.round(estSavings).toLocaleString()}` : <span className="text-xs text-gray-400 font-normal">Pending</span>}
              </p>
            </div>
          </div>
        </div>

        {/* Termination Queue — only shown when nodes are draining/cordoned */}
        {terminatingNodes.length > 0 && (
          <div className="bg-red-50 border border-red-200 rounded-lg p-4">
            <div className="flex items-center gap-2 mb-3">
              <FiAlertTriangle className="text-red-600 w-4 h-4 flex-shrink-0" />
              <h3 className="text-sm font-bold text-red-800">Termination Queue ({terminatingNodes.length} node{terminatingNodes.length !== 1 ? 's' : ''})</h3>
            </div>
            <div className="flex flex-wrap gap-3">
              {terminatingNodes.map(n => {
                const lc = lcMeta(n.lifecycle_state);
                const planDrain = drainMeta[n.node_name];
                const totalPods = planDrain?.total_pods_on_node ?? n.pod_count ?? 0;
                const remainingPods = n.pod_count ?? 0;
                const movedPods = Math.max(0, totalPods - remainingPods);
                const progressPct = totalPods > 0 ? Math.round((movedPods / totalPods) * 100) : 0;
                const isDraining = n.lifecycle_state === 'draining';
                const isCordoned = n.lifecycle_state === 'cordoned';
                const isPlanDrain = drainSet.has(n.node_name) && !isDraining && !isCordoned;
                return (
                  <div key={n.node_name} className="bg-white border border-red-200 rounded-lg px-4 py-3 shadow-sm min-w-[240px]">
                    <div className="flex items-center justify-between mb-1">
                      <span className="font-mono text-[12px] font-bold text-gray-900 truncate max-w-[150px]">{n.node_name}</span>
                      <span className={`px-2 py-0.5 text-[9px] font-bold border rounded uppercase ${isPlanDrain ? 'bg-amber-50 text-amber-700 border-amber-200' : lc.cls}`}>
                        {isPlanDrain ? 'Scheduled' : lc.label}
                      </span>
                    </div>
                    <div className="text-[11px] text-gray-500 space-y-0.5">
                      <div>{n.instance_type || '—'} · <span className="font-semibold">{n.capacity_type || '—'}</span></div>
                      <div>{n.az || '—'} · {remainingPods} pods remaining</div>
                    </div>
                    {/* Pod migration progress bar */}
                    {(isDraining || isCordoned) && totalPods > 0 && (
                      <div className="mt-2">
                        <div className="flex justify-between text-[10px] text-gray-500 mb-1">
                          <span className="text-emerald-600 font-medium">{movedPods} pods migrated</span>
                          <span>{progressPct}%</span>
                        </div>
                        <div className="w-full h-1.5 bg-red-100 rounded-full overflow-hidden">
                          <div
                            className="h-full bg-emerald-500 rounded-full transition-all duration-500"
                            style={{ width: `${progressPct}%` }}
                          />
                        </div>
                      </div>
                    )}
                    <div className="mt-1.5 text-[10px] font-medium text-red-600">
                      {isDraining ? 'Drain in progress — pods migrating away'
                        : isCordoned ? 'Cordoned — no new scheduling'
                        : 'Engine consolidation plan — awaiting execution'}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* Error banner */}
        {clusterListError && (
          <div className="flex items-center gap-2 bg-red-50 border border-red-200 text-red-700 text-xs px-4 py-3 rounded">
            <FiAlertCircle className="w-4 h-4 flex-shrink-0" />
            {clusterListError}
          </div>
        )}

        {/* Main Table */}
        <div className="bg-white border border-gray-200 rounded-lg shadow-sm flex flex-col min-h-[600px] overflow-hidden">

          {/* Filter Bar */}
          <div className="bg-gray-50 p-3 border-b border-gray-200 flex items-center justify-between">
            {viewMode === 'current' ? (
              <div className="flex items-center gap-4 flex-1">
                <div className="relative w-64">
                  <FiSearch className="absolute left-2.5 top-1/2 -translate-y-1/2 text-gray-400 w-3.5 h-3.5" />
                  <input
                    type="text"
                    className="w-full pl-8 pr-3 py-1.5 bg-white border border-gray-300 rounded text-xs text-gray-900 focus:outline-none focus:ring-1 focus:ring-indigo-500 shadow-sm"
                    placeholder="Filter by node name or instance type…"
                    value={searchTerm}
                    onChange={e => setSearchTerm(e.target.value)}
                  />
                </div>
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="text-[10px] text-gray-500 font-bold uppercase tracking-wider mr-1">Status:</span>
                  {[['all','All'], ['draining','Draining'], ['cordoned','Cordoned'], ['overloaded','Overloaded']].map(([key, label]) => (
                    <button key={key}
                      onClick={() => setStatusFilter(key)}
                      className={`px-3 py-1 text-[11px] font-medium border rounded-full transition-colors ${
                        statusFilter === key
                          ? 'bg-indigo-50 text-indigo-700 border-indigo-200 font-bold'
                          : 'bg-white text-gray-600 border-gray-200 hover:bg-gray-50'
                      }`}
                    >
                      {label} ({filterCounts[key] ?? 0})
                    </button>
                  ))}
                  {clusterPlan && (
                    <>
                      <span className="text-[10px] text-gray-400 font-bold uppercase tracking-wider mx-1">Plan:</span>
                      {[
                        ['all',       'All',       null],
                        ['replace',   'Replace',   'bg-orange-50 text-orange-700 border-orange-200'],
                        ['terminate', 'Terminate', 'bg-gray-100 text-gray-700 border-gray-300'],
                        ['keep',      'Keep',      'bg-amber-50 text-amber-700 border-amber-200'],
                        ['no_plan',   'No Plan',   null],
                      ].map(([key, label, activeCls]) => (
                        <button key={key}
                          onClick={() => setPlanActionFilter(key)}
                          className={`px-3 py-1 text-[11px] font-medium border rounded-full transition-colors ${
                            planActionFilter === key
                              ? (activeCls || 'bg-indigo-50 text-indigo-700 border-indigo-200') + ' font-bold'
                              : 'bg-white text-gray-600 border-gray-200 hover:bg-gray-50'
                          }`}
                        >
                          {label}
                        </button>
                      ))}
                    </>
                  )}
                </div>
              </div>
            ) : (
              <div className="flex items-center gap-2 flex-1">
                <FiZap className="w-3.5 h-3.5 text-indigo-500 flex-shrink-0" />
                <div className="relative w-72">
                  <FiSearch className="absolute left-2.5 top-1/2 -translate-y-1/2 text-gray-400 w-3.5 h-3.5" />
                  <input
                    type="text"
                    className="w-full pl-8 pr-3 py-1.5 bg-white border border-gray-300 rounded text-xs text-gray-900 focus:outline-none focus:ring-1 focus:ring-indigo-500 shadow-sm"
                    placeholder="Filter by instance type, node name, or AZ…"
                    value={desiredSearch}
                    onChange={e => setDesiredSearch(e.target.value)}
                  />
                </div>
              </div>
            )}
            {/* View mode toggle */}
            <div className="flex items-center gap-1 ml-4 border border-gray-200 rounded-lg p-0.5 bg-white">
              {[['desired', 'Plan View'], ['current', 'Live Nodes']].map(([mode, label]) => (
                <button key={mode} onClick={() => setViewMode(mode)}
                  className={`px-3 py-1.5 text-[11px] font-semibold rounded transition-colors ${
                    viewMode === mode
                      ? 'bg-indigo-600 text-white shadow-sm'
                      : 'text-gray-600 hover:bg-gray-50'
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>

          {/* Plan View — three sections */}
          {viewMode === 'desired' && (
            <div className="flex-1 overflow-auto p-6 space-y-8">

              {/* Plan completeness banner */}
              {planCompleteness === 'loading' && (
                <div className="flex items-center justify-center h-24 text-sm text-gray-400 gap-2">
                  <FiRefreshCw className="w-4 h-4 animate-spin" /> Loading cluster plan…
                </div>
              )}
              {(planCompleteness === 'draft' || planCompleteness === 'partial') && (
                <div className="bg-amber-50 border border-amber-200 rounded-lg px-4 py-3 flex items-center gap-2 text-xs text-amber-800">
                  <FiAlertTriangle className="w-4 h-4 flex-shrink-0 text-amber-500" />
                  <span><strong>Instance types not yet resolved</strong> — run ISS to complete this plan.
                    {planCompleteness === 'partial' && ' Some nodes are already resolved.'}
                  </span>
                  <span className={`ml-auto px-2 py-0.5 rounded text-[10px] font-bold border flex-shrink-0 ${planCompleteness === 'draft' ? 'bg-gray-100 text-gray-600 border-gray-300' : 'bg-amber-100 text-amber-700 border-amber-200'}`}>
                    {planCompleteness === 'draft' ? 'ISS Pending' : 'ISS Partial'}
                  </span>
                </div>
              )}
              {planCompleteness === 'none' && (
                <div className="flex flex-col items-center justify-center h-48 gap-3 text-gray-400">
                  <FiAlertCircle className="w-8 h-8 text-gray-300" />
                  <span className="text-sm">No engine plan available for this cluster.</span>
                </div>
              )}
              {planCompleteness === 'no_action' && (
                <div className="flex flex-col items-center justify-center h-48 gap-3 text-gray-500">
                  <FiCheckCircle className="w-8 h-8 text-green-400" />
                  <span className="text-sm font-semibold">Cluster is already at target state — no node changes needed.</span>
                  <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-green-50 text-green-700 border border-green-200">At Target</span>
                </div>
              )}
              {planCompleteness === 'az_spread' && (
                <div className="bg-teal-50 border border-teal-200 rounded-lg px-4 py-3 flex items-center gap-2 text-xs text-teal-800">
                  <FiCheckCircle className="w-4 h-4 flex-shrink-0 text-teal-500" />
                  <span><strong>AZ Spread Consolidation</strong> — All workloads are already on OD. The engine is consolidating onto {keepSet.size} node{keepSet.size !== 1 ? 's' : ''} (min AZ spread = {clusterPlan?.summary?.min_az_spread ?? '?'}) and bin-packing pods from the remaining {drainSet.size} node{drainSet.size !== 1 ? 's' : ''}.</span>
                  <span className="ml-auto px-2 py-0.5 rounded text-[10px] font-bold border flex-shrink-0 bg-teal-100 text-teal-700 border-teal-200">AZ Spread</span>
                </div>
              )}

              {/* ── Optimization Summary Header ── */}
              {planCompleteness !== 'loading' && planCompleteness !== 'none' && planCompleteness !== 'no_action' && planCompleteness !== 'az_spread' && (
                <div className="border border-gray-200 rounded-xl overflow-hidden shadow-sm">
                  {/* Stat bar */}
                  <div className="px-5 py-4 bg-white grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-4 border-b border-gray-100">
                    {[
                      { label: 'Current Nodes', val: rawNodes.length, cls: 'text-gray-700' },
                      { label: 'Final Nodes',   val: [...keepSet].length + provisionList.length, cls: 'text-gray-700' },
                      { label: 'OD Before',     val: beforeODCnt, cls: 'text-orange-700' },
                      { label: 'OD After',      val: afterODCnt,  cls: afterODCnt < beforeODCnt ? 'text-green-700' : 'text-orange-700' },
                      { label: 'Spot Before',   val: beforeSpotCnt, cls: 'text-indigo-700' },
                      { label: 'Spot After',    val: afterSpotCnt,  cls: afterSpotCnt > beforeSpotCnt ? 'text-green-700' : 'text-indigo-700' },
                    ].map(({ label, val, cls }) => (
                      <div key={label} className="text-center">
                        <p className="text-[10px] text-gray-400 uppercase tracking-wider font-bold mb-0.5">{label}</p>
                        <p className={`text-xl font-bold ${cls}`}>{val}</p>
                      </div>
                    ))}
                  </div>
                  {/* Strategy checklist */}
                  <div className="px-5 py-3 bg-gray-50 flex flex-wrap items-center gap-x-5 gap-y-2">
                    <span className="text-[10px] font-bold text-gray-500 uppercase tracking-wider flex-shrink-0">Active Strategies</span>
                    {[
                      { label: 'Consolidation',          on: drainSet.size > 0 },
                      { label: 'Spot Migration',          on: afterSpotCnt > beforeSpotCnt || provisionList.some(p => (p.capacity_type||'').toLowerCase().includes('spot')) },
                      { label: 'Workload-Aware Placement', on: (clusterPlan?.drain_nodes ?? []).some(d => d.workload_class) },
                      { label: 'AZ Diversification',     on: true },
                      { label: 'DaemonSet-Aware Sizing',  on: true },
                      { label: 'Right-Sizing',           on: false },
                    ].map(({ label, on }) => (
                      <span key={label} className={`flex items-center gap-1 text-[10px] font-semibold px-2 py-0.5 rounded-full border ${on ? 'bg-green-50 text-green-700 border-green-200' : 'bg-gray-100 text-gray-400 border-gray-200 line-through'}`}>
                        <span>{on ? '✓' : '○'}</span>{label}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {/* ── Before → After Cluster Topology ── */}
              {planCompleteness !== 'loading' && planCompleteness !== 'none' && planCompleteness !== 'no_action' && rawNodes.length > 0 && (
                <div className="border border-gray-200 rounded-xl overflow-hidden shadow-sm">
                  <div className="px-5 py-3 bg-gray-50 border-b border-gray-200 flex items-center justify-between flex-wrap gap-2">
                    <h3 className="text-sm font-bold text-gray-800">Before → After Cluster Topology</h3>
                    <div className="flex items-center gap-4 text-xs">
                      <span className="text-gray-500">{rawNodes.length} nodes → <span className="font-bold text-gray-700">{[...keepSet].length + provisionList.length}</span></span>
                      <span className="text-red-600 font-bold">−{drainSet.size} removed</span>
                      <span className="text-indigo-600 font-bold">+{provisionList.length} new</span>
                    </div>
                  </div>
                  <div className="grid grid-cols-2 divide-x divide-gray-200">
                    {/* BEFORE */}
                    <div className="p-4">
                      <div className="flex items-center justify-between mb-2">
                        <span className="text-[11px] font-bold text-gray-500 uppercase tracking-wider">Before</span>
                        <div className="flex gap-1.5 text-[9px] font-bold">
                          <span className="px-1.5 py-0.5 bg-orange-50 text-orange-700 border border-orange-200 rounded">{beforeODCnt} OD</span>
                          <span className="px-1.5 py-0.5 bg-indigo-50 text-indigo-700 border border-indigo-200 rounded">{beforeSpotCnt} Spot</span>
                        </div>
                      </div>
                      <div className="space-y-1 max-h-48 overflow-y-auto">
                        {rawNodes.map((n, i) => {
                          const isK = keepSet.has(n.node_name);
                          const isD = !isK && drainSet.has(n.node_name); // keep always overrides drain
                          return (
                            <div key={i} className={`flex items-center gap-1.5 px-2 py-1 rounded text-[11px] ${isD ? 'opacity-50' : ''}`}>
                              <span className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${isD ? 'bg-red-400' : isK ? 'bg-amber-400' : 'bg-gray-300'}`} />
                              <span className={`font-mono flex-1 truncate ${isD ? 'line-through text-gray-400' : 'text-gray-700'}`}>{n.node_name.split('.')[0]}</span>
                              <span className="text-gray-400 flex-shrink-0">{n.pod_count ?? '?'} pods</span>
                              <span className={`text-[9px] font-bold uppercase flex-shrink-0 w-8 text-right ${isD ? 'text-red-500' : isK ? 'text-amber-600' : 'text-gray-300'}`}>
                                {isD ? 'OUT' : isK ? 'KEEP' : ''}
                              </span>
                            </div>
                          );
                        })}
                      </div>
                    </div>
                    {/* AFTER */}
                    <div className="p-4">
                      <div className="flex items-center justify-between mb-2">
                        <span className="text-[11px] font-bold text-gray-500 uppercase tracking-wider">After</span>
                        <div className="flex gap-1.5 text-[9px] font-bold">
                          <span className="px-1.5 py-0.5 bg-orange-50 text-orange-700 border border-orange-200 rounded">{afterODCnt} OD</span>
                          <span className="px-1.5 py-0.5 bg-indigo-50 text-indigo-700 border border-indigo-200 rounded">{afterSpotCnt} Spot</span>
                        </div>
                      </div>
                      <div className="space-y-1 max-h-48 overflow-y-auto">
                        {[...keepSet].map((name, i) => {
                          const km = keepNodeMap[name]; const rn = rawNodes.find(r => r.node_name === name);
                          const cur = km?.pod_count || rn?.pod_count || 0;
                          const inc = (incomingPodsMap[name] || []).length;
                          const isODk = _isODCap(km?.capacity_type || rn?.capacity_type);
                          return (
                            <div key={`k${i}`} className="flex items-center gap-1.5 px-2 py-1 rounded text-[11px] bg-amber-50/40">
                              <span className="w-1.5 h-1.5 rounded-full flex-shrink-0 bg-amber-400" />
                              <span className="font-mono flex-1 truncate text-gray-700">{name.split('.')[0]}</span>
                              <span className="text-gray-500 flex-shrink-0">{cur}{inc > 0 ? <span className="text-green-600 font-bold">+{inc}</span> : ''} pods</span>
                              <span className={`text-[9px] font-bold uppercase flex-shrink-0 w-12 text-right ${isODk ? 'text-orange-600' : 'text-indigo-600'}`}>{isODk ? 'OD' : 'SPOT'}</span>
                            </div>
                          );
                        })}
                        {provisionList.map((p, i) => {
                          const isSpot = _isSpotCap(p.capacity_type);
                          return (
                            <div key={`p${i}`} className="flex items-center gap-1.5 px-2 py-1 rounded text-[11px] bg-indigo-50/40">
                              <span className="w-1.5 h-1.5 rounded-full flex-shrink-0 bg-indigo-400" />
                              <span className="font-mono flex-1 truncate text-gray-600 italic">{p.prov_node_name}</span>
                              <span className="text-gray-500 flex-shrink-0">{p.pod_count || (p.pods||[]).length} pods</span>
                              <span className={`text-[9px] font-bold uppercase flex-shrink-0 w-12 text-right ${isSpot ? 'text-indigo-600' : 'text-orange-600'}`}>NEW {isSpot ? 'SPOT' : 'OD'}</span>
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  </div>
                  {/* Summary footer bar */}
                  <div className="px-5 py-2.5 bg-gray-50 border-t border-gray-200 flex items-center justify-around flex-wrap gap-3 text-xs">
                    <div className="flex items-center gap-1.5">
                      <span className="text-gray-500">OD nodes:</span>
                      <span className="font-bold text-orange-700">{beforeODCnt} → {afterODCnt}</span>
                      {afterODCnt < beforeODCnt && <span className="text-green-600 font-bold text-[10px]">↓{beforeODCnt - afterODCnt} saved</span>}
                    </div>
                    <div className="flex items-center gap-1.5">
                      <span className="text-gray-500">Spot nodes:</span>
                      <span className="font-bold text-indigo-700">{beforeSpotCnt} → {afterSpotCnt}</span>
                      {afterSpotCnt !== beforeSpotCnt && <span className={`font-bold text-[10px] ${afterSpotCnt > beforeSpotCnt ? 'text-indigo-600' : 'text-gray-400'}`}>{afterSpotCnt > beforeSpotCnt ? `+${afterSpotCnt - beforeSpotCnt}` : `↓${beforeSpotCnt - afterSpotCnt}`}</span>}
                    </div>
                    <div className="flex items-center gap-1.5">
                      <span className="text-gray-500">Total pods:</span>
                      <span className="font-bold text-gray-700">{beforeTotalPods} → {afterTotalPods}</span>
                    </div>
                  </div>
                </div>
              )}

              {/* ── Section A: Nodes to Provision ── */}
              {planCompleteness !== 'loading' && planCompleteness !== 'none' && planCompleteness !== 'no_action' && (
                <div>
                  <div className="flex items-center gap-3 mb-4">
                    <h3 className="text-sm font-bold text-gray-800 flex items-center gap-2 flex-shrink-0">
                      <span className="w-5 h-5 rounded-full bg-indigo-600 text-white text-[10px] font-bold flex items-center justify-center flex-shrink-0">A</span>
                      Nodes to Provision
                      <span className="px-2 py-0.5 text-[10px] font-bold bg-indigo-50 text-indigo-700 border border-indigo-200 rounded-full">{filteredProvList.length}</span>
                    </h3>
                    <div className="h-px flex-1 bg-gray-200" />
                  </div>
                  {filteredProvList.length === 0 ? (
                    <div className="text-xs text-gray-400 italic py-3">No provision nodes match the current filter.</div>
                  ) : (
                    <div className="space-y-8">
                  {azList.map(az => (
                    <div key={az}>
                      {/* AZ header */}
                      <div className="flex items-center gap-3 mb-4">
                        <div className="h-px flex-1 bg-gray-200" />
                        <span className="px-3 py-1 bg-indigo-50 text-indigo-700 border border-indigo-200 rounded-full text-[11px] font-bold uppercase tracking-wider">
                          AZ: {az}
                        </span>
                        <div className="h-px flex-1 bg-gray-200" />
                      </div>
                      {/* Node cards in this AZ */}
                      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                        {provByAz[az].map((prov, idx) => {
                          const isSpot = (prov.capacity_type || '').toLowerCase() === 'spot';
                          const podRouting = provNodeSourceMap[prov.prov_node_name] || [];
                          const totalCpu = (prov.pods || []).reduce((s, p) => s + (p.cpu_request_millicores || 0), 0);
                          const totalMem = (prov.pods || []).reduce((s, p) => s + (p.memory_request_mb || 0), 0);
                          const fromNodes = [...new Set(podRouting.map(r => r.from_node))];
                          return (
                            <div key={idx} className={`border rounded-xl shadow-sm overflow-hidden ${isSpot ? 'border-indigo-200' : 'border-orange-200'}`}>
                              {/* Card header */}
                              <div className={`px-5 py-3 flex items-center justify-between ${isSpot ? 'bg-indigo-50' : 'bg-orange-50'}`}>
                                <div className="flex items-center gap-3">
                                  <FiServer className={`w-4 h-4 ${isSpot ? 'text-indigo-600' : 'text-orange-600'}`} />
                                  <div>
                                    <span className="font-mono text-[13px] font-bold text-gray-900">
                                      {prov.instance_type || 'TBD'}
                                    </span>
                                    <span className="ml-2 text-[10px] text-gray-500 font-mono">{prov.prov_node_name}</span>
                                  </div>
                                </div>
                                <div className="flex items-center gap-2">
                                  <span className={`px-2 py-0.5 text-[10px] font-bold rounded-full border uppercase ${isSpot ? 'bg-indigo-100 text-indigo-700 border-indigo-200' : 'bg-orange-100 text-orange-700 border-orange-200'}`}>
                                    {prov.capacity_type || 'spot'}
                                  </span>
                                  <span className="px-2 py-0.5 text-[10px] font-bold rounded-full border bg-white text-gray-600 border-gray-200">
                                    {prov.pod_count || (prov.pods || []).length} pods
                                  </span>
                                </div>
                              </div>

                              {/* Resource totals + heatbars */}
                              <div className="px-5 py-3 bg-white border-b border-gray-100 space-y-2">
                                <div className="grid grid-cols-3 gap-4 mb-2">
                                  <div>
                                    <p className="text-[10px] text-gray-400 uppercase tracking-wider mb-0.5">CPU Request</p>
                                    <p className="text-sm font-bold text-gray-900 font-mono">{totalCpu >= 1000 ? `${(totalCpu/1000).toFixed(1)}` : totalCpu}<span className="text-[10px] text-gray-400 ml-1">{totalCpu >= 1000 ? 'cores' : 'm'}</span></p>
                                  </div>
                                  <div>
                                    <p className="text-[10px] text-gray-400 uppercase tracking-wider mb-0.5">Mem Request</p>
                                    <p className="text-sm font-bold text-gray-900 font-mono">{totalMem >= 1024 ? `${(totalMem/1024).toFixed(1)}` : Math.round(totalMem)}<span className="text-[10px] text-gray-400 ml-1">{totalMem >= 1024 ? 'GiB' : 'MiB'}</span></p>
                                  </div>
                                  <div>
                                    <p className="text-[10px] text-gray-400 uppercase tracking-wider mb-0.5">Replacing</p>
                                    <p className="text-sm font-bold text-gray-700 truncate">{fromNodes.length > 0 ? fromNodes.length + ' node' + (fromNodes.length > 1 ? 's' : '') : '—'}</p>
                                  </div>
                                </div>
                                {prov.required_cpu_millicores > 0 && (
                                  <CapBar label="CPU" pct={Math.round(totalCpu / prov.required_cpu_millicores * 100)} color="bg-indigo-400" />
                                )}
                                {prov.required_memory_bytes > 0 && (
                                  <CapBar label="MEM" pct={Math.round((totalMem * 1024 * 1024) / prov.required_memory_bytes * 100)} color="bg-purple-400" />
                                )}
                                <CapBar label="PODS" pct={Math.min(100, ((prov.pod_count || (prov.pods||[]).length) / 58) * 100)} color="bg-teal-400" />
                              </div>

                              {/* Pod routing table */}
                              <div className="px-5 py-3 bg-white max-h-52 overflow-y-auto">
                                <p className="text-[10px] font-bold text-gray-400 uppercase tracking-wider mb-2">Pod Routing</p>
                                {(prov.pods || []).length === 0 ? (
                                  <p className="text-xs text-gray-400 italic">No pod data available</p>
                                ) : (prov.pods || []).map((pod, pi) => {
                                  const routing = podRouting.find(r => r.pod_name === pod.pod_name);
                                  return (
                                    <div key={pi} className="flex items-start gap-2 py-1.5 border-b border-gray-50 last:border-0">
                                      <div className="flex-1 min-w-0">
                                        <p className="font-mono text-[12px] text-gray-900 truncate">{pod.pod_name}</p>
                                        {routing && (
                                          <p className="text-[10px] text-gray-400 mt-0.5 flex items-center gap-1">
                                            <span className="font-mono truncate max-w-[120px]">{routing.from_node}</span>
                                            <FiArrowRight className="w-2.5 h-2.5 flex-shrink-0 text-indigo-400" />
                                            <span className="font-mono text-indigo-600 font-medium">{prov.prov_node_name}</span>
                                          </p>
                                        )}
                                      </div>
                                      <div className="text-right flex-shrink-0">
                                        <p className="text-[11px] font-mono text-gray-600">{pod.cpu_request_millicores}m</p>
                                        <p className="text-[11px] font-mono text-gray-400">{pod.memory_request_mb}MiB</p>
                                      </div>
                                    </div>
                                  );
                                })}
                              </div>

                              {/* Source nodes footer */}
                              {fromNodes.length > 0 && (
                                <div className="px-5 py-2 bg-gray-50 border-t border-gray-100">
                                  <p className="text-[10px] text-gray-400 uppercase tracking-wider mb-1">Draining from</p>
                                  <div className="flex flex-wrap gap-1">
                                    {fromNodes.map((fn, fi) => (
                                      <span key={fi} className="px-2 py-0.5 bg-red-50 border border-red-200 text-red-700 rounded text-[10px] font-mono truncate max-w-[160px]">{fn}</span>
                                    ))}
                                  </div>
                                </div>
                              )}
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  ))}
                </div>
              )}
                </div>
              )}

              {/* ── Section B: Nodes Being Kept ── */}
              {planCompleteness !== 'loading' && planCompleteness !== 'none' && keepSet.size > 0 && (
                <div>
                  <div className="flex items-center gap-3 mb-4">
                    <h3 className="text-sm font-bold text-gray-800 flex items-center gap-2 flex-shrink-0">
                      <span className="w-5 h-5 rounded-full bg-amber-500 text-white text-[10px] font-bold flex items-center justify-center flex-shrink-0">B</span>
                      Nodes Being Kept (OD Anchors)
                      <span className="px-2 py-0.5 text-[10px] font-bold bg-amber-50 text-amber-700 border border-amber-200 rounded-full">{keepSet.size}</span>
                    </h3>
                    <div className="h-px flex-1 bg-gray-200" />
                  </div>
                  <div className="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 gap-3">
                    {[...keepSet].map(nodeName => {
                      const n = rawNodes.find(r => r.node_name === nodeName);
                      const km = keepNodeMap[nodeName] ?? {};
                      const instType = n?.instance_type || km.instance_type || '—';
                      const capType  = n?.capacity_type || km.capacity_type || '—';
                      const az       = n?.az || km.az || '—';
                      const podCnt   = n?.pod_count ?? km.pod_count ?? '?';
                      const capCls = (capType || '').toLowerCase() === 'spot'
                        ? 'bg-indigo-50 text-indigo-700 border-indigo-200'
                        : 'bg-orange-50 text-orange-700 border-orange-200';
                      const reason = km.retention_reason;
                      const REASON_LABEL = {
                        od_anchor:   { label: 'OD Anchor', cls: 'bg-orange-100 text-orange-700 border-orange-200', detail: 'On-demand node kept as a cost anchor; spot pods are placed around it.' },
                        fits_pods:   { label: 'Fits Pods',  cls: 'bg-green-100 text-green-700 border-green-200',   detail: 'Existing node has sufficient spare capacity to absorb relocating pods — no replacement needed.' },
                        drain_reuse: { label: 'Drain Reuse', cls: 'bg-blue-100 text-blue-700 border-blue-200',    detail: 'Node will be emptied by outgoing moves and repurposed to receive incoming pods, avoiding a new provision.' },
                      };
                      const rl = reason ? (REASON_LABEL[reason] || { label: reason, cls: 'bg-gray-100 text-gray-600 border-gray-200', detail: '' }) : null;
                      return (
                        <div key={nodeName} className="border border-amber-200 rounded-lg bg-amber-50/30 overflow-hidden">
                          <div className="px-4 py-2.5 bg-amber-50 border-b border-amber-100 flex items-center justify-between">
                            <div className="flex items-center gap-2 min-w-0">
                              <FiServer className="w-3 h-3 text-amber-600 flex-shrink-0" />
                              <span className="font-mono text-[12px] font-bold text-gray-900 truncate">{nodeName.split('.')[0]}</span>
                            </div>
                            <span className="px-1.5 py-0.5 text-[9px] font-bold bg-amber-100 text-amber-700 border border-amber-300 rounded uppercase ml-2 flex-shrink-0">KEPT</span>
                          </div>
                          <div className="px-4 py-3 space-y-1.5 text-xs">
                            <div className="flex items-center gap-2">
                              <span className="font-mono text-gray-700 font-semibold">{instType}</span>
                              <span className={`px-1.5 py-0.5 text-[9px] font-bold border rounded uppercase ${capCls}`}>{capType}</span>
                            </div>
                            <div className="text-gray-400 font-mono text-[11px]">{az}</div>
                            {/* Capacity bars from live metrics */}
                            {(() => {
                              const rn = rawNodes.find(r => r.node_name === nodeName);
                              const incoming = incomingPodsMap[nodeName] || [];
                              const curPods = km.pod_count || rn?.pod_count || 0;
                              const finalPods = curPods + incoming.length;
                              const allocCPU = rn?.allocatable_cpu_millicores || 0;
                              const allocMem = rn?.allocatable_memory_bytes || 0;
                              const afterCPUpct = allocCPU > 0 && rn ? Math.min(100, Math.round(((rn.cpu_actual_pct / 100 * allocCPU)) / allocCPU * 100)) : null;
                              return (
                                <>
                                  {rn && (
                                    <div className="mt-1.5 space-y-1">
                                      <CapBar label="CPU" pct={rn.cpu_actual_pct ?? 0} color="bg-blue-400" />
                                      <CapBar label="MEM" pct={rn.mem_actual_pct ?? 0} color="bg-purple-400" />
                                      <CapBar label="PODS" pct={Math.min(100, (curPods / Math.max(rn.allocatable_cpu_millicores ? 58 : 20, 1)) * 100)} color="bg-teal-400" />
                                    </div>
                                  )}
                                  {/* Incoming pods panel */}
                                  <div className={`mt-2 border rounded px-3 py-2 ${incoming.length > 0 ? 'border-green-200 bg-green-50/40' : 'border-gray-100 bg-gray-50/40'}`}>
                                    <div className="grid grid-cols-3 gap-2 text-center mb-1.5">
                                      <div>
                                        <div className="text-[9px] text-gray-400 uppercase font-bold">Current</div>
                                        <div className="text-sm font-bold text-gray-700">{curPods}</div>
                                        <div className="text-[9px] text-gray-400">pods</div>
                                      </div>
                                      <div>
                                        <div className="text-[9px] text-green-600 uppercase font-bold">Incoming</div>
                                        <div className={`text-sm font-bold ${incoming.length > 0 ? 'text-green-700' : 'text-gray-400'}`}>+{incoming.length}</div>
                                        <div className="text-[9px] text-gray-400">pods</div>
                                      </div>
                                      <div>
                                        <div className="text-[9px] text-gray-700 uppercase font-bold">Final</div>
                                        <div className="text-sm font-bold text-gray-900">{finalPods}</div>
                                        <div className="text-[9px] text-gray-400">pods</div>
                                      </div>
                                    </div>
                                    {incoming.length > 0 && (
                                      <div className="border-t border-green-100 pt-1.5 space-y-0.5 max-h-20 overflow-y-auto">
                                        {incoming.map((ip, ii) => (
                                          <div key={ii} className="flex items-center gap-1 text-[10px] text-gray-600">
                                            <FiArrowRight className="w-2.5 h-2.5 flex-shrink-0 text-green-500" />
                                            <span className="font-mono truncate flex-1">{ip.pod_name}</span>
                                            <span className="text-[9px] text-gray-400 font-mono truncate max-w-[90px]">{ip.from_node?.split('.')[0]}</span>
                                          </div>
                                        ))}
                                      </div>
                                    )}
                                  </div>
                                </>
                              );
                            })()}
                            {rl ? (
                              <div className={`mt-2 border rounded px-3 py-2 text-[11px] ${rl.cls}`}>
                                <div className="flex items-center justify-between mb-1">
                                  <span className="font-semibold">Retention reason</span>
                                  <span className={`text-[9px] font-bold border rounded px-1.5 py-0.5 ${rl.cls}`}>{rl.label}</span>
                                </div>
                                {rl.detail && <p className="leading-snug opacity-80">{rl.detail}</p>}
                              </div>
                            ) : (
                              <div className="mt-2 bg-amber-100/60 border border-amber-200 rounded px-3 py-2 text-[11px] text-amber-800">
                                <p className="leading-snug">No retention reason from engine.</p>
                              </div>
                            )}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}

              {/* ── Section C: Nodes Being Drained ── */}
              {planCompleteness !== 'loading' && planCompleteness !== 'none' && drainSet.size > 0 && (
                <div>
                  <div className="flex items-center gap-3 mb-4">
                    <h3 className="text-sm font-bold text-gray-800 flex items-center gap-2 flex-shrink-0">
                      <span className="w-5 h-5 rounded-full bg-red-500 text-white text-[10px] font-bold flex items-center justify-center flex-shrink-0">C</span>
                      Nodes Being Drained
                      <span className="px-2 py-0.5 text-[10px] font-bold bg-red-50 text-red-700 border border-red-200 rounded-full">{drainSet.size}</span>
                    </h3>
                    <div className="h-px flex-1 bg-gray-200" />
                  </div>
                  <div className="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 gap-3">
                    {(clusterPlan?.drain_nodes ?? []).map((dn, i) => {
                      const tx = dn.transition_type || 'TERMINATE';
                      const rep = dn.replacement_spec ?? null;
                      const isReplace = tx === 'REPLACE';
                      const rn = rawNodes.find(r => r.node_name === dn.node_name);
                      const podsLeaving = dn.pods_leaving || [];
                      const toNewNode = podsLeaving.filter(p => p.is_new_node).length;
                      const toExisting = podsLeaving.filter(p => !p.is_new_node && p.to_node).length;
                      const destNodes = [...new Set(podsLeaving.filter(p => p.to_node).map(p => p.to_node?.split('.')[0]))];
                      return (
                        <div key={i} className={`border rounded-lg overflow-hidden ${isReplace ? 'border-orange-200' : 'border-gray-200'}`}>
                          {/* Card header */}
                          <div className={`px-4 py-2.5 border-b flex items-center justify-between ${isReplace ? 'bg-orange-50 border-orange-100' : 'bg-gray-100 border-gray-200'}`}>
                            <div className="flex items-center gap-2 min-w-0">
                              <FiServer className={`w-3 h-3 flex-shrink-0 ${isReplace ? 'text-orange-600' : 'text-gray-500'}`} />
                              <span className="font-mono text-[12px] font-bold text-gray-900 truncate">{dn.node_name ? dn.node_name.split('.')[0] : '—'}</span>
                            </div>
                            <div className="flex items-center gap-1.5 ml-2 flex-shrink-0">
                              {dn.workload_class && <span className="px-1.5 py-0.5 text-[9px] font-bold border rounded bg-gray-50 text-gray-600 border-gray-300 uppercase">{dn.workload_class}</span>}
                              <span className={`px-1.5 py-0.5 text-[9px] font-bold border rounded uppercase ${isReplace ? 'bg-orange-100 text-orange-700 border-orange-200' : 'bg-red-100 text-red-700 border-red-200'}`}>{tx}</span>
                            </div>
                          </div>
                          <div className="px-4 py-3 space-y-2 text-xs">
                            {/* Instance + capacity type */}
                            <div className="flex items-center gap-2">
                              <span className="font-mono text-gray-700 font-semibold">{dn.current_instance_type || '—'}</span>
                              <span className={`px-1.5 py-0.5 text-[9px] font-bold border rounded uppercase ${(dn.current_capacity_type || '').toLowerCase() === 'spot' ? 'bg-indigo-50 text-indigo-700 border-indigo-200' : 'bg-orange-50 text-orange-700 border-orange-200'}`}>{dn.current_capacity_type || '—'}</span>
                              <span className="text-gray-400 font-mono text-[10px]">{dn.az || '—'}</span>
                            </div>
                            {/* Capacity bars */}
                            {rn && (
                              <div className="space-y-1">
                                <CapBar label="CPU" pct={rn.cpu_actual_pct ?? 0} color="bg-red-300" />
                                <CapBar label="MEM" pct={rn.mem_actual_pct ?? 0} color="bg-red-300" />
                              </div>
                            )}
                            {/* Pod routing summary */}
                            <div className="border border-gray-100 rounded px-2.5 py-2 bg-gray-50/60 space-y-1">
                              <div className="flex items-center justify-between text-[10px]">
                                <span className="text-gray-500 font-medium">{podsLeaving.length} pods leaving</span>
                                <div className="flex gap-2">
                                  {toNewNode > 0 && <span className="text-indigo-600 font-bold">→ {toNewNode} new node</span>}
                                  {toExisting > 0 && <span className="text-amber-600 font-bold">→ {toExisting} existing</span>}
                                </div>
                              </div>
                              {destNodes.length > 0 && (
                                <div className="flex flex-wrap gap-1 mt-1">
                                  {destNodes.slice(0, 3).map((nd, di) => (
                                    <span key={di} className="px-1.5 py-0.5 bg-white border border-gray-200 text-gray-600 rounded text-[9px] font-mono truncate max-w-[110px]">{nd}</span>
                                  ))}
                                  {destNodes.length > 3 && <span className="text-[9px] text-gray-400">+{destNodes.length - 3} more</span>}
                                </div>
                              )}
                            </div>
                            {/* REPLACE chain */}
                            {isReplace && rep && (
                              <div className="flex items-center gap-2 text-[11px] border border-orange-200 rounded px-2.5 py-2 bg-orange-50/60">
                                <span className="text-gray-500 font-mono truncate max-w-[80px]">{dn.current_instance_type}</span>
                                <FiArrowRight className="w-3 h-3 text-orange-500 flex-shrink-0" />
                                <span className={`font-bold ${rep.instance_type ? 'text-orange-700' : 'text-amber-500 italic'}`}>
                                  {rep.capacity_type?.toUpperCase()} {rep.instance_type || 'Pending ISS'}
                                </span>
                              </div>
                            )}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}

            </div>
          )}

          {/* Table (Live Nodes view) */}
          {viewMode === 'current' && <div className="flex-1 overflow-auto bg-white">
            <table className="w-full text-left border-collapse">
              <thead className="sticky top-0 bg-gray-50 border-b border-gray-200 z-10">
                <tr>
                  <th className="px-4 py-3 w-8"></th>
                  <th className="px-4 py-3 text-[10px] font-bold text-gray-500 uppercase tracking-wider">Node</th>
                  <th className="px-4 py-3 text-[10px] font-bold text-gray-500 uppercase tracking-wider">Instance / Capacity</th>
                  <th className="px-4 py-3 text-[10px] font-bold text-gray-500 uppercase tracking-wider text-right">$/hr</th>
                  <th className="px-4 py-3 text-[10px] font-bold text-gray-500 uppercase tracking-wider">CPU util</th>
                  <th className="px-4 py-3 text-[10px] font-bold text-gray-500 uppercase tracking-wider">Mem util</th>
                  <th className="px-4 py-3 text-[10px] font-bold text-gray-500 uppercase tracking-wider">Pods</th>
                  <th className="px-4 py-3 text-[10px] font-bold text-gray-500 uppercase tracking-wider">Plan</th>
                  <th className="px-4 py-3 text-[10px] font-bold text-gray-500 uppercase tracking-wider">State</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {rawNodesLoading ? (
                  <tr><td colSpan="9" className="px-4 py-12 text-center text-xs text-gray-500">Loading nodes…</td></tr>
                ) : !clusterId ? (
                  <tr><td colSpan="9" className="px-4 py-12 text-center text-xs text-gray-500">Select a cluster to view nodes.</td></tr>
                ) : filtered.length === 0 ? (
                  <tr><td colSpan="9" className="px-4 py-12 text-center text-xs text-gray-500">No nodes match your filters.</td></tr>
                ) : filtered.map(node => {
                  const id = node.node_name;
                  const isExpanded = !!expandedRows[id];
                  const lc = lcMeta(node.lifecycle_state);
                  const capCls = (node.capacity_type || '').toLowerCase() === 'spot'
                    ? 'bg-indigo-50 text-indigo-700 border-indigo-200'
                    : 'bg-gray-100 text-gray-600 border-gray-200';
                  const isEngineDrain = drainSet.has(id);
                  const isEngineKeep  = keepSet.has(id);
                  const txType = transitionType[id]; // 'REPLACE' | 'TERMINATE' | undefined
                  const repSpec = replacementSpec[id];
                  // Derive engine intent for this node — used by deriveOptTarget to avoid misleading labels
                  const engineIntent = isEngineKeep ? 'keep'
                    : txType === 'REPLACE' ? 'replace'
                    : txType === 'TERMINATE' ? 'drain'
                    : null;
                  return (
                    <React.Fragment key={id}>
                      <tr onClick={() => toggleRow(id)}
                        className={`cursor-pointer transition-colors ${
                          txType === 'REPLACE'  ? 'bg-orange-50/60 hover:bg-orange-50'
                          : txType === 'TERMINATE' ? 'bg-gray-100/80 opacity-70 hover:opacity-90'
                          : isEngineKeep       ? 'bg-green-50/40 hover:bg-green-50'
                          : isExpanded         ? 'bg-indigo-50/40' : 'hover:bg-gray-50'
                        }`}
                      >
                        <td className="px-4 py-3">
                          <div className={`w-2.5 h-2.5 rounded-full ${isExpanded ? 'bg-indigo-500 ring-2 ring-indigo-500/30' : 'bg-gray-300'}`} />
                        </td>
                        <td className="px-4 py-3">
                          <div className="font-mono text-[13px] font-semibold text-gray-900">{node.node_name}</div>
                          <div className="text-[11px] text-gray-500 mt-0.5">{node.az || '—'}</div>
                        </td>
                        <td className="px-4 py-3">
                          <div className="flex items-center gap-2">
                            <span className="font-mono text-[13px] font-medium text-gray-800">{node.instance_type || '—'}</span>
                            <span className={`px-1.5 py-0.5 text-[9px] font-bold border rounded uppercase tracking-wider ${capCls}`}>
                              {node.capacity_type || '—'}
                            </span>
                          </div>
                        </td>
                        <td className="px-4 py-3 text-right font-mono text-[13px] text-gray-600">
                          {node.hourly_price_usd != null ? `$${node.hourly_price_usd.toFixed(3)}` : <span className="text-gray-400 text-xs">—</span>}
                        </td>
                        <td className="px-4 py-3">
                          <div className="flex items-center gap-2 w-28">
                            <span className={`text-[12px] font-semibold w-9 ${node.cpu_actual_pct > 80 ? 'text-red-600' : 'text-gray-700'}`}>
                              {node.cpu_actual_pct ?? '—'}%
                            </span>
                            <div className="h-1.5 flex-1 bg-gray-200 rounded-full overflow-hidden">
                              <div className={`h-full rounded-full ${node.cpu_actual_pct > 80 ? 'bg-red-400' : 'bg-indigo-400'}`}
                                style={{ width: `${node.cpu_actual_pct ?? 0}%` }} />
                            </div>
                          </div>
                        </td>
                        <td className="px-4 py-3">
                          <div className="flex items-center gap-2 w-28">
                            <span className={`text-[12px] font-semibold w-9 ${node.mem_actual_pct > 80 ? 'text-red-600' : 'text-gray-700'}`}>
                              {node.mem_actual_pct ?? '—'}%
                            </span>
                            <div className="h-1.5 flex-1 bg-gray-200 rounded-full overflow-hidden">
                              <div className={`h-full rounded-full ${node.mem_actual_pct > 80 ? 'bg-red-400' : 'bg-violet-400'}`}
                                style={{ width: `${node.mem_actual_pct ?? 0}%` }} />
                            </div>
                          </div>
                        </td>
                        <td className="px-4 py-3 text-[13px] text-gray-700 font-medium">{node.pod_count ?? '—'}</td>
                        {/* Plan column */}
                        <td className="px-4 py-3">
                          {clusterPlanLoading ? (
                            <div className="h-4 w-20 bg-gray-200 rounded animate-pulse" />
                          ) : txType === 'REPLACE' ? (
                            <span className="px-1.5 py-0.5 text-[9px] font-bold bg-orange-600 text-white rounded uppercase whitespace-nowrap">
                              REPLACE → {repSpec?.instance_type || repSpec?.capacity_type?.toUpperCase() || 'SPOT'}
                            </span>
                          ) : txType === 'TERMINATE' ? (
                            <span className="px-1.5 py-0.5 text-[9px] font-bold bg-gray-700 text-white rounded uppercase">TERMINATE</span>
                          ) : isEngineKeep ? (
                            <span className="px-1.5 py-0.5 text-[9px] font-bold bg-amber-50 text-amber-700 border border-amber-300 rounded uppercase">KEPT</span>
                          ) : clusterPlan ? (
                            <span className="text-[9px] italic text-gray-400 border border-gray-200 rounded px-1.5 py-0.5">Not in plan</span>
                          ) : null}
                        </td>
                        {/* State column — lifecycle + overload only */}
                        <td className="px-4 py-3">
                          <div className="flex flex-wrap gap-1">
                            <span className={`px-2 py-0.5 text-[9px] font-bold border rounded uppercase tracking-wider ${lc.cls}`}>
                              {lc.label}
                            </span>
                            {node.is_overloaded && (
                              <span className="px-1.5 py-0.5 text-[9px] font-bold bg-red-50 text-red-600 border border-red-200 rounded uppercase">⚠ Hot</span>
                            )}
                          </div>
                        </td>
                      </tr>

                      {/* Expanded detail */}
                      {isExpanded && (
                        <tr className="bg-gray-50/50">
                          <td colSpan="8" className="p-0 border-t border-gray-200">
                            <div className="grid grid-cols-2 min-h-[320px]">

                              {/* Left — current node facts */}
                              <div className="p-6 pr-8 border-r border-gray-200 space-y-6">
                                <div className="flex justify-between items-start">
                                  <h4 className="text-[13px] font-bold text-gray-900 flex items-center gap-2">
                                    <FiServer className="text-gray-500 w-4 h-4" />
                                    Node Details
                                  </h4>
                                  <span className={`px-2 py-1 text-[9px] font-bold border rounded uppercase tracking-wider ${lc.cls}`}>{lc.label}</span>
                                </div>
                                <div className="grid grid-cols-2 gap-4 bg-white p-4 rounded-lg border border-gray-200 shadow-sm">
                                  <div>
                                    <p className="text-[9px] text-gray-500 uppercase tracking-wider font-bold mb-1">Instance Type</p>
                                    <p className="font-mono text-xs font-semibold text-gray-900">{node.instance_type || '—'}</p>
                                  </div>
                                  <div>
                                    <p className="text-[9px] text-gray-500 uppercase tracking-wider font-bold mb-1">Capacity</p>
                                    <p className="text-xs font-semibold text-gray-900">{node.capacity_type || '—'}</p>
                                  </div>
                                  <div>
                                    <p className="text-[9px] text-gray-500 uppercase tracking-wider font-bold mb-1">vCPU</p>
                                    <p className="text-xs font-semibold text-gray-900">{node.vcpu_count != null ? `${node.vcpu_count} vCPU` : '—'}</p>
                                  </div>
                                  <div>
                                    <p className="text-[9px] text-gray-500 uppercase tracking-wider font-bold mb-1">Memory</p>
                                    <p className="text-xs font-semibold text-gray-900">{node.memory_gib != null ? `${node.memory_gib} GiB` : '—'}</p>
                                  </div>
                                  <div>
                                    <p className="text-[9px] text-gray-500 uppercase tracking-wider font-bold mb-1">AZ</p>
                                    <p className="font-mono text-xs text-gray-700">{node.az || '—'}</p>
                                  </div>
                                  <div>
                                    <p className="text-[9px] text-gray-500 uppercase tracking-wider font-bold mb-1">Hourly Price</p>
                                    <p className="font-mono text-xs font-semibold text-gray-900">
                                      {node.hourly_price_usd != null ? `$${node.hourly_price_usd.toFixed(4)}/hr` : '—'}
                                    </p>
                                  </div>
                                </div>
                                <div>
                                  <p className="text-[10px] text-gray-500 uppercase tracking-wider font-bold mb-3">Resource Utilisation (actual)</p>
                                  <div className="space-y-3">
                                    {[
                                      { label: 'CPU (actual)', pct: node.cpu_actual_pct, reqPct: node.cpu_requested_pct },
                                      { label: 'Memory (actual)', pct: node.mem_actual_pct, reqPct: node.mem_requested_pct },
                                    ].map(({ label, pct, reqPct }) => (
                                      <div key={label}>
                                        <div className="flex justify-between text-xs mb-1">
                                          <span className="text-gray-600 font-medium">{label}</span>
                                          <span className="font-mono text-gray-700">
                                            {pct ?? '—'}% actual · {reqPct ?? '—'}% requested
                                          </span>
                                        </div>
                                        <div className="h-1.5 w-full bg-gray-200 rounded-full overflow-hidden">
                                          <div className="h-full bg-gray-500 rounded-full" style={{ width: `${pct ?? 0}%` }} />
                                        </div>
                                      </div>
                                    ))}
                                  </div>
                                </div>
                              </div>

                              {/* Right — Current → Desired state panel */}
                              {(() => {
                                const plan = nodePlans[id];
                                const isLoadingPlan = planLoading[id];
                                const moves = drainMovements[id] ?? [];
                                const rep = repSpec;

                                if (txType === 'REPLACE' || txType === 'TERMINATE') {
                                  // Build per-pod resource map: provision pods + per-node plan pods
                                  const podRes = {};
                                  provisionList.forEach(prov => {
                                    (prov.pods || []).forEach(p => {
                                      podRes[p.pod_name] = { cpu: p.cpu_request_millicores, mem: p.memory_request_mb };
                                    });
                                  });
                                  const planLocal = nodePlans[id];
                                  (planLocal?.current_pods || []).forEach(p => {
                                    if (!podRes[p.pod_name]) podRes[p.pod_name] = { cpu: p.cpu_request_millicores, mem: p.memory_request_mb };
                                  });

                                  // Group pods-leaving by destination node (namespace-safe keys via planNodeMap)
                                  const destMap = {};
                                  moves.forEach(mv => {
                                    const toNodeId = mv.to_node
                                      ? (mv.is_new_node ? `prov:${mv.to_node}` : `node:${mv.to_node}`)
                                      : '__unknown__';
                                    if (!destMap[toNodeId]) destMap[toNodeId] = { to_node_id: toNodeId, to_node: mv.to_node, is_new_node: !!mv.is_new_node, to_instance_type: mv.to_instance_type, to_capacity_type: mv.to_capacity_type, pods: [] };
                                    destMap[toNodeId].pods.push(mv);
                                  });

                                  // Enrich via planNodeMap — single authoritative lookup, no silent fallback
                                  const destGroups = Object.values(destMap).map(g => {
                                    const planNode = planNodeMap.get(g.to_node_id);
                                    if (planNode) {
                                      const m = planNode.meta;
                                      return { ...g,
                                        instance_type: g.to_instance_type || m.instance_type || m.current_instance_type,
                                        capacity_type: g.to_capacity_type || m.capacity_type,
                                        price: m.hourly_cost_usd || m.hourly_price_usd,
                                        az: m.az,
                                        _unresolved: false,
                                      };
                                    }
                                    return { ...g, instance_type: null, capacity_type: g.to_capacity_type, price: null, az: null, _unresolved: g.to_node_id !== '__unknown__' };
                                  }).sort((a, b) => Number(a.is_new_node) - Number(b.is_new_node));

                                  // Workload class + execution strategy badges
                                  const _wClass  = workloadClassMap[id] || 'stateless';
                                  const _execStr = execStrategyMap[id] || 'ROLLING';
                                  const _wcStyle = { db: { bg: 'bg-red-100 text-red-700', label: 'DB' }, stateful: { bg: 'bg-amber-100 text-amber-700', label: 'Stateful' }, stateless: { bg: 'bg-green-100 text-green-700', label: 'Stateless' }, mixed: { bg: 'bg-purple-100 text-purple-700', label: 'Mixed' } }[_wClass] || { bg: 'bg-gray-100 text-gray-600', label: _wClass };
                                  const _exStyle = { SERIAL: { bg: 'bg-red-50 text-red-600 border border-red-200', label: 'Serial' }, BLUE_GREEN: { bg: 'bg-blue-50 text-blue-700 border border-blue-200', label: 'Blue/Green' }, ROLLING: { bg: 'bg-green-50 text-green-700 border border-green-200', label: 'Rolling' } }[_execStr] || { bg: 'bg-gray-50 text-gray-500 border border-gray-200', label: _execStr };

                                  return (
                                    <div className="flex flex-col bg-gray-50 border-l border-gray-200 overflow-y-auto max-h-[600px]">
                                      {/* Header */}
                                      <div className={`px-4 py-2.5 flex items-center gap-3 border-b flex-shrink-0 ${txType === 'REPLACE' ? 'bg-orange-50 border-orange-200' : 'bg-gray-100 border-gray-200'}`}>
                                        <FiArrowRight className={`w-3.5 h-3.5 flex-shrink-0 ${txType === 'REPLACE' ? 'text-orange-600' : 'text-gray-500'}`} />
                                        <div className="min-w-0 flex-1">
                                          <div className="flex items-center gap-2 flex-wrap">
                                            <p className={`text-[12px] font-bold ${txType === 'REPLACE' ? 'text-orange-700' : 'text-gray-700'}`}>
                                              {moves.length} app pod{moves.length !== 1 ? 's' : ''} → {destGroups.length} node{destGroups.length !== 1 ? 's' : ''}
                                            </p>
                                            {(() => {
                                              const _dm = drainMeta[id];
                                              const _total = _dm?.total_pods_on_node;
                                              const _sys = _dm?.system_pods_on_node;
                                              if (!_total) return null;
                                              const _other = _total - moves.length - (_sys || 0);
                                              return (
                                                <span className="text-[10px] text-gray-400">
                                                  {_total} total · {_sys || 0} sys/DS{_other > 0 ? ` · ${_other} other app` : ''}
                                                </span>
                                              );
                                            })()}
                                            <span className={`text-[10px] font-semibold px-1.5 py-0.5 rounded ${_wcStyle.bg}`}>{_wcStyle.label}</span>
                                            <span className={`text-[10px] font-medium px-1.5 py-0.5 rounded ${_exStyle.bg}`}>{_exStyle.label}</span>
                                          </div>
                                          <p className="text-[10px] text-gray-500 mt-0.5 font-mono">
                                            {node.instance_type} · {(node.capacity_type || '').toUpperCase()} · {node.az || '—'} · {node.hourly_price_usd != null ? `$${node.hourly_price_usd.toFixed(4)}/hr` : '—'}
                                          </p>
                                        </div>
                                      </div>

                                      {/* Per-destination-node cards */}
                                      <div className="p-3 space-y-3">
                                        {moves.length === 0 ? (
                                          <div className="text-xs text-gray-400 italic py-4 text-center">
                                            {clusterPlanLoading ? 'Computing cluster plan…' : 'No pod movements computed yet.'}
                                          </div>
                                        ) : destGroups.map((grp, gi) => {
                                          const isSpot = (grp.capacity_type || '').toLowerCase() === 'spot';
                                          const isNew = !!grp.is_new_node;
                                          const grpCpu = grp.pods.reduce((s, mv) => s + (podRes[mv.pod_name]?.cpu || 0), 0);
                                          const grpMem = grp.pods.reduce((s, mv) => s + (podRes[mv.pod_name]?.mem || 0), 0);
                                          const fmtMem = m => m >= 1024 ? `${(m / 1024).toFixed(1)}G` : `${m}M`;
                                          return (
                                            <div key={gi} className={`border rounded-lg overflow-hidden shadow-sm ${
                                              isNew
                                                ? (isSpot ? 'border-emerald-300' : 'border-orange-300')
                                                : (isSpot ? 'border-indigo-200' : 'border-gray-300')
                                            }`}>
                                              {/* Destination node card header */}
                                              <div className={`px-3 py-2 flex items-center justify-between gap-2 ${
                                                isNew
                                                  ? (isSpot ? 'bg-emerald-50' : 'bg-orange-50')
                                                  : (isSpot ? 'bg-indigo-50' : 'bg-gray-100')
                                              }`}>
                                                <div className="flex items-center gap-2 min-w-0">
                                                  <FiServer className={`w-3 h-3 flex-shrink-0 ${isNew ? (isSpot ? 'text-emerald-600' : 'text-orange-600') : (isSpot ? 'text-indigo-600' : 'text-gray-500')}`} />
                                                  {grp._unresolved
                                                    ? <span className="text-red-500 italic text-[11px]">Unresolved node</span>
                                                    : grp.instance_type
                                                      ? <span className="font-mono text-[12px] font-bold text-gray-900">{grp.instance_type}</span>
                                                      : <span className="text-amber-500 italic text-[11px]">Pending ISS</span>
                                                  }
                                                  {grp.az && <span className="text-[10px] text-gray-400 font-mono">{grp.az}</span>}
                                                  {!isNew && grp.to_node && (
                                                    <span className="text-[10px] text-gray-400 font-mono truncate max-w-[120px]" title={grp.to_node}>{grp.to_node.split('.')[0]}</span>
                                                  )}
                                                </div>
                                                <div className="flex items-center gap-1 flex-shrink-0">
                                                  {grp.price != null && (
                                                    <span className="text-[10px] font-mono font-semibold bg-white border border-gray-200 rounded px-1.5 py-0.5 text-gray-700">
                                                      ${grp.price.toFixed(4)}/hr
                                                    </span>
                                                  )}
                                                  <span className={`px-1.5 py-0.5 text-[9px] font-bold border rounded uppercase ${isSpot ? 'bg-indigo-100 text-indigo-700 border-indigo-200' : 'bg-orange-100 text-orange-700 border-orange-200'}`}>
                                                    {isSpot ? 'Spot' : 'On-Demand'}
                                                  </span>
                                                  {isNew
                                                    ? <span className="px-1.5 py-0.5 text-[9px] font-bold bg-emerald-600 text-white rounded">NEW</span>
                                                    : <span className="px-1.5 py-0.5 text-[9px] font-bold bg-blue-600 text-white rounded">EXISTING</span>
                                                  }
                                                </div>
                                              </div>

                                              {/* Pod table */}
                                              <table className="w-full text-[11px] bg-white">
                                                <thead className="bg-gray-50 border-b border-gray-100">
                                                  <tr>
                                                    <th className="px-3 py-1 text-left font-bold text-gray-400 text-[9px] uppercase tracking-wider">Pod</th>
                                                    <th className="px-3 py-1 text-right font-bold text-gray-400 text-[9px] uppercase tracking-wider">CPU Req</th>
                                                    <th className="px-3 py-1 text-right font-bold text-gray-400 text-[9px] uppercase tracking-wider">Mem Req</th>
                                                  </tr>
                                                </thead>
                                                <tbody className="divide-y divide-gray-50">
                                                  {grp.pods.map((mv, pi) => {
                                                    const r = podRes[mv.pod_name] || {};
                                                    return (
                                                      <tr key={pi} className="hover:bg-gray-50">
                                                        <td className="px-3 py-1.5 font-mono text-gray-800 truncate max-w-[150px]" title={mv.pod_name}>{mv.pod_name || '—'}</td>
                                                        <td className="px-3 py-1.5 text-right font-mono text-gray-600">{r.cpu != null ? `${r.cpu}m` : <span className="text-gray-300">—</span>}</td>
                                                        <td className="px-3 py-1.5 text-right font-mono text-gray-600">{r.mem != null ? fmtMem(r.mem) : <span className="text-gray-300">—</span>}</td>
                                                      </tr>
                                                    );
                                                  })}
                                                </tbody>
                                                <tfoot className="bg-gray-50 border-t border-gray-200">
                                                  <tr>
                                                    <td className="px-3 py-1.5 text-[10px] font-bold text-gray-500 uppercase">{grp.pods.length} pod{grp.pods.length !== 1 ? 's' : ''} total</td>
                                                    <td className="px-3 py-1.5 text-right font-mono font-bold text-gray-700">{grpCpu > 0 ? `${grpCpu}m` : '—'}</td>
                                                    <td className="px-3 py-1.5 text-right font-mono font-bold text-gray-700">{grpMem > 0 ? fmtMem(grpMem) : '—'}</td>
                                                  </tr>
                                                </tfoot>
                                              </table>
                                            </div>
                                          );
                                        })}
                                      </div>
                                    </div>
                                  );
                                }

                                // Keep node: pods stay here — node is NOT being terminated or replaced
                                const opt = plan?.optimization_target || null;
                                const apiOpt = opt || deriveOptTarget(node, engineIntent, keepReasonMap[id]);
                                const COLOR_MAP = {
                                  red: 'text-red-700 bg-red-50 border-red-200',
                                  amber: 'text-amber-700 bg-amber-50 border-amber-200',
                                  blue: 'text-blue-700 bg-blue-50 border-blue-200',
                                  indigo: 'text-indigo-700 bg-indigo-50 border-indigo-200',
                                  violet: 'text-violet-700 bg-violet-50 border-violet-200',
                                  green: 'text-green-700 bg-green-50 border-green-200',
                                };
                                const badgeCls = COLOR_MAP[opt?.color] || apiOpt?.bg || COLOR_MAP.green;
                                const textCls = badgeCls.split(' ')[0];
                                return (
                                  <div className="p-5 bg-gray-50 border-l border-gray-200 flex flex-col gap-4 overflow-y-auto max-h-[600px]">
                                    <div className="flex items-start justify-between gap-2">
                                      <div className="flex items-start gap-2">
                                        <FiCheckCircle className="text-orange-500 w-4 h-4 mt-0.5 flex-shrink-0" />
                                        <div>
                                          <h4 className="text-[13px] font-bold text-gray-700">Node Kept <span className="text-[10px] font-semibold px-1.5 py-0.5 bg-amber-100 text-amber-700 rounded ml-1">KEPT</span></h4>
                                          <p className="text-[11px] text-gray-400 mt-0.5">This node stays in the cluster. Pods on it are <strong>not moved</strong> — they remain here.</p>
                                        </div>
                                      </div>
                                      {/* Instance + capacity type chips */}
                                      <div className="flex items-center gap-1.5 flex-wrap justify-end shrink-0">
                                        {node.instance_type && (
                                          <span className="text-[10px] font-mono font-bold px-2 py-0.5 bg-white border border-gray-300 rounded text-gray-700">{node.instance_type}</span>
                                        )}
                                        <span className={`text-[10px] font-bold px-2 py-0.5 rounded border uppercase ${
                                          (node.capacity_type || '').toLowerCase() === 'spot'
                                            ? 'bg-indigo-50 border-indigo-200 text-indigo-700'
                                            : 'bg-orange-50 border-orange-200 text-orange-700'
                                        }`}>
                                          {(node.capacity_type || 'OD').toLowerCase() === 'spot' ? 'Spot' : 'On-Demand'}
                                        </span>
                                        {node.az && (
                                          <span className="text-[10px] text-gray-500 font-mono">{node.az}</span>
                                        )}
                                      </div>
                                    </div>
                                    {isLoadingPlan ? (
                                      <div className="text-xs text-gray-400 py-4 text-center">Loading…</div>
                                    ) : (
                                    <>
                                      <div className={`border rounded-lg px-4 py-3 ${badgeCls}`}>
                                        <div className={`text-sm font-bold mb-1 ${textCls}`}>{opt ? opt.action : apiOpt.action}</div>
                                        <div className="text-[11px] text-gray-600 leading-relaxed">{opt ? opt.detail : apiOpt.detail}</div>
                                      </div>
                                      <div className="grid grid-cols-2 gap-2 text-[11px]">
                                        {[
                                          ['CPU Free', `${opt?.cpu_buffer_pct ?? node.cpu_buffer_pct ?? '—'}%`, (opt?.cpu_buffer_pct ?? node.cpu_buffer_pct ?? 0) > 50 ? 'text-green-600' : 'text-amber-600'],
                                          ['Mem Free', `${opt?.mem_buffer_pct ?? node.mem_buffer_pct ?? '—'}%`, (opt?.mem_buffer_pct ?? node.mem_buffer_pct ?? 0) > 50 ? 'text-green-600' : 'text-amber-600'],
                                          ['Pods', node.pod_count ?? '—', 'text-gray-800'],
                                          ['Cost', node.hourly_price_usd != null ? `$${node.hourly_price_usd.toFixed(3)}/hr` : '—', 'text-gray-800'],
                                        ].map(([l, v, c]) => (
                                          <div key={l} className="bg-white border border-gray-200 rounded p-2.5">
                                            <p className="font-bold text-gray-400 uppercase tracking-wider text-[9px] mb-1">{l}</p>
                                            <p className={`font-bold text-sm ${c}`}>{v}</p>
                                          </div>
                                        ))}
                                      </div>
                                      {plan?.current_pods?.length > 0 && (
                                        <div>
                                          <p className="text-[10px] font-bold uppercase tracking-wider text-gray-500 mb-1.5">Pods staying on this node ({plan.current_pods.length}) <span className="text-[9px] font-semibold text-amber-600">KEPT</span></p>
                                          <div className="space-y-1">
                                            {plan.current_pods.map(p => (
                                              <div key={p.pod_name} className="flex items-center justify-between bg-white border border-amber-100 rounded px-3 py-1.5 text-[11px]">
                                                <span className="font-mono text-gray-800 truncate">{p.pod_name}</span>
                                                <div className="flex items-center gap-1.5 shrink-0 ml-2">
                                                  <span className="text-gray-400">{p.cpu_request_millicores ?? '—'}m</span>
                                                  <span className="text-[9px] font-bold px-1 py-0.5 bg-amber-50 text-amber-600 border border-amber-200 rounded">KEPT</span>
                                                </div>
                                              </div>
                                            ))}
                                          </div>
                                        </div>
                                      )}
                                    </>
                                    )}
                                  </div>
                                );
                              })()}

                            </div>
                          </td>
                        </tr>
                      )}
                    </React.Fragment>
                  );
                })}
              </tbody>
            </table>
          </div>}

          {/* Planned Provisions footer */}
          {provisionList.length > 0 && (
            <div className="border-t border-dashed border-indigo-200 bg-indigo-50/50 px-4 py-3">
              <p className="text-[10px] font-bold uppercase tracking-wider text-indigo-600 mb-2 flex items-center gap-1">
                <FiServer className="w-3 h-3" /> Engine Plans to Provision ({provisionList.length} new node{provisionList.length !== 1 ? 's' : ''})
              </p>
              <div className="flex flex-wrap gap-2">
                {provisionList.map((p, i) => (
                  <div key={i} className="bg-white border border-indigo-200 rounded px-3 py-1.5 text-[11px] flex items-center gap-2">
                    <span className={`px-1.5 py-0.5 text-[9px] font-bold border rounded uppercase ${
                      (p.capacity_type || '').toLowerCase() === 'spot'
                        ? 'bg-indigo-50 text-indigo-700 border-indigo-200'
                        : 'bg-orange-50 text-orange-700 border-orange-200'
                    }`}>{p.capacity_type || 'spot'}</span>
                    {p.instance_type && (
                      <span className="font-mono font-semibold text-gray-800">{p.instance_type}</span>
                    )}
                    <span className="text-gray-500">{p.az || 'any AZ'}</span>
                    <span className="font-bold text-gray-700">{p.pod_count} pod{p.pod_count !== 1 ? 's' : ''}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
