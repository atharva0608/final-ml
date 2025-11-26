import React, { useState, useEffect, useCallback } from 'react';
import { Server, CheckCircle, XCircle, Power, PowerOff, Settings, Trash2, RefreshCw } from 'lucide-react';
import LoadingSpinner from '../../common/LoadingSpinner';
import ErrorMessage from '../../common/ErrorMessage';
import EmptyState from '../../common/EmptyState';
import Badge from '../../common/Badge';
import Button from '../../common/Button';
import AgentConfigModal from '../../modals/AgentConfigModal';
import api from '../../../services/api';

const ClientAgentsTab = ({ clientId }) => {
  const [agents, setAgents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedAgent, setSelectedAgent] = useState(null);
  const [showConfigModal, setShowConfigModal] = useState(false);
  const [error, setError] = useState(null);

  const loadAgents = useCallback(async (showLoadingSpinner = true) => {
    if (showLoadingSpinner) {
      setLoading(true);
    }
    setError(null);
    try {
      const data = await api.getAgents(clientId);
      setAgents(data);
    } catch (err) {
      setError(err.message);
    } finally {
      if (showLoadingSpinner) {
        setLoading(false);
      }
    }
  }, [clientId]);

  useEffect(() => {
    loadAgents(true); // Initial load with spinner
    // Auto-refresh every 5 seconds for live updates (without spinner)
    const interval = setInterval(() => loadAgents(false), 5000);
    return () => clearInterval(interval);
  }, [loadAgents]);

  const handleToggle = async (agentId, currentEnabled) => {
    try {
      await api.toggleAgent(agentId, !currentEnabled);
      await loadAgents(false); // Refresh without spinner
    } catch (error) {
      alert('Failed to toggle agent: ' + error.message);
    }
  };

  const handleDelete = async (agentId) => {
    if (!window.confirm('Are you sure you want to delete this agent? This will terminate all replicas and mark the agent as deleted. This action cannot be undone.')) {
      return;
    }

    try {
      await api.deleteAgent(agentId);
      await loadAgents(false); // Refresh without spinner
      alert('Agent deleted successfully');
    } catch (error) {
      alert('Failed to delete agent: ' + error.message);
    }
  };

  const openConfigModal = (agent) => {
    setSelectedAgent(agent);
    setShowConfigModal(true);
  };

  const getStatusBadge = (status) => {
    switch (status) {
      case 'online':
        return <Badge variant="success" icon={<CheckCircle size={14} />}>Online</Badge>;
      case 'offline':
        return <Badge variant="warning" icon={<XCircle size={14} />}>Offline</Badge>;
      case 'deleted':
        return <Badge variant="danger" icon={<Trash2 size={14} />}>Deleted</Badge>;
      case 'switching':
        return <Badge variant="info" icon={<RefreshCw size={14} />}>Switching</Badge>;
      default:
        return <Badge variant="secondary">{status}</Badge>;
    }
  };

  if (loading) {
    return <div className="flex justify-center items-center h-64"><LoadingSpinner /></div>;
  }

  if (error) {
    return <ErrorMessage message={error} onRetry={() => loadAgents(true)} />;
  }

  return (
    <>
      <div className="bg-white p-4 md:p-6 rounded-xl shadow-sm border border-gray-200">
        <div className="flex items-center justify-between mb-6">
          <h3 className="text-lg font-bold text-gray-900">Agents Management</h3>
          <Badge variant="info">{agents.length} Total</Badge>
        </div>

        {agents.length === 0 ? (
          <EmptyState
            icon={<Server size={48} />}
            title="No Agents Found"
            description="No agents are registered for this client"
          />
        ) : (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {agents.map(agent => (
              <div key={agent.id} className="border border-gray-200 rounded-lg p-5 hover:shadow-md transition-all">
                <div className="flex items-start justify-between mb-4">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center space-x-3 mb-2">
                      <h4 className="font-mono text-sm font-bold text-gray-900 truncate">{agent.id}</h4>
                      {getStatusBadge(agent.status)}
                    </div>
                    <p className="text-xs text-gray-500">
                      Last heartbeat: {agent.lastHeartbeat ? new Date(agent.lastHeartbeat).toLocaleString() : 'Never'}
                    </p>
                    <p className="text-xs text-gray-500 mt-1">
                      Managing {agent.instanceCount} instance{agent.instanceCount !== 1 ? 's' : ''}
                    </p>
                  </div>
                  <Badge variant={agent.enabled ? 'success' : 'danger'}>
                    {agent.enabled ? 'Enabled' : 'Disabled'}
                  </Badge>
                </div>

                {/* Configuration Summary */}
                <div className="mb-4 p-3 bg-gray-50 rounded-lg">
                  <div className="grid grid-cols-2 gap-2 text-xs">
                    <div>
                      <span className="text-gray-600">Auto-Switch:</span>
                      <span className={`ml-2 font-semibold ${agent.autoSwitchEnabled ? 'text-green-600' : 'text-gray-400'}`}>
                        {agent.autoSwitchEnabled ? 'ON' : 'OFF'}
                      </span>
                    </div>
                    <div>
                      <span className="text-gray-600">Manual Replica:</span>
                      <span className={`ml-2 font-semibold ${agent.manualReplicaEnabled ? 'text-green-600' : 'text-gray-400'}`}>
                        {agent.manualReplicaEnabled ? 'ON' : 'OFF'}
                      </span>
                    </div>
                    <div>
                      <span className="text-gray-600">Auto-Terminate:</span>
                      <span className={`ml-2 font-semibold ${agent.autoTerminateEnabled ? 'text-red-600' : 'text-gray-400'}`}>
                        {agent.autoTerminateEnabled ? 'ON' : 'OFF'}
                      </span>
                    </div>
                  </div>
                </div>

                <div className="flex space-x-2">
                  <Button
                    variant={agent.enabled ? 'danger' : 'success'}
                    size="sm"
                    onClick={() => handleToggle(agent.id, agent.enabled)}
                    icon={agent.enabled ? <PowerOff size={14} /> : <Power size={14} />}
                    className="flex-1"
                  >
                    {agent.enabled ? 'Disable' : 'Enable'}
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => openConfigModal(agent)}
                    icon={<Settings size={14} />}
                  >
                    Config
                  </Button>
                  <Button
                    variant="danger"
                    size="sm"
                    onClick={() => handleDelete(agent.id)}
                    icon={<Trash2 size={14} />}
                  >
                    Delete
                  </Button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {showConfigModal && selectedAgent && (
        <AgentConfigModal
          agent={selectedAgent}
          onClose={() => setShowConfigModal(false)}
          onSave={() => loadAgents(false)}
        />
      )}
    </>
  );
};

export default ClientAgentsTab;
