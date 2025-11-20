import React, { useState, useEffect, useCallback } from 'react';
import { Server, CheckCircle, XCircle, Power, PowerOff, Settings } from 'lucide-react';
import LoadingSpinner from '../../common/LoadingSpinner';
import ErrorMessage from '../../common/ErrorMessage';
import EmptyState from '../../common/EmptyState';
import Badge from '../../common/Badge';
import Button from '../../common/Button';
import ToggleSwitch from '../../common/ToggleSwitch';
import AgentConfigModal from '../../modals/AgentConfigModal';
import api from '../../../services/api';

const ClientAgentsTab = ({ clientId }) => {
  const [agents, setAgents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedAgent, setSelectedAgent] = useState(null);
  const [showConfigModal, setShowConfigModal] = useState(false);
  const [error, setError] = useState(null);

  const loadAgents = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.getAgents(clientId);
      setAgents(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [clientId]);

  useEffect(() => {
    loadAgents();
  }, [loadAgents]);

  const handleToggle = async (agentId, currentEnabled) => {
    try {
      await api.toggleAgent(agentId, !currentEnabled);
      await loadAgents();
    } catch (error) {
      alert('Failed to toggle agent: ' + error.message);
    }
  };

  const handleSettingToggle = async (agentId, setting, currentValue) => {
    try {
      await api.updateAgentSettings(agentId, { [setting]: !currentValue });
      
      setAgents(prev => prev.map(agent => 
        agent.id === agentId 
          ? { ...agent, [setting]: !currentValue }
          : agent
      ));
    } catch (error) {
      alert('Failed to update settings: ' + error.message);
      await loadAgents();
    }
  };

  const openConfigModal = (agent) => {
    setSelectedAgent(agent);
    setShowConfigModal(true);
  };

  if (loading) {
    return <div className="flex justify-center items-center h-64"><LoadingSpinner /></div>;
  }

  if (error) {
    return <ErrorMessage message={error} onRetry={loadAgents} />;
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
                      {agent.status === 'online' ? (
                        <CheckCircle size={18} className="text-green-500 flex-shrink-0" />
                      ) : (
                        <XCircle size={18} className="text-red-500 flex-shrink-0" />
                      )}
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
                
                <div className="space-y-3 mb-4">
                  <div className="flex items-center justify-between p-3 bg-gray-50 rounded-lg">
                    <span className="text-sm font-medium text-gray-700">Auto Switch</span>
                    <ToggleSwitch
                      enabled={agent.auto_switch_enabled}
                      onChange={() => handleSettingToggle(agent.id, 'auto_switch_enabled', agent.auto_switch_enabled)}
                      label="Auto Switch"
                    />
                  </div>
                  
                  <div className="flex items-center justify-between p-3 bg-gray-50 rounded-lg">
                    <span className="text-sm font-medium text-gray-700">Auto Terminate</span>
                    <ToggleSwitch
                      enabled={agent.auto_terminate_enabled}
                      onChange={() => handleSettingToggle(agent.id, 'auto_terminate_enabled', agent.auto_terminate_enabled)}
                      label="Auto Terminate"
                    />
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
                    Configure
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
          onSave={loadAgents}
        />
      )}
    </>
  );
};

export default ClientAgentsTab;
