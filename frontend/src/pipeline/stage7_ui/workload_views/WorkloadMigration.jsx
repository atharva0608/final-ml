import React, { useState, useEffect, useCallback } from 'react';
import useClusters from '../../../hooks/useClusters';
import { migrationStatusAPI, decisionEngineAPI } from '../../../services/api';

// ── EE state machine — mirrors ExecutionEngine.STATE_LABELS ──────────────────
const EE_FLOW = [
  { key: 'PROVISIONING',        short: 'Provision' },
  { key: 'EXECUTING',           short: 'Stateful' },
  { key: 'EXECUTING_STATELESS', short: 'Batch' },
  { key: 'DRAINING',            short: 'Drain' },
  { key: 'VERIFYING',           short: 'Verify' },
];
const EE_LABELS = {
  IDLE:                'Idle',
  PROVISIONING:        'Provisioning nodes',
  EXECUTING:           'Migrating stateful workloads',
  EXECUTING_STATELESS: 'Migrating batch workloads',
  DRAINING:            'Draining vacated nodes',
  VERIFYING:           'Verifying placement',
  FAILED:              'Execution failed',
  PARTIAL:             'Completed with warnings',
  COMPLETED:           'Completed',
};
const EE_STATE_CLS = {
  IDLE:                'bg-gray-100 text-gray-500 border-gray-200',
  PROVISIONING:        'bg-blue-50 text-blue-700 border-blue-200',
  EXECUTING:           'bg-amber-50 text-amber-700 border-amber-200',
  EXECUTING_STATELESS: 'bg-amber-50 text-amber-700 border-amber-200',
  DRAINING:            'bg-orange-50 text-orange-700 border-orange-200',
  VERIFYING:           'bg-indigo-50 text-indigo-700 border-indigo-200',
  FAILED:              'bg-red-50 text-red-600 border-red-200',
  PARTIAL:             'bg-yellow-50 text-yellow-700 border-yellow-200',
  COMPLETED:           'bg-green-50 text-green-700 border-green-200',
};

const EE_STEP_DETAIL = {
  IDLE:                'Waiting for a trigger — no migration in progress.',
  PROVISIONING:        'Spinning up new spot nodes as per the node plan. DaemonSets auto-schedule.',
  EXECUTING:           'Moving DB / stateful workloads first (SERIAL strategy). HPA & KEDA frozen.',
  EXECUTING_STATELESS: 'Rolling migration of stateless batch workloads. Blue-green or rolling strategy.',
  DRAINING:            'Draining vacated nodes — evicting any remaining pods before termination.',
  VERIFYING:           'Checking all pods are scheduled on the correct node type as per the plan.',
  FAILED:              'Execution stopped due to an error. Check the error message below.',
  PARTIAL:             'Migration completed but some pods are on incorrect node types.',
  COMPLETED:           'All pods are on target nodes. Migration succeeded.',
};

const HISTORY_STYLE = {
  SUCCESS:     'bg-green-50 text-green-700 border-green-200',
  COMPLETED:   'bg-green-50 text-green-700 border-green-200',
  FAILED:      'bg-red-50 text-red-600 border-red-200',
  IN_PROGRESS: 'bg-amber-50 text-amber-700 border-amber-200',
  PENDING:     'bg-gray-100 text-gray-500 border-gray-200',
  FROZEN:      'bg-blue-50 text-blue-700 border-blue-200',
};

function fmtTs(iso) {
  if (!iso) return '—';
  try { return new Date(iso).toLocaleString(); } catch (e) { return iso; }
}

function fmtTtl(secs) {
  if (secs == null || secs < 0) return '—';
  const m = Math.floor(secs / 60);
  const s = secs % 60;
  return m > 0 ? (m + 'm ' + s + 's') : (s + 's');
}

// ── EE State Machine visual ───────────────────────────────────────────────────
function EEStateMachine({ state }) {
  const s = (state || 'IDLE').toUpperCase();
  const isTerminal = s === 'FAILED' || s === 'PARTIAL' || s === 'COMPLETED';
  const activeIdx  = EE_FLOW.findIndex(f => f.key === s);

  return (
    <div className="space-y-2">
      <div className="flex items-center gap-1">
        {EE_FLOW.map((step, idx) => {
          const done    = activeIdx >= 0 && idx < activeIdx;
          const current = idx === activeIdx;
          const pending = activeIdx < 0 || idx > activeIdx;
          return (
            <React.Fragment key={step.key}>
              <div className={`flex flex-col items-center`}>
                <div className={`w-6 h-6 rounded-full flex items-center justify-center text-[9px] font-bold border-2 transition-all ${
                  done    ? 'bg-green-500 border-green-500 text-white' :
                  current ? 'bg-blue-600 border-blue-600 text-white animate-pulse' :
                            'bg-white border-gray-300 text-gray-400'
                }`}>
                  {done ? '✓' : current ? '●' : idx + 1}
                </div>
                <span className={`text-[8px] mt-0.5 font-medium ${
                  done ? 'text-green-600' : current ? 'text-blue-700' : 'text-gray-400'
                }`}>{step.short}</span>
              </div>
              {idx < EE_FLOW.length - 1 && (
                <div className={`flex-1 h-0.5 mb-3 ${done ? 'bg-green-400' : 'bg-gray-200'}`} />
              )}
            </React.Fragment>
          );
        })}
        {/* Terminal badge */}
        {isTerminal && (
          <>
            <div className={`flex-1 h-0.5 mb-3 ${s === 'COMPLETED' || s === 'PARTIAL' ? 'bg-green-300' : 'bg-red-300'}`} />
            <div className={`flex flex-col items-center`}>
              <div className={`w-6 h-6 rounded-full flex items-center justify-center text-[9px] font-bold border-2 ${
                s === 'COMPLETED' ? 'bg-green-500 border-green-500 text-white' :
                s === 'PARTIAL'   ? 'bg-yellow-400 border-yellow-500 text-white' :
                                    'bg-red-500 border-red-500 text-white'
              }`}>
                {s === 'COMPLETED' ? '✓' : s === 'PARTIAL' ? '⚠' : '✗'}
              </div>
              <span className={`text-[8px] mt-0.5 font-medium ${
                s === 'COMPLETED' ? 'text-green-600' : s === 'PARTIAL' ? 'text-yellow-600' : 'text-red-600'
              }`}>{s === 'COMPLETED' ? 'Done' : s === 'PARTIAL' ? 'Partial' : 'Failed'}</span>
            </div>
          </>
        )}
      </div>
      <div className={`px-2 py-1 rounded text-[10px] font-semibold border inline-block ${EE_STATE_CLS[s] || EE_STATE_CLS.IDLE}`}>
        {EE_LABELS[s] || s}
      </div>
      {EE_STEP_DETAIL[s] && (
        <p className="text-[10px] text-gray-500 mt-1.5 leading-snug">{EE_STEP_DETAIL[s]}</p>
      )}
    </div>
  );
}

// ── Execution Plan (node_plan + movement_plan) ────────────────────────────────
function ExecutionPlanSection({ manifest }) {
  if (!manifest) return null;
  const nodePlan     = manifest.node_plan || [];
  const movementPlan = manifest.movement_plan || [];
  const provNodes    = nodePlan.filter(n => n.action === 'provision');
  const drainNodes   = nodePlan.filter(n => n.action === 'drain');
  if (!nodePlan.length && !movementPlan.length) return null;

  return (
    <div className="bg-white border border-blue-100 rounded-xl overflow-hidden shadow-sm">
      <div className="px-4 py-2.5 bg-gradient-to-r from-blue-50 to-white border-b border-blue-100 flex items-center justify-between">
        <div>
          <h2 className="text-xs font-bold uppercase tracking-wider text-blue-700">Execution Plan</h2>
          <p className="text-[10px] text-blue-400 mt-0.5">What the engine will do — from resolved manifest</p>
        </div>
        <div className="flex gap-1.5 text-[10px] flex-wrap">
          {provNodes.length  > 0 && <span className="px-2 py-0.5 rounded border bg-blue-50 border-blue-200 text-blue-700 font-semibold">+{provNodes.length} node{provNodes.length !== 1 ? 's' : ''}</span>}
          {drainNodes.length > 0 && <span className="px-2 py-0.5 rounded border bg-amber-50 border-amber-200 text-amber-700 font-semibold">drain {drainNodes.length}</span>}
          {movementPlan.length > 0 && <span className="px-2 py-0.5 rounded border bg-gray-50 border-gray-200 text-gray-600 font-semibold">{movementPlan.length} pod move{movementPlan.length !== 1 ? 's' : ''}</span>}
        </div>
      </div>
      <div className="p-4 space-y-4">
        {/* Nodes to provision */}
        {provNodes.length > 0 && (
          <div>
            <div className="text-[10px] font-bold uppercase tracking-wider text-gray-400 mb-1.5">Nodes to Provision</div>
            <div className="space-y-1.5">
              {provNodes.map((n, i) => (
                <div key={i} className="flex items-center gap-3 bg-blue-50 border border-blue-100 rounded-lg px-3 py-2 text-xs">
                  <span className="w-1.5 h-1.5 rounded-full bg-blue-500 flex-shrink-0" />
                  <span className="font-mono text-gray-700 font-semibold min-w-0 truncate">{n.node_name || `node-${i+1}`}</span>
                  <span className="text-gray-400">{n.az || '—'}</span>
                  <span className={`px-1.5 py-0.5 rounded text-[9px] font-bold border ${
                    (n.capacity_type||'').toLowerCase() === 'spot' ? 'bg-indigo-100 border-indigo-200 text-indigo-700' : 'bg-red-100 border-red-200 text-red-700'
                  }`}>{n.capacity_type || '—'}</span>
                  {n.instance_type
                    ? <span className="font-mono text-gray-600 text-[11px]">{n.instance_type}</span>
                    : <span className="text-amber-500 italic text-[10px]">Pending ISS</span>
                  }
                  <span className="ml-auto text-gray-400 flex-shrink-0">{n.pod_count || 0} pods · {Math.round((n.required_cpu_millicores||0)/1000 * 10)/10} vCPU</span>
                </div>
              ))}
            </div>
          </div>
        )}
        {/* Nodes to drain */}
        {drainNodes.length > 0 && (
          <div>
            <div className="text-[10px] font-bold uppercase tracking-wider text-gray-400 mb-1.5">Nodes to Drain</div>
            <div className="space-y-1.5">
              {drainNodes.map((n, i) => (
                <div key={i} className="flex items-center gap-3 bg-amber-50 border border-amber-100 rounded-lg px-3 py-2 text-xs">
                  <span className="w-1.5 h-1.5 rounded-full bg-amber-500 flex-shrink-0" />
                  <span className="font-mono text-gray-700 font-semibold truncate">{n.node_name || `drain-${i+1}`}</span>
                  <span className="text-gray-400">{n.az || '—'}</span>
                  <span className="ml-auto text-amber-600 font-semibold flex-shrink-0">All pods evicted</span>
                </div>
              ))}
            </div>
          </div>
        )}
        {/* Pod movements */}
        {movementPlan.length > 0 && (
          <div>
            <div className="text-[10px] font-bold uppercase tracking-wider text-gray-400 mb-1.5">Pod Movements</div>
            <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
              <table className="min-w-full text-xs font-mono">
                <thead>
                  <tr className="border-b border-gray-100 bg-gray-50">
                    {['Pod', 'From', 'To Node', 'Instance', 'AZ', 'Status'].map(h => (
                      <th key={h} className="px-3 py-1.5 text-left text-[10px] font-semibold uppercase text-gray-400">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-50">
                  {movementPlan.slice(0, 8).map((m, i) => {
                    const toNodePlan = nodePlan.find(n => n.node_name === m.to_node);
                    const instType = m.to_instance_type || toNodePlan?.instance_type;
                    return (
                    <tr key={i} className="hover:bg-gray-50">
                      <td className="px-3 py-1.5 text-gray-700 truncate max-w-[140px]" title={m.pod_name}>{m.pod_name}</td>
                      <td className="px-3 py-1.5">
                        <span className={`px-1.5 py-0.5 rounded text-[9px] font-semibold ${m.from_capacity_type === 'spot' ? 'bg-indigo-50 text-indigo-700' : 'bg-red-50 text-red-700'}`}>
                          {m.from_capacity_type || '—'}
                        </span>
                      </td>
                      <td className="px-3 py-1.5 text-gray-600 truncate max-w-[100px]">{m.to_node ? m.to_node.split('.')[0] : '—'}</td>
                      <td className="px-3 py-1.5">
                        {instType
                          ? <span className="font-mono text-gray-600 text-[10px]">{instType}</span>
                          : <span className="text-amber-500 italic text-[9px]">Pending ISS</span>}
                      </td>
                      <td className="px-3 py-1.5 text-gray-400">{m.to_az || '—'}</td>
                      <td className="px-3 py-1.5">
                        {m.blocked_by
                          ? <span className="text-red-600 font-semibold text-[9px]">⚠ {m.blocked_by}</span>
                          : <span className="text-green-600 text-[9px]">ready</span>}
                      </td>
                    </tr>
                    );
                  })}
                </tbody>
              </table>
              {movementPlan.length > 8 && (
                <div className="px-3 py-1.5 text-[10px] text-gray-400 italic border-t border-gray-50">
                  +{movementPlan.length - 8} more moves…
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// ── Planned vs Actual (override merge display) ────────────────────────────────
function PlannedVsActualSection({ manifest, overrides }) {
  if (!manifest) return null;
  const nodePlan = (manifest.node_plan || []).filter(n => n.action === 'provision');
  if (!nodePlan.length) return null;

  // overrides: { node_name: { instance_type: { original, override } } }
  const hasOverrides = overrides && Object.keys(overrides).length > 0;
  if (!hasOverrides && !manifest._overrides_applied) return null;

  return (
    <div className="bg-white border border-yellow-100 rounded-xl overflow-hidden shadow-sm">
      <div className="px-4 py-2.5 bg-gradient-to-r from-yellow-50 to-white border-b border-yellow-100 flex items-center gap-2">
        <h2 className="text-xs font-bold uppercase tracking-wider text-yellow-700">Planned vs Actual</h2>
        <span className="px-2 py-0.5 text-[9px] font-bold bg-yellow-100 border border-yellow-200 text-yellow-700 rounded">Override active</span>
        <p className="text-[10px] text-yellow-500 ml-auto">Instance type changed at runtime due to pool failure</p>
      </div>
      <div className="p-4">
        <div className="space-y-2">
          {nodePlan.map((n, i) => {
            const nodeOvr = overrides && overrides[n.node_name];
            const plannedType = nodeOvr?.instance_type?.original || n._planned_instance_type || null;
            const actualType  = nodeOvr?.instance_type?.override  || n.instance_type;
            const wasChanged  = plannedType && plannedType !== actualType;
            return (
              <div key={i} className={`flex items-center gap-3 rounded-lg px-3 py-2 text-xs border ${wasChanged ? 'bg-yellow-50 border-yellow-200' : 'bg-gray-50 border-gray-200'}`}>
                <span className="w-1.5 h-1.5 rounded-full flex-shrink-0" style={{ background: wasChanged ? '#f59e0b' : '#9ca3af' }} />
                <span className="font-mono text-gray-700 font-semibold min-w-0 truncate">{n.node_name}</span>
                <span className="text-gray-400 flex-shrink-0">{n.az}</span>
                {wasChanged ? (
                  <div className="flex items-center gap-1.5 ml-auto flex-shrink-0">
                    <span className="font-mono text-gray-400 line-through text-[10px]">{plannedType}</span>
                    <span className="text-gray-400 text-[10px]">→</span>
                    <span className="font-mono text-yellow-700 font-bold text-[11px]">{actualType}</span>
                    <span className="px-1.5 py-0.5 rounded text-[9px] font-bold bg-yellow-100 border border-yellow-300 text-yellow-700">retry</span>
                  </div>
                ) : (
                  <div className="ml-auto flex-shrink-0">
                    <span className="font-mono text-gray-600 text-[11px]">{actualType || '—'}</span>
                    <span className="ml-2 text-[9px] text-green-600">✓ as planned</span>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

// ── Execution Result (verification summary) ───────────────────────────────────
function VerificationResultSection({ verification, eeState }) {
  if (!verification && eeState !== 'PARTIAL' && eeState !== 'COMPLETED' && eeState !== 'FAILED') return null;
  const matched    = (verification?.matched    || []).length;
  const mismatched = (verification?.mismatched || []).length;
  const skipped    = (verification?.skipped    || []).length;
  const total      = matched + mismatched;
  const mismatchPct = total > 0 ? Math.round((mismatched / total) * 100) : 0;

  return (
    <div className={`rounded-xl border overflow-hidden shadow-sm ${
      eeState === 'FAILED'  ? 'bg-red-50 border-red-200' :
      eeState === 'PARTIAL' ? 'bg-yellow-50 border-yellow-200' :
                              'bg-green-50 border-green-200'
    }`}>
      <div className="px-4 py-2.5 border-b border-opacity-50 flex items-center gap-2">
        <span className="text-lg leading-none">
          {eeState === 'FAILED' ? '✗' : eeState === 'PARTIAL' ? '⚠' : '✓'}
        </span>
        <h2 className={`text-xs font-bold uppercase tracking-wider ${
          eeState === 'FAILED' ? 'text-red-700' : eeState === 'PARTIAL' ? 'text-yellow-700' : 'text-green-700'
        }`}>Execution Result</h2>
      </div>
      <div className="p-4 grid grid-cols-3 gap-3">
        <div className="bg-white rounded-lg border border-green-200 p-3 text-center">
          <div className="text-xl font-bold text-green-700">{matched}</div>
          <div className="text-[10px] font-semibold uppercase text-green-600">Pods Matched</div>
        </div>
        <div className={`bg-white rounded-lg border p-3 text-center ${mismatched > 0 ? 'border-red-200' : 'border-gray-200'}`}>
          <div className={`text-xl font-bold ${mismatched > 0 ? 'text-red-600' : 'text-gray-400'}`}>{mismatched}</div>
          <div className={`text-[10px] font-semibold uppercase ${mismatched > 0 ? 'text-red-500' : 'text-gray-400'}`}>Mismatched</div>
        </div>
        <div className="bg-white rounded-lg border border-gray-200 p-3 text-center">
          <div className="text-xl font-bold text-gray-400">{skipped}</div>
          <div className="text-[10px] font-semibold uppercase text-gray-400">Skipped</div>
        </div>
      </div>
      {mismatchPct > 0 && (
        <div className="px-4 pb-3 text-xs text-yellow-700">
          {mismatchPct}% mismatch rate — pods scheduled on incorrect node type
        </div>
      )}
    </div>
  );
}

export default function WorkloadMigration() {
  const { clusters, selectedId: clusterId, setSelectedId: setClusterId, planCompleteness } = useClusters();

  const [data, setData]             = useState(null);
  const [loading, setLoading]       = useState(false);
  const [error, setError]           = useState(null);
  const [selected, setSelected]     = useState(null);
  const [search, setSearch]         = useState('');
  const [actionMsg, setActionMsg]   = useState(null);
  const [acting, setActing]         = useState(false);
  const [execStatus, setExecStatus] = useState(null);

  const load = useCallback(() => {
    if (!clusterId) return;
    setLoading(true);
    setError(null);
    migrationStatusAPI.get(clusterId, 100)
      .then(r => {
        setData(r.data);
        setSelected(prev => {
          if (!prev && r.data?.active_migrations?.length)
            return r.data.active_migrations[0];
          return prev;
        });
      })
      .catch(e => setError(
        e?.response?.data?.detail || 'Failed to load migration data'
      ))
      .finally(() => setLoading(false));
  }, [clusterId]);

  const loadExecStatus = useCallback(() => {
    if (!clusterId) return;
    decisionEngineAPI.getExecutionStatus(clusterId)
      .then(r => setExecStatus(r.data))
      .catch(() => setExecStatus(null));
  }, [clusterId]);

  useEffect(() => { load(); loadExecStatus(); }, [load, loadExecStatus]);

  const allItems = [
    ...((data?.active_migrations) ? data.active_migrations.map(m => ({ ...m, _type: 'active' }))  : []),
    ...((data?.history)           ? data.history.map(h => ({ ...h, _type: 'history' }))           : []),
  ];
  const filtered = allItems.filter(item =>
    (item.controller_name || '').toLowerCase().includes(search.toLowerCase())
  );

  function handleStartMigration() {
    if (!clusterId || acting) return;
    setActing(true);
    setActionMsg(null);
    migrationStatusAPI.startMigration(clusterId)
      .then(() => { setActionMsg('Migration started — refreshing…'); load(); loadExecStatus(); })
      .catch(e => setActionMsg(e?.response?.data?.detail || 'Start migration failed.'))
      .finally(() => setActing(false));
  }

  const phase    = data?.phase || 'not_started';
  const eeState  = (execStatus?.state || 'IDLE').toUpperCase();
  const manifest = execStatus?.manifest || null;
  const overrides = execStatus?.overrides || null;
  const verification = execStatus?.verification || null;
  const c = selected;

  return (
    <div className="flex bg-gray-50 overflow-hidden" style={{ height: 'calc(100vh - 64px)' }}>

      {/* ── LEFT PANEL ───────────────────────────────────────────── */}
      <div className="w-72 flex-shrink-0 bg-white border-r border-gray-200 flex flex-col">
        <div className="p-4 border-b border-gray-100">
          <div className="flex items-center justify-between mb-2">
            <h2 className="text-sm font-bold text-gray-900">Workload Migrations</h2>
            <button onClick={() => { load(); loadExecStatus(); }} disabled={loading} title="Refresh"
              className="text-gray-400 hover:text-gray-600 text-xs px-1">
              {loading ? '⟳' : '↻'}
            </button>
          </div>
          <div className="mb-2">
            <label className="text-[10px] font-bold text-gray-400 uppercase tracking-wide">Cluster:</label>
            <select
              value={clusterId}
              onChange={e => { setClusterId(e.target.value); setSelected(null); setData(null); setExecStatus(null); }}
              className="text-xs border border-gray-200 rounded px-2 py-0.5 w-full mt-0.5 focus:outline-none focus:border-blue-400"
            >
              <option value="" disabled>Select cluster</option>
              {clusters.map(cl => <option key={cl.id} value={cl.id}>{cl.name || cl.id}</option>)}
            </select>
          </div>
          <input
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="Filter workloads…"
            className="w-full px-2 py-1.5 bg-gray-50 border border-gray-200 rounded text-xs focus:outline-none focus:border-blue-400"
          />
        </div>

        {/* ── EE State Machine in sidebar ── */}
        {clusterId && (
          <div className="px-4 py-3 border-b border-gray-100">
            <div className="text-[9px] font-bold uppercase tracking-wider text-gray-400 mb-2">Execution Engine</div>
            <EEStateMachine state={eeState} />
            {data?.spot_percentage != null && (
              <div className="text-[10px] text-gray-400 mt-2">{data.spot_percentage}% spot coverage</div>
            )}
          </div>
        )}

        <div className="flex-1 overflow-y-auto p-2 space-y-1">
          {!clusterId && (
            <p className="text-xs text-gray-400 text-center mt-8">Select a cluster</p>
          )}
          {clusterId && !loading && filtered.length === 0 && (
            <p className="text-xs text-gray-400 text-center mt-8">No migration events</p>
          )}
          {filtered.map((item, idx) => {
            const key = item.id != null ? item.id : (item.controller_name + '-' + idx);
            const isActive = item._type === 'active';
            const isSel = c && c === item;
            const stateCls = item.state ? (HISTORY_STYLE[item.state.toUpperCase()] || HISTORY_STYLE.PENDING) : '';
            return (
              <button key={key} onClick={() => setSelected(item)}
                className={'w-full text-left p-3 rounded-lg transition-all relative overflow-hidden ' +
                  (isSel ? 'bg-white border border-blue-200 shadow-sm' : 'border border-transparent hover:bg-gray-50')}>
                {isSel && <div className="absolute left-0 top-0 bottom-0 w-1 bg-blue-600 rounded-r" />}
                <div className="flex justify-between items-start">
                  <span className="font-mono text-xs font-semibold text-gray-900 truncate pr-1">
                    {item.controller_name || '—'}
                  </span>
                  {isActive && (
                    <span className="px-1.5 py-0.5 text-[9px] font-bold bg-amber-50 text-amber-700 border border-amber-200 rounded-full shrink-0">
                      ACTIVE
                    </span>
                  )}
                </div>
                <div className="text-[10px] text-gray-400 mt-1 truncate">
                  {item.namespace || item.controller_kind || '—'}
                </div>
                {item.state && (
                  <span className={'mt-1.5 inline-block px-1.5 py-0.5 text-[9px] font-bold rounded border ' + stateCls}>
                    {item.state}
                  </span>
                )}
                {isActive && item.ttl_remaining_s != null && (
                  <div className="text-[10px] text-gray-400 mt-1">TTL: {fmtTtl(item.ttl_remaining_s)}</div>
                )}
              </button>
            );
          })}
        </div>
      </div>

      {/* ── RIGHT PANEL ──────────────────────────────────────────── */}
      <div className="flex-1 overflow-y-auto bg-gray-50 p-6">
        {error && (
          <div className="mb-4 bg-red-50 border border-red-200 rounded-lg px-4 py-2 text-xs text-red-700">{error}</div>
        )}
        {actionMsg && (
          <div className="mb-4 bg-blue-50 border border-blue-200 rounded-lg px-4 py-2 text-xs text-blue-700">{actionMsg}</div>
        )}

        {/* ── Cluster overview (no item selected) ── */}
        {!c && data && (
          <div className="max-w-2xl mx-auto space-y-4">
            {/* Cluster stats */}
            <div className="bg-white border border-gray-200 rounded-xl p-6">
              <h1 className="text-base font-bold text-gray-900 mb-1">{data.cluster_name || clusterId}</h1>
              <p className="text-xs text-gray-400 mb-4">Cluster migration overview</p>
              <div className="grid grid-cols-3 gap-4">
                {[
                  { l: 'Total Nodes',       v: data.total_nodes         ?? '—' },
                  { l: 'Spot Nodes',        v: data.spot_nodes          ?? '—' },
                  { l: 'OD Remaining',      v: data.on_demand_remaining ?? '—' },
                  { l: 'Spot %',            v: (data.spot_percentage ?? 0) + '%' },
                  { l: 'Active Migrations', v: data.active_migrations?.length ?? 0 },
                  { l: 'History Events',    v: data.history?.length ?? 0 },
                ].map(s => (
                  <div key={s.l} className="bg-gray-50 border border-gray-100 rounded-lg p-3">
                    <div className="text-[10px] font-bold uppercase tracking-wider text-gray-400 mb-1">{s.l}</div>
                    <div className="text-lg font-bold text-gray-900">{s.v}</div>
                  </div>
                ))}
              </div>
            </div>

            {/* EE state + Execution Plan in overview (when manifest exists) */}
            {execStatus && (
              <div className="bg-white border border-gray-200 rounded-xl p-5">
                <div className="flex items-start justify-between mb-3">
                  <h2 className="text-xs font-bold uppercase tracking-wider text-gray-700">Execution Engine State</h2>
                  {execStatus.manifest_id && (
                    <span className="font-mono text-[10px] text-gray-400">#{execStatus.manifest_id}</span>
                  )}
                </div>
                <EEStateMachine state={eeState} />
                {execStatus.error && (
                  <div className="mt-3 bg-red-50 border border-red-200 rounded px-3 py-2 text-xs text-red-700">
                    {execStatus.error}
                  </div>
                )}
              </div>
            )}

            {/* Execution Plan (from overview manifest) */}
            <ExecutionPlanSection manifest={manifest} />

            {/* Planned vs Actual */}
            <PlannedVsActualSection manifest={manifest} overrides={overrides} />

            {/* Verification Result */}
            <VerificationResultSection verification={verification} eeState={eeState} />

            <div className="flex gap-3">
              <button
                onClick={handleStartMigration}
                disabled={acting || phase === 'completed' || planCompleteness !== 'resolved'}
                title={
                  phase === 'completed' ? 'Migration already completed'
                  : planCompleteness === 'loading' ? 'Loading plan…'
                  : planCompleteness === 'draft' ? 'Plan not fully resolved — run ISS first'
                  : planCompleteness === 'partial' ? 'Some instance types still pending ISS'
                  : planCompleteness === 'none' ? 'No engine plan available'
                  : 'Trigger OD→Spot migration cycle'
                }
                className={'px-4 py-2 text-xs font-semibold rounded-lg transition-colors ' +
                  (acting || phase === 'completed' || planCompleteness !== 'resolved'
                    ? 'bg-gray-200 text-gray-400 cursor-not-allowed'
                    : 'bg-blue-600 hover:bg-blue-700 text-white')}
              >
                {acting ? '⟳ Starting…' : '▶ Start Migration'}
                {planCompleteness !== 'resolved' && planCompleteness !== 'loading' && planCompleteness !== 'none' && (
                  <span className="ml-1 text-[9px]">(ISS incomplete)</span>
                )}
              </button>
            </div>
          </div>
        )}

        {/* ── Detail view (migration event selected) ── */}
        {c && (
          <div className="max-w-3xl mx-auto space-y-5 pb-16">
            <div className="flex items-start justify-between pb-4 border-b border-gray-200">
              <div>
                <div className="flex items-center gap-3 mb-1">
                  <h1 className="font-mono text-lg font-bold text-gray-900">{c.controller_name || '—'}</h1>
                  {c._type === 'active' && (
                    <span className="px-2 py-0.5 text-[10px] font-bold bg-amber-50 text-amber-700 border border-amber-200 rounded">
                      ACTIVE
                    </span>
                  )}
                </div>
                <div className="flex gap-2 flex-wrap">
                  {c.namespace && (
                    <span className="px-2 py-0.5 text-[10px] bg-gray-100 text-gray-600 border border-gray-200 rounded">{c.namespace}</span>
                  )}
                  {c.controller_kind && (
                    <span className="px-2 py-0.5 text-[10px] bg-gray-100 text-gray-600 border border-gray-200 rounded">{c.controller_kind}</span>
                  )}
                  {c.workload_tier && (
                    <span className="px-2 py-0.5 text-[10px] bg-blue-50 text-blue-700 border border-blue-200 rounded">{c.workload_tier}</span>
                  )}
                  {c.state && (
                    <span className={'px-2 py-0.5 text-[10px] font-bold border rounded ' + (HISTORY_STYLE[c.state.toUpperCase()] || HISTORY_STYLE.PENDING)}>
                      {c.state}
                    </span>
                  )}
                </div>
              </div>
              <button onClick={() => setSelected(null)} className="text-xs text-gray-400 hover:text-gray-600 mt-1">
                ✕ Close
              </button>
            </div>

            {/* Active migration detail */}
            {c._type === 'active' && (
              <div className="bg-white border border-gray-200 rounded-xl p-5">
                <h2 className="text-xs font-bold text-gray-700 uppercase tracking-wider mb-3">Active Migration State</h2>
                <div className="grid grid-cols-2 gap-3">
                  {[
                    { l: 'Frozen At',     v: fmtTs(c.frozen_at) },
                    { l: 'TTL Remaining', v: fmtTtl(c.ttl_remaining_s) },
                    { l: 'HPA Frozen',    v: c.hpa_frozen  ? '✓ Yes' : '✗ No' },
                    { l: 'KEDA Frozen',   v: c.keda_frozen ? '✓ Yes' : '✗ No' },
                  ].map(f => (
                    <div key={f.l} className="bg-gray-50 rounded-lg p-3">
                      <div className="text-[10px] font-bold uppercase tracking-wider text-gray-400 mb-0.5">{f.l}</div>
                      <div className="text-sm font-semibold text-gray-800">{f.v}</div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* History migration event */}
            {c._type === 'history' && (
              <div className="bg-white border border-gray-200 rounded-xl p-5">
                <h2 className="text-xs font-bold text-gray-700 uppercase tracking-wider mb-3">Migration Event</h2>
                <div className="grid grid-cols-2 gap-3">
                  {[
                    { l: 'Source Node',     v: c.source_node    || '—' },
                    { l: 'Target Node',     v: c.target_node    || '—' },
                    { l: 'Pod Location',    v: c.pod_location   || '—' },
                    { l: 'Freeze Restored', v: c.freeze_restored ? '✓ Yes' : '✗ No' },
                    { l: 'Failure Reason',  v: c.failure_reason || 'None' },
                    { l: 'Created At',      v: fmtTs(c.created_at) },
                  ].map(f => (
                    <div key={f.l} className="bg-gray-50 rounded-lg p-3">
                      <div className="text-[10px] font-bold uppercase tracking-wider text-gray-400 mb-0.5">{f.l}</div>
                      <div className="text-sm font-semibold text-gray-800 break-all">{f.v}</div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* EE State Machine — always shown in detail view if cluster active */}
            {execStatus && (
              <div className="bg-white border border-gray-200 rounded-xl p-5">
                <div className="flex items-center justify-between mb-3">
                  <h2 className="text-xs font-bold text-gray-700 uppercase tracking-wider">Execution Engine State</h2>
                  {execStatus.manifest_id && (
                    <span className="font-mono text-[10px] text-gray-400">manifest #{execStatus.manifest_id}</span>
                  )}
                </div>
                <EEStateMachine state={eeState} />
              </div>
            )}

            {/* Execution Plan (from cluster manifest) */}
            <ExecutionPlanSection manifest={manifest} />

            {/* Planned vs Actual override comparison */}
            <PlannedVsActualSection manifest={manifest} overrides={overrides} />

            {/* Verification / execution result */}
            <VerificationResultSection verification={verification} eeState={eeState} />

            <div className="flex gap-3">
              <button
                onClick={() => setSelected(null)}
                className="px-3 py-1.5 text-xs font-semibold border border-gray-200 rounded-lg text-gray-600 hover:bg-gray-100"
              >
                ← Back to Overview
              </button>
            </div>
          </div>
        )}

        {!clusterId && (
          <div className="flex items-center justify-center h-full text-gray-400 text-sm">
            Select a cluster to view migration status
          </div>
        )}
        {clusterId && loading && !data && (
          <div className="flex items-center justify-center h-full text-gray-400 text-sm">Loading…</div>
        )}
      </div>
    </div>
  );
}
