import React, { useMemo } from 'react';
import {
  FiRefreshCw, FiAlertTriangle, FiLoader, FiCheck, FiActivity,
} from 'react-icons/fi';
import { PieChart, Pie, Cell } from 'recharts';
import useClusters from '../../hooks/useClusters';
import useExecutionState from '../../hooks/useExecutionState';
import { BlockedNodeCard, RunningNodeCard } from '../../components/shared/NodeCard';

const EventTimeline = () => {
  const { clusters, selectedId, setSelectedId }                                             = useClusters();
  const { rebalancingActions, rebalancingByState, timeline, loading, error, refetch }       = useExecutionState(selectedId);

  const { active, scheduling, completed, blocked } = rebalancingByState;
  const total      = rebalancingActions.length;
  const overallPct = total > 0 ? Math.round((completed.length / total) * 100) : 0;
  const runningPct = total > 0 ? Math.round((active.length    / total) * 100) : 0;

  const donutData = useMemo(() => {
    const rows = [
      { name: 'Completed', value: completed.length,  color: '#6366f1' },
      { name: 'Running',   value: active.length,     color: '#818cf8' },
      { name: 'Blocked',   value: blocked.length,    color: '#ef4444' },
      { name: 'Pending',   value: scheduling.length, color: '#d1d5db' },
    ].filter(d => d.value > 0);
    return rows.length > 0 ? rows : [{ name: 'No Data', value: 1, color: '#e5e7eb' }];
  }, [completed, active, blocked, scheduling]);

  return (
    <div className="min-h-full bg-gray-50 p-6">
      <div className="max-w-screen-xl mx-auto space-y-6">

        {/* ── Header ── */}
        <div className="flex flex-col md:flex-row md:items-end justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">Rebalancing</h1>
            <p className="text-sm text-gray-500 mt-0.5">Parallel node eviction and pod scheduling in progress.</p>
          </div>
          <div className="flex items-center gap-3">
            {blocked.length > 0 && (
              <button className="flex items-center gap-2.5 bg-gray-100 hover:bg-gray-200 transition-colors px-5 py-2.5 rounded-xl">
                <span className="w-2 h-2 rounded-full bg-red-500" />
                <span className="text-sm font-bold text-gray-800">
                  {blocked.length} node{blocked.length > 1 ? 's' : ''} blocked
                </span>
                <span className="text-xs text-gray-500">Click to fix →</span>
              </button>
            )}
            <div>
              <label className="block text-xs font-medium text-gray-500 mb-1">Cluster</label>
              <select
                value={selectedId}
                onChange={e => setSelectedId(e.target.value)}
                className="text-sm border border-gray-300 rounded-md px-3 py-1.5 focus:outline-none focus:ring-1 focus:ring-indigo-500 focus:border-indigo-500"
              >
                <option value="" disabled>Select cluster</option>
                {clusters.map(c => <option key={c.id} value={c.id}>{c.name || c.id}</option>)}
              </select>
            </div>
            <button
              onClick={refetch}
              disabled={loading}
              className="mt-5 p-2 rounded-md border border-gray-200 bg-white hover:bg-gray-50 transition-colors disabled:opacity-50"
            >
              <FiRefreshCw className={`w-4 h-4 text-gray-600 ${loading ? 'animate-spin' : ''}`} />
            </button>
          </div>
        </div>

        {error && (
          <div className="flex items-center gap-2 p-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700">
            <FiAlertTriangle className="w-4 h-4 flex-shrink-0" /> {error}
          </div>
        )}

        {/* ── Top Section: Progress Card + Status Donut ── */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">

          {/* Rebalancing Progress Card */}
          <div className="lg:col-span-2 bg-white rounded-lg border border-gray-200 shadow-sm p-6 flex flex-col justify-between">
            <div>
              <h2 className="text-base font-bold text-gray-900 mb-5">Rebalancing Progress</h2>
              <div className="flex flex-wrap items-start gap-8 mb-6">
                {[
                  { label: 'Completed', value: completed.length, cls: 'text-indigo-600'  },
                  { label: 'Running',   value: active.length,    cls: 'text-indigo-400'  },
                  { label: 'Blocked',   value: blocked.length,   cls: 'text-red-600'     },
                  { label: 'Pending',   value: scheduling.length, cls: 'text-gray-400'   },
                ].map(({ label, value, cls }) => (
                  <div key={label} className="flex flex-col">
                    <span className="text-xs font-semibold uppercase tracking-wider text-gray-400 mb-0.5">{label}</span>
                    <span className={`text-lg font-bold ${cls}`}>{loading ? '—' : value}</span>
                  </div>
                ))}
              </div>
            </div>
            <div>
              <div className="flex justify-between items-center mb-2">
                <span className="text-sm font-medium text-gray-700">Overall Completion</span>
                <span className="text-sm font-bold text-gray-900">{overallPct}%</span>
              </div>
              <div className="h-3 w-full bg-gray-100 rounded-full overflow-hidden flex">
                <div
                  className="h-full bg-indigo-600 transition-all duration-500"
                  style={{ width: `${overallPct}%` }}
                />
                <div
                  className="h-full bg-indigo-400 opacity-80 transition-all duration-500"
                  style={{ width: `${runningPct}%` }}
                />
              </div>
            </div>
          </div>

          {/* Status Distribution Donut */}
          <div className="bg-white rounded-lg border border-gray-200 shadow-sm p-6 flex items-center justify-between gap-4">
            <div className="flex-1">
              <h2 className="text-base font-bold text-gray-900 mb-4">Status Distribution</h2>
              <ul className="space-y-2.5">
                {[
                  { label: 'Completed', count: completed.length, color: 'bg-indigo-500' },
                  { label: 'Running',   count: active.length,    color: 'bg-indigo-300' },
                  { label: 'Blocked',   count: blocked.length,   color: 'bg-red-500'    },
                  { label: 'Pending',   count: scheduling.length, color: 'bg-gray-300'  },
                ].map(({ label, count, color }) => (
                  <li key={label} className="flex items-center gap-2 text-sm text-gray-700">
                    <span className={`w-2.5 h-2.5 rounded-full flex-shrink-0 ${color}`} />
                    {label} ({total > 0 ? Math.round(count / total * 100) : 0}%)
                  </li>
                ))}
              </ul>
            </div>
            <div className="flex-shrink-0">
              <PieChart width={112} height={112}>
                <Pie
                  data={donutData}
                  cx={52} cy={52}
                  innerRadius={30} outerRadius={50}
                  dataKey="value"
                  strokeWidth={0}
                >
                  {donutData.map((entry, i) => <Cell key={i} fill={entry.color} />)}
                </Pie>
              </PieChart>
            </div>
          </div>
        </div>

        {loading && !total ? (
          <div className="flex items-center justify-center py-20 text-gray-400">
            <FiLoader className="w-6 h-6 animate-spin mr-2" /> Loading rebalancing data…
          </div>
        ) : (
          <div className="space-y-10">

            {/* ── Blocked Nodes ── */}
            <section>
              <div className="flex items-center gap-2 px-1 mb-4">
                <span className="w-2.5 h-2.5 rounded-full bg-red-500" />
                <h3 className="text-base font-bold text-gray-900">Blocked ({blocked.length} nodes)</h3>
                <div className="h-px bg-gray-200 flex-1 ml-4 opacity-50" />
              </div>
              {blocked.length === 0 ? (
                <p className="text-sm text-gray-400 pl-5">No blocked nodes</p>
              ) : (
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
                  {blocked.map((a, i) => <BlockedNodeCard key={a.action_id || i} action={a} />)}
                </div>
              )}
            </section>

            {/* ── Running Nodes ── */}
            <section>
              <div className="flex items-center gap-2 px-1 mb-4">
                <span className="w-2.5 h-2.5 rounded-full bg-indigo-400" />
                <h3 className="text-base font-bold text-gray-900">Running ({active.length} nodes)</h3>
                <div className="h-px bg-gray-200 flex-1 ml-4 opacity-50" />
              </div>
              {active.length === 0 ? (
                <p className="text-sm text-gray-400 pl-5">No active rebalancing operations</p>
              ) : (
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
                  {active.map((a, i) => <RunningNodeCard key={a.action_id || i} action={a} />)}
                </div>
              )}
            </section>

            {/* ── Scheduling / Pending ── */}
            {scheduling.length > 0 && (
              <section>
                <div className="flex items-center gap-2 px-1 mb-4">
                  <span className="w-2.5 h-2.5 rounded-full bg-yellow-400" />
                  <h3 className="text-base font-bold text-gray-900">Scheduling ({scheduling.length} nodes)</h3>
                  <div className="h-px bg-gray-200 flex-1 ml-4 opacity-50" />
                </div>
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
                  {scheduling.map((a, i) => <RunningNodeCard key={a.action_id || i} action={a} />)}
                </div>
              </section>
            )}

            {/* ── Completed Nodes ── */}
            <section>
              <div className="flex items-center gap-2 px-1 mb-4">
                <span className="w-2.5 h-2.5 rounded-full bg-indigo-600" />
                <h3 className="text-base font-bold text-gray-900">Completed ({completed.length} nodes)</h3>
                <div className="h-px bg-gray-200 flex-1 ml-4 opacity-50" />
              </div>
              {completed.length === 0 ? (
                <p className="text-sm text-gray-400 pl-5">No completed operations yet</p>
              ) : (
                <div className="flex flex-wrap gap-2">
                  {completed.slice(0, 20).map((a, i) => (
                    <div
                      key={a.action_id || i}
                      className="bg-gray-50 border border-gray-200 px-4 py-2 rounded-full flex items-center gap-2 text-sm shadow-sm"
                    >
                      <span className="font-medium text-gray-700">{a.node_id || a.action_id || `op-${i}`}</span>
                      <FiCheck className="w-3.5 h-3.5 text-indigo-500" />
                    </div>
                  ))}
                  {completed.length > 20 && (
                    <div className="bg-gray-100 border border-gray-200 px-4 py-2 rounded-full text-sm text-gray-500 cursor-pointer hover:bg-gray-200 transition-colors">
                      +{completed.length - 20} more
                    </div>
                  )}
                </div>
              )}
            </section>

            {/* ── Event Feed ── */}
            {timeline.length > 0 && (
              <section>
                <div className="flex items-center gap-2 mb-4">
                  <FiActivity className="w-4 h-4 text-gray-400" />
                  <h3 className="text-base font-bold text-gray-900">Event Feed</h3>
                  <div className="h-px bg-gray-200 flex-1 ml-2" />
                  <span className="text-xs text-gray-400">{timeline.length} recent events</span>
                </div>
                <div className="bg-white rounded-lg border border-gray-200 shadow-sm divide-y divide-gray-50">
                  {timeline.map((a, i) => (
                    <div key={a.id || i} className="px-5 py-3 hover:bg-gray-50 transition-colors flex items-start justify-between gap-2">
                      <div className="min-w-0">
                        <p className="text-sm font-medium text-gray-900 capitalize truncate">
                          {(a.action_type || a.type || 'event').replace(/_/g, ' ')}
                        </p>
                        <p className="text-xs text-gray-500 mt-0.5 truncate">{a.node_id || a.workload || a.target || '—'}</p>
                      </div>
                      <div className="text-right flex-shrink-0">
                        <span className={`text-xs px-1.5 py-0.5 rounded font-semibold ${
                          a.status === 'completed' ? 'bg-green-100 text-green-700' :
                          a.status === 'failed'    ? 'bg-red-100 text-red-700'     :
                                                     'bg-gray-100 text-gray-600'
                        }`}>{a.status || 'unknown'}</span>
                        <p className="text-xs text-gray-400 mt-0.5">
                          {a.created_at ? new Date(a.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : ''}
                        </p>
                      </div>
                    </div>
                  ))}
                </div>
              </section>
            )}
          </div>
        )}
      </div>
    </div>
  );
};

export default EventTimeline;
