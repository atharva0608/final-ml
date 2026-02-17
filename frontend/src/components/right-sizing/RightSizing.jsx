import React, { useState, useEffect } from 'react';
import { FiDollarSign, FiTrendingDown, FiServer, FiCheckCircle, FiCpu, FiInfo, FiArrowDownRight, FiLayers } from 'react-icons/fi';
import { Card, Button, Badge } from '../shared';
import { useClusterStore } from '../../store/useStore';
import { api, optimizationAPI } from '../../services/api';
import toast from 'react-hot-toast';
import EmptyState from '../shared/EmptyState';

// New Components
import ImpactSummary from './ImpactSummary';
import BatchApplyModal from './BatchApplyModal';
import SavingsTracker from './SavingsTracker';
import InstanceUsageDetailPanel from './InstanceUsageDetailPanel';
import RecommendationAgeIndicator from './RecommendationAgeIndicator';

const RightSizing = () => {
    const { clusters, selectedCluster } = useClusterStore();
    const [loading, setLoading] = useState(true);
    const [data, setData] = useState(null);
    const [recommendations, setRecommendations] = useState([]);

    // UI State
    const [selectedInstance, setSelectedInstance] = useState(null);
    const [isBatchModalOpen, setIsBatchModalOpen] = useState(false);
    const [selectedForBatch, setSelectedForBatch] = useState([]);

    const [savingsData, setSavingsData] = useState(null);

    useEffect(() => {
        if (selectedCluster) {
            fetchRecommendations();
            fetchSavings();
        } else {
            setLoading(false);
        }
    }, [selectedCluster]);

    const fetchSavings = async () => {
        try {
            const res = await api.get('/optimization/savings/realized');
            setSavingsData(res.data);
        } catch (err) {
            console.error("Failed to load savings history", err);
        }
    };

    const fetchRecommendations = async () => {
        try {
            setLoading(true);
            const clusterId = selectedCluster?.id || 'ALL';
            const res = await optimizationAPI.getRightsizing(clusterId);
            setRecommendations(res.data.overprovisioned_instances || []);
            setData(res.data);
            setSelectedForBatch(res.data.overprovisioned_instances || []);
        } catch (err) {
            console.error("RightSizing fetch error:", err);
            setData(null);
        } finally {
            setLoading(false);
        }
    };

    const handleApply = (instance) => {
        // Prepare single instance batch
        setSelectedForBatch([instance]);
        setIsBatchModalOpen(true);
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

    const hasRecommendations = recommendations.length > 0;

    // Calculate Stats for ImpactSummary
    const calculateStats = () => {
        if (!data) return {};

        // Calculate Score: Realized Savings / (Realized + Potential)
        const realized = savingsData?.total_savings || 0;
        const potential = data.total_potential_savings || 0;
        const total = realized + potential;
        const score = total > 0 ? Math.round((realized / total) * 100) : 0;

        return {
            potential_savings: potential,
            instance_count: recommendations.length,
            vcpu_reduction: recommendations.reduce((acc, curr) => acc + (curr.capacity?.cpu || 0) * 0.5, 0), // Est 50%
            memory_reduction: recommendations.reduce((acc, curr) => acc + (curr.capacity?.memory || 0) * 0.5, 0), // Est 50%
            optimization_score: score
        };
    };

    return (
        <div className="space-y-6 relative">
            {/* Header */}
            <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
                <div>
                    <h1 className="text-2xl font-bold text-gray-900">Right Sizing</h1>
                    <p className="text-gray-500 mt-1">Optimize infrastructure costs by resizing over-provisioned instances</p>
                </div>
                {hasRecommendations && (
                    <Button variant="primary" onClick={() => setIsBatchModalOpen(true)}>
                        Batch Apply Fixes ({selectedForBatch.length})
                    </Button>
                )}
            </div>

            {/* KPI Strip */}
            <ImpactSummary stats={calculateStats()} />

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                {/* Main Content Area */}
                <div className="lg:col-span-2 space-y-6">
                    {/* Recommendations Table */}
                    <Card title="Recommendations" className="overflow-hidden">
                        {!hasRecommendations ? (
                            <div className="p-8 text-center text-gray-500">
                                <FiCheckCircle className="w-12 h-12 text-green-500 mx-auto mb-3" />
                                <p className="font-medium">Everything looks optimized!</p>
                                <p className="text-sm mt-1">No over-provisioned workloads found in the last 14 days.</p>
                            </div>
                        ) : (
                            <div className="overflow-x-auto">
                                <table className="w-full text-left">
                                    <thead className="bg-gray-50 border-b border-gray-100">
                                        <tr>
                                            <th className="py-3 px-4 text-xs font-semibold text-gray-500 uppercase">Instance</th>
                                            <th className="py-3 px-4 text-xs font-semibold text-gray-500 uppercase">Type</th>
                                            <th className="py-3 px-4 text-xs font-semibold text-gray-500 uppercase">Utilization</th>
                                            <th className="py-3 px-4 text-xs font-semibold text-gray-500 uppercase">Savings</th>
                                            <th className="py-3 px-4 text-xs font-semibold text-gray-500 uppercase">Age</th>
                                            <th className="py-3 px-4 text-xs font-semibold text-gray-500 uppercase"></th>
                                        </tr>
                                    </thead>
                                    <tbody className="divide-y divide-gray-50">
                                        {recommendations.map((item, idx) => (
                                            <tr
                                                key={idx}
                                                className={`hover:bg-blue-50/30 cursor-pointer transition-colors ${selectedInstance?.instance_id === item.instance_id ? 'bg-blue-50 border-l-2 border-blue-500' : ''}`}
                                                onClick={() => setSelectedInstance(item)}
                                            >
                                                <td className="py-3 px-4">
                                                    <div className="font-medium text-gray-900 text-sm">{item.instance_id}</div>
                                                    <div className="text-[10px] text-gray-400">{item.confidence} Confidence</div>
                                                </td>
                                                <td className="py-3 px-4">
                                                    <div className="flex flex-col">
                                                        <span className="text-gray-500 strike-through text-xs">{item.instance_type}</span>
                                                        <span className="text-green-600 font-bold text-sm flex items-center gap-1">
                                                            <FiArrowDownRight /> {item.recommendation.replace("Downsize to ", "")}
                                                        </span>
                                                    </div>
                                                </td>
                                                <td className="py-3 px-4">
                                                    <div className="w-24 space-y-1">
                                                        <div className="flex items-center gap-1 text-[10px] text-gray-500">
                                                            <FiCpu /> {item.utilization_percent.cpu}%
                                                        </div>
                                                        <div className="w-full h-1 bg-gray-100 rounded-full overflow-hidden">
                                                            <div className="h-full bg-blue-500" style={{ width: `${item.utilization_percent.cpu}%` }}></div>
                                                        </div>
                                                        <div className="flex items-center gap-1 text-[10px] text-gray-500">
                                                            <FiLayers /> {item.utilization_percent.memory}%
                                                        </div>
                                                        <div className="w-full h-1 bg-gray-100 rounded-full overflow-hidden">
                                                            <div className="h-full bg-indigo-500" style={{ width: `${item.utilization_percent.memory}%` }}></div>
                                                        </div>
                                                    </div>
                                                </td>
                                                <td className="py-3 px-4 text-green-700 font-bold text-sm">
                                                    ${item.potential_savings_monthly}
                                                </td>
                                                <td className="py-3 px-4">
                                                    {/* Mock age random 1-10 days */}
                                                    <RecommendationAgeIndicator days={Math.floor(Math.random() * 10) + 1} />
                                                </td>
                                                <td className="py-3 px-4 text-right">
                                                    <Button
                                                        size="xs"
                                                        variant="outline"
                                                        onClick={(e) => {
                                                            e.stopPropagation();
                                                            handleApply(item);
                                                        }}
                                                    >
                                                        Apply
                                                    </Button>
                                                </td>
                                            </tr>
                                        ))}
                                    </tbody>
                                </table>
                            </div>
                        )}
                    </Card>
                </div>

                {/* Right Column (Tracker + Panel Placeholder) */}
                <div className="space-y-6">
                    {/* Savings Tracker */}
                    <div className="h-64">
                        <SavingsTracker />
                    </div>

                    {/* Helper Panel if no instance selected */}
                    {!selectedInstance && (
                        <Card className="bg-gray-50 border-dashed border-2 border-gray-200">
                            <div className="p-6 text-center text-gray-400">
                                <FiInfo className="w-8 h-8 mx-auto mb-2" />
                                <p className="text-sm">Select an instance from the list to view detailed utilization analysis and utilization history.</p>
                            </div>
                        </Card>
                    )}
                </div>
            </div>

            {/* Slide-over Detail Panel */}
            <InstanceUsageDetailPanel
                instance={selectedInstance}
                onClose={() => setSelectedInstance(null)}
                onApply={handleApply}
            />

            {/* Batch Apply Modal */}
            <BatchApplyModal
                isOpen={isBatchModalOpen}
                onClose={() => setIsBatchModalOpen(false)}
                selectedInstances={selectedForBatch}
                clusterId={selectedCluster?.id}
                onSuccess={() => {
                    toast.success("Optimization request submitted");
                    setIsBatchModalOpen(false);
                    // Optionally refresh data
                    fetchRecommendations();
                }}
            />
        </div>
    );
};

export default RightSizing;
