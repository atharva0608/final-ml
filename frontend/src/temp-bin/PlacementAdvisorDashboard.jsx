import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { usePlacementPolicies, usePlacementPolicySummary } from '../../hooks/usePlacementPolicies';
import { Card, Badge, Button, EmptyState } from '../shared';
import { 
  AlertCircle, 
  Server, 
  Activity, 
  ArrowRight, 
  Play, 
  RefreshCw,
  Search,
  Filter
} from 'lucide-react';
import { formatCurrency, formatPercentage } from '../../utils/formatters';

const PlacementAdvisorDashboard = ({ clusterId }) => {
  const navigate = useNavigate();
  const { summary, loading: summaryLoading, refresh: refreshSummary } = usePlacementPolicySummary(clusterId);
  const { 
    policies, 
    loading: policiesLoading, 
    filters, 
    updateFilters, 
    refresh: refreshPolicies,
    generatePolicies 
  } = usePlacementPolicies(clusterId);

  const [searchTerm, setSearchTerm] = useState('');

  const [isGenerating, setIsGenerating] = useState(false);

  const handleRefresh = async () => {
    await Promise.all([refreshSummary(), refreshPolicies()]);
  };

  const handleGenerate = async () => {
    setIsGenerating(true);
    await generatePolicies();
    
    // Poll for changes for 15 seconds
    let attempts = 0;
    const pollId = setInterval(async () => {
      attempts++;
      await handleRefresh();
      if (attempts >= 5) {
         clearInterval(pollId);
         setIsGenerating(false);
      }
    }, 3000);
  };

  const getTierColor = (tier) => {
    switch(tier) {
      case 'Platinum': return 'purple';
      case 'Gold': return 'yellow';
      case 'Silver': return 'gray';
      case 'Bronze': return 'amber';
      default: return 'gray';
    }
  };

  if (summaryLoading && !summary) {
    return <div className="p-8 flex justify-center"><RefreshCw className="w-8 h-8 animate-spin text-gray-400" /></div>;
  }

  return (
    <div className="space-y-6">
      {/* Header & Controls */}
      <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4 bg-white border border-gray-200 rounded-lg shadow-sm p-5">
        <div>
          <h2 className="text-xl font-semibold text-gray-900">Placement Intelligence Advisor</h2>
          <p className="text-sm text-gray-500 mt-0.5">
            Automated, safe Spot instance placement for your workloads
            {summary?.observation_mode && (
              <span className="ml-3 px-2 py-0.5 bg-yellow-50 text-yellow-700 border border-yellow-200 rounded text-xs font-medium">Observation Mode</span>
            )}
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="secondary" onClick={handleRefresh} isLoading={summaryLoading || policiesLoading}>
            <RefreshCw className="w-4 h-4 mr-1.5" />
            Refresh
          </Button>
          <Button variant="primary" onClick={handleGenerate} isLoading={isGenerating}>
            <Play className="w-4 h-4 mr-1.5" />
            Run Advisor Cycle
          </Button>
        </div>
      </div>

      {/* Summary Stats */}
      {summary && (
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <div className="bg-white border border-gray-200 rounded-lg shadow-sm p-4 flex items-center justify-between">
            <div>
              <p className="text-xs font-medium text-gray-500 mb-1">Total Savings</p>
              <p className="text-2xl font-bold text-green-600">
                {formatCurrency(summary.total_estimated_savings_usd)}
              </p>
            </div>
            <div className="p-3 bg-green-50 rounded-lg">
              <Activity className="w-5 h-5 text-green-600" />
            </div>
          </div>

          <div className="bg-white border border-gray-200 rounded-lg shadow-sm p-4 flex items-center justify-between">
            <div>
              <p className="text-xs font-medium text-gray-500 mb-1">Spot / On-Demand</p>
              <p className="text-2xl font-bold text-gray-900">
                {summary.total_spot_target} <span className="text-sm font-normal text-gray-400">/ {summary.total_od_target}</span>
              </p>
            </div>
            <div className="p-3 bg-blue-50 rounded-lg">
              <Server className="w-5 h-5 text-blue-600" />
            </div>
          </div>

          <div className="bg-white border border-gray-200 rounded-lg shadow-sm p-4 flex items-center justify-between">
            <div>
              <p className="text-xs font-medium text-gray-500 mb-1">Actionable Workloads</p>
              <p className="text-2xl font-bold text-gray-900">
                {summary.actionable_count} <span className="text-sm font-normal text-gray-400">of {summary.total_workloads}</span>
              </p>
            </div>
            <div className="p-3 bg-purple-50 rounded-lg">
              <Activity className="w-5 h-5 text-purple-600" />
            </div>
          </div>

          <div className="bg-white border border-gray-200 rounded-lg shadow-sm p-4 flex items-center justify-between">
            <div>
              <p className="text-xs font-medium text-gray-500 mb-1">Ready for Rollout</p>
              <p className="text-2xl font-bold text-gray-900">
                {summary.rollout_eligible_count}
              </p>
            </div>
            <div className="p-3 bg-yellow-50 rounded-lg">
              <AlertCircle className="w-5 h-5 text-yellow-600" />
            </div>
          </div>
        </div>
      )}

      {/* Filters & Search */}
      <div className="flex gap-3 items-center bg-white border border-gray-200 rounded-lg shadow-sm p-4">
        <div className="relative flex-1">
          <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
          <input
            type="text"
            placeholder="Search workloads by name or namespace..."
            className="w-full bg-white border border-gray-200 text-gray-900 rounded-md pl-9 pr-4 py-1.5 text-sm focus:ring-2 focus:ring-blue-500 focus:border-transparent outline-none shadow-sm transition-all"
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
          />
        </div>
        <div className="flex items-center gap-2">
          <Filter className="w-4 h-4 text-gray-400" />
          <select
            className="bg-white border border-gray-200 text-gray-700 rounded-md px-3 py-1.5 text-sm cursor-pointer focus:ring-2 focus:ring-blue-500 outline-none shadow-sm"
            value={filters.tier || ''}
            onChange={(e) => updateFilters({ tier: e.target.value || null })}
          >
            <option value="">All Tiers</option>
            <option value="Platinum">Platinum</option>
            <option value="Gold">Gold</option>
            <option value="Silver">Silver</option>
            <option value="Bronze">Bronze</option>
          </select>
          <select
            className="bg-white border border-gray-200 text-gray-700 rounded-md px-3 py-1.5 text-sm cursor-pointer focus:ring-2 focus:ring-blue-500 outline-none shadow-sm"
            value={filters.actionable === null ? '' : String(filters.actionable)}
            onChange={(e) => {
              const val = e.target.value === '' ? null : e.target.value === 'true';
              updateFilters({ actionable: val });
            }}
          >
            <option value="">All Statuses</option>
            <option value="true">Actionable</option>
            <option value="false">Not Actionable</option>
          </select>
        </div>
      </div>

      {/* Data Table */}
      <div className="bg-white border border-gray-200 rounded-lg shadow-sm overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="bg-gray-50 border-b border-gray-200 text-gray-500 font-medium">
              <tr>
                <th className="px-5 py-3.5 font-medium">Workload</th>
                <th className="px-5 py-3.5 font-medium">Tier &amp; Confidence</th>
                <th className="px-5 py-3.5 font-medium">Replicas</th>
                <th className="px-5 py-3.5 font-medium">Target (OD / Spot)</th>
                <th className="px-5 py-3.5 font-medium">Est. Savings</th>
                <th className="px-5 py-3.5 font-medium">Status</th>
                <th className="px-5 py-3.5 font-medium text-right">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {policiesLoading ? (
                <tr>
                  <td colSpan="7" className="px-5 py-10 text-center text-gray-400">
                    <RefreshCw className="w-5 h-5 animate-spin mx-auto mb-2 text-gray-400" />
                    Loading policies...
                  </td>
                </tr>
              ) : policies.length === 0 ? (
                <tr>
                  <td colSpan="7" className="px-5 py-12 text-center text-gray-500">
                    <Server className="w-8 h-8 mx-auto mb-2 text-gray-300" />
                    <p className="font-medium">No placement policies found</p>
                    <p className="text-xs mt-1">No policies match the current filters, or no advisor cycles have run yet.</p>
                  </td>
                </tr>
              ) : (
                policies
                  .filter(p => !searchTerm || p.workload_id.toLowerCase().includes(searchTerm.toLowerCase()))
                  .map((policy) => (
                  <tr key={policy.workload_id} className="hover:bg-gray-50 transition-colors">
                    <td className="px-5 py-3">
                      <div className="font-medium text-gray-900">{policy.name || policy.workload_id?.split('/')[1]}</div>
                      <div className="text-xs text-gray-400 mt-0.5">{policy.namespace || policy.workload_id?.split('/')[0]}</div>
                    </td>
                    <td className="px-5 py-3">
                      <div className="flex items-center gap-2">
                        <span className={`px-2 py-0.5 rounded text-[11px] font-semibold border uppercase tracking-wider ${
                          policy.criticality_tier === 'Platinum' ? 'bg-purple-50 text-purple-700 border-purple-200' :
                          policy.criticality_tier === 'Gold' ? 'bg-yellow-50 text-yellow-700 border-yellow-200' :
                          policy.criticality_tier === 'Bronze' ? 'bg-orange-50 text-orange-700 border-orange-200' :
                          'bg-gray-100 text-gray-600 border-gray-200'
                        }`}>{policy.criticality_tier}</span>
                        <span className={`text-xs font-medium ${policy.confidence_state === 'CONFIRMED' ? 'text-green-600' : 'text-yellow-600'}`}>
                          {policy.confidence_state}
                        </span>
                      </div>
                    </td>
                    <td className="px-5 py-3">
                      <span className="text-gray-700 font-mono bg-gray-100 px-2 py-0.5 rounded text-[13px]">
                        {policy.pod_state?.observed_replicas ?? 0}
                      </span>
                    </td>
                    <td className="px-5 py-3">
                      <div className="flex items-center gap-1 font-mono text-[13px]">
                        <span className="text-blue-700 bg-blue-50 border border-blue-100 px-1.5 py-0.5 rounded">{policy.ondemand_target}</span>
                        <span className="text-gray-400">/</span>
                        <span className="text-purple-700 bg-purple-50 border border-purple-100 px-1.5 py-0.5 rounded">{policy.spot_target}</span>
                      </div>
                    </td>
                    <td className="px-5 py-3">
                      <span className="text-green-700 font-medium text-sm">{formatPercentage(policy.estimated_savings_pct)}</span>
                    </td>
                    <td className="px-5 py-3">
                      <div className="flex items-center gap-1.5 flex-wrap">
                        {policy.actionable ? (
                          <span className="px-2 py-0.5 rounded text-[11px] font-semibold border bg-green-50 text-green-700 border-green-200">Actionable</span>
                        ) : (
                          <span className="px-2 py-0.5 rounded text-[11px] font-semibold border bg-gray-100 text-gray-500 border-gray-200">Not Actionable</span>
                        )}
                        {policy.rollout_eligible && (
                          <span className="px-2 py-0.5 rounded text-[11px] font-semibold border bg-yellow-50 text-yellow-700 border-yellow-200">Rollout Ready</span>
                        )}
                      </div>
                    </td>
                    <td className="px-5 py-3 text-right">
                      <button
                        className="text-blue-600 hover:text-blue-800 text-sm font-medium flex items-center gap-1 ml-auto transition-colors"
                        onClick={() => navigate(`/clusters/${clusterId}/placement-policies/${encodeURIComponent(policy.workload_id)}`)}
                      >
                        Details <ArrowRight className="w-3.5 h-3.5" />
                      </button>
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

export default PlacementAdvisorDashboard;
