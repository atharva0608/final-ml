import React, { useState, useEffect } from 'react';
import { FiX, FiCheckCircle, FiAlertTriangle, FiActivity, FiClock, FiServer, FiInfo, FiSliders } from 'react-icons/fi';
import { atharvaaiAPI } from '../../services/api';

const getStatusBadge = (status) => {
    switch (status) {
        case 'completed':
            return (
                <span className="px-2 py-1 bg-green-50 text-green-700 text-xs font-medium rounded-full border border-green-200 flex items-center gap-1 w-max">
                    <FiCheckCircle className="w-3 h-3" /> Completed
                </span>
            );
        case 'failed':
            return (
                <span className="px-2 py-1 bg-red-50 text-red-700 text-xs font-medium rounded-full border border-red-200 flex items-center gap-1 w-max">
                    <FiAlertTriangle className="w-3 h-3" /> Failed
                </span>
            );
        case 'in_progress':
            return (
                <span className="px-2 py-1 bg-blue-50 text-blue-700 text-xs font-medium rounded-full border border-blue-200 flex items-center gap-1 w-max">
                    <FiActivity className="w-3 h-3 animate-pulse" /> In Progress
                </span>
            );
        case 'pending_approval':
            return (
                <span className="px-2 py-1 bg-amber-50 text-amber-700 text-xs font-medium rounded-full border border-amber-200 flex items-center gap-1 w-max">
                    <FiClock className="w-3 h-3" /> Awaiting Approval
                </span>
            );
        case 'deferred':
            return (
                <span className="px-2 py-1 bg-gray-50 text-gray-600 text-xs font-medium rounded-full border border-gray-200 flex items-center gap-1 w-max">
                    <FiClock className="w-3 h-3" /> Deferred
                </span>
            );
        case 'waiting_agent':
            return (
                <span className="px-2 py-1 bg-purple-50 text-purple-700 text-xs font-medium rounded-full border border-purple-200 flex items-center gap-1 w-max">
                    <FiActivity className="w-3 h-3 animate-pulse" /> Waiting
                </span>
            );
        default:
            return (
                <span className="px-2 py-1 bg-gray-100 text-gray-700 text-xs font-medium rounded-full border border-gray-300 w-max">
                    {status}
                </span>
            );
    }
};

const getTriggerBadge = (trigger, manual_approval_required) => {
    const isManual = manual_approval_required;
    const triggerLabel = isManual ? "Manual Approval" :
        (trigger === 'emergency' ? "Emergency" : "Auto");
    
    // Always use consistent color schemes based on trigger type
    if (trigger === 'emergency') {
        return (
            <span className="px-2 py-1 bg-red-50 text-red-700 text-xs font-medium rounded border border-red-200 flex items-center gap-1 w-max">
                <FiAlertTriangle className="w-3 h-3" /> {triggerLabel}
            </span>
        );
    }
    return (
        <span className="px-2 py-1 bg-blue-50 text-blue-700 text-xs font-medium rounded border border-blue-100 flex items-center gap-1 w-max">
            <FiSliders className="w-3 h-3" /> {triggerLabel}
        </span>
    );
};

const getReasonText = (action) => {
    if (action.error_message && action.status === 'failed') {
        return `Execution Failed: ${action.error_message}`;
    }
    if (action.error_message && action.status === 'deferred') {
        return `Deferred — ${action.error_message}`;
    }
    if (action.pool_change_reason) {
        return `Pool change: ${action.pool_change_reason}`;
    }
    if (action.trigger === 'emergency') {
        return 'AWS Spot Interruption termination notice received — emergency capacity replacement triggered to maintain workloads.';
    }
    if (action.trigger === 'graceful' || action.trigger === 'auto_rebalance') {
        return 'Proactive optimization to a safer or more cost-efficient capacity pool, draining workloads before potential interruption.';
    }
    return `Rebalancing triggered by system: ${action.trigger || 'Auto'}`;
};

const formatDate = (isoString) => {
    if (!isoString) return '—';
    return new Intl.DateTimeFormat('en-US', {
        month: 'short', day: 'numeric',
        hour: '2-digit', minute: '2-digit', second: '2-digit',
        hour12: true
    }).format(new Date(isoString));
};

const AutoRebalanceAuditModal = ({ isOpen, onClose, clusterId }) => {
    const [actions, setActions] = useState([]);
    const [loading, setLoading] = useState(true);
    const [selectedActionId, setSelectedActionId] = useState(null);
    const [error, setError] = useState(null);

    useEffect(() => {
        if (isOpen) {
            fetchActions();
        } else {
            // Reset state when closed
            setActions([]);
            setSelectedActionId(null);
            setError(null);
        }
    }, [isOpen, clusterId]);

    const fetchActions = async () => {
        setLoading(true);
        setError(null);
        try {
            // Fetch up to 100 recent actions for the detailed log
            const response = await atharvaaiAPI.getRebalancingStatus(clusterId, 100);
            if (response.data && Array.isArray(response.data)) {
                setActions(response.data);
                if (response.data.length > 0) {
                    setSelectedActionId(response.data[0].id);
                }
            } else {
                setActions([]);
            }
        } catch (err) {
            console.error("Failed to fetch full audit log:", err);
            setError("Failed to load audit logs. Please try again.");
        } finally {
            setLoading(false);
        }
    };

    if (!isOpen) return null;

    const selectedAction = actions.find(a => a.id === selectedActionId);

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4">
            <div className="bg-white rounded-xl shadow-2xl w-full max-w-6xl h-[85vh] flex flex-col overflow-hidden ring-1 ring-black/5">
                
                {/* Header */}
                <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100 bg-gray-50/50">
                    <div>
                        <h2 className="text-xl font-bold text-gray-900 flex items-center gap-2">
                            <FiActivity className="text-indigo-600" />
                            Auto-Rebalancer Audit Log
                        </h2>
                        <p className="text-sm text-gray-500 mt-1">
                            Complete history and detailed execution traces of pool rebalancing actions.
                        </p>
                    </div>
                    <button 
                        onClick={onClose}
                        className="p-2 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-full transition-colors"
                    >
                        <FiX className="w-5 h-5" />
                    </button>
                </div>

                <div className="flex flex-1 overflow-hidden">
                    {/* Master List (Left Pane) */}
                    <div className="w-1/3 border-r border-gray-200 flex flex-col bg-gray-50/30 overflow-y-auto">
                        {loading ? (
                            <div className="flex items-center justify-center flex-1">
                                <span className="text-gray-400 text-sm animate-pulse">Loading execution history...</span>
                            </div>
                        ) : error ? (
                            <div className="p-6 text-center text-red-500">
                                <FiAlertTriangle className="w-8 h-8 mx-auto mb-2 opacity-50" />
                                <p className="text-sm">{error}</p>
                                <button onClick={fetchActions} className="mt-3 text-sm text-indigo-600 font-medium hover:underline">Retry</button>
                            </div>
                        ) : actions.length === 0 ? (
                            <div className="p-6 text-center text-gray-500 mt-10">
                                <FiInfo className="w-8 h-8 mx-auto mb-2 opacity-30" />
                                <p className="text-sm">No rebalancing history found for this cluster.</p>
                            </div>
                        ) : (
                            <div className="divide-y divide-gray-100">
                                {actions.map((action) => (
                                    <div
                                        key={action.id}
                                        role="button"
                                        tabIndex={0}
                                        onClick={() => setSelectedActionId(action.id)}
                                        onKeyDown={(e) => { if(e.key === 'Enter') setSelectedActionId(action.id); }}
                                        className={`w-full text-left p-4 cursor-pointer hover:bg-gray-100 transition-colors focus:outline-none border-b border-gray-100 ${
                                            selectedActionId === action.id 
                                                ? 'bg-white shadow-[inset_4px_0_0_0_#4f46e5] border-r-0 relative z-10' 
                                                : 'border-r border-r-gray-200'
                                        }`}
                                    >
                                        <div className="flex justify-between items-start mb-2">
                                            <span className="text-xs font-semibold text-gray-500">
                                                {formatDate(action.started_at)}
                                            </span>
                                        </div>
                                        <div className="font-mono text-sm text-gray-900 font-medium truncate mb-2">
                                            {action.source_pool ? action.source_pool.split(':')[0] : 'Unknown'} 
                                            <span className="text-gray-400 mx-1">→</span> 
                                            {action.target_pool ? action.target_pool.split(':')[0] : 'Unknown'}
                                        </div>
                                        <div className="flex flex-wrap items-center gap-2 mt-2">
                                            {getStatusBadge(action.status)}
                                            {action.trigger === 'emergency' && (
                                                <span className="px-1.5 py-0.5 bg-red-100 text-red-800 text-[10px] uppercase font-bold tracking-wider rounded">Emerg</span>
                                            )}
                                        </div>
                                    </div>
                                ))}
                            </div>
                        )}
                    </div>

                    {/* Detail View (Right Pane) */}
                    <div className="w-2/3 bg-white flex flex-col overflow-y-auto relative">
                        {loading && !selectedAction ? (
                            <div className="flex items-center justify-center flex-1">
                                <div className="w-8 h-8 rounded-full border-2 border-indigo-200 border-t-indigo-600 animate-spin"></div>
                            </div>
                        ) : selectedAction ? (
                            <div className="p-6 md:p-8 max-w-4xl mx-auto w-full">
                                <div className="flex items-center justify-between mb-8">
                                    <h3 className="text-2xl font-bold text-gray-900 leading-tight">
                                        Execution Details
                                    </h3>
                                    {getStatusBadge(selectedAction.status)}
                                </div>

                                <div className="grid grid-cols-1 md:grid-cols-2 gap-x-8 gap-y-6">
                                    
                                    {/* General Info */}
                                    <div className="space-y-4">
                                        <div>
                                            <label className="block text-xs font-semibold text-gray-400 uppercase tracking-widest mb-1">Action ID</label>
                                            <div className="font-mono text-sm text-gray-800 bg-gray-100 px-2 py-1 rounded inline-block">
                                                {selectedAction.id}
                                            </div>
                                        </div>
                                        
                                        <div>
                                            <label className="block text-xs font-semibold text-gray-400 uppercase tracking-widest mb-1">Cluster</label>
                                            <div className="flex items-center gap-2 text-sm text-gray-800 font-medium">
                                                <FiServer className="text-gray-400" />
                                                {selectedAction.cluster_id}
                                            </div>
                                        </div>

                                        <div>
                                            <label className="block text-xs font-semibold text-gray-400 uppercase tracking-widest mb-1">Trigger Mechanism</label>
                                            <div className="mt-1">
                                                {getTriggerBadge(selectedAction.trigger, selectedAction.manual_approval_required)}
                                            </div>
                                        </div>
                                        
                                        <div>
                                            <label className="block text-xs font-semibold text-gray-400 uppercase tracking-widest mb-1">Primary Reason</label>
                                            <div className="text-sm text-gray-700 bg-gray-50 border border-gray-100 p-3 rounded-lg leading-relaxed">
                                                {getReasonText(selectedAction)}
                                            </div>
                                        </div>
                                    </div>

                                    {/* Timeline & Metrics */}
                                    <div className="space-y-6">
                                        <div className="bg-slate-50 border border-slate-100 rounded-xl p-4">
                                            <h4 className="text-xs font-bold text-slate-800 uppercase tracking-wider mb-3">Timeline</h4>
                                            
                                            <div className="relative pl-4 space-y-4 border-l-2 border-indigo-100">
                                                <div className="relative">
                                                    <div className="absolute -left-[21px] top-1 w-2.5 h-2.5 bg-indigo-500 rounded-full border-2 border-white"></div>
                                                    <p className="text-xs font-semibold text-gray-500 uppercase">Commenced</p>
                                                    <p className="text-sm font-medium text-gray-900">{formatDate(selectedAction.started_at)}</p>
                                                </div>
                                                
                                                <div className="relative">
                                                    <div className={`absolute -left-[21px] top-1 w-2.5 h-2.5 rounded-full border-2 border-white ${selectedAction.completed_at ? (selectedAction.status === 'failed' ? 'bg-red-500' : 'bg-green-500') : 'bg-gray-300'}`}></div>
                                                    <p className="text-xs font-semibold text-gray-500 uppercase">Concluded</p>
                                                    <p className="text-sm font-medium text-gray-900">
                                                        {selectedAction.completed_at ? formatDate(selectedAction.completed_at) : 'Pending / Ongoing'}
                                                    </p>
                                                </div>
                                            </div>
                                        </div>

                                        <div className="grid grid-cols-2 gap-4">
                                            <div className="bg-white border text-center border-gray-200 rounded-lg p-3 shadow-sm">
                                                <div className="text-xl font-bold text-indigo-600">{selectedAction.nodes_affected > 0 ? selectedAction.nodes_affected : 'Auto'}</div>
                                                <div className="text-xs text-gray-500 font-medium mt-1">Nodes Migrated</div>
                                            </div>
                                            <div className="bg-white border text-center border-gray-200 rounded-lg p-3 shadow-sm">
                                                <div className="text-xl font-bold text-green-600">
                                                    {selectedAction.savings_score ? `+${(selectedAction.savings_score).toFixed(1)}%` : 'Processing'}
                                                </div>
                                                <div className="text-xs text-gray-500 font-medium mt-1">Est. Savings Gain</div>
                                            </div>
                                        </div>

                                    </div>
                                </div>

                                {/* Migration Diagram */}
                                <div className="mt-8 mb-6">
                                    <h4 className="text-sm font-bold text-gray-800 border-b border-gray-100 pb-2 mb-4">Capacity Transition</h4>
                                    
                                    <div className="flex flex-col md:flex-row items-center justify-between gap-4 bg-gray-50 rounded-xl p-6 border border-gray-100 shadow-inner">
                                        <div className="w-full md:w-2/5 bg-white border border-gray-200 rounded-lg p-4 text-center shadow-sm">
                                            <span className="block text-xs font-semibold text-gray-400 uppercase tracking-widest mb-2">Evacuating From</span>
                                            <span className="font-mono text-base font-bold text-red-600">
                                                {selectedAction.source_pool || 'N/A'}
                                            </span>
                                        </div>
                                        
                                        <div className="flex-shrink-0 text-gray-300 flex flex-col items-center">
                                            <span className="text-xs font-medium text-gray-400 mb-1">Migrating</span>
                                            <svg className="w-6 h-6 animate-pulse text-indigo-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14 5l7 7m0 0l-7 7m7-7H3" />
                                            </svg>
                                        </div>

                                        <div className="w-full md:w-2/5 bg-white border border-gray-200 rounded-lg p-4 text-center shadow-sm relative overflow-hidden">
                                            <div className="absolute inset-0 bg-green-50 opacity-20"></div>
                                            <span className="block relative text-xs font-semibold text-gray-400 uppercase tracking-widest mb-2">Targeting Safe Capacity</span>
                                            <span className="font-mono text-base font-bold text-green-600 relative">
                                                {selectedAction.target_pool || 'N/A'}
                                            </span>
                                        </div>
                                    </div>
                                </div>

                                {/* Execution Trace / Logs */}
                                <div className="mt-8">
                                    <div className="flex flex-col">
                                        <h4 className="text-sm font-bold text-gray-800 border-b border-gray-100 pb-2 mb-4">Execution Trace</h4>
                                    </div>
                                    
                                    <div className="bg-[#1e1e1e] rounded-xl font-mono text-xs overflow-hidden shadow-inner border border-gray-800 ring-1 ring-white/10">
                                        <div className="bg-[#2d2d2d] border-b border-black px-4 py-2 flex items-center justify-between">
                                            <div className="flex gap-2">
                                                <div className="w-3 h-3 rounded-full bg-red-500"></div>
                                                <div className="w-3 h-3 rounded-full bg-yellow-500"></div>
                                                <div className="w-3 h-3 rounded-full bg-green-500"></div>
                                            </div>
                                            <span className="text-gray-400 text-[10px] uppercase font-bold tracking-wider">system.log</span>
                                        </div>
                                        <div className="p-4 overflow-x-auto whitespace-pre-wrap leading-relaxed space-y-1">
                                            <div className="text-blue-400">[{formatDate(selectedAction.started_at)}] INFO: Initializing rebalance orchestration.</div>
                                            <div className="text-blue-400">[{formatDate(selectedAction.started_at)}] INFO: Trigger context: {selectedAction.trigger}</div>
                                            <div className="text-blue-400">[{formatDate(selectedAction.started_at)}] INFO: Current Step: {selectedAction.current_step || 'unknown'}</div>
                                            
                                            {selectedAction.step_1_spot_provisioning && (
                                                <div className="text-emerald-400">[{formatDate(selectedAction.started_at)}] SUCCESS: Step 1: Provisioning spot replacement instances via {selectedAction.provisioner_type || 'Karpenter'}</div>
                                            )}
                                            
                                            {selectedAction.step_2_cordon && (
                                                <div className="text-emerald-400">[{formatDate(selectedAction.started_at)}] SUCCESS: Step 2: Cordoning original vulnerable nodes</div>
                                            )}
                                            
                                            {selectedAction.step_3_draining_pods && (
                                                <div className="text-emerald-400">[{formatDate(selectedAction.started_at)}] SUCCESS: Step 3: Evicting pods and draining node</div>
                                            )}
                                            
                                            {selectedAction.step_4_new_node_joined && (
                                                <div className="text-emerald-400">[{formatDate(selectedAction.started_at)}] SUCCESS: Step 4: Acknowledged new replacement node cluster join</div>
                                            )}
                                            
                                            {selectedAction.step_5_old_node_terminated && (
                                                <div className="text-emerald-400">[{formatDate(selectedAction.started_at)}] SUCCESS: Step 5: Original node {selectedAction.instance_id || ''} gracefully terminated</div>
                                            )}
                                            
                                            {selectedAction.step_6_optimization_complete && (
                                                <div className="text-emerald-400">[{formatDate(selectedAction.completed_at)}] SUCCESS: Step 6: Full cycle optimization complete</div>
                                            )}
                                            
                                            {selectedAction.error_message ? (
                                                <>
                                                    <div className="text-red-400 mt-3 font-bold">[{formatDate(selectedAction.completed_at || selectedAction.started_at)}] ERROR: Execution Failed</div>
                                                    <div className="text-red-300 mt-1 pl-4 border-l-2 border-red-500">{selectedAction.error_message}</div>
                                                </>
                                            ) : selectedAction.status === 'completed' ? (
                                                <div className="text-green-400 mt-3 font-bold">[{formatDate(selectedAction.completed_at)}] SUCCESS: Capacity migrated cleanly.</div>
                                            ) : (
                                                <div className="text-yellow-400 mt-3 animate-pulse">[{formatDate(new Date().toISOString())}] RUNNING: Waiting for pod readiness and node termination...</div>
                                            )}
                                        </div>
                                    </div>
                                </div>

                            </div>
                        ) : (
                            <div className="flex-1 flex flex-col items-center justify-center text-gray-400 p-8">
                                <FiActivity className="w-16 h-16 mb-4 opacity-20" />
                                <p className="text-lg font-medium text-gray-600">Select an execution</p>
                                <p className="text-sm mt-2 text-center max-w-sm">
                                    Click on any action from the list on the left to view detailed execution traces and migration specifics.
                                </p>
                            </div>
                        )}
                    </div>
                </div>
            </div>
        </div>
    );
};

export default AutoRebalanceAuditModal;
