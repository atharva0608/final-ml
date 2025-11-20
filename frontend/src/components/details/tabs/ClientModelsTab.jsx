import React, { useState, useEffect } from 'react';
import { Server, CheckCircle, XCircle, Clock, TrendingUp, TrendingDown } from 'lucide-react';
import LoadingSpinner from '../../common/LoadingSpinner';
import EmptyState from '../../common/EmptyState';
import Badge from '../../common/Badge';
import api from '../../../services/api';

const ClientModelsTab = ({ clientId }) => {
  const [agents, setAgents] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const loadData = async () => {
      setLoading(true);
      try {
        const data = await api.getAgentDecisions(clientId);
        // Backend returns array of agents with decisions and pricing health
        setAgents(data || []);
      } catch (error) {
        console.error('Failed to load agent decisions:', error);
        setAgents([]);
      } finally {
        setLoading(false);
      }
    };
    loadData();

    const interval = setInterval(loadData, 30000);
    return () => clearInterval(interval);
  }, [clientId]);

  const getDecisionColor = (type) => {
    if (type === 'stay') return 'bg-blue-500';
    if (type === 'switch_spot') return 'bg-green-500';
    if (type === 'switch_ondemand') return 'bg-yellow-500';
    return 'bg-gray-500';
  };

  const getDecisionLabel = (type) => {
    if (type === 'stay') return 'Stay';
    if (type === 'switch_spot') return 'Switch Spot';
    if (type === 'switch_ondemand') return 'To On-Demand';
    return 'No Decision';
  };

  if (loading) {
    return (
      <div className="bg-white p-6 rounded-xl shadow-sm border border-gray-200">
        <div className="flex justify-center items-center h-64">
          <LoadingSpinner />
        </div>
      </div>
    );
  }

  if (agents.length === 0) {
    return (
      <div className="bg-white p-6 rounded-xl shadow-sm border border-gray-200">
        <EmptyState
          icon={<Server size={48} />}
          title="No Agents Found"
          description="No agents are currently registered for this client"
        />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {agents.map((agent) => (
        <div key={agent.agentId} className="bg-white p-6 rounded-xl shadow-sm border border-gray-200">
          {/* Agent Header */}
          <div className="flex items-center justify-between mb-6 pb-4 border-b border-gray-200">
            <div className="flex items-center space-x-3">
              <div className="p-3 bg-blue-100 rounded-lg">
                <Server size={24} className="text-blue-600" />
              </div>
              <div>
                <h3 className="text-lg font-bold text-gray-900">{agent.agentName}</h3>
                <p className="text-xs text-gray-500 font-mono">{agent.agentId}</p>
              </div>
            </div>
            <Badge variant={agent.status === 'online' ? 'success' : 'danger'}>
              {agent.status}
            </Badge>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            {/* Last Decision - Circular Progress */}
            <div className="bg-gradient-to-br from-blue-50 to-indigo-50 p-6 rounded-xl border border-blue-200">
              <h4 className="text-sm font-semibold text-gray-700 mb-4">Last Decision</h4>

              {agent.lastDecision?.type ? (
                <div className="flex flex-col items-center">
                  {/* Circular Progress Bar */}
                  <div className="relative w-32 h-32 mb-4">
                    <svg className="transform -rotate-90 w-32 h-32">
                      <circle
                        cx="64"
                        cy="64"
                        r="56"
                        stroke="currentColor"
                        strokeWidth="8"
                        fill="transparent"
                        className="text-gray-200"
                      />
                      <circle
                        cx="64"
                        cy="64"
                        r="56"
                        stroke="currentColor"
                        strokeWidth="8"
                        fill="transparent"
                        strokeDasharray={`${2 * Math.PI * 56}`}
                        strokeDashoffset={`${2 * Math.PI * 56 * 0.25}`}
                        className={getDecisionColor(agent.lastDecision.type)}
                        strokeLinecap="round"
                      />
                    </svg>
                    <div className="absolute inset-0 flex flex-col items-center justify-center">
                      <p className="text-2xl font-bold text-gray-900">
                        {agent.lastDecision.elapsed?.value || '0'}
                      </p>
                      <p className="text-xs text-gray-500">
                        {agent.lastDecision.elapsed?.unit || 'min'}
                      </p>
                    </div>
                  </div>

                  <Badge variant={
                    agent.lastDecision.type === 'stay' ? 'info' :
                    agent.lastDecision.type === 'switch_spot' ? 'success' :
                    'warning'
                  }>
                    {getDecisionLabel(agent.lastDecision.type)}
                  </Badge>

                  {agent.lastDecision.elapsed?.formatted && (
                    <p className="text-xs text-gray-600 mt-2">
                      {agent.lastDecision.elapsed.formatted} ago
                    </p>
                  )}
                </div>
              ) : (
                <div className="flex flex-col items-center py-8">
                  <XCircle size={48} className="text-gray-400 mb-2" />
                  <p className="text-sm text-gray-500">No decision yet</p>
                </div>
              )}
            </div>

            {/* Pricing Health Status */}
            <div className="bg-gradient-to-br from-green-50 to-emerald-50 p-6 rounded-xl border border-green-200">
              <h4 className="text-sm font-semibold text-gray-700 mb-4">Pricing Health</h4>

              <div className="flex items-center justify-center mb-4">
                {agent.pricingHealth?.status === 'healthy' ? (
                  <div className="flex flex-col items-center">
                    <CheckCircle size={48} className="text-green-600 mb-2" />
                    <span className="text-lg font-bold text-green-700">Healthy</span>
                  </div>
                ) : (
                  <div className="flex flex-col items-center">
                    <XCircle size={48} className="text-red-600 mb-2" />
                    <span className="text-lg font-bold text-red-700">Unhealthy</span>
                  </div>
                )}
              </div>

              <div className="text-center">
                <p className="text-sm text-gray-600">Reports in last 10 min</p>
                <p className="text-2xl font-bold text-gray-900 mt-1">
                  {agent.pricingHealth?.recentReportsCount || 0}
                </p>
                <p className="text-xs text-gray-500 mt-1">
                  {agent.pricingHealth?.status === 'healthy' ? '≥ 5 required' : '< 5 reports'}
                </p>
              </div>
            </div>

            {/* Last 5 Pricing Reports */}
            <div className="bg-gradient-to-br from-purple-50 to-pink-50 p-6 rounded-xl border border-purple-200">
              <h4 className="text-sm font-semibold text-gray-700 mb-4">Recent Data Fetches</h4>

              {agent.pricingHealth?.recentReports && agent.pricingHealth.recentReports.length > 0 ? (
                <div className="space-y-2">
                  {agent.pricingHealth.recentReports.slice(0, 5).map((report, idx) => {
                    const savings = report.onDemandPrice - report.spotPrice;
                    const savingsPercent = (savings / report.onDemandPrice * 100).toFixed(1);

                    return (
                      <div key={idx} className="bg-white p-3 rounded-lg border border-purple-200 shadow-sm">
                        <div className="flex items-center justify-between mb-2">
                          <div className="flex items-center space-x-2">
                            <Clock size={12} className="text-gray-400" />
                            <span className="text-xs text-gray-600">
                              {new Date(report.time).toLocaleTimeString()}
                            </span>
                          </div>
                          {parseFloat(savingsPercent) > 0 ? (
                            <TrendingUp size={14} className="text-green-500" />
                          ) : (
                            <TrendingDown size={14} className="text-red-500" />
                          )}
                        </div>

                        <div className="grid grid-cols-2 gap-2 text-xs">
                          <div>
                            <p className="text-gray-500">On-Demand</p>
                            <p className="font-semibold text-gray-900">
                              ${report.onDemandPrice.toFixed(4)}
                            </p>
                          </div>
                          <div>
                            <p className="text-gray-500">Spot</p>
                            <p className="font-semibold text-gray-900">
                              ${report.spotPrice.toFixed(4)}
                            </p>
                          </div>
                        </div>

                        <div className="mt-2 pt-2 border-t border-gray-200">
                          <div className="flex justify-between items-center">
                            <span className="text-xs text-gray-500">Savings</span>
                            <span className={`text-xs font-bold ${
                              parseFloat(savingsPercent) > 0 ? 'text-green-600' : 'text-red-600'
                            }`}>
                              {savingsPercent}%
                            </span>
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              ) : (
                <div className="flex flex-col items-center justify-center py-8">
                  <XCircle size={32} className="text-gray-400 mb-2" />
                  <p className="text-xs text-gray-500 text-center">No pricing data available</p>
                </div>
              )}
            </div>
          </div>
        </div>
      ))}
    </div>
  );
};

export default ClientModelsTab;
