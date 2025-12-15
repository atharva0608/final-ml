import React, { useState, useEffect } from 'react';
import { Activity } from 'lucide-react';
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';

// Mock Data Generator for "Live" Feel
const generateData = () => {
    const data = [];
    let baseRisk = 20;
    for (let i = 0; i < 30; i++) {
        const volatility = Math.random() * 10 - 5;
        baseRisk = Math.max(5, Math.min(90, baseRisk + volatility));

        data.push({
            time: `${10 + Math.floor(i / 60)}:${(i % 60).toString().padStart(2, '0')}`,
            production: Math.floor(baseRisk), // Production Model Risk
            shadow: Math.floor(baseRisk * (0.8 + Math.random() * 0.4)), // Shadow Model (Experimental)
        });
    }
    return data;
};

const ShadowGraph = ({ activeModel }) => {
    const [data, setData] = useState(generateData());

    // Simulate Live Data Update
    useEffect(() => {
        const interval = setInterval(() => {
            setData(prev => {
                const lastRisk = prev[prev.length - 1].production;
                const newTime = new Date().toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' });
                const newRisk = Math.max(5, Math.min(90, lastRisk + (Math.random() * 10 - 5)));

                const newPoint = {
                    time: newTime,
                    production: Math.floor(newRisk),
                    shadow: Math.floor(newRisk * (0.7 + Math.random() * 0.5)) // Shadow varies
                };
                return [...prev.slice(1), newPoint];
            });
        }, 2000);
        return () => clearInterval(interval);
    }, []);

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
            </div>
        </div>
    );
};

export default ShadowGraph;
