import React, { useEffect, useState } from 'react';
import { PieChart, Pie, Cell, ResponsiveContainer } from 'recharts';
import { motion, animate } from 'framer-motion';

const SavingsGauge = ({ selectedSavings, totalPotentialSavings }) => {
    const [displayValue, setDisplayValue] = useState(0);

    // Calculate percentage for gauge (avoid division by zero)
    const percentage = totalPotentialSavings > 0
        ? Math.min((selectedSavings / totalPotentialSavings) * 100, 100)
        : 0;

    // Data for the semi-circle gauge
    const data = [
        { name: 'Selected', value: percentage },
        { name: 'Remaining', value: 100 - percentage }
    ];

    // Animate the number
    useEffect(() => {
        const controls = animate(0, selectedSavings, {
            duration: 0.8,
            onUpdate: value => setDisplayValue(value),
            ease: "easeOut"
        });
        return () => controls.stop();
    }, [selectedSavings]);

    return (
        <div className="flex items-center gap-4 bg-white border border-gray-200 rounded-xl px-5 py-2 shadow-sm">
            {/* Left text */}
            <div className="flex flex-col">
                <span className="text-[10px] font-bold text-gray-400 uppercase tracking-widest">Potential Savings</span>
                <div className="flex items-baseline gap-1">
                    <span className="text-2xl font-bold text-green-600 font-mono">
                        ${displayValue.toFixed(2)}
                    </span>
                    <span className="text-xs text-gray-500 font-medium">/mo</span>
                </div>
            </div>

            {/* Gauge Graphic */}
            <div className="relative w-16 h-8 flex items-end justify-center">
                <ResponsiveContainer width="100%" height="100%">
                    <PieChart>
                        <Pie
                            data={data}
                            cx="50%"
                            cy="100%"
                            startAngle={180}
                            endAngle={0}
                            innerRadius="60%"
                            outerRadius="100%"
                            paddingAngle={0}
                            dataKey="value"
                            stroke="none"
                        >
                            <Cell key="cell-0" fill="#16a34a" /> {/* green-600 */}
                            <Cell key="cell-1" fill="#e5e7eb" /> {/* gray-200 */}
                        </Pie>
                    </PieChart>
                </ResponsiveContainer>
                {/* Percentage Text Tiny */}
                {/* <div className="absolute bottom-0 text-[8px] font-bold text-gray-400 mb-1">
                    {percentage.toFixed(0)}%
                </div> */}
            </div>

            {/* Total Context */}
            {totalPotentialSavings > 0 && (
                <div className="text-xs text-gray-400 border-l border-gray-200 pl-4">
                    of ${totalPotentialSavings.toFixed(2)} total
                </div>
            )}
        </div>
    );
};

export default SavingsGauge;
