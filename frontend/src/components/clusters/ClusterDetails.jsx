/**
 * Cluster Details Component
 * Detailed view of cluster with metrics, nodes, and configuration
 */
import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { clusterAPI, metricsAPI, policyAPI, hibernationAPI, decisionEngineAPI } from '../../services/api';
import { Card, Button, Badge } from '../shared';
import { FiX, FiRefreshCw, FiSettings, FiClock, FiCpu, FiHardDrive, FiDollarSign, FiActivity } from 'react-icons/fi';
import toast from 'react-hot-toast';
import { formatCurrency, formatNumber, formatDate, formatDateTime } from '../../utils/formatters';

import NodeList from './NodeList';
import NodeGroupBreakdown from './NodeGroupBreakdown';
import ClusterHealthTimeline from './ClusterHealthTimeline';
import NodeTemplateTab from './NodeTemplateTab';
import PermissionGate from '../governance/PermissionGate';

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
  const [expandedNodes, setExpandedNodes] = useState(new Set());
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [optimizing, setOptimizing] = useState(false);
  const [modeUpdating, setModeUpdating] = useState(false);
  const [showDisconnectModal, setShowDisconnectModal] = useState(false);
  const [showRemoveModal, setShowRemoveModal] = useState(false);
  const [agentActionLoading, setAgentActionLoading] = useState(false);
  const [fallbackLoading, setFallbackLoading] = useState(false);
  const navigate = useNavigate();

  useEffect(() => {
    if (clusterId) {
      fetchClusterDetails();
    }
  }, [clusterId]);

  const fetchClusterDetails = async () => {
    setLoading(true);
    try {
      // Fetch cluster data, metrics, policy, schedule, utilization, workload type, and detailed nodes in parallel
      const [clusterRes, metricsRes, policyRes, scheduleRes, classRes, subRes, coolRes, execRes, utilRes, workloadRes, nodesRes] = await Promise.allSettled([
        clusterAPI.getCluster(clusterId),
        metricsAPI.getClusterMetrics(clusterId),
        policyAPI.getPolicy(clusterId),
        hibernationAPI.getSchedule(clusterId),
        decisionEngineAPI.getClassification(clusterId),
        decisionEngineAPI.getSubstituteStatus(clusterId),
        decisionEngineAPI.getCooldownStatus(clusterId),
        decisionEngineAPI.getExecutionStatus(clusterId),
        clusterAPI.getUtilization(clusterId),
        clusterAPI.getWorkloadType(clusterId),
        clusterAPI.getNodesDetailed(clusterId),
      ]);

      if (clusterRes.status === 'fulfilled') setCluster(clusterRes.value.data);
      if (metricsRes.status === 'fulfilled') setMetrics(metricsRes.value.data);
      if (policyRes.status === 'fulfilled') setPolicy(policyRes.value.data);
      if (scheduleRes.status === 'fulfilled') setSchedule(scheduleRes.value.data);
      if (classRes.status === 'fulfilled') setClassification(classRes.value.data);
      if (subRes.status === 'fulfilled') setSubstituteStatus(subRes.value.data);
      if (coolRes.status === 'fulfilled') setCooldownStatus(coolRes.value.data);
      if (execRes.status === 'fulfilled') setExecutionStatus(execRes.value.data);
      if (utilRes.status === 'fulfilled') setUtilization(utilRes.value.data);
      if (workloadRes.status === 'fulfilled') setWorkloadType(workloadRes.value.data);
      if (nodesRes.status === 'fulfilled') setNodesDetailed(nodesRes.value.data);
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

  if (loading) {
    return (
      <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
        <div className="bg-white rounded-lg p-8">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
        </div>
      </div>
    );
  }

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-lg w-full max-w-4xl max-h-[90vh] overflow-y-auto">
        {/* Header */}
        <div className="sticky top-0 bg-white border-b px-6 py-4 flex justify-between items-center z-10">
          <div>
            <h2 className="text-2xl font-bold text-gray-900">{cluster?.name}</h2>
            <p className="text-sm text-gray-600 mt-1">
              {cluster?.region} • {cluster?.provider || 'AWS'}
            </p>
          </div>
          <div className="flex items-center gap-2">
            <Button
              variant="primary"
              size="sm"
              onClick={handleOptimize}
              loading={optimizing}
              disabled={optimizing}
            >
              Instant Rebalance
            </Button>
            <Button
              variant="outline"
              size="sm"
              icon={<FiRefreshCw className={refreshing ? 'animate-spin' : ''} />}
              onClick={handleRefresh}
              disabled={refreshing}
            >
              Refresh
            </Button>
            <button
              onClick={onClose}
              className="p-2 hover:bg-gray-100 rounded-lg transition-colors"
            >
              <FiX className="w-5 h-5 text-gray-500" />
            </button>
          </div>
        </div>

        {/* Tabs Navigation */}
        <div className="flex border-b border-gray-200 px-6 pt-2 bg-gray-50 sticky top-[73px] z-10">
          {['Overview', 'Optimization Settings', 'Node Template', 'Activity Log'].map(tab => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={`px-4 py-3 font-medium text-sm border-b-2 transition-colors -mb-[1px] ${activeTab === tab
                ? 'border-blue-600 text-blue-600'
                : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                }`}
            >
              {tab}
            </button>
          ))}
        </div>

        <div className="p-6 space-y-6">
          {activeTab === 'Overview' && (
            <>
              {/* Status Overview */}
              <Card>
                <h3 className="text-lg font-semibold text-gray-900 mb-4">Status Overview</h3>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                  <div>
                    <div className="text-sm text-gray-600 mb-1">Status</div>
                    <Badge color={getStatusColor(cluster?.status)} size="lg">
                      {cluster?.status || 'Unknown'}
                    </Badge>
                  </div>
                  <div>
                    <div className="text-sm text-gray-600 mb-1">Cluster ID</div>
                    <div className="text-sm font-mono text-gray-900 truncate" title={cluster?.id}>
                      {cluster?.id?.substring(0, 8)}...
                    </div>
                  </div>
                  <div>
                    <div className="text-sm text-gray-600 mb-1">Created</div>
                    <div className="text-sm text-gray-900">{formatDate(cluster?.created_at)}</div>
                  </div>
                  <div>
                    <div className="text-sm text-gray-600 mb-1">Last Heartbeat</div>
                    <div className="text-sm text-gray-900">
                      {cluster?.last_heartbeat ? formatDateTime(cluster.last_heartbeat) : 'Never'}
                    </div>
                  </div>
                </div>
              </Card>

              {/* Utilization Section */}
              {utilization && (
                <Card>
                  <h3 className="text-lg font-semibold text-gray-900 mb-4 flex items-center gap-2">
                    <FiActivity className="w-5 h-5 text-blue-500" />
                    Utilization
                  </h3>
                  <div className="grid grid-cols-2 md:grid-cols-5 gap-6">
                    <div className="text-center">
                      <div className="text-3xl font-bold text-blue-600">
                        {utilization.cpu_utilization_pct.toFixed(1)}%
                      </div>
                      <div className="text-sm text-gray-600 mt-1">CPU Utilization</div>
                      <div className="text-xs text-gray-500 mt-1">
                        {utilization.total_cpu_millicores ? `${(utilization.total_cpu_millicores / 1000).toFixed(2)} cores` : 'N/A'}
                      </div>
                    </div>
                    <div className="text-center">
                      <div className="text-3xl font-bold text-purple-600">
                        {utilization.memory_utilization_pct.toFixed(1)}%
                      </div>
                      <div className="text-sm text-gray-600 mt-1">Memory Utilization</div>
                      <div className="text-xs text-gray-500 mt-1">
                        {utilization.total_memory_bytes ? `${(utilization.total_memory_bytes / (1024 ** 3)).toFixed(2)} GB` : 'N/A'}
                      </div>
                    </div>
                    <div className="text-center">
                      <div className="text-3xl font-bold text-green-600">
                        {formatNumber(utilization.pod_count || 0)}
                      </div>
                      <div className="text-sm text-gray-600 mt-1">Pod Count</div>
                    </div>
                    <div className="text-center">
                      <div className="text-3xl font-bold text-orange-600">
                        {formatNumber(utilization.node_count || 0)}
                      </div>
                      <div className="text-sm text-gray-600 mt-1">Node Count</div>
                    </div>
                    <div className="text-center">
                      <div className="text-2xl font-bold text-indigo-600">
                        {utilization.avg_cpu_cores.toFixed(2)} / {utilization.avg_memory_gb.toFixed(2)}
                      </div>
                      <div className="text-sm text-gray-600 mt-1">Avg CPU / Mem</div>
                      <div className="text-xs text-gray-500 mt-1">cores / GB per pod</div>
                    </div>
                  </div>
                </Card>
              )}

              {/* Workload Type */}
              {workloadType && (
                <Card>
                  <h3 className="text-lg font-semibold text-gray-900 mb-4 flex items-center gap-2">
                    <FiHardDrive className="w-5 h-5 text-purple-500" />
                    Workload Classification
                  </h3>
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                    <div>
                      <div className="text-sm text-gray-600 mb-2">Workload Type</div>
                      <Badge
                        color={
                          workloadType.workload_type === 'STATELESS' ? 'green' :
                            workloadType.workload_type === 'STATEFUL' ? 'red' :
                              workloadType.workload_type === 'MIXED' ? 'yellow' : 'gray'
                        }
                        size="lg"
                      >
                        {workloadType.workload_type}
                      </Badge>
                      {workloadType.cached && (
                        <div className="text-xs text-gray-500 mt-1">Cached</div>
                      )}
                    </div>
                    <div>
                      <div className="text-sm text-gray-600 mb-2">PVC Pods</div>
                      <div className="text-2xl font-semibold text-gray-900">
                        {workloadType.pvc_pod_count || 0} / {workloadType.total_pod_count || 0}
                      </div>
                      <div className="text-xs text-gray-500 mt-1">Pods with Persistent Volumes</div>
                    </div>
                    <div>
                      <div className="text-sm text-gray-600 mb-2">StatefulSet Pods</div>
                      <div className="text-2xl font-semibold text-gray-900">
                        {workloadType.statefulset_pod_count || 0} / {workloadType.total_pod_count || 0}
                      </div>
                      <div className="text-xs text-gray-500 mt-1">StatefulSet workloads</div>
                    </div>
                  </div>
                  <div className="mt-4 p-3 bg-gray-50 rounded-lg">
                    <p className="text-sm text-gray-700">
                      <strong>Analysis:</strong> {workloadType.description}
                    </p>
                    {workloadType.can_optimize_spot !== undefined && (
                      <p className="text-sm mt-2">
                        <strong>Spot Optimization:</strong>{' '}
                        <span className={workloadType.can_optimize_spot ? 'text-green-600' : 'text-red-600'}>
                          {workloadType.can_optimize_spot ? 'Recommended' : 'Use with caution'}
                        </span>
                      </p>
                    )}
                  </div>
                </Card>
              )}

              {/* Node Details with Pods */}
              {nodesDetailed && nodesDetailed.nodes && nodesDetailed.nodes.length > 0 && (
                <Card>
                  <h3 className="text-lg font-semibold text-gray-900 mb-4 flex items-center gap-2">
                    <FiCpu className="w-5 h-5 text-indigo-500" />
                    Node Details ({nodesDetailed.total_nodes} Nodes)
                  </h3>
                  <div className="space-y-3">
                    {nodesDetailed.nodes.map((node, idx) => {
                      const isExpanded = expandedNodes.has(node.node_name);
                      const classificationColor =
                        node.classification === 'STATELESS' ? 'green' :
                          node.classification === 'STATEFUL' ? 'red' :
                            node.classification === 'MIXED' ? 'yellow' : 'gray';

                      return (
                        <div key={idx} className="border border-gray-200 rounded-lg overflow-hidden">
                          {/* Node Header - Clickable */}
                          <div
                            className="bg-gray-50 p-4 cursor-pointer hover:bg-gray-100 transition-colors"
                            onClick={() => {
                              const newExpanded = new Set(expandedNodes);
                              if (isExpanded) {
                                newExpanded.delete(node.node_name);
                              } else {
                                newExpanded.add(node.node_name);
                              }
                              setExpandedNodes(newExpanded);
                            }}
                          >
                            <div className="flex items-center justify-between">
                              <div className="flex items-center gap-3">
                                <span className="text-base font-semibold text-gray-900">
                                  {node.instance_type || 'Unknown'}
                                </span>
                                <Badge color={node.lifecycle === 'spot' ? 'green' : 'blue'} size="sm">
                                  {node.lifecycle}
                                </Badge>
                                <Badge color={classificationColor} size="sm">
                                  {node.classification}
                                </Badge>
                                <span className="text-xs text-gray-500">
                                  {node.availability_zone}
                                </span>
                              </div>
                              <div className="flex items-center gap-6">
                                <div className="text-right">
                                  <div className="text-xs text-gray-500">CPU</div>
                                  <div className="text-sm font-semibold text-gray-900">
                                    {node.cpu_utilization_pct.toFixed(1)}%
                                  </div>
                                </div>
                                <div className="text-right">
                                  <div className="text-xs text-gray-500">Memory</div>
                                  <div className="text-sm font-semibold text-gray-900">
                                    {node.memory_utilization_pct.toFixed(1)}%
                                  </div>
                                </div>
                                <div className="text-right">
                                  <div className="text-xs text-gray-500">Pods</div>
                                  <div className="text-sm font-semibold text-gray-900">
                                    {node.pod_count}
                                  </div>
                                </div>
                                <div className="text-gray-400">
                                  {isExpanded ? '▼' : '▶'}
                                </div>
                              </div>
                            </div>
                          </div>

                          {/* Expanded Pod List */}
                          {isExpanded && (
                            <div className="bg-white p-4">
                              {node.pods && node.pods.length > 0 ? (
                                <div className="space-y-2">
                                  <div className="text-sm font-semibold text-gray-700 mb-3">
                                    Pods ({node.pods.length})
                                  </div>
                                  <table className="w-full text-sm">
                                    <thead className="bg-gray-50">
                                      <tr>
                                        <th className="text-left p-2 text-gray-600">Pod Name</th>
                                        <th className="text-left p-2 text-gray-600">Namespace</th>
                                        <th className="text-left p-2 text-gray-600">Controller</th>
                                        <th className="text-right p-2 text-gray-600">CPU (m)</th>
                                        <th className="text-right p-2 text-gray-600">Memory (MB)</th>
                                        <th className="text-center p-2 text-gray-600">Storage</th>
                                        <th className="text-center p-2 text-gray-600">Type</th>
                                      </tr>
                                    </thead>
                                    <tbody>
                                      {node.pods.map((pod, pidx) => (
                                        <tr key={pidx} className="border-t border-gray-100 hover:bg-gray-50">
                                          <td className="p-2 font-mono text-xs text-gray-900">{pod.pod_name}</td>
                                          <td className="p-2 text-gray-600">{pod.namespace}</td>
                                          <td className="p-2">
                                            <Badge color="blue" size="sm">{pod.controller_type}</Badge>
                                          </td>
                                          <td className="p-2 text-right text-gray-900">
                                            {pod.cpu_usage_millicores || 0}
                                          </td>
                                          <td className="p-2 text-right text-gray-900">
                                            {pod.memory_usage_mb || 0}
                                          </td>
                                          <td className="p-2 text-center">
                                            {pod.has_pvc ? (
                                              <Badge color="orange" size="sm">PVC</Badge>
                                            ) : (
                                              <span className="text-gray-400 text-xs">-</span>
                                            )}
                                          </td>
                                          <td className="p-2 text-center">
                                            <Badge
                                              color={pod.is_stateful ? 'red' : 'green'}
                                              size="sm"
                                            >
                                              {pod.is_stateful ? 'Stateful' : 'Stateless'}
                                            </Badge>
                                          </td>
                                        </tr>
                                      ))}
                                    </tbody>
                                  </table>
                                </div>
                              ) : (
                                <div className="text-center text-gray-500 py-4">
                                  No pods running on this node
                                </div>
                              )}
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                </Card>
              )}

              {/* Metrics */}
              {metrics && (
                <Card>
                  <h3 className="text-lg font-semibold text-gray-900 mb-4 flex items-center gap-2">
                    <FiActivity className="w-5 h-5" />
                    Cluster Metrics
                  </h3>
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-6">
                    <div className="text-center">
                      <div className="text-3xl font-bold text-blue-600">
                        {formatNumber(metrics.total_instances || 0)}
                      </div>
                      <div className="text-sm text-gray-600 mt-1">Total Instances</div>
                    </div>
                    <div className="text-center">
                      <div className="text-3xl font-bold text-green-600">
                        {formatNumber(metrics.spot_instances || 0)}
                      </div>
                      <div className="text-sm text-gray-600 mt-1">Spot Instances</div>
                    </div>
                    <div className="text-center">
                      <div className="text-3xl font-bold text-orange-600">
                        {formatNumber(metrics.on_demand_instances || 0)}
                      </div>
                      <div className="text-sm text-gray-600 mt-1">On-Demand</div>
                    </div>
                    <div className="text-center">
                      <div className="text-3xl font-bold text-purple-600">
                        {metrics.total_instances > 0
                          ? `${Math.round((metrics.spot_instances / metrics.total_instances) * 100)}%`
                          : '0%'}
                      </div>
                      <div className="text-sm text-gray-600 mt-1">Spot Ratio</div>
                    </div>
                  </div>

                  <div className="grid grid-cols-2 md:grid-cols-3 gap-6 mt-6 pt-6 border-t">
                    <div>
                      <div className="flex items-center gap-2 text-sm text-gray-600 mb-1">
                        <FiDollarSign className="w-4 h-4" />
                        Monthly Cost
                      </div>
                      <div className="text-2xl font-bold text-gray-900">
                        {formatCurrency(metrics.monthly_cost || 0)}
                      </div>
                    </div>
                    <div>
                      <div className="flex items-center gap-2 text-sm text-gray-600 mb-1">
                        <FiDollarSign className="w-4 h-4" />
                        Estimated Savings
                      </div>
                      <div className="text-2xl font-bold text-green-600">
                        {formatCurrency(metrics.estimated_savings || 0)}
                      </div>
                    </div>
                    <div>
                      <div className="flex items-center gap-2 text-sm text-gray-600 mb-1">
                        <FiCpu className="w-4 h-4" />
                        Avg CPU
                      </div>
                      <div className="text-2xl font-bold text-gray-900">
                        {metrics.average_cpu_utilization ? `${metrics.average_cpu_utilization}%` : 'N/A'}
                      </div>
                    </div>
                  </div>
                </Card>
              )}

              {/* Detailed Analysis (Node Groups & Health) */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div className="h-80">
                  <NodeGroupBreakdown clusterId={clusterId} />
                </div>
                <div className="h-80">
                  <ClusterHealthTimeline clusterId={clusterId} />
                </div>
              </div>

              {/* Decision Engine Configuration & State */}
              <Card>
                <h3 className="text-lg font-semibold text-gray-900 mb-4 flex items-center gap-2">
                  <FiActivity className="w-5 h-5 text-indigo-500" />
                  Decision Engine State
                </h3>

                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">

                  {/* Optimization Mode & Classification */}
                  <div className="space-y-4">
                    <div>
                      <label className="block text-sm text-gray-600 mb-1">Optimization Mode</label>
                      <select
                        value={cluster?.optimization_mode || 'COST_FIRST'}
                        onChange={handleModeChange}
                        disabled={modeUpdating}
                        className="w-full text-sm border-gray-300 rounded-md shadow-sm focus:ring-indigo-500 focus:border-indigo-500 disabled:opacity-50"
                      >
                        <option value="COST_FIRST">Cost Priority (Max Savings)</option>
                        <option value="BALANCED">Balanced</option>
                        <option value="NO_DOWNTIME_FIRST">No Downtime Priority</option>
                      </select>
                    </div>

                    <div>
                      <div className="text-sm text-gray-600 mb-1">Workload Capability</div>
                      <Badge color={classification?.status === 'STATELESS' ? 'green' : classification?.status === 'STATEFUL' ? 'red' : 'gray'}>
                        {classification?.status || 'UNKNOWN'}
                      </Badge>
                      {classification?.status === 'STATEFUL' && (
                        <p className="text-xs text-red-500 mt-1">Optimization disabled due to stateful workloads.</p>
                      )}
                    </div>
                  </div>

                  {/* Substitute Engine & Circuit Breaker */}
                  <div className="space-y-4">
                    <div className="bg-gray-50 p-3 rounded-md border border-gray-100">
                      <div className="text-xs text-gray-500 font-semibold uppercase mb-1">Substitute Engine</div>
                      <div className="flex items-center justify-between">
                        <Badge color={substituteStatus?.state === 'ACTIVE' ? 'green' : substituteStatus?.state === 'PREWARMING' ? 'yellow' : 'gray'}>
                          {substituteStatus?.state || 'IDLE'}
                        </Badge>
                        {substituteStatus?.state === 'PREWARMING' && substituteStatus?.countdown && (
                          <span className="text-xs font-mono text-orange-600">{substituteStatus.countdown}s left</span>
                        )}
                      </div>
                      {substituteStatus?.state === 'ACTIVE' && substituteStatus?.pool && (
                        <div className="mt-2 text-xs text-gray-700 break-words">Target: {substituteStatus.pool}</div>
                      )}
                    </div>

                    <div className="bg-gray-50 p-3 rounded-md border border-gray-100">
                      <div className="text-xs text-gray-500 font-semibold uppercase mb-1">Execution Circuit Breaker</div>
                      <div className="flex items-center justify-between">
                        <Badge color={executionStatus?.state === 'OPEN' ? 'red' : 'green'}>
                          {executionStatus?.state || 'CLOSED'}
                        </Badge>
                        <span className="text-xs text-gray-600 font-medium">{executionStatus?.failure_count || 0} recent failures</span>
                      </div>
                      {executionStatus?.state === 'OPEN' && (
                        <Button variant="outline" size="sm" className="w-full mt-2 text-xs py-1">Resume Ops</Button>
                      )}
                    </div>

                    {/* Task 8.4: Manual Fallback Button */}
                    {(executionStatus?.state === 'OPEN' || ['PREWARMING', 'READY'].includes(substituteStatus?.state)) && (
                      <PermissionGate permission="manage_clusters">
                        <div className="bg-red-50 p-3 rounded-md border border-red-100">
                          <div className="text-xs text-red-700 font-semibold uppercase mb-1">Manual Fallback</div>
                          <p className="text-xs text-red-600 mb-2">Switch to on-demand instances for 12 hours.</p>
                          <Button
                            variant="primary" // Reverting to primary style with red bg manually
                            size="sm"
                            className="w-full text-xs py-1 bg-red-600 hover:bg-red-700 text-white border-transparent"
                            onClick={() => {
                              if (window.confirm('Are you sure you want to trigger manual fallback?\n\nThis will force the cluster to use on-demand instances (via fallbacks) for the next 12 hours (FALLBACK_TTL_SECONDS = 43200).')) {
                                handleFallback();
                              }
                            }}
                            disabled={fallbackLoading}
                          >
                            {fallbackLoading ? 'Triggering...' : 'Trigger Fallback'}
                          </Button>
                        </div>
                      </PermissionGate>
                    )}
                  </div>

                  {/* Cooldown Status */}
                  <div>
                    <div className="bg-gray-50 p-3 rounded-md border border-gray-100 h-full flex flex-col justify-center">
                      <div className="text-xs text-gray-500 font-semibold uppercase mb-3">Cooldown Enforcer</div>

                      <div className="space-y-2 text-sm">
                        <div className="flex justify-between">
                          <span className="text-gray-500">Duration:</span>
                          <span className="font-medium">{cooldownStatus?.duration_minutes || 60} min</span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-gray-500">Last Switch:</span>
                          <span className="font-medium text-gray-900">{cooldownStatus?.last_switch ? new Date(cooldownStatus.last_switch).toLocaleTimeString() : 'N/A'}</span>
                        </div>
                        <div className="flex justify-between border-t border-gray-200 pt-2 mt-2">
                          <span className="text-gray-500">Status:</span>
                          <span className={`font-bold ${cooldownStatus?.in_cooldown ? 'text-orange-500' : 'text-green-500'}`}>
                            {cooldownStatus?.in_cooldown ? 'LOCKED' : 'READY'}
                          </span>
                        </div>
                      </div>
                    </div>
                  </div>

                </div>
              </Card>

              {/* Policy Configuration */}
              {policy ? (
                <Card>
                  <div className="flex justify-between items-center mb-4">
                    <h3 className="text-lg font-semibold text-gray-900 flex items-center gap-2">
                      <FiSettings className="w-5 h-5" />
                      Optimization Policy
                    </h3>
                    <Badge color={policy.is_active ? 'green' : 'gray'}>
                      {policy.is_active ? 'Active' : 'Inactive'}
                    </Badge>
                  </div>
                  <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
                    <div>
                      <div className="text-sm text-gray-600 mb-1">Spot Target</div>
                      <div className="text-lg font-semibold text-gray-900">
                        {policy.config?.spot_percentage || 0}%
                      </div>
                    </div>
                    <div>
                      <div className="text-sm text-gray-600 mb-1">Node Range</div>
                      <div className="text-lg font-semibold text-gray-900">
                        {policy.config?.min_nodes || 0} - {policy.config?.max_nodes || 0}
                      </div>
                    </div>
                    <div>
                      <div className="text-sm text-gray-600 mb-1">Target CPU</div>
                      <div className="text-lg font-semibold text-gray-900">
                        {policy.config?.target_cpu_utilization || 0}%
                      </div>
                    </div>
                    <div>
                      <div className="text-sm text-gray-600 mb-1">Target Memory</div>
                      <div className="text-lg font-semibold text-gray-900">
                        {policy.config?.target_memory_utilization || 0}%
                      </div>
                    </div>
                    <div>
                      <div className="text-sm text-gray-600 mb-1">Fallback</div>
                      <div className="text-lg font-semibold text-gray-900">
                        {policy.config?.enable_fallback_to_on_demand ? 'Enabled' : 'Disabled'}
                      </div>
                    </div>
                    <div>
                      <div className="text-sm text-gray-600 mb-1">Diversification</div>
                      <div className="text-lg font-semibold text-gray-900">
                        {policy.config?.enable_diversification ? 'Enabled' : 'Disabled'}
                      </div>
                    </div>
                  </div>
                </Card>
              ) : (
                <Card>
                  <div className="text-center py-6">
                    <FiSettings className="w-12 h-12 text-gray-300 mx-auto mb-3" />
                    <p className="text-gray-500">No optimization policy configured</p>
                    <Button variant="primary" size="sm" className="mt-3">
                      Configure Policy
                    </Button>
                  </div>
                </Card>
              )}

              {/* Hibernation Schedule */}
              {schedule ? (
                <Card>
                  <div className="flex justify-between items-center mb-4">
                    <h3 className="text-lg font-semibold text-gray-900 flex items-center gap-2">
                      <FiClock className="w-5 h-5" />
                      Hibernation Schedule
                    </h3>
                    <div className="flex items-center gap-3">
                      <Badge color={schedule.is_active ? 'green' : 'gray'}>
                        {schedule.is_active ? 'Active' : 'Inactive'}
                      </Badge>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => navigate(`/hibernation/${clusterId}`)}
                      >
                        <FiSettings className="w-4 h-4 mr-1" />
                        Edit Schedule
                      </Button>
                    </div>
                  </div>
                  <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
                    <div>
                      <div className="text-sm text-gray-600 mb-1">Strategy</div>
                      <div className="text-lg font-semibold text-gray-900">
                        {schedule.strategy?.replace('_', ' ') || 'Namespace Sleep'}
                      </div>
                    </div>
                    <div>
                      <div className="text-sm text-gray-600 mb-1">Timezone</div>
                      <div className="text-lg font-semibold text-gray-900">{schedule.timezone}</div>
                    </div>
                    <div>
                      <div className="text-sm text-gray-600 mb-1">Pre-warm Minutes</div>
                      <div className="text-lg font-semibold text-gray-900">
                        {schedule.pre_warm_minutes} min
                      </div>
                    </div>
                    <div>
                      <div className="text-sm text-gray-600 mb-1">Active Hours</div>
                      <div className="text-lg font-semibold text-gray-900">
                        {schedule.schedule_matrix?.filter((h) => h === 1).length || 0} / 168 hours
                      </div>
                    </div>
                    <div>
                      <div className="text-sm text-gray-600 mb-1">Last Action</div>
                      <div className="text-lg font-semibold text-gray-900">
                        {schedule.last_action || 'None'}
                      </div>
                    </div>
                    <div>
                      <div className="text-sm text-gray-600 mb-1">Last Action At</div>
                      <div className="text-lg font-semibold text-gray-900">
                        {schedule.last_action_at ? formatDateTime(schedule.last_action_at) : 'N/A'}
                      </div>
                    </div>
                  </div>
                </Card>
              ) : (
                <Card>
                  <div className="text-center py-6">
                    <FiClock className="w-12 h-12 text-gray-300 mx-auto mb-3" />
                    <p className="text-gray-500">No hibernation schedule configured</p>
                    <Button
                      variant="primary"
                      size="sm"
                      className="mt-3"
                      onClick={() => navigate(`/hibernation/${clusterId}`)}
                    >
                      Configure Schedule
                    </Button>
                  </div>
                </Card>
              )}

              {/* Cluster Configuration */}
              <Card>
                <h3 className="text-lg font-semibold text-gray-900 mb-4">Cluster Configuration</h3>
                <div className="space-y-3 text-sm">
                  <div className="flex justify-between">
                    <span className="text-gray-600">Kubernetes Version:</span>
                    <span className="font-medium text-gray-900">{cluster?.version || 'N/A'}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-600">VPC ID:</span>
                    <span className="font-mono text-gray-900">{cluster?.vpc_id || 'N/A'}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-600">Tags:</span>
                    <span className="font-medium text-gray-900">
                      {cluster?.tags ? Object.keys(cluster.tags).length : 0} tags
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-600">Agent Installed:</span>
                    <Badge color={cluster?.last_heartbeat ? 'green' : 'red'}>
                      {cluster?.last_heartbeat ? 'Yes' : 'No'}
                    </Badge>
                  </div>
                </div>
              </Card>

              {/* Agent Management */}
              <Card>
                <h3 className="text-lg font-semibold text-gray-900 mb-4 flex items-center gap-2">
                  <FiActivity className="w-5 h-5 text-blue-500" />
                  Agent Management
                </h3>
                <div className="flex items-center justify-between p-3 bg-gray-50 rounded-lg mb-4">
                  <div>
                    <div className="text-sm font-medium text-gray-900">Agent Status</div>
                    <div className="text-sm text-gray-500">
                      {cluster?.agent_installed === 'Y'
                        ? `Active — last heartbeat ${cluster?.last_heartbeat ? formatDateTime(cluster.last_heartbeat) : 'unknown'}`
                        : 'No agent installed or agent disconnected'}
                    </div>
                  </div>
                  <Badge color={cluster?.agent_installed === 'Y' ? 'green' : 'gray'} size="lg">
                    {cluster?.agent_installed === 'Y' ? 'Connected' : 'Not Connected'}
                  </Badge>
                </div>

                {cluster?.agent_installed === 'Y' ? (
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                    <div className="border border-yellow-200 rounded-lg p-4 bg-yellow-50">
                      <h4 className="font-semibold text-gray-900 mb-1">Disconnect Agent</h4>
                      <p className="text-xs text-gray-500 mb-3">
                        Stops data collection. All existing metrics and history are kept.
                        The DaemonSet stays on the cluster but the API key is rotated so it stops sending data.
                        You can reinstall later.
                      </p>
                      <button
                        onClick={() => setShowDisconnectModal(true)}
                        className="text-sm px-3 py-1.5 border border-yellow-500 text-yellow-700 rounded hover:bg-yellow-100 transition-colors"
                      >
                        Disconnect Agent
                      </button>
                    </div>
                    <div className="border border-red-200 rounded-lg p-4 bg-red-50">
                      <h4 className="font-semibold text-gray-900 mb-1">Remove Agent & Delete Data</h4>
                      <p className="text-xs text-gray-500 mb-3">
                        Permanently deletes the agent from the cluster and removes all pod metrics,
                        instance records, and history. The cluster registration is kept.
                        This cannot be undone.
                      </p>
                      <button
                        onClick={() => setShowRemoveModal(true)}
                        className="text-sm px-3 py-1.5 border border-red-500 text-red-700 rounded hover:bg-red-100 transition-colors"
                      >
                        Remove Agent & Data
                      </button>
                    </div>
                  </div>
                ) : (
                  <div className="flex flex-col items-center py-6 bg-gray-50 rounded-lg border border-gray-200">
                    <p className="text-gray-500 text-sm mb-4">No agent connected. Use the installer to add an agent to this cluster.</p>
                    <button
                      onClick={() => {
                        toast.loading(`Installing agent on ${cluster.name}...`, { id: 'inject-detail' });
                        clusterAPI.autoInstallAgent(clusterId)
                          .then((result) => {
                            toast.success(`Agent installation queued. It will be active in ~30s.`, { id: 'inject-detail', duration: 5000 });
                            setTimeout(() => window.dispatchEvent(new Event('refresh-clusters')), 8000);
                          })
                          .catch((error) => {
                            console.error('Agent installation error:', error);
                            toast.error('Failed to install agent: ' + (error.response?.data?.detail || error.message), { id: 'inject-detail' });
                          });
                      }}
                      className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white text-sm font-medium rounded-lg shadow-sm transition-colors"
                      disabled={agentActionLoading}
                    >
                      {agentActionLoading ? 'Installing...' : 'Install Agent'}
                    </button>
                  </div>
                )}
              </Card>

              {/* Node List */}
              <NodeList clusterId={clusterId} />
            </>
          )}

          {activeTab === 'Optimization Settings' && (
            <div className="space-y-6">
              <Card>
                <div className="flex items-center justify-between mb-6">
                  <div>
                    <h3 className="text-lg font-semibold text-gray-900 flex items-center gap-2">
                      <FiSettings className="w-5 h-5 text-blue-600" />
                      Global Optimization Settings
                    </h3>
                    <p className="text-sm text-gray-500 mt-1">
                      Configure high-level automation permissions for this cluster.
                    </p>
                  </div>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                  {/* ML Spot Optimization Toggle */}
                  <div className="flex items-start justify-between p-4 border rounded-lg bg-gray-50">
                    <div>
                      <h4 className="font-semibold text-gray-900">Auto Rebalance (ML Spot Optimization)</h4>
                      <p className="text-sm text-gray-500 mt-1">
                        Allow AtharvaAI to automatically move stateless pods to cheaper, stable Spot instances.
                      </p>
                    </div>
                    <label className="relative inline-flex items-center cursor-pointer mt-1">
                      <input
                        type="checkbox"
                        className="sr-only peer"
                        checked={cluster?.auto_rebalance_enabled !== false}
                        onChange={async (e) => {
                          const enabled = e.target.checked;
                          try {
                            await decisionEngineAPI.toggleAutoRebalance(clusterId, enabled);
                            toast.success(`Auto Rebalance ${enabled ? 'Enabled' : 'Disabled'}`);
                            handleRefresh();
                          } catch (err) {
                            toast.error('Failed to update Auto Rebalance setting');
                          }
                        }}
                      />
                      <div className="w-11 h-6 bg-gray-200 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-blue-600"></div>
                    </label>
                  </div>

                  {/* Auto Rightsizing Toggle */}
                  <div className="flex items-start justify-between p-4 border rounded-lg bg-gray-50">
                    <div>
                      <h4 className="font-semibold text-gray-900">Auto Rightsizing</h4>
                      <p className="text-sm text-gray-500 mt-1">
                        Automatically apply VPA/HPA rightsizing recommendations to stateless workloads.
                      </p>
                    </div>
                    <label className="relative inline-flex items-center cursor-pointer mt-1">
                      <input
                        type="checkbox"
                        className="sr-only peer"
                        checked={cluster?.rightsizing_enabled !== false}
                        onChange={async (e) => {
                          const enabled = e.target.checked;
                          try {
                            await decisionEngineAPI.toggleRightsizing(clusterId, enabled);
                            toast.success(`Auto Rightsizing ${enabled ? 'Enabled' : 'Disabled'}`);
                            handleRefresh();
                          } catch (err) {
                            toast.error('Failed to update Rightsizing setting');
                          }
                        }}
                      />
                      <div className="w-11 h-6 bg-gray-200 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-blue-600"></div>
                    </label>
                  </div>

                  {/* Cooldown Override */}
                  <div className="flex items-start justify-between p-4 border rounded-lg">
                    <div>
                      <h4 className="font-semibold text-gray-900">Cooldown Duration Override</h4>
                      <p className="text-xs text-blue-600 font-medium mt-1 uppercase tracking-wider">Advanced Users</p>
                      <p className="text-sm text-gray-500 mt-1">
                        Override the default cluster stabilization cooldown timer.
                      </p>
                    </div>
                    <div className="mt-1 flex items-center">
                      <input type="number" defaultValue="30" className="w-16 h-8 text-sm border-gray-300 rounded-md text-right mr-2" />
                      <span className="text-sm text-gray-500">min</span>
                    </div>
                  </div>

                  {/* Conservative Mode */}
                  <div className="flex items-start justify-between p-4 border rounded-lg">
                    <div>
                      <h4 className="font-semibold text-gray-900">Conservative Mode</h4>
                      <p className="text-xs text-green-600 font-medium mt-1 uppercase tracking-wider">Fresh Cluster Protection</p>
                      <p className="text-sm text-gray-500 mt-1">
                        Enables stringent safety checks and restricts severe downscaling.
                      </p>
                    </div>
                    <label className="relative inline-flex items-center cursor-pointer mt-1">
                      <input type="checkbox" className="sr-only peer" defaultChecked={true} />
                      <div className="w-11 h-6 bg-gray-200 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-green-600"></div>
                    </label>
                  </div>

                  {/* Manual Approval */}
                  <div className="flex items-start justify-between p-4 border rounded-lg md:col-span-2">
                    <div>
                      <h4 className="font-semibold text-gray-900">Manual Approval Required</h4>
                      <p className="text-sm text-gray-500 mt-1">
                        When enabled, all automated optimization actions generated by the engine will be staged as "Pending" and require manual human approval in the Activity Log before execution.
                      </p>
                    </div>
                    <label className="relative inline-flex items-center cursor-pointer mt-3">
                      <input type="checkbox" className="sr-only peer" />
                      <div className="w-11 h-6 bg-gray-200 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-gray-800"></div>
                    </label>
                  </div>
                </div>
              </Card>

              {/* Render the Strategy and Rules Engine below */}
              <DecisionEngineV3Dashboard clusterId={clusterId} cluster={cluster} />
            </div>
          )}

          {activeTab === 'Node Template' && (
            <NodeTemplateTab clusterId={clusterId} />
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
