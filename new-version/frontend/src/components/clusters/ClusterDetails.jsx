/**
 * Cluster Details Component
 * Detailed view of cluster with metrics, nodes, and configuration
 */
import React, { useState, useEffect } from 'react';
import { clusterAPI, metricsAPI, policyAPI, hibernationAPI } from '../../services/api';
import { Card, Button, Badge } from '../shared';
import { FiX, FiRefreshCw, FiSettings, FiClock, FiCpu, FiHardDrive, FiDollarSign, FiActivity } from 'react-icons/fi';
import toast from 'react-hot-toast';
import { formatCurrency, formatNumber, formatDate, formatDateTime } from '../../utils/formatters';

const ClusterDetails = ({ clusterId, onClose }) => {
  const [cluster, setCluster] = useState(null);
  const [metrics, setMetrics] = useState(null);
  const [policy, setPolicy] = useState(null);
  const [schedule, setSchedule] = useState(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  useEffect(() => {
    if (clusterId) {
      fetchClusterDetails();
    }
  }, [clusterId]);

  const fetchClusterDetails = async () => {
    setLoading(true);
    try {
      // Fetch cluster data, metrics, policy, and schedule in parallel
      const [clusterRes, metricsRes, policyRes, scheduleRes] = await Promise.allSettled([
        clusterAPI.get(clusterId),
        metricsAPI.getCluster(clusterId),
        policyAPI.getByCluster(clusterId),
        hibernationAPI.getByCluster(clusterId),
      ]);

      if (clusterRes.status === 'fulfilled') {
        setCluster(clusterRes.value.data.cluster);
      }

      if (metricsRes.status === 'fulfilled') {
        setMetrics(metricsRes.value.data.metrics);
      }

      if (policyRes.status === 'fulfilled') {
        setPolicy(policyRes.value.data.policy);
      }

      if (scheduleRes.status === 'fulfilled') {
        setSchedule(scheduleRes.value.data.schedule);
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
        <div className="sticky top-0 bg-white border-b px-6 py-4 flex justify-between items-center">
          <div>
            <h2 className="text-2xl font-bold text-gray-900">{cluster?.name}</h2>
            <p className="text-sm text-gray-600 mt-1">
              {cluster?.region} • {cluster?.provider || 'AWS'}
            </p>
          </div>
          <div className="flex items-center gap-2">
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

        <div className="p-6 space-y-6">
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
                <Badge color={schedule.is_active ? 'green' : 'gray'}>
                  {schedule.is_active ? 'Active' : 'Inactive'}
                </Badge>
              </div>
              <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
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
              </div>
            </Card>
          ) : (
            <Card>
              <div className="text-center py-6">
                <FiClock className="w-12 h-12 text-gray-300 mx-auto mb-3" />
                <p className="text-gray-500">No hibernation schedule configured</p>
                <Button variant="primary" size="sm" className="mt-3">
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
        </div>

        {/* Footer Actions */}
        <div className="sticky bottom-0 bg-gray-50 border-t px-6 py-4 flex justify-end gap-2">
          <Button variant="secondary" onClick={onClose}>
            Close
          </Button>
        </div>
      </div>
    </div>
  );
};

export default ClusterDetails;
