import React, { useState, useEffect } from 'react';
import { decisionEngineAPI, workloadClassificationAPI } from '../../services/api';
import { FiLayers, FiCheckCircle, FiShield, FiAlertTriangle, FiXCircle, FiExternalLink } from 'react-icons/fi';
import { useNavigate } from 'react-router-dom';

const TIER_COLORS = {
    Platinum: { bg: '#fef2f2', text: '#991b1b', border: '#fecaca' },
    Gold:     { bg: '#fffbeb', text: '#92400e', border: '#fde68a' },
    Silver:   { bg: '#eff6ff', text: '#1e40af', border: '#bfdbfe' },
    Bronze:   { bg: '#f0fdf4', text: '#166534', border: '#bbf7d0' },
};

const CONFIDENCE_COLORS = {
    CONFIRMED:   { color: '#16a34a' },
    PROVISIONAL: { color: '#d97706' },
    DRAFT:       { color: '#6b7280' },
};

const NODE_STATUS_CONFIG = {
    STATELESS_ELIGIBLE: {
        label: 'Stateless Eligible',
        icon: FiCheckCircle,
        color: 'green',
        description: 'Safe to optimize - no persistent state',
    },
    STATEFUL_PROTECTED: {
        label: 'Stateful Protected',
        icon: FiShield,
        color: 'orange',
        description: 'Has PVC/StatefulSet - protected from replacement',
    },
    DRAIN_UNSAFE: {
        label: 'Drain Unsafe',
        icon: FiAlertTriangle,
        color: 'red',
        description: 'PDB maxUnavailable=0 or finalizer issue',
    },
    SYSTEM_PROTECTED: {
        label: 'System Protected',
        icon: FiXCircle,
        color: 'purple',
        description: 'Control plane or system node',
    }
};

const WorkloadClassificationPanel = ({ clusterId }) => {
    const [classification, setClassification] = useState(null);
    const [loading, setLoading] = useState(true);
    const [expandedNodes, setExpandedNodes] = useState(false);
    const [wieSummary, setWieSummary] = useState(null);
    const navigate = useNavigate();

    useEffect(() => {
        const fetchClassification = async () => {
            try {
                const response = await decisionEngineAPI.getWorkloadStatus(clusterId);
                setClassification(response.data);
            } catch (err) {
                console.error('Failed to fetch workload classification:', err);
            } finally {
                setLoading(false);
            }
        };

        const fetchWieSummary = async () => {
            try {
                const res = await workloadClassificationAPI.getSummary(clusterId);
                setWieSummary(res.data);
            } catch {
                // Non-fatal — engine may not have run yet
            }
        };

        fetchClassification();
        fetchWieSummary();
        const interval = setInterval(() => {
            fetchClassification();
            fetchWieSummary();
        }, 60000);
        return () => clearInterval(interval);
    }, [clusterId]);

    if (loading) {
        return (
            <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6 animate-pulse">
                <div className="h-6 bg-gray-200 rounded w-1/2 mb-4"></div>
                <div className="space-y-3">
                    <div className="h-4 bg-gray-200 rounded"></div>
                    <div className="h-4 bg-gray-200 rounded w-3/4"></div>
                </div>
            </div>
        );
    }

    if (!classification || classification.status === 'classification_unavailable') {
        return (
            <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
                <h3 className="text-lg font-semibold text-gray-900 mb-4 flex items-center">
                    <FiLayers className="mr-2 text-indigo-600" />
                    Workload Classification
                </h3>
                <p className="text-sm text-gray-500">Classification data unavailable - waiting for next scan</p>
            </div>
        );
    }

    // Count nodes by status
    const nodesByStatus = Object.entries(classification.nodes || {}).reduce((acc, [nodeName, status]) => {
        if (!acc[status]) acc[status] = [];
        acc[status].push(nodeName);
        return acc;
    }, {});

    const eligibleCount = classification.eligible_count || 0;
    const totalCount = classification.total_count || 0;
    const eligiblePct = totalCount > 0 ? (eligibleCount / totalCount) * 100 : 0;

    return (
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
            <div className="flex items-center justify-between mb-6">
                <h3 className="text-lg font-semibold text-gray-900 flex items-center">
                    <FiLayers className="mr-2 text-indigo-600" />
                    Workload Classification
                </h3>
                <span className="text-sm text-gray-500">{totalCount} nodes</span>
            </div>

            {/* Summary Stats */}
            <div className="grid grid-cols-2 gap-4 mb-6">
                <div className="p-4 bg-green-50 rounded-lg border border-green-200">
                    <div className="text-xs font-medium text-green-600 uppercase mb-1">Eligible for Optimization</div>
                    <div className="text-3xl font-bold text-green-900">{eligibleCount}</div>
                    <div className="text-xs text-green-600 mt-1">{eligiblePct.toFixed(0)}% of cluster</div>
                </div>

                <div className="p-4 bg-orange-50 rounded-lg border border-orange-200">
                    <div className="text-xs font-medium text-orange-600 uppercase mb-1">Protected Nodes</div>
                    <div className="text-3xl font-bold text-orange-900">{totalCount - eligibleCount}</div>
                    <div className="text-xs text-orange-600 mt-1">{(100 - eligiblePct).toFixed(0)}% of cluster</div>
                </div>
            </div>

            {/* Status Breakdown */}
            <div className="space-y-3 mb-4">
                {Object.entries(NODE_STATUS_CONFIG).map(([status, config]) => {
                    const nodes = nodesByStatus[status] || [];
                    const count = nodes.length;
                    const Icon = config.icon;

                    if (count === 0) return null;

                    return (
                        <div key={status} className={`p-3 bg-${config.color}-50 border border-${config.color}-200 rounded-lg`}>
                            <div className="flex items-center justify-between">
                                <div className="flex items-center">
                                    <Icon className={`mr-2 text-${config.color}-600`} />
                                    <div>
                                        <div className={`text-sm font-semibold text-${config.color}-900`}>{config.label}</div>
                                        <div className={`text-xs text-${config.color}-600`}>{config.description}</div>
                                    </div>
                                </div>
                                <span className={`text-lg font-bold text-${config.color}-900`}>{count}</span>
                            </div>
                        </div>
                    );
                })}
            </div>

            {/* Node List Toggle */}
            {totalCount > 0 && (
                <div>
                    <button
                        onClick={() => setExpandedNodes(!expandedNodes)}
                        className="text-sm text-indigo-600 hover:text-indigo-700 font-medium"
                    >
                        {expandedNodes ? 'Hide' : 'Show'} node details
                    </button>

                    {expandedNodes && (
                        <div className="mt-4 pt-4 border-t border-gray-200 max-h-96 overflow-y-auto">
                            {Object.entries(classification.nodes || {}).map(([nodeName, status]) => {
                                const config = NODE_STATUS_CONFIG[status];
                                if (!config) return null;

                                const Icon = config.icon;
                                return (
                                    <div key={nodeName} className="flex items-center justify-between py-2 text-sm border-b border-gray-100 last:border-0">
                                        <span className="font-mono text-gray-700">{nodeName}</span>
                                        <div className={`flex items-center text-${config.color}-700 bg-${config.color}-100 px-2 py-1 rounded text-xs`}>
                                            <Icon className="mr-1" size={14} />
                                            {config.label}
                                        </div>
                                    </div>
                                );
                            })}
                        </div>
                    )}
                </div>
            )}

            {eligibleCount === 0 && (
                <div className="mt-4 p-3 bg-red-50 border border-red-200 rounded-lg">
                    <p className="text-sm text-red-800">
                        <strong>Warning:</strong> No eligible nodes for optimization. All nodes are protected by stateful workloads or system constraints.
                    </p>
                </div>
            )}

            {/* Workload Intelligence v4.3 Section */}
            {wieSummary && (
                <div className="mt-4 border-t border-gray-200 pt-4">
                    <div className="flex items-center justify-between mb-3">
                        <h4 className="text-sm font-semibold text-gray-700">
                            Workload Intelligence <span className="text-xs text-gray-400 font-normal ml-1">v4.3</span>
                        </h4>
                        <button
                            onClick={() => navigate('/right-sizing?tab=workload')}
                            className="text-xs text-indigo-600 hover:text-indigo-700 font-medium flex items-center gap-1"
                        >
                            View Full Classification
                            <FiExternalLink size={11} />
                        </button>
                    </div>

                    {/* Tier mini-badges */}
                    <div className="flex gap-2 flex-wrap mb-3">
                        {['Platinum', 'Gold', 'Silver', 'Bronze'].map(tier => {
                            const c = TIER_COLORS[tier];
                            const count = wieSummary.tier_distribution?.[tier] || 0;
                            return (
                                <div key={tier} style={{
                                    padding: '4px 10px',
                                    background: c.bg,
                                    border: `1px solid ${c.border}`,
                                    borderRadius: 99,
                                    display: 'flex',
                                    alignItems: 'center',
                                    gap: 5,
                                }}>
                                    <span style={{ fontSize: 11, fontWeight: 700, color: c.text }}>{count}</span>
                                    <span style={{ fontSize: 10, color: c.text }}>{tier}</span>
                                </div>
                            );
                        })}
                    </div>

                    {/* Confidence distribution bar */}
                    {(() => {
                        const total = wieSummary.total_workloads || 1;
                        const confDist = wieSummary.confidence_distribution || {};
                        return (
                            <div>
                                <div className="text-xs text-gray-500 mb-1">Confidence</div>
                                <div className="flex rounded overflow-hidden h-2 bg-gray-100">
                                    {['CONFIRMED', 'PROVISIONAL', 'DRAFT'].map(state => {
                                        const count = confDist[state] || 0;
                                        const pct = Math.round((count / total) * 100);
                                        const c = CONFIDENCE_COLORS[state];
                                        return pct > 0 ? (
                                            <div
                                                key={state}
                                                style={{ width: `${pct}%`, background: c.color }}
                                                title={`${state}: ${count} (${pct}%)`}
                                            />
                                        ) : null;
                                    })}
                                </div>
                                <div className="flex gap-3 mt-1">
                                    {['CONFIRMED', 'PROVISIONAL', 'DRAFT'].map(state => {
                                        const count = confDist[state] || 0;
                                        if (!count) return null;
                                        const c = CONFIDENCE_COLORS[state];
                                        return (
                                            <span key={state} style={{ fontSize: 10, color: c.color, fontWeight: 600 }}>
                                                {state}: {count}
                                            </span>
                                        );
                                    })}
                                </div>
                            </div>
                        );
                    })()}
                </div>
            )}
        </div>
    );
};

export default WorkloadClassificationPanel;
