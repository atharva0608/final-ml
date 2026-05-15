/**
 * WorkloadTierPanel.jsx — W3.x workload tier display + manual tier-override UI.
 *
 * Lists all detected workload controllers with their tier classification badges
 * and provides a "Set Tier Override" drawer for manual adjustments (§15).
 *
 * Tier legend:
 *   0 — NEVER_MIGRATE       (system / DaemonSet)
 *   1 — ANCHORED_MANUAL     (stateful, user-pinned)
 *   2 — STATEFUL_CAREFUL    (has PVC, careful migration)
 *   3 — STATELESS_PREFER_SPOT (stateless, prefers spot)
 *   4 — SPOT_ELIGIBLE       (fully stateless, optimise freely)
 */

import React, { useState, useEffect, useCallback } from 'react';
import { workloadTierAPI } from '../../services/api';
import {
    FiLayers, FiSliders, FiCheckCircle, FiAlertTriangle,
    FiRefreshCw, FiEdit2, FiX,
} from 'react-icons/fi';

const TIER_CONFIG = {
    0: { label: 'NEVER_MIGRATE',        color: '#ef4444', bg: '#7f1d1d33', desc: 'System / DaemonSet — never evict' },
    1: { label: 'ANCHORED_MANUAL',      color: '#f59e0b', bg: '#78350f33', desc: 'Stateful pinned to on-demand' },
    2: { label: 'STATEFUL_CAREFUL',     color: '#60a5fa', bg: '#1e3a5f33', desc: 'Has PVC — careful migration only' },
    3: { label: 'STATELESS_PREFER_SPOT',color: '#a78bfa', bg: '#4c1d9533', desc: 'Stateless, prefer spot' },
    4: { label: 'SPOT_ELIGIBLE',        color: '#22c55e', bg: '#14532d33', desc: 'Fully stateless — optimise freely' },
};

const TierBadge = ({ tier }) => {
    const cfg = TIER_CONFIG[tier] || TIER_CONFIG[4];
    return (
        <span style={{
            fontSize: 11,
            fontWeight: 700,
            padding: '2px 8px',
            borderRadius: 4,
            background: cfg.bg,
            color: cfg.color,
            letterSpacing: '0.03em',
        }}>
            T{tier} — {cfg.label}
        </span>
    );
};

const OverrideDrawer = ({ clusterId, workload, onClose, onSaved }) => {
    const [tier, setTier]           = useState(workload?.tier ?? 4);
    const [reason, setReason]       = useState('');
    const [saving, setSaving]       = useState(false);
    const [saveError, setSaveError] = useState(null);

    const handleSave = async () => {
        setSaving(true);
        setSaveError(null);
        try {
            await workloadTierAPI.setTierOverride(
                clusterId,
                workload.namespace,
                workload.controller_name,
                { tier, reason, controller_kind: workload.kind || 'Deployment' },
            );
            onSaved?.();
            onClose();
        } catch (err) {
            setSaveError(err?.response?.data?.detail || 'Save failed');
        } finally {
            setSaving(false);
        }
    };

    return (
        <div style={drawerStyles.overlay} onClick={onClose}>
            <div style={drawerStyles.drawer} onClick={e => e.stopPropagation()}>
                <div style={drawerStyles.drawerHeader}>
                    <span style={drawerStyles.drawerTitle}>
                        Override Tier — {workload?.namespace}/{workload?.controller_name}
                    </span>
                    <button style={drawerStyles.closeBtn} onClick={onClose}>
                        <FiX size={16} />
                    </button>
                </div>

                <label style={drawerStyles.label}>New Tier</label>
                <select
                    value={tier}
                    onChange={e => setTier(parseInt(e.target.value))}
                    style={drawerStyles.select}
                >
                    {Object.entries(TIER_CONFIG).map(([t, cfg]) => (
                        <option key={t} value={t}>T{t} — {cfg.label}</option>
                    ))}
                </select>
                <div style={{ ...drawerStyles.tierDesc, color: TIER_CONFIG[tier]?.color }}>
                    {TIER_CONFIG[tier]?.desc}
                </div>

                <label style={drawerStyles.label}>Reason (optional)</label>
                <input
                    type="text"
                    placeholder="e.g. contains Redis with AOF persistence"
                    value={reason}
                    onChange={e => setReason(e.target.value)}
                    style={drawerStyles.input}
                />

                {saveError && (
                    <div style={drawerStyles.errorBand}>{saveError}</div>
                )}

                <button
                    style={{
                        ...drawerStyles.saveBtn,
                        opacity: saving ? 0.7 : 1,
                    }}
                    onClick={handleSave}
                    disabled={saving}
                >
                    {saving ? 'Saving…' : 'Apply Override'}
                </button>
            </div>
        </div>
    );
};

const drawerStyles = {
    overlay: {
        position: 'fixed',
        inset: 0,
        background: '#000000aa',
        zIndex: 1000,
        display: 'flex',
        justifyContent: 'flex-end',
    },
    drawer: {
        width: 360,
        background: '#1a1f2e',
        borderLeft: '1px solid #2d3748',
        padding: 24,
        display: 'flex',
        flexDirection: 'column',
        gap: 12,
        overflowY: 'auto',
        color: '#e2e8f0',
        fontFamily: 'Inter, sans-serif',
    },
    drawerHeader: {
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        marginBottom: 4,
    },
    drawerTitle: {
        fontSize: 14,
        fontWeight: 600,
        fontFamily: 'monospace',
    },
    closeBtn: {
        background: 'transparent',
        border: 'none',
        color: '#94a3b8',
        cursor: 'pointer',
    },
    label: {
        fontSize: 12,
        color: '#94a3b8',
        fontWeight: 600,
        textTransform: 'uppercase',
        letterSpacing: '0.05em',
    },
    select: {
        background: '#0f172a',
        border: '1px solid #334155',
        borderRadius: 6,
        color: '#e2e8f0',
        padding: '8px 10px',
        fontSize: 13,
        width: '100%',
    },
    tierDesc: {
        fontSize: 12,
        marginTop: 2,
    },
    input: {
        background: '#0f172a',
        border: '1px solid #334155',
        borderRadius: 6,
        color: '#e2e8f0',
        padding: '8px 10px',
        fontSize: 13,
        width: '100%',
        boxSizing: 'border-box',
    },
    errorBand: {
        background: '#7f1d1d33',
        border: '1px solid #ef444444',
        borderRadius: 6,
        padding: '8px 10px',
        fontSize: 12,
        color: '#fca5a5',
    },
    saveBtn: {
        background: '#7c3aed',
        color: '#fff',
        border: 'none',
        borderRadius: 8,
        padding: '10px 0',
        fontSize: 14,
        fontWeight: 600,
        cursor: 'pointer',
        width: '100%',
        marginTop: 4,
    },
};

const WorkloadTierPanel = ({ clusterId }) => {
    const [tiers, setTiers]           = useState([]);
    const [loading, setLoading]       = useState(true);
    const [error, setError]           = useState(null);
    const [filterTier, setFilterTier] = useState('all');
    const [overrideTarget, setOverrideTarget] = useState(null);
    const [search, setSearch]         = useState('');

    const fetchTiers = useCallback(async () => {
        if (!clusterId) return;
        try {
            const res = await workloadTierAPI.listTiers(clusterId);
            setTiers(res.data?.tiers || []);
            setError(null);
        } catch (err) {
            setError('Failed to load workload tiers');
        } finally {
            setLoading(false);
        }
    }, [clusterId]);

    useEffect(() => {
        fetchTiers();
        const poll = setInterval(fetchTiers, 60000);
        return () => clearInterval(poll);
    }, [fetchTiers]);

    const filtered = tiers.filter(w => {
        const matchTier = filterTier === 'all' || String(w.tier) === filterTier;
        const matchSearch = !search
            || `${w.namespace}/${w.controller_name}`.toLowerCase().includes(search.toLowerCase());
        return matchTier && matchSearch;
    });

    const tierCounts = tiers.reduce((acc, w) => {
        acc[w.tier] = (acc[w.tier] || 0) + 1;
        return acc;
    }, {});

    return (
        <div style={styles.card}>
            <div style={styles.header}>
                <div style={styles.titleRow}>
                    <FiLayers size={18} color="#a78bfa" />
                    <span style={styles.title}>Workload Tiers</span>
                    <span style={styles.count}>{tiers.length} workloads</span>
                </div>
                <button style={styles.refreshBtn} onClick={fetchTiers}>
                    <FiRefreshCw size={13} />
                </button>
            </div>

            {/* Tier breakdown pills */}
            <div style={styles.tierPills}>
                <button
                    style={{ ...styles.pill, ...(filterTier === 'all' ? styles.pillActive : {}) }}
                    onClick={() => setFilterTier('all')}
                >
                    All ({tiers.length})
                </button>
                {[0, 1, 2, 3, 4].map(t => tierCounts[t] ? (
                    <button
                        key={t}
                        style={{
                            ...styles.pill,
                            border: `1px solid ${TIER_CONFIG[t].color}44`,
                            color: TIER_CONFIG[t].color,
                            ...(filterTier === String(t) ? { background: TIER_CONFIG[t].bg } : {}),
                        }}
                        onClick={() => setFilterTier(String(t))}
                    >
                        T{t} ({tierCounts[t]})
                    </button>
                ) : null)}
            </div>

            {/* Search */}
            <input
                type="text"
                placeholder="Filter by namespace/controller…"
                value={search}
                onChange={e => setSearch(e.target.value)}
                style={styles.searchInput}
            />

            {error && (
                <div style={styles.errorBand}><FiAlertTriangle size={12} /> {error}</div>
            )}

            {loading ? (
                <div style={styles.placeholder}>Loading…</div>
            ) : filtered.length === 0 ? (
                <div style={styles.placeholder}>No workloads match filter.</div>
            ) : (
                <div style={styles.table}>
                    <div style={styles.tableHeader}>
                        <span style={{ flex: 2 }}>Controller</span>
                        <span style={{ flex: 1 }}>Tier</span>
                        <span style={{ flex: 1 }}>Confidence</span>
                        <span style={{ width: 40 }}></span>
                    </div>
                    {filtered.map((w, i) => (
                        <div key={i} style={styles.tableRow}>
                            <span style={{ flex: 2, fontFamily: 'monospace', fontSize: 12, color: '#cbd5e1' }}>
                                {w.namespace}/{w.controller_name}
                            </span>
                            <span style={{ flex: 1 }}><TierBadge tier={w.tier} /></span>
                            <span style={{ flex: 1, fontSize: 12, color: '#94a3b8' }}>
                                {w.classification_confidence !== undefined
                                    ? `${(w.classification_confidence * 100).toFixed(0)}%`
                                    : '—'}
                                {w.migration_policy === 'manual_override' && (
                                    <span style={{ color: '#f59e0b', marginLeft: 4 }}> ✎</span>
                                )}
                            </span>
                            <button
                                style={styles.editBtn}
                                onClick={() => setOverrideTarget(w)}
                                title="Override tier"
                            >
                                <FiEdit2 size={12} />
                            </button>
                        </div>
                    ))}
                </div>
            )}

            {overrideTarget && (
                <OverrideDrawer
                    clusterId={clusterId}
                    workload={overrideTarget}
                    onClose={() => setOverrideTarget(null)}
                    onSaved={() => {
                        setOverrideTarget(null);
                        fetchTiers();
                    }}
                />
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
        marginBottom: 14,
    },
    titleRow: {
        display: 'flex',
        alignItems: 'center',
        gap: 8,
    },
    title: { fontSize: 15, fontWeight: 600 },
    count: {
        fontSize: 12,
        color: '#64748b',
        background: '#1e293b',
        padding: '2px 7px',
        borderRadius: 10,
    },
    refreshBtn: {
        background: 'transparent',
        border: 'none',
        color: '#94a3b8',
        cursor: 'pointer',
        padding: 4,
    },
    tierPills: {
        display: 'flex',
        flexWrap: 'wrap',
        gap: 6,
        marginBottom: 12,
    },
    pill: {
        background: '#1e293b',
        border: '1px solid #334155',
        borderRadius: 20,
        padding: '3px 10px',
        fontSize: 12,
        color: '#94a3b8',
        cursor: 'pointer',
    },
    pillActive: {
        background: '#334155',
        color: '#e2e8f0',
    },
    searchInput: {
        width: '100%',
        boxSizing: 'border-box',
        background: '#0f172a',
        border: '1px solid #334155',
        borderRadius: 6,
        color: '#e2e8f0',
        padding: '7px 10px',
        fontSize: 13,
        marginBottom: 12,
    },
    errorBand: {
        display: 'flex',
        alignItems: 'center',
        gap: 6,
        background: '#7f1d1d33',
        borderRadius: 6,
        padding: '7px 10px',
        marginBottom: 10,
        fontSize: 12,
        color: '#fca5a5',
    },
    placeholder: {
        color: '#64748b',
        fontSize: 13,
        textAlign: 'center',
        padding: '16px 0',
    },
    table: {
        display: 'flex',
        flexDirection: 'column',
        gap: 1,
    },
    tableHeader: {
        display: 'flex',
        alignItems: 'center',
        padding: '6px 8px',
        fontSize: 11,
        color: '#64748b',
        textTransform: 'uppercase',
        letterSpacing: '0.05em',
        borderBottom: '1px solid #1e293b',
        marginBottom: 4,
    },
    tableRow: {
        display: 'flex',
        alignItems: 'center',
        padding: '8px 8px',
        borderRadius: 6,
        background: '#0f172a',
        marginBottom: 3,
    },
    editBtn: {
        background: 'transparent',
        border: '1px solid #334155',
        borderRadius: 4,
        color: '#94a3b8',
        cursor: 'pointer',
        padding: '3px 5px',
        width: 28,
        height: 26,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
    },
};

export default WorkloadTierPanel;
