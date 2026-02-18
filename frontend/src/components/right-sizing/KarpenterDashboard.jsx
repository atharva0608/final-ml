import React, { useState, useEffect } from 'react';
import {
    FiActivity, FiDollarSign, FiCpu, FiZap, FiRefreshCw,
    FiSettings, FiPauseCircle, FiBarChart2, FiTrendingUp, FiChevronRight,
    FiCheckCircle, FiAlertCircle
} from 'react-icons/fi';
import { Card, Button, Badge } from '../shared';
import { karpenterAPI } from '../../services/api';

/**
 * KarpenterDashboard — post-setup live monitoring view.
 *
 * Props:
 *   onOpenSettings – () => void   (opens the settings slide-over)
 *   onPause        – () => void   (pauses all clusters)
 */
const KarpenterDashboard = ({ onOpenSettings, onPause }) => {
    const [stats, setStats] = useState(null);
    const [activity, setActivity] = useState([]);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        loadData();
    }, []);

    const loadData = async () => {
        try {
            setLoading(true);
            const [statsRes, actRes] = await Promise.all([
                karpenterAPI.getStats('week'),
                karpenterAPI.getActivity(null, 10),
            ]);
            setStats(statsRes.data);
            setActivity(actRes.data.events || []);
        } catch (err) {
            console.error('Failed to load Karpenter data:', err);
        } finally {
            setLoading(false);
        }
    };

    if (loading) {
        return (
            <div className="min-h-[300px] flex items-center justify-center">
                <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-blue-600"></div>
            </div>
        );
    }

    const kpis = [
        {
            label: 'Avg Utilization',
            value: `${stats?.avg_utilization_pct || 0}%`,
            sub: `↑ from ${stats?.prev_utilization_pct || 0}%`,
            color: 'text-blue-600',
            icon: <FiCpu className="w-4 h-4" />,
        },
        {
            label: 'Optimizations Made',
            value: stats?.optimizations_count || 0,
            sub: 'auto-sizes',
            color: 'text-purple-600',
            icon: <FiRefreshCw className="w-4 h-4" />,
        },
        {
            label: 'Cost Saved',
            value: `$${(stats?.cost_saved || 0).toLocaleString()}`,
            sub: 'this week',
            color: 'text-green-600',
            icon: <FiDollarSign className="w-4 h-4" />,
        },
        {
            label: 'Spot Coverage',
            value: `${stats?.spot_coverage_pct || 0}%`,
            sub: 'of nodes',
            color: 'text-amber-600',
            icon: <FiZap className="w-4 h-4" />,
        },
    ];

    const eventIcons = {
        consolidation: <FiRefreshCw className="w-4 h-4 text-blue-500" />,
        instance_switch: <FiRefreshCw className="w-4 h-4 text-purple-500" />,
        spot_replacement: <FiZap className="w-4 h-4 text-amber-500" />,
    };

    return (
        <div className="space-y-5">
            {/* Status header */}
            <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                    <div className="flex items-center gap-2">
                        <FiZap className="w-5 h-5 text-blue-600" />
                        <h2 className="text-lg font-bold text-gray-900">Karpenter Auto-Optimization</h2>
                    </div>
                    <Badge variant="success">
                        <span className="inline-block w-2 h-2 rounded-full bg-green-500 mr-1 animate-pulse"></span>
                        ACTIVE
                    </Badge>
                </div>
                <Button variant="outline" size="sm" onClick={onOpenSettings}>
                    <FiSettings className="w-4 h-4 mr-1" /> Settings
                </Button>
            </div>

            <p className="text-xs text-gray-500">
                Running on {stats?.clusters?.length || 0} clusters • Managing {stats?.clusters?.reduce((s, c) => s + c.nodes, 0) || 0} nodes • Last activity: {activity[0]?.timestamp ? new Date(activity[0].timestamp).toLocaleTimeString() : '—'}
            </p>

            {/* KPI Strip */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                {kpis.map((kpi, i) => (
                    <Card key={i} className="!p-4">
                        <div className="flex items-center gap-2 mb-1">
                            <span className={kpi.color}>{kpi.icon}</span>
                            <span className="text-[10px] font-semibold uppercase text-gray-400">{kpi.label}</span>
                        </div>
                        <div className={`text-2xl font-bold ${kpi.color}`}>{kpi.value}</div>
                        <div className="text-[10px] text-gray-400">{kpi.sub}</div>
                    </Card>
                ))}
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
                {/* Activity Feed */}
                <div className="lg:col-span-2">
                    <Card title="Live Activity Feed" className="overflow-hidden">
                        {activity.length === 0 ? (
                            <div className="text-center text-gray-400 py-6 text-sm">No recent activity</div>
                        ) : (
                            <div className="divide-y divide-gray-50">
                                {activity.map((evt) => (
                                    <div key={evt.id} className="p-4 hover:bg-gray-50/50 transition-colors">
                                        <div className="flex items-start gap-3">
                                            <div className="mt-0.5">{eventIcons[evt.type] || <FiActivity className="w-4 h-4 text-gray-400" />}</div>
                                            <div className="flex-1 min-w-0">
                                                <div className="flex items-center gap-2 mb-0.5">
                                                    <span className="text-[10px] text-gray-400">
                                                        {new Date(evt.timestamp).toLocaleTimeString()}
                                                    </span>
                                                    <Badge variant="default">{evt.cluster}</Badge>
                                                </div>
                                                <div className="text-sm font-medium text-gray-900">{evt.title}</div>
                                                <ul className="mt-1 space-y-0.5">
                                                    {(evt.details || []).map((d, i) => (
                                                        <li key={i} className="text-xs text-gray-500">• {d}</li>
                                                    ))}
                                                </ul>
                                                <div className="flex gap-3 mt-1 text-[10px]">
                                                    {evt.savings_daily && (
                                                        <span className="text-green-600 font-medium flex items-center gap-1">
                                                            <FiDollarSign className="w-3 h-3" /> Saved: ${evt.savings_daily}/day
                                                        </span>
                                                    )}
                                                    {evt.utilization_after && (
                                                        <span className="text-blue-600 flex items-center gap-1">
                                                            <FiTrendingUp className="w-3 h-3" /> Utilization now: {evt.utilization_after}%
                                                        </span>
                                                    )}
                                                    {evt.zero_downtime && (
                                                        <span className="text-green-600 flex items-center gap-1">
                                                            <FiActivity className="w-3 h-3" /> Zero downtime • {evt.reschedule_seconds}s reschedule
                                                        </span>
                                                    )}
                                                </div>
                                            </div>
                                        </div>
                                    </div>
                                ))}
                            </div>
                        )}
                    </Card>
                </div>

                {/* Cluster Breakdown with Progress Bars */}
                <div>
                    <Card title="Cluster Breakdown">
                        <div className="space-y-4">
                            {(stats?.clusters || []).map((cl) => (
                                <div key={cl.cluster_id} className="border border-gray-100 rounded-lg p-3 hover:border-gray-200 transition-colors">
                                    <div className="flex items-center gap-2 mb-2">
                                        <span className="inline-block w-2 h-2 rounded-full bg-green-500"></span>
                                        <span className="text-sm font-semibold text-gray-900">{cl.name}</span>
                                        <span className="text-[10px] text-gray-400">({cl.region})</span>
                                        <Badge variant="default" className="!text-[9px] !px-1.5 !py-0">
                                            {cl.strategy}
                                        </Badge>
                                    </div>

                                    {/* Utilization Progress Bar */}
                                    <div className="mb-2">
                                        <div className="flex items-center justify-between text-xs mb-1">
                                            <span className="text-gray-500">CPU Utilization</span>
                                            <span className="font-medium text-gray-900">{cl.utilization_pct}%</span>
                                        </div>
                                        <div className="h-2 bg-gray-100 rounded-full overflow-hidden">
                                            <div
                                                className={`h-full transition-all duration-500 ${
                                                    cl.utilization_pct >= 70 ? 'bg-green-500' :
                                                    cl.utilization_pct >= 50 ? 'bg-blue-500' :
                                                    'bg-amber-500'
                                                }`}
                                                style={{ width: `${Math.min(cl.utilization_pct, 100)}%` }}
                                            ></div>
                                        </div>
                                    </div>

                                    {/* Spot Coverage Progress Bar */}
                                    <div className="mb-2">
                                        <div className="flex items-center justify-between text-xs mb-1">
                                            <span className="text-gray-500">Spot Coverage</span>
                                            <span className="font-medium text-gray-900">{cl.spot_pct}%</span>
                                        </div>
                                        <div className="h-2 bg-gray-100 rounded-full overflow-hidden">
                                            <div
                                                className="h-full bg-purple-500 transition-all duration-500"
                                                style={{ width: `${Math.min(cl.spot_pct, 100)}%` }}
                                            ></div>
                                        </div>
                                    </div>

                                    <div className="space-y-0.5 text-xs text-gray-500 pt-2 border-t border-gray-50">
                                        <div className="flex items-center justify-between">
                                            <span>Nodes: {cl.nodes}</span>
                                            <span>Optimizations: {cl.optimizations_24h}/24h</span>
                                        </div>
                                        <div className="flex items-center justify-between">
                                            <span>Cost: ${cl.cost_current}/wk</span>
                                            <span className="text-green-600 font-medium">
                                                Saved: ${cl.cost_before - cl.cost_current}/wk
                                            </span>
                                        </div>
                                    </div>
                                </div>
                            ))}
                        </div>
                    </Card>
                </div>
            </div>

            {/* Savings Summary Cards */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <Card className="!p-5 bg-gradient-to-br from-green-50 to-emerald-50 border-green-200">
                    <div className="flex items-start justify-between mb-2">
                        <div className="flex-shrink-0">
                            <div className="w-10 h-10 bg-green-500 rounded-lg flex items-center justify-center">
                                <FiDollarSign className="w-5 h-5 text-white" />
                            </div>
                        </div>
                        <Badge variant="success" className="!text-[9px]">THIS WEEK</Badge>
                    </div>
                    <div className="text-2xl font-bold text-gray-900 mb-1">
                        ${(stats?.cost_saved || 0).toLocaleString()}
                    </div>
                    <div className="text-xs text-gray-600">Cost Saved</div>
                    <div className="text-[10px] text-green-700 mt-1">
                        ${((stats?.cost_saved || 0) * 4.33).toFixed(0)}/month projected
                    </div>
                </Card>

                <Card className="!p-5 bg-gradient-to-br from-blue-50 to-indigo-50 border-blue-200">
                    <div className="flex items-start justify-between mb-2">
                        <div className="flex-shrink-0">
                            <div className="w-10 h-10 bg-blue-500 rounded-lg flex items-center justify-center">
                                <FiCpu className="w-5 h-5 text-white" />
                            </div>
                        </div>
                        <Badge variant="info" className="!text-[9px]">AVG</Badge>
                    </div>
                    <div className="text-2xl font-bold text-gray-900 mb-1">
                        {stats?.avg_utilization_pct || 0}%
                    </div>
                    <div className="text-xs text-gray-600">Resource Utilization</div>
                    <div className="text-[10px] text-blue-700 mt-1 flex items-center gap-1">
                        <FiTrendingUp className="w-3 h-3" />
                        +{((stats?.avg_utilization_pct || 0) - (stats?.prev_utilization_pct || 0))}% improvement
                    </div>
                </Card>

                <Card className="!p-5 bg-gradient-to-br from-purple-50 to-pink-50 border-purple-200">
                    <div className="flex items-start justify-between mb-2">
                        <div className="flex-shrink-0">
                            <div className="w-10 h-10 bg-purple-500 rounded-lg flex items-center justify-center">
                                <FiRefreshCw className="w-5 h-5 text-white" />
                            </div>
                        </div>
                        <Badge variant="default" className="!text-[9px]">AUTOMATIC</Badge>
                    </div>
                    <div className="text-2xl font-bold text-gray-900 mb-1">
                        {stats?.optimizations_count || 0}
                    </div>
                    <div className="text-xs text-gray-600">Optimizations Made</div>
                    <div className="text-[10px] text-purple-700 mt-1">
                        Automated adjustments
                    </div>
                </Card>
            </div>

            {/* Cost Trend + Instance Distribution */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
                {/* Cost Trend with Enhanced Visualization */}
                <Card title="Cost Trend (Last 30 Days)">
                    {stats?.cost_trend ? (
                        <div className="space-y-3">
                            {/* Legend */}
                            <div className="flex items-center gap-4 text-[10px] pb-2 border-b border-gray-100">
                                <div className="flex items-center gap-1.5">
                                    <div className="w-3 h-3 bg-red-300 rounded"></div>
                                    <span className="text-gray-500">Before Karpenter</span>
                                </div>
                                <div className="flex items-center gap-1.5">
                                    <div className="w-3 h-3 bg-green-500 rounded"></div>
                                    <span className="text-gray-500">With Karpenter</span>
                                </div>
                            </div>

                            {/* Bar Chart */}
                            <div className="space-y-2">
                                {stats.cost_trend.map((week, i) => {
                                    const maxCost = 10000;
                                    const beforeWidth = week.before ? (week.before / maxCost) * 100 : 0;
                                    const afterWidth = week.after ? (week.after / maxCost) * 100 : 0;

                                    return (
                                        <div key={i} className="space-y-1">
                                            <div className="flex items-center gap-2 text-xs">
                                                <span className="w-16 text-gray-500 font-medium">{week.week}</span>
                                                <div className="flex-1">
                                                    {week.before && (
                                                        <div className="mb-0.5">
                                                            <div className="h-4 bg-red-200 rounded flex items-center px-2" style={{ width: `${Math.max(beforeWidth, 15)}%` }}>
                                                                <span className="text-[10px] text-gray-700">${week.before.toLocaleString()}</span>
                                                            </div>
                                                        </div>
                                                    )}
                                                    {week.after && (
                                                        <div>
                                                            <div className="h-4 bg-green-400 rounded flex items-center px-2" style={{ width: `${Math.max(afterWidth, 15)}%` }}>
                                                                <span className="text-[10px] text-white font-medium">${week.after.toLocaleString()}</span>
                                                            </div>
                                                        </div>
                                                    )}
                                                </div>
                                                {week.before && week.after && (
                                                    <span className="text-[10px] text-green-600 font-semibold w-12 text-right">
                                                        -{Math.round(((week.before - week.after) / week.before) * 100)}%
                                                    </span>
                                                )}
                                            </div>
                                        </div>
                                    );
                                })}
                            </div>

                            <div className="text-xs text-gray-500 pt-2 border-t border-gray-100 flex items-center gap-1">
                                <FiDollarSign className="w-3 h-3 text-green-600" />
                                Total saved: ${(stats.total_saved || 0).toLocaleString()} • Average reduction: {stats.avg_reduction_pct}%
                            </div>
                        </div>
                    ) : (
                        <div className="text-center text-gray-400 text-sm py-4">No cost data yet</div>
                    )}
                </Card>

                {/* Instance Distribution */}
                <Card title="Instance Type Distribution">
                    {stats?.instance_distribution ? (
                        <div className="space-y-4">
                            <div>
                                <div className="text-[10px] text-gray-400 font-semibold uppercase mb-1">Before Karpenter</div>
                                <div className="flex h-5 rounded-full overflow-hidden">
                                    {Object.entries(stats.instance_distribution.before).map(([type, pct], i) => (
                                        <div key={type} className={`flex items-center justify-center text-[9px] text-white font-medium ${['bg-red-400', 'bg-orange-400', 'bg-yellow-500'][i % 3]
                                            }`} style={{ width: `${pct}%` }} title={`${type}: ${pct}%`}>
                                            {pct > 12 && `${type} ${pct}%`}
                                        </div>
                                    ))}
                                </div>
                            </div>
                            <div>
                                <div className="text-[10px] text-gray-400 font-semibold uppercase mb-1">With Karpenter (Now)</div>
                                <div className="flex h-5 rounded-full overflow-hidden">
                                    {Object.entries(stats.instance_distribution.after).map(([type, pct], i) => (
                                        <div key={type} className={`flex items-center justify-center text-[9px] text-white font-medium ${['bg-blue-500', 'bg-indigo-500', 'bg-teal-500', 'bg-emerald-500', 'bg-gray-400'][i % 5]
                                            }`} style={{ width: `${pct}%` }} title={`${type}: ${pct}%`}>
                                            {pct > 12 && `${type} ${pct}%`}
                                        </div>
                                    ))}
                                </div>
                            </div>
                            <div className="text-xs text-green-600 flex items-center gap-1">
                                <FiActivity className="w-3 h-3" />
                                More diverse = better pricing + better availability
                            </div>
                        </div>
                    ) : (
                        <div className="text-center text-gray-400 text-sm py-4">No distribution data yet</div>
                    )}
                </Card>
            </div>

            {/* Bottom Actions */}
            <div className="flex items-center gap-3">
                <Button variant="outline" size="sm" onClick={onOpenSettings}>
                    <FiSettings className="w-4 h-4 mr-1" /> Manage Configuration
                </Button>
                <Button variant="outline" size="sm" onClick={onPause}>
                    <FiPauseCircle className="w-4 h-4 mr-1" /> Pause Karpenter
                </Button>
                <Button variant="outline" size="sm" onClick={loadData}>
                    <FiBarChart2 className="w-4 h-4 mr-1" /> Refresh
                </Button>
            </div>
        </div>
    );
};

export default KarpenterDashboard;
