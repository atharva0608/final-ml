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
} from 'react-icons/fi';
import toast from 'react-hot-toast';
import { formatNumber } from '../../utils/formatters';
import { api } from '../../services/api';


const AdminHealth = () => {
  // ... state

  const fetchHealth = async () => {
    if (!loading) setRefreshing(true);

    try {
      const response = await api.get('/health/system');
      setHealth(response.data);
    } catch (error) {
      console.error('Health check failed:', error);
      toast.error('Failed to fetch system health');
      // Set degraded status on error
      setHealth({
        status: 'degraded',
        timestamp: new Date().toISOString(),
        services: {},
        metrics: {},
        incidents: []
      });
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };


  const handleRefresh = () => {
    fetchHealth();
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
