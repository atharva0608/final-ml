import React, { useState } from 'react';
import { Card, Button, Badge } from '../shared';
import { FiTrendingDown, FiActivity, FiCheck, FiCpu, FiAlertTriangle } from 'react-icons/fi';
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, ReferenceLine } from 'recharts';
import toast from 'react-hot-toast';

const RightSizing = () => {
    const [timeRange, setTimeRange] = useState('7d');
    const [autoResize, setAutoResize] = useState(false);

    // Mock Data
    const summaryStats = {
        monthly_savings: 450.25,
        oversized_count: 12,
        efficiency_improvement: 24, // percent
    };

    const recommendations = [
        { id: 1, namespace: 'payment-service', name: 'api-gateway', current_cpu: '2000m', rec_cpu: '500m', current_mem: '4Gi', rec_mem: '2Gi', savings: 125.00, confidence: 'High' },
        { id: 2, namespace: 'data-pipeline', name: 'processor-worker', current_cpu: '4000m', rec_cpu: '2500m', current_mem: '8Gi', rec_mem: '6Gi', savings: 85.50, confidence: 'Medium' },
        { id: 3, namespace: 'frontend', name: 'web-server', current_cpu: '1000m', rec_cpu: '200m', current_mem: '2Gi', rec_mem: '512Mi', savings: 45.20, confidence: 'High' },
        { id: 4, namespace: 'monitoring', name: 'log-collector', current_cpu: '500m', rec_cpu: '100m', current_mem: '1Gi', rec_mem: '256Mi', savings: 15.00, confidence: 'Low' },
    ];

    const chartData = [
        { time: '00:00', usage: 15, request: 80 },
        { time: '04:00', usage: 12, request: 80 },
        { time: '08:00', usage: 45, request: 80 },
        { time: '12:00', usage: 60, request: 80 },
        { time: '16:00', usage: 55, request: 80 },
        { time: '20:00', usage: 30, request: 80 },
        { time: '23:59', usage: 20, request: 80 },
    ];

    const handleApply = (id) => {
        toast.success(`Resize applied to workload ID ${id}`);
    };

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
