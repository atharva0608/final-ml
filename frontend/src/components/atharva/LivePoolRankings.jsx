import React from 'react';
import useAtharvaStore from '../../store/useAtharvaStore';
import { Card } from '../shared';
import {
    FiTrendingUp, FiTrendingDown, FiMinus, FiStar, FiAlertCircle,
    FiInfo, FiFilter, FiArrowUp, FiArrowDown, FiChevronRight
} from 'react-icons/fi';

const TREND_CONFIG = {
    improving: { icon: FiTrendingUp, color: 'text-green-600', label: 'Improving' },
    stable: { icon: FiMinus, color: 'text-gray-500', label: 'Stable' },
    degrading: { icon: FiTrendingDown, color: 'text-red-600', label: 'Degrading' },
};

const getRiskColor = (score) => {
    if (score < 0.3) return 'text-green-600 bg-green-50';
    if (score <= 0.6) return 'text-yellow-600 bg-yellow-50';
    return 'text-red-600 bg-red-50';
};

const LivePoolRankings = () => {
    const { poolRankings, filteringStats, openPoolDetails, openSwitchConfirm } = useAtharvaStore();

    if (!poolRankings || poolRankings.length === 0) {
        return (
            <Card className="border-gray-200">
                <div className="p-8 text-center text-gray-400">
                    <FiFilter className="w-8 h-8 mx-auto mb-3" />
                    <p className="font-medium">No pool rankings available</p>
                    <p className="text-xs mt-1">Select a cluster and template to see rankings</p>
                </div>
            </Card>
        );
    }

    return (
        <Card className="border-gray-200">
            <div className="flex items-center justify-between mb-4">
                <h3 className="text-lg font-semibold text-gray-900">Live Pool Rankings</h3>
                <span className="relative flex h-2 w-2">
                    <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75"></span>
                    <span className="relative inline-flex rounded-full h-2 w-2 bg-green-500"></span>
                </span>
            </div>

            {/* Filtering Pipeline Stats */}
            {filteringStats && (
                <div className="flex items-center gap-2 mb-4 p-2.5 bg-gray-50 rounded-lg text-[10px] font-medium text-gray-500 overflow-x-auto">
                    <FiFilter className="w-3 h-3 flex-shrink-0" />
                    <span>{filteringStats.total_pools_available} total</span>
                    <FiChevronRight className="w-3 h-3 flex-shrink-0" />
                    <span>{filteringStats.after_template_filter} template</span>
                    <FiChevronRight className="w-3 h-3 flex-shrink-0" />
                    <span>{filteringStats.after_interruption_filter} interrupt</span>
                    <FiChevronRight className="w-3 h-3 flex-shrink-0" />
                    <span>{filteringStats.after_blacklist_filter} blacklist</span>
                    <FiChevronRight className="w-3 h-3 flex-shrink-0" />
                    <span>{filteringStats.after_uniqueness_filter} unique</span>
                    <FiChevronRight className="w-3 h-3 flex-shrink-0" />
                    <span className="text-blue-600 font-bold">{filteringStats.final_top_10} shown</span>
                </div>
            )}

            {/* Rankings Table */}
            <div className="overflow-x-auto">
                <table className="min-w-full text-sm">
                    <thead>
                        <tr className="text-left text-gray-500 text-xs border-b border-gray-200">
                            <th className="pb-2 pr-3 font-medium w-12">#</th>
                            <th className="pb-2 pr-3 font-medium">Pool</th>
                            <th className="pb-2 pr-3 font-medium">Risk</th>
                            <th className="pb-2 pr-3 font-medium">Interrupt</th>
                            <th className="pb-2 pr-3 font-medium">Cost/hr</th>
                            <th className="pb-2 pr-3 font-medium">Nodes</th>
                            <th className="pb-2 pr-3 font-medium">Trend</th>
                            <th className="pb-2 font-medium text-right">Actions</th>
                        </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-100">
                        {poolRankings.map((pool) => {
                            const TrendIcon = TREND_CONFIG[pool.trend]?.icon || FiMinus;
                            const trendColor = TREND_CONFIG[pool.trend]?.color || 'text-gray-500';
                            const riskColors = getRiskColor(pool.risk_score);

                            return (
                                <tr
                                    key={pool.pool_id}
                                    className={`group transition-colors ${pool.is_blacklisted
                                            ? 'bg-red-50/50 line-through opacity-60'
                                            : pool.is_current
                                                ? 'bg-yellow-50/30'
                                                : 'hover:bg-gray-50'
                                        }`}
                                >
                                    {/* Rank */}
                                    <td className="py-3 pr-3">
                                        <div className="flex items-center gap-1">
                                            <span className="font-bold text-gray-900 w-5">{pool.rank}</span>
                                            {pool.rank_change !== 0 && (
                                                <span className={`text-[10px] flex items-center ${pool.rank_change > 0 ? 'text-red-500' : 'text-green-500'}`}>
                                                    {pool.rank_change > 0 ? <FiArrowDown className="w-2.5 h-2.5" /> : <FiArrowUp className="w-2.5 h-2.5" />}
                                                    {Math.abs(pool.rank_change)}
                                                </span>
                                            )}
                                        </div>
                                    </td>

                                    {/* Pool Name */}
                                    <td className="py-3 pr-3">
                                        <button
                                            onClick={() => openPoolDetails(pool.pool_id)}
                                            className="text-left hover:text-blue-600 transition-colors"
                                        >
                                            <p className="font-medium text-gray-900 flex items-center gap-1.5">
                                                {pool.instance_type}
                                                {pool.is_current && <FiStar className="w-3 h-3 text-yellow-500" />}
                                                {pool.is_blacklisted && <FiAlertCircle className="w-3 h-3 text-red-500" />}
                                            </p>
                                            <p className="text-[10px] text-gray-400">{pool.availability_zone}</p>
                                        </button>
                                    </td>

                                    {/* Risk Score */}
                                    <td className="py-3 pr-3">
                                        <span className={`inline-flex px-2 py-0.5 rounded-full text-xs font-bold ${riskColors}`}>
                                            {(pool.risk_score * 100).toFixed(0)}%
                                        </span>
                                    </td>

                                    {/* Interruption Rate */}
                                    <td className="py-3 pr-3 text-gray-600">
                                        {(pool.interruption_rate * 100).toFixed(1)}%
                                    </td>

                                    {/* Hourly Cost */}
                                    <td className="py-3 pr-3 font-medium text-gray-900">
                                        ${pool.hourly_cost.toFixed(4)}
                                    </td>

                                    {/* Current Nodes */}
                                    <td className="py-3 pr-3 text-gray-600">
                                        {pool.current_nodes || '—'}
                                    </td>

                                    {/* Trend */}
                                    <td className="py-3 pr-3">
                                        <div className={`flex items-center gap-1 ${trendColor}`}>
                                            <TrendIcon className="w-3.5 h-3.5" />
                                        </div>
                                    </td>

                                    {/* Actions */}
                                    <td className="py-3 text-right">
                                        <div className="flex items-center gap-1 justify-end opacity-0 group-hover:opacity-100 transition-opacity">
                                            {!pool.is_current && !pool.is_blacklisted && (
                                                <button
                                                    onClick={() => openSwitchConfirm(pool)}
                                                    className="px-2.5 py-1 bg-blue-600 text-white text-xs font-medium rounded-md hover:bg-blue-700 transition-colors"
                                                >
                                                    Select
                                                </button>
                                            )}
                                            <button
                                                onClick={() => openPoolDetails(pool.pool_id)}
                                                className="px-2.5 py-1 bg-gray-100 text-gray-600 text-xs font-medium rounded-md hover:bg-gray-200 transition-colors"
                                            >
                                                <FiInfo className="w-3 h-3" />
                                            </button>
                                        </div>
                                    </td>
                                </tr>
                            );
                        })}
                    </tbody>
                </table>
            </div>
        </Card>
    );
};

export default LivePoolRankings;
