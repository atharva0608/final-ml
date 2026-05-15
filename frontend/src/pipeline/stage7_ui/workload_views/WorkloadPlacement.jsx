import React, { useState, useEffect } from 'react';
import { FiAlertCircle } from 'react-icons/fi';
import useClusters from '../../../hooks/useClusters';
import { optimizeAPI } from '../../../services/api';

// Real EE state progression — mirrors ExecutionEngine.STATE_LABELS
const EE_TIMELINE_STEPS = [
  'Idle',
  'Provisioning nodes',
  'Migrating stateful workloads',
  'Migrating batch workloads',
  'Draining vacated nodes',
  'Verifying placement',
  'Completed',
];
const EE_STEP_KEYS = ['IDLE', 'PROVISIONING', 'EXECUTING', 'EXECUTING_STATELESS', 'DRAINING', 'VERIFYING', 'COMPLETED'];
const EE_STEP_STYLE = {
  0: 'text-gray-400',
  1: 'text-blue-700',
  2: 'text-amber-700',
  3: 'text-amber-700',
  4: 'text-orange-700',
  5: 'text-indigo-700',
  6: 'text-green-700',
};

const STATE_STYLE = {
  STABLE:        'bg-green-50 text-green-700 border-green-200',
  AT_TARGET:     'bg-green-50 text-green-700 border-green-200',
  CONVERGING:    'bg-blue-50 text-blue-700 border-blue-200',
  DRIFTING:      'bg-amber-50 text-amber-700 border-amber-200',
  EVICTING:      'bg-red-50 text-red-700 border-red-200',
  DRIFT_DETECTED:'bg-amber-50 text-amber-700 border-amber-200',
  SCALING_UP:    'bg-blue-50 text-blue-700 border-blue-200',
  IN_PROGRESS:   'bg-blue-50 text-blue-700 border-blue-200',
  RECONCILING:   'bg-blue-50 text-blue-700 border-blue-200',
  PENDING:       'bg-gray-50 text-gray-400 border-gray-200',
  UNKNOWN:       'bg-gray-50 text-gray-500 border-gray-200',
};

function formatMem(bytes) {
  if (!bytes) return '—';
  if (bytes >= 1073741824) return `${(bytes / 1073741824).toFixed(1)}Gi`;
  if (bytes >= 1048576)    return `${Math.round(bytes / 1048576)}Mi`;
  if (bytes >= 1024)       return `${Math.round(bytes / 1024)}Ki`;
  return `${bytes}B`;
}

function formatAge(secs) {
  if (!secs) return '—';
  if (secs < 60)        return `${secs}s`;
  if (secs < 3600)      return `${Math.floor(secs / 60)}m`;
  if (secs < 86400)     return `${Math.floor(secs / 3600)}h`;
  if (secs < 86400 * 7) return `${Math.floor(secs / 86400)}d`;
  return `${Math.floor(secs / 86400 / 7)}w`;
}

function buildAzGroups(pods) {
  const groups = {};
  pods.forEach(p => {
    const az = p.az || 'unknown';
    if (!groups[az]) groups[az] = [];
    const ct = (p.capacity_type || '').toLowerCase();
    groups[az].push(ct === 'spot' ? 'blue' : ct === 'on_demand' || ct === 'on-demand' ? 'red' : 'gray');
  });
  return Object.entries(groups).map(([name, dots]) => ({ name, count: dots.length, dots }));
}

function buildExpectedAzGroups(podPlan) {
  const groups = {};
  podPlan.forEach(p => {
    const az = p.az || 'unknown';
    if (!groups[az]) groups[az] = [];
    const rec = p.recommendation;
    groups[az].push(rec === 'spot' ? 'blue' : rec === 'od' ? 'red' : 'gray');
  });
  return Object.entries(groups).map(([name, dots]) => ({ name, count: dots.length, dots }));
}

function buildReason(w) {
  if (w.engine_decision_reason) return w.engine_decision_reason;
  if (w.pdb_active) return 'Blocked — PDB active';
  if (w.placement_state === 'DRIFTING') return 'Drift detected — correcting placement';
  if (w.placement_state === 'EVICTING') return 'Eviction in progress';
  if ((w.spot_target || 0) > (w.spot_count || 0)) return 'Moving to spot — cost optimization';
  if ((w.od_excess  || 0) > 0) return 'Reducing OD — excess capacity';
  return 'Stable — no action needed';
}

function computeImpact(detail) {
  const moves  = detail?.placement_plan?.movement_plan?.length || 0;
  const drains = (detail?.placement_plan?.node_plan || []).filter(n => n.action === 'drain').length;
  if (drains > 0) return { label: 'High',   style: 'bg-red-50 border-red-200 text-red-700' };
  if (moves > 3)  return { label: 'Medium', style: 'bg-amber-50 border-amber-200 text-amber-700' };
  return               { label: 'Low',    style: 'bg-green-50 border-green-200 text-green-700' };
}

function lockSummary(locks) {
  if (!locks) return '—';
  const active = [];
  if (locks.pdb_active)                   active.push('PDB');
  if (locks.cooldown_active)              active.push('Cooldown');
  if ((locks.in_flight_actions || 0) > 0) active.push('In-flight');
  if (locks.keda_scaling_active)          active.push('KEDA');
  if (locks.rollout_blocked)              active.push('Rollout');
  return active.length ? `Blocked: ${active.join(', ')}` : 'Ready';
}

function mapRow(w) {
  const state      = w.placement_state || 'UNKNOWN';
  const odEx       = w.od_excess  != null ? Math.max(0, w.od_excess)  : null;
  const odReq      = w.od_required != null ? Math.max(0, w.od_required) : null;
  const spot       = w.spot_count  != null ? Math.max(0, w.spot_count)  : null;
  const spotTarget = w.spot_target != null ? Math.max(0, w.spot_target) : null;
  const total      = (odReq ?? 0) + (odEx ?? 0) + (spot ?? 0) || 1;
  const spotDrift  = (spot != null && spotTarget != null) ? spotTarget - spot : null;
  const wClass = w.workload_class || w.wie_role || null;
  const execStrat = w.execution_strategy || null;
  return {
    id:           w.workload_id,
    name:         w.workload_id ? w.workload_id.split('/').pop() : w.namespace,
    namespace:    w.namespace,
    od_excess:    odEx,
    od_required:  odReq,
    spot,
    spot_target:  spotTarget,
    spot_drift:   spotDrift,
    total,
    status:       state,
    statusStyle:  STATE_STYLE[state] || STATE_STYLE.UNKNOWN,
    pdb_active:      w.pdb_active || false,
    savings:         w.estimated_monthly_saving_usd || 0,
    timeline_step:   w.timeline_step ?? 0,
    reason:          buildReason(w),
    workloadClass:   wClass,
    executionStrategy: execStrat,
    is_db_workload:  wClass === 'db' || wClass === 'DB',
    min_od_replicas: w.min_on_demand_replicas ?? null,
    max_spot_replicas: w.max_spot_replicas ?? null,
  };
}

export default function WorkloadPlacement() {
  const { clusters, selectedId: clusterId, setSelectedId: setClusterId } = useClusters();
  const [workloads, setWorkloads] = useState([]);
  const [totalCount, setTotalCount] = useState(0);
  const [selected, setSelected] = useState(null);
  const [detail, setDetail] = useState(null);
  const [loading, setLoading] = useState(false);
  const [detailLoading, setDetailLoading] = useState(false);
  const [activeOps, setActiveOps] = useState([]);
  const [azRebalancing, setAzRebalancing] = useState(false);
  const [azRebalanceMsg, setAzRebalanceMsg] = useState(null);
  const [ppePaneTab, setPpePaneTab] = useState('summary');
  function handleRebalanceAz() {
    if (!w || !clusterId || azRebalancing) return;
    setAzRebalancing(true);
    setAzRebalanceMsg(null);
    optimizeAPI.triggerAzRebalance(w.id, clusterId)
      .then(() => setAzRebalanceMsg('AZ rebalance queued — PlacementController will evict from over-represented AZ.'))
      .catch(err => setAzRebalanceMsg(err?.response?.data?.detail || 'AZ rebalance failed.'))
      .finally(() => setAzRebalancing(false));
  }
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!clusterId) return;
    setLoading(true);
    setError(null);
    optimizeAPI.getWorkloadsPlacement(clusterId)
      .then(res => {
        const data = res.data;
        const mapped = (data.workloads || []).map(mapRow);
        setWorkloads(mapped);
        setTotalCount(data.total_count || mapped.length);
        if (mapped.length > 0) setSelected(mapped[0]);
      })
      .catch(err => setError(err?.response?.data?.detail || err?.message || 'Failed to load placement data'))
      .finally(() => setLoading(false));
  }, [clusterId]);

  useEffect(() => {
    if (!selected || !clusterId) return;
    setDetailLoading(true);
    setDetail(null);
    optimizeAPI.getWorkloadPlacementDetail(selected.id, clusterId)
      .then(res => setDetail(res.data))
      .catch(() => setDetail(null))
      .finally(() => setDetailLoading(false));
    optimizeAPI.getActiveRebalancing(selected.id, clusterId)
      .then(res => setActiveOps(res.data?.active_operations || []))
      .catch(() => setActiveOps([]));
  }, [selected?.id, clusterId]);

  const w = selected;

  const SectionBadge = ({ label, variant = 'gray' }) => {
    const cls = {
      gray:    'bg-gray-100 text-gray-500 border-gray-200',
      indigo:  'bg-indigo-50 text-indigo-600 border-indigo-200',
      emerald: 'bg-emerald-50 text-emerald-700 border-emerald-200',
      amber:   'bg-amber-50 text-amber-700 border-amber-200',
    }[variant] || 'bg-gray-100 text-gray-500 border-gray-200';
    return <span className={`text-xs font-bold px-2 py-0.5 rounded border tracking-wider uppercase ${cls}`}>{label}</span>;
  };

  const locks  = detail?.state_locks || {};
  const pods   = detail?.pods || [];
  const log    = detail?.recent_decisions || [];
  const policy             = detail?.policy              || {};
  const podPlan            = detail?.pod_plan            || [];
  const capacityPlan       = detail?.capacity_plan       || null;
  const topologyConstraints = detail?.topology_constraints || null;
  const placementPlan      = detail?.placement_plan      || null;
  const engineTargets      = detail?.engine_targets       || null;
  const azGroups = buildAzGroups(pods);
  const evictionPod = pods.find(p => p.phase === 'Terminating');

  const driftingCount = workloads.filter(r => r.status !== 'STABLE' && r.status !== 'UNKNOWN').length;
  const reconPct = totalCount > 0 ? Math.round(((totalCount - driftingCount) / totalCount) * 100) : 100;

  return (
    <div className="flex bg-gray-50 overflow-hidden" style={{ height: 'calc(100vh - 64px)' }}>

      {/* ── LEFT LIST ── */}
      <div className="w-[52%] flex flex-col border-r border-gray-200 bg-white overflow-hidden">

        {/* header */}
        <div className="px-5 pt-4 pb-3 border-b border-gray-100">
          <div className="flex items-center justify-between mb-3">
            <h1 className="text-base font-bold text-gray-900">Workload Placement</h1>
            <div>
              <label className="block text-xs font-medium text-gray-500 mb-0.5">Cluster</label>
              <select
                value={clusterId}
                onChange={e => { setSelected(null); setClusterId(e.target.value); }}
                className="text-xs border border-gray-300 rounded px-2 py-1 focus:outline-none focus:ring-1 focus:ring-indigo-500"
              >
                <option value="" disabled>Select cluster</option>
                {clusters.map(c => <option key={c.id} value={c.id}>{c.health_score ? `[${c.health_score}] ${c.name || c.id}` : (c.name || c.id)}</option>)}
              </select>
            </div>
          </div>
          <div className="grid grid-cols-3 gap-2 mb-3 text-center">
            {[
              { l: 'Total Tracked', v: loading ? '…' : totalCount,            c: 'text-gray-900' },
              { l: 'Drifting',      v: loading ? '…' : driftingCount,          c: 'text-red-600' },
              { l: 'Reconcile %',   v: loading ? '…' : `${reconPct}%`,         c: 'text-indigo-600' },
            ].map(s => (
              <div key={s.l} className="bg-gray-50 rounded-lg p-2 border border-gray-100">
                <div className="text-[10px] text-gray-400 uppercase tracking-wider">{s.l}</div>
                <div className={`text-sm font-bold ${s.c}`}>{s.v}</div>
              </div>
            ))}
          </div>
        </div>

        {error && <div className="mx-3 my-2 bg-red-50 border border-red-200 rounded-lg px-3 py-2 text-xs text-red-700">{error}</div>}

        {/* list */}
        <div className="flex-1 overflow-y-auto p-3 flex flex-col gap-2">
          {loading ? (
            <div className="text-center py-8 text-xs text-gray-500">Loading workloads...</div>
          ) : !clusterId ? (
            <div className="text-center py-8 text-xs text-gray-400">Select a cluster to view placement data.</div>
          ) : workloads.length === 0 ? (
            <div className="text-center py-8 text-xs text-gray-400">No placement data available.</div>
          ) : workloads.map(row => {
            const active   = row.id === w?.id;
            const hasData  = row.od_excess != null || row.od_required != null || row.spot != null;
            const odEx     = row.od_excess  ?? 0;
            const odReq    = row.od_required ?? 0;
            const spot     = row.spot        ?? 0;
            const barTotal = odEx + odReq + spot || 1;
            return (
              <div key={row.id} onClick={() => setSelected(row)}
                className={`rounded-xl border p-4 cursor-pointer transition-all relative overflow-hidden ${active ? 'border-indigo-300 bg-indigo-50 ring-1 ring-indigo-200 shadow' : 'border-gray-200 bg-white hover:bg-gray-50'}`}>
                {active && <div className="absolute left-0 top-0 bottom-0 w-1 bg-indigo-500 rounded-l-xl" />}
                <div className="pl-2">
                  <div className="flex items-start justify-between mb-1">
                    <div>
                      <div className="flex items-center gap-2 mb-0.5 flex-wrap">
                        <span className="font-mono font-bold text-sm text-gray-900">{row.name}</span>
                        <span className={`text-[10px] font-bold px-2 py-0.5 rounded-sm border ${row.statusStyle}`}>{row.status}</span>
                        {row.workloadClass && (
                          <span className={`text-[9px] font-bold px-1.5 py-0.5 rounded border uppercase ${
                            row.workloadClass === 'db' || row.workloadClass === 'DB' ? 'bg-red-50 text-red-700 border-red-200' :
                            row.workloadClass === 'stateful'   ? 'bg-amber-50 text-amber-700 border-amber-200' :
                            row.workloadClass === 'stateless'  ? 'bg-green-50 text-green-700 border-green-200' :
                            'bg-gray-100 text-gray-600 border-gray-200'
                          }`}>{row.workloadClass}</span>
                        )}
                        {row.executionStrategy && (
                          <span className="text-[9px] font-semibold px-1.5 py-0.5 rounded border bg-blue-50 text-blue-700 border-blue-200 uppercase">{row.executionStrategy}</span>
                        )}
                      </div>
                      <p className="text-xs text-gray-500">
                        ns: {row.namespace}
                        {row.od_excess > 0 && <span className="text-red-600 font-semibold"> | Δ OD: +{row.od_excess}</span>}
                        {row.spot_drift > 0 && <span className="text-amber-600 font-semibold"> | Spot behind: {row.spot}/{row.spot_target}</span>}
                        {row.spot_drift === 0 && row.spot_target != null && <span className="text-green-600"> | Spot: {row.spot}/{row.spot_target} ✓</span>}
                        {row.savings > 0 && <span className="text-green-600"> | ${Math.round(row.savings)}/mo</span>}
                      </p>
                      <p className="text-[11px] text-gray-400 mt-0.5">{row.reason}</p>
                    </div>
                  </div>
                  {/* Current distribution bar */}
                  <div className="w-full h-2 rounded-full bg-gray-100 flex overflow-hidden mt-2 mb-0.5">
                    {!hasData ? (
                      <div className="h-full w-full bg-gray-200" />
                    ) : (
                      <>
                        {odEx  > 0 && <div className="h-full bg-red-500"    style={{ flexGrow: odEx  }} />}
                        {odReq > 0 && <div className="h-full bg-gray-400"   style={{ flexGrow: odReq }} />}
                        {spot  > 0 && <div className="h-full bg-indigo-500" style={{ flexGrow: spot  }} />}
                        <div className="h-full bg-gray-100" style={{ flexGrow: Math.max(0, barTotal - odEx - odReq - spot) }} />
                      </>
                    )}
                  </div>
                  {/* Target distribution bar */}
                  {(row.min_od_replicas != null || row.max_spot_replicas != null) && (() => {
                    const tOD   = row.min_od_replicas ?? 0;
                    const tSpot = row.max_spot_replicas ?? 0;
                    const tTotal = tOD + tSpot || 1;
                    return (
                      <div className="w-full h-1.5 rounded-full bg-gray-50 border border-gray-100 flex overflow-hidden mt-0.5 mb-0.5">
                        {tOD   > 0 && <div className="h-full bg-orange-400"  style={{ flexGrow: tOD   }} title={`Target OD: ${tOD}`} />}
                        {tSpot > 0 && <div className="h-full bg-blue-400"    style={{ flexGrow: tSpot }} title={`Target Spot: ${tSpot}`} />}
                        <div className="h-full bg-gray-50" style={{ flexGrow: Math.max(0, tTotal - tOD - tSpot) }} />
                      </div>
                    );
                  })()}
                  <div className="text-[10px] text-gray-400">
                    OD: {row.od_required ?? '—'}/{row.total}
                    {row.spot_target != null && <> · Spot target: {row.spot_target}</>}
                    {row.min_od_replicas != null && <> · Target: {row.min_od_replicas} OD + {row.max_spot_replicas ?? 0} Spot</>}
                    {row.status === 'PENDING' && <span className="ml-1 text-gray-400">(awaiting classification)</span>}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* ── RIGHT DETAIL ── */}
      <div className="flex-1 overflow-y-auto bg-gray-50">
        {!w ? (
          <div className="flex items-center justify-center h-full text-sm text-gray-400">Select a workload to view details.</div>
        ) : (
          <div className="p-5 flex flex-col gap-5">

            {/* Header card */}
            <div className="bg-white rounded-xl border border-gray-200 p-4 flex items-start justify-between shadow-sm">
              <div>
                <div className="flex items-center gap-2 mb-1">
                  <span className="font-mono font-bold text-base text-gray-900">{w.name}</span>
                  <span className="text-xs text-gray-400">ns: {w.namespace}</span>
                  <span className={`text-[10px] font-bold px-2 py-0.5 rounded border ${w.statusStyle}`}>{w.status}</span>
                  {detail && (() => { const imp = computeImpact(detail); return <span className={`text-[10px] font-semibold px-2 py-0.5 rounded border ${imp.style}`}>Impact: {imp.label}</span>; })()}
                </div>
                <p className="text-xs text-gray-500">{w.reason}</p>
              </div>
              {evictionPod && (
                <span className="flex items-center gap-1 px-3 py-1.5 bg-red-50 border border-red-200 rounded-lg text-xs font-bold text-red-700">
                  <FiAlertCircle className="w-3.5 h-3.5" /> Disruption Path Active
                </span>
              )}
            </div>

            {/* Execution Progress — real EE state machine */}
            <div className="bg-white rounded-xl border border-gray-200 p-4 shadow-sm">
              <h4 className="text-xs font-bold uppercase tracking-wider text-gray-400 mb-3">Execution Progress</h4>
              {/* Step strip */}
              <div className="flex items-center gap-0.5 mb-3">
                {EE_TIMELINE_STEPS.map((label, idx) => {
                  const step = w.timeline_step ?? 0;
                  const done    = idx < step;
                  const current = idx === step;
                  return (
                    <React.Fragment key={label}>
                      <div className="flex flex-col items-center">
                        <div className={`w-5 h-5 rounded-full flex items-center justify-center text-[8px] font-bold border ${
                          done    ? 'bg-green-500 border-green-500 text-white' :
                          current ? 'bg-blue-600 border-blue-600 text-white' :
                                    'bg-white border-gray-300 text-gray-400'
                        }`}>
                          {done ? '✓' : current ? '●' : idx + 1}
                        </div>
                      </div>
                      {idx < EE_TIMELINE_STEPS.length - 1 && (
                        <div className={`flex-1 h-0.5 ${done ? 'bg-green-400' : 'bg-gray-200'}`} />
                      )}
                    </React.Fragment>
                  );
                })}
              </div>
              <div className="flex gap-8 text-xs">
                <div>
                  <span className="text-[10px] font-bold text-gray-400 uppercase tracking-wider block mb-0.5">Now</span>
                  <span className={`font-semibold ${EE_STEP_STYLE[w.timeline_step ?? 0] || 'text-gray-800'}`}>
                    {EE_TIMELINE_STEPS[w.timeline_step ?? 0] || 'Unknown'}
                  </span>
                </div>
                <div>
                  <span className="text-[10px] font-bold text-gray-400 uppercase tracking-wider block mb-0.5">Next</span>
                  <span className="text-gray-500">{EE_TIMELINE_STEPS[(w.timeline_step ?? 0) + 1] || '—'}</span>
                </div>
                {w.savings > 0 && (
                  <div className="ml-auto text-right">
                    <span className="text-[10px] font-bold text-gray-400 uppercase tracking-wider block mb-0.5">Savings</span>
                    <span className="font-semibold text-green-600">${Math.round(w.savings)}/mo</span>
                  </div>
                )}
              </div>
            </div>

            {/* Eviction Risk */}
            {evictionPod && (
              <div className="bg-red-50 border border-red-200 rounded-xl p-4">
                <div className="flex items-center gap-2 mb-2">
                  <FiAlertCircle className="w-4 h-4 text-red-600" />
                  <h4 className="text-xs font-bold uppercase tracking-wider text-red-700">Eviction Risk Signal</h4>
                </div>
                <div className="flex justify-between items-center text-xs bg-white border border-red-100 rounded-lg px-3 py-2">
                  <code className="font-mono text-gray-700">{evictionPod.name}</code>
                  <span className="text-red-600 font-medium">Pod Terminating</span>
                  <span className="text-indigo-600 font-medium">Replacement Pending</span>
                </div>
              </div>
            )}

            {/* AZ Topology — derived from detail pods */}
            <div className="bg-white rounded-xl border border-gray-200 p-4 shadow-sm">
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2">
                  <h4 className="text-xs font-bold uppercase tracking-wider text-gray-400">Topology Balance</h4>
                  <SectionBadge label="Current State" variant="gray" />
                </div>
                <button
                  onClick={handleRebalanceAz}
                  disabled={!w || azRebalancing}
                  title={azRebalancing ? 'Queuing…' : 'Trigger AZ-balance pass for this workload'}
                  className={`px-2 py-1 text-xs border rounded-lg transition-colors ${
                    azRebalancing
                      ? 'bg-indigo-100 border-indigo-200 text-indigo-500 cursor-wait'
                      : 'bg-indigo-50 border-indigo-200 text-indigo-700 hover:bg-indigo-100'
                  }`}
                >{azRebalancing ? 'Queuing…' : 'Rebalance AZ'}</button>
              </div>
              {azRebalanceMsg && (
                <div className="text-xs text-indigo-700 bg-indigo-50 border border-indigo-100 rounded px-2 py-1 mb-2">{azRebalanceMsg}</div>
              )}
              {detailLoading ? (
                <div className="text-xs text-gray-400 text-center py-4">Loading topology...</div>
              ) : azGroups.length > 0 ? (
                <div className="grid grid-cols-3 gap-3">
                  {azGroups.map(az => {
                    const isUnknownAz = az.name === 'unknown';
                    return (
                    <div key={az.name} className={`border rounded-lg p-3 ${isUnknownAz ? 'bg-amber-50 border-amber-200' : 'bg-gray-50 border-gray-100'}`}>
                      <div className={`flex justify-between text-xs font-mono font-semibold mb-2 ${isUnknownAz ? 'text-amber-700' : 'text-gray-700'}`}>
                        <span title={isUnknownAz ? 'NodeMetadata not yet populated for these pods' : az.name}>
                          {isUnknownAz ? '⚠ No AZ data' : az.name}
                        </span>
                        <span>({az.count})</span>
                      </div>
                      <div className="flex flex-wrap justify-center gap-1">
                        {az.dots.map((d, i) => (
                          <div key={i} className={`w-3 h-3 rounded-full ${d === 'blue' ? 'bg-indigo-500' : d === 'red' ? 'bg-red-500' : 'bg-gray-300'}`} />
                        ))}
                      </div>
                      {isUnknownAz && <p className="text-[9px] text-amber-600 mt-1 text-center">Node metadata pending</p>}
                    </div>
                    );
                  })}
                </div>
              ) : (
                <div className="text-xs text-gray-400 italic text-center py-3">No pod topology data available.</div>
              )}
            </div>

            {/* Pod Table — live from placement-detail */}
            <div className="bg-white rounded-xl border border-gray-200 overflow-hidden shadow-sm">
              <div className="px-4 py-2.5 bg-gray-50 border-b border-gray-100 flex items-center gap-2">
                <h4 className="text-xs font-bold uppercase tracking-wider text-gray-400">Ground Truth</h4>
                <SectionBadge label="Current State" variant="gray" />
              </div>
              {detailLoading ? (
                <div className="text-xs text-gray-400 text-center py-6">Loading pod data...</div>
              ) : (
                <table className="min-w-full text-xs font-mono">
                  <thead>
                    <tr className="border-b border-gray-100 bg-gray-50">
                      {['Pod Name', 'Node Type', 'AZ', 'Status', 'Age'].map(h => (
                        <th key={h} className="px-3 py-2 text-left text-[10px] font-semibold uppercase text-gray-400">{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-50">
                    {pods.length === 0 ? (
                      <tr><td colSpan={5} className="px-3 py-4 text-center text-gray-400 text-xs">No pod data available.</td></tr>
                    ) : pods.slice(0, 12).map((p, i) => {
                      const ct = (p.capacity_type || '').toLowerCase();
                      const isSpot = ct === 'spot';
                      const isOD   = ct === 'on_demand' || ct === 'on-demand' || ct === 'ondemand';
                      const isRunning = p.phase === 'Running';
                      return (
                        <tr key={i} className="hover:bg-gray-50 transition-colors">
                          <td className="px-3 py-2 text-gray-700 truncate max-w-[140px]" title={p.pod_name || p.name}>{p.pod_name || p.name}</td>
                          <td className="px-3 py-2">
                            {isSpot ? (
                              <span className="text-indigo-600 font-semibold">Spot</span>
                            ) : isOD ? (
                              <span className="text-red-600 font-semibold">On-Demand</span>
                            ) : (
                              <span className="text-gray-400 italic">Unknown</span>
                            )}
                          </td>
                          <td className="px-3 py-2 text-gray-500">{p.az || '—'}</td>
                          <td className={`px-3 py-2 font-medium ${isRunning ? 'text-green-600' : 'text-amber-600'}`}>{p.phase || '—'}</td>
                          <td className="px-3 py-2 text-gray-400">{formatAge(p.age_seconds)}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              )}
            </div>

            {/* ── Pod Placement Engine Plan header placeholder (Expected block removed) ── */}
            {false && (() => {
              const odTarget   = null;
              const hasPolicy  = false;
              return (
                <div className="hidden">
                  <div className="hidden">
                    <div className="flex items-center gap-2 text-[10px] flex-wrap">
                      {/* WIE classification badge */}
                      {capacityPlan?.wie_role && (
                        <span className={`rounded px-2 py-1 font-semibold border ${capacityPlan.wie_spot_friendly ? 'bg-green-50 border-green-200 text-green-700' : 'bg-red-50 border-red-200 text-red-600'}`}>
                          WIE: {capacityPlan.wie_role}{capacityPlan.wie_spot_friendly ? ' ✓ Spot OK' : ' ✗ OD Only'}
                        </span>
                      )}
                      {/* Simulated hint when no real policy */}
                      {capacityPlan?.wie_simulated && !hasPolicy && (
                        <span className="bg-amber-50 border border-amber-200 text-amber-700 rounded px-2 py-1 font-semibold">Simulated</span>
                      )}
                      {/* Real policy pills */}
                      {hasPolicy ? (
                        <>
                          <span className="bg-red-50 border border-red-100 rounded px-2 py-1 text-red-700 font-semibold">{odTarget} OD</span>
                          <span className="text-gray-300">+</span>
                          <span className="bg-indigo-50 border border-indigo-100 rounded px-2 py-1 text-indigo-700 font-semibold">{spotTarget} Spot</span>
                          <span className="text-gray-400">= {(odTarget ?? 0) + (spotTarget ?? 0)} total</span>
                        </>
                      ) : null}
                    </div>
                  </div>

                  <div className="p-4">
                    {!hasPodData ? (
                      <p className="text-xs text-gray-400 italic text-center py-3">No pod data — agent not yet reporting for this workload.</p>
                    ) : (
                      <>
                        {/* ── Expected Topology Balance (mirrors current Topology Balance) ── */}
                        <div className="mb-4">
                          <div className="flex items-center justify-between mb-2">
                            <h4 className="text-xs font-bold uppercase tracking-wider text-gray-400">Expected Topology Balance</h4>
                            {topologyConstraints && (
                              <div className="flex gap-1.5">
                                {[
                                  { label: 'Min 2 Nodes', ok: topologyConstraints.min_nodes_ok },
                                  { label: 'AZ Spread',   ok: topologyConstraints.az_spread_ok },
                                  { label: 'Anti-Affinity', ok: topologyConstraints.anti_affinity_ok },
                                ].map(c => (
                                  <span key={c.label} className={`text-[9px] px-1.5 py-0.5 rounded font-semibold border ${c.ok ? 'bg-green-50 border-green-200 text-green-700' : 'bg-red-50 border-red-200 text-red-700'}`}>
                                    {c.ok ? '✓' : '✗'} {c.label}
                                  </span>
                                ))}
                              </div>
                            )}
                          </div>
                          <div className="grid grid-cols-3 gap-3">
                            {expPodAzGroups.map(az => {
                              const isUnknownAz = az.name === 'unknown';
                              return (
                                <div key={az.name} className={`border rounded-lg p-3 ${isUnknownAz ? 'bg-amber-50 border-amber-200' : 'bg-gray-50 border-gray-100'}`}>
                                  <div className={`flex justify-between text-xs font-mono font-semibold mb-2 ${isUnknownAz ? 'text-amber-700' : 'text-gray-700'}`}>
                                    <span title={az.name}>{isUnknownAz ? '⚠ No AZ data' : az.name}</span>
                                    <span>({az.count})</span>
                                  </div>
                                  <div className="flex flex-wrap justify-center gap-1">
                                    {az.dots.map((d, i) => (
                                      <div key={i} className={`w-3 h-3 rounded-full ${d === 'blue' ? 'bg-indigo-500' : d === 'red' ? 'bg-red-500' : 'bg-gray-300'}`} />
                                    ))}
                                  </div>
                                  {isUnknownAz && <p className="text-[9px] text-amber-600 mt-1 text-center">Node metadata pending</p>}
                                </div>
                              );
                            })}
                          </div>
                          {/* Capacity row below topology */}
                          {capacityPlan && (
                            <div className="flex gap-2 mt-2 text-[10px] flex-wrap">
                              <div className="flex items-center gap-1 bg-red-50 border border-red-100 rounded px-2 py-1">
                                <span className="text-red-600 font-semibold">{capacityPlan.od_pod_count} OD</span>
                                <span className="text-gray-300">·</span>
                                <span className="text-red-500">{capacityPlan.total_cpu_od_millicores}m</span>
                                <span className="text-gray-300">·</span>
                                <span className="text-red-500">{formatMem(capacityPlan.total_memory_od_bytes)}</span>
                              </div>
                              <div className="flex items-center gap-1 bg-indigo-50 border border-indigo-100 rounded px-2 py-1">
                                <span className="text-indigo-600 font-semibold">{capacityPlan.spot_pod_count} Spot</span>
                                <span className="text-gray-300">·</span>
                                <span className="text-indigo-500">{capacityPlan.total_cpu_spot_millicores}m</span>
                                <span className="text-gray-300">·</span>
                                <span className="text-indigo-500">{formatMem(capacityPlan.total_memory_spot_bytes)}</span>
                              </div>
                              {capacityPlan.skipped_pod_count > 0 && (
                                <div className="flex items-center gap-1 bg-gray-50 border border-gray-200 rounded px-2 py-1 text-gray-400">
                                  <span>⊘ {capacityPlan.skipped_pod_count} sys/DS excluded</span>
                                </div>
                              )}
                            </div>
                          )}
                        </div>

                        {/* ── Expected Ground Truth (mirrors current Ground Truth table) ── */}
                        <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
                          <div className="px-4 py-2 bg-gray-50 border-b border-gray-100">
                            <h4 className="text-xs font-bold uppercase tracking-wider text-gray-400">Expected Ground Truth</h4>
                          </div>
                          <table className="min-w-full text-xs font-mono">
                            <thead>
                              <tr className="border-b border-gray-100 bg-gray-50">
                                {['Pod Name', 'Recommended', 'AZ', 'Score', 'Reason'].map(h => (
                                  <th key={h} className="px-3 py-2 text-left text-[10px] font-semibold uppercase text-gray-400">{h}</th>
                                ))}
                              </tr>
                            </thead>
                            <tbody className="divide-y divide-gray-50">
                              {podPlan.slice(0, 12).map((p, i) => {
                                const isSpot = p.recommendation === 'spot';
                                const isOd   = p.recommendation === 'od';
                                return (
                                  <tr key={i} className="hover:bg-gray-50 transition-colors">
                                    <td className="px-3 py-2 text-gray-700 truncate max-w-[140px]" title={p.pod_name || p.name}>{p.pod_name || p.name}</td>
                                    <td className="px-3 py-2">
                                      {isSpot ? (
                                        <span className="text-indigo-600 font-semibold">Spot</span>
                                      ) : isOd ? (
                                        <span className="text-red-600 font-semibold">On-Demand</span>
                                      ) : (
                                        <span className="text-gray-400 italic">Skip</span>
                                      )}
                                    </td>
                                    <td className="px-3 py-2 text-gray-500">{p.az || '—'}</td>
                                    <td className="px-3 py-2">
                                      <span className={`font-bold ${(p.spot_score ?? 0) >= 6 ? 'text-green-600' : (p.spot_score ?? 0) <= 3 ? 'text-red-500' : 'text-amber-600'}`}>{p.spot_score ?? '—'}</span>
                                    </td>
                                    <td className="px-3 py-2 text-gray-400 truncate max-w-[120px]" title={p.reason}>{p.reason || '—'}</td>
                                  </tr>
                                );
                              })}
                            </tbody>
                          </table>
                        </div>
                      </>
                    )}
                  </div>
                </div>
              );
            })()}

            {/* ── Pod Placement Engine Plan ── */}
            {placementPlan && (() => {
              const fz = placementPlan.feasibility || {};
              const moves = placementPlan.movement_plan || [];
              const nodes = placementPlan.node_plan || [];
              const azDist = placementPlan.az_distribution || {};
              const feasibilityOk = fz.feasible !== false;
              const planStatus = fz.status || '';
              const isNoop = planStatus === 'no_pods_observed' || planStatus === 'no_node_data' || planStatus === 'already_optimal';
              const movesTotal = fz.moves_total ?? moves.length;
              const warnings = fz.warnings || [];
              const provNodes  = nodes.filter(n => n.action === 'provision');
              const drainNodes = nodes.filter(n => n.action === 'drain');
              const keepNodes  = nodes.filter(n => n.action === 'keep');
              const reuseNodes = keepNodes.filter(n => n.retention_reason === 'drain_reuse');
              // Anchor node computation
              const _anchorNameSet = new Set(placementPlan.anchor_plan?.anchor_nodes || []);
              const _isAnchorEntry = (n) => n.retention_reason === 'anchor_node' || _anchorNameSet.has(n.node_name);
              const _isOd = (n) => (n.capacity_type || '').toLowerCase() !== 'spot';

              const trueAnchorNodes      = keepNodes.filter(n => _isAnchorEntry(n) && _isOd(n));
              const provisionAnchorNodes = provNodes.filter(n => _isAnchorEntry(n) && _isOd(n));
              const _hasExplicitAnchor   = trueAnchorNodes.length > 0 || provisionAnchorNodes.length > 0;

              const azKeys = Object.keys(azDist).sort();
              const nodeLayout    = placementPlan.node_layout || {};
              const layoutByAz    = nodeLayout.by_az || {};
              const allLayoutNodes = Object.values(layoutByAz).flatMap(azd => azd.nodes || []);
              const _getLayoutNode = (name) => allLayoutNodes.find(n => n.node_name === name);
              const _isDsOnlyNode = (kn) => {
                const ln = _getLayoutNode(kn.node_name);
                if (!ln) return false;
                const allPods = ln.existing_pods || [];
                const wlPods  = allPods.filter(p => !p.is_daemonset && p.pod_kind !== 'DaemonSet' && p.owner_kind !== 'DaemonSet');
                return wlPods.length === 0 && allPods.length > 0;
              };
              const dsManagedWorkload = keepNodes.length > 0 && keepNodes.every(_isDsOnlyNode) && provNodes.length === 0 && moves.length === 0;

              // Implicit anchor: first OD keep node if no explicit anchor set
              const implicitAnchorNode = (!dsManagedWorkload && !_hasExplicitAnchor)
                ? keepNodes.find(n => _isOd(n) && !_isAnchorEntry(n) && n.retention_reason !== 'drain_reuse')
                : null;

              const displayAnchorNodes = [
                ...trueAnchorNodes.map(n => ({ ...n, _isNew: false, _isImplicit: false })),
                ...provisionAnchorNodes.map(n => ({ ...n, _isNew: true, _isImplicit: false })),
                ...(implicitAnchorNode ? [{ ...implicitAnchorNode, _isNew: false, _isImplicit: true }] : []),
              ];
              const _anchorDisplayNames = new Set(displayAnchorNodes.map(n => n.node_name));

              const activeKeepNodes = keepNodes.filter(n =>
                n.retention_reason !== 'drain_reuse' && !_anchorDisplayNames.has(n.node_name)
              );
              const drainLayout   = nodeLayout.drain_candidates || [];
              const provLayout    = nodeLayout.provision_required || [];
              const hasNodeLayout = Object.keys(layoutByAz).length > 0 || drainLayout.length > 0 || provLayout.length > 0;
              return (
                <div className="bg-white rounded-xl border border-emerald-200 shadow-sm overflow-hidden">
                  <div className="px-4 py-2.5 bg-gradient-to-r from-emerald-50 to-white border-b border-emerald-100 flex items-center justify-between flex-wrap gap-2">
                    <div>
                      <div className="flex items-center gap-2">
                        <h4 className="text-xs font-bold uppercase tracking-wider text-emerald-700">Pod Placement Engine Plan</h4>
                        <SectionBadge label="Final Plan (PPE)" variant="emerald" />
                      </div>
                      <p className="text-[10px] text-emerald-400 mt-0.5">Materialised plan: pod selection → AZ distribution → capacity → bin packing</p>
                    </div>
                    <div className="flex items-center gap-2 text-[10px] flex-wrap">
                      <span className={`px-2 py-1 rounded font-semibold border ${
                        isNoop ? 'bg-slate-50 border-slate-200 text-slate-500'
                        : feasibilityOk ? 'bg-green-50 border-green-200 text-green-700'
                        : 'bg-red-50 border-red-200 text-red-700'
                      }`}>
                        {planStatus === 'already_optimal' && '✓ Already Optimal'}
                        {planStatus === 'no_pods_observed' && '— No Pods'}
                        {planStatus === 'no_node_data' && '— No Node Data'}
                        {planStatus === 'plan_generated' && '✓ Feasible'}
                        {planStatus === 'infeasible' && '✗ Infeasible'}
                        {!planStatus && (feasibilityOk ? '✓ Feasible' : '✗ Infeasible')}
                      </span>
                      <span className="px-2 py-1 rounded font-semibold border bg-gray-50 border-gray-200 text-gray-600">
                        {movesTotal} move{movesTotal !== 1 ? 's' : ''}
                      </span>
                      <span className="px-2 py-1 rounded font-semibold border bg-emerald-50 border-emerald-200 text-emerald-700">
                        keep {keepNodes.length}
                      </span>
                      <span className="px-2 py-1 rounded font-semibold border bg-teal-50 border-teal-200 text-teal-700">
                        provision {provNodes.length}
                      </span>
                      <span className="px-2 py-1 rounded font-semibold border bg-amber-50 border-amber-200 text-amber-700">
                        drain {drainNodes.length}
                      </span>
                    </div>
                  </div>

                  {/* Tab strip */}
                  <div className="flex border-b border-gray-100 bg-gray-50 px-4">
                    {[
                      { key: 'summary',   label: 'Summary' },
                      { key: 'movements', label: `Movements${moves.length ? ` (${moves.length})` : ''}` },
                      { key: 'nodes',     label: `Nodes${nodes.length ? ` (${nodes.length})` : ''}` },
                      { key: 'layout',    label: 'Layout' },
                    ].map(t => (
                      <button key={t.key} onClick={() => setPpePaneTab(t.key)}
                        className={`px-4 py-2 text-xs font-semibold border-b-2 transition-colors ${
                          ppePaneTab === t.key
                            ? 'border-emerald-600 text-emerald-700'
                            : 'border-transparent text-gray-400 hover:text-gray-600'
                        }`}>
                        {t.label}
                      </button>
                    ))}
                  </div>

                  <div className="p-4 space-y-4">
                    {/* No-op banner — always visible */}
                    {isNoop && (
                      <div className="bg-slate-50 border border-slate-200 rounded px-3 py-2.5 text-xs text-slate-600 flex items-start gap-2">
                        <div>
                          <div className="font-semibold">
                            {planStatus === 'already_optimal' && 'Placement already optimal — no movements required.'}
                            {planStatus === 'no_pods_observed' && 'No pod data available — plan cannot be generated.'}
                            {planStatus === 'no_node_data'    && 'No node data available — plan cannot be generated.'}
                          </div>
                          <div className="text-slate-400 mt-0.5">The engine performed no actions. Nothing will be moved or reprovisioned.</div>
                        </div>
                      </div>
                    )}
                    {/* Summary tab — full Plan Overview */}
                    {ppePaneTab === 'summary' && nodes.length > 0 && (
                      <div className="space-y-4">
                        {/* ── 0. Engine Target Decision (not shown for DaemonSet workloads) ── */}
                        {engineTargets && !dsManagedWorkload && (() => {
                          const basisLabel = {
                            policy:               'From Policy',
                            wie_score_high:       'WIE Score High',
                            wie_score_moderate:   'WIE Score Moderate',
                            wie_not_spot_friendly:'Not Spot-Friendly',
                            unknown:              'Unknown',
                          }[engineTargets.basis] || engineTargets.basis;
                          const basisStyle = {
                            policy:               'bg-blue-50 border-blue-200 text-blue-700',
                            wie_score_high:       'bg-indigo-50 border-indigo-200 text-indigo-700',
                            wie_score_moderate:   'bg-teal-50 border-teal-200 text-teal-700',
                            wie_not_spot_friendly:'bg-red-50 border-red-200 text-red-700',
                            unknown:              'bg-gray-50 border-gray-200 text-gray-500',
                          }[engineTargets.basis] || 'bg-gray-50 border-gray-200 text-gray-500';
                          return (
                            <div className="flex items-center gap-2 flex-wrap text-[10px] px-1">
                              <span className="font-bold uppercase tracking-wider text-gray-400">Engine Decision</span>
                              <span className="px-2 py-0.5 rounded border bg-indigo-50 border-indigo-200 text-indigo-700 font-semibold">
                                Spot target: {engineTargets.spot_target}
                              </span>
                              <span className="px-2 py-0.5 rounded border bg-red-50 border-red-200 text-red-700 font-semibold">
                                OD required: {engineTargets.od_target}
                              </span>
                              <span className="text-gray-300">·</span>
                              <span className={`px-2 py-0.5 rounded border font-semibold ${basisStyle}`}>{basisLabel}</span>
                              {engineTargets.wie_spot_score > 0 && (
                                <span className="px-2 py-0.5 rounded border bg-gray-50 border-gray-200 text-gray-500">
                                  WIE score: {engineTargets.wie_spot_score}/10
                                </span>
                              )}
                              <span className="text-gray-400">{engineTargets.total_pods} total pods</span>
                            </div>
                          );
                        })()}

                        {/* ── 1. Future State Resource Overview ── */}
                        {dsManagedWorkload ? (
                          <div>
                            <div className="text-[10px] font-bold uppercase tracking-wider text-blue-500 mb-2">Current Distribution</div>
                            <div className="bg-blue-50 border border-blue-200 rounded-lg px-4 py-3">
                              <div className="flex items-start gap-3">
                                <div className="text-2xl">&#9654;</div>
                                <div>
                                  <div className="text-xs font-semibold text-blue-800 mb-0.5">
                                    Present on every node — {keepNodes.length} node{keepNodes.length !== 1 ? 's' : ''} currently in cluster
                                  </div>
                                  <p className="text-[10px] text-blue-600">
                                    DaemonSet pods run automatically on <strong>every node</strong> in the cluster, regardless of capacity type (OD or Spot).
                                    When new Spot nodes are provisioned, this DaemonSet will auto-schedule on those too.
                                    No OD / Spot split applies here — Kubernetes schedules it on all nodes.
                                  </p>
                                  <div className="flex flex-wrap gap-2 mt-2">
                                    {keepNodes.map((kn, ki) => {
                                      const isSpot = (kn.capacity_type || '').toLowerCase() === 'spot';
                                      return (
                                        <span key={ki} className={`text-[9px] font-mono px-2 py-0.5 rounded border font-semibold ${
                                          isSpot ? 'bg-indigo-50 border-indigo-200 text-indigo-700' : 'bg-orange-50 border-orange-200 text-orange-700'
                                        }`}>
                                          {kn.node_name?.split('.')[0] || '—'}
                                          <span className="ml-1 opacity-60">{isSpot ? 'Spot' : 'OD'}</span>
                                        </span>
                                      );
                                    })}
                                  </div>
                                </div>
                              </div>
                            </div>
                          </div>
                        ) : (() => {
                          const futureNodes = [...keepNodes, ...provNodes];
                          const totalFuturePods = futureNodes.reduce((s, n) => s + (n.pod_count || 0), 0);
                          const totalCpuM = futureNodes.reduce((s, n) => s + (n.required_cpu_millicores || 0), 0);
                          const totalMemB = futureNodes.reduce((s, n) => s + (n.required_memory_bytes || 0), 0);
                          const spotCount = futureNodes.filter(n => (n.capacity_type || '').toLowerCase() === 'spot').length;
                          const odCount   = futureNodes.length - spotCount;
                          return (
                            <div>
                              <div className="text-[10px] font-bold uppercase tracking-wider text-gray-400 mb-2">Future State Overview</div>
                              <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
                                <div className="rounded-lg border p-3 bg-gray-50 border-gray-200">
                                  <div className="text-xl font-bold text-gray-800">{futureNodes.length}</div>
                                  <div className="text-[10px] font-semibold uppercase text-gray-500">Nodes Needed</div>
                                  <div className="text-[10px] text-gray-400 mt-0.5">
                                    <span className="text-red-500 font-semibold">{odCount} OD</span>{' · '}
                                    <span className="text-indigo-500 font-semibold">{spotCount} Spot</span>
                                  </div>
                                </div>
                                <div className="rounded-lg border p-3 bg-indigo-50 border-indigo-200">
                                  <div className="text-xl font-bold text-indigo-700">{totalFuturePods}</div>
                                  <div className="text-[10px] font-semibold uppercase text-indigo-600">Pods Placed</div>
                                  <div className="text-[10px] text-gray-400 mt-0.5">
                                    {movesTotal > 0 ? `${movesTotal} moving · ${totalFuturePods - movesTotal} staying` : 'all staying put'}
                                  </div>
                                </div>
                                <div className="rounded-lg border p-3 bg-emerald-50 border-emerald-200">
                                  <div className="text-xl font-bold text-emerald-700">{Math.round(totalCpuM)}</div>
                                  <div className="text-[10px] font-semibold uppercase text-emerald-600">CPU (millicores)</div>
                                  <div className="text-[10px] text-gray-400 mt-0.5">total requested</div>
                                </div>
                                <div className="rounded-lg border p-3 bg-purple-50 border-purple-200">
                                  <div className="text-xl font-bold text-purple-700">{formatMem(totalMemB)}</div>
                                  <div className="text-[10px] font-semibold uppercase text-purple-600">Memory</div>
                                  <div className="text-[10px] text-gray-400 mt-0.5">total requested</div>
                                </div>
                              </div>
                            </div>
                          );
                        })()}

                        {/* ── 2. Node Replacement Map (only when drains exist) ── */}
                        {drainNodes.length > 0 && (() => {
                          const replacements = drainNodes.map(dn => {
                            const drainMoves = moves.filter(m => m.from_node === dn.node_name);
                            const destNodeNames = [...new Set(drainMoves.map(m => m.to_node))];
                            const destNodes = destNodeNames.map(toNode => {
                              const nm = [...keepNodes, ...provNodes].find(n => n.node_name === toNode);
                              return {
                                node_name: toNode,
                                capacity_type: nm?.capacity_type || 'spot',
                                az: nm?.az || '?',
                                instance_type: nm?.instance_type || '?',
                                pods: drainMoves.filter(m => m.to_node === toNode),
                              };
                            });
                            return { drain: dn, destNodes, totalMoved: drainMoves.length };
                          });
                          return (
                            <div>
                              <div className="text-[10px] font-bold uppercase tracking-wider text-gray-400 mb-2">
                                Node Replacements — {drainNodes.length} OD node{drainNodes.length !== 1 ? 's' : ''} drained
                              </div>
                              <div className="space-y-2">
                                {replacements.map((r, ri) => (
                                  <div key={ri} className="border border-gray-200 rounded-lg overflow-hidden font-mono">
                                    <div className="flex items-center gap-2 px-3 py-2 bg-amber-50 border-b border-amber-100">
                                      <span className="text-[9px] font-bold px-1.5 py-0.5 bg-amber-200 text-amber-800 rounded uppercase shrink-0">drain</span>
                                      <code className="text-[10px] text-gray-700 truncate flex-1" title={r.drain.node_name}>{r.drain.node_name.split('.')[0]}</code>
                                      <span className="text-[9px] text-red-600 font-semibold shrink-0">{r.drain.instance_type}</span>
                                      <span className="text-[9px] text-gray-400 shrink-0">{r.drain.az}</span>
                                      <span className="text-[9px] text-amber-700 font-semibold shrink-0">{r.totalMoved} pod{r.totalMoved !== 1 ? 's' : ''} evacuated</span>
                                    </div>
                                    {r.destNodes.length === 0 ? (
                                      <div className="px-4 py-2 bg-white text-gray-400 text-[9px] italic">Pods absorbed into existing spot nodes</div>
                                    ) : r.destNodes.map((dest, di) => (
                                      <div key={di} className="flex items-start gap-2 px-3 py-2 bg-white border-b border-gray-50 last:border-b-0">
                                        <span className="text-gray-300 mt-0.5 shrink-0">↳</span>
                                        <span className="text-[9px] font-bold px-1.5 py-0.5 bg-indigo-100 text-indigo-700 rounded uppercase shrink-0">spot</span>
                                        <div className="flex-1 min-w-0">
                                          <div className="flex items-center gap-2 flex-wrap">
                                            <code className="text-[10px] text-gray-700" title={dest.node_name}>{dest.node_name.split('.')[0]}</code>
                                            <span className="text-[9px] text-indigo-600 font-semibold">{dest.instance_type}</span>
                                            <span className="text-[9px] text-gray-400">{dest.az}</span>
                                          </div>
                                          <div className="flex flex-wrap gap-1 mt-1">
                                            {dest.pods.map((pm, pi) => (
                                              <span key={pi} className="text-[9px] px-1.5 py-0.5 bg-indigo-50 border border-indigo-100 rounded text-indigo-700">
                                                {pm.pod_name}
                                              </span>
                                            ))}
                                          </div>
                                        </div>
                                        <span className="text-[9px] text-indigo-700 font-semibold shrink-0">{dest.pods.length} in</span>
                                      </div>
                                    ))}
                                  </div>
                                ))}
                              </div>
                            </div>
                          );
                        })()}

                        {/* ── 2b. New Nodes — to be provisioned ── */}
                        {provNodes.length > 0 && (
                          <div>
                            <div className="text-[10px] font-bold uppercase tracking-wider text-teal-600 mb-1">
                              + New Nodes ({provNodes.length}) — will be provisioned
                            </div>
                            <p className="text-[10px] text-gray-400 italic mb-2">
                              These nodes do not exist yet. The engine will provision them to receive pods
                              that need to move. Instance type is resolved by the Instance Selection Service (ISS).
                            </p>
                            <div className="space-y-1.5">
                              {provNodes.map((pn, pi) => {
                                const isSpot = (pn.capacity_type || '').toLowerCase() === 'spot';
                                const packedPods = pn.packed_pods || [];
                                return (
                                  <div key={pi} className="border border-teal-200 rounded-lg overflow-hidden">
                                    <div className="flex items-center gap-2 px-3 py-2 bg-teal-50">
                                      <span className="text-[9px] font-bold px-1.5 py-0.5 bg-teal-200 text-teal-800 rounded uppercase shrink-0">new</span>
                                      <span className="text-[9px] font-bold px-1.5 py-0.5 bg-teal-100 text-teal-700 rounded uppercase shrink-0">provision</span>
                                      <code className="text-[10px] font-mono text-gray-500 truncate flex-1 italic" title={pn.node_name}>
                                        {pn.node_name || `new-${pn.capacity_type}-${pn.az}-${pi + 1}`}
                                      </code>
                                      <span className={`text-[9px] font-semibold shrink-0 ${isSpot ? 'text-indigo-600' : 'text-orange-700'}`}>
                                        {isSpot ? 'Spot' : 'OD'}
                                      </span>
                                      <span className="text-[9px] text-gray-500 shrink-0">
                                        {pn.instance_type || <span className="italic text-amber-600">ISS pending</span>}
                                      </span>
                                      <span className="text-[9px] text-gray-400 shrink-0">{pn.az}</span>
                                      <span className="text-[9px] font-semibold text-gray-600 shrink-0">
                                        {Math.round(pn.required_cpu_millicores || 0)}m · {formatMem(pn.required_memory_bytes || 0)}
                                      </span>
                                      <span className="text-[9px] font-semibold text-teal-700 shrink-0">
                                        {pn.pod_count || packedPods.length} pod{(pn.pod_count || packedPods.length) !== 1 ? 's' : ''}
                                      </span>
                                    </div>
                                    {packedPods.length > 0 && (
                                      <div className="px-3 py-1.5 bg-white flex flex-wrap gap-x-3 gap-y-0.5">
                                        {packedPods.slice(0, 8).map((p, ppi) => (
                                          <span key={ppi} className="flex items-center gap-1 text-[9px] font-mono text-teal-700">
                                            <span className="w-1.5 h-1.5 rounded-full bg-teal-300 shrink-0" />{p.pod_name || p.name}
                                          </span>
                                        ))}
                                        {packedPods.length > 8 && (
                                          <span className="text-[9px] text-gray-400 italic">+{packedPods.length - 8} more</span>
                                        )}
                                      </div>
                                    )}
                                  </div>
                                );
                              })}
                            </div>
                          </div>
                        )}

                        {/* ── 3a. OD Anchor Node — OD reference for this workload ── */}
                        {!dsManagedWorkload && displayAnchorNodes.length > 0 && (
                          <div>
                            <div className="text-[10px] font-bold uppercase tracking-wider text-purple-600 mb-1">
                              ⚓ Anchor Node{displayAnchorNodes.length !== 1 ? 's' : ''} ({displayAnchorNodes.length}) — OD reference for this workload
                            </div>
                            <p className="text-[10px] text-gray-400 italic mb-2">
                              Every workload keeps ≥1 pod on an <strong>On-Demand</strong> node.
                              That OD node is the <em>anchor</em> — it stays stable while spot pods scale.
                              {implicitAnchorNode
                                ? ' No explicit anchor was configured; showing the first OD node in the plan as implicit anchor.'
                                : ' Critical pods (DB, primary replicas, PVC-backed) are pinned here and will not move.'}
                            </p>
                            <div className="space-y-1.5">
                              {displayAnchorNodes.map((kn, ki) => {
                                const layoutNode   = kn._isNew ? null : _getLayoutNode(kn.node_name);
                                const allExisting  = layoutNode?.existing_pods || [];
                                const incomingPods = kn._isNew
                                  ? (kn.packed_pods || [])
                                  : (layoutNode?.incoming_pods || []);
                                const existingPods = allExisting.filter(p =>
                                  !p.is_daemonset && p.pod_kind !== 'DaemonSet' && p.owner_kind !== 'DaemonSet'
                                );
                                const dsCount  = allExisting.length - existingPods.length;
                                const isRealName = /^ip-\d+-\d+-\d+-\d+/.test(kn.node_name || '');
                                return (
                                  <div key={ki} className={`border rounded-lg overflow-hidden ${kn._isNew ? 'border-purple-300' : 'border-purple-200'}`}>
                                    <div className={`flex items-center gap-2 px-3 py-2 ${kn._isNew ? 'bg-purple-100' : 'bg-purple-50'}`}>
                                      <span className="text-[9px] font-bold px-1.5 py-0.5 bg-purple-200 text-purple-800 rounded uppercase shrink-0">anchor</span>
                                      {kn._isNew
                                        ? <span className="text-[9px] font-bold px-1.5 py-0.5 bg-teal-100 text-teal-700 rounded uppercase shrink-0">new</span>
                                        : kn._isImplicit
                                          ? <span className="text-[9px] font-bold px-1.5 py-0.5 bg-gray-100 text-gray-600 rounded uppercase shrink-0">implicit</span>
                                          : <span className="text-[9px] font-bold px-1.5 py-0.5 bg-emerald-100 text-emerald-700 rounded uppercase shrink-0">keep</span>
                                      }
                                      <code className="text-[10px] font-mono truncate flex-1" title={kn.node_name}>
                                        {kn._isNew && !isRealName
                                          ? <span className="text-gray-400 italic">— assigned after launch</span>
                                          : kn.node_name.split('.')[0]
                                        }
                                      </code>
                                      <span className="text-[9px] font-semibold text-orange-700 shrink-0">OD</span>
                                      <span className="text-[9px] text-gray-500 shrink-0">
                                        {kn.instance_type
                                          ? kn.instance_type
                                          : kn._isNew ? <span className="italic text-amber-600">ISS pending</span> : '—'}
                                      </span>
                                      <span className="text-[9px] text-gray-400 shrink-0">{kn.az}</span>
                                      <span className="text-[9px] font-semibold text-gray-600 shrink-0">{Math.round(kn.required_cpu_millicores || 0)}m · {formatMem(kn.required_memory_bytes || 0)}</span>
                                    </div>
                                    <div className="px-3 py-1.5 bg-white flex flex-wrap gap-x-3 gap-y-0.5 items-center">
                                      {kn._isNew && incomingPods.length === 0 && (
                                        <span className="text-[9px] text-gray-400 italic">pod assignment confirmed after node launch</span>
                                      )}
                                      {existingPods.slice(0, 6).map((p, pi) => (
                                        <span key={pi} className="flex items-center gap-1 text-[9px] font-mono text-gray-600">
                                          <span className="w-1.5 h-1.5 rounded-full bg-purple-300 shrink-0" />{p.pod_name}
                                        </span>
                                      ))}
                                      {existingPods.length > 6 && <span className="text-[9px] text-gray-400 italic">+{existingPods.length - 6} more</span>}
                                      {dsCount > 0 && (
                                        <span className="text-[9px] text-gray-400 italic ml-2">· {dsCount} DaemonSet pod{dsCount !== 1 ? 's' : ''} (auto)</span>
                                      )}
                                      {incomingPods.slice(0, 5).map((p, pi) => (
                                        <span key={'i'+pi} className="flex items-center gap-1 text-[9px] font-mono text-emerald-600">
                                          <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 shrink-0" />{p.pod_name || p.name}
                                        </span>
                                      ))}
                                      {incomingPods.length > 5 && <span className="text-[9px] text-emerald-500 italic">+{incomingPods.length - 5} incoming</span>}
                                      {kn._isImplicit && (
                                        <span className="text-[9px] text-amber-600 italic ml-auto">implicit anchor</span>
                                      )}
                                    </div>
                                  </div>
                                );
                              })}
                            </div>
                          </div>
                        )}

                        {/* ── 3b. Active Keep Nodes (non-anchor, includes spot) ── */}
                        {activeKeepNodes.length > 0 && (
                          <div>
                            <div className="text-[10px] font-bold uppercase tracking-wider text-gray-400 mb-1">
                              Active Nodes ({activeKeepNodes.length}) — kept as-is, receiving incoming pods
                            </div>
                            <p className="text-[10px] text-gray-400 italic mb-2">
                              These nodes already have capacity to absorb incoming pods — no new node provisioned for them.
                              Spot nodes here are regular active nodes, not anchors.
                            </p>
                            <div className="space-y-1.5">
                              {activeKeepNodes.map((kn, ki) => {
                                const layoutNode = _getLayoutNode(kn.node_name);
                                const allExisting = layoutNode?.existing_pods || [];
                                const incomingPods = layoutNode?.incoming_pods || [];
                                const existingPods = allExisting.filter(p =>
                                  !p.is_daemonset && p.pod_kind !== 'DaemonSet' && p.owner_kind !== 'DaemonSet'
                                );
                                const dsCount = allExisting.length - existingPods.length;
                                const isSpot = (kn.capacity_type || '').toLowerCase() === 'spot';
                                return (
                                  <div key={ki} className={`border rounded-lg overflow-hidden ${isSpot ? 'border-indigo-100' : 'border-orange-100'}`}>
                                    <div className={`flex items-center gap-2 px-3 py-2 ${isSpot ? 'bg-indigo-50' : 'bg-orange-50'}`}>
                                      <span className="text-[9px] font-bold px-1.5 py-0.5 bg-emerald-100 text-emerald-700 rounded uppercase shrink-0">keep</span>
                                      <code className="text-[10px] font-mono text-gray-700 truncate flex-1" title={kn.node_name}>{kn.node_name.split('.')[0]}</code>
                                      <span className={`text-[9px] font-semibold shrink-0 ${isSpot ? 'text-indigo-600' : 'text-orange-700'}`}>{isSpot ? 'Spot' : 'OD'}</span>
                                      <span className="text-[9px] text-gray-500 shrink-0">{kn.instance_type}</span>
                                      <span className="text-[9px] text-gray-400 shrink-0">{kn.az}</span>
                                      <span className="text-[9px] font-semibold text-gray-600 shrink-0">{Math.round(kn.required_cpu_millicores || 0)}m · {formatMem(kn.required_memory_bytes || 0)}</span>
                                    </div>
                                    {(existingPods.length > 0 || incomingPods.length > 0) && (
                                      <div className="px-3 py-1.5 bg-white flex flex-wrap gap-x-3 gap-y-0.5">
                                        {existingPods.slice(0, 6).map((p, pi) => (
                                          <span key={pi} className="flex items-center gap-1 text-[9px] font-mono text-gray-600">
                                            <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${isSpot ? 'bg-indigo-300' : 'bg-orange-300'}`} />{p.pod_name}
                                          </span>
                                        ))}
                                        {existingPods.length > 6 && <span className="text-[9px] text-gray-400 italic">+{existingPods.length - 6} more</span>}
                                        {dsCount > 0 && (
                                          <span className="text-[9px] text-gray-400 italic ml-2">· {dsCount} DaemonSet pod{dsCount !== 1 ? 's' : ''} (auto)</span>
                                        )}
                                        {incomingPods.slice(0, 5).map((p, pi) => (
                                          <span key={'i'+pi} className="flex items-center gap-1 text-[9px] font-mono text-emerald-600">
                                            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 shrink-0" />{p.pod_name || p.name}
                                          </span>
                                        ))}
                                        {incomingPods.length > 5 && <span className="text-[9px] text-emerald-500 italic">+{incomingPods.length - 5} incoming</span>}
                                      </div>
                                    )}
                                  </div>
                                );
                              })}
                            </div>
                          </div>
                        )}
                      </div>
                    )}
                    {/* Warnings strip — always visible regardless of tab */}
                    {warnings.length > 0 && (
                      <div className="bg-amber-50 border border-amber-200 rounded px-3 py-2 text-[11px] text-amber-700">
                        <div className="font-semibold mb-1">Warnings ({warnings.length}):</div>
                        <ul className="list-disc ml-5 space-y-0.5">
                          {warnings.slice(0, 4).map((w, i) => <li key={i}>{w}</li>)}
                          {warnings.length > 4 && <li className="italic text-amber-500">+{warnings.length - 4} more…</li>}
                        </ul>
                      </div>
                    )}

                    {/* Movements tab */}
                    {ppePaneTab === 'movements' && azKeys.length > 0 && (
                      <div>
                        <div className="text-xs font-bold uppercase tracking-wider text-gray-400 mb-2">Target AZ Distribution</div>
                        <div className="grid grid-cols-3 gap-3">
                          {azKeys.map(az => {
                            const d = azDist[az] || { spot: 0, ondemand: 0, total: 0 };
                            return (
                              <div key={az} className="bg-gray-50 border border-gray-200 rounded-lg px-3 py-2">
                                <div className="text-[10px] font-mono text-gray-500 mb-1">{az}</div>
                                <div className="flex items-center gap-2 text-xs">
                                  <span className="px-1.5 py-0.5 rounded bg-indigo-50 border border-indigo-100 text-indigo-700 font-semibold">
                                    Spot {d.spot || 0}
                                  </span>
                                  <span className="px-1.5 py-0.5 rounded bg-red-50 border border-red-100 text-red-700 font-semibold">
                                    OD {d.ondemand || 0}
                                  </span>
                                  <span className="ml-auto text-gray-400 font-mono">{d.total || 0} pods</span>
                                </div>
                              </div>
                            );
                          })}
                        </div>
                      </div>
                    )}

                    {ppePaneTab === 'movements' && moves.length > 0 && (() => {
                      const nodeByName = {};
                      nodes.forEach(n => { nodeByName[n.node_name] = n; });
                      return (
                      <div>
                        <div className="text-xs font-bold uppercase tracking-wider text-gray-400 mb-2">Movement Plan</div>
                        <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
                          <table className="min-w-full text-xs font-mono">
                            <thead>
                              <tr className="border-b border-gray-100 bg-gray-50">
                                {['#', 'Pod', 'From', 'To Node', 'Instance', 'AZ', 'Status'].map(h => (
                                  <th key={h} className="px-3 py-2 text-left text-[10px] font-semibold uppercase text-gray-400">{h}</th>
                                ))}
                              </tr>
                            </thead>
                            <tbody className="divide-y divide-gray-50">
                              {moves.slice(0, 10).map((m, i) => {
                                const destNode = nodeByName[m.to_node];
                                const instType = m.to_instance_type || destNode?.instance_type;
                                return (
                                <tr key={i} className="hover:bg-gray-50">
                                  <td className="px-3 py-1.5 text-gray-400">{m.step}</td>
                                  <td className="px-3 py-1.5 text-gray-700 truncate max-w-[140px]" title={m.pod_name}>{m.pod_name}</td>
                                  <td className="px-3 py-1.5">
                                    <span className={`px-1.5 py-0.5 rounded text-[10px] font-semibold ${m.from_capacity_type === 'spot' ? 'bg-indigo-50 text-indigo-700' : 'bg-red-50 text-red-700'}`}>
                                      {m.from_capacity_type || '—'}
                                    </span>
                                  </td>
                                  <td className="px-3 py-1.5">
                                    <span className={`px-1.5 py-0.5 rounded text-[10px] font-semibold ${m.to_capacity_type === 'spot' ? 'bg-indigo-100 text-indigo-800' : 'bg-red-100 text-red-800'}`}>
                                      {m.to_capacity_type || '—'}
                                    </span>
                                  </td>
                                  <td className="px-3 py-1.5">
                                    {instType
                                      ? <span className="font-mono text-gray-600 text-[10px]">{instType}</span>
                                      : <span className="text-amber-500 italic text-[10px]">Pending ISS</span>
                                    }
                                  </td>
                                  <td className="px-3 py-1.5 text-gray-500">{m.to_az || '—'}</td>
                                  <td className="px-3 py-1.5">
                                    {m.blocked_by ? (
                                      <span className="text-red-600 font-semibold text-[10px]">⚠ {m.blocked_by}</span>
                                    ) : (
                                      <span className="text-emerald-600 text-[10px]">ready</span>
                                    )}
                                  </td>
                                </tr>
                                );
                              })}
                            </tbody>
                          </table>
                        </div>
                        {moves.length > 10 && (
                          <div className="text-[10px] text-gray-400 italic mt-1">+{moves.length - 10} more moves…</div>
                        )}
                      </div>
                      );
                    })()}

                    {/* Nodes tab */}
                    {ppePaneTab === 'nodes' && nodes.length > 0 && (
                      <div>
                        <div className="text-xs font-bold uppercase tracking-wider text-gray-400 mb-2">Node Plan</div>
                        <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
                          <table className="min-w-full text-xs font-mono">
                            <thead>
                              <tr className="border-b border-gray-100 bg-gray-50">
                                {['Action', 'Node', 'Capacity', 'AZ', 'Instance', 'CPU', 'Mem (GB)', 'Pods'].map(h => (
                                  <th key={h} className="px-3 py-2 text-left text-[10px] font-semibold uppercase text-gray-400">{h}</th>
                                ))}
                              </tr>
                            </thead>
                            <tbody className="divide-y divide-gray-50">
                              {nodes.slice(0, 12).map((n, i) => {
                                const actionStyle =
                                  n.action === 'provision' ? 'bg-teal-50 border-teal-200 text-teal-700' :
                                  n.action === 'drain'     ? 'bg-amber-50 border-amber-200 text-amber-700' :
                                                             'bg-emerald-50 border-emerald-200 text-emerald-700';
                                const memGb = ((n.required_memory_bytes || 0) / 1e9).toFixed(1);
                                return (
                                  <tr key={i} className="hover:bg-gray-50">
                                    <td className="px-3 py-1.5">
                                      <span className={`px-1.5 py-0.5 rounded text-[10px] font-semibold border ${actionStyle}`}>{n.action}</span>
                                    </td>
                                    <td className="px-3 py-1.5 text-gray-700 truncate max-w-[160px]" title={n.node_name}>{n.node_name || '—'}</td>
                                    <td className="px-3 py-1.5 text-gray-500">{n.capacity_type}</td>
                                    <td className="px-3 py-1.5 text-gray-500">{n.az || '—'}</td>
                                    <td className="px-3 py-1.5">
                                      {n.instance_type
                                        ? <span className="font-mono text-gray-600">{n.instance_type}</span>
                                        : n.action === 'provision'
                                          ? <span className="text-amber-600 italic text-[10px]">Pending ISS</span>
                                          : <span className="text-gray-300">—</span>
                                      }
                                    </td>
                                    <td className="px-3 py-1.5 text-gray-500">{Math.round(n.required_cpu_millicores || 0)} mc</td>
                                    <td className="px-3 py-1.5 text-gray-500">{memGb}</td>
                                    <td className="px-3 py-1.5 text-gray-500">{n.pod_count || 0}</td>
                                  </tr>
                                );
                              })}
                            </tbody>
                          </table>
                        </div>
                      </div>
                    )}

                    {/* Layout tab */}
                    {ppePaneTab === 'layout' && hasNodeLayout && (
                      <div>
                        <div className="text-xs font-bold uppercase tracking-wider text-gray-400 mb-2">Node Layout</div>
                        <div className="space-y-3">
                          {Object.entries(layoutByAz).sort(([a], [b]) => a.localeCompare(b)).map(([az, azData]) => {
                            const azNodes = azData.nodes || [];
                            return (
                              <div key={az}>
                                <div className="text-[10px] font-mono font-semibold text-gray-500 mb-1.5">
                                  {az}
                                  <span className="ml-2 text-gray-300">·</span>
                                  <span className="ml-1 text-gray-400">{azData.az_totals?.node_count || 0} nodes · {azData.az_totals?.pod_count_total_after || 0} pods after</span>
                                </div>
                                <div className="grid grid-cols-2 gap-2">
                                  {azNodes.map((node, idx) => {
                                    const label = `Node ${String.fromCharCode(65 + idx)}`;
                                    const isAnchor = node.is_anchor;
                                    const isSpot = (node.capacity_type || '').toLowerCase() === 'spot';
                                    const util = node.resources?.cpu_utilization_after_pct ?? 0;
                                    const utilColor = util >= 80 ? 'text-red-600' : util >= 60 ? 'text-amber-600' : 'text-emerald-600';
                                    const incoming = node.incoming_pods || [];
                                    const existing = node.existing_pods || [];
                                    return (
                                      <div key={node.node_name} className={`rounded-lg border p-2.5 ${
                                        isAnchor ? 'bg-purple-50 border-purple-200'
                                        : isSpot  ? 'bg-indigo-50 border-indigo-100'
                                        :           'bg-red-50 border-red-100'
                                      }`}>
                                        <div className="flex items-center justify-between mb-1.5">
                                          <div className="flex items-center gap-1.5">
                                            <span className="text-[11px] font-bold text-gray-700">{label}</span>
                                            {isAnchor && <span className="text-[9px] px-1 py-0.5 rounded bg-purple-100 border border-purple-200 text-purple-700 font-semibold">anchor</span>}
                                            <span className={`text-[9px] px-1 py-0.5 rounded font-semibold border ${
                                              isSpot ? 'bg-indigo-100 border-indigo-200 text-indigo-700' : 'bg-red-100 border-red-200 text-red-700'
                                            }`}>{isSpot ? 'Spot' : 'OD'}</span>
                                          </div>
                                          <span className={`text-[10px] font-bold font-mono ${utilColor}`}>{util.toFixed(0)}% CPU</span>
                                        </div>
                                        {/* CPU utilization bar */}
                                        <div className="w-full h-1 rounded-full bg-gray-200 mb-1.5 overflow-hidden">
                                          <div className={`h-full rounded-full ${
                                            util >= 80 ? 'bg-red-400' : util >= 60 ? 'bg-amber-400' : 'bg-emerald-400'
                                          }`} style={{ width: `${Math.min(util, 100)}%` }} />
                                        </div>
                                        {/* Incoming pods (highlighted) */}
                                        {incoming.length > 0 && (
                                          <div className="space-y-0.5">
                                            {incoming.slice(0, 4).map((p, pi) => (
                                              <div key={pi} className="flex items-center gap-1 text-[9px] font-mono">
                                                <span className="w-1 h-1 rounded-full bg-emerald-500 flex-shrink-0" />
                                                <span className="text-gray-700 truncate" title={p.pod_name}>{p.pod_name}</span>
                                                <span className="text-emerald-600 text-[8px] ml-auto flex-shrink-0">→ here</span>
                                              </div>
                                            ))}
                                            {incoming.length > 4 && <div className="text-[9px] text-gray-400 italic">+{incoming.length - 4} more incoming</div>}
                                          </div>
                                        )}
                                        {/* Existing pods (dimmed) */}
                                        {existing.length > 0 && incoming.length === 0 && (
                                          <div className="space-y-0.5">
                                            {existing.slice(0, 3).map((p, pi) => (
                                              <div key={pi} className="flex items-center gap-1 text-[9px] font-mono">
                                                <span className="w-1 h-1 rounded-full bg-gray-300 flex-shrink-0" />
                                                <span className="text-gray-500 truncate" title={p.pod_name}>{p.pod_name}</span>
                                              </div>
                                            ))}
                                            {existing.length > 3 && <div className="text-[9px] text-gray-400 italic">+{existing.length - 3} pods staying</div>}
                                          </div>
                                        )}
                                        <div className="text-[9px] text-gray-400 mt-1">
                                          {node.existing_pod_count} staying · {node.incoming_pod_count} incoming
                                        </div>
                                      </div>
                                    );
                                  })}
                                </div>
                              </div>
                            );
                          })}
                          {/* Drain candidates */}
                          {drainLayout.length > 0 && (
                            <div>
                              <div className="text-[10px] font-mono font-semibold text-amber-600 mb-1.5">Draining ({drainLayout.length})</div>
                              <div className="grid grid-cols-2 gap-2">
                                {drainLayout.map((node, idx) => (
                                  <div key={node.node_name} className="rounded-lg border bg-amber-50 border-amber-200 p-2.5">
                                    <div className="flex items-center justify-between">
                                      <span className="text-xs font-bold text-amber-700">Drain {idx + 1}</span>
                                      <span className="text-xs px-1 py-0.5 rounded bg-amber-100 border border-amber-300 text-amber-700 font-semibold">draining</span>
                                    </div>
                                    <div className="text-xs text-gray-400 mt-1">{node.az || '—'} · {(node.capacity_type || '').toLowerCase() === 'spot' ? 'Spot' : 'OD'}</div>
                                    <div className="text-xs text-amber-600 mt-0.5">All {node.existing_pod_count || 0} pods moving off</div>
                                  </div>
                                ))}
                              </div>
                            </div>
                          )}
                          {/* Provision required */}
                          {provLayout.length > 0 && (
                            <div>
                              <div className="text-xs font-mono font-semibold text-teal-600 mb-1.5">Provisioning ({provLayout.length})</div>
                              <div className="grid grid-cols-2 gap-2">
                                {provLayout.map((node, idx) => (
                                  <div key={node.node_name} className="rounded-lg border bg-teal-50 border-teal-200 p-2.5">
                                    <div className="flex items-center justify-between">
                                      <span className="text-xs font-bold text-teal-700">New Node {idx + 1}</span>
                                      <span className="text-xs px-1 py-0.5 rounded bg-teal-100 border border-teal-200 text-teal-700 font-semibold">provision</span>
                                    </div>
                                    <div className="text-xs text-gray-400 mt-1">{node.az || '—'} · {(node.capacity_type || '').toLowerCase() === 'spot' ? 'Spot' : 'OD'}</div>
                                    <div className="text-xs text-teal-600 mt-0.5">{node.incoming_pod_count || 0} pods scheduled here</div>
                                    {node.instance_type && <div className="text-xs text-gray-400">{node.instance_type}</div>}
                                  </div>
                                ))}
                              </div>
                            </div>
                          )}
                        </div>
                      </div>
                    )}

                    {ppePaneTab === 'summary' && moves.length === 0 && nodes.length === 0 && (
                      <div className="text-xs text-gray-400 italic text-center py-3">
                        Engine returned no plan — workload is at target or blocked by safety rules.
                        {warnings.length === 0 && <> {placementPlan.schema_version && <span className="text-gray-300">(schema {placementPlan.schema_version})</span>}</>}
                      </div>
                    )}
                  </div>
                </div>
              );
            })()}

            {/* Active Rebalancing Operations */}
            {activeOps.length > 0 && (
              <div className="bg-amber-50 rounded-xl border border-amber-200 p-4 shadow-sm">
                <h4 className="text-xs font-bold uppercase tracking-wider text-amber-700 mb-3">Active Operations</h4>
                <div className="space-y-2">
                  {activeOps.map(op => (
                    <div key={op.id} className="bg-white border border-amber-100 rounded-lg px-3 py-2 text-xs">
                      <div className="flex justify-between items-center mb-1">
                        <span className="font-mono font-semibold text-gray-800">{op.current_state}</span>
                        <span className={`px-1.5 py-0.5 rounded text-[10px] font-semibold ${
                          op.scope === 'workload' ? 'bg-indigo-100 text-indigo-700' : 'bg-gray-100 text-gray-600'
                        }`}>{op.scope === 'workload' ? 'pod-level' : 'node-level'}</span>
                      </div>
                      <div className="text-gray-500">{op.source_pool} → {op.target_pool}</div>
                      {op.source_instance_id && <div className="text-gray-400 font-mono">{op.source_instance_id}</div>}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* State Locks + Log */}
            <div className="grid grid-cols-2 gap-4">
              <div className="bg-white rounded-xl border border-gray-200 p-4 shadow-sm">
                <h4 className="text-xs font-bold uppercase tracking-wider text-gray-400 mb-2">State Locks</h4>
                {detailLoading ? (
                  <div className="text-xs text-gray-400">Loading...</div>
                ) : (
                  <p className="text-xs text-gray-600">{lockSummary(locks)}</p>
                )}
              </div>
              <div className="bg-white rounded-xl border border-gray-200 p-4 shadow-sm">
                <h4 className="text-xs font-bold uppercase tracking-wider text-gray-400 mb-3">Controller Log</h4>
                {detailLoading ? (
                  <div className="text-xs text-gray-400">Loading...</div>
                ) : log.length === 0 ? (
                  <div className="text-xs text-gray-400 italic">No recent decisions recorded.</div>
                ) : (
                  <div className="space-y-1.5 font-mono text-[11px] text-gray-500 overflow-y-auto max-h-28">
                    {log.map((entry, i) => {
                      const ts  = entry.timestamp ? String(entry.timestamp).substring(11, 19) : '';
                      const act = entry.action || JSON.stringify(entry);
                      return <div key={i}>{ts}{ts ? ' — ' : ''}{act}</div>;
                    })}
                  </div>
                )}
              </div>
            </div>

          </div>
        )}
      </div>
    </div>
  );
}