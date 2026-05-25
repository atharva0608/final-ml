import React, { useState, useEffect, useRef } from 'react';
import {
  FiActivity, FiAlertTriangle, FiCheckCircle, FiClock, FiRefreshCw,
  FiServer, FiZap, FiAlertCircle, FiLoader, FiFilter,
} from 'react-icons/fi';
import useClusters from '../../hooks/useClusters';
import { api } from '../../services/api';

// ── helpers ──────────────────────────────────────────────────────────────────
const fmtTime = (iso) => {
  if (!iso) return '—';
  const d = new Date(iso);
  return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
};
const fmtDate = (iso) => {
  if (!iso) return '';
  const d = new Date(iso);
  return d.toLocaleDateString([], { month: 'short', day: 'numeric' });
};
const fmtDur = (sec) => {
  if (sec == null) return null;
  if (sec < 60) return `${sec}s`;
  return `${Math.floor(sec / 60)}m ${sec % 60}s`;
};
const relTime = (iso) => {
  if (!iso) return '';
  const sec = Math.round((Date.now() - new Date(iso).getTime()) / 1000);
  if (sec < 5)  return 'just now';
  if (sec < 60) return `${sec}s ago`;
  if (sec < 3600) return `${Math.floor(sec / 60)}m ago`;
  return `${Math.floor(sec / 3600)}h ago`;
};

const SEV = {
  error:   { dot: 'bg-red-500',    line: 'border-red-200',    badge: 'bg-red-50 text-red-700 border-red-200',    icon: <FiAlertCircle className="w-3.5 h-3.5" /> },
  warning: { dot: 'bg-amber-400',  line: 'border-amber-200',  badge: 'bg-amber-50 text-amber-700 border-amber-200', icon: <FiAlertTriangle className="w-3.5 h-3.5" /> },
  success: { dot: 'bg-emerald-500',line: 'border-emerald-200',badge: 'bg-emerald-50 text-emerald-700 border-emerald-200', icon: <FiCheckCircle className="w-3.5 h-3.5" /> },
  info:    { dot: 'bg-indigo-400', line: 'border-indigo-200', badge: 'bg-indigo-50 text-indigo-700 border-indigo-200',  icon: <FiClock className="w-3.5 h-3.5" /> },
};

const ACTION_ICON = {
  CORDON_NODE: <FiServer className="w-3.5 h-3.5" />,
  DRAIN_NODE:  <FiServer className="w-3.5 h-3.5" />,
  TERMINATE_NODE: <FiServer className="w-3.5 h-3.5" />,
  EVICT_POD:   <FiZap className="w-3.5 h-3.5" />,
  PATCH_CONTAINER_RESOURCES: <FiActivity className="w-3.5 h-3.5" />,
  NODE_REBALANCE: <FiRefreshCw className="w-3.5 h-3.5" />,
};

const FILTER_TYPES = ['All', 'Rebalancing', 'Node', 'Pod', 'Rightsizing', 'Error'];

// ── data hook ─────────────────────────────────────────────────────────────────
const useTimeline = (clusterId) => {
  const [events, setEvents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [lastRefresh, setLastRefresh] = useState(null);
  const timerRef = useRef(null);

  const fetch = async () => {
    if (!clusterId) return;
    try {
      const res = await api.get('/api/v1/actions/timeline', { params: { cluster_id: clusterId, limit: 150 } });
      setEvents(res.data?.events ?? []);
      setError(null);
      setLastRefresh(new Date());
    } catch (err) {
      setError(err?.response?.data?.detail || err.message || 'Failed to load timeline');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (!clusterId) return;
    setLoading(true);
    fetch();
    timerRef.current = setInterval(fetch, 5000);
    return () => clearInterval(timerRef.current);
  }, [clusterId]);

  return { events, loading, error, lastRefresh, refresh: fetch };
};

// ── event card ────────────────────────────────────────────────────────────────
const EventRow = ({ ev, isLast }) => {
  const [expanded, setExpanded] = useState(false);
  const sev = SEV[ev.severity] ?? SEV.info;
  const dur = fmtDur(ev.duration_seconds);
  const icon = ACTION_ICON[ev.action_type] ?? <FiActivity className="w-3.5 h-3.5" />;

  const detail = [];
  if (ev.node)    detail.push({ k: 'Node', v: ev.node });
  if (ev.workload) detail.push({ k: 'Workload', v: ev.workload });
  if (ev.current_state) detail.push({ k: 'State', v: ev.current_state });
  if (ev.payload?.source_pool) detail.push({ k: 'From', v: ev.payload.source_pool });
  if (ev.payload?.target_pool) detail.push({ k: 'To',   v: ev.payload.target_pool });
  if (ev.payload?.pods_migrated != null) detail.push({ k: 'Pods migrated', v: ev.payload.pods_migrated });
  if (ev.payload?.estimated_savings_mo != null) detail.push({ k: 'Est savings', v: `$${ev.payload.estimated_savings_mo.toFixed(0)}/mo` });
  if (ev.error_message) detail.push({ k: 'Error', v: ev.error_message });
  if (ev.retry_count > 0) detail.push({ k: 'Retries', v: ev.retry_count });

  return (
    <div className="flex gap-3">
      {/* timeline spine */}
      <div className="flex flex-col items-center w-6 shrink-0">
        <div className={`w-2.5 h-2.5 rounded-full mt-3 shrink-0 ${sev.dot}`} />
        {!isLast && <div className="w-px flex-1 bg-gray-200 mt-1" />}
      </div>

      {/* card */}
      <div
        className={`flex-1 mb-3 rounded-lg border bg-white shadow-sm cursor-pointer hover:shadow-md transition-shadow overflow-hidden ${
          ev.severity === 'error' ? 'border-red-200' : ev.severity === 'warning' ? 'border-amber-200' : 'border-gray-200'
        }`}
        onClick={() => setExpanded(x => !x)}
      >
        {/* main row */}
        <div className="px-4 py-2.5 flex items-center gap-3">
          {/* icon + type */}
          <span className={`p-1 rounded ${sev.badge} border shrink-0`}>{icon}</span>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <span className="text-[13px] font-semibold text-gray-900 truncate">{ev.title}</span>
              {ev.priority >= 10 && (
                <span className="px-1.5 py-0.5 text-[9px] font-bold bg-red-600 text-white rounded uppercase">Emergency</span>
              )}
              <span className={`px-1.5 py-0.5 text-[9px] font-bold border rounded uppercase ${sev.badge}`}>
                {ev.status?.toUpperCase()}
              </span>
              {ev.action_type && ev.action_type !== 'NODE_REBALANCE' && (
                <span className="px-1.5 py-0.5 text-[9px] font-semibold bg-gray-100 text-gray-500 rounded border border-gray-200 uppercase">
                  {ev.action_type}
                </span>
              )}
            </div>
            <div className="flex items-center gap-3 mt-0.5 text-[11px] text-gray-400">
              {ev.node    && <span className="font-mono truncate max-w-[200px]">{ev.node}</span>}
              {ev.workload && <span className="truncate max-w-[160px]">{ev.workload}</span>}
              {dur && <span>{dur}</span>}
            </div>
          </div>
          {/* time */}
          <div className="text-right shrink-0">
            <p className="text-[11px] font-mono text-gray-500">{fmtTime(ev.timestamp)}</p>
            <p className="text-[10px] text-gray-400">{relTime(ev.timestamp)}</p>
          </div>
        </div>

        {/* expanded detail */}
        {expanded && detail.length > 0 && (
          <div className="px-4 py-2 border-t border-gray-100 bg-gray-50 grid grid-cols-2 sm:grid-cols-3 gap-x-6 gap-y-1">
            {detail.map(({ k, v }) => (
              <div key={k} className="text-[11px]">
                <span className="text-gray-400 uppercase font-bold tracking-wider text-[9px]">{k}:</span>{' '}
                <span className={`font-mono ${k === 'Error' ? 'text-red-600' : 'text-gray-700'}`}>{String(v)}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};

// ── date separator ─────────────────────────────────────────────────────────────
const DateSep = ({ label }) => (
  <div className="flex items-center gap-2 my-3 pl-9">
    <div className="h-px flex-1 bg-gray-200" />
    <span className="text-[10px] font-bold text-gray-400 uppercase tracking-wider px-2">{label}</span>
    <div className="h-px flex-1 bg-gray-200" />
  </div>
);

// ── main component ─────────────────────────────────────────────────────────────
const EventTimeline = () => {
  const { clusters, selectedId: globalClusterId, setSelectedId } = useClusters();
  const [clusterId, setClusterId] = useState(globalClusterId || clusters[0]?.id || '');
  const [activeFilter, setActiveFilter] = useState('All');

  useEffect(() => {
    if (globalClusterId && globalClusterId !== clusterId) setClusterId(globalClusterId);
  }, [globalClusterId]);

  const { events, loading, error, lastRefresh, refresh } = useTimeline(clusterId);

  const handleClusterChange = (e) => {
    setClusterId(e.target.value);
    setSelectedId(e.target.value);
  };

  // filter
  const filtered = events.filter(ev => {
    if (activeFilter === 'All')         return true;
    if (activeFilter === 'Rebalancing') return ev.event_type === 'rebalancing';
    if (activeFilter === 'Node')        return ['CORDON_NODE','DRAIN_NODE','TERMINATE_NODE','UNCORDON_NODE'].includes(ev.action_type);
    if (activeFilter === 'Pod')         return ['EVICT_POD','PATCH_AFFINITY','ANNOTATE_WORKLOAD'].includes(ev.action_type);
    if (activeFilter === 'Rightsizing') return ev.action_type === 'PATCH_CONTAINER_RESOURCES';
    if (activeFilter === 'Error')       return ev.severity === 'error' || ev.severity === 'warning';
    return true;
  });

  // group by date
  const groups = [];
  let lastDate = null;
  filtered.forEach((ev, i) => {
    const d = ev.timestamp ? fmtDate(ev.timestamp) : 'Unknown';
    if (d !== lastDate) { groups.push({ type: 'sep', label: d }); lastDate = d; }
    groups.push({ type: 'event', ev, isLast: i === filtered.length - 1 });
  });

  // stats
  const inFlight  = events.filter(e => ['PENDING','PICKED_UP','in_progress','IN_PROGRESS','waiting_agent','WAITING_AGENT','WAITING_FOR_KARPENTER','SOURCE_CORDONED','SOURCE_DRAINED','REPLACEMENT_LAUNCHING','REPLACEMENT_READY','SOURCE_TERMINATING'].includes(e.status || e.current_state)).length;
  const errCount  = events.filter(e => e.severity === 'error').length;
  const rebCount  = events.filter(e => e.event_type === 'rebalancing').length;
  const rsCount   = events.filter(e => e.action_type === 'PATCH_CONTAINER_RESOURCES').length;

  return (
    <div className="min-h-full bg-gray-50 p-6">
      <div className="max-w-screen-xl mx-auto space-y-5">

        {/* Header */}
        <div className="flex items-start justify-between flex-wrap gap-4">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-indigo-50 rounded-lg">
              <FiActivity className="w-5 h-5 text-indigo-600" />
            </div>
            <div>
              <h1 className="text-2xl font-bold text-gray-900">Event Timeline</h1>
              <p className="text-sm text-gray-500 mt-0.5">Live chronological feed · auto-refreshes every 5s</p>
            </div>
          </div>
          <div className="flex items-center gap-3 flex-wrap">
            {/* cluster picker */}
            <select
              value={clusterId}
              onChange={handleClusterChange}
              className="px-3 py-1.5 text-sm border border-gray-300 rounded-lg bg-white text-gray-700 shadow-sm outline-none"
            >
              {clusters.length === 0 && <option value="">No clusters</option>}
              {clusters.map(c => <option key={c.id} value={c.id}>{c.name || c.id}</option>)}
            </select>
            {/* live pulse */}
            <div className="flex items-center gap-1.5 bg-emerald-50 border border-emerald-200 rounded-full px-3 py-1">
              <div className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
              <span className="text-[11px] font-bold text-emerald-700 uppercase tracking-wider">Live</span>
            </div>
            <button
              onClick={refresh}
              className="p-1.5 rounded-lg border border-gray-200 bg-white hover:bg-gray-50 text-gray-500"
            >
              <FiRefreshCw className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Stats row */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          {[
            { label: 'In Flight',    val: inFlight, cls: 'text-indigo-700' },
            { label: 'Errors',       val: errCount,  cls: errCount > 0 ? 'text-red-700' : 'text-gray-700' },
            { label: 'Rebalancing',  val: rebCount,  cls: 'text-amber-700' },
            { label: 'Rightsizing',  val: rsCount,   cls: 'text-violet-700' },
          ].map(({ label, val, cls }) => (
            <div key={label} className="bg-white rounded-xl border border-gray-200 shadow-sm px-4 py-3 text-center">
              <p className="text-[10px] font-bold text-gray-400 uppercase tracking-wider mb-0.5">{label}</p>
              <p className={`text-2xl font-extrabold ${cls}`}>{val}</p>
            </div>
          ))}
        </div>

        {/* Filter bar */}
        <div className="flex items-center gap-1 bg-gray-100 p-1 rounded-lg w-fit">
          <FiFilter className="w-3.5 h-3.5 text-gray-400 ml-1 mr-1" />
          {FILTER_TYPES.map(f => (
            <button
              key={f}
              onClick={() => setActiveFilter(f)}
              className={`px-3 py-1 text-[12px] font-semibold rounded-md transition-all ${
                activeFilter === f ? 'bg-white shadow text-gray-900' : 'text-gray-500 hover:text-gray-700'
              }`}
            >{f}</button>
          ))}
          {lastRefresh && (
            <span className="ml-2 text-[10px] text-gray-400 font-mono pr-1">
              {fmtTime(lastRefresh.toISOString())}
            </span>
          )}
        </div>

        {/* Error banner */}
        {error && (
          <div className="flex items-center gap-2 px-4 py-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700">
            <FiAlertTriangle className="w-4 h-4 shrink-0" />
            {error}
          </div>
        )}

        {/* Timeline */}
        <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-5">
          {loading ? (
            <div className="flex flex-col items-center justify-center py-20 gap-3 text-gray-400">
              <FiLoader className="w-8 h-8 animate-spin" />
              <p className="text-sm">Loading event feed…</p>
            </div>
          ) : !clusterId ? (
            <div className="flex flex-col items-center justify-center py-20 gap-2 text-gray-400">
              <FiActivity className="w-10 h-10 text-gray-200" />
              <p className="text-sm">Select a cluster to view events.</p>
            </div>
          ) : groups.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-20 gap-3">
              <FiCheckCircle className="w-10 h-10 text-emerald-300" />
              <p className="text-sm font-medium text-gray-500">No events match the current filter.</p>
              {activeFilter !== 'All' && (
                <button onClick={() => setActiveFilter('All')} className="text-xs text-indigo-600 hover:underline">
                  Clear filter
                </button>
              )}
            </div>
          ) : (
            <div>
              {groups.map((g, i) =>
                g.type === 'sep'
                  ? <DateSep key={`sep-${i}`} label={g.label} />
                  : <EventRow key={g.ev.id} ev={g.ev} isLast={g.isLast} />
              )}
            </div>
          )}
        </div>

      </div>
    </div>
  );
};

export default EventTimeline;
