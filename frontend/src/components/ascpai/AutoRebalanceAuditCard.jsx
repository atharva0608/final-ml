import React, { useEffect, useState } from 'react';
import { Card } from '../shared';
import { FiSliders, FiCheckCircle, FiAlertTriangle, FiArrowUpRight, FiActivity, FiInbox, FiShield, FiClock, FiThumbsUp, FiThumbsDown, FiZap } from 'react-icons/fi';
import api, { clusterAPI, adminAPI, ascpaiAPI } from '../../services/api';
import AutoRebalanceAuditModal from './AutoRebalanceAuditModal';

const AutoRebalanceAuditCard = ({ clusterId, initialEnabled = false, karpenterMode = null }) => {
    // karpenterMode: null = not installed, 'dry_run' = observe only, 'auto' = full manage
    const isKarpenterActive = karpenterMode != null;
    const [decisions, setDecisions] = useState([]);
    const [loading, setLoading] = useState(true);
    const [isEnabled, setIsEnabled] = useState(initialEnabled);
    const [toggling, setToggling] = useState(false);
    const [cbState, setCbState] = useState(null);
    const [approving, setApproving] = useState(null); // action id being approved/denied
    const [isAuditModalOpen, setIsAuditModalOpen] = useState(false);

    useEffect(() => {
        fetchAuditLog();
        // Fetch current cluster state
        if (clusterId) {
            fetchClusterState();
            fetchCbState();
        }
    }, [clusterId]);

    const fetchClusterState = async () => {
        try {
            const response = await clusterAPI.getCluster(clusterId);
            if (response.data) {
                setIsEnabled(response.data.auto_rebalance_enabled || false);
            }
        } catch (error) {
            console.error("Failed to fetch cluster state:", error);
        }
    };

    const fetchCbState = async () => {
        try {
            const res = await adminAPI.getCircuitBreakers();
            const breakers = res.data?.circuit_breakers || [];
            const match = breakers.find(b => b.cluster_id === clusterId);
            if (match) setCbState(match.state);
        } catch (_) {
            // Circuit breaker data unavailable
        }
    };

    const fetchAuditLog = async () => {
        try {
            const params = clusterId
                ? `/api/v1/ascpai/rebalancing/status?limit=5&cluster_id=${clusterId}`
                : '/api/v1/ascpai/rebalancing/status?limit=5';
            const response = await api.get(params);
            if (response.data && Array.isArray(response.data)) {
                setDecisions(response.data);
            } else {
                setDecisions([]);
            }
        } catch (error) {
            console.error("Failed to fetch audit log:", error);
            setDecisions([]);
        } finally {
            setLoading(false);
        }
    };

    const handleToggle = async () => {
        if (!clusterId || toggling) return;

        setToggling(true);
        const newState = !isEnabled;

        try {
            await clusterAPI.toggleAutoRebalance(clusterId, newState);
            setIsEnabled(newState);
            console.log(`Auto-rebalance ${newState ? 'enabled' : 'disabled'} for cluster ${clusterId}`);
        } catch (error) {
            console.error("Failed to toggle auto-rebalance:", error);
            // Show error notification (you can add toast here)
            alert(`Failed to ${newState ? 'enable' : 'disable'} auto-rebalance: ${error.message}`);
        } finally {
            setToggling(false);
        }
    };

    const getReasonText = (action) => {
        const isKarpenterAction = action.provisioner_type === 'karpenter' || isKarpenterActive;
        if (action.trigger === 'emergency') {
            return isKarpenterAction
                ? 'Interruption notice — Karpenter reprovisioning spot node'
                : 'Termination notice received — emergency rebalancing';
        }
        return isKarpenterAction
            ? 'Karpenter-managed node consolidation — CORDON → DRAIN → TERMINATE'
            : 'Proactive optimization to safer pool';
    };

    const isKarpenterProvisioned = (action) =>
        action.provisioner_type === 'karpenter' || isKarpenterActive;

    const handleApprove = async (actionId) => {
        setApproving(actionId);
        try {
            await ascpaiAPI.approveRebalancingAction(actionId);
            await fetchAuditLog();
        } catch (e) {
            alert('Failed to approve: ' + (e.response?.data?.detail || e.message));
        } finally {
            setApproving(null);
        }
    };

    const handleDeny = async (actionId) => {
        setApproving(actionId);
        try {
            await ascpaiAPI.denyRebalancingAction(actionId);
            await fetchAuditLog();
        } catch (e) {
            alert('Failed to deny: ' + (e.response?.data?.detail || e.message));
        } finally {
            setApproving(null);
        }
    };

    const getStatusBadge = (status) => {
        switch (status) {
            case 'completed':
                return (
                    <span className="px-1.5 py-0.5 bg-green-50 text-green-600 text-[10px] rounded border border-green-100 flex items-center gap-1">
                        <FiCheckCircle className="w-2 h-2" /> Completed
                    </span>
                );
            case 'failed':
                return (
                    <span className="px-1.5 py-0.5 bg-red-50 text-red-600 text-[10px] rounded border border-red-100 flex items-center gap-1">
                        <FiAlertTriangle className="w-2 h-2" /> Failed
                    </span>
                );
            case 'in_progress':
                return (
                    <span className="px-1.5 py-0.5 bg-blue-50 text-blue-600 text-[10px] rounded border border-blue-100 flex items-center gap-1">
                        <FiActivity className="w-2 h-2 animate-pulse" /> In Progress
                    </span>
                );
            case 'pending_approval':
                return (
                    <span className="px-1.5 py-0.5 bg-amber-50 text-amber-700 text-[10px] rounded border border-amber-200 flex items-center gap-1">
                        <FiClock className="w-2 h-2" /> Awaiting Approval
                    </span>
                );
            case 'deferred':
                return (
                    <span className="px-1.5 py-0.5 bg-gray-50 text-gray-500 text-[10px] rounded border border-gray-200 flex items-center gap-1">
                        <FiClock className="w-2 h-2" /> Deferred
                    </span>
                );
            case 'waiting_agent':
                return (
                    <span className="px-1.5 py-0.5 bg-purple-50 text-purple-600 text-[10px] rounded border border-purple-200 flex items-center gap-1">
                        <FiActivity className="w-2 h-2 animate-pulse" /> Waiting
                    </span>
                );
            default:
                return null;
        }
    };

    const getTriggerBadge = (trigger) => {
        if (trigger === 'emergency') {
            return (
                <span className="px-1.5 py-0.5 bg-red-50 text-red-700 text-[10px] rounded border border-red-200 flex items-center gap-1">
                    <FiAlertTriangle className="w-2 h-2" /> Emergency
                </span>
            );
        }
        return (
            <span className="px-1.5 py-0.5 bg-blue-50 text-blue-600 text-[10px] rounded border border-blue-100 flex items-center gap-1">
                <FiSliders className="w-2 h-2" /> Graceful
            </span>
        );
    };

    const timeAgo = (isoString) => {
        if (!isoString) return '';
        const seconds = Math.floor((new Date() - new Date(isoString)) / 1000);
        if (seconds < 60) return `${seconds}s ago`;
        if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
        if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
        return `${Math.floor(seconds / 86400)}d ago`;
    };

    if (loading) return <div className="h-40 bg-gray-50 rounded animate-pulse"></div>;

    return (
        <Card className="flex flex-col h-full bg-gradient-to-br from-white to-gray-50">
            <div className="flex items-center justify-between mb-1">
                <div className="flex items-center gap-2">
                    <div className={`w-2 h-2 rounded-full ${isEnabled ? (isKarpenterActive ? 'bg-indigo-500 animate-pulse' : 'bg-green-500 animate-pulse') : 'bg-gray-300'}`}></div>
                    <h3 className="font-semibold text-gray-800">
                        {isKarpenterActive ? 'Karpenter Managed Actions' : 'Auto-Rebalancer History'}
                    </h3>
                    {isKarpenterActive && (
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 text-[10px] font-semibold rounded-full bg-indigo-100 text-indigo-700">
                            <FiZap className="w-2.5 h-2.5" />
                            {karpenterMode === 'auto' ? 'AUTO' : 'DRY RUN'}
                        </span>
                    )}
                    {cbState && (
                        <span className={`inline-flex items-center gap-1 px-2 py-0.5 text-[10px] font-semibold rounded-full ${cbState === 'NORMAL' ? 'bg-green-100 text-green-700' :
                                cbState === 'CONSERVATIVE' ? 'bg-yellow-100 text-yellow-700' :
                                    'bg-red-100 text-red-700'
                            }`}>
                            <FiShield className="w-2.5 h-2.5" />
                            CB: {cbState}
                        </span>
                    )}
                </div>
            </div>
            {isKarpenterActive && (
                <p className="text-[10px] text-indigo-500 mb-3 ml-4">
                    Karpenter handles spot provisioning · rebalancer manages CORDON/DRAIN lifecycle
                </p>
            )}

            <div className="space-y-3 flex-1">
                {decisions.length === 0 ? (
                    <div className="flex flex-col items-center justify-center py-8 text-gray-400">
                        <FiInbox className="w-8 h-8 mb-2 text-gray-300" />
                        <p className="text-sm font-medium">
                            {isKarpenterActive ? 'No Karpenter actions yet' : 'No rebalancing events yet'}
                        </p>
                        <p className="text-xs mt-1">
                            {isKarpenterActive
                                ? 'Actions appear here when Karpenter triggers node consolidation'
                                : 'Events will appear here when auto-rebalancing triggers'}
                        </p>
                    </div>
                ) : (
                    decisions.map((action, idx) => (
                        <div key={action.id || idx} className={`bg-white p-3 rounded-lg border shadow-sm hover:shadow-md transition-shadow ${action.status === 'failed' ? 'border-red-200' : 'border-gray-100'}`}>
                            <div className="flex justify-between items-start mb-1">
                                <span className="text-xs font-bold text-gray-700 font-mono flex items-center gap-1 flex-wrap">
                                    {/* Source → Target display */}
                                    {action.source_pool && (
                                        <span className="text-gray-400">{action.source_pool.split(':')[0]}</span>
                                    )}
                                    {action.source_pool && <span className="text-gray-300">→</span>}
                                    {action.original_target_pool ? (
                                        <>
                                            <span className="line-through text-gray-400">{action.original_target_pool.split(':')[0]}</span>
                                            <span className="text-gray-300">→</span>
                                            <span>{action.target_pool ? action.target_pool.split(':')[0] : 'Unknown'}</span>
                                        </>
                                    ) : (
                                        action.target_pool ? action.target_pool.split(':')[0] : 'Unknown'
                                    )}
                                </span>
                                <span className="text-[10px] text-gray-400 ml-2 shrink-0">
                                    {timeAgo(action.started_at)}
                                </span>
                            </div>

                            <p className="text-xs text-gray-600 leading-snug mb-2">
                                {getReasonText(action)}
                            </p>

                            <div className="flex items-center justify-between">
                                <div className="flex items-center gap-1.5">
                                    {getTriggerBadge(action.trigger)}
                                    {getStatusBadge(action.status)}
                                    {isKarpenterProvisioned(action) && (
                                        <span className="px-1.5 py-0.5 bg-indigo-50 text-indigo-700 text-[10px] rounded border border-indigo-200 flex items-center gap-1">
                                            <FiZap className="w-2 h-2" /> Karpenter
                                        </span>
                                    )}
                                </div>

                                {action.nodes_affected > 0 && (
                                    <span className="text-[10px] font-medium text-gray-500">
                                        {action.nodes_affected} node{action.nodes_affected !== 1 ? 's' : ''}
                                    </span>
                                )}
                            </div>

                            {action.status === 'failed' && action.error_message && (
                                <div className="mt-2 p-2 bg-red-50 border border-red-100 rounded text-[10px] text-red-600 font-mono break-words">
                                    {action.error_message}
                                </div>
                            )}
                            {action.status === 'deferred' && action.error_message && (
                                <div className="mt-2 p-2 bg-amber-50 border border-amber-100 rounded text-[10px] text-amber-700 font-mono break-words">
                                    {action.error_message}
                                </div>
                            )}
                            {action.pool_change_reason && (
                                <div className="mt-2 p-2 bg-blue-50 border border-blue-100 rounded text-[10px] text-blue-700 font-mono break-words">
                                    Pool changed: {action.pool_change_reason}
                                </div>
                            )}

                            {action.status === 'pending_approval' && (
                                <div className="flex items-center gap-2 mt-2 pt-2 border-t border-amber-100">
                                    <span className="text-[10px] text-amber-700 flex-1">
                                        {action.source_pool} → {action.target_pool?.split(':')[0]}
                                    </span>
                                    <button
                                        onClick={() => handleApprove(action.id)}
                                        disabled={approving === action.id}
                                        className="flex items-center gap-1 px-2 py-1 text-[10px] font-semibold bg-green-600 text-white rounded hover:bg-green-700 disabled:opacity-50"
                                    >
                                        <FiThumbsUp className="w-2.5 h-2.5" /> Approve
                                    </button>
                                    <button
                                        onClick={() => handleDeny(action.id)}
                                        disabled={approving === action.id}
                                        className="flex items-center gap-1 px-2 py-1 text-[10px] font-semibold bg-red-100 text-red-700 rounded hover:bg-red-200 disabled:opacity-50"
                                    >
                                        <FiThumbsDown className="w-2.5 h-2.5" /> Deny
                                    </button>
                                </div>
                            )}
                        </div>
                    ))
                )}
            </div>

            <div className="mt-3 pt-2 border-t border-gray-200 text-center">
                <button 
                    onClick={() => setIsAuditModalOpen(true)}
                    className="text-xs text-blue-600 hover:text-blue-800 font-medium flex items-center justify-center gap-1 mx-auto"
                >
                    View Full Audit Log <FiArrowUpRight />
                </button>
            </div>
            
            {/* Full Audit Log Modal */}
            <AutoRebalanceAuditModal 
                isOpen={isAuditModalOpen} 
                onClose={() => setIsAuditModalOpen(false)} 
                clusterId={clusterId}
            />
        </Card>
    );
};

export default AutoRebalanceAuditCard;
