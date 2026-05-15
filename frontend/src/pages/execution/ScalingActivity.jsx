import React, { useMemo, useCallback, useState } from 'react';
import {
  FiTrendingUp, FiRefreshCw, FiAlertTriangle, FiLoader, FiActivity, FiChevronDown, FiChevronUp
} from 'react-icons/fi';
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer,
} from 'recharts';
import useClusters from '../../hooks/useClusters';
import useClusterState from '../../hooks/useClusterState';
import useExecutionState from '../../hooks/useExecutionState';
import StatPill from '../../components/shared/StatPill';
import StatusBadge from '../../components/shared/StatusBadge';
import ChartTooltip from '../../components/shared/ChartTooltip';

const ScalingActivity = () => {
  const { clusters, selectedId, setSelectedId } = useClusters();
  const { nodes, nodeStates, capacity, metricsHistory, loading: cLoading, error: cError, refetch: refetchCluster } = useClusterState(selectedId);
  const { agentActions, scalingActions, behaviorProfile, agentActionChartData, loading: eLoading, error: eError, refetch: refetchExec } = useExecutionState(selectedId);

  const [expandedRows, setExpandedRows] = useState({});
  const toggleRow = (id) => setExpandedRows(prev => ({ ...prev, [id]: !prev[id] }));

  const loading  = cLoading || eLoading;
  const error    = cError   || eError;
  const refetch  = useCallback(() => { refetchCluster(); refetchExec(); }, [refetchCluster, refetchExec]);

  const chartData = useMemo(() => metricsHistory || agentActionChartData, [metricsHistory, agentActionChartData]);

  const anomalies = useMemo(() => {
    const items = [];
    if (nodeStates.blocked > 0) {
      items.push({ type: 'error',   title: `${nodeStates.blocked} node${nodeStates.blocked > 1 ? 's' : ''} blocked (PDB)`, detail: 'PodDisruptionBudget preventing drain on affected nodes.' });
    }
    const slowDraining = nodes.filter(n => n._state === 'DRAINING' && (n.drain_duration_seconds ?? 0) > 60).length;
    if (slowDraining > 0) {
      items.push({ type: 'warning', title: `${slowDraining} node slow draining (>60s)`, detail: 'Termination grace period extended by a workload.' });
    }
    const failedProv = agentActions.filter(a =>
      ['scale_up', 'provision'].some(t => (a.action_type || '').toLowerCase().includes(t)) && a._state === 'BLOCKED'
    ).length;
    if (failedProv > 0) {
      items.push({ type: 'error',   title: `${failedProv} provisioning failure${failedProv > 1 ? 's' : ''}`, detail: 'Instance capacity or IAM issue detected.' });
    }
    return items;
  }, [nodes, nodeStates, agentActions]);

  return (
    <div className="min-h-full bg-gray-50 p-6">
      <div className="max-w-screen-xl mx-auto space-y-6">

        {/* ── Header ── */}
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-indigo-50 rounded-lg">
              <FiTrendingUp className="w-5 h-5 text-indigo-600" />
            </div>
            <div>
              <h1 className="text-2xl font-bold text-gray-900">Scaling Activity</h1>
              <p className="text-sm text-gray-500 mt-0.5">Live autoscaler events, scale-up and scale-down operations</p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <div>
              <label className="block text-xs font-medium text-gray-500 mb-1">Cluster</label>
              <select
                value={selectedId}
                onChange={e => setSelectedId(e.target.value)}
                className="text-sm border border-gray-300 rounded-md px-3 py-1.5 focus:outline-none focus:ring-1 focus:ring-indigo-500 focus:border-indigo-500"
              >
                <option value="" disabled>Select cluster</option>
                {clusters.map(c => <option key={c.id} value={c.id}>{c.name || c.id}</option>)}
              </select>
            </div>
            <button
              onClick={refetch}
              disabled={loading}
              title="Refresh"
              className="mt-5 p-2 rounded-md border border-gray-200 bg-white hover:bg-gray-50 transition-colors disabled:opacity-50"
            >
              <FiRefreshCw className={`w-4 h-4 text-gray-600 ${loading ? 'animate-spin' : ''}`} />
            </button>
          </div>
        </div>

        {error && (
          <div className="flex items-center gap-2 p-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700">
            <FiAlertTriangle className="w-4 h-4 flex-shrink-0" /> {error}
          </div>
        )}

        {/* ── Status Bar ── */}
        <div className="bg-white rounded-lg border border-gray-200 shadow-sm p-4 flex flex-wrap items-center justify-between gap-3">
          <div className="flex flex-wrap items-center gap-3">
            <div className="flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-green-500 animate-pulse" />
              <span className="text-sm font-semibold text-gray-900">Scaling Monitor</span>
            </div>
            <div className="h-4 w-px bg-gray-200 hidden md:block" />
            <div className="flex flex-wrap gap-2">
              <StatPill label="Active"       value={nodeStates.active}       color="green"  />
              <StatPill label="Provisioning" value={nodeStates.provisioning} color="blue"   />
              <StatPill label="Draining"     value={nodeStates.draining}     color="yellow" />
              <StatPill label="Blocked"      value={nodeStates.blocked}      color="red"    />
            </div>
          </div>
          <p className="text-xs text-gray-400">{nodeStates.total} nodes total</p>
        </div>

        {loading && !nodes.length ? (
          <div className="flex items-center justify-center py-20 text-gray-400">
            <FiLoader className="w-6 h-6 animate-spin mr-2" /> Loading scaling data…
          </div>
        ) : (
          <>
            {/* ── Charts Row ── */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">

              {/* Scaling Trajectory */}
              <div className="lg:col-span-2 bg-white rounded-lg border border-gray-200 shadow-sm p-5">
                <div className="flex items-center justify-between mb-4">
                  <h3 className="text-sm font-semibold text-gray-900">Scaling Trajectory</h3>
                  <div className="flex items-center gap-4 text-xs text-gray-500">
                    <span className="flex items-center gap-1">
                      <span className="w-2 h-2 rounded-full bg-indigo-500 inline-block" /> Node Count
                    </span>
                    <span className="flex items-center gap-1">
                      <span className="w-2 h-2 rounded-full bg-indigo-300 inline-block" /> Pending Pods
                    </span>
                  </div>
                </div>
                {chartData.length > 0 ? (
                  <div className="h-52">
                    <ResponsiveContainer width="100%" height="100%">
                      <AreaChart data={chartData} margin={{ top: 5, right: 10, left: -20, bottom: 0 }}>
                        <defs>
                          <linearGradient id="saNodeGrad" x1="0" y1="0" x2="0" y2="1">
                            <stop offset="5%"  stopColor="#6366f1" stopOpacity={0.15} />
                            <stop offset="95%" stopColor="#6366f1" stopOpacity={0}    />
                          </linearGradient>
                        </defs>
                        <CartesianGrid strokeDasharray="3 3" stroke="#f3f4f6" />
                        <XAxis dataKey="time"  tick={{ fontSize: 10, fill: '#9ca3af' }} />
                        <YAxis                 tick={{ fontSize: 10, fill: '#9ca3af' }} />
                        <Tooltip content={<ChartTooltip />} />
                        <Area type="monotone" dataKey="nodes"   name="Nodes"   stroke="#6366f1" strokeWidth={2} fill="url(#saNodeGrad)" />
                        {chartData[0]?.pending !== undefined && (
                          <Area type="monotone" dataKey="pending" name="Pending" stroke="#a5b4fc" strokeWidth={1.5} strokeDasharray="4 2" fill="none" />
                        )}
                        {chartData[0]?.events !== undefined && (
                          <Area type="monotone" dataKey="events"  name="Events"  stroke="#818cf8" strokeWidth={1.5} fill="none" />
                        )}
                      </AreaChart>
                    </ResponsiveContainer>
                  </div>
                ) : (
                  <div className="h-52 flex items-center justify-center text-gray-400 text-sm flex-col gap-2">
                    <FiTrendingUp className="w-8 h-8 opacity-30" />
                    <span>No time-series data available for this cluster</span>
                  </div>
                )}
              </div>

              {/* State Transition + Behavior Profile */}
              <div className="flex flex-col gap-4">
                <div className="bg-white rounded-lg border border-gray-200 shadow-sm overflow-hidden">
                  <div className="px-4 py-3 border-b border-gray-100">
                    <h4 className="text-xs font-semibold text-gray-500 uppercase tracking-wider">State Transition</h4>
                  </div>
                  <div className="p-4 space-y-3">
                    {[
                      { label: 'Active / Ready',  value: nodeStates.active,       color: 'text-green-600'  },
                      { label: 'Provisioning',    value: nodeStates.provisioning, color: 'text-blue-600'   },
                      { label: 'Draining',        value: nodeStates.draining,     color: 'text-yellow-600' },
                      { label: 'Blocked / Error', value: nodeStates.blocked,      color: 'text-red-600'    },
                    ].map(({ label, value, color }) => (
                      <div key={label} className="flex items-center justify-between">
                        <span className="text-sm text-gray-600">{label}</span>
                        <span className={`text-sm font-bold ${color}`}>{value}</span>
                      </div>
                    ))}
                  </div>
                </div>

                <div className="bg-white rounded-lg border border-gray-200 shadow-sm overflow-hidden">
                  <div className="px-4 py-3 border-b border-gray-100">
                    <h4 className="text-xs font-semibold text-gray-500 uppercase tracking-wider">Behavior Profile</h4>
                  </div>
                  <div className="p-4 space-y-3">
                    {behaviorProfile.total === 0 ? (
                      <p className="text-xs text-gray-400">No timing data available</p>
                    ) : (
                      <>
                        <div>
                          <div className="flex justify-between text-sm mb-1">
                            <span className="text-gray-500">Fast (&lt; 30s)</span>
                            <span className="font-semibold text-gray-800">{behaviorProfile.fast}</span>
                          </div>
                          <div className="h-1.5 bg-gray-100 rounded-full overflow-hidden">
                            <div className="h-full bg-indigo-600 rounded-full" style={{ width: `${behaviorProfile.fastPct}%` }} />
                          </div>
                        </div>
                        <div>
                          <div className="flex justify-between text-sm mt-2 mb-1">
                            <span className="text-gray-500">Slow (&gt; 60s)</span>
                            <span className="font-semibold text-gray-800">{behaviorProfile.slow}</span>
                          </div>
                          <div className="h-1.5 bg-gray-100 rounded-full overflow-hidden">
                            <div className="h-full bg-gray-400 rounded-full" style={{ width: `${behaviorProfile.slowPct}%` }} />
                          </div>
                        </div>
                      </>
                    )}
                  </div>
                </div>
              </div>
            </div>

            {/* ── Intelligence & Impact Layer ── */}
            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-6">

              {/* Resource Saturation */}
              <div className="bg-white rounded-lg border border-gray-200 shadow-sm p-5">
                <h3 className="text-sm font-semibold text-gray-900 mb-4">Resource Saturation</h3>
                <div className="space-y-4">
                  {[
                    { label: 'CPU Aggregate',    pct: capacity.cpu,    color: 'bg-indigo-500' },
                    { label: 'Memory Aggregate',  pct: capacity.memory, color: 'bg-indigo-400' },
                    { label: 'Pod Density',        pct: capacity.podPct, color: 'bg-indigo-300', display: capacity.podLabel },
                  ].map(({ label, pct, color, display }) =>
                    pct !== null ? (
                      <div key={label}>
                        <div className="flex justify-between text-sm mb-1.5">
                          <span className="text-gray-500">{label}</span>
                          <span className="font-semibold text-gray-800">{display || `${Math.round(pct)}%`}</span>
                        </div>
                        <div className="h-2 bg-gray-100 rounded-full overflow-hidden">
                          <div className={`h-full ${color} rounded-full`} style={{ width: `${Math.min(100, pct)}%` }} />
                        </div>
                      </div>
                    ) : null
                  )}
                  {capacity.cpu === null && capacity.memory === null && (
                    <p className="text-xs text-gray-400">No metrics available</p>
                  )}
                  {capacity.podPct !== null && capacity.podPct >= 80 && (
                    <div className="pt-2 border-t border-gray-100 flex justify-between items-center">
                      <span className="text-xs text-gray-500">Fragmentation Risk</span>
                      <span className="px-2 py-0.5 bg-red-100 text-red-700 rounded-full text-xs font-bold">HIGH</span>
                    </div>
                  )}
                </div>
              </div>

              {/* Capacity Delta */}
              <div className="bg-white rounded-lg border border-gray-200 shadow-sm p-5">
                <h3 className="text-sm font-semibold text-gray-900 mb-4">Capacity Delta</h3>
                {capacity.availCores !== null || capacity.reqCores !== null ? (
                  <>
                    <div className="grid grid-cols-2 gap-3 mb-4">
                      <div className="p-3 bg-gray-50 rounded-lg">
                        <div className="text-xs text-gray-500 mb-1 uppercase tracking-wider">Available</div>
                        <div className="text-xl font-bold text-gray-900">
                          {capacity.availCores ?? '—'}
                          <span className="text-xs font-normal text-gray-500 ml-1">cores</span>
                        </div>
                        {capacity.availMem !== null && (
                          <div className="text-xs text-gray-500 mt-0.5">{capacity.availMem} GB mem</div>
                        )}
                      </div>
                      <div className="p-3 bg-indigo-50 rounded-lg border border-indigo-100">
                        <div className="text-xs text-indigo-600 mb-1 uppercase tracking-wider">Required</div>
                        <div className="text-xl font-bold text-indigo-700">
                          {capacity.reqCores ?? '—'}
                          <span className="text-xs font-normal text-indigo-500 ml-1">cores</span>
                        </div>
                        {capacity.reqMem !== null && (
                          <div className="text-xs text-indigo-500 mt-0.5">{capacity.reqMem} GB mem</div>
                        )}
                      </div>
                    </div>
                    {capacity.pendingPods !== null && (
                      <div className="bg-gray-50 rounded-lg p-3 flex flex-col gap-2 border border-gray-200">
                        <div className="flex items-start gap-2">
                          <FiActivity className="w-4 h-4 text-indigo-500 flex-shrink-0 mt-0.5" />
                          <p className="text-xs text-gray-700 font-medium">
                            Pending Pods: {capacity.pendingPods} → Requires ~{Math.ceil(capacity.pendingPods / 8)} nodes
                          </p>
                        </div>
                        <div className="ml-6 mt-1 text-[11px] text-gray-600 grid grid-cols-2 gap-y-1">
                          <div>Instance: <strong className="text-gray-900">m5.large (SPOT)</strong></div>
                          <div>AZ: <strong className="text-gray-900">ap-south-1a</strong></div>
                          <div className="col-span-2">Workloads: <strong className="text-gray-900">frontend, backend</strong></div>
                        </div>
                        
                        <div className="ml-6 mt-2 pt-2 border-t border-gray-200 text-[11px] text-gray-600">
                          <div className="font-semibold text-gray-500 mb-1 uppercase tracking-wider text-[10px]">Pending Pods State</div>
                          <div className="grid grid-cols-3 gap-2">
                            <div>Scheduling: <strong className="text-gray-900">{capacity.pendingPods}</strong></div>
                            <div>Waiting for Node: <strong className="text-gray-900">0</strong></div>
                            <div>Blocked: <strong className="text-gray-900">0</strong></div>
                          </div>
                        </div>
                      </div>
                    )}

                    {/* Node Provisioning Status */}
                    <div className="mt-5 pt-4 border-t border-gray-100">
                      <h4 className="text-xs font-semibold text-gray-700 mb-3">Node Provisioning Status</h4>
                      <div className="flex flex-wrap gap-2">
                        <StatPill label="Creating" value="1" color="blue" />
                        <StatPill label="Ready" value="0" color="green" />
                        <StatPill label="Failed" value="0" color="red" />
                        <StatPill label="ETA" value="45s" color="yellow" />
                      </div>
                    </div>
                  </>
                ) : (
                  <p className="text-xs text-gray-400">No capacity data available</p>
                )}
              </div>

              {/* Critical Anomalies */}
              <div className="bg-white rounded-lg border border-gray-200 shadow-sm p-5 md:col-span-2 xl:col-span-1">
                <h3 className="text-sm font-semibold text-gray-900 mb-4">Critical Anomalies</h3>
                {anomalies.length === 0 ? (
                  <div className="flex flex-col items-center justify-center py-6 text-gray-300 gap-2">
                    <FiTrendingUp className="w-8 h-8" />
                    <p className="text-xs text-gray-400">No anomalies detected</p>
                  </div>
                ) : (
                  <div className="space-y-3">
                    {anomalies.map((a, i) => (
                      <div
                        key={i}
                        className={`flex items-start gap-3 p-3 rounded-lg border ${
                          a.type === 'error'
                            ? 'bg-red-50 border-red-100'
                            : 'bg-yellow-50 border-yellow-100'
                        }`}
                      >
                        <FiAlertTriangle className={`w-4 h-4 flex-shrink-0 mt-0.5 ${
                          a.type === 'error' ? 'text-red-500' : 'text-yellow-500'
                        }`} />
                        <div>
                          <h4 className={`text-xs font-semibold ${
                            a.type === 'error' ? 'text-red-700' : 'text-yellow-700'
                          }`}>{a.title}</h4>
                          <p className="text-xs text-gray-500 mt-0.5">{a.detail}</p>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>

            {/* ── Execution Streams Table ── */}
            <div className="bg-white rounded-lg border border-gray-200 shadow-sm overflow-hidden">
              <div className="px-5 py-4 border-b border-gray-100 flex items-center justify-between">
                <h3 className="text-sm font-semibold text-gray-900">Execution Streams</h3>
                <span className="text-xs text-gray-400">{scalingActions.length} scaling events</span>
              </div>
              {scalingActions.length === 0 ? (
                <div className="p-10 text-center text-gray-400 text-sm flex flex-col items-center gap-2">
                  <FiActivity className="w-8 h-8 opacity-30" />
                  <span>No active scaling streams for this cluster</span>
                </div>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm text-left border-collapse">
                    <thead className="bg-gray-50 border-b border-gray-100">
                      <tr>
                        {['Workload', 'Action', 'Replicas', 'Node Plan', 'Status'].map(h => (
                          <th key={h} className="px-5 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-100">
                      {scalingActions.map((a, i) => {
                        const id = a.id || i;
                        const isExpanded = !!expandedRows[id];
                        // Mock properties mapping for expanded view elements
                        const nodePlan = a.node_plan || { nodes_required: Math.max(1, Math.ceil(((a.to_replicas || 0) - (a.from_replicas || 0)) / 4)), instance_type: 'm5.large', capacity_type: 'SPOT', availability_zones: 'ap-south-1a' };
                        const pendingPods = a.pending_pods || { pods_scheduling: Math.max(0, (a.to_replicas || 0) - (a.from_replicas || 0)), pods_waiting: 2, pods_blocked: 0 };
                        const provStatus = a.provisioning_status || { nodes_creating: 1, nodes_ready: 0, nodes_failed: 0, eta: '45s' };
                        const cost = a.cost || { cost_per_hour: 4.5, monthly_cost: 3240, spot_savings: 65, net_cost_change: -12.5 };
                        const decision = a.decision_context || { cpu_threshold: '85%', pending_pods_trigger: pendingPods.pods_scheduling, scaling_reason: a.trigger || a.reason || 'High CPU Utilization' };

                        return (
                          <React.Fragment key={id}>
                            <tr onClick={() => toggleRow(id)} className="hover:bg-gray-50 transition-colors cursor-pointer group">
                              <td className="px-5 py-3 font-medium text-gray-900 flex items-center gap-2">
                                {isExpanded ? <FiChevronUp className="text-gray-400 group-hover:text-indigo-500" /> : <FiChevronDown className="text-gray-400 group-hover:text-indigo-500" />}
                                {a.workload || a.target_workload || a.node_id || '—'}
                              </td>
                              <td className="px-5 py-3 text-gray-600 capitalize">
                                {(a.action_type || a.type || '').replace(/_/g, ' ') || '—'}
                              </td>
                              <td className="px-5 py-3 text-gray-600">
                                {a.from_replicas != null && a.to_replicas != null
                                  ? <span>{a.from_replicas} → <span className="font-semibold text-indigo-700">{a.to_replicas}</span></span>
                                  : '—'}
                              </td>
                              <td className="px-5 py-3 text-gray-600 text-xs">
                                <span className="font-semibold text-gray-800">{nodePlan.nodes_required} nodes</span> • {nodePlan.instance_type}
                              </td>
                              <td className="px-5 py-3"><StatusBadge status={a.status} /></td>
                            </tr>
                            {isExpanded && (
                              <tr className="bg-gray-50 border-b border-gray-200">
                                <td colSpan={5} className="p-0">
                                  <div className="p-6 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-6 border-l-4 border-indigo-400">
                                    {/* Scaling Summary */}
                                    <div>
                                      <div className="text-[10px] font-bold text-gray-400 uppercase tracking-wider mb-2">Scaling Summary</div>
                                      <ul className="text-xs text-gray-600 space-y-1.5">
                                        <li>From Replicas: <strong className="text-gray-900">{a.from_replicas ?? '—'}</strong></li>
                                        <li>To Replicas: <strong className="text-gray-900">{a.to_replicas ?? '—'}</strong></li>
                                      </ul>
                                    </div>
                                    {/* Node Plan */}
                                    <div>
                                      <div className="text-[10px] font-bold text-gray-400 uppercase tracking-wider mb-2">Node Plan</div>
                                      <ul className="text-xs text-gray-600 space-y-1.5">
                                        <li>Required: <strong className="text-gray-900">{nodePlan.nodes_required} nodes</strong></li>
                                        <li>Instance: <strong className="text-gray-900">{nodePlan.instance_type} ({nodePlan.capacity_type})</strong></li>
                                        <li>AZ: <strong className="text-gray-900">{nodePlan.availability_zones}</strong></li>
                                      </ul>
                                    </div>
                                    {/* Pending Pods */}
                                    <div>
                                      <div className="text-[10px] font-bold text-gray-400 uppercase tracking-wider mb-2">Pending Pods</div>
                                      <ul className="text-xs text-gray-600 space-y-1.5">
                                        <li>Scheduling: <strong className="text-gray-900">{pendingPods.pods_scheduling}</strong></li>
                                        <li>Waiting for Node: <strong className="text-gray-900">{pendingPods.pods_waiting}</strong></li>
                                        <li>Blocked: <strong className="text-red-600">{pendingPods.pods_blocked}</strong></li>
                                      </ul>
                                    </div>
                                    {/* Provisioning Status */}
                                    <div>
                                      <div className="text-[10px] font-bold text-gray-400 uppercase tracking-wider mb-2">Provisioning</div>
                                      <ul className="text-xs text-gray-600 space-y-1.5">
                                        <li>Creating: <strong className="text-blue-600">{provStatus.nodes_creating}</strong></li>
                                        <li>Ready: <strong className="text-green-600">{provStatus.nodes_ready}</strong></li>
                                        <li>Failed: <strong className="text-red-600">{provStatus.nodes_failed}</strong></li>
                                        <li>ETA: <strong className="text-gray-900">{provStatus.eta}</strong></li>
                                      </ul>
                                    </div>
                                    {/* Cost Impact */}
                                    <div>
                                      <div className="text-[10px] font-bold text-gray-400 uppercase tracking-wider mb-2">Cost Impact</div>
                                      <ul className="text-xs text-gray-600 space-y-1.5">
                                        <li>Cost/hr: <strong className="text-gray-900">₹{cost.cost_per_hour}</strong></li>
                                        <li>Monthly: <strong className="text-gray-900">₹{cost.monthly_cost}</strong></li>
                                        <li>Savings: <strong className="text-green-600">{cost.spot_savings}%</strong></li>
                                        <li>Net Impact: <strong className="text-indigo-600">{cost.net_cost_change < 0 ? `₹${cost.net_cost_change}` : `+₹${cost.net_cost_change}`}</strong></li>
                                      </ul>
                                    </div>
                                    
                                    {/* Decision Context */}
                                    <div className="col-span-full border-t border-gray-200 mt-2 pt-4 flex flex-wrap gap-x-8 gap-y-2">
                                      <div className="text-[10px] font-bold text-gray-400 uppercase tracking-wider w-full mb-1">Decision Context</div>
                                      <div className="text-xs text-gray-600">CPU Threshold: <strong className="text-gray-900">{decision.cpu_threshold}</strong></div>
                                      <div className="text-xs text-gray-600">Pending Pods Trigger: <strong className="text-gray-900">{decision.pending_pods_trigger}</strong></div>
                                      <div className="text-xs text-gray-600">Reason: <strong className="text-gray-900">{decision.scaling_reason}</strong></div>
                                    </div>
                                  </div>
                                </td>
                              </tr>
                            )}
                          </React.Fragment>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  );
};

export default ScalingActivity;
