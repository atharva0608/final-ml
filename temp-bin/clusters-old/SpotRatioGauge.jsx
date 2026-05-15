import React from 'react';
import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from 'recharts';

const SpotRatioGauge = ({ spotPct, onDemandPct }) => {
    // Expected props: spotPct (0-100), onDemandPct (0-100)
    // If missing, use mock or 0
    const spot = spotPct || 0;
    const od = onDemandPct || 0;
    const total = spot + od;

    // Normalize if total != 100
    const spotVal = total > 0 ? (spot / total) * 100 : 0;
    const odVal = total > 0 ? (od / total) * 100 : 0;

    const data = [
        { name: 'Spot', value: spotVal, color: '#10B981' }, // Green
        { name: 'On-Demand', value: odVal, color: '#F59E0B' }, // Yellow/Orange
    ];

    return (
        <div className="relative h-16 w-16">
            <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                    <Pie
                        data={data}
                        cx="50%"
                        cy="50%"
                        innerRadius={20}
                        outerRadius={30}
                        startAngle={180}
                        endAngle={0}
                        paddingAngle={2}
                        dataKey="value"
                    >
                        {data.map((entry, index) => (
                            <Cell key={`cell-${index}`} fill={entry.color} stroke="none" />
                        ))}
                    </Pie>
                    <Tooltip
                        contentStyle={{ fontSize: '10px', padding: '2px', borderRadius: '4px' }}
                        itemStyle={{ padding: 0 }}
                        formatter={(val) => [`${Math.round(val)}%`]}
                    />
                </PieChart>
            </ResponsiveContainer>
            <div className="absolute top-1/2 left-1/2 transform -translate-x-1/2 -translate-y-0 text-[10px] font-bold text-gray-700 mt-1">
                {Math.round(spotVal)}%
            </div>
            <div className="absolute -bottom-1 w-full text-center text-[8px] text-gray-500 font-medium">SPOT</div>
        </div>
    );
};

export default SpotRatioGauge;
