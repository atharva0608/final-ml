import React, { useState, useEffect } from 'react';
import { decisionEngineAPI } from '../../services/api';
import { FiActivity, FiCheckCircle, FiAlertCircle, FiClock } from 'react-icons/fi';

const GlobalIntelligencePanel = ({ region = 'ap-south-1' }) => {
    const [intelligence, setIntelligence] = useState(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        const fetchIntelligence = async () => {
            try {
                const response = await decisionEngineAPI.getGlobalIntelligenceStatus(region);
                setIntelligence(response.data);
            } catch (err) {
                console.error('Failed to fetch global intelligence:', err);
            } finally {
                setLoading(false);
            }
        };

        fetchIntelligence();
        const interval = setInterval(fetchIntelligence, 15000);
        return () => clearInterval(interval);
    }, [region]);

    if (loading) {
        return (
            <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6 animate-pulse">
                <div className="h-6 bg-gray-200 rounded w-1/2 mb-4"></div>
                <div className="grid grid-cols-3 gap-4">
                    {[1, 2, 3].map(i => (
                        <div key={i} className="h-20 bg-gray-200 rounded"></div>
                    ))}
                </div>
            </div>
        );
    }

    if (!intelligence || intelligence.status === 'no_rankings_available') {
        return (
            <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
                <h3 className="text-lg font-semibold text-gray-900 mb-4 flex items-center">
                    <FiActivity className="mr-2 text-indigo-600" />
                    Global Intelligence Status
                </h3>
                <p className="text-sm text-gray-500">No rankings data available for {region}</p>
            </div>
        );
    }

    const budgetUsedPct = (intelligence.dryrun_budget_used / intelligence.dryrun_budget_max) * 100;
    const capacityPct = intelligence.pools_evaluated > 0
        ? (intelligence.capacity_validated_count / intelligence.pools_evaluated) * 100
        : 0;

    // Calculate time since last ranking
    const lastRankingTime = intelligence.last_ranking_timestamp
        ? new Date(intelligence.last_ranking_timestamp)
        : null;
    const minutesSinceRanking = lastRankingTime
        ? Math.floor((Date.now() - lastRankingTime.getTime()) / 60000)
        : null;

    const isBudgetCritical = budgetUsedPct > 80;
    const isBudgetWarning = budgetUsedPct > 60;

    return (
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
            <div className="flex items-center justify-between mb-6">
                <h3 className="text-lg font-semibold text-gray-900 flex items-center">
                    <FiActivity className="mr-2 text-indigo-600" />
                    Global Intelligence Status
                </h3>
                {lastRankingTime && (
                    <div className="flex items-center text-sm text-gray-500">
                        <FiClock className="mr-1.5" />
                        {minutesSinceRanking}m ago
                    </div>
                )}
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
                {/* Pools Evaluated */}
                <div className="p-4 bg-indigo-50 rounded-lg border border-indigo-200">
                    <div className="text-xs font-medium text-indigo-600 uppercase mb-1">Pools Evaluated</div>
                    <div className="text-3xl font-bold text-indigo-900">{intelligence.pools_evaluated}</div>
                    <div className="text-xs text-indigo-600 mt-1">Model v{intelligence.model_version}</div>
                </div>

                {/* Capacity Validated */}
                <div className="p-4 bg-green-50 rounded-lg border border-green-200">
                    <div className="text-xs font-medium text-green-600 uppercase mb-1">Capacity Validated</div>
                    <div className="text-3xl font-bold text-green-900">{intelligence.capacity_validated_count}</div>
                    <div className="text-xs text-green-600 mt-1">{capacityPct.toFixed(0)}% of pools</div>
                </div>

                {/* DryRun Budget */}
                <div className={`p-4 rounded-lg border ${isBudgetCritical ? 'bg-red-50 border-red-200' : isBudgetWarning ? 'bg-orange-50 border-orange-200' : 'bg-blue-50 border-blue-200'}`}>
                    <div className={`text-xs font-medium uppercase mb-1 ${isBudgetCritical ? 'text-red-600' : isBudgetWarning ? 'text-orange-600' : 'text-blue-600'}`}>
                        DryRun Budget
                    </div>
                    <div className={`text-3xl font-bold ${isBudgetCritical ? 'text-red-900' : isBudgetWarning ? 'text-orange-900' : 'text-blue-900'}`}>
                        {intelligence.dryrun_budget_used}
                        <span className="text-lg text-gray-500 font-normal"> / {intelligence.dryrun_budget_max}</span>
                    </div>
                    <div className={`text-xs mt-1 ${isBudgetCritical ? 'text-red-600' : isBudgetWarning ? 'text-orange-600' : 'text-blue-600'}`}>
                        {budgetUsedPct.toFixed(1)}% used
                    </div>
                </div>
            </div>

            {/* DryRun Budget Bar */}
            <div className="mb-4">
                <div className="flex items-center justify-between text-sm mb-2">
                    <span className="font-medium text-gray-700">DryRun API Budget</span>
                    <span className={`font-semibold ${isBudgetCritical ? 'text-red-600' : isBudgetWarning ? 'text-orange-600' : 'text-gray-600'}`}>
                        {intelligence.dryrun_budget_remaining} remaining
                    </span>
                </div>
                <div className="w-full bg-gray-200 rounded-full h-3">
                    <div
                        className={`h-3 rounded-full transition-all ${isBudgetCritical ? 'bg-red-500' : isBudgetWarning ? 'bg-orange-500' : 'bg-indigo-600'}`}
                        style={{ width: `${Math.min(budgetUsedPct, 100)}%` }}
                    ></div>
                </div>
            </div>

            {/* Status Indicators */}
            <div className="flex items-center gap-4 pt-4 border-t border-gray-200">
                {isBudgetCritical ? (
                    <div className="flex items-center text-sm text-red-700 bg-red-50 px-3 py-1.5 rounded-lg">
                        <FiAlertCircle className="mr-1.5" />
                        Budget Critical - Capacity checks throttled
                    </div>
                ) : (
                    <div className="flex items-center text-sm text-green-700 bg-green-50 px-3 py-1.5 rounded-lg">
                        <FiCheckCircle className="mr-1.5" />
                        Intelligence Layer Healthy
                    </div>
                )}

                <div className="text-xs text-gray-500">
                    Region: <strong>{region}</strong>
                </div>
            </div>
        </div>
    );
};

export default GlobalIntelligencePanel;
