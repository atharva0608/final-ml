import React, { useState, useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';
import { clusterAPI } from '../../services/api';
import PlacementAdvisorDashboard from '../../components/placement/PlacementAdvisorDashboard';

const PlacementAdvisorPage = () => {
    const [searchParams] = useSearchParams();
    const [selectedClusterId, setSelectedClusterId] = useState('');
    const [clusters, setClusters] = useState([]);
    const [error, setError] = useState(null);

    useEffect(() => {
        const fetchClusters = async () => {
            try {
                setError(null);
                const res = await clusterAPI.list();
                const clusterList = res.data.clusters || res.data || [];
                setClusters(clusterList);
                if (clusterList.length > 0) {
                    const initialCluster = searchParams.get('cluster') || clusterList[0].id;
                    setSelectedClusterId(initialCluster);
                }
            } catch (e) {
                console.error("Failed to fetch clusters", e);
                setError(e.message || 'Failed to load clusters');
            }
        };
        fetchClusters();
    }, [searchParams]);

    return (
        <div className="p-6 max-w-7xl mx-auto space-y-6">
            <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
                <div>
                    <h1 className="text-2xl font-bold text-gray-900">Placement Advisor</h1>
                    <p className="text-sm text-gray-500 mt-1">
                        Automated workload placement policies & rollout status
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
                <div className="p-4 bg-red-50 border border-red-200 rounded-lg flex items-center justify-between">
                    <div>
                        <p className="text-sm font-medium text-red-800">Failed to load clusters</p>
                        <p className="text-xs text-red-600 mt-0.5">{error}</p>
                    </div>
                </div>
            )}

            {selectedClusterId ? (
                <PlacementAdvisorDashboard clusterId={selectedClusterId} />
            ) : (
                !error && <div className="text-gray-500 p-8 text-center bg-gray-50 rounded-lg border border-gray-200">Please select a cluster to view placement policies.</div>
            )}
        </div>
    );
};

export default PlacementAdvisorPage;
