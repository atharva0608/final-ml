import React, { useState } from 'react';
import { FiMoon, FiZap, FiShield, FiCheck, FiInfo, FiActivity, FiClock, FiAlertTriangle } from 'react-icons/fi';

const STRATEGIES = [
    {
        id: 'NAMESPACE_SLEEP',
        label: 'Namespace Sleep',
        icon: FiMoon,
        color: '#6366f1',
        bg: 'rgba(99,102,241,0.08)',
        border: 'rgba(99,102,241,0.25)',
        wakeTime: '~2 min',
        savings: '80%',
        risk: 'LOW',
        desc: 'Scales workloads to 0 replicas. Best for stateless apps.',
        details: [
            'Gracefully scales down Deployment and StatefulSet replicas to 0.',
            'Preserves the Kubernetes namespace and all configurations.',
            'Instantly restores the exact previous replica counts upon wake up.'
        ]
    },
    {
        id: 'NUCLEAR',
        label: 'Nuclear',
        icon: FiZap,
        color: '#ef4444',
        bg: 'rgba(239,68,68,0.08)',
        border: 'rgba(239,68,68,0.25)',
        wakeTime: '~8 min',
        savings: '99%',
        risk: 'MEDIUM',
        desc: 'Scales Auto Scaling Groups (ASGs) to 0 directly. Maximum cost reduction.',
        details: [
            'Bypasses Kubernetes and terminates worker nodes directly via the Cloud Provider.',
            'Saves maximum cost as compute boundaries are eliminated entirely.',
            'Longer wake-up time as nodes must be re-provisioned and joined to the cluster.'
        ]
    },
    {
        id: 'SNAPSHOT_RESTORE',
        label: 'Snapshot & Restore',
        icon: FiShield,
        color: '#22c55e',
        bg: 'rgba(34,197,94,0.08)',
        border: 'rgba(34,197,94,0.25)',
        wakeTime: '~12 min',
        savings: '90%',
        risk: 'LOWEST',
        desc: 'Creates EBS snapshots before sleep. Best for stateful workloads.',
        details: [
            'Triggers synchronous CSI VolumeSnapshot creation for all attached PVCs.',
            'Ensures database and cache consistency before shutting down pods.',
            'Restores volumes dynamically before pod re-initialization on wake.'
        ]
    },
];

const C = {
    bg: "#f8f9fb", surface: "#fff", surfaceHover: "#fcfcfd",
    border: "#e8eaed", borderHover: "#d0d5dd",
    text: "#0f172a", muted: "#64748b", subtle: "#94a3b8",
    accent: "#4f46e5", accentLight: "#eef2ff",
};

export default function StrategiesTab() {
    const [selectedId, setSelectedId] = useState(STRATEGIES[0].id);
    const selectedStrategy = STRATEGIES.find(s => s.id === selectedId);

    return (
        <div style={{ display: 'flex', height: 'calc(100vh - 80px)', padding: '24px 28px', gap: 24, maxWidth: 1400, margin: '0 auto' }}>

            {/* ── MASTER: Strategies List ── */}
            <div style={{ width: '340px', display: 'flex', flexDirection: 'column', flexShrink: 0 }}>
                <div style={{
                    fontSize: 10, fontWeight: 700, letterSpacing: "0.1em",
                    textTransform: "uppercase", color: C.subtle,
                    marginBottom: 10, paddingBottom: 7, borderBottom: `1px solid ${C.border}`,
                }}>
                    Supported Strategies
                </div>

                <div style={{ flex: 1, overflowY: 'auto', paddingRight: 4 }}>
                    {STRATEGIES.map(st => {
                        const isSelected = selectedId === st.id;
                        const Icon = st.icon;
                        return (
                            <div
                                key={st.id}
                                onClick={() => setSelectedId(st.id)}
                                style={{
                                    padding: "16px", borderRadius: 10, cursor: "pointer", marginBottom: 8,
                                    border: `1.5px solid ${isSelected ? C.accent : C.border}`,
                                    background: isSelected ? C.accentLight : C.surface,
                                    transition: "all 0.15s",
                                }}
                            >
                                <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
                                    <div style={{
                                        width: 36, height: 36, borderRadius: 8, display: "flex", alignItems: "center", justifyContent: "center",
                                        background: st.bg, color: st.color, border: `1px solid ${st.border}`
                                    }}>
                                        <Icon size={18} />
                                    </div>
                                    <div style={{ flex: 1 }}>
                                        <div style={{ fontWeight: 600, fontSize: 13, color: isSelected ? C.accent : C.text, marginBottom: 2 }}>{st.label}</div>
                                        <div style={{ fontSize: 11, color: C.subtle }}>Savings: {st.savings}</div>
                                    </div>
                                    {isSelected && <FiCheck size={18} color={C.accent} />}
                                </div>
                            </div>
                        );
                    })}
                </div>
            </div>

            {/* ── DETAIL: Selected Strategy ── */}
            <div style={{ flex: 1, background: C.surface, borderRadius: 12, border: `1px solid ${C.border}`, display: 'flex', flexDirection: 'column' }}>
                <div style={{ padding: '32px' }}>

                    <div style={{ display: "flex", alignItems: "center", gap: 16, marginBottom: 24 }}>
                        <div style={{
                            width: 48, height: 48, borderRadius: 12, display: "flex", alignItems: "center", justifyContent: "center",
                            background: selectedStrategy.bg, color: selectedStrategy.color, border: `1px solid ${selectedStrategy.border}`
                        }}>
                            <selectedStrategy.icon size={24} />
                        </div>
                        <div>
                            <h2 style={{ fontSize: 24, fontWeight: 700, margin: '0 0 4px 0', color: C.text }}>{selectedStrategy.label}</h2>
                            <div style={{ fontSize: 13, color: C.muted }}>{selectedStrategy.desc}</div>
                        </div>
                    </div>

                    <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 12, marginBottom: 32 }}>
                        <div style={{ padding: "16px", borderRadius: 10, border: `1px solid ${C.border}`, background: C.bg }}>
                            <div style={{ fontSize: 11, fontWeight: 600, color: C.subtle, textTransform: "uppercase", marginBottom: 8, display: "flex", alignItems: "center", gap: 6 }}><FiClock /> Wake Time</div>
                            <div style={{ fontSize: 20, fontWeight: 700, color: C.text }}>{selectedStrategy.wakeTime}</div>
                        </div>
                        <div style={{ padding: "16px", borderRadius: 10, border: `1px solid ${C.border}`, background: C.bg }}>
                            <div style={{ fontSize: 11, fontWeight: 600, color: C.subtle, textTransform: "uppercase", marginBottom: 8, display: "flex", alignItems: "center", gap: 6 }}><FiActivity /> Max Savings</div>
                            <div style={{ fontSize: 20, fontWeight: 700, color: '#10b981' }}>{selectedStrategy.savings}</div>
                        </div>
                        <div style={{ padding: "16px", borderRadius: 10, border: `1px solid ${C.border}`, background: C.bg }}>
                            <div style={{ fontSize: 11, fontWeight: 600, color: C.subtle, textTransform: "uppercase", marginBottom: 8, display: "flex", alignItems: "center", gap: 6 }}><FiAlertTriangle /> Risk Profile</div>
                            <div style={{ fontSize: 20, fontWeight: 700, color: selectedStrategy.color }}>{selectedStrategy.risk}</div>
                        </div>
                    </div>

                    <div style={{ fontSize: 13, fontWeight: 700, color: C.text, marginBottom: 16 }}>Mechanism of Action</div>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                        {selectedStrategy.details.map((detail, idx) => (
                            <div key={idx} style={{ display: 'flex', gap: 12, alignItems: 'flex-start' }}>
                                <div style={{ width: 6, height: 6, borderRadius: '50%', background: selectedStrategy.color, marginTop: 7, flexShrink: 0 }} />
                                <div style={{ fontSize: 13, color: '#475569', lineHeight: 1.6 }}>{detail}</div>
                            </div>
                        ))}
                    </div>

                </div>
            </div>
        </div>
    );
}
