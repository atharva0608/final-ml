import React, { useState, useEffect, useCallback } from 'react';
import { Copy, RefreshCw, AlertTriangle, CheckCircle, XCircle, ArrowRight, Trash2 } from 'lucide-react';
import LoadingSpinner from '../../common/LoadingSpinner';
import ErrorMessage from '../../common/ErrorMessage';
import EmptyState from '../../common/EmptyState';
import Badge from '../../common/Badge';
import Button from '../../common/Button';
import api from '../../../services/api';

const ClientReplicasTab = ({ clientId }) => {
  const [replicas, setReplicas] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [actionLoading, setActionLoading] = useState(null);
  const [copiedId, setCopiedId] = useState(null);

  const loadReplicas = useCallback(async (showLoadingSpinner = true) => {
    if (showLoadingSpinner) {
      setLoading(true);
    }
    setError(null);
    try {
      const data = await api.getClientReplicas(clientId);
      setReplicas(data);
    } catch (err) {
      setError(err.message);
    } finally {
      if (showLoadingSpinner) {
        setLoading(false);
      }
    }
  }, [clientId]);

  useEffect(() => {
    loadReplicas(true); // Initial load with spinner
    // Auto-refresh every 10 seconds for live replica status updates (without spinner)
    const interval = setInterval(() => loadReplicas(false), 10000);
    return () => clearInterval(interval);
  }, [loadReplicas]);

  const handleCopyInstanceId = async (instanceId) => {
    try {
      await navigator.clipboard.writeText(instanceId);
      setCopiedId(instanceId);
      setTimeout(() => setCopiedId(null), 2000);
    } catch (err) {
      console.error('Failed to copy:', err);
      alert('Failed to copy to clipboard');
    }
  };

  const handleSwitchToReplica = async (agentId, replicaId) => {
    if (!window.confirm('Switch to this replica? This will promote the replica to become the primary instance.')) {
      return;
    }

    setActionLoading(`switch-${replicaId}`);
    try {
      await api.promoteReplica(agentId, replicaId);
      alert('✓ Successfully switched to replica! The replica is now your primary instance.');
      await loadReplicas(false); // Refresh without spinner
    } catch (error) {
      alert(`✗ Failed to switch to replica: ${error.message}`);
    } finally {
      setActionLoading(null);
    }
  };

  const handleTerminateReplica = async (agentId, replicaId) => {
    if (!window.confirm('Terminate this replica? This action cannot be undone. Note: If manual replica mode is enabled, a new replica will be created.')) {
      return;
    }

    setActionLoading(`terminate-${replicaId}`);
    try {
      await api.deleteReplica(agentId, replicaId);
      alert('✓ Replica terminated successfully');
      await loadReplicas(false); // Refresh without spinner
    } catch (error) {
      alert(`✗ Failed to terminate replica: ${error.message}`);
    } finally {
      setActionLoading(null);
    }
  };

  const getStatusBadge = (status) => {
    const statusMap = {
      'launching': { variant: 'warning', label: 'Launching', icon: <RefreshCw size={12} className="animate-spin" /> },
      'syncing': { variant: 'info', label: 'Syncing', icon: <RefreshCw size={12} className="animate-spin" /> },
      'ready': { variant: 'success', label: '✓ Done', icon: <CheckCircle size={12} /> },
      'promoted': { variant: 'secondary', label: 'Promoted', icon: null },
      'terminated': { variant: 'danger', label: 'Terminated', icon: <XCircle size={12} /> },
      'failed': { variant: 'danger', label: 'Failed', icon: <XCircle size={12} /> }
    };
    const config = statusMap[status] || { variant: 'secondary', label: status, icon: null };
    return (
      <Badge variant={config.variant}>
        {config.icon && <span className="inline-flex items-center mr-1">{config.icon}</span>}
        {config.label}
      </Badge>
    );
  };

  const getSyncStatusIcon = (syncStatus) => {
    const iconMap = {
      'synced': <CheckCircle size={16} className="text-green-600" />,
      'syncing': <RefreshCw size={16} className="text-blue-600 animate-spin" />,
      'out-of-sync': <AlertTriangle size={16} className="text-amber-600" />,
      'initializing': <RefreshCw size={16} className="text-gray-400 animate-spin" />
    };
    return iconMap[syncStatus] || <AlertTriangle size={16} className="text-gray-400" />;
  };

  const getReplicaTypeLabel = (type) => {
    const labels = {
      'manual': 'Manual',
      'automatic-rebalance': 'Auto (Rebalance)',
      'automatic-termination': 'Auto (Termination)'
    };
    return labels[type] || type;
  };

  if (error) {
    return <ErrorMessage message={error} onRetry={() => loadReplicas(true)} />;
  }

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="bg-white p-4 rounded-xl shadow-sm border border-gray-200">
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
          <div>
            <h3 className="text-lg font-bold text-gray-900">Instance Replicas</h3>
            <p className="text-sm text-gray-500 mt-1">
              Standby instances that can be promoted to primary in case of interruption
            </p>
          </div>
          <Button variant="outline" size="sm" icon={<RefreshCw size={16} />} onClick={() => loadReplicas(true)}>
            Refresh
          </Button>
        </div>
      </div>

      {/* Replicas List */}
      {loading ? (
        <div className="bg-white p-12 rounded-xl shadow-sm border border-gray-200 flex justify-center">
          <LoadingSpinner />
        </div>
      ) : replicas.length === 0 ? (
        <EmptyState
          icon={<Copy size={48} />}
          title="No Replicas Found"
          description="No instances currently have active replicas. Enable manual replica mode in agent configuration to create one."
        />
      ) : (
        <div className="space-y-6">
          {replicas.map((item) => (
            <div key={item.replica.id} className="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden">
              {/* Primary Instance Section */}
              <div className="bg-gradient-to-r from-blue-50 to-white p-4 border-b border-gray-200">
                <div className="flex items-start justify-between">
                  <div>
                    <div className="flex items-center space-x-2 mb-2">
                      <h4 className="text-sm font-semibold text-gray-700 uppercase">Primary Instance</h4>
                      <Badge variant="primary">Active</Badge>
                    </div>
                    <div className="flex items-center space-x-2 mb-1">
                      <p className="text-sm font-mono text-gray-900">{item.primary.instanceId}</p>
                      <button
                        onClick={() => handleCopyInstanceId(item.primary.instanceId)}
                        className="p-1 hover:bg-gray-200 rounded transition-colors"
                        title="Copy instance ID"
                      >
                        <Copy size={14} className={copiedId === item.primary.instanceId ? 'text-green-600' : 'text-gray-500'} />
                      </button>
                    </div>
                    <div className="flex flex-wrap items-center gap-3 text-xs text-gray-600">
                      <span>Type: <span className="font-semibold">{item.primary.instanceType}</span></span>
                      <span>•</span>
                      <span>Region: <span className="font-semibold">{item.primary.region}</span></span>
                      <span>•</span>
                      <span>AZ: <span className="font-semibold">{item.primary.az}</span></span>
                      <span>•</span>
                      <span>Mode: <Badge variant={item.primary.mode === 'spot' ? 'info' : 'secondary'} size="sm">{item.primary.mode}</Badge></span>
                    </div>
                  </div>
                </div>
              </div>

              {/* Arrow Separator */}
              <div className="flex justify-center py-2 bg-gray-50">
                <ArrowRight size={24} className="text-gray-400" />
              </div>

              {/* Replica Instance Section */}
              <div className="bg-gradient-to-r from-green-50 to-white p-4">
                <div className="flex items-start justify-between mb-4">
                  <div className="flex-1">
                    <div className="flex items-center space-x-2 mb-2">
                      <h4 className="text-sm font-semibold text-gray-700 uppercase">Replica Instance</h4>
                      {getStatusBadge(item.replica.status)}
                      <Badge variant="secondary" size="sm">{getReplicaTypeLabel(item.replica.type)}</Badge>
                    </div>
                    <div className="flex items-center space-x-2 mb-1">
                      <p className="text-sm font-mono text-gray-900">{item.replica.instanceId}</p>
                      <button
                        onClick={() => handleCopyInstanceId(item.replica.instanceId)}
                        className="p-1 hover:bg-gray-200 rounded transition-colors"
                        title="Copy instance ID"
                      >
                        <Copy size={14} className={copiedId === item.replica.instanceId ? 'text-green-600' : 'text-gray-500'} />
                      </button>
                    </div>
                    <div className="flex flex-wrap items-center gap-3 text-xs text-gray-600">
                      <span>Pool: <span className="font-semibold">{item.replica.pool?.name || 'N/A'}</span></span>
                      <span>•</span>
                      <span>AZ: <span className="font-semibold">{item.replica.pool?.az || 'N/A'}</span></span>
                      {item.replica.cost?.hourly && (
                        <>
                          <span>•</span>
                          <span>Cost: <span className="font-semibold">${item.replica.cost.hourly.toFixed(4)}/hr</span></span>
                        </>
                      )}
                    </div>

                    {/* Sync Status */}
                    <div className="flex items-center space-x-2 mt-3 p-2 bg-white rounded-lg border border-gray-200">
                      {getSyncStatusIcon(item.replica.sync_status)}
                      <span className="text-xs font-medium text-gray-700">
                        {item.replica.sync_status === 'synced' ? 'Fully Synced' :
                         item.replica.sync_status === 'syncing' ? `Syncing (${item.replica.state_transfer_progress.toFixed(0)}%)` :
                         item.replica.sync_status === 'out-of-sync' ? 'Out of Sync' :
                         'Initializing'}
                      </span>
                      {item.replica.sync_latency_ms && (
                        <span className="text-xs text-gray-500">
                          • Latency: {item.replica.sync_latency_ms}ms
                        </span>
                      )}
                    </div>

                    {/* Timestamps */}
                    <div className="mt-3 text-xs text-gray-500 space-y-1">
                      {item.replica.created_at && (
                        <p>Created: {new Date(item.replica.created_at).toLocaleString()}</p>
                      )}
                      {item.replica.ready_at && (
                        <p>Ready: {new Date(item.replica.ready_at).toLocaleString()}</p>
                      )}
                    </div>
                  </div>
                </div>

                {/* Action Buttons */}
                <div className="flex flex-wrap gap-2 pt-4 border-t border-gray-200">
                  <Button
                    variant="success"
                    size="sm"
                    icon={<ArrowRight size={16} />}
                    onClick={() => handleSwitchToReplica(item.agentId, item.replica.id)}
                    loading={actionLoading === `switch-${item.replica.id}`}
                    disabled={item.replica.status !== 'ready'}
                  >
                    {item.replica.status === 'ready' ? 'Switch to Replica' : 'Waiting for Ready...'}
                  </Button>
                  <Button
                    variant="danger"
                    size="sm"
                    icon={<Trash2 size={16} />}
                    onClick={() => handleTerminateReplica(item.agentId, item.replica.id)}
                    loading={actionLoading === `terminate-${item.replica.id}`}
                    disabled={item.replica.status === 'terminated'}
                  >
                    Terminate Replica
                  </Button>
                </div>

                {/* Warning Message */}
                {item.replica.type === 'manual' && (
                  <div className="mt-3 p-3 bg-amber-50 border border-amber-200 rounded-lg flex items-start space-x-2">
                    <AlertTriangle size={16} className="text-amber-600 flex-shrink-0 mt-0.5" />
                    <p className="text-xs text-amber-800">
                      <span className="font-semibold">Manual Replica: </span>
                      If you terminate this replica while manual replica mode is enabled, a new replica will be created automatically.
                      To permanently stop replicas, disable manual replica mode in agent configuration.
                    </p>
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

export default ClientReplicasTab;
