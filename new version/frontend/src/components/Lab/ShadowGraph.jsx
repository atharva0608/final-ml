import React, { useState, useEffect } from 'react';
import { Activity, AlertCircle } from 'lucide-react';
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import api from '../../services/api';

const ShadowGraph = ({ activeModel, modelId, instanceId }) => {
    const [data, setData] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);

    useEffect(() => {
        if (!instanceId) {
            setData([]);
            setLoading(false);
            return;
        }

        const fetchData = async () => {
            try {
                setLoading(true);
                setError(null);
                const logs = await api.getExperimentLogs(instanceId, 30);

                // Transform experiment logs into chart data
                const chartData = (logs || []).map(log => ({
                    time: new Date(log.created_at).toLocaleTimeString('en-US', {
                        hour12: false,
                        hour: '2-digit',
                        minute: '2-digit'
                    }),
                    production: log.baseline_risk_score || 0,
                    shadow: log.predicted_risk_score || 0
                })).reverse();

                setData(chartData.length > 0 ? chartData : []);
            } catch (err) {
                console.error('Failed to fetch shadow evaluation data:', err);
                setError('Unable to load evaluation data');
                setData([]);
            } finally {
                setLoading(false);
            }
        };

        fetchData();
        const interval = setInterval(fetchData, 10000); // Refresh every 10s
        return () => clearInterval(interval);
    }, [instanceId]);

    return (
        <div className="bg-white border border-slate-200 rounded-xl p-6 shadow-sm min-h-[350px] flex flex-col h-full">
            <div className="flex items-center justify-between mb-6">
                <h3 className="text-sm font-bold text-slate-900 flex items-center">
                    <Activity className="w-4 h-4 mr-2 text-purple-600" />
                    Shadow Evaluation (Risk Score)
                </h3>
                <div className="flex items-center gap-4 text-xs">
                    <div className="flex items-center">
                        <span className="w-2 h-2 rounded-full bg-blue-500 mr-2"></span>
                        <span className="text-slate-500">Production (Baseline)</span>
                    </div>
                    <div className="flex items-center">
                        <span className="w-2 h-2 rounded-full bg-purple-500 mr-2"></span>
                        <span className="text-purple-700 font-bold">{activeModel} (Shadow)</span>
                    </div>
                </div>
            </div>

            <div className="flex-1 w-full min-h-[250px]">
                {loading ? (
                    <div className="flex items-center justify-center h-full text-slate-400">
                        <div className="text-center">
                            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-purple-600 mx-auto mb-2"></div>
                            <div className="text-xs">Loading evaluation data...</div>
                        </div>
                    </div>
                ) : error ? (
                    <div className="flex items-center justify-center h-full">
                        <div className="text-center text-slate-500">
                            <AlertCircle className="w-8 h-8 mx-auto mb-2" />
                            <div className="text-xs">{error}</div>
                        </div>
                    </div>
                ) : data.length === 0 ? (
                    <div className="flex items-center justify-center h-full">
                        <div className="text-center text-slate-400">
                            <AlertCircle className="w-8 h-8 mx-auto mb-2 opacity-50" />
                            <div className="text-xs">No evaluation data available</div>
                            <div className="text-[10px] mt-1">Run experiments to see comparison data</div>
                        </div>
                    </div>
                ) : (
                    <ResponsiveContainer width="100%" height="100%">
                        <AreaChart data={data}>
                            <defs>
                                <linearGradient id="colorProd" x1="0" y1="0" x2="0" y2="1">
                                    <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.1} />
                                    <stop offset="95%" stopColor="#3b82f6" stopOpacity={0} />
                                </linearGradient>
                                <linearGradient id="colorShadow" x1="0" y1="0" x2="0" y2="1">
                                    <stop offset="5%" stopColor="#a855f7" stopOpacity={0.2} />
                                    <stop offset="95%" stopColor="#a855f7" stopOpacity={0} />
                                </linearGradient>
                            </defs>
                            <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" vertical={false} />
                            <XAxis
                                dataKey="time"
                                stroke="#94a3b8"
                                tick={{ fontSize: 10 }}
                                tickLine={false}
                                axisLine={false}
                            />
                            <YAxis
                                stroke="#94a3b8"
                                tick={{ fontSize: 10 }}
                                tickLine={false}
                                axisLine={false}
                                domain={[0, 100]}
                            />
                            <Tooltip
                                contentStyle={{ backgroundColor: '#ffffff', borderColor: '#e2e8f0', color: '#1e293b' }}
                                itemStyle={{ fontSize: '12px' }}
                                labelStyle={{ color: '#64748b', fontSize: '10px', marginBottom: '4px' }}
                            />
                            <Area
                                type="monotone"
                                dataKey="production"
                                stroke="#3b82f6"
                                strokeWidth={2}
                                fillOpacity={1}
                                fill="url(#colorProd)"
                            />
                            <Area
                                type="monotone"
                                dataKey="shadow"
                                stroke="#a855f7"
                                strokeWidth={2}
                                strokeDasharray="4 4" // Dashed line for experimental
                                fillOpacity={1}
                                fill="url(#colorShadow)"
                            />
                        </AreaChart>
                    </ResponsiveContainer>
                )}
            </div>
        </div>
    );
};

export default ShadowGraph;
