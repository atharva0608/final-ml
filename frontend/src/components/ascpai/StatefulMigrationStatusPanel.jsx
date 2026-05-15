/**
 * StatefulMigrationStatusPanel.jsx — §15 Stateful migration status dashboard.
 *
 * Shows real-time active migrations (from Redis autoscaler-freeze keys) and
 * historical state transitions from the migration_event table.
 *
 * State machine colours:
 *   freeze-start  → yellow
 *   migrating     → blue
 *   soak          → purple
 *   complete      → green
 *   failed        → red
 */

import React, { useState, useEffect, useCallback } from 'react';
import { migrationStatusAPI } from '../../services/api';
import {
    FiActivity, FiClock, FiCheckCircle, FiXCircle,
    FiRefreshCw, FiAlertTriangle, FiArrowRight,
} from 'react-icons/fi';

const STATE_CONFIG = {
    'freeze-start': { color: '#f59e0b', bg: '#78350f33', icon: FiClock,        label: 'Freeze Start'  },
    migrating:      { color: '#60a5fa', bg: '#1e3a5f33', icon: FiArrowRight,   label: 'Migrating'     },
    soak:           { color: '#a78bfa', bg: '#4c1d9533', icon: FiActivity,     label: 'Soak'          },
    complete:       { color: '#22c55e', bg: '#14532d33', icon: FiCheckCircle,  label: 'Complete'      },
    failed:         { color: '#ef4444', bg: '#7f1d1d33', icon: FiXCircle,      label: 'Failed'        },
};

const TIER_BADGE_COLOR = {
    0: '#ef4444', 1: '#f59e0b', 2: '#60a5fa', 3: '#a78bfa', 4: '#22c55e',
};

const StateBadge = ({ state }) => {
    const cfg = STATE_CONFIG[state] || { color: '#94a3b8', bg: '#1e293b', label: state };
    return (
        <span style={{
            fontSize: 11, fontWeight: 700,
            padding: '2px 8px', borderRadius: 4,
            background: cfg.bg, color: cfg.color,
        }}>
            {cfg.label || state}
        </span>
    );
};

const ActiveCard = ({ migration }) => {
    const elapsedS = migration.frozen_at
        ? Math.round(Date.now() / 1000 - migration.frozen_at)
        : null;
    const isSlow   = elapsedS !== null && elapsedS > 90;

    return (
        <div style={{
            ...styles.eventRow,
            border: `1px solid ${isSlow ? '#f59e0b44' : '#1e3a5f'}`,
            background: isSlow ? '#78350f18' : '#1e293b',
        }}>
            <div style={styles.eventMain}>
                <span style={styles.ctrlName}>
                    {migration.namespace}/{migration.controller_name}
                </span>
                <StateBadge state="freeze-start" />
            </div>
            <div style={styles.eventMeta}>
                {elapsedS !== null && (
                    <span style={{ color: isSlow ? '#f59e0b' : '#94a3b8', fontSize: 12 }}>
                        <FiClock size={11} style={{ marginRight: 4 }} />
                        {elapsedS}s
                        {isSlow && ' — approaching 120s cap'}
                    </span>
                )}
                <span style={styles.metaTag}>
                    HPA: {migration.hpa_frozen ? 'frozen' : '—'}
                </span>
                <span style={styles.metaTag}>
                    KEDA: {migration.keda_frozen ? 'paused' : '—'}
                </span>
                {migration.ttl_remaining_s !== null && (
                    <span style={styles.metaTag}>TTL {migration.ttl_remaining_s}s</span>
                )}
            </div>
        </div>
    );
};

const HistoryRow = ({ event }) => {
    const tierColor = TIER_BADGE_COLOR[event.workload_tier] || '#94a3b8';
    return (
        <div style={styles.eventRow}>
            <div style={styles.eventMain}>
                <span style={styles.ctrlName}>
                    {event.namespace}/{event.controller_name}
                </span>
                <StateBadge state={event.state} />
                {event.workload_tier !== null && event.workload_tier !== undefined && (
                    <span style={{ ...styles.tierPill, color: tierColor, borderColor: tierColor + '44' }}>
                        T{event.workload_tier}
                    </span>
                )}
            </div>
            <div style={styles.eventMeta}>
                {event.source_node && (
                    <span style={styles.metaTag} title="Source node">
                        {event.source_node.slice(0, 20)}{event.source_node.length > 20 ? '…' : ''}
                        {event.target_node && ` → ${event.target_node.slice(0, 20)}${event.target_node.length > 20 ? '…' : ''}`}
                    </span>
                )}
                {event.failure_reason && (
                    <span style={{ ...styles.metaTag, color: '#f87171' }}>
                        {event.failure_reason.slice(0, 60)}
                    </span>
                )}
                {event.freeze_restored !== null && event.state !== 'failed' && (
                    <span style={{
                        ...styles.metaTag,
                        color: event.freeze_restored ? '#22c55e' : '#f59e0b',
                    }}>
                        {event.freeze_restored ? '✓ restored' : 'restoring…'}
                    </span>
                )}
                <span style={{ ...styles.metaTag, color: '#475569', marginLeft: 'auto' }}>
                    {event.created_at
                        ? new Date(event.created_at).toLocaleTimeString()
                        : ''}
                </span>
            </div>
        </div>
    );
};

const StatefulMigrationStatusPanel = ({ clusterId }) => {
    const [data, setData]           = useState(null);
    const [loading, setLoading]     = useState(true);
    const [error, setError]         = useState(null);
    const [tab, setTab]             = useState('active');   // 'active' | 'history'
    const [lastUpdated, setLastUpdated] = useState(null);

    const fetch = useCallback(async () => {
        if (!clusterId) return;
        try {
            const res = await migrationStatusAPI.get(clusterId, 50);
            setData(res.data);
            setLastUpdated(new Date());
            setError(null);
        } catch (err) {
            setError('Failed to load migration status');
        } finally {
            setLoading(false);
        }
    }, [clusterId]);

    useEffect(() => {
        fetch();
        const poll = setInterval(fetch, 10000);
        return () => clearInterval(poll);
    }, [fetch]);

    const active  = data?.active_migrations  || [];
    const history = data?.history            || [];

    const nodeSummary = data && {
        total:    data.total_nodes,
        od:       data.on_demand_remaining,
        spot:     data.spot_nodes,
        spotPct:  data.spot_percentage,
        phase:    data.phase,
    };

    return (
        <div style={styles.card}>
            {/* Header */}
            <div style={styles.header}>
                <div style={styles.titleRow}>
                    <FiActivity size={18} color="#60a5fa" />
                    <span style={styles.title}>Migration Status</span>
                    {active.length > 0 && (
                        <span style={styles.activePill}>{active.length} active</span>
                    )}
                </div>
                <button style={styles.refreshBtn} onClick={fetch} title="Refresh">
                    <FiRefreshCw size={13} />
                </button>
            </div>

            {error && (
                <div style={styles.errorBand}>
                    <FiAlertTriangle size={12} /> {error}
                </div>
            )}

            {/* Node summary bar */}
            {nodeSummary && (
                <div style={styles.summaryRow}>
                    <StatPill label="Nodes" value={nodeSummary.total} />
                    <StatPill label="On-Demand" value={nodeSummary.od} color="#f59e0b" />
                    <StatPill label="Spot" value={nodeSummary.spot} color="#22c55e" />
                    <StatPill label="Spot %" value={`${nodeSummary.spotPct}%`} color="#a78bfa" />
                    <span style={{
                        ...styles.phasePill,
                        background: nodeSummary.phase === 'completed' ? '#14532d33' : '#1e3a5f33',
                        color:      nodeSummary.phase === 'completed' ? '#22c55e' : '#60a5fa',
                    }}>
                        {nodeSummary.phase?.replace('_', ' ')}
                    </span>
                </div>
            )}

            {/* Tabs */}
            <div style={styles.tabs}>
                {['active', 'history'].map(t => (
                    <button
                        key={t}
                        style={{ ...styles.tab, ...(tab === t ? styles.tabActive : {}) }}
                        onClick={() => setTab(t)}
                    >
                        {t === 'active' ? `Active (${active.length})` : `History (${history.length})`}
                    </button>
                ))}
            </div>

            {/* Content */}
            {loading ? (
                <div style={styles.placeholder}>Loading…</div>
            ) : tab === 'active' ? (
                active.length === 0 ? (
                    <div style={styles.placeholder}>
                        <FiCheckCircle size={16} color="#22c55e" style={{ marginBottom: 4 }} />
                        <div>No active migrations — all autoscalers running normally.</div>
                    </div>
                ) : (
                    <div style={styles.list}>
                        {active.map((m, i) => <ActiveCard key={i} migration={m} />)}
                    </div>
                )
            ) : (
                history.length === 0 ? (
                    <div style={styles.placeholder}>No historical events yet.</div>
                ) : (
                    <div style={styles.list}>
                        {history.map((ev, i) => <HistoryRow key={ev.id || i} event={ev} />)}
                    </div>
                )
            )}

            {lastUpdated && (
                <div style={styles.footer}>
                    Updated {lastUpdated.toLocaleTimeString()} · auto-refresh 10s
                </div>
            )}
        </div>
    );
};

const StatPill = ({ label, value, color = '#e2e8f0' }) => (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
        <span style={{ fontSize: 16, fontWeight: 700, color }}>{value}</span>
        <span style={{ fontSize: 10, color: '#64748b' }}>{label}</span>
    </div>
);

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
        marginBottom: 14,
    },
    titleRow: {
        display: 'flex',
        alignItems: 'center',
        gap: 8,
    },
    title: { fontSize: 15, fontWeight: 600 },
    activePill: {
        background: '#1e3a5f',
        color: '#60a5fa',
        fontSize: 11,
        fontWeight: 700,
        padding: '2px 8px',
        borderRadius: 20,
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
    summaryRow: {
        display: 'flex',
        alignItems: 'center',
        gap: 16,
        padding: '10px 14px',
        background: '#0f172a',
        borderRadius: 8,
        marginBottom: 14,
    },
    phasePill: {
        fontSize: 11,
        fontWeight: 700,
        padding: '3px 10px',
        borderRadius: 20,
        marginLeft: 'auto',
        textTransform: 'uppercase',
        letterSpacing: '0.04em',
    },
    tabs: {
        display: 'flex',
        gap: 4,
        marginBottom: 12,
        borderBottom: '1px solid #1e293b',
    },
    tab: {
        background: 'transparent',
        border: 'none',
        color: '#64748b',
        fontSize: 13,
        fontWeight: 500,
        padding: '8px 14px',
        cursor: 'pointer',
        borderBottom: '2px solid transparent',
    },
    tabActive: {
        color: '#e2e8f0',
        borderBottomColor: '#60a5fa',
    },
    placeholder: {
        color: '#64748b',
        fontSize: 13,
        textAlign: 'center',
        padding: '24px 0',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        gap: 6,
    },
    list: {
        display: 'flex',
        flexDirection: 'column',
        gap: 6,
    },
    eventRow: {
        background: '#0f172a',
        borderRadius: 8,
        padding: '10px 12px',
        border: '1px solid #1e293b',
    },
    eventMain: {
        display: 'flex',
        alignItems: 'center',
        gap: 8,
        marginBottom: 6,
        flexWrap: 'wrap',
    },
    ctrlName: {
        fontFamily: 'monospace',
        fontSize: 13,
        color: '#cbd5e1',
        flex: 1,
        minWidth: 120,
    },
    tierPill: {
        fontSize: 10,
        fontWeight: 700,
        padding: '1px 6px',
        borderRadius: 4,
        border: '1px solid',
    },
    eventMeta: {
        display: 'flex',
        alignItems: 'center',
        gap: 8,
        flexWrap: 'wrap',
    },
    metaTag: {
        fontSize: 11,
        color: '#94a3b8',
        background: '#1e293b',
        padding: '1px 6px',
        borderRadius: 4,
    },
    footer: {
        marginTop: 12,
        fontSize: 11,
        color: '#475569',
        textAlign: 'right',
    },
};

export default StatefulMigrationStatusPanel;
