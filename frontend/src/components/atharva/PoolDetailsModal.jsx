import React, { useState } from 'react';
import useAtharvaStore from '../../store/useAtharvaStore';
import {
    FiX, FiCpu, FiAlertTriangle, FiDollarSign, FiActivity,
    FiArrowRight, FiShield, FiCloud, FiHardDrive, FiZap
} from 'react-icons/fi';

const TABS = [
    { id: 'overview', label: 'Overview', icon: FiCloud },
    { id: 'specs', label: 'Specs', icon: FiCpu },
    { id: 'risk', label: 'Risk', icon: FiAlertTriangle },
    { id: 'cost', label: 'Cost', icon: FiDollarSign },
    { id: 'usage', label: 'Usage', icon: FiActivity },
    { id: 'switch', label: 'Switch Preview', icon: FiArrowRight },
];

const PoolDetailsModal = () => {
    const { showPoolDetails, poolDetails, closePoolDetails, openSwitchConfirm, addToBlacklist } = useAtharvaStore();
    const [activeTab, setActiveTab] = useState('overview');

    if (!showPoolDetails) return null;

    const d = poolDetails;

    const handleBlacklist = () => {
        if (d?.overview) {
            addToBlacklist({
                instance_type: d.overview.instance_type,
                availability_zone: d.overview.availability_zone,
                reason: 'manual',
                duration_hours: 12
            });
            closePoolDetails();
        }
    };

    return (
        <div className="fixed inset-0 bg-black/40 backdrop-blur-sm z-50 flex items-center justify-center p-4" onClick={closePoolDetails}>
            <div className="bg-white rounded-xl shadow-2xl w-full max-w-2xl max-h-[85vh] overflow-hidden" onClick={e => e.stopPropagation()}>
                {/* Header */}
                <div className="flex items-center justify-between p-5 border-b border-gray-200">
                    <div>
                        <h2 className="text-lg font-bold text-gray-900">
                            {d ? d.overview.instance_type : 'Loading...'}
                        </h2>
                        {d && <p className="text-xs text-gray-500 mt-0.5">{d.overview.availability_zone} • {d.overview.pool_name}</p>}
                    </div>
                    <button onClick={closePoolDetails} className="p-2 hover:bg-gray-100 rounded-lg"><FiX className="w-5 h-5" /></button>
                </div>

                {/* Tabs */}
                <div className="flex border-b border-gray-200 px-5 overflow-x-auto">
                    {TABS.map(tab => (
                        <button
                            key={tab.id}
                            onClick={() => setActiveTab(tab.id)}
                            className={`flex items-center gap-1.5 px-3 py-2.5 text-xs font-medium border-b-2 transition-colors whitespace-nowrap ${activeTab === tab.id
                                    ? 'border-blue-600 text-blue-600' : 'border-transparent text-gray-500 hover:text-gray-700'
                                }`}
                        >
                            <tab.icon className="w-3.5 h-3.5" /> {tab.label}
                        </button>
                    ))}
                </div>

                {/* Content */}
                <div className="p-5 overflow-y-auto max-h-[55vh]">
                    {!d ? (
                        <div className="flex items-center justify-center py-12 text-gray-400">
                            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600" />
                        </div>
                    ) : (
                        <>
                            {activeTab === 'overview' && <OverviewTab data={d.overview} />}
                            {activeTab === 'specs' && <SpecsTab data={d.specifications} />}
                            {activeTab === 'risk' && <RiskTab data={d.risk_breakdown} />}
                            {activeTab === 'cost' && <CostTab data={d.cost_analysis} />}
                            {activeTab === 'usage' && <UsageTab data={d.current_usage} />}
                            {activeTab === 'switch' && <SwitchPreviewTab data={d.switch_preview} />}
                        </>
                    )}
                </div>

                {/* Footer Actions */}
                {d && (
                    <div className="flex items-center justify-between p-5 border-t border-gray-200 bg-gray-50">
                        <button onClick={handleBlacklist}
                            className="px-4 py-2 text-xs font-medium text-red-600 bg-red-50 rounded-lg hover:bg-red-100 border border-red-200 transition-colors">
                            Blacklist 12h
                        </button>
                        <div className="flex gap-2">
                            <button onClick={closePoolDetails}
                                className="px-4 py-2 text-xs font-medium text-gray-600 bg-white rounded-lg hover:bg-gray-50 border border-gray-200 transition-colors">
                                Close
                            </button>
                            <button onClick={() => { closePoolDetails(); openSwitchConfirm({ instance_type: d.overview.instance_type, pool_id: 'current', availability_zone: d.overview.availability_zone }); }}
                                className="px-4 py-2 text-xs font-semibold text-white bg-blue-600 rounded-lg hover:bg-blue-700 transition-colors">
                                Switch to This Pool
                            </button>
                        </div>
                    </div>
                )}
            </div>
        </div>
    );
};

const StatRow = ({ label, value, className = '' }) => (
    <div className="flex justify-between py-2 border-b border-gray-50">
        <span className="text-xs text-gray-500">{label}</span>
        <span className={`text-xs font-semibold text-gray-900 ${className}`}>{value}</span>
    </div>
);

const OverviewTab = ({ data }) => (
    <div className="space-y-1">
        <StatRow label="Instance Type" value={data.instance_type} />
        <StatRow label="Availability Zone" value={data.availability_zone} />
        <StatRow label="Risk Score" value={`${(data.risk_score * 100).toFixed(0)}%`} className={data.risk_score < 0.3 ? 'text-green-600' : 'text-yellow-600'} />
        <StatRow label="Interruption Rate" value={`${(data.interruption_rate * 100).toFixed(1)}%`} />
        <StatRow label="Spot Price" value={`$${data.spot_price_current.toFixed(4)}/hr`} />
        <StatRow label="On-Demand Price" value={`$${data.ondemand_price.toFixed(4)}/hr`} />
        <StatRow label="Discount" value={`${data.discount_percentage.toFixed(1)}%`} className="text-green-600" />
    </div>
);

const SpecsTab = ({ data }) => (
    <div className="space-y-1">
        <StatRow label="vCPU" value={data.vcpu} />
        <StatRow label="Memory" value={`${data.memory_gib} GiB`} />
        <StatRow label="Architecture" value={data.architecture} />
        <StatRow label="Network" value={data.network_performance} />
        <StatRow label="Storage" value={data.storage} />
        <StatRow label="EBS Optimized" value={data.ebs_optimized ? 'Yes' : 'No'} />
    </div>
);

const RiskTab = ({ data }) => (
    <div className="space-y-3">
        <div className="p-3 rounded-lg bg-gray-50">
            <div className="flex justify-between mb-2">
                <span className="text-xs text-gray-500">Overall Risk</span>
                <span className="text-lg font-bold text-gray-900">{(data.overall_risk_score * 100).toFixed(0)}%</span>
            </div>
            <div className="w-full bg-gray-200 rounded-full h-2">
                <div className="h-2 rounded-full transition-all" style={{
                    width: `${data.overall_risk_score * 100}%`,
                    backgroundColor: data.overall_risk_score < 0.3 ? '#22c55e' : data.overall_risk_score < 0.6 ? '#eab308' : '#ef4444'
                }} />
            </div>
        </div>
        <StatRow label="Interruption Probability" value={`${(data.interruption_probability * 100).toFixed(1)}%`} />
        <StatRow label="Regional Capacity" value={`${(data.regional_capacity_score * 100).toFixed(0)}%`} />
        <StatRow label="Interruptions (24h)" value={data.historical_interruptions_24h} />
        <StatRow label="Global Interruptions (1h)" value={data.global_interruptions_1h} />
    </div>
);

const CostTab = ({ data }) => (
    <div className="space-y-3">
        <StatRow label="Hourly Cost" value={`$${data.hourly_cost.toFixed(4)}`} />
        <StatRow label="Daily Cost" value={`$${data.daily_cost.toFixed(2)}`} />
        <StatRow label="Monthly Projection" value={`$${data.monthly_cost_projection.toFixed(2)}`} />
        <div className="p-3 rounded-lg bg-green-50 border border-green-100">
            <p className="text-[10px] font-bold text-green-700 uppercase mb-2">Savings vs On-Demand</p>
            <div className="grid grid-cols-3 gap-3 text-center">
                <div><p className="text-xs text-gray-500">Hourly</p><p className="text-sm font-bold text-green-700">${data.savings_vs_ondemand.hourly.toFixed(4)}</p></div>
                <div><p className="text-xs text-gray-500">Monthly</p><p className="text-sm font-bold text-green-700">${data.savings_vs_ondemand.monthly.toFixed(2)}</p></div>
                <div><p className="text-xs text-gray-500">Discount</p><p className="text-sm font-bold text-green-700">{data.savings_vs_ondemand.percentage.toFixed(1)}%</p></div>
            </div>
        </div>
    </div>
);

const UsageTab = ({ data }) => {
    if (!data) return <p className="text-sm text-gray-400 text-center py-8">No current usage data</p>;
    return (
        <div className="space-y-3">
            <StatRow label="Nodes in Cluster" value={data.nodes_in_cluster} />
            <StatRow label="Total Pods" value={data.total_pods} />
            <div>
                <div className="flex justify-between mb-1"><span className="text-xs text-gray-500">CPU Utilization</span><span className="text-xs font-semibold">{data.avg_cpu_utilization}%</span></div>
                <div className="w-full bg-gray-200 rounded-full h-2"><div className="h-2 bg-blue-500 rounded-full" style={{ width: `${data.avg_cpu_utilization}%` }} /></div>
            </div>
            <div>
                <div className="flex justify-between mb-1"><span className="text-xs text-gray-500">Memory Utilization</span><span className="text-xs font-semibold">{data.avg_memory_utilization}%</span></div>
                <div className="w-full bg-gray-200 rounded-full h-2"><div className="h-2 bg-purple-500 rounded-full" style={{ width: `${data.avg_memory_utilization}%` }} /></div>
            </div>
        </div>
    );
};

const SwitchPreviewTab = ({ data }) => {
    if (!data) return <p className="text-sm text-gray-400 text-center py-8">No switch preview available</p>;
    return (
        <div className="space-y-3">
            <div className="p-3 rounded-lg bg-blue-50 border border-blue-100 space-y-1">
                <StatRow label="Nodes to Migrate" value={data.nodes_to_migrate} />
                <StatRow label="Pods to Reschedule" value={data.pods_to_reschedule} />
                <StatRow label="Est. Duration" value={data.estimated_duration} />
                <StatRow label="Expected Downtime" value={data.estimated_downtime} />
            </div>
            <div className="grid grid-cols-2 gap-3">
                <div className={`p-3 rounded-lg border ${data.cost_impact.monthly_change < 0 ? 'bg-green-50 border-green-100' : 'bg-red-50 border-red-100'}`}>
                    <p className="text-[10px] font-bold uppercase text-gray-500 mb-1">Cost Impact</p>
                    <p className={`text-sm font-bold ${data.cost_impact.monthly_change < 0 ? 'text-green-700' : 'text-red-700'}`}>
                        {data.cost_impact.monthly_change < 0 ? '' : '+'}${data.cost_impact.monthly_change.toFixed(2)}/mo
                    </p>
                </div>
                <div className={`p-3 rounded-lg border ${data.risk_impact.change === 'improving' ? 'bg-green-50 border-green-100' : 'bg-red-50 border-red-100'}`}>
                    <p className="text-[10px] font-bold uppercase text-gray-500 mb-1">Risk Impact</p>
                    <p className={`text-sm font-bold ${data.risk_impact.change === 'improving' ? 'text-green-700' : 'text-red-700'}`}>
                        {(data.risk_impact.current_risk * 100).toFixed(0)}% → {(data.risk_impact.new_risk * 100).toFixed(0)}%
                    </p>
                </div>
            </div>
        </div>
    );
};

export default PoolDetailsModal;
