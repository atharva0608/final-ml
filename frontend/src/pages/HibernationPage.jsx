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
import HistoryLog from '../components/hibernation/HistoryLog';
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
        <div className="min-h-screen bg-gray-50 p-8">
            <div className="max-w-7xl mx-auto">
                {/* Header - Larger and more prominent */}
                <div className="mb-8">
                    <Link
                        to="/clusters"
                        className="inline-flex items-center gap-2 text-sm text-gray-600 hover:text-gray-900 mb-6 font-medium"
                    >
                        <FiArrowLeft className="w-5 h-5" />
                        Back to Clusters
                    </Link>
                    <div className="flex items-center gap-4 bg-white p-6 rounded-xl shadow-sm border border-gray-200">
                        <div className="p-4 bg-blue-100 rounded-xl">
                            <FiActivity className="w-8 h-8 text-blue-600" />
                        </div>
                        <div>
                            <h1 className="text-3xl font-bold text-gray-900">Cluster Hibernation</h1>
                            <p className="text-base text-gray-600 mt-1">{clusterName} • Configure automatic sleep schedules</p>
                        </div>
                    </div>
                </div>

                {/* Main Content Grid - Full-page scheduler */}
                <div className="mb-8">
                    <HibernationScheduler />
                </div>

                {/* Hibernation History */}
                <div className="mb-8">
                    <HistoryLog />
                </div>
            </div>
        </div>
    );
};

export default HibernationPage;
