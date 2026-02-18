import React, { useState, useEffect } from 'react';
import {
    FiChevronRight, FiChevronLeft, FiCheck, FiAlertTriangle,
    FiServer, FiCpu, FiDollarSign, FiShield, FiZap, FiSave,
    FiX, FiInfo, FiLayers
} from 'react-icons/fi';
import { Card, Button, Badge } from '../shared';
import { useClusterStore } from '../../store/useStore';
import { karpenterAPI } from '../../services/api';
import toast from 'react-hot-toast';

/* ─── Constants ──────────────────────────────────────────────────────────── */

const STRATEGIES = [
    {
        key: 'cost-first',
        label: 'Cost-First',
        subtitle: 'Maximum Savings',
        desc: 'Prioritizes cheapest instance types (Graviton, older gen). Aggressive consolidation (merges nodes frequently). 90%+ spot instances.',
        savings: '40-50%', utilization: '80-90%', churn: 'Medium-High',
        bestFor: ['Dev/staging environments', 'Batch processing workloads', 'Stateless applications'],
        notFor: 'Databases, stateful apps',
    },
    {
        key: 'balanced',
        label: 'Balanced',
        subtitle: 'Recommended',
        desc: 'Mix of cost and performance optimization. Moderate consolidation. 70-80% spot instances with on-demand fallback.',
        savings: '30-40%', utilization: '70-80%', churn: 'Low-Medium',
        bestFor: ['Production web applications', 'API services', 'Most general workloads'],
        notFor: null,
    },
    {
        key: 'performance-first',
        label: 'Performance-First',
        subtitle: 'Stability Priority',
        desc: 'Favors current-gen, proven instance types. Conservative consolidation. 50-60% spot instances.',
        savings: '20-30%', utilization: '60-70%', churn: 'Very Low',
        bestFor: ['Mission-critical production apps', 'Stateful workloads (databases)', 'Strict SLA requirements'],
        notFor: null,
    },
];

const INSTANCE_FAMILIES = [
    { key: 'm', label: 'General Purpose (m-family)', types: ['m5', 'm6i', 'm6a', 'm7i'], defaultChecked: ['m5', 'm6i'] },
    { key: 'c', label: 'Compute Optimized (c-family)', types: ['c5', 'c6i', 'c6a', 'c7i'], defaultChecked: ['c5', 'c6i'] },
    { key: 'r', label: 'Memory Optimized (r-family)', types: ['r5', 'r6i', 'r6a'], defaultChecked: [] },
    { key: 't', label: 'Burstable (t-family)', types: ['t3', 't3a', 't4g'], defaultChecked: [] },
];

const PRESETS = {
    'web': { label: 'Web Tier', families: ['m5', 'm6i', 'm6a', 'c5', 'c6i'] },
    'api': { label: 'API/Backend', families: ['c5', 'c6i', 'c6a', 'c7i', 'm6i'] },
    'database': { label: 'Database', families: ['r5', 'r6i', 'r6a', 'm6i'] },
    'batch': { label: 'Batch Processing', families: ['t3', 't4g', 'm5', 'c5'] },
};

/* ─── Component ──────────────────────────────────────────────────────────── */

const KarpenterSetup = ({ onComplete, onCancel }) => {
    const { clusters } = useClusterStore();
    const [step, setStep] = useState(1);
    const [deploying, setDeploying] = useState(false);

    // ── Step 1 state: cluster selection
    const [selectedClusters, setSelectedClusters] = useState([]);

    // ── Step 2 state: strategy per cluster (map clusterID → strategy key)
    const [strategies, setStrategies] = useState({});

    // ── Step 3 state: instance config (shared across clusters for simplicity)
    const [selectedTypes, setSelectedTypes] = useState(['m5', 'm6i', 'c5', 'c6i']);
    const [architectures, setArchitectures] = useState(['amd64']);
    const [spotTarget, setSpotTarget] = useState(75);
    const [onDemandFallback, setOnDemandFallback] = useState(true);
    const [minVcpu, setMinVcpu] = useState(2);
    const [maxVcpu, setMaxVcpu] = useState(16);
    const [minMemory, setMinMemory] = useState(4);
    const [maxMemory, setMaxMemory] = useState(64);

    // ── Step 4 state: advanced settings
    const [consolidation, setConsolidation] = useState(true);
    const [consolidationThreshold, setConsolidationThreshold] = useState(60);
    const [nodeMaxLifetime, setNodeMaxLifetime] = useState(7);
    const [respectPDB, setRespectPDB] = useState(true);
    const [drainTimeout, setDrainTimeout] = useState(90);
    const [costAlertMonthly, setCostAlertMonthly] = useState('');
    const [acks, setAcks] = useState({ manage: false, reviewed: false, understand: false });

    // Seed strategies when clusters are selected
    useEffect(() => {
        const newStrats = { ...strategies };
        selectedClusters.forEach(c => {
            if (!newStrats[c.id]) newStrats[c.id] = 'balanced';
        });
        setStrategies(newStrats);
    }, [selectedClusters]);

    /* ─── Helpers ─────────────────────────────────────────────────────── */

    const toggleCluster = (cluster) => {
        setSelectedClusters(prev =>
            prev.find(c => c.id === cluster.id)
                ? prev.filter(c => c.id !== cluster.id)
                : [...prev, cluster]
        );
    };

    const toggleType = (t) => {
        setSelectedTypes(prev =>
            prev.includes(t) ? prev.filter(x => x !== t) : [...prev, t]
        );
    };

    const applyPreset = (presetKey) => {
        setSelectedTypes([...PRESETS[presetKey].families]);
    };

    const canAdvance = () => {
        if (step === 1) return selectedClusters.length > 0;
        if (step === 2) return selectedClusters.every(c => strategies[c.id]);
        if (step === 3) return selectedTypes.length > 0 && architectures.length > 0;
        if (step === 4) return acks.manage && acks.reviewed && acks.understand;
        return true;
    };

    const handleDeploy = async () => {
        setDeploying(true);
        try {
            const configs = selectedClusters.map(c => ({
                cluster_id: c.id,
                strategy: strategies[c.id] || 'balanced',
                instance_families: selectedTypes,
                architectures,
                spot_target_pct: spotTarget,
                on_demand_fallback: onDemandFallback,
                min_vcpu: minVcpu,
                max_vcpu: maxVcpu,
                min_memory_gib: minMemory,
                max_memory_gib: maxMemory,
                consolidation_enabled: consolidation,
                consolidation_threshold_pct: consolidationThreshold,
                node_max_lifetime_days: nodeMaxLifetime,
                cost_alert_monthly: costAlertMonthly ? parseFloat(costAlertMonthly) : null,
            }));

            await karpenterAPI.deploy({
                cluster_configs: configs,
                gradual_rollout: true,
                acknowledgements: Object.keys(acks).filter(k => acks[k]),
            });

            toast.success('Karpenter deployment initiated!');
            onComplete?.();
        } catch (err) {
            console.error('Deploy error:', err);
            toast.error('Failed to deploy Karpenter');
        } finally {
            setDeploying(false);
        }
    };

    /* ─── Step Renderers ─────────────────────────────────────────────── */

    const renderStep1 = () => (
        <div className="space-y-4">
            <div className="bg-blue-50 border border-blue-100 rounded-lg p-3 text-xs text-blue-700">
                <FiInfo className="inline w-3.5 h-3.5 mr-1" />
                <strong>RECOMMENDATION:</strong> Start with dev/staging clusters first. Validate behavior before enabling on production.
            </div>

            {(clusters || []).length === 0 ? (
                <div className="text-center py-8 text-gray-400 text-sm">No clusters available. Please connect a cluster first.</div>
            ) : (
                <div className="space-y-3">
                    {(clusters || []).map(cluster => {
                        const isSelected = selectedClusters.find(c => c.id === cluster.id);
                        const estimatedSavings = Math.round((cluster.monthly_cost || 1200) * 0.30);
                        return (
                            <button
                                key={cluster.id}
                                onClick={() => toggleCluster(cluster)}
                                className={`w-full text-left rounded-xl border-2 p-4 transition-all ${isSelected
                                        ? 'border-blue-500 bg-blue-50/50'
                                        : 'border-gray-200 bg-white hover:border-gray-300'
                                    }`}
                            >
                                <div className="flex items-start justify-between">
                                    <div>
                                        <div className="flex items-center gap-2">
                                            <span className={`w-4 h-4 rounded border flex items-center justify-center ${isSelected ? 'bg-blue-500 border-blue-500 text-white' : 'border-gray-300'
                                                }`}>
                                                {isSelected && <FiCheck className="w-3 h-3" />}
                                            </span>
                                            <span className="font-semibold text-gray-900 text-sm">{cluster.name}</span>
                                            <Badge variant="default">{cluster.region || 'us-east-1'}</Badge>
                                        </div>
                                        <div className="ml-6 mt-1 text-xs text-gray-500 space-y-0.5">
                                            <div>{cluster.node_count || 0} nodes • Current: ${(cluster.monthly_cost || 0).toLocaleString()}/mo</div>
                                            <div>k8s {cluster.version || '1.28'} • Status: {cluster.status || 'Healthy'}</div>
                                        </div>
                                    </div>
                                    <div className="text-right">
                                        <div className="text-green-600 font-bold text-sm">+${estimatedSavings.toLocaleString()}/mo</div>
                                        <div className="text-[10px] text-gray-400">~30% savings</div>
                                    </div>
                                </div>
                            </button>
                        );
                    })}
                </div>
            )}

            {selectedClusters.length > 0 && (
                <div className="bg-gray-50 rounded-lg p-3 text-xs text-gray-600 border border-gray-100">
                    <div className="font-semibold mb-1">Selection Summary</div>
                    <div>Selected clusters: {selectedClusters.length} • Total nodes: {selectedClusters.reduce((s, c) => s + (c.node_count || 0), 0)}</div>
                    <div>Estimated savings: ${selectedClusters.reduce((s, c) => s + Math.round((c.monthly_cost || 1200) * 0.30), 0).toLocaleString()}/mo</div>
                </div>
            )}
        </div>
    );

    const renderStep2 = () => (
        <div className="space-y-4">
            <div className="bg-blue-50 border border-blue-100 rounded-lg p-3 text-xs text-blue-700">
                <FiInfo className="inline w-3.5 h-3.5 mr-1" />
                Choose how Karpenter balances cost savings vs performance/stability. You can change this anytime.
            </div>

            {selectedClusters.map(cluster => (
                <div key={cluster.id} className="space-y-3">
                    <div className="flex items-center gap-2 text-sm font-medium text-gray-700">
                        <FiServer className="w-4 h-4" /> {cluster.name}
                    </div>

                    <div className="space-y-2">
                        {STRATEGIES.map(strat => {
                            const isSelected = strategies[cluster.id] === strat.key;
                            return (
                                <button
                                    key={strat.key}
                                    onClick={() => setStrategies(prev => ({ ...prev, [cluster.id]: strat.key }))}
                                    className={`w-full text-left rounded-xl border-2 p-4 transition-all ${isSelected ? 'border-blue-500 bg-blue-50/50' : 'border-gray-200 bg-white hover:border-gray-300'
                                        }`}
                                >
                                    <div className="flex items-center gap-2 mb-1">
                                        <span className={`w-3.5 h-3.5 rounded-full border-2 ${isSelected ? 'border-blue-500 bg-blue-500' : 'border-gray-300'
                                            }`}></span>
                                        <span className="font-semibold text-sm text-gray-900">{strat.label}</span>
                                        {strat.subtitle === 'Recommended' && (
                                            <Badge variant="info">Recommended</Badge>
                                        )}
                                    </div>
                                    <p className="text-xs text-gray-500 ml-5 mb-2">{strat.desc}</p>
                                    <div className="ml-5 flex gap-4 text-[10px] text-gray-500">
                                        <span>💰 Savings: {strat.savings}</span>
                                        <span>⚡ Util: {strat.utilization}</span>
                                        <span>🔄 Churn: {strat.churn}</span>
                                    </div>
                                    <div className="ml-5 mt-2 text-[10px]">
                                        <span className="text-gray-400">Best for: </span>
                                        {strat.bestFor.map((b, i) => (
                                            <span key={i} className="text-gray-600">{i > 0 ? ' • ' : ''}{b}</span>
                                        ))}
                                    </div>
                                </button>
                            );
                        })}
                    </div>
                </div>
            ))}
        </div>
    );

    const renderStep3 = () => (
        <div className="space-y-5">
            {/* Instance Families */}
            <div>
                <h3 className="text-sm font-semibold text-gray-900 mb-2 flex items-center gap-1.5">
                    <FiCpu className="w-4 h-4" /> Instance Families
                </h3>
                <div className="bg-blue-50 border border-blue-100 rounded-lg p-2.5 text-xs text-blue-700 mb-3">
                    Different types optimized for different workloads. More families = more flexibility = better pricing.
                </div>

                {/* Preset dropdown */}
                <div className="flex gap-2 mb-3 flex-wrap">
                    {Object.entries(PRESETS).map(([k, v]) => (
                        <button key={k} onClick={() => applyPreset(k)}
                            className="px-3 py-1 rounded-full text-xs border border-gray-200 hover:bg-blue-50 hover:border-blue-300 transition-colors">
                            {v.label}
                        </button>
                    ))}
                </div>

                <div className="space-y-2">
                    {INSTANCE_FAMILIES.map(fam => {
                        const anySelected = fam.types.some(t => selectedTypes.includes(t));
                        return (
                            <div key={fam.key} className="border border-gray-200 rounded-lg p-3">
                                <div className="font-medium text-xs text-gray-700 mb-1.5">{fam.label}</div>
                                <div className="flex flex-wrap gap-2">
                                    {fam.types.map(t => (
                                        <button key={t} onClick={() => toggleType(t)}
                                            className={`px-3 py-1 rounded-full text-xs border transition-colors ${selectedTypes.includes(t)
                                                    ? 'bg-blue-500 text-white border-blue-500'
                                                    : 'border-gray-200 text-gray-600 hover:border-blue-300'
                                                }`}>
                                            {t}
                                        </button>
                                    ))}
                                </div>
                            </div>
                        );
                    })}
                </div>
                <div className="text-xs text-gray-400 mt-1">Currently selected: {selectedTypes.length} instance types</div>
            </div>

            {/* Architecture */}
            <div>
                <h3 className="text-sm font-semibold text-gray-900 mb-2 flex items-center gap-1.5">
                    <FiLayers className="w-4 h-4" /> Architecture
                </h3>
                <div className="flex gap-3">
                    {[{ key: 'amd64', label: 'AMD64 (x86)', desc: 'Traditional Intel/AMD' }, { key: 'arm64', label: 'ARM64 (Graviton)', desc: '20% cheaper, great performance' }].map(arch => (
                        <button key={arch.key}
                            onClick={() => setArchitectures(prev => prev.includes(arch.key) ? prev.filter(a => a !== arch.key) : [...prev, arch.key])}
                            className={`flex-1 text-left rounded-lg border-2 p-3 transition-all ${architectures.includes(arch.key) ? 'border-blue-500 bg-blue-50/50' : 'border-gray-200'
                                }`}>
                            <div className="flex items-center gap-2">
                                <span className={`w-4 h-4 rounded border flex items-center justify-center ${architectures.includes(arch.key) ? 'bg-blue-500 border-blue-500 text-white' : 'border-gray-300'
                                    }`}>{architectures.includes(arch.key) && <FiCheck className="w-2.5 h-2.5" />}</span>
                                <span className="text-xs font-semibold text-gray-900">{arch.label}</span>
                            </div>
                            <div className="text-[10px] text-gray-400 ml-6">{arch.desc}</div>
                        </button>
                    ))}
                </div>
            </div>

            {/* Spot Target */}
            <div>
                <h3 className="text-sm font-semibold text-gray-900 mb-2 flex items-center gap-1.5">
                    <FiDollarSign className="w-4 h-4" /> Capacity Type (Spot vs On-Demand)
                </h3>
                <div className="bg-blue-50 border border-blue-100 rounded-lg p-2.5 text-xs text-blue-700 mb-3">
                    Spot instances are unused AWS capacity at 70% discount. Karpenter handles interruptions automatically.
                </div>
                <div className="flex items-center gap-3">
                    <span className="text-xs text-gray-500">Spot target:</span>
                    <input type="range" min="0" max="100" value={spotTarget}
                        onChange={(e) => setSpotTarget(parseInt(e.target.value))}
                        className="flex-1 accent-blue-500" />
                    <span className="text-sm font-bold text-gray-900 w-12 text-right">{spotTarget}%</span>
                </div>
                <label className="flex items-center gap-2 mt-2 text-xs text-gray-600">
                    <input type="checkbox" checked={onDemandFallback}
                        onChange={(e) => setOnDemandFallback(e.target.checked)}
                        className="rounded border-gray-300" />
                    Enable on-demand fallback (prevents stuck pods)
                </label>
            </div>

            {/* Resource Limits */}
            <div>
                <h3 className="text-sm font-semibold text-gray-900 mb-2 flex items-center gap-1.5">
                    <FiShield className="w-4 h-4" /> Resource Limits (per node)
                </h3>
                <div className="grid grid-cols-2 gap-4">
                    <div>
                        <label className="text-xs text-gray-500">vCPU: Min</label>
                        <input type="number" min="1" value={minVcpu} onChange={e => setMinVcpu(parseInt(e.target.value) || 1)}
                            className="w-full mt-1 px-3 py-1.5 text-sm border border-gray-200 rounded-lg" />
                    </div>
                    <div>
                        <label className="text-xs text-gray-500">vCPU: Max</label>
                        <input type="number" min="1" value={maxVcpu} onChange={e => setMaxVcpu(parseInt(e.target.value) || 1)}
                            className="w-full mt-1 px-3 py-1.5 text-sm border border-gray-200 rounded-lg" />
                    </div>
                    <div>
                        <label className="text-xs text-gray-500">Memory (GiB): Min</label>
                        <input type="number" min="1" value={minMemory} onChange={e => setMinMemory(parseInt(e.target.value) || 1)}
                            className="w-full mt-1 px-3 py-1.5 text-sm border border-gray-200 rounded-lg" />
                    </div>
                    <div>
                        <label className="text-xs text-gray-500">Memory (GiB): Max</label>
                        <input type="number" min="1" value={maxMemory} onChange={e => setMaxMemory(parseInt(e.target.value) || 1)}
                            className="w-full mt-1 px-3 py-1.5 text-sm border border-gray-200 rounded-lg" />
                    </div>
                </div>
            </div>
        </div>
    );

    const renderStep4 = () => (
        <div className="space-y-5">
            {/* Consolidation */}
            <div>
                <h3 className="text-sm font-semibold text-gray-900 mb-2">Consolidation (Cost Optimization)</h3>
                <div className="bg-blue-50 border border-blue-100 rounded-lg p-2.5 text-xs text-blue-700 mb-2">
                    Karpenter packs pods onto fewer, cheaper nodes. When nodes are under-utilized, it moves pods and terminates empty nodes.
                </div>
                <label className="flex items-center gap-2 text-xs text-gray-700">
                    <input type="checkbox" checked={consolidation} onChange={e => setConsolidation(e.target.checked)} className="rounded border-gray-300" />
                    Enable consolidation
                </label>
                {consolidation && (
                    <div className="mt-2 flex items-center gap-3">
                        <span className="text-xs text-gray-500">Threshold:</span>
                        <input type="range" min="10" max="90" value={consolidationThreshold}
                            onChange={e => setConsolidationThreshold(parseInt(e.target.value))} className="flex-1 accent-blue-500" />
                        <span className="text-sm font-bold w-12 text-right">{consolidationThreshold}%</span>
                    </div>
                )}
            </div>

            {/* Node Lifecycle */}
            <div>
                <h3 className="text-sm font-semibold text-gray-900 mb-2">Node Lifecycle</h3>
                <div className="flex items-center gap-3">
                    <span className="text-xs text-gray-500">Max node lifetime:</span>
                    <input type="number" min="1" max="30" value={nodeMaxLifetime}
                        onChange={e => setNodeMaxLifetime(parseInt(e.target.value) || 7)}
                        className="w-20 px-3 py-1.5 text-sm border border-gray-200 rounded-lg" />
                    <span className="text-xs text-gray-400">days</span>
                </div>
            </div>

            {/* Workload Protection */}
            <div>
                <h3 className="text-sm font-semibold text-gray-900 mb-2">Workload Protection</h3>
                <div className="space-y-2">
                    <label className="flex items-center gap-2 text-xs text-gray-700">
                        <input type="checkbox" checked={respectPDB} onChange={e => setRespectPDB(e.target.checked)} className="rounded border-gray-300" />
                        Respect PodDisruptionBudgets
                    </label>
                    <div className="flex items-center gap-2">
                        <span className="text-xs text-gray-500">Drain timeout:</span>
                        <input type="number" min="30" max="300" value={drainTimeout}
                            onChange={e => setDrainTimeout(parseInt(e.target.value) || 90)}
                            className="w-20 px-3 py-1.5 text-sm border border-gray-200 rounded-lg" />
                        <span className="text-xs text-gray-400">seconds</span>
                    </div>
                </div>
            </div>

            {/* Cost Guardrails */}
            <div>
                <h3 className="text-sm font-semibold text-gray-900 mb-2">Cost Guardrails</h3>
                <div className="flex items-center gap-2">
                    <span className="text-xs text-gray-500">Alert when cluster cost exceeds:</span>
                    <span className="text-xs text-gray-400">$</span>
                    <input type="number" min="0" value={costAlertMonthly}
                        onChange={e => setCostAlertMonthly(e.target.value)}
                        placeholder="5000"
                        className="w-24 px-3 py-1.5 text-sm border border-gray-200 rounded-lg" />
                    <span className="text-xs text-gray-400">/ month</span>
                </div>
            </div>

            {/* Deployment Summary */}
            <div className="bg-gray-50 rounded-xl border border-gray-200 p-4 space-y-3">
                <h3 className="text-sm font-semibold text-gray-900 flex items-center gap-1.5">📋 Review Your Configuration</h3>
                <div className="text-xs text-gray-600 space-y-1">
                    <div>Clusters: {selectedClusters.map(c => `${c.name} (${strategies[c.id]})`).join(', ')}</div>
                    <div>Instance types: {selectedTypes.join(', ')}</div>
                    <div>Architecture: {architectures.join(', ')}</div>
                    <div>Spot target: {spotTarget}%</div>
                    <div>Consolidation: {consolidation ? `On (${consolidationThreshold}% threshold)` : 'Off'}</div>
                    <div>Max node lifetime: {nodeMaxLifetime} days</div>
                </div>
                <div className="border-t border-gray-200 pt-2 text-xs text-gray-500 space-y-1">
                    <div className="font-medium text-gray-700">What happens next?</div>
                    <div>1. Install Karpenter controller (Helm chart) — 2 min</div>
                    <div>2. Create IAM roles — 1 min</div>
                    <div>3. Deploy NodePool configurations — 30 sec</div>
                    <div>4. Set up monitoring + cost alerts — 30 sec</div>
                    <div className="mt-1 font-medium">Gradual rollout: Day 1 new pods only → Day 4-5 migrate 75% → Day 6-7 complete.</div>
                </div>
            </div>

            {/* Acknowledgements */}
            <div className="space-y-2">
                {[
                    { key: 'manage', label: 'I understand Karpenter will manage node provisioning' },
                    { key: 'reviewed', label: 'I have reviewed the configuration' },
                    { key: 'understand', label: 'I understand this can be paused or disabled anytime' },
                ].map(ack => (
                    <label key={ack.key} className="flex items-center gap-2 text-xs text-gray-700">
                        <input type="checkbox" checked={acks[ack.key]}
                            onChange={e => setAcks(prev => ({ ...prev, [ack.key]: e.target.checked }))}
                            className="rounded border-gray-300" />
                        {ack.label}
                    </label>
                ))}
            </div>
        </div>
    );

    const STEPS = [
        { num: 1, label: 'Choose Clusters', render: renderStep1 },
        { num: 2, label: 'Configure Strategy', render: renderStep2 },
        { num: 3, label: 'Instance Settings', render: renderStep3 },
        { num: 4, label: 'Advanced & Review', render: renderStep4 },
    ];

    const currentStep = STEPS.find(s => s.num === step);

    return (
        <div className="space-y-4">
            {/* Header */}
            <div className="flex items-center justify-between">
                <h2 className="text-lg font-bold text-gray-900">
                    🚀 Karpenter Setup — Step {step} of 4
                </h2>
                <div className="flex items-center gap-2">
                    <button onClick={onCancel} className="text-gray-400 hover:text-gray-600 text-xs flex items-center gap-1">
                        <FiSave className="w-3.5 h-3.5" /> Save & Exit
                    </button>
                    <button onClick={onCancel} className="text-gray-400 hover:text-gray-600">
                        <FiX className="w-5 h-5" />
                    </button>
                </div>
            </div>

            {/* Progress bar */}
            <div className="flex items-center gap-1">
                {STEPS.map(s => (
                    <div key={s.num} className="flex-1 flex items-center gap-1">
                        <div className={`h-1.5 flex-1 rounded-full transition-colors ${s.num <= step ? 'bg-blue-500' : 'bg-gray-200'
                            }`} />
                        <span className={`text-[10px] ${s.num <= step ? 'text-blue-600 font-semibold' : 'text-gray-400'}`}>
                            {s.label}
                        </span>
                    </div>
                ))}
            </div>

            {/* Body */}
            <Card className="p-0">
                <div className="p-5">
                    {currentStep?.render()}
                </div>
            </Card>

            {/* Footer */}
            <div className="flex items-center justify-between">
                <div>
                    {step > 1 && (
                        <Button variant="outline" onClick={() => setStep(step - 1)}>
                            <FiChevronLeft className="w-4 h-4 mr-1" /> Back
                        </Button>
                    )}
                </div>
                <div className="flex items-center gap-2">
                    {step < 4 ? (
                        <Button variant="primary" disabled={!canAdvance()} onClick={() => setStep(step + 1)}>
                            Continue <FiChevronRight className="w-4 h-4 ml-1" />
                        </Button>
                    ) : (
                        <Button variant="primary" disabled={!canAdvance() || deploying} onClick={handleDeploy}>
                            {deploying ? 'Deploying…' : '🚀 Deploy Karpenter'}
                        </Button>
                    )}
                </div>
            </div>
        </div>
    );
};

export default KarpenterSetup;
