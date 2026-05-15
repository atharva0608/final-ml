import React, { useState, useEffect } from 'react';
import useClusters from '../../../hooks/useClusters';
import { optimizeAPI } from '../../../services/api';

const STATUS_MAP = {
  AT_MAX:        { label: 'At Max',        color: 'error' },
  THRASHING:     { label: 'Thrashing',     color: 'error' },
  OVERPROVISIONED:{ label: 'Overprovisioned', color: 'amber' },
  OPTIMAL:       { label: 'Optimal',       color: 'green' },
  SCALING_UP:    { label: 'Scaling Up',    color: 'green' },
  'KEDA-managed':{ label: 'KEDA-managed',  color: 'purple' },
};

const STATUS_BADGE = {
  error:  'bg-red-50 text-red-700 border-red-200',
  green:  'bg-green-50 text-green-700 border-green-200',
  amber:  'bg-amber-50 text-amber-700 border-amber-200',
  purple: 'bg-purple-50 text-purple-700 border-purple-200',
};

function mapWorkload(w) {
  const info = STATUS_MAP[w.status] || { label: w.status || '—', color: 'green' };
  return {
    id: w.workload_id || w.namespace,
    name: w.workload_id ? w.workload_id.split('/').pop() : w.namespace,
    namespace: w.namespace,
    status: info.label,
    statusColor: info.color,
    min: w.min_replicas ?? '—',
    max: w.max_replicas ?? '—',
    current: w.current_replicas ?? '—',
    keda_managed: w.keda_managed || false,
    has_warning: w.has_warning || false,
    scale_events_24h: w.scale_events_24h || 0,
    thrash: w.status === 'THRASHING',
    recommendation_basis_label: w.recommendation_basis_label || null,
  };
}

function assessCooldown(secs) {
  if (secs == null) return { value: '—', assess: '—', color: 'text-gray-400' };
  const label = secs < 60 ? 'Too short' : secs < 120 ? 'Adequate' : 'Optimal';
  const color = secs < 60 ? 'text-red-600' : 'text-green-600';
  return { value: `${secs}s`, assess: label, color };
}

export default function WorkloadScaling() {
  const { clusters, selectedId: clusterId, setSelectedId: setClusterId } = useClusters();
  const [workloads, setWorkloads] = useState([]);
  const [apiSummary, setApiSummary] = useState({});
  const [selected, setSelected] = useState(null);
  const [detail, setDetail] = useState(null);
  const [loading, setLoading] = useState(false);
  const [detailLoading, setDetailLoading] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!clusterId) return;
    setLoading(true);
    setError(null);
    optimizeAPI.getWorkloadsScaling(clusterId)
      .then(res => {
        const data = res.data;
        const mapped = (data.workloads || []).map(mapWorkload);
        setWorkloads(mapped);
        setApiSummary(data.summary || {});
        if (mapped.length > 0) setSelected(mapped[0]);
      })
      .catch(err => setError(err?.response?.data?.detail || err?.message || 'Failed to load scaling data'))
      .finally(() => setLoading(false));
  }, [clusterId]);

  useEffect(() => {
    if (!selected || !clusterId) return;
    setDetailLoading(true);
    setDetail(null);
    optimizeAPI.getWorkloadScalingDetail(selected.id, clusterId)
      .then(res => setDetail(res.data))
      .catch(() => setDetail(null))
      .finally(() => setDetailLoading(false));
  }, [selected?.id, clusterId]);

  const w = selected;
  const hpaCfg = detail?.hpa_config;

  const hpaRows = hpaCfg ? [
    { param: 'Min Replicas', current: String(hpaCfg.min_replicas ?? '—'), warn: w?.has_warning, rec: hpaCfg.recommended_min != null ? String(hpaCfg.recommended_min) : '—' },
    { param: 'Max Replicas', current: String(hpaCfg.max_replicas ?? '—'), warn: w?.has_warning, rec: hpaCfg.recommended_max != null ? String(hpaCfg.recommended_max) : '—' },
    { param: 'Target CPU',   current: hpaCfg.target_cpu_pct != null ? `${hpaCfg.target_cpu_pct}%` : '—', warn: false, rec: '—' },
  ] : [];

  const cooldownRows = hpaCfg ? [
    { policy: 'Scale-Up Stabilization',   ...assessCooldown(hpaCfg.scale_up_stabilization_seconds) },
    { policy: 'Scale-Down Stabilization', ...assessCooldown(hpaCfg.scale_down_stabilization_seconds) },
  ] : [];

  function efficiencyBreakdown() {
    if (!detail) return [];
    const serving  = detail.serving_count  || 0;
    const idle     = detail.idle_count     || 0;
    const evicting = detail.evicting_count || 0;
    const total    = serving + idle + evicting || 1;
    return [
      { label: 'Serving',  pct: Math.round(serving  / total * 100), color: '#005cba' },
      { label: 'Idle',     pct: Math.round(idle     / total * 100), color: '#d3dbe2' },
      { label: 'Draining', pct: Math.round(evicting / total * 100), color: '#757c81' },
    ];
  }

  const summaryItems = [
    { label: 'Tracked Workloads',   value: loading ? '…' : (apiSummary.tracked_workloads ?? '—'),   cls: 'text-gray-900' },
    { label: 'HPA Misconfigured',   value: loading ? '…' : (apiSummary.hpa_misconfigured ?? '—'),   cls: 'text-gray-900' },
    { label: 'Scale Events (24h)',  value: loading ? '…' : (apiSummary.scale_events_24h ?? '—'),    cls: 'text-gray-900' },
    { label: 'Avg Scale Latency',   value: '—', cls: 'text-gray-400' },
    { label: 'Idle Replica Waste',  value: '—', cls: 'text-gray-400' },
    { label: 'VPA Recommendations', value: '—', cls: 'text-gray-400' },
  ];

  return (
    <div className="flex flex-col bg-gray-50 min-h-full">
      {/* Cluster selector + Summary Strip */}
      <div className="px-6 pt-4 pb-3">
        <div className="flex justify-end mb-3">
          <div>
            <label className="block text-xs font-medium text-gray-500 mb-1">Cluster</label>
            <select
              value={clusterId}
              onChange={e => { setSelected(null); setClusterId(e.target.value); }}
              className="text-sm border border-gray-300 rounded-md px-3 py-1.5 focus:outline-none focus:ring-1 focus:ring-indigo-500"
            >
              <option value="" disabled>Select cluster</option>
              {clusters.map(c => <option key={c.id} value={c.id}>{c.name || c.id}</option>)}
            </select>
          </div>
        </div>
        <div className="grid grid-cols-6 gap-3">
          {summaryItems.map(s => (
            <div key={s.label} className="bg-white rounded-xl p-4 border border-gray-200 shadow-sm">
              <div className="text-[10px] font-bold uppercase tracking-wider text-gray-400 mb-1">{s.label}</div>
              <div className={`text-base font-bold ${s.cls}`}>{s.value}</div>
            </div>
          ))}
        </div>
      </div>

      {error && <div className="mx-6 mb-2 bg-red-50 border border-red-200 rounded-lg px-4 py-2 text-xs text-red-700">{error}</div>}

      {/* Split Panel */}
      <div className="flex flex-1 mx-6 mb-6 gap-4 overflow-hidden" style={{ height: 'calc(100vh - 240px)' }}>

        {/* LEFT — Workload List */}
        <div className="w-[52%] flex flex-col bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
          <div className="px-5 py-3 border-b border-gray-100">
            <span className="font-bold text-sm text-gray-900">Workload Scaling Profiles</span>
          </div>
          <div className="flex-1 overflow-y-auto p-3 flex flex-col gap-2">
            {loading ? (
              <div className="text-center py-8 text-xs text-gray-500">Loading workloads...</div>
            ) : !clusterId ? (
              <div className="text-center py-8 text-xs text-gray-400">Select a cluster to view workloads.</div>
            ) : workloads.length === 0 ? (
              <div className="text-center py-8 text-xs text-gray-400">No HPA scaling data available.</div>
            ) : workloads.map(row => {
              const badge = STATUS_BADGE[row.statusColor] || STATUS_BADGE.green;
              const active = selected?.id === row.id;
              const utilPct = (row.max && row.current && row.max !== '—') ? Math.round((row.current / row.max) * 100) : 0;
              return (
                <div key={row.id} onClick={() => setSelected(row)}
                  className={`rounded-xl border p-4 cursor-pointer transition-all relative overflow-hidden ${active ? 'border-indigo-300 bg-indigo-50 ring-1 ring-indigo-200 shadow' : 'border-gray-200 bg-white hover:bg-gray-50'}`}>
                  {active && <div className="absolute left-0 top-0 bottom-0 w-1 bg-indigo-500 rounded-l-xl" />}
                  <div className="pl-2">
                    <div className="flex items-start justify-between mb-1">
                      <div>
                        <div className="flex items-center gap-2 mb-0.5">
                          <span className="font-mono font-bold text-sm text-gray-900">{row.name}</span>
                          <span className={`text-[10px] font-bold px-2 py-0.5 rounded-sm border ${badge}`}>{row.status}</span>
                        </div>
                        <p className="text-xs text-gray-500">ns: {row.namespace} · Min: {row.min} · Max: {row.max} · Current: {row.current}</p>
                      </div>
                      <span className="text-[11px] font-mono text-gray-500">Events 24h: {row.scale_events_24h}</span>
                    </div>
                    <div className="w-full h-2 rounded-full bg-gray-100 overflow-hidden mt-2 mb-1">
                      <div className="h-full bg-indigo-500 rounded-full" style={{ width: `${utilPct}%` }} />
                    </div>
                    <div className="text-[10px] text-gray-400">{row.current} / {row.max} replicas running</div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* RIGHT — Forensics */}
        {w && (
          <div className="flex-1 bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden flex flex-col">
            <div className="px-6 py-4 border-b border-gray-100 bg-gray-50">
              <div className="flex items-center justify-between">
                <h2 className="font-bold text-base text-gray-900">
                  <span className="font-mono">{w.name}</span>
                  <span className="text-gray-400 font-normal text-sm ml-2">Forensics</span>
                </h2>
                {w.keda_managed && (
                  <span className="px-2.5 py-1 text-[10px] font-bold rounded border bg-purple-50 text-purple-700 border-purple-200 uppercase tracking-wider">KEDA-managed</span>
                )}
              </div>
              <p className="text-xs text-gray-500 mt-1">Detailed audit of scaling behavior and efficiency metrics.</p>
            </div>

            <div className="flex-1 overflow-y-auto p-6 space-y-7">

              {/* HPA Config */}
              {!w.keda_managed && (
                <section>
                  <h3 className="font-semibold text-sm text-gray-800 mb-3 flex items-center gap-2">
                    <span className="text-gray-400">⊞</span> HPA Configuration Health
                  </h3>
                  {detailLoading ? (
                    <div className="text-xs text-gray-400 py-2">Loading HPA config...</div>
                  ) : hpaRows.length > 0 ? (
                    <>
                      <div className="rounded-lg overflow-hidden border border-gray-100">
                        <table className="w-full text-xs">
                          <thead className="bg-gray-50 border-b border-gray-100">
                            <tr>
                              {['Parameter', 'Current', 'Recommended'].map(h => (
                                <th key={h} className="px-4 py-2.5 text-left font-semibold uppercase tracking-wider text-gray-400">{h}</th>
                              ))}
                            </tr>
                          </thead>
                          <tbody className="divide-y divide-gray-50 font-mono">
                            {hpaRows.map(r => (
                              <tr key={r.param}>
                                <td className="px-4 py-2.5 text-gray-600 font-sans">{r.param}</td>
                                <td className={`px-4 py-2.5 ${r.warn ? 'text-red-600' : 'text-gray-800'}`}>
                                  {r.current}{r.warn && <span className="text-red-400 ml-1">⚠</span>}
                                </td>
                                <td className="px-4 py-2.5 text-blue-700 font-semibold">{r.rec}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                      {w.recommendation_basis_label && (
                        <p className="text-[10px] text-gray-400 italic mt-2">{w.recommendation_basis_label}</p>
                      )}
                    </>
                  ) : (
                    <div className="text-xs text-gray-400 italic py-2">No HPA config available for this workload.</div>
                  )}
                </section>
              )}

              {/* Scale Event Timeline */}
              <section>
                <div className="flex items-center justify-between mb-3">
                  <h3 className="font-semibold text-sm text-gray-800 flex items-center gap-2">
                    <span className="text-gray-400">⟳</span> Scale Event Timeline (120m)
                  </h3>
                  {w.thrash && <span className="px-2 py-0.5 bg-red-50 text-red-700 text-[10px] font-bold rounded border border-red-200">Thrash Pattern Detected</span>}
                </div>
                <div className="bg-gray-50 rounded-lg p-4 border border-gray-100">
                  {detailLoading ? (
                    <div className="h-16 flex items-center justify-center text-xs text-gray-400">Loading...</div>
                  ) : detail?.hpa_snapshots?.length > 0 ? (
                    <div className="flex items-end gap-0.5 h-16 overflow-x-auto">
                      {detail.hpa_snapshots.slice(-40).map((s, i) => {
                        const maxR = w.max && w.max !== '—' ? w.max : 1;
                        const pct = Math.max(4, Math.round(((s.desired || 0) / maxR) * 100));
                        return (
                          <div key={i} className="flex-shrink-0 w-1.5 bg-indigo-400 rounded-t"
                            style={{ height: `${pct}%` }}
                            title={`${(s.snapshot_at || '').substring(11, 16)} — desired: ${s.desired}`}
                          />
                        );
                      })}
                    </div>
                  ) : (
                    <div className="h-16 flex items-center justify-center text-xs text-gray-400 italic">
                      {detail ? `${detail.scale_events_120m || 0} scale events in last 120m` : 'No snapshot data available'}
                    </div>
                  )}
                </div>
              </section>

              {/* Efficiency */}
              <section>
                <h3 className="font-semibold text-sm text-gray-800 mb-3 flex items-center gap-2">
                  <span className="text-gray-400">◎</span> Replica Efficiency
                </h3>
                <div className="bg-gray-50 rounded-lg p-4 border border-gray-100">
                  {detailLoading ? (
                    <div className="text-xs text-gray-400">Loading...</div>
                  ) : (
                    <>
                      <div className="h-4 w-full rounded-full flex overflow-hidden mb-4">
                        {efficiencyBreakdown().map((e, i) => (
                          <div key={i} className="h-full" style={{ width: `${e.pct}%`, backgroundColor: e.color }} />
                        ))}
                      </div>
                      <div className="space-y-2 text-xs">
                        {efficiencyBreakdown().map((e, i) => (
                          <div key={i} className="flex justify-between items-center">
                            <div className="flex items-center gap-1.5">
                              <div className="w-2 h-2 rounded-full" style={{ backgroundColor: e.color }} />
                              <span className="text-gray-500">{e.label}</span>
                            </div>
                            <span className="font-mono text-gray-800">{e.pct}%</span>
                          </div>
                        ))}
                        {efficiencyBreakdown().length === 0 && (
                          <span className="text-gray-400 italic text-xs">Pod lifecycle data not yet available.</span>
                        )}
                      </div>
                    </>
                  )}
                </div>
              </section>

              {/* Cooldown Audit */}
              <section>
                <h3 className="font-semibold text-sm text-gray-800 mb-3 flex items-center gap-2">
                  <span className="text-gray-400">⊟</span> Cooldown Audit
                </h3>
                {cooldownRows.length > 0 ? (
                  <div className="rounded-lg overflow-hidden border border-gray-100">
                    <table className="w-full text-xs">
                      <thead className="bg-gray-50 border-b border-gray-100">
                        <tr>
                          {['Policy', 'Value', 'Assessment'].map(h => (
                            <th key={h} className="px-4 py-2.5 text-left font-semibold uppercase tracking-wider text-gray-400">{h}</th>
                          ))}
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-gray-50 font-mono">
                        {cooldownRows.map(r => (
                          <tr key={r.policy}>
                            <td className="px-4 py-2.5 text-gray-600 font-sans">{r.policy}</td>
                            <td className="px-4 py-2.5 text-gray-800">{r.value}</td>
                            <td className={`px-4 py-2.5 font-semibold ${r.color}`}>{r.assess}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <div className="text-xs text-gray-400 italic py-2">
                    {detailLoading ? 'Loading...' : 'Stabilization window data not collected by agent yet.'}
                  </div>
                )}
              </section>

            </div>
          </div>
        )}
      </div>
    </div>
  );
}
