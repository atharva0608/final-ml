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

  const loadInstances = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.getInstances(clientId, filters);
      setInstances(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [clientId, filters]);

  useEffect(() => {
    loadInstances();
  }, [loadInstances]);

  const toggleInstanceDetail = (instanceId) => {
    setSelectedInstanceId(prevId => prevId === instanceId ? null : instanceId);
  };

  if (error) {
    return <ErrorMessage message={error} onRetry={loadInstances} />;
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
          
          <Button variant="outline" size="sm" icon={<RefreshCw size={16} />} onClick={loadInstances}>
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
                instances.map(inst => {
                  const isZombie = inst.instanceRole === 'zombie';
                  const isPrimary = inst.instanceRole === 'primary';
                  const savings = inst.onDemandPrice > 0
                    ? (((inst.onDemandPrice - inst.spotPrice) / inst.onDemandPrice) * 100).toFixed(1)
                    : '0.0';

                  return (
                    <React.Fragment key={inst.id}>
                      <tr className={`hover:bg-gray-50 transition-colors ${isZombie ? 'opacity-60' : ''}`}>
                        <td className="py-4 px-4">
                          {!isZombie && (
                            <button onClick={() => toggleInstanceDetail(inst.id)}>
                              {selectedInstanceId === inst.id ? (
                                <ChevronDown size={18} className="text-gray-400" />
                              ) : (
                                <ChevronRight size={18} className="text-gray-400" />
                              )}
                            </button>
                          )}
                        </td>
                        <td className="py-4 px-4">
                          <span className="text-sm font-mono text-gray-700">{inst.id}</span>
                        </td>
                        <td className="py-4 px-4 text-sm text-gray-700">{inst.type}</td>
                        <td className="py-4 px-4 text-sm text-gray-500">{inst.az}</td>
                        <td className="py-4 px-4">
                          <Badge variant={isPrimary ? 'success' : 'secondary'}>
                            {isPrimary ? 'Primary' : isZombie ? 'Zombie' : 'Unknown'}
                          </Badge>
                        </td>
                        <td className="py-4 px-4">
                          <Badge variant={inst.mode === 'ondemand' ? 'danger' : 'success'}>
                            {inst.mode}
                          </Badge>
                        </td>
                        <td className="py-4 px-4 text-sm font-mono text-gray-500">{inst.poolId}</td>
                        <td className="py-4 px-4 text-sm font-semibold text-gray-900">
                          ${inst.spotPrice.toFixed(4)}
                        </td>
                        <td className="py-4 px-4 text-sm font-bold text-green-600">
                          {savings}%
                        </td>
                        <td className="py-4 px-4 text-sm text-gray-500">
                          {inst.lastSwitch ? new Date(inst.lastSwitch).toLocaleString() : 'Never'}
                        </td>
                        <td className="py-4 px-4">
                          {!isZombie ? (
                            <button
                              onClick={() => toggleInstanceDetail(inst.id)}
                              className="text-blue-600 hover:text-blue-800 text-sm font-medium"
                            >
                              {selectedInstanceId === inst.id ? 'Hide' : 'Manage'}
                            </button>
                          ) : (
                            <span className="text-gray-400 text-sm">—</span>
                          )}
                        </td>
                      </tr>
                      {selectedInstanceId === inst.id && !isZombie && (
                        <InstanceDetailPanel
                          instanceId={inst.id}
                          clientId={clientId}
                          onClose={() => setSelectedInstanceId(null)}
                        />
                      )}
                    </React.Fragment>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};

export default ClientInstancesTab;
