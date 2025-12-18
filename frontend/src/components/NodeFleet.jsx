
import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import {
    Activity, AlertTriangle, ArrowLeft, BarChart2, CheckCircle2, ChevronDown, ChevronRight,
    Circle, Clock, Cpu, Filter, Globe, History, Info, Layers, Layout, LayoutDashboard,
    MoreHorizontal, PieChart as PieIcon, Play, Plus, RefreshCw, Search, Server, Settings,
    Shield, Sliders, Terminal, Trash2, X, Zap, ChevronLeft, Database, ExternalLink,
    Maximize2, Minimize2, ScrollText, Users, Lock, Eye, Download, FileText, ShieldCheck, MinusCircle
} from 'lucide-react';
import {
    Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, Legend, Line, LineChart,
    Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis
} from 'recharts';
import { cn } from "../lib/utils";
import api from '../services/api';

// --- Helpers & Visual Components ---

const StatusBadge = ({ status }) => {
    const styles = {
        Active: "bg-emerald-50 text-emerald-700 border-emerald-200",
        Draining: "bg-amber-50 text-amber-700 border-amber-200",
        Stopped: "bg-slate-50 text-slate-700 border-slate-200",
    };
    return (
        <span className={cn("px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider border rounded-sm", styles[status] || styles.Stopped)}>
            {status}
        </span>
    );
};

const RiskBadge = ({ risk }) => {
    const styles = {
        Low: "bg-emerald-50 text-emerald-700 border-emerald-200",
        Medium: "bg-yellow-50 text-yellow-700 border-yellow-200",
        High: "bg-red-50 text-red-700 border-red-200",
        Critical: "bg-rose-100 text-rose-800 border-rose-200",
    };
    return (
        <span className={cn("px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider border rounded-sm", styles[risk] || styles.Medium)}>
            {risk} Risk
        </span>
    );
};

const StressBar = ({ value }) => (
    <div className="flex items-center space-x-2 w-full max-w-[120px]">
        <div className="flex-1 h-1.5 bg-slate-100 rounded-full overflow-hidden">
            <div
                className={cn("h-full rounded-full transition-all duration-500",
                    value > 80 ? "bg-red-500" : value > 50 ? "bg-yellow-500" : "bg-emerald-500"
                )}
                style={{ width: `${value}%` }}
            />
        </div>
        <span className="text-[10px] font-mono text-slate-500 w-6 text-right">{value}%</span>
    </div>
);

const AnimatedCounter = ({ value, duration = 1000 }) => {
    const [count, setCount] = useState(0);

    useEffect(() => {
        let start = 0;
        const end = value; // Target value
        if (start === end) return;

        const startTime = performance.now();

        const animate = (currentTime) => {
            const elapsed = currentTime - startTime;
            const progress = Math.min(elapsed / duration, 1);
            // Ease out quart
            const ease = 1 - Math.pow(1 - progress, 4);

            setCount(Math.floor(start + (end - start) * ease));

            if (progress < 1) {
                requestAnimationFrame(animate);
            } else {
                setCount(end); // Ensure exact end value
            }
        };

        requestAnimationFrame(animate);
    }, [value, duration]);

    return count;
};

const Switch = ({ checked, onChange }) => (
    <button
        onClick={() => onChange(!checked)}
        className={cn("w-9 h-5 rounded-full transition-colors relative", checked ? "bg-blue-600" : "bg-slate-300")}
    >
        <div className={cn("w-3.5 h-3.5 bg-white rounded-full absolute top-0.5 transition-all shadow-sm", checked ? "left-5" : "left-0.5")} />
    </button>
);

// --- Sub-Components (View Modules) ---

const UnregisteredInstances = () => {
    const [instances, setInstances] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [decisions, setDecisions] = useState({});

    // Fetch real unregistered instances from governance API
    useEffect(() => {
        const fetchUnregistered = async () => {
            try {
                setLoading(true);
                const data = await api.getUnauthorizedInstances();
                setInstances(data || []);
                setError(null);
            } catch (err) {
                console.error("Failed to load unregistered instances:", err);
                setError("Failed to load unregistered instances");
                setInstances([]);
            } finally {
                setLoading(false);
            }
        };
        fetchUnregistered();
    }, []);

    const handleDecision = (id, decision) => {
        setDecisions(prev => ({ ...prev, [id]: decision }));
        // TODO: Add API call to persist decision
    };

    return (
        <div className="bg-white border border-slate-200 rounded-lg shadow-sm p-6 mb-8 animate-in fade-in slide-in-from-bottom-2">
            <div className="flex items-center space-x-2 mb-4">
                <div className="p-2 bg-amber-50 rounded-lg">
                    <AlertTriangle className="w-5 h-5 text-amber-600" />
                </div>
                <div>
                    <h3 className="text-lg font-bold text-slate-900">Unregistered Instances</h3>
                    <p className="text-xs text-slate-500">Nodes running outside of managed clusters</p>
                </div>
            </div>

            <div className="overflow-hidden rounded-lg border border-slate-200">
                <table className="w-full text-left text-sm">
                    <thead className="bg-slate-50 border-b border-slate-200">
                        <tr>
                            <th className="px-4 py-3 font-bold text-slate-500 uppercase tracking-wider text-[10px]">Instance ID</th>
                            <th className="px-4 py-3 font-bold text-slate-500 uppercase tracking-wider text-[10px]">Region/AZ</th>
                            <th className="px-4 py-3 font-bold text-slate-500 uppercase tracking-wider text-[10px]">Type</th>
                            <th className="px-4 py-3 font-bold text-slate-500 uppercase tracking-wider text-[10px]">Launch Time</th>
                            <th className="px-4 py-3 font-bold text-slate-500 uppercase tracking-wider text-[10px] text-right">Action</th>
                        </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100 bg-white">
                        {loading ? (
                            <tr>
                                <td colSpan={5} className="px-4 py-8 text-center text-slate-400 text-xs">
                                    <RefreshCw className="w-5 h-5 mx-auto mb-2 animate-spin text-blue-500" />
                                    Loading unregistered instances...
                                </td>
                            </tr>
                        ) : error ? (
                            <tr>
                                <td colSpan={5} className="px-4 py-8 text-center text-red-600 text-xs">
                                    <AlertTriangle className="w-5 h-5 mx-auto mb-2" />
                                    {error}
                                </td>
                            </tr>
                        ) : instances.length === 0 ? (
                            <tr>
                                <td colSpan={5} className="px-4 py-8 text-center text-slate-400 text-xs italic">
                                    No unregistered instances found. All instances are properly tracked.
                                </td>
                            </tr>
                        ) : instances.map(inst => (
                            <tr key={inst.id} className="hover:bg-slate-50 transition-colors">
                                <td className="px-4 py-3 font-mono text-xs font-medium text-slate-700 flex items-center">
                                    <Server className="w-3 h-3 mr-2 text-slate-400" />
                                    {inst.id}
                                </td>
                                <td className="px-4 py-3 text-xs text-slate-600">
                                    <span className="font-bold text-slate-900">{inst.region}</span>
                                    <span className="text-slate-400 mx-1">/</span>
                                    {inst.zone}
                                </td>
                                <td className="px-4 py-3">
                                    <span className="px-1.5 py-0.5 bg-slate-100 border border-slate-200 rounded text-[10px] font-mono font-bold text-slate-600">
                                        {inst.type}
                                    </span>
                                </td>
                                <td className="px-4 py-3 text-xs text-slate-600 font-mono">
                                    {inst.launchTime}
                                </td>
                                <td className="px-4 py-3 text-right">
                                    <div className="inline-flex bg-slate-100 rounded-lg p-0.5 border border-slate-200">
                                        <button
                                            onClick={() => handleDecision(inst.id, 'authorized')}
                                            className={cn(
                                                "px-3 py-1 text-[10px] font-bold rounded-md transition-all flex items-center gap-1",
                                                decisions[inst.id] === 'authorized' ? "bg-white text-emerald-600 shadow-sm border border-emerald-100" : "text-slate-500 hover:text-slate-700"
                                            )}
                                        >
                                            <ShieldCheck className="w-3 h-3" />
                                            Authorize
                                        </button>
                                        <button
                                            onClick={() => handleDecision(inst.id, 'unauthorized')}
                                            className={cn(
                                                "px-3 py-1 text-[10px] font-bold rounded-md transition-all flex items-center gap-1",
                                                decisions[inst.id] === 'unauthorized' ? "bg-white text-red-600 shadow-sm border border-red-100" : "text-slate-500 hover:text-slate-700"
                                            )}
                                        >
                                            <MinusCircle className="w-3 h-3" />
                                            Unauthorize
                                        </button>
                                    </div>
                                </td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>
            <div className="mt-3 flex items-center gap-2 text-[10px] text-slate-400">
                <Info className="w-3 h-3" />
                <span>Unauthorized instances will be terminated upon clicking Apply.</span>
            </div>
        </div>
    );
};

const UnmappedVolumes = () => {
    const [volumes, setVolumes] = useState([]); // Empty state demo
    const deleteVolume = (id) => setVolumes(prev => prev.filter(v => v.id !== id));

    return (
        <div className="bg-white border border-slate-200 rounded-lg shadow-sm p-6 mb-8 animate-in fade-in slide-in-from-bottom-2">
            <div className="flex items-center space-x-2 mb-4">
                <div className="p-2 bg-slate-100 rounded-lg">
                    <Database className="w-5 h-5 text-slate-600" />
                </div>
                <div>
                    <h3 className="text-lg font-bold text-slate-900">Unmapped Volumes</h3>
                    <p className="text-xs text-slate-500">Orphaned EBS volumes accruing costs</p>
                </div>
            </div>

            <div className="overflow-hidden rounded-lg border border-slate-200">
                <table className="w-full text-left text-sm">
                    <thead className="bg-slate-50 border-b border-slate-200">
                        <tr>
                            <th className="px-4 py-3 font-bold text-slate-500 uppercase tracking-wider text-[10px]">Volume ID</th>
                            <th className="px-4 py-3 font-bold text-slate-500 uppercase tracking-wider text-[10px]">Size</th>
                            <th className="px-4 py-3 font-bold text-slate-500 uppercase tracking-wider text-[10px]">Type</th>
                            <th className="px-4 py-3 font-bold text-slate-500 uppercase tracking-wider text-[10px]">Created</th>
                            <th className="px-4 py-3 font-bold text-slate-500 uppercase tracking-wider text-[10px] text-right">Action</th>
                        </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100 bg-white">
                        {volumes.length === 0 ? (
                            <tr>
                                <td colSpan={5} className="px-4 py-8 text-center text-slate-400 text-xs italic">No unmapped volumes found.</td>
                            </tr>
                        ) : volumes.map(vol => (
                            <tr key={vol.id} className="hover:bg-slate-50 transition-colors">
                                <td className="px-4 py-3 font-mono text-xs font-medium text-slate-700">{vol.id}</td>
                                <td className="px-4 py-3 text-xs text-slate-600 font-bold">{vol.size}</td>
                                <td className="px-4 py-3 text-xs text-slate-500 uppercase">{vol.type}</td>
                                <td className="px-4 py-3 text-xs text-slate-500">{vol.created}</td>
                                <td className="px-4 py-3 text-right">
                                    <button onClick={() => deleteVolume(vol.id)} className="text-red-600 hover:text-red-800 hover:bg-red-50 px-2 py-1 rounded text-[10px] font-bold transition-colors flex items-center justify-end gap-1 ml-auto">
                                        <Trash2 className="w-3 h-3" /> Delete
                                    </button>
                                </td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>
        </div>
    );
};

const AmiSnapshots = () => {
    const [snapshots, setSnapshots] = useState([]); // Empty state demo
    const deleteSnapshot = (id) => setSnapshots(prev => prev.filter(s => s.id !== id));

    return (
        <div className="bg-white border border-slate-200 rounded-lg shadow-sm p-6 mb-8 animate-in fade-in slide-in-from-bottom-2">
            <div className="flex items-center space-x-2 mb-4">
                <div className="p-2 bg-slate-100 rounded-lg">
                    <History className="w-5 h-5 text-slate-600" />
                </div>
                <div>
                    <h3 className="text-lg font-bold text-slate-900">AMI & Snapshots</h3>
                    <p className="text-xs text-slate-500">Unused images and backups</p>
                </div>
            </div>

            <div className="overflow-hidden rounded-lg border border-slate-200">
                <table className="w-full text-left text-sm">
                    <thead className="bg-slate-50 border-b border-slate-200">
                        <tr>
                            <th className="px-4 py-3 font-bold text-slate-500 uppercase tracking-wider text-[10px]">Snapshot ID</th>
                            <th className="px-4 py-3 font-bold text-slate-500 uppercase tracking-wider text-[10px]">Name</th>
                            <th className="px-4 py-3 font-bold text-slate-500 uppercase tracking-wider text-[10px]">Size</th>
                            <th className="px-4 py-3 font-bold text-slate-500 uppercase tracking-wider text-[10px]">Created</th>
                            <th className="px-4 py-3 font-bold text-slate-500 uppercase tracking-wider text-[10px] text-right">Action</th>
                        </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100 bg-white">
                        {snapshots.length === 0 ? (
                            <tr>
                                <td colSpan={5} className="px-4 py-8 text-center text-slate-400 text-xs italic">No snapshots found.</td>
                            </tr>
                        ) : snapshots.map(snap => (
                            <tr key={snap.id} className="hover:bg-slate-50 transition-colors">
                                {/* Row logic */}
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>
        </div>
    );
};

const ActivityLog = () => {
    const [logs, setLogs] = useState([]);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        const fetchActivity = async () => {
            try {
                setLoading(true);
                const data = await api.getActivityFeed(10);
                setLogs(data || []);
            } catch (err) {
                console.error("Failed to load activity feed:", err);
                setLogs([]);
            } finally {
                setLoading(false);
            }
        };
        fetchActivity();
        const interval = setInterval(fetchActivity, 30000); // Refresh every 30s
        return () => clearInterval(interval);
    }, []);

    return (
        <div className="bg-white border border-slate-200 shadow-sm rounded-lg p-6">
            <div className="flex items-center justify-between mb-4">
                <h3 className="text-sm font-bold text-slate-900 flex items-center">
                    <Clock className="w-4 h-4 text-slate-400 mr-2" />
                    Recent Activity
                </h3>
                {loading && <RefreshCw className="w-3 h-3 text-blue-500 animate-spin" />}
            </div>
            <div className="space-y-4">
                {logs.length === 0 ? (
                    <p className="text-xs text-slate-400 italic text-center py-4">No recent activity</p>
                ) : logs.map(log => (
                    <div key={log.id} className="flex items-start space-x-3 pb-3 border-b border-slate-50 last:border-0 last:pb-0">
                        <div className={cn("mt-0.5 w-2 h-2 rounded-full",
                            log.type === 'info' ? "bg-blue-400" : (log.type === 'alert' ? "bg-amber-400" : "bg-emerald-400")
                        )} />
                        <div>
                            <p className="text-xs font-medium text-slate-700 leading-snug">{log.message}</p>
                            <p className="text-[10px] text-slate-400 mt-0.5">{log.timestamp || log.time}</p>
                        </div>
                    </div>
                ))}
            </div>
        </div>
    );
};

const ResourceDistributionChart = ({ clusters }) => {
    const [currIndex, setCurrIndex] = useState(0);
    // Simple distribution simulation based on cluster or empty default
    const getClusterDist = (id) => [
        { name: 'C5 Family', value: 30 + (id.length * 2), color: '#6366f1' },
        { name: 'M5 Family', value: 20 + (id.length % 3 * 10), color: '#ec4899' },
        { name: 'R6 Family', value: 15 + (id.length % 2 * 5), color: '#8b5cf6' },
        { name: 'T3 Others', value: 10, color: '#0ea5e9' },
    ];

    const effectiveClusters = clusters && clusters.length > 0 ? clusters : [{ id: 'default', name: 'Global Fleet', nodes: [] }];
    const current = effectiveClusters[currIndex];

    const next = () => setCurrIndex(prev => (prev + 1) % effectiveClusters.length);
    const prev = () => setCurrIndex(prev => (prev - 1 + effectiveClusters.length) % effectiveClusters.length);

    if (!current) return null;

    return (
        <div className="bg-white border border-slate-200 shadow-sm rounded-lg p-6 h-full flex flex-col items-center justify-start relative overflow-hidden">
            <h3 className="w-full text-sm font-bold text-slate-900 mb-6 flex items-center justify-between z-10">
                <div className="flex items-center">
                    <div className="p-1.5 bg-indigo-50 text-indigo-600 rounded-md mr-2">
                        <Cpu className="w-4 h-4" />
                    </div>
                    Resource Distribution
                </div>
                <div className="text-[10px] font-mono text-slate-400 bg-slate-50 px-2 py-0.5 rounded-full border border-slate-100">
                    {(currIndex + 1) || 1} / {effectiveClusters.length || 1}
                </div>
            </h3>
            <div className="w-full flex flex-col items-center justify-start relative z-0 pt-2">
                <div key={current.id || 'default'} className="h-56 w-full relative flex items-center justify-center animate-in fade-in zoom-in-95 duration-500">
                    <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
                        <div className="w-40 h-40 rounded-full border-[6px] border-slate-50"></div>
                    </div>
                    <ResponsiveContainer width="100%" height="100%">
                        <PieChart>
                            <Pie
                                data={getClusterDist(current.id || 'default')}
                                innerRadius={60}
                                outerRadius={80}
                                paddingAngle={4}
                                cornerRadius={4}
                                dataKey="value"
                                stroke="none"
                            >
                                {getClusterDist(current.id || 'default').map((entry, index) => (
                                    <Cell key={`cell-${index}`} fill={entry.color} />
                                ))}
                            </Pie>
                            <Tooltip contentStyle={{ fontSize: '12px', borderRadius: '12px' }} />
                        </PieChart>
                    </ResponsiveContainer>
                    <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none pb-8">
                        <span className="text-2xl font-black text-slate-800 tracking-tight">
                            <AnimatedCounter value={getClusterDist(current.id || 'default').reduce((acc, curr) => acc + curr.value, 0)} key={current.id || 'default'} />
                        </span>
                        <span className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">Nodes</span>
                    </div>
                    <div className="w-full flex items-center justify-between absolute top-[40%] -translate-y-1/2 px-0 pointer-events-none z-20">
                        <button onClick={(e) => { e.stopPropagation(); prev(); }} className="p-2 rounded-full bg-white border border-slate-200 text-slate-400 pointer-events-auto shadow-sm">
                            <ChevronLeft className="w-5 h-5" />
                        </button>
                        <button onClick={(e) => { e.stopPropagation(); next(); }} className="p-2 rounded-full bg-white border border-slate-200 text-slate-400 pointer-events-auto shadow-sm">
                            <ChevronRight className="w-5 h-5" />
                        </button>
                    </div>
                </div>
                <div className="mt-2 text-center relative z-10 w-full">
                    <span className="inline-flex items-center px-4 py-1.5 rounded-full bg-white border border-slate-200 shadow-sm text-xs font-bold text-slate-700">
                        {current.name || 'Global'}
                    </span>
                </div>
            </div>
        </div>
    );
};

// --- View Components ---

const ClusterDetailView = ({ cluster, onBack, onSelectInstance }) => {
    return (
        <div className="animate-in fade-in slide-in-from-right-4 duration-300 relative">
            <div className="flex items-center space-x-4 mb-6">
                <button onClick={onBack} className="p-2 hover:bg-slate-100 rounded-lg text-slate-500 hover:text-slate-900 transition-colors">
                    <ArrowLeft className="w-5 h-5" />
                </button>
                <div>
                    <h2 className="text-xl font-bold text-slate-900">{cluster.name}</h2>
                    <p className="text-xs text-slate-500">Region: {cluster.region}</p>
                </div>
            </div>
            <div className="bg-white border border-slate-200 rounded-xl overflow-hidden shadow-sm">
                <table className="w-full text-left">
                    <thead className="bg-slate-50 border-b border-slate-100">
                        <tr>
                            <th className="px-6 py-4 font-bold text-slate-500 uppercase tracking-wider text-xs">Node ID</th>
                            <th className="px-6 py-4 font-bold text-slate-500 uppercase tracking-wider text-xs">Zone</th>
                            <th className="px-6 py-4 font-bold text-slate-500 uppercase tracking-wider text-xs">Type</th>
                            <th className="px-6 py-4 font-bold text-slate-500 uppercase tracking-wider text-xs">Stress</th>
                            <th className="px-6 py-4 font-bold text-slate-500 uppercase tracking-wider text-xs">Risk</th>
                            <th className="px-6 py-4 font-bold text-slate-500 uppercase tracking-wider text-xs">Status</th>
                        </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100">
                        {cluster.nodes.length === 0 ? (
                            <tr><td colSpan={6} className="px-6 py-8 text-center text-slate-400 text-sm">No nodes found in this cluster.</td></tr>
                        ) : cluster.nodes.map(node => (
                            <tr key={node.id} className="hover:bg-blue-50/50 cursor-pointer" onClick={() => onSelectInstance(node)}>
                                <td className="px-6 py-4 font-mono text-xs text-blue-600 font-medium">{node.id}</td>
                                <td className="px-6 py-4 text-slate-900 text-xs">{node.zone}</td>
                                <td className="px-6 py-4 text-xs font-mono">{node.family}</td>
                                <td className="px-6 py-4"><StressBar value={node.stress} /></td>
                                <td className="px-6 py-4"><RiskBadge risk={node.risk} /></td>
                                <td className="px-6 py-4"><StatusBadge status={node.status} /></td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>
        </div>
    );
};

const InstanceDetailPanel = ({ instance, onClose }) => {
    if (!instance) return null;
    return (
        <div className="fixed top-1/2 left-1/2 transform -translate-x-1/2 -translate-y-1/2 w-[600px] bg-white shadow-2xl border border-slate-200 rounded-xl z-50 overflow-hidden flex flex-col max-h-[90vh]">
            <div className="p-6 border-b border-slate-100 flex justify-between items-start">
                <div>
                    <h2 className="text-xl font-bold text-slate-900">{instance.id}</h2>
                    <div className="flex space-x-2 mt-2">
                        <StatusBadge status={instance.status} />
                        <RiskBadge risk={instance.risk} />
                    </div>
                </div>
                <button onClick={onClose}><X className="w-5 h-5 text-slate-400" /></button>
            </div>
            <div className="p-6 space-y-6 overflow-y-auto">
                <div className="grid grid-cols-2 gap-4">
                    <div>
                        <label className="text-xs uppercase text-slate-500 font-bold">Zone</label>
                        <p className="text-sm font-medium">{instance.zone}</p>
                    </div>
                    <div>
                        <label className="text-xs uppercase text-slate-500 font-bold">Type</label>
                        <p className="text-sm font-medium">{instance.family}</p>
                    </div>
                </div>
                <div>
                    <label className="text-xs uppercase text-slate-500 font-bold mb-2 block">Stress History</label>
                    <StressBar value={instance.stress} />
                </div>
            </div>
        </div>
    );
};

const ClientDetailView = ({ client, onBack, onSelectCluster }) => {
    const [activeTab, setActiveTab] = useState('dashboard');
    const [policies, setPolicies] = useState(client.policies || {});
    const togglePolicy = (key) => setPolicies(prev => ({ ...prev, [key]: !prev[key] }));

    return (
        <div className="animate-in fade-in slide-in-from-right-4 duration-300 relative">
            <div className="flex items-center space-x-4 mb-4">
                <button onClick={onBack} className="p-2 hover:bg-slate-100 rounded-lg text-slate-500 hover:text-slate-900 transition-colors">
                    <ArrowLeft className="w-5 h-5" />
                </button>
                <div>
                    <h1 className="text-2xl font-bold text-slate-900 tracking-tight">{client.name}</h1>
                    <p className="text-slate-500 text-sm">Client ID: {client.id}</p>
                </div>
            </div>

            {/* Tab Navigation */}
            <div className="flex space-x-1 border-b border-slate-200 mb-6">
                {['dashboard', 'clusters', 'unregistered', 'volumes', 'snapshots'].map(tab => (
                    <button
                        key={tab}
                        onClick={() => setActiveTab(tab)}
                        className={cn("px-4 py-2 text-sm font-bold border-b-2 transition-colors capitalize", activeTab === tab ? "border-blue-600 text-blue-600" : "border-transparent text-slate-500 hover:text-slate-700")}
                    >
                        {tab}
                    </button>
                ))}
            </div>

            {activeTab === 'dashboard' && (
                <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                    <div className="lg:col-span-2 space-y-6">
                        {/* Savings Chart Placeholder */}
                        <div className="bg-white border border-slate-200 rounded-lg shadow-sm p-6">
                            <h3 className="text-sm font-bold text-slate-900 mb-4">Cost Savings Overview</h3>
                            <div className="h-64 flex items-center justify-center bg-slate-50 rounded text-slate-400 text-xs">Chart Visualization Check</div>
                        </div>
                    </div>
                    <div className="space-y-6">
                        <ResourceDistributionChart clusters={client.clusters || []} />
                        <ActivityLog />
                        <div className="bg-white border border-slate-200 shadow-sm rounded-lg p-6">
                            <h3 className="text-sm font-bold text-slate-900 mb-4">Fleet Policies</h3>
                            <div className="space-y-4">
                                {/* Policies section - currently empty, can be expanded with future policies */}
                            </div>
                        </div>
                    </div>
                </div>
            )}

            {activeTab === 'clusters' && (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    {(!client.clusters || client.clusters.length === 0) ? (
                        <div className="col-span-2 text-center py-10 text-slate-400 italic">No clusters configured.</div>
                    ) : client.clusters.map(cluster => (
                        <div key={cluster.id} onClick={() => onSelectCluster(cluster)} className="bg-white border border-slate-200 p-4 rounded-lg hover:border-blue-500 cursor-pointer shadow-sm">
                            <div className="flex items-center space-x-3">
                                <Layers className="w-5 h-5 text-blue-500" />
                                <div>
                                    <h4 className="font-bold text-slate-900">{cluster.name}</h4>
                                    <p className="text-xs text-slate-500">{cluster.nodeCount} Nodes • {cluster.region}</p>
                                </div>
                            </div>
                        </div>
                    ))}
                </div>
            )}

            {activeTab === 'unregistered' && <UnregisteredInstances />}
            {activeTab === 'volumes' && <UnmappedVolumes />}
            {activeTab === 'snapshots' && <AmiSnapshots />}
        </div>
    );
};

const ClientCard = ({ client, onClick }) => (
    <div onClick={onClick} className="bg-white border border-slate-200 shadow-sm rounded-lg p-6 cursor-pointer hover:border-blue-400 hover:shadow-md transition-all group">
        <div className="flex justify-between items-start mb-4">
            <div className="p-2 bg-slate-50 rounded-lg group-hover:bg-blue-50 transition-colors">
                <Globe className="w-6 h-6 text-slate-400 group-hover:text-blue-600 transition-colors" />
            </div>
            <StatusBadge status={client.status} />
        </div>
        <h3 className="text-lg font-bold text-slate-900 mb-1">{client.name}</h3>
        <p className="text-xs text-slate-400 mb-4 font-mono">{client.id}</p>
        <div className="space-y-3 pt-4 border-t border-slate-100">
            <div className="flex justify-between text-xs"><span className="text-slate-500">Nodes</span><span className="font-bold">{client.totalNodes}</span></div>
            <div className="flex justify-between text-xs"><span className="text-slate-500">Savings</span><span className="font-bold text-emerald-600">{client.potentialSavings}</span></div>
        </div>
    </div>
);

const ClientMasterView = ({ clients, onSelectClient, loading, error }) => {
    // Calculate real KPIs from client data
    const totalNodes = clients.reduce((sum, client) => sum + (client.totalNodes || 0), 0);
    const totalSavings = clients.reduce((sum, client) => {
        const savingsStr = client.potentialSavings || '$0';
        const savingsNum = parseFloat(savingsStr.replace(/[$,]/g, ''));
        return sum + (isNaN(savingsNum) ? 0 : savingsNum);
    }, 0);
    const activeClients = clients.filter(c => c.status === 'Active').length;
    const optimizationRate = clients.length > 0 ? ((activeClients / clients.length) * 100).toFixed(1) : 0;

    return (
        <div className="space-y-8 animate-in fade-in slide-in-from-bottom-4 duration-500">
            <div className="flex justify-between items-end">
                <div>
                    <h1 className="text-2xl font-bold text-slate-900 mb-2 tracking-tight">Mission Control</h1>
                    <p className="text-slate-500 text-sm">Overview of all managed clients and fleet status</p>
                </div>
            </div>

            {/* KPI Grid */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                <div className="bg-slate-900 rounded-xl p-6 shadow-xl text-white relative overflow-hidden">
                    <div className="absolute top-0 right-0 p-8 bg-blue-500 rounded-full blur-[60px] opacity-20 -mr-10 -mt-10" />
                    <div className="relative">
                        <div className="text-slate-400 text-xs font-bold uppercase tracking-wider mb-2">Total Monthly Savings</div>
                        <div className="text-3xl font-bold mb-4">
                            {loading ? '...' : `$${totalSavings.toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: 0 })}`}
                        </div>
                    </div>
                </div>
                <div className="bg-white border border-slate-200 rounded-xl p-6 shadow-sm">
                    <div className="text-slate-500 text-xs font-bold uppercase tracking-wider mb-2">Total Active Nodes</div>
                    <div className="text-3xl font-bold text-slate-900 mb-4">
                        {loading ? '...' : totalNodes.toLocaleString()}
                    </div>
                    <div className="w-full bg-slate-100 h-1.5 rounded-full overflow-hidden">
                        <div className="bg-blue-600 h-full w-[75%] rounded-full" />
                    </div>
                </div>
                <div className="bg-white border border-slate-200 rounded-xl p-6 shadow-sm">
                    <div className="text-slate-500 text-xs font-bold uppercase tracking-wider mb-2">Optimization Rate</div>
                    <div className="text-3xl font-bold text-emerald-600 mb-4">
                        {loading ? '...' : `${optimizationRate}%`}
                    </div>
                    <div className="w-full bg-slate-100 h-1.5 rounded-full overflow-hidden">
                        <div className="bg-emerald-500 h-full rounded-full" style={{ width: `${optimizationRate}%` }} />
                    </div>
                </div>
            </div>

        {/* Client Grid */}
        <div>
            <h3 className="text-sm font-bold text-slate-900 uppercase tracking-wider mb-6">Client List</h3>
            {loading ? (
                <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                    {[1, 2, 3].map(i => <div key={i} className="h-64 bg-slate-100 animate-pulse rounded-lg border border-slate-200"></div>)}
                </div>
            ) : error ? (
                <div className="p-8 border border-red-200 bg-red-50 rounded-lg text-center text-red-600">
                    <AlertTriangle className="w-8 h-8 mx-auto mb-2" />
                    {error}
                </div>
            ) : clients.length === 0 ? (
                <div className="p-12 border-2 border-dashed border-slate-200 rounded-xl text-center">
                    <Users className="w-12 h-12 mx-auto text-slate-300 mb-4" />
                    <h3 className="text-lg font-bold text-slate-900">No Clients Found</h3>
                    <p className="text-slate-500 text-sm mt-2">Get started by adding your first managed client.</p>
                </div>
            ) : (
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                    {clients.map(client => (
                        <ClientCard key={client.id} client={client} onClick={() => onSelectClient(client)} />
                    ))}
                </div>
            )}
        </div>
    </div>
    );
};

// --- Main Component ---

const NodeFleet = ({ externalSelectedClientId }) => {
    const navigate = useNavigate();
    const [clients, setClients] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);

    const [selectedClient, setSelectedClient] = useState(null);
    const [selectedCluster, setSelectedCluster] = useState(null);
    const [selectedInstance, setSelectedInstance] = useState(null);

    // Fetch Clients (Real API)
    useEffect(() => {
        const fetchClients = async () => {
            try {
                setLoading(true);
                const data = await api.getClients();
                setClients(data);
            } catch (err) {
                console.error("Failed to fetch fleet data:", err);
                setError("Failed to load fleet data. Please ensure the backend is running.");
            } finally {
                setLoading(false);
            }
        };
        fetchClients();
    }, []);

    // Sync sidebar selection
    useEffect(() => {
        if (externalSelectedClientId && clients.length > 0) {
            const client = clients.find(c => c.id === externalSelectedClientId);
            if (client) {
                setSelectedClient(client);
                setSelectedCluster(null);
                setSelectedInstance(null);
            }
        } else if (externalSelectedClientId === null) {
            setSelectedClient(null);
        }
    }, [externalSelectedClientId, clients]);

    return (
        <div className="relative">
            {selectedInstance && (
                <>
                    <div className="fixed inset-0 bg-slate-900/20 backdrop-blur-sm z-40" onClick={() => setSelectedInstance(null)} />
                    <InstanceDetailPanel instance={selectedInstance} onClose={() => setSelectedInstance(null)} />
                </>
            )}

            {selectedCluster ? (
                <ClusterDetailView
                    cluster={selectedCluster}
                    onBack={() => setSelectedCluster(null)}
                    onSelectInstance={setSelectedInstance}
                />
            ) : selectedClient ? (
                <ClientDetailView
                    client={selectedClient}
                    onBack={() => setSelectedClient(null)}
                    onSelectCluster={setSelectedCluster}
                />
            ) : (
                <ClientMasterView
                    clients={clients}
                    loading={loading}
                    error={error}
                    onSelectClient={setSelectedClient}
                    onAddClient={() => navigate('/clients')}
                    onOpenGlobalPolicies={() => { }}
                />
            )}
        </div>
    );
};

export default NodeFleet;
