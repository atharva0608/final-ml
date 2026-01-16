import React, { useState, useEffect } from 'react';
import { Card, Button } from '../shared';
import { adminAPI } from '../../services/api';
import {
    FiUsers, FiDollarSign, FiActivity, FiServer, FiCpu, FiTrendingUp, FiClock
} from 'react-icons/fi';
import { format } from 'date-fns';

const StatCard = ({ title, value, subtext, icon: Icon, color }) => (
    <Card className="p-6">
        <div className="flex items-center justify-between">
            <div>
                <p className="text-sm font-medium text-gray-500">{title}</p>
                <p className="text-2xl font-bold text-gray-900 mt-1">{value}</p>
                {subtext && <p className={`text-xs mt-1 ${subtext.includes('+') ? 'text-green-600' : 'text-gray-500'}`}>{subtext}</p>}
            </div>
            <div className={`p-3 rounded-full bg-${color}-100`}>
                <Icon className={`w-6 h-6 text-${color}-600`} />
            </div>
        </div>
    </Card>
);

const AdminOverview = () => {
    const [stats, setStats] = useState(null);
    const [activity, setActivity] = useState([]);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        const fetchDashboard = async () => {
            try {
                const response = await adminAPI.getDashboardStats();
                setStats(response.data.stats);
                setActivity(response.data.activity_feed);
            } catch (error) {
                console.error("Failed to load dashboard stats", error);
            } finally {
                setLoading(false);
            }
        };
        fetchDashboard();
    }, []);

    if (loading) {
        return (
            <div className="flex justify-center items-center h-64">
                <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
            </div>
        );
    }

    return (
        <div className="space-y-6">
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
                <StatCard
                    title="Total Revenue (MRR)"
                    value={stats?.mrr || "$0.00"}
                    subtext="+12% from last month"
                    icon={FiDollarSign}
                    color="green"
                />
                <StatCard
                    title="Active Users"
                    value={stats?.active_users || 0}
                    subtext={`${stats?.recent_signups || 0} new this month`}
                    icon={FiUsers}
                    color="blue"
                />
                <StatCard
                    title="Active Clusters"
                    value={stats?.active_clusters || 0}
                    subtext={`${stats?.total_clusters || 0} total registered`}
                    icon={FiServer}
                    color="purple"
                />
                <StatCard
                    title="Spot Instances"
                    value={stats?.spot_instances || 0}
                    subtext={`${stats?.running_instances || 0} total running`}
                    icon={FiCpu}
                    color="indigo"
                />
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                {/* Activity Feed */}
                <div className="lg:col-span-2">
                    <Card className="h-full">
                        <div className="p-6 border-b border-gray-100 flex justify-between items-center">
                            <h2 className="text-lg font-bold text-gray-900 flex items-center gap-2">
                                <FiActivity className="text-blue-500" />
                                Real-Time Activity
                            </h2>
                            <Button variant="outline" size="sm" onClick={() => window.location.reload()}>Refresh</Button>
                        </div>
                        <div className="p-6">
                            <div className="space-y-6">
                                {activity.length === 0 ? (
                                    <p className="text-gray-500 text-center py-4">No recent activity</p>
                                ) : (
                                    activity.map((item, index) => (
                                        <div key={index} className="flex gap-4">
                                            <div className="flex-shrink-0 mt-1">
                                                <div className="w-2 h-2 rounded-full bg-blue-500 ring-4 ring-blue-50"></div>
                                            </div>
                                            <div className="flex-1">
                                                <div className="flex justify-between">
                                                    <p className="text-sm font-medium text-gray-900">
                                                        {item.user} <span className="text-gray-500 font-normal">performed</span> {item.action}
                                                    </p>
                                                    <span className="text-xs text-gray-400 flex items-center gap-1">
                                                        <FiClock className="w-3 h-3" />
                                                        {item.time}
                                                    </span>
                                                </div>
                                                <p className="text-sm text-gray-500 mt-1 bg-gray-50 p-2 rounded border border-gray-100 font-mono text-xs">
                                                    {item.detail}
                                                </p>
                                            </div>
                                        </div>
                                    ))
                                )}
                            </div>
                        </div>
                    </Card>
                </div>

                {/* System Health / Quick Status */}
                <div>
                    <Card className="h-full p-6">
                        <h2 className="text-lg font-bold text-gray-900 mb-4">System Status</h2>
                        <div className="space-y-4">
                            <div className="flex items-center justify-between p-3 bg-green-50 rounded-lg border border-green-100">
                                <div className="flex items-center gap-3">
                                    <div className="w-2 h-2 rounded-full bg-green-500 animate-pulse"></div>
                                    <span className="text-sm font-medium text-green-700">API Gateway</span>
                                </div>
                                <span className="text-xs text-green-600 font-bold">OPERATIONAL</span>
                            </div>
                            <div className="flex items-center justify-between p-3 bg-green-50 rounded-lg border border-green-100">
                                <div className="flex items-center gap-3">
                                    <div className="w-2 h-2 rounded-full bg-green-500 animate-pulse"></div>
                                    <span className="text-sm font-medium text-green-700">Database</span>
                                </div>
                                <span className="text-xs text-green-600 font-bold">OPERATIONAL</span>
                            </div>
                            <div className="flex items-center justify-between p-3 bg-green-50 rounded-lg border border-green-100">
                                <div className="flex items-center gap-3">
                                    <div className="w-2 h-2 rounded-full bg-green-500 animate-pulse"></div>
                                    <span className="text-sm font-medium text-green-700">Workers</span>
                                </div>
                                <span className="text-xs text-green-600 font-bold">OPERATIONAL</span>
                            </div>
                        </div>

                        <div className="mt-8 pt-6 border-t border-gray-100">
                            <p className="text-xs text-gray-400 uppercase tracking-wider font-bold mb-3">Quick Links</p>
                            <div className="space-y-2">
                                <Button variant="ghost" className="w-full justify-start text-blue-600 text-sm">View System Logs</Button>
                                <Button variant="ghost" className="w-full justify-start text-blue-600 text-sm">Manage API Keys</Button>
                            </div>
                        </div>
                    </Card>
                </div>
            </div>
        </div>
    );
};

export default AdminOverview;
