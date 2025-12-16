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
  const [showLogs, setShowLogs] = useState(true);

  return (
    <div className={`bg-white border border-slate-200 rounded-xl shadow-sm hover:shadow-md transition-all duration-300 overflow-hidden flex flex-col h-full ring-1 ring-slate-900/5`}>
      {/* Header with Status Strip */}
      <div className={`h-1 w-full ${statusColors.bg.replace('bg-', 'bg-').replace('50', '500')}`}></div>

      <div className="p-5 flex-1 flex flex-col">
        <div className="flex items-start justify-between mb-6">
          <div className="flex items-start space-x-4">
            <div className={`p-3 rounded-lg ${statusColors.bg} ${statusColors.text} ring-1 ring-inset ring-black/5`}>
              <span className="text-2xl">{info.icon}</span>
            </div>
            <div>
              <h3 className="text-lg font-bold text-slate-900 leading-tight">{info.name}</h3>
              <p className="text-xs font-medium text-slate-500 mt-1">{info.description}</p>
            </div>
          </div>
          <div className={`flex items-center space-x-2 px-2.5 py-1 rounded-full text-xs font-bold uppercase tracking-wider ${statusColors.badge}`}>
            <div className={`w-1.5 h-1.5 rounded-full bg-current animate-pulse`} />
            <span>{health?.status || 'unknown'}</span>
          </div>
        </div>

        {/* Health Metrics Grid */}
        {health && (
          <div className="grid grid-cols-2 gap-3 mb-6">
            <div className="p-3 bg-slate-50 rounded-lg border border-slate-100">
              <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider block mb-1">Uptime (24h)</span>
              <span className="text-lg font-mono font-bold text-slate-700">{health.uptime_percentage.toFixed(1)}%</span>
            </div>
            <div className="p-3 bg-slate-50 rounded-lg border border-slate-100">
              <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider block mb-1">Avg Latency</span>
              <span className="text-lg font-mono font-bold text-slate-700">
                {health.avg_execution_time_ms ? `${health.avg_execution_time_ms}ms` : '-'}
              </span>
            </div>
            <div className="p-3 bg-slate-50 rounded-lg border border-slate-100 col-span-2 flex items-center justify-between">
              <div>
                <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider block mb-1">Success Rate</span>
                <div className="flex items-baseline space-x-1">
                  <span className="text-lg font-mono font-bold text-emerald-600">{health.success_count_24h}</span>
                  <span className="text-xs text-slate-400">/</span>
                  <span className="text-sm font-mono font-medium text-slate-500">{health.success_count_24h + health.failure_count_24h}</span>
                </div>
              </div>
              {health.failure_count_24h > 0 && (
                <div className="px-2 py-1 bg-red-100 text-red-700 text-xs font-bold rounded">
                  {health.failure_count_24h} Faulures
                </div>
              )}
            </div>
          </div>
        )}

        {/* Logs Section */}
        <div className="mt-auto">
          <div className="flex items-center justify-between mb-2">
            <button
              onClick={() => setShowLogs(!showLogs)}
              className="flex items-center text-xs font-bold text-slate-500 uppercase tracking-wider hover:text-slate-800 transition-colors"
            >
              <Activity className="w-3 h-3 mr-1.5" />
              Recent Activity
            </button>
            <button
              onClick={() => onRefresh(component)}
              className="p-1.5 text-slate-400 hover:text-indigo-600 hover:bg-indigo-50 rounded-md transition-all"
              title="Refresh logs"
            >
              <RefreshCw className="w-3.5 h-3.5" />
            </button>
          </div>

          {showLogs && (
            <div className="bg-slate-900 rounded-lg border border-slate-800 overflow-hidden flex flex-col">
              <div className="flex items-center px-3 py-1.5 bg-slate-950 border-b border-slate-800">
                <div className="flex space-x-1.5">
                  <div className="w-2 h-2 rounded-full bg-slate-700"></div>
                  <div className="w-2 h-2 rounded-full bg-slate-700"></div>
                  <div className="w-2 h-2 rounded-full bg-slate-700"></div>
                </div>
                <span className="ml-auto text-[10px] text-slate-600 font-mono">bash</span>
              </div>
              <div className="p-3 space-y-2 font-mono text-[10px] h-48 overflow-y-auto scrollbar-thin scrollbar-thumb-slate-700 scrollbar-track-transparent">
                {logs && logs.length > 0 ? (
                  logs.slice(0, 20).map((log, idx) => ( // Show max 20 logs in card
                    <div key={log.id || idx} className="flex flex-col border-b border-slate-800/50 last:border-0 pb-1 last:pb-0">
                      <div className="flex items-start">
                        <span className={`mr-2 font-bold ${LOG_LEVEL_COLORS[log.level]}`}>
                          {log.level === 'info' ? '➜' : log.level === 'error' ? '✖' : '•'}
                        </span>
                        <span className="text-slate-300 flex-1 break-all">{log.message}</span>
                      </div>
                      <div className="flex items-center mt-0.5 ml-4 space-x-2 opacity-50">
                        <span className="text-slate-500">{new Date(log.timestamp).toLocaleTimeString()}</span>
                        {log.execution_time_ms && <span className="text-slate-600">{log.execution_time_ms}ms</span>}
                      </div>
                    </div>
                  ))
                ) : (
                  <span className="text-slate-600 italic">waiting for logs...</span>
                )}
              </div>
            </div>
          )}
        </div>
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
      // Fallback to show UI even if backend is down
      setOverview({
        overall_status: 'critical',
        healthy_count: 0,
        degraded_count: 0,
        down_count: Object.keys(COMPONENT_INFO).length,
        last_updated: new Date().toISOString(),
        components: Object.keys(COMPONENT_INFO).map(key => ({
          component: key,
          status: 'down', // Default to down
          uptime_percentage: 0,
          success_count_24h: 0,
          failure_count_24h: 0,
          avg_execution_time_ms: 0,
          last_check: null,
          error_message: 'Backend Unreachable'
        }))
      });
    }
  };

  // Fetch logs for a specific component
  const fetchComponentLogs = async (component) => {
    try {
      const data = await api.getComponentLogs(component, 50);
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



  const overallStatusColors = {
    healthy: 'bg-green-500',
    warning: 'bg-yellow-500',
    critical: 'bg-red-500',
    unknown: 'bg-gray-500'
  };

  return (
    <div className="min-h-screen bg-slate-50 p-8">
      {/* Header & Stats Dashboard */}
      <div className="mb-8">
        <div className="flex flex-col md:flex-row md:items-center justify-between mb-8">
          <div>
            <h1 className="text-3xl font-black text-slate-900 tracking-tight">System Monitor</h1>
            <p className="text-slate-500 mt-1 font-medium">Real-time infrastructure & pipeline observability</p>
          </div>

          <div className="flex items-center space-x-4 mt-4 md:mt-0">
            {/* Auto-refresh toggle */}
            <label className="flex items-center space-x-3 cursor-pointer bg-white px-4 py-2 rounded-full border border-slate-200 shadow-sm hover:border-slate-300 transition-colors">
              <div className={`w-2 h-2 rounded-full ${autoRefresh ? 'bg-green-500 animate-pulse' : 'bg-slate-300'}`}></div>
              <input
                type="checkbox"
                checked={autoRefresh}
                onChange={(e) => setAutoRefresh(e.target.checked)}
                className="hidden"
              />
              <span className="text-sm font-bold text-slate-600">Auto-refresh</span>
            </label>

            <button
              onClick={handleRefresh}
              disabled={loading}
              className="bg-indigo-600 text-white px-5 py-2 rounded-full hover:bg-indigo-700 transition-all shadow-md hover:shadow-lg flex items-center font-bold text-sm disabled:opacity-50 disabled:shadow-none"
            >
              <RefreshCw className={`w-4 h-4 mr-2 ${loading ? 'animate-spin' : ''}`} />
              Refresh
            </button>
          </div>
        </div>

        {/* Connection Error Alert */}
        {error && (
          <div className="bg-red-50 border border-red-200 p-4 mb-8 rounded-xl flex items-center justify-between shadow-sm animate-in slide-in-from-top-2">
            <div className="flex items-center">
              <div className="p-2 bg-red-100 rounded-lg mr-3">
                <AlertCircle className="w-5 h-5 text-red-600" />
              </div>
              <div>
                <p className="font-bold text-red-900">System Connection Error</p>
                <p className="text-sm text-red-700">{error} - Displaying offline mode</p>
              </div>
            </div>
            <button onClick={handleRefresh} className="px-4 py-2 bg-white border border-red-200 text-red-700 hover:bg-red-50 font-bold rounded-lg text-sm transition-colors shadow-sm">Retry Connection</button>
          </div>
        )}

        {/* Stat Cards */}
        {overview && (
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            <div className="bg-white p-6 rounded-2xl border border-slate-100 shadow-sm relative overflow-hidden group hover:shadow-md transition-all">
              <div className="absolute right-0 top-0 p-4 opacity-10 group-hover:opacity-20 transition-opacity">
                <CheckCircle className="w-24 h-24 text-teal-500" />
              </div>
              <p className="text-sm font-bold text-slate-400 uppercase tracking-wider mb-1">Healthy Components</p>
              <div className="flex items-baseline space-x-2">
                <h3 className="text-4xl font-black text-slate-900">{overview.healthy_count}</h3>
                <span className="text-sm font-bold text-teal-600 bg-teal-50 px-2 py-0.5 rounded-full">Operational</span>
              </div>
            </div>

            <div className="bg-white p-6 rounded-2xl border border-slate-100 shadow-sm relative overflow-hidden group hover:shadow-md transition-all">
              <div className="absolute right-0 top-0 p-4 opacity-10 group-hover:opacity-20 transition-opacity">
                <Activity className="w-24 h-24 text-amber-500" />
              </div>
              <p className="text-sm font-bold text-slate-400 uppercase tracking-wider mb-1">Degraded</p>
              <div className="flex items-baseline space-x-2">
                <h3 className="text-4xl font-black text-slate-900">{overview.degraded_count}</h3>
                <span className="text-sm font-bold text-amber-600 bg-amber-50 px-2 py-0.5 rounded-full">Warning</span>
              </div>
            </div>

            <div className="bg-white p-6 rounded-2xl border border-slate-100 shadow-sm relative overflow-hidden group hover:shadow-md transition-all">
              <div className="absolute right-0 top-0 p-4 opacity-10 group-hover:opacity-20 transition-opacity">
                <XCircle className="w-24 h-24 text-rose-500" />
              </div>
              <p className="text-sm font-bold text-slate-400 uppercase tracking-wider mb-1">Critical / Down</p>
              <div className="flex items-baseline space-x-2">
                <h3 className="text-4xl font-black text-slate-900">{overview.down_count}</h3>
                <span className="text-sm font-bold text-rose-600 bg-rose-50 px-2 py-0.5 rounded-full">Action Req.</span>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Component Grid */}
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
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

      {/* Footer Info */}
      {overview && (
        <div className="mt-8 text-center text-xs font-medium text-slate-400">
          Last updated: {new Date(overview.last_updated).toLocaleString()} • ID: {Math.random().toString(36).substr(2, 9)}
        </div>
      )}
    </div>
  );
};

export default SystemMonitor;
