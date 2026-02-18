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
            const clusterId = selectedCluster?.id;

            // New endpoint: /pod-metrics/right-sizing/recommendations
            const res = await optimizationAPI.getRightsizing(clusterId, {
                analysis_window_hours: 336  // 14 days
            });

            // Backend returns array of recommendations directly
            const recommendationsData = Array.isArray(res.data) ? res.data : [];
            setRecommendations(recommendationsData);

            // Calculate aggregated data for summary
            const totalSavings = recommendationsData.reduce((sum, rec) => sum + (rec.savings_monthly || 0), 0);
            const avgScore = recommendationsData.length > 0
                ? recommendationsData.reduce((sum, rec) => {
                    const waste = 100 - ((rec.cpu_avg_millicores / (rec.current_cpu_request_millicores || 1000)) * 100);
                    return sum + Math.max(0, Math.min(100, waste));
                }, 0) / recommendationsData.length
                : 100;

            setData({
                total_potential_savings: totalSavings,
                overprovisioned_count: recommendationsData.length,
                optimization_score: Math.round(avgScore),
                recommendations: recommendationsData
            });

            setSelectedForBatch(recommendationsData);
        } catch (err) {
            console.error("RightSizing fetch error:", err);
            setData(null);
            setRecommendations([]);
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

        // Calculate reductions based on current vs recommended
        const vcpuReduction = recommendations.reduce((acc, curr) => {
            const currentCores = (curr.current_cpu_request_millicores || 0) / 1000;
            const recommendedCores = (curr.recommended_cpu_request_millicores || 0) / 1000;
            return acc + (currentCores - recommendedCores);
        }, 0);

        const memoryReduction = recommendations.reduce((acc, curr) => {
            const currentGB = (curr.current_memory_request_mb || 0) / 1024;
            const recommendedGB = (curr.recommended_memory_request_mb || 0) / 1024;
            return acc + (currentGB - recommendedGB);
        }, 0);

        return {
            potential_savings: data.total_potential_savings || 0,
            instance_count: recommendations.length,
            vcpu_reduction: Math.round(vcpuReduction * 10) / 10,  // Round to 1 decimal
            memory_reduction: Math.round(memoryReduction * 10) / 10,  // Round to 1 decimal
            optimization_score: data.optimization_score || 0
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
                                            <th className="py-3 px-4 text-xs font-semibold text-gray-500 uppercase">Workload</th>
                                            <th className="py-3 px-4 text-xs font-semibold text-gray-500 uppercase">Current / Recommended</th>
                                            <th className="py-3 px-4 text-xs font-semibold text-gray-500 uppercase">CPU Utilization</th>
                                            <th className="py-3 px-4 text-xs font-semibold text-gray-500 uppercase">Memory Utilization</th>
                                            <th className="py-3 px-4 text-xs font-semibold text-gray-500 uppercase">Monthly Savings</th>
                                            <th className="py-3 px-4 text-xs font-semibold text-gray-500 uppercase">Confidence</th>
                                            <th className="py-3 px-4 text-xs font-semibold text-gray-500 uppercase"></th>
                                        </tr>
                                    </thead>
                                    <tbody className="divide-y divide-gray-50">
                                        {recommendations.map((item, idx) => {
                                            // Calculate utilization percentages
                                            const cpuUtilPct = item.current_cpu_request_millicores > 0
                                                ? Math.round((item.cpu_avg_millicores / item.current_cpu_request_millicores) * 100)
                                                : 0;
                                            const memUtilPct = item.current_memory_request_mb > 0
                                                ? Math.round((item.memory_avg_mb / item.current_memory_request_mb) * 100)
                                                : 0;

                                            return (
                                                <tr
                                                    key={`${item.namespace}-${item.controller_name}-${idx}`}
                                                    className={`hover:bg-blue-50/30 cursor-pointer transition-colors ${selectedInstance?.controller_name === item.controller_name ? 'bg-blue-50 border-l-2 border-blue-500' : ''}`}
                                                    onClick={() => setSelectedInstance(item)}
                                                >
                                                    <td className="py-3 px-4">
                                                        <div className="font-medium text-gray-900 text-sm">{item.controller_name}</div>
                                                        <div className="text-[10px] text-gray-400">
                                                            {item.controller_kind} • {item.namespace}
                                                        </div>
                                                        <div className="text-[10px] text-gray-400">
                                                            {item.data_points} data points • {Math.round(item.analysis_window_hours / 24)}d analysis
                                                        </div>
                                                    </td>
                                                    <td className="py-3 px-4">
                                                        <div className="flex flex-col gap-1 text-xs">
                                                            <div className="text-gray-500">
                                                                CPU: {item.current_cpu_request_millicores}m → <span className="text-green-600 font-semibold">{item.recommended_cpu_request_millicores}m</span>
                                                            </div>
                                                            <div className="text-gray-500">
                                                                Mem: {item.current_memory_request_mb}MB → <span className="text-green-600 font-semibold">{item.recommended_memory_request_mb}MB</span>
                                                            </div>
                                                        </div>
                                                    </td>
                                                    <td className="py-3 px-4">
                                                        <div className="w-28 space-y-1">
                                                            <div className="flex items-center justify-between text-[10px]">
                                                                <span className="text-gray-500">Avg</span>
                                                                <span className="font-medium">{cpuUtilPct}%</span>
                                                            </div>
                                                            <div className="w-full h-1.5 bg-gray-100 rounded-full overflow-hidden">
                                                                <div
                                                                    className={`h-full ${cpuUtilPct < 40 ? 'bg-green-500' : cpuUtilPct < 70 ? 'bg-yellow-500' : 'bg-red-500'}`}
                                                                    style={{ width: `${Math.min(100, cpuUtilPct)}%` }}
                                                                ></div>
                                                            </div>
                                                            <div className="text-[10px] text-gray-400">
                                                                P95: {item.cpu_p95_millicores}m
                                                            </div>
                                                        </div>
                                                    </td>
                                                    <td className="py-3 px-4">
                                                        <div className="w-28 space-y-1">
                                                            <div className="flex items-center justify-between text-[10px]">
                                                                <span className="text-gray-500">Avg</span>
                                                                <span className="font-medium">{memUtilPct}%</span>
                                                            </div>
                                                            <div className="w-full h-1.5 bg-gray-100 rounded-full overflow-hidden">
                                                                <div
                                                                    className={`h-full ${memUtilPct < 40 ? 'bg-green-500' : memUtilPct < 70 ? 'bg-yellow-500' : 'bg-red-500'}`}
                                                                    style={{ width: `${Math.min(100, memUtilPct)}%` }}
                                                                ></div>
                                                            </div>
                                                            <div className="text-[10px] text-gray-400">
                                                                P95: {item.memory_p95_mb}MB
                                                            </div>
                                                        </div>
                                                    </td>
                                                    <td className="py-3 px-4">
                                                        <div className="text-green-700 font-bold text-sm">
                                                            ${item.savings_monthly.toFixed(2)}
                                                        </div>
                                                        <div className="text-[10px] text-gray-400">
                                                            {item.savings_pct.toFixed(1)}% reduction
                                                        </div>
                                                    </td>
                                                    <td className="py-3 px-4">
                                                        <Badge
                                                            variant={
                                                                item.confidence === 'HIGH' ? 'success' :
                                                                item.confidence === 'MEDIUM' ? 'warning' : 'default'
                                                            }
                                                        >
                                                            {item.confidence}
                                                        </Badge>
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
                                            );
                                        })}
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
