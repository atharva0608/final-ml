/**
 * Clusters.jsx — consolidated from ClusterList, ClusterDetails, and all sub-components
 * Sub-files merged: ClusterDeleteModal, ClusterDisconnectModal, PolicyGapAlert,
 * SpotRatioGauge, ClusterUtilizationSparkline, NodeGroupBreakdown,
 * ClusterHealthTimeline, NodeList, NodeTemplateTab
 */
import React, { useState, useEffect, useMemo, useRef, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  clusterAPI, metricsAPI, policyAPI, hibernationAPI,
  decisionEngineAPI, karpenterAPI, kedaAPI, nativeSpotAPI,
  ascpaiAPI, optimizationAPI, nodeTemplateAPI,
} from '../../../services/api';
import api from '../../../services/api';
import { Card, Button, Badge } from '../../../components/shared';
import {
  FiX, FiRefreshCw, FiSettings, FiClock, FiCpu,
  FiActivity, FiAlertTriangle, FiCheck, FiAlertCircle,
  FiCheckCircle, FiXCircle, FiServer, FiShield, FiLink,
} from 'react-icons/fi';
import { FaAws } from 'react-icons/fa';
import {
  AreaChart, Area, BarChart, Bar, PieChart, Pie, Cell,
  XAxis, YAxis, Tooltip, Legend, ResponsiveContainer,
} from 'recharts';
import toast from 'react-hot-toast';
import OverviewTab from './ClustersOverview';

// ─── Palette ──────────────────────────────────────────────────────────────────
const C = {
  bg: "#f5f6f8", surface: "#ffffff", surfaceHover: "#fafafa",
  border: "#e4e6ea", borderHover: "#c8cdd6",
  text: "#111318", muted: "#5a6272", subtle: "#98a1b0",
  accent: "#2563eb", accentLight: "#eff6ff",
  green: "#16a34a", greenBg: "#f0fdf4", greenBorder: "#bbf7d0",
  amber: "#b45309", amberBg: "#fffbeb", amberBorder: "#fde68a",
  red: "#dc2626", redBg: "#fef2f2", redBorder: "#fecaca",
  blue: "#2563eb", indigo: "#4f46e5",
  spotColor: "#16a34a", spotBg: "#f0fdf4",
  fallbackColor: "#b45309", fallbackBg: "#fffbeb",
  onDemandColor: "#2563eb", onDemandBg: "#eff6ff",
};
const utilColor = p => p < 60 ? C.green : p < 85 ? C.amber : C.fallbackColor;
const statusConfig = {
  healthy:    { label: "Healthy",  dot: C.green  },
  warning:    { label: "Warning",  dot: C.amber  },
  degraded:   { label: "Degraded", dot: "#dc2626" },
  "no-agent": { label: "No Agent", dot: C.subtle  },
};

// ─── Toggle helper ────────────────────────────────────────────────────────────
const Toggle = ({ checked, onChange, color = 'blue', disabled = false }) => {
  const colors = { blue: 'peer-checked:bg-blue-600', green: 'peer-checked:bg-green-600', teal: 'peer-checked:bg-teal-600', gray: 'peer-checked:bg-gray-800', indigo: 'peer-checked:bg-indigo-600' };
  return (
    <label className={`relative inline-flex items-center ml-4 shrink-0 ${disabled ? 'cursor-not-allowed opacity-40' : 'cursor-pointer'}`}>
      <input type="checkbox" className="sr-only peer" checked={checked} onChange={disabled ? undefined : onChange} disabled={disabled} />
      <div className={`w-9 h-5 bg-gray-200 rounded-full peer after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:after:translate-x-full peer-checked:after:border-white ${disabled ? 'peer-checked:bg-gray-400' : (colors[color] || colors.blue)}`} />
    </label>
  );
};

// ─── PolicyGapAlert ───────────────────────────────────────────────────────────
const PolicyGapAlert = ({ gapCount, onFix }) => {
  if (!gapCount || gapCount === 0) return (
    <div className="flex items-center gap-1.5 px-2 py-1 bg-green-50 text-green-700 rounded text-xs border border-green-100">
      <FiCheck className="w-3 h-3" /> Aligned
    </div>
  );
  return (
    <div className="flex items-center gap-2 px-2 py-1 bg-orange-50 text-orange-800 rounded text-xs border border-orange-200">
      <FiAlertCircle className="w-3 h-3 flex-shrink-0" />
      <span className="font-medium whitespace-nowrap">{gapCount} Policy Gaps</span>
      {onFix && (
        <button onClick={e => { e.stopPropagation(); onFix(); }} className="ml-1 px-1.5 py-0.5 bg-white border border-orange-200 rounded hover:bg-orange-100 flex items-center gap-1 text-[10px]">
          <FiSettings className="w-2.5 h-2.5" /> Fix
        </button>
      )}
    </div>
  );
};

// ─── SpotRatioGauge ───────────────────────────────────────────────────────────
const SpotRatioGauge = ({ spotPct, onDemandPct }) => {
  const spot = spotPct || 0; const od = onDemandPct || 0; const total = spot + od;
  const sv = total > 0 ? (spot / total) * 100 : 0;
  const data = [{ name: 'Spot', value: sv, color: '#10B981' }, { name: 'On-Demand', value: total > 0 ? (od / total) * 100 : 0, color: '#F59E0B' }];
  return (
    <div className="relative h-16 w-16">
      <ResponsiveContainer width="100%" height="100%">
        <PieChart><Pie data={data} cx="50%" cy="50%" innerRadius={20} outerRadius={30} startAngle={180} endAngle={0} paddingAngle={2} dataKey="value">{data.map((e, i) => <Cell key={i} fill={e.color} stroke="none" />)}</Pie><Tooltip contentStyle={{ fontSize: '10px', padding: '2px', borderRadius: '4px' }} formatter={v => [`${Math.round(v)}%`]} /></PieChart>
      </ResponsiveContainer>
      <div className="absolute top-1/2 left-1/2 transform -translate-x-1/2 -translate-y-0 text-[10px] font-bold text-gray-700 mt-1">{Math.round(sv)}%</div>
      <div className="absolute -bottom-1 w-full text-center text-[8px] text-gray-500 font-medium">SPOT</div>
    </div>
  );
};

// ─── ClusterUtilizationSparkline ──────────────────────────────────────────────
const ClusterUtilizationSparkline = ({ clusterId }) => {
  const [data, setData] = useState(null);
  useEffect(() => { if (!clusterId) return; api.get(`/api/v1/metrics/cluster/${clusterId}/utilization`).then(r => setData(r.data)).catch(() => {}); }, [clusterId]);
  if (!data) return <div className="h-8 w-24 bg-gray-50 animate-pulse rounded" />;
  return (
    <div className="flex items-center gap-2">
      <div className="h-8 w-24">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={data.cpu_history.map((v, i) => ({ i, v }))}>
            <defs><linearGradient id="cpuGrad" x1="0" y1="0" x2="0" y2="1"><stop offset="5%" stopColor="#3B82F6" stopOpacity={0.3} /><stop offset="95%" stopColor="#3B82F6" stopOpacity={0} /></linearGradient></defs>
            <Tooltip content={<></>} cursor={false} />
            <Area type="monotone" dataKey="v" stroke="#3B82F6" strokeWidth={1.5} fill="url(#cpuGrad)" />
          </AreaChart>
        </ResponsiveContainer>
      </div>
      <div className="flex flex-col text-[10px] leading-tight"><span className="font-bold text-gray-700">{data.cpu_current}%</span><span className="text-gray-400">CPU</span></div>
    </div>
  );
};

// ─── NodeGroupBreakdown ───────────────────────────────────────────────────────
const NodeGroupBreakdown = ({ clusterId }) => {
  const [data, setData] = useState([]);
  const [loading, setLoading] = useState(true);
  useEffect(() => { if (!clusterId) return; api.get(`/api/v1/metrics/cluster/${clusterId}/nodegroups`).then(r => setData(r.data)).catch(() => {}).finally(() => setLoading(false)); }, [clusterId]);
  if (loading) return <div className="h-48 bg-gray-50 animate-pulse rounded-lg" />;
  return (
    <Card title="Node Group Breakdown" className="h-full">
      <div className="h-64">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} layout="vertical" margin={{ top: 5, right: 30, left: 40, bottom: 5 }}>
            <XAxis type="number" /><YAxis type="category" dataKey="name" width={100} tick={{ fontSize: 10 }} />
            <Tooltip formatter={(v, n, p) => [v, `${p.payload.lifecycle} (${p.payload.instance_type})`]} cursor={{ fill: 'transparent' }} /><Legend />
            <Bar dataKey="count" name="Node Count" fill="#3B82F6" radius={[0, 4, 4, 0]} barSize={20} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </Card>
  );
};

// ─── ClusterHealthTimeline ────────────────────────────────────────────────────
const ClusterHealthTimeline = ({ clusterId }) => {
  const [events, setEvents] = useState([]);
  const [loading, setLoading] = useState(true);
  useEffect(() => { if (!clusterId) return; api.get(`/api/v1/metrics/cluster/${clusterId}/health-timeline`).then(r => setEvents(r.data)).catch(() => {}).finally(() => setLoading(false)); }, [clusterId]);
  const icon = s => s === 'healthy' ? <FiCheckCircle className="text-green-500" /> : s === 'degraded' ? <FiAlertTriangle className="text-yellow-500" /> : s === 'unavailable' ? <FiXCircle className="text-red-500" /> : <FiActivity className="text-gray-400" />;
  if (loading) return <div className="h-48 bg-gray-50 animate-pulse rounded-lg" />;
  return (
    <Card title="Health Timeline (24h)" className="h-full">
      <div className="relative border-l-2 border-gray-100 ml-3 space-y-6 py-2">
        {events.map((ev, i) => (
          <div key={i} className="relative pl-6">
            <div className="absolute -left-[9px] top-0 bg-white p-0.5 rounded-full">{icon(ev.status)}</div>
            <p className="text-xs text-gray-400 mb-0.5">{new Date(ev.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</p>
            <p className="text-sm font-medium text-gray-800">{ev.message}</p>
            <span className={`text-[10px] uppercase font-bold px-1.5 py-0.5 rounded ${ev.status === 'healthy' ? 'bg-green-50 text-green-700' : ev.status === 'degraded' ? 'bg-yellow-50 text-yellow-700' : 'bg-red-50 text-red-700'}`}>{ev.status}</span>
          </div>
        ))}
      </div>
    </Card>
  );
};

// ─── NodeList ─────────────────────────────────────────────────────────────────
const NodeList = ({ clusterId }) => {
  const [nodes, setNodes] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const fetch = useCallback(async () => {
    setError(null); setLoading(true);
    try { const r = await clusterAPI.getNodes(clusterId); setNodes(r.data.nodes || []); }
    catch (e) { setError(e.message || 'Failed to load nodes'); setNodes([]); }
    finally { setLoading(false); }
  }, [clusterId]);
  useEffect(() => { fetch(); }, [fetch]);
  if (loading) return <div className="text-center py-4">Loading nodes...</div>;
  if (error) return <Card><div className="flex flex-col items-center justify-center py-8 px-4"><FiActivity className="w-6 h-6 text-red-500 mb-3" /><p className="text-sm font-medium text-gray-900 mb-1">Failed to load nodes</p><p className="text-xs text-gray-500 mb-4">{error}</p><button onClick={fetch} className="px-4 py-2 text-sm font-medium text-white bg-blue-600 rounded-lg hover:bg-blue-700">Retry</button></div></Card>;
  if (!nodes.length) return <Card><div className="flex flex-col items-center justify-center py-8 px-4"><FiServer className="w-6 h-6 text-gray-400 mb-3" /><p className="text-sm font-medium text-gray-900 mb-1">No nodes found</p><p className="text-xs text-gray-500">No node data available yet.</p></div></Card>;
  return (
    <Card>
      <div className="flex justify-between items-center mb-4"><h3 className="text-lg font-semibold text-gray-900 flex items-center gap-2"><FiServer className="w-5 h-5" />Node List</h3><Badge color="gray">{nodes.length} Nodes</Badge></div>
      <div className="overflow-x-auto">
        <table className="min-w-full divide-y divide-gray-200">
          <thead className="bg-gray-50"><tr>{['Instance ID','Type','Lifecycle','CPU %','Zone'].map(h => <th key={h} className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">{h}</th>)}</tr></thead>
          <tbody className="bg-white divide-y divide-gray-200">
            {nodes.map(n => (
              <tr key={n.id}>
                <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900">{n.id}</td>
                <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">{n.type}</td>
                <td className="px-6 py-4 whitespace-nowrap"><Badge color={n.lifecycle === 'SPOT' ? 'green' : 'blue'}>{n.lifecycle}</Badge></td>
                <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500"><div className="flex items-center"><div className="w-16 bg-gray-200 rounded-full h-2 mr-2"><div className={`h-2 rounded-full ${n.cpu_util > 80 ? 'bg-red-500' : 'bg-green-500'}`} style={{ width: `${n.cpu_util}%` }} /></div>{n.cpu_util}%</div></td>
                <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">{n.az}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
};

// ─── NodeTemplateTab ──────────────────────────────────────────────────────────
const NodeTemplateTab = ({ clusterId }) => {
  const [loading, setLoading] = useState(true);
  const [templates, setTemplates] = useState([]);
  const [activeMapping, setActiveMapping] = useState(null);
  const [activeConstraints, setActiveConstraints] = useState(null);
  const [selectedTemplateId, setSelectedTemplateId] = useState('');
  const [assigning, setAssigning] = useState(false);
  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const [tR, mR] = await Promise.allSettled([nodeTemplateAPI.getGlobalTemplates(), nodeTemplateAPI.getActiveMapping(clusterId)]);
      if (tR.status === 'fulfilled') setTemplates(tR.value.data.templates || []);
      if (mR.status === 'fulfilled' && mR.value.data) { const m = mR.value.data; setActiveMapping(m); if (m.version?.constraints_json) setActiveConstraints(m.version.constraints_json); }
      else { setActiveMapping(null); setActiveConstraints(null); }
    } catch { toast.error('Failed to load template assignment data'); }
    finally { setLoading(false); }
  }, [clusterId]);
  useEffect(() => { if (clusterId) loadData(); }, [clusterId, loadData]);
  const handleAssign = async () => {
    if (!selectedTemplateId) return; setAssigning(true);
    try { await nodeTemplateAPI.assignToCluster(clusterId, selectedTemplateId, null); toast.success('Template assigned'); loadData(); setSelectedTemplateId(''); }
    catch { toast.error('Failed to assign template'); }
    finally { setAssigning(false); }
  };
  if (loading) return <div className="py-12 flex justify-center"><div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600" /></div>;
  return (
    <div className="space-y-6">
      <Card className="bg-gradient-to-r from-blue-50 to-indigo-50 border-blue-100">
        <div className="flex items-center justify-between">
          <div><h3 className="text-lg font-bold text-gray-900 flex items-center gap-2"><FiLink /> Enterprise Template Assignment</h3><p className="text-sm text-gray-600 mt-1">Assign an authoritative constraint wrapper to guide ML candidate filtering.</p></div>
          <div>{activeMapping ? <Badge color="green" size="lg"><FiCheck className="inline mr-1" />ACTIVE MAPPING</Badge> : <Badge color="gray" size="lg">NO TEMPLATE ASSIGNED</Badge>}</div>
        </div>
      </Card>
      <Card className="border-indigo-100 shadow-sm border p-5 bg-white">
        <h4 className="text-sm font-semibold text-gray-900 mb-3 uppercase tracking-wider">Set Cluster Default Template</h4>
        <div className="flex gap-4 items-end">
          <div className="flex-1">
            <label className="block text-sm font-medium text-gray-700 mb-1">Select Global Template <span className="text-red-500">*</span></label>
            <select className="w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500" value={selectedTemplateId} onChange={e => setSelectedTemplateId(e.target.value)} disabled={assigning}>
              <option value="">-- Choose a template from the Global Registry --</option>
              {templates.map(t => <option key={t.id} value={t.id}>{t.name} (Global)</option>)}
            </select>
          </div>
          <Button variant="primary" onClick={handleAssign} disabled={!selectedTemplateId || assigning} className="bg-indigo-600 hover:bg-indigo-700">{assigning ? 'Assigning...' : 'Set as Cluster Default'}</Button>
        </div>
      </Card>
      {activeMapping && activeConstraints ? (
        <Card className="border-green-100 shadow-sm border p-5 bg-white relative overflow-hidden">
          <div className="absolute top-0 left-0 w-1 h-full bg-green-500" />
          <div className="flex justify-between items-start mb-6">
            <div><h4 className="text-sm font-semibold text-gray-900 uppercase tracking-wider">Active Configuration</h4><p className="text-sm text-gray-500 mt-1">This cluster is currently governed by the constraints below.</p></div>
            <div className="text-right"><div className="text-lg font-bold text-gray-900">{activeMapping.template?.name || 'Unknown Template'}</div><div className="text-xs text-gray-500 font-mono mt-1">Version ID: {activeMapping.version_id.split('-')[0]}</div></div>
          </div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 bg-gray-50 rounded-lg p-4 border border-gray-100">
            <div><div className="text-xs text-gray-500 mb-1">Workload Scope</div><div className="text-sm font-semibold text-gray-900">{activeConstraints.workload_scope}</div></div>
            <div><div className="text-xs text-gray-500 mb-1">Policy Objective</div><div className="text-sm font-semibold text-gray-900">{activeConstraints.optimization_policy.replace('_', ' ')}</div></div>
            <div><div className="text-xs text-gray-500 mb-1">Max Interruption Risk</div><div className="text-sm font-bold text-orange-600">{activeConstraints.risk_threshold}%</div></div>
            <div><div className="text-xs text-gray-500 mb-1">Min Expected Savings</div><div className="text-sm font-bold text-green-600">{activeConstraints.savings_threshold}%</div></div>
            <div className="col-span-2 pt-3 border-t border-gray-200 mt-1"><div className="text-xs text-gray-500 mb-1">vCPU Bounds</div><div className="text-sm font-semibold text-gray-900">{activeConstraints.min_vcpu} - {activeConstraints.max_vcpu} Cores</div></div>
            <div className="col-span-2 pt-3 border-t border-gray-200 mt-1"><div className="text-xs text-gray-500 mb-1">Memory Bounds</div><div className="text-sm font-semibold text-gray-900">{activeConstraints.min_memory} - {activeConstraints.max_memory} GiB</div></div>
            <div className="col-span-4 pt-3 border-t border-gray-200 mt-1"><div className="text-xs text-gray-500 mb-1">Provisioning Strategy</div><div className="text-sm font-semibold text-gray-900">{activeConstraints.substitute_strategy}</div></div>
          </div>
        </Card>
      ) : (
        <Card className="p-12 text-center text-gray-500 border border-dashed border-gray-300">
          <FiShield className="mx-auto text-gray-300 mb-4" size={48} />
          <h3 className="text-lg font-semibold text-gray-600 mb-2">Cluster Unprotected</h3>
          <p className="text-sm mb-4 max-w-md mx-auto">This cluster cannot enter optimization mode because it does not have an active template assigned.</p>
        </Card>
      )}
    </div>
  );
};

// ─── ClusterDeleteModal ───────────────────────────────────────────────────────
const ClusterDeleteModal = ({ isOpen, onClose, cluster, onConfirm }) => {
  const [confirmName, setConfirmName] = useState('');
  const [loading, setLoading] = useState(false);
  if (!isOpen || !cluster) return null;
  const ok = confirmName === cluster.name;
  const handle = async () => { if (!ok) return; setLoading(true); try { await onConfirm(cluster.id); onClose(); setConfirmName(''); } catch {} finally { setLoading(false); } };
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm">
      <div className="bg-white rounded-xl shadow-2xl max-w-md w-full mx-4 overflow-hidden">
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100 bg-red-50">
          <div className="flex items-center gap-3"><div className="w-8 h-8 bg-red-100 rounded-full flex items-center justify-center"><FiAlertTriangle className="w-4 h-4 text-red-600" /></div><span className="font-semibold text-gray-900">Delete Cluster</span></div>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600"><FiX className="w-5 h-5" /></button>
        </div>
        <div className="px-6 py-5">
          <div className="flex items-start gap-3 mb-4"><FaAws className="w-5 h-5 text-gray-400 mt-0.5" /><div><h3 className="font-semibold text-gray-900 mb-1">{cluster.name}</h3><p className="text-sm text-gray-600">{cluster.region}</p></div></div>
          <div className="bg-red-50 border border-red-200 rounded-lg p-4 mb-6">
            <div className="flex items-start gap-2"><FiAlertTriangle className="w-5 h-5 text-red-600 mt-0.5 shrink-0" /><div><h4 className="text-sm font-semibold text-red-900 mb-1">This action cannot be undone</h4><ul className="text-sm text-red-700 space-y-1"><li>• Remove the Balancekube agent from Kubernetes</li><li>• Delete the balancekube namespace and all resources</li><li>• Remove cluster data from our database</li><li>• Delete all metrics history</li></ul></div></div>
          </div>
          <div><h3 className="text-sm font-semibold text-gray-900 mb-2">Confirmation</h3><p className="text-sm text-gray-600 mb-3">Type <span className="font-mono font-semibold text-gray-900">{cluster.name}</span> to confirm deletion</p><input type="text" value={confirmName} onChange={e => setConfirmName(e.target.value)} placeholder={cluster.name} className="w-full px-4 py-2.5 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-red-500" autoComplete="off" /></div>
        </div>
        <div className="flex justify-end gap-3 px-6 py-4 border-t border-gray-100 bg-gray-50">
          <button onClick={onClose} disabled={loading} className="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-200 rounded-lg hover:bg-gray-50 disabled:opacity-50">Cancel</button>
          <button onClick={handle} disabled={!ok || loading} className={`px-4 py-2 text-sm font-medium text-white rounded-lg ${ok && !loading ? 'bg-red-600 hover:bg-red-700' : 'bg-gray-300 cursor-not-allowed'}`}>{loading ? 'Deleting...' : 'Delete Cluster'}</button>
        </div>
      </div>
    </div>
  );
};

// ─── ClusterDisconnectModal ───────────────────────────────────────────────────
const ClusterDisconnectModal = ({ isOpen, onClose, cluster, onConfirm }) => {
  const [confirmName, setConfirmName] = useState('');
  const [deleteNodes, setDeleteNodes] = useState(false);
  const [loading, setLoading] = useState(false);
  if (!isOpen || !cluster) return null;
  const ok = confirmName === cluster.name;
  const handle = async () => { if (!ok) return; setLoading(true); try { await onConfirm(cluster.id, deleteNodes); onClose(); } catch {} finally { setLoading(false); } };
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm">
      <div className="bg-white rounded-xl shadow-2xl max-w-md w-full mx-4 overflow-hidden">
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100">
          <div className="flex items-center gap-3"><div className="w-8 h-8 bg-orange-100 rounded-full flex items-center justify-center"><FaAws className="w-4 h-4 text-orange-500" /></div><span className="font-semibold text-gray-900">{cluster.name}</span></div>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600"><FiX className="w-5 h-5" /></button>
        </div>
        <div className="px-6 py-5">
          <h2 className="text-xl font-bold text-gray-900 mb-2">Disconnect your cluster</h2>
          <p className="text-sm text-gray-600 mb-6">This action will remove all Balancekube resources managing your cluster. Please go to AWS IAM and delete it manually.</p>
          <div className="mb-6"><h3 className="text-sm font-semibold text-gray-900 mb-2">Confirmation</h3><p className="text-sm text-gray-600 mb-3">Enter the cluster name to confirm.</p><input type="text" value={confirmName} onChange={e => setConfirmName(e.target.value)} placeholder={cluster.name} className="w-full px-4 py-2.5 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" /></div>
          <div className="bg-gray-50 rounded-lg p-4 mb-6">
            <label className="flex items-start gap-3 cursor-pointer">
              <input type="checkbox" checked={deleteNodes} onChange={e => setDeleteNodes(e.target.checked)} className="mt-0.5 w-4 h-4 text-blue-600 border-gray-300 rounded" />
              <div className="flex-1"><div className="flex items-center gap-2 mb-1"><span className="text-sm font-semibold text-gray-900">Delete all Balancekube created nodes</span><span className="inline-flex items-center gap-1 px-2 py-0.5 bg-amber-100 text-amber-700 text-xs font-medium rounded"><FiAlertTriangle className="w-3 h-3" />Might cause downtime</span></div><p className="text-xs text-gray-500">All optimized nodes will be drained and deleted.</p></div>
            </label>
          </div>
        </div>
        <div className="flex justify-end gap-3 px-6 py-4 border-t border-gray-100 bg-gray-50">
          <button onClick={onClose} className="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-200 rounded-lg hover:bg-gray-50">Cancel</button>
          <button onClick={handle} disabled={!ok || loading} className={`px-4 py-2 text-sm font-medium text-white rounded-lg ${ok && !loading ? 'bg-blue-600 hover:bg-blue-700' : 'bg-gray-300 cursor-not-allowed'}`}>{loading ? 'Disconnecting...' : 'Disconnect'}</button>
        </div>
      </div>
    </div>
  );
};

// ─── MiniBar + MetricBox ──────────────────────────────────────────────────────
const MiniBar = ({ used, total, color, pct, allocatedPct }) => {
  const usagePct = pct !== undefined ? Math.round(pct) : (total > 0 ? Math.round((used / total) * 100) : 0);
  const allocPct = allocatedPct !== undefined ? Math.round(allocatedPct) : 0;
  const primary = allocPct > 0 ? allocPct : usagePct;
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
      <div style={{ flex: 1, height: 5, background: "#f0f0f0", borderRadius: 3, position: "relative" }}>
        {allocPct > 0 && <div style={{ position: "absolute", width: `${Math.min(allocPct, 100)}%`, height: 5, background: C.amber + "88", borderRadius: 3 }} />}
        <div style={{ position: "relative", width: `${Math.min(usagePct, 100)}%`, height: 5, background: color, borderRadius: 3, transition: "width 0.4s" }} />
      </div>
      <span style={{ fontSize: 10, color: C.muted, width: 28, textAlign: "right", flexShrink: 0 }}>{primary}%</span>
    </div>
  );
};
const MetricBox = ({ label, value, sub, icon, style = {} }) => (
  <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: 10, padding: "12px 14px", ...style }}>
    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
      <div style={{ fontSize: 11, color: C.muted, marginBottom: 4, fontWeight: 500 }}>{label}</div>
      {icon && <span style={{ fontSize: 13, opacity: 0.5 }}>{icon}</span>}
    </div>
    <div style={{ fontSize: 19, fontWeight: 700, letterSpacing: "-0.4px", color: C.text }}>{value}</div>
    {sub && <div style={{ fontSize: 11, color: C.subtle, marginTop: 3 }}>{sub}</div>}
  </div>
);

// ─── ClusterListItem ──────────────────────────────────────────────────────────
const ClusterListItem = ({ cluster, selected, onClick }) => {
  const sc = statusConfig[cluster.status] || statusConfig['no-agent'];
  return (
    <div onClick={onClick} style={{ padding: "12px 14px", borderRadius: 10, border: `1.5px solid ${selected ? C.accent : C.border}`, background: selected ? C.accentLight : C.surface, cursor: "pointer", transition: "all 0.15s", marginBottom: 6 }}
      onMouseEnter={e => { if (!selected) { e.currentTarget.style.borderColor = C.borderHover; e.currentTarget.style.background = C.surfaceHover; } }}
      onMouseLeave={e => { if (!selected) { e.currentTarget.style.borderColor = C.border; e.currentTarget.style.background = C.surface; } }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 6 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 7 }}>
          <div style={{ width: 6, height: 6, borderRadius: "50%", background: sc.dot, flexShrink: 0 }} />
          <span style={{ fontWeight: 600, fontSize: 12.5, color: selected ? C.accent : C.text, letterSpacing: "-0.2px", maxWidth: 130, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{cluster.name}</span>
          {cluster.health_score && <span style={{ fontSize: 9, fontWeight: 700, padding: "2px 5px", borderRadius: 4, flexShrink: 0, background: cluster.health_score === "A" ? "#dcfce7" : cluster.health_score === "B" ? "#dbeafe" : cluster.health_score === "C" ? "#fef9c3" : "#fee2e2", color: cluster.health_score === "A" ? "#166534" : cluster.health_score === "B" ? "#1e40af" : cluster.health_score === "C" ? "#854d0e" : "#991b1b" }}>{cluster.health_score}</span>}
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 4, padding: "2px 7px", borderRadius: 5, background: "#f0f1f3", border: `1px solid ${C.border}`, fontSize: 10, fontWeight: 500, color: C.muted }}>
          <div style={{ width: 5, height: 5, borderRadius: "50%", background: sc.dot }} />{sc.label}
        </div>
      </div>
      <div style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 6 }}>
        <span style={{ fontSize: 10, color: C.subtle, background: "#f0f1f3", padding: "2px 6px", borderRadius: 4 }}>{cluster.region}</span>
        <span style={{ fontSize: 10, color: C.subtle }}>{cluster._nodeCountPending ? '…' : cluster.nodes.total} nodes</span>
        <span style={{ fontSize: 10, color: cluster.agentInstalled ? C.green : C.subtle, fontWeight: cluster.agentInstalled ? 600 : 400 }}>{cluster.agentInstalled ? "● Agent" : "○ No Agent"}</span>
      </div>
      {cluster.agentInstalled && (
        <div style={{ display: "flex", flexDirection: "column", gap: 3, marginBottom: 6 }}>
          {[{ key: "CPU", ...cluster.cpu }, { key: "MEM", ...cluster.memory }].map(r => {
            const ap = r.total > 0 && r.requested > 0 ? Math.round((r.requested / r.total) * 100) : 0;
            return <div key={r.key} style={{ display: "flex", gap: 6, alignItems: "center" }}><span style={{ fontSize: 9, color: C.subtle, width: 26, textTransform: "uppercase" }}>{r.key}</span><div style={{ flex: 1 }}><MiniBar used={r.used} total={r.total} color={utilColor(r.total > 0 ? Math.round(r.used / r.total * 100) : 0)} allocatedPct={ap} /></div></div>;
          })}
        </div>
      )}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <span style={{ fontSize: 11, color: C.muted, fontWeight: 500 }}>${cluster.cost.monthly.toLocaleString()}/mo</span>
        {cluster.cost.savings > 0 && <span style={{ fontSize: 10, color: C.muted, display: "flex", alignItems: "center", gap: 4 }}><div style={{ width: 5, height: 5, borderRadius: "50%", background: C.green }} />${cluster.cost.savings.toLocaleString()} saved</span>}
      </div>
    </div>
  );
};

// ─── NoAgentDetail ────────────────────────────────────────────────────────────
const NoAgentDetail = ({ cluster, onClose }) => {
  const [showDel, setShowDel] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const doDelete = () => {
    setDeleting(true);
    clusterAPI.deleteCluster(cluster.id).then(() => { toast.success(`Cluster "${cluster.name}" removed.`); setDeleting(false); setShowDel(false); if (onClose) onClose(); window.dispatchEvent(new Event('refresh-clusters')); }).catch(err => { toast.error(`Failed: ${err.response?.data?.detail || err.message}`); setDeleting(false); });
  };
  return (
    <div style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", padding: 40, textAlign: "center" }}>
      <div style={{ fontSize: 40, marginBottom: 16, opacity: 0.25 }}>⬡</div>
      <div style={{ fontSize: 16, fontWeight: 700, color: C.text, marginBottom: 6 }}>{cluster.name}</div>
      <div style={{ fontSize: 13, color: C.muted, maxWidth: 340, lineHeight: 1.7, marginBottom: 24 }}>This cluster doesn't have the Balancekube agent installed. Install it to unlock real-time metrics, ML optimization, and savings tracking.</div>
      <div style={{ display: "flex", gap: 8 }}>
        <button type="button" onClick={e => { e.preventDefault(); e.stopPropagation(); toast.loading(`Installing agent on ${cluster.name}...`, { id: 'inject' }); clusterAPI.autoInstallAgent(cluster.id).then(() => { toast.success(`Agent installation queued for ${cluster.name}. Active in ~30s.`, { id: 'inject', duration: 5000 }); setTimeout(() => window.dispatchEvent(new Event('refresh-clusters')), 8000); }).catch(err => toast.error('Failed to install agent: ' + (err.response?.data?.detail || err.message), { id: 'inject' })); }}
          style={{ padding: "9px 20px", borderRadius: 10, background: "linear-gradient(135deg, #2563eb, #4f46e5)", border: "none", color: "#fff", fontSize: 13, fontWeight: 600, cursor: "pointer", fontFamily: "inherit", boxShadow: "0 2px 10px rgba(37,99,235,0.3)" }}>Install Agent</button>
        <button style={{ padding: "9px 20px", borderRadius: 10, border: `1px solid ${C.border}`, background: C.surface, color: C.muted, fontSize: 13, cursor: "pointer", fontFamily: "inherit" }}>View Docs</button>
        <button onClick={() => setShowDel(true)} style={{ padding: "9px 20px", borderRadius: 10, background: "#fef2f2", border: "1px solid #fecaca", color: "#dc2626", fontSize: 13, fontWeight: 600, cursor: "pointer", fontFamily: "inherit" }}>Remove Cluster</button>
      </div>
      <div style={{ marginTop: 32, display: "grid", gridTemplateColumns: "repeat(5, 1fr)", gap: 10, width: "100%", maxWidth: 640 }}>
        <MetricBox label="Region" value={cluster.region} /><MetricBox label="K8s Version" value={cluster.k8sVersion} />
        <MetricBox label="Total Nodes" value={cluster._nodeCountPending ? '…' : cluster.nodes.total} />
        <MetricBox label="Est. Cost" value={`$${cluster.cost.monthly}/mo`} sub="on-demand pricing" />
        <MetricBox label="Est. Savings" value={`$${cluster.cost.potential || 0}/mo`} sub="potential" />
      </div>
      {showDel && (
        <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.55)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 9999 }}>
          <div style={{ background: "#fff", borderRadius: 14, padding: "28px 32px", maxWidth: 420, width: "100%", margin: "0 16px", boxShadow: "0 20px 60px rgba(0,0,0,0.25)" }}>
            <div style={{ fontSize: 17, fontWeight: 700, color: "#dc2626", marginBottom: 10 }}>Remove Cluster?</div>
            <div style={{ fontSize: 13, color: "#374151", marginBottom: 16, lineHeight: 1.7 }}>Permanently delete <strong>{cluster.name}</strong> and all associated data? This cannot be undone.</div>
            <div style={{ display: "flex", gap: 10, justifyContent: "flex-end" }}>
              <button onClick={() => setShowDel(false)} disabled={deleting} style={{ padding: "8px 18px", borderRadius: 8, border: "1px solid #d1d5db", background: "#fff", fontSize: 13, cursor: "pointer", fontFamily: "inherit" }}>Cancel</button>
              <button onClick={doDelete} disabled={deleting} style={{ padding: "8px 18px", borderRadius: 8, border: "none", background: "#dc2626", color: "#fff", fontSize: 13, fontWeight: 600, cursor: deleting ? "not-allowed" : "pointer", fontFamily: "inherit", opacity: deleting ? 0.7 : 1 }}>{deleting ? "Removing..." : "Remove Cluster"}</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

// ─── NodeConditionBadge ───────────────────────────────────────────────────────
const CONDITION_STYLES = {
  'REBALANCING': 'bg-indigo-50 text-indigo-700 border-indigo-200',
  'AWAITING_SPOT': 'bg-blue-50 text-blue-700 border-blue-200',
  'REBALANCE:RISK_HIGH': 'bg-red-50 text-red-700 border-red-200',
  'REBALANCE:BETTER_POOL': 'bg-amber-50 text-amber-700 border-amber-200',
  'STABLE': 'bg-green-50 text-green-700 border-green-200',
};
const CONDITION_TOOLTIPS = {
  'AWAITING_SPOT': 'This on-demand node is eligible for spot conversion.',
  'REBALANCE:RISK_HIGH': 'Current spot pool has elevated interruption risk.',
  'REBALANCE:BETTER_POOL': 'A more cost-effective spot pool has been identified.',
  'STABLE': 'This node is optimally placed. No rebalancing action is needed.',
};
const NodeConditionBadge = ({ node, rec, isInFlight }) => {
  if (isInFlight) return <span className="px-2 py-0.5 text-xs rounded-full border bg-indigo-50 text-indigo-700 border-indigo-200 flex items-center gap-1 whitespace-nowrap"><span className="w-1.5 h-1.5 bg-indigo-500 rounded-full animate-pulse inline-block" />Rebalancing...</span>;
  const cond = node.rebalance_condition || (node.lifecycle !== 'spot' ? 'AWAITING_SPOT' : 'STABLE');
  const style = CONDITION_STYLES[cond] || CONDITION_STYLES['STABLE'];
  const riskPct = node.current_risk_score != null ? ` · ${(node.current_risk_score * 100).toFixed(0)}%` : (rec?.risk_score != null ? ` · ${(rec.risk_score * 100).toFixed(0)}%` : '');
  const labels = { 'AWAITING_SPOT': 'OD → Spot', 'REBALANCE:RISK_HIGH': `⚠ Risk High${riskPct}`, 'REBALANCE:BETTER_POOL': '↑ Better Pool', 'STABLE': `Stable${riskPct}` };
  const poolHint = node.best_available_pool || rec?.target_type || null;
  return (
    <div title={CONDITION_TOOLTIPS[cond] || 'Node status is being evaluated.'}>
      <span className={`px-2 py-0.5 text-xs rounded-full border ${style} whitespace-nowrap`}>{labels[cond] || 'Stable'}</span>
      {poolHint && cond === 'REBALANCE:BETTER_POOL' && <div className="text-[10px] text-gray-400 mt-0.5">{poolHint}</div>}
    </div>
  );
};

// ─── ClusterDetails ───────────────────────────────────────────────────────────
const ClusterDetails = ({ clusterId, onClose }) => {
  const [cluster, setCluster] = useState(null);
  const [activeTab, setActiveTab] = useState('Overview');
  const [metrics, setMetrics] = useState(null);
  const [policy, setPolicy] = useState(null);
  const [schedule, setSchedule] = useState(null);
  const [utilization, setUtilization] = useState(null);
  const [nodesDetailed, setNodesDetailed] = useState(null);
  const [nodeRecommendations, setNodeRecommendations] = useState([]);
  const [karpenterSimulation, setKarpenterSimulation] = useState(null);
  const [rebalancingActions, setRebalancingActions] = useState([]);
  const [rightsizing, setRightsizing] = useState([]);
  const [costTrends, setCostTrends] = useState(null);
  const [optSettings, setOptSettings] = useState(null);
  const optSettingsRef = useRef(null);
  const [savingOptSettings, setSavingOptSettings] = useState(false);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [optimizing, setOptimizing] = useState(false);
  const [showDisconnectModal, setShowDisconnectModal] = useState(false);
  const [showRemoveModal, setShowRemoveModal] = useState(false);
  const [agentActionLoading, setAgentActionLoading] = useState(false);
  const [fallbackLoading, setFallbackLoading] = useState(false);
  const [karpenterInstallStatus, setKarpenterInstallStatus] = useState(null);
  const [karpenterActionLoading, setKarpenterActionLoading] = useState(false);
  const [showKarpenterRequiredModal, setShowKarpenterRequiredModal] = useState(false);
  const [karpenterRequiredTrigger, setKarpenterRequiredTrigger] = useState(null);
  const [karpenterModalInstalling, setKarpenterModalInstalling] = useState(false);
  const [nativeSpotStatus, setNativeSpotStatus] = useState(null);
  const [fetchError, setFetchError] = useState(null);
  const navigate = useNavigate();

  const recByNode = useMemo(() => { const m = {}; nodeRecommendations.forEach(r => { if (r.node_name) m[r.node_name] = r; }); return m; }, [nodeRecommendations]);
  const inFlightNodeIds = useMemo(() => { const s = new Set(); rebalancingActions.filter(a => ['in_progress','waiting_agent'].includes(a.status)).forEach(a => { const id = a.instance_id || a.action_metadata?.instance_id; if (id) s.add(id); }); return s; }, [rebalancingActions]);

  useEffect(() => { if (clusterId) fetchClusterDetails(); }, [clusterId]);
  useEffect(() => { optSettingsRef.current = optSettings; }, [optSettings]);

  useEffect(() => {
    if (!clusterId) return;
    let tick = 0;
    const poll = async () => {
      try {
        tick++;
        const _rs = !!optSettingsRef.current?.automation_controls?.auto_rightsizing_enabled;
        const [nR, rbR, recR] = await Promise.allSettled([clusterAPI.getNodesDetailed(clusterId), ascpaiAPI.getRebalancingStatus(clusterId), ascpaiAPI.getNodeRecommendations(clusterId, { useRightsized: _rs })]);
        if (nR.status === 'fulfilled' && nR.value.data) setNodesDetailed(nR.value.data);
        if (rbR.status === 'fulfilled' && Array.isArray(rbR.value.data)) setRebalancingActions(rbR.value.data);
        if (recR.status === 'fulfilled' && recR.value.data) { const recs = recR.value.data?.recommendations; if (Array.isArray(recs) && recs.length > 0) setNodeRecommendations(recs); setKarpenterSimulation(recR.value.data?.karpenter_simulation || null); }
        if (tick % 2 === 0) {
          const [cR, mR, ctR, rsR, kR] = await Promise.allSettled([clusterAPI.getCluster(clusterId), metricsAPI.getClusterMetrics(clusterId), metricsAPI.getCostTimeSeries({ cluster_id: clusterId }), optimizationAPI.getRightsizing(clusterId), karpenterAPI.getInstallStatus(clusterId)]);
          if (cR.status === 'fulfilled' && cR.value.data) setCluster(cR.value.data);
          if (mR.status === 'fulfilled' && mR.value.data) setMetrics(mR.value.data);
          if (ctR.status === 'fulfilled' && ctR.value.data) setCostTrends(ctR.value.data);
          if (rsR.status === 'fulfilled') { const rs = rsR.value.data?.recommendations || rsR.value.data; if (Array.isArray(rs) && rs.length > 0) setRightsizing(rs); }
          if (kR.status === 'fulfilled' && kR.value?.data) setKarpenterInstallStatus(kR.value.data);
        }
      } catch (_) {}
    };
    const t = setInterval(poll, 30_000);
    return () => clearInterval(t);
  }, [clusterId]);

  useEffect(() => {
    if (!showKarpenterRequiredModal || !clusterId) return;
    const t = setInterval(async () => {
      try { const r = await karpenterAPI.getInstallStatus(clusterId); if (r?.data) { setKarpenterInstallStatus(r.data); if (r.data.karpenter_installed && karpenterRequiredTrigger) { setShowKarpenterRequiredModal(false); setKarpenterModalInstalling(false); setOptSettings(p => ({ ...p, automation_controls: { ...p?.automation_controls, [karpenterRequiredTrigger]: true } })); toast.success('Karpenter detected — toggle enabled!'); } } } catch (_) {}
    }, 5000);
    return () => clearInterval(t);
  }, [showKarpenterRequiredModal, clusterId, karpenterRequiredTrigger]);

  const fetchClusterDetails = async () => {
    if (!cluster) setLoading(true);
    setFetchError(null);
    try {
      const [cR, mR, polR, schR, uR, wR, nR, oR, recR, rbR, rsR, ctR] = await Promise.allSettled([
        clusterAPI.getCluster(clusterId), metricsAPI.getClusterMetrics(clusterId),
        policyAPI.getPolicy(clusterId), hibernationAPI.getByCluster(clusterId),
        clusterAPI.getUtilization(clusterId), clusterAPI.getWorkloadType(clusterId),
        clusterAPI.getNodesDetailed(clusterId), clusterAPI.getOptimizationSettings(clusterId),
        ascpaiAPI.getNodeRecommendations(clusterId), ascpaiAPI.getRebalancingStatus(clusterId),
        optimizationAPI.getRightsizing(clusterId), metricsAPI.getCostTimeSeries({ cluster_id: clusterId }),
      ]);
      if (cR.status === 'fulfilled' && cR.value.data) setCluster(cR.value.data);
      if (mR.status === 'fulfilled' && mR.value.data) setMetrics(mR.value.data);
      if (polR.status === 'fulfilled') setPolicy(polR.value.data);
      if (schR.status === 'fulfilled') setSchedule(schR.value.data);
      if (uR.status === 'fulfilled' && uR.value.data) setUtilization(uR.value.data);
      if (nR.status === 'fulfilled' && nR.value.data) setNodesDetailed(nR.value.data);
      if (recR.status === 'fulfilled' && recR.value.data) { const recs = recR.value.data?.recommendations; if (Array.isArray(recs) && recs.length > 0) setNodeRecommendations(recs); if (recR.value.data?.karpenter_simulation) setKarpenterSimulation(recR.value.data.karpenter_simulation); }
      if (rbR.status === 'fulfilled' && Array.isArray(rbR.value.data)) setRebalancingActions(rbR.value.data);
      if (rsR.status === 'fulfilled') { const rs = rsR.value.data?.recommendations || rsR.value.data; if (Array.isArray(rs) && rs.length > 0) setRightsizing(rs); }
      if (ctR.status === 'fulfilled' && ctR.value.data) setCostTrends(ctR.value.data);
      if (oR.status === 'fulfilled') setOptSettings(oR.value.data || { optimization_strategy: { strategy_type: 'BALANCED', risk_ceiling_percent: 25, min_savings_percent: 15, risk_savings_tradeoff_pct: 20 } });
      try { const kR = await karpenterAPI.getInstallStatus(clusterId); setKarpenterInstallStatus(kR.data); if (!kR.data?.karpenter_installed) nativeSpotAPI.getStatus(clusterId).then(r => setNativeSpotStatus(r.data)).catch(() => {}); } catch (_) {}
    } catch (err) { toast.error('Failed to load cluster details'); setFetchError(err.message || 'Failed to load cluster details'); }
    finally { setLoading(false); }
  };

  const handleRefresh = async () => { setRefreshing(true); await fetchClusterDetails(); setRefreshing(false); toast.success('Cluster details refreshed'); };

  const _rsEnabled = !!optSettings?.automation_controls?.auto_rightsizing_enabled;
  useEffect(() => {
    if (!clusterId) return;
    ascpaiAPI.getNodeRecommendations(clusterId, { useRightsized: _rsEnabled }).then(r => { if (r.data) { const recs = r.data?.recommendations; if (Array.isArray(recs) && recs.length > 0) setNodeRecommendations(recs); setKarpenterSimulation(r.data?.karpenter_simulation || null); } }).catch(() => {});
  }, [clusterId, _rsEnabled]);

  const handleOptimize = async () => { if (!clusterId) return; try { await clusterAPI.optimize(clusterId); toast.success('Optimization triggered successfully'); } catch { toast.error('Failed to trigger optimization'); } };
  const handleFallback = async () => { setFallbackLoading(true); try { await clusterAPI.fallback(clusterId); toast.success('Cluster switched to On-Demand fallback for 12 hours'); fetchClusterDetails(); } catch { toast.error('Failed to trigger manual fallback'); } finally { setFallbackLoading(false); } };
  const handleDisconnectAgent = async () => { setAgentActionLoading(true); try { await clusterAPI.disconnectAgent(clusterId); toast.success('Agent disconnected.'); setShowDisconnectModal(false); fetchClusterDetails(); } catch { toast.error('Failed to disconnect agent'); } finally { setAgentActionLoading(false); } };
  const handleRemoveAgent = async () => { setAgentActionLoading(true); try { await clusterAPI.deleteCluster(clusterId); toast.success('Cluster and all data removed.'); setShowRemoveModal(false); window.dispatchEvent(new Event('refresh-clusters')); if (onClose) onClose(); } catch { toast.error('Failed to remove cluster'); } finally { setAgentActionLoading(false); } };
  const handleSaveOptSettings = async () => {
    if (!clusterId || !optSettings) return;
    setSavingOptSettings(true);
    const _prevRebalance = !!optSettings?.automation_controls?.auto_rebalance_enabled;
    try {
      await clusterAPI.updateOptimizationSettings(clusterId, optSettings);
      toast.success("Optimization settings saved!");
      if (_prevRebalance) {
        toast('Auto-Rebalancer active — ML engine will evaluate nodes within ~60 seconds', { icon: '⚡', duration: 5000 });
      }
    } catch (err) {
      const _detail = err?.response?.data?.detail || err?.message || '';
      if (err?.response?.status === 400 && _detail.toLowerCase().includes('karpenter')) {
        toast.error(_detail, { duration: 6000 });
        setShowKarpenterRequiredModal(true);
        setKarpenterRequiredTrigger(
          _detail.includes('rebalancing') ? 'auto_rebalance_enabled' : 'auto_rightsizing_enabled'
        );
      } else {
        toast.error('Failed to save settings');
      }
    } finally {
      setSavingOptSettings(false);
    }
  };
  const handleOptConfigChange = (section, key, value) => {
    if (section === 'automation_controls' && (key === 'auto_rebalance_enabled' || key === 'auto_rightsizing_enabled') && value === true && !karpenterInstallStatus?.karpenter_installed) {
      setKarpenterRequiredTrigger(key); setKarpenterModalInstalling(false); setShowKarpenterRequiredModal(true); return;
    }
    setOptSettings(p => ({ ...p, [section]: { ...p[section], [key]: value } }));
  };

  if (!clusterId) return null;
  if (loading && !cluster) return <div className="flex-1 flex items-center justify-center bg-white"><div className="flex flex-col items-center gap-3"><div className="animate-spin rounded-full h-10 w-10 border-b-2 border-blue-600" /><span className="text-sm text-gray-500">Loading cluster details…</span></div></div>;

  return (
    <div className="flex-1 overflow-y-auto bg-white flex flex-col">
      {fetchError && !loading && (
        <div className="mx-8 mt-4 p-4 bg-red-50 border border-red-200 rounded-lg flex items-center justify-between">
          <div><p className="text-sm font-medium text-red-800">Failed to load cluster details</p><p className="text-xs text-red-600 mt-0.5">{fetchError}</p></div>
          <button onClick={handleRefresh} className="px-3 py-1.5 text-xs font-medium text-red-700 bg-white border border-red-300 rounded-md hover:bg-red-50">Retry</button>
        </div>
      )}
      <div className="w-full">
        {/* Header */}
        <header className="sticky top-0 bg-white border-b border-gray-200 px-8 py-4 flex items-center justify-between z-20">
          <div className="flex items-center space-x-4">
            <h1 className="text-[17px] font-bold text-[#111318] tracking-tight m-0">{cluster?.name || 'Loading...'}</h1>
            <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${cluster?.status?.toLowerCase() === 'active' ? 'bg-green-100 text-green-800' : 'bg-orange-100 text-orange-800'}`}><span className={`w-2 h-2 mr-1.5 rounded-full ${cluster?.status?.toLowerCase() === 'active' ? 'bg-green-500' : 'bg-orange-500'}`} />{cluster?.status || 'Unknown'}</span>
            <div className="flex space-x-1 ml-4 hidden sm:flex">
              {[cluster?.provider || 'AWS', cluster?.region || 'Unknown', cluster?.k8s_version ? `K8S ${cluster.k8s_version}` : 'K8S 1.28'].map(l => <span key={l} className="px-2 py-0.5 bg-gray-100 text-gray-600 rounded text-[10px] font-medium border border-gray-200 uppercase">{l}</span>)}
            </div>
          </div>
          <div className="flex items-center space-x-3">
            <button className="px-4 py-2 border border-blue-600 text-blue-600 rounded-md text-sm font-medium hover:bg-blue-50 transition-colors" onClick={handleOptimize}>Update Agent</button>
            <button className="px-4 py-2 border border-gray-300 text-gray-700 rounded-md text-sm font-medium hover:bg-gray-50 flex items-center gap-1.5 transition-colors" onClick={handleRefresh} disabled={refreshing}><FiRefreshCw className={refreshing ? 'animate-spin' : ''} />Refresh</button>
            <button className="px-4 py-2 border border-red-200 text-red-600 rounded-md text-sm font-medium hover:bg-red-50 transition-colors" onClick={() => setShowRemoveModal(true)}>Remove</button>
          </div>
        </header>

        {/* Tabs */}
        <div className="bg-white border-b border-gray-200 px-8 sticky top-[69px] z-10">
          <nav className="flex space-x-8">
            {['Overview', 'Optimization Settings', 'Node Template', 'Activity Log'].map(tab => (
              <button key={tab} onClick={() => setActiveTab(tab)} className={`whitespace-nowrap py-4 px-1 border-b-2 font-medium text-sm transition-colors ${activeTab === tab ? 'border-blue-600 text-blue-600' : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'}`}>{tab}</button>
            ))}
          </nav>
        </div>

        <div className="p-6 space-y-6">
          {/* ── Overview tab ── */}
          {activeTab === 'Overview' && (
            <OverviewTab
              cluster={cluster} metrics={metrics} utilization={utilization}
              karpenterInstallStatus={karpenterInstallStatus} schedule={schedule} policy={policy}
              nodeRecommendations={nodeRecommendations} karpenterSimulation={karpenterSimulation}
              nodesDetailed={nodesDetailed} costTrends={costTrends} rightsizing={rightsizing}
              autoRightsizingEnabled={!!optSettings?.automation_controls?.auto_rightsizing_enabled}
              autoRebalanceEnabled={!!optSettings?.automation_controls?.auto_rebalance_enabled}
              onInstallKarpenter={() => { toast.loading(`Installing Karpenter on ${cluster?.name}...`, { id: 'karp' }); karpenterAPI.installKarpenter(clusterId).then(() => { toast.success('Karpenter installation triggered', { id: 'karp' }); fetchClusterDetails(); }).catch(() => toast.error('Failed to install Karpenter', { id: 'karp' })); }}
              onInstallKeda={() => { toast.loading(`Installing KEDA on ${cluster?.name}...`, { id: 'keda' }); kedaAPI.install(clusterId).then(() => { toast.success('KEDA installation triggered', { id: 'keda' }); fetchClusterDetails(); }).catch(() => toast.error('Failed to install KEDA', { id: 'keda' })); }}
              onManagePolicies={() => setActiveTab('Optimization Settings')}
            />
          )}

          {/* ── Optimization Settings tab ── */}
          {activeTab === 'Optimization Settings' && (
            <div className="space-y-5">
              {optSettings && (
                <div className={`flex items-center gap-3 px-4 py-3 rounded-lg border ${optSettings.automation_controls?.auto_rebalance_enabled ? 'bg-green-50 border-green-200 text-green-800' : 'bg-gray-100 border-gray-300 text-gray-500'}`}>
                  <span className={`w-2.5 h-2.5 rounded-full shrink-0 ${optSettings.automation_controls?.auto_rebalance_enabled ? 'bg-green-500 animate-pulse' : 'bg-gray-400'}`} />
                  <span className="font-semibold text-sm">{optSettings.automation_controls?.auto_rebalance_enabled ? 'ENABLED' : 'DISABLED'}</span>
                  <span className="text-sm">{optSettings.automation_controls?.auto_rebalance_enabled ? 'Auto-rebalancer is active — ML engine monitors and moves nodes to optimal spot pools' : 'All automation paused — manual mode only'}</span>
                </div>
              )}
              <Card>
                <div className="flex items-center justify-between mb-3">
                  <h3 className="text-sm font-semibold text-gray-900 flex items-center gap-1.5"><FiSettings className="w-3.5 h-3.5 text-blue-600" />Optimization Engine Settings</h3>
                  {optSettings && <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full tracking-wide ${optSettings.automation_controls?.auto_rebalance_enabled ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-500'}`}>{optSettings.automation_controls?.auto_rebalance_enabled ? (optSettings.automation_controls?.auto_rightsizing_enabled ? 'FULL AUTO' : 'REBALANCE ACTIVE') : 'DISABLED'}</span>}
                </div>
                <div className="space-y-0 divide-y divide-gray-100">
                  {/* CPU Architecture */}
                  <div className="flex items-center justify-between py-2.5">
                    <div><div className="text-xs font-semibold text-gray-800">CPU Architecture</div><div className="text-[11px] text-gray-500 mt-0.5">Select which CPU architectures to include in pool selection and rebalancing</div></div>
                    <select value={optSettings?.automation_controls?.architecture_preference ?? 'both'} onChange={e => handleOptConfigChange("automation_controls", "architecture_preference", e.target.value)} className="text-xs border border-gray-200 rounded px-2 py-1 text-gray-700 focus:outline-none focus:ring-1 focus:ring-blue-400 ml-4 shrink-0">
                      <option value="both">Both (x86 + ARM)</option><option value="amd64">x86 / AMD64 Only</option><option value="arm64">ARM64 / Graviton Only</option>
                    </select>
                  </div>
                  {/* Diversify Spot Pools */}
                  <div className="flex items-center justify-between py-2.5">
                    <div><div className="text-xs font-semibold text-gray-800">Diversify Spot Pools</div><div className="text-[11px] text-gray-500 mt-0.5">Spread across multiple instance pools to lower interruption risk</div></div>
                    <Toggle checked={!!optSettings?.automation_controls?.diversify_pools} onChange={e => handleOptConfigChange("automation_controls", "diversify_pools", e.target.checked)} color="indigo" />
                  </div>
                  {optSettings?.automation_controls?.diversify_pools && (
                    <div className="ml-4 pl-3 border-l-2 border-indigo-100 py-2 space-y-3">
                      <div>
                        <div className="flex items-center justify-between mb-1"><div><div className="text-[12px] font-medium text-gray-700">Max Family Diversification Cap</div><div className="text-[10px] text-gray-400 mt-0.5">Limit instances of the same family (e.g. c5, m5) to a % of total nodes.</div></div><span className="text-xs font-bold text-indigo-600 ml-4 shrink-0">{optSettings?.automation_controls?.max_family_diversification_cap_pct ?? 40}%</span></div>
                        <input type="range" min="10" max="100" step="5" value={optSettings?.automation_controls?.max_family_diversification_cap_pct ?? 40} onChange={e => handleOptConfigChange("automation_controls", "max_family_diversification_cap_pct", parseInt(e.target.value))} className="w-full accent-indigo-600" />
                      </div>
                      <div>
                        <div className="flex items-center justify-between mb-1"><div><div className="text-[12px] font-medium text-gray-700">Instance Type Diversification</div></div><span className="text-xs font-bold text-indigo-600 ml-4 shrink-0">{optSettings?.automation_controls?.instance_type_diversification_pct ?? 100}%</span></div>
                        <input type="range" min="0" max="100" step="10" value={optSettings?.automation_controls?.instance_type_diversification_pct ?? 100} onChange={e => handleOptConfigChange("automation_controls", "instance_type_diversification_pct", parseInt(e.target.value))} className="w-full accent-indigo-600" />
                        <div className="flex justify-between text-[9px] text-gray-400 mt-1"><span>0% — All same type OK</span><span>100% — All unique types</span></div>
                      </div>
                    </div>
                  )}
                  {/* Auto Rebalance */}
                  <div className="flex items-center justify-between py-2.5">
                    <div>
                      <div className="text-xs font-semibold text-gray-800 flex items-center gap-1.5">
                        Auto Rebalance <span className="text-[10px] font-normal text-blue-600">(ML Spot Optimization)</span>
                        {!karpenterInstallStatus?.karpenter_installed && <span className="text-[9px] font-bold px-1.5 py-0.5 rounded bg-amber-100 text-amber-700 border border-amber-200">Requires Karpenter</span>}
                      </div>
                      <div className="text-[11px] text-gray-500 mt-0.5">Automatically replace on-demand nodes with ML-predicted stable spot instances</div>
                    </div>
                    <Toggle checked={!!optSettings?.automation_controls?.auto_rebalance_enabled} onChange={e => handleOptConfigChange("automation_controls", "auto_rebalance_enabled", e.target.checked)} color="blue" disabled={!karpenterInstallStatus?.karpenter_installed && !optSettings?.automation_controls?.auto_rebalance_enabled} />
                  </div>
                  {optSettings?.automation_controls?.auto_rebalance_enabled && (
                    <div className="ml-4 pl-3 border-l-2 border-gray-100 py-2 space-y-2.5">
                      <div className="flex items-center justify-between"><div><div className="text-[12px] font-medium text-gray-700">Maintain Warm Standby</div><div className="text-[10px] text-gray-400 mt-0.5">Keep 1 pre-warmed spot node for instant failover</div></div><Toggle checked={!!optSettings?.automation_controls?.maintain_standby} onChange={e => handleOptConfigChange("automation_controls", "maintain_standby", e.target.checked)} color="teal" /></div>
                      <div className="grid grid-cols-2 gap-3">
                        <div><div className="text-[11px] font-medium text-gray-700 mb-1">Failure Cooldown</div><div className="flex items-center gap-1.5"><input type="number" value={optSettings?.automation_controls?.failure_cooldown_minutes ?? 30} onChange={e => handleOptConfigChange("automation_controls", "failure_cooldown_minutes", parseInt(e.target.value) || 30)} className="w-14 text-xs border border-gray-200 rounded px-2 py-1" /><span className="text-[10px] text-gray-400">min</span></div></div>
                        <div><div className="text-[11px] font-medium text-gray-700 mb-1">Post-Rebalance Cooldown</div><div className="flex items-center gap-1.5"><input type="number" value={optSettings?.automation_controls?.cooldown_override_minutes ?? 60} onChange={e => handleOptConfigChange("automation_controls", "cooldown_override_minutes", parseInt(e.target.value) || 60)} className="w-14 text-xs border border-gray-200 rounded px-2 py-1" /><span className="text-[10px] text-gray-400">min</span></div></div>
                      </div>
                    </div>
                  )}
                  {/* Check interval */}
                  <div className="flex items-center justify-between py-2.5">
                    <div><div className="text-xs font-semibold text-gray-800">Check Cycle Interval</div><div className="text-[11px] text-gray-500 mt-0.5">How often the rebalancer evaluates nodes (min 15s)</div></div>
                    <div className="flex items-center gap-1.5 ml-4 shrink-0"><input type="number" min="15" step="15" value={optSettings?.automation_controls?.check_interval_seconds ?? 15} onChange={e => handleOptConfigChange("automation_controls", "check_interval_seconds", Math.max(15, parseInt(e.target.value) || 15))} className="w-14 text-xs border border-gray-200 rounded px-2 py-1" /><span className="text-[10px] text-gray-400">sec</span></div>
                  </div>
                  {/* Auto Right-Sizing */}
                  <div className="flex items-center justify-between py-2.5">
                    <div>
                      <div className="text-xs font-semibold text-gray-800 flex items-center gap-1.5">
                        Auto Right-Sizing
                        {!karpenterInstallStatus?.karpenter_installed && <span className="text-[9px] font-bold px-1.5 py-0.5 rounded bg-amber-100 text-amber-700 border border-amber-200">Requires Karpenter</span>}
                      </div>
                      <div className="text-[11px] text-gray-500 mt-0.5">Automatically scale down over-provisioned pods based on historical metrics</div>
                    </div>
                    <Toggle checked={!!optSettings?.automation_controls?.auto_rightsizing_enabled} onChange={e => handleOptConfigChange("automation_controls", "auto_rightsizing_enabled", e.target.checked)} color="blue" disabled={!karpenterInstallStatus?.karpenter_installed && !optSettings?.automation_controls?.auto_rightsizing_enabled} />
                  </div>
                  {!!optSettings?.automation_controls?.auto_rightsizing_enabled && (
                    <div className="p-3 bg-gradient-to-br from-teal-50 to-cyan-50 rounded-xl border border-teal-200 ml-2">
                      <div className="flex justify-between items-center mb-2"><label className="text-xs font-semibold text-gray-800">Min Topology Spread</label><span className="text-lg font-bold text-teal-700">{optSettings?.automation_controls?.min_topology_spread ?? 1}</span></div>
                      <input type="range" min="1" max="5" step="1" value={optSettings?.automation_controls?.min_topology_spread ?? 1} onChange={e => handleOptConfigChange("automation_controls", "min_topology_spread", +e.target.value)} className="w-full h-2 bg-teal-200 rounded-lg appearance-none cursor-pointer accent-teal-600" />
                      <div className="flex justify-between text-[10px] text-gray-400 mt-1"><span>1</span><span>5</span></div>
                      <p className="text-[11px] text-gray-500 mt-2">Minimum number of nodes across different AZs during right-sizing consolidation. Higher values increase HA but may limit cost savings.</p>
                    </div>
                  )}
                  {/* Optimization Target */}
                  {(() => {
                    const locked = !!optSettings?.automation_controls?.auto_rebalance_enabled && !!optSettings?.automation_controls?.auto_rightsizing_enabled;
                    return (
                      <div className="flex items-center justify-between py-2.5">
                        <div><div className="text-xs font-semibold text-gray-800">Optimization Target</div><div className="text-[11px] text-gray-500 mt-0.5">{locked ? 'Locked to Spot — synergy mode active' : 'Billing model for right-sized node replacements'}</div></div>
                        <div className="flex items-center gap-2 ml-4 shrink-0">
                          {locked && <span className="text-[10px] text-amber-700 bg-amber-50 border border-amber-200 rounded px-1.5 py-0.5">Locked</span>}
                          <select className={`text-xs border rounded px-2 py-1 focus:outline-none ${locked ? 'bg-gray-100 border-gray-200 text-gray-400 cursor-not-allowed' : 'bg-white border-gray-300 text-gray-700'}`} value={locked ? 'spot' : (optSettings?.automation_controls?.optimization_target ?? 'spot')} onChange={e => !locked && handleOptConfigChange("automation_controls", "optimization_target", e.target.value)} disabled={locked}><option value="spot">Spot</option><option value="on_demand">On-Demand</option></select>
                        </div>
                      </div>
                    );
                  })()}
                  {/* Conservative Mode */}
                  <div className="flex items-center justify-between py-2.5">
                    <div><div className="text-xs font-semibold text-gray-800">Conservative Mode <span className="text-[10px] font-normal text-green-600">(Fresh Cluster Protection)</span></div><div className="text-[11px] text-gray-500 mt-0.5">Limit aggressive spot replacements during the first 24 hours</div></div>
                    <Toggle checked={optSettings?.automation_controls?.conservative_mode_enabled ?? true} onChange={e => handleOptConfigChange("automation_controls", "conservative_mode_enabled", e.target.checked)} color="green" />
                  </div>
                  {/* Manual Approval */}
                  <div className="flex items-center justify-between py-2.5">
                    <div><div className="text-xs font-semibold text-gray-800">Manual Approval Required <span className="text-[10px] font-normal text-gray-400">(RBAC)</span></div><div className="text-[11px] text-gray-500 mt-0.5">Route proposed changes to Team Lead / Org Admin before execution</div></div>
                    <Toggle checked={!!optSettings?.automation_controls?.manual_approval_required} onChange={e => handleOptConfigChange("automation_controls", "manual_approval_required", e.target.checked)} color="gray" />
                  </div>
                  {/* Rebalance Batch Size */}
                  <div className="pt-3 mt-1 border-t border-gray-100">
                    <div className="text-xs font-semibold text-gray-800 mb-3">Rebalance Batch Size</div>
                    <div className="flex items-center justify-between py-2">
                      <div><div className="text-[12px] font-medium text-gray-700">Respect PodDisruptionBudgets</div><div className="text-[10px] text-gray-400 mt-0.5">Cap batch size to PDB-safe limit to prevent service disruption</div></div>
                      <Toggle checked={optSettings?.stateless_rules?.respect_pdb_enabled ?? true} onChange={e => handleOptConfigChange("stateless_rules", "respect_pdb_enabled", e.target.checked)} color="blue" />
                    </div>
                    <div>
                      <div className="flex items-center justify-between mb-1"><label className="text-[12px] font-medium text-gray-700">Max Concurrent Node Replacements</label><span className="text-xs font-bold text-blue-600">{optSettings?.automation_controls?.max_batch_size ?? 1} {(optSettings?.automation_controls?.max_batch_size ?? 1) === 1 ? 'node' : 'nodes'}</span></div>
                      <input type="range" min="1" max="5" step="1" value={optSettings?.automation_controls?.max_batch_size ?? 1} onChange={e => handleOptConfigChange("automation_controls", "max_batch_size", parseInt(e.target.value))} className="w-full accent-blue-600" />
                      <div className="flex justify-between text-[9px] text-gray-400 mt-1"><span>1 (safest)</span><span>5 (fastest)</span></div>
                    </div>
                  </div>
                </div>
              </Card>

              {/* Risk vs Savings Controls */}
              <Card>
                <h3 className="text-sm font-semibold text-gray-900 flex items-center gap-1.5 mb-4"><FiClock className="w-3.5 h-3.5 text-blue-600" />Risk vs Savings Controls</h3>
                <div className="space-y-4">
                  <div>
                    <div className="flex items-center justify-between mb-1"><label className="text-xs font-medium text-gray-700">Risk Ceiling</label><span className="text-xs font-bold text-red-500">{optSettings?.optimization_strategy?.risk_ceiling_percent ?? 25}%</span></div>
                    <input type="range" min="5" max="50" step="5" value={optSettings?.optimization_strategy?.risk_ceiling_percent ?? 25} onChange={e => handleOptConfigChange("optimization_strategy", "risk_ceiling_percent", parseInt(e.target.value))} className="w-full accent-red-500" />
                    <div className="flex justify-between text-[9px] text-gray-400 mt-1"><span>5% (very safe)</span><span>50% (aggressive)</span></div>
                  </div>
                  <div>
                    <div className="flex items-center justify-between mb-1"><label className="text-xs font-medium text-gray-700">Min Savings Threshold</label><span className="text-xs font-bold text-green-600">{optSettings?.optimization_strategy?.min_savings_percent ?? 15}%</span></div>
                    <input type="range" min="5" max="50" step="5" value={optSettings?.optimization_strategy?.min_savings_percent ?? 15} onChange={e => handleOptConfigChange("optimization_strategy", "min_savings_percent", parseInt(e.target.value))} className="w-full accent-green-500" />
                    <div className="flex justify-between text-[9px] text-gray-400 mt-1"><span>5% (accept any savings)</span><span>50% (only big wins)</span></div>
                  </div>
                  <div>
                    <div className="flex items-center justify-between mb-1"><label className="text-xs font-medium text-gray-700">Risk/Savings Tradeoff Balance</label><span className="text-xs font-bold text-blue-600">{optSettings?.optimization_strategy?.risk_savings_tradeoff_pct ?? 20}%</span></div>
                    <input type="range" min="0" max="100" step="5" value={optSettings?.optimization_strategy?.risk_savings_tradeoff_pct ?? 20} onChange={e => handleOptConfigChange("optimization_strategy", "risk_savings_tradeoff_pct", parseInt(e.target.value))} className="w-full accent-blue-500" />
                    <div className="flex justify-between text-[9px] text-gray-400 mt-1"><span>0% (pure savings)</span><span>100% (pure safety)</span></div>
                  </div>
                </div>
              </Card>

              {/* Save Button */}
              <div className="flex justify-end pt-2">
                <button onClick={handleSaveOptSettings} disabled={savingOptSettings} className={`px-5 py-2.5 text-sm font-semibold text-white rounded-lg transition-colors ${savingOptSettings ? 'bg-gray-400 cursor-not-allowed' : 'bg-blue-600 hover:bg-blue-700'}`}>{savingOptSettings ? 'Saving...' : 'Save Settings'}</button>
              </div>

              {/* Danger Zone */}
              <div className="pt-4 border-t border-gray-100">
                <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-3">Danger Zone</h3>
                <div className="flex gap-3">
                  <button onClick={() => setShowDisconnectModal(true)} className="px-4 py-2 text-sm font-medium text-orange-600 bg-orange-50 border border-orange-200 rounded-lg hover:bg-orange-100 transition-colors">Disconnect Agent</button>
                  <button onClick={handleFallback} disabled={fallbackLoading} className="px-4 py-2 text-sm font-medium text-blue-600 bg-blue-50 border border-blue-200 rounded-lg hover:bg-blue-100 transition-colors disabled:opacity-50">{fallbackLoading ? 'Switching...' : 'Manual OD Fallback (12h)'}</button>
                </div>
              </div>
            </div>
          )}

          {/* ── Node Template tab ── */}
          {activeTab === 'Node Template' && <NodeTemplateTab clusterId={clusterId} />}

          {/* ── Activity Log tab ── */}
          {activeTab === 'Activity Log' && (
            <div className="space-y-3">
              {rebalancingActions.length === 0 ? (
                <div className="text-center py-12 text-gray-400"><FiActivity className="mx-auto mb-3 w-8 h-8 opacity-30" /><p className="text-sm">No rebalancing actions recorded yet.</p></div>
              ) : rebalancingActions.map((action, i) => (
                <div key={i} className="flex items-start gap-3 p-3 bg-gray-50 rounded-lg border border-gray-100">
                  <div className={`w-2 h-2 rounded-full mt-1.5 shrink-0 ${action.status === 'completed' ? 'bg-green-500' : action.status === 'failed' ? 'bg-red-500' : action.status === 'in_progress' ? 'bg-blue-500 animate-pulse' : 'bg-gray-400'}`} />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center justify-between gap-2"><span className="text-xs font-semibold text-gray-800 truncate">{action.action_type || 'Rebalance Action'}</span><span className={`text-[10px] font-bold px-1.5 py-0.5 rounded uppercase shrink-0 ${action.status === 'completed' ? 'bg-green-100 text-green-700' : action.status === 'failed' ? 'bg-red-100 text-red-700' : action.status === 'in_progress' ? 'bg-blue-100 text-blue-700' : 'bg-gray-100 text-gray-500'}`}>{action.status}</span></div>
                    {action.instance_id && <div className="text-[10px] text-gray-500 mt-0.5 font-mono">{action.instance_id}</div>}
                    {action.created_at && <div className="text-[10px] text-gray-400 mt-0.5">{new Date(action.created_at).toLocaleString()}</div>}
                    {action.error_message && <div className="text-[10px] text-red-600 mt-1">{action.error_message}</div>}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Disconnect Modal */}
      <ClusterDisconnectModal isOpen={showDisconnectModal} onClose={() => setShowDisconnectModal(false)} cluster={cluster} onConfirm={handleDisconnectAgent} />

      {/* Remove Confirmation Modal */}
      {showRemoveModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm">
          <div className="bg-white rounded-xl shadow-2xl max-w-md w-full mx-4 overflow-hidden">
            <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100 bg-red-50">
              <span className="font-semibold text-gray-900">Remove Cluster & Agent</span>
              <button onClick={() => setShowRemoveModal(false)} className="text-gray-400 hover:text-gray-600"><FiX className="w-5 h-5" /></button>
            </div>
            <div className="px-6 py-5">
              <p className="text-sm text-gray-600 mb-4">This will permanently remove <strong>{cluster?.name}</strong> and all associated data (metrics, policies, settings). The agent will be uninstalled from your cluster.</p>
              <p className="text-xs text-gray-500">This action cannot be undone. The cluster will reappear as "Discovered" on the next AWS scan.</p>
            </div>
            <div className="flex justify-end gap-3 px-6 py-4 border-t border-gray-100 bg-gray-50">
              <button onClick={() => setShowRemoveModal(false)} disabled={agentActionLoading} className="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-200 rounded-lg hover:bg-gray-50 disabled:opacity-50">Cancel</button>
              <button onClick={handleRemoveAgent} disabled={agentActionLoading} className="px-4 py-2 text-sm font-medium text-white bg-red-600 hover:bg-red-700 rounded-lg disabled:opacity-50 transition-colors">{agentActionLoading ? 'Removing...' : 'Remove Cluster'}</button>
            </div>
          </div>
        </div>
      )}

      {/* Karpenter Required Modal */}
      {showKarpenterRequiredModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm">
          <div className="bg-white rounded-xl shadow-2xl max-w-md w-full mx-4 p-6">
            <h3 className="text-base font-bold text-gray-900 mb-2">Karpenter Required</h3>
            <p className="text-sm text-gray-600 mb-4">Auto-rebalancing and Auto right-sizing require Karpenter to be installed on your cluster. Install it now to enable this feature.</p>
            <div className="flex gap-3 justify-end">
              <button onClick={() => { setShowKarpenterRequiredModal(false); setKarpenterModalInstalling(false); }} className="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-200 rounded-lg hover:bg-gray-50">Cancel</button>
              <button disabled={karpenterModalInstalling} onClick={() => { setKarpenterModalInstalling(true); toast.loading(`Installing Karpenter on ${cluster?.name}...`, { id: 'karp-req' }); karpenterAPI.installKarpenter(clusterId).then(() => { toast.success('Karpenter installing — polling for completion...', { id: 'karp-req' }); }).catch(() => { toast.error('Failed to start Karpenter installation', { id: 'karp-req' }); setKarpenterModalInstalling(false); }); }} className="px-4 py-2 text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 rounded-lg disabled:opacity-50">{karpenterModalInstalling ? 'Installing...' : 'Install Karpenter'}</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

// ─── ClustersPage (default export) ───────────────────────────────────────────
const ClustersPage = () => {
  const [clusters, setClusters] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [selectedClusterId, setSelectedClusterId] = useState(null);
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('all');
  const [discovering, setDiscovering] = useState(false);
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [clusterToDelete, setClusterToDelete] = useState(null);
  const navigate = useNavigate();

  const fetchClusters = useCallback(async () => {
    try {
      const res = await clusterAPI.listClusters();
      const raw = res.data?.clusters || res.data || [];
      const normalized = raw.map(c => ({
        ...c,
        status: c.agent_installed ? (c.status || 'healthy') : 'no-agent',
        agentInstalled: !!c.agent_installed,
        nodes: c.nodes || { total: c.node_count || 0, spot: 0, onDemand: 0 },
        cpu: c.cpu || { used: 0, total: 0, requested: 0 },
        memory: c.memory || { used: 0, total: 0, requested: 0 },
        cost: c.cost || { monthly: 0, savings: 0, potential: 0 },
        k8sVersion: c.k8s_version || c.kubernetes_version || 'Unknown',
        _nodeCountPending: !c.agent_installed,
      }));
      setClusters(normalized);
      if (!selectedClusterId && normalized.length > 0) setSelectedClusterId(normalized[0].id);
    } catch (e) { setError(e.message || 'Failed to load clusters'); }
    finally { setLoading(false); }
  }, [selectedClusterId]);

  useEffect(() => { fetchClusters(); }, []);
  useEffect(() => {
    const handler = () => fetchClusters();
    window.addEventListener('refresh-clusters', handler);
    return () => window.removeEventListener('refresh-clusters', handler);
  }, [fetchClusters]);
  useEffect(() => {
    const interval = setInterval(fetchClusters, 60_000);
    return () => clearInterval(interval);
  }, [fetchClusters]);

  const handleDiscoverClusters = async () => {
    setDiscovering(true);
    try {
      const res = await clusterAPI.discover();
      const data = res?.data ?? {};
      const failed = data?.failed_accounts ?? [];
      if (failed.length > 0) {
        failed.forEach(acct => {
          const err = acct.sync_error || 'Unknown error';
          const shortErr = err.length > 120 ? err.slice(0, 120) + '…' : err;
          toast.error(`Account ${acct.aws_account_id}: ${shortErr}`, { duration: 8000 });
        });
      } else {
        toast.success('Discovery triggered — checking for new clusters...');
      }
      setTimeout(fetchClusters, 5000);
    }
    catch { toast.error('Failed to trigger cluster discovery'); }
    finally { setDiscovering(false); }
  };

  const handleDeleteCluster = async (clusterId) => {
    try { await clusterAPI.deleteCluster(clusterId); toast.success('Cluster deleted successfully'); fetchClusters(); if (selectedClusterId === clusterId) setSelectedClusterId(null); }
    catch (e) { toast.error(`Failed to delete cluster: ${e.response?.data?.detail || e.message}`); }
  };

  const filtered = useMemo(() => {
    let list = clusters;
    if (search.trim()) { const q = search.toLowerCase(); list = list.filter(c => c.name.toLowerCase().includes(q) || c.region?.toLowerCase().includes(q)); }
    if (statusFilter !== 'all') list = list.filter(c => c.status === statusFilter);
    return list;
  }, [clusters, search, statusFilter]);

  const summary = useMemo(() => ({
    total: clusters.length,
    healthy: clusters.filter(c => c.status === 'healthy').length,
    withAgent: clusters.filter(c => c.agentInstalled).length,
    totalNodes: clusters.reduce((acc, c) => acc + (c.nodes?.total || 0), 0),
    totalSavings: clusters.reduce((acc, c) => acc + (c.cost?.savings || 0), 0),
  }), [clusters]);

  const selectedCluster = useMemo(() => clusters.find(c => c.id === selectedClusterId), [clusters, selectedClusterId]);

  if (loading) return (
    <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "60vh" }}>
      <div style={{ textAlign: "center" }}><div style={{ width: 40, height: 40, border: "3px solid #e4e6ea", borderTopColor: C.accent, borderRadius: "50%", animation: "spin 0.8s linear infinite", margin: "0 auto 12px" }} /><div style={{ fontSize: 13, color: C.muted }}>Loading clusters…</div></div>
    </div>
  );

  if (error) return (
    <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "60vh" }}>
      <div style={{ textAlign: "center" }}><div style={{ fontSize: 32, marginBottom: 12 }}>⚠</div><div style={{ fontSize: 15, fontWeight: 600, color: C.text, marginBottom: 6 }}>Failed to load clusters</div><div style={{ fontSize: 13, color: C.muted, marginBottom: 16 }}>{error}</div><button onClick={fetchClusters} style={{ padding: "8px 20px", borderRadius: 8, background: C.accent, border: "none", color: "#fff", fontSize: 13, cursor: "pointer" }}>Retry</button></div>
    </div>
  );

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100vh", background: C.bg, fontFamily: "'Inter', system-ui, sans-serif" }}>
      {/* Summary bar */}
      <div style={{ background: C.surface, borderBottom: `1px solid ${C.border}`, padding: "10px 20px", display: "flex", alignItems: "center", gap: 20, flexShrink: 0 }}>
        <div style={{ display: "flex", gap: 16, flex: 1 }}>
          {[
            { label: "Total Clusters", value: summary.total },
            { label: "Healthy",        value: summary.healthy,    color: C.green },
            { label: "With Agent",     value: summary.withAgent,  color: C.accent },
            { label: "Total Nodes",    value: summary.totalNodes },
            { label: "Monthly Savings", value: `$${summary.totalSavings.toLocaleString()}`, color: C.green },
          ].map(s => (
            <div key={s.label} style={{ display: "flex", flexDirection: "column", gap: 1 }}>
              <span style={{ fontSize: 10, color: C.subtle, textTransform: "uppercase", letterSpacing: "0.06em", fontWeight: 500 }}>{s.label}</span>
              <span style={{ fontSize: 16, fontWeight: 700, color: s.color || C.text, letterSpacing: "-0.3px" }}>{s.value}</span>
            </div>
          ))}
        </div>
        <button onClick={handleDiscoverClusters} disabled={discovering} style={{ display: "flex", alignItems: "center", gap: 6, padding: "7px 14px", borderRadius: 8, border: `1px solid ${C.border}`, background: C.surface, fontSize: 12, color: C.muted, cursor: discovering ? "not-allowed" : "pointer", fontFamily: "inherit", opacity: discovering ? 0.6 : 1 }}>
          <FiRefreshCw style={{ width: 12, height: 12, animation: discovering ? "spin 0.8s linear infinite" : "none" }} />{discovering ? "Discovering…" : "Discover Clusters"}
        </button>
      </div>

      {/* Master-detail layout */}
      <div style={{ display: "flex", flex: 1, overflow: "hidden" }}>
        {/* Left sidebar — cluster list */}
        <div style={{ width: 260, flexShrink: 0, background: C.surface, borderRight: `1px solid ${C.border}`, display: "flex", flexDirection: "column", overflow: "hidden" }}>
          {/* Search + filter */}
          <div style={{ padding: "10px 12px", borderBottom: `1px solid ${C.border}`, flexShrink: 0 }}>
            <input type="text" value={search} onChange={e => setSearch(e.target.value)} placeholder="Search clusters…" style={{ width: "100%", padding: "7px 10px", borderRadius: 7, border: `1px solid ${C.border}`, fontSize: 12, color: C.text, background: C.bg, fontFamily: "inherit", boxSizing: "border-box", outline: "none" }} />
            <div style={{ display: "flex", gap: 4, marginTop: 7, flexWrap: "wrap" }}>
              {['all', 'healthy', 'warning', 'degraded', 'no-agent'].map(s => (
                <button key={s} onClick={() => setStatusFilter(s)} style={{ padding: "3px 8px", borderRadius: 5, border: `1px solid ${statusFilter === s ? C.accent : C.border}`, background: statusFilter === s ? C.accentLight : "transparent", fontSize: 10, color: statusFilter === s ? C.accent : C.muted, cursor: "pointer", fontFamily: "inherit", fontWeight: statusFilter === s ? 600 : 400 }}>
                  {s === 'all' ? 'All' : s === 'no-agent' ? 'No Agent' : s.charAt(0).toUpperCase() + s.slice(1)}
                </button>
              ))}
            </div>
          </div>

          {/* Cluster list */}
          <div style={{ flex: 1, overflow: "auto", padding: "8px 10px" }}>
            {filtered.length === 0 ? (
              <div style={{ textAlign: "center", padding: "32px 16px", color: C.subtle }}>
                <div style={{ fontSize: 24, marginBottom: 8 }}>⬡</div>
                <div style={{ fontSize: 12 }}>{search || statusFilter !== 'all' ? 'No clusters match your filter' : 'No clusters found'}</div>
                {clusters.length === 0 && <button onClick={handleDiscoverClusters} style={{ marginTop: 12, padding: "7px 14px", borderRadius: 8, background: C.accent, border: "none", color: "#fff", fontSize: 12, cursor: "pointer", fontFamily: "inherit" }}>Discover Clusters</button>}
              </div>
            ) : filtered.map(cluster => (
              <ClusterListItem key={cluster.id} cluster={cluster} selected={selectedClusterId === cluster.id} onClick={() => setSelectedClusterId(cluster.id)} />
            ))}
          </div>
        </div>

        {/* Right panel — detail */}
        <div style={{ flex: 1, overflow: "hidden", display: "flex", flexDirection: "column" }}>
          {!selectedClusterId || !selectedCluster ? (
            <div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center", color: C.subtle }}>
              <div style={{ textAlign: "center" }}><div style={{ fontSize: 40, marginBottom: 12, opacity: 0.2 }}>⬡</div><div style={{ fontSize: 14, color: C.muted }}>Select a cluster to view details</div></div>
            </div>
          ) : selectedCluster.agentInstalled ? (
            <ClusterDetails clusterId={selectedClusterId} onClose={() => setSelectedClusterId(null)} />
          ) : (
            <NoAgentDetail cluster={selectedCluster} onClose={() => { setSelectedClusterId(null); fetchClusters(); }} />
          )}
        </div>
      </div>

      {/* Delete Modal */}
      <ClusterDeleteModal isOpen={showDeleteModal} onClose={() => { setShowDeleteModal(false); setClusterToDelete(null); }} cluster={clusterToDelete} onConfirm={handleDeleteCluster} />

      <style>{`@keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }`}</style>
    </div>
  );
};

export default ClustersPage;
