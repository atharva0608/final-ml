import React, { useState, useEffect } from 'react';
import useClusters from '../../../hooks/useClusters';
import { optimizeAPI, workloadClassificationAPI, placementPolicyAPI } from '../../../services/api';

const GATE_LABELS = ['Confidence State', 'Spot Friendly Flag', 'Spot Target > 0', 'Rollout Not Blocked', 'Not in System Namespace', 'Data Freshness', 'Distribution Computed'];
const DEFAULT_SYSTEM_NS = new Set(['kube-system', 'kube-public', 'kube-node-lease', 'monitoring', 'cert-manager', 'ingress-nginx', 'flux-system']);

const TIER_STYLE = {
    GOLD:   'bg-amber-50 text-amber-700 border border-amber-200',
    SILVER: 'bg-gray-100 text-gray-600 border border-gray-200',
    BRONZE: 'bg-gray-100 text-gray-500 border border-gray-200',
};
const TIER_LOGIC = {
    GOLD:   'Gold (100% OD Floor)',
    SILVER: 'Silver (50% OD Floor)',
    BRONZE: 'Bronze (0% OD Floor)',
};
function critColor(score) {
    if (score >= 7) return '#dc2626';
    if (score >= 5) return '#D97706';
    return '#059669';
}
function confColor(state) {
    if (state === 'CONFIRMED')   return '#059669';
    if (state === 'PROVISIONAL') return '#D97706';
    return '#9ca3af';
}

function readiness(state) {
    if (state === 'CONFIRMED')   return { label: 'Ready',    style: 'bg-green-50 border-green-200 text-green-700' };
    if (state === 'PROVISIONAL') return { label: 'Review',   style: 'bg-amber-50 border-amber-200 text-amber-700' };
    return                              { label: 'Observing', style: 'bg-gray-100 border-gray-300 text-gray-600' };
}

function buildCpuPath(timeseries) {
    if (!timeseries || timeseries.length === 0) return null;
    const vals = timeseries.map(t => t.avg_cpu_millicores || 0);
    const max  = Math.max(...vals, 1);
    const pts  = vals.slice(-11);
    const step = pts.length > 1 ? 100 / (pts.length - 1) : 0;
    return pts.map((v, i) => {
        const x = Math.round(i * step);
        const y = Math.round(38 - (v / max) * 34);
        return `${i === 0 ? 'M' : 'L'}${x},${y}`;
    }).join(' ');
}

function mapListItem(w) {
    const minOD   = w.min_on_demand_replicas ?? null;
    const maxSpot = w.max_spot_replicas ?? null;
    const totR    = (w.total_replicas ?? ((minOD ?? 0) + (maxSpot ?? 0))) || null;
    return {
        id:           w.workload_id,
        name:         w.workload_id ? w.workload_id.split('/').pop() : w.namespace,
        ns:           w.namespace || '—',
        tier:         w.tier || 'BRONZE',
        conf:         w.confidence_score || 0,
        confLabel:    w.confidence_state || 'DRAFT',
        confPct:      `${Math.round((w.confidence_score || 0) * 10)}%`,
        spotScore:    w.spot_score || 0,
        spotPct:      Math.round((w.spot_score || 0) * 10),
        spotFriendly: w.spot_friendly || false,
        spotEligible: w.spot_eligible ?? (w.spot_friendly || false),
        minOD,
        maxSpot,
        totalReplicas: totR,
        workloadClass: w.workload_class || null,
        controllerKind: w.controller_kind || null,
        role: w.role || null,
        critScore:    w.criticality_score || 0,
        critPct:      Math.round((w.criticality_score || 0) * 10),
        critColor:    critColor(w.criticality_score || 0),
        confColor:    confColor(w.confidence_state),
        readiness:    readiness(w.confidence_state),
        signals:      w.signals_fired || [],
        cpuStable:    !w.traffic_skew_detected,
        savings:      w.estimated_monthly_saving_usd || 0,
        isDbWorkload: w.workload_class === 'db' || (
            (w.controller_kind === 'StatefulSet') &&
            ['redis', 'postgres', 'mysql', 'mongo', 'cassandra', 'elasticsearch'].some(k => (w.workload_id || '').toLowerCase().includes(k))
        ),
        distributionSet: (w.min_on_demand_replicas != null && w.max_spot_replicas != null) &&
            ((w.min_on_demand_replicas + w.max_spot_replicas) > 0),
    };
}

export default function WorkloadProfiling() {
    const { clusters, selectedId: clusterId, setSelectedId: setClusterId } = useClusters();
    const [workloads, setWorkloads] = useState([]);
    const [apiSummary, setApiSummary] = useState({});
    const [selectedId, setSelectedId] = useState(null);
    const [detail, setDetail]         = useState(null);
    const [search, setSearch]         = useState('');
    const [confFilter, setConfFilter] = useState('all');
    const [loading, setLoading]       = useState(false);
    const [detailLoading, setDetailLoading] = useState(false);
    const [error, setError]           = useState(null);
    const [advisorRunning, setAdvisorRunning] = useState(false);
    const [advisorMsg, setAdvisorMsg]         = useState(null);
    const [systemNS, setSystemNS]             = useState(DEFAULT_SYSTEM_NS);
    const [rescanRunning, setRescanRunning]   = useState(false);
    const [rescanMsg, setRescanMsg]           = useState(null);

    function runRescan() {
        if (!clusterId || rescanRunning) return;
        setRescanRunning(true);
        setRescanMsg(null);
        workloadClassificationAPI.rescan(clusterId)
            .then(() => {
                setRescanMsg('WIE rescan triggered — refreshing in 8s…');
                setTimeout(() => {
                    setRescanMsg(null);
                    setRescanRunning(false);
                    // Re-fetch workload list and summary
                    Promise.all([
                        workloadClassificationAPI.getWorkloads(clusterId, { page_size: 200 }),
                        workloadClassificationAPI.getSummary(clusterId),
                    ]).then(([wRes, sRes]) => {
                        const items = wRes.data?.items || wRes.data || [];
                        setWorkloads(Array.isArray(items) ? items.map(mapListItem) : []);
                        setApiSummary(sRes.data || {});
                    }).catch(() => {});
                }, 8000);
            })
            .catch(err => {
                setRescanMsg(err?.response?.data?.detail || 'Rescan trigger failed.');
                setRescanRunning(false);
            });
    }

    function runAdvisorCycle() {
        if (!clusterId || advisorRunning) return;
        setAdvisorRunning(true);
        setAdvisorMsg(null);
        placementPolicyAPI.generate(clusterId)
            .then(() => setAdvisorMsg('Advisor cycle queued — policies will refresh shortly.'))
            .catch(err => setAdvisorMsg(err?.response?.data?.detail || 'Advisor trigger failed.'))
            .finally(() => setAdvisorRunning(false));
    }

    useEffect(() => {
        if (!clusterId) return;
        workloadClassificationAPI.getSystemNamespaces(clusterId)
            .then(res => {
                const effective = res.data?.effective || [];
                setSystemNS(effective.length > 0 ? new Set(effective) : DEFAULT_SYSTEM_NS);
            })
            .catch(() => setSystemNS(DEFAULT_SYSTEM_NS));
    }, [clusterId]);

    useEffect(() => {
        if (!clusterId) return;
        setLoading(true);
        setError(null);
        Promise.all([
            workloadClassificationAPI.getWorkloads(clusterId, { page_size: 100 }),
            workloadClassificationAPI.getSummary(clusterId),
        ])
            .then(([wlRes, sumRes]) => {
                const items = wlRes.data?.workloads || wlRes.data?.items || [];
                const mapped = items.map(mapListItem);
                setWorkloads(mapped);
                setApiSummary(sumRes.data || {});
                if (mapped.length > 0) setSelectedId(prev => prev || mapped[0].id);
            })
            .catch(err => setError(err?.response?.data?.detail || err?.message || 'Failed to load workloads'))
            .finally(() => setLoading(false));
    }, [clusterId]);

    useEffect(() => {
        if (!selectedId || !clusterId) return;
        setDetailLoading(true);
        setDetail(null);
        optimizeAPI.getWorkloadProfilingDetail(selectedId, clusterId)
            .then(res => setDetail(res.data))
            .catch(() => setDetail(null))
            .finally(() => setDetailLoading(false));
    }, [selectedId, clusterId]);

    const w = workloads.find(x => x.id === selectedId) || workloads[0] || null;

    const CONF_RANK = { CONFIRMED: 0, PROVISIONAL: 1, DRAFT: 2 };
    const filtered = workloads
        .filter(x => {
            const s = x.name.toLowerCase().includes(search.toLowerCase()) || x.ns.toLowerCase().includes(search.toLowerCase());
            const c = confFilter === 'all' || x.confLabel.toLowerCase() === confFilter.toLowerCase();
            return s && c;
        })
        .sort((a, b) => {
            if (b.spotFriendly !== a.spotFriendly) return b.spotFriendly ? 1 : -1;
            const cr = (CONF_RANK[a.confLabel] ?? 3) - (CONF_RANK[b.confLabel] ?? 3);
            if (cr !== 0) return cr;
            return b.spotScore - a.spotScore;
        });

    const totalSavings = detail?.estimated_monthly_saving_usd || 0;
    const od  = detail?.ondemand_target || 0;
    const spt = detail?.spot_target     || 0;
    const total = od + spt || 1;
    const wieMinOD   = detail?.min_on_demand_replicas ?? null;
    const wieMaxSpot = detail?.max_spot_replicas ?? null;
    const wieTotal   = (wieMinOD ?? 0) + (wieMaxSpot ?? 0) || 1;
    const dataSafety = detail?.data_safety || w?.dataSafety || null;
    const cpuCV   = detail?.cpu_cv ?? null;
    const cpuStable = cpuCV != null ? cpuCV < 0.4 : (w?.cpuStable ?? true);
    const cpuPath = buildCpuPath(detail?.cpu_timeseries);

    const gates = w ? [
        w.confLabel === 'CONFIRMED' ? 'pass' : 'fail',
        w.spotFriendly ? 'pass' : 'fail',
        spt > 0 ? 'pass' : 'fail',
        detail ? (detail.rollout_eligible === true ? 'pass' : 'fail') : 'pending',
        !systemNS.has(w.ns) ? 'pass' : 'fail',
        detail ? (detail.data_ready ? 'pass' : 'fail') : 'fail',
        w.distributionSet ? 'pass' : 'fail',
    ] : [];
    const allPass = gates.every(g => g === 'pass');

    const nonDaemonWorkloads = workloads.filter(x => x.controllerKind !== 'DaemonSet' && x.role !== 'SYSTEM');
    const fullySpotCount    = nonDaemonWorkloads.filter(x => (x.maxSpot ?? 0) > 0 && (x.minOD ?? 0) === 0).length;
    const partiallySpotCount = nonDaemonWorkloads.filter(x => (x.maxSpot ?? 0) > 0 && (x.minOD ?? 0) > 0).length;
    const spotFriendlyFallbackCount = nonDaemonWorkloads.filter(x => x.spotFriendly && (x.maxSpot ?? 0) === 0 && (x.minOD ?? 0) === 0).length;
    const odOnlyCount        = nonDaemonWorkloads.filter(x => !x.spotFriendly).length;
    const daemonSetCount     = workloads.filter(x => x.controllerKind === 'DaemonSet' || x.role === 'SYSTEM').length;

    const sumStrip = [
        { l: 'Total Workloads',   v: loading ? '…' : (apiSummary.total_workloads ?? apiSummary.total ?? workloads.length), c: 'text-gray-900' },
        { l: 'CONFIRMED',         v: loading ? '…' : (apiSummary.confirmed_count ?? apiSummary.confidence_distribution?.CONFIRMED ?? '—'),           c: 'text-green-600' },
        { l: 'PROVISIONAL',       v: loading ? '…' : (apiSummary.provisional_count ?? apiSummary.confidence_distribution?.PROVISIONAL ?? '—'),       c: 'text-amber-600' },
        { l: 'Fully Spot',        v: loading ? '…' : fullySpotCount,    c: 'text-indigo-700',
          tip: 'All replicas can run on spot — 0 OD floor required' },
        { l: 'Partial Spot',      v: loading ? '…' : partiallySpotCount, c: 'text-blue-600',
          tip: 'Mix of OD (safety floor) + spot replicas allowed' },
        { l: 'OD Only',           v: loading ? '…' : odOnlyCount,        c: 'text-red-500',
          tip: 'DB, Redis, StatefulSet primaries — 0 spot allowed' },
        { l: 'Node-Wide',          v: loading ? '…' : daemonSetCount,     c: 'text-gray-400',
          tip: 'DaemonSet — runs on all nodes, not placement-managed' },
        { l: 'Potential Savings', v: loading ? '…' : (apiSummary.total_estimated_saving_usd != null ? `$${Math.round(apiSummary.total_estimated_saving_usd).toLocaleString()}` : '—'), c: 'text-green-600' },
    ];

    return (
        <div className="flex flex-col bg-gray-50 min-h-full">
            {/* Header */}
            <div className="bg-white border-b border-gray-200 px-6 pt-4 pb-3">
                <div className="flex items-center justify-between mb-1">
                    <span className="text-xs text-gray-400 tracking-wide">Optimize / Workloads / Profiling</span>
                    <div className="flex items-center gap-3">
                        <div>
                            <label className="text-xs font-medium text-gray-500 mr-1">Cluster:</label>
                            <select
                                value={clusterId}
                                onChange={e => { setSelectedId(null); setClusterId(e.target.value); }}
                                className="text-xs border border-gray-300 rounded px-2 py-1 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                            >
                                <option value="" disabled>Select</option>
                                {clusters.map(c => <option key={c.id} value={c.id}>{c.name || c.id}</option>)}
                            </select>
                        </div>
                        <button
                            onClick={runRescan}
                            disabled={!clusterId || rescanRunning}
                            title={clusterId ? 'Force WIE reclassification — updates spot_friendly and tier scores' : 'Select a cluster first'}
                            className={`px-3 py-1.5 text-xs font-semibold rounded-lg transition-colors ${
                                rescanRunning ? 'bg-emerald-400 text-white cursor-wait' :
                                !clusterId ? 'bg-emerald-300 text-white opacity-50 cursor-not-allowed' :
                                'bg-emerald-600 hover:bg-emerald-700 text-white cursor-pointer'
                            }`}
                        >{rescanRunning ? '⏳ Scanning…' : '🔄 Rescan Classifications'}</button>
                        <button
                            onClick={runAdvisorCycle}
                            disabled={!clusterId || advisorRunning}
                            title={clusterId ? 'Trigger placement policy generation for this cluster' : 'Select a cluster first'}
                            className={`px-3 py-1.5 text-xs font-semibold rounded-lg transition-colors ${
                                advisorRunning ? 'bg-blue-400 text-white cursor-wait' :
                                !clusterId ? 'bg-blue-300 text-white opacity-50 cursor-not-allowed' :
                                'bg-blue-600 hover:bg-blue-700 text-white cursor-pointer'
                            }`}
                        >{advisorRunning ? '⏳ Running…' : '▶ Run Advisor Cycle'}</button>
                    </div>
                </div>
                <h1 className="text-base font-bold text-gray-900">Workload Profiling</h1>
                <p className="text-xs text-gray-400 mt-0.5">WIE classification scores, Spot-readiness signals, traffic variance, and Placement Advisor targets per workload</p>
            </div>

            {error && <div className="mx-6 mt-2 bg-red-50 border border-red-200 rounded-lg px-4 py-2 text-xs text-red-700">{error}</div>}
            {rescanMsg && <div className="mx-6 mt-2 bg-emerald-50 border border-emerald-200 rounded-lg px-4 py-2 text-xs text-emerald-700">{rescanMsg}</div>}
            {advisorMsg && <div className="mx-6 mt-2 bg-blue-50 border border-blue-200 rounded-lg px-4 py-2 text-xs text-blue-700">{advisorMsg}</div>}

            {/* Summary Strip */}
            <div className="bg-white border-b border-gray-100 px-6 py-2.5 flex flex-wrap gap-6 text-sm">
                {sumStrip.map((s, i, arr) => (
                    <React.Fragment key={s.l}>
                        <div className="flex flex-col" title={s.tip || ''}>
                            <span className="text-[10px] font-bold tracking-wider uppercase text-gray-400 mb-0.5">{s.l}</span>
                            <span className={`font-bold text-base leading-tight ${s.c}`}>{s.v}</span>
                        </div>
                        {i < arr.length - 1 && <div className="w-px bg-gray-200 h-8 my-auto" />}
                    </React.Fragment>
                ))}
            </div>

            {/* Filter Bar */}
            <div className="bg-gray-50 border-b border-gray-200 px-6 py-2 flex items-center gap-4 flex-wrap text-xs">
                <div className="relative">
                    <span className="absolute left-2.5 top-1/2 -translate-y-1/2 text-gray-400">🔍</span>
                    <input
                        value={search} onChange={e => setSearch(e.target.value)}
                        placeholder="Search workloads..."
                        className="pl-8 pr-3 py-1.5 bg-white border border-gray-200 rounded-md text-xs focus:outline-none focus:border-blue-400 w-52"
                    />
                </div>
                <div className="h-4 w-px bg-gray-200" />
                <span className="text-gray-500 font-semibold">Confidence:</span>
                {[['all', 'All'], ['confirmed', 'CONFIRMED'], ['provisional', 'PROVISIONAL'], ['draft', 'DRAFT']].map(([v, l]) => (
                    <button key={v} onClick={() => setConfFilter(v)}
                        className={`px-2.5 py-1 rounded font-medium transition-colors ${confFilter === v ? 'bg-gray-800 text-white' : 'bg-white border border-gray-200 text-gray-600 hover:bg-gray-50'}`}
                    >{l}</button>
                ))}
            </div>

            {/* Split Panel */}
            <div className="flex flex-1 overflow-hidden" style={{ height: 'calc(100vh - 240px)' }}>

                {/* LEFT — List */}
                <div className="w-[42%] bg-white border-r border-gray-200 overflow-hidden flex flex-col">
                    <div className="grid grid-cols-12 gap-2 px-5 py-2 text-[10px] font-bold tracking-wider text-gray-400 uppercase border-b border-gray-100 bg-white sticky top-0">
                        <div className="col-span-4">Workload</div>
                        <div className="col-span-2">Tier</div>
                        <div className="col-span-2">Readiness</div>
                        <div className="col-span-2">Spot Score</div>
                        <div className="col-span-2 text-right">Savings</div>
                    </div>
                    <div className="flex-1 overflow-y-auto p-2 space-y-0.5">
                        {loading ? (
                            <div className="text-center py-8 text-xs text-gray-500">Loading workloads...</div>
                        ) : !clusterId ? (
                            <div className="text-center py-8 text-xs text-gray-400">Select a cluster.</div>
                        ) : filtered.length === 0 ? (
                            <div className="text-center py-8 text-xs text-gray-400">No workloads found.</div>
                        ) : filtered.map((row, idx) => {
                            const active = row.id === selectedId;
                            const prevRow = filtered[idx - 1];
                            const showDivider = idx > 0 && !row.spotFriendly && prevRow?.spotFriendly;
                            return (
                                <React.Fragment key={row.id}>
                                {showDivider && (
                                    <div className="flex items-center gap-2 px-2 py-1.5">
                                        <div className="flex-1 h-px bg-gray-200" />
                                        <span className="text-[9px] font-bold text-gray-400 uppercase tracking-wider">Not Spot Ready</span>
                                        <div className="flex-1 h-px bg-gray-200" />
                                    </div>
                                )}
                                <div onClick={() => setSelectedId(row.id)}
                                    className={`grid grid-cols-12 gap-2 px-4 py-2.5 rounded-lg cursor-pointer transition-all relative ${
                                        active
                                            ? 'bg-blue-50 border border-blue-200'
                                            : row.spotFriendly
                                                ? 'bg-green-50/60 border border-green-100 hover:bg-green-50'
                                                : 'hover:bg-gray-50 border border-transparent'
                                    }`}>
                                    {active && <div className="absolute left-0 top-1 bottom-1 w-1 bg-blue-600 rounded-r" />}
                                    <div className="col-span-4 flex items-center gap-2">
                                        <div className={`w-1.5 h-1.5 rounded-full shrink-0 ${row.cpuStable ? 'bg-green-500' : 'bg-amber-500'}`} />
                                        <div className="min-w-0">
                                            <div className="font-mono text-xs font-semibold text-gray-900 truncate">{row.name}</div>
                                            <div className="text-[10px] text-gray-400 truncate">{row.ns}</div>
                                            <div className="flex items-center gap-1 mt-0.5">
                                                {row.isDbWorkload ? (
                                                    <span className="px-1 py-0 text-[9px] font-bold rounded bg-red-100 text-red-700 border border-red-200">Always OD</span>
                                                ) : row.distributionSet ? (
                                                    <>
                                                        <span className="px-1 py-0 text-[9px] font-semibold rounded bg-gray-100 text-gray-600 border border-gray-200">OD:{row.minOD}</span>
                                                        <span className="px-1 py-0 text-[9px] font-semibold rounded bg-indigo-50 text-indigo-700 border border-indigo-200">Spot:{row.maxSpot}</span>
                                                    </>
                                                ) : (
                                                    <span className="px-1 py-0 text-[9px] font-semibold rounded bg-amber-50 text-amber-600 border border-amber-200">Dist pending</span>
                                                )}
                                            </div>
                                        </div>
                                    </div>
                                    <div className="col-span-2 flex items-center">
                                        <span className={`px-1.5 py-0.5 text-[9px] font-bold rounded-full tracking-wider ${TIER_STYLE[row.tier] || TIER_STYLE.BRONZE}`}>{row.tier}</span>
                                    </div>
                                    <div className="col-span-2 flex items-center">
                                        <span className={`text-[10px] font-semibold px-1.5 py-0.5 rounded border ${row.readiness.style}`}>{row.readiness.label}</span>
                                    </div>
                                    <div className="col-span-2 flex items-center gap-1.5">
                                        <div className="flex-1 h-1.5 bg-gray-100 rounded-full overflow-hidden">
                                            <div className="h-full bg-blue-600" style={{ width: `${row.spotPct}%` }} />
                                        </div>
                                        <span className="text-[10px] font-semibold text-gray-600 w-6 text-right">{row.spotScore.toFixed(1)}</span>
                                    </div>
                                    <div className="col-span-2 flex items-center justify-end">
                                        <span className={`text-xs font-semibold ${row.savings > 0 ? 'text-green-600' : 'text-gray-400'}`}>${row.savings}</span>
                                    </div>
                                </div>
                                </React.Fragment>
                            );
                        })}
                    </div>
                </div>

                {/* RIGHT — Deep Dive */}
                {!w ? (
                    <div className="flex-1 flex items-center justify-center text-sm text-gray-400">Select a cluster and workload.</div>
                ) : (
                <div className="flex-1 bg-gray-50 overflow-y-auto p-6 space-y-6">

                    {/* Identity */}
                    <div>
                        <div className="flex items-center justify-between mb-3">
                            <h2 className="text-lg font-bold text-gray-900 font-mono">{w.name}</h2>
                            <div className="flex items-center gap-2 flex-wrap justify-end">
                                {/* Spot classification badge */}
                                {(() => {
                                    // DaemonSets are node-wide — OD/Spot classification does not apply
                                    if (w.controllerKind === 'DaemonSet' || w.role === 'SYSTEM') return (
                                        <span className="px-2.5 py-1 text-[11px] font-bold rounded border flex items-center gap-1 uppercase tracking-wider bg-gray-100 text-gray-500 border-gray-300">
                                            ⬡ NODE WIDE
                                        </span>
                                    );
                                    const hasDistribution = (w.maxSpot ?? 0) > 0 || (w.minOD ?? 0) > 0;
                                    // Partial: has explicit OD floor AND some spot allowed
                                    const isPartial = (w.minOD ?? 0) > 0 && (w.maxSpot ?? 0) > 0;
                                    // Full spot: no OD floor, spot > 0
                                    const isFullSpot = (w.maxSpot ?? 0) > 0 && (w.minOD ?? 0) === 0;
                                    // Fallback for old records without distribution data: use spot_friendly flag
                                    const isFriendlyFallback = !hasDistribution && w.spotFriendly;
                                    // OD only: has distribution data and no spot allowed, OR not spot friendly at all
                                    const isOdOnly = hasDistribution && (w.maxSpot ?? 0) === 0;

                                    if (isFullSpot) return (
                                        <>
                                            <span className="px-2.5 py-1 text-[11px] font-bold rounded border flex items-center gap-1 uppercase tracking-wider bg-indigo-50 text-indigo-700 border-indigo-200">
                                                ⚡ FULLY SPOT
                                            </span>
                                            <span className="text-[11px] text-gray-500 font-mono">All {w.maxSpot} pods → Spot</span>
                                        </>
                                    );
                                    if (isPartial) return (
                                        <>
                                            <span className="px-2.5 py-1 text-[11px] font-bold rounded border flex items-center gap-1 uppercase tracking-wider bg-blue-50 text-blue-700 border-blue-200">
                                                ⚡ PARTIALLY SPOT
                                            </span>
                                            <span className="text-[11px] text-gray-500 font-mono">{w.minOD} OD · {w.maxSpot} Spot</span>
                                        </>
                                    );
                                    if (isFriendlyFallback) return (
                                        <>
                                            <span className="px-2.5 py-1 text-[11px] font-bold rounded border flex items-center gap-1 uppercase tracking-wider bg-green-50 text-green-700 border-green-200">
                                                ⚡ SPOT FRIENDLY
                                            </span>
                                            <span className="text-[10px] text-gray-400 italic">rescan to compute distribution</span>
                                        </>
                                    );
                                    if (isOdOnly || !w.spotFriendly) return (
                                        <span className="px-2.5 py-1 text-[11px] font-bold rounded border flex items-center gap-1 uppercase tracking-wider bg-red-50 text-red-700 border-red-200">
                                            ⛔ OD ONLY
                                        </span>
                                    );
                                    return null;
                                })()}
                            </div>
                        </div>
                        <div className="grid grid-cols-5 gap-4 text-xs">
                            {[['Namespace', w.ns], ['Tier', w.tier], ['Confidence', `${w.confLabel} (${w.confPct})`], ['Status', w.confLabel === 'CONFIRMED' ? 'Active Profile' : w.confLabel === 'PROVISIONAL' ? 'Observing' : 'Learning'], ['Data Safety', dataSafety || '—']].map(([l, v]) => (
                                <div key={l}>
                                    <span className="block text-[10px] font-bold text-gray-400 uppercase tracking-wider mb-0.5">{l}</span>
                                    <span className="text-gray-800 font-medium font-mono text-xs">{v}</span>
                                </div>
                            ))}
                        </div>
                    </div>

                    {/* WIE Spot Eligibility */}
                    <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm">
                        <h3 className="text-xs font-bold text-gray-700 mb-0.5 uppercase tracking-wider">WIE Spot Eligibility</h3>
                        <p className="text-[10px] text-gray-400 mb-3">Maximum allowed distribution — actual placement decided by the Planner based on capacity &amp; confidence</p>
                        {w.isDbWorkload ? (
                            <div className="flex items-center gap-3 flex-wrap">
                                <span className="text-2xl font-bold text-red-600">Always OD</span>
                                <span className="px-2 py-0.5 text-[10px] font-bold rounded bg-red-50 border border-red-200 text-red-700">DB workload</span>
                                <p className="text-xs text-gray-500 w-full mt-1">StatefulSet with DB-class name detected — 0 spot replicas allowed, all pods must remain on-demand.</p>
                            </div>
                        ) : w.distributionSet ? (
                            <div className="space-y-3">
                                <div className="flex items-baseline gap-3">
                                    <span className="text-2xl font-bold text-gray-800 font-mono">{w.minOD} OD</span>
                                    <span className="text-gray-400">+</span>
                                    <span className="text-2xl font-bold text-indigo-700 font-mono">{w.maxSpot} Spot</span>
                                    <span className="text-gray-400 text-sm">= {(w.minOD ?? 0) + (w.maxSpot ?? 0)} total</span>
                                </div>
                                <div className="flex items-center gap-2 flex-wrap text-[10px]">
                                    {w.workloadClass && (
                                        <span className={`px-2 py-0.5 font-bold rounded border uppercase ${
                                            w.workloadClass === 'db'         ? 'bg-red-50 text-red-700 border-red-200' :
                                            w.workloadClass === 'stateful'   ? 'bg-amber-50 text-amber-700 border-amber-200' :
                                            w.workloadClass === 'stateless'  ? 'bg-green-50 text-green-700 border-green-200' :
                                            'bg-gray-100 text-gray-600 border-gray-200'
                                        }`}>
                                            {w.workloadClass === 'db' ? 'DB' : w.workloadClass === 'stateful' ? 'Stateful' : w.workloadClass === 'stateless' ? 'Stateless' : w.workloadClass}
                                        </span>
                                    )}
                                    <span className="text-gray-400">{
                                        w.workloadClass === 'db'        ? 'Always on-demand' :
                                        w.workloadClass === 'stateful'  ? 'Mixed placement' :
                                        w.workloadClass === 'stateless' ? 'Spot preferred' :
                                        'Distribution computed by WIE'
                                    }</span>
                                </div>
                            </div>
                        ) : (
                            <div className="flex items-center gap-2">
                                <span className="px-2 py-1 text-xs font-bold rounded bg-amber-50 border border-amber-200 text-amber-700">Distribution Pending</span>
                                <span className="text-xs text-gray-500">Run a WIE rescan to compute OD/Spot distribution for this workload.</span>
                            </div>
                        )}
                    </div>

                    {/* WIE Score Cards */}
                    <div>
                        <h3 className="text-xs font-bold text-gray-700 mb-3">WIE Assessment Scores</h3>
                        <div className="grid grid-cols-3 gap-3">
                            {[
                                { label: 'Criticality', score: w.critScore, pct: w.critPct, color: w.critColor },
                                { label: 'Spot Score',  score: w.spotScore, pct: w.spotPct, color: '#2563eb' },
                                { label: 'Confidence',  score: w.conf,      pct: w.conf * 10, color: w.confColor },
                            ].map(card => (
                                <div key={card.label} className="bg-white rounded-xl border border-gray-200 p-4 shadow-sm flex flex-col">
                                    <div className="text-[10px] font-bold text-gray-400 uppercase tracking-wider mb-2">{card.label}</div>
                                    <div className="flex items-baseline gap-1 mb-2">
                                        <span className="text-2xl font-bold text-gray-900 leading-none">{card.score.toFixed(1)}</span>
                                        <span className="text-[11px] text-gray-400">/10</span>
                                    </div>
                                    <div className="h-1 bg-gray-100 rounded-full mb-3 overflow-hidden">
                                        <div className="h-full rounded-full" style={{ width: `${card.pct}%`, backgroundColor: card.color }} />
                                    </div>
                                </div>
                            ))}
                        </div>
                    </div>

                    {/* Signals */}
                    <div>
                        <h3 className="text-[10px] font-bold tracking-widest text-gray-400 uppercase mb-2">Signals Used in Scoring</h3>
                        <div className="flex gap-2 flex-wrap">
                            {w.signals.length > 0
                                ? w.signals.map(s => <span key={s} className="px-2 py-1 text-[10px] font-medium bg-green-50 text-green-700 rounded border border-green-200">{s}</span>)
                                : <span className="text-xs text-gray-400 italic">No signals available.</span>
                            }
                        </div>
                    </div>

                    {/* Traffic Variance */}
                    <div>
                        <h3 className="text-xs font-bold text-gray-700 mb-1">Traffic &amp; Load Variance (14d)</h3>
                        <p className="text-[11px] italic text-gray-400 mb-3">CV &gt; 40% raises OD target above tier floor.</p>
                        <div className="bg-white rounded-xl border border-gray-200 p-4 shadow-sm">
                            <div className="text-[10px] font-bold text-gray-400 uppercase tracking-wider mb-2">CPU Usage (Cores) — 14-day daily average</div>
                            <div className="h-16 w-full">
                                {detailLoading ? (
                                    <div className="h-full flex items-center justify-center text-[10px] text-gray-400">Loading...</div>
                                ) : cpuPath ? (
                                    <svg className="w-full h-full" viewBox="0 0 100 40" preserveAspectRatio="none">
                                        <path d={cpuPath} fill="none" stroke={cpuStable ? '#059669' : '#dc2626'} strokeWidth="1.5" />
                                    </svg>
                                ) : (
                                    <div className="h-full flex items-center justify-center text-[10px] text-gray-400 italic">No timeseries data</div>
                                )}
                            </div>
                            <div className="mt-2 flex items-center gap-4">
                                <span className={`font-bold text-sm ${cpuStable ? 'text-green-600' : 'text-red-600'}`}>
                                    {cpuCV != null ? `CV: ${cpuCV.toFixed(2)}` : 'CV: —'}
                                </span>
                                <span className="text-[10px] text-gray-400">{cpuStable ? 'Stable — no OD adjustment' : 'Skew detected — OD baseline raised'}</span>
                            </div>
                        </div>
                        <p className="text-[10px] text-gray-400 italic mt-2">Variability measured over 14-day window. CV &gt; 0.4 raises OD baseline.</p>
                    </div>

                    {/* Pod Distribution */}
                    <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm">
                        <h3 className="text-sm font-bold text-gray-900 mb-4">Pod Distribution</h3>
                        {detailLoading ? (
                            <div className="text-xs text-gray-400 py-4 text-center">Loading distribution...</div>
                        ) : (
                        <div className="space-y-4">
                            {/* WIE Constraint row */}
                            <div>
                                <div className="flex justify-between text-[10px] font-bold uppercase tracking-wider text-gray-400 mb-1.5">
                                    <span>WIE Constraint (min OD / max Spot)</span>
                                    <span>{wieMinOD ?? '—'} OD + {wieMaxSpot ?? '—'} Spot = {wieTotal} pods</span>
                                </div>
                                <div className="flex h-7 rounded-md overflow-hidden shadow-inner text-[11px] font-mono">
                                    {(wieMinOD ?? 0) > 0 && (
                                        <div className="bg-orange-600 text-white flex items-center justify-center font-bold transition-all"
                                            style={{ width: `${((wieMinOD ?? 0) / wieTotal) * 100}%` }}>
                                            {wieMinOD} OD
                                        </div>
                                    )}
                                    {(wieMaxSpot ?? 0) > 0 && (
                                        <div className="bg-blue-600 text-white flex items-center justify-center font-bold transition-all"
                                            style={{ width: `${((wieMaxSpot ?? 0) / wieTotal) * 100}%` }}>
                                            {wieMaxSpot} Spot
                                        </div>
                                    )}
                                    {(wieMinOD == null && wieMaxSpot == null) && (
                                        <div className="flex-1 bg-gray-100 flex items-center justify-center text-gray-400 text-[10px]">
                                            No WIE distribution yet — rescan to populate
                                        </div>
                                    )}
                                </div>
                            </div>
                            {/* Policy Target row */}
                            <div>
                                <div className="flex justify-between text-[10px] font-bold uppercase tracking-wider text-gray-400 mb-1.5">
                                    <span>Placement Policy Target</span>
                                    <span>{od} OD + {spt} Spot = {total} pods</span>
                                </div>
                                <div className="flex h-7 rounded-md overflow-hidden shadow-inner text-[11px] font-mono">
                                    {od > 0 && (
                                        <div className="bg-red-600 text-white flex items-center justify-center font-bold transition-all"
                                            style={{ width: `${(od / total) * 100}%` }}>
                                            {od} OD
                                        </div>
                                    )}
                                    {spt > 0 && (
                                        <div className="bg-indigo-700 text-white flex items-center justify-center font-bold transition-all"
                                            style={{ width: `${(spt / total) * 100}%` }}>
                                            {spt} Spot
                                        </div>
                                    )}
                                    {od === 0 && spt === 0 && (
                                        <div className="flex-1 bg-gray-100 flex items-center justify-center text-gray-400 text-[10px]">
                                            No policy target — run Advisor Cycle
                                        </div>
                                    )}
                                </div>
                            </div>
                            {/* Summary row */}
                            <div className="grid grid-cols-3 gap-3 pt-3 border-t border-gray-100">
                                <div className="text-center">
                                    <div className="text-[10px] uppercase font-bold tracking-wider text-gray-400 mb-1">Est. Saving</div>
                                    <div className="text-sm font-bold text-green-600">{detail ? `$${totalSavings.toFixed(2)}` : '—'}</div>
                                </div>
                                <div className="text-center">
                                    <div className="text-[10px] uppercase font-bold tracking-wider text-gray-400 mb-1">Tier Logic</div>
                                    <div className="text-xs font-semibold text-gray-700">{TIER_LOGIC[w.tier] || '—'}</div>
                                </div>
                                <div className="text-center">
                                    <div className="text-[10px] uppercase font-bold tracking-wider text-gray-400 mb-1">CV Adjust</div>
                                    <div className="text-xs font-semibold text-gray-700">{cpuCV != null ? (cpuCV >= 0.4 ? 'OD raised' : 'None') : '—'}</div>
                                </div>
                            </div>
                        </div>
                        )}
                    </div>

                    {/* Actionability Gates */}
                    <div>
                        <h3 className="text-xs font-bold text-gray-700 mb-3">Advisor Actionability Gates</h3>
                        <div className="bg-white border border-gray-200 rounded-xl overflow-hidden shadow-sm">
                            <div className={`px-4 py-2.5 border-b border-gray-100 flex items-center justify-between ${allPass ? 'bg-green-50' : 'bg-red-50'}`}>
                                <span className="text-xs font-bold text-gray-800">Overall Status</span>
                                <span className={`text-[10px] font-bold uppercase tracking-wider ${allPass ? 'text-green-600' : 'text-red-600'}`}>
                                    {allPass ? 'READY FOR AUTOMATION' : 'BLOCKED BY RULES'}
                                </span>
                            </div>
                            <div className="divide-y divide-gray-50">
                                {GATE_LABELS.map((label, i) => {
                                    const g = gates[i];
                                    const pass = g === 'pass';
                                    const pending = g === 'pending';
                                    const extraHint = (i === 3 && !pass && !pending && detail?.rollout_blocked_reason)
                                        ? ` (${detail.rollout_blocked_reason})` : '';
                                    return (
                                        <div key={label} className="flex items-center justify-between px-4 py-2.5 text-xs">
                                            <div className="flex items-center gap-2">
                                                <span className={pass ? 'text-green-500' : pending ? 'text-gray-400' : 'text-red-500'}>{pass ? '✓' : pending ? '…' : '✗'}</span>
                                                <span className="font-medium text-gray-800">{label}</span>
                                            </div>
                                            <span className={pass ? 'text-gray-400' : pending ? 'text-gray-400' : 'text-red-500 font-medium'}>
                                                {pass ? 'Pass' : pending ? 'Pending' : `Fail${extraHint}`}
                                            </span>
                                        </div>
                                    );
                                })}
                            </div>
                        </div>
                    </div>

                </div>
                )}
            </div>
        </div>
    );
}
