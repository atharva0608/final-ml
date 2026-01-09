import React, { useState, useEffect } from 'react';
import { FiDollarSign, FiTrendingDown, FiServer, FiCheckCircle, FiCpu, FiInfo, FiArrowDownRight } from 'react-icons/fi';
import { Card, Button, Badge } from '../shared';
import { useClusterStore } from '../../store/useStore';
import { api } from '../../services/api';
import toast from 'react-hot-toast';
import EmptyState from '../shared/EmptyState';

const RightSizing = () => {
    const { clusters } = useClusterStore();
    const [loading, setLoading] = useState(true);
    const [data, setData] = useState(null);

    // For demo, pick first cluster or handle selection better
    const selectedCluster = clusters?.[0];

    useEffect(() => {
        if (selectedCluster?.id) {
            fetchRecommendations(selectedCluster.id);
        } else {
            setLoading(false);
        }
    }, [selectedCluster]);

    const fetchRecommendations = async (clusterId) => {
        try {
            setLoading(true);
            // Using direct api call for new endpoint
            const res = await api.get(`/optimization/rightsizing/${clusterId}`);
            setData(res.data);
        } catch (err) {
            console.error("RightSizing fetch error:", err);
            // toast.error("Could not load recommendations");
            setData(null);
        } finally {
            setLoading(false);
        }
    };


    if (!selectedCluster) {
        return (
            <EmptyState
                title="No Cluster Available"
                message="Please connect a cluster to view rightsizing recommendations."
            />
        );
    }

    if (loading) {
        return (
            <div className="min-h-[400px] flex items-center justify-center">
                <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
            </div>
        );
    }

    const hasRecommendations = data?.overprovisioned_instances?.length > 0;
    const savings = data?.total_potential_savings || 0;
    const instanceCount = data?.overprovisioned_instances?.length || 0;

    return (
        <div className="space-y-6">
            {/* Header */}
            <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
                <div>
                    <h1 className="text-2xl font-bold text-gray-900">Right Sizing</h1>
                    <p className="text-gray-500 mt-1">optimize your infrastructure costs by resizing over-provisioned instances</p>
                </div>
            </div>

            {/* Summary Stats */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                <div className="bg-gradient-to-br from-blue-50 to-white p-6 rounded-xl border border-blue-100 shadow-sm">
                    <div className="flex items-start justify-between mb-4">
                        <div className="p-2 bg-blue-100 rounded-lg text-blue-600">
                            <FiDollarSign className="w-6 h-6" />
                        </div>
                    </div>
                    <h3 className="text-sm font-medium text-gray-500 mb-1">Potential Monthly Savings</h3>
                    <p className="text-3xl font-bold text-gray-900">${savings.toFixed(2)}</p>
                    <div className="mt-4 text-sm text-gray-600">
                        Based on 14-day analysis
                    </div>
                </div>

                <div className="bg-white p-6 rounded-xl border border-gray-200 shadow-sm">
                    <div className="flex items-start justify-between mb-4">
                        <div className="p-2 bg-purple-100 rounded-lg text-purple-600">
                            <FiServer className="w-6 h-6" />
                        </div>
                    </div>
                    <h3 className="text-sm font-medium text-gray-500 mb-1">Over-provisioned Instances</h3>
                    <p className="text-3xl font-bold text-gray-900">{instanceCount}</p>
                </div>

                <div className="bg-white p-6 rounded-xl border border-gray-200 shadow-sm">
                    <div className="flex items-start justify-between mb-4">
                        <div className="p-2 bg-green-100 rounded-lg text-green-600">
                            <FiCheckCircle className="w-6 h-6" />
                        </div>
                    </div>
                    <h3 className="text-sm font-medium text-gray-500 mb-1">Optimization Score</h3>
                    <div className="flex items-end gap-2">
                        <p className="text-3xl font-bold text-gray-900">{instanceCount > 0 ? 65 : 100}</p>
                        <span className="text-sm text-gray-500 mb-1">/100</span>
                    </div>
                </div>
            </div>

            {!hasRecommendations ? (
                <EmptyState
                    title="Everything looks optimized!"
                    message="We couldn't find any over-provisioned workloads in this cluster based on the last 14 days of data."
                />
            ) : (
                <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                    {/* Recommendations List */}
                    <div className="lg:col-span-2 space-y-6">
                        <Card title="Recommendations" className="overflow-hidden">
                            <div className="overflow-x-auto">
                                <table className="w-full text-left">
                                    <thead className="bg-gray-50 border-b border-gray-100">
                                        <tr>
                                            <th className="py-3 px-4 text-xs font-semibold text-gray-500 uppercase">Instance</th>
                                            <th className="py-3 px-4 text-xs font-semibold text-gray-500 uppercase">Current</th>
                                            <th className="py-3 px-4 text-xs font-semibold text-gray-500 uppercase">Recommendation</th>
                                            <th className="py-3 px-4 text-xs font-semibold text-gray-500 uppercase">CPU / Mem Util</th>
                                            <th className="py-3 px-4 text-xs font-semibold text-gray-500 uppercase">Savings</th>
                                            <th className="py-3 px-4 text-xs font-semibold text-gray-500 uppercase"></th>
                                        </tr>
                                    </thead>
                                    <tbody className="divide-y divide-gray-50">
                                        {data.overprovisioned_instances.map((item, idx) => (
                                            <tr key={idx} className="hover:bg-gray-50/50">
                                                <td className="py-3 px-4">
                                                    <div className="font-medium text-gray-900 text-sm">{item.instance_id}</div>
                                                </td>
                                                <td className="py-3 px-4">
                                                    <Badge variant="gray">{item.instance_type}</Badge>
                                                </td>
                                                <td className="py-3 px-4">
                                                    <div className="flex items-center gap-2 text-green-600 font-medium text-sm">
                                                        <FiArrowDownRight />
                                                        {item.recommendation.replace("Downsize to ", "")}
                                                    </div>
                                                </td>
                                                <td className="py-3 px-4 text-sm text-gray-600">
                                                    <div className="flex flex-col gap-1">
                                                        <div className="flex justify-between text-xs">
                                                            <span>CPU</span>
                                                            <span>{item.utilization_percent.cpu}%</span>
                                                        </div>
                                                        <div className="w-24 h-1.5 bg-gray-100 rounded-full overflow-hidden">
                                                            <div className="h-full bg-blue-500" style={{ width: `${item.utilization_percent.cpu}%` }}></div>
                                                        </div>
                                                        <div className="flex justify-between text-xs mt-1">
                                                            <span>Mem</span>
                                                            <span>{item.utilization_percent.memory}%</span>
                                                        </div>
                                                        <div className="w-24 h-1.5 bg-gray-100 rounded-full overflow-hidden">
                                                            <div className="h-full bg-indigo-500" style={{ width: `${item.utilization_percent.memory}%` }}></div>
                                                        </div>
                                                    </div>
                                                </td>
                                                <td className="py-3 px-4 font-bold text-gray-900 text-sm">
                                                    ${item.potential_savings_monthly}
                                                </td>
                                                <td className="py-3 px-4 text-right">
                                                    <Button size="sm" variant="outline">Apply</Button>
                                                </td>
                                            </tr>
                                        ))}
                                    </tbody>
                                </table>
                            </div>
                        </Card>
                    </div>

                    {/* Side Panel placeholder */}
                    <div className="space-y-6">
                        <Card title="Resource Efficiency">
                            <div className="h-64 flex items-center justify-center text-gray-400 text-sm italic border-2 border-dashed rounded-lg">
                                Select an instance to view usage charts
                            </div>
                        </Card>
                    </div>
                </div>
            )}
        </div>
    );
};

export default RightSizing;
