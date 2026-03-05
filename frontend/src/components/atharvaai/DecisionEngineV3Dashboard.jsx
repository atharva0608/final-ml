import React, { useState, useEffect } from 'react';
import { decisionEngineAPI, clusterAPI, atharvaaiAPI, poolRotationAPI, metricsAPI, atharvaAiAPI } from '../../services/api';
import OptimizationModeSelector from './OptimizationModeSelector';
import { toast } from 'react-hot-toast';
import { FiActivity, FiSliders, FiCpu, FiRefreshCw } from 'react-icons/fi';

const DecisionEngineV3Dashboard = ({ clusterId, clusterRegion = 'ap-south-1', cluster }) => {
    const [stateMachine, setStateMachine] = useState(null);
    const [metrics, setMetrics] = useState(null);
    const [loading, setLoading] = useState(true);
    const [unifiedConfig, setUnifiedConfig] = useState(null);
    const [effectiveConfig, setEffectiveConfig] = useState(null);
    const [saving, setSaving] = useState(false);

    // Task 7.3: Pool Rotation Status
    const [poolRotation, setPoolRotation] = useState(null);
    // Task 7.4: AtharvaAI Health
    const [aiHealth, setAiHealth] = useState(null);
    // Task 7.6: Rejection Counters
    const [rejectionCounters, setRejectionCounters] = useState(null);
    // Substitute live state
    const [substituteStatus, setSubstituteStatus] = useState(null);

    const [config, setConfig] = useState({
        rightsizing: cluster?.rightsizing_enabled || false,
        autoRebalance: cluster?.auto_rebalance_enabled || false
    });

    useEffect(() => {
        if (cluster) {
            setConfig({
                rightsizing: cluster.rightsizing_enabled || false,
                autoRebalance: cluster.auto_rebalance_enabled || false
            });
        }
    }, [cluster]);

    const handleConfigToggle = async (key) => {
        const newValue = !config[key];
        setConfig(prev => ({ ...prev, [key]: newValue }));
        try {
            const payload = {};
            if (key === 'rightsizing') payload.rightsizing_enabled = newValue;
            if (key === 'autoRebalance') payload.auto_rebalance_enabled = newValue;
            await clusterAPI.updateCluster(clusterId, payload);
            window.dispatchEvent(new Event('refresh-clusters'));
        } catch (err) {
            setConfig(prev => ({ ...prev, [key]: !newValue }));
            console.error('Failed to update config:', err);
        }
    };

    useEffect(() => {
        const fetchData = async () => {
            try {
                const [stateRes, metricsRes, configRes, effectiveRes] = await Promise.all([
                    decisionEngineAPI.getStateMachine(clusterId),
                    decisionEngineAPI.getDecisionMetrics(),
                    clusterAPI.getOptimizationSettings(clusterId).catch(() => ({ data: null })),
                    atharvaaiAPI.getEffectiveConfiguration(clusterId).catch(() => ({ data: null }))
                ]);

                setStateMachine(stateRes.data);
                setMetrics(metricsRes.data);
                if (effectiveRes.data) setEffectiveConfig(effectiveRes.data);

                const c = configRes.data || {
                    automation_controls: { auto_rebalance_enabled: false, auto_rightsizing_enabled: false, conservative_mode_enabled: true, manual_approval_required: false },
                    optimization_strategy: { strategy_type: 'BALANCED', risk_ceiling_percent: 25, min_savings_percent: 15, volatility_tolerance_percent: 20, migration_penalty_multiplier: 1.5, diversity_strictness_level: 'Medium' },
                    stateless_rules: { spot_target_percent: 100, instance_diversification_enabled: true, respect_pdb_enabled: true, prewarm_minutes: 0, substitute_strategy: 'PREWARMED', max_rebalances_per_24h: 5, resize_cooldown_minutes: 120, resize_headroom_multiplier: 1.2, volatility_safety_multiplier: 1.35, fresh_cluster_stabilization_minutes: 1440 },
                    stateful_rules: { manual_resize_allowed: true, show_ondemand_only: true, require_approval: true, block_spot_for_stateful: true, max_downscale_percent: 25 }
                };
                setUnifiedConfig(c);

                // Task 7.3: Pool Rotation Status
                poolRotationAPI.getStatus(clusterId)
                    .then(res => setPoolRotation(res.data))
                    .catch(() => setPoolRotation(null));

                // Task 7.4: AtharvaAI Health
                atharvaAiAPI.getHealth()
                    .then(res => setAiHealth(res.data))
                    .catch(() => setAiHealth(null));

                // Task 7.6: Rejection Counters
                metricsAPI.getRejectionCounters(clusterId)
                    .then(res => setRejectionCounters(res.data))
                    .catch(() => setRejectionCounters(null));

                // Substitute live state (PREWARMING / READY / ACTIVE / RELEASING / IDLE)
                decisionEngineAPI.getSubstituteStatusV3(clusterId)
                    .then(res => setSubstituteStatus(res.data))
                    .catch(() => setSubstituteStatus(null));
            } catch (err) {
                console.error('Failed to fetch decision engine data:', err);
            } finally {
                setLoading(false);
            }
        };

        if (clusterId) {
            fetchData();
            const interval = setInterval(fetchData, 30000);
            return () => clearInterval(interval);
        }
    }, [clusterId]);


    const handleConfigChange = (section, key, value) => {
        setUnifiedConfig(prev => ({
            ...prev,
            [section]: {
                ...prev[section],
                [key]: value
            }
        }));
    };

    const saveConfig = async () => {
        setSaving(true);
        try {
            await clusterAPI.updateOptimizationSettings(clusterId, unifiedConfig);
            toast.success("Optimization settings saved successfully!");
        } catch (err) {
            console.error("Failed to save config:", err);
            toast.error("Failed to save settings");
        } finally {
            setSaving(false);
        }
    };

    if (!clusterId || !unifiedConfig) {
        return (
            <div className="p-8 text-center text-gray-500">
                Select a cluster to view Decision Engine v3 telemetry
            </div>
        );
    }

    return (
        <div className="space-y-8 mt-8 border-t pt-8">
            {/* Automation Controls removed as requested */}
            {/* Effective Configuration Summary & Execution Flow */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                {/* Flow Diagram Mini-Panel */}
                <div className="bg-gradient-to-br from-indigo-50 to-blue-50 rounded-xl shadow-sm border border-indigo-100 p-6 flex flex-col justify-center">
                    <h4 className="text-sm font-semibold text-indigo-900 mb-4 uppercase tracking-wider">Execution Pipeline Precedence</h4>
                    <div className="space-y-3 relative">
                        {/* Connecting line */}
                        <div className="absolute left-[15px] top-[20px] bottom-[20px] w-0.5 bg-indigo-200"></div>

                        <div className="flex items-center relative z-10">
                            <div className="w-8 h-8 rounded-full bg-indigo-600 text-white flex items-center justify-center font-bold text-sm shadow-md ring-4 ring-indigo-50 z-10">1</div>
                            <div className="ml-4 flex-1 bg-white px-4 py-2 rounded-lg shadow-sm border border-indigo-100"><span className="font-semibold text-gray-900">Cluster Policy</span><span className="block text-xs text-gray-500">Global Overrides & Targets</span></div>
                        </div>
                        <div className="flex items-center relative z-10">
                            <div className="w-8 h-8 rounded-full bg-blue-500 text-white flex items-center justify-center font-bold text-sm shadow-md ring-4 ring-blue-50 z-10">2</div>
                            <div className="ml-4 flex-1 bg-white px-4 py-2 rounded-lg shadow-sm border border-blue-100"><span className="font-semibold text-gray-900">Node Template</span><span className="block text-xs text-gray-500">Hardware & Capacity Constraints</span></div>
                        </div>
                        <div className="flex items-center relative z-10">
                            <div className="w-8 h-8 rounded-full bg-indigo-400 text-white flex items-center justify-center font-bold text-sm shadow-md ring-4 ring-indigo-50 z-10">3</div>
                            <div className="ml-4 flex-1 bg-white px-4 py-2 rounded-lg shadow-sm border border-indigo-100"><span className="font-semibold text-gray-900">Optimization Strategy</span><span className="block text-xs text-gray-500">Risk vs Cost Math Scoring</span></div>
                        </div>
                    </div>
                </div>

                {/* Effective Config Card */}
                {effectiveConfig && (
                    <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6 lg:col-span-2">
                        <div className="flex items-center justify-between mb-6">
                            <h4 className="text-lg font-semibold text-gray-900 flex items-center">
                                <FiActivity className="mr-2 text-indigo-600" />
                                Effective Optimization Summary
                            </h4>
                            <span className="text-xs font-medium px-2 py-1 bg-green-100 text-green-700 rounded-full flex items-center"><div className="w-2 h-2 rounded-full bg-green-500 mr-1.5 animate-pulse"></div>Live Merged View</span>
                        </div>
                        <div className="grid grid-cols-2 md:grid-cols-3 gap-6">
                            <div>
                                <p className="text-xs text-gray-500 mb-1">Stateful spot</p>
                                <p className="font-semibold text-gray-900">{effectiveConfig.stateful_spot}</p>
                            </div>
                            <div>
                                <p className="text-xs text-gray-500 mb-1">Active Template</p>
                                <p className="font-semibold text-indigo-600">{effectiveConfig.template}</p>
                            </div>
                            <div>
                                <p className="text-xs text-gray-500 mb-1">Risk Strategy</p>
                                <p className="font-semibold text-gray-900">{effectiveConfig.strategy}</p>
                            </div>
                            <div>
                                <p className="text-xs text-gray-500 mb-1">Target Spot Exposure</p>
                                <p className="font-semibold text-gray-900">{effectiveConfig.target_spot_exposure_pct}%</p>
                            </div>
                            <div>
                                <p className="text-xs text-gray-500 mb-1">Substitute Mode</p>
                                <p className="font-semibold text-gray-900">{effectiveConfig.substitute_mode}</p>
                            </div>
                            <div>
                                <p className="text-xs text-gray-500 mb-1">Auto-Rebalance Mode</p>
                                <p className={`font-semibold ${effectiveConfig.auto_rebalance === 'ON' ? 'text-green-600' : 'text-gray-500'}`}>{effectiveConfig.auto_rebalance}</p>
                            </div>
                        </div>
                    </div>
                )}
            </div>

            {/* Task 7.4: AtharvaAI Health Status */}
            {aiHealth && (
                <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
                    <h4 className="text-lg font-semibold text-gray-900 mb-4 flex items-center">
                        <FiActivity className="mr-2 text-green-600" />
                        ASCP.ai Engine Health
                    </h4>
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                        <div className={`p-4 rounded-lg ${aiHealth.status === 'active' ? 'bg-green-50' : aiHealth.status === 'degraded' ? 'bg-yellow-50' : 'bg-red-50'}`}>
                            <div className="text-xs text-gray-500 mb-1">ML Model Status</div>
                            <div className={`text-lg font-bold ${aiHealth.status === 'active' ? 'text-green-600' : aiHealth.status === 'degraded' ? 'text-yellow-600' : 'text-red-600'}`}>
                                {aiHealth.status?.toUpperCase() || 'UNKNOWN'}
                            </div>
                        </div>
                        <div className="p-4 bg-gray-50 rounded-lg">
                            <div className="text-xs text-gray-500 mb-1">Fail Count</div>
                            <div className="text-lg font-bold text-gray-900">{aiHealth.ml_fail_count || 0}</div>
                        </div>
                        <div className="p-4 bg-gray-50 rounded-lg">
                            <div className="text-xs text-gray-500 mb-1">Degraded</div>
                            <div className={`text-lg font-bold ${aiHealth.ml_degraded ? 'text-yellow-600' : 'text-green-600'}`}>
                                {aiHealth.ml_degraded ? 'YES' : 'NO'}
                            </div>
                        </div>
                        <div className="p-4 bg-gray-50 rounded-lg">
                            <div className="text-xs text-gray-500 mb-1">Model Version</div>
                            <div className="text-lg font-bold text-indigo-600">{aiHealth.model_version || 'v6'}</div>
                        </div>
                    </div>
                </div>
            )}

            {/* Warm Spare Substitute Status */}
            {substituteStatus && (() => {
                const state = substituteStatus.state || 'IDLE';
                const isWarmSpare = substituteStatus.is_warm_spare;
                const stateCfg = {
                    PREWARMING: { label: 'PREWARMING', color: 'text-amber-700', bg: 'bg-amber-50', border: 'border-amber-300', dot: 'bg-amber-500', pulse: true },
                    READY: { label: 'READY — WARM', color: 'text-green-700', bg: 'bg-green-50', border: 'border-green-300', dot: 'bg-green-500', pulse: false },
                    ACTIVE: { label: 'IN USE', color: 'text-indigo-700', bg: 'bg-indigo-50', border: 'border-indigo-300', dot: 'bg-indigo-500', pulse: true },
                    RELEASING: { label: 'RELEASING', color: 'text-orange-700', bg: 'bg-orange-50', border: 'border-orange-300', dot: 'bg-orange-500', pulse: true },
                    IDLE: { label: 'IDLE', color: 'text-gray-500', bg: 'bg-gray-50', border: 'border-gray-200', dot: 'bg-gray-400', pulse: false },
                }[state] || { label: state, color: 'text-gray-500', bg: 'bg-gray-50', border: 'border-gray-200', dot: 'bg-gray-400', pulse: false };
                return (
                    <div className={`rounded-xl shadow-sm border p-6 ${stateCfg.bg} ${stateCfg.border}`}>
                        <div className="flex items-center justify-between mb-1">
                            <h4 className="text-lg font-semibold text-gray-900 flex items-center">
                                <FiCpu className="mr-2 text-indigo-600" />
                                Warm Spare Node
                            </h4>
                            <span className={`inline-flex items-center gap-1.5 text-xs font-bold px-3 py-1 rounded-full border ${stateCfg.bg} ${stateCfg.border} ${stateCfg.color}`}>
                                <span className={`w-2 h-2 rounded-full ${stateCfg.dot} ${stateCfg.pulse ? 'animate-pulse' : ''}`}></span>
                                {stateCfg.label}
                            </span>
                        </div>
                        {isWarmSpare && (
                            <p className="text-xs text-gray-500 mb-4">
                                Running 24x7 · Compatible with any cluster node · Drain → reschedule in &lt;30s
                            </p>
                        )}

                        {state === 'IDLE' ? (
                            <p className="text-sm text-gray-500 mt-2">
                                No warm spare yet. Enable <strong>Auto Rebalance</strong> in Cluster Settings — the system will provision a spot spare within 5 minutes.
                            </p>
                        ) : (
                            <>
                                <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3">
                                    <div className="p-3 bg-white rounded-lg shadow-sm border border-gray-100">
                                        <div className="text-xs text-gray-500 mb-1">Spare Instance</div>
                                        <div className="text-sm font-bold text-gray-900">{substituteStatus.spare_instance_type || '—'}</div>
                                    </div>
                                    <div className="p-3 bg-white rounded-lg shadow-sm border border-gray-100">
                                        <div className="text-xs text-gray-500 mb-1">AZ</div>
                                        <div className="text-sm font-bold text-gray-900">{substituteStatus.spare_az || '—'}</div>
                                    </div>
                                    <div className="p-3 bg-white rounded-lg shadow-sm border border-gray-100">
                                        <div className="text-xs text-gray-500 mb-1">Spot Cost</div>
                                        <div className="text-sm font-bold text-green-700">
                                            {substituteStatus.spot_price_hourly ? `$${substituteStatus.spot_price_hourly}/hr` : '—'}
                                        </div>
                                        <div className="text-xs text-gray-400">
                                            {substituteStatus.monthly_cost ? `~$${substituteStatus.monthly_cost}/mo` : ''}
                                        </div>
                                    </div>
                                    <div className="p-3 bg-white rounded-lg shadow-sm border border-gray-100">
                                        <div className="text-xs text-gray-500 mb-1">Sized For</div>
                                        <div className="text-sm font-bold text-gray-900">
                                            {substituteStatus.target_vcpu ? `${substituteStatus.target_vcpu} vCPU / ${substituteStatus.target_memory_gb} GB` : '—'}
                                        </div>
                                        <div className="text-xs text-gray-400">{substituteStatus.target_node_instance_type || ''}</div>
                                    </div>
                                </div>
                                {substituteStatus.compatible_with && (
                                    <div className="text-xs text-indigo-700 bg-indigo-50 rounded-lg px-3 py-2 mb-2 font-medium">
                                        ✓ {substituteStatus.compatible_with} — can absorb drain of any node in this cluster
                                    </div>
                                )}
                            </>
                        )}

                        {state === 'READY' && (
                            <div className="mt-2 p-3 bg-green-100 rounded-lg text-xs text-green-800 font-medium">
                                ✅ Spare is warm and ready. When any node needs draining: pods reschedule here instantly — no new node spin-up wait.
                            </div>
                        )}
                        {state === 'ACTIVE' && (
                            <>
                                <div className="mt-2 p-3 bg-indigo-100 rounded-lg text-xs text-indigo-800 font-medium">
                                    ⚡ Spare is IN USE — currently absorbing a node migration. A replacement spare is being provisioned.
                                </div>
                                {substituteStatus.next_spare && (
                                    <div className="mt-2 p-3 bg-amber-100 rounded-lg text-xs text-amber-800 font-medium flex items-center gap-2">
                                        <span className="w-2 h-2 rounded-full bg-amber-500 animate-pulse inline-block"></span>
                                        Replacement spare prewarming: {substituteStatus.next_spare.instance_type} in {substituteStatus.next_spare.az}
                                    </div>
                                )}
                            </>
                        )}
                        {state === 'PREWARMING' && (
                            <div className="mt-2 p-3 bg-amber-100 rounded-lg text-xs text-amber-800 font-medium">
                                ⏳ Provisioning warm spare in {substituteStatus.spare_az || 'target AZ'}. Will be READY within ~2 minutes once Kubernetes marks the node healthy.
                            </div>
                        )}
                    </div>
                );
            })()}

            {/* Task 7.3: Pool Rotation Status */}
            {poolRotation && (
                <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
                    <h4 className="text-lg font-semibold text-gray-900 mb-4 flex items-center">
                        <FiRefreshCw className="mr-2 text-blue-600" />
                        Pool Rotation Status
                    </h4>
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                        <div className="p-4 bg-blue-50 rounded-lg">
                            <div className="text-xs text-gray-500 mb-1">Primary AZ</div>
                            <div className="text-lg font-bold text-blue-700">{poolRotation.primary_az || '—'}</div>
                        </div>
                        <div className="p-4 bg-gray-50 rounded-lg">
                            <div className="text-xs text-gray-500 mb-1">Last Rotation</div>
                            <div className="text-sm font-semibold text-gray-900">
                                {poolRotation.last_rotation_at ? new Date(poolRotation.last_rotation_at).toLocaleString() : 'Never'}
                            </div>
                        </div>
                        <div className="p-4 bg-gray-50 rounded-lg">
                            <div className="text-xs text-gray-500 mb-1">Trigger Reason</div>
                            <div className="text-sm font-semibold text-gray-900">{poolRotation.trigger_reason || '—'}</div>
                        </div>
                        <div className="p-4 bg-gray-50 rounded-lg">
                            <div className="text-xs text-gray-500 mb-1">Next Eligible</div>
                            <div className="text-sm font-semibold text-gray-900">
                                {poolRotation.next_eligible_at ? new Date(poolRotation.next_eligible_at).toLocaleString() : 'Now'}
                            </div>
                        </div>
                    </div>
                </div>
            )}

            {/* Task 7.6: Rejection Counters */}
            {rejectionCounters && rejectionCounters.counters && Object.keys(rejectionCounters.counters).length > 0 && (
                <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
                    <div className="flex items-center justify-between mb-4">
                        <h4 className="text-lg font-semibold text-gray-900 flex items-center">
                            <FiActivity className="mr-2 text-amber-600" />
                            Decision Rejection Breakdown (24h)
                        </h4>
                        {rejectionCounters.resets_in_hours && (
                            <span className="text-xs text-gray-500">Resets in {rejectionCounters.resets_in_hours}h</span>
                        )}
                    </div>
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                        {Object.entries(rejectionCounters.counters).map(([reason, count]) => {
                            let color = 'text-gray-600';
                            let bg = 'bg-gray-50';
                            if (reason.includes('catastrophic')) { color = count > 0 ? 'text-red-600' : 'text-green-600'; bg = count > 0 ? 'bg-red-50' : 'bg-green-50'; }
                            else if (reason.includes('pricing') || reason.includes('diversity')) { color = 'text-yellow-600'; bg = 'bg-yellow-50'; }
                            else if (reason.includes('ev_not')) { color = 'text-blue-600'; bg = 'bg-blue-50'; }
                            return (
                                <div key={reason} className={`p-3 rounded-lg ${bg}`}>
                                    <div className="text-xs text-gray-500 mb-1 truncate" title={reason}>{reason.replace(/_/g, ' ')}</div>
                                    <div className={`text-xl font-bold ${color}`}>{count}</div>
                                </div>
                            );
                        })}
                    </div>
                </div>
            )}

            <div className="mb-6">
                <h3 className="text-xl font-bold text-gray-900 flex items-center">
                    <FiSliders className="mr-2 text-gray-600" />
                    Optimization Policies (Strategy Layer)
                </h3>
                <p className="text-sm text-gray-500 mt-1">
                    This section controls how Expected Value (EV) is calculated to rank candidates, not when optimization executes.
                </p>
            </div>

            {/* Optimization Strategy */}
            <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
                <h4 className="text-lg font-semibold text-gray-900 mb-4 flex items-center">
                    <FiSliders className="mr-2 text-gray-500" />
                    Optimization Strategy Profiles
                </h4>

                <OptimizationModeSelector
                    clusterId={clusterId}
                    currentMode={stateMachine?.optimization_mode || 'BALANCED'}
                    onModeChange={() => {
                        decisionEngineAPI.getStateMachine(clusterId).then(res => setStateMachine(res.data));
                    }}
                />

                {/* Advanced EV Controls - Only show when CUSTOM mode is active */}
                {stateMachine && stateMachine.optimization_mode === 'CUSTOM' && (
                    <div className="mt-8 border-t pt-6">
                        <h5 className="font-semibold text-gray-900 mb-4 flex items-center justify-between">
                            <span>Expected Value (EV) Calculation Parameters</span>
                            <span className="text-xs font-medium px-2 py-1 bg-purple-100 text-purple-700 rounded-full">Custom Profile (Advanced)</span>
                        </h5>

                        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                            <div>
                                <label className="block text-sm font-medium text-gray-700 mb-1">Risk Ceiling %</label>
                                <input type="number" value={unifiedConfig.optimization_strategy.risk_ceiling_percent} onChange={e => handleConfigChange("optimization_strategy", "risk_ceiling_percent", +e.target.value)} className="w-full border-gray-300 rounded-md shadow-sm sm:text-sm" />
                                <p className="text-xs text-gray-500 mt-1">Maximum acceptable risk score.</p>
                            </div>
                            <div>
                                <label className="block text-sm font-medium text-gray-700 mb-1">Minimum Savings %</label>
                                <input type="number" value={unifiedConfig.optimization_strategy.min_savings_percent} onChange={e => handleConfigChange("optimization_strategy", "min_savings_percent", +e.target.value)} className="w-full border-gray-300 rounded-md shadow-sm sm:text-sm" />
                                <p className="text-xs text-gray-500 mt-1">Required delta to trigger action.</p>
                            </div>
                            <div>
                                <label className="block text-sm font-medium text-gray-700 mb-1">Volatility Tolerance %</label>
                                <input type="number" value={unifiedConfig.optimization_strategy.volatility_tolerance_percent} onChange={e => handleConfigChange("optimization_strategy", "volatility_tolerance_percent", +e.target.value)} className="w-full border-gray-300 rounded-md shadow-sm sm:text-sm" />
                                <p className="text-xs text-gray-500 mt-1">Allowed market interruption rate.</p>
                            </div>
                            <div>
                                <label className="block text-sm font-medium text-gray-700 mb-1">Migration Penalty Multiplier</label>
                                <input type="number" step="0.1" value={unifiedConfig.optimization_strategy.migration_penalty_multiplier} onChange={e => handleConfigChange("optimization_strategy", "migration_penalty_multiplier", +e.target.value)} className="w-full border-gray-300 rounded-md shadow-sm sm:text-sm" />
                                <p className="text-xs text-gray-500 mt-1">Cost penalty weight for pod eviction.</p>
                            </div>
                            <div>
                                <label className="block text-sm font-medium text-gray-700 mb-1">Diversity Strictness Level</label>
                                <select className="w-full border-gray-300 rounded-md shadow-sm sm:text-sm" value={unifiedConfig.optimization_strategy.diversity_strictness_level} onChange={e => handleConfigChange("optimization_strategy", "diversity_strictness_level", e.target.value)}>
                                    <option>Low (Best Effort)</option>
                                    <option>Medium (Standard)</option>
                                    <option>High (Strict Enforcement)</option>
                                </select>
                                <p className="text-xs text-gray-500 mt-1">Enforcement level for spot fleet diversity.</p>
                            </div>
                        </div>
                    </div>
                )}
            </div>
            <div className="mt-12 mb-6">
                <h3 className="text-xl font-bold text-gray-900 flex items-center">
                    <FiCpu className="mr-2 text-blue-600" />
                    Workload Optimization Rules
                </h3>
                <p className="text-sm text-gray-500 mt-1">
                    These are runtime execution rules. They apply only when top-level toggles allow.
                </p>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
                {/* Stateless Rules */}
                <div className="bg-white rounded-xl shadow-sm border border-blue-200 p-6">
                    <div className="flex items-center justify-between mb-6">
                        <h4 className="text-lg font-semibold text-blue-900 flex items-center">
                            Stateless Optimization Rules
                        </h4>
                        <div className="flex gap-2">
                            <span className="text-xs font-medium px-2 py-1 bg-blue-100 text-blue-700 rounded-full border border-blue-200">Automated Execution</span>
                            <span className="text-xs font-medium px-2 py-1 bg-indigo-100 text-indigo-700 rounded-full border border-indigo-200 shadow-sm flex items-center">Source: Cluster Policy</span>
                        </div>
                    </div>

                    <div className="space-y-5">
                        <div className="flex justify-between items-center border-b pb-4">
                            <div>
                                <h5 className="text-sm font-medium text-gray-900">Instance Diversification</h5>
                                <p className="text-xs text-gray-500">Require multiple instance families for spot pools.</p>
                            </div>
                            <label className="relative inline-flex items-center cursor-pointer">
                                <input type="checkbox" className="sr-only peer" checked={unifiedConfig.stateless_rules.instance_diversification_enabled} onChange={e => handleConfigChange("stateless_rules", "instance_diversification_enabled", e.target.checked)} />
                                <div className="w-9 h-5 bg-gray-200 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-blue-600"></div>
                            </label>
                        </div>

                        <div className="flex justify-between items-center border-b pb-4">
                            <div>
                                <h5 className="text-sm font-medium text-gray-900">Substitute Strategy</h5>
                                <p className="text-xs text-gray-500">How replacement instances are provisioned.</p>
                            </div>
                            <select className="border-gray-300 rounded-md shadow-sm sm:text-sm w-36" value={unifiedConfig.stateless_rules.substitute_strategy} onChange={e => handleConfigChange("stateless_rules", "substitute_strategy", e.target.value)}>
                                <option>PREWARMED</option>
                                <option>ON_DEMAND</option>
                            </select>
                        </div>

                        <div className="flex justify-between items-center border-b pb-4">
                            <div>
                                <h5 className="text-sm font-medium text-gray-900">Respect PDBs</h5>
                                <p className="text-xs text-gray-500">Strictly adhere to PodDisruptionBudgets.</p>
                            </div>
                            <label className="relative inline-flex items-center cursor-pointer">
                                <input type="checkbox" className="sr-only peer" checked={unifiedConfig.stateless_rules.respect_pdb_enabled} onChange={e => handleConfigChange("stateless_rules", "respect_pdb_enabled", e.target.checked)} />
                                <div className="w-9 h-5 bg-gray-200 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-blue-600"></div>
                            </label>
                        </div>

                        <div className="flex justify-between items-center border-b pb-4">
                            <div>
                                <h5 className="text-sm font-medium text-gray-900">Max Rebalances per 24h</h5>
                                <p className="text-xs text-gray-500">Limit daily churn for stable workloads.</p>
                            </div>
                            <input type="number" value={unifiedConfig.stateless_rules.max_rebalances_per_24h} onChange={e => handleConfigChange("stateless_rules", "max_rebalances_per_24h", +e.target.value)} className="w-20 border-gray-300 rounded-md shadow-sm sm:text-sm text-right" />
                        </div>

                        <div className="flex justify-between items-center border-b pb-4">
                            <div>
                                <h5 className="text-sm font-medium text-gray-900">Resize Headroom Multiplier</h5>
                                <p className="text-xs text-gray-500">Amount of buffer capacity to maintain after resizing.</p>
                            </div>
                            <input type="number" step="0.1" value={unifiedConfig.stateless_rules.resize_headroom_multiplier} onChange={e => handleConfigChange("stateless_rules", "resize_headroom_multiplier", +e.target.value)} className="w-20 border-gray-300 rounded-md shadow-sm sm:text-sm text-right" />
                        </div>

                        <div className="flex justify-between items-center">
                            <div>
                                <h5 className="text-sm font-medium text-gray-900">Volatility Safety Multiplier</h5>
                                <p className="text-xs text-gray-500">Extra headroom applied during high market volatility.</p>
                            </div>
                            <input type="number" step="0.05" value={unifiedConfig.stateless_rules.volatility_safety_multiplier} onChange={e => handleConfigChange("stateless_rules", "volatility_safety_multiplier", +e.target.value)} className="w-20 border-gray-300 rounded-md shadow-sm sm:text-sm text-right" />
                        </div>
                    </div>
                </div>

                {/* Stateful Rules */}
                <div className="bg-gray-50 rounded-xl shadow-sm border border-gray-300 p-6 relative overflow-hidden">
                    <div className="absolute top-0 right-0 w-16 h-16 bg-gradient-to-bl from-gray-200 to-transparent"></div>

                    <div className="flex items-center justify-between mb-6">
                        <h4 className="text-lg font-semibold text-gray-800 flex items-center">
                            Stateful Optimization Rules
                        </h4>
                        <div className="flex gap-2">
                            <span className="text-xs font-medium px-2 py-1 bg-gray-200 text-gray-600 rounded-full border border-gray-300">Manual Only</span>
                            <span className="text-xs font-medium px-2 py-1 bg-indigo-100 text-indigo-700 rounded-full border border-indigo-200 shadow-sm flex items-center">Source: Cluster Policy</span>
                        </div>
                    </div>

                    <div className="space-y-5">
                        <div className="flex justify-between items-center border-b border-gray-200 pb-4">
                            <div>
                                <h5 className="text-sm font-medium text-gray-800">Allow Manual Resize</h5>
                                <p className="text-xs text-gray-500">Generate manual rightsizing recommendations.</p>
                            </div>
                            <label className="relative inline-flex items-center cursor-pointer">
                                <input type="checkbox" className="sr-only peer" checked={unifiedConfig.stateful_rules.manual_resize_allowed} onChange={e => handleConfigChange("stateful_rules", "manual_resize_allowed", e.target.checked)} />
                                <div className="w-9 h-5 bg-gray-300 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-400 after:border after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-gray-700"></div>
                            </label>
                        </div>

                        <div className="flex justify-between items-center border-b border-gray-200 pb-4">
                            <div>
                                <h5 className="text-sm font-medium text-gray-800">Show On-Demand Savings Only</h5>
                                <p className="text-xs text-gray-500">Do not calculate savings based on Spot pricing.</p>
                            </div>
                            <label className="relative inline-flex items-center cursor-pointer">
                                <input type="checkbox" className="sr-only peer" checked={unifiedConfig.stateful_rules.show_ondemand_only} onChange={e => handleConfigChange("stateful_rules", "show_ondemand_only", e.target.checked)} />
                                <div className="w-9 h-5 bg-gray-300 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-400 after:border after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-gray-700"></div>
                            </label>
                        </div>

                        <div className="flex justify-between items-center border-b border-gray-200 pb-4">
                            <div>
                                <h5 className="text-sm font-medium text-gray-800">Block Spot for Stateful</h5>
                                <p className="text-xs text-gray-500">Strictly forbid migrating statful pods to spot nodes.</p>
                            </div>
                            <label className="relative inline-flex items-center cursor-not-allowed opacity-70">
                                <input type="checkbox" className="sr-only peer" checked={true} disabled />
                                <div className="w-9 h-5 bg-gray-300 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-400 after:border after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-gray-500"></div>
                            </label>
                        </div>

                        <div className="flex justify-between items-center border-b border-gray-200 pb-4">
                            <div>
                                <h5 className="text-sm font-medium text-gray-800">Require Approval Always</h5>
                                <p className="text-xs text-gray-500">Every action requires manual user consent.</p>
                            </div>
                            <label className="relative inline-flex items-center cursor-not-allowed opacity-70">
                                <input type="checkbox" className="sr-only peer" checked={true} disabled />
                                <div className="w-9 h-5 bg-gray-300 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-400 after:border after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-gray-500"></div>
                            </label>
                        </div>

                        <div className="flex justify-between items-center">
                            <div>
                                <h5 className="text-sm font-medium text-gray-800">Maximum Downscale %</h5>
                                <p className="text-xs text-gray-500">Limit how much a stateful volume/compute can shrink.</p>
                            </div>
                            <input type="number" value={unifiedConfig.stateful_rules.max_downscale_percent} onChange={e => handleConfigChange("stateful_rules", "max_downscale_percent", +e.target.value)} className="w-20 border-gray-300 rounded-md shadow-sm sm:text-sm text-right bg-white" />
                        </div>
                    </div>
                </div>
            </div>

            <div className="mt-8 pt-6 border-t border-gray-200 flex justify-end">
                <button
                    onClick={saveConfig}
                    disabled={saving}
                    className="inline-flex items-center px-4 py-2 border border-transparent shadow-sm text-sm font-medium rounded-md text-white bg-indigo-600 hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500 disabled:opacity-50"
                >
                    {saving ? "Saving..." : "Save Optimization Rules"}
                </button>
            </div>
        </div>
    );
};

export default DecisionEngineV3Dashboard;
