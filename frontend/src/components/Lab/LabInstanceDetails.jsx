import React, { useState } from 'react';
import { ArrowLeft, TrendingUp, AlertTriangle, ShieldCheck, Zap, Server, History } from 'lucide-react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';
import { cn } from '../../lib/utils';
import { useModel } from '../../context/ModelContext';

const LabInstanceDetails = ({ instance, onBack }) => {
    // Instance here is actually a "Model" object now
    // { id, name, status, accuracy, ... }
    const { getLabModels, getProdModels } = useModel();
    const labModels = getLabModels();
    const prodModels = getProdModels();
    const allModels = [...labModels, ...prodModels];

    const [overrideModel, setOverrideModel] = useState(instance.currentModel || instance.name);

    // Mock History Log Data (Scrollable)
    const historyLog = Array.from({ length: 20 }).map((_, i) => ({
        id: i,
        date: '2023-12-15',
        time: `10:${45 - i}`,
        action: i % 3 === 0 ? 'Switch: Spot -> On-Demand' : i % 2 === 0 ? 'Prediction: Safe' : 'Switch: On-Demand -> Spot',
        model: i % 4 === 0 ? 'CostSaver X1' : 'DeepSpot V3',
        type: i % 3 === 0 ? 'switch_safe' : i % 2 === 0 ? 'info' : 'switch_spot'
    }));

    // Mock Alternate Instances
    const alternates = [
        { type: 'g4dn.xlarge', spotPrice: '$0.158', onDemandPrice: '$0.526', savings: '70%' },
        { type: 'g5.xlarge', spotPrice: '$0.240', onDemandPrice: '$0.750', savings: '68%' },
        { type: 'p3.2xlarge', spotPrice: '$0.918', onDemandPrice: '$3.060', savings: '70%' },
        { type: 'p2.xlarge', spotPrice: '$0.270', onDemandPrice: '$0.900', savings: '70%' },
        { type: 'g3.4xlarge', spotPrice: '$0.400', onDemandPrice: '$1.140', savings: '65%' } // 5th for variety
    ];

    // Mock Pricing History Data for Graph
    const pricingHistory = [
        { time: '10:00', 'g4dn.xlarge': 0.15, 'g5.xlarge': 0.24, 'p3.2xlarge': 0.90, 'p2.xlarge': 0.27 },
        { time: '10:15', 'g4dn.xlarge': 0.16, 'g5.xlarge': 0.24, 'p3.2xlarge': 0.92, 'p2.xlarge': 0.27 },
        { time: '10:30', 'g4dn.xlarge': 0.15, 'g5.xlarge': 0.25, 'p3.2xlarge': 0.91, 'p2.xlarge': 0.28 },
        { time: '10:45', 'g4dn.xlarge': 0.15, 'g5.xlarge': 0.24, 'p3.2xlarge': 0.89, 'p2.xlarge': 0.27 },
        { time: '11:00', 'g4dn.xlarge': 0.18, 'g5.xlarge': 0.24, 'p3.2xlarge': 0.95, 'p2.xlarge': 0.27 }, // Spike
        { time: '11:15', 'g4dn.xlarge': 0.15, 'g5.xlarge': 0.23, 'p3.2xlarge': 0.90, 'p2.xlarge': 0.27 },
        { time: '11:30', 'g4dn.xlarge': 0.15, 'g5.xlarge': 0.24, 'p3.2xlarge': 0.91, 'p2.xlarge': 0.27 },
    ];

    const colors = ['#8b5cf6', '#10b981', '#f59e0b', '#3b82f6']; // Purple, Emerald, Amber, Blue

    return (
        <div className="space-y-6 animate-in fade-in slide-in-from-right-8 duration-300 h-full flex flex-col">
            {/* Nav */}
            <div className="flex items-center justify-between flex-shrink-0">
                <button
                    onClick={onBack}
                    className="flex items-center text-slate-500 hover:text-purple-600 transition-colors text-sm font-medium"
                >
                    <ArrowLeft className="w-4 h-4 mr-1" />
                    Back to Experiments
                </button>
                <div className="text-xs font-mono text-slate-400">Instance: {instance.id}</div>
            </div>

            {/* Header */}
            <div className="bg-white border border-slate-200 rounded-xl p-6 shadow-sm flex-shrink-0">
                <div className="flex items-start justify-between">
                    <div>
                        <h1 className="text-xl font-bold text-slate-900 flex items-center">
                            <Server className="w-6 h-6 mr-3 text-purple-600" />
                            {instance.type || 'Unknown Type'}
                            <span className="ml-3 px-2 py-0.5 bg-slate-100 border border-slate-200 rounded text-xs text-slate-500 font-mono font-normal">
                                {instance.id}
                            </span>
                        </h1>
                        <div className="mt-4 flex items-center gap-4">
                            <div className="flex flex-col">
                                <label className="text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-1">Active Model</label>
                                <select
                                    value={overrideModel}
                                    onChange={(e) => setOverrideModel(e.target.value)}
                                    className="px-3 py-1.5 bg-slate-50 border border-slate-200 rounded-lg text-sm font-medium text-slate-900 focus:outline-none focus:ring-2 focus:ring-purple-500 min-w-[200px]"
                                >
                                    {allModels.map(m => (
                                        <option key={m.id} value={m.name}>{m.name} ({m.scope})</option>
                                    ))}
                                    {!allModels.find(m => m.name === overrideModel) && <option value={overrideModel}>{overrideModel}</option>}
                                </select>
                            </div>

                            <div className="h-8 w-px bg-slate-200 mx-2"></div>

                            <div className="flex flex-col">
                                <label className="text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-1">Status</label>
                                <span className={cn(
                                    "px-2 py-1 rounded text-xs font-bold w-fit",
                                    instance.status === 'active' ? "bg-emerald-50 text-emerald-700" : "bg-slate-100 text-slate-600"
                                )}>
                                    {instance.status ? instance.status.toUpperCase() : 'ACTIVE'}
                                </span>
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            {/* Main Content Grid */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 flex-1 min-h-0">

                {/* Left Column: Analysis */}
                <div className="lg:col-span-2 space-y-6 flex flex-col">

                    {/* 1. Alternate Pricing Graph */}
                    <div className="bg-white border border-slate-200 rounded-xl p-6 shadow-sm h-[350px] flex-shrink-0">
                        <h3 className="text-sm font-bold text-slate-900 mb-4 flex items-center justify-between">
                            <span className="flex items-center"><TrendingUp className="w-4 h-4 mr-2 text-slate-400" /> Alternate Instance Pricing</span>
                            <span className="text-xs font-normal text-slate-400">Live Spot Market</span>
                        </h3>
                        <div className="h-[250px] w-full">
                            <ResponsiveContainer width="100%" height="100%">
                                <LineChart data={pricingHistory}>
                                    <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e2e8f0" />
                                    <XAxis dataKey="time" stroke="#94a3b8" fontSize={12} tickLine={false} axisLine={false} />
                                    <YAxis stroke="#94a3b8" fontSize={12} tickFormatter={(val) => `$${val}`} tickLine={false} axisLine={false} />
                                    <Tooltip
                                        contentStyle={{ backgroundColor: '#fff', borderRadius: '8px', border: '1px solid #e2e8f0', boxShadow: '0 4px 6px -1px rgb(0 0 0 / 0.1)' }}
                                        labelStyle={{ color: '#64748b', marginBottom: '0.5rem' }}
                                    />
                                    <Legend wrapperStyle={{ paddingTop: '10px' }} />
                                    {Object.keys(pricingHistory[0]).filter(k => k !== 'time').map((key, index) => (
                                        <Line
                                            key={key}
                                            type="monotone"
                                            dataKey={key}
                                            stroke={colors[index % colors.length]}
                                            strokeWidth={2}
                                            dot={false}
                                            activeDot={{ r: 6 }}
                                        />
                                    ))}
                                </LineChart>
                            </ResponsiveContainer>
                        </div>
                    </div>

                    {/* 2. Alternate Instances List */}
                    <div className="bg-white border border-slate-200 rounded-xl shadow-sm overflow-hidden flex-shrink-0">
                        <div className="px-6 py-4 border-b border-slate-200 bg-slate-50/50">
                            <h3 className="text-sm font-bold text-slate-900 flex items-center">
                                <Zap className="w-4 h-4 mr-2 text-slate-400" />
                                Considered Alternates
                            </h3>
                        </div>
                        <div className="overflow-x-auto">
                            <table className="w-full text-sm text-left">
                                <thead className="bg-slate-50 text-slate-500 font-medium border-b border-slate-200">
                                    <tr>
                                        <th className="px-6 py-3">Instance Type</th>
                                        <th className="px-6 py-3">Spot Price</th>
                                        <th className="px-6 py-3">On-Demand</th>
                                        <th className="px-6 py-3 text-emerald-600">Savings</th>
                                    </tr>
                                </thead>
                                <tbody className="divide-y divide-slate-100">
                                    {alternates.map((alt, i) => (
                                        <tr key={i} className="hover:bg-slate-50">
                                            <td className="px-6 py-3 font-mono font-medium text-slate-900">{alt.type}</td>
                                            <td className="px-6 py-3 text-slate-600">{alt.spotPrice}</td>
                                            <td className="px-6 py-3 text-slate-400 line-through">{alt.onDemandPrice}</td>
                                            <td className="px-6 py-3 font-bold text-emerald-600">{alt.savings}</td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    </div>
                </div>

                {/* Right Column: Scrollable History */}
                <div className="bg-white border border-slate-200 rounded-xl shadow-sm flex flex-col h-[600px]">
                    <div className="px-6 py-4 border-b border-slate-200 bg-slate-50/50 flex-shrink-0">
                        <h3 className="text-sm font-bold text-slate-900 flex items-center">
                            <History className="w-4 h-4 mr-2 text-slate-400" />
                            Decision History
                        </h3>
                    </div>
                    <div className="flex-1 overflow-y-auto p-4 space-y-4 pr-2">
                        {historyLog.map((log, i) => (
                            <div key={i} className="flex gap-3 group">
                                <div className="flex flex-col items-center">
                                    <div className={cn(
                                        "w-2 h-2 rounded-full mt-1.5 flex-shrink-0",
                                        log.type === 'info' ? "bg-slate-300" :
                                            log.type === 'switch_safe' ? "bg-emerald-500" :
                                                log.type === 'switch_spot' ? "bg-purple-500" : "bg-slate-300"
                                    )} />
                                    {i !== historyLog.length - 1 && <div className="w-px bg-slate-100 flex-1 my-1" />}
                                </div>
                                <div className="pb-2">
                                    <div className="flex items-baseline gap-2 mb-1">
                                        <span className="text-xs font-mono text-slate-500">{log.date}</span>
                                        <span className="text-xs font-mono font-bold text-slate-700">{log.time}</span>
                                    </div>
                                    <div className="text-sm font-medium text-slate-900">{log.action}</div>
                                    <div className="text-xs text-slate-400 mt-0.5">Model: {log.model}</div>
                                </div>
                            </div>
                        ))}
                    </div>
                </div>
            </div>
        </div>
    );
};

export default LabInstanceDetails;
