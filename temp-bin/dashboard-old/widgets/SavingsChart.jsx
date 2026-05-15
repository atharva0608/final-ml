/**
 * Savings Chart Widget
 * Bar chart comparing optimized vs unoptimized costs
 */
import React from 'react';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend } from 'recharts';
import { FiBarChart2 } from 'react-icons/fi';

const SavingsChart = ({ data = {}, widgetKey }) => {
    // Use real data from API, no fallback to fake data
    const chartData = data.chartData || [];
    const hasData = chartData && chartData.length > 0;

    return (
        <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-6 hover:shadow-md transition-shadow">
            <div className="flex items-center justify-between mb-4">
                <div>
                    <h3 className="text-lg font-semibold text-gray-900">Savings Projection</h3>
                    <p className="text-sm text-gray-500">Optimized vs Unoptimized Costs</p>
                </div>
                <div className="p-2 bg-indigo-50 rounded-lg">
                    <FiBarChart2 className="w-5 h-5 text-indigo-600" />
                </div>
            </div>

            <div className="h-64">
                {hasData ? (
                    <ResponsiveContainer width="100%" height="100%">
                        <BarChart data={chartData} margin={{ top: 10, right: 30, left: 0, bottom: 0 }}>
                            <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                            <XAxis dataKey="month" tick={{ fontSize: 12 }} />
                            <YAxis tick={{ fontSize: 12 }} tickFormatter={(v) => `$${(v / 1000).toFixed(0)}k`} />
                            <Tooltip
                                formatter={(value) => [`$${value.toLocaleString()}`, '']}
                                contentStyle={{ borderRadius: '8px', border: '1px solid #e5e7eb' }}
                            />
                            <Legend />
                            <Bar dataKey="unoptimized" name="Without Optimization" fill="#ef4444" radius={[4, 4, 0, 0]} />
                            <Bar dataKey="optimized" name="With Optimization" fill="#10b981" radius={[4, 4, 0, 0]} />
                        </BarChart>
                    </ResponsiveContainer>
                ) : (
                    <div className="flex flex-col items-center justify-center h-full text-gray-400">
                        <FiBarChart2 className="w-12 h-12 mb-3" />
                        <p className="text-sm font-medium">No cost data available yet</p>
                        <p className="text-xs mt-1">Connect AWS accounts to see savings projections</p>
                    </div>
                )}
            </div>
        </div>
    );
};

export default SavingsChart;
