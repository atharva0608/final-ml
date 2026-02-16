import React from 'react';
import useAtharvaStore from '../../store/useAtharvaStore';
import { Card } from '../shared';
import {
    FiActivity, FiPower, FiPause, FiPlay, FiCpu, FiLayers,
    FiZap, FiAlertCircle, FiRefreshCw, FiUser, FiShield
} from 'react-icons/fi';

const EVENT_ICONS = {
    system_decision: { icon: FiZap, color: 'text-blue-600', bg: 'bg-blue-50' },
    manual_decision: { icon: FiUser, color: 'text-purple-600', bg: 'bg-purple-50' },
    rebalancing_started: { icon: FiRefreshCw, color: 'text-yellow-600', bg: 'bg-yellow-50' },
    rebalancing_completed: { icon: FiActivity, color: 'text-green-600', bg: 'bg-green-50' },
    pool_switched: { icon: FiLayers, color: 'text-indigo-600', bg: 'bg-indigo-50' },
    pool_blacklisted: { icon: FiAlertCircle, color: 'text-red-600', bg: 'bg-red-50' },
};

const OptimizationStatusHeader = () => {
    const { status, activityFeed, settings, updateSettings } = useAtharvaStore();

    if (!status) return null;

    const toggleOptimization = () => {
        updateSettings({
            ...settings,
            auto_rebalance: !settings.autoRebalance,
            risk_threshold: settings.riskThreshold,
            notification_channels: ["slack", "email"],
            excluded_node_groups: []
        });
    };

    const timeAgo = (ts) => {
        const diff = (Date.now() - new Date(ts).getTime()) / 1000;
        if (diff < 60) return 'just now';
        if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
        if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
        return `${Math.floor(diff / 86400)}d ago`;
    };

    return (
        <div className="mb-6">
            {/* Status Bar */}
            <Card className="border-gray-200 mb-4">
                <div className="flex items-center justify-between">
                    <div className="flex items-center gap-6">
                        {/* Optimization Toggle */}
                        <div className="flex items-center gap-3">
                            <div className={`p-2.5 rounded-lg ${status.auto_rebalance_enabled ? 'bg-green-100' : 'bg-gray-100'}`}>
                                <FiPower className={`w-5 h-5 ${status.auto_rebalance_enabled ? 'text-green-600' : 'text-gray-400'}`} />
                            </div>
                            <div>
                                <p className="text-sm font-semibold text-gray-900">Optimization Engine</p>
                                <p className="text-xs text-gray-500">
                                    {status.auto_rebalance_enabled ? 'Auto-rebalancing active' : 'Paused'}
                                </p>
                            </div>
                        </div>

                        {/* Divider */}
                        <div className="h-10 w-px bg-gray-200" />

                        {/* Quick Stats */}
                        <div className="flex items-center gap-2">
                            <FiCpu className="w-4 h-4 text-gray-400" />
                            <div>
                                <p className="text-xs text-gray-500">Nodes</p>
                                <p className="text-sm font-bold text-gray-900">{status.monitored_nodes || 0}</p>
                            </div>
                        </div>
                        <div className="flex items-center gap-2">
                            <FiLayers className="w-4 h-4 text-gray-400" />
                            <div>
                                <p className="text-xs text-gray-500">Active Pools</p>
                                <p className="text-sm font-bold text-gray-900">{status.active_pools || 0}</p>
                            </div>
                        </div>
                        <div className="flex items-center gap-2">
                            <FiShield className="w-4 h-4 text-gray-400" />
                            <div>
                                <p className="text-xs text-gray-500">Risk Score</p>
                                <p className={`text-sm font-bold ${status.risk_score < 30 ? 'text-green-600' : status.risk_score < 60 ? 'text-yellow-600' : 'text-red-600'}`}>
                                    {status.risk_score}/100
                                </p>
                            </div>
                        </div>
                    </div>

                    {/* Action Buttons */}
                    <div className="flex items-center gap-2">
                        <button
                            onClick={toggleOptimization}
                            className={`flex items-center gap-1.5 px-3 py-2 rounded-lg text-xs font-semibold transition-all ${status.auto_rebalance_enabled
                                    ? 'bg-yellow-50 text-yellow-700 hover:bg-yellow-100 border border-yellow-200'
                                    : 'bg-green-50 text-green-700 hover:bg-green-100 border border-green-200'
                                }`}
                        >
                            {status.auto_rebalance_enabled ? <><FiPause className="w-3.5 h-3.5" /> Pause 12h</> : <><FiPlay className="w-3.5 h-3.5" /> Resume Auto</>}
                        </button>
                    </div>
                </div>
            </Card>

            {/* Activity Feed */}
            {activityFeed.length > 0 && (
                <Card className="border-gray-200">
                    <div className="flex items-center gap-2 mb-3">
                        <FiActivity className="w-4 h-4 text-gray-500" />
                        <h4 className="text-sm font-semibold text-gray-700">Live Activity</h4>
                        <span className="relative flex h-2 w-2">
                            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75"></span>
                            <span className="relative inline-flex rounded-full h-2 w-2 bg-green-500"></span>
                        </span>
                    </div>
                    <div className="space-y-2">
                        {activityFeed.slice(0, 5).map((event) => {
                            const cfg = EVENT_ICONS[event.event_type] || EVENT_ICONS.system_decision;
                            const Icon = cfg.icon;
                            return (
                                <div key={event.id} className="flex items-start gap-3 py-2 border-b border-gray-50 last:border-0">
                                    <div className={`p-1.5 rounded-md ${cfg.bg} mt-0.5`}>
                                        <Icon className={`w-3.5 h-3.5 ${cfg.color}`} />
                                    </div>
                                    <div className="flex-1 min-w-0">
                                        <p className="text-xs text-gray-700 leading-relaxed">{event.description}</p>
                                    </div>
                                    <span className="text-[10px] text-gray-400 whitespace-nowrap font-medium">{timeAgo(event.timestamp)}</span>
                                </div>
                            );
                        })}
                    </div>
                </Card>
            )}
        </div>
    );
};

export default OptimizationStatusHeader;
