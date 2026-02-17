import React, { useEffect, useState } from 'react';
import useAtharvaStore from '../../store/useAtharvaStore';
import { Card } from '../shared';
import {
    FiTrendingUp, FiTrendingDown, FiMinus, FiStar, FiAlertCircle,
    FiInfo, FiFilter, FiArrowUp, FiArrowDown, FiChevronRight, FiRefreshCw
} from 'react-icons/fi';

const getRiskColor = (interruptionRank) => {
    if (interruptionRank === 0) return 'text-green-600 bg-green-50';
    if (interruptionRank === 1) return 'text-blue-600 bg-blue-50';
    if (interruptionRank === 2) return 'text-yellow-600 bg-yellow-50';
    if (interruptionRank === 3) return 'text-orange-600 bg-orange-50';
    return 'text-red-600 bg-red-50';
};

const getInterruptionLabel = (rank) => {
    const labels = { 0: '<5%', 1: '5-10%', 2: '10-15%', 3: '15-20%', 4: '>20%' };
    return labels[rank] || 'Unknown';
};

const getSavingsColor = (savingsPct) => {
    if (savingsPct >= 0.90) return 'text-green-600';
    if (savingsPct >= 0.70) return 'text-yellow-600';
    return 'text-red-600';
};

const LivePoolRankings = () => {
    const { poolRankings, filteringStats, fetchPoolRankings, blacklist } = useAtharvaStore();
    const [autoRefresh, setAutoRefresh] = useState(true);
    const [refreshing, setRefreshing] = useState(false);

    useEffect(() => {
        // Auto-refresh every 30 seconds
        const interval = setInterval(() => {
            if (autoRefresh) {
                handleRefresh();
            }
        }, 30000);

        return () => clearInterval(interval);
    }, [autoRefresh]);

    const handleRefresh = async () => {
        setRefreshing(true);
        await fetchPoolRankings();
        setRefreshing(false);
    };

    if (!poolRankings || poolRankings.length === 0) {
        return (
            <Card className="border-gray-200">
                <div className="p-8 text-center text-gray-400">
                    <FiFilter className="w-8 h-8 mx-auto mb-3" />
                    <p className="font-medium">No pool rankings available</p>
                    <p className="text-xs mt-1">Click refresh to load ML-scored pool rankings</p>
                    <button
                        onClick={handleRefresh}
                        className="mt-4 px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 transition-colors"
                    >
                        <FiRefreshCw className="inline w-4 h-4 mr-2" />
                        Load Rankings
                    </button>
                </div>
            </Card>
        );
    }

    // Check if pool is in blacklist
    const isPoolBlacklisted = (instanceType, az) => {
        return blacklist.some(b => b.instance_type === instanceType && b.az === az);
    };

    return (
        <Card className="border-gray-200">
            {/* Header */}
            <div className="flex items-center justify-between mb-4">
                <div className="flex items-center gap-3">
                    <h3 className="text-lg font-semibold text-gray-900">Live Pool Rankings</h3>
                    <span className="relative flex h-2 w-2">
                        <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75"></span>
                        <span className="relative inline-flex rounded-full h-2 w-2 bg-green-500"></span>
                    </span>
                </div>
                <div className="flex items-center gap-2">
                    <label className="flex items-center text-xs text-gray-600">
                        <input
                            type="checkbox"
                            checked={autoRefresh}
                            onChange={(e) => setAutoRefresh(e.target.checked)}
                            className="mr-1"
                        />
                        Auto-refresh (30s)
                    </label>
                    <button
                        onClick={handleRefresh}
                        disabled={refreshing}
                        className="p-2 text-gray-600 hover:bg-gray-100 rounded-md transition-colors disabled:opacity-50"
                        title="Refresh rankings"
                    >
                        <FiRefreshCw className={`w-4 h-4 ${refreshing ? 'animate-spin' : ''}`} />
                    </button>
                </div>
            </div>

            {/* Pipeline Stats */}
            {filteringStats && (
                <div className="mb-4 p-2.5 bg-blue-50 border border-blue-200 rounded-lg">
                    <div className="flex items-center gap-2 text-xs text-blue-700">
                        <FiFilter className="w-3.5 h-3.5" />
                        <span className="font-semibold">8-Step Pipeline:</span>
                        <span>Total Pools: <strong>{filteringStats.total_pools || poolRankings.length}</strong></span>
                        <FiChevronRight className="w-3 h-3" />
                        <span>ML Scored: <strong>{poolRankings.length}</strong></span>
                    </div>
                </div>
            )}

            {/* Global Blacklist Alert */}
            {blacklist && blacklist.length > 0 && (
                <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-lg">
                    <div className="flex items-center gap-2 mb-2">
                        <FiAlertCircle className="w-4 h-4 text-red-600" />
                        <h4 className="text-sm font-semibold text-red-800">
                            Globally Flagged Pools ({blacklist.length})
                        </h4>
                    </div>
                    <div className="flex flex-wrap gap-2">
                        {blacklist.map((item, idx) => (
                            <span
                                key={idx}
                                className="px-2 py-1 bg-red-100 text-red-800 rounded-full text-xs"
                            >
                                {item.instance_type}:{item.az}
                                <span className="text-[10px] ml-1">
                                    ({Math.floor(item.ttl_remaining_seconds / 3600)}h left)
                                </span>
                            </span>
                        ))}
                    </div>
                </div>
            )}

            {/* Rankings Table */}
            <div className="overflow-x-auto">
                <table className="min-w-full text-sm">
                    <thead>
                        <tr className="text-left text-gray-500 text-xs border-b border-gray-200">
                            <th className="pb-2 pr-3 font-medium w-12">#</th>
                            <th className="pb-2 pr-3 font-medium">Instance Type</th>
                            <th className="pb-2 pr-3 font-medium">AZ</th>
                            <th className="pb-2 pr-3 font-medium">Specs</th>
                            <th className="pb-2 pr-3 font-medium">Spot Price</th>
                            <th className="pb-2 pr-3 font-medium">Savings %</th>
                            <th className="pb-2 pr-3 font-medium">Cost/Day</th>
                            <th className="pb-2 pr-3 font-medium">Interruption</th>
                            <th className="pb-2 font-medium text-right">ML Score</th>
                        </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-100">
                        {poolRankings.map((pool) => {
                            const isFlagged = pool.is_flagged || isPoolBlacklisted(pool.instance_type, pool.az);
                            const riskColors = getRiskColor(pool.spot_advisor_rank);

                            return (
                                <tr
                                    key={`${pool.instance_type}-${pool.az}`}
                                    className={`group transition-colors ${
                                        isFlagged
                                            ? 'bg-red-50/50 opacity-60'
                                            : pool.rank <= 3
                                            ? 'bg-green-50/20'
                                            : 'hover:bg-gray-50'
                                    }`}
                                >
                                    {/* Rank */}
                                    <td className="py-3 pr-3">
                                        <span className={`inline-flex items-center justify-center w-7 h-7 rounded-full font-bold text-sm ${
                                            pool.rank === 1 ? 'bg-yellow-100 text-yellow-800' :
                                            pool.rank <= 3 ? 'bg-green-100 text-green-800' :
                                            'bg-gray-100 text-gray-700'
                                        }`}>
                                            {pool.rank}
                                        </span>
                                    </td>

                                    {/* Instance Type */}
                                    <td className="py-3 pr-3">
                                        <div className="flex items-center gap-1.5">
                                            <p className="font-medium text-gray-900">{pool.instance_type}</p>
                                            {pool.rank === 1 && <FiStar className="w-3 h-3 text-yellow-500" />}
                                            {isFlagged && <FiAlertCircle className="w-3 h-3 text-red-500" />}
                                        </div>
                                        <p className="text-[10px] text-gray-400">{pool.architecture}</p>
                                    </td>

                                    {/* AZ */}
                                    <td className="py-3 pr-3 text-gray-700">
                                        {pool.az}
                                    </td>

                                    {/* Specs */}
                                    <td className="py-3 pr-3 text-gray-600 text-xs">
                                        {pool.vcpu}vCPU / {pool.memory_gb}GB
                                    </td>

                                    {/* Spot Price */}
                                    <td className="py-3 pr-3">
                                        <p className="font-medium text-gray-900">${pool.spot_price.toFixed(4)}/hr</p>
                                        <p className="text-[10px] text-gray-400">vs ${pool.ondemand_price.toFixed(4)}</p>
                                    </td>

                                    {/* Savings % */}
                                    <td className="py-3 pr-3">
                                        <span className={`text-sm font-bold ${getSavingsColor(pool.savings_pct)}`}>
                                            {(pool.savings_pct * 100).toFixed(1)}%
                                        </span>
                                    </td>

                                    {/* Cost Estimate */}
                                    <td className="py-3 pr-3 font-medium text-gray-900">
                                        ${pool.cost_estimate.toFixed(2)}
                                    </td>

                                    {/* Interruption Rate */}
                                    <td className="py-3 pr-3">
                                        <span className={`px-2 py-1 inline-flex text-xs font-semibold rounded-full ${riskColors}`}>
                                            {getInterruptionLabel(pool.spot_advisor_rank)}
                                        </span>
                                    </td>

                                    {/* ML Score */}
                                    <td className="py-3 text-right">
                                        <div className="text-sm font-bold text-blue-600">{pool.ml_score.toFixed(2)}</div>
                                        <div className="text-[10px] text-gray-400">ML Score</div>
                                    </td>
                                </tr>
                            );
                        })}
                    </tbody>
                </table>
            </div>

            {/* Legend */}
            <div className="mt-4 pt-4 border-t border-gray-200">
                <div className="grid grid-cols-1 md:grid-cols-3 gap-3 text-xs text-gray-600">
                    <div>
                        <span className="font-semibold">ML Score:</span> Combined savings % and cost (higher = better)
                    </div>
                    <div>
                        <span className="font-semibold">Savings %:</span> Spot vs On-Demand price difference
                    </div>
                    <div>
                        <span className="font-semibold">Interruption:</span> AWS Spot Advisor frequency rating
                    </div>
                </div>
            </div>
        </Card>
    );
};

export default LivePoolRankings;
