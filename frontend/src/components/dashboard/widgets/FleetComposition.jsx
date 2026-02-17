/**
 * Fleet Composition Widget
 * Pie chart showing Spot vs On-Demand distribution
 */
import React from 'react';
import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip, Legend } from 'recharts';
import { FiPieChart } from 'react-icons/fi';
import api from '../../../services/api';
import { useState } from 'react'; // Added useState import

const COLORS = ['#10B981', '#F59E0B']; // Green (Spot), Yellow (On-Demand)

const FleetComposition = ({ data: externalData }) => {
    const [internalData, setInternalData] = useState([]);
    const [loading, setLoading] = useState(!externalData);

    // Transform external data (API response) into Chart Data [{name, value}]
    const chartData = React.useMemo(() => {
        if (!externalData) return internalData;

        // Use pre-processed chartData if available
        if (externalData.chartData) return externalData.chartData;

        // If it's already an array, assume it's chart data
        if (Array.isArray(externalData)) return externalData;

        // Otherwise transform from API response object
        const spot = externalData.spot_instances || 0;
        const onDemand = externalData.on_demand_instances || 0;

        if (spot === 0 && onDemand === 0) return [];

        return [
            { name: 'Spot', value: spot },
            { name: 'On-Demand', value: onDemand }
        ];
    }, [externalData, internalData]);

    React.useEffect(() => {
        if (externalData) {
            setLoading(false);
            return;
        }

        const fetchData = async () => {
            try {
                const response = await api.get('/metrics/instances');
                const data = response.data;

                // Transform for Pie Chart
                const spot = data.spot_instances || 0;
                const onDemand = data.on_demand_instances || 0;

                let newData = [];
                // If both are 0, handle empty
                if (spot !== 0 || onDemand !== 0) {
                    newData = [
                        { name: 'Spot', value: spot },
                        { name: 'On-Demand', value: onDemand }
                    ];
                }
                setInternalData(newData);
                setLoading(false);
            } catch (err) {
                console.error("Error fetching fleet composition:", err);
                setLoading(false);
                setInternalData([]);
            }
        };

        fetchData();
        // Refresh every 5 minutes
        const interval = setInterval(fetchData, 300000);
        return () => clearInterval(interval);
    }, [externalData]);

    if (loading) {
        return (
            <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-6 h-full flex items-center justify-center">
                <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-purple-600"></div>
            </div>
        );
    }

    return (
        <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-6 hover:shadow-md transition-shadow h-full">
            <div className="flex items-center justify-between mb-4">
                <div>
                    <h3 className="text-lg font-semibold text-gray-900">Fleet Composition</h3>
                    <p className="text-sm text-gray-500">Spot vs On-Demand</p>
                </div>
                <div className="p-2 bg-purple-50 rounded-lg">
                    <FiPieChart className="w-5 h-5 text-purple-600" />
                </div>
            </div>

            <div className="h-64">
                {chartData && chartData.length > 0 ? (
                    <ResponsiveContainer width="100%" height="100%">
                        <PieChart>
                            <Pie
                                data={chartData}
                                cx="50%"
                                cy="50%"
                                innerRadius={60}
                                outerRadius={80}
                                paddingAngle={5}
                                dataKey="value"
                            >
                                {chartData.map((entry, index) => (
                                    <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                                ))}
                            </Pie>
                            <Tooltip formatter={(value) => [value, 'Instances']} />
                            <Legend verticalAlign="bottom" height={36} />
                        </PieChart>
                    </ResponsiveContainer>
                ) : (
                    <div className="flex flex-col items-center justify-center h-full text-gray-400">
                        <FiPieChart className="w-12 h-12 mb-3" />
                        <p className="text-sm font-medium">No instances found</p>
                        <p className="text-xs mt-1">Connect AWS accounts to see instance distribution</p>
                    </div>
                )}
            </div>
        </div>
    );
};

export default FleetComposition;
