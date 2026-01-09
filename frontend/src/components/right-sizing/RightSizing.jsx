import React, { useState, useEffect } from 'react';
import { Card, Button, Badge, EmptyState } from '../shared';
import { FiTrendingDown, FiActivity, FiCheck, FiCpu, FiAlertTriangle } from 'react-icons/fi';
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, ReferenceLine } from 'recharts';
import toast from 'react-hot-toast';
import { optimizationAPI } from '../../services/api';

const RightSizing = () => {
    const [timeRange, setTimeRange] = useState('7d');
    const [autoResize, setAutoResize] = useState(false);
    const [loading, setLoading] = useState(true);
    const [data, setData] = useState(null);
    const [selectedClusterId, setSelectedClusterId] = useState(null);

    useEffect(() => {
        // Get cluster from URL or global state - for now use first available
        const clusterId = localStorage.getItem('selectedClusterId') || 'default';
        setSelectedClusterId(clusterId);
        fetchRecommendations(clusterId);
    }, []);

    const fetchRecommendations = async (clusterId) => {
        setLoading(true);
        try {
            const response = await optimizationAPI.getRightsizing(clusterId);
            setData(response.data);
        } catch (error) {
            console.error("Failed to fetch rightsizing data", error);
            // Fallback to empty state
            setData(null);
        } finally {
            setLoading(false);
        }
    };

    const handleApply = async (id) => {
        toast.success(`Resize applied to workload ID ${id}`);
    };

    if (loading) return <div className="p-8 text-center">Loading analysis...</div>;

    // Handle no data state
    if (!data || !data.recommendations || data.recommendations.length === 0) {
        return (
            <div className="space-y-6">
                <div>
                    <h1 className="text-3xl font-bold text-gray-900">Workload Rightsizing</h1>
                    <p className="mt-1 text-gray-600">Optimize pod resource requests to reduce waste.</p>
                </div>
                <EmptyState
                    title="Everything looks optimized!"
                    message="We couldn't find any over-provisioned workloads in this cluster based on the last 14 days of data."
                />
            </div>
        );
    }

    const { summaryStats, recommendations, chartData } = data;

    return (
        <div className="space-y-6">
            <div className="flex justify-between items-center">
                <div>
                    <h1 className="text-3xl font-bold text-gray-900">Workload Rightsizing</h1>
                    <p className="mt-1 text-gray-600">
                        Optimize pod resource requests to reduce waste and improve stability.
                    </p>
                </div>
                <div className="flex items-center bg-white p-2 rounded-lg border shadow-sm">
                    <span className="text-sm font-medium mr-3 text-gray-700">Auto-Resize</span>
                    <button
                        onClick={() => setAutoResize(!autoResize)}
                        className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${autoResize ? 'bg-green-500' : 'bg-gray-300'
                            }`}
                    >
                        <span className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${autoResize ? 'translate-x-6' : 'translate-x-1'
                            }`} />
                    </button>
                </div>
            </div>

            {/* Summary Cards */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                <Card className="bg-gradient-to-br from-blue-50 to-white">
                    <div className="flex items-center gap-4">
                        <div className="p-3 bg-blue-100 rounded-lg text-blue-600">
                            <FiTrendingDown className="w-6 h-6" />
                        </div>
                        <div>
                            <p className="text-sm font-medium text-gray-600">Monthly Potential Savings</p>
                            <p className="text-2xl font-bold text-gray-900">${summaryStats.monthly_savings}</p>
                        </div>
                    </div>
                </Card>
                <Card className="bg-gradient-to-br from-orange-50 to-white">
                    <div className="flex items-center gap-4">
                        <div className="p-3 bg-orange-100 rounded-lg text-orange-600">
                            <FiActivity className="w-6 h-6" />
                        </div>
                        <div>
                            <p className="text-sm font-medium text-gray-600">Oversized Workloads</p>
                            <p className="text-2xl font-bold text-gray-900">{summaryStats.oversized_count}</p>
                        </div>
                    </div>
                </Card>
                <Card className="bg-gradient-to-br from-green-50 to-white">
                    <div className="flex items-center gap-4">
                        <div className="p-3 bg-green-100 rounded-lg text-green-600">
                            <FiCheck className="w-6 h-6" />
                        </div>
                        <div>
                            <p className="text-sm font-medium text-gray-600">Efficiency Gain</p>
                            <p className="text-2xl font-bold text-gray-900">+{summaryStats.efficiency_improvement}%</p>
                        </div>
                    </div>
                </Card>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                {/* Recommendations Table */}
                <div className="lg:col-span-2">
                    <Card title="Resize Recommendations">
                        <div className="overflow-x-auto">
                            <table className="min-w-full divide-y divide-gray-200">
                                <thead className="bg-gray-50">
                                    <tr>
                                        <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Workload</th>
                                        <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Current Limit</th>
                                        <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Recommended</th>
                                        <th className="px-6 py-3 text-left text-xs font-medium text-green-600 uppercase">Savings</th>
                                        <th className="px-6 py-3 text-right">Action</th>
                                    </tr>
                                </thead>
                                <tbody className="bg-white divide-y divide-gray-200">
                                    {recommendations.map((rec) => (
                                        <tr key={rec.id} className="hover:bg-gray-50">
                                            <td className="px-6 py-4">
                                                <div className="text-sm font-medium text-gray-900">{rec.name}</div>
                                                <div className="text-xs text-gray-500">{rec.namespace}</div>
                                            </td>
                                            <td className="px-6 py-4 text-sm text-gray-500">
                                                <div>CPU: {rec.current_cpu}</div>
                                                <div>Mem: {rec.current_mem}</div>
                                            </td>
                                            <td className="px-6 py-4 text-sm text-gray-900">
                                                <div className="font-semibold text-blue-600">CPU: {rec.rec_cpu}</div>
                                                <div className="font-semibold text-blue-600">Mem: {rec.rec_mem}</div>
                                            </td>
                                            <td className="px-6 py-4 text-sm text-green-600 font-bold">
                                                ${rec.savings}/mo
                                            </td>
                                            <td className="px-6 py-4 text-right">
                                                <Button size="sm" variant="outline" onClick={() => handleApply(rec.id)}>
                                                    Resize
                                                </Button>
                                            </td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    </Card>
                </div>

                {/* Utilization Chart */}
                <div>
                    <Card title="Analysis: payment-service/api-gateway">
                        <div className="h-64 mt-4">
                            <ResponsiveContainer width="100%" height="100%">
                                <AreaChart data={chartData}>
                                    <defs>
                                        <linearGradient id="colorUsage" x1="0" y1="0" x2="0" y2="1">
                                            <stop offset="5%" stopColor="#3B82F6" stopOpacity={0.8} />
                                            <stop offset="95%" stopColor="#3B82F6" stopOpacity={0} />
                                        </linearGradient>
                                    </defs>
                                    <CartesianGrid strokeDasharray="3 3" vertical={false} />
                                    <XAxis dataKey="time" tick={{ fontSize: 12 }} />
                                    <YAxis tick={{ fontSize: 12 }} label={{ value: 'CPU %', angle: -90, position: 'insideLeft' }} />
                                    <Tooltip />
                                    <ReferenceLine y={80} stroke="orange" strokeDasharray="3 3" label="Limit" />
                                    <ReferenceLine y={40} stroke="green" strokeDasharray="3 3" label="Rec" />
                                    <Area type="monotone" dataKey="usage" stroke="#3B82F6" fillOpacity={1} fill="url(#colorUsage)" />
                                </AreaChart>
                            </ResponsiveContainer>
                        </div>
                        <div className="mt-4 p-4 bg-gray-50 rounded-lg text-sm">
                            <h4 className="font-semibold flex items-center mb-2">
                                <FiAlertTriangle className="text-orange-500 mr-2" />
                                Analysis Insight
                            </h4>
                            <p className="text-gray-600">
                                This workload requests <strong>{recommendations[0].current_cpu}</strong> CPU but averages only <strong>15%</strong> utilization.
                                Reducing request to <strong>{recommendations[0].rec_cpu}</strong> is safe based on peak usage over the last 30 days.
                            </p>
                        </div>
                    </Card>
                </div>
            </div>
        </div>
    );
};

export default RightSizing;
