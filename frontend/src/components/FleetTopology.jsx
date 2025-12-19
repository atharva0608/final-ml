/**
 * [ARCH-006] Fleet Topology Component
 *
 * Interactive visualization of client cluster topology with two modes:
 * 1. Cycle View - Rotating banner through clusters
 * 2. Live View - Real-time switching animations via WebSocket
 *
 * From realworkflow.md Table 1, Lines 31-33
 */

import React, { useState, useEffect, useRef } from 'react';
import { Activity, RefreshCw, Radio, Layers, Server, Zap, AlertCircle } from 'lucide-react';
import { cn } from '../lib/utils';
import api from '../services/api';

const FleetTopology = ({ clientId }) => {
  const [viewMode, setViewMode] = useState('cycle'); // 'cycle' or 'live'
  const [topology, setTopology] = useState(null);
  const [currentClusterIndex, setCurrentClusterIndex] = useState(0);
  const [liveSwitches, setLiveSwitches] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const wsRef = useRef(null);

  // Fetch topology data
  useEffect(() => {
    fetchTopology();
  }, [clientId]);

  // Cycle View - Rotate through clusters
  useEffect(() => {
    if (viewMode === 'cycle' && topology?.clusters?.length > 0) {
      const interval = setInterval(() => {
        setCurrentClusterIndex((prev) =>
          (prev + 1) % topology.clusters.length
        );
      }, 5000); // Rotate every 5 seconds

      return () => clearInterval(interval);
    }
  }, [viewMode, topology]);

  // Live View - WebSocket connection
  useEffect(() => {
    if (viewMode === 'live') {
      connectWebSocket();
    } else {
      disconnectWebSocket();
    }

    return () => disconnectWebSocket();
  }, [viewMode, clientId]);

  const fetchTopology = async () => {
    setLoading(true);
    setError(null);

    try {
      const data = await api.getClientTopology(clientId);
      setTopology(data);
    } catch (err) {
      console.error('Failed to fetch topology:', err);
      setError('Failed to load topology data');
    } finally {
      setLoading(false);
    }
  };

  const connectWebSocket = () => {
    // WebSocket URL would be configured based on environment
    const wsUrl = `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}/api/v1/ws/client/${clientId}/live-switches`;

    try {
      wsRef.current = new WebSocket(wsUrl);

      wsRef.current.onopen = () => {
        console.log('✓ WebSocket connected for live updates');
      };

      wsRef.current.onmessage = (event) => {
        const data = JSON.parse(event.data);

        if (data.type === 'live_switch') {
          // Add new switch event
          setLiveSwitches((prev) => [
            {
              id: Date.now(),
              ...data.data,
              timestamp: new Date().toISOString()
            },
            ...prev.slice(0, 9) // Keep last 10 events
          ]);
        } else if (data.type === 'cluster_update') {
          // Update topology
          setTopology(data.data);
        }
      };

      wsRef.current.onerror = (error) => {
        console.error('WebSocket error:', error);
      };

      wsRef.current.onclose = () => {
        console.log('WebSocket disconnected');
      };
    } catch (err) {
      console.error('Failed to connect WebSocket:', err);
    }
  };

  const disconnectWebSocket = () => {
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64 bg-white border border-slate-200 rounded-lg">
        <RefreshCw className="w-6 h-6 text-blue-500 animate-spin" />
        <span className="ml-2 text-slate-600">Loading topology...</span>
      </div>
    );
  }

  if (error || !topology) {
    return (
      <div className="flex items-center justify-center h-64 bg-white border border-slate-200 rounded-lg">
        <AlertCircle className="w-6 h-6 text-red-500" />
        <span className="ml-2 text-slate-600">{error || 'No topology data available'}</span>
      </div>
    );
  }

  const currentCluster = topology.clusters[currentClusterIndex];

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between bg-white border border-slate-200 rounded-lg p-4">
        <div className="flex items-center space-x-3">
          <Layers className="w-5 h-5 text-blue-500" />
          <div>
            <h3 className="font-bold text-slate-900">Fleet Topology</h3>
            <p className="text-xs text-slate-500">
              {topology.clusters.length} clusters • {topology.clusters.reduce((sum, c) => sum + c.node_count, 0)} nodes
            </p>
          </div>
        </div>

        {/* View Mode Toggle */}
        <div className="flex items-center space-x-2 bg-slate-100 rounded-lg p-1">
          <button
            onClick={() => setViewMode('cycle')}
            className={cn(
              'px-3 py-1.5 rounded text-sm font-medium transition-colors',
              viewMode === 'cycle'
                ? 'bg-white text-blue-600 shadow-sm'
                : 'text-slate-600 hover:text-slate-900'
            )}
          >
            <RefreshCw className="w-4 h-4 inline mr-1" />
            Cycle View
          </button>
          <button
            onClick={() => setViewMode('live')}
            className={cn(
              'px-3 py-1.5 rounded text-sm font-medium transition-colors',
              viewMode === 'live'
                ? 'bg-white text-blue-600 shadow-sm'
                : 'text-slate-600 hover:text-slate-900'
            )}
          >
            <Radio className="w-4 h-4 inline mr-1" />
            Live View
          </button>
        </div>
      </div>

      {/* Content */}
      {viewMode === 'cycle' ? (
        <CycleView cluster={currentCluster} totalClusters={topology.clusters.length} currentIndex={currentClusterIndex} />
      ) : (
        <LiveView liveSwitches={liveSwitches} topology={topology} />
      )}
    </div>
  );
};

// Cycle View Component
const CycleView = ({ cluster, totalClusters, currentIndex }) => {
  return (
    <div className="bg-white border border-slate-200 rounded-lg p-6 space-y-6">
      {/* Cluster Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center space-x-3">
          <div className="w-12 h-12 bg-blue-100 rounded-lg flex items-center justify-center">
            <Server className="w-6 h-6 text-blue-600" />
          </div>
          <div>
            <h4 className="font-bold text-slate-900">{cluster.cluster_name}</h4>
            <p className="text-sm text-slate-500">{cluster.region} • {cluster.node_count} nodes</p>
          </div>
        </div>
        <div className="text-xs text-slate-400 font-mono">
          {currentIndex + 1} / {totalClusters}
        </div>
      </div>

      {/* Cluster Flow: Cluster → Engines → Nodes */}
      <div className="flex items-center justify-around py-8">
        {/* Cluster */}
        <div className="text-center">
          <div className="w-20 h-20 bg-blue-50 border-2 border-blue-500 rounded-lg flex items-center justify-center mb-2">
            <Layers className="w-10 h-10 text-blue-600" />
          </div>
          <p className="text-xs font-bold text-slate-700">Cluster</p>
          <p className="text-xs text-slate-500">{cluster.cluster_name}</p>
        </div>

        {/* Arrow */}
        <div className="flex flex-col items-center">
          <div className="w-16 h-0.5 bg-slate-300"></div>
          <Zap className="w-4 h-4 text-slate-400 my-1" />
          <div className="w-16 h-0.5 bg-slate-300"></div>
        </div>

        {/* Engines (Mock - in production would show actual engines) */}
        <div className="text-center">
          <div className="w-20 h-20 bg-green-50 border-2 border-green-500 rounded-lg flex items-center justify-center mb-2">
            <Activity className="w-10 h-10 text-green-600" />
          </div>
          <p className="text-xs font-bold text-slate-700">Engines</p>
          <p className="text-xs text-slate-500">{Math.ceil(cluster.node_count / 3)} active</p>
        </div>

        {/* Arrow */}
        <div className="flex flex-col items-center">
          <div className="w-16 h-0.5 bg-slate-300"></div>
          <Zap className="w-4 h-4 text-slate-400 my-1" />
          <div className="w-16 h-0.5 bg-slate-300"></div>
        </div>

        {/* Nodes */}
        <div className="text-center">
          <div className="w-20 h-20 bg-purple-50 border-2 border-purple-500 rounded-lg flex items-center justify-center mb-2">
            <Server className="w-10 h-10 text-purple-600" />
          </div>
          <p className="text-xs font-bold text-slate-700">Nodes</p>
          <p className="text-xs text-slate-500">{cluster.node_count} running</p>
        </div>
      </div>

      {/* Node Grid */}
      <div>
        <h5 className="text-sm font-bold text-slate-700 mb-3">Active Nodes</h5>
        <div className="grid grid-cols-4 gap-2">
          {cluster.nodes.slice(0, 12).map((node, idx) => (
            <div
              key={idx}
              className="bg-slate-50 border border-slate-200 rounded p-2 hover:border-blue-300 transition-colors"
            >
              <div className="flex items-center justify-between mb-1">
                <Server className="w-3 h-3 text-slate-400" />
                <span className={cn(
                  'w-2 h-2 rounded-full',
                  node.status === 'active' ? 'bg-green-500' : 'bg-red-500'
                )}></span>
              </div>
              <p className="text-xs font-mono text-slate-600 truncate">{node.instance_id.slice(0, 10)}...</p>
              <p className="text-[10px] text-slate-400">{node.instance_type}</p>
            </div>
          ))}
        </div>
        {cluster.node_count > 12 && (
          <p className="text-xs text-slate-400 text-center mt-2">
            +{cluster.node_count - 12} more nodes
          </p>
        )}
      </div>
    </div>
  );
};

// Live View Component
const LiveView = ({ liveSwitches, topology }) => {
  return (
    <div className="space-y-4">
      {/* Live Status */}
      <div className="bg-white border border-slate-200 rounded-lg p-4">
        <div className="flex items-center space-x-2">
          <div className="relative flex h-3 w-3">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75"></span>
            <span className="relative inline-flex rounded-full h-3 w-3 bg-green-500"></span>
          </div>
          <span className="text-sm font-medium text-slate-700">Live Updates Active</span>
          <span className="text-xs text-slate-500">• {liveSwitches.length} events in last minute</span>
        </div>
      </div>

      {/* Recent Switches */}
      <div className="bg-white border border-slate-200 rounded-lg p-6">
        <h5 className="text-sm font-bold text-slate-700 mb-4">Recent Switches</h5>

        {liveSwitches.length === 0 ? (
          <div className="text-center py-8 text-slate-400">
            <Zap className="w-8 h-8 mx-auto mb-2 opacity-50" />
            <p className="text-sm">No recent switches. Waiting for events...</p>
          </div>
        ) : (
          <div className="space-y-3">
            {liveSwitches.map((switch_event) => (
              <div
                key={switch_event.id}
                className="flex items-center space-x-4 p-3 bg-blue-50 border border-blue-200 rounded-lg animate-fadeIn"
              >
                <Zap className="w-5 h-5 text-blue-600 flex-shrink-0" />
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-slate-900 truncate">
                    {switch_event.instance_id}
                  </p>
                  <p className="text-xs text-slate-600">
                    <span className="font-mono bg-slate-200 px-1 rounded">{switch_event.from_type}</span>
                    {' → '}
                    <span className="font-mono bg-green-200 px-1 rounded">{switch_event.to_type}</span>
                  </p>
                </div>
                <div className="text-right">
                  <p className="text-[10px] text-slate-400 font-mono">
                    {new Date(switch_event.timestamp).toLocaleTimeString()}
                  </p>
                  <p className="text-[10px] text-slate-500">{switch_event.reason}</p>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Cluster Grid - Real-time status */}
      <div className="grid grid-cols-2 gap-4">
        {topology.clusters.map((cluster) => (
          <div key={cluster.cluster_id} className="bg-white border border-slate-200 rounded-lg p-4">
            <div className="flex items-center justify-between mb-2">
              <h6 className="text-sm font-bold text-slate-700">{cluster.cluster_name}</h6>
              <span className="text-xs bg-green-100 text-green-700 px-2 py-0.5 rounded-full">
                {cluster.node_count} nodes
              </span>
            </div>
            <div className="grid grid-cols-5 gap-1">
              {cluster.nodes.slice(0, 10).map((node, idx) => (
                <div
                  key={idx}
                  className={cn(
                    'w-full aspect-square rounded border-2',
                    node.status === 'active'
                      ? 'bg-green-100 border-green-500'
                      : 'bg-red-100 border-red-500'
                  )}
                  title={node.instance_id}
                ></div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};

export default FleetTopology;
