import React from 'react';
import { useSearchParams } from 'react-router-dom';
import PoolRankings from '../components/atharvaai/PoolRankings';
import InterruptionHeatmap from '../components/atharvaai/InterruptionHeatmap';
import RebalancingTimeline from '../components/atharvaai/RebalancingTimeline';
import AutoRebalanceAuditCard from '../components/atharvaai/AutoRebalanceAuditCard';

const AtharvaAiPage = () => {
    const [searchParams] = useSearchParams();
    const [selectedClusterId, setSelectedClusterId] = React.useState('');
    const [clusters, setClusters] = React.useState([]);

    React.useEffect(() => {
        // Fetch clusters for dropdown
        const fetchClusters = async () => {
            // Mock fetch for now, replace with actual API call if available or import from store/api
            // Assuming clusterAPI is imported or available via context/store
            // For now, let's use a simple placeholder if API import is needed
            // In a real implementation, import { clusterAPI } from '../services/api';
            try {
                //Dynamic import to avoid top-level dependency issues if not already present
                const { clusterAPI } = await import('../services/api');
                const res = await clusterAPI.list();
                const clusterList = res.data.clusters || res.data || [];
                setClusters(clusterList);
                if (clusterList.length > 0) {
                    setSelectedClusterId(clusterList[0].id);
                }
            } catch (e) {
                console.error("Failed to fetch clusters", e);
            }
        };
        fetchClusters();
    }, []);

    return (
        <div className="p-6 max-w-7xl mx-auto">
            {/* Page Header & Cluster Selector */}
            <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 mb-6">
                <div>
                    <h1 className="text-2xl font-bold text-gray-900">AtharvaAI - ML Pool Optimizer</h1>
                    <p className="text-sm text-gray-500 mt-1">
                        8-Step ML pipeline for intelligent spot instance pool selection and termination monitoring
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

            {/* Two Column Layout - Audit & Heatmap (Moved to Top) */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
                <AutoRebalanceAuditCard clusterId={selectedClusterId} />
                <InterruptionHeatmap clusterId={selectedClusterId} />
            </div>

            {/* Rebalancing Timeline - Middle */}
            <div className="mb-6">
                <RebalancingTimeline clusterId={selectedClusterId} />
            </div>

            {/* Main Pool Rankings - Bottom */}
            <div className="mb-6">
                <PoolRankings
                    clusterId={selectedClusterId}
                    initialTemplateId={searchParams.get('template_id')}
                />
            </div>
        </div>
    );
};

export default AtharvaAiPage;
