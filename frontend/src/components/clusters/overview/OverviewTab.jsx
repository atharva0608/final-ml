import React, { useMemo, useState } from 'react';
import {
    AreaChart, Area, XAxis, YAxis, CartesianGrid,
    Tooltip as RechartsTooltip, ResponsiveContainer, Legend,
} from 'recharts';
import { formatCurrency } from '../../../utils/formatters';
import { FiArrowRight, FiDownload } from 'react-icons/fi';

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
const ConfigTable = ({ rows, title, accent, totalLabel, totalMonthly, totalInstances, totalCpu, totalMem }) => {
    return (
        <div className="bg-white rounded-lg border border-gray-200 card-shadow overflow-hidden flex flex-col">
            <div className="p-4 border-b border-gray-100 bg-gray-50/50">
                <h3 className="section-title text-[14px]">{title}</h3>
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
                                                </div>
                                                {(r.vcpu > 0 || r.memGib > 0) && (
                                                    <span className="text-[9px] text-gray-400 uppercase">{r.vcpu > 0 ? `${r.vcpu} CPU` : ''}{r.vcpu > 0 && r.memGib > 0 ? ', ' : ''}{r.memGib > 0 ? `${Math.round(r.memGib)} GIB` : ''}</span>
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
    schedule, policy, nodeRecommendations, nodesDetailed,
    costTrends, rightsizing, onInstallKarpenter, onManagePolicies,
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

    /* ── Pods — sum pod_count per node; spot-friendly = non-stateful pods */
    const totalPods = metrics?.total_pods
        || nodesDetailed?.total_pods
        || nodesList.reduce((s, n) => s + (n.pod_count || 0), 0)
        || 0;
    const spotFriendlyPods = metrics?.spot_friendly_pods
        || nodesDetailed?.spot_friendly_pods
        || nodesList.reduce((s, n) => s + (n.pods || []).filter(p => !p.is_stateful).length, 0)
        || 0;
    const statefulPods = nodesList.reduce((s, n) => s + (n.stateful_pod_count || 0), 0);
    const spotFriendlyPct = totalPods > 0 ? (spotFriendlyPods / totalPods) * 100 : 0;

    /* ── Node classification — from nodesDetailed[].classification ─────── */
    const statelessNodes = nodesList.filter(n => n.classification === 'STATELESS').length;
    const statefulNodes  = nodesList.filter(n => n.classification === 'STATEFUL').length;
    const mixedNodes     = nodesList.filter(n => n.classification === 'MIXED').length;
    const emptyNodes     = nodesList.filter(n => n.classification === 'EMPTY' || !n.classification).length;

    /* ── Costs — derive from nodeRecommendations when metrics are stale ─ */
    // current_cost = hourly rate of current instance (spot price if already spot, OD price if OD)
    // od_cost = OD hourly rate (always)
    // target_spot_price = best available spot hourly rate
    const calcMonthly = (nodeRecommendations || []).reduce(
        (s, r) => s + (r.current_cost || 0) * 730, 0);
    // Potential additional savings = OD nodes not yet on spot
    const calcSavings = (nodeRecommendations || [])
        .filter(r => r.lifecycle !== 'spot' && r.lifecycle !== 'SPOT')
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
    const addlPotential   = calcSavings > 0 ? calcSavings : (metrics?.estimated_savings ?? cluster?.estimated_savings ?? 0);
    // savingsPct = total savings (realized + potential) vs all-OD baseline
    const allODBaseline   = totalCost + realizedSavings;
    const savingsPct      = allODBaseline > 0 ? ((realizedSavings + addlPotential) / allODBaseline) * 100 : 0;

    /* ── Agent ─────────────────────────────────────────────────────────── */
    const isHealthy = ['active', 'ACTIVE'].includes(cluster?.status || '');
    const lastHbStr = (() => {
        if (!cluster?.last_heartbeat) return 'Unknown';
        const s = (Date.now() - new Date(cluster.last_heartbeat)) / 1000;
        if (s < 60)   return 'Just now';
        if (s < 3600) return `${Math.floor(s / 60)}m ago`;
        return `${Math.floor(s / 3600)}h ago`;
    })();

    /* ── Karpenter ─────────────────────────────────────────────────────── */
    const karpInstalled = karpenterInstallStatus?.karpenter_installed;
    const karpMode = karpenterInstallStatus?.karpenter_mode;
    const karpDetectedVia = karpenterInstallStatus?.detected_via;

    /* ── Optimization ──────────────────────────────────────────────────── */
    // Agent is active if the cluster status is 'active' (agent_installed field is unreliable)
    const ascpActive  = isHealthy;
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
    const optimizedConfigRows = useMemo(() => {
        const byType = {};
        (nodeRecommendations || []).forEach(r => {
            const t = r.target_type || r.current_type;
            if (!t) return;
            const price = (r.target_spot_price != null && r.target_spot_price > 0) ? r.target_spot_price : 0;
            const isSpot = r.target_type !== r.current_type || r.lifecycle === 'spot';
            if (!byType[t]) byType[t] = { qty: 0, hourly: price, isSpot };
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

    const optTotal = optimizedConfigRows.reduce((s, r) => s + r.totalMonthly, 0);
    const optInst  = optimizedConfigRows.reduce((s, r) => s + r.qty, 0);
    const optCpu   = optimizedConfigRows.reduce((s, r) => s + r.qty * r.vcpu, 0);
    const optMem   = optimizedConfigRows.reduce((s, r) => s + r.qty * r.memGib, 0);

    /* ── Cost trend chart ──────────────────────────────────────────────── */
    const trendData = useMemo(() => {
        const pts = costTrends?.data_points || costTrends?.points || [];
        if (!pts.length) return [];
        const frac = totalCost > 0 && addlPotential > 0 ? addlPotential / totalCost : 0;
        const now = Date.now();
        const cutoff = trendWindow === '24h' ? now - 86_400_000 : now - 7 * 86_400_000;
        return pts
            .filter(p => new Date(p.timestamp).getTime() >= cutoff)
            .map(p => ({
                // Daily data points — convert to monthly equivalent (×30) so chart
                // Y-axis scale matches the $/mo KPI cards above.
                time: new Date(p.timestamp).toLocaleDateString([], { month: 'numeric', day: 'numeric' }),
                current: +(p.value * 30).toFixed(2),
                optimal: +(p.value * (1 - frac) * 30).toFixed(2),
            }));
    }, [costTrends, trendWindow, totalCost, addlPotential]);

    // trendData values are already $/month (daily × 30); average = avg monthly cost over window.
    // Fallback uses totalCost/addlPotential directly (already monthly).
    const avgMonthly      = trendData.length ? trendData.reduce((s, d) => s + d.current, 0) / trendData.length : totalCost;
    const avgMonthlyOpt   = trendData.length ? trendData.reduce((s, d) => s + d.optimal, 0) / trendData.length : Math.max(0, totalCost - addlPotential);
    const availSavingsPct = avgMonthly > 0 ? ((avgMonthly - avgMonthlyOpt) / avgMonthly) * 100 : savingsPct;

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

    // Available savings = average projected_savings_pct for OD nodes only (real savings opportunity)
    const odRows = spotAnalysisRows.filter(r => r.currentType === 'ON DEMAND');
    const totalAvailSavings = odRows.length > 0
        ? (odRows.reduce((s, r) => s + r.savings, 0) / odRows.length).toFixed(1)
        : spotAnalysisRows.length > 0
            ? (spotAnalysisRows.reduce((s, r) => s + r.savings, 0) / spotAnalysisRows.length).toFixed(1)
            : '0';

    /* ──────────────────────────────────────────────────────────────────── */
    return (
        <div className="space-y-5">

            {/* ── Agent Banner ───────────────────────────────────────── */}
            <div className={`bg-white rounded-lg px-5 py-3 flex items-center justify-between shadow-sm border border-l-4 ${
                isHealthy ? 'border-green-200 border-l-green-500' : 'border-orange-200 border-l-orange-400'
            }`}>
                <div>
                    <div className="flex items-center gap-2">
                        <span className="text-sm font-semibold text-gray-900">{isHealthy ? 'Agent Healthy' : 'Agent Degraded'}</span>
                        <span className="text-[10px] text-gray-400 bg-gray-100 px-1.5 py-0.5 rounded uppercase tracking-wide">
                            {cluster?.version || 'v1.0.0'}
                        </span>
                    </div>
                    <p className="text-xs text-gray-500 mt-0.5">Last heartbeat: {lastHbStr} · Metrics collection active</p>
                </div>
                <div className={`w-2.5 h-2.5 rounded-full flex-shrink-0 ${isHealthy ? 'bg-green-500' : 'bg-orange-400'}`} />
            </div>

            {/* ── Top row: Cost & Savings | Node Composition | Pods ── */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">

                {/* Cost & Savings */}
                <div className="bg-white border border-gray-200 rounded-lg p-4">
                    <p className="text-[10px] font-semibold text-gray-400 uppercase tracking-widest mb-3">Cost &amp; Savings</p>
                    <div className="flex items-center gap-4">
                        <SavingsDonut pct={savingsPct} />
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
                                    <p className="text-sm font-semibold text-orange-500">{formatCurrency(addlPotential)}</p>
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
                            {/* Top row: total + spot-friendly */}
                            <div className="flex items-center gap-3">
                                <div>
                                    <p className="text-2xl font-bold text-gray-900">{totalPods}</p>
                                    <p className="text-[10px] text-gray-400 uppercase tracking-wider">Total Pods</p>
                                </div>
                                <div className="flex-1 bg-green-50 border border-green-100 rounded-lg px-2.5 py-1.5 text-center">
                                    <p className="text-base font-bold text-green-700">{spotFriendlyPods}</p>
                                    <p className="text-[10px] text-green-600 font-medium">Spot-friendly · {spotFriendlyPct.toFixed(0)}%</p>
                                </div>
                                {statefulPods > 0 && (
                                    <div className="flex-1 bg-orange-50 border border-orange-100 rounded-lg px-2.5 py-1.5 text-center">
                                        <p className="text-base font-bold text-orange-600">{statefulPods}</p>
                                        <p className="text-[10px] text-orange-500 font-medium">Stateful pods</p>
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
                        <p className="text-xs font-semibold text-gray-700 mb-1">ASCP.ai</p>
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
                        <p className="text-xs font-semibold text-gray-700 mb-1">Right-Sizing</p>
                        {rsCount > 0 ? (
                            <>
                                <div className="flex items-center gap-1.5 mb-1">
                                    <span className="w-1.5 h-1.5 rounded-full bg-orange-500" />
                                    <span className="text-xs text-orange-600 font-medium">Over-provisioned</span>
                                </div>
                                <p className="text-lg font-bold text-gray-800">{rsCount}</p>
                                <p className="text-[10px] text-gray-400">{formatCurrency(addlPotential)}/mo potential</p>
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
                <div className="px-5 py-3 border-b border-gray-100">
                    <p className="text-sm font-semibold text-gray-800">Karpenter Management</p>
                </div>
                <div className="px-5 py-4 flex items-center justify-between">
                    <div className="flex items-center gap-3">
                        <div>
                            <div className="flex items-center gap-2 mb-1">
                                <span className="text-xs text-gray-500">Status</span>
                                <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded uppercase tracking-wide ${
                                    karpInstalled
                                        ? 'bg-green-100 text-green-700'
                                        : 'bg-gray-100 text-gray-600'
                                }`}>
                                    {karpInstalled ? 'INSTALLED' : 'NOT INSTALLED'}
                                </span>
                                {karpInstalled && karpMode && (
                                    <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded uppercase tracking-wide bg-blue-50 text-blue-600 border border-blue-100">
                                        {karpMode}
                                    </span>
                                )}
                            </div>
                            <p className="text-xs text-gray-500">
                                {karpInstalled
                                    ? spotCount > 0
                                        ? `Active — managing ${spotCount} spot node${spotCount > 1 ? 's' : ''}`
                                        : karpDetectedVia
                                            ? 'Detected in cluster — will provision spot nodes when rebalancer triggers'
                                            : 'Installed — will provision spot nodes when rebalancer triggers'
                                    : 'Not installed — required for spot node provisioning'}
                            </p>
                        </div>
                    </div>
                    {!karpInstalled && (
                        <button
                            onClick={onInstallKarpenter}
                            className="flex items-center gap-1.5 bg-green-600 hover:bg-green-700 text-white text-xs font-semibold px-4 py-2 rounded-lg transition-colors"
                        >
                            <FiDownload className="w-3.5 h-3.5" />
                            Install Karpenter
                        </button>
                    )}
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
                        title="Optimized Cluster Configuration"
                        accent="border-l-green-500"
                        totalLabel="Optimized Cluster Compute Cost:"
                        totalMonthly={optTotal || Math.max(0, totalCost - addlPotential)}
                        totalInstances={optInst}
                        totalCpu={optCpu}
                        totalMem={optMem}
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
                                        <Area type="monotone" dataKey="current" name="current" stroke="#3b82f6" strokeWidth={2} fill="url(#gCurrent)" dot={false} />
                                        <Area type="monotone" dataKey="optimal"  name="optimal"  stroke="#22c55e" strokeWidth={2} fill="url(#gOptimal)"  dot={false} />
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
