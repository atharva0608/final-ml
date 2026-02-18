import React, { useState, useEffect } from 'react';
import {
  FiActivity, FiDollarSign, FiCpu, FiZap, FiRefreshCw,
  FiSettings, FiPause, FiPlay, FiCheck, FiX, FiChevronDown,
  FiServer, FiTrendingUp, FiGrid, FiLayers, FiAlertCircle
} from 'react-icons/fi';
import { karpenterAPI } from '../../services/api';
import ManualRightSizing from './ManualRightSizing';

// ==================== CONSTANTS ====================

const STRATEGIES = [
  { id: 'cost', label: 'Cost-First', desc: 'Max savings, more churn' },
  { id: 'balanced', label: 'Balanced', desc: 'Recommended - cost + stability' },
  { id: 'performance', label: 'Performance-First', desc: 'Stable, less churn' }
];

// ==================== COMPONENTS ====================

// KPI Card
const KPICard = ({ label, value, sub, color, accent }) => {
  return (
    <div
      className="bg-white border border-gray-200 rounded-xl p-4"
      style={{ borderTopWidth: '3px', borderTopColor: accent || color }}
    >
      <div className="text-xs font-bold uppercase tracking-wide text-gray-500 mb-1">
        {label}
      </div>
      <div className="text-2xl font-extrabold tracking-tight mb-0.5" style={{ color }}>
        {value}
      </div>
      <div className="text-xs text-gray-500">{sub}</div>
    </div>
  );
};

// Karpenter Status Card - OFF State
const KarpenterOff = ({ onEnable }) => {
  return (
    <div className="bg-white border border-gray-200 rounded-xl overflow-hidden">
      <div className="px-5 py-4 border-b border-gray-200 flex justify-between items-center">
        <div className="flex items-center gap-3">
          <FiZap size={18} className="text-gray-900" />
          <span className="text-sm font-bold uppercase tracking-wide text-gray-900">
            KARPENTER AUTO-SIZING
          </span>
        </div>
        <div className="flex items-center gap-3">
          <span className="flex items-center gap-2 px-3 py-1 bg-gray-100 text-gray-600 rounded-full text-xs font-semibold">
            <div className="w-2 h-2 rounded-full bg-gray-400" />
            OFF
          </span>
          <button
            onClick={onEnable}
            className="flex items-center gap-2 px-4 py-2 bg-indigo-600 text-white rounded-lg text-sm font-semibold hover:bg-indigo-700 transition-colors"
          >
            Enable
          </button>
        </div>
      </div>

      <div className="px-5 py-6">
        <div className="text-sm text-gray-700 mb-3">
          Automatic right-sizing: 30-50% cost reduction, 75%+ utilization
        </div>
        <div className="text-sm text-gray-500 mb-4">
          Currently using manual mode - recommendations shown below
        </div>
        <div className="flex gap-3">
          <button className="text-xs font-medium text-indigo-600 hover:text-indigo-700 underline">
            Learn More
          </button>
          <button className="text-xs font-medium text-indigo-600 hover:text-indigo-700 underline">
            Quick Start Guide
          </button>
        </div>
      </div>
    </div>
  );
};

// Karpenter Enable Form - Inline Configuration
const KarpenterEnableForm = ({ clusters, onCancel, onSubmit }) => {
  const [selected, setSelected] = useState([]);
  const [strategy, setStrategy] = useState('balanced');
  const [spotTarget, setSpotTarget] = useState(75);
  const [architectures, setArchitectures] = useState(['amd64', 'arm64']);

  const handleToggleCluster = (clusterId) => {
    setSelected(prev =>
      prev.includes(clusterId)
        ? prev.filter(id => id !== clusterId)
        : [...prev, clusterId]
    );
  };

  const handleSubmit = () => {
    onSubmit({ clusters: selected, strategy, spotTarget, architectures });
  };

  const totalSavings = selected.length * 1200; // Estimate per cluster

  return (
    <div className="bg-white border border-gray-200 rounded-xl overflow-hidden">
      <div className="px-5 py-4 bg-gray-50 border-b border-gray-200 flex justify-between items-center">
        <span className="text-sm font-bold uppercase tracking-wide text-gray-900">
          ENABLE KARPENTER
        </span>
        <div className="flex gap-2">
          <button
            onClick={onCancel}
            className="px-4 py-2 text-sm font-medium text-gray-700 hover:text-gray-900 transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={handleSubmit}
            disabled={selected.length === 0}
            className="flex items-center gap-2 px-4 py-2 bg-indigo-600 text-white rounded-lg text-sm font-semibold hover:bg-indigo-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            Turn On
          </button>
        </div>
      </div>

      <div className="p-5 space-y-6">
        {/* Cluster Selection */}
        <div>
          <div className="text-xs font-bold uppercase tracking-wide text-gray-600 mb-3">
            Select Clusters
          </div>
          <div className="space-y-2">
            {clusters.map(cluster => (
              <label
                key={cluster.id}
                className="flex items-center gap-3 p-3 border border-gray-200 rounded-lg hover:bg-gray-50 cursor-pointer transition-colors"
              >
                <input
                  type="checkbox"
                  checked={selected.includes(cluster.id)}
                  onChange={() => handleToggleCluster(cluster.id)}
                  className="w-4 h-4 text-indigo-600 rounded"
                />
                <div className="flex-1 flex items-center justify-between">
                  <div>
                    <span className="text-sm font-semibold text-gray-900">{cluster.name}</span>
                    <span className="text-xs text-gray-500 ml-2">{cluster.nodes} nodes</span>
                  </div>
                  <span className="text-sm font-medium text-green-600">
                    Est. savings: +${(cluster.nodes * 40).toLocaleString()}/mo (30%)
                  </span>
                </div>
              </label>
            ))}
          </div>
        </div>

        {/* Strategy Selection */}
        <div>
          <div className="text-xs font-bold uppercase tracking-wide text-gray-600 mb-3">
            Strategy (applies to all selected clusters)
          </div>
          <div className="space-y-2">
            {STRATEGIES.map(s => (
              <label
                key={s.id}
                className="flex items-center gap-3 p-3 border border-gray-200 rounded-lg hover:bg-gray-50 cursor-pointer transition-colors"
              >
                <input
                  type="radio"
                  name="strategy"
                  value={s.id}
                  checked={strategy === s.id}
                  onChange={(e) => setStrategy(e.target.value)}
                  className="w-4 h-4 text-indigo-600"
                />
                <div>
                  <div className="text-sm font-semibold text-gray-900">{s.label}</div>
                  <div className="text-xs text-gray-500">{s.desc}</div>
                </div>
              </label>
            ))}
          </div>
        </div>

        {/* Quick Settings */}
        <div>
          <div className="text-xs font-bold uppercase tracking-wide text-gray-600 mb-3">
            Quick Settings
          </div>
          <div className="flex items-center gap-6">
            <div className="flex-1">
              <label className="text-xs text-gray-600 mb-2 block">
                Spot Target: {spotTarget}%
              </label>
              <input
                type="range"
                min="0"
                max="100"
                value={spotTarget}
                onChange={(e) => setSpotTarget(parseInt(e.target.value))}
                className="w-full"
              />
            </div>
            <div>
              <label className="text-xs text-gray-600 mb-2 block">Architecture</label>
              <div className="flex gap-3">
                <label className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    checked={architectures.includes('amd64')}
                    onChange={(e) => {
                      if (e.target.checked) {
                        setArchitectures([...architectures, 'amd64']);
                      } else {
                        setArchitectures(architectures.filter(a => a !== 'amd64'));
                      }
                    }}
                    className="w-4 h-4 text-indigo-600 rounded"
                  />
                  <span className="text-sm text-gray-700">AMD64</span>
                </label>
                <label className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    checked={architectures.includes('arm64')}
                    onChange={(e) => {
                      if (e.target.checked) {
                        setArchitectures([...architectures, 'arm64']);
                      } else {
                        setArchitectures(architectures.filter(a => a !== 'arm64'));
                      }
                    }}
                    className="w-4 h-4 text-indigo-600 rounded"
                  />
                  <span className="text-sm text-gray-700">ARM64</span>
                </label>
              </div>
            </div>
          </div>
        </div>

        {/* Total Savings */}
        <div className="pt-4 border-t border-gray-200">
          <div className="text-sm font-bold text-gray-900">
            Total Est. Savings: <span className="text-green-600">${totalSavings.toLocaleString()}/mo</span>
            <span className="text-xs font-normal text-gray-500 ml-2">({selected.length} clusters)</span>
          </div>
        </div>
      </div>
    </div>
  );
};

// Karpenter Active Dashboard
const KarpenterActive = ({ stats, activity, clusters, onOpenSettings, onPause }) => {
  const totalNodes = clusters.reduce((sum, c) => sum + (c.nodes || 0), 0);
  const lastAction = activity[0];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="bg-white border border-gray-200 rounded-xl overflow-hidden">
        <div className="px-5 py-4 border-b border-gray-200 flex justify-between items-center">
          <div className="flex items-center gap-3">
            <FiZap size={18} className="text-gray-900" />
            <span className="text-sm font-bold uppercase tracking-wide text-gray-900">
              KARPENTER AUTO-SIZING
            </span>
          </div>
          <div className="flex items-center gap-3">
            <span className="flex items-center gap-2 px-3 py-1 bg-green-50 text-green-700 rounded-full text-xs font-semibold border border-green-200">
              <div className="w-2 h-2 rounded-full bg-green-500 animate-pulse" />
              ON
            </span>
            <button
              onClick={onOpenSettings}
              className="flex items-center gap-2 px-3 py-2 bg-white border border-gray-300 rounded-lg text-sm font-medium text-gray-700 hover:bg-gray-50 transition-colors"
            >
              <FiSettings size={14} />
              Settings
            </button>
            <button
              onClick={onPause}
              className="flex items-center gap-2 px-3 py-2 bg-white border border-gray-300 rounded-lg text-sm font-medium text-gray-700 hover:bg-gray-50 transition-colors"
            >
              <FiPause size={14} />
              Pause
            </button>
          </div>
        </div>

        <div className="px-5 py-3 bg-gray-50 border-b border-gray-200 text-sm text-gray-600">
          Active on {clusters.length} clusters • {totalNodes} nodes managed • Last action: {lastAction ? new Date(lastAction.timestamp).toLocaleTimeString() : 'N/A'}
        </div>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-4 gap-4">
        <KPICard
          label="AVG UTIL"
          value={`${stats.avgUtil}%`}
          sub={`↑ from ${stats.prevUtil}%`}
          color="#6366f1"
          accent="#6366f1"
        />
        <KPICard
          label="OPTIMIZATIONS"
          value={stats.optimizations}
          sub="auto-sizes"
          color="#8b5cf6"
          accent="#8b5cf6"
        />
        <KPICard
          label="SAVED THIS WEEK"
          value={`$${stats.savedWeek.toLocaleString()}`}
          sub="vs manual"
          color="#22c55e"
          accent="#22c55e"
        />
        <KPICard
          label="SPOT COVERAGE"
          value={`${stats.spotCoverage}%`}
          sub="of nodes"
          color="#f59e0b"
          accent="#f59e0b"
        />
      </div>

      {/* Recent Actions */}
      <div className="bg-white border border-gray-200 rounded-xl overflow-hidden">
        <div className="px-5 py-4 border-b border-gray-200 flex justify-between items-center">
          <span className="text-sm font-bold uppercase tracking-wide text-gray-900">
            RECENT ACTIONS (Last 6h)
          </span>
          <button className="text-xs font-medium text-indigo-600 hover:text-indigo-700 transition-colors">
            View All →
          </button>
        </div>

        <div className="divide-y divide-gray-100">
          {activity.slice(0, 3).map((action, idx) => (
            <div key={idx} className="px-5 py-3 hover:bg-gray-50 transition-colors">
              <div className="flex items-start gap-3">
                <div className="w-2 h-2 rounded-full bg-green-500 mt-2 flex-shrink-0" />
                <div className="flex-1 min-w-0">
                  <div className="text-sm text-gray-700">{action.description}</div>
                  <div className="text-xs text-gray-500 mt-0.5">
                    {action.cluster} • {action.time}
                  </div>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Active Clusters */}
      <div className="bg-white border border-gray-200 rounded-xl overflow-hidden">
        <div className="px-5 py-4 border-b border-gray-200 flex justify-between items-center">
          <span className="text-sm font-bold uppercase tracking-wide text-gray-900">
            ACTIVE CLUSTERS
          </span>
          <button
            onClick={onOpenSettings}
            className="text-xs font-medium text-indigo-600 hover:text-indigo-700 transition-colors"
          >
            Manage →
          </button>
        </div>

        <div className="px-5 py-4">
          <div className="flex flex-wrap gap-3">
            {clusters.map(cluster => (
              <div
                key={cluster.id}
                className="flex items-center gap-2 px-3 py-2 bg-gray-50 rounded-lg border border-gray-200"
              >
                <div className="w-2 h-2 rounded-full bg-green-500" />
                <span className="text-sm font-medium text-gray-900">{cluster.name}</span>
                <span className="text-xs text-gray-500">
                  ({cluster.nodes} nodes, {cluster.utilization}% util)
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
};

// ==================== MAIN COMPONENT ====================

const RightSizingNew = () => {
  const [mode, setMode] = useState('manual'); // 'manual' | 'karpenter'
  const [karpenterState, setKarpenterState] = useState('off'); // 'off' | 'enabling' | 'active' | 'paused'
  const [loading, setLoading] = useState(false);

  // Mock data
  const mockClusters = [
    { id: '1', name: 'prod-web', nodes: 12, utilization: 82 },
    { id: '2', name: 'prod-api', nodes: 18, utilization: 75 },
    { id: '3', name: 'staging', nodes: 5, utilization: 60 },
    { id: '4', name: 'dev-cluster', nodes: 3, utilization: 55 }
  ];

  const mockStats = {
    avgUtil: 78,
    prevUtil: 45,
    optimizations: 38,
    savedWeek: 1240,
    spotCoverage: 82
  };

  const mockActivity = [
    {
      id: 1,
      description: 'Consolidated 3 m5.xlarge → 2 c6i.large (saved $42/day)',
      cluster: 'prod-web',
      time: '3 min ago',
      timestamp: new Date()
    },
    {
      id: 2,
      description: 'Switched r5.2xlarge → r6g.2xlarge Graviton (-$68/day)',
      cluster: 'prod-api',
      time: '12 min ago',
      timestamp: new Date()
    },
    {
      id: 3,
      description: 'Replaced spot interruption in 12 sec (zero downtime)',
      cluster: 'prod-web',
      time: '45 min ago',
      timestamp: new Date()
    }
  ];

  const handleEnableKarpenter = () => {
    setKarpenterState('enabling');
  };

  const handleCancelEnable = () => {
    setKarpenterState('off');
  };

  const handleSubmitEnable = (config) => {
    console.log('Enabling Karpenter with config:', config);
    setKarpenterState('active');
  };

  const handlePause = () => {
    setKarpenterState('paused');
  };

  const handleOpenSettings = () => {
    console.log('Opening settings');
  };

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Top Bar */}
      <div className="bg-white border-b border-gray-200 px-8 py-5 sticky top-0 z-30">
        <div className="flex justify-between items-center">
          <div>
            <h1 className="text-xl font-bold text-gray-900 tracking-tight">
              Right-Sizing Dashboard
            </h1>
            <p className="text-sm text-gray-500 mt-1">
              Optimize instance types and reduce infrastructure costs
            </p>
          </div>

          {/* Mode Switcher */}
          <div className="bg-gray-100 p-1 rounded-lg flex items-center gap-1">
            <button
              onClick={() => setMode('manual')}
              className={`flex items-center gap-2 px-4 py-2 rounded-md text-sm font-medium transition-all ${
                mode === 'manual'
                  ? 'bg-white text-gray-900 shadow-sm'
                  : 'text-gray-600 hover:text-gray-900'
              }`}
            >
              <FiGrid size={16} />
              Manual Recommendations
            </button>
            <button
              onClick={() => setMode('karpenter')}
              className={`flex items-center gap-2 px-4 py-2 rounded-md text-sm font-medium transition-all ${
                mode === 'karpenter'
                  ? 'bg-white text-indigo-600 shadow-sm'
                  : 'text-gray-600 hover:text-gray-900'
              }`}
            >
              <FiLayers size={16} />
              Karpenter Auto-Sizing
            </button>
          </div>
        </div>
      </div>

      {/* Content */}
      <div className="px-8 py-6 max-w-[1600px] mx-auto">
        {mode === 'manual' ? (
          <div className="space-y-6">
            <KarpenterOff onEnable={handleEnableKarpenter} />
            <ManualRightSizing />
          </div>
        ) : (
          <div>
            {karpenterState === 'off' && (
              <div className="space-y-6">
                <KarpenterOff onEnable={handleEnableKarpenter} />
                <div className="text-center py-12 text-gray-500">
                  Enable Karpenter to see the auto-sizing dashboard
                </div>
              </div>
            )}
            {karpenterState === 'enabling' && (
              <KarpenterEnableForm
                clusters={mockClusters}
                onCancel={handleCancelEnable}
                onSubmit={handleSubmitEnable}
              />
            )}
            {karpenterState === 'active' && (
              <KarpenterActive
                stats={mockStats}
                activity={mockActivity}
                clusters={mockClusters.slice(0, 2)}
                onOpenSettings={handleOpenSettings}
                onPause={handlePause}
              />
            )}
          </div>
        )}
      </div>
    </div>
  );
};

export default RightSizingNew;
