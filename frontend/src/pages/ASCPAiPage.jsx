import React from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';
import PoolRankings from '../components/ascpai/PoolRankings';
import InterruptionHeatmap from '../components/ascpai/InterruptionHeatmap';
import RebalancingTimeline from '../components/ascpai/RebalancingTimeline';
import AutoRebalanceAuditCard from '../components/ascpai/AutoRebalanceAuditCard';
// GlobalRankingsCard removed - using cluster-specific Pool Rankings only
import BlacklistMonitorCard from '../components/ascpai/BlacklistMonitorCard';
import DecisionEngineV3Dashboard from '../components/ascpai/DecisionEngineV3Dashboard';

const ASCPAiPage = () => {
    const [searchParams] = useSearchParams();
    const navigate = useNavigate();
    const [selectedClusterId, setSelectedClusterId] = React.useState('');
    const [clusters, setClusters] = React.useState([]);
    const [error, setError] = React.useState(null);
    const currentTab = searchParams.get('tab') || 'dashboard';

    React.useEffect(() => {
        const fetchClusters = async () => {
            try {
                setError(null);
                const { clusterAPI } = await import('../services/api');
                const res = await clusterAPI.list();
                const clusterList = res.data.clusters || res.data || [];
                setClusters(clusterList);
                if (clusterList.length > 0) {
                    setSelectedClusterId(clusterList[0].id);
                }
            } catch (e) {
                console.error("Failed to fetch clusters", e);
                setError(e.message || 'Failed to load clusters');
            }
        };
        fetchClusters();
    }, []);



    const selectedCluster = clusters.find(c => c.id === selectedClusterId);

    return (
        <div className="p-6 max-w-7xl mx-auto">
            {/* Page Header & Cluster Selector */}
            <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 mb-6">
                <div>
                    <h1 className="text-2xl font-bold text-gray-900">Balancekube.ai</h1>
                    <p className="text-sm text-gray-500 mt-1">
                        Spot Cost Prediction · Intelligent Rebalancing · ML Pool Optimizer
                    </p>
                </div>
                <div className="w-full md:w-64">
                    <label className="block text-xs font-medium text-gray-500 mb-1">Target Cluster</label>
                    <select
                        value={selectedClusterId}
                        onChange={(e) => setSelectedClusterId(e.target.value)}
                        className="w-full p-2 border border-gray-300 rounded-md shadow-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500 text-sm"
                    >
                        <option value="" disabled>Select Cluster</option>
                        {clusters.map(c => (
                            <option key={c.id} value={c.id}>{c.name} ({c.region})</option>
                        ))}
                    </select>
                </div>
            </div>

            {error && (
                <div className="mb-6 p-4 bg-red-50 border border-red-200 rounded-lg flex items-center justify-between">
                    <div>
                        <p className="text-sm font-medium text-red-800">Failed to load clusters</p>
                        <p className="text-xs text-red-600 mt-0.5">{error}</p>
                    </div>
                    <button
                        onClick={() => window.location.reload()}
                        className="px-3 py-1.5 text-xs font-medium text-red-700 bg-white border border-red-300 rounded-md hover:bg-red-50"
                    >
                        Retry
                    </button>
                </div>
            )}



            {/* Global ML Intelligence Headers (show on dashboard only) */}
            {currentTab === 'dashboard' && <BlacklistMonitorCard />}

            {(!searchParams.get('tab') || searchParams.get('tab') === 'dashboard') && (
                <div className="space-y-6">
                    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                        <AutoRebalanceAuditCard
                            clusterId={selectedClusterId}
                            initialEnabled={selectedCluster?.auto_rebalance_enabled || false}
                            karpenterMode={selectedCluster?.karpenter_mode || null}
                        />
                        <InterruptionHeatmap clusterId={selectedClusterId} />
                    </div>
                    <RebalancingTimeline clusterId={selectedClusterId} />
                    <PoolRankings clusterId={selectedClusterId} initialTemplateId={searchParams.get('template_id')} />
                </div>
            )}

            {searchParams.get('tab') === 'rankings' && (
                <div className="space-y-6">
                    <PoolRankings clusterId={selectedClusterId} initialTemplateId={searchParams.get('template_id')} />
                </div>
            )}

            {searchParams.get('tab') === 'heatmap' && (
                <div className="space-y-6">
                    <InterruptionHeatmap clusterId={selectedClusterId} />
                </div>
            )}

            {searchParams.get('tab') === 'rebalancing' && (
                <div className="space-y-6">
                    <AutoRebalanceAuditCard
                        clusterId={selectedClusterId}
                        initialEnabled={selectedCluster?.auto_rebalance_enabled || false}
                        karpenterMode={selectedCluster?.karpenter_mode || null}
                    />
                    <RebalancingTimeline clusterId={selectedClusterId} />
                </div>
            )}

            {currentTab === 'decision-engine-v3' && (
                <DecisionEngineV3Dashboard
                    clusterId={selectedClusterId}
                    clusterRegion={selectedCluster?.region || 'ap-south-1'}
                    cluster={selectedCluster}
                />
            )}
        </div>
    );
};

export default ASCPAiPage;
