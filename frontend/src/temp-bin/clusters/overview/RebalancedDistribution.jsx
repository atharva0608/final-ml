/**
 * RebalancedDistribution v2
 * Real-time BFD-TSC recommended node layout with pod-to-node placement,
 * placement score breakdown with 4-factor explanation, Buffer node callout,
 * 60s auto-refresh, and AZ distribution. No Apply button.
 */
import React, { useEffect, useState, useCallback, useRef } from 'react';
import {
    FiDownload, FiAlertTriangle, FiRefreshCw, FiServer,
    FiBox, FiClock, FiCpu,
} from 'react-icons/fi';
import { ascpaiAPI } from '../../../../services/api';

const fmtMo = v =>
    v >= 1_000_000 ? `$${(v / 1_000_000).toFixed(2)}M`
    : v >= 1_000   ? `$${(v / 1_000).toFixed(1)}k`
    : `$${v.toFixed(2)}`;

const fmtAgo = secs => {
    if (secs < 5)  return 'just now';
    if (secs < 60) return `${secs}s ago`;
    return `${Math.floor(secs / 60)}m ago`;
};

/* Hover tooltip */
const Tip = ({ text, children }) => (
    <span className="relative group inline-flex items-center">
        {children}
        <span className="pointer-events-none absolute bottom-full left-1/2 -translate-x-1/2 mb-1 z-50
            hidden group-hover:flex bg-gray-800 text-white text-[10px] rounded px-2 py-1 whitespace-nowrap shadow-lg max-w-xs text-center">
            {text}
        </span>
    </span>
);

const Badge = ({ label, count, color, tip }) => (
    <Tip text={tip || label}>
        <div className={`flex-1 rounded-lg px-2.5 py-1.5 text-center border cursor-default ${color}`}>
            <p className="text-base font-bold">{count}</p>
            <p className="text-[10px] font-medium">{label}</p>
        </div>
    </Tip>
);

const lcBadgeCls = lc => {
    if (lc === 'spot')      return 'bg-green-100 text-green-700 border-green-200';
    if (lc === 'on-demand') return 'bg-blue-100 text-blue-700 border-blue-200';
    return 'bg-purple-100 text-purple-700 border-purple-200';
};
const lcLabel = lc =>
    lc === 'on-demand' ? 'OD' : lc === 'spot' ? 'Spot' : 'Buffer';

const ROLE_LABELS = {
    od_stateful:    'OD · Stateful workloads',
    od_anchor:      'OD · Anchor node',
    od_overflow:    'OD · Spot-overflow',
    spot_stateless: 'Spot · Stateless workloads',
    buffer:         'Buffer · Spare capacity',
};
const roleLabel = r => ROLE_LABELS[r] || r;

/* CPU / memory utilisation bar */
const UtilBar = ({ used, capacity, label, baseColor }) => {
    const pct = capacity > 0 ? Math.min(100, Math.round(used / capacity * 100)) : 0;
    return (
        <div className="space-y-0.5">
            <div className="flex justify-between text-[10px] text-gray-400">
                <span>{label}</span><span>{pct}%</span>
            </div>
            <div className="bg-gray-100 rounded-full h-1">
                <div
                    className={`h-1 rounded-full transition-all ${
                        pct > 85 ? 'bg-red-400' : pct > 65 ? 'bg-amber-400' : baseColor
                    }`}
                    style={{ width: `${pct}%` }}
                />
            </div>
        </div>
    );
};

/* Composite score breakdown — removed per user request */

const NodeCard = ({ node }) => {
    const [open, setOpen] = useState(true);
    const podNames = node.pod_names || [];

    return (
        <div className="border border-gray-100 rounded-lg overflow-hidden text-left">
            {/* Node header row */}
            <button
                onClick={() => setOpen(o => !o)}
                className="w-full flex items-center gap-2 px-3 py-2 bg-gray-50 hover:bg-gray-100 transition-colors text-left"
            >
                <FiServer className="w-3.5 h-3.5 text-gray-400 flex-shrink-0" />
                <span className="text-[11px] font-semibold text-gray-700 flex-1 min-w-0 truncate">
                    {node.type}
                    {node.vcpu != null && (
                        <span className="font-normal text-gray-400 ml-1">{node.vcpu}vCPU · {node.memory_gb}GB</span>
                    )}
                </span>
                <span className={`text-[10px] px-1.5 py-0.5 rounded border font-medium flex-shrink-0 ${lcBadgeCls(node.lifecycle)}`}>
                    {lcLabel(node.lifecycle)}
                </span>
                <span className="text-[10px] text-gray-400 flex-shrink-0">{node.az?.split('-').slice(-1)[0]}</span>
                <span className="text-[10px] font-semibold text-gray-600 flex-shrink-0">
                    {node.pods}<span className="font-normal text-gray-400">/{node.max_pods} pods</span>
                </span>
                <span className="text-[10px] text-gray-400 flex-shrink-0">{fmtMo(node.monthly)}/mo</span>
                <span className="text-[10px] text-gray-300 flex-shrink-0">{open ? '▲' : '▼'}</span>
            </button>

            {/* Role + utilisation bars */}
            <div className="px-3 py-1.5 border-t border-gray-50 space-y-1">
                <span className="text-[10px] text-gray-400 block">{roleLabel(node.role)}</span>
                {(node.cpu_capacity_millicores || 0) > 0 && (
                    <div className="grid grid-cols-2 gap-1.5">
                        <UtilBar used={node.cpu_used_millicores} capacity={node.cpu_capacity_millicores}
                            label="CPU" baseColor="bg-blue-400" />
                        <UtilBar used={node.memory_used_mb} capacity={node.memory_capacity_mb}
                            label="Memory" baseColor="bg-indigo-400" />
                    </div>
                )}
            </div>

            {/* Expandable pod list */}
            {open && (
                <div className="px-3 pb-2 border-t border-gray-50">
                    {podNames.length > 0 ? (
                        <>
                            <p className="text-[10px] font-bold text-gray-400 uppercase tracking-wider pt-1.5 mb-1">
                                Assigned pods ({podNames.length})
                            </p>
                            <div className="space-y-0.5 max-h-40 overflow-y-auto pr-1">
                                {podNames.map(pname => (
                                    <div key={pname} className="flex items-center gap-1.5 text-[11px] text-gray-600">
                                        <FiBox className="w-2.5 h-2.5 text-gray-300 flex-shrink-0" />
                                        <span className="truncate font-mono">{pname}</span>
                                    </div>
                                ))}
                            </div>
                        </>
                    ) : (
                        <p className="text-[11px] text-gray-400 pt-1.5">
                            No pods assigned to this node.
                        </p>
                    )}
                </div>
            )}
        </div>
    );
};

const REFRESH_S = 60;

const RebalancedDistribution = ({ clusterId }) => {
    const [data,        setData]        = useState(null);
    const [loading,     setLoading]     = useState(false);
    const [error,       setError]       = useState(null);
    const [lastFetched, setLastFetched] = useState(null);
    const [secsAgo,     setSecsAgo]     = useState(0);
    const [countdown,   setCountdown]   = useState(REFRESH_S);
    const refreshTimer = useRef(null);
    const tickTimer    = useRef(null);

    const fetchConfig = useCallback(() => {
        if (!clusterId) return;
        setLoading(true);
        setError(null);
        ascpaiAPI.getRecommendedConfig(clusterId)
            .then(r => {
                setData(r.data);
                setLastFetched(new Date());
                setSecsAgo(0);
                setCountdown(REFRESH_S);
            })
            .catch(e => setError(e?.response?.data?.detail || 'Failed to load recommended config'))
            .finally(() => setLoading(false));
    }, [clusterId]);

    useEffect(() => { fetchConfig(); }, [fetchConfig]);

    /* Auto-refresh every 60 s */
    useEffect(() => {
        refreshTimer.current = setInterval(fetchConfig, REFRESH_S * 1000);
        return () => clearInterval(refreshTimer.current);
    }, [fetchConfig]);

    /* Per-second ticker for "X s ago" + countdown */
    useEffect(() => {
        tickTimer.current = setInterval(() => {
            setSecsAgo(s => s + 1);
            setCountdown(c => Math.max(0, c - 1));
        }, 1000);
        return () => clearInterval(tickTimer.current);
    }, []);

    const handleDownloadYaml = () => {
        ascpaiAPI.downloadRecommendedConfigYaml(clusterId)
            .then(r => {
                const url = URL.createObjectURL(new Blob([r.data], { type: 'application/x-yaml' }));
                const a = document.createElement('a');
                a.href = url;
                a.download = `recommended-config-${clusterId}.yaml`;
                a.click();
                URL.revokeObjectURL(url);
            })
            .catch(() => alert('Failed to download YAML'));
    };

    if (!clusterId) return null;

    const rec         = data?.recommended_state;
    const nodes       = rec?.node_breakdown?.filter(n => n.role !== 'buffer') || [];
    const odNodes     = nodes.filter(n => n.lifecycle === 'on-demand');
    const spotNodes   = nodes.filter(n => n.lifecycle === 'spot');

    return (
        <div className="bg-white rounded-lg border border-gray-200 card-shadow overflow-hidden">
            {/* Header */}
            <div className="p-4 border-b border-gray-100 bg-gray-50/50 flex items-center justify-between">
                <div>
                    <h3 className="section-title text-[14px]">Optimized Configuration</h3>
                    <p className="text-[11px] text-gray-400 mt-0.5">
                        BFD-TSC · real-time pod-level recommendations · auto-applied when Auto-Rebalancing is on
                    </p>
                </div>
                <div className="flex items-center gap-2">
                    {lastFetched && !loading && (
                        <Tip text={`Next auto-refresh in ${countdown}s`}>
                            <span className="text-[10px] text-gray-400 flex items-center gap-1 cursor-default">
                                <FiClock className="w-3 h-3" />{fmtAgo(secsAgo)}
                            </span>
                        </Tip>
                    )}
                    <button
                        onClick={fetchConfig}
                        disabled={loading}
                        className="p-1.5 rounded text-gray-400 hover:text-blue-500 hover:bg-blue-50 transition-colors"
                        title="Refresh now"
                    >
                        <FiRefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
                    </button>
                </div>
            </div>

            <div className="p-4">
                {loading && !data && (
                    <div className="flex items-center justify-center py-6 text-xs text-gray-400">
                        <FiRefreshCw className="w-4 h-4 animate-spin mr-2" />
                        Computing BFD-TSC optimal placement based on live pod resource requests…
                    </div>
                )}

                {error && !loading && (
                    <div className="flex items-center gap-2 text-xs text-red-500 py-3">
                        <FiAlertTriangle className="w-4 h-4 flex-shrink-0" />
                        <span>{error}</span>
                    </div>
                )}

                {data && (
                    <div className="space-y-4">
                        {/* Current vs Recommended summary */}
                        <div className="grid grid-cols-2 gap-3">
                            <div>
                                <p className="text-[10px] font-bold text-gray-400 uppercase tracking-widest mb-2">Current</p>
                                <div className="flex gap-2">
                                    <Badge label="On-Demand" count={data.current_state.od_nodes}
                                        color="bg-blue-50 border-blue-100 text-blue-700"
                                        tip="Currently running on-demand EC2 nodes" />
                                    <Badge label="Spot" count={data.current_state.spot_nodes}
                                        color="bg-green-50 border-green-100 text-green-700"
                                        tip="Currently running spot EC2 nodes" />
                                </div>
                                <p className="text-[11px] text-gray-500 mt-1.5">
                                    {fmtMo(data.current_state.monthly_cost)}<span className="text-gray-400">/mo</span>
                                </p>
                            </div>

                            <div>
                                <p className="text-[10px] font-bold text-gray-400 uppercase tracking-widest mb-2">Recommended</p>
                                <div className="flex gap-2">
                                    <Badge label="On-Demand" count={rec?.od_nodes ?? 0}
                                        color="bg-blue-50 border-blue-100 text-blue-700"
                                        tip="OD nodes: stateful + overflow pods — never evicted" />
                                    <Badge label="Spot" count={rec?.spot_nodes ?? 0}
                                        color="bg-green-50 border-green-100 text-green-700"
                                        tip="Spot nodes: stateless pods — up to 90% cheaper" />
                                    {(rec?.buffer_nodes ?? 0) > 0 && (
                                        <Badge label="Buffer" count={rec.buffer_nodes}
                                            color="bg-gray-50 border-gray-200 text-gray-500"
                                            tip="Spare capacity nodes" />
                                    )}
                                </div>
                                <p className="text-[11px] text-green-600 font-semibold mt-1.5">
                                    {fmtMo(rec?.monthly_cost ?? 0)}<span className="text-gray-400 font-normal">/mo</span>
                                    {(rec?.savings_monthly ?? 0) > 0 && (
                                        <span className="ml-1.5 text-green-500">
                                            · saves {fmtMo(rec.savings_monthly)}/mo ({rec.savings_pct?.toFixed(1)}%)
                                        </span>
                                    )}
                                </p>
                            </div>
                        </div>

                        {/* Pod distribution stats */}
                        <div className="flex flex-wrap gap-4 pt-2 border-t border-gray-100">
                            <Tip text="Total pods from live cluster data (all namespaces)">
                                <div className="text-center cursor-default">
                                    <p className="text-sm font-bold text-gray-800">{data.pod_distribution.total}</p>
                                    <p className="text-[10px] text-gray-400">total pods</p>
                                </div>
                            </Tip>
                            <Tip text="Safe for spot: stateless, no PVC, no hostPath, no DaemonSet">
                                <div className="text-center cursor-default">
                                    <p className="text-sm font-bold text-green-700">{data.pod_distribution.spot_friendly}</p>
                                    <p className="text-[10px] text-gray-400">spot-eligible</p>
                                </div>
                            </Tip>
                            <Tip text="Must stay on OD: StatefulSets, databases, PVC mounts, critical system pods">
                                <div className="text-center cursor-default">
                                    <p className="text-sm font-bold text-orange-600">{data.pod_distribution.stateful_by_nature}</p>
                                    <p className="text-[10px] text-gray-400">stateful → OD only</p>
                                </div>
                            </Tip>
                            {data.pod_distribution.misplaced > 0 && (
                                <Tip text="Pods on wrong lifecycle node — rebalancer will fix these">
                                    <div className="text-center cursor-default">
                                        <p className="text-sm font-bold text-red-500">{data.pod_distribution.misplaced}</p>
                                        <p className="text-[10px] text-gray-400">misplaced</p>
                                    </div>
                                </Tip>
                            )}
                        </div>

                        {/* Per-node pod placement — pods are real-time from cluster */}
                        {nodes.length > 0 && (
                            <div className="space-y-2 pt-1 border-t border-gray-100">
                                <p className="text-[10px] font-bold text-gray-400 uppercase tracking-widest">
                                    Live pod placement — {nodes.length} node{nodes.length !== 1 ? 's' : ''}
                                </p>

                                {odNodes.length > 0 && (
                                    <div className="space-y-1.5">
                                        <p className="text-[10px] font-semibold text-blue-600 flex items-center gap-1">
                                            <FiCpu className="w-3 h-3" />
                                            On-Demand ({odNodes.length})
                                            <span className="font-normal text-gray-400 ml-1">· stateful &amp; overflow pods</span>
                                        </p>
                                        {odNodes.map((n, i) => <NodeCard key={`od-${i}`} node={n} />)}
                                    </div>
                                )}

                                {spotNodes.length > 0 && (
                                    <div className="space-y-1.5 mt-2">
                                        <p className="text-[10px] font-semibold text-green-600 flex items-center gap-1">
                                            <FiServer className="w-3 h-3" />
                                            Spot ({spotNodes.length})
                                            <span className="font-normal text-gray-400 ml-1">· stateless &amp; spot-eligible pods</span>
                                        </p>
                                        {spotNodes.map((n, i) => <NodeCard key={`sp-${i}`} node={n} />)}
                                    </div>
                                )}
                            </div>
                        )}

                        {/* AZ distribution */}
                        {rec?.az_distribution && Object.keys(rec.az_distribution).length > 0 && (
                            <div className="pt-1 border-t border-gray-100">
                                <p className="text-[10px] font-bold text-gray-400 uppercase tracking-widest mb-1.5">AZ distribution</p>
                                <div className="flex gap-2 flex-wrap">
                                    {Object.entries(rec.az_distribution).map(([az, cnt]) => (
                                        <span key={az} className="text-[10px] px-2 py-0.5 rounded-full bg-gray-100 text-gray-600">
                                            {az.split('-').slice(-1)[0]}: {cnt} node{cnt !== 1 ? 's' : ''}
                                        </span>
                                    ))}
                                </div>
                            </div>
                        )}

                        {/* Warnings */}
                        {data.warnings?.length > 0 && (
                            <div className="space-y-1">
                                {data.warnings.map((w, i) => (
                                    <div key={i} className="flex items-start gap-1.5 text-[11px] text-amber-700 bg-amber-50 border border-amber-100 rounded px-2 py-1">
                                        <FiAlertTriangle className="w-3 h-3 flex-shrink-0 mt-0.5" />
                                        <span>{w}</span>
                                    </div>
                                ))}
                            </div>
                        )}

                        {/* Info banner: how to apply */}
                        <div className="flex items-start gap-2 bg-blue-50 border border-blue-100 rounded-lg px-3 py-2">
                            <span className="text-blue-400 text-sm mt-0.5">ℹ</span>
                            <p className="text-[11px] text-blue-700">
                                Recommendations are based on <strong>live pod resource requests</strong> from the
                                cluster and auto-refresh every {REFRESH_S}s.
                                Configuration is applied automatically when <strong>Auto-Rebalancing</strong> is enabled.
                            </p>
                        </div>

                        {/* Download YAML only */}
                        <div className="flex justify-end pt-1">
                            <button
                                onClick={handleDownloadYaml}
                                className="py-1.5 px-3 rounded text-xs font-semibold border border-gray-200 text-gray-600 hover:bg-gray-50 transition-colors flex items-center gap-1"
                                title="Download Karpenter NodePool YAML"
                            >
                                <FiDownload className="w-3.5 h-3.5" /> Download YAML
                            </button>
                        </div>
                    </div>
                )}
            </div>
        </div>
    );
};

export default RebalancedDistribution;
