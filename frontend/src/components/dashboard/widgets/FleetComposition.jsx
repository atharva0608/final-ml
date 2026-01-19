/**
 * Fleet Composition Widget
 * Pie chart showing instance type distribution
 */
import React from 'react';
import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip, Legend } from 'recharts';
import { FiPieChart } from 'react-icons/fi';

const COLORS = ['#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#06b6d4'];

const FleetComposition = ({ data = {}, widgetKey }) => {
    const chartData = data.chartData || [
        { name: 'm5.large', value: 35 },
        { name: 'c5.xlarge', value: 25 },
        { name: 'r5.2xlarge', value: 20 },
        { name: 't3.medium', value: 15 },
        { name: 'Other', value: 5 }
    ];

    return (
        <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-6 hover:shadow-md transition-shadow">
            <div className="flex items-center justify-between mb-4">
                <div>
                    <h3 className="text-lg font-semibold text-gray-900">Fleet Composition</h3>
                    <p className="text-sm text-gray-500">Instance type distribution</p>
                </div>
                <div className="p-2 bg-purple-50 rounded-lg">
                    <FiPieChart className="w-5 h-5 text-purple-600" />
                </div>
            </div>

            <div className="h-64">
                <ResponsiveContainer width="100%" height="100%">
                    <PieChart>
                        <Pie
                            data={chartData}
                            cx="50%"
                            cy="50%"
                            innerRadius={50}
                            outerRadius={80}
                            paddingAngle={2}
                            dataKey="value"
                            label={({ name, percent }) => `${name} ${(percent * 100).toFixed(0)}%`}
                            labelLine={false}
                        >
                            {chartData.map((entry, index) => (
                                <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                            ))}
                        </Pie>
                        <Tooltip formatter={(value) => [`${value}%`, 'Share']} />
                    </PieChart>
                </ResponsiveContainer>
            </div>
        </div>
    );
};

export default FleetComposition;
