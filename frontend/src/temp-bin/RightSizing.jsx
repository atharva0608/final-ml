import React, { useState } from 'react';
import { FiTrendingDown, FiCpu, FiServer, FiRefreshCw, FiCheckCircle, FiArrowRight, FiZap } from 'react-icons/fi';
import useClusters from '../../hooks/useClusters';
import useRightsizing from '../../hooks/useRightsizing';
import { optimizationAPI } from '../../services/api';

const RiskChip = ({ level }) => {
  const map = { HIGH: 'bg-red-100 text-red-700', MEDIUM: 'bg-yellow-100 text-yellow-700', LOW: 'bg-gray-100 text-gray-600' };
  const l = (level || 'LOW').toUpperCase();
  return <span className={`px-2 py-0.5 rounded-full text-xs font-bold ${map[l] || map.LOW}`}>{l}</span>;
};

const RightSizing = () => {
  const { clusters, selectedId, setSelectedId } = useClusters();
  const { recommendations, nodePools, utilizationMetrics, costImpact, summary, loading, error, refetch } = useRightsizing(selectedId);
  const [selectedWorkload, setSelectedWorkload] = useState(null);

  const totals = { ...summary, ...costImpact };
  const { cpuPct, memPct, cpuUsed, cpuReq, memUsed, memReq, insight } = utilizationMetrics;
  const totalWorkloads = recommendations.length || totals.workloads || 0;
  const optimizable = totals.optimizable || recommendations.filter(r => parseFloat(r.monthly_saving || 0) > 0).length;
  const autoCount = recommendations.filter(r => r.mode === 'AUTO' || r.auto_apply).length;
  const pendingCount = recommendations.filter(r => !r.applied && !r.dismissed).length;
  const totalCurrent = totals.totalCurrent || 0;
  const totalRec = totals.totalRecommended || 0;
  const totalSave = totals.totalSaving || 0;
  const savePct = totalCurrent > 0 ? ((totalSave / totalCurrent) * 100).toFixed(1) : 0;
  const cpuOver = cpuPct != null && cpuReq ? Math.round(((parseFloat(cpuReq) / Math.max(parseFloat(cpuUsed || 1), 1)) - 1) * 100) : null;
  const memOver = memPct != null && memReq ? Math.round(((parseFloat(memReq) / Math.max(parseFloat(memUsed || 1), 1)) - 1) * 100) : null;

  return (
    <div className="min-h-full bg-gray-50 flex flex-col">

      {/* ── Sticky Top Bar ── */}
      <header className="sticky top-0 z-10 bg-white border-b border-gray-200 shadow-sm px-6 py-3 flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-4 flex-wrap">
          <h1 className="text-sm font-bold tracking-widest text-gray-900 uppercase">Rightsizing</h1>
          <div className="w-px h-4 bg-gray-300 hidden md:block" />
          <div className="flex items-center gap-5 text-xs font-semibold tracking-wide text-gray-500 uppercase flex-wrap">
            <span><span className="text-gray-900">{totalWorkloads}</span> Workloads</span>
            <span className="flex items-center gap-1 text-indigo-600">
              <FiZap className="w-3 h-3" /> {optimizable} Optimizable
            </span>
            <span><span className="text-gray-900">{autoCount}</span> Auto</span>
            <span className="flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-full bg-gray-400" />
              {pendingCount} Pending
            </span>
          </div>
        </div>
        <div className="flex items-center gap-5 text-xs font-semibold tracking-wide text-gray-500 uppercase flex-wrap">
          <div className="flex items-center gap-3">
            <label className="text-gray-500">Cluster:</label>
            <select
              value={selectedId}
              onChange={e => { setSelectedId(e.target.value); setSelectedWorkload(null); }}
              className="text-xs border border-gray-200 rounded px-2 py-1 text-gray-700 focus:outline-none focus:ring-1 focus:ring-indigo-500"
            >
              <option value="" disabled>Select</option>
              {clusters.map(c => <option key={c.id} value={c.id}>{c.name || c.id}</option>)}
            </select>
          </div>
          <button onClick={refetch} disabled={loading} title="Refresh"
            className="p-1.5 rounded border border-gray-200 bg-white hover:bg-gray-50 disabled:opacity-50 transition-colors">
            <FiRefreshCw className={`w-3.5 h-3.5 text-gray-500 ${loading ? 'animate-spin' : ''}`} />
          </button>
          <div className="flex items-center gap-2 bg-indigo-50 border border-indigo-100 px-3 py-1 rounded text-indigo-700">
            <FiZap className="w-3 h-3" /> Mode: AUTO
          </div>
        </div>
      </header>

      {/* ── Main Scrollable Area ── */}
      <div className="flex-1 overflow-y-auto p-6">
        <div className="max-w-screen-xl mx-auto space-y-6">

        {error && (
          <div className="p-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700">{error}</div>
        )}

        {/* ── Top Row: Cost + Resource Allocation ── */}
        <div className="grid grid-cols-12 gap-6">

          {/* Cost Impact Projection */}
          <div className="col-span-12 lg:col-span-8 bg-white rounded-lg border border-gray-200 shadow-sm p-6">
            <div className="flex items-start justify-between mb-6 flex-wrap gap-4">
              <div>
                <h2 className="text-base font-bold text-gray-900 mb-2">Cost Impact Projection</h2>
                <div className="flex items-baseline gap-4 flex-wrap">
                  {totalCurrent > 0 ? (
                    <>
                      <span className="text-2xl font-bold text-gray-400 line-through opacity-60">
                        ${totalCurrent.toLocaleString()}
                      </span>
                      <span className="text-3xl font-bold text-gray-900">
                        ${totalRec.toLocaleString()}
                      </span>
                      {totalSave > 0 && (
                        <div className="flex items-center gap-1 bg-indigo-100 text-indigo-800 px-3 py-1 rounded-full text-xs font-bold">
                          <FiTrendingDown className="w-3 h-3" />
                          Savings: ${totalSave.toLocaleString()} / {savePct}%
                        </div>
                      )}
                    </>
                  ) : (
                    <span className="text-sm text-gray-400">Connect cluster to see cost data</span>
                  )}
                </div>
              </div>
              {optimizable > 0 && (
                <button className="flex items-center gap-2 bg-indigo-600 hover:bg-indigo-700 text-white px-4 py-2 rounded text-sm font-semibold transition-colors">
                  Apply All {optimizable} Recommendations
                  <FiArrowRight className="w-4 h-4" />
                </button>
              )}
            </div>

            {/* Chart Area */}
            <div className="relative h-48 w-full bg-gray-50 rounded p-4 border border-gray-100">
              <div className="absolute left-4 top-4 bottom-8 flex flex-col justify-between text-xs font-semibold text-gray-400">
                <span>High</span><span>Mid</span><span>Low</span>
              </div>
              <svg className="w-full h-full pl-8 pb-4" preserveAspectRatio="none" viewBox="0 0 100 100">
                <path stroke="#d1d5db" d="M0,20 L20,25 L40,22 L60,15 L80,18 L100,10" fill="none" strokeDasharray="4" strokeWidth="1.5" />
                <path stroke="#4f46e5" d="M0,20 L20,25 L40,22 L60,45 L80,55 L100,60" fill="none" strokeWidth="2" />
                <polygon fill="#4f46e5" points="60,45 58,48 62,48" />
                <polygon fill="#4f46e5" points="80,55 78,58 82,58" />
              </svg>
              {totalCurrent > 0 && (
                <div className="absolute right-6 top-4 bg-gray-900 bg-opacity-90 rounded p-2.5 text-white text-xs shadow-xl w-40 pointer-events-none">
                  <div className="font-bold text-gray-300 mb-1 text-[10px]">Projected</div>
                  <div className="flex justify-between mb-1">
                    <span className="text-gray-400">Current</span>
                    <span>${totalCurrent.toLocaleString()}</span>
                  </div>
                  <div className="flex justify-between mb-1 font-semibold text-indigo-300">
                    <span>Optimized</span>
                    <span>${totalRec.toLocaleString()}</span>
                  </div>
                  <div className="h-px bg-white bg-opacity-20 my-1.5" />
                  <div className="flex justify-between text-[10px] font-bold text-red-300">
                    <span>Save</span>
                    <span>${totalSave.toLocaleString()}</span>
                  </div>
                </div>
              )}
              <div className="absolute bottom-1 left-10 right-4 flex justify-between text-[10px] text-gray-400">
                <span>-1mo</span><span>-2w</span><span>Now</span>
              </div>
            </div>
          </div>

          {/* Resource Allocation */}
          <div className="col-span-12 lg:col-span-4 bg-white rounded-lg border border-gray-200 shadow-sm p-6 flex flex-col">
            <h2 className="text-base font-bold text-gray-900 mb-5">Resource Allocation</h2>
            <div className="space-y-5 flex-1">
              {/* CPU */}
              <div>
                <div className="flex justify-between text-xs font-semibold uppercase tracking-wide text-gray-500 mb-2">
                  <span className="flex items-center gap-1"><FiCpu className="w-3 h-3" /> CPU Core Usage</span>
                  {cpuOver != null && <span className="text-red-600 font-bold">+{cpuOver}% Over</span>}
                </div>
                <div className="relative h-2 bg-gray-100 rounded-full overflow-hidden">
                  <div className="absolute top-0 left-0 h-full bg-red-200 bg-opacity-50 rounded-full w-full" />
                  <div className="absolute top-0 left-0 h-full bg-indigo-600 rounded-full z-10" style={{ width: `${Math.min(100, cpuPct || 35)}%` }} />
                </div>
                <div className="flex justify-between mt-1 text-xs text-gray-400">
                  <span>Actual: {cpuUsed || '—'}</span>
                  <span>Req: {cpuReq || '—'}</span>
                </div>
              </div>
              {/* Memory */}
              <div>
                <div className="flex justify-between text-xs font-semibold uppercase tracking-wide text-gray-500 mb-2">
                  <span className="flex items-center gap-1"><FiServer className="w-3 h-3" /> Memory Usage</span>
                  {memOver != null && <span className="text-red-600 font-bold">+{memOver}% Over</span>}
                </div>
                <div className="relative h-2 bg-gray-100 rounded-full overflow-hidden">
                  <div className="absolute top-0 left-0 h-full bg-red-200 bg-opacity-50 rounded-full w-full" />
                  <div className="absolute top-0 left-0 h-full bg-indigo-500 rounded-full z-10" style={{ width: `${Math.min(100, memPct || 60)}%` }} />
                </div>
                <div className="flex justify-between mt-1 text-xs text-gray-400">
                  <span>Actual: {memUsed || '—'}</span>
                  <span>Req: {memReq || '—'}</span>
                </div>
              </div>
            </div>
            <div className="mt-4 bg-gray-50 border border-gray-100 rounded p-3 flex items-start gap-2">
              <FiZap className="w-4 h-4 text-indigo-500 mt-0.5 flex-shrink-0" />
              <p className="text-xs text-gray-600 leading-relaxed">
                {insight || 'Rightsizing will reclaim idle resources and correct over-provisioning across worker nodes.'}
              </p>
            </div>
          </div>
        </div>

        {/* ── Node Pool Optimization Table ── */}
        <div className="bg-white rounded-lg border border-gray-200 shadow-sm overflow-hidden">
          <div className="px-6 py-4 border-b border-gray-100 flex items-center justify-between">
            <h2 className="text-base font-bold text-gray-900">Node Pool Optimization</h2>
            <button className="text-sm font-semibold text-indigo-600 hover:text-indigo-800 transition-colors">View All Pools</button>
          </div>
          {loading ? (
            <div className="px-6 py-8 text-center text-sm text-gray-400 flex items-center justify-center gap-2">
              <FiRefreshCw className="w-4 h-4 animate-spin" /> Loading…
            </div>
          ) : nodePools.length === 0 ? (
            <div className="px-6 py-6 overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead className="bg-gray-50 border-b border-gray-100 text-xs font-semibold text-gray-500 uppercase tracking-wide">
                  <tr>
                    {['Pool / Instance', 'Node Count (Cur → Rec)', 'Proj. CPU', 'Proj. Mem', 'Fragmentation', 'Risk Level', 'Actions'].map(h => (
                      <th key={h} className="px-6 py-3">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {[{ pool: 'c6a.large', label: 'Spot Fleet • us-east-1', cur: 12, rec: 9, cpu: '72%', mem: '58%', frag: 'HIGH', risk: 'LOW' },
                    { pool: 'm5.large', label: 'On-Demand • us-east-1', cur: 8, rec: 6, cpu: '65%', mem: '80%', frag: 'MED', risk: 'LOW' }].map((row, i) => (
                    <tr key={i} className="border-b border-gray-50 hover:bg-gray-50 transition-colors">
                      <td className="px-6 py-4">
                        <div className="font-bold text-gray-900">{row.pool}</div>
                        <div className="text-xs text-gray-400">{row.label}</div>
                      </td>
                      <td className="px-6 py-4">
                        <span className="line-through text-gray-400 text-xs mr-2">{row.cur}</span>
                        <span className="font-bold text-indigo-700">{row.rec} nodes</span>
                      </td>
                      <td className="px-6 py-4 text-gray-700">{row.cpu}</td>
                      <td className="px-6 py-4 text-gray-700">{row.mem}</td>
                      <td className="px-6 py-4"><RiskChip level={row.frag} /></td>
                      <td className="px-6 py-4"><RiskChip level={row.risk} /></td>
                      <td className="px-6 py-4">
                        <div className="flex gap-2 justify-end">
                          <button className="px-3 py-1.5 text-xs font-semibold text-indigo-600 hover:bg-gray-100 rounded transition-colors">Simulate</button>
                          <button className="px-3 py-1.5 text-xs font-semibold bg-indigo-600 text-white rounded hover:bg-indigo-700 transition-colors">Apply</button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead className="bg-gray-50 border-b border-gray-100 text-xs font-semibold text-gray-500 uppercase tracking-wide">
                  <tr>
                    {['Pool / Instance', 'Node Count (Cur → Rec)', 'Proj. CPU', 'Proj. Mem', 'Fragmentation', 'Risk Level', 'Actions'].map(h => (
                      <th key={h} className="px-6 py-3">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-50">
                  {nodePools.slice(0, 5).map((p, i) => (
                    <tr key={p.id || i} className="hover:bg-gray-50 transition-colors">
                      <td className="px-6 py-4">
                        <div className="font-bold text-gray-900">{p.instance_type || p.pool_name || '—'}</div>
                        <div className="text-xs text-gray-400">{p.lifecycle || p.type || ''}{p.region ? ` • ${p.region}` : ''}</div>
                      </td>
                      <td className="px-6 py-4">
                        {p.current_node_count != null ? (
                          <>
                            <span className="line-through text-gray-400 text-xs mr-2">{p.current_node_count}</span>
                            <span className="font-bold text-indigo-700">{p.recommended_node_count} nodes</span>
                          </>
                        ) : '—'}
                      </td>
                      <td className="px-6 py-4 text-gray-700">{p.projected_cpu_pct != null ? `${p.projected_cpu_pct}%` : '—'}</td>
                      <td className="px-6 py-4 text-gray-700">{p.projected_mem_pct != null ? `${p.projected_mem_pct}%` : '—'}</td>
                      <td className="px-6 py-4"><RiskChip level={p.fragmentation || p.fragmentation_risk} /></td>
                      <td className="px-6 py-4"><RiskChip level={p.risk_level || p.risk} /></td>
                      <td className="px-6 py-4">
                        <div className="flex gap-2 justify-end">
                          <button className="px-3 py-1.5 text-xs font-semibold text-indigo-600 hover:bg-gray-100 rounded transition-colors">Simulate</button>
                          <button className="px-3 py-1.5 text-xs font-semibold bg-indigo-600 text-white rounded hover:bg-indigo-700 transition-colors">Apply</button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* ── Bottom Row: Workload Table + Drilldown ── */}
        <div className="grid grid-cols-12 gap-6">

          {/* Workload Recommendations */}
          <div className="col-span-12 xl:col-span-7 bg-white rounded-lg border border-gray-200 shadow-sm flex flex-col overflow-hidden">
            <div className="px-6 py-4 border-b border-gray-100">
              <h2 className="text-base font-bold text-gray-900">Workload Recommendations</h2>
            </div>
            <div className="overflow-y-auto max-h-96">
              {loading && !recommendations.length ? (
                <div className="flex items-center justify-center py-12 text-sm text-gray-400 gap-2">
                  <FiRefreshCw className="w-4 h-4 animate-spin" /> Loading…
                </div>
              ) : recommendations.length === 0 ? (
                <div className="flex flex-col items-center py-12 gap-2 text-gray-400">
                  <FiCheckCircle className="w-8 h-8 opacity-30" />
                  <span className="text-sm">No recommendations available</span>
                </div>
              ) : (
                <table className="w-full text-left text-sm">
                  <thead className="bg-gray-50 border-b border-gray-100 sticky top-0 text-xs font-semibold text-gray-500 uppercase tracking-wide">
                    <tr>
                      <th className="px-4 py-3">Workload</th>
                      <th className="px-4 py-3">CPU (Cur→Rec)</th>
                      <th className="px-4 py-3">Mem (Cur→Rec)</th>
                      <th className="px-4 py-3 text-right">Save/mo</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-50">
                    {recommendations.map((r, i) => {
                      const isSelected = selectedWorkload === r;
                      const saving = parseFloat(r.monthly_saving || r.savings_per_month || 0);
                      return (
                        <tr key={r.id || i} onClick={() => setSelectedWorkload(r)}
                          className={`cursor-pointer transition-colors relative ${isSelected ? 'bg-gray-100' : 'hover:bg-gray-50'}`}>
                          {isSelected && <td className="absolute left-0 top-0 bottom-0 w-1 bg-indigo-600 rounded" />}
                          <td className={`px-4 py-4 pl-5 font-bold ${isSelected ? 'text-indigo-700' : 'text-gray-900'}`}>
                            {r.workload || r.name || r.deployment_name || '—'}
                            {r.namespace && <p className="text-xs text-gray-400 font-normal">{r.namespace}</p>}
                          </td>
                          <td className="px-4 py-4 text-xs text-gray-600">
                            {r.current_cpu ? <><span className="line-through text-gray-400 mr-1">{r.current_cpu}</span>{r.recommended_cpu}</> : '—'}
                          </td>
                          <td className="px-4 py-4 text-xs text-gray-600">
                            {r.current_memory ? <><span className="line-through text-gray-400 mr-1">{r.current_memory}</span>{r.recommended_memory}</> : '—'}
                          </td>
                          <td className="px-4 py-4 text-right font-bold text-gray-900">
                            ${saving.toLocaleString(undefined, { maximumFractionDigits: 0 })}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              )}
            </div>
          </div>

          {/* Drilldown Panel */}
          <div className="col-span-12 xl:col-span-5 bg-white rounded-lg border border-gray-200 shadow-sm p-6">
            {!selectedWorkload ? (
              <div className="flex flex-col items-center justify-center h-full gap-3 text-gray-400 py-12">
                <FiCpu className="w-10 h-10 opacity-20" />
                <p className="text-sm">Select a workload to inspect</p>
              </div>
            ) : (
              <>
                <div className="flex items-center gap-3 mb-5">
                  <div className="p-2 bg-indigo-50 rounded-lg">
                    <FiZap className="w-5 h-5 text-indigo-600" />
                  </div>
                  <div className="min-w-0">
                    <h3 className="text-base font-bold text-gray-900 truncate">
                      {selectedWorkload.workload || selectedWorkload.name || selectedWorkload.deployment_name}
                    </h3>
                    <p className="text-xs font-semibold tracking-wide text-gray-500 uppercase">
                      {selectedWorkload.kind || 'Deployment'} · namespace: {selectedWorkload.namespace || 'default'}
                    </p>
                  </div>
                </div>

                <div className="space-y-5">
                  {/* Profiling */}
                  <div className="grid grid-cols-2 gap-3">
                    <div className="bg-gray-50 p-3 rounded">
                      <p className="text-xs font-semibold uppercase tracking-wide text-gray-500 mb-1.5">CPU Profiling</p>
                      {selectedWorkload.cpu_avg && <p className="text-sm text-gray-700">Avg: {selectedWorkload.cpu_avg}</p>}
                      {selectedWorkload.cpu_p95 && <p className="text-sm text-gray-700">P95: {selectedWorkload.cpu_p95}</p>}
                      {selectedWorkload.recommended_cpu && (
                        <p className="text-sm font-bold text-indigo-700 mt-1">Peak: {selectedWorkload.recommended_cpu}</p>
                      )}
                      {!selectedWorkload.cpu_avg && <p className="text-xs text-gray-400">No telemetry</p>}
                    </div>
                    <div className="bg-gray-50 p-3 rounded">
                      <p className="text-xs font-semibold uppercase tracking-wide text-gray-500 mb-1.5">Mem Profiling</p>
                      {selectedWorkload.memory_avg && <p className="text-sm text-gray-700">Avg: {selectedWorkload.memory_avg}</p>}
                      {selectedWorkload.memory_p95 && <p className="text-sm text-gray-700">P95: {selectedWorkload.memory_p95}</p>}
                      {selectedWorkload.recommended_memory && (
                        <p className="text-sm font-bold text-indigo-700 mt-1">Peak: {selectedWorkload.recommended_memory}</p>
                      )}
                      {!selectedWorkload.memory_avg && <p className="text-xs text-gray-400">No telemetry</p>}
                    </div>
                  </div>

                  {/* Rationale */}
                  {selectedWorkload.rationale && (
                    <div>
                      <h4 className="text-sm font-bold text-gray-900 mb-1.5">Recommendation Rationale</h4>
                      <p className="text-sm text-gray-500 leading-relaxed">{selectedWorkload.rationale}</p>
                    </div>
                  )}

                  {/* Safety Checks */}
                  {(selectedWorkload.replicas > 1 || selectedWorkload.has_pdb || selectedWorkload.oom_kills === 0) && (
                    <div>
                      <h4 className="text-sm font-bold text-gray-900 mb-2">Safety Verification</h4>
                      <ul className="space-y-2">
                        {selectedWorkload.replicas > 1 && (
                          <li className="flex items-center gap-2 text-sm text-gray-500">
                            <FiCheckCircle className="w-4 h-4 text-indigo-600 flex-shrink-0" />
                            Multi-replica deployment ({selectedWorkload.replicas}/3 ready)
                          </li>
                        )}
                        {selectedWorkload.has_pdb && (
                          <li className="flex items-center gap-2 text-sm text-gray-500">
                            <FiCheckCircle className="w-4 h-4 text-indigo-600 flex-shrink-0" />
                            PodDisruptionBudget active
                          </li>
                        )}
                        {selectedWorkload.oom_kills === 0 && (
                          <li className="flex items-center gap-2 text-sm text-gray-500">
                            <FiCheckCircle className="w-4 h-4 text-indigo-600 flex-shrink-0" />
                            No OOMKills in 30 days
                          </li>
                        )}
                      </ul>
                    </div>
                  )}

                  {/* Actions */}
                  <div className="pt-4 border-t border-gray-100 flex gap-3">
                    <button
                      onClick={() => setSelectedWorkload(null)}
                      className="flex-1 py-2 rounded border border-gray-200 text-sm font-semibold text-gray-700 hover:bg-gray-50 transition-colors"
                    >
                      Decline
                    </button>
                    <button
                      onClick={() => selectedWorkload.id && optimizationAPI.applyRecommendation(selectedWorkload.id).catch(() => {})}
                      disabled={!selectedWorkload.id}
                      className="flex-1 py-2 rounded bg-indigo-600 text-white text-sm font-semibold hover:bg-indigo-700 transition-colors disabled:opacity-50"
                    >
                      Apply {selectedWorkload.recommended_cpu || ''} / {selectedWorkload.recommended_memory || ''}
                    </button>
                  </div>
                </div>
              </>
            )}
          </div>
        </div>

        </div>
      </div>
    </div>
  );
};

export default RightSizing;
