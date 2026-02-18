import React, { useState, useEffect } from 'react';
import {
    FiX, FiServer, FiSettings, FiShield, FiCpu,
    FiBell, FiPlay, FiPause, FiTrash2, FiEdit2,
    FiPlus, FiDownload, FiFileText, FiCheck
} from 'react-icons/fi';
import { Button, Badge } from '../shared';
import { karpenterAPI } from '../../services/api';
import toast from 'react-hot-toast';

/* ─── TABS ───────────────────────────────────────────────────────────────── */

const TABS = [
    { key: 'clusters', label: 'Clusters', icon: <FiServer className="w-3.5 h-3.5" /> },
    { key: 'strategy', label: 'Strategy', icon: <FiSettings className="w-3.5 h-3.5" /> },
    { key: 'instances', label: 'Instances', icon: <FiCpu className="w-3.5 h-3.5" /> },
    { key: 'advanced', label: 'Advanced', icon: <FiShield className="w-3.5 h-3.5" /> },
    { key: 'alerts', label: 'Alerts', icon: <FiBell className="w-3.5 h-3.5" /> },
];

/* ─── Component ──────────────────────────────────────────────────────────── */

/**
 * KarpenterSettings — slide-over panel for post-setup configuration changes.
 *
 * Props:
 *   isOpen    – boolean
 *   onClose   – () => void
 *   clusters  – array of cluster objects with Karpenter config
 *   onRefresh – () => void   (called after applying changes)
 */
const KarpenterSettings = ({ isOpen, onClose, clusters = [], onRefresh }) => {
    const [tab, setTab] = useState('clusters');
    const [saving, setSaving] = useState(false);

    if (!isOpen) return null;

    const handlePauseAll = async () => {
        try {
            await Promise.all(clusters.map(c => karpenterAPI.toggle(c.cluster_id, false)));
            toast.success('All clusters paused');
            onRefresh?.();
        } catch { toast.error('Failed to pause'); }
    };

    const handleResumeAll = async () => {
        try {
            await Promise.all(clusters.map(c => karpenterAPI.toggle(c.cluster_id, true)));
            toast.success('All clusters resumed');
            onRefresh?.();
        } catch { toast.error('Failed to resume'); }
    };

    const handleToggle = async (clusterId, enable) => {
        try {
            await karpenterAPI.toggle(clusterId, enable);
            toast.success(enable ? 'Cluster resumed' : 'Cluster paused');
            onRefresh?.();
        } catch { toast.error('Toggle failed'); }
    };

    /* ─── Tab Content Renderers ───────────────────────────────────── */

    const renderClusters = () => (
        <div className="space-y-3">
            {clusters.map(cl => (
                <div key={cl.cluster_id} className="border border-gray-200 rounded-lg p-4">
                    <div className="flex items-center justify-between mb-2">
                        <div className="flex items-center gap-2">
                            <span className={`inline-block w-2 h-2 rounded-full ${cl.status === 'active' ? 'bg-green-500' : 'bg-yellow-400'}`}></span>
                            <span className="text-sm font-semibold text-gray-900">{cl.name}</span>
                            <Badge variant={cl.status === 'active' ? 'success' : 'warning'}>{cl.status}</Badge>
                        </div>
                        <div className="flex items-center gap-1">
                            <button className="p-1.5 rounded hover:bg-gray-100 text-gray-400 hover:text-gray-600">
                                <FiEdit2 className="w-3.5 h-3.5" />
                            </button>
                            <button
                                className="p-1.5 rounded hover:bg-gray-100 text-gray-400 hover:text-gray-600"
                                onClick={() => handleToggle(cl.cluster_id, cl.status !== 'active')}
                            >
                                {cl.status === 'active' ? <FiPause className="w-3.5 h-3.5" /> : <FiPlay className="w-3.5 h-3.5" />}
                            </button>
                            <button className="p-1.5 rounded hover:bg-red-50 text-gray-400 hover:text-red-500">
                                <FiTrash2 className="w-3.5 h-3.5" />
                            </button>
                        </div>
                    </div>
                    <div className="text-xs text-gray-500 space-y-0.5">
                        <div>Strategy: <span className="capitalize">{cl.strategy}</span></div>
                        <div>Nodes: {cl.nodes} • Spot: {cl.spot_pct}%</div>
                        <div>Region: {cl.region}</div>
                    </div>
                </div>
            ))}

            <button className="w-full border-2 border-dashed border-gray-200 rounded-lg p-3 text-sm text-gray-400 hover:border-blue-300 hover:text-blue-500 transition-colors flex items-center justify-center gap-1.5">
                <FiPlus className="w-4 h-4" /> Add Another Cluster
            </button>
        </div>
    );

    const renderStrategy = () => (
        <div className="space-y-4">
            <p className="text-xs text-gray-500">Change the optimization strategy for each cluster.</p>
            {clusters.map(cl => (
                <div key={cl.cluster_id} className="border border-gray-200 rounded-lg p-4 space-y-2">
                    <div className="text-sm font-semibold text-gray-900">{cl.name}</div>
                    <div className="flex gap-2">
                        {['cost-first', 'balanced', 'performance-first'].map(s => (
                            <button key={s} className={`flex-1 py-2 rounded-lg text-xs font-medium border transition-colors ${cl.strategy === s
                                    ? 'bg-blue-500 text-white border-blue-500'
                                    : 'bg-white text-gray-600 border-gray-200 hover:border-blue-300'
                                }`}>
                                {s.split('-').map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' ')}
                            </button>
                        ))}
                    </div>
                </div>
            ))}
        </div>
    );

    const renderInstances = () => (
        <div className="space-y-4">
            <p className="text-xs text-gray-500">Modify which instance types Karpenter can use.</p>
            <div className="border border-gray-200 rounded-lg p-4 space-y-3">
                <div className="text-sm font-semibold text-gray-900">Allowed Instance Families</div>
                <div className="flex flex-wrap gap-2">
                    {['m5', 'm6i', 'm6a', 'c5', 'c6i', 'c6a', 'r5', 'r6i', 't3', 't4g'].map(t => (
                        <span key={t} className="px-3 py-1 rounded-full text-xs border border-gray-200 bg-gray-50 text-gray-600">{t}</span>
                    ))}
                </div>
                <div className="text-sm font-semibold text-gray-900 mt-3">Architecture</div>
                <div className="flex gap-2">
                    {['AMD64 (x86)', 'ARM64 (Graviton)'].map(a => (
                        <span key={a} className="px-3 py-1 rounded-full text-xs border border-blue-200 bg-blue-50 text-blue-700">{a}</span>
                    ))}
                </div>
            </div>
        </div>
    );

    const renderAdvanced = () => (
        <div className="space-y-4">
            <div className="border border-gray-200 rounded-lg p-4 space-y-3">
                <div className="text-sm font-semibold text-gray-900">Consolidation</div>
                <div className="flex items-center gap-2 text-xs text-gray-600">
                    <FiCheck className="w-3.5 h-3.5 text-green-500" /> Enabled at 60% threshold
                </div>
            </div>
            <div className="border border-gray-200 rounded-lg p-4 space-y-3">
                <div className="text-sm font-semibold text-gray-900">Node Lifecycle</div>
                <div className="text-xs text-gray-600">Max lifetime: 7 days • Rotation: Gradual</div>
            </div>
            <div className="border border-gray-200 rounded-lg p-4 space-y-3">
                <div className="text-sm font-semibold text-gray-900">Workload Protection</div>
                <div className="text-xs text-gray-600 space-y-0.5">
                    <div><FiCheck className="inline w-3 h-3 text-green-500 mr-1" />Respect PodDisruptionBudgets</div>
                    <div><FiCheck className="inline w-3 h-3 text-green-500 mr-1" />Respect node affinity</div>
                    <div><FiCheck className="inline w-3 h-3 text-green-500 mr-1" />Drain nodes gracefully (90s timeout)</div>
                </div>
            </div>
        </div>
    );

    const renderAlerts = () => (
        <div className="space-y-4">
            <div className="border border-gray-200 rounded-lg p-4 space-y-3">
                <div className="text-sm font-semibold text-gray-900">Cost Alerts</div>
                <div className="text-xs text-gray-600">
                    <div><FiCheck className="inline w-3 h-3 text-green-500 mr-1" />Monthly cost alert: $5,000</div>
                    <div><FiCheck className="inline w-3 h-3 text-green-500 mr-1" />Hourly instance limit: $2.00</div>
                    <div><FiCheck className="inline w-3 h-3 text-green-500 mr-1" />Daily budget: $200</div>
                </div>
            </div>
            <div className="border border-gray-200 rounded-lg p-4 space-y-3">
                <div className="text-sm font-semibold text-gray-900">Notification Channels</div>
                <div className="text-xs text-gray-600">Email + Slack</div>
            </div>
        </div>
    );

    const tabContent = {
        clusters: renderClusters,
        strategy: renderStrategy,
        instances: renderInstances,
        advanced: renderAdvanced,
        alerts: renderAlerts,
    };

    return (
        <>
            {/* Backdrop */}
            <div className="fixed inset-0 bg-black/30 z-40" onClick={onClose} />

            {/* Panel */}
            <div className="fixed inset-y-0 right-0 w-full max-w-lg bg-white shadow-xl z-50 flex flex-col animate-slide-in-right">
                {/* Header */}
                <div className="flex items-center justify-between px-5 py-4 border-b border-gray-200">
                    <h3 className="text-lg font-bold text-gray-900">Karpenter Settings</h3>
                    <div className="flex items-center gap-2">
                        <Button variant="primary" size="sm" disabled={saving} onClick={() => { toast.success('Settings applied'); onClose(); }}>
                            Apply
                        </Button>
                        <button onClick={onClose} className="text-gray-400 hover:text-gray-600">
                            <FiX className="w-5 h-5" />
                        </button>
                    </div>
                </div>

                {/* Tabs */}
                <div className="flex border-b border-gray-200 px-5 gap-1 overflow-x-auto">
                    {TABS.map(t => (
                        <button
                            key={t.key}
                            onClick={() => setTab(t.key)}
                            className={`flex items-center gap-1.5 px-3 py-2.5 text-xs font-medium border-b-2 transition-colors whitespace-nowrap ${tab === t.key
                                    ? 'border-blue-500 text-blue-600'
                                    : 'border-transparent text-gray-500 hover:text-gray-700'
                                }`}
                        >
                            {t.icon} {t.label}
                        </button>
                    ))}
                </div>

                {/* Content */}
                <div className="flex-1 overflow-y-auto p-5">
                    {tabContent[tab]?.()}
                </div>

                {/* Quick actions */}
                <div className="border-t border-gray-200 px-5 py-3 flex items-center gap-2">
                    <Button variant="outline" size="xs" onClick={handlePauseAll}>Pause All</Button>
                    <Button variant="outline" size="xs" onClick={handleResumeAll}>Resume All</Button>
                    <Button variant="outline" size="xs" onClick={() => toast('Config exported')}>
                        <FiDownload className="w-3 h-3 mr-1" /> Export
                    </Button>
                    <Button variant="outline" size="xs" onClick={() => toast('Logs panel coming soon')}>
                        <FiFileText className="w-3 h-3 mr-1" /> Logs
                    </Button>
                </div>
            </div>
        </>
    );
};

export default KarpenterSettings;
