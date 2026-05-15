/**
 * KedaInstallation.jsx — K2 KEDA lifecycle panel
 *
 * Shows install status, install/uninstall controls, and detected ScaledObjects
 * for the selected cluster.
 */

import React, { useState, useEffect, useCallback } from 'react';
import { kedaAPI } from '../../services/api';
import {
    FiZap, FiCheckCircle, FiXCircle, FiAlertTriangle,
    FiDownload, FiTrash2, FiRefreshCw,
} from 'react-icons/fi';

const STATUS_CONFIG = {
    installed:   { color: '#22c55e', label: 'Installed',    icon: FiCheckCircle },
    installing:  { color: '#f59e0b', label: 'Installing…',  icon: FiRefreshCw   },
    uninstalling:{ color: '#f59e0b', label: 'Removing…',    icon: FiRefreshCw   },
    not_installed:{ color: '#6b7280', label: 'Not Installed', icon: FiXCircle    },
    error:       { color: '#ef4444', label: 'Error',         icon: FiAlertTriangle },
};

const KedaInstallation = ({ clusterId }) => {
    const [status, setStatus]             = useState(null);
    const [scaledObjects, setScaledObjects] = useState([]);
    const [loading, setLoading]           = useState(true);
    const [actionInProgress, setActionInProgress] = useState(false);
    const [error, setError]               = useState(null);

    const fetchStatus = useCallback(async () => {
        if (!clusterId) return;
        try {
            const res = await kedaAPI.getInstallStatus(clusterId);
            setStatus(res.data);
            setError(null);
        } catch (err) {
            setError('Failed to fetch KEDA status');
        } finally {
            setLoading(false);
        }
    }, [clusterId]);

    const fetchScaledObjects = useCallback(async () => {
        if (!clusterId || !status?.installed) return;
        try {
            const res = await kedaAPI.listScaledObjects(clusterId);
            setScaledObjects(res.data?.scaled_objects || []);
        } catch {
            /* non-fatal */
        }
    }, [clusterId, status?.installed]);

    useEffect(() => {
        fetchStatus();
        const poll = setInterval(fetchStatus, 15000);
        return () => clearInterval(poll);
    }, [fetchStatus]);

    useEffect(() => {
        fetchScaledObjects();
    }, [fetchScaledObjects]);

    const handleInstall = async () => {
        setActionInProgress(true);
        try {
            await kedaAPI.install(clusterId);
            await fetchStatus();
        } catch (err) {
            setError(err?.response?.data?.detail || 'Install failed');
        } finally {
            setActionInProgress(false);
        }
    };

    const handleUninstall = async () => {
        if (!window.confirm('Uninstall KEDA? All ScaledObjects will stop autoscaling.')) return;
        setActionInProgress(true);
        try {
            await kedaAPI.uninstall(clusterId);
            await fetchStatus();
        } catch (err) {
            setError(err?.response?.data?.detail || 'Uninstall failed');
        } finally {
            setActionInProgress(false);
        }
    };

    if (loading) {
        return (
            <div style={styles.card}>
                <div style={styles.loadingRow}>
                    <FiRefreshCw style={{ animation: 'spin 1s linear infinite' }} />
                    <span>Loading KEDA status…</span>
                </div>
            </div>
        );
    }

    const statusKey = status?.installing ? 'installing'
        : status?.installed             ? 'installed'
        : 'not_installed';
    const cfg = STATUS_CONFIG[statusKey] || STATUS_CONFIG.not_installed;
    const Icon = cfg.icon;

    return (
        <div style={styles.card}>
            {/* Header */}
            <div style={styles.header}>
                <div style={styles.titleRow}>
                    <FiZap size={20} color="#8b5cf6" />
                    <span style={styles.title}>KEDA — Event-Driven Autoscaling</span>
                </div>
                <button style={styles.refreshBtn} onClick={fetchStatus} title="Refresh">
                    <FiRefreshCw size={14} />
                </button>
            </div>

            {error && (
                <div style={styles.errorBand}>
                    <FiAlertTriangle size={14} /> {error}
                </div>
            )}

            {/* Status badge */}
            <div style={styles.statusRow}>
                <Icon size={18} color={cfg.color} />
                <span style={{ ...styles.statusLabel, color: cfg.color }}>{cfg.label}</span>
                {status?.version && (
                    <span style={styles.versionPill}>v{status.version}</span>
                )}
            </div>

            {/* Controls */}
            <div style={styles.controlRow}>
                {!status?.installed && !status?.installing && (
                    <button
                        style={{ ...styles.btn, ...styles.btnPrimary }}
                        onClick={handleInstall}
                        disabled={actionInProgress}
                    >
                        <FiDownload size={14} />
                        {actionInProgress ? 'Installing…' : 'Install KEDA'}
                    </button>
                )}
                {status?.installed && (
                    <button
                        style={{ ...styles.btn, ...styles.btnDanger }}
                        onClick={handleUninstall}
                        disabled={actionInProgress}
                    >
                        <FiTrash2 size={14} />
                        {actionInProgress ? 'Removing…' : 'Uninstall'}
                    </button>
                )}
            </div>

            {/* ScaledObjects list */}
            {scaledObjects.length > 0 && (
                <div style={styles.soSection}>
                    <div style={styles.soHeader}>
                        ScaledObjects ({scaledObjects.length})
                    </div>
                    <div style={styles.soList}>
                        {scaledObjects.map((so, i) => (
                            <div key={i} style={styles.soRow}>
                                <span style={styles.soName}>
                                    {so.namespace}/{so.name}
                                </span>
                                <span style={{
                                    ...styles.soBadge,
                                    background: so.paused ? '#6b7280' : '#22c55e22',
                                    color:      so.paused ? '#e5e7eb' : '#22c55e',
                                }}>
                                    {so.paused ? 'paused' : 'active'}
                                </span>
                            </div>
                        ))}
                    </div>
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
    loadingRow: {
        display: 'flex',
        alignItems: 'center',
        gap: 8,
        color: '#94a3b8',
        fontSize: 14,
    },
    errorBand: {
        display: 'flex',
        alignItems: 'center',
        gap: 6,
        background: '#7f1d1d33',
        border: '1px solid #ef444444',
        borderRadius: 6,
        padding: '8px 12px',
        marginBottom: 12,
        fontSize: 13,
        color: '#fca5a5',
    },
    statusRow: {
        display: 'flex',
        alignItems: 'center',
        gap: 8,
        marginBottom: 16,
    },
    statusLabel: {
        fontSize: 14,
        fontWeight: 600,
    },
    versionPill: {
        background: '#1e293b',
        border: '1px solid #334155',
        borderRadius: 20,
        padding: '2px 8px',
        fontSize: 12,
        color: '#94a3b8',
    },
    controlRow: {
        display: 'flex',
        gap: 8,
        marginBottom: 16,
    },
    btn: {
        display: 'flex',
        alignItems: 'center',
        gap: 6,
        padding: '8px 16px',
        borderRadius: 8,
        border: 'none',
        fontSize: 13,
        fontWeight: 500,
        cursor: 'pointer',
    },
    btnPrimary: {
        background: '#7c3aed',
        color: '#fff',
    },
    btnDanger: {
        background: '#7f1d1d',
        color: '#fca5a5',
    },
    soSection: {
        marginTop: 8,
    },
    soHeader: {
        fontSize: 12,
        fontWeight: 600,
        color: '#94a3b8',
        textTransform: 'uppercase',
        letterSpacing: '0.05em',
        marginBottom: 8,
    },
    soList: {
        display: 'flex',
        flexDirection: 'column',
        gap: 4,
    },
    soRow: {
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        background: '#0f172a',
        borderRadius: 6,
        padding: '6px 10px',
    },
    soName: {
        fontSize: 13,
        color: '#cbd5e1',
        fontFamily: 'monospace',
    },
    soBadge: {
        fontSize: 11,
        fontWeight: 600,
        padding: '2px 8px',
        borderRadius: 20,
    },
};

export default KedaInstallation;
