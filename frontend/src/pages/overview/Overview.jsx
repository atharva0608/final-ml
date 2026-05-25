import React, { useState, useEffect } from 'react';
import { clusterAPI, workloadClassificationAPI, optimizationAPI } from '../../services/api';

const Y_LABELS = ['$25k', '$20k', '$15k', '$10k', '$5k', '0'];

function fmt$(n) { return n == null ? '—' : `$${Math.round(n).toLocaleString()}`; }
function fmtPct(n) { return n == null ? '—' : `${Math.round(n)}%`; }
function timeAgo(ts) {
  if (!ts) return '';
  const s = Math.floor((Date.now() - new Date(ts)) / 1000);
  if (s < 60) return `${s}s ago`;
  if (s < 3600) return `${Math.floor(s/60)}m ago`;
  if (s < 86400) return `${Math.floor(s/3600)}h ago`;
  return `${Math.floor(s/86400)}d ago`;
}

function useOverviewData() {
  const [clusters, setClusters]     = useState([]);
  const [activity, setActivity]     = useState([]);
  const [wieStats, setWieStats]     = useState({});
  const [proposals, setProposals]   = useState([]);
  const [loading, setLoading]       = useState(true);

  useEffect(() => {
    Promise.allSettled([
      clusterAPI.list(),
      clusterAPI.getAgentActions('', 20),
    ]).then(([clsRes, actRes]) => {
      const clsList = clsRes.value?.data?.clusters || clsRes.value?.data || [];
      setClusters(Array.isArray(clsList) ? clsList : []);

      const actions = actRes.value?.data?.actions || actRes.value?.data || [];
      setActivity(Array.isArray(actions) ? actions.slice(0, 8) : []);

      // Per-cluster: fetch WIE summary + rightsizing proposals
      const validClusters = Array.isArray(clsList) ? clsList.filter(c => c.id) : [];
      if (validClusters.length === 0) { setLoading(false); return; }
      const firstId = validClusters[0].id;
      Promise.allSettled([
        workloadClassificationAPI.getSummary(firstId),
        optimizationAPI.getRightsizing(firstId, { analysis_window_hours: 168, min_data_points: 50 }),
      ]).then(([wieRes, propRes]) => {
        setWieStats(wieRes.value?.data || {});
        const recs = propRes.value?.data || [];
        setProposals(Array.isArray(recs) ? recs : []);
      }).finally(() => setLoading(false));
    }).catch(() => setLoading(false));
  }, []);

  return { clusters, activity, wieStats, proposals, loading };
}

export default function Overview() {
  const [costView, setCostView] = useState('Namespace');
  const { clusters, activity, wieStats, proposals, loading } = useOverviewData();

  // ── Derived stats from real data ──────────────────────────────────────
  const totalNodes   = clusters.reduce((s, c) => s + (c.node_count ?? c.nodes ?? 0), 0);
  const totalWl      = wieStats.total_workloads ?? wieStats.total ?? '—';
  const confirmedWl  = wieStats.confirmed_count ?? wieStats.confidence_distribution?.CONFIRMED ?? '—';
  const reduceCandidates = proposals.filter(p => p.recommendation_action === 'REDUCE').length;
  const totalSavings = proposals.reduce((s, p) => s + (p.savings_monthly || 0), 0);
  const pendingActs  = activity.filter(a => a.status === 'PENDING' || a.status === 'QUEUED').length;

  const STATS = [
    { label: 'Rightsizing Savings',  value: loading ? '…' : fmt$(totalSavings),     sub: `${proposals.length} workload${proposals.length !== 1 ? 's' : ''} analyzed`, subColor: 'text-green-600' },
    { label: 'REDUCE Candidates',    value: loading ? '…' : String(reduceCandidates), sub: 'oversized workloads',  subColor: 'text-amber-600' },
    { label: 'Active Clusters',      value: loading ? '…' : String(clusters.length), sub: `${totalNodes} total nodes`, subColor: 'text-gray-500' },
    { label: 'Active Workloads',     value: loading ? '…' : String(totalWl),         sub: `${confirmedWl} CONFIRMED`, subColor: 'text-gray-500' },
    { label: 'Pending Actions',      value: loading ? '…' : String(pendingActs),     sub: pendingActs > 0 ? 'AMBER' : 'CLEAR', subColor: pendingActs > 0 ? 'text-amber-600' : 'text-green-600', badge: pendingActs > 0 },
    { label: 'Data Points',          value: loading ? '…' : String(proposals.reduce((s,p)=>s+(p.data_points||0),0).toLocaleString()), sub: 'pod metrics analyzed', subColor: 'text-gray-400' },
  ];

  // Cost drivers from proposals (by namespace)
  const nsBySpend = {};
  proposals.forEach(p => {
    const ns = p.namespace || 'unknown';
    nsBySpend[ns] = (nsBySpend[ns] || 0) + (p.current_cost_monthly || 0);
  });
  const totalSpend = Object.values(nsBySpend).reduce((s, v) => s + v, 0) || 1;
  const COST_DRIVERS = Object.entries(nsBySpend)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 5)
    .map(([name, spend]) => ({
      name,
      pct: Math.round((spend / totalSpend) * 100),
      spend: fmt$(spend),
    }));

  // Workload-level cost drivers
  const wlBySpend = proposals
    .sort((a, b) => (b.current_cost_monthly || 0) - (a.current_cost_monthly || 0))
    .slice(0, 5)
    .map(p => ({
      name: p.controller_name,
      pct: Math.round(((p.current_cost_monthly || 0) / totalSpend) * 100),
      spend: fmt$(p.current_cost_monthly),
    }));

  const costDrivers = costView === 'Namespace' ? COST_DRIVERS : wlBySpend;

  // Activity dot colours by action_type / status
  function actDot(a) {
    if (a.status === 'COMPLETED' || a.status === 'DONE') return 'bg-green-500';
    if (a.status === 'FAILED')  return 'bg-red-400';
    if (a.status === 'PENDING' || a.status === 'QUEUED') return 'bg-amber-400';
    return 'bg-blue-600';
  }

  return (
    <div className="flex flex-col bg-gray-50 min-h-full w-full">
      <div className="p-6 flex flex-col gap-6 max-w-[1600px] mx-auto w-full">

        {/* ── Row 1: Stat Strip ── */}
        <section className="w-full bg-white border border-gray-200 rounded-xl overflow-hidden grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 divide-y md:divide-y-0 md:divide-x divide-gray-100 shadow-sm">
          {STATS.map(s => (
            <div key={s.label} className="p-4 flex flex-col gap-1">
              <span className="text-[11px] uppercase tracking-widest text-gray-400 font-semibold">{s.label}</span>
              <span className="text-2xl font-bold text-gray-900 font-mono tracking-tight">{s.value}</span>
              <div className={`flex items-center text-[12px] font-medium ${s.subColor}`}>
                {s.badge
                  ? <span className="px-2 py-0.5 bg-amber-100 text-amber-700 text-[11px] font-semibold rounded-full uppercase tracking-wider">{s.sub}</span>
                  : <span>{s.sub}</span>
                }
              </div>
            </div>
          ))}
        </section>

        {/* ── Row 2: Cluster Health Table ── */}
        <section className="w-full bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
          <div className="px-5 py-4 border-b border-gray-100 bg-white flex justify-between items-center">
            <h2 className="text-sm font-semibold text-gray-900">Cluster Health</h2>
            {loading && <span className="text-[11px] text-gray-400 italic">Loading…</span>}
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead>
                <tr className="border-b border-gray-100 text-[10px] uppercase tracking-widest text-gray-400 bg-gray-50">
                  {['Cluster', 'Region', 'Nodes', 'Provider', 'Status'].map(h => (
                    <th key={h} className="px-5 py-3 font-semibold">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-50 font-mono">
                {clusters.length === 0 && !loading && (
                  <tr><td colSpan={5} className="px-5 py-4 text-gray-400 text-center italic text-xs">No clusters found</td></tr>
                )}
                {clusters.map(c => {
                  const st = c.status || 'UNKNOWN';
                  const stColor = st === 'ACTIVE' || st === 'HEALTHY' ? 'bg-green-500' : st === 'DEGRADED' ? 'bg-amber-500' : 'bg-gray-400';
                  return (
                    <tr key={c.id} className="hover:bg-gray-50 transition-colors">
                      <td className="px-5 py-3.5 font-semibold text-gray-900">{c.name || c.id}</td>
                      <td className="px-5 py-3.5 text-gray-500">{c.region || '—'}</td>
                      <td className="px-5 py-3.5 text-gray-700">{c.node_count ?? c.nodes ?? '—'}</td>
                      <td className="px-5 py-3.5 text-gray-500 uppercase text-[10px]">{c.cloud_provider || c.provider || 'aws'}</td>
                      <td className="px-5 py-3.5">
                        <div className="flex items-center gap-2 text-[12px] font-sans">
                          <span className={`w-2 h-2 rounded-full ${stColor}`} />
                          <span className="text-gray-700">{st}</span>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </section>

        {/* ── Row 3: Activity + Cost Drivers ── */}
        <section className="flex flex-col lg:flex-row gap-5">

          {/* Optimization Activity Feed */}
          <div className="flex-1 bg-white rounded-xl border border-gray-200 p-5 shadow-sm flex flex-col">
            <h2 className="text-sm font-semibold text-gray-900 mb-5">Optimization Activity</h2>
            {activity.length === 0 && !loading && (
              <p className="text-xs text-gray-400 italic">No recent agent actions.</p>
            )}
            <div className="flex flex-col relative pl-4 border-l border-gray-100 ml-2 gap-5">
              {activity.map((a, i) => (
                <div key={a.id || i} className="relative">
                  <div className={`absolute -left-[21px] top-1 w-2.5 h-2.5 rounded-full ${actDot(a)} ring-4 ring-white`} />
                  <div className="flex flex-col">
                    <span className="text-xs text-gray-800 font-medium">{a.action_type || a.type || 'Action'}</span>
                    <span className="text-[11px] text-gray-400 mt-0.5">
                      {a.status} {a.cluster_name ? `• ${a.cluster_name}` : ''} {a.created_at ? `• ${timeAgo(a.created_at)}` : ''}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Top Cost Drivers */}
          <div className="flex-1 bg-white rounded-xl border border-gray-200 p-5 shadow-sm flex flex-col">
            <div className="flex justify-between items-center mb-5">
              <h2 className="text-sm font-semibold text-gray-900">Top Cost Drivers</h2>
              <div className="flex bg-gray-100 rounded p-0.5 border border-gray-200">
                {['Namespace', 'Workload'].map(v => (
                  <button key={v} onClick={() => setCostView(v)}
                    className={`px-3 py-1 text-[11px] font-medium rounded transition-colors ${costView === v ? 'bg-white shadow-sm text-gray-800' : 'text-gray-500 hover:text-gray-700'}`}>
                    {v}
                  </button>
                ))}
              </div>
            </div>
            {costDrivers.length === 0 && !loading && (
              <p className="text-xs text-gray-400 italic">No cost data available — run rightsizing analysis.</p>
            )}
            <div className="flex flex-col gap-4">
              {costDrivers.map((d, i) => (
                <div key={d.name} className="flex flex-col gap-1">
                  <div className="flex justify-between text-xs font-mono">
                    <span className="text-gray-800 font-semibold truncate max-w-[140px]">{d.name}</span>
                    <div className="flex items-center gap-2">
                      <span className="text-gray-400">{d.pct}%</span>
                      <span className="text-gray-800">{d.spend}</span>
                    </div>
                  </div>
                  <div className="w-full bg-gray-100 h-2 rounded-full overflow-hidden">
                    <div className="bg-blue-600 h-full rounded-full" style={{ width: `${d.pct}%`, opacity: 1 - i * 0.15 }} />
                  </div>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* ── Row 4: Rightsizing Summary Strip ── */}
        {proposals.length > 0 && (
          <section className="w-full bg-green-50 border-l-4 border-green-600 rounded-xl p-4 flex flex-col md:flex-row items-start md:items-center justify-between gap-4 border border-green-100">
            <div className="flex items-center gap-3">
              <span className="text-green-700 text-lg">📊</span>
              <span className="text-xs font-semibold text-green-800 tracking-tight">Rightsizing analysis complete — real data from pod metrics</span>
            </div>
            <div className="flex flex-wrap items-center gap-5 font-mono text-xs">
              {[
                { label: 'REDUCE', value: proposals.filter(p=>p.recommendation_action==='REDUCE').length, color: 'text-amber-700' },
                { label: 'INCREASE', value: proposals.filter(p=>p.recommendation_action==='INCREASE').length, color: 'text-red-600' },
                { label: 'OBSERVE', value: proposals.filter(p=>p.recommendation_action==='OBSERVE').length, color: 'text-blue-600' },
                { label: 'Throttle Risk', value: proposals.filter(p=>p.throttle_risk).length, color: 'text-orange-600' },
              ].map((item, i) => (
                <React.Fragment key={item.label}>
                  {i > 0 && <div className="w-px h-4 bg-green-300 hidden md:block" />}
                  <div className="flex items-center gap-1.5">
                    <span className="text-gray-500">{item.label}</span>
                    <span className={`font-bold ${item.color}`}>{item.value}</span>
                  </div>
                </React.Fragment>
              ))}
              <div className="w-px h-4 bg-green-300 hidden md:block" />
              <div className="flex items-center gap-1.5 font-semibold text-green-700">
                Total Savings: <span className="font-bold">{fmt$(totalSavings)}/mo</span>
              </div>
            </div>
          </section>
        )}

      </div>
    </div>
  );
}