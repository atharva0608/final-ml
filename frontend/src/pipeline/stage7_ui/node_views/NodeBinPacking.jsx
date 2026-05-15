import React, { useState, useEffect } from 'react';
import {
  FiSearch, FiChevronRight, FiArrowRight, FiLayers,
} from 'react-icons/fi';
import { MdDeveloperBoard } from 'react-icons/md';
import useClusters from '../../../hooks/useClusters';
import { optimizeAPI } from '../../../services/api';

function deriveStatus(node, planAction) {
  if (planAction === 'drain')     return 'Engine: Drain';
  if (planAction === 'keep')      return 'Engine: Keep';
  if (planAction === 'provision') return 'Engine: Provision';
  if (node.is_overloaded) return 'Overloaded';
  if ((node.cpu_actual_pct || 0) < 60) return 'Can consolidate';
  return 'Optimal';
}

function buildSummary(nodes, consolidationData) {
  if (!nodes.length) return { total_nodes: 0, total_pods: 0, avg_cpu_util: 0, avg_mem_util: 0, consolidation_candidates: null, est_savings_monthly: null };
  const total_pods = nodes.reduce((s, n) => s + (n.pod_count || 0), 0);
  const avg_cpu_util = Math.round(nodes.reduce((s, n) => s + (n.cpu_util || 0), 0) / nodes.length);
  const avg_mem_util = Math.round(nodes.reduce((s, n) => s + (n.mem_util || 0), 0) / nodes.length);
  let consolidation_candidates = null;
  let est_savings_monthly = null;
  if (Array.isArray(consolidationData)) {
    consolidation_candidates = consolidationData.length;
    est_savings_monthly = Math.round(consolidationData.reduce((s, c) => s + (c.monthly_saving_usd || 0), 0));
  }
  return { total_nodes: nodes.length, total_pods, avg_cpu_util, avg_mem_util, consolidation_candidates, est_savings_monthly };
}

const POD_COLORS = [
  'bg-indigo-100 border-indigo-200 text-indigo-700',
  'bg-emerald-100 border-emerald-200 text-emerald-700',
  'bg-purple-100 border-purple-200 text-purple-700',
  'bg-gray-200 border-gray-300 text-gray-700',
];

function buildHint(summary) {
  const n = summary.consolidation_candidates || 0;
  if (!n) return 'No consolidation action needed';
  return `Move pods off ${n} node${n !== 1 ? 's' : ''} — save $${summary.est_savings_monthly}/mo`;
}

function buildDecisionReason(node, pods, planAction, planMeta) {
  if (!node) return null;
  if (planAction === 'drain') {
    const txType = planMeta?.transition_type;
    return {
      verdict: txType === 'REPLACE' ? 'Engine: Replace' : 'Engine: Terminate',
      style: txType === 'REPLACE' ? 'bg-orange-50 border-orange-200' : 'bg-gray-100 border-gray-300',
      badgeStyle: txType === 'REPLACE' ? 'bg-orange-100 text-orange-700 border-orange-300' : 'bg-gray-200 text-gray-700 border-gray-300',
      icon: txType === 'REPLACE' ? '⇄' : '✗',
      reason: txType === 'REPLACE'
        ? 'Engine is replacing this node. Pods are moving to a bin-packed equivalent.'
        : 'Engine is terminating this node. Pods consolidate onto existing nodes.',
      action: txType === 'REPLACE'
        ? `Replacement: ${planMeta?.capacity_type || 'spot'} ${planMeta?.instance_type || '—'}`
        : 'All pods will be evicted and rescheduled on remaining nodes.',
    };
  }
  if (planAction === 'keep') {
    return {
      verdict: 'Engine: Keep',
      style: 'bg-green-50 border-green-200',
      badgeStyle: 'bg-green-100 text-green-700 border-green-200',
      icon: '⚓',
      reason: 'Engine determined this node should remain unchanged — it hosts workloads that must stay on on-demand, or packing is already optimal.',
      action: 'No pods will be moved. Node continues normal operation.',
    };
  }
  const systemPods = (pods || []).filter(p =>
    p.namespace === 'kube-system' || p.namespace === 'karpenter' || (p.pod_name || '').includes('daemonset')
  );
  const hasSystemPods = systemPods.length > 0;
  if (node.status === 'Overloaded') {
    return {
      verdict: 'Overloaded',
      style: 'bg-red-50 border-red-200',
      badgeStyle: 'bg-red-100 text-red-700 border-red-300',
      icon: '⚠',
      reason: 'CPU or memory usage exceeds safe threshold. Avoid adding more pods to this node.',
      action: 'Do NOT consolidate here — node needs capacity relief.',
    };
  }
  if (node.status === 'Can consolidate') {
    return {
      verdict: hasSystemPods ? 'Soft consolidation candidate' : 'Consolidation candidate',
      style: 'bg-amber-50 border-amber-100',
      badgeStyle: 'bg-amber-100 text-amber-700 border-amber-300',
      icon: '↓',
      reason: `CPU utilization (${node.cpu_util}%) is below the 60% efficiency threshold. Pods can be repacked onto other nodes.`,
      action: hasSystemPods
        ? 'System/DaemonSet pods detected — drain will skip them. Only moveable pods will migrate.'
        : `Drain and terminate this node to save ~$${Math.round((node.cpu_util < 30 ? 60 : 30))}/mo.`,
    };
  }
  return {
    verdict: 'Optimal',
    style: 'bg-green-50 border-green-100',
    badgeStyle: 'bg-green-100 text-green-700 border-green-200',
    icon: '✓',
    reason: `CPU utilization (${node.cpu_util}%) is within the efficient range (60–85%). No action required.`,
    action: 'Node is healthy — no consolidation or scaling needed.',
  };
}

export default function NodeBinPacking() {
  const { clusters, selectedId: clusterId, setSelectedId: setClusterId, clusterPlan } = useClusters();
  const [nodes, setNodes] = useState([]);
  const [summary, setSummary] = useState({ total_nodes: 0, total_pods: 0, avg_cpu_util: 0, avg_mem_util: 0, consolidation_candidates: null, est_savings_monthly: null });
  const [selectedNodeId, setSelectedNodeId] = useState(null);
  const [detailPods, setDetailPods] = useState([]);
  const [searchTerm, setSearchTerm] = useState('');
  const [loading, setLoading] = useState(false);
  const [detailLoading, setDetailLoading] = useState(false);
  const [error, setError] = useState(null);
  const [karpenterMetrics, setKarpenterMetrics] = useState(null);
  const [podDataAge, setPodDataAge] = useState(null);

  useEffect(() => {
    if (!clusterId) return;
    optimizeAPI.getKarpenterMetrics(clusterId)
      .then(res => setKarpenterMetrics(res.data))
      .catch(() => setKarpenterMetrics(null));
  }, [clusterId]);

  useEffect(() => {
    if (!clusterId) return;
    setLoading(true);
    setError(null);
    optimizeAPI.getNodeBinPacking(clusterId)
      .then(res => {
        const data = res.data;
        const planActionMap = {};
        const planMetaMap = {};
        const planDrainNodes = clusterPlan?.drain_nodes || [];
        const planKeepNodes  = clusterPlan?.keep_nodes  || [];
        planDrainNodes.forEach(d => {
          planActionMap[d.node_name] = 'drain';
          planMetaMap[d.node_name] = { transition_type: d.transition_type, instance_type: d.replacement_instance_type, capacity_type: d.replacement_capacity_type };
        });
        planKeepNodes.forEach(k => { planActionMap[k.node_name] = 'keep'; });
        const mapped = (data.nodes || []).map(n => {
          const pa = planActionMap[n.node_name] || null;
          return {
            id: n.node_name,
            hostname: n.node_name,
            pool: [n.capacity_type, n.az].filter(Boolean).join(' / ') || '—',
            type: n.instance_type || '—',
            pod_count: n.pod_count || 0,
            cpu_util: n.cpu_actual_pct || 0,
            cpu_requested_pct: n.cpu_requested_pct || 0,
            mem_util: n.mem_actual_pct || 0,
            mem_requested_pct: n.mem_requested_pct || 0,
            is_overloaded: n.is_overloaded || false,
            planAction: pa,
            planMeta: planMetaMap[n.node_name] || null,
            status: deriveStatus(n, pa),
            allocatable_cpu_mc: n.allocatable_cpu_millicores || 0,
            allocatable_mem_bytes: n.allocatable_memory_bytes || 0,
            effective_cpu_mc: n.effective_cpu_mc || 0,
            effective_mem_bytes: n.effective_mem_bytes || 0,
            overhead_detail: n.overhead_detail || null,
          };
        });
        setNodes(mapped);
        setSummary(buildSummary(mapped, data.consolidation_candidates));
        setPodDataAge(data.pod_data_age_seconds ?? null);
        if (mapped.length > 0) setSelectedNodeId(prev => prev || mapped[0].id);
      })
      .catch(err => setError(err?.response?.data?.detail || err?.message || 'Failed to load nodes'))
      .finally(() => setLoading(false));
  }, [clusterId]);

  useEffect(() => {
    if (!selectedNodeId || !clusterId) return;
    setDetailLoading(true);
    optimizeAPI.getNodeBinPackingDetail(selectedNodeId, clusterId)
      .then(res => setDetailPods(res.data.pods || []))
      .catch(() => setDetailPods([]))
      .finally(() => setDetailLoading(false));
  }, [selectedNodeId, clusterId]);

  const filtered = searchTerm
    ? nodes.filter(n => n.hostname.toLowerCase().includes(searchTerm.toLowerCase()))
    : nodes;
  const selectedNode = nodes.find(n => n.id === selectedNodeId) || nodes[0] || null;

  return (
    <div className="min-h-full bg-gray-50 p-6 text-gray-900">
      <div className="max-w-[1500px] mx-auto space-y-4">

        {/* Header */}
        <div className="flex justify-between items-start mb-2">
          <div>
            <div className="flex items-center gap-3">
              <div className="p-2 bg-indigo-50 rounded-lg">
                <FiLayers className="w-5 h-5 text-indigo-600" />
              </div>
              <h1 className="text-xl font-bold text-gray-900 m-0">Node Bin Packing</h1>
            </div>
            <p className="text-xs text-gray-500 mt-2">Identify underutilized nodes and consolidate workloads to reduce infrastructure costs.</p>
          {podDataAge != null && (
            <span className={`inline-flex items-center gap-1 mt-1 text-[10px] px-2 py-0.5 rounded-full border ${
              podDataAge > 600 ? 'bg-red-50 border-red-200 text-red-600' :
              podDataAge > 120 ? 'bg-amber-50 border-amber-200 text-amber-600' :
              'bg-green-50 border-green-200 text-green-600'
            }`}>
              Agent data: {podDataAge < 60 ? `${podDataAge}s ago` : `${Math.round(podDataAge/60)}m ago`}
              {podDataAge > 600 && ' — stale, agent may be down'}
            </span>
          )}
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-500 mb-1">Cluster</label>
            <select
              value={clusterId}
              onChange={e => { setSelectedNodeId(null); setClusterId(e.target.value); }}
              className="text-sm border border-gray-300 rounded-md px-3 py-1.5 focus:outline-none focus:ring-1 focus:ring-indigo-500"
            >
              <option value="" disabled>Select cluster</option>
              {clusters.map(c => <option key={c.id} value={c.id}>{c.name || c.id}</option>)}
            </select>
          </div>
        </div>

        {error && <div className="bg-red-50 border border-red-200 rounded-lg px-4 py-2 text-xs text-red-700">{error}</div>}

        {/* 1. SUMMARY STRIP */}
        <div className="bg-white border border-gray-200 rounded-lg shadow-sm">
          <div className="grid grid-cols-2 md:grid-cols-6 divide-y md:divide-y-0 md:divide-x divide-gray-200">
            <div className="px-4 py-3 flex flex-col justify-center">
              <span className="text-[10px] font-bold text-gray-500 uppercase tracking-wider mb-1">Total Nodes</span>
              <span className="text-lg font-semibold text-gray-900">{loading ? '…' : summary.total_nodes}</span>
            </div>
            <div className="px-4 py-3 flex flex-col justify-center">
              <span className="text-[10px] font-bold text-gray-500 uppercase tracking-wider mb-1">Total Pods</span>
              <span className="text-lg font-semibold text-gray-900">{loading ? '…' : summary.total_pods}</span>
            </div>
            <div className="px-4 py-3 flex flex-col justify-center">
              <span className="text-[10px] font-bold text-gray-500 uppercase tracking-wider mb-1">Avg CPU Util</span>
              <span className="text-lg font-semibold text-amber-600">{loading ? '…' : `${summary.avg_cpu_util}%`}</span>
              <span className="text-[9px] text-gray-500 mt-0.5">underutilized &lt; 60%</span>
            </div>
            <div className="px-4 py-3 flex flex-col justify-center">
              <span className="text-[10px] font-bold text-gray-500 uppercase tracking-wider mb-1">Avg Mem Util</span>
              <span className="text-lg font-semibold text-gray-900">{loading ? '…' : `${summary.avg_mem_util}%`}</span>
            </div>
            <div className="px-4 py-3 flex flex-col justify-center bg-red-50">
              <span className="text-[10px] font-bold text-gray-500 uppercase tracking-wider mb-1">Consolidation Candidates</span>
              <span className="text-lg font-semibold text-red-600">{loading ? '…' : summary.consolidation_candidates != null ? `${summary.consolidation_candidates} nodes` : <span className="text-gray-400 text-sm">—</span>}</span>
              <span className="text-[9px] text-red-400 mt-0.5">pods can be repacked</span>
            </div>
            <div className="px-4 py-3 flex flex-col justify-center bg-emerald-50 rounded-r-lg">
              <span className="text-[10px] font-bold text-gray-500 uppercase tracking-wider mb-1">Est. Savings if Packed</span>
              <span className="text-lg font-semibold text-emerald-600">{loading ? '…' : summary.est_savings_monthly != null ? `$${summary.est_savings_monthly}/mo` : <span className="text-gray-400 text-sm">—</span>}</span>
            </div>
          </div>
        </div>

        {!loading && (
          <p className="text-xs text-gray-600 bg-white border border-gray-200 rounded px-4 py-2 shadow-sm">
            {buildHint(summary)}
          </p>
        )}

        {/* 2. MAIN LAYOUT */}
        <div className="flex flex-col md:flex-row bg-white border border-gray-200 rounded-lg shadow-sm overflow-hidden" style={{ height: 'calc(100vh - 270px)', minHeight: '500px' }}>

          {/* LEFT PANEL */}
          <div className="w-full md:w-[40%] border-r border-gray-200 flex flex-col bg-gray-50/50">
            <div className="p-3 border-b border-gray-200 bg-white">
              <div className="relative">
                <FiSearch className="absolute left-2.5 top-1/2 -translate-y-1/2 text-gray-400 w-3.5 h-3.5" />
                <input
                  type="text"
                  className="w-full pl-8 pr-3 py-1.5 bg-white border border-gray-300 rounded text-xs text-gray-900 focus:outline-none focus:ring-1 focus:ring-indigo-500 shadow-sm"
                  placeholder="Search nodes by name..."
                  value={searchTerm}
                  onChange={e => setSearchTerm(e.target.value)}
                />
              </div>
            </div>

            <div className="px-4 py-2 border-b border-gray-200 bg-gray-100/50 flex justify-between items-center">
              <span className="text-[10px] font-bold text-gray-500 uppercase tracking-wider">Node List</span>
              <span className="text-[10px] text-gray-500">{filtered.length} of {summary.total_nodes}</span>
            </div>

            <div className="flex-1 overflow-y-auto p-3 space-y-2">
              {loading ? (
                <div className="text-center py-8 text-xs text-gray-500">Loading nodes...</div>
              ) : !clusterId ? (
                <div className="text-center py-8 text-xs text-gray-400">Select a cluster to view nodes.</div>
              ) : filtered.length === 0 ? (
                <div className="text-center py-8 text-xs text-gray-400">No nodes available.</div>
              ) : filtered.map(node => {
                const isSelected = selectedNodeId === node.id;
                const isConsolidate = node.status === 'Can consolidate';
                const isOverloaded = node.status === 'Overloaded';
                return (
                  <div
                    key={node.id}
                    onClick={() => setSelectedNodeId(node.id)}
                    className={`p-3 rounded border cursor-pointer transition-all ${
                      isSelected
                        ? 'border-indigo-400 bg-indigo-50 shadow-sm ring-1 ring-indigo-400'
                        : 'border-gray-200 bg-white hover:border-gray-300 hover:bg-gray-50'
                    }`}
                  >
                    <div className="flex justify-between items-start mb-2">
                      <div>
                        <div className="flex items-center gap-2">
                          <h3 className={`font-semibold text-[13px] ${isSelected ? 'text-indigo-900' : 'text-gray-900'}`}>
                            {node.hostname}
                          </h3>
                          {node.planAction === 'drain'  && <span className="px-1.5 py-0.5 rounded-sm text-[9px] font-bold bg-orange-100 text-orange-700">DRAIN</span>}
                          {node.planAction === 'keep'   && <span className="px-1.5 py-0.5 rounded-sm text-[9px] font-bold bg-green-100 text-green-700">KEPT</span>}
                          {!node.planAction && isConsolidate && <span className="px-1.5 py-0.5 rounded-sm text-[9px] font-bold bg-amber-100 text-amber-700">CONSOLIDATE</span>}
                          {isOverloaded && <span className="px-1.5 py-0.5 rounded-sm text-[9px] font-bold bg-red-100 text-red-700">OVERLOADED</span>}
                        </div>
                        <div className="text-[11px] text-gray-500 mt-0.5 flex gap-2">
                          <span>{node.pool}</span>
                          <span className="text-gray-300">•</span>
                          <span>{node.type}</span>
                        </div>
                      </div>
                      <FiChevronRight className={`transition-opacity ${isSelected ? 'text-indigo-600' : 'text-gray-400'}`} />
                    </div>
                    <div className="grid grid-cols-2 gap-4">
                      <div>
                        <div className="flex justify-between text-[10px] mb-1">
                          <span className="text-gray-500 font-medium">CPU</span>
                          <span className={isOverloaded ? 'text-red-600 font-bold' : 'text-gray-700'}>{node.cpu_util}%</span>
                        </div>
                        <div className="h-1.5 w-full bg-gray-100 rounded-full overflow-hidden">
                          <div className={`h-full ${isOverloaded ? 'bg-red-500' : isConsolidate ? 'bg-amber-400' : 'bg-indigo-500'}`} style={{ width: `${node.cpu_util}%` }} />
                        </div>
                      </div>
                      <div>
                        <div className="flex justify-between text-[10px] mb-1">
                          <span className="text-gray-500 font-medium">Mem</span>
                          <span className={isOverloaded ? 'text-red-600 font-bold' : 'text-gray-700'}>{node.mem_util}%</span>
                        </div>
                        <div className="h-1.5 w-full bg-gray-100 rounded-full overflow-hidden">
                          <div className={`h-full ${isOverloaded ? 'bg-red-500' : 'bg-emerald-500'}`} style={{ width: `${node.mem_util}%` }} />
                        </div>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* RIGHT PANEL */}
          <div className="w-full md:w-[60%] bg-white flex flex-col overflow-y-auto">
            {selectedNode ? (
              <>
                <div className="px-6 py-4 border-b border-gray-200 bg-gray-50/50">
                  <div className="flex items-center justify-between mb-3">
                    <div className="flex items-center gap-2">
                      <MdDeveloperBoard className="text-indigo-600 w-5 h-5" />
                      <h2 className="text-base font-bold text-gray-900">{selectedNode.hostname}</h2>
                    </div>
                    <span className="text-[11px] font-medium text-gray-500">Pods: {selectedNode.pod_count}</span>
                  </div>
                  <div className="flex gap-6 border-t border-gray-200 pt-3">
                    <div>
                      <div className="text-[9px] font-bold text-gray-500 uppercase tracking-wider mb-0.5">Instance Type</div>
                      <div className="text-[13px] font-semibold text-gray-900">{selectedNode.type}</div>
                    </div>
                    <div>
                      <div className="text-[9px] font-bold text-gray-500 uppercase tracking-wider mb-0.5">Capacity / AZ</div>
                      <div className="text-[13px] font-semibold text-gray-900">{selectedNode.pool}</div>
                    </div>
                    <div>
                      <div className="text-[9px] font-bold text-gray-500 uppercase tracking-wider mb-0.5">Status</div>
                      <div className={`text-[13px] font-semibold ${
                        selectedNode.status === 'Can consolidate' ? 'text-amber-600'
                        : selectedNode.status === 'Overloaded' ? 'text-red-600'
                        : 'text-emerald-600'
                      }`}>{selectedNode.status}</div>
                    </div>
                  </div>
                  {/* Decision Rationale */}
                  {selectedNode.planAction && (
                    <div className="mt-3 flex items-center gap-2 flex-wrap text-[10px]">
                      <span className="font-bold text-gray-500 uppercase tracking-wider">Engine Plan</span>
                      <span className={`px-2 py-0.5 font-bold rounded border uppercase ${selectedNode.planAction === 'drain' ? 'bg-orange-100 text-orange-700 border-orange-300' : 'bg-green-100 text-green-700 border-green-200'}`}>
                        {selectedNode.planMeta?.transition_type || (selectedNode.planAction === 'drain' ? 'DRAIN' : 'KEEP')}
                      </span>
                      {selectedNode.planAction === 'drain' && selectedNode.planMeta?.instance_type && (
                        <span className="font-mono text-gray-600">→ {selectedNode.planMeta.capacity_type?.toUpperCase()} {selectedNode.planMeta.instance_type}</span>
                      )}
                      {!selectedNode.planAction && (
                        <span className="italic text-gray-400">Not in current plan</span>
                      )}
                    </div>
                  )}
                  {(() => {
                    const dr = buildDecisionReason(selectedNode, detailPods, selectedNode.planAction, selectedNode.planMeta);
                    if (!dr) return null;
                    return (
                      <div className={`mt-3 rounded-lg border px-3 py-2.5 ${dr.style}`}>
                        <div className="flex items-center gap-2 mb-1">
                          <span className={`text-[9px] font-bold px-1.5 py-0.5 rounded border ${dr.badgeStyle}`}>
                            {dr.icon} {dr.verdict}
                          </span>
                        </div>
                        <p className="text-[11px] text-gray-700">{dr.reason}</p>
                        <p className="text-[10px] text-gray-500 mt-0.5 italic">{dr.action}</p>
                      </div>
                    );
                  })()}
                </div>

                <div className="p-6 space-y-6">
                  <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                    <div className="bg-white p-4 rounded-lg border border-gray-200 shadow-sm">
                      <h4 className="text-[11px] font-bold text-gray-500 uppercase tracking-wider mb-3 flex justify-between">
                        <span>CPU Allocation</span>
                        <span className="text-indigo-600">{selectedNode.cpu_util}% Used</span>
                      </h4>
                      <div className="h-3 w-full bg-gray-100 rounded flex overflow-hidden mb-3">
                        <div className="bg-indigo-500 h-full" style={{ width: `${selectedNode.cpu_util}%` }} />
                      </div>
                      <div className="flex gap-4 text-[11px] font-medium text-gray-500">
                        <div className="flex items-center gap-1.5"><div className="w-2 h-2 rounded-sm bg-indigo-500" />Used</div>
                        <div className="flex items-center gap-1.5"><div className="w-2 h-2 rounded-sm bg-gray-200" />Free</div>
                      </div>
                    </div>
                    <div className="bg-white p-4 rounded-lg border border-gray-200 shadow-sm">
                      <h4 className="text-[11px] font-bold text-gray-500 uppercase tracking-wider mb-3 flex justify-between">
                        <span>Memory Allocation</span>
                        <span className="text-emerald-600">{selectedNode.mem_util}% Used</span>
                      </h4>
                      <div className="h-3 w-full bg-gray-100 rounded flex overflow-hidden mb-3">
                        <div className="bg-emerald-500 h-full" style={{ width: `${selectedNode.mem_util}%` }} />
                      </div>
                      <div className="flex gap-4 text-[11px] font-medium text-gray-500">
                        <div className="flex items-center gap-1.5"><div className="w-2 h-2 rounded-sm bg-emerald-500" />Used</div>
                        <div className="flex items-center gap-1.5"><div className="w-2 h-2 rounded-sm bg-gray-200" />Free</div>
                      </div>
                    </div>
                  </div>

                  {selectedNode.status === 'Can consolidate' && (() => {
                    const packedTarget = Math.min(85, Math.max(selectedNode.cpu_util + 5, selectedNode.cpu_requested_pct));
                    const headroomPct  = Math.max(0, packedTarget - selectedNode.cpu_util);
                    return (
                      <div className="bg-amber-50/50 rounded-lg border border-amber-100 shadow-sm overflow-hidden">
                        <div className="px-4 py-3 border-b border-amber-100 flex justify-between items-center bg-white">
                          <h3 className="text-sm font-semibold text-gray-900">Density Optimization</h3>
                          <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-amber-100 text-amber-700 tracking-wide uppercase">Underutilized Candidate</span>
                        </div>
                        <div className="p-4 flex gap-6 items-center justify-center">
                          <div className="flex flex-col items-center">
                            <span className="text-[11px] text-gray-500 mb-2 font-medium uppercase tracking-wider">Actual Usage</span>
                            <div className="w-20 h-28 border border-gray-300 rounded p-1 flex flex-col justify-end relative bg-white">
                              <div className="w-full bg-indigo-400 rounded-sm" style={{ height: `${Math.max(4, selectedNode.cpu_util)}%` }} />
                              <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
                                <span className="text-xs font-bold text-gray-500">{selectedNode.cpu_util}%</span>
                              </div>
                            </div>
                            <span className="text-[9px] text-gray-400 mt-1">cpu_usage</span>
                          </div>
                          <FiArrowRight className="text-gray-300 text-2xl" />
                          <div className="flex flex-col items-center">
                            <span className="text-[11px] text-indigo-600 mb-2 font-bold uppercase tracking-wider">Requested Capacity</span>
                            <div className="w-20 h-28 border-2 border-indigo-200 rounded p-1 flex flex-col justify-end relative bg-indigo-50 shadow-sm">
                              <div className="w-full bg-indigo-400 rounded-sm mb-0.5" style={{ height: `${Math.max(4, selectedNode.cpu_util)}%` }} />
                              {headroomPct > 0 && <div className="w-full bg-amber-400 rounded-sm opacity-60 border border-dashed border-amber-500" style={{ height: `${headroomPct}%` }} />}
                              <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
                                <span className="text-xs font-bold text-indigo-700">{packedTarget}%</span>
                              </div>
                            </div>
                            <span className="text-[9px] text-gray-400 mt-1">cpu_requested</span>
                          </div>
                        </div>
                        <div className="px-4 pb-3 text-[10px] text-gray-500 text-center">
                          Headroom: actual {selectedNode.cpu_util}% vs requested {selectedNode.cpu_requested_pct}% — {Math.round(selectedNode.cpu_requested_pct - selectedNode.cpu_util)}% over-provisioned
                        </div>
                      </div>
                    );
                  })()}

                  {/* Node Economics Breakdown */}
                  {selectedNode.overhead_detail && (() => {
                    const od = selectedNode.overhead_detail;
                    const totalCPU = selectedNode.allocatable_cpu_mc;
                    const workloadCPU = Math.max(0, selectedNode.effective_cpu_mc - (selectedNode.cpu_util / 100 * totalCPU));
                    const usedCPU = Math.round(selectedNode.cpu_util / 100 * totalCPU);
                    const rows = [
                      { label: 'Workload CPU (actual)', val: `${usedCPU}m`, color: 'bg-indigo-400', pct: totalCPU > 0 ? usedCPU / totalCPU * 100 : 0 },
                      { label: 'DaemonSet overhead', val: `${Math.round(od.daemonset_cpu_mc)}m`, color: 'bg-orange-300', pct: totalCPU > 0 ? od.daemonset_cpu_mc / totalCPU * 100 : 0 },
                      { label: 'kube-reserved', val: `${Math.round(od.kube_reserved_cpu_mc)}m`, color: 'bg-gray-300', pct: totalCPU > 0 ? od.kube_reserved_cpu_mc / totalCPU * 100 : 0 },
                      { label: 'Safety margin (10%)', val: `${Math.round(od.safety_margin_cpu_mc)}m`, color: 'bg-amber-200', pct: totalCPU > 0 ? od.safety_margin_cpu_mc / totalCPU * 100 : 0 },
                    ];
                    const effectivePct = totalCPU > 0 ? Math.round(selectedNode.effective_cpu_mc / totalCPU * 100) : 0;
                    return (
                      <div className="bg-white rounded-lg border border-gray-200 shadow-sm p-4">
                        <h3 className="text-[11px] font-bold text-gray-500 uppercase tracking-wider mb-3 flex items-center justify-between">
                          <span>Node Capacity Breakdown</span>
                          <span className="text-[10px] text-gray-400 font-normal">Allocatable: {Math.round(totalCPU / 1000 * 10) / 10} cores / {Math.round(selectedNode.allocatable_mem_bytes / (1024**3) * 10) / 10} GiB</span>
                        </h3>
                        <div className="space-y-1.5 mb-3">
                          {rows.map(r => (
                            <div key={r.label} className="flex items-center gap-2 text-[11px]">
                              <span className="w-36 flex-shrink-0 text-gray-500">{r.label}</span>
                              <div className="flex-1 h-2 bg-gray-100 rounded-full overflow-hidden">
                                <div className={`h-full rounded-full ${r.color}`} style={{ width: `${Math.min(100, r.pct)}%` }} />
                              </div>
                              <span className="font-mono text-gray-700 w-12 text-right flex-shrink-0">{r.val}</span>
                            </div>
                          ))}
                          <div className="border-t border-dashed border-gray-200 pt-1.5 flex items-center gap-2 text-[11px] font-bold">
                            <span className="w-36 flex-shrink-0 text-gray-700">Effective schedulable</span>
                            <div className="flex-1 h-2 bg-gray-100 rounded-full overflow-hidden">
                              <div className="h-full rounded-full bg-green-400" style={{ width: `${effectivePct}%` }} />
                            </div>
                            <span className="font-mono text-green-700 w-12 text-right flex-shrink-0">{Math.round(selectedNode.effective_cpu_mc)}m</span>
                          </div>
                        </div>
                        <p className="text-[10px] text-gray-400 italic">
                          Eviction buffer: {Math.round((od.eviction_buffer_bytes || 0) / (1024**2))} MiB · kube-reserve mem: {Math.round((od.kube_reserved_mem_bytes || 0) / (1024**2))} MiB · DS mem: {Math.round((od.daemonset_mem_bytes || 0) / (1024**2))} MiB
                        </p>
                      </div>
                    );
                  })()}

                  {/* Right-Sizing Mode Indicator */}
                  {selectedNode.type && selectedNode.type !== '—' && (
                    <div className="flex items-center gap-3 px-4 py-2.5 bg-gray-50 border border-gray-200 rounded-lg text-[11px]">
                      <span className="font-bold text-gray-500 uppercase tracking-wider text-[9px] flex-shrink-0">Sizing Mode</span>
                      <span className="px-2 py-0.5 bg-blue-50 border border-blue-200 text-blue-700 font-bold rounded text-[9px] uppercase">Shape Preserved</span>
                      <span className="text-gray-500">{selectedNode.type} <span className="text-gray-400">OD</span> → <span className="font-bold text-indigo-700">{selectedNode.type} Spot</span> (Right-Sizing OFF)</span>
                    </div>
                  )}

                  {/* Karpenter Provisioning Latency */}
                  {karpenterMetrics?.available && (
                    <div className="bg-white rounded-lg border border-gray-200 shadow-sm p-4">
                      <h3 className="text-sm font-semibold text-gray-900 mb-3">Karpenter Provisioning Latency <span className="text-xs font-normal text-gray-500">(P90, seconds)</span></h3>
                      <div className="grid grid-cols-2 gap-2">
                        {Object.entries(karpenterMetrics.latency_p90_seconds || {}).map(([cls, p90]) =>
                          p90 != null ? (
                            <div key={cls} className="flex justify-between items-center bg-gray-50 rounded px-3 py-2 text-xs">
                              <span className="text-gray-500 font-mono">{cls}</span>
                              <span className={`font-bold ${p90 > 90 ? 'text-red-600' : p90 > 45 ? 'text-amber-600' : 'text-green-700'}`}>{p90}s</span>
                            </div>
                          ) : null
                        )}
                      </div>
                    </div>
                  )}

                  {/* Pod Spatial Map — live data from bin-packing-detail, tile width proportional to real cpu_usage_millicores */}
                  <div className="bg-white rounded-lg border border-gray-200 shadow-sm p-4">
                    <h3 className="text-sm font-semibold text-gray-900 mb-3">Pod Spatial Map <span className="text-xs font-normal text-gray-500">(tile width ∝ CPU usage)</span></h3>
                    {detailLoading ? (
                      <div className="w-full h-24 bg-gray-50 rounded flex items-center justify-center text-xs text-gray-400">Loading pod data...</div>
                    ) : detailPods.length === 0 ? (
                      <div className="w-full h-24 bg-gray-50 rounded flex items-center justify-center text-xs text-gray-400">No pod data available for this node.</div>
                    ) : (() => {
                      const maxCpu = Math.max(1, ...detailPods.map(p => p.cpu_usage_millicores || 0));
                      const totalCpu = detailPods.reduce((s, p) => s + (p.cpu_usage_millicores || 0), 0);
                      return (
                        <div className="w-full bg-gray-50 rounded border border-gray-200 overflow-hidden">
                          <div className="flex flex-wrap gap-0.5 p-1.5">
                            {detailPods.slice(0, 24).map((pod, i) => {
                              const cpu = pod.cpu_usage_millicores || 0;
                              const widthPct = totalCpu > 0 ? Math.max(4, Math.round((cpu / totalCpu) * 100)) : 4;
                              return (
                                <div
                                  key={i}
                                  className={`rounded border flex items-center justify-center py-1 text-[9px] font-semibold cursor-default hover:opacity-80 transition-opacity overflow-hidden ${POD_COLORS[i % POD_COLORS.length]}`}
                                  style={{ width: `${widthPct}%`, minWidth: '2.5rem' }}
                                  title={`${pod.pod_name} | CPU: ${cpu}m used / ${pod.cpu_request_millicores || 0}m req`}
                                >
                                  <span className="truncate px-1">{pod.pod_name?.split('-').slice(-2).join('-') || `pod-${i}`}</span>
                                </div>
                              );
                            })}
                            {detailPods.length > 24 && (
                              <span className="px-2 py-1 text-[9px] text-gray-400 self-center">+{detailPods.length - 24} more</span>
                            )}
                          </div>
                          <div className="flex justify-between items-center px-2 py-1 bg-white border-t border-gray-100 text-[9px] text-gray-400">
                            <span>Total used: {totalCpu}m CPU across {detailPods.length} pods</span>
                            <span className="font-medium">{Math.max(0, 100 - selectedNode.cpu_util)}% node capacity free</span>
                          </div>
                        </div>
                      );
                    })()}
                  </div>
                </div>
              </>
            ) : (
              <div className="flex-1 flex items-center justify-center text-sm text-gray-500">
                Select a node to view packing details
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}