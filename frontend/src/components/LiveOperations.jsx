import React from 'react';
import { FunnelChart, Funnel, Tooltip, ResponsiveContainer, LabelList, Cell } from 'recharts';
import { Shield, Filter, Zap, Activity } from 'lucide-react';
import { cn } from '../lib/utils';

const data = [
    {
        "value": 500,
        "name": "Pools Scanned",
        "fill": "#3b82f6",
        "description": "Total candidates found"
    },
    {
        "value": 400,
        "name": "Static Filter",
        "fill": "#6366f1",
        "description": "Hardware & Region checks"
    },
    {
        "value": 350,
        "name": "ML Prediction",
        "fill": "#8b5cf6",
        "description": "Risk < 0.85"
    },
    {
        "value": 5,
        "name": "Final Top 5",
        "fill": "#10b981",
        "description": "Lowest cost & risk"
    }
];

const MetricCard = ({ label, value, icon: Icon, trend }) => (
    <div className="bg-white border border-slate-200 shadow-sm rounded-lg p-6">
        <div className="flex justify-between items-start mb-4">
            <Icon className="w-5 h-5 text-slate-400" />
            {trend && (
                <span className={cn(
                    "text-xs font-bold px-2 py-0.5 rounded",
                    trend.includes('+') ? "text-emerald-700 bg-emerald-50" : "text-amber-700 bg-amber-50"
                )}>
                    {trend}
                </span>
            )}
        </div>
        <div className="text-3xl font-bold text-slate-900 tracking-tight mb-1 font-sans">{value}</div>
        <div className="text-xs font-bold uppercase tracking-wider text-slate-500">{label}</div>
    </div>
);

const CustomTooltip = ({ active, payload }) => {
    if (active && payload && payload.length) {
        const data = payload[0].payload;
        return (
            <div className="bg-white border border-slate-200 p-3 shadow-xl rounded-sm">
                <p className="font-bold text-slate-900 text-sm">{data.name}</p>
                <p className="text-blue-600 text-xs font-mono mt-1">Count: {data.value}</p>
                <p className="text-slate-400 text-[10px] mt-1 uppercase tracking-wide">{data.description}</p>
            </div>
        );
    }
    return null;
};

const LiveOperations = () => {
    return (
        <div className="space-y-8">
            <div>
                <h1 className="text-2xl font-bold text-slate-900 mb-2 tracking-tight">Live Operations</h1>
                <p className="text-slate-500 text-sm">Real-time pipeline monitoring and decision analytics</p>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
                <MetricCard
                    label="Active Instances"
                    value="142"
                    icon={Activity}
                    trend="+12%"
                />
                <MetricCard
                    label="Risk Detected"
                    value="3"
                    icon={Shield}
                    trend="Warning"
                />
                <MetricCard
                    label="Cost Savings"
                    value="$1.2k"
                    icon={Filter}
                    trend="Daily"
                />
                <MetricCard
                    label="Optimizations"
                    value="89"
                    icon={Zap}
                    trend="Last 1h"
                />
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
                <div className="lg:col-span-2 bg-white border border-slate-200 shadow-sm rounded-lg p-8">
                    <div className="flex items-center justify-between mb-8">
                        <h2 className="text-base font-bold text-slate-900">Decision Pipeline Funnel</h2>
                        <div className="flex space-x-4">
                            <span className="flex items-center text-[10px] font-bold uppercase text-slate-400 tracking-wider">
                                <div className="w-2 h-2 rounded-full bg-blue-600 mr-2"></div>
                                Input
                            </span>
                            <span className="flex items-center text-[10px] font-bold uppercase text-slate-400 tracking-wider">
                                <div className="w-2 h-2 rounded-full bg-indigo-500 mr-2"></div>
                                Processing
                            </span>
                            <span className="flex items-center text-[10px] font-bold uppercase text-slate-400 tracking-wider">
                                <div className="w-2 h-2 rounded-full bg-emerald-500 mr-2"></div>
                                Output
                            </span>
                        </div>
                    </div>

                    <div className="h-[400px] w-full">
                        <ResponsiveContainer width="100%" height="100%">
                            <FunnelChart>
                                <Tooltip content={<CustomTooltip />} cursor={{ fill: 'transparent' }} />
                                <Funnel
                                    dataKey="value"
                                    data={data}
                                    isAnimationActive
                                >
                                    <LabelList position="right" fill="#64748b" stroke="none" dataKey="name" />
                                </Funnel>
                            </FunnelChart>
                        </ResponsiveContainer>
                    </div>
                </div>

                <div className="bg-white border border-slate-200 shadow-sm rounded-lg p-6">
                    <h2 className="text-base font-bold text-slate-900 mb-6">Pipeline Status</h2>
                    <div className="space-y-4">
                        {[
                            { name: "Scraper Service", status: "Operational", color: "text-emerald-700 bg-emerald-50 border-emerald-100" },
                            { name: "Risk Engine", status: "Processing", color: "text-blue-700 bg-blue-50 border-blue-100" },
                            { name: "Cost Optimizer", status: "Operational", color: "text-emerald-700 bg-emerald-50 border-emerald-100" },
                            { name: "K8s Controller", status: "Standby", color: "text-slate-600 bg-slate-50 border-slate-100" },
                        ].map((item, idx) => (
                            <div key={idx} className="flex items-center justify-between p-3 rounded border border-slate-100 bg-white hover:bg-slate-50 transition-colors">
                                <span className="text-sm font-semibold text-slate-700">{item.name}</span>
                                <span className={cn("text-[10px] font-bold uppercase tracking-wider px-2 py-1 rounded border", item.color)}>
                                    {item.status}
                                </span>
                            </div>
                        ))}
                    </div>

                    <div className="mt-8 pt-6 border-t border-slate-100">
                        <p className="text-[10px] font-bold uppercase text-slate-400 mb-3 tracking-wider">System Load</p>
                        <div className="w-full bg-slate-100 h-1.5 mb-2 rounded-full overflow-hidden">
                            <div className="bg-blue-600 h-full rounded-full" style={{ width: '45%' }}></div>
                        </div>
                        <div className="flex justify-between text-[10px] font-mono text-slate-400">
                            <span>0%</span>
                            <span>45%</span>
                            <span>100%</span>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
};

export default LiveOperations;
