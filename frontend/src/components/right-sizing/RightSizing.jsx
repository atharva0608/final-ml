import React, { useState, useEffect } from 'react';
import { useClusterStore } from '../../store/useStore';
import { karpenterAPI } from '../../services/api';
import EmptyState from '../shared/EmptyState';
import { FiGrid, FiCpu, FiLayers } from 'react-icons/fi'; // Icons for tabs

// Sub-views
import ManualRightSizing from './ManualRightSizing';
import KarpenterEnable from './KarpenterEnable';
import KarpenterDashboard from './KarpenterDashboard';
import KarpenterSettings from './KarpenterSettings';

// Note: ModeSelector is deprecated/removed in favor of inline tabs


/**
 * RightSizing — top-level container that orchestrates:
 *   • ModeSelector  (manual vs karpenter toggle)
 *   • ManualRightSizing  (existing manual recommendations view)
 *   • KarpenterEnable    (simplified one-click enablement)
 *   • KarpenterDashboard (post-setup live monitoring)
 *   • KarpenterSettings  (slide-over config panel)
 */
const RightSizing = () => {
    const { selectedCluster } = useClusterStore();

    // ── Mode state ──────────────────────────────────────────────────
    const [mode, setMode] = useState('manual');               // 'manual' | 'karpenter'
    const [karpenterStatus, setKarpenterStatus] = useState(null); // API status object
    const [statusLoading, setStatusLoading] = useState(false);

    // ── Settings slide-over ─────────────────────────────────────────
    const [settingsOpen, setSettingsOpen] = useState(false);

    // ── Fetch Karpenter status on mount / mode switch ───────────────
    useEffect(() => {
        if (mode === 'karpenter') {
            fetchKarpenterStatus();
        }
    }, [mode]);

    const fetchKarpenterStatus = async () => {
        try {
            setStatusLoading(true);
            const res = await karpenterAPI.getStatus();
            setKarpenterStatus(res.data);
        } catch (err) {
            console.error('Failed to fetch Karpenter status:', err);
            setKarpenterStatus({ is_setup: false, status: 'not_setup' });
        } finally {
            setStatusLoading(false);
        }
    };

    // Note: We don't guard on selectedCluster anymore
    // The mode selector and Karpenter work without a cluster selection

    // ── Determine which Karpenter sub-view to show ──────────────────
    const renderKarpenterView = () => {
        if (statusLoading) {
            return (
                <div className="min-h-[300px] flex items-center justify-center">
                    <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-blue-600"></div>
                </div>
            );
        }

        const isActive = karpenterStatus?.status === 'active';
        const isDeploying = karpenterStatus?.status === 'deploying';
        const isSetup = karpenterStatus?.is_setup;

        if (isActive || isDeploying) {
            return (
                <KarpenterDashboard
                    onOpenSettings={() => setSettingsOpen(true)}
                    onPause={fetchKarpenterStatus}
                />
            );
        }

        // Not setup yet → show simple enablement
        return (
            <KarpenterEnable
                onComplete={() => {
                    fetchKarpenterStatus();
                }}
                onCancel={() => setMode('manual')}
            />
        );
    };

    // Helper to determine if Karpenter is considered "enabled" for the UI flow
    const isKarpenterEnabled = karpenterStatus?.is_setup && (karpenterStatus?.status === 'active' || karpenterStatus?.status === 'deploying');

    return (
        <div className="h-full flex flex-col bg-gray-50/50">
            {/* ─── Header & Tabs ────────────────────────────────────────────── */}
            <div className="bg-white border-b border-gray-200 px-8 py-5 flex items-center justify-between sticky top-0 z-30">
                <div>
                    <h1 className="text-2xl font-bold text-gray-900 tracking-tight">Right Sizing</h1>
                    <p className="text-sm text-gray-500 mt-1">Optimize instance types and reduce infrastructure costs.</p>
                </div>

                {/* Segmented Control */}
                <div className="bg-gray-100/80 p-1 rounded-lg flex items-center gap-1">
                    <button
                        onClick={() => setMode('manual')}
                        className={`flex items-center gap-2 px-4 py-2 rounded-md text-sm font-medium transition-all ${mode === 'manual'
                                ? 'bg-white text-gray-900 shadow-sm ring-1 ring-gray-200'
                                : 'text-gray-500 hover:text-gray-700 hover:bg-gray-200/50'
                            }`}
                    >
                        <FiGrid className="w-4 h-4" />
                        <span>Manual</span>
                    </button>
                    <button
                        onClick={() => setMode('karpenter')}
                        className={`flex items-center gap-2 px-4 py-2 rounded-md text-sm font-medium transition-all ${mode === 'karpenter'
                                ? 'bg-white text-blue-600 shadow-sm ring-1 ring-gray-200'
                                : 'text-gray-500 hover:text-gray-700 hover:bg-gray-200/50'
                            }`}
                    >
                        <FiLayers className="w-4 h-4" />
                        <span>Karpenter (Auto)</span>
                    </button>
                </div>
            </div>

            {/* ─── Content ──────────────────────────────────────────────────── */}
            <div className="flex-1 overflow-hidden relative">
                {mode === 'manual' ? (
                    <ManualRightSizing />
                ) : (
                    // Check if Karpenter is enabled at all (if not, show Enable screen, else Dashboard)
                    isKarpenterEnabled ? (
                        <div className="h-full overflow-y-auto">
                            <KarpenterDashboard
                                onOpenSettings={() => setSettingsOpen(true)}
                                onPause={fetchKarpenterStatus}
                            />
                        </div>
                    ) : (
                        <div className="h-full overflow-y-auto p-8">
                            <KarpenterEnable onComplete={fetchKarpenterStatus} onCancel={() => setMode('manual')} />
                        </div>
                    )
                )}
            </div>

            {/* Settings slide-over (always mounted, visibility controlled) */}
            <KarpenterSettings
                isOpen={settingsOpen}
                onClose={() => setSettingsOpen(false)}
                clusters={karpenterStatus?.clusters || []}
                onRefresh={fetchKarpenterStatus}
            />
        </div>
    );
};

export default RightSizing;
