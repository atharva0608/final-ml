import React, { useMemo, useState } from 'react';
import {
    AreaChart, Area, XAxis, YAxis, CartesianGrid,
    Tooltip as RechartsTooltip, ResponsiveContainer, Legend,
} from 'recharts';
import { formatCurrency } from '../../../../utils/formatters';
import { FiArrowRight, FiDownload } from 'react-icons/fi';
import RebalancedDistribution from './RebalancedDistribution';

/* ─── helpers ────────────────────────────────────────────────────────────── */
const fmt$ = v => v >= 1000 ? `$${(v / 1000).toFixed(1)}k` : `$${v.toFixed(2)}`;
const fmtMo = v =>
    v >= 1_000_000 ? `$${(v / 1_000_000).toFixed(2)}M`
    : v >= 1_000   ? `$${(v / 1_000).toFixed(1)}k`
    : `$${v.toFixed(2)}`;

/* ─── Savings Donut ──────────────────────────────────────────────────────── */
const SavingsDonut = ({ pct }) => {
    const r = 15.9155;
    const circ = 2 * Math.PI * r;
    const dash = `${(pct / 100) * circ} ${circ}`;
    const color = pct >= 50 ? '#22c55e' : pct >= 25 ? '#f97316' : '#ef4444';
    return (
        <div className="relative w-16 h-16 flex-shrink-0">
            <svg className="w-full h-full -rotate-90" viewBox="0 0 36 36">
                <circle cx="18" cy="18" r={r} fill="none" stroke="#f3f4f6" strokeWidth="3" />
                <circle
                    cx="18" cy="18" r={r} fill="none"
                    stroke={color} strokeWidth="3"
                    strokeLinecap="round"
                    strokeDasharray={dash}
                    strokeDashoffset="0"
                />
            </svg>
            <div className="absolute inset-0 flex items-center justify-center">
                <span className="text-[11px] font-bold text-gray-800">{pct.toFixed(1)}%</span>
            </div>
        </div>
    );
};

/* ─── Node Composition Ring ─────────────────────────────────────────────── */
const NodeRing = ({ pct, color }) => {
    const dash = `${pct.toFixed(1)}, 100`;
    return (
        <div className="relative w-14 h-14 flex-shrink-0">
            <svg className="w-full h-full -rotate-90" viewBox="0 0 36 36">
                <circle cx="18" cy="18" r="15.9155" fill="none" stroke="#f3f4f6" strokeWidth="3" />
                <path
                    fill="none" stroke={color} strokeWidth="3" strokeLinecap="round"
                    strokeDasharray={dash}
                    d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
                />
            </svg>
            <div className="absolute inset-0 flex items-center justify-center">
                <span className="text-[10px] font-bold text-gray-700">{Math.round(pct)}%</span>
            </div>
        </div>
    );
};

/* ─── Config Table ───────────────────────────────────────────────────────── */
const ConfigTable = ({ rows, title, accent, totalLabel, totalMonthly, totalInstances, totalCpu, totalMem, karpenterSimulation, rightsizingSavings = 0 }) => {
    return (
        <div className="bg-white rounded-lg border border-gray-200 card-shadow overflow-hidden flex flex-col">
            <div className="p-4 border-b border-gray-100 bg-gray-50/50">
                <h3 className="section-title text-[14px]">{title}</h3>
                {karpenterSimulation && (
                    <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
                        <span className="text-[10px] font-bold px-1.5 py-0.5 rounded bg-purple-100 text-purple-700 uppercase tracking-wide">
                            Karpenter {karpenterSimulation.mode}
                        </span>
                        {karpenterSimulation.rightsized && (
                            <span className="text-[10px] font-bold px-1.5 py-0.5 rounded bg-green-100 text-green-700 uppercase tracking-wide">
                                Right-Sized
                            </span>
                        )}
                        {karpenterSimulation.multi_arch && (
                            <span className="text-[10px] font-bold px-1.5 py-0.5 rounded bg-indigo-100 text-indigo-700 uppercase tracking-wide">
                                Multi-Arch
                            </span>
                        )}
                        <span className="text-[10px] text-gray-500">
                            {karpenterSimulation.total_pods_packed} pods → {karpenterSimulation.total_node_count} nodes
                            {karpenterSimulation.monthly_savings > 0 && (
                                <> · <span className="font-semibold text-green-600">{fmtMo(karpenterSimulation.monthly_savings)} savings</span></>
                            )}
                        </span>
                    </div>
                )}
            </div>
            <div className="overflow-x-auto flex-1">
                <table className="min-w-full divide-y divide-gray-100">
                    <thead className="bg-gray-50">
                        <tr>
                            <th className="px-4 py-2 text-left text-[10px] font-bold text-gray-400 uppercase">Qty</th>
                            <th className="px-4 py-2 text-left text-[10px] font-bold text-gray-400 uppercase">Instance</th>
                            <th className="px-4 py-2 text-right text-[10px] font-bold text-gray-400 uppercase">Hourly</th>
                            <th className="px-4 py-2 text-right text-[10px] font-bold text-gray-400 uppercase">Total Hourly</th>
                            <th className="px-4 py-2 text-right text-[10px] font-bold text-gray-400 uppercase">Total Monthly</th>
                        </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-50 text-[11px]">
                        {rows.length === 0
                            ? <tr><td colSpan={5} className="px-4 py-5 text-center text-xs text-gray-400">No data available</td></tr>
                            : rows.map((r, i) => (
                                <tr key={i} className="hover:bg-gray-50/50">
                                    <td className="px-4 py-3 font-medium text-gray-900">{r.qty} x</td>
                                    <td className="px-4 py-3">
                                        <div className="flex items-center space-x-2">
                                            <svg className="w-4 h-4 text-gray-400" fill="currentColor" viewBox="0 0 24 24"><path d="M19,20H5V20H19V20M19,18H5V4H19V18M17,10H15V8H17V10M17,14H15V12H17V14M13,10H11V8H13V10M13,14H11V12H13V14M9,10H7V8H9V10M9,14H7V12H9V14Z"></path></svg>
                                            <div className="flex flex-col">
                                                <div className="flex items-center space-x-1">
                                                    <span className="font-bold text-gray-700">{r.type}</span>
                                                    {r.isSpot && (
                                                        <span className="bg-gray-800 text-white text-[8px] px-1 rounded">SPOT</span>
                                                    )}
                                                    {r.architecture && (
                                                        <span className={`text-[8px] px-1 rounded font-bold ${r.architecture === 'arm64' ? 'bg-orange-100 text-orange-700' : 'bg-blue-100 text-blue-700'}`}>
                                                            {r.architecture === 'arm64' ? 'ARM64' : 'x86_64'}
                                                        </span>
                                                    )}
                                                </div>
                                                {(r.vcpu > 0 || r.memGib > 0) && (
                                                    <span className="text-[9px] text-gray-400 uppercase">{r.vcpu > 0 ? `${r.vcpu} CPU` : ''}{r.vcpu > 0 && r.memGib > 0 ? ', ' : ''}{r.memGib > 0 ? `${Math.round(r.memGib)} GIB` : ''}</span>
                                                )}
                                                {r.mlScore > 0 && (
                                                    <span className="text-[9px] text-gray-400">ML Score: {(r.mlScore * 100).toFixed(1)}%</span>
                                                )}
                                            </div>
                                        </div>
                                    </td>
                                    <td className="px-4 py-3 text-right text-gray-600">${r.hourly.toFixed(4)} <span className="text-[9px] text-gray-400">/ h</span></td>
                                    <td className="px-4 py-3 text-right text-gray-600">${r.totalHourly.toFixed(4)} <span className="text-[9px] text-gray-400">/ h</span></td>
                                    <td className="px-4 py-3 text-right font-medium text-gray-900">{fmtMo(r.totalMonthly)} <span className="text-[9px] text-gray-400">/ mo</span></td>
                                </tr>
                            ))
                        }
                    </tbody>
                </table>
            </div>
            
            <div className={`p-4 ${accent === "border-l-blue-500" ? "bg-blue-50/50 border-blue-100" : "bg-green-50/50 border-green-100"} border-t flex justify-between items-center`}>
                <div>
                    <p className="section-title text-[10px] uppercase mb-1">{totalLabel}</p>
                    <div className="flex space-x-3">
                        {totalInstances > 0 && <span className="text-[9px] text-gray-500 font-semibold uppercase">{totalInstances} Instances</span>}
                        {totalCpu > 0 && <span className="text-[9px] text-gray-500 font-semibold uppercase">{totalCpu} CPU</span>}
                        {totalMem > 0 && <span className="text-[9px] text-gray-500 font-semibold uppercase">{Math.round(totalMem)} GIB</span>}
                    </div>
                </div>
                <div className="text-right">
                    <span className={`text-xl font-bold ${accent === "border-l-green-500" ? "text-green-600" : "text-slate-800"}`}>{fmtMo(totalMonthly)}</span>
                    <span className="text-xs text-gray-400 ml-1">/mo</span>
                    {rightsizingSavings > 0 && (
                        <p className="text-[9px] text-green-600 font-semibold mt-0.5">incl. {fmtMo(rightsizingSavings)} right-sizing savings</p>
                    )}
                </div>
            </div>
        </div>
    );
};

/* ─── Tooltip ────────────────────────────────────────────────────────────── */
const CostTooltip = ({ active, payload, label }) => {
    if (!active || !payload?.length) return null;
    return (
        <div className="bg-white border border-gray-200 rounded-lg shadow-lg px-3 py-2 text-xs">
            <p className="text-gray-500 mb-1">{label}</p>
            {payload.map((p, i) => (
                <div key={i} className="flex items-center gap-2">
                    <span className="w-2 h-2 rounded-full" style={{ background: p.color }} />
                    <span className="text-gray-600">{p.name}:</span>
                    <span className="font-semibold">{fmt$(p.value)}/mo</span>
                </div>
            ))}
            {payload.length === 2 && payload[0].value > 0 && (
                <div className="mt-1 pt-1 border-t border-gray-100 font-semibold text-blue-600">
                    Available Savings: {((1 - payload[1].value / payload[0].value) * 100).toFixed(2)}%
                </div>
            )}
        </div>
    );
};

/* ═══════════════════════════════════════════════════════════════════════════
   Main Component
   ═══════════════════════════════════════════════════════════════════════════ */
const OverviewTab = ({
    cluster, metrics, utilization, karpenterInstallStatus,
    schedule, policy, nodeRecommendations, karpenterSimulation, nodesDetailed,
    costTrends, rightsizing, autoRightsizingEnabled, autoRebalanceEnabled, onInstallKarpenter, onInstallKeda, onManagePolicies,
}) => {
    const [trendWindow, setTrendWindow] = useState('24h');

    /* ── Node composition — count directly from nodesDetailed.nodes[] ─── */
    const nodesList = nodesDetailed?.nodes || [];
    const spotCount = nodesList.filter(n =>
        n.lifecycle === 'spot' || n.lifecycle === 'SPOT').length
        || metrics?.spot_instances || cluster?.spot_count || 0;
    const odCount = nodesList.filter(n =>
        n.lifecycle === 'on-demand' || n.lifecycle === 'on_demand' || n.lifecycle === 'ON_DEMAND').length
        || metrics?.on_demand_instances || cluster?.on_demand_node_count || 0;
    const fallbackCount = nodesList.filter(n =>
        n.lifecycle === 'fallback' || n.lifecycle === 'FALLBACK').length
        || metrics?.fallback_instances || 0;
    const totalNodes = (spotCount + odCount + fallbackCount) || nodesDetailed?.total_nodes || cluster?.node_count || 0;
    const spotRatioPct = totalNodes > 0 ? (spotCount / totalNodes) * 100 : 0;
    const ringColor = spotRatioPct >= 70 ? '#22c55e' : spotRatioPct >= 40 ? '#f97316' : '#3b82f6';

    /* ── Pods — nodesDetailed is the single consistent source of truth ─── */
    const totalPods = nodesDetailed?.total_pods
        ?? metrics?.total_pods
        ?? nodesList.reduce((s, n) => s + (n.pod_count || 0), 0);
    const spotFriendlyPods = nodesDetailed?.spot_friendly_pods
        ?? metrics?.spot_friendly_pods
        ?? nodesList.reduce((s, n) => s + (n.pods || []).filter(p => !p.is_stateful).length, 0);
    const statefulPods = nodesList.reduce((s, n) => s + (n.stateful_pod_count || 0), 0);
    const spotFriendlyPct = totalPods > 0 ? (spotFriendlyPods / totalPods) * 100 : 0;
    const nonSpotFriendlyPods = nodesDetailed?.non_spot_friendly_pods
        ?? (totalPods - spotFriendlyPods);
    const misplacedPods = nodesDetailed?.misplaced_pods || 0;

    /* ── Node classification — from nodesDetailed[].classification ─────── */
    const statelessNodes = nodesList.filter(n => n.classification === 'STATELESS').length;
    const statefulNodes  = nodesList.filter(n => n.classification === 'STATEFUL').length;
    const mixedNodes     = nodesList.filter(n => n.classification === 'MIXED').length;
    const anchorNodes    = nodesList.filter(n => n.classification === 'ANCHOR').length;
    const emptyNodes     = nodesList.filter(n => n.classification === 'EMPTY' || !n.classification).length;

    /* ── Costs — derive from nodeRecommendations when metrics are stale ─ */
    // current_cost = hourly rate of current instance (spot price if already spot, OD price if OD)
    // od_cost = OD hourly rate (always)
    // target_spot_price = best available spot hourly rate
    const calcMonthly = (nodeRecommendations || []).reduce(
        (s, r) => s + (r.current_cost || 0) * 730, 0);
    // Potential additional savings = OD nodes not yet on spot (exclude anchor)
    const calcSavings = (nodeRecommendations || [])
        .filter(r => r.lifecycle !== 'spot' && r.lifecycle !== 'SPOT' && !r.is_anchor)
        .reduce((s, r) => {
            // Skip nodes with no real spot price — never fabricate savings with a multiplier
            if (!(r.target_spot_price > 0)) return s;
            const od = r.current_cost || 0;
            return s + Math.max(0, od - r.target_spot_price) * 730;
        }, 0);
    // Realized savings = spot nodes already running: (od_equivalent - actual_spot) × 730h/mo
    // od_cost field (from API) = OD price for node; current_cost = actual spot price for spot nodes
    // Guard: both prices must be > 0; current_cost=0 means price unavailable, not free
    const calcRealized = (nodeRecommendations || [])
        .filter(r => r.lifecycle === 'spot' || r.lifecycle === 'SPOT')
        .reduce((s, r) => {
            const od = r.od_cost || 0;
            const spot = r.current_cost || 0;
            if (od > 0 && spot > 0 && od > spot) return s + (od - spot) * 730;
            return s;
        }, 0);
    // Prefer live nodeRecommendations data over stale DB values when available
    const totalCost       = calcMonthly > 0 ? calcMonthly : (metrics?.monthly_cost ?? cluster?.monthly_cost ?? 0);
    const realizedSavings = calcRealized > 0 ? calcRealized : (metrics?.realized_savings ?? 0);
    // When Karpenter simulation is available AND right-sizing is enabled,
    // use simulation monthly_savings (bin-packing consolidation).
    // When right-sizing is OFF, use 1:1 node swap savings from nodeRecommendations.
    const addlPotential   = (autoRightsizingEnabled && karpenterSimulation?.monthly_savings > 0)
        ? karpenterSimulation.monthly_savings
        : calcSavings > 0 ? calcSavings : (metrics?.estimated_savings ?? cluster?.estimated_savings ?? 0);
    // savingsPct = total savings (realized + potential) vs all-OD baseline
    const allODBaseline   = totalCost + realizedSavings;
    const savingsPct      = allODBaseline > 0 ? ((realizedSavings + addlPotential) / allODBaseline) * 100 : 0;

    /* ── Agent ─────────────────────────────────────────────────────────── */
    // Backend stores last_heartbeat as UTC but without a 'Z' suffix,
    // so JavaScript's Date() would treat it as local time. Force UTC.
    const _hbUtc = cluster?.last_heartbeat
        ? (cluster.last_heartbeat.endsWith('Z') ? cluster.last_heartbeat : cluster.last_heartbeat + 'Z')
        : null;
    const _hbAgeSec = _hbUtc ? (Date.now() - new Date(_hbUtc)) / 1000 : Infinity;
    const isHealthy = (() => {
        if (!cluster?.agent_installed || cluster.agent_installed === 'N') return false;
        if (!_hbUtc) return false;
        return _hbAgeSec < 300; // Healthy if heartbeat within last 5 minutes (agent retries with backoff)
    })();
    // Stale = agent was recently connected but last heartbeat is 5-15 min old
    const isStale = !isHealthy && _hbAgeSec < 900 && cluster?.agent_installed === 'Y';
    const lastHbStr = (() => {
        if (!_hbUtc) return 'Unknown';
        const s = _hbAgeSec;
        if (s < 60)   return 'Just now';
        if (s < 3600) return `${Math.floor(s / 60)}m ago`;
        return `${Math.floor(s / 3600)}h ago`;
    })();

    /* ── Karpenter ─────────────────────────────────────────────────────── */
    const karpInstalled = karpenterInstallStatus?.karpenter_installed;
    const karpIsMissing = karpInstalled === 'missing' || karpenterInstallStatus?.status === 'missing';
    const karpMode = karpenterInstallStatus?.karpenter_mode;
    const karpDetectedVia = karpenterInstallStatus?.detected_via;

    /* ── Optimization ──────────────────────────────────────────────────── */
    // Agent is considered active if healthy OR stale (cached data still valid)
    const ascpActive  = isHealthy || isStale;
    const rsCount     = rightsizing?.length || 0;
    const policyCount = policy ? 1 : 0;

    /* ── Type specs — actual field names: cpu_capacity_cores, memory_capacity_gb */
    const typeSpecs = useMemo(() => {
        const m = {};
        nodesList.forEach(n => {
            if (n.instance_type && !m[n.instance_type])
                m[n.instance_type] = {
                    vcpu: n.cpu_capacity_cores || n.cpu_capacity || 0,
                    mem:  n.memory_capacity_gb  || n.mem_capacity  || 0,
                };
        });
        return m;
    }, [nodesList]);

    /* ── Current config rows ───────────────────────────────────────────── */
    const currentConfigRows = useMemo(() => {
        const byType = {};
        (nodeRecommendations || []).forEach(r => {
            const t = r.current_type || r.instance_type;
            if (!t) return;
            if (!byType[t]) byType[t] = { qty: 0, hourly: r.current_cost || 0, isSpot: r.lifecycle === 'spot' };
            byType[t].qty++;
        });
        return Object.entries(byType)
            .map(([type, d]) => ({
                type, qty: d.qty, hourly: d.hourly, isSpot: d.isSpot,
                totalHourly: d.qty * (d.hourly || 0),
                totalMonthly: d.qty * (d.hourly || 0) * 730,
                vcpu: typeSpecs[type]?.vcpu || 0,
                memGib: typeSpecs[type]?.mem || 0,
            }))
            .sort((a, b) => b.totalMonthly - a.totalMonthly);
    }, [nodeRecommendations, typeSpecs]);

    const curTotal   = currentConfigRows.reduce((s, r) => s + r.totalMonthly, 0);
    const curInst    = currentConfigRows.reduce((s, r) => s + r.qty, 0);
    const curCpu     = currentConfigRows.reduce((s, r) => s + r.qty * r.vcpu, 0);
    const curMem     = currentConfigRows.reduce((s, r) => s + r.qty * r.memGib, 0);

    /* ── Optimized config rows ─────────────────────────────────────────── */
    // When Karpenter simulation is available AND right-sizing is enabled,
    // use consolidated bin-packed nodes. When right-sizing is OFF, show 1:1
    // spot replacement recommendations (auto-rebalancer behavior).
    const optimizedConfigRows = useMemo(() => {
        if (autoRightsizingEnabled && karpenterSimulation?.consolidated_nodes?.length > 0) {
            // Karpenter mode: show consolidated bin-packed nodes
            return karpenterSimulation.consolidated_nodes
                .map(n => ({
                    type: n.instance_type,
                    qty: n.count,
                    hourly: n.spot_price || 0,
                    isSpot: true,
                    totalHourly: n.count * (n.spot_price || 0),
                    totalMonthly: n.count * (n.spot_price || 0) * 730,
                    vcpu: n.vcpu || 0,
                    memGib: n.memory_gb || 0,
                    architecture: n.architecture || null,
                    mlScore: n.ml_score || 0,
                    odPrice: n.od_price || 0,
                }))
                .sort((a, b) => b.totalMonthly - a.totalMonthly);
        }
        // Non-Karpenter mode: 1:1 rebalancing (current behavior)
        // Anchor nodes stay at current OD type+cost — not converted to spot.
        // Key by type+lifecycle so anchor OD and spot target of the same type
        // don't merge into a single row.
        const byKey = {};
        (nodeRecommendations || []).forEach(r => {
            if (r.is_anchor) {
                const t = r.current_type;
                if (!t) return;
                const key = `${t}:OD`;
                const price = r.od_cost || r.current_cost || 0;
                if (!byKey[key]) byKey[key] = { type: t, qty: 0, hourly: price, isSpot: false };
                byKey[key].qty++;
            } else {
                const t = r.target_type || r.current_type;
                if (!t) return;
                const key = `${t}:SPOT`;
                const price = (r.target_spot_price != null && r.target_spot_price > 0) ? r.target_spot_price : 0;
                if (!byKey[key]) byKey[key] = { type: t, qty: 0, hourly: price, isSpot: true };
                byKey[key].qty++;
            }
        });
        return Object.values(byKey)
            .map(d => ({
                type: d.type, qty: d.qty, hourly: d.hourly, isSpot: d.isSpot,
                totalHourly: d.qty * (d.hourly || 0),
                totalMonthly: d.qty * (d.hourly || 0) * 730,
                vcpu: typeSpecs[d.type]?.vcpu || 0,
                memGib: typeSpecs[d.type]?.mem || 0,
            }))
            .sort((a, b) => b.totalMonthly - a.totalMonthly);
    }, [nodeRecommendations, typeSpecs, karpenterSimulation]);

    const optTotal = optimizedConfigRows.reduce((s, r) => s + r.totalMonthly, 0);
    const optInst  = optimizedConfigRows.reduce((s, r) => s + r.qty, 0);
    const optCpu   = optimizedConfigRows.reduce((s, r) => s + r.qty * r.vcpu, 0);
    const optMem   = optimizedConfigRows.reduce((s, r) => s + r.qty * r.memGib, 0);

    /* ── Right-sizing combined savings ────────────────────────────── */
    const bothActive = autoRightsizingEnabled && autoRebalanceEnabled;
    const rsSavingsTotal = (rightsizing || []).reduce((s, r) => s + (r.savings_monthly || 0), 0);
    // When right-sizing is active, the karpenter_simulation already
    // accounts for right-sized pod resources (use_rightsized=true on the API).
    // The optTotal from consolidated_nodes already reflects tighter bin-packing.
    // We use it directly — no extra subtraction needed.

    /* ── Optimized Config title ────────────────────────────────────── */
    const optimizedConfigTitle = (() => {
        if (autoRightsizingEnabled && karpenterSimulation)
            return "Optimized Configuration (Karpenter + Right-Sizing)";
        if (bothActive)
            return "Optimized Cluster Configuration (Right-Sizing + Rebalance)";
        if (autoRebalanceEnabled)
            return "Optimized Cluster Configuration (Spot Replacement)";
        return "Optimized Cluster Configuration";
    })();

    /* ── Effective optimal cost ─────────────────────────────────────────
       When the Karpenter simulation is active (rightsizing ON) and produced
       consolidated nodes, the optimized cost from the simulation is far more
       accurate than the 1:1 per-node addlPotential.  Use optTotal as the
       source of truth so KPI cards, chart, and config table all agree.
    ────────────────────────────────────────────────────────────────────── */
    const useSimCost = autoRightsizingEnabled && optTotal > 0 && karpenterSimulation?.consolidated_nodes?.length > 0;
    const effectiveOptCost   = useSimCost ? optTotal : Math.max(0, totalCost - addlPotential);
    const effectiveSavings   = totalCost > 0 ? Math.max(0, totalCost - effectiveOptCost) : 0;
    const effectiveSavingPct = totalCost > 0 ? (effectiveSavings / totalCost) * 100 : 0;

    /* ── Cost trend chart ──────────────────────────────────────────────── */
    const trendData = useMemo(() => {
        const frac = totalCost > 0 && effectiveSavings > 0 ? effectiveSavings / totalCost : 0;
        const now = Date.now();
        const is24h = trendWindow === '24h';
        const cutoff = is24h ? now - 86_400_000 : now - 7 * 86_400_000;

        const pts = costTrends?.data_points || costTrends?.points || [];

        // For 24h: backend only has daily points, so we may get 0-1 points.
        // Synthesize hourly data from current totalCost so the graph is always visible.
        if (is24h) {
            // Generate 24 hourly points as a stable flat line at current cost.
            // As rebalancing events occur and cost snapshots accumulate, these
            // will diverge and the line will show real movement.
            if (totalCost <= 0) return [];
            const points = [];
            for (let h = 23; h >= 0; h--) {
                const t = new Date(now - h * 3_600_000);
                points.push({
                    time: t.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
                    current: +totalCost.toFixed(2),
                    optimal: +((totalCost * (1 - frac))).toFixed(2),
                });
            }
            return points;
        }

        // 7-day mode: use backend daily data
        if (!pts.length) return [];
        const filtered = pts.filter(p => new Date(p.timestamp).getTime() >= cutoff);
        const rawAvg = filtered.length > 0
            ? filtered.reduce((s, p) => s + (p.value || 0), 0) / filtered.length
            : 0;
        const scale = rawAvg > 0 && totalCost > 0 ? totalCost / (rawAvg * 30) : 1;

        return filtered.map(p => ({
            time: new Date(p.timestamp).toLocaleDateString([], { month: 'numeric', day: 'numeric' }),
            current: +(p.value * 30 * scale).toFixed(2),
            optimal: +(p.value * (1 - frac) * 30 * scale).toFixed(2),
        }));
    }, [costTrends, trendWindow, totalCost, effectiveSavings]);

    // KPI cards use simulation-aware values when rightsizing is active,
    // otherwise fall back to 1:1 nodeRecommendations-based savings.
    const avgMonthly      = totalCost;
    const avgMonthlyOpt   = effectiveOptCost;
    const availSavingsPct = effectiveSavingPct;

    /* ── Spot analysis rows ────────────────────────────────────────────── */
    const spotAnalysisRows = useMemo(() =>
        (nodeRecommendations || []).map(r => ({
            workload: (() => {
                const raw = (r.node_name || '').replace(/\..*$/, '');
                // K8s assigns IP-based hostnames like "ip-192-168-x-x"; show instance_type instead
                return (raw && !raw.startsWith('ip-'))
                    ? raw.slice(0, 32)
                    : (r.instance_type || r.instance_id || raw).slice(0, 32);
            })(),
            replicas: 1,
            currentType: (r.lifecycle === 'spot' || r.lifecycle === 'SPOT') ? 'SPOT' : 'ON DEMAND',
            recommendation: (r.lifecycle === 'spot' || r.lifecycle === 'SPOT') ? 'STABLE' : 'SPOT',
            savings: r.projected_savings_pct ?? 0,
        })),
    [nodeRecommendations]);

    // Available savings — single source of truth: simulation-aware savings %
    // (same value shown in the Cost & Savings donut and chart KPIs)
    const totalAvailSavings = effectiveSavingPct > 0 ? effectiveSavingPct.toFixed(1) : '0';

    /* ──────────────────────────────────────────────────────────────────── */
    return (
        <div className="space-y-5">

            {/* ── Agent Banner ───────────────────────────────────────── */}
            <div className={`bg-white rounded-lg px-5 py-3 flex items-center justify-between shadow-sm border border-l-4 ${
                isHealthy ? 'border-green-200 border-l-green-500' : isStale ? 'border-yellow-200 border-l-yellow-500' : 'border-orange-200 border-l-orange-400'
            }`}>
                <div>
                    <div className="flex items-center gap-2">
                        <span className="text-sm font-semibold text-gray-900">
                            {isHealthy ? 'Agent Healthy' : isStale ? 'Agent Reconnecting' : 'Agent Disconnected'}
                        </span>
                        <span className="text-[10px] text-gray-400 bg-gray-100 px-1.5 py-0.5 rounded uppercase tracking-wide">
                            {cluster?.version || 'v1.0.0'}
                        </span>
                    </div>
                    <p className="text-xs text-gray-500 mt-0.5">
                        Last heartbeat: {lastHbStr}
                        {isHealthy ? ' · Metrics collection active' : isStale ? ' · Showing cached data · Agent will auto-reconnect' : ' · Agent offline or uninstalled'}
                    </p>
                </div>
                <div className={`w-2.5 h-2.5 rounded-full flex-shrink-0 ${
                    isHealthy ? 'bg-green-500' : isStale ? 'bg-yellow-500 animate-pulse' : 'bg-orange-400'
                }`} />
            </div>

            {/* ── Top row: Cost & Savings | Node Composition | Pods ── */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">

                {/* Cost & Savings */}
                <div className="bg-white border border-gray-200 rounded-lg p-4">
                    <p className="text-[10px] font-semibold text-gray-400 uppercase tracking-widest mb-3">Cost &amp; Savings</p>
                    <div className="flex items-center gap-4">
                        <SavingsDonut pct={effectiveSavingPct} />
                        <div className="min-w-0">
                            <p className="text-xs text-gray-500">Monthly Cost</p>
                            <p className="text-2xl font-bold text-gray-900 leading-tight">{formatCurrency(totalCost)}</p>
                            <div className="flex gap-3 mt-1">
                                <div>
                                    <p className="text-[10px] text-gray-400">Realized</p>
                                    <p className="text-sm font-semibold text-gray-700">{formatCurrency(realizedSavings)}</p>
                                </div>
                                <div>
                                    <p className="text-[10px] text-gray-400">Potential</p>
                                    <p className="text-sm font-semibold text-orange-500">{formatCurrency(effectiveSavings)}</p>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>

                {/* Node Composition */}
                <div className="bg-white border border-gray-200 rounded-lg p-4">
                    <p className="text-[10px] font-semibold text-gray-400 uppercase tracking-widest mb-3">Node Composition</p>
                    <div className="flex items-center gap-4">
                        <NodeRing pct={spotRatioPct} color={ringColor} />
                        <div className="flex flex-col gap-1.5">
                            <div className="flex items-center justify-between gap-6">
                                <div className="flex items-center gap-1.5">
                                    <span className="w-2 h-2 rounded-full bg-green-500 flex-shrink-0" />
                                    <span className="text-xs text-gray-600">Spot</span>
                                </div>
                                <span className="text-xs font-semibold text-gray-800">{spotCount}</span>
                            </div>
                            <div className="flex items-center justify-between gap-6">
                                <div className="flex items-center gap-1.5">
                                    <span className="w-2 h-2 rounded-full bg-blue-600 flex-shrink-0" />
                                    <span className="text-xs text-gray-600">On-Demand</span>
                                </div>
                                <span className="text-xs font-semibold text-gray-800">{odCount}</span>
                            </div>
                            {fallbackCount > 0 && (
                                <div className="flex items-center justify-between gap-6">
                                    <div className="flex items-center gap-1.5">
                                        <span className="w-2 h-2 rounded-full bg-orange-500 flex-shrink-0" />
                                        <span className="text-xs text-gray-600">Fallback</span>
                                    </div>
                                    <span className="text-xs font-semibold text-gray-800">{fallbackCount}</span>
                                </div>
                            )}
                        </div>
                    </div>
                </div>

                {/* Pods */}
                <div className="bg-white border border-gray-200 rounded-lg p-4">
                    <p className="text-[10px] font-semibold text-gray-400 uppercase tracking-widest mb-3">Pods</p>
                    {totalPods === 0 ? (
                        <div className="flex items-center gap-4">
                            <div>
                                <p className="text-3xl font-bold text-gray-900">0</p>
                                <p className="text-[10px] text-gray-400 uppercase tracking-wider mt-0.5">Total Pods</p>
                            </div>
                            <div className="flex-1 text-xs text-gray-400 italic">No pod data yet</div>
                        </div>
                    ) : (
                        <div className="space-y-2.5">
                            {/* Top row: total + spot-friendly + non-spot-friendly */}
                            <div className="flex items-center gap-3">
                                <div>
                                    <p className="text-2xl font-bold text-gray-900">{totalPods}</p>
                                    <p className="text-[10px] text-gray-400 uppercase tracking-wider">Total Pods</p>
                                </div>
                                <div className="flex-1 bg-green-50 border border-green-100 rounded-lg px-2.5 py-1.5 text-center">
                                    <p className="text-base font-bold text-green-700">{spotFriendlyPods}</p>
                                    <p className="text-[10px] text-green-600 font-medium">Spot-friendly · {spotFriendlyPct.toFixed(0)}%</p>
                                </div>
                                {nonSpotFriendlyPods > 0 && (
                                    <div className="flex-1 bg-blue-50 border border-blue-100 rounded-lg px-2.5 py-1.5 text-center">
                                        <p className="text-base font-bold text-blue-700">{nonSpotFriendlyPods}</p>
                                        <p className="text-[10px] text-blue-600 font-medium">Non spot-friendly</p>
                                    </div>
                                )}
                                {statefulPods > 0 && (
                                    <div className="flex-1 bg-orange-50 border border-orange-100 rounded-lg px-2.5 py-1.5 text-center">
                                        <p className="text-base font-bold text-orange-600">{statefulPods}</p>
                                        <p className="text-[10px] text-orange-500 font-medium">Stateful pods</p>
                                    </div>
                                )}
                                {misplacedPods > 0 && (
                                    <div className="flex-1 bg-red-50 border border-red-200 rounded-lg px-2.5 py-1.5 text-center" title="Stateful pods running on spot nodes — should be on OD">
                                        <p className="text-base font-bold text-red-600">{misplacedPods}</p>
                                        <p className="text-[10px] text-red-500 font-medium">Misplaced ⚠</p>
                                    </div>
                                )}
                            </div>
                            {/* Node classification row — drives recommendations */}
                            {nodesList.length > 0 && (
                                <div className="pt-2 border-t border-gray-100">
                                    <p className="text-[9px] font-bold text-gray-400 uppercase tracking-wider mb-1.5">Node Workload Classification</p>
                                    <div className="flex gap-2 flex-wrap">
                                        {statelessNodes > 0 && (
                                            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold bg-green-50 text-green-700 border border-green-200">
                                                <span className="w-1.5 h-1.5 rounded-full bg-green-500 inline-block" />
                                                {statelessNodes} Stateless → <span className="text-green-600">SPOT safe</span>
                                            </span>
                                        )}
                                        {anchorNodes > 0 && (
                                            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold bg-indigo-50 text-indigo-700 border border-indigo-200">
                                                <span className="w-1.5 h-1.5 rounded-full bg-indigo-500 inline-block" />
                                                {anchorNodes} Anchor → <span className="text-indigo-600">OD locked</span>
                                            </span>
                                        )}
                                        {statefulNodes > 0 && (
                                            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold bg-orange-50 text-orange-700 border border-orange-200">
                                                <span className="w-1.5 h-1.5 rounded-full bg-orange-500 inline-block" />
                                                {statefulNodes} Stateful → <span className="text-orange-600">OD recommended</span>
                                            </span>
                                        )}
                                        {mixedNodes > 0 && (
                                            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold bg-yellow-50 text-yellow-700 border border-yellow-200">
                                                <span className="w-1.5 h-1.5 rounded-full bg-yellow-500 inline-block" />
                                                {mixedNodes} Mixed → review
                                            </span>
                                        )}
                                        {emptyNodes > 0 && (
                                            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold bg-gray-100 text-gray-500 border border-gray-200">
                                                {emptyNodes} Empty
                                            </span>
                                        )}
                                    </div>
                                </div>
                            )}
                        </div>
                    )}
                </div>
            </div>

            {/* ── Optimization Status ─────────────────────────────── */}
            <div className="bg-white border border-gray-200 rounded-lg shadow-sm">
                <div className="flex items-center justify-between px-5 py-3 border-b border-gray-100">
                    <p className="text-sm font-semibold text-gray-800">Optimization Status</p>
                    <button
                        onClick={onManagePolicies}
                        className="text-xs text-blue-600 hover:text-blue-800 font-medium flex items-center gap-1"
                    >
                        Manage Policies <FiArrowRight className="w-3 h-3" />
                    </button>
                </div>
                <div className="grid grid-cols-2 md:grid-cols-4 divide-y md:divide-y-0 md:divide-x divide-gray-100">
                    {/* ASCP.ai */}
                    <div className="px-5 py-4">
                        <p className="text-xs font-semibold text-gray-700 mb-1">Balancekube.ai</p>
                        <div className="flex items-center gap-1.5 mb-1">
                            <span className={`w-1.5 h-1.5 rounded-full ${ascpActive ? 'bg-green-500' : 'bg-gray-400'}`} />
                            <span className="text-xs text-gray-500">{ascpActive ? 'Active' : 'Inactive'}</span>
                        </div>
                        {!ascpActive && (
                            <button
                                onClick={onInstallKarpenter}
                                className="text-[10px] text-blue-500 hover:text-blue-700"
                            >
                                Install agent to enable
                            </button>
                        )}
                    </div>
                    {/* Right-Sizing */}
                    <div className="px-5 py-4">
                        <div className="flex items-center gap-1.5 mb-1">
                            <p className="text-xs font-semibold text-gray-700">Right-Sizing</p>
                            {autoRightsizingEnabled && rsCount > 0 && (
                                bothActive ? (
                                    <span className="text-[9px] font-bold px-1 py-0.5 rounded bg-green-100 text-green-700 uppercase tracking-wide">Active</span>
                                ) : (
                                    <span className="text-[9px] font-bold px-1 py-0.5 rounded bg-yellow-100 text-yellow-700 uppercase tracking-wide">Rec. Only</span>
                                )
                            )}
                        </div>
                        {rsCount > 0 ? (
                            <>
                                <div className="flex items-center gap-1.5 mb-1">
                                    <span className="w-1.5 h-1.5 rounded-full bg-orange-500" />
                                    <span className="text-xs text-orange-600 font-medium">{rsCount} workload{rsCount !== 1 ? 's' : ''}</span>
                                </div>
                                <p className="text-[10px] text-gray-400">{formatCurrency(rsSavingsTotal)}/mo potential savings</p>
                            </>
                        ) : (
                            <div className="flex items-center gap-1.5">
                                <span className="w-1.5 h-1.5 rounded-full bg-green-500" />
                                <span className="text-xs text-gray-500">No issues</span>
                            </div>
                        )}
                    </div>
                    {/* Policies */}
                    <div className="px-5 py-4">
                        <p className="text-xs font-semibold text-gray-700 mb-1">Policies</p>
                        <p className="text-xs text-gray-600">
                            <span className="font-semibold text-gray-800">{policyCount}</span>
                            {policyCount === 1 ? ' active policy' : policyCount === 0 ? ' policies configured' : ' active policies'}
                        </p>
                    </div>
                    {/* Hibernation */}
                    <div className="px-5 py-4">
                        <p className="text-xs font-semibold text-gray-700 mb-1">Hibernation</p>
                        <div className="flex items-center gap-1.5 mb-1">
                            <span className={`w-1.5 h-1.5 rounded-full ${schedule ? 'bg-green-500' : 'bg-gray-400'}`} />
                            <span className="text-xs text-gray-500">{schedule ? 'Active schedules' : 'No schedules'}</span>
                        </div>
                        <p className="text-[10px] text-gray-400">Configure to save on dev</p>
                    </div>
                </div>
            </div>

            {/* ── Karpenter Management ────────────────────────────── */}
            <div className="bg-white border border-gray-200 rounded-lg shadow-sm">
                <div className="px-5 py-3 border-b border-gray-100 flex items-center justify-between">
                    <p className="text-sm font-semibold text-gray-800">Karpenter Management</p>
                    <span className="flex items-center gap-1 text-[10px] text-gray-400" title="Status refreshes every 60s">
                        <span className="w-1.5 h-1.5 rounded-full bg-green-400 animate-pulse inline-block" />
                        live
                    </span>
                </div>
                <div className="px-5 py-4 flex items-center justify-between">
                    <div className="flex items-center gap-3">
                        <div>
                            <div className="flex items-center gap-2 mb-1">
                                <span className="text-xs text-gray-500">Status</span>
                                <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded uppercase tracking-wide ${
                                    karpIsMissing
                                        ? 'bg-red-100 text-red-700'
                                        : karpInstalled
                                            ? 'bg-green-100 text-green-700'
                                            : 'bg-gray-100 text-gray-600'
                                }`}>
                                    {karpIsMissing ? 'MISSING' : karpInstalled ? 'INSTALLED' : 'NOT INSTALLED'}
                                </span>
                                {karpInstalled && !karpIsMissing && karpMode && (
                                    <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded uppercase tracking-wide bg-blue-50 text-blue-600 border border-blue-100">
                                        {karpMode}
                                    </span>
                                )}
                            </div>
                            <p className="text-xs text-gray-500">
                                {karpIsMissing
                                    ? 'Karpenter pods are not running — reinstall required'
                                    : karpInstalled
                                    ? spotCount > 0
                                        ? `Active — managing ${spotCount} spot node${spotCount > 1 ? 's' : ''}`
                                        : karpDetectedVia
                                            ? 'Detected in cluster — will provision spot nodes when rebalancer triggers'
                                            : 'Installed — will provision spot nodes when rebalancer triggers'
                                    : 'Not installed — required for spot node provisioning'}
                            </p>
                        </div>
                    </div>
                    <div className="flex flex-col gap-2">
                        {(karpIsMissing || !karpInstalled) && (
                            <button
                                onClick={onInstallKarpenter}
                                className={`flex items-center gap-1.5 ${karpIsMissing ? 'bg-red-600 hover:bg-red-700' : 'bg-green-600 hover:bg-green-700'} text-white text-xs font-semibold px-4 py-2 rounded-lg transition-colors`}
                            >
                                <FiDownload className="w-3.5 h-3.5" />
                                {karpIsMissing ? 'Reinstall Karpenter' : 'Install Karpenter'}
                            </button>
                        )}
                        <button
                            onClick={onInstallKeda}
                            className="flex items-center gap-1.5 bg-white hover:bg-gray-50 text-gray-800 text-xs font-semibold px-4 py-2 rounded-lg transition-colors border border-gray-200"
                        >
                            <FiDownload className="w-3.5 h-3.5" />
                            Install KEDA
                        </button>
                    </div>
                </div>
            </div>

            {/* ── Spot Instance Analysis ──────────────────────────── */}
            <div className="bg-white border border-gray-200 rounded-lg shadow-sm">
                <div className="flex items-center justify-between px-5 py-3 border-b border-gray-100">
                    <p className="text-sm font-semibold text-gray-800">Spot Instance Analysis</p>
                    {parseFloat(totalAvailSavings) > 0 && (
                        <span className="text-xs text-gray-500">
                            Available Savings:{' '}
                            <span className="font-bold text-green-600">{totalAvailSavings}%</span>
                        </span>
                    )}
                </div>
                <div className="overflow-x-auto">
                    <table className="w-full">
                        <thead>
                            <tr className="border-b border-gray-100 bg-gray-50">
                                <th className="text-left px-5 py-2.5 text-[10px] text-gray-400 font-semibold uppercase tracking-wider">Workloads</th>
                                <th className="text-center px-4 py-2.5 text-[10px] text-gray-400 font-semibold uppercase tracking-wider">Replicas</th>
                                <th className="text-center px-4 py-2.5 text-[10px] text-gray-400 font-semibold uppercase tracking-wider">Current Type</th>
                                <th className="text-right px-5 py-2.5 text-[10px] text-gray-400 font-semibold uppercase tracking-wider">Recommendation</th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-gray-50">
                            {spotAnalysisRows.length === 0 ? (
                                <tr>
                                    <td colSpan={4} className="px-5 py-6 text-center text-xs text-gray-400">
                                        No workload data available
                                    </td>
                                </tr>
                            ) : spotAnalysisRows.map((r, i) => (
                                <tr key={i} className="hover:bg-gray-50">
                                    <td className="px-5 py-3 text-xs font-mono text-gray-700">{r.workload || '—'}</td>
                                    <td className="px-4 py-3 text-center text-xs text-gray-600">{r.replicas}</td>
                                    <td className="px-4 py-3 text-center">
                                        <span className={`text-[10px] font-semibold px-2 py-0.5 rounded uppercase ${
                                            r.currentType === 'SPOT'
                                                ? 'bg-green-50 text-green-700'
                                                : 'bg-gray-100 text-gray-600'
                                        }`}>
                                            {r.currentType}
                                        </span>
                                    </td>
                                    <td className="px-5 py-3 text-right">
                                        {r.recommendation === 'SPOT' ? (
                                            <span className="text-[10px] font-bold px-2.5 py-1 rounded bg-blue-600 text-white uppercase">SPOT</span>
                                        ) : (
                                            <span className="text-[10px] font-semibold px-2 py-0.5 rounded bg-green-50 text-green-700 uppercase">Stable</span>
                                        )}
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            </div>

            {/* ── Optimized Configuration (BFD-TSC) ───────────────────── */}
            {cluster?.id && (
                <RebalancedDistribution clusterId={cluster.id} />
            )}

            {/* ── Current + Optimized Config ──────────────────────── */}
            {(currentConfigRows.length > 0 || optimizedConfigRows.length > 0) && (
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                    <ConfigTable
                        rows={currentConfigRows}
                        title="Current Cluster Configuration"
                        accent="border-l-blue-500"
                        totalLabel="Current Cluster Compute Cost:"
                        totalMonthly={curTotal || totalCost}
                        totalInstances={curInst}
                        totalCpu={curCpu}
                        totalMem={curMem}
                    />
                    <ConfigTable
                        rows={optimizedConfigRows}
                        title={optimizedConfigTitle}
                        accent="border-l-green-500"
                        totalLabel={bothActive ? "Optimized Cost (incl. Right-Sizing):" : "Optimized Cluster Compute Cost:"}
                        totalMonthly={optTotal || Math.max(0, totalCost - addlPotential)}
                        totalInstances={optInst}
                        totalCpu={optCpu}
                        totalMem={optMem}
                        karpenterSimulation={autoRightsizingEnabled ? karpenterSimulation : null}
                        rightsizingSavings={bothActive ? rsSavingsTotal : 0}
                    />
                </div>
            )}

            {/* ── Cluster Cost Trends ─────────────────────────────── */}
            <div className="bg-white rounded-lg border border-gray-200 card-shadow p-6">
                <div className="flex items-center justify-between mb-8">
                    <h3 className="section-title text-[14px]">Cluster Cost Trends</h3>
                    <div className="flex bg-gray-100 rounded-md p-1">
                        {['24h', '7d'].map(w => (
                            <button
                                key={w}
                                onClick={() => setTrendWindow(w)}
                                className={`px-4 py-1.5 rounded text-xs font-semibold transition-colors border ${
                                    trendWindow === w
                                        ? 'bg-white text-blue-600 border-gray-100 shadow-sm'
                                        : 'text-gray-500 hover:text-gray-700 bg-transparent border-transparent font-medium'
                                }`}
                            >
                                {w === '24h' ? '24 hours' : '7 days'}
                            </button>
                        ))}
                    </div>
                </div>
                
                <div className="grid grid-cols-1 lg:grid-cols-4 gap-8">
                    <div className="space-y-8 pr-6 border-r border-gray-50 flex flex-col justify-between">
                        <div>
                            <p className="text-[10px] font-bold text-gray-400 uppercase tracking-widest mb-1">Current Average Cost</p>
                            <p className="text-2xl font-bold text-slate-800">
                                {formatCurrency(avgMonthly)} <span className="text-xs text-gray-400">/mo</span>
                            </p>
                            <div className="w-full h-1 bg-blue-100 rounded-full mt-2">
                                <div className="w-full h-full bg-blue-500 rounded-full" />
                            </div>
                        </div>
                        <div>
                            <p className="text-[10px] font-bold text-gray-400 uppercase tracking-widest mb-1">Optimal Average Cost</p>
                            <p className="text-2xl font-bold text-green-600">
                                {formatCurrency(avgMonthlyOpt)} <span className="text-xs text-gray-400">/mo</span>
                            </p>
                            <div className="w-full h-1 bg-green-100 rounded-full mt-2">
                                <div className="w-3/5 h-full bg-green-500 rounded-full" />
                            </div>
                        </div>
                        <div className="pt-6 border-t border-gray-100">
                            <p className="text-[10px] font-bold text-gray-400 uppercase tracking-widest mb-1">Available Savings</p>
                            <p className="text-4xl font-extrabold text-blue-600 tracking-tight">{availSavingsPct.toFixed(2)}%</p>
                        </div>
                    </div>
                    
                    <div className="lg:col-span-3 h-80 relative">
                        <div className="flex justify-between text-[9px] text-gray-400 border-b border-gray-50 pb-1 mb-2">
                            <span>$ {Math.ceil(Math.max(...trendData.map(d => d.current), totalCost, 1))}</span>
                            <span className="flex items-center">
                                Monthly cost equiv.
                                <svg className="w-3 h-3 ml-1" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M19 9l-7 7-7-7" strokeLinecap="round" strokeLinejoin="round" strokeWidth="2"></path></svg>
                            </span>
                        </div>
                        {trendData.length > 0 ? (
                            <div className="flex-1 w-full h-[calc(100%-25px)]">
                                <ResponsiveContainer width="100%" height="100%">
                                    <AreaChart data={trendData} margin={{ top: 5, right: 0, left: -20, bottom: 0 }}>
                                        <defs>
                                            <linearGradient id="gCurrent" x1="0" y1="0" x2="0" y2="1">
                                                <stop offset="5%"  stopColor="#3b82f6" stopOpacity={0.4} />
                                                <stop offset="95%" stopColor="#3b82f6" stopOpacity={0.0} />
                                            </linearGradient>
                                            <linearGradient id="gOptimal" x1="0" y1="0" x2="0" y2="1">
                                                <stop offset="5%"  stopColor="#22c55e" stopOpacity={0.4} />
                                                <stop offset="95%" stopColor="#22c55e" stopOpacity={0.0} />
                                            </linearGradient>
                                        </defs>
                                        <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#f3f4f6" />
                                        <XAxis dataKey="time" tick={{ fontSize: 10, fill: '#9ca3af', fontWeight: 'bold' }} axisLine={false} tickLine={false} interval="preserveStartEnd" />
                                        <YAxis tick={false} axisLine={false} tickLine={false} />
                                        <RechartsTooltip content={<CostTooltip />} />
                                        <Legend
                                            iconType="circle" iconSize={8}
                                            wrapperStyle={{ fontSize: 10, paddingTop: 10 }}
                                            formatter={v => v === 'current' ? 'Current Cluster Cost' : v === 'optimal' ? 'Optimal Cluster Cost' : 'Total Savings Potential'}
                                        />
                                        <Area type="linear" dataKey="current" name="current" stroke="#3b82f6" strokeWidth={2} fill="url(#gCurrent)" dot={false} activeDot={false} />
                                        <Area type="linear" dataKey="optimal"  name="optimal"  stroke="#22c55e" strokeWidth={2} fill="url(#gOptimal)"  dot={false} activeDot={false} />
                                    </AreaChart>
                                </ResponsiveContainer>
                            </div>
                        ) : (
                            <div className="h-48 flex items-center justify-center text-xs text-gray-400">
                                No historical cost data available yet
                            </div>
                        )}
                    </div>
                </div>
            </div>

        </div>
    );
};

export default OverviewTab;
