import React from 'react';
import PoolRankings from '../components/atharvaai/PoolRankings';
import InterruptionHeatmap from '../components/atharvaai/InterruptionHeatmap';
import RebalancingTimeline from '../components/atharvaai/RebalancingTimeline';
import AutoRebalanceAuditCard from '../components/atharvaai/AutoRebalanceAuditCard';

const AtharvaAiPage = () => {
    return (
        <div className="p-6 max-w-7xl mx-auto">
            {/* Page Header */}
            <div className="mb-6">
                <h1 className="text-2xl font-bold text-gray-900">AtharvaAI - ML Pool Optimizer</h1>
                <p className="text-sm text-gray-500 mt-1">
                    8-Step ML pipeline for intelligent spot instance pool selection and termination monitoring
                </p>
            </div>

            {/* Main Pool Rankings - Full Width */}
            <div className="mb-6">
                <PoolRankings />
            </div>

            {/* Two Column Layout */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
                <InterruptionHeatmap />
                <AutoRebalanceAuditCard />
            </div>

            {/* Rebalancing Timeline - Full Width */}
            <div className="mb-6">
                <RebalancingTimeline />
            </div>
        </div>
    );
};

export default AtharvaAiPage;
