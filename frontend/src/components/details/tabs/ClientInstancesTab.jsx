import React, { useState, useEffect, useCallback } from 'react';
import { Zap, Search, RefreshCw, ChevronDown, ChevronRight } from 'lucide-react';
import LoadingSpinner from '../../common/LoadingSpinner';
import ErrorMessage from '../../common/ErrorMessage';
import EmptyState from '../../common/EmptyState';
import Badge from '../../common/Badge';
import Button from '../../common/Button';
import InstanceDetailPanel from '../InstanceDetailPanel';
import api from '../../../services/api';

const ClientInstancesTab = ({ clientId }) => {
  const [instances, setInstances] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedInstanceId, setSelectedInstanceId] = useState(null);
  const [filters, setFilters] = useState({ status: 'active', mode: 'all', search: '' });
  const [error, setError] = useState(null);
  const [isInitialLoad, setIsInitialLoad] = useState(true);

  const getStatusBadge = (status, isPrimary) => {
    if (status === 'running_primary' || (status === 'running_replica' && isPrimary)) {
      return (
        <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-800">
          Running (Primary)
        </span>
      );
    } else if (status === 'running_replica') {
      return (
        <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800">
          Running (Replica)
        </span>
      );
    } else if (status === 'zombie') {
      return (
        <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-yellow-100 text-yellow-800">
          Zombie
        </span>
      );
    } else if (status === 'terminated') {
      return (
        <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-gray-100 text-gray-800">
          Terminated
        </span>
      );
    } else {
      return (
        <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-gray-100 text-gray-600">
          {status || 'Unknown'}
        </span>
      );
    }
  };

  const loadInstances = useCallback(async (showLoadingSpinner = true) => {
    if (showLoadingSpinner) {
      setLoading(true);
    }
    setError(null);
    try {
      const data = await api.getInstances(clientId, filters);
      setInstances(data);
      setIsInitialLoad(false);
    } catch (err) {
      setError(err.message);
    } finally {
      if (showLoadingSpinner) {
        setLoading(false);
      }
    }
  }, [clientId, filters]);

  useEffect(() => {
    loadInstances(true); // Initial load with spinner
    // Auto-refresh every 5 seconds for live updates (without spinner)
    const interval = setInterval(() => loadInstances(false), 5000);
    return () => clearInterval(interval);
  }, [loadInstances]);

  const toggleInstanceDetail = (instanceId) => {
    setSelectedInstanceId(prevId => prevId === instanceId ? null : instanceId);
  };

  if (error) {
    return <ErrorMessage message={error} onRetry={() => loadInstances(true)} />;
  }

  return (
    <div className="space-y-4">
      {/* Filters */}
      <div className="bg-white p-4 rounded-xl shadow-sm border border-gray-200">
        <div className="flex flex-col sm:flex-row sm:flex-wrap items-stretch sm:items-center gap-4">
          <select
            value={filters.status}
            onChange={(e) => setFilters({...filters, status: e.target.value})}
            className="px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent text-sm"
          >
            <option value="all">All Status</option>
            <option value="active">Active</option>
            <option value="terminated">Terminated</option>
          </select>
          
          <select
            value={filters.mode}
            onChange={(e) => setFilters({...filters, mode: e.target.value})}
            className="px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent text-sm"
          >
            <option value="all">All Modes</option>
            <option value="spot">Spot</option>
            <option value="ondemand">On-Demand</option>
          </select>
          
          <div className="relative flex-1 min-w-[200px]">
            <Search size={18} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
            <input
              type="text"
              placeholder="Search instances..."
              value={filters.search}
              onChange={(e) => setFilters({...filters, search: e.target.value})}
              className="w-full pl-10 pr-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent text-sm"
            />
          </div>
          
          <Button variant="outline" size="sm" icon={<RefreshCw size={16} />} onClick={() => loadInstances(true)}>
            Refresh
          </Button>
        </div>
      </div>
      
      {/* Instances Table */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="min-w-full">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>
                <th className="py-3 px-4 text-left text-xs font-semibold text-gray-600 uppercase w-10"></th>
                <th className="py-3 px-4 text-left text-xs font-semibold text-gray-600 uppercase">Instance ID</th>
                <th className="py-3 px-4 text-left text-xs font-semibold text-gray-600 uppercase">Type</th>
                <th className="py-3 px-4 text-left text-xs font-semibold text-gray-600 uppercase">AZ</th>
                <th className="py-3 px-4 text-left text-xs font-semibold text-gray-600 uppercase">Status</th>
                <th className="py-3 px-4 text-left text-xs font-semibold text-gray-600 uppercase">Mode</th>
                <th className="py-3 px-4 text-left text-xs font-semibold text-gray-600 uppercase">Pool</th>
                <th className="py-3 px-4 text-left text-xs font-semibold text-gray-600 uppercase">Current Price</th>
                <th className="py-3 px-4 text-left text-xs font-semibold text-gray-600 uppercase">Savings</th>
                <th className="py-3 px-4 text-left text-xs font-semibold text-gray-600 uppercase">Last Switch</th>
                <th className="py-3 px-4 text-left text-xs font-semibold text-gray-600 uppercase">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {loading ? (
                <tr>
                  <td colSpan="11" className="text-center py-8">
                    <LoadingSpinner />
                  </td>
                </tr>
              ) : instances.length === 0 ? (
                <tr>
                  <td colSpan="11" className="text-center py-8">
                    <EmptyState
                      icon={<Zap size={48} />}
                      title="No Instances Found"
                      description="No instances match your filter criteria"
                    />
                  </td>
                </tr>
              ) : (
                instances.map(inst => (
                  <React.Fragment key={inst.id}>
                    <tr className="hover:bg-gray-50 transition-colors">
                      <td className="py-4 px-4">
                        <button onClick={() => toggleInstanceDetail(inst.id)}>
                          {selectedInstanceId === inst.id ? (
                            <ChevronDown size={18} className="text-gray-400" />
                          ) : (
                            <ChevronRight size={18} className="text-gray-400" />
                          )}
                        </button>
                      </td>
                      <td className="py-4 px-4">
                        <span className="text-sm font-mono text-gray-700">{inst.id}</span>
                      </td>
                      <td className="py-4 px-4 text-sm text-gray-700">{inst.type}</td>
                      <td className="py-4 px-4 text-sm text-gray-500">{inst.az}</td>
                      <td className="py-4 px-4">
                        {getStatusBadge(inst.instanceStatus, inst.isPrimary)}
                      </td>
                      <td className="py-4 px-4">
                        <Badge variant={inst.mode === 'ondemand' ? 'danger' : 'success'}>
                          {inst.mode}
                        </Badge>
                      </td>
                      <td className="py-4 px-4 text-sm font-mono text-gray-500">{inst.poolId}</td>
                      <td className="py-4 px-4 text-sm font-semibold text-gray-900">
                        ${(inst.spotPrice || 0).toFixed(4)}
                      </td>
                      <td className="py-4 px-4 text-sm font-bold text-green-600">
                        {inst.onDemandPrice && inst.onDemandPrice > 0
                          ? (((inst.onDemandPrice - (inst.spotPrice || 0)) / inst.onDemandPrice) * 100).toFixed(1) + '%'
                          : 'N/A'}
                      </td>
                      <td className="py-4 px-4 text-sm text-gray-500">
                        {inst.lastSwitch ? new Date(inst.lastSwitch).toLocaleString() : 'Never'}
                      </td>
                      <td className="py-4 px-4">
                        {inst.isPrimary && inst.instanceStatus !== 'zombie' && inst.instanceStatus !== 'terminated' ? (
                          <button
                            onClick={() => toggleInstanceDetail(inst.id)}
                            className="text-blue-600 hover:text-blue-800 text-sm font-medium"
                          >
                            {selectedInstanceId === inst.id ? 'Hide' : 'Manage'}
                          </button>
                        ) : (
                          <span className="text-gray-400 text-sm">N/A</span>
                        )}
                      </td>
                    </tr>
                    {selectedInstanceId === inst.id && inst.instanceStatus !== 'zombie' && (
                      <InstanceDetailPanel
                        instanceId={inst.id}
                        clientId={clientId}
                        isPrimary={inst.isPrimary}
                        instanceStatus={inst.instanceStatus}
                        onClose={() => setSelectedInstanceId(null)}
                        onSwitchComplete={() => loadInstances(false)}
                      />
                    )}
                  </React.Fragment>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};

export default ClientInstancesTab;
