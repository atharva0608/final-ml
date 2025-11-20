import React, { useState, useEffect } from 'react';
import { Search } from 'lucide-react';
import LoadingSpinner from '../components/common/LoadingSpinner';
import Badge from '../components/common/Badge';
import api from '../services/api';

const AllAgentsPage = () => {
  const [agents, setAgents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('all');

  useEffect(() => {
    const loadAgents = async () => {
      setLoading(true);
      try {
        const data = await api.getAllAgentsGlobal();
        // Backend returns { agents: [...], total: ..., filters: ... }
        setAgents(data.agents || []);
      } catch (error) {
        console.error('Failed to load agents:', error);
        setAgents([]); // Set empty array on error
      } finally {
        setLoading(false);
      }
    };
    loadAgents();
  }, []);

  const filteredAgents = (agents || []).filter(a => {
    const matchesSearch = a.id?.toLowerCase().includes(search.toLowerCase()) ||
                         (a.hostname && a.hostname.toLowerCase().includes(search.toLowerCase()));
    const matchesStatus = statusFilter === 'all' || a.status === statusFilter;
    return matchesSearch && matchesStatus;
  });

  return (
    <div className="space-y-6">
      <div className="bg-white p-4 md:p-6 rounded-xl shadow-sm border border-gray-200">
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 mb-6">
          <h3 className="text-lg font-bold text-gray-900">All Agents</h3>
          <div className="flex flex-col sm:flex-row gap-2 w-full sm:w-auto">
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              className="px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 text-sm"
            >
              <option value="all">All Status</option>
              <option value="online">Online</option>
              <option value="offline">Offline</option>
            </select>
            <div className="relative flex-1 sm:w-64">
              <Search size={18} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
              <input
                type="text"
                placeholder="Search agents..."
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="w-full pl-10 pr-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 text-sm"
              />
            </div>
          </div>
        </div>

        {loading ? (
          <div className="flex justify-center items-center h-64"><LoadingSpinner /></div>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full">
              <thead className="bg-gray-50 border-b border-gray-200">
                <tr>
                  <th className="text-left py-3 px-4 text-xs font-semibold text-gray-600 uppercase">Agent ID</th>
                  <th className="text-left py-3 px-4 text-xs font-semibold text-gray-600 uppercase">Client</th>
                  <th className="text-left py-3 px-4 text-xs font-semibold text-gray-600 uppercase">Status</th>
                  <th className="text-left py-3 px-4 text-xs font-semibold text-gray-600 uppercase">Hostname</th>
                  <th className="text-left py-3 px-4 text-xs font-semibold text-gray-600 uppercase">Instances</th>
                  <th className="text-left py-3 px-4 text-xs font-semibold text-gray-600 uppercase">Last Heartbeat</th>
                  <th className="text-left py-3 px-4 text-xs font-semibold text-gray-600 uppercase">Version</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {filteredAgents.map(agent => (
                  <tr key={agent.id} className="hover:bg-gray-50">
                    <td className="py-3 px-4 text-sm font-mono text-gray-700">{agent.id}</td>
                    <td className="py-3 px-4 text-sm text-gray-700">{agent.clientName}</td>
                    <td className="py-3 px-4">
                      <Badge variant={agent.status === 'online' ? 'success' : 'danger'}>
                        {agent.status}
                      </Badge>
                    </td>
                    <td className="py-3 px-4 text-sm text-gray-600">{agent.hostname || 'N/A'}</td>
                    <td className="py-3 px-4 text-sm text-gray-700">{agent.instanceId ? 1 : 0}</td>
                    <td className="py-3 px-4 text-sm text-gray-600">
                      {agent.lastHeartbeatAt ? new Date(agent.lastHeartbeatAt).toLocaleString() : 'Never'}
                    </td>
                    <td className="py-3 px-4 text-sm text-gray-600">{agent.version || 'N/A'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
};

export default AllAgentsPage;
