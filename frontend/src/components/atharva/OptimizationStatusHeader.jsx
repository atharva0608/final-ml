import React, { useEffect } from 'react';
import useAtharvaStore from '../../store/useAtharvaStore';
import { Card } from '../shared';
import {
    FiActivity, FiAlertCircle, FiCheckCircle, FiClock, FiRefreshCw, FiZap
} from 'react-icons/fi';
import { atharvaaiAPI } from '../../services/api';

const OptimizationStatusHeader = () => {
    const { poolRankings, blacklist } = useAtharvaStore();
    const [rebalancingStatus, setRebalancingStatus] = React.useState([]);
    const [health, setHealth] = React.useState(null);

    useEffect(() => {
        fetchRebalancingStatus();
        fetchHealth();

        // Refresh every 30 seconds
        const interval = setInterval(() => {
            fetchRebalancingStatus();
            fetchHealth();
        }, 30000);

        return () => clearInterval(interval);
    }, []);

    const fetchRebalancingStatus = async () => {
        try {
            const response = await atharvaaiAPI.getRebalancingStatus(null, 5);
            setRebalancingStatus(response.data);
        } catch (err) {
            console.error('Failed to fetch rebalancing status:', err);
        }
    };

    const fetchHealth = async () => {
        try {
            const response = await atharvaaiAPI.getHealth();
            setHealth(response.data);
        } catch (err) {
            console.error('Failed to fetch health:', err);
        }
    };

    const topPool = poolRankings && poolRankings.length > 0 ? poolRankings[0] : null;
    const activeRebalancing = rebalancingStatus.filter(r => r.status === 'in_progress').length;

    return (
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
            {/* System Health */}
            <Card className="border-l-4 border-l-green-500">
                <div className="flex items-center justify-between">
                    <div>
                        <p className="text-xs text-gray-500 font-medium">System Status</p>
                        <p className="text-2xl font-bold text-gray-900 mt-1">
                            {health?.status === 'healthy' ? 'Healthy' : 'Unknown'}
                        </p>
                        <p className="text-xs text-gray-400 mt-1">
                            {health?.service || 'AtharvaAi Pool Selection'}
                        </p>
                    </div>
                    <div className="w-12 h-12 bg-green-100 rounded-full flex items-center justify-center">
                        <FiCheckCircle className="w-6 h-6 text-green-600" />
                    </div>
                </div>
            </Card>

            {/* Top Ranked Pool */}
            <Card className="border-l-4 border-l-blue-500">
                <div className="flex items-center justify-between">
                    <div>
                        <p className="text-xs text-gray-500 font-medium">Top Ranked Pool</p>
                        {topPool ? (
                            <>
                                <p className="text-lg font-bold text-gray-900 mt-1">
                                    {topPool.instance_type}
                                </p>
                                <p className="text-xs text-gray-400 mt-1">
                                    {topPool.az} • {(topPool.savings_pct * 100).toFixed(1)}% savings
                                </p>
                            </>
                        ) : (
                            <>
                                <p className="text-2xl font-bold text-gray-900 mt-1">—</p>
                                <p className="text-xs text-gray-400 mt-1">No rankings yet</p>
                            </>
                        )}
                    </div>
                    <div className="w-12 h-12 bg-blue-100 rounded-full flex items-center justify-center">
                        <FiZap className="w-6 h-6 text-blue-600" />
                    </div>
                </div>
            </Card>

            {/* Active Rebalancing */}
            <Card className="border-l-4 border-l-yellow-500">
                <div className="flex items-center justify-between">
                    <div>
                        <p className="text-xs text-gray-500 font-medium">Rebalancing Actions</p>
                        <p className="text-2xl font-bold text-gray-900 mt-1">
                            {activeRebalancing}
                        </p>
                        <p className="text-xs text-gray-400 mt-1">
                            {activeRebalancing === 0 ? 'All stable' : 'In progress'}
                        </p>
                    </div>
                    <div className="w-12 h-12 bg-yellow-100 rounded-full flex items-center justify-center">
                        <FiRefreshCw className={`w-6 h-6 text-yellow-600 ${activeRebalancing > 0 ? 'animate-spin' : ''}`} />
                    </div>
                </div>
            </Card>

            {/* Flagged Pools */}
            <Card className="border-l-4 border-l-red-500">
                <div className="flex items-center justify-between">
                    <div>
                        <p className="text-xs text-gray-500 font-medium">Flagged Pools</p>
                        <p className="text-2xl font-bold text-gray-900 mt-1">
                            {blacklist?.length || 0}
                        </p>
                        <p className="text-xs text-gray-400 mt-1">
                            {blacklist?.length === 0 ? 'All safe' : 'Globally blacklisted'}
                        </p>
                    </div>
                    <div className="w-12 h-12 bg-red-100 rounded-full flex items-center justify-center">
                        <FiAlertCircle className="w-6 h-6 text-red-600" />
                    </div>
                </div>
            </Card>

            {/* Recent Activity */}
            {rebalancingStatus.length > 0 && (
                <Card className="md:col-span-4 border-l-4 border-l-purple-500">
                    <div className="flex items-center gap-2 mb-3">
                        <FiActivity className="w-4 h-4 text-purple-600" />
                        <h4 className="text-sm font-semibold text-gray-900">Recent Rebalancing Activity</h4>
                    </div>
                    <div className="space-y-2">
                        {rebalancingStatus.slice(0, 3).map((action, idx) => (
                            <div key={idx} className="flex items-center justify-between p-2 bg-gray-50 rounded-lg text-xs">
                                <div className="flex items-center gap-3">
                                    <span className={`px-2 py-0.5 rounded-full font-semibold ${
                                        action.status === 'completed' ? 'bg-green-100 text-green-800' :
                                        action.status === 'in_progress' ? 'bg-yellow-100 text-yellow-800' :
                                        'bg-red-100 text-red-800'
                                    }`}>
                                        {action.status === 'completed' ? 'Completed' :
                                         action.status === 'in_progress' ? 'In Progress' : 'Failed'}
                                    </span>
                                    <span className="text-gray-600">
                                        <strong>{action.cluster_id}</strong>
                                    </span>
                                    <span className="text-gray-400">
                                        {action.source_pool} → {action.target_pool}
                                    </span>
                                    <span className={`px-1.5 py-0.5 rounded text-[10px] font-medium ${
                                        action.trigger === 'emergency' ? 'bg-red-100 text-red-700' : 'bg-blue-100 text-blue-700'
                                    }`}>
                                        {action.trigger}
                                    </span>
                                </div>
                                <div className="flex items-center gap-2 text-gray-500">
                                    <FiClock className="w-3 h-3" />
                                    <span>
                                        {action.duration_seconds ? `${action.duration_seconds}s` : 'Ongoing'}
                                    </span>
                                </div>
                            </div>
                        ))}
                    </div>
                </Card>
            )}
        </div>
    );
};

export default OptimizationStatusHeader;
