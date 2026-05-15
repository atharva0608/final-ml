/**
 * IntegrationsPanel.jsx — Combined Karpenter + KEDA installation status panel.
 *
 * Shown in the cluster detail view under "Integrations" tab.
 * Renders KedaInstallation alongside a Karpenter status summary card.
 */

import React, { useState, useEffect } from 'react';
import { karpenterAPI, kedaAPI } from '../../services/api';
import KedaInstallation from './KedaInstallation';
import { FiPackage, FiCheckCircle, FiXCircle, FiRefreshCw } from 'react-icons/fi';

const IntegrationStatusCard = ({ title, icon: Icon, installed, version, onRefresh }) => (
    <div style={cardStyles.card}>
        <div style={cardStyles.header}>
            <div style={cardStyles.titleRow}>
                <Icon size={16} color="#60a5fa" />
                <span style={cardStyles.title}>{title}</span>
            </div>
            {onRefresh && (
                <button style={cardStyles.refreshBtn} onClick={onRefresh}>
                    <FiRefreshCw size={12} />
                </button>
            )}
        </div>
        <div style={cardStyles.statusRow}>
            {installed ? (
                <FiCheckCircle size={16} color="#22c55e" />
            ) : (
                <FiXCircle size={16} color="#6b7280" />
            )}
            <span style={{ color: installed ? '#22c55e' : '#6b7280', fontSize: 13, fontWeight: 600 }}>
                {installed ? 'Installed' : 'Not Installed'}
            </span>
            {version && (
                <span style={cardStyles.versionPill}>v{version}</span>
            )}
        </div>
    </div>
);

const cardStyles = {
    card: {
        background: '#1a1f2e',
        border: '1px solid #2d3748',
        borderRadius: 10,
        padding: 16,
        color: '#e2e8f0',
        flex: 1,
    },
    header: {
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        marginBottom: 12,
    },
    titleRow: {
        display: 'flex',
        alignItems: 'center',
        gap: 6,
    },
    title: {
        fontSize: 14,
        fontWeight: 600,
    },
    refreshBtn: {
        background: 'transparent',
        border: 'none',
        color: '#94a3b8',
        cursor: 'pointer',
    },
    statusRow: {
        display: 'flex',
        alignItems: 'center',
        gap: 6,
    },
    versionPill: {
        background: '#1e293b',
        border: '1px solid #334155',
        borderRadius: 20,
        padding: '2px 8px',
        fontSize: 11,
        color: '#94a3b8',
    },
};

const IntegrationsPanel = ({ clusterId }) => {
    const [karpenterStatus, setKarpenterStatus] = useState(null);
    const [kedaStatus, setKedaStatus]           = useState(null);

    useEffect(() => {
        if (!clusterId) return;
        karpenterAPI.getInstallStatus(clusterId)
            .then(r => setKarpenterStatus(r.data))
            .catch(() => {});
        kedaAPI.getInstallStatus(clusterId)
            .then(r => setKedaStatus(r.data))
            .catch(() => {});
    }, [clusterId]);

    return (
        <div style={styles.container}>
            <div style={styles.sectionHeader}>
                <FiPackage size={18} color="#60a5fa" />
                <span style={styles.sectionTitle}>Cluster Integrations</span>
            </div>

            {/* Status Overview Row */}
            <div style={styles.statusRow}>
                <IntegrationStatusCard
                    title="Karpenter"
                    icon={FiPackage}
                    installed={karpenterStatus?.installed}
                    version={karpenterStatus?.version}
                    onRefresh={() =>
                        karpenterAPI.getInstallStatus(clusterId)
                            .then(r => setKarpenterStatus(r.data))
                            .catch(() => {})
                    }
                />
                <IntegrationStatusCard
                    title="KEDA"
                    icon={FiPackage}
                    installed={kedaStatus?.installed}
                    version={kedaStatus?.version}
                    onRefresh={() =>
                        kedaAPI.getInstallStatus(clusterId)
                            .then(r => setKedaStatus(r.data))
                            .catch(() => {})
                    }
                />
            </div>

            {/* Full KEDA management panel */}
            <KedaInstallation clusterId={clusterId} />
        </div>
    );
};

const styles = {
    container: {
        display: 'flex',
        flexDirection: 'column',
        gap: 16,
        fontFamily: 'Inter, sans-serif',
    },
    sectionHeader: {
        display: 'flex',
        alignItems: 'center',
        gap: 8,
    },
    sectionTitle: {
        fontSize: 16,
        fontWeight: 700,
        color: '#e2e8f0',
    },
    statusRow: {
        display: 'flex',
        gap: 12,
    },
};

export default IntegrationsPanel;
