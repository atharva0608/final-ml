import React, { useState, useEffect } from 'react';
import { Clock, Trash2, CheckCircle, XCircle, RefreshCw } from 'lucide-react';
import LoadingSpinner from '../components/common/LoadingSpinner';
import ErrorMessage from '../components/common/ErrorMessage';
import Badge from '../components/common/Badge';
import api from '../services/api';

const AgentHistoryPage = ({ clientId }) => {
  const [agents, setAgents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [filter, setFilter] = useState('all'); // 'all', 'online', 'offline', 'deleted'

  useEffect(() => {
    loadAgentHistory();
  }, [clientId]);

  const loadAgentHistory = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.getAgentHistory(clientId);
      setAgents(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const filteredAgents = agents.filter(agent => {
    if (filter === 'all') return true;
    return agent.status === filter;
  });

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
    return (
      <div className="flex justify-center items-center h-96">
        <LoadingSpinner />
      </div>
    );
  }

  if (error) {
    return <ErrorMessage message={error} onRetry={loadAgentHistory} />;
  }

  return (
    <div className="p-6">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900">Agent History</h1>
        <p className="text-gray-600">View all agents including deleted ones</p>
      </div>

      {/* Filter Buttons */}
      <div className="flex gap-2 mb-6">
        <button
          onClick={() => setFilter('all')}
          className={`px-4 py-2 rounded-lg font-medium transition-colors ${
            filter === 'all'
              ? 'bg-blue-600 text-white'
              : 'bg-gray-200 text-gray-700 hover:bg-gray-300'
          }`}
        >
          All ({agents.length})
        </button>
        <button
          onClick={() => setFilter('online')}
          className={`px-4 py-2 rounded-lg font-medium transition-colors ${
            filter === 'online'
              ? 'bg-green-600 text-white'
              : 'bg-gray-200 text-gray-700 hover:bg-gray-300'
          }`}
        >
          Online ({agents.filter(a => a.status === 'online').length})
        </button>
        <button
          onClick={() => setFilter('offline')}
          className={`px-4 py-2 rounded-lg font-medium transition-colors ${
            filter === 'offline'
              ? 'bg-yellow-600 text-white'
              : 'bg-gray-200 text-gray-700 hover:bg-gray-300'
          }`}
        >
          Offline ({agents.filter(a => a.status === 'offline').length})
        </button>
        <button
          onClick={() => setFilter('deleted')}
          className={`px-4 py-2 rounded-lg font-medium transition-colors ${
            filter === 'deleted'
              ? 'bg-red-600 text-white'
              : 'bg-gray-200 text-gray-700 hover:bg-gray-300'
          }`}
        >
          Deleted ({agents.filter(a => a.status === 'deleted').length})
        </button>
      </div>

      {/* Agent Table */}
      <div className="bg-white rounded-lg shadow overflow-hidden">
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Agent ID
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Status
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Instance
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Region / AZ
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Created
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Last Heartbeat
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Terminated
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Config
                </th>
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-gray-200">
              {filteredAgents.length === 0 ? (
                <tr>
                  <td colSpan="8" className="px-6 py-12 text-center text-gray-500">
                    No agents found with status: {filter}
                  </td>
                </tr>
              ) : (
                filteredAgents.map(agent => (
                  <tr
                    key={agent.id}
                    className={agent.status === 'deleted' ? 'bg-red-50' : ''}
                  >
                    <td className="px-6 py-4 whitespace-nowrap">
                      <div className="flex flex-col">
                        <div className="text-sm font-mono text-gray-900 truncate max-w-xs" title={agent.id}>
                          {agent.logicalAgentId || agent.id}
                        </div>
                        {agent.logicalAgentId && (
                          <div className="text-xs font-mono text-gray-400 truncate max-w-xs" title={agent.id}>
                            {agent.id}
                          </div>
                        )}
                      </div>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap">
                      {getStatusBadge(agent.status)}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap">
                      <div className="flex flex-col">
                        <div className="text-sm text-gray-900 font-mono">
                          {agent.instanceId || 'N/A'}
                        </div>
                        {agent.instanceType && (
                          <div className="text-xs text-gray-500">
                            {agent.instanceType}
                          </div>
                        )}
                      </div>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                      {agent.region && agent.az ? (
                        <div className="flex flex-col">
                          <div>{agent.region}</div>
                          <div className="text-xs text-gray-500">{agent.az}</div>
                        </div>
                      ) : (
                        'N/A'
                      )}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                      {agent.createdAt ? (
                        <div className="flex flex-col">
                          <div>{new Date(agent.createdAt).toLocaleDateString()}</div>
                          <div className="text-xs text-gray-400">
                            {new Date(agent.createdAt).toLocaleTimeString()}
                          </div>
                        </div>
                      ) : (
                        'N/A'
                      )}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                      {agent.lastHeartbeat ? (
                        <div className="flex flex-col">
                          <div>{new Date(agent.lastHeartbeat).toLocaleDateString()}</div>
                          <div className="text-xs text-gray-400">
                            {new Date(agent.lastHeartbeat).toLocaleTimeString()}
                          </div>
                        </div>
                      ) : (
                        'Never'
                      )}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                      {agent.terminatedAt ? (
                        <div className="flex flex-col">
                          <div>{new Date(agent.terminatedAt).toLocaleDateString()}</div>
                          <div className="text-xs text-gray-400">
                            {new Date(agent.terminatedAt).toLocaleTimeString()}
                          </div>
                        </div>
                      ) : (
                        '-'
                      )}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap">
                      <div className="flex flex-col text-xs space-y-1">
                        <div>
                          <span className="text-gray-600">Auto-Switch:</span>
                          <span className={`ml-1 font-semibold ${agent.autoSwitchEnabled ? 'text-green-600' : 'text-gray-400'}`}>
                            {agent.autoSwitchEnabled ? 'ON' : 'OFF'}
                          </span>
                        </div>
                        <div>
                          <span className="text-gray-600">Manual Replica:</span>
                          <span className={`ml-1 font-semibold ${agent.manualReplicaEnabled ? 'text-green-600' : 'text-gray-400'}`}>
                            {agent.manualReplicaEnabled ? 'ON' : 'OFF'}
                          </span>
                        </div>
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Summary Stats */}
      <div className="mt-6 grid grid-cols-1 md:grid-cols-4 gap-4">
        <div className="bg-blue-50 rounded-lg p-4">
          <div className="text-2xl font-bold text-blue-900">{agents.length}</div>
          <div className="text-sm text-blue-600">Total Agents</div>
        </div>
        <div className="bg-green-50 rounded-lg p-4">
          <div className="text-2xl font-bold text-green-900">
            {agents.filter(a => a.status === 'online').length}
          </div>
          <div className="text-sm text-green-600">Online</div>
        </div>
        <div className="bg-yellow-50 rounded-lg p-4">
          <div className="text-2xl font-bold text-yellow-900">
            {agents.filter(a => a.status === 'offline').length}
          </div>
          <div className="text-sm text-yellow-600">Offline</div>
        </div>
        <div className="bg-red-50 rounded-lg p-4">
          <div className="text-2xl font-bold text-red-900">
            {agents.filter(a => a.status === 'deleted').length}
          </div>
          <div className="text-sm text-red-600">Deleted</div>
        </div>
      </div>
    </div>
  );
};

export default AgentHistoryPage;
