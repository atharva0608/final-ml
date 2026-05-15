import React, { useState, useEffect, useMemo } from 'react';
import { 
  Search, SlidersHorizontal, Activity, BarChart2, Server, 
  MoreVertical, CheckCircle2, XCircle, Loader2, AlertCircle, 
  ChevronRight, Clock, Filter
} from 'lucide-react';
import { workloadClassificationAPI, placementPolicyAPI, clustersAPI } from '../../services/api';

// --- COMPONENTS ---
const StatusBadge = ({ status }) => {
  const styles = {
    STABLE: 'bg-green-100 text-green-700 border-green-200',
    REBALANCING: 'bg-blue-100 text-blue-700 border-blue-200 animate-pulse-subtle',
    THROTTLING: 'bg-orange-100 text-orange-700 border-orange-200',
    BLOCKED: 'bg-red-100 text-red-700 border-red-200',
    SCALING: 'bg-purple-100 text-purple-700 border-purple-200',
  };

  return (
    <span className={`px-2 py-0.5 rounded text-[11px] font-semibold border uppercase tracking-wider ${styles[status] || styles.STABLE}`}>
      {status}
    </span>
  );
};

const DriftBadge = ({ level, value }) => {
  const styles = {
    Low: 'bg-gray-100 text-gray-600',
    Medium: 'bg-yellow-100 text-yellow-700',
    High: 'bg-red-100 text-red-700',
  };

  return (
    <div className="flex items-center gap-1.5">
      <span className={`px-2 py-0.5 rounded text-xs font-medium ${styles[level] || styles.Low}`}>
        {level}
      </span>
      {value > 0 && <span className="text-sm font-medium text-gray-700">Drift: {value}</span>}
    </div>
  );
};

const ProgressBar = ({ progress, status }) => {
  const getBarColor = () => {
    if (progress === 100) return 'bg-green-500';
    if (status === 'REBALANCING' || status === 'SCALING') return 'bg-blue-500';
    if (status === 'THROTTLING') return 'bg-orange-400';
    if (status === 'BLOCKED') return 'bg-red-500';
    return 'bg-gray-400';
  };

  return (
    <div className="flex items-center gap-2">
      <div className="w-24 h-1.5 bg-gray-100 rounded-full overflow-hidden">
        <div 
          className={`h-full rounded-full transition-all duration-500 ${getBarColor()}`} 
          style={{ width: `${Math.min(100, Math.max(0, progress))}%` }}
        />
      </div>
      <span className="text-xs text-gray-500 font-medium w-8">{Math.round(progress)}%</span>
    </div>
  );
};

const WorkloadsTable = ({ workloads, loading }) => {
  if (loading) return <div className="p-8 text-center text-gray-500">Loading real data...</div>;

  return (
    <div className="bg-white rounded-lg border border-gray-200 shadow-sm overflow-hidden">
      <table className="w-full text-left text-sm">
        <thead className="bg-gray-50 border-b border-gray-200 text-gray-500 font-medium">
          <tr>
            <th className="px-5 py-3.5 font-medium">Workload</th>
            <th className="px-5 py-3.5 font-medium">Status</th>
            <th className="px-5 py-3.5 font-medium">Current</th>
            <th className="px-5 py-3.5 font-medium">Target</th>
            <th className="px-5 py-3.5 font-medium">Drift</th>
            <th className="px-5 py-3.5 font-medium">Progress</th>
            <th className="px-5 py-3.5 font-medium">Confidence</th>
            <th className="px-5 py-3.5 font-medium text-right">Actions</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-100">
          {workloads.map((w) => (
            <tr key={w.uid} className="hover:bg-gray-50 transition-colors">
              <td className="px-5 py-3">
                <div className="font-medium text-gray-900">{w.name}</div>
                <div className="text-[11px] text-gray-400 mt-0.5">{w.uid}</div>
              </td>
              <td className="px-5 py-3">
                <StatusBadge status={w.status} />
              </td>
              <td className="px-5 py-3">
                <span className="font-mono text-gray-600 text-[13px]">{w.current}</span>
              </td>
              <td className="px-5 py-3">
                <span className="font-mono text-green-700 bg-green-50 px-1.5 py-0.5 rounded text-[13px] border border-green-100">{w.target}</span>
              </td>
              <td className="px-5 py-3">
                <DriftBadge level={w.driftLevel} value={w.driftValue} />
              </td>
              <td className="px-5 py-3">
                <ProgressBar progress={w.progress} status={w.status} />
              </td>
              <td className="px-5 py-3">
                <span className="text-gray-500 text-xs">{w.confidence}%</span>
              </td>
              <td className="px-5 py-3 text-right">
                <button className="text-gray-400 hover:text-gray-700 transition-colors">
                  <MoreVertical size={16} />
                </button>
              </td>
            </tr>
          ))}
          {workloads.length === 0 && (
            <tr>
              <td colSpan="8" className="px-5 py-8 text-center text-gray-500">No actionable workloads found.</td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
};

const LiveActivityFeed = ({ agentActions, loading }) => {
  if (loading) return <div className="p-4 text-gray-500">Connecting to agent stream...</div>;

  return (
    <div className="max-w-4xl">
      <div className="flex items-center gap-2 mb-4 text-sm text-gray-500">
        <div className="w-2 h-2 rounded-full bg-green-500 animate-pulse"></div>
        Live connection established. Polling actively.
      </div>
      <div className="flex flex-col gap-2.5">
        {agentActions.map((item) => (
          <div 
            key={item.id} 
            className="bg-white border border-gray-200 rounded-md p-3.5 shadow-sm flex items-start gap-3.5 animate-slide-in"
          >
            <div className="mt-0.5">
              {item.type === 'RUNNING' && <Loader2 className="text-blue-500 animate-spin" size={18} />}
              {item.type === 'SUCCESS' && <CheckCircle2 className="text-green-500" size={18} />}
              {item.type === 'RETRY' && <AlertCircle className="text-red-500" size={18} />}
              {item.type === 'FAILED' && <XCircle className="text-red-600" size={18} />}
            </div>
            <div className="flex-1">
              <div className="flex justify-between items-start mb-1.5">
                <span className="font-medium text-gray-900 text-[15px]">{item.text}</span>
                <span className="text-xs text-gray-400 flex items-center gap-1">
                  <Clock size={12} /> {item.time}
                </span>
              </div>
              <div className="grid grid-cols-3 gap-4 text-[13px]">
                <div>
                  <span className="text-gray-400 block text-xs mb-0.5">Reason</span>
                  <span className="text-gray-700">{item.reason}</span>
                </div>
                <div>
                  <span className="text-gray-400 block text-xs mb-0.5">Target</span>
                  <span className="text-gray-700">{item.target}</span>
                </div>
                <div>
                  <span className="text-gray-400 block text-xs mb-0.5">Source</span>
                  <span className="text-gray-700">{item.source}</span>
                </div>
              </div>
            </div>
          </div>
        ))}
        {agentActions.length === 0 && (
          <div className="p-4 text-gray-500 border border-gray-200 rounded-md bg-white">No recent actions found.</div>
        )}
      </div>
    </div>
  );
};

const SystemInsights = ({ nodeClaims, placementMetrics, rolloutStatus, loading }) => (
  <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
    {/* Card 1: Skip Reasons */}
    <div className="bg-white border border-gray-200 rounded-lg shadow-sm p-5">
      <h3 className="font-medium text-gray-900 mb-5 flex items-center gap-2">
        <AlertCircle size={16} className="text-gray-400" />
        Optimization Skip Reasons
      </h3>
      <div className="space-y-4">
        {placementMetrics?.skip_reasons?.length > 0 ? (
          placementMetrics.skip_reasons.map(item => (
            <div key={item.label}>
              <div className="flex justify-between text-sm mb-1.5">
                <span className="text-gray-600">{item.label}</span>
                <span className="font-medium text-gray-900">{item.value}%</span>
              </div>
              <div className="w-full bg-gray-100 h-1.5 rounded-full overflow-hidden">
                <div className={`h-full ${item.color} rounded-full`} style={{ width: `${item.value}%` }}></div>
              </div>
            </div>
          ))
        ) : (
          <div className="text-gray-500 text-sm">No skip reasons data available</div>
        )}
      </div>
    </div>

    {/* Card 2: Rollout Success */}
    <div className="bg-white border border-gray-200 rounded-lg shadow-sm p-5 flex flex-col items-center justify-center relative overflow-hidden">
      <h3 className="font-medium text-gray-900 absolute top-5 left-5">Rollout Success</h3>
      <div className="relative flex items-center justify-center w-28 h-28 mt-4">
        <svg className="w-full h-full transform -rotate-90">
          <circle cx="56" cy="56" r="48" fill="transparent" stroke="#f3f4f6" strokeWidth="10" />
          <circle cx="56" cy="56" r="48" fill="transparent" stroke="#22c55e" strokeWidth="10" strokeDasharray="301.5" strokeDashoffset={301.5 * (1 - (rolloutStatus?.success_rate || 0) / 100)} className="transition-all duration-1000" />
        </svg>
        <div className="absolute flex flex-col items-center justify-center">
          <span className="text-2xl font-bold text-gray-900">{rolloutStatus?.success_rate || 0}%</span>
          <span className="text-[11px] text-gray-500 mt-0.5">Success Rate</span>
        </div>
      </div>
    </div>

    {/* Card 3: Timeout Tracking */}
    <div className="bg-white border border-gray-200 rounded-lg shadow-sm p-5">
      <h3 className="font-medium text-gray-900 mb-5 flex items-center gap-2">
        <Clock size={16} className="text-gray-400" />
        Action Timeout Tracking
      </h3>
      <div className="space-y-4 text-sm">
        {rolloutStatus?.active_timeouts?.length > 0 ? (
          rolloutStatus.active_timeouts.map((timeout, idx) => (
            <div key={idx} className="flex items-center gap-4 group">
              <span className="w-24 text-gray-700 font-mono text-xs truncate">{timeout.workload_id}</span>
              <div className="flex-1 bg-gray-100 h-1.5 rounded-full overflow-hidden">
                <div className={`h-full ${timeout.color} rounded-full`} style={{ width: `${timeout.progress_pct}%` }}></div>
              </div>
              <span className="w-16 text-right text-gray-500 font-medium text-xs">{timeout.age_minutes}m / {timeout.timeout_limit}m</span>
            </div>
          ))
        ) : (
          <div className="text-gray-500 text-sm">No active timeouts</div>
        )}
      </div>
    </div>

    {/* Card 4: NodeClaims Table */}
    <div className="bg-white border border-gray-200 rounded-lg shadow-sm p-0 overflow-hidden flex flex-col">
      <div className="p-4 border-b border-gray-100">
        <h3 className="font-medium text-gray-900">Active NodeClaims</h3>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-left text-sm whitespace-nowrap">
          <thead className="bg-gray-50 text-gray-400 border-b border-gray-100 text-[11px] uppercase tracking-wider">
            <tr>
              <th className="px-4 py-2 font-medium">Node</th>
              <th className="px-4 py-2 font-medium">Type</th>
              <th className="px-4 py-2 font-medium">Zone</th>
              <th className="px-4 py-2 font-medium">Price</th>
              <th className="px-4 py-2 font-medium">Age</th>
              <th className="px-4 py-2 font-medium">TTL</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-50">
            {nodeClaims?.length > 0 ? nodeClaims.map((nc, idx) => (
               <tr key={idx}>
                 <td className="px-4 py-2.5 font-mono text-[11px] text-gray-700">{nc.name || nc.node}</td>
                 <td className="px-4 py-2.5 text-gray-600">{nc.type}</td>
                 <td className="px-4 py-2.5 text-gray-600">{nc.zone}</td>
                 <td className="px-4 py-2.5 text-gray-600">{nc.price || 'N/A'}</td>
                 <td className="px-4 py-2.5 text-gray-500">{nc.age || 'N/A'}</td>
                 <td className="px-4 py-2.5 text-gray-500">{nc.ttl || 'N/A'}</td>
               </tr>
            )) : (
              <tr>
                <td colSpan="6" className="px-4 py-2.5 text-gray-500 text-center">Loading or no claims...</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  </div>
);

// --- MAIN APP ---
export default function WorkloadInventoryDashboard({ clusterId }) {
  const [activeTab, setActiveTab] = useState('Workloads');
  const [workloadsData, setWorkloadsData] = useState([]);
  const [policiesData, setPoliciesData] = useState([]);
  const [podsData, setPodsData] = useState([]);
  const [agentActionsData, setAgentActionsData] = useState([]);
  const [nodeClaimsData, setNodeClaimsData] = useState([]);
  // Real metrics data to replace fake data
  const [placementMetrics, setPlacementMetrics] = useState(null);
  const [rolloutStatus, setRolloutStatus] = useState(null);
  const [loading, setLoading] = useState(true);

  // DATA FETCHING HOOKS
  useEffect(() => {
    let mounted = true;
    
    const fetchAllData = async () => {
      try {
        const [wRes, pRes, podRes, actRes, ncRes, metricsRes, rolloutRes] = await Promise.allSettled([
          workloadClassificationAPI.getWorkloads(clusterId),
          placementPolicyAPI.list ? placementPolicyAPI.list(clusterId) : { data: [] },
          clustersAPI.getPods ? clustersAPI.getPods(clusterId) : { data: [] },
          clustersAPI.getAgentActions ? clustersAPI.getAgentActions(clusterId) : { data: [] },
          clustersAPI.getNodeClaims ? clustersAPI.getNodeClaims(clusterId) : { data: [] },
          clustersAPI.getPlacementMetrics ? clustersAPI.getPlacementMetrics(clusterId) : { data: [] },
          clustersAPI.getRolloutStatus ? clustersAPI.getRolloutStatus(clusterId) : { data: [] }
        ]);

        if (!mounted) return;

        const wItems = wRes.status === 'fulfilled' ? (wRes.value.data.items || wRes.value.data) : [];
        const policies = pRes.status === 'fulfilled' ? (pRes.value.data.items || pRes.value.data) : [];
        const pods = podRes.status === 'fulfilled' ? (podRes.value.data.items || podRes.value.data) : [];
        const actions = actRes.status === 'fulfilled' ? (actRes.value.data.items || actRes.value.data) : [];
        const nodeClaims = ncRes.status === 'fulfilled' ? (ncRes.value.data.items || ncRes.value.data) : [];
        const metrics = metricsRes.status === 'fulfilled' ? metricsRes.value.data : {};
        const rollout = rolloutRes.status === 'fulfilled' ? rolloutRes.value.data : {};

        setWorkloadsData(wItems);
        setPoliciesData(Array.isArray(policies) ? policies : []);
        setPodsData(Array.isArray(pods) ? pods : []);
        setAgentActionsData(actions);
        setNodeClaimsData(nodeClaims);
        setPlacementMetrics(metrics);
        setRolloutStatus(rollout);
        setLoading(false);
      } catch (err) {
        console.error("Failed to load real data", err);
        if (mounted) setLoading(false);
      }
    };

    fetchAllData();
    const interval = setInterval(fetchAllData, 3000);
    return () => { mounted = false; clearInterval(interval); };
  }, [clusterId]);

  const enrichedWorkloads = useMemo(() => {
    if (!workloadsData.length) return [];
    const policyMap = {};
    (policiesData || []).forEach(p => { if (p.workload_id) policyMap[p.workload_id] = p; });
    const podsByWorkload = {};
    (podsData || []).forEach(p => {
      if (!p.workload_id) return;
      if (!podsByWorkload[p.workload_id]) podsByWorkload[p.workload_id] = [];
      podsByWorkload[p.workload_id].push(p);
    });
    return workloadsData.map(w => {
      const policy = policyMap[w.workload_id];
      const wPods = podsByWorkload[w.workload_id] || [];
      const spotPods = wPods.filter(p => (p.capacity_type || '').toLowerCase() === 'spot').length;
      const odPods = wPods.filter(p => { const ct = (p.capacity_type || '').toLowerCase(); return ct === 'on-demand' || ct === 'on_demand' || ct === 'ondemand'; }).length;
      const spotTarget = policy?.spot_target ?? policy?.target_spot ?? '?';
      const odTarget = policy?.ondemand_target ?? policy?.target_od ?? '?';
      const driftValue = (typeof spotTarget === 'number' && typeof odTarget === 'number')
        ? Math.abs(spotPods - spotTarget) + Math.abs(odPods - odTarget) : 0;
      const driftLevel = driftValue > 3 ? 'High' : driftValue > 0 ? 'Medium' : 'Low';
      const rawSpot = w.spot_score || 0;
      const progress = rawSpot <= 1 ? Math.round(rawSpot * 100) : Math.round(rawSpot);
      const rawConf = w.confidence_score || 0;
      const confidence = rawConf <= 1 ? Math.round(rawConf * 100) : Math.round(rawConf);
      let status = 'STABLE';
      if (w.confidence_state === 'DRAFT') status = 'BLOCKED';
      else if (w.confidence_state === 'PROVISIONAL') status = 'SCALING';
      else if (driftValue > 1) status = 'REBALANCING';
      else if (wPods.some(p => (p.cpu_usage_pct || 0) > 85)) status = 'THROTTLING';
      return {
        uid: w.workload_id,
        name: w.name ? `${w.namespace}/${w.name}` : (w.workload_id || 'unknown'),
        current: wPods.length > 0 ? `${odPods} OD / ${spotPods} Spot` : '-- OD / -- Spot',
        target: (spotTarget !== '?' || odTarget !== '?') ? `${odTarget} OD / ${spotTarget} Spot` : (w.spot_friendly ? '↑ Spot preferred' : 'OD only'),
        driftValue, driftLevel, progress, confidence, status,
      };
    });
  }, [workloadsData, policiesData, podsData]);

  const mappedActions = useMemo(() => {
    return (agentActionsData || []).map(r => {
      const st = (r.status || '').toUpperCase();
      let type = 'SUCCESS';
      if (st === 'PENDING' || st === 'PICKED_UP') type = 'RUNNING';
      else if (st === 'FAILED' || st === 'EXPIRED') type = 'RETRY';
      const payload = r.payload || {};
      const actionLabel = (r.action_type || 'ACTION').replace(/_/g, ' ');
      const targetLabel = payload.pod_name || payload.workload_id || payload.node_id || payload.node_name
        || (r.action_type?.includes('INSTALL') || r.action_type?.includes('UNINSTALL') ? `cluster:${(r.cluster_id || '').slice(0, 8) || '...'}` : null)
        || 'unknown';
      let timeStr = 'Just now';
      if (r.created_at) {
        const secs = Math.floor((Date.now() - new Date(r.created_at).getTime()) / 1000);
        if (secs >= 86400) timeStr = `${Math.floor(secs / 86400)}d ago`;
        else if (secs >= 3600) timeStr = `${Math.floor(secs / 3600)}h ago`;
        else if (secs >= 60) timeStr = `${Math.floor(secs / 60)}m ago`;
        else if (secs > 0) timeStr = `${secs}s ago`;
      }
      return {
        id: r.id || `${r.action_type}-${r.created_at}`,
        type,
        text: `${actionLabel} on ${targetLabel}`,
        time: timeStr,
        reason: payload.reason || r.error_message || 'Queued by controller',
        target: payload.target_node || payload.node_name || payload.pod_name || 'N/A',
        source: payload.source || (r.action_type?.includes('KARPENTER') ? 'KarpenterController' : r.action_type?.includes('KEDA') ? 'KedaController' : 'PlacementController'),
      };
    });
  }, [agentActionsData]);

  const overallDrift = useMemo(() => {
    if (!enrichedWorkloads.length) return 'Tracking';
    if (enrichedWorkloads.some(w => w.driftLevel === 'High')) return 'High';
    if (enrichedWorkloads.some(w => w.driftLevel === 'Medium')) return 'Medium';
    return 'Low';
  }, [enrichedWorkloads]);

  const tabs = [
    { name: 'Workloads', icon: Server },
    { name: 'Live Activity', icon: Activity },
    { name: 'System Insights', icon: BarChart2 }
  ];

  const activeActionsCount = mappedActions.filter(a => a.type === 'RUNNING').length;
  const totalActionsCount = mappedActions.length;
  const isOptimizing = activeActionsCount > 0;
  
  return (
    <div className="min-h-screen bg-gray-50/50 text-gray-900 font-sans pb-20">
      <style dangerouslySetInnerHTML={{__html: `
        @keyframes slideIn {
          from { opacity: 0; transform: translateY(-8px) scale(0.99); }
          to { opacity: 1; transform: translateY(0) scale(1); }
        }
        .animate-slide-in {
          animation: slideIn 0.3s cubic-bezier(0.16, 1, 0.3, 1) forwards;
        }
        @keyframes pulseSubtle {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.75; }
        }
        .animate-pulse-subtle {
          animation: pulseSubtle 2.5s ease-in-out infinite;
        }
      `}} />

      <div className="max-w-[1400px] mx-auto p-6 md:p-8">
        
        {/* Breadcrumb Context */}
        <div className="flex items-center text-sm text-gray-500 mb-6">
          <span className="hover:text-gray-800 cursor-pointer transition-colors">Cluster: {clusterId || 'prod-us-east-1'}</span>
          <ChevronRight size={14} className="mx-2 text-gray-400" />
          <span className="font-medium text-gray-900">Workload Inventory</span>
        </div>

        {/* TOP CONTROLS */}
        <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4 mb-6">
          <div className="flex flex-wrap gap-2 w-full md:w-auto">
            <div className="relative">
              <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
              <input 
                type="text" 
                placeholder="Search workloads..." 
                className="pl-8 pr-4 py-1.5 bg-white border border-gray-200 rounded-md text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent w-full md:w-64 transition-all"
              />
            </div>
            <button className="flex items-center gap-1.5 px-3 py-1.5 bg-white border border-gray-200 rounded-md text-sm text-gray-600 shadow-sm hover:bg-gray-50 transition-colors">
              <SlidersHorizontal size={14} />
              Namespaces
            </button>
            <button className="flex items-center gap-1.5 px-3 py-1.5 bg-white border border-gray-200 rounded-md text-sm text-gray-600 shadow-sm hover:bg-gray-50 transition-colors">
              <Filter size={14} />
              Status
            </button>
          </div>

          <div className="flex items-center gap-2 bg-white px-3 py-1.5 border border-gray-200 rounded-md shadow-sm">
            <span className="text-sm text-gray-500">Optimization Mode:</span>
            <select className="text-sm font-semibold text-blue-600 bg-transparent border-none p-0 pr-6 focus:ring-0 cursor-pointer outline-none">
              <option value="active">Active</option>
              <option value="shadow">Shadow</option>
            </select>
          </div>
        </div>

        {/* OPTIMIZATION SUMMARY BAR */}
        <div className="bg-[#fcfcfc] border border-gray-200 rounded-lg shadow-sm mb-6 h-16 flex items-center">
          <div className="flex w-full divide-x divide-gray-200">
            
            <div className="flex-1 px-6 flex items-center justify-between">
              <span className="text-xs font-medium text-gray-500">Cluster Status</span>
              <div className="flex items-center gap-2">
                {isOptimizing && <div className="w-2.5 h-2.5 rounded-full bg-blue-500 animate-pulse-subtle"></div>}
                <span className="font-semibold text-gray-900">{isOptimizing ? 'Optimizing' : 'Stable'}</span>
              </div>
            </div>
            
            <div className="flex-1 px-6 flex items-center justify-between">
              <span className="text-xs font-medium text-gray-500">Savings</span>
              <div className="flex items-baseline gap-1.5">
                <span className="font-bold text-green-600 text-lg">{enrichedWorkloads.filter(w => w.status !== 'BLOCKED').length}</span>
                <span className="text-[11px] text-gray-400">workloads active</span>
              </div>
            </div>
            
            <div className="flex-1 px-6 flex items-center justify-between">
              <span className="text-xs font-medium text-gray-500">Active Actions</span>
              <div className="text-gray-900 font-medium text-[15px]">
                {activeActionsCount} <span className="text-gray-400 text-sm font-normal">/ {totalActionsCount} running</span>
              </div>
            </div>
            
            <div className="flex-1 px-6 flex items-center justify-between">
              <span className="text-xs font-medium text-gray-500">Drift Level</span>
              <span className={`text-xs font-medium px-2 py-0.5 rounded border ${
                overallDrift === 'High' ? 'bg-red-50 text-red-700 border-red-200' :
                overallDrift === 'Medium' ? 'bg-yellow-50 text-yellow-700 border-yellow-200' :
                overallDrift === 'Low' ? 'bg-green-50 text-green-700 border-green-200' :
                'bg-gray-50 text-gray-600 border-gray-200'
              }`}>
                {overallDrift}
              </span>
            </div>

          </div>
        </div>

        {/* TABS NAVIGATION */}
        <div className="border-b border-gray-200 mb-6 flex overflow-x-auto">
          {tabs.map((tab) => {
            const Icon = tab.icon;
            const isActive = activeTab === tab.name;
            return (
              <button
                key={tab.name}
                onClick={() => setActiveTab(tab.name)}
                className={`flex items-center gap-2 px-6 py-3 text-sm font-medium border-b-2 transition-colors whitespace-nowrap ${
                  isActive 
                    ? 'border-blue-600 text-blue-700' 
                    : 'border-transparent text-gray-500 hover:text-gray-800 hover:border-gray-300'
                }`}
              >
                <Icon size={16} className={isActive ? 'text-blue-600' : 'text-gray-400'} />
                {tab.name}
              </button>
            )
          })}
        </div>

        {/* TAB CONTENT AREAS */}
        <div className="transition-all duration-300 relative">
          {activeTab === 'Workloads' && (
            <div className="animate-slide-in">
              <WorkloadsTable workloads={enrichedWorkloads} loading={loading} />
            </div>
          )}
          
          {activeTab === 'Live Activity' && (
            <div className="animate-slide-in">
              <LiveActivityFeed agentActions={mappedActions} loading={loading} />
            </div>
          )}
          
          {activeTab === 'System Insights' && (
            <div className="animate-slide-in">
              <SystemInsights nodeClaims={nodeClaimsData} placementMetrics={placementMetrics} rolloutStatus={rolloutStatus} loading={loading} />
            </div>
          )}
        </div>

      </div>
    </div>
  );
}
