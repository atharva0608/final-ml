import React, { useEffect, useState } from 'react';
import { useHibernationStore } from '../../store/useHibernationStore';
import { useClusterStore } from '../../store/useStore';
import { clusterAPI } from '../../services/api';
import { FiMonitor, FiBell, FiUser, FiMaximize2, FiDollarSign } from 'react-icons/fi';
import { Dropdown, Badge } from '../shared';

const HibernationHeader = () => {
    const { clusterId, setClusterId, metrics, fetchInitialData } = useHibernationStore();
    const { clusters, setClusters } = useClusterStore();
    const [loading, setLoading] = useState(false);
    const selectedCluster = clusters.find(c => c.id === clusterId);

    // Fetch clusters on mount
    useEffect(() => {
        const fetchClusters = async () => {
            try {
                console.log('HibernationHeader - Fetching clusters...');
                setLoading(true);
                const response = await clusterAPI.list({});
                const fetchedClusters = response.data.clusters || [];
                console.log('HibernationHeader - Fetched clusters:', fetchedClusters);
                setClusters(fetchedClusters);
            } catch (error) {
                console.error('HibernationHeader - Failed to fetch clusters', error);
            } finally {
                setLoading(false);
            }
        };
        fetchClusters();
    }, [setClusters]);

    useEffect(() => {
        if (clusterId) {
            // Re-fetch if cluster changes
            fetchInitialData(clusterId);
        }
    }, [clusterId, fetchInitialData]);

    // Initial load if no cluster selected but clusters exist
    useEffect(() => {
        console.log('HibernationHeader - Auto-select check:', { clusterId, clustersLength: clusters.length });
        if (!clusterId && clusters.length > 0) {
            console.log('HibernationHeader - Auto-selecting first cluster:', clusters[0].id);
            setClusterId(clusters[0].id);
        }
    }, [clusters, clusterId, setClusterId]);

    return (
        <header className="bg-white/80 backdrop-blur-md border-b border-gray-200 sticky top-0 z-50">
            <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">

                {/* Left: Branding & Breadcrumbs */}
                <div className="flex items-center gap-4">
                    <div className="flex items-center gap-2">
                        <div className="bg-blue-600 p-2 rounded-lg">
                            <FiMonitor className="w-5 h-5 text-white" />
                        </div>
                        <h1 className="text-xl font-bold text-gray-900 hidden md:block">Hibernation</h1>
                    </div>
                    <div className="hidden md:flex items-center text-sm text-gray-500">
                        <span className="mx-2">/</span>
                        <span>Clusters</span>
                        <span className="mx-2">/</span>
                        <span className="font-medium text-gray-900">{selectedCluster ? selectedCluster.name : 'Select Cluster'}</span>
                    </div>
                </div>

                {/* Center: Cluster Selector */}
                <div className="flex-1 max-w-lg mx-8">
                    <div className="relative">
                        <select
                            value={clusterId || ''}
                            onChange={(e) => setClusterId(e.target.value)}
                            className="w-full pl-4 pr-10 py-2 border border-gray-300 rounded-lg appearance-none focus:outline-none focus:ring-2 focus:ring-blue-500 bg-white shadow-sm transition-all hover:border-gray-400 cursor-pointer"
                        >
                            <option value="" disabled>Select a cluster...</option>
                            {clusters.map((cluster) => (
                                <option key={cluster.id} value={cluster.id}>
                                    {cluster.name} ({cluster.region}) - {cluster.status}
                                </option>
                            ))}
                        </select>
                        <div className="absolute inset-y-0 right-0 flex items-center px-2 pointer-events-none">
                            <svg className="w-4 h-4 text-gray-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 9l-7 7-7-7"></path></svg>
                        </div>
                    </div>
                </div>

                {/* Right: Actions & Savings */}
                <div className="flex items-center gap-4">
                    {/* Savings Counter */}
                    <div className="hidden lg:flex items-center gap-2 bg-green-50 px-3 py-1.5 rounded-full border border-green-100">
                        <span className="p-1 bg-green-100 rounded-full text-green-600">
                            <FiDollarSign className="w-4 h-4" />
                        </span>
                        <div className="flex flex-col leading-none">
                            <span className="text-[10px] text-green-700 font-medium uppercase tracking-wider">Saved This Month</span>
                            <span className="text-sm font-bold text-green-800">
                                ${metrics.monthlySavings.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                            </span>
                        </div>
                    </div>

                    <div className="h-6 w-px bg-gray-200 hidden md:block"></div>

                    <button className="p-2 text-gray-400 hover:text-gray-600 transition-colors relative">
                        <FiBell className="w-5 h-5" />
                        <span className="absolute top-1.5 right-1.5 w-2 h-2 bg-red-500 rounded-full border-2 border-white"></span>
                    </button>
                    <button className="p-2 text-gray-400 hover:text-gray-600 transition-colors">
                        <FiUser className="w-5 h-5" />
                    </button>
                </div>
            </div>
        </header>
    );
};

export default HibernationHeader;
