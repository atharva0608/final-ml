/**
 * AnchoredNodePanel.jsx — W3.5 Anchored node fill status panel.
 *
 * Displays fill percentage for each on-demand "anchored" node and highlights
 * nodes approaching the auto-nomination threshold (70% WARNING, 85% CRITICAL).
 */

import React, { useState, useEffect, useCallback } from 'react';
import { decisionEngineAPI } from '../../services/api';
import {
    FiAnchor, FiAlertTriangle, FiCheckCircle, FiRefreshCw,
} from 'react-icons/fi';

const FILL_WARN     = 70;
const FILL_CRITICAL = 85;

const FillBar = ({ pct, alertLevel }) => {
    const color = alertLevel === 'CRITICAL' ? '#ef4444'
        : alertLevel === 'WARNING'          ? '#f59e0b'
        : '#22c55e';
    return (
        <div style={barStyles.track}>
            <div style={{ ...barStyles.fill, width: `${Math.min(pct, 100)}%`, background: color }} />
        </div>
    );
};

const barStyles = {
    track: {
        width: '100%',
        height: 6,
        background: '#1e293b',
        borderRadius: 3,
        overflow: 'hidden',
    },
    fill: {
        height: '100%',
        borderRadius: 3,
        transition: 'width 0.4s ease',
    },
};

const AlertBadge = ({ level }) => {
    if (!level || level === 'OK') return null;
    const cfg = {
        WARNING:  { bg: '#78350f33', color: '#fbbf24', text: 'WARNING' },
        CRITICAL: { bg: '#7f1d1d33', color: '#f87171', text: 'CRITICAL' },
    }[level] || null;
    if (!cfg) return null;
    return (
        <span style={{
            background: cfg.bg, color: cfg.color,
            fontSize: 10, fontWeight: 700,
            padding: '2px 6px', borderRadius: 4,
            textTransform: 'uppercase', letterSpacing: '0.05em',
        }}>
            {cfg.text}
        </span>
    );
};

const AnchoredNodePanel = ({ clusterId }) => {
    const [nodes, setNodes]   = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError]   = useState(null);
    const [lastUpdated, setLastUpdated] = useState(null);

    const fetch = useCallback(async () => {
        if (!clusterId) return;
        try {
            // anchored-status endpoint returns fill info per anchored node
            const res = await decisionEngineAPI.getAnchoredStatus
                ? decisionEngineAPI.getAnchoredStatus(clusterId)
                : Promise.resolve({ data: { nodes: [] } });
            const data = (await res)?.data || await res.data;
            const nodeList = data?.nodes || data?.fill_status || [];
            // Normalise to array of { node_name, vcpu_fill_pct, mem_fill_pct, alert_level }
            const normalised = Array.isArray(nodeList)
                ? nodeList
                : Object.entries(nodeList).map(([node_name, v]) => ({
                    node_name,
                    vcpu_fill_pct: v.vcpu_fill_pct || 0,
                    mem_fill_pct:  v.mem_fill_pct  || 0,
                    alert_level:   v.alert_level   || 'OK',
                }));
            setNodes(normalised);
            setLastUpdated(new Date());
            setError(null);
        } catch (err) {
            setError('Failed to load anchored node status');
        } finally {
            setLoading(false);
        }
    }, [clusterId]);

    useEffect(() => {
        fetch();
        const poll = setInterval(fetch, 30000);
        return () => clearInterval(poll);
    }, [fetch]);

    return (
        <div style={styles.card}>
            <div style={styles.header}>
                <div style={styles.titleRow}>
                    <FiAnchor size={18} color="#60a5fa" />
                    <span style={styles.title}>Anchored Nodes</span>
                    {nodes.some(n => n.alert_level === 'CRITICAL') && (
                        <FiAlertTriangle size={14} color="#ef4444" title="Critical fill detected" />
                    )}
                </div>
                <button style={styles.refreshBtn} onClick={fetch} title="Refresh">
                    <FiRefreshCw size={13} />
                </button>
            </div>

            {error && (
                <div style={styles.errorBand}><FiAlertTriangle size={12} /> {error}</div>
            )}

            {loading ? (
                <div style={styles.placeholder}>Loading…</div>
            ) : nodes.length === 0 ? (
                <div style={styles.placeholder}>
                    No anchored nodes configured. Nodes are auto-nominated when anchored
                    fill exceeds {FILL_CRITICAL}%.
                </div>
            ) : (
                <div style={styles.nodeList}>
                    {nodes.map((node, i) => {
                        const maxFill = Math.max(node.vcpu_fill_pct, node.mem_fill_pct);
                        const alert   = node.alert_level || (
                            maxFill >= FILL_CRITICAL ? 'CRITICAL'
                            : maxFill >= FILL_WARN   ? 'WARNING'
                            : 'OK'
                        );
                        return (
                            <div key={i} style={styles.nodeCard}>
                                <div style={styles.nodeHeader}>
                                    <span style={styles.nodeName}>{node.node_name}</span>
                                    <AlertBadge level={alert} />
                                </div>

                                <div style={styles.metricRow}>
                                    <span style={styles.metricLabel}>vCPU</span>
                                    <FillBar pct={node.vcpu_fill_pct} alertLevel={alert} />
                                    <span style={styles.metricPct}>
                                        {node.vcpu_fill_pct?.toFixed(0)}%
                                    </span>
                                </div>
                                <div style={styles.metricRow}>
                                    <span style={styles.metricLabel}>Mem</span>
                                    <FillBar pct={node.mem_fill_pct} alertLevel={alert} />
                                    <span style={styles.metricPct}>
                                        {node.mem_fill_pct?.toFixed(0)}%
                                    </span>
                                </div>

                                {alert === 'CRITICAL' && (
                                    <div style={styles.infoHint}>
                                        <FiAlertTriangle size={11} color="#f87171" />
                                        Over {FILL_CRITICAL}% fill — a backup node will be auto-nominated.
                                    </div>
                                )}
                                {alert === 'WARNING' && (
                                    <div style={styles.infoHint}>
                                        <FiAlertTriangle size={11} color="#fbbf24" />
                                        Over {FILL_WARN}% fill — consider nominating an additional anchor.
                                    </div>
                                )}
                            </div>
                        );
                    })}
                </div>
            )}

            {lastUpdated && (
                <div style={styles.footer}>
                    Last updated {lastUpdated.toLocaleTimeString()}
                </div>
            )}
        </div>
    );
};

const styles = {
    card: {
        background: '#1a1f2e',
        border: '1px solid #2d3748',
        borderRadius: 12,
        padding: 20,
        color: '#e2e8f0',
        fontFamily: 'Inter, sans-serif',
    },
    header: {
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        marginBottom: 16,
    },
    titleRow: {
        display: 'flex',
        alignItems: 'center',
        gap: 8,
    },
    title: {
        fontSize: 15,
        fontWeight: 600,
    },
    refreshBtn: {
        background: 'transparent',
        border: 'none',
        color: '#94a3b8',
        cursor: 'pointer',
        padding: 4,
    },
    errorBand: {
        display: 'flex',
        alignItems: 'center',
        gap: 6,
        background: '#7f1d1d33',
        border: '1px solid #ef444444',
        borderRadius: 6,
        padding: '7px 10px',
        marginBottom: 12,
        fontSize: 12,
        color: '#fca5a5',
    },
    placeholder: {
        color: '#64748b',
        fontSize: 13,
        textAlign: 'center',
        padding: '16px 0',
    },
    nodeList: {
        display: 'flex',
        flexDirection: 'column',
        gap: 10,
    },
    nodeCard: {
        background: '#0f172a',
        borderRadius: 8,
        padding: '12px 14px',
    },
    nodeHeader: {
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        marginBottom: 10,
    },
    nodeName: {
        fontSize: 13,
        fontWeight: 600,
        fontFamily: 'monospace',
        color: '#cbd5e1',
    },
    metricRow: {
        display: 'flex',
        alignItems: 'center',
        gap: 8,
        marginBottom: 6,
    },
    metricLabel: {
        fontSize: 11,
        color: '#64748b',
        width: 28,
        flexShrink: 0,
    },
    metricPct: {
        fontSize: 11,
        color: '#94a3b8',
        width: 30,
        textAlign: 'right',
        flexShrink: 0,
    },
    infoHint: {
        display: 'flex',
        alignItems: 'center',
        gap: 4,
        marginTop: 6,
        fontSize: 11,
        color: '#94a3b8',
    },
    footer: {
        marginTop: 12,
        fontSize: 11,
        color: '#475569',
        textAlign: 'right',
    },
};

export default AnchoredNodePanel;
