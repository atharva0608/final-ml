import React, { useEffect, useState } from 'react';
import { Card } from '../shared';
import { atharvaaiAPI } from '../../services/api';

// Theme primitives to match the original layout
const T = {
    bg: "#f8f9fb",
    surface: "#ffffff",
    border: "#e5e7eb",
    borderLight: "#f3f4f6",
    text: "#111827",
    textMid: "#374151",
    textMuted: "#6b7280",
    textFaint: "#9ca3af",
    primary: "#4f46e5",
    primaryLight: "#eef2ff",
    green: "#059669",
    greenLight: "#ecfdf5",
    greenBorder: "#bbf7d0",
    amber: "#d97706",
    amberLight: "#fffbeb",
    amberBorder: "#fde68a",
    red: "#dc2626",
    redLight: "#fef2f2",
    cyan: "#0891b2",
    cyanLight: "#ecfeff",
    greyLight: "#f9fafb",
    greyBorder: "#d1d5db",
    greyDark: "#4b5563",
    shadow: "0 1px 3px rgba(0,0,0,.06), 0 1px 2px rgba(0,0,0,.04)",
};

const REBALANCE_STEPS = [
    { key: 'step_1_spot_provisioning', label: 'New Pool Provisioned', desc: 'Karpenter NodePool updated with ML-ranked spot pools' },
    { key: 'step_2_cordon', label: 'Node Cordoned', desc: 'No new pods scheduled on the source node' },
    { key: 'step_3_draining_pods', label: 'Pods Draining', desc: 'Existing pods gracefully evicted to other nodes' },
    { key: 'step_4_new_node_joined', label: 'New Node Joined', desc: 'Replacement spot node provisioned and joined the cluster' },
    { key: 'step_5_old_node_terminated', label: 'Old Node Terminated', desc: 'Source EC2 instance terminated' },
    { key: 'step_6_optimization_complete', label: 'Complete', desc: 'Node migration finished' },
];

const STEP_CURRENT_MAP = {
    provisioning_spot_pool: 0,
    cordoning_node: 1,
    draining_pods: 2,
    waiting_for_spot_node: 3,
    old_node_terminating: 4,
    old_node_terminating_timeout: 4,
    optimization_complete: 5,
};

const formatRemainingTime = (seconds) => {
    if (!seconds || seconds <= 0) return '0m';
    const hrs = Math.floor(seconds / 3600);
    const mins = Math.floor((seconds % 3600) / 60);
    if (hrs > 0) return `${hrs}h ${mins}m`;
    return `${mins}m`;
};

const RebalancingTimeline = ({ clusterId, actions: externalActions }) => {
    const [actions, setActions] = useState(externalActions || []);
    const [cooldownData, setCooldownData] = useState(null);
    const [nextNodeData, setNextNodeData] = useState(null);
    const [loading, setLoading] = useState(!externalActions);

    // Fetch data if no external actions are provided (when rendered directly on dashboard)
    useEffect(() => {
        if (!clusterId && !externalActions) return;

        const fetchData = async () => {
            try {
                if (!externalActions && clusterId) {
                    const statusRes = await atharvaaiAPI.getRebalancingStatus(clusterId, 5);
                    setActions(Array.isArray(statusRes.data) ? statusRes.data : []);
                }

                if (clusterId) {
                    // Fetch unified rebalancing context (cooldown + next target)
                    const ctxRes = await atharvaaiAPI.getRebalancingContext(clusterId).catch(() => ({ data: null }));
                    if (ctxRes.data) {
                        setCooldownData(ctxRes.data.cooldown?.active ? ctxRes.data.cooldown : null);
                        setNextNodeData(ctxRes.data.next_target || null);
                    }
                }
            } catch (err) {
                console.error("Failed to fetch rebalancing context:", err);
            } finally {
                setLoading(false);
            }
        };

        fetchData();
        const intervalId = setInterval(fetchData, 15000);
        return () => clearInterval(intervalId);
    }, [clusterId, externalActions]);

    // Use latest available actions (internal state or props)
    const displayActions = externalActions || actions;

    // Filter to active or recent migrations
    const now = Date.now();
    const visible = (displayActions || []).filter(a => {
        if (['in_progress', 'waiting_agent'].includes(a.status)) return true;
        if (a.status === 'completed' && a.completed_at) {
            return (now - new Date(a.completed_at).getTime()) < 3600_000;
        }
        return false;
    });

    if (loading && !displayActions.length) {
        return <div className="text-center py-4 text-gray-500">Loading timeline data...</div>;
    }

    return (
        <div style={{ marginBottom: 24 }}>
            {/* Real-time Status Metadata Bar */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
                {/* Next Node Target */}
                <div style={{ background: T.surface, border: `1px solid ${T.border}`, borderRadius: 8, padding: '12px 16px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', boxShadow: T.shadow }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                        <div style={{ background: T.primaryLight, color: T.primary, width: 32, height: 32, borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 16 }}>🎯</div>
                        <div>
                            <div style={{ fontSize: 11, fontWeight: 700, color: T.textFaint, textTransform: 'uppercase', letterSpacing: '0.05em' }}>Next Target</div>
                            <div style={{ fontSize: 14, fontWeight: 600, color: T.text }}>
                                {nextNodeData ? nextNodeData.node : 'Fleet Optimized'}
                            </div>
                        </div>
                    </div>
                    {nextNodeData && (
                        <div style={{ textAlign: 'right' }}>
                            <div style={{ fontSize: 13, fontWeight: 600, color: T.green }}>${nextNodeData.monthly_savings}/mo</div>
                            <div style={{ fontSize: 11, color: T.textMuted }}>Est. Savings</div>
                        </div>
                    )}
                </div>

                {/* Cooldown Timer */}
                <div style={{ background: T.surface, border: `1px solid ${T.border}`, borderRadius: 8, padding: '12px 16px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', boxShadow: T.shadow }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                        <div style={{ background: cooldownData && cooldownData.active ? T.amberLight : T.greenLight, color: cooldownData && cooldownData.active ? T.amber : T.green, width: 32, height: 32, borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 16 }}>
                            {cooldownData && cooldownData.active ? '⏳' : '✅'}
                        </div>
                        <div>
                            <div style={{ fontSize: 11, fontWeight: 700, color: T.textFaint, textTransform: 'uppercase', letterSpacing: '0.05em' }}>Stabilization</div>
                            <div style={{ fontSize: 14, fontWeight: 600, color: T.text }}>
                                {cooldownData && cooldownData.active ? 'Cooldown Active' : 'Ready'}
                            </div>
                        </div>
                    </div>
                    {cooldownData && cooldownData.active && (
                        <div style={{ textAlign: 'right' }}>
                            <div style={{ fontSize: 14, fontWeight: 700, color: T.amber }}>{formatRemainingTime(cooldownData.remaining_seconds)}</div>
                            <div style={{ fontSize: 11, color: T.textMuted }}>Remaining</div>
                        </div>
                    )}
                </div>
            </div>

            <div style={{ fontSize: 13, fontWeight: 700, color: T.text, marginBottom: 12, display: 'flex', alignItems: 'center', gap: 8 }}>
                {visible.length > 0 ? (
                    <span style={{ width: 8, height: 8, borderRadius: '50%', background: '#f59e0b', display: 'inline-block', animation: 'pulse 1.5s infinite' }} />
                ) : (
                    <span style={{ width: 8, height: 8, borderRadius: '50%', background: T.border, display: 'inline-block' }} />
                )}
                Active Node Migrations
                <span style={{ fontSize: 11, fontWeight: 500, color: T.textMuted }}>
                    ({visible.length} migration{visible.length !== 1 ? 's' : ''})
                </span>
            </div>

            <style>{`@keyframes pulse { 0%,100%{opacity:1} 50%{opacity:.4} }`}</style>

            {visible.length === 0 ? (
                <div style={{ background: T.surface, border: `1px dashed ${T.border}`, borderRadius: 10, padding: '32px 20px', textAlign: 'center', boxShadow: 'none' }}>
                    <div style={{ fontSize: 24, marginBottom: 8 }}>💤</div>
                    <div style={{ fontSize: 14, fontWeight: 600, color: T.textMid }}>No Active Migrations</div>
                    <div style={{ fontSize: 13, color: T.textMuted, marginTop: 4 }}>The cluster is currently stable and no nodes are being replaced.</div>
                </div>
            ) : (
                visible.map((action, ai) => {
                    const currentStepIdx = STEP_CURRENT_MAP[action.current_step] ?? -1;
                    const meta = action.action_metadata || {};
                    const isS2S = meta.spot_to_spot === true;
                    const s2sReason = meta.reason || null;
                    const isDiversify = s2sReason && s2sReason.startsWith('diversify');
                    const borderColor = isS2S ? '#f59e0b' : T.border;

                    return (
                    <div key={ai} style={{ background: T.surface, border: `1px solid ${borderColor}`, borderRadius: 10, padding: '16px 20px', marginBottom: 12, boxShadow: T.shadow }}>
                            {/* Header */}
                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 16 }}>
                                <div style={{ flex: 1, minWidth: 0 }}>
                                    {/* Migration type badge */}
                                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                                        {isS2S ? (
                                            <span style={{
                                                fontSize: 10, fontWeight: 700, padding: '2px 8px', borderRadius: 10,
                                                background: '#fef3c7', color: '#d97706', letterSpacing: '0.05em',
                                            }}>
                                                {isDiversify ? '🔀 SPOT→SPOT (Diversify)' : '⚡ SPOT→SPOT (Risk)'}
                                            </span>
                                        ) : (
                                            <span style={{
                                                fontSize: 10, fontWeight: 700, padding: '2px 8px', borderRadius: 10,
                                                background: T.primaryLight, color: T.primary, letterSpacing: '0.05em',
                                            }}>
                                                ↑ OD→SPOT
                                            </span>
                                        )}
                                    </div>
                                    <div style={{ fontSize: 13, fontWeight: 700, color: T.text }}>
                                        {action.source_pool} → {action.target_pool}
                                    </div>
                                    <div style={{ fontSize: 11, color: T.textMuted, marginTop: 2 }}>
                                        {(meta.instance_id || action.instance_id) && (
                                            <span style={{ fontFamily: 'monospace', background: T.bg, padding: '1px 6px', borderRadius: 3, marginRight: 8 }}>
                                                {meta.instance_id || action.instance_id}
                                            </span>
                                        )}
                                        Started {action.started_at ? new Date(action.started_at).toLocaleTimeString() : '—'}
                                    </div>
                                    {/* S2S reason line */}
                                    {isS2S && s2sReason && (
                                        <div style={{ fontSize: 11, color: '#92400e', marginTop: 4, padding: '3px 8px', background: '#fef3c7', borderRadius: 4, display: 'inline-block', maxWidth: '100%', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}
                                            title={s2sReason}>
                                            {s2sReason}
                                        </div>
                                    )}
                                </div>
                                <span style={{
                                    fontSize: 11, fontWeight: 600, padding: '3px 10px', borderRadius: 12, flexShrink: 0, marginLeft: 8,
                                    background: action.status === 'completed' ? T.greenLight : action.status === 'failed' ? T.redLight : T.amberLight,
                                    color: action.status === 'completed' ? T.green : action.status === 'failed' ? T.red : T.amber,
                                }}>
                                    {action.status === 'waiting_agent' || action.status === 'in_progress' ? 'In Progress' : action.status.toUpperCase()}
                                </span>
                            </div>

                            {/* Step Timeline */}
                            <div style={{ display: 'flex', alignItems: 'flex-start', gap: 0, overflowX: 'auto', paddingBottom: 8 }}>
                                {REBALANCE_STEPS.map((step, si) => {
                                    const done = Boolean(action[step.key]);
                                    const active = !done && si === currentStepIdx;
                                    const pending = !done && !active;

                                    const dotColor = done ? T.green : active ? T.amber : T.greyBorder;
                                    const labelColor = done ? T.green : active ? T.amber : T.textFaint;

                                    return (
                                        <div key={step.key} style={{ flex: 1, minWidth: 80, display: 'flex', flexDirection: 'column', alignItems: 'center', position: 'relative' }}>
                                            {/* Connector line (not for last step) */}
                                            {si < REBALANCE_STEPS.length - 1 && (
                                                <div style={{
                                                    position: 'absolute', top: 8, left: '50%', width: '100%', height: 2,
                                                    background: done ? T.green : T.greyBorder, zIndex: 0
                                                }} />
                                            )}
                                            {/* Dot */}
                                            <div style={{
                                                width: 18, height: 18, borderRadius: '50%',
                                                background: done ? T.green : active ? T.amber : T.surface,
                                                border: `2px solid ${dotColor}`,
                                                display: 'flex', alignItems: 'center', justifyContent: 'center',
                                                zIndex: 1, position: 'relative',
                                                animation: active ? 'pulse 1.5s infinite' : 'none',
                                            }}>
                                                {done && <span style={{ color: '#fff', fontSize: 10, fontWeight: 900 }}>✓</span>}
                                            </div>
                                            {/* Label */}
                                            <div style={{ fontSize: 10, fontWeight: 600, color: labelColor, textAlign: 'center', marginTop: 6, lineHeight: 1.3, maxWidth: 80 }}>
                                                {step.label}
                                            </div>
                                            {/* Timestamp if done */}
                                            {done && action[step.key] && (
                                                <div style={{ fontSize: 9, color: T.textFaint, textAlign: 'center', marginTop: 2 }}>
                                                    {new Date(action[step.key]).toLocaleTimeString()}
                                                </div>
                                            )}
                                            {active && (
                                                <div style={{ fontSize: 9, color: T.amber, textAlign: 'center', marginTop: 2, fontWeight: 700 }}>
                                                    In progress...
                                                </div>
                                            )}
                                        </div>
                                    );
                                })}
                            </div>

                            {/* Waiting for spot node warning text */}
                            {action.current_step === 'waiting_for_spot_node' && (
                                <div style={{ marginTop: 12, padding: '8px 12px', background: T.amberLight, borderRadius: 6, fontSize: 12, color: T.amber, fontWeight: 500 }}>
                                    ⏳ Waiting for {action.provisioner_type === 'karpenter' ? 'Karpenter' : 'agent'} to provision a new spot node ({Math.round((action.spot_wait_elapsed_s || 0) / 60)} min elapsed, max 30 min)
                                </div>
                            )}
                    </div>
                    );
                })
            )}
        </div>
    );
};

export default RebalancingTimeline;
