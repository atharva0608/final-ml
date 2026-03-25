/**
 * Cluster Details Component
 * Detailed view of cluster with metrics, nodes, and configuration
 */
import React, { useState, useEffect, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { clusterAPI, metricsAPI, policyAPI, hibernationAPI, decisionEngineAPI, karpenterAPI, nativeSpotAPI, ascpaiAPI, optimizationAPI } from '../../services/api';
import { Card, Button, Badge } from '../shared';
import { FiX, FiRefreshCw, FiSettings, FiClock, FiCpu, FiHardDrive, FiDollarSign, FiActivity, FiSliders } from 'react-icons/fi';
import toast from 'react-hot-toast';
import { formatCurrency, formatNumber, formatDate, formatDateTime } from '../../utils/formatters';

import NodeList from './NodeList';
import NodeGroupBreakdown from './NodeGroupBreakdown';
import ClusterHealthTimeline from './ClusterHealthTimeline';
import NodeTemplateTab from './NodeTemplateTab';
import PermissionGate from '../governance/PermissionGate';
import OverviewTab from './overview/OverviewTab';

const CONDITION_STYLES = {
  'REBALANCING': 'bg-indigo-50 text-indigo-700 border-indigo-200',
  'AWAITING_SPOT': 'bg-blue-50 text-blue-700 border-blue-200',
  'REBALANCE:RISK_HIGH': 'bg-red-50 text-red-700 border-red-200',
  'REBALANCE:BETTER_POOL': 'bg-amber-50 text-amber-700 border-amber-200',
  'STABLE': 'bg-green-50 text-green-700 border-green-200',
};

const NodeConditionBadge = ({ node, rec, isInFlight }) => {
  if (isInFlight) {
    return (
      <span className="px-2 py-0.5 text-xs rounded-full border bg-indigo-50 text-indigo-700 border-indigo-200 flex items-center gap-1 whitespace-nowrap">
        <span className="w-1.5 h-1.5 bg-indigo-500 rounded-full animate-pulse inline-block" />
        Rebalancing...
      </span>
    );
  }
  const cond = node.rebalance_condition || (node.lifecycle !== 'spot' ? 'AWAITING_SPOT' : 'STABLE');
  const style = CONDITION_STYLES[cond] || CONDITION_STYLES['STABLE'];
  const riskPct = node.current_risk_score != null
    ? ` · ${(node.current_risk_score * 100).toFixed(0)}%`
    : (rec?.risk_score != null ? ` · ${(rec.risk_score * 100).toFixed(0)}%` : '');
  const labels = {
    'AWAITING_SPOT': 'OD → Spot',
    'REBALANCE:RISK_HIGH': `⚠ Risk High${riskPct}`,
    'REBALANCE:BETTER_POOL': '↑ Better Pool',
    'STABLE': `Stable${riskPct}`,
  };
  const poolHint = node.best_available_pool || rec?.target_type || null;
  return (
    <div>
      <span className={`px-2 py-0.5 text-xs rounded-full border ${style} whitespace-nowrap`}>
        {labels[cond] || 'Stable'}
      </span>
      {poolHint && cond === 'REBALANCE:BETTER_POOL' && (
        <div className="text-[10px] text-gray-400 mt-0.5">{poolHint}</div>
      )}
    </div>
  );
};

const ClusterDetails = ({ clusterId, onClose }) => {
  const [cluster, setCluster] = useState(null);
  const [activeTab, setActiveTab] = useState('Overview');
  const [metrics, setMetrics] = useState(null);
  const [policy, setPolicy] = useState(null);
  const [schedule, setSchedule] = useState(null);
  const [classification, setClassification] = useState(null);
  const [substituteStatus, setSubstituteStatus] = useState(null);
  const [cooldownStatus, setCooldownStatus] = useState(null);
  const [executionStatus, setExecutionStatus] = useState(null);
  const [utilization, setUtilization] = useState(null);
  const [workloadType, setWorkloadType] = useState(null);
  const [nodesDetailed, setNodesDetailed] = useState(null);
  const [nodeRecommendations, setNodeRecommendations] = useState([]);
  const [rebalancingActions, setRebalancingActions] = useState([]);
  const [rightsizing, setRightsizing] = useState([]);
  const [costTrends, setCostTrends] = useState(null);
  const [expandedNodes, setExpandedNodes] = useState(new Set());
  const [optSettings, setOptSettings] = useState(null);
  const [savingOptSettings, setSavingOptSettings] = useState(false);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [optimizing, setOptimizing] = useState(false);
  const [modeUpdating, setModeUpdating] = useState(false);
  const [showDisconnectModal, setShowDisconnectModal] = useState(false);
  const [showRemoveModal, setShowRemoveModal] = useState(false);
  const [agentActionLoading, setAgentActionLoading] = useState(false);
  const [fallbackLoading, setFallbackLoading] = useState(false);
  const [karpenterInstallStatus, setKarpenterInstallStatus] = useState(null);
  const [karpenterActionLoading, setKarpenterActionLoading] = useState(false);
  const [nativeSpotStatus, setNativeSpotStatus] = useState(null);
  const [nativeSpotLoading, setNativeSpotLoading] = useState(false);
  const navigate = useNavigate();

  // Build per-node recommendation lookup (keyed by node_name)
  const recByNode = useMemo(() => {
    const m = {};
    nodeRecommendations.forEach(r => { if (r.node_name) m[r.node_name] = r; });
    return m;
  }, [nodeRecommendations]);

  // Build set of instance IDs currently in-flight (rebalancing in progress)
  const inFlightNodeIds = useMemo(() => {
    const s = new Set();
    rebalancingActions
      .filter(a => ['in_progress', 'waiting_agent'].includes(a.status))
      .forEach(a => {
        const iid = a.instance_id || a.action_metadata?.instance_id;
        if (iid) s.add(iid);
      });
    return s;
  }, [rebalancingActions]);

  useEffect(() => {
    if (clusterId) {
      fetchClusterDetails();
    }
  }, [clusterId]);

  // Lightweight 30s poll: refresh live node state + rebalancing status without
  // reloading all cluster metadata (avoids UI flicker from full fetchClusterDetails).
  useEffect(() => {
    if (!clusterId) return;
    const pollNodeData = async () => {
      try {
        const [nodesRes, rebalRes, recRes] = await Promise.allSettled([
          clusterAPI.getNodesDetailed(clusterId),
          ascpaiAPI.getRebalancingStatus(clusterId),
          ascpaiAPI.getNodeRecommendations(clusterId),
        ]);
        if (nodesRes.status === 'fulfilled') setNodesDetailed(nodesRes.value.data);
        if (rebalRes.status === 'fulfilled')
          setRebalancingActions(Array.isArray(rebalRes.value.data) ? rebalRes.value.data : []);
        if (recRes.status === 'fulfilled')
          setNodeRecommendations(recRes.value.data?.recommendations || []);
      } catch (_) {
        // silent — polling failures don't need user notification
      }
    };
    const _pollTimer = setInterval(pollNodeData, 30_000);
    return () => clearInterval(_pollTimer);
  }, [clusterId]);

  const fetchClusterDetails = async () => {
    // Only set loading=true if we have no cluster data yet (avoids blanking the UI on refresh)
    if (!cluster) setLoading(true);
    try {
      // Fetch cluster data, metrics, policy, schedule, utilization, workload type, and detailed nodes in parallel
      const [clusterRes, metricsRes, policyRes, scheduleRes, utilRes, workloadRes, nodesRes, optRes, recRes, rebalRes, rsizeRes, costTRes] = await Promise.allSettled([
        clusterAPI.getCluster(clusterId),
        metricsAPI.getClusterMetrics(clusterId),
        policyAPI.getPolicy(clusterId),
        hibernationAPI.getByCluster(clusterId),
        clusterAPI.getUtilization(clusterId),
        clusterAPI.getWorkloadType(clusterId),
        clusterAPI.getNodesDetailed(clusterId),
        clusterAPI.getOptimizationSettings(clusterId),
        ascpaiAPI.getNodeRecommendations(clusterId),
        ascpaiAPI.getRebalancingStatus(clusterId),
        optimizationAPI.getRightsizing(clusterId),
        metricsAPI.getCostTimeSeries({ cluster_id: clusterId }),
      ]);

      if (clusterRes.status === 'fulfilled') setCluster(clusterRes.value.data);
      if (metricsRes.status === 'fulfilled') setMetrics(metricsRes.value.data);
      if (policyRes.status === 'fulfilled') setPolicy(policyRes.value.data);
      if (scheduleRes.status === 'fulfilled') setSchedule(scheduleRes.value.data);
      if (utilRes.status === 'fulfilled') setUtilization(utilRes.value.data);
      if (workloadRes.status === 'fulfilled') setWorkloadType(workloadRes.value.data);
      if (nodesRes.status === 'fulfilled') setNodesDetailed(nodesRes.value.data);
      if (recRes.status === 'fulfilled') setNodeRecommendations(recRes.value.data?.recommendations || []);
      if (rebalRes.status === 'fulfilled') setRebalancingActions(Array.isArray(rebalRes.value.data) ? rebalRes.value.data : []);
      if (rsizeRes.status === 'fulfilled') setRightsizing(rsizeRes.value.data?.recommendations || rsizeRes.value.data || []);
      if (costTRes.status === 'fulfilled') setCostTrends(costTRes.value.data);
      if (optRes.status === 'fulfilled') {
        const c = optRes.value.data || {
          optimization_strategy: { strategy_type: 'BALANCED', risk_ceiling_percent: 25, min_savings_percent: 15, risk_savings_tradeoff_pct: 20 }
        };
        setOptSettings(c);
      }

      // Fetch Karpenter install status separately (non-critical)
      try {
        const karpenterRes = await karpenterAPI.getInstallStatus(clusterId);
        setKarpenterInstallStatus(karpenterRes.data);
        // For non-Karpenter clusters: fetch native ASG spot status
        if (!karpenterRes.data?.karpenter_installed) {
          nativeSpotAPI.getStatus(clusterId)
            .then(r => setNativeSpotStatus(r.data))
            .catch(() => { });
        }
      } catch (_) {
        // Not critical — ignore
      }
    } catch (error) {
      toast.error('Failed to load cluster details');
    } finally {
      setLoading(false);
    }
  };

  const handleRefresh = async () => {
    setRefreshing(true);
    await fetchClusterDetails();
    setRefreshing(false);
    toast.success('Cluster details refreshed');
  };

  const handleOptimize = async () => {
    if (!clusterId) return;
    setOptimizing(true);
    try {
      await clusterAPI.optimize(clusterId); // Assuming this API endpoint exists or will exist
      toast.success('Optimization triggered successfully');
    } catch (error) {
      toast.error('Failed to trigger optimization');
    } finally {
      setOptimizing(false);
    }
  };

  const handleModeChange = async (e) => {
    const newMode = e.target.value;
    setModeUpdating(true);
    try {
      await decisionEngineAPI.updateOptimizationMode(clusterId, newMode);
      setCluster({ ...cluster, optimization_mode: newMode });
      toast.success(`Mode updated to ${newMode}`);
    } catch (err) {
      toast.error('Failed to update optimization mode');
    } finally {
      setModeUpdating(false);
    }
  };

  const handleFallback = async () => {
    setFallbackLoading(true);
    try {
      await clusterAPI.fallback(clusterId);
      toast.success('Cluster switched to On-Demand fallback for 12 hours');
      fetchClusterDetails();
    } catch (err) {
      toast.error('Failed to trigger manual fallback');
    } finally {
      setFallbackLoading(false);
    }
  };

  const handleDisconnectAgent = async () => {
    setAgentActionLoading(true);
    try {
      await clusterAPI.disconnectAgent(clusterId);
      toast.success('Agent disconnected. Historical data preserved.');
      setShowDisconnectModal(false);
      fetchClusterDetails();
    } catch (err) {
      toast.error('Failed to disconnect agent');
    } finally {
      setAgentActionLoading(false);
    }
  };

  const handleRemoveAgent = async () => {
    setAgentActionLoading(true);
    try {
      const res = await clusterAPI.removeAgent(clusterId);
      toast.success(`Agent removed. Deleted ${res.data.pod_metrics_deleted} metrics records.`);
      setShowRemoveModal(false);
      fetchClusterDetails();
    } catch (err) {
      toast.error('Failed to remove agent');
    } finally {
      setAgentActionLoading(false);
    }
  };

  const handleSaveOptSettings = async () => {
    if (!clusterId || !optSettings) return;
    setSavingOptSettings(true);
    try {
      await clusterAPI.updateOptimizationSettings(clusterId, optSettings);
      toast.success("Optimization settings saved successfully!");
    } catch (err) {
      toast.error("Failed to save optimization settings");
    } finally {
      setSavingOptSettings(false);
    }
  };

  const handleOptConfigChange = (section, key, value) => {
    setOptSettings(prev => ({
      ...prev,
      [section]: {
        ...prev[section],
        [key]: value
      }
    }));
  };

  const getStatusColor = (status) => {
    switch (status) {
      case 'active':
        return 'green';
      case 'discovered':
        return 'blue';
      case 'inactive':
        return 'gray';
      case 'error':
        return 'red';
      default:
        return 'gray';
    }
  };

  if (!clusterId) return null;

  // Only blank the screen on TRUE initial load (no cluster data yet).
  // Subsequent refreshes keep showing stale data while fetching silently.
  if (loading && !cluster) {
    return (
      <div className="flex-1 flex items-center justify-center bg-white">
        <div className="flex flex-col items-center gap-3">
          <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-blue-600"></div>
          <span className="text-sm text-gray-500">Loading cluster details…</span>
        </div>
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-y-auto bg-white flex flex-col">
      <div className="w-full">
        {/* Header */}
        <header className="sticky top-0 bg-white border-b border-gray-200 px-8 py-4 flex items-center justify-between z-20">
          <div className="flex items-center space-x-4">
            <h1 className="text-[17px] font-bold text-[#111318] tracking-tight m-0">{cluster?.name || 'Loading...'}</h1>
            
            <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${
              cluster?.status?.toLowerCase() === 'active' 
                ? 'bg-green-100 text-green-800' 
                : 'bg-orange-100 text-orange-800'
            }`}>
              <span className={`w-2 h-2 mr-1.5 rounded-full ${
                cluster?.status?.toLowerCase() === 'active' 
                  ? 'bg-green-500' 
                  : 'bg-orange-500'
              }`}></span>
              {cluster?.status || 'Unknown'}
            </span>
            
            <div className="flex space-x-1 ml-4 hidden sm:flex">
              <span className="px-2 py-0.5 bg-gray-100 text-gray-600 rounded text-[10px] font-medium border border-gray-200 uppercase">
                {cluster?.provider || 'AWS'}
              </span>
              <span className="px-2 py-0.5 bg-gray-100 text-gray-600 rounded text-[10px] font-medium border border-gray-200 uppercase">
                {cluster?.region || 'Unknown'}
              </span>
              <span className="px-2 py-0.5 bg-gray-100 text-gray-600 rounded text-[10px] font-medium border border-gray-200 uppercase">
                {cluster?.k8s_version ? `K8S ${cluster.k8s_version}` : 'K8S 1.28'}
              </span>
            </div>
          </div>
          
          <div className="flex items-center space-x-3">
            <button 
              className="px-4 py-2 border border-blue-600 text-blue-600 rounded-md text-sm font-medium hover:bg-blue-50 transition-colors"
              onClick={handleOptimize}
              disabled={optimizing}
            >
              {optimizing ? 'Updating...' : 'Update Agent'}
            </button>
            <button 
              className="px-4 py-2 border border-gray-300 text-gray-700 rounded-md text-sm font-medium hover:bg-gray-50 flex items-center gap-1.5 transition-colors"
              onClick={handleRefresh}
              disabled={refreshing}
            >
              <FiRefreshCw className={refreshing ? 'animate-spin' : ''} />
              Refresh
            </button>
            <button 
              className="px-4 py-2 border border-red-200 text-red-600 rounded-md text-sm font-medium hover:bg-red-50 transition-colors"
              onClick={() => setShowRemoveModal(true)}
            >
              Remove
            </button>
          </div>
        </header>

        {/* Tabs Navigation */}
        <div className="bg-white border-b border-gray-200 px-8 sticky top-[69px] z-10">
          <nav aria-label="Tabs" className="flex space-x-8">
            {['Overview', 'Optimization Settings', 'Node Template', 'Activity Log'].map(tab => (
              <button
                key={tab}
                onClick={() => setActiveTab(tab)}
                className={`whitespace-nowrap py-4 px-1 border-b-2 font-medium text-sm transition-colors ${
                  activeTab === tab
                    ? 'border-blue-600 text-blue-600'
                    : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                }`}
              >
                {tab}
              </button>
            ))}
          </nav>
        </div>

        <div className="p-6 space-y-6">
          {activeTab === 'Overview' && (
            <OverviewTab
              cluster={cluster}
              metrics={metrics}
              utilization={utilization}
              karpenterInstallStatus={karpenterInstallStatus}
              schedule={schedule}
              policy={policy}
              nodeRecommendations={nodeRecommendations}
              nodesDetailed={nodesDetailed}
              costTrends={costTrends}
              rightsizing={rightsizing}
              onInstallKarpenter={() => {
                toast.loading(`Installing Karpenter on ${cluster?.name}...`, { id: 'karp-install' });
                karpenterAPI.installKarpenter(clusterId).then(() => { // Changed to installKarpenter
                  toast.success('Karpenter installation triggered', { id: 'karp-install' });
                  fetchClusterDetails();
                }).catch(e => toast.error('Failed to install Karpenter', { id: 'karp-install' }));
              }}
              onManagePolicies={() => setActiveTab('Optimization Settings')}
            />
          )}

          {activeTab === 'Optimization Settings' && (
            <div className="space-y-5">
              {/* ── Status Banner ── */}
              {optSettings && (
                <div className={`flex items-center gap-3 px-4 py-3 rounded-lg border ${optSettings.automation_controls?.auto_rebalance_enabled
                    ? 'bg-green-50 border-green-200 text-green-800'
                    : 'bg-gray-100 border-gray-300 text-gray-500'
                  }`}>
                  <span className={`w-2.5 h-2.5 rounded-full shrink-0 ${optSettings.automation_controls?.auto_rebalance_enabled
                      ? 'bg-green-500 animate-pulse'
                      : 'bg-gray-400'
                    }`} />
                  <span className="font-semibold text-sm">
                    {optSettings.automation_controls?.auto_rebalance_enabled ? 'ENABLED' : 'DISABLED'}
                  </span>
                  <span className="text-sm">
                    {optSettings.automation_controls?.auto_rebalance_enabled
                      ? 'Auto-rebalancer is active — ML engine monitors and moves nodes to optimal spot pools'
                      : 'All automation paused — manual mode only'}
                  </span>
                </div>
              )}

              {/* ── Automation Controls ── */}
              <Card>
                {/* Header + mode badge */}
                <div className="flex items-center justify-between mb-3">
                  <h3 className="text-sm font-semibold text-gray-900 flex items-center gap-1.5">
                    <FiSettings className="w-3.5 h-3.5 text-blue-600" />
                    Optimization Engine Settings
                  </h3>
                  {optSettings && (
                    <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full tracking-wide ${
                      optSettings.automation_controls?.auto_rebalance_enabled
                        ? 'bg-green-100 text-green-700'
                        : 'bg-gray-100 text-gray-500'
                    }`}>
                      {optSettings.automation_controls?.auto_rebalance_enabled
                        ? (optSettings.automation_controls?.auto_rightsizing_enabled ? 'FULL AUTO' : 'REBALANCE ACTIVE')
                        : 'DISABLED'}
                    </span>
                  )}
                </div>

                <div className="space-y-0 divide-y divide-gray-100">
                  {/* Auto Rebalance */}
                  <div className="flex items-center justify-between py-2.5">
                    <div>
                      <div className="text-xs font-semibold text-gray-800">Auto Rebalance <span className="text-[10px] font-normal text-blue-600">(ML Spot Optimization)</span></div>
                      <div className="text-[11px] text-gray-500 mt-0.5">Automatically replace on-demand nodes with ML-predicted stable spot instances</div>
                    </div>
                    <label className="relative inline-flex items-center cursor-pointer ml-4 shrink-0">
                      <input type="checkbox" className="sr-only peer"
                        checked={!!optSettings?.automation_controls?.auto_rebalance_enabled}
                        onChange={e => handleOptConfigChange("automation_controls", "auto_rebalance_enabled", e.target.checked)} />
                      <div className="w-9 h-5 bg-gray-200 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-blue-600" />
                    </label>
                  </div>

                  {/* Sub-settings — shown when Auto Rebalance is ON */}
                  {optSettings?.automation_controls?.auto_rebalance_enabled && (
                    <div className="ml-4 pl-3 border-l-2 border-gray-100 py-2 space-y-2.5">
                      {/* Diversify Pools */}
                      <div className="flex items-center justify-between">
                        <div>
                          <div className="text-[12px] font-medium text-gray-700">Diversify Spot Pools</div>
                          <div className="text-[10px] text-gray-400 mt-0.5">Spread across multiple instance pools to lower interruption risk</div>
                        </div>
                        <label className="relative inline-flex items-center cursor-pointer ml-4 shrink-0">
                          <input type="checkbox" className="sr-only peer"
                            checked={!!optSettings?.automation_controls?.diversify_pools}
                            onChange={e => handleOptConfigChange("automation_controls", "diversify_pools", e.target.checked)} />
                          <div className="w-9 h-5 bg-gray-200 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-indigo-600" />
                        </label>
                      </div>
                      {/* Maintain Standby */}
                      <div className="flex items-center justify-between">
                        <div>
                          <div className="text-[12px] font-medium text-gray-700">Maintain Warm Standby</div>
                          <div className="text-[10px] text-gray-400 mt-0.5">Keep 1 pre-warmed spot node for instant failover</div>
                        </div>
                        <label className="relative inline-flex items-center cursor-pointer ml-4 shrink-0">
                          <input type="checkbox" className="sr-only peer"
                            checked={!!optSettings?.automation_controls?.maintain_standby}
                            onChange={e => handleOptConfigChange("automation_controls", "maintain_standby", e.target.checked)} />
                          <div className="w-9 h-5 bg-gray-200 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-teal-600" />
                        </label>
                      </div>
                      {/* Failure Cooldown + Post-Rebalance Cooldown */}
                      <div className="grid grid-cols-2 gap-3">
                        <div>
                          <div className="text-[11px] font-medium text-gray-700 mb-1">Failure Cooldown</div>
                          <div className="flex items-center gap-1.5">
                            <input type="number"
                              value={optSettings?.automation_controls?.failure_cooldown_minutes ?? 30}
                              onChange={e => handleOptConfigChange("automation_controls", "failure_cooldown_minutes", parseInt(e.target.value) || 30)}
                              className="w-14 text-xs border border-gray-200 rounded px-2 py-1 text-gray-700 focus:outline-none focus:ring-1 focus:ring-blue-400" />
                            <span className="text-[10px] text-gray-400">min</span>
                          </div>
                        </div>
                        <div>
                          <div className="text-[11px] font-medium text-gray-700 mb-1">Post-Rebalance Cooldown</div>
                          <div className="flex items-center gap-1.5">
                            <input type="number"
                              value={optSettings?.automation_controls?.cooldown_override_minutes ?? 60}
                              onChange={e => handleOptConfigChange("automation_controls", "cooldown_override_minutes", parseInt(e.target.value) || 60)}
                              className="w-14 text-xs border border-gray-200 rounded px-2 py-1 text-gray-700 focus:outline-none focus:ring-1 focus:ring-blue-400" />
                            <span className="text-[10px] text-gray-400">min</span>
                          </div>
                        </div>
                      </div>
                    </div>
                  )}

                  {/* Check Cycle Interval */}
                  <div className="flex items-center justify-between py-2.5">
                    <div>
                      <div className="text-xs font-semibold text-gray-800">Check Cycle Interval</div>
                      <div className="text-[11px] text-gray-500 mt-0.5">How often the rebalancer evaluates nodes (min 15s)</div>
                    </div>
                    <div className="flex items-center gap-1.5 ml-4 shrink-0">
                      <input type="number" min="15" step="15"
                        value={optSettings?.automation_controls?.check_interval_seconds ?? 15}
                        onChange={e => handleOptConfigChange("automation_controls", "check_interval_seconds", Math.max(15, parseInt(e.target.value) || 15))}
                        className="w-14 text-xs border border-gray-200 rounded px-2 py-1 text-gray-700 focus:outline-none focus:ring-1 focus:ring-blue-400" />
                      <span className="text-[10px] text-gray-400">sec</span>
                    </div>
                  </div>

                  {/* Auto Right-Sizing */}
                  <div className="flex items-center justify-between py-2.5">
                    <div>
                      <div className="text-xs font-semibold text-gray-800">Auto Right-Sizing</div>
                      <div className="text-[11px] text-gray-500 mt-0.5">Automatically scale down over-provisioned pods based on historical metrics</div>
                    </div>
                    <label className="relative inline-flex items-center cursor-pointer ml-4 shrink-0">
                      <input type="checkbox" className="sr-only peer"
                        checked={!!optSettings?.automation_controls?.auto_rightsizing_enabled}
                        onChange={e => handleOptConfigChange("automation_controls", "auto_rightsizing_enabled", e.target.checked)} />
                      <div className="w-9 h-5 bg-gray-200 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-blue-600" />
                    </label>
                  </div>

                  {/* Optimization Target */}
                  {(() => {
                    const _synLocked = !!optSettings?.automation_controls?.auto_rebalance_enabled && !!optSettings?.automation_controls?.auto_rightsizing_enabled;
                    return (
                      <div className="flex items-center justify-between py-2.5">
                        <div>
                          <div className="text-xs font-semibold text-gray-800">Optimization Target</div>
                          <div className="text-[11px] text-gray-500 mt-0.5">
                            {_synLocked ? 'Locked to Spot — synergy mode active' : 'Billing model for right-sized node replacements'}
                          </div>
                        </div>
                        <div className="flex items-center gap-2 ml-4 shrink-0">
                          {_synLocked && <span className="text-[10px] text-amber-700 bg-amber-50 border border-amber-200 rounded px-1.5 py-0.5">Locked</span>}
                          <select
                            className={`text-xs border rounded px-2 py-1 focus:outline-none ${_synLocked ? 'bg-gray-100 border-gray-200 text-gray-400 cursor-not-allowed' : 'bg-white border-gray-300 text-gray-700'}`}
                            value={_synLocked ? 'spot' : (optSettings?.automation_controls?.optimization_target ?? 'spot')}
                            onChange={e => !_synLocked && handleOptConfigChange("automation_controls", "optimization_target", e.target.value)}
                            disabled={_synLocked}
                          >
                            <option value="spot">Spot</option>
                            <option value="on_demand">On-Demand</option>
                          </select>
                        </div>
                      </div>
                    );
                  })()}

                  {/* Conservative Mode */}
                  <div className="flex items-center justify-between py-2.5">
                    <div>
                      <div className="text-xs font-semibold text-gray-800">Conservative Mode <span className="text-[10px] font-normal text-green-600">(Fresh Cluster Protection)</span></div>
                      <div className="text-[11px] text-gray-500 mt-0.5">Limit aggressive spot replacements during the first 24 hours</div>
                    </div>
                    <label className="relative inline-flex items-center cursor-pointer ml-4 shrink-0">
                      <input type="checkbox" className="sr-only peer"
                        checked={optSettings?.automation_controls?.conservative_mode_enabled ?? true}
                        onChange={e => handleOptConfigChange("automation_controls", "conservative_mode_enabled", e.target.checked)} />
                      <div className="w-9 h-5 bg-gray-200 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-green-600" />
                    </label>
                  </div>

                  {/* Manual Approval */}
                  <div className="flex items-center justify-between py-2.5">
                    <div>
                      <div className="text-xs font-semibold text-gray-800">Manual Approval Required <span className="text-[10px] font-normal text-gray-400">(RBAC)</span></div>
                      <div className="text-[11px] text-gray-500 mt-0.5">Route proposed changes to Team Lead / Org Admin before execution</div>
                    </div>
                    <label className="relative inline-flex items-center cursor-pointer ml-4 shrink-0">
                      <input type="checkbox" className="sr-only peer"
                        checked={!!optSettings?.automation_controls?.manual_approval_required}
                        onChange={e => handleOptConfigChange("automation_controls", "manual_approval_required", e.target.checked)} />
                      <div className="w-9 h-5 bg-gray-200 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-gray-800" />
                    </label>
                  </div>
                </div>
              </Card>

              {/* ── Risk vs Savings Controls ── */}
              <Card>
                <h3 className="text-base font-semibold text-gray-900 flex items-center gap-2 mb-1">
                  <FiSliders className="w-4 h-4 text-indigo-600" />
                  Risk vs Savings Controls
                </h3>
                <p className="text-sm text-gray-500 mb-5">Controls how the ML engine selects target spot pools.</p>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
                  {/* Risk/Savings Tradeoff */}
                  <div className="p-4 bg-gradient-to-br from-blue-50 to-indigo-50 rounded-xl border border-blue-200">
                    <div className="flex justify-between items-center mb-2">
                      <label className="text-sm font-semibold text-gray-900">Risk/Savings Tradeoff</label>
                      <span className="text-xl font-bold text-blue-700">
                        {optSettings?.optimization_strategy?.risk_savings_tradeoff_pct ?? 20}%
                      </span>
                    </div>
                    <input
                      type="range"
                      min="0"
                      max="50"
                      step="5"
                      value={optSettings?.optimization_strategy?.risk_savings_tradeoff_pct ?? 20}
                      onChange={e => handleOptConfigChange("optimization_strategy", "risk_savings_tradeoff_pct", +e.target.value)}
                      className="w-full h-2 bg-blue-200 rounded-lg appearance-none cursor-pointer accent-blue-600"
                    />
                    <p className="text-xs text-gray-500 mt-2">
                      Sacrifice up to <strong>{optSettings?.optimization_strategy?.risk_savings_tradeoff_pct ?? 20}%</strong> of potential Spot savings if a safer pool is available. <span className="text-blue-600">0% = cheapest only.</span>
                    </p>
                  </div>

                  {/* Maximum Risk Ceiling */}
                  <div className="p-4 bg-gradient-to-br from-amber-50 to-orange-50 rounded-xl border border-amber-200">
                    <div className="flex justify-between items-center mb-2">
                      <label className="text-sm font-semibold text-gray-900">Maximum Risk Ceiling</label>
                      <span className="text-xl font-bold text-amber-700">
                        {optSettings?.optimization_strategy?.risk_ceiling_percent ?? 25}%
                      </span>
                    </div>
                    <input
                      type="range"
                      min="5"
                      max="80"
                      step="5"
                      value={optSettings?.optimization_strategy?.risk_ceiling_percent ?? 25}
                      onChange={e => handleOptConfigChange("optimization_strategy", "risk_ceiling_percent", +e.target.value)}
                      className="w-full h-2 bg-amber-200 rounded-lg appearance-none cursor-pointer accent-amber-500"
                    />
                    <p className="text-xs text-gray-500 mt-2">
                      Reject any pool with risk score above <strong>{optSettings?.optimization_strategy?.risk_ceiling_percent ?? 25}%</strong>. <span className="text-amber-600">Lower = safer but fewer candidates.</span>
                    </p>
                  </div>
                </div>

                <div className="mt-5 flex justify-end">
                  <Button
                    variant="primary"
                    onClick={handleSaveOptSettings}
                    loading={savingOptSettings}
                    disabled={savingOptSettings}
                  >
                    Save All Settings
                  </Button>
                </div>
              </Card>
            </div>
          )}

          {activeTab === 'Node Template' && (
            <NodeTemplateTab clusterId={clusterId} />
          )}

          {activeTab === 'Activity Log' && (
            <Card className="p-4">
              <h3 className="text-sm font-semibold text-gray-700 mb-3">Recent Rebalancing Actions</h3>
              {rebalancingActions.length === 0 ? (
                <p className="text-sm text-gray-400 text-center py-8">No rebalancing activity recorded for this cluster.</p>
              ) : (
                <div className="space-y-2">
                  {rebalancingActions.map((action, idx) => (
                    <div key={action.id || idx} className="flex items-start gap-3 p-3 rounded-lg bg-gray-50 border border-gray-100">
                      <span className={`mt-0.5 w-2 h-2 rounded-full flex-shrink-0 ${
                        action.status === 'completed' ? 'bg-green-500' :
                        action.status === 'failed' ? 'bg-red-500' :
                        action.status === 'in_progress' ? 'bg-blue-500' :
                        'bg-gray-400'
                      }`} />
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center justify-between gap-2">
                          <span className="text-xs font-medium text-gray-800 truncate">
                            {action.source_instance_type || action.source_node_name || 'Node'} →{' '}
                            {action.target_instance_type || 'spot'}
                          </span>
                          <span className="text-xs text-gray-400 whitespace-nowrap">
                            {action.created_at ? formatDateTime(action.created_at) : ''}
                          </span>
                        </div>
                        <div className="text-xs text-gray-500 mt-0.5">
                          Status: <span className="capitalize">{action.status}</span>
                          {action.savings_pct != null && (
                            <span className="ml-2 text-green-600">· {(action.savings_pct * 100).toFixed(0)}% savings</span>
                          )}
                          {action.failure_reason && (
                            <span className="ml-2 text-red-500">· {action.failure_reason}</span>
                          )}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </Card>
          )}
        </div>

        {/* Footer Actions */}
        <div className="sticky bottom-0 bg-gray-50 border-t px-6 py-4 flex justify-end gap-2">
          <Button variant="secondary" onClick={onClose}>
            Close
          </Button>
        </div>
      </div>

      {/* Disconnect Agent Confirmation Modal */}
      {showDisconnectModal && (
        <div className="fixed inset-0 bg-black bg-opacity-60 flex items-center justify-center z-[60]">
          <div className="bg-white rounded-xl p-6 max-w-md w-full mx-4 shadow-xl">
            <h3 className="text-lg font-bold text-gray-900 mb-2">Disconnect Agent?</h3>
            <p className="text-sm text-gray-600 mb-4">
              The agent DaemonSet on <strong>{cluster?.name}</strong> will stop sending metrics to the backend.
              All existing historical data is preserved. You can reconnect by reinstalling the agent
              with the new API key.
            </p>
            <div className="flex gap-3 justify-end">
              <button
                onClick={() => setShowDisconnectModal(false)}
                className="px-4 py-2 text-sm border border-gray-300 rounded hover:bg-gray-50"
              >
                Cancel
              </button>
              <button
                onClick={handleDisconnectAgent}
                disabled={agentActionLoading}
                className="px-4 py-2 text-sm bg-yellow-500 text-white rounded hover:bg-yellow-600 disabled:opacity-50"
              >
                {agentActionLoading ? 'Disconnecting...' : 'Disconnect Agent'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Remove Agent Confirmation Modal */}
      {showRemoveModal && (
        <div className="fixed inset-0 bg-black bg-opacity-60 flex items-center justify-center z-[60]">
          <div className="bg-white rounded-xl p-6 max-w-md w-full mx-4 shadow-xl">
            <h3 className="text-lg font-bold text-red-700 mb-2">Remove Agent & Delete All Data?</h3>
            <p className="text-sm text-gray-600 mb-3">
              This will permanently delete from <strong>{cluster?.name}</strong>:
            </p>
            <ul className="text-sm text-gray-600 mb-4 space-y-1 list-disc list-inside bg-red-50 p-3 rounded">
              <li>All pod metrics (CPU/memory history)</li>
              <li>All instance records</li>
              <li>Agent connection credentials</li>
              <li>Cluster reset to initial (discovered) state</li>
            </ul>
            <p className="text-sm font-semibold text-red-600 mb-4">This action cannot be undone.</p>
            <div className="flex gap-3 justify-end">
              <button
                onClick={() => setShowRemoveModal(false)}
                className="px-4 py-2 text-sm border border-gray-300 rounded hover:bg-gray-50"
              >
                Cancel
              </button>
              <button
                onClick={handleRemoveAgent}
                disabled={agentActionLoading}
                className="px-4 py-2 text-sm bg-red-600 text-white rounded hover:bg-red-700 disabled:opacity-50"
              >
                {agentActionLoading ? 'Removing...' : 'Remove Agent & Data'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default ClusterDetails;
