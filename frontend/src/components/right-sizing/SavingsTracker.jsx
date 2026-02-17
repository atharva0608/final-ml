import React, { useEffect, useState } from 'react';
import { Card } from '../shared';
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts';
import { FiTrendingUp, FiArrowUp } from 'react-icons/fi';
import api from '../../services/api';

const SavingsTracker = ({ data: externalData }) => {
    const [internalData, setInternalData] = useState(null);
    const [loading, setLoading] = useState(!externalData);

    const data = externalData || internalData;

    useEffect(() => {
        if (externalData) {
            setLoading(false);
            return;
        }

        const fetchSavings = async () => {
            try {
                const res = await api.get('/optimization/savings/realized');
                setInternalData(res.data);
            } catch (err) {
                console.error("Failed to load savings history", err);
            } finally {
                setLoading(false);
            }
        };
        fetchSavings();
    }, [externalData]);

    if (loading) return <div className="h-48 bg-gray-50 animate-pulse rounded-lg"></div>;
    if (!data) return <div className="text-gray-400 text-sm">No savings data available.</div>;

    return (
        <Card className="h-full bg-gradient-to-br from-green-50 to-white border-green-100">
            <div className="flex justify-between items-start mb-4">
                <div>
                    <h3 className="text-sm font-medium text-green-800 uppercase tracking-widest">Running Savings Total</h3>
                    <div className="flex items-baseline gap-2 mt-1">
                        <span className="text-3xl font-bold text-gray-900">${data.total_savings.toLocaleString()}</span>
                        <span className="text-xs font-semibold text-green-600 bg-green-100 px-1.5 py-0.5 rounded flex items-center">
                            <FiTrendingUp className="mr-0.5" /> +{((data.this_month / data.total_savings) * 100).toFixed(1)}%
                        </span>
                    </div>
                    <p className="text-xs text-gray-500 mt-1">
                        Realized in last 30 days: <span className="font-medium text-gray-700">${data.this_month}</span>
                    </p>
                </div>
            </div>

            <div className="h-32">
                <ResponsiveContainer width="100%" height="100%">
                    <AreaChart data={data.trend}>
                        <defs>
                            <linearGradient id="colorSavings" x1="0" y1="0" x2="0" y2="1">
                                <stop offset="5%" stopColor="#10B981" stopOpacity={0.2} />
                                <stop offset="95%" stopColor="#10B981" stopOpacity={0} />
                            </linearGradient>
                        </defs>
                        <Tooltip
                            contentStyle={{ borderRadius: '8px', border: 'none', boxShadow: '0 4px 6px -1px rgb(0 0 0 / 0.1)' }}
                            formatter={(value) => [`$${value}`, 'Daily Savings']}
                            labelFormatter={(label) => new Date(label).toLocaleDateString()}
                        />
                        <Area
                            type="monotone"
                            dataKey="amount"
                            stroke="#059669"
                            strokeWidth={2}
                            fillOpacity={1}
                            fill="url(#colorSavings)"
                        />
                    </AreaChart>
                </ResponsiveContainer>
            </div>
        </Card>
    );
};

export default SavingsTracker;
