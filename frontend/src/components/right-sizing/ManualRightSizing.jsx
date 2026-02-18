import React, { useState, useEffect } from 'react';
import { FiDollarSign, FiTrendingDown, FiServer, FiCheckCircle, FiCpu, FiInfo, FiArrowDownRight, FiLayers } from 'react-icons/fi';
import { Card, Button, Badge } from '../shared';
import { useClusterStore } from '../../store/useStore';
import { api, optimizationAPI } from '../../services/api';
import toast from 'react-hot-toast';
import EmptyState from '../shared/EmptyState';

// Sub-components (shared with parent)
import ImpactSummary from './ImpactSummary';
import BatchApplyModal from './BatchApplyModal';
import SavingsTracker from './SavingsTracker';
import InstanceUsageDetailPanel from './InstanceUsageDetailPanel';
import RecommendationAgeIndicator from './RecommendationAgeIndicator';

/**
 * ManualRightSizing — extracted from the original RightSizing.jsx.
 *
 * Renders manual right-sizing recommendations: KPI strip, recommendations
 * table, savings tracker, instance detail slide-over, and batch apply modal.
 */
const ManualRightSizing = () => {
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
            const res = await api.get('/api/v1/optimization/savings/realized');
            setSavingsData(res.data);
        } catch (err) {
            console.error("Failed to load savings history", err);
        }
    };

    const fetchRecommendations = async () => {
        try {
            setLoading(true);
            const clusterId = selectedCluster?.id;
            const res = await optimizationAPI.getRightsizing(clusterId, {
                analysis_window_hours: 336
            });

            const recommendationsData = Array.isArray(res.data) ? res.data : [];
            setRecommendations(recommendationsData);

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
        setSelectedForBatch([instance]);
        setIsBatchModalOpen(true);
    };

    if (loading) {
        return (
            <div className="min-h-[400px] flex items-center justify-center">
                <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
            </div>
        );
    }

    const hasRecommendations = recommendations.length > 0;

    const calculateStats = () => {
        if (!data) return {};
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
            vcpu_reduction: Math.round(vcpuReduction * 10) / 10,
            memory_reduction: Math.round(memoryReduction * 10) / 10,
            optimization_score: data.optimization_score || 0
        };
    };

    return (
        <div className="space-y-6 relative">
            {/* Batch Apply Header */}
            {hasRecommendations && (
                <div className="flex justify-end">
                    <Button variant="primary" onClick={() => setIsBatchModalOpen(true)}>
                        Batch Apply Fixes ({selectedForBatch.length})
                    </Button>
                </div>
            )}

            {/* KPI Strip */}
            <ImpactSummary stats={calculateStats()} />

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                {/* Main Content Area */}
                <div className="lg:col-span-2 space-y-6">
                    <Card className="overflow-hidden flex flex-col h-full">
                        <div className="px-6 py-4 border-b border-gray-100 flex items-center justify-between bg-white">
                            <h3 className="font-bold text-gray-900">Right Sizing Recommendations</h3>
                            <div className="flex items-center gap-2">
                                <div className="relative">
                                    <input
                                        type="text"
                                        placeholder="Filter workloads..."
                                        className="pl-8 pr-3 py-1.5 text-xs border border-gray-200 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-transparent outline-none w-48 transition-all"
                                    // TODO: implement filter logic
                                    />
                                    <FiCheckCircle className="absolute left-2.5 top-1/2 -translate-y-1/2 text-gray-400 w-3 h-3" />
                                </div>
                                <Button size="sm" variant="outline" onClick={fetchRecommendations} title="Refresh">
                                    <FiTrendingDown className="w-4 h-4" />
                                </Button>
                            </div>
                        </div>

                        {!hasRecommendations ? (
                            <div className="p-12 text-center text-gray-500 flex flex-col items-center justify-center h-64">
                                <div className="w-16 h-16 bg-green-50 rounded-full flex items-center justify-center mb-4">
                                    <FiCheckCircle className="w-8 h-8 text-green-500" />
                                </div>
                                <h4 className="text-lg font-semibold text-gray-900">All Optimized!</h4>
                                <p className="text-sm mt-1 max-w-xs mx-auto">Your workloads are running efficiently. No right-sizing opportunities found in the last 14 days.</p>
                            </div>
                        ) : (
                            <div className="overflow-x-auto flex-1">
                                <table className="w-full text-left border-collapse">
                                    <thead className="bg-gray-50/50 text-xs text-gray-500 font-semibold uppercase tracking-wider sticky top-0 z-10">
                                        <tr>
                                            <th className="py-3 px-6 border-b border-gray-100">Workload</th>
                                            <th className="py-3 px-6 border-b border-gray-100">Resource Usage</th>
                                            <th className="py-3 px-6 border-b border-gray-100">Recommendation</th>
                                            <th className="py-3 px-6 border-b border-gray-100 text-right">Potential Savings</th>
                                            <th className="py-3 px-6 border-b border-gray-100 text-center">Confidence</th>
                                            <th className="py-3 px-6 border-b border-gray-100"></th>
                                        </tr>
                                    </thead>
                                    <tbody className="divide-y divide-gray-50 bg-white">
                                        {recommendations.map((item, idx) => {
                                            const cpuUtilPct = item.current_cpu_request_millicores > 0
                                                ? Math.round((item.cpu_avg_millicores / item.current_cpu_request_millicores) * 100) : 0;
                                            const memUtilPct = item.current_memory_request_mb > 0
                                                ? Math.round((item.memory_avg_mb / item.current_memory_request_mb) * 100) : 0;

                                            return (
                                                <tr
                                                    key={`${item.namespace}-${item.controller_name}-${idx}`}
                                                    className={`group hover:bg-blue-50/40 transition-colors cursor-pointer ${selectedInstance?.controller_name === item.controller_name ? 'bg-blue-50 border-l-4 border-blue-500' : 'border-l-4 border-transparent'
                                                        }`}
                                                    onClick={() => setSelectedInstance(item)}
                                                >
                                                    <td className="py-3 px-6">
                                                        <div className="flex items-center gap-3">
                                                            <div className="p-2 bg-gray-100 text-gray-500 rounded-lg group-hover:bg-white group-hover:text-blue-600 transition-colors">
                                                                <FiLayers className="w-5 h-5" />
                                                            </div>
                                                            <div>
                                                                <div className="font-bold text-gray-900 text-sm">{item.controller_name}</div>
                                                                <div className="text-[11px] text-gray-400 font-mono mt-0.5 flex items-center gap-1.5">
                                                                    <span className="bg-gray-100 px-1.5 py-0.5 rounded text-gray-600">{item.namespace}</span>
                                                                    <span>{item.controller_kind}</span>
                                                                </div>
                                                            </div>
                                                        </div>
                                                    </td>
                                                    <td className="py-3 px-6">
                                                        <div className="space-y-3 w-40">
                                                            {/* CPU Bar */}
                                                            <div className="space-y-1">
                                                                <div className="flex justify-between text-[10px] uppercase font-semibold text-gray-500">
                                                                    <span>CPU</span>
                                                                    <span>{cpuUtilPct}%</span>
                                                                </div>
                                                                <div className="h-1.5 w-full bg-gray-100 rounded-full overflow-hidden">
                                                                    <div
                                                                        className={`h-full rounded-full ${cpuUtilPct > 80 ? 'bg-red-500' : cpuUtilPct > 50 ? 'bg-yellow-400' : 'bg-green-500'}`}
                                                                        style={{ width: `${Math.min(100, cpuUtilPct)}%` }}
                                                                    />
                                                                </div>
                                                            </div>
                                                            {/* Memory Bar */}
                                                            <div className="space-y-1">
                                                                <div className="flex justify-between text-[10px] uppercase font-semibold text-gray-500">
                                                                    <span>Mem</span>
                                                                    <span>{memUtilPct}%</span>
                                                                </div>
                                                                <div className="h-1.5 w-full bg-gray-100 rounded-full overflow-hidden">
                                                                    <div
                                                                        className={`h-full rounded-full ${memUtilPct > 80 ? 'bg-red-500' : memUtilPct > 50 ? 'bg-yellow-400' : 'bg-green-500'}`}
                                                                        style={{ width: `${Math.min(100, memUtilPct)}%` }}
                                                                    />
                                                                </div>
                                                            </div>
                                                        </div>
                                                    </td>
                                                    <td className="py-3 px-6">
                                                        <div className="flex flex-col gap-1 text-xs">
                                                            <div className="flex items-center gap-2">
                                                                <span className="min-w-[30px] text-gray-400">CPU</span>
                                                                <span className="font-mono text-gray-500 strike-through decoration-red-400 decoration-2">{item.current_cpu_request_millicores}m</span>
                                                                <FiArrowDownRight className="text-green-500" />
                                                                <span className="font-mono font-bold text-gray-900 bg-green-50 px-1 rounded border border-green-100">{item.recommended_cpu_request_millicores}m</span>
                                                            </div>
                                                            <div className="flex items-center gap-2">
                                                                <span className="min-w-[30px] text-gray-400">Mem</span>
                                                                <span className="font-mono text-gray-500 strike-through decoration-red-400 decoration-2">{item.current_memory_request_mb}Mi</span>
                                                                <FiArrowDownRight className="text-green-500" />
                                                                <span className="font-mono font-bold text-gray-900 bg-green-50 px-1 rounded border border-green-100">{item.recommended_memory_request_mb}Mi</span>
                                                            </div>
                                                        </div>
                                                    </td>
                                                    <td className="py-3 px-6 text-right">
                                                        <div className="text-green-600 font-bold text-sm flex items-center justify-end gap-1">
                                                            <FiDollarSign className="w-3 h-3" />{item.savings_monthly.toFixed(2)}
                                                        </div>
                                                        <div className="text-[10px] text-gray-400">/ month</div>
                                                    </td>
                                                    <td className="py-3 px-6 text-center">
                                                        <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[10px] font-bold uppercase tracking-wide border ${item.confidence === 'HIGH' ? 'bg-green-50 text-green-700 border-green-200' :
                                                                item.confidence === 'MEDIUM' ? 'bg-yellow-50 text-yellow-700 border-yellow-200' :
                                                                    'bg-gray-100 text-gray-600 border-gray-200'
                                                            }`}>
                                                            <span className={`w-1.5 h-1.5 rounded-full ${item.confidence === 'HIGH' ? 'bg-green-500' :
                                                                    item.confidence === 'MEDIUM' ? 'bg-yellow-500' :
                                                                        'bg-gray-400'
                                                                }`} />
                                                            {item.confidence}
                                                        </span>
                                                    </td>
                                                    <td className="py-3 px-6 text-right">
                                                        <Button
                                                            size="sm"
                                                            variant="primary"
                                                            className="opacity-0 group-hover:opacity-100 transition-opacity shadow-sm"
                                                            onClick={(e) => { e.stopPropagation(); handleApply(item); }}
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

                {/* Right Column */}
                <div className="space-y-6">
                    <div className="h-64">
                        <SavingsTracker />
                    </div>
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
                    fetchRecommendations();
                }}
            />
        </div>
    );
};

export default ManualRightSizing;
