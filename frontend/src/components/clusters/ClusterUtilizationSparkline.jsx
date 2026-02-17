import React, { useEffect, useState } from 'react';
import { AreaChart, Area, ResponsiveContainer, Tooltip } from 'recharts';
import api from '../../services/api';

const ClusterUtilizationSparkline = ({ clusterId }) => {
    const [data, setData] = useState(null);

    useEffect(() => {
        const fetchData = async () => {
            try {
                // If clusterId is missing or mock mode, generate random data or fetch
                if (!clusterId) return;
                const res = await api.get(`/metrics/cluster/${clusterId}/utilization`);
                setData(res.data);
            } catch (err) {
                console.error("Failed to load utilization sparkline", err);
            }
        };
        fetchData();
    }, [clusterId]);

    if (!data) return <div className="h-8 w-24 bg-gray-50 animate-pulse rounded"></div>;

    const chartData = data.cpu_history.map((val, i) => ({ i, val }));

    return (
        <div className="flex items-center gap-2">
            <div className="h-8 w-24">
                <ResponsiveContainer width="100%" height="100%">
                    <AreaChart data={chartData}>
                        <defs>
                            <linearGradient id="colorCpu" x1="0" y1="0" x2="0" y2="1">
                                <stop offset="5%" stopColor="#3B82F6" stopOpacity={0.3} />
                                <stop offset="95%" stopColor="#3B82F6" stopOpacity={0} />
                            </linearGradient>
                        </defs>
                        <Tooltip content={<></>} cursor={false} />
                        <Area type="monotone" dataKey="val" stroke="#3B82F6" strokeWidth={1.5} fill="url(#colorCpu)" />
                    </AreaChart>
                </ResponsiveContainer>
            </div>
            <div className="flex flex-col text-[10px] leading-tight">
                <span className="font-bold text-gray-700">{data.cpu_current}%</span>
                <span className="text-gray-400">CPU</span>
            </div>
        </div>
    );
};

export default ClusterUtilizationSparkline;
