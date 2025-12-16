import React, { useState, useEffect } from 'react';
import {
    MoreHorizontal, AlertTriangle, ShieldCheck, Server, ChevronDown,
    Layers, Globe, ArrowLeft, Plus, Settings, DollarSign, Activity, Zap,
    X, History, TrendingDown, Cpu, BarChart3, Database, Trash2, MinusCircle, Info, LayoutDashboard,
    Download, RefreshCw, FileText, CheckCircle, Clock, ChevronLeft, ChevronRight
} from 'lucide-react';
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, LineChart, Line, Legend, BarChart, Bar, PieChart, Pie, Cell } from 'recharts';
import { cn } from '../lib/utils';

import { mockClients, mockInstanceDetails, DEMO_CLIENT } from '../data/mockData';
import InstanceFlowAnimation from './InstanceFlowAnimation';

// --- Shared Components ---

// --- MOCK DATA FOR UNREGISTERED INSTANCES ---
const MOCK_UNREGISTERED_INSTANCES = [
    { id: 'i-0x9988776655', region: 'us-east-1', zone: 'us-east-1a', type: 't3.micro', launchTime: '2h 15m' },
    { id: 'i-0y1122334455', region: 'us-east-1', zone: 'us-east-1b', type: 'm5.large', launchTime: '4d 12h' },
    { id: 'i-0z5544332211', region: 'eu-west-1', zone: 'eu-west-1c', type: 'c5.xlarge', launchTime: '15m 30s' },
    { id: 'i-0w1234567890', region: 'ap-south-1', zone: 'ap-south-1a', type: 'r6g.medium', launchTime: '1h 05m' },
];

const UnregisteredInstances = () => {
    const [instances, setInstances] = useState(MOCK_UNREGISTERED_INSTANCES);
    const [decisions, setDecisions] = useState({}); // { [id]: 'authorized' | 'unauthorized' }

    // Initialize decisions as 'unauthorized' by default for rogue instances
    React.useEffect(() => {
        const initial = {};
        MOCK_UNREGISTERED_INSTANCES.forEach(i => initial[i.id] = 'unauthorized');
        setDecisions(initial);
    }, []);

    const handleDecision = (id, status) => {
        setDecisions(prev => ({ ...prev, [id]: status }));
    };

    const applyChanges = () => {
        // Will replace in next step after viewing
        // Remove only the ones marked as 'unauthorized'
        const kept = instances.filter(i => decisions[i.id] === 'authorized');
        setInstances(kept);

        // In a real app, this would send an API request to terminate the others
        // For now, we just update the local list
    };

    if (instances.length === 0) return null;

    return (
        <div className="bg-white border border-slate-200 rounded-lg shadow-sm p-6 mb-8 animate-in fade-in slide-in-from-bottom-2">
            <div className="flex items-center justify-between mb-4">
                <div className="flex items-center space-x-2">
                    <div className="p-2 bg-amber-50 rounded-lg">
                        <AlertTriangle className="w-5 h-5 text-amber-600" />
                    </div>
                    <div>
                        <h3 className="text-lg font-bold text-slate-900">Unregistered Instances</h3>
                        <p className="text-xs text-slate-500">Rogue instances detected outside managed clusters</p>
                    </div>
                </div>
                <button
                    onClick={applyChanges}
                    className="flex items-center space-x-2 px-4 py-2 bg-slate-900 text-white text-xs font-bold rounded-lg shadow-sm hover:bg-black transition-all hover:scale-105 active:scale-95"
                >
                    <Trash2 className="w-3.5 h-3.5" />
                    <span>Apply Actions</span>
                </button>
            </div>

            <div className="overflow-hidden rounded-lg border border-slate-200">
                <table className="w-full text-left text-sm">
                    <thead className="bg-slate-50 border-b border-slate-200">
                        <tr>
                            <th className="px-4 py-3 font-bold text-slate-500 uppercase tracking-wider text-[10px]">Instance ID</th>
                            <th className="px-4 py-3 font-bold text-slate-500 uppercase tracking-wider text-[10px]">Region / Zone</th>
                            <th className="px-4 py-3 font-bold text-slate-500 uppercase tracking-wider text-[10px]">Type</th>
                            <th className="px-4 py-3 font-bold text-slate-500 uppercase tracking-wider text-[10px]">Launch Since</th>
                            <th className="px-4 py-3 font-bold text-slate-500 uppercase tracking-wider text-[10px] text-right">Action</th>
                        </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100 bg-white">
                        {instances.map(inst => (
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
        Safe: "bg-blue-50 text-blue-700 border-blue-200",
        High: "bg-orange-50 text-orange-700 border-orange-200",
        Critical: "bg-red-50 text-red-700 border-red-200",
    };
    return (
        <span className={cn("px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider border rounded-sm flex items-center w-fit", styles[risk] || styles.Safe)}>
            {risk === 'Safe' ? <ShieldCheck className="w-3 h-3 mr-1" /> : <AlertTriangle className="w-3 h-3 mr-1" />}
            {risk}
        </span>
    );
};

const StressBar = ({ value }) => (
    <div className="w-full max-w-[140px] flex items-center">
        <div className="flex-1 h-2 bg-slate-100 rounded-full overflow-hidden">
            <div
                className={cn("h-full rounded-full transition-all duration-500",
                    value > 0.8 ? "bg-red-500" : value > 0.5 ? "bg-amber-500" : "bg-emerald-500"
                )}
                style={{ width: `${value * 100}% ` }}
            />
        </div>
        <span className="ml-2 text-xs font-mono text-slate-500">{(value * 100).toFixed(0)}%</span>
    </div>
);

// --- Cluster Detail View (Full Screen) ---

const ClusterDetailView = ({ cluster, onBack, onToggleFallback, isFallbackActive, onSelectInstance }) => {
    const [activeTab, setActiveTab] = useState('overview');
    const [showConfirm, setShowConfirm] = useState(false);

    return (
        <div className="space-y-6">
            <div className="flex items-center justify-between mb-6">
                <div className="flex items-center space-x-4">
                    <button
                        onClick={onBack}
                        className="p-2 hover:bg-slate-100 rounded-full transition-colors"
                    >
                        <ArrowLeft className="w-5 h-5 text-slate-500" />
                    </button>
                    <div>
                        <h2 className="text-2xl font-bold text-slate-900">{cluster.name}</h2>
                        <div className="flex items-center space-x-2 text-slate-500">
                            <span className="text-sm">Manage Cluster Configuration & Policies</span>
                        </div>
                    </div>
                </div>
                <div className="flex items-center space-x-3 relative">
                    {showConfirm && (
                        <div className="absolute top-10 right-0 bg-white shadow-xl border border-red-200 p-4 rounded-xl z-50 w-64 animate-in fade-in zoom-in-95 duration-200">
                            <div className="flex items-center space-x-2 text-red-600 mb-2">
                                <AlertTriangle className="w-4 h-4" />
                                <p className="text-xs font-bold uppercase tracking-wider">Confirm Fallback</p>
                            </div>
                            <p className="text-xs text-slate-600 mb-3 leading-relaxed">
                                This will immediately provision On-Demand capacity for the entire cluster. Costs will increase significantly.
                            </p>
                            <div className="flex space-x-2">
                                <button
                                    className="flex-1 py-1.5 bg-red-600 text-white text-xs font-bold rounded shadow-sm hover:bg-red-700 transition-colors"
                                    onClick={() => {
                                        onToggleFallback();
                                        setShowConfirm(false);
                                    }}
                                >
                                    ACTIVATE
                                </button>
                                <button
                                    className="flex-1 py-1.5 bg-slate-100 text-slate-600 text-xs font-bold rounded hover:bg-slate-200 transition-colors"
                                    onClick={() => setShowConfirm(false)}
                                >
                                    Cancel
                                </button>
                            </div>
                        </div>
                    )}

                    <button
                        onClick={() => {
                            if (isFallbackActive) {
                                onToggleFallback();
                            } else {
                                setShowConfirm(true);
                            }
                        }}
                        className={cn(
                            "px-3 py-1.5 text-xs rounded-lg font-bold transition-all shadow-sm flex items-center space-x-2",
                            isFallbackActive
                                ? "bg-red-600 text-white shadow-red-200 hover:bg-red-700 blink-subtle"
                                : "bg-white border border-red-200 text-red-600 hover:bg-red-50"
                        )}
                    >
                        <AlertTriangle className="w-3.5 h-3.5" />
                        <span>{isFallbackActive ? "Disable Emergency" : "Emergency Fallback"}</span>
                    </button>
                    <button className="px-3 py-1.5 bg-blue-600 text-white text-xs rounded-lg hover:bg-blue-700 font-bold shadow-sm shadow-blue-200 transition-all">
                        Save Configuration
                    </button>
                </div>
            </div>
            {/* Nodes Table (Full Screen Style) */}
            <div className="bg-white border border-slate-200 rounded-lg shadow-sm overflow-hidden">
                <table className="w-full text-left text-sm">
                    <thead className="bg-slate-50 border-b border-slate-200">
                        <tr>
                            <th className="px-6 py-4 font-bold text-slate-500 uppercase tracking-wider text-xs">Instance ID</th>
                            <th className="px-6 py-4 font-bold text-slate-500 uppercase tracking-wider text-xs">Zone</th>
                            <th className="px-6 py-4 font-bold text-slate-500 uppercase tracking-wider text-xs">Type</th>
                            <th className="px-6 py-4 font-bold text-slate-500 uppercase tracking-wider text-xs">Stress</th>
                            <th className="px-6 py-4 font-bold text-slate-500 uppercase tracking-wider text-xs">Risk</th>
                            <th className="px-6 py-4 font-bold text-slate-500 uppercase tracking-wider text-xs">Status</th>
                            <th className="px-6 py-4 font-bold text-slate-500 uppercase tracking-wider text-xs text-right">Actions</th>
                        </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100">
                        {cluster.nodes.map((node) => (
                            <tr
                                key={node.id}
                                className="hover:bg-blue-50/50 transition-colors cursor-pointer group"
                                onClick={(e) => {
                                    if (e.target.closest('button')) return;
                                    onSelectInstance(node);
                                }}
                            >
                                <td className="px-6 py-4 font-mono text-xs text-blue-600 font-medium flex items-center group-hover:underline">
                                    <Server className="w-4 h-4 mr-3 text-slate-300 group-hover:text-blue-500 transition-colors" />
                                    {node.id}
                                </td>
                                <td className="px-6 py-4 text-slate-900">{node.zone}</td>
                                <td className="px-6 py-4">
                                    <span className="px-2 py-1 bg-slate-100 rounded text-xs font-mono font-bold text-slate-600 border border-slate-200">
                                        {node.family}
                                    </span>
                                </td>
                                <td className="px-6 py-4">
                                    <StressBar value={node.stress} />
                                </td>
                                <td className="px-6 py-4">
                                    <RiskBadge risk={node.risk} />
                                </td>
                                <td className="px-6 py-4">
                                    <StatusBadge status={node.status} />
                                </td>
                                <td className="px-6 py-4 text-right">
                                    <button className="p-2 hover:bg-slate-100 rounded text-slate-400 hover:text-slate-600 transition-colors">
                                        <MoreHorizontal className="w-5 h-5" />
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

// --- Instance Detail Panel ---

const InstanceDetailPanel = ({ instance, onClose }) => {
    if (!instance) return null;
    const region = instance.zone.slice(0, -1);
    const [showConfirm, setShowConfirm] = useState(false);

    return (
        <div className="fixed top-1/2 left-1/2 transform -translate-x-1/2 -translate-y-1/2 w-[800px] max-h-[90vh] bg-white shadow-2xl border border-slate-200 rounded-xl z-50 overflow-hidden flex flex-col">
            {/* Header */}
            <div className="p-6 border-b border-slate-100 flex justify-between items-start bg-white/90 backdrop-blur-sm z-10 shrink-0">
                <div>
                    <div className="flex items-center space-x-2 text-sm text-slate-500 mb-1">
                        <Globe className="w-4 h-4" />
                        <span className="font-bold text-slate-700">{region}</span>
                        <span className="text-slate-300">/</span>
                        <span className="font-mono text-slate-600">{instance.zone}</span>
                    </div>
                    <h2 className="text-2xl font-bold text-slate-900 tracking-tight mb-3">{instance.id}</h2>
                    <div className="flex space-x-2">
                        <StatusBadge status={instance.status} />
                        <RiskBadge risk={instance.risk} />
                    </div>
                </div>
                <div className="flex items-center space-x-3 relative">
                    {showConfirm ? (
                        <div className="absolute top-10 right-0 bg-white shadow-xl border border-slate-200 p-3 rounded-lg z-20 w-48 animate-in fade-in zoom-in-95 duration-200">
                            <p className="text-xs font-bold text-slate-900 mb-2 text-center">Are you sure?</p>
                            <div className="flex space-x-2">
                                <button
                                    className="flex-1 py-1 bg-red-50 text-red-600 text-xs font-bold rounded hover:bg-red-100"
                                    onClick={() => {
                                        console.log("Fallback Confirmed");
                                        setShowConfirm(false);
                                    }}
                                >
                                    Yes
                                </button>
                                <button
                                    className="flex-1 py-1 bg-slate-50 text-slate-600 text-xs font-bold rounded hover:bg-slate-100"
                                    onClick={() => setShowConfirm(false)}
                                >
                                    No
                                </button>
                            </div>
                        </div>
                    ) : null}

                    <button
                        onClick={() => setShowConfirm(true)}
                        className="px-3 py-1.5 bg-amber-50 text-amber-700 text-xs font-bold border border-amber-200 rounded hover:bg-amber-100 transition-colors flex items-center"
                    >
                        <AlertTriangle className="w-3 h-3 mr-1.5" />
                        Fallback to On-Demand
                    </button>
                    <button
                        onClick={onClose}
                        className="p-2 hover:bg-slate-100 rounded-full text-slate-400 hover:text-slate-600 transition-colors"
                    >
                        <X className="w-5 h-5" />
                    </button>
                </div>
            </div>

            <div className="p-6 space-y-8 overflow-y-auto">

                {/* Info Grid */}
                <div className="grid grid-cols-3 gap-4 bg-slate-50 rounded-xl p-4 border border-slate-100">
                    <div>
                        <div className="text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-1">Spot Pool Details</div>
                        <div className="flex items-center space-x-2">
                            <Server className="w-4 h-4 text-blue-500" />
                            <span className="text-sm font-bold text-slate-900 font-mono">{instance.family}</span>
                        </div>
                    </div>
                    <div>
                        <div className="text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-1">Availability Zone</div>
                        <div className="flex items-center space-x-2">
                            <Layers className="w-4 h-4 text-slate-400" />
                            <span className="text-sm font-medium text-slate-900">{instance.zone}</span>
                        </div>
                    </div>
                    <div>
                        <div className="text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-1">Current Stress</div>
                        <StressBar value={instance.stress} />
                    </div>
                </div>

                {/* Economic Intelligence Graph */}
                <div className="space-y-4">
                    <div className="flex items-center justify-between">
                        <h3 className="text-sm font-bold text-slate-900 flex items-center">
                            <DollarSign className="w-4 h-4 text-emerald-600 mr-2" />
                            Real-time Market Analytics
                        </h3>
                        <span className="text-xs font-mono text-slate-500">Last 24 Hours</span>
                    </div>

                    <div className="bg-slate-50 rounded-xl p-4 border border-slate-100" style={{ height: 250 }}>
                        <ResponsiveContainer width="100%" height="100%">
                            <LineChart data={mockInstanceDetails.priceHistory}>
                                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e2e8f0" />
                                <XAxis dataKey="time" hide />
                                <YAxis domain={['auto', 'auto']} width={40} tick={{ fontSize: 10 }} tickFormatter={(val) => `$${val} `} />
                                <Tooltip
                                    contentStyle={{ backgroundColor: '#fff', border: '1px solid #e2e8f0', borderRadius: '8px' }}
                                    itemStyle={{ fontSize: '10px' }}
                                    labelStyle={{ fontSize: '10px', fontWeight: 'bold', marginBottom: '4px' }}
                                />
                                <Legend iconType="circle" wrapperStyle={{ fontSize: '10px', paddingTop: '10px' }} />
                                <Line type="monotone" dataKey="current" name="Current (c5.large)" stroke="#3b82f6" strokeWidth={2} dot={false} />
                                <Line type="monotone" dataKey="alt1" name="Alt 1 (m5.large)" stroke="#10b981" strokeWidth={2} strokeDasharray="5 5" dot={false} />
                                <Line type="monotone" dataKey="alt2" name="Alt 2 (r5.large)" stroke="#f59e0b" strokeWidth={2} strokeDasharray="3 3" dot={false} />
                            </LineChart>
                        </ResponsiveContainer>
                    </div>
                    <div className="flex gap-2 text-xs text-slate-500">
                        <div className="flex items-center"><div className="w-2 h-2 rounded-full bg-emerald-500 mr-1" /> Best Alternative</div>
                        <div className="flex items-center"><div className="w-2 h-2 rounded-full bg-blue-500 mr-1" /> Current Price</div>
                    </div>
                </div>

                {/* Stress History */}
                <div className="space-y-4">
                    <div className="flex items-center justify-between">
                        <h3 className="text-sm font-bold text-slate-900 flex items-center">
                            <Cpu className="w-4 h-4 text-indigo-500 mr-2" />
                            Resource Utilization History
                        </h3>
                    </div>

                    <div className="bg-slate-50 rounded-xl p-4 border border-slate-100" style={{ height: 200 }}>
                        <ResponsiveContainer width="100%" height="100%">
                            <AreaChart data={mockInstanceDetails.stressHistory}>
                                <defs>
                                    <linearGradient id="colorCpu" x1="0" y1="0" x2="0" y2="1">
                                        <stop offset="5%" stopColor="#6366f1" stopOpacity={0.1} />
                                        <stop offset="95%" stopColor="#6366f1" stopOpacity={0} />
                                    </linearGradient>
                                </defs>
                                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e2e8f0" />
                                <XAxis dataKey="time" hide />
                                <YAxis width={30} tick={{ fontSize: 10 }} />
                                <Tooltip />
                                <Area type="monotone" dataKey="cpu" stackId="1" stroke="#6366f1" fill="url(#colorCpu)" />
                                <Area type="monotone" dataKey="memory" stackId="1" stroke="#8b5cf6" fill="#8b5cf6" fillOpacity={0.1} />
                            </AreaChart>
                        </ResponsiveContainer>
                    </div>
                </div>

                {/* Decision Log */}
                <div className="space-y-4">
                    <h3 className="text-sm font-bold text-slate-900 flex items-center">
                        <History className="w-4 h-4 text-slate-400 mr-2" />
                        Decision Audit Log
                    </h3>
                    <div className="bg-white border border-slate-200 rounded-lg overflow-hidden">
                        <table className="w-full text-left text-xs">
                            <thead className="bg-slate-50 border-b border-slate-200">
                                <tr>
                                    <th className="px-4 py-2 font-bold text-slate-500">Time</th>
                                    <th className="px-4 py-2 font-bold text-slate-900">Action</th>
                                    <th className="px-4 py-2 font-bold text-slate-500">Reason</th>
                                </tr>
                            </thead>
                            <tbody className="divide-y divide-slate-100">
                                {mockInstanceDetails.decisionLog.map((log, i) => (
                                    <tr key={i} className="hover:bg-slate-50">
                                        <td className="px-4 py-3 font-mono text-slate-500">{log.time}</td>
                                        <td className="px-4 py-3 font-bold text-slate-900">{log.action}</td>
                                        <td className="px-4 py-3 text-slate-600">{log.reason}</td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                </div>

            </div>
        </div>
    );
};

// --- Detail View Components ---

const ClusterSection = ({ cluster, onSelectInstance }) => {
    const [isOpen, setIsOpen] = useState(true);

    return (
        <div className="border border-slate-200 rounded-lg shadow-sm bg-white overflow-hidden mb-4">
            <div
                className="flex items-center justify-between px-4 py-3 bg-slate-50 border-b border-slate-200 cursor-pointer hover:bg-slate-100/50 transition-colors"
                onClick={() => setIsOpen(!isOpen)}
            >
                <div className="flex items-center space-x-3">
                    <ChevronDown className={cn("w-4 h-4 text-slate-400 transition-transform", !isOpen && "-rotate-90")} />
                    <div className="flex items-center space-x-2">
                        <Layers className="w-4 h-4 text-blue-600" />
                        <span className="text-sm font-bold text-slate-900">{cluster.name}</span>
                    </div>
                    <span className="px-2 py-0.5 text-[10px] font-bold text-slate-500 bg-white border border-slate-200 rounded uppercase tracking-wider">
                        {cluster.region}
                    </span>
                </div>
                <div className="text-xs text-slate-500 font-medium">
                    {cluster.nodeCount} nodes
                </div>
            </div>

            {isOpen && (
                <div className="overflow-x-auto">
                    <table className="w-full text-left text-sm">
                        <thead className="bg-white border-b border-slate-100">
                            <tr>
                                <th className="px-6 py-3 text-[10px] font-bold text-slate-400 uppercase tracking-wider">Instance ID</th>
                                <th className="px-6 py-3 text-[10px] font-bold text-slate-400 uppercase tracking-wider">Zone</th>
                                <th className="px-6 py-3 text-[10px] font-bold text-slate-400 uppercase tracking-wider">Type</th>
                                <th className="px-6 py-3 text-[10px] font-bold text-slate-400 uppercase tracking-wider">Stress</th>
                                <th className="px-6 py-3 text-[10px] font-bold text-slate-400 uppercase tracking-wider">Risk</th>
                                <th className="px-6 py-3 text-[10px] font-bold text-slate-400 uppercase tracking-wider">Status</th>
                                <th className="px-6 py-3 text-[10px] font-bold text-slate-400 uppercase tracking-wider text-right">Actions</th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-100">
                            {cluster.nodes.map((node) => (
                                <tr
                                    key={node.id}
                                    className="hover:bg-blue-50/50 transition-colors group cursor-pointer"
                                    onClick={(e) => {
                                        if (e.target.closest('button')) return;
                                        onSelectInstance(node);
                                    }}
                                >
                                    <td className="px-6 py-3 font-mono text-xs text-blue-600 font-medium flex items-center group-hover:underline">
                                        <Server className="w-3.5 h-3.5 mr-2 text-slate-300 group-hover:text-blue-500 transition-colors" />
                                        {node.id}
                                    </td>
                                    <td className="px-6 py-3 text-slate-900 text-xs font-medium">{node.zone}</td>
                                    <td className="px-6 py-3">
                                        <span className="px-1.5 py-0.5 bg-slate-50 rounded text-[10px] font-mono font-bold text-slate-600 border border-slate-200">
                                            {node.family}
                                        </span>
                                    </td>
                                    <td className="px-6 py-3">
                                        <StressBar value={node.stress} />
                                    </td>
                                    <td className="px-6 py-3">
                                        <RiskBadge risk={node.risk} />
                                    </td>
                                    <td className="px-6 py-3">
                                        <StatusBadge status={node.status} />
                                    </td>
                                    <td className="px-6 py-3 text-right">
                                        <button className="p-1 hover:bg-slate-100 rounded text-slate-400 hover:text-slate-600 transition-colors">
                                            <MoreHorizontal className="w-4 h-4" />
                                        </button>
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            )}
        </div>
    );
};

// --- MOCK DATA FOR VOLUMES & SNAPSHOTS ---
const MOCK_VOLUMES = [
    { id: 'vol-0a1b2c3d4e', size: '100 GB', type: 'gp3', created: '2023-10-15', status: 'available' },
    { id: 'vol-0f9e8d7c6b', size: '500 GB', type: 'io2', created: '2023-09-20', status: 'available' },
    { id: 'vol-0x1y2z3a4b', size: '20 GB', type: 'gp2', created: '2023-11-01', status: 'available' },
];

const MOCK_SNAPSHOTS = [
    { id: 'snap-0a1b2c3d4e', name: 'backup-prod-db-2023', size: '250 GB', created: '2023-08-10' },
    { id: 'snap-0f9e8d7c6b', name: 'legacy-app-v1', size: '50 GB', created: '2022-12-05' },
    { id: 'snap-0x1y2z3a4b', name: 'dev-environment-base', size: '120 GB', created: '2023-05-20' },
];

const UnmappedVolumes = () => {
    const [volumes, setVolumes] = useState(MOCK_VOLUMES);

    const deleteVolume = (id) => {
        setVolumes(prev => prev.filter(v => v.id !== id));
    };

    return (
        <div className="bg-white border border-slate-200 rounded-lg shadow-sm p-6 mb-8 animate-in fade-in slide-in-from-bottom-2">
            <div className="flex items-center space-x-2 mb-4">
                <div className="p-2 bg-slate-100 rounded-lg">
                    <Database className="w-5 h-5 text-slate-600" />
                </div>
                <div>
                    <h3 className="text-lg font-bold text-slate-900">Unmapped Volumes</h3>
                    <p className="text-xs text-slate-500">Detached EBS volumes incurring costs</p>
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
                        {volumes.map(vol => (
                            <tr key={vol.id} className="hover:bg-slate-50 transition-colors">
                                <td className="px-4 py-3 font-mono text-xs font-medium text-slate-700">{vol.id}</td>
                                <td className="px-4 py-3 text-xs text-slate-600 font-bold">{vol.size}</td>
                                <td className="px-4 py-3 text-xs text-slate-500 uppercase">{vol.type}</td>
                                <td className="px-4 py-3 text-xs text-slate-500">{vol.created}</td>
                                <td className="px-4 py-3 text-right">
                                    <button
                                        onClick={() => deleteVolume(vol.id)}
                                        className="text-red-600 hover:text-red-800 hover:bg-red-50 px-2 py-1 rounded text-[10px] font-bold transition-colors flex items-center justify-end gap-1 ml-auto"
                                    >
                                        <Trash2 className="w-3 h-3" />
                                        Delete
                                    </button>
                                </td>
                            </tr>
                        ))}
                        {volumes.length === 0 && (
                            <tr>
                                <td colSpan={5} className="px-4 py-8 text-center text-slate-400 text-xs italic">No unmapped volumes found.</td>
                            </tr>
                        )}
                    </tbody>
                </table>
            </div>
        </div>
    );
};

const AmiSnapshots = () => {
    const [snapshots, setSnapshots] = useState(MOCK_SNAPSHOTS);

    const deleteSnapshot = (id) => {
        setSnapshots(prev => prev.filter(s => s.id !== id));
    };

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
                        {snapshots.map(snap => (
                            <tr key={snap.id} className="hover:bg-slate-50 transition-colors">
                                <td className="px-4 py-3 font-mono text-xs font-medium text-slate-700">{snap.id}</td>
                                <td className="px-4 py-3 text-xs text-slate-600 font-bold">{snap.name}</td>
                                <td className="px-4 py-3 text-xs text-slate-500">{snap.size}</td>
                                <td className="px-4 py-3 text-xs text-slate-500">{snap.created}</td>
                                <td className="px-4 py-3 text-right">
                                    <button
                                        onClick={() => deleteSnapshot(snap.id)}
                                        className="text-red-600 hover:text-red-800 hover:bg-red-50 px-2 py-1 rounded text-[10px] font-bold transition-colors flex items-center justify-end gap-1 ml-auto"
                                    >
                                        <Trash2 className="w-3 h-3" />
                                        Delete
                                    </button>
                                </td>
                            </tr>
                        ))}
                        {snapshots.length === 0 && (
                            <tr>
                                <td colSpan={5} className="px-4 py-8 text-center text-slate-400 text-xs italic">No snapshots found.</td>
                            </tr>
                        )}
                    </tbody>
                </table>
            </div>
        </div>
    );
};

const IPv4Summary = () => {
    return (
        <div className="bg-white border border-slate-200 rounded-lg shadow-sm p-6 flex items-center justify-between mb-8 animate-in fade-in slide-in-from-bottom-2">
            <div className="flex items-center space-x-4">
                <div className="p-3 bg-indigo-50 rounded-lg">
                    <Globe className="w-6 h-6 text-indigo-600" />
                </div>
                <div>
                    <h3 className="text-sm font-bold text-slate-500 uppercase tracking-wider">Public IPv4 Allocation</h3>
                    <div className="flex items-baseline space-x-2">
                        <span className="text-2xl font-bold text-slate-900">128</span>
                        <span className="text-xs font-bold text-slate-400">Total Addresses</span>
                    </div>
                </div>
            </div>

            <div className="h-8 w-px bg-slate-100 mx-4 hidden md:block" />

            <div className="flex space-x-8 text-right md:text-left">
                <div>
                    <div className="text-xs text-slate-400 font-bold mb-1">Active</div>
                    <div className="text-lg font-bold text-slate-700">112</div>
                </div>
                <div>
                    <div className="text-xs text-slate-400 font-bold mb-1">Unused</div>
                    <div className="text-lg font-bold text-amber-600">16</div>
                </div>
                <div className="hidden md:block">
                    <div className="text-xs text-slate-400 font-bold mb-1">Hourly Cost</div>
                    <div className="text-lg font-bold text-slate-900">$0.64</div>
                </div>
                <div className="hidden md:block">
                    <div className="text-xs text-slate-400 font-bold mb-1">Est. Monthly</div>
                    <div className="text-lg font-bold text-slate-900">$460.80</div>
                </div>
            </div>
        </div>
    );
};

const Switch = ({ checked, onChange }) => (
    <button
        onClick={() => onChange(!checked)}
        className={cn("w-9 h-5 rounded-full transition-colors relative", checked ? "bg-blue-600" : "bg-slate-300")}
    >
        <div className={cn("w-3.5 h-3.5 bg-white rounded-full absolute top-0.5 transition-all shadow-sm", checked ? "left-5" : "left-0.5")} />
    </button>
);

const QuickActions = () => (
    <div className="flex space-x-2 mb-6">
        <button className="flex items-center px-3 py-2 bg-white border border-slate-200 rounded-lg text-xs font-bold text-slate-600 hover:bg-slate-50 shadow-sm transition-colors">
            <RefreshCw className="w-3.5 h-3.5 mr-2 text-slate-400" />
            System Scan
        </button>
        <button className="flex items-center px-3 py-2 bg-white border border-slate-200 rounded-lg text-xs font-bold text-slate-600 hover:bg-slate-50 shadow-sm transition-colors">
            <Download className="w-3.5 h-3.5 mr-2 text-slate-400" />
            Export Report
        </button>
        <button className="flex items-center px-3 py-2 bg-white border border-slate-200 rounded-lg text-xs font-bold text-slate-600 hover:bg-slate-50 shadow-sm transition-colors">
            <FileText className="w-3.5 h-3.5 mr-2 text-slate-400" />
            View Logs
        </button>
        <div className="flex-1" />
        <button className="flex items-center px-3 py-2 bg-blue-50 border border-blue-100 rounded-lg text-xs font-bold text-blue-700 hover:bg-blue-100 shadow-sm transition-colors">
            <Zap className="w-3.5 h-3.5 mr-2" />
            Optimize All
        </button>
    </div>
);

const ActivityLog = () => {
    const logs = [
        { id: 1, time: '2m ago', message: 'Auto-scaled Cluster "Production-East" to 84 nodes', type: 'info' },
        { id: 2, time: '15m ago', message: 'Spot instance i-0a1b... reclaimed. Fallback triggered.', type: 'alert' },
        { id: 3, time: '1h ago', message: 'Cost optimization routine saved $45.20', type: 'success' },
        { id: 4, time: '2h ago', message: 'Weekly backup completed successfully', type: 'info' },
    ];

    return (
        <div className="bg-white border border-slate-200 shadow-sm rounded-lg p-6">
            <div className="flex items-center justify-between mb-4">
                <h3 className="text-sm font-bold text-slate-900 flex items-center">
                    <Clock className="w-4 h-4 text-slate-400 mr-2" />
                    Recent Activity
                </h3>
                <span className="text-[10px] text-blue-600 font-bold uppercase cursor-pointer hover:underline">View All</span>
            </div>
            <div className="space-y-4">
                {logs.map(log => (
                    <div key={log.id} className="flex items-start space-x-3 pb-3 border-b border-slate-50 last:border-0 last:pb-0">
                        <div className={cn("mt-0.5 w-2 h-2 rounded-full",
                            log.type === 'info' ? "bg-blue-400" : (log.type === 'alert' ? "bg-amber-400" : "bg-emerald-400")
                        )} />
                        <div>
                            <p className="text-xs font-medium text-slate-700 leading-snug">{log.message}</p>
                            <p className="text-[10px] text-slate-400 mt-0.5">{log.time}</p>
                        </div>
                    </div>
                ))}
            </div>
        </div>
    );
};

const AnimatedCounter = ({ value, duration = 1000 }) => {
    const [count, setCount] = useState(0);

    useEffect(() => {
        let start = 0;
        const end = value;
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

const ResourceDistributionChart = ({ clusters = [] }) => {
    const [currIndex, setCurrIndex] = useState(0);

    // Mock distribution generator based on cluster name/id to keep it deterministic
    const getClusterDist = (id) => [
        { name: 'C5 Family', value: 30 + (id.length * 2), color: '#6366f1' }, // Indigo
        { name: 'M5 Family', value: 20 + (id.length % 3 * 10), color: '#ec4899' }, // Pink
        { name: 'R6 Family', value: 15 + (id.length % 2 * 5), color: '#8b5cf6' }, // Purple
        { name: 'T3 Others', value: 10, color: '#0ea5e9' }, // Sky
    ];

    // Default if no clusters passed (fallback)
    const effectiveClusters = clusters.length > 0 ? clusters : [{ id: 'default', name: 'Global Fleet', nodes: [] }];
    const current = effectiveClusters[currIndex];

    const next = () => setCurrIndex(prev => (prev + 1) % effectiveClusters.length);
    const prev = () => setCurrIndex(prev => (prev - 1 + effectiveClusters.length) % effectiveClusters.length);

    return (
        <div className="bg-white border border-slate-200 shadow-sm rounded-lg p-6 h-full flex flex-col items-center justify-start relative overflow-hidden">
            {/* Header */}
            <h3 className="w-full text-sm font-bold text-slate-900 mb-6 flex items-center justify-between z-10">
                <div className="flex items-center">
                    <div className="p-1.5 bg-indigo-50 text-indigo-600 rounded-md mr-2">
                        <Cpu className="w-4 h-4" />
                    </div>
                    Resource Distribution
                </div>
                <div className="text-[10px] font-mono text-slate-400 bg-slate-50 px-2 py-0.5 rounded-full border border-slate-100">
                    {currIndex + 1} / {effectiveClusters.length}
                </div>
            </h3>

            <div className="w-full flex flex-col items-center justify-start relative z-0 pt-2">
                {/* Chart Container - Holds Ring, Chart, Center Label, and Controls */}
                <div key={current.id} className="h-56 w-full relative flex items-center justify-center animate-in fade-in zoom-in-95 duration-500">

                    {/* Decorative Background Ring */}
                    <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
                        <div className="w-40 h-40 rounded-full border-[6px] border-slate-50"></div>
                    </div>

                    {/* Chart */}
                    <ResponsiveContainer width="100%" height="100%">
                        <PieChart>
                            <Pie
                                data={getClusterDist(current.id)}
                                innerRadius={60}
                                outerRadius={80}
                                paddingAngle={4}
                                cornerRadius={4}
                                dataKey="value"
                                stroke="none"
                            >
                                {getClusterDist(current.id).map((entry, index) => (
                                    <Cell key={`cell-${index}`} fill={entry.color} />
                                ))}
                            </Pie>
                            <Tooltip
                                contentStyle={{ fontSize: '12px', borderRadius: '12px', border: 'none', boxShadow: '0 10px 15px -3px rgb(0 0 0 / 0.1)' }}
                                itemStyle={{ fontWeight: 600 }}
                            />
                            <Legend
                                iconType="circle"
                                iconSize={6}
                                wrapperStyle={{ fontSize: '11px', paddingTop: '10px' }}
                                layout="horizontal"
                                verticalAlign="bottom"
                                align="center"
                            />
                        </PieChart>
                    </ResponsiveContainer>

                    {/* Centered Total/Label */}
                    <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none pb-8">
                        <span className="text-2xl font-black text-slate-800 tracking-tight">
                            <AnimatedCounter value={getClusterDist(current.id).reduce((acc, curr) => acc + curr.value, 0)} key={current.id} />
                        </span>
                        <span className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">Nodes</span>
                    </div>

                    {/* Controls Overlay (Now inside Chart Container) */}
                    <div className="w-full flex items-center justify-between absolute top-[40%] -translate-y-1/2 px-0 pointer-events-none z-20">
                        <button
                            onClick={(e) => { e.stopPropagation(); prev(); }}
                            className="p-2 rounded-full bg-white border border-slate-200 text-slate-400 hover:text-indigo-600 hover:border-indigo-100 shadow-sm hover:shadow-md transition-all pointer-events-auto transform hover:-translate-x-1 active:scale-95"
                            disabled={effectiveClusters.length <= 1}
                        >
                            <ChevronLeft className="w-5 h-5" />
                        </button>
                        <button
                            onClick={(e) => { e.stopPropagation(); next(); }}
                            className="p-2 rounded-full bg-white border border-slate-200 text-slate-400 hover:text-indigo-600 hover:border-indigo-100 shadow-sm hover:shadow-md transition-all pointer-events-auto transform hover:translate-x-1 active:scale-95"
                            disabled={effectiveClusters.length <= 1}
                        >
                            <ChevronRight className="w-5 h-5" />
                        </button>
                    </div>
                </div>

                {/* Cluster Name Badge */}
                <div className="mt-2 text-center relative z-10 w-full">
                    <span
                        key={current.id}
                        className="inline-flex items-center px-4 py-1.5 rounded-full bg-white border border-slate-200 shadow-sm text-xs font-bold text-slate-700 animate-in fade-in slide-in-from-bottom-2 duration-300"
                    >
                        {current.name}
                    </span>
                </div>
            </div>
        </div>
    );
};

const ClientDetailView = ({ client, onBack, onSelectCluster, isFallbackActive }) => {
    const [policies, setPolicies] = useState(client.policies);
    const [activeTab, setActiveTab] = useState('dashboard');

    const togglePolicy = (key) => {
        setPolicies(prev => ({ ...prev, [key]: !prev[key] }));
    };

    const tabs = [
        { id: 'dashboard', label: 'Dashboard', icon: LayoutDashboard },
        { id: 'clusters', label: 'Managed Clusters', icon: Layers },
        { id: 'unregistered', label: 'Unregistered Instances', icon: AlertTriangle },
        { id: 'volumes', label: 'Unmapped Volumes', icon: Database },
        { id: 'snapshots', label: 'AMI & Snapshots', icon: History },
    ];

    return (
        <div className="animate-in fade-in slide-in-from-right-4 duration-300 relative">
            {/* Header */}
            <div className="flex items-center space-x-4 mb-4">
                <button
                    onClick={onBack}
                    className="p-2 hover:bg-slate-100 rounded-lg text-slate-500 hover:text-slate-900 transition-colors"
                >
                    <ArrowLeft className="w-5 h-5" />
                </button>
                <div>
                    <div className="flex items-center space-x-2">
                        <h1 className="text-2xl font-bold text-slate-900 tracking-tight">{client.name}</h1>
                        <span className="px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-700 text-[10px] font-bold uppercase tracking-wider">Healthy</span>
                    </div>
                    <p className="text-slate-500 text-sm">Client ID: {client.id}</p>
                </div>
                <div className="flex-1" />
                <div className="flex space-x-4 text-right">
                    <div>
                        <div className="text-[10px] text-slate-400 font-bold uppercase tracking-wider">Total Savings</div>
                        <div className="text-xl font-bold text-emerald-600">{client.potentialSavings}</div>
                    </div>
                    <div>
                        <div className="text-[10px] text-slate-400 font-bold uppercase tracking-wider">Active Nodes</div>
                        <div className="text-xl font-bold text-slate-700">{client.totalNodes}</div>
                    </div>
                </div>
            </div>

            {/* Tab Navigation */}
            <div className="flex items-center space-x-1 mb-6 overflow-x-auto pb-2 noscrollbar border-b border-slate-200">
                {tabs.map(tab => {
                    const Icon = tab.icon;
                    const isActive = activeTab === tab.id;
                    return (
                        <button
                            key={tab.id}
                            onClick={() => setActiveTab(tab.id)}
                            className={cn(
                                "flex items-center space-x-2 px-4 py-2 border-b-2 transition-all whitespace-nowrap text-sm font-medium",
                                isActive ? "border-blue-600 text-blue-600" : "border-transparent text-slate-500 hover:text-slate-800 hover:border-slate-300"
                            )}
                        >
                            <Icon className={cn("w-4 h-4", isActive ? "text-blue-600" : "text-slate-400")} />
                            <span>{tab.label}</span>
                        </button>
                    )
                })}
            </div>

            {/* TAB CONTENT: Dashboard (Default) */}
            {activeTab === 'dashboard' && (
                <div className="animate-in fade-in zoom-in-95 duration-300 space-y-6">

                    {/* Top Row: Topology (Main Visual) */}
                    <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                        <div className="lg:col-span-2 space-y-6">
                            {/* Section 1: Fleet Topology */}
                            <section>
                                <div className="flex items-center justify-between mb-2">
                                    <h3 className="text-xs font-bold text-slate-400 uppercase tracking-widest">Live Topology</h3>
                                    <div className="flex space-x-2">
                                        <div className="flex items-center text-[10px] text-slate-400"><div className="w-1.5 h-1.5 rounded-full bg-emerald-400 mr-1" /> Stable</div>
                                        <div className="flex items-center text-[10px] text-slate-400"><div className="w-1.5 h-1.5 rounded-full bg-blue-400 mr-1" /> Optimizing</div>
                                    </div>
                                </div>
                                <InstanceFlowAnimation clusters={client.clusters} fallbackMode={isFallbackActive ? 'cluster' : 'none'} />
                            </section>

                            {/* IPv4 Summary */}
                            <IPv4Summary />

                            {/* Cost Chart */}
                            <div className="bg-white border border-slate-200 shadow-sm rounded-lg p-6">
                                <h3 className="text-sm font-bold text-slate-900 mb-4 flex items-center">
                                    <Activity className="w-4 h-4 text-slate-400 mr-2" />
                                    Cost vs. Savings Analysis
                                </h3>
                                <div className="w-full" style={{ height: 250 }}>
                                    <ResponsiveContainer width="100%" height="100%">
                                        <AreaChart data={client.savingsHistory}>
                                            <defs>
                                                <linearGradient id="colorSavings" x1="0" y1="0" x2="0" y2="1">
                                                    <stop offset="5%" stopColor="#10b981" stopOpacity={0.1} />
                                                    <stop offset="95%" stopColor="#10b981" stopOpacity={0} />
                                                </linearGradient>
                                            </defs>
                                            <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e2e8f0" />
                                            <XAxis dataKey="month" hide />
                                            <YAxis hide />
                                            <Tooltip
                                                contentStyle={{ backgroundColor: '#fff', border: '1px solid #e2e8f0', borderRadius: '8px', boxShadow: '0 4px 6px -1px rgb(0 0 0 / 0.1)' }}
                                                itemStyle={{ color: '#0f172a', fontSize: '12px', fontWeight: '600' }}
                                            />
                                            <Area type="monotone" dataKey="savings" stroke="#10b981" strokeWidth={2} fillOpacity={1} fill="url(#colorSavings)" />
                                            <Area type="monotone" dataKey="cost" stroke="#64748b" strokeWidth={2} fill="transparent" strokeDasharray="5 5" />
                                        </AreaChart>
                                    </ResponsiveContainer>
                                </div>
                            </div>
                        </div>

                        {/* Right Column: Stats & Controls */}
                        <div className="space-y-6">
                            {/* Distribution Chart */}
                            <ResourceDistributionChart clusters={client.clusters} />

                            {/* Activity Log */}
                            <ActivityLog />

                            {/* Policies (Options) */}
                            <div className="bg-white border border-slate-200 shadow-sm rounded-lg p-6">
                                <h3 className="text-sm font-bold text-slate-900 mb-6 flex items-center">
                                    <Settings className="w-4 h-4 text-slate-400 mr-2" />
                                    Fleet Policies
                                </h3>
                                <div className="space-y-6">
                                    <div className="flex items-center justify-between">
                                        <div>
                                            <div className="text-sm font-bold text-slate-900">Spot Fallback</div>
                                            <div className="text-xs text-slate-500">Auto-switch to OD on failure</div>
                                        </div>
                                        <Switch checked={policies.spotFallback} onChange={() => togglePolicy('spotFallback')} />
                                    </div>
                                    <div className="flex items-center justify-between">
                                        <div>
                                            <div className="text-sm font-bold text-slate-900">Aggressive Rebalance</div>
                                            <div className="text-xs text-slate-500">Replace nodes for 10% saving</div>
                                        </div>
                                        <Switch checked={policies.rebalanceAggressive} onChange={() => togglePolicy('rebalanceAggressive')} />
                                    </div>
                                    <div className="flex items-center justify-between">
                                        <div>
                                            <div className="text-sm font-bold text-slate-900">Auto-Binpacking</div>
                                            <div className="text-xs text-slate-500">Consolidate pods to fewer nodes</div>
                                        </div>
                                        <Switch checked={policies.autoBinpacking} onChange={() => togglePolicy('autoBinpacking')} />
                                    </div>
                                    <div className="flex items-center justify-between">
                                        <div>
                                            <div className="text-sm font-bold text-slate-900">Predictive Scaling</div>
                                            <div className="text-xs text-slate-500">Scale up before spike</div>
                                        </div>
                                        <Switch checked={true} onChange={() => { }} />
                                    </div>
                                </div>
                                <div className="mt-8 pt-6 border-t border-slate-100">
                                    <button className="w-full py-2 bg-slate-50 border border-slate-200 text-slate-700 text-xs font-bold rounded hover:bg-slate-100 transition-colors uppercase tracking-wider">
                                        Export Policy Config
                                    </button>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            )}

            {/* TAB CONTENT: Clusters */}
            {activeTab === 'clusters' && (
                <div className="animate-in fade-in zoom-in-95 duration-300">
                    <h3 className="text-lg font-bold text-slate-900 mb-4 px-1">Managed Clusters</h3>
                    <div className="space-y-4">
                        {client.clusters.map(cluster => (
                            <div
                                key={cluster.id}
                                onClick={() => onSelectCluster(cluster)}
                                className="bg-white border border-slate-200 rounded-lg p-4 shadow-sm hover:shadow-md hover:border-blue-400 transition-all cursor-pointer group flex items-center justify-between"
                            >
                                <div className="flex items-center space-x-4">
                                    <div className="p-2 bg-blue-50 text-blue-600 rounded-lg group-hover:bg-blue-600 group-hover:text-white transition-colors">
                                        <Layers className="w-6 h-6" />
                                    </div>
                                    <div>
                                        <h4 className="text-base font-bold text-slate-900 group-hover:text-blue-700 transition-colors">{cluster.name}</h4>
                                        <div className="flex items-center space-x-2 text-xs text-slate-500">
                                            <span>{cluster.region}</span>
                                            <span>•</span>
                                            <span>{cluster.nodeCount} Nodes</span>
                                        </div>
                                    </div>
                                </div>
                                <div className="text-slate-400">
                                    <ChevronDown className="w-5 h-5 -rotate-90 group-hover:translate-x-1 transition-transform" />
                                </div>
                            </div>
                        ))}
                    </div>
                </div>
            )}

            {/* TAB CONTENT: Unregistered Instances */}
            {activeTab === 'unregistered' && (
                <div className="animate-in fade-in zoom-in-95 duration-300">
                    <UnregisteredInstances />
                </div>
            )}

            {/* TAB CONTENT: Unmapped Volumes */}
            {activeTab === 'volumes' && (
                <div className="animate-in fade-in zoom-in-95 duration-300">
                    <UnmappedVolumes />
                </div>
            )}

            {/* TAB CONTENT: AMI & Snapshots */}
            {activeTab === 'snapshots' && (
                <div className="animate-in fade-in zoom-in-95 duration-300">
                    <AmiSnapshots />
                </div>
            )}

        </div>
    );
};

// --- Master List Components ---

const ClientCard = ({ client, onClick }) => (
    <div
        onClick={onClick}
        className="bg-white border border-slate-200 shadow-sm rounded-lg p-6 cursor-pointer hover:border-blue-400 hover:shadow-md transition-all group"
    >
        <div className="flex justify-between items-start mb-4">
            <div className="p-2 bg-slate-50 rounded-lg group-hover:bg-blue-50 transition-colors">
                <Globe className="w-6 h-6 text-slate-400 group-hover:text-blue-600 transition-colors" />
            </div>
            <div className={cn("px-2 py-1 rounded-full border text-[10px] font-bold uppercase tracking-wider",
                client.status === 'Active' ? "bg-emerald-50 border-emerald-100 text-emerald-700" : "bg-slate-50 border-slate-200 text-slate-500"
            )}>
                {client.status}
            </div>
        </div>

        <h3 className="text-lg font-bold text-slate-900 mb-1">{client.name}</h3>
        <p className="text-xs text-slate-400 mb-4 font-mono">{client.id}</p>

        <div className="space-y-3 pt-4 border-t border-slate-100">
            <div className="flex justify-between items-center text-xs">
                <span className="text-slate-500">Joined</span>
                <span className="font-medium text-slate-900">{client.joinedAt}</span>
            </div>
            <div className="flex justify-between items-center text-xs">
                <span className="text-slate-500">Clusters</span>
                <span className="font-medium text-slate-900">{client.clusters.length}</span>
            </div>
            <div className="flex justify-between items-center text-xs">
                <span className="text-slate-500">Total Nodes</span>
                <span className="font-medium text-slate-900">{client.totalNodes}</span>
            </div>
            <div className="flex justify-between items-center text-xs">
                <span className="text-slate-500">Mth. Savings</span>
                <span className="font-bold text-emerald-600">{client.potentialSavings}</span>
            </div>
        </div>
    </div>
);

const ClientMasterView = ({ clients, onSelectClient, onAddClient, onOpenGlobalPolicies }) => (
    <div className="space-y-8 animate-in fade-in slide-in-from-bottom-4 duration-500">
        <div className="flex justify-between items-end">
            <div>
                <h1 className="text-2xl font-bold text-slate-900 mb-2 tracking-tight">Mission Control</h1>
                <p className="text-slate-500 text-sm">Overview of all managed clients and fleet status</p>
            </div>
            <button
                onClick={onAddClient}
                className="flex items-center space-x-2 px-4 py-2 bg-blue-600 text-white text-sm font-bold rounded shadow-sm hover:bg-blue-700 transition-colors"
            >
                <Plus className="w-4 h-4" />
                <span>Add Client</span>
            </button>
            <button
                onClick={onOpenGlobalPolicies}
                className="flex items-center space-x-2 px-4 py-2 bg-white border border-slate-200 text-slate-700 text-sm font-bold rounded shadow-sm hover:bg-slate-50 transition-colors mr-2"
            >
                <Settings className="w-4 h-4 text-slate-500" />
                <span>Global Policies</span>
            </button>
        </div>

        {/* KPI Grid */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            <div className="bg-slate-900 rounded-xl p-6 shadow-xl text-white relative overflow-hidden">
                <div className="absolute top-0 right-0 p-8 bg-blue-500 rounded-full blur-[60px] opacity-20 -mr-10 -mt-10" />
                <div className="relative">
                    <div className="text-slate-400 text-xs font-bold uppercase tracking-wider mb-2">Total Monthly Savings</div>
                    <div className="text-3xl font-bold mb-4">$42,850</div>
                    <p className="text-xs text-slate-400 flex items-center">
                        <Zap className="w-3 h-3 text-yellow-400 mr-1" />
                        Across all managed fleets
                    </p>
                </div>
            </div>

            <div className="bg-white border border-slate-200 rounded-xl p-6 shadow-sm">
                <div className="text-slate-500 text-xs font-bold uppercase tracking-wider mb-2">Total Active Nodes</div>
                <div className="text-3xl font-bold text-slate-900 mb-4">1,248</div>
                <div className="w-full bg-slate-100 h-1.5 rounded-full overflow-hidden">
                    <div className="bg-blue-600 h-full w-[75%] rounded-full" />
                </div>
            </div>

            <div className="bg-white border border-slate-200 rounded-xl p-6 shadow-sm">
                <div className="text-slate-500 text-xs font-bold uppercase tracking-wider mb-2">Optimization Rate</div>
                <div className="text-3xl font-bold text-emerald-600 mb-4">98.2%</div>
                <div className="w-full bg-slate-100 h-1.5 rounded-full overflow-hidden">
                    <div className="bg-emerald-500 h-full w-[98%] rounded-full" />
                </div>
            </div>
        </div>

        {/* Client Grid */}
        <div>
            <h3 className="text-sm font-bold text-slate-900 uppercase tracking-wider mb-6">Client List</h3>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                {clients.map(client => (
                    <ClientCard key={client.id} client={client} onClick={() => onSelectClient(client)} />
                ))}
                {/* Add Logic for empty state or more clients */}
            </div>
        </div>
    </div>
);

// --- Add Client Modal ---
const AddClientModal = ({ onClose, onAdd }) => {
    const [name, setName] = useState('');
    const [region, setRegion] = useState('us-east-1');
    const [username, setUsername] = useState('');

    const handleSubmit = (e) => {
        e.preventDefault();
        onAdd({ name, region, username });
    };

    return (
        <div className="fixed inset-0 bg-slate-900/40 backdrop-blur-sm z-50 flex items-center justify-center p-4">
            <div className="bg-white rounded-xl shadow-2xl w-full max-w-md overflow-hidden animate-in fade-in zoom-in-95">
                <div className="px-6 py-4 border-b border-slate-100 flex justify-between items-center bg-slate-50">
                    <h3 className="text-lg font-bold text-slate-900">Add New Client</h3>
                    <button onClick={onClose} className="p-1 hover:bg-slate-200 rounded-full transition-colors">
                        <X className="w-5 h-5 text-slate-500" />
                    </button>
                </div>
                <form onSubmit={handleSubmit} className="p-6 space-y-4">
                    <div className="space-y-2">
                        <label className="text-xs font-bold text-slate-500 uppercase">Company Name</label>
                        <input
                            type="text"
                            required
                            className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                            placeholder="e.g. Globex Corp"
                            value={name}
                            onChange={e => setName(e.target.value)}
                        />
                    </div>
                    <div className="space-y-2">
                        <label className="text-xs font-bold text-slate-500 uppercase">Primary Region</label>
                        <select
                            className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 bg-white"
                            value={region}
                            onChange={e => setRegion(e.target.value)}
                        >
                            <option value="us-east-1">us-east-1 (N. Virginia)</option>
                            <option value="us-west-2">us-west-2 (Oregon)</option>
                            <option value="eu-west-1">eu-west-1 (Ireland)</option>
                            <option value="ap-south-1">ap-south-1 (Mumbai)</option>
                        </select>
                    </div>
                    <div className="space-y-2">
                        <label className="text-xs font-bold text-slate-500 uppercase">Client User Account (Optional)</label>
                        <input
                            type="text"
                            className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                            placeholder="Username (e.g. globex_admin)"
                            value={username}
                            onChange={e => setUsername(e.target.value)}
                        />
                        <p className="text-[10px] text-slate-400">Default password will be 'password123'</p>
                    </div>
                    <div className="pt-4 flex space-x-3">
                        <button
                            type="button"
                            onClick={onClose}
                            className="flex-1 px-4 py-2 border border-slate-200 rounded-lg text-sm font-bold text-slate-600 hover:bg-slate-50"
                        >
                            Cancel
                        </button>
                        <button
                            type="submit"
                            className="flex-1 px-4 py-2 bg-blue-600 rounded-lg text-sm font-bold text-white hover:bg-blue-700 shadow-sm"
                        >
                            Create Client
                        </button>
                    </div>
                </form>
            </div>
        </div>
    );
};

// --- Global Policy Modal ---
const GlobalPolicyModal = ({ onClose, onUpdate }) => {
    // Mock Global Defaults
    const [policies, setPolicies] = useState({
        spotFallback: true,
        rebalanceAggressive: false,
        autoBinpacking: true,
    });

    return (
        <div className="fixed inset-0 bg-slate-900/40 backdrop-blur-sm z-50 flex items-center justify-center p-4">
            <div className="bg-white rounded-xl shadow-2xl w-full max-w-lg overflow-hidden animate-in fade-in zoom-in-95">
                <div className="px-6 py-4 border-b border-slate-100 flex justify-between items-center bg-slate-50">
                    <div className="flex items-center space-x-2">
                        <ScrollText className="w-5 h-5 text-blue-600" />
                        <h3 className="text-lg font-bold text-slate-900">Global Fleet Policies</h3>
                    </div>
                    <button onClick={onClose} className="p-1 hover:bg-slate-200 rounded-full transition-colors">
                        <X className="w-5 h-5 text-slate-500" />
                    </button>
                </div>
                <div className="p-6 space-y-6">
                    <div className="bg-blue-50 border border-blue-100 rounded-lg p-3 text-xs text-blue-700 mb-4">
                        <Info className="w-4 h-4 inline mr-2 mb-0.5" />
                        Changes here will apply defaults to <strong>All Managed Clients</strong>.
                    </div>

                    <div className="space-y-4">
                        <div className="flex items-center justify-between p-3 border border-slate-200 rounded-lg hover:bg-slate-50">
                            <div>
                                <div className="text-sm font-bold text-slate-900">Spot Fallback Strategy</div>
                                <div className="text-xs text-slate-500">Auto-switch to On-Demand when Spot pools are exhausted.</div>
                            </div>
                            <Switch checked={policies.spotFallback} onChange={() => setPolicies(p => ({ ...p, spotFallback: !p.spotFallback }))} />
                        </div>
                        <div className="flex items-center justify-between p-3 border border-slate-200 rounded-lg hover:bg-slate-50">
                            <div>
                                <div className="text-sm font-bold text-slate-900">Aggressive Rebalancing</div>
                                <div className="text-xs text-slate-500">Proactively cycle nodes for &gt;10% savings opportunities.</div>
                            </div>
                            <Switch checked={policies.rebalanceAggressive} onChange={() => setPolicies(p => ({ ...p, rebalanceAggressive: !p.rebalanceAggressive }))} />
                        </div>
                        <div className="flex items-center justify-between p-3 border border-slate-200 rounded-lg hover:bg-slate-50">
                            <div>
                                <div className="text-sm font-bold text-slate-900">Auto-Binpacking</div>
                                <div className="text-xs text-slate-500">Consolidate workloads to minimize node count.</div>
                            </div>
                            <Switch checked={policies.autoBinpacking} onChange={() => setPolicies(p => ({ ...p, autoBinpacking: !p.autoBinpacking }))} />
                        </div>
                    </div>
                </div>
                <div className="px-6 py-4 bg-slate-50 border-t border-slate-100 flex justify-end space-x-3">
                    <button onClick={onClose} className="px-4 py-2 border border-slate-200 rounded-lg text-sm font-bold text-slate-600 hover:bg-white">
                        Cancel
                    </button>
                    <button
                        onClick={() => onUpdate(policies)}
                        className="px-4 py-2 bg-blue-600 rounded-lg text-sm font-bold text-white hover:bg-blue-700 shadow-sm"
                    >
                        Apply Global Changes
                    </button>
                </div>
            </div>
        </div>
    );
};


// --- Main Component ---


const NodeFleet = ({ externalSelectedClientId }) => {
    // Initialize with mockClients AND the Demo Client
    const [clients, setClients] = useState([...mockClients, DEMO_CLIENT]);
    const [selectedClient, setSelectedClient] = useState(null);
    const [selectedCluster, setSelectedCluster] = useState(null);
    const [selectedInstance, setSelectedInstance] = useState(null);
    const [isAddClientOpen, setIsAddClientOpen] = useState(false);
    const [isGlobalPolicyOpen, setIsGlobalPolicyOpen] = useState(false);

    // Sync with sidebar selection
    React.useEffect(() => {
        if (externalSelectedClientId) {
            const client = clients.find(c => c.id === externalSelectedClientId);
            if (client) {
                setSelectedClient(client);
                setSelectedCluster(null); // Reset drill-down
                setSelectedInstance(null);
            }
        } else if (externalSelectedClientId === null) {
            // If expressly passed null (sidebar header click), go to master
            setSelectedClient(null);
        }
    }, [externalSelectedClientId, clients]); // Add clients dependency

    const handleAddClient = (data) => {
        const newClient = {
            id: `client-${Date.now()}`,
            name: data.name,
            status: 'Active',
            joinedAt: 'Just now',
            totalNodes: 0,
            potentialSavings: '$0.00',
            policies: { spotFallback: false },
            savingsHistory: [],
            clusters: [],
            // If we were using auth context properly, we'd add the user there.
            // For now, we just simulate client creation.
        };
        setClients(prev => [...prev, newClient]);
        setIsAddClientOpen(false);
        // Simulate creating user in localStorage for AuthContext to potentially pick up?
        if (data.username) {
            const storedUsers = JSON.parse(localStorage.getItem('ecc_custom_users') || '[]');
            storedUsers.push({ username: data.username, password: 'password123', role: 'client', clientId: newClient.id });
            localStorage.setItem('ecc_custom_users', JSON.stringify(storedUsers));
            console.log("Created user:", data.username);
        }
    };

    const handleUpdateGlobalPolicies = (newPolicies) => {
        // Update all clients with new policies
        setClients(prev => prev.map(c => ({
            ...c,
            policies: { ...c.policies, ...newPolicies }
        })));
        setIsGlobalPolicyOpen(false);
    };

    return (
        <div className="relative">
            {isAddClientOpen && (
                <AddClientModal
                    onClose={() => setIsAddClientOpen(false)}
                    onAdd={handleAddClient}
                />
            )}

            {/* Instance Panel Overlay */}
            {selectedInstance && (
                <>
                    <div
                        className="fixed inset-0 bg-slate-900/20 backdrop-blur-sm z-40 transition-opacity"
                        onClick={() => setSelectedInstance(null)}
                    />
                    <InstanceDetailPanel
                        instance={selectedInstance}
                        onClose={() => setSelectedInstance(null)}
                    />
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
                    onSelectInstance={setSelectedInstance}
                />
            ) : (
                <ClientMasterView
                    clients={clients}
                    onSelectClient={setSelectedClient}
                    onAddClient={() => setIsAddClientOpen(true)}
                    onOpenGlobalPolicies={() => setIsGlobalPolicyOpen(true)}
                />
            )}
        </div>
    );
};

export default NodeFleet;
export { ClientDetailView, mockClients as MOCK_CLIENTS };


