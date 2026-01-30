/**
 * Fleet Composition Widget
 * Pie chart showing instance type distribution
 */
import React from 'react';
import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip, Legend } from 'recharts';
import { FiPieChart } from 'react-icons/fi';

const COLORS = ['#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#06b6d4'];

const FleetComposition = ({ widgetKey }) => {
    const [chartData, setChartData] = React.useState([]);
    const [loading, setLoading] = React.useState(true);
    const [error, setError] = React.useState(null);

    React.useEffect(() => {
        const fetchData = async () => {
            try {
                const token = localStorage.getItem('token');
                const response = await fetch('http://localhost:8000/api/v1/metrics/instances', {
                    headers: {
                        'Authorization': `Bearer ${token}`
                    }
                });

                if (!response.ok) throw new Error('Failed to fetch metrics');

                const data = await response.json();

                // Transform type_distribution dictionary to chart array
                // Example: {"t3.medium": 5, "m5.large": 10} -> [{name: "t3.medium", value: 5}, ...]
                const distribution = data.type_distribution || {};
                const transformed = Object.entries(distribution).map(([name, value]) => ({
                    name,
                    value
                }));

                // Sort by value desc and take top 5, group others
                transformed.sort((a, b) => b.value - a.value);

                let finalData = transformed;
                if (transformed.length > 5) {
                    const top5 = transformed.slice(0, 5);
                    const others = transformed.slice(5).reduce((acc, curr) => acc + curr.value, 0);
                    finalData = [...top5, { name: 'Other', value: others }];
                }

                setChartData(finalData.length > 0 ? finalData : [{ name: 'No Data', value: 1 }]);
                setLoading(false);
            } catch (err) {
                console.error("Error fetching fleet composition:", err);
                setError(err.message);
                setLoading(false);
                // Fallback to empty state
                setChartData([{ name: 'No Data', value: 1 }]);
            }
        };

        fetchData();
        // Refresh every 5 minutes
        const interval = setInterval(fetchData, 300000);
        return () => clearInterval(interval);
    }, []);

    if (loading) {
        return (
            <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-6 h-full flex items-center justify-center">
                <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-purple-600"></div>
            </div>
        );
    }

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
                        <Tooltip formatter={(value) => [value, 'Instances']} />
                        <Legend />
                    </PieChart>
                </ResponsiveContainer>
            </div>
        </div>
    );
};

export default FleetComposition;
