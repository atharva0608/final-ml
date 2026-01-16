import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { metricsAPI } from '../services/api';
import {
    FiArrowLeft, FiLayers, FiDollarSign, FiTrendingUp, FiAlertCircle
} from 'react-icons/fi';
import { StatsCard, Card, EmptyState, Badge } from '../components/shared';
import {
    AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer,
    PieChart, Pie, Cell, Legend
} from 'recharts';
import { toast } from 'react-hot-toast';

const COLORS = ['#0088FE', '#00C49F', '#FFBB28', '#FF8042', '#EF4444'];

const AccountAnalytics = () => {
    const { accountId } = useParams();
    const navigate = useNavigate();
    const [data, setData] = useState(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        fetchData();
    }, [accountId]);

    const fetchData = async () => {
        try {
            setLoading(true);
            // Fetch account summary
            const response = await metricsAPI.getAccountSummary(accountId);
            setData(response.data);
        } catch (error) {
            console.error("Failed to fetch account analytics:", error);
            toast.error("Failed to load account data");
        } finally {
            setLoading(false);
        }
    };

    if (loading) return <div className="p-8 text-gray-500">Loading Account Analytics...</div>;
    if (!data) return <div className="p-8 text-red-500">Account not found</div>;

    return (
        <div className="p-6 space-y-6 bg-gray-50 min-h-screen">
            {/* Header */}
            <div className="flex items-center gap-4">
                <button
                    onClick={() => navigate(-1)}
                    className="p-2 hover:bg-gray-200 rounded-full transition-colors"
                >
                    <FiArrowLeft className="w-5 h-5" />
                </button>
                <div>
                    <h1 className="text-2xl font-bold text-gray-900">Account Analytics</h1>
                    <p className="text-sm text-gray-500">Deep dive into usage and waste for this account.</p>
                </div>
            </div>

            {/* KPI Cards */}
            <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
                <StatsCard
                    title="Total Spend (Est.)"
                    value={`$${data.total_cost}`}
                    icon={<FiDollarSign className="text-blue-500" />}
                    trend="+5.2%"
                />
                <StatsCard
                    title="Total Waste (Est.)"
                    value={`$${data.total_waste}`}
                    icon={<FiAlertCircle className="text-red-500" />}
                    trend="Action Needed"
                    trendColor="red"
                />
                <StatsCard
                    title="Active Instances"
                    value={data.instance_count || 0}
                    icon={<FiLayers className="text-purple-500" />}
                />
                <StatsCard
                    title="Efficiency Score"
                    value={`${data.efficiency_score}%`}
                    icon={<FiTrendingUp className={data.efficiency_score > 80 ? "text-green-500" : "text-yellow-500"} />}
                />
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                {/* Cost Trends */}
                <Card title="Monthly Cost Trend">
                    <div className="h-64">
                        <ResponsiveContainer width="100%" height="100%">
                            <AreaChart data={data.history}>
                                <defs>
                                    <linearGradient id="colorCost" x1="0" y1="0" x2="0" y2="1">
                                        <stop offset="5%" stopColor="#3B82F6" stopOpacity={0.1} />
                                        <stop offset="95%" stopColor="#3B82F6" stopOpacity={0} />
                                    </linearGradient>
                                </defs>
                                <XAxis dataKey="date" />
                                <YAxis />
                                <Tooltip />
                                <Area type="monotone" dataKey="cost" stroke="#3B82F6" fillOpacity={1} fill="url(#colorCost)" />
                            </AreaChart>
                        </ResponsiveContainer>
                    </div>
                </Card>

                {/* Waste Distribution */}
                <Card title="Waste Breakdown">
                    <div className="h-64 flex items-center justify-center">
                        {data.waste_distribution && data.waste_distribution.length > 0 ? (
                            <ResponsiveContainer width="100%" height="100%">
                                <PieChart>
                                    <Pie
                                        data={data.waste_distribution}
                                        cx="50%"
                                        cy="50%"
                                        innerRadius={60}
                                        outerRadius={80}
                                        paddingAngle={5}
                                        dataKey="value"
                                    >
                                        {data.waste_distribution.map((entry, index) => (
                                            <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                                        ))}
                                    </Pie>
                                    <Tooltip />
                                    <Legend />
                                </PieChart>
                            </ResponsiveContainer>
                        ) : (
                            <EmptyState
                                title="No Waste Detected"
                                message="Great job! This account is running efficiently."
                                icon={FiAlertCircle}
                            />
                        )}
                    </div>
                </Card>
            </div>

        </div>
    );
};

export default AccountAnalytics;
