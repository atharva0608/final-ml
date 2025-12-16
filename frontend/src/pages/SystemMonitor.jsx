/**
 * System Monitor - Admin Dashboard
 *
 * Provides real-time monitoring of all system components:
 * - Web Scraper (AWS Spot Advisor)
 * - Price Scraper (AWS Pricing API)
 * - Database Operations
 * - Linear Optimizer (switching decisions)
 * - ML Inference Engine
 * - Instance Management
 * - Redis Cache
 * - API Server
 *
 * Features:
 * - Component health status with visual indicators
 * - Last 5 console logs for each component
 * - Execution time metrics
 * - Error rate tracking
 * - Auto-refresh capability
 */

import React, { useState, useEffect } from 'react';
import { RefreshCw, AlertCircle, CheckCircle, XCircle, Activity } from 'lucide-react';
import api from '../services/api';

// Component status colors
const STATUS_COLORS = {
  healthy: {
    bg: 'bg-green-50',
    border: 'border-green-500',
    text: 'text-green-700',
    icon: 'text-green-500',
    badge: 'bg-green-100 text-green-800'
  },
  degraded: {
    bg: 'bg-yellow-50',
    border: 'border-yellow-500',
    text: 'text-yellow-700',
    icon: 'text-yellow-500',
    badge: 'bg-yellow-100 text-yellow-800'
  },
  down: {
    bg: 'bg-red-50',
    border: 'border-red-500',
    text: 'text-red-700',
    icon: 'text-red-500',
    badge: 'bg-red-100 text-red-800'
  },
  unknown: {
    bg: 'bg-gray-50',
    border: 'border-gray-500',
    text: 'text-gray-700',
    icon: 'text-gray-500',
    badge: 'bg-gray-100 text-gray-800'
  }
};

// Log level colors
const LOG_LEVEL_COLORS = {
  debug: 'text-gray-500',
  info: 'text-blue-600',
  warning: 'text-yellow-600',
  error: 'text-red-600',
  critical: 'text-red-800 font-bold'
};

// Component display names and descriptions
const COMPONENT_INFO = {
  web_scraper: {
    name: 'Web Scraper',
    description: 'AWS Spot Advisor data fetching',
    icon: '🌐'
  },
  price_scraper: {
    name: 'Price Scraper',
    description: 'AWS Pricing API integration',
    icon: '💰'
  },
  database: {
    name: 'Database',
    description: 'PostgreSQL operations',
    icon: '🗄️'
  },
  linear_optimizer: {
    name: 'Linear Optimizer',
    description: 'Instance switching decisions',
    icon: '⚡'
  },
  ml_inference: {
    name: 'ML Inference',
    description: 'Model predictions and features',
    icon: '🤖'
  },
  instance_manager: {
    name: 'Instance Manager',
    description: 'EC2 instance tracking',
    icon: '☁️'
  },
  redis_cache: {
    name: 'Redis Cache',
    description: 'Data pipeline caching',
    icon: '🔴'
  },
  api_server: {
    name: 'API Server',
    description: 'FastAPI backend',
    icon: '🚀'
  }
};

const ComponentCard = ({ component, health, logs, onRefresh }) => {
  const info = COMPONENT_INFO[component] || {
    name: component,
    description: '',
    icon: '📊'
  };

  const statusColors = STATUS_COLORS[health?.status || 'unknown'];

  return (
    <div className={`${statusColors.bg} border-l-4 ${statusColors.border} rounded-lg shadow-md p-6 mb-6`}>
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center space-x-3">
          <span className="text-3xl">{info.icon}</span>
          <div>
            <h3 className="text-lg font-bold text-gray-900">{info.name}</h3>
            <p className="text-sm text-gray-600">{info.description}</p>
          </div>
        </div>

        <div className="flex items-center space-x-3">
          {/* Status Badge */}
          <span className={`px-3 py-1 rounded-full text-sm font-medium ${statusColors.badge}`}>
            {health?.status || 'unknown'}
          </span>

          {/* Refresh Button */}
          <button
            onClick={() => onRefresh(component)}
            className="p-2 hover:bg-gray-200 rounded-full transition-colors"
            title="Refresh logs"
          >
            <RefreshCw className="w-4 h-4 text-gray-600" />
          </button>
        </div>
      </div>

      {/* Health Metrics */}
      {health && (
        <div className="grid grid-cols-4 gap-4 mb-4 bg-white bg-opacity-50 rounded-lg p-4">
          <div>
            <p className="text-xs text-gray-600 uppercase">Uptime 24h</p>
            <p className="text-xl font-bold text-gray-900">
              {health.uptime_percentage.toFixed(1)}%
            </p>
          </div>
          <div>
            <p className="text-xs text-gray-600 uppercase">Success / Fail</p>
            <p className="text-xl font-bold text-gray-900">
              <span className="text-green-600">{health.success_count_24h}</span>
              {' / '}
              <span className="text-red-600">{health.failure_count_24h}</span>
            </p>
          </div>
          <div>
            <p className="text-xs text-gray-600 uppercase">Avg Exec Time</p>
            <p className="text-xl font-bold text-gray-900">
              {health.avg_execution_time_ms ? `${health.avg_execution_time_ms}ms` : 'N/A'}
            </p>
          </div>
          <div>
            <p className="text-xs text-gray-600 uppercase">Last Check</p>
            <p className="text-sm font-medium text-gray-900">
              {health.last_check ? new Date(health.last_check).toLocaleTimeString() : 'Never'}
            </p>
          </div>
        </div>
      )}

      {/* Error Message (if any) */}
      {health?.error_message && (
        <div className="bg-red-50 border border-red-200 rounded p-3 mb-4">
          <div className="flex items-start space-x-2">
            <AlertCircle className="w-5 h-5 text-red-500 mt-0.5" />
            <div>
              <p className="text-sm font-medium text-red-800">Last Error:</p>
              <p className="text-sm text-red-700">{health.error_message}</p>
            </div>
          </div>
        </div>
      )}

      {/* Recent Logs */}
      <div>
        <h4 className="text-sm font-bold text-gray-700 uppercase mb-2 flex items-center">
          <Activity className="w-4 h-4 mr-2" />
          Recent Logs (Last 5)
        </h4>

        {logs && logs.length > 0 ? (
          <div className="space-y-2 bg-gray-900 rounded-lg p-4 font-mono text-xs">
            {logs.map((log, idx) => (
              <div key={log.id || idx} className="border-b border-gray-700 last:border-0 pb-2 last:pb-0">
                <div className="flex items-start justify-between space-x-2">
                  <div className="flex-1">
                    <div className="flex items-center space-x-2 mb-1">
                      <span className={`font-bold uppercase ${LOG_LEVEL_COLORS[log.level]}`}>
                        [{log.level}]
                      </span>
                      <span className="text-gray-400 text-xs">
                        {new Date(log.timestamp).toLocaleString()}
                      </span>
                      {log.execution_time_ms && (
                        <span className="text-green-400 text-xs">
                          {log.execution_time_ms}ms
                        </span>
                      )}
                      {log.success && (
                        <span className={`text-xs ${log.success === 'success' ? 'text-green-400' : 'text-red-400'}`}>
                          {log.success === 'success' ? '✓' : '✗'}
                        </span>
                      )}
                    </div>
                    <p className="text-gray-300">{log.message}</p>

                    {/* Log Details (if any) */}
                    {log.details && Object.keys(log.details).length > 0 && (
                      <details className="mt-1">
                        <summary className="text-gray-500 cursor-pointer text-xs">
                          View details
                        </summary>
                        <pre className="text-gray-400 text-xs mt-1 overflow-x-auto">
                          {JSON.stringify(log.details, null, 2)}
                        </pre>
                      </details>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="bg-gray-900 rounded-lg p-4 text-center">
            <p className="text-gray-500 text-sm">No logs available</p>
          </div>
        )}
      </div>
    </div>
  );
};

const SystemMonitor = () => {
  const [overview, setOverview] = useState(null);
  const [componentLogs, setComponentLogs] = useState({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [autoRefresh, setAutoRefresh] = useState(true);

  // Fetch system overview
  const fetchOverview = async () => {
    try {
      const data = await api.getSystemOverview();
      setOverview(data);
      setError(null);
    } catch (err) {
      setError(err.message);
      console.error('Failed to fetch system overview:', err);
    }
  };

  // Fetch logs for a specific component
  const fetchComponentLogs = async (component) => {
    try {
      const data = await api.getComponentLogs(component, 5);
      setComponentLogs(prev => ({
        ...prev,
        [component]: data
      }));
    } catch (err) {
      console.error(`Failed to fetch logs for ${component}:`, err);
    }
  };

  // Fetch all component logs
  const fetchAllLogs = async (components) => {
    const promises = components.map(c => fetchComponentLogs(c.component));
    await Promise.all(promises);
  };

  // Initial load
  useEffect(() => {
    const init = async () => {
      setLoading(true);
      await fetchOverview();
      setLoading(false);
    };
    init();
  }, []);

  // Fetch logs when overview is loaded
  useEffect(() => {
    if (overview?.components) {
      fetchAllLogs(overview.components);
    }
  }, [overview]);

  // Auto-refresh every 30 seconds
  useEffect(() => {
    if (!autoRefresh) return;

    const interval = setInterval(async () => {
      await fetchOverview();
      if (overview?.components) {
        await fetchAllLogs(overview.components);
      }
    }, 30000);

    return () => clearInterval(interval);
  }, [autoRefresh, overview]);

  // Manual refresh
  const handleRefresh = async () => {
    setLoading(true);
    await fetchOverview();
    if (overview?.components) {
      await fetchAllLogs(overview.components);
    }
    setLoading(false);
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-screen">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-500"></div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex items-center justify-center h-screen">
        <div className="bg-red-50 border border-red-200 rounded-lg p-6 max-w-md">
          <div className="flex items-center space-x-3 mb-3">
            <XCircle className="w-6 h-6 text-red-500" />
            <h3 className="text-lg font-bold text-red-900">Error Loading System Status</h3>
          </div>
          <p className="text-red-700 mb-4">{error}</p>
          <button
            onClick={handleRefresh}
            className="bg-red-600 text-white px-4 py-2 rounded hover:bg-red-700 transition-colors"
          >
            Retry
          </button>
        </div>
      </div>
    );
  }

  const overallStatusColors = {
    healthy: 'bg-green-500',
    warning: 'bg-yellow-500',
    critical: 'bg-red-500',
    unknown: 'bg-gray-500'
  };

  return (
    <div className="min-h-screen bg-gray-100 p-6">
      {/* Header */}
      <div className="mb-6">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h1 className="text-3xl font-bold text-gray-900">System Monitor</h1>
            <p className="text-gray-600">Real-time component health and logs</p>
          </div>

          <div className="flex items-center space-x-4">
            {/* Auto-refresh toggle */}
            <label className="flex items-center space-x-2 cursor-pointer">
              <input
                type="checkbox"
                checked={autoRefresh}
                onChange={(e) => setAutoRefresh(e.target.checked)}
                className="form-checkbox h-5 w-5 text-blue-600"
              />
              <span className="text-sm text-gray-700">Auto-refresh (30s)</span>
            </label>

            {/* Manual refresh */}
            <button
              onClick={handleRefresh}
              disabled={loading}
              className="bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700 transition-colors flex items-center space-x-2 disabled:opacity-50"
            >
              <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
              <span>Refresh</span>
            </button>
          </div>
        </div>

        {/* Overall Status */}
        {overview && (
          <div className="bg-white rounded-lg shadow p-6">
            <div className="flex items-center justify-between">
              <div className="flex items-center space-x-4">
                <div className={`w-4 h-4 rounded-full ${overallStatusColors[overview.overall_status]} animate-pulse`}></div>
                <div>
                  <h3 className="text-lg font-bold text-gray-900">Overall Status: <span className="capitalize">{overview.overall_status}</span></h3>
                  <p className="text-sm text-gray-600">
                    {overview.healthy_count} healthy, {overview.degraded_count} degraded, {overview.down_count} down
                  </p>
                </div>
              </div>
              <div className="text-right">
                <p className="text-xs text-gray-500 uppercase">Last Updated</p>
                <p className="text-sm font-medium text-gray-900">
                  {new Date(overview.last_updated).toLocaleString()}
                </p>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Component Cards */}
      <div className="space-y-6">
        {overview?.components.map((component) => (
          <ComponentCard
            key={component.component}
            component={component.component}
            health={component}
            logs={componentLogs[component.component]?.logs || []}
            onRefresh={fetchComponentLogs}
          />
        ))}
      </div>
    </div>
  );
};

export default SystemMonitor;
