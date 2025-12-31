import React, { useState, useEffect } from 'react';
import {
    DollarSign,
    TrendingUp,
    TrendingDown,
    Calendar,
    Filter,
    Download,
    RefreshCw,
    Server,
    Package,
    Cpu,
    HardDrive,
    BarChart3,
    PieChart
} from 'lucide-react';

const CostMonitoring = () => {
    const [loading, setLoading] = useState(true);
    const [timeRange, setTimeRange] = useState('30d'); // 7d, 30d, 90d
    const [breakdownBy, setBreakdownBy] = useState('cluster'); // cluster, node, workload
    const [filters, setFilters] = useState({
        cluster: 'all',
        namespace: 'all',
        resourceType: 'all',
        pricingModel: 'all'
    });

    // Mock cost data
    const mockCostData = {
        overview: {
            totalCost: 8647.92,
            trend: 12.5, // percentage change
            trendDirection: 'down', // up or down
            previousPeriod: 9887.45
        },
        breakdown: {
            cluster: [
                { name: 'production-cluster', cost: 2847.50, percentage: 32.9, trend: -8.2 },
                { name: 'staging-cluster', cost: 1245.00, percentage: 14.4, trend: 5.3 },
                { name: 'ml-workloads', cost: 3456.75, percentage: 40.0, trend: -15.8 },
                { name: 'dev-cluster', cost: 678.25, percentage: 7.8, trend: 2.1 },
                { name: 'test-cluster', cost: 420.42, percentage: 4.9, trend: -3.5 }
            ],
            node: [
                { name: 't3.medium', cost: 1234.56, percentage: 14.3, count: 15 },
                { name: 't3.large', cost: 2345.67, percentage: 27.1, count: 12 },
                { name: 'c5.xlarge', cost: 1876.43, percentage: 21.7, count: 8 },
                { name: 'r5.large', cost: 987.65, percentage: 11.4, count: 6 },
                { name: 'm5.large', cost: 2203.61, percentage: 25.5, count: 10 }
            ],
            workload: [
                { name: 'web-frontend', cost: 1456.78, percentage: 16.8, pods: 45 },
                { name: 'api-backend', cost: 2987.34, percentage: 34.5, pods: 32 },
                { name: 'database', cost: 1876.23, percentage: 21.7, pods: 12 },
                { name: 'ml-training', cost: 1543.98, percentage: 17.9, pods: 8 },
                { name: 'monitoring', cost: 783.59, percentage: 9.1, pods: 18 }
            ]
        },
        trends: [
            { date: '2025-12-20', cost: 287.50 },
            { date: '2025-12-21', cost: 294.20 },
            { date: '2025-12-22', cost: 276.80 },
            { date: '2025-12-23', cost: 301.45 },
            { date: '2025-12-24', cost: 288.30 },
            { date: '2025-12-25', cost: 265.90 },
            { date: '2025-12-26', cost: 275.20 }
        ]
    };

    useEffect(() => {
        // Simulate API call
        setTimeout(() => {
            setLoading(false);
        }, 500);
    }, [timeRange, breakdownBy, filters]);

    const getBreakdownData = () => {
        switch (breakdownBy) {
            case 'node':
                return mockCostData.breakdown.node;
            case 'workload':
                return mockCostData.breakdown.workload;
            default:
                return mockCostData.breakdown.cluster;
        }
    };

    const getBreakdownIcon = () => {
        switch (breakdownBy) {
            case 'node':
                return Server;
            case 'workload':
                return Package;
            default:
                return Server;
        }
    };

    const formatCurrency = (amount) => {
        return `$${amount.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
    };

    const getTrendIcon = (direction) => {
        return direction === 'up' ? TrendingUp : TrendingDown;
    };

    const getTrendColor = (direction) => {
        return direction === 'up' ? 'text-red-600' : 'text-green-600';
    };

    if (loading) {
        return (
            <div className="flex items-center justify-center h-96">
                <div className="text-center">
                    <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto mb-4"></div>
                    <p className="text-gray-600">Loading cost data...</p>
                </div>
            </div>
        );
    }

    const TrendIcon = getTrendIcon(mockCostData.overview.trendDirection);
    const breakdownData = getBreakdownData();
    const BreakdownIcon = getBreakdownIcon();

    return (
        <div className="space-y-6">
            {/* Header */}
            <div className="flex items-center justify-between">
                <div>
                    <h1 className="text-2xl font-bold text-gray-900">Cost Monitoring</h1>
                    <p className="text-sm text-gray-500 mt-1">Track and analyze your cloud spending</p>
                </div>
                <div className="flex items-center gap-3">
                    <button className="flex items-center gap-2 px-4 py-2 text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50 transition-colors">
                        <RefreshCw className="w-4 h-4" />
                        Refresh
                    </button>
                    <button className="flex items-center gap-2 px-4 py-2 text-white bg-blue-600 rounded-lg hover:bg-blue-700 transition-colors">
                        <Download className="w-4 h-4" />
                        Export
                    </button>
                </div>
            </div>

            {/* Filters Bar */}
            <div className="bg-white rounded-lg border border-gray-200 p-4">
                <div className="flex items-center gap-4 flex-wrap">
                    <div className="flex items-center gap-2">
                        <Filter className="w-4 h-4 text-gray-500" />
                        <span className="text-sm font-medium text-gray-700">Filters:</span>
                    </div>

                    {/* Time Range */}
                    <div className="flex items-center gap-2">
                        <Calendar className="w-4 h-4 text-gray-500" />
                        <select
                            value={timeRange}
                            onChange={(e) => setTimeRange(e.target.value)}
                            className="px-3 py-1.5 text-sm border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                        >
                            <option value="7d">Last 7 days</option>
                            <option value="30d">Last 30 days</option>
                            <option value="90d">Last 90 days</option>
                        </select>
                    </div>

                    {/* Cluster Filter */}
                    <select
                        value={filters.cluster}
                        onChange={(e) => setFilters({ ...filters, cluster: e.target.value })}
                        className="px-3 py-1.5 text-sm border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                    >
                        <option value="all">All Clusters</option>
                        <option value="production">Production</option>
                        <option value="staging">Staging</option>
                        <option value="dev">Development</option>
                    </select>

                    {/* Resource Type Filter */}
                    <select
                        value={filters.resourceType}
                        onChange={(e) => setFilters({ ...filters, resourceType: e.target.value })}
                        className="px-3 py-1.5 text-sm border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                    >
                        <option value="all">All Resources</option>
                        <option value="cpu">CPU</option>
                        <option value="memory">Memory</option>
                        <option value="storage">Storage</option>
                    </select>

                    {/* Pricing Model Filter */}
                    <select
                        value={filters.pricingModel}
                        onChange={(e) => setFilters({ ...filters, pricingModel: e.target.value })}
                        className="px-3 py-1.5 text-sm border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                    >
                        <option value="all">All Pricing</option>
                        <option value="spot">Spot</option>
                        <option value="on-demand">On-Demand</option>
                    </select>
                </div>
            </div>

            {/* Overview Metrics */}
            <div className="grid grid-cols-3 gap-6">
                {/* Total Cost */}
                <div className="bg-white rounded-lg border border-gray-200 p-6">
                    <div className="flex items-center justify-between mb-2">
                        <div className="flex items-center gap-2 text-gray-600">
                            <DollarSign className="w-5 h-5" />
                            <span className="text-sm font-medium">Total Compute Cost</span>
                        </div>
                    </div>
                    <div className="text-3xl font-bold text-gray-900 mb-2">
                        {formatCurrency(mockCostData.overview.totalCost)}
                    </div>
                    <div className={`flex items-center gap-1 text-sm ${getTrendColor(mockCostData.overview.trendDirection)}`}>
                        <TrendIcon className="w-4 h-4" />
                        <span className="font-medium">{mockCostData.overview.trend}%</span>
                        <span className="text-gray-600">vs last period</span>
                    </div>
                </div>

                {/* Average Daily Cost */}
                <div className="bg-white rounded-lg border border-gray-200 p-6">
                    <div className="flex items-center gap-2 text-gray-600 mb-2">
                        <BarChart3 className="w-5 h-5" />
                        <span className="text-sm font-medium">Average Daily Cost</span>
                    </div>
                    <div className="text-3xl font-bold text-gray-900 mb-2">
                        {formatCurrency(mockCostData.overview.totalCost / 30)}
                    </div>
                    <div className="text-sm text-gray-600">
                        Based on {timeRange === '7d' ? '7' : timeRange === '30d' ? '30' : '90'} days
                    </div>
                </div>

                {/* Projected Monthly */}
                <div className="bg-white rounded-lg border border-gray-200 p-6">
                    <div className="flex items-center gap-2 text-gray-600 mb-2">
                        <TrendingUp className="w-5 h-5" />
                        <span className="text-sm font-medium">Projected Monthly</span>
                    </div>
                    <div className="text-3xl font-bold text-gray-900 mb-2">
                        {formatCurrency((mockCostData.overview.totalCost / 30) * 30)}
                    </div>
                    <div className="text-sm text-gray-600">
                        Estimated for full month
                    </div>
                </div>
            </div>

            {/* Cost Trend Chart */}
            <div className="bg-white rounded-lg border border-gray-200 p-6">
                <div className="flex items-center justify-between mb-6">
                    <h2 className="text-lg font-semibold text-gray-900 flex items-center gap-2">
                        <BarChart3 className="w-5 h-5 text-blue-600" />
                        Cost Trend
                    </h2>
                    <div className="flex items-center gap-2">
                        <span className="text-xs text-gray-600">Last 7 days</span>
                    </div>
                </div>

                {/* Simple Bar Chart */}
                <div className="relative h-64">
                    <div className="absolute inset-0 flex items-end justify-between gap-2">
                        {mockCostData.trends.map((item, index) => {
                            const maxCost = Math.max(...mockCostData.trends.map(t => t.cost));
                            const height = (item.cost / maxCost) * 100;

                            return (
                                <div key={index} className="flex-1 flex flex-col items-center">
                                    <div className="w-full bg-blue-600 rounded-t hover:bg-blue-700 transition-colors cursor-pointer relative group" style={{ height: `${height}%` }}>
                                        <div className="absolute bottom-full left-1/2 transform -translate-x-1/2 mb-2 hidden group-hover:block">
                                            <div className="bg-gray-900 text-white text-xs rounded py-1 px-2 whitespace-nowrap">
                                                {formatCurrency(item.cost)}
                                            </div>
                                        </div>
                                    </div>
                                    <div className="text-xs text-gray-600 mt-2 rotate-0">
                                        {new Date(item.date).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}
                                    </div>
                                </div>
                            );
                        })}
                    </div>
                </div>

                {/* Grid lines */}
                <div className="absolute inset-0 flex flex-col justify-between pointer-events-none">
                    {[0, 25, 50, 75, 100].map((percent, index) => (
                        <div key={index} className="border-t border-gray-200 border-dashed"></div>
                    ))}
                </div>
            </div>

            {/* Cost Breakdown */}
            <div className="bg-white rounded-lg border border-gray-200 p-6">
                <div className="flex items-center justify-between mb-6">
                    <h2 className="text-lg font-semibold text-gray-900 flex items-center gap-2">
                        <PieChart className="w-5 h-5 text-blue-600" />
                        Cost Breakdown
                    </h2>
                    <div className="flex items-center gap-2">
                        <span className="text-xs text-gray-600">View by:</span>
                        <select
                            value={breakdownBy}
                            onChange={(e) => setBreakdownBy(e.target.value)}
                            className="px-3 py-1.5 text-sm border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                        >
                            <option value="cluster">Cluster</option>
                            <option value="node">Node Type</option>
                            <option value="workload">Workload</option>
                        </select>
                    </div>
                </div>

                <div className="space-y-3">
                    {breakdownData.map((item, index) => (
                        <div key={index} className="flex items-center gap-4">
                            <div className="flex items-center gap-3 flex-1">
                                <BreakdownIcon className="w-4 h-4 text-gray-400" />
                                <div className="flex-1">
                                    <div className="flex items-center justify-between mb-1">
                                        <span className="text-sm font-medium text-gray-900">{item.name}</span>
                                        <span className="text-sm font-semibold text-gray-900">{formatCurrency(item.cost)}</span>
                                    </div>
                                    <div className="flex items-center gap-3">
                                        <div className="flex-1 bg-gray-200 rounded-full h-2">
                                            <div
                                                className="bg-blue-600 rounded-full h-2"
                                                style={{ width: `${item.percentage}%` }}
                                            ></div>
                                        </div>
                                        <span className="text-xs text-gray-600 w-12 text-right">{item.percentage.toFixed(1)}%</span>
                                    </div>
                                </div>
                            </div>
                            {item.trend !== undefined && (
                                <div className={`flex items-center gap-1 text-xs ${item.trend < 0 ? 'text-green-600' : 'text-red-600'}`}>
                                    {item.trend < 0 ? <TrendingDown className="w-3 h-3" /> : <TrendingUp className="w-3 h-3" />}
                                    <span>{Math.abs(item.trend)}%</span>
                                </div>
                            )}
                            {item.count !== undefined && (
                                <span className="text-xs text-gray-600">{item.count} nodes</span>
                            )}
                            {item.pods !== undefined && (
                                <span className="text-xs text-gray-600">{item.pods} pods</span>
                            )}
                        </div>
                    ))}
                </div>
            </div>
        </div>
    );
};

export default CostMonitoring;
