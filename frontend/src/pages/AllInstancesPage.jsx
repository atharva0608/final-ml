import React, { useState, useEffect } from 'react';
import { Zap, Search } from 'lucide-react';
import LoadingSpinner from '../components/common/LoadingSpinner';
import EmptyState from '../components/common/EmptyState';
import Badge from '../components/common/Badge';
import api from '../services/api';

const AllInstancesPage = () => {
  const [instances, setInstances] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filters, setFilters] = useState({ status: 'all', mode: 'all', search: '' });

  useEffect(() => {
    const loadInstances = async (showLoadingSpinner = true) => {
      if (showLoadingSpinner) {
        setLoading(true);
      }
      try {
        const data = await api.getAllInstancesGlobal(filters);
        // Backend returns { instances: [...], total: ..., filters: ... }
        setInstances(data.instances || []);
      } catch (error) {
        console.error('Failed to load instances:', error);
        setInstances([]); // Set empty array on error
      } finally {
        if (showLoadingSpinner) {
          setLoading(false);
        }
      }
    };

    loadInstances(true); // Initial load with spinner
    // Auto-refresh every 5 seconds for live updates (without spinner)
    const interval = setInterval(() => loadInstances(false), 5000);
    return () => clearInterval(interval);
  }, [filters]);

  return (
    <div className="space-y-6">
      <div className="bg-white p-4 rounded-xl shadow-sm border border-gray-200">
        <div className="flex flex-col sm:flex-row sm:flex-wrap items-stretch sm:items-center gap-4">
          <select
            value={filters.status}
            onChange={(e) => setFilters({...filters, status: e.target.value})}
            className="px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 text-sm"
          >
            <option value="all">All Status</option>
            <option value="active">Active</option>
            <option value="terminated">Terminated</option>
          </select>
          
          <select
            value={filters.mode}
            onChange={(e) => setFilters({...filters, mode: e.target.value})}
            className="px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 text-sm"
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
              className="w-full pl-10 pr-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 text-sm"
            />
          </div>
        </div>
      </div>

      <div className="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="min-w-full">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>
                <th className="text-left py-3 px-4 text-xs font-semibold text-gray-600 uppercase">Instance ID</th>
                <th className="text-left py-3 px-4 text-xs font-semibold text-gray-600 uppercase">Client</th>
                <th className="text-left py-3 px-4 text-xs font-semibold text-gray-600 uppercase">Type</th>
                <th className="text-left py-3 px-4 text-xs font-semibold text-gray-600 uppercase">Region</th>
                <th className="text-left py-3 px-4 text-xs font-semibold text-gray-600 uppercase">Mode</th>
                <th className="text-left py-3 px-4 text-xs font-semibold text-gray-600 uppercase">Price</th>
                <th className="text-left py-3 px-4 text-xs font-semibold text-gray-600 uppercase">Savings</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {loading ? (
                <tr>
                  <td colSpan="7" className="text-center py-8">
                    <LoadingSpinner />
                  </td>
                </tr>
              ) : instances.length === 0 ? (
                <tr>
                  <td colSpan="7" className="text-center py-8">
                    <EmptyState
                      icon={<Zap size={48} />}
                      title="No Instances Found"
                      description="No instances match your filter criteria"
                    />
                  </td>
                </tr>
              ) : (
                instances.map(inst => (
                  <tr key={inst.id} className="hover:bg-gray-50">
                    <td className="py-3 px-4 text-sm font-mono text-gray-700">{inst.id}</td>
                    <td className="py-3 px-4 text-sm text-gray-700">{inst.clientName}</td>
                    <td className="py-3 px-4 text-sm text-gray-700">{inst.instanceType}</td>
                    <td className="py-3 px-4 text-sm text-gray-600">{inst.region}</td>
                    <td className="py-3 px-4">
                      <Badge variant={inst.currentMode === 'ondemand' ? 'danger' : 'success'}>
                        {inst.currentMode}
                      </Badge>
                    </td>
                    <td className="py-3 px-4 text-sm font-semibold text-gray-900">
                      ${inst.spotPrice?.toFixed(4) || 'N/A'}
                    </td>
                    <td className="py-3 px-4 text-sm font-bold text-green-600">
                      {inst.spotPrice && inst.ondemandPrice ?
                        (((inst.ondemandPrice - inst.spotPrice) / inst.ondemandPrice) * 100).toFixed(1) + '%' :
                        'N/A'}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};

export default AllInstancesPage;
