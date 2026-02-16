/**
 * Hibernation Page - Consolidated cluster hibernation management
 *
 * Layout:
 * - Header with back link
 * - Strategy selector
 * - HibernationScheduler (calendar + time inputs + scheduled jobs)
 * - Validation + Cost analytics sidebar
 */
import React, { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { useHibernationStore } from '../store/useHibernationStore';
import StrategySelector from '../components/hibernation/StrategySelector';
import HibernationScheduler from '../components/hibernation/HibernationScheduler';
import ValidationPanel from '../components/hibernation/ValidationPanel';
import CostAnalytics from '../components/hibernation/CostAnalytics';
import { FiArrowLeft, FiActivity } from 'react-icons/fi';
import { Link } from 'react-router-dom';

const HibernationPage = () => {
    const { clusterId } = useParams();
    const { fetchInitialData, loading } = useHibernationStore();
    const [clusterName, setClusterName] = useState('');

    useEffect(() => {
        if (clusterId) {
            fetchInitialData(clusterId);
            setClusterName(`Cluster ${clusterId.substring(0, 8)}`);
        }
    }, [clusterId, fetchInitialData]);

    if (loading) {
        return (
            <div className="min-h-screen bg-gray-50 flex items-center justify-center">
                <div className="text-center">
                    <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto mb-4"></div>
                    <p className="text-gray-600">Loading hibernation configuration...</p>
                </div>
            </div>
        );
    }

    return (
        <div className="min-h-screen bg-gray-50 p-6">
            <div className="max-w-7xl mx-auto">
                {/* Header */}
                <div className="mb-6">
                    <Link
                        to="/clusters"
                        className="inline-flex items-center gap-2 text-sm text-gray-600 hover:text-gray-900 mb-4"
                    >
                        <FiArrowLeft className="w-4 h-4" />
                        Back to Clusters
                    </Link>
                    <div className="flex items-center gap-3">
                        <div className="p-3 bg-blue-100 rounded-lg">
                            <FiActivity className="w-6 h-6 text-blue-600" />
                        </div>
                        <div>
                            <h1 className="text-2xl font-bold text-gray-900">Cluster Hibernation</h1>
                            <p className="text-sm text-gray-500">{clusterName}</p>
                        </div>
                    </div>
                </div>

                {/* Strategy Selector */}
                <div className="mb-6">
                    <StrategySelector />
                </div>

                {/* Main Content Grid */}
                <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-6">
                    {/* Scheduler - Takes up 2 columns */}
                    <div className="lg:col-span-2">
                        <HibernationScheduler />
                    </div>

                    {/* Right sidebar: Validation + Cost */}
                    <div className="space-y-6">
                        <ValidationPanel />
                        <CostAnalytics />
                    </div>
                </div>
            </div>
        </div>
    );
};

export default HibernationPage;
