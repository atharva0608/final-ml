import React, { useEffect } from 'react';
import useAtharvaStore from '../store/useAtharvaStore';
import OptimizationStatusHeader from '../components/atharva/OptimizationStatusHeader';
import LivePoolRankings from '../components/atharva/LivePoolRankings';
import NodeTemplateEditor from '../components/atharva/NodeTemplateEditor';
import Recommendations from '../components/atharva/Recommendations';
import RiskMonitor from '../components/atharva/RiskMonitor';
import PoolDetailsModal from '../components/atharva/PoolDetailsModal';
import SwitchConfirmationModal from '../components/atharva/SwitchConfirmationModal';

const AtharvaAiPage = () => {
    const { init, isLoading } = useAtharvaStore();

    useEffect(() => {
        init();
    }, []);

    return (
        <div className="p-6 max-w-7xl mx-auto">
            {/* Page Header */}
            <div className="mb-6">
                <h1 className="text-2xl font-bold text-gray-900">AtharvaAI Live Pool Management</h1>
                <p className="text-sm text-gray-500 mt-1">Intelligent spot instance optimization and pool management</p>
            </div>

            {/* Optimization Status + Activity Feed */}
            <OptimizationStatusHeader />

            {/* Main Content: Rankings + Templates */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-6">
                <div className="lg:col-span-2">
                    <LivePoolRankings />
                </div>
                <div className="lg:col-span-1">
                    <NodeTemplateEditor />
                </div>
            </div>

            {/* Bottom Row: Recommendations + Risk Monitor */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                <Recommendations />
                <RiskMonitor />
            </div>

            {/* Modals */}
            <PoolDetailsModal />
            <SwitchConfirmationModal />
        </div>
    );
};

export default AtharvaAiPage;
