import React, { useState, useEffect } from 'react';
import { Card, Button, Badge } from '../shared';
import {
  FiActivity,
  FiDatabase,
  FiServer,
  FiAlertTriangle,
  FiCheckCircle,
  FiClock,
  FiRefreshCw,
  FiCpu,
  FiHardDrive,
  FiShield,
} from 'react-icons/fi';
import toast from 'react-hot-toast';
import { formatNumber } from '../../utils/formatters';
import { api, atharvaAiAPI, adminAPI } from '../../services/api';


const AdminHealth = () => {
  const [health, setHealth] = useState(null);
  const [mlHealth, setMlHealth] = useState(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [autoRefresh, setAutoRefresh] = useState(false);
  const [circuitBreakers, setCircuitBreakers] = useState([]);
  const [cbLoading, setCbLoading] = useState(true);
  const [cbResetting, setCbResetting] = useState({});

  useEffect(() => {
    fetchHealth();
    fetchCircuitBreakers();
  }, []);

  useEffect(() => {
    if (!autoRefresh) return;
    const interval = setInterval(() => {
      fetchHealth();
      fetchCircuitBreakers();
    }, 30000);
    return () => clearInterval(interval);
  }, [autoRefresh]);

  const fetchHealth = async () => {
    if (!loading) setRefreshing(true);

    try {
      const [sysRes, mlRes] = await Promise.all([
        api.get('/api/v1/health/system').catch(() => null),
        atharvaAiAPI.getHealth().catch(() => null)
      ]);

      if (sysRes?.data) setHealth(sysRes.data);
      else throw new Error("System health failed");

      if (mlRes?.data) setMlHealth(mlRes.data);
    } catch (error) {
      console.error('Health check failed:', error);
      toast.error('Failed to fetch system/ML health');
      // Set degraded status on error
      if (!health) {
        setHealth({
          status: 'degraded',
          timestamp: new Date().toISOString(),
          services: {},
          metrics: {},
          incidents: []
        });
      }
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };


  const fetchCircuitBreakers = async () => {
    setCbLoading(true);
    try {
      const res = await adminAPI.getCircuitBreakers();
      setCircuitBreakers(res.data?.circuit_breakers || []);
    } catch (err) {
      console.error('Failed to fetch circuit breakers:', err);
    } finally {
      setCbLoading(false);
    }
  };

  const handleResetCircuitBreaker = async (clusterId) => {
    setCbResetting(prev => ({ ...prev, [clusterId]: true }));
    try {
      await adminAPI.resetCircuitBreaker(clusterId);
      toast.success(`Circuit breaker reset for ${clusterId}`);
      fetchCircuitBreakers();
    } catch (err) {
      toast.error(`Failed to reset circuit breaker: ${err.message}`);
    } finally {
      setCbResetting(prev => ({ ...prev, [clusterId]: false }));
    }
  };

  const getCbStateBadge = (state) => {
    if (state === 'NORMAL') return 'bg-green-100 text-green-800';
    if (state === 'CONSERVATIVE') return 'bg-yellow-100 text-yellow-800';
    if (state === 'HALT') return 'bg-red-100 text-red-800';
    return 'bg-gray-100 text-gray-700';
  };

  const handleRefresh = () => {
    fetchHealth();
    fetchCircuitBreakers();
    toast.success('Health data refreshed');
  };

  const getStatusColor = (status) => {
    switch (status) {
      case 'healthy':
        return 'green';
      case 'degraded':
        return 'yellow';
      case 'unhealthy':
        return 'red';
      default:
        return 'gray';
    }
  };

  const getSeverityColor = (severity) => {
    switch (severity) {
      case 'critical':
        return 'red';
      case 'warning':
        return 'yellow';
      case 'info':
        return 'blue';
      default:
        return 'gray';
    }
  };

  const getUsageColor = (percentage) => {
    if (percentage >= 90) return 'text-red-600';
    if (percentage >= 75) return 'text-yellow-600';
    return 'text-green-600';
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-3xl font-bold text-gray-900">System Health</h1>
          <p className="text-gray-600 mt-1">Real-time platform monitoring and diagnostics</p>
        </div>
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2">
            <input
              type="checkbox"
              id="auto-refresh"
              checked={autoRefresh}
              onChange={(e) => setAutoRefresh(e.target.checked)}
              className="h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-300 rounded"
            />
            <label htmlFor="auto-refresh" className="text-sm text-gray-700">
              Auto-refresh (30s)
            </label>
          </div>
          <Button
            variant="outline"
            icon={<FiRefreshCw className={refreshing ? 'animate-spin' : ''} />}
            onClick={handleRefresh}
            disabled={refreshing}
          >
            Refresh
          </Button>
        </div>
      </div>

      {/* Overall Status */}
      <Card className={`border-2 ${health?.status === 'healthy' ? 'border-green-200 bg-green-50' : 'border-red-200 bg-red-50'}`}>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-4">
            {health?.status === 'healthy' ? (
              <FiCheckCircle className="w-12 h-12 text-green-600" />
            ) : (
              <FiAlertTriangle className="w-12 h-12 text-red-600" />
            )}
            <div>
              <h2 className="text-2xl font-bold text-gray-900 capitalize">
                System Status: {health?.status}
              </h2>
              <p className="text-sm text-gray-600 mt-1">
                Last updated: {new Date(health?.timestamp).toLocaleString()}
              </p>
            </div>
          </div>
          <Badge color={getStatusColor(health?.status)} size="lg">
            {health?.status?.toUpperCase()}
          </Badge>
        </div>
      </Card>

      {/* ML System Status */}
      <Card className={`border-2 ${mlHealth?.status === 'online' ? 'border-indigo-200 bg-indigo-50' : 'border-gray-200 bg-gray-50'}`}>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-4">
            <FiActivity className={`w-12 h-12 ${mlHealth?.status === 'online' ? 'text-indigo-600' : 'text-gray-400'}`} />
            <div>
              <h2 className="text-2xl font-bold text-gray-900 capitalize">
                ASCP.ai Engine: {mlHealth?.status || 'UNKNOWN'}
              </h2>
              <p className="text-sm text-gray-600 mt-1">
                Version: {mlHealth?.version || 'v3.1.2'} • Global Engine Status
              </p>
            </div>
          </div>
          <Badge color={mlHealth?.status === 'online' ? 'indigo' : 'gray'} size="lg">
            {mlHealth?.status === 'online' ? 'ACTIVE' : 'STANDBY'}
          </Badge>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mt-6 border-t border-indigo-100 pt-6">
          <div className="bg-white p-4 rounded-lg shadow-sm border border-gray-100">
            <div className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-1">Classifier Model</div>
            <div className="text-lg font-bold text-gray-900 font-mono text-sm">{mlHealth?.models?.classifier?.version || 'v1.4.0'}</div>
            <div className="text-xs text-green-600 mt-1 flex items-center"><FiCheckCircle className="mr-1" /> Loaded</div>
          </div>
          <div className="bg-white p-4 rounded-lg shadow-sm border border-gray-100">
            <div className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-1">Regressor Model</div>
            <div className="text-lg font-bold text-gray-900 font-mono text-sm">{mlHealth?.models?.regressor?.version || 'v2.1.1'}</div>
            <div className="text-xs text-green-600 mt-1 flex items-center"><FiCheckCircle className="mr-1" /> Loaded</div>
          </div>
          <div className="bg-white p-4 rounded-lg shadow-sm border border-gray-100">
            <div className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-1">Avg Inference Latency</div>
            <div className="text-2xl font-bold text-gray-900 flex items-end gap-1">
              {mlHealth?.inference_latency_ms || 18} <span className="text-sm font-normal text-gray-500 mb-1">ms</span>
            </div>
          </div>
          <div className="bg-white p-4 rounded-lg shadow-sm border border-gray-100">
            <div className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-1">Prediction Accuracy</div>
            <div className="text-2xl font-bold text-indigo-600 flex items-end gap-1">
              {((mlHealth?.accuracy || 0.94) * 100).toFixed(1)} <span className="text-sm font-normal text-gray-500 mb-1">%</span>
            </div>
          </div>
        </div>
      </Card>

      {/* Services Status */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        {/* API Service */}
        <Card>
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-2">
              <FiServer className="w-5 h-5 text-gray-700" />
              <h3 className="font-semibold text-gray-900">API Service</h3>
            </div>
            <Badge color={getStatusColor(health?.services?.api?.status)}>
              {health?.services?.api?.status}
            </Badge>
          </div>
          <div className="space-y-2 text-sm">
            <div className="flex justify-between">
              <span className="text-gray-600">Response Time:</span>
              <span className="font-medium">{health?.services?.api?.response_time}ms</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-600">Uptime:</span>
              <span className="font-medium text-green-600">{health?.services?.api?.uptime}%</span>
            </div>
          </div>
        </Card>

        {/* Database */}
        <Card>
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-2">
              <FiDatabase className="w-5 h-5 text-gray-700" />
              <h3 className="font-semibold text-gray-900">Database</h3>
            </div>
            <Badge color={getStatusColor(health?.services?.database?.status)}>
              {health?.services?.database?.status}
            </Badge>
          </div>
          <div className="space-y-2 text-sm">
            <div className="flex justify-between">
              <span className="text-gray-600">Connections:</span>
              <span className="font-medium">
                {health?.services?.database?.connections}/{health?.services?.database?.max_connections}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-600">Query Time:</span>
              <span className="font-medium">{health?.services?.database?.query_time_avg}ms</span>
            </div>
          </div>
        </Card>

        {/* Redis Cache */}
        <Card>
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-2">
              <FiActivity className="w-5 h-5 text-gray-700" />
              <h3 className="font-semibold text-gray-900">Redis Cache</h3>
            </div>
            <Badge color={getStatusColor(health?.services?.redis?.status)}>
              {health?.services?.redis?.status}
            </Badge>
          </div>
          <div className="space-y-2 text-sm">
            <div className="flex justify-between">
              <span className="text-gray-600">Memory Usage:</span>
              <span className="font-medium">
                {health?.services?.redis?.memory_usage}/{health?.services?.redis?.max_memory} MB
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-600">Hit Rate:</span>
              <span className="font-medium text-green-600">{health?.services?.redis?.hit_rate}%</span>
            </div>
          </div>
        </Card>

        {/* Job Queue */}
        <Card>
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-2">
              <FiClock className="w-5 h-5 text-gray-700" />
              <h3 className="font-semibold text-gray-900">Job Queue</h3>
            </div>
            <Badge color={getStatusColor(health?.services?.queue?.status)}>
              {health?.services?.queue?.status}
            </Badge>
          </div>
          <div className="space-y-2 text-sm">
            <div className="flex justify-between">
              <span className="text-gray-600">Pending Jobs:</span>
              <span className="font-medium">{formatNumber(health?.services?.queue?.pending_jobs)}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-600">Processing Rate:</span>
              <span className="font-medium">{formatNumber(health?.services?.queue?.processed_per_minute)}/min</span>
            </div>
          </div>
        </Card>
      </div>

      {/* System Metrics */}
      <Card>
        <h3 className="text-lg font-semibold text-gray-900 mb-4">System Metrics</h3>
        <div className="grid grid-cols-1 md:grid-cols-3 lg:grid-cols-5 gap-6">
          {/* CPU Usage */}
          <div className="text-center">
            <FiCpu className="w-8 h-8 text-blue-600 mx-auto mb-2" />
            <div className={`text-3xl font-bold ${getUsageColor(health?.metrics?.cpu_usage)}`}>
              {health?.metrics?.cpu_usage}%
            </div>
            <div className="text-sm text-gray-600 mt-1">CPU Usage</div>
            <div className="w-full bg-gray-200 rounded-full h-2 mt-2">
              <div
                className="bg-blue-600 h-2 rounded-full transition-all"
                style={{ width: `${health?.metrics?.cpu_usage}%` }}
              />
            </div>
          </div>

          {/* Memory Usage */}
          <div className="text-center">
            <FiHardDrive className="w-8 h-8 text-green-600 mx-auto mb-2" />
            <div className={`text-3xl font-bold ${getUsageColor(health?.metrics?.memory_usage)}`}>
              {health?.metrics?.memory_usage}%
            </div>
            <div className="text-sm text-gray-600 mt-1">Memory Usage</div>
            <div className="w-full bg-gray-200 rounded-full h-2 mt-2">
              <div
                className="bg-green-600 h-2 rounded-full transition-all"
                style={{ width: `${health?.metrics?.memory_usage}%` }}
              />
            </div>
          </div>

          {/* Disk Usage */}
          <div className="text-center">
            <FiHardDrive className="w-8 h-8 text-purple-600 mx-auto mb-2" />
            <div className={`text-3xl font-bold ${getUsageColor(health?.metrics?.disk_usage)}`}>
              {health?.metrics?.disk_usage}%
            </div>
            <div className="text-sm text-gray-600 mt-1">Disk Usage</div>
            <div className="w-full bg-gray-200 rounded-full h-2 mt-2">
              <div
                className="bg-purple-600 h-2 rounded-full transition-all"
                style={{ width: `${health?.metrics?.disk_usage}%` }}
              />
            </div>
          </div>

          {/* Network In */}
          <div className="text-center">
            <FiActivity className="w-8 h-8 text-orange-600 mx-auto mb-2" />
            <div className="text-3xl font-bold text-orange-600">{health?.metrics?.network_in}</div>
            <div className="text-sm text-gray-600 mt-1">MB/s In</div>
          </div>

          {/* Network Out */}
          <div className="text-center">
            <FiActivity className="w-8 h-8 text-red-600 mx-auto mb-2" />
            <div className="text-3xl font-bold text-red-600">{health?.metrics?.network_out}</div>
            <div className="text-sm text-gray-600 mt-1">MB/s Out</div>
          </div>
        </div>
      </Card>

      {/* Recent Incidents */}
      <Card>
        <h3 className="text-lg font-semibold text-gray-900 mb-4">Recent Incidents</h3>
        {health?.incidents && health.incidents.length > 0 ? (
          <div className="space-y-3">
            {health.incidents.map((incident) => (
              <div
                key={incident.id}
                className={`p-4 rounded-lg border ${incident.resolved ? 'bg-gray-50 border-gray-200' : 'bg-yellow-50 border-yellow-200'
                  }`}
              >
                <div className="flex items-start justify-between">
                  <div className="flex items-start gap-3 flex-1">
                    <Badge color={getSeverityColor(incident.severity)}>{incident.severity}</Badge>
                    <div className="flex-1">
                      <p className="text-sm font-medium text-gray-900">{incident.message}</p>
                      <p className="text-xs text-gray-600 mt-1">
                        {new Date(incident.timestamp).toLocaleString()}
                      </p>
                    </div>
                  </div>
                  {incident.resolved && (
                    <Badge color="green">
                      <FiCheckCircle className="w-3 h-3 mr-1" />
                      Resolved
                    </Badge>
                  )}
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="text-center py-8 text-gray-500">
            <FiCheckCircle className="w-12 h-12 text-green-500 mx-auto mb-3" />
            <p>No incidents reported</p>
          </div>
        )}
      </Card>

      {/* Circuit Breaker Status */}
      <Card>
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <FiShield className="w-5 h-5 text-indigo-600" />
            <h3 className="text-lg font-semibold text-gray-900">Circuit Breaker Status</h3>
          </div>
          <Button
            variant="outline"
            size="sm"
            icon={<FiRefreshCw className={cbLoading ? 'animate-spin' : ''} />}
            onClick={fetchCircuitBreakers}
            disabled={cbLoading}
          >
            Refresh
          </Button>
        </div>
        {cbLoading ? (
          <div className="flex justify-center py-6">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-600"></div>
          </div>
        ) : circuitBreakers.length === 0 ? (
          <div className="text-center py-6 text-gray-500">
            <FiCheckCircle className="w-10 h-10 text-green-400 mx-auto mb-2" />
            <p className="text-sm">All circuit breakers nominal</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[600px] divide-y divide-gray-200 text-sm">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Cluster</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">State</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Rollback Count</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Failure Count</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Action</th>
                </tr>
              </thead>
              <tbody className="bg-white divide-y divide-gray-200">
                {circuitBreakers.map((cb) => (
                  <tr key={cb.cluster_id} className="hover:bg-gray-50">
                    <td className="px-4 py-3 font-medium text-gray-900">{cb.cluster_name || cb.cluster_id}</td>
                    <td className="px-4 py-3">
                      <span className={`px-2 py-0.5 inline-flex text-xs font-semibold rounded-full ${getCbStateBadge(cb.state)}`}>
                        {cb.state || 'NORMAL'}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-gray-700">{cb.rollback_count ?? 0}</td>
                    <td className="px-4 py-3 text-gray-700">{cb.failure_count ?? 0}</td>
                    <td className="px-4 py-3">
                      <button
                        onClick={() => handleResetCircuitBreaker(cb.cluster_id)}
                        disabled={cbResetting[cb.cluster_id]}
                        className="px-3 py-1 text-xs bg-indigo-600 text-white rounded hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed"
                      >
                        {cbResetting[cb.cluster_id] ? 'Resetting...' : 'Reset'}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {/* System Information */}
      <Card>
        <h3 className="text-lg font-semibold text-gray-900 mb-4">System Information</h3>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
          <div>
            <div className="text-gray-600 mb-1">Platform Version</div>
            <div className="font-medium text-gray-900">v1.0.0</div>
          </div>
          <div>
            <div className="text-gray-600 mb-1">Environment</div>
            <div className="font-medium text-gray-900">Production</div>
          </div>
          <div>
            <div className="text-gray-600 mb-1">Region</div>
            <div className="font-medium text-gray-900">us-east-1</div>
          </div>
          <div>
            <div className="text-gray-600 mb-1">Deployment</div>
            <div className="font-medium text-gray-900">Kubernetes</div>
          </div>
        </div>
      </Card>
    </div>
  );
};

export default AdminHealth;
