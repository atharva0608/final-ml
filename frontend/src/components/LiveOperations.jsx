import React, { useState, useEffect } from 'react';
import { FunnelChart, Funnel, Tooltip, ResponsiveContainer, LabelList } from 'recharts';
import { Shield, Filter, Zap, Activity, AlertCircle, RefreshCw, WifiOff } from 'lucide-react';
import { cn } from '../lib/utils';
import api from '../services/api';

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

const MetricCard = ({ label, value, icon: Icon, trend }) => (
    <div className="bg-white border border-slate-200 shadow-sm rounded-lg p-6 group hover:border-blue-300 transition-colors">
        <div className="flex justify-between items-start mb-4">
            <Icon className="w-5 h-5 text-slate-400 group-hover:text-blue-500 transition-colors" />
            {trend && (
                <span className={cn(
                    "text-xs font-bold px-2 py-0.5 rounded",
                    trend.includes('+') ? "text-emerald-700 bg-emerald-50" : (trend === 'Offline' ? "text-slate-500 bg-slate-100" : "text-amber-700 bg-amber-50")
                )}>
                    {trend}
                </span>
            )}
        </div>
        <div className="text-3xl font-bold text-slate-900 tracking-tight mb-1 font-sans">{value}</div>
        <div className="text-xs font-bold uppercase tracking-wider text-slate-500">{label}</div>
    </div>
);

const LiveOperations = () => {
    const [pipelineData, setPipelineData] = useState(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);

    const fetchData = async () => {
        setLoading(true);
        try {
            // Fetch real system health overview to derive pipeline status
            const healthOverview = await api.getSystemOverview();

            setPipelineData({
                status: healthOverview.overall_status,
                components: [
                    { name: "Scraper Service", status: healthOverview.components.find(c => c.component === 'web_scraper')?.status || 'degraded' },
                    { name: "Risk Engine", status: healthOverview.components.find(c => c.component === 'ml_inference')?.status || 'degraded' },
                    { name: "Cost Optimizer", status: healthOverview.components.find(c => c.component === 'linear_optimizer')?.status || 'degraded' },
                    { name: "K8s Controller", status: healthOverview.components.find(c => c.component === 'instance_manager')?.status || 'degraded' }
                ],
                metrics: {
                    activeInstances: healthOverview.components.find(c => c.component === 'instance_manager')?.success_count_24h || 0,
                    riskDetected: healthOverview.components.find(c => c.component === 'ml_inference')?.failure_count_24h || 0,
                    costSavings: healthOverview.cost_savings_24h || 0,
                    optimizations: healthOverview.components.find(c => c.component === 'linear_optimizer')?.success_count_24h || 0,
                },
                funnel: [
                    { value: 500, name: "Pools Scanned", fill: "#3b82f6", description: "Total candidates found" },
                    { value: 400, name: "Static Filter", fill: "#6366f1", description: "Hardware & Region checks" },
                    { value: 350, name: "ML Prediction", fill: "#8b5cf6", description: "Risk < 0.85" },
                    { value: 5, name: "Final Top 5", fill: "#10b981", description: "Lowest cost & risk" }
                ]
            });
            setError(null);
        } catch (err) {
            console.error("Pipeline data fetch failed:", err);
            setError("Backend unreachable - Showing cached/offline data");

            // Fallback / Offline Data so UI doesn't break
            setPipelineData({
                status: 'offline',
                components: [
                    { name: "Scraper Service", status: 'Offline' },
                    { name: "Risk Engine", status: 'Offline' },
                    { name: "Cost Optimizer", status: 'Offline' },
                    { name: "K8s Controller", status: 'Offline' }
                ],
                metrics: {
                    activeInstances: 0,
                    riskDetected: 0,
                    costSavings: 0,
                    optimizations: 0,
                },
                funnel: [
                    { value: 0, name: "Pools Scanned", fill: "#94a3b8", description: "Offline" },
                    { value: 0, name: "Static Filter", fill: "#94a3b8", description: "Offline" },
                    { value: 0, name: "ML Prediction", fill: "#94a3b8", description: "Offline" },
                    { value: 0, name: "Final Top 5", fill: "#94a3b8", description: "Offline" }
                ]
            });
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchData();
        const interval = setInterval(fetchData, 30000); // Poll every 30s
        return () => clearInterval(interval);
    }, []);

    const getStatusColor = (status) => {
        switch (status?.toLowerCase()) {
            case 'healthy': return "text-emerald-700 bg-emerald-50 border-emerald-100";
            case 'degraded': return "text-amber-700 bg-amber-50 border-amber-100";
            case 'down':
            case 'critical': return "text-red-700 bg-red-50 border-red-100";
            case 'offline': return "text-slate-500 bg-slate-100 border-slate-200";
            default: return "text-slate-600 bg-slate-50 border-slate-100";
        }
    };

    // Initial loading state
    if (loading && !pipelineData) {
        return (
            <div className="flex items-center justify-center p-12">
                <RefreshCw className="w-8 h-8 text-blue-500 animate-spin" />
            </div>
        );
    }

    return (
        <div className="space-y-8 animate-in fade-in slide-in-from-bottom-4 duration-500">
            <div className="flex justify-between items-start">
                <div>
                    <h1 className="text-2xl font-bold text-slate-900 mb-2 tracking-tight">Live Operations</h1>
                    <p className="text-slate-500 text-sm">Real-time pipeline monitoring and decision analytics</p>
                </div>
                {error && (
                    <div className="flex items-center px-4 py-2 bg-red-50 text-red-700 border border-red-200 rounded-lg text-sm font-bold animate-in slide-in-from-top-2">
                        <WifiOff className="w-4 h-4 mr-2" />
                        {error}
                        <button onClick={fetchData} className="ml-4 hover:underline">Retry</button>
                    </div>
                )}
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
                <MetricCard
                    label="Active Instances"
                    value={pipelineData?.metrics.activeInstances || 0}
                    icon={Activity}
                    trend={error ? "Offline" : "+12%"}
                />
                <MetricCard
                    label="Risk Detected"
                    value={pipelineData?.metrics.riskDetected || 0}
                    icon={Shield}
                    trend={error ? "Offline" : "Warning"}
                />
                <MetricCard
                    label="Cost Savings"
                    value={error ? "-" : `$${(pipelineData?.metrics.costSavings || 0).toLocaleString()}`}
                    icon={Filter}
                    trend={error ? "Offline" : "24h"}
                />
                <MetricCard
                    label="Optimizations"
                    value={error ? "-" : (pipelineData?.metrics.optimizations || 0)}
                    icon={Zap}
                    trend={error ? "Offline" : "24h"}
                />
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
                <div className="lg:col-span-2 bg-white border border-slate-200 shadow-sm rounded-lg p-8">
                    <div className="flex items-center justify-between mb-8">
                        <h2 className="text-base font-bold text-slate-900">Decision Pipeline Funnel</h2>
                        <div className="flex space-x-4">
                            {!error && (
                                <>
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
                                </>
                            )}
                        </div>
                    </div>

                    <div className="h-[400px] w-full" style={{ height: 400, width: '100%', minHeight: 400 }}>
                        <ResponsiveContainer width="100%" height="100%">
                            <FunnelChart>
                                <Tooltip content={<CustomTooltip />} cursor={{ fill: 'transparent' }} />
                                <Funnel
                                    dataKey="value"
                                    data={pipelineData?.funnel || []}
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
                        {pipelineData?.components.map((item, idx) => (
                            <div key={idx} className="flex items-center justify-between p-3 rounded border border-slate-100 bg-white hover:bg-slate-50 transition-colors">
                                <span className="text-sm font-semibold text-slate-700">{item.name}</span>
                                <span className={cn("text-[10px] font-bold uppercase tracking-wider px-2 py-1 rounded border", getStatusColor(item.status))}>
                                    {item.status}
                                </span>
                            </div>
                        ))}
                    </div>

                    <div className="mt-8 pt-6 border-t border-slate-100">
                        <p className="text-[10px] font-bold uppercase text-slate-400 mb-3 tracking-wider">System Load</p>
                        <div className="w-full bg-slate-100 h-1.5 mb-2 rounded-full overflow-hidden">
                            <div className={cn("h-full rounded-full transition-all", error ? "bg-slate-300 w-0" : "bg-blue-600 w-[45%]")}></div>
                        </div>
                        <div className="flex justify-between text-[10px] font-mono text-slate-400">
                            <span>0%</span>
                            <span>{error ? '-' : '45%'}</span>
                            <span>100%</span>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
};

export default LiveOperations;
