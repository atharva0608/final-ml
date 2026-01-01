/**
 * Dashboard Component
 *
 * Main dashboard with KPIs, metrics, and charts
 */
import React, { useEffect, useState } from 'react';
import { LineChart, Line, PieChart, Pie, Cell, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';
import { useDashboard } from '../../hooks/useDashboard';
import { Card, Button, Badge } from '../shared';
import { formatCurrency, formatNumber, formatPercentage, formatRelativeTime } from '../../utils/formatters';
import { FiServer, FiDollarSign, FiTrendingDown, FiActivity, FiRefreshCw } from 'react-icons/fi';

const Dashboard = () => {
  const { dashboardKPIs, costMetrics, instanceMetrics, costTimeSeries, loading, refreshDashboard } = useDashboard();
  const [selectedRange, setSelectedRange] = useState('30d');

  const KPICard = ({ title, value, subtitle, icon: Icon, color = 'blue', trend = null }) => (
    <Card className="hover:shadow-lg transition-shadow">
      <div className="flex items-start justify-between">
        <div>
          <p className="text-sm font-medium text-gray-600">{title}</p>
          <p className={`text-3xl font-bold text-${color}-600 mt-2`}>{value}</p>
          {subtitle && <p className="text-sm text-gray-500 mt-1">{subtitle}</p>}
          {trend && (
            <div className="flex items-center mt-2">
              <span className={`text-sm font-medium ${trend > 0 ? 'text-green-600' : 'text-red-600'}`}>
                {trend > 0 ? '↑' : '↓'} {Math.abs(trend)}%
              </span>
              <span className="text-xs text-gray-500 ml-2">vs last period</span>
            </div>
          )}
        </div>
        <div className={`p-3 bg-${color}-100 rounded-lg`}>
          <Icon className={`w-6 h-6 text-${color}-600`} />
        </div>
      </div>
    </Card>
  );

  if (loading && !dashboardKPIs) {
    return (
      <div className="flex items-center justify-center h-96">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-3xl font-bold text-gray-900">Dashboard</h1>
          <p className="text-gray-600 mt-1">Monitor your cluster optimization and cost savings</p>
        </div>
        <div className="flex gap-2">
          <Button
            variant="outline"
            icon={<FiRefreshCw />}
            onClick={refreshDashboard}
            loading={loading}
          >
            Refresh
          </Button>
        </div>
      </div>

      {/* Time Range Selector */}
      <div className="flex gap-2">
        {['7d', '30d', '90d'].map((range) => (
          <Button
            key={range}
            variant={selectedRange === range ? 'primary' : 'ghost'}
            size="sm"
            onClick={() => setSelectedRange(range)}
          >
            Last {range}
          </Button>
        ))}
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        <KPICard
          title="Total Instances"
          value={formatNumber(dashboardKPIs?.total_instances || 0)}
          subtitle={`${formatNumber(dashboardKPIs?.active_instances || 0)} active`}
          icon={FiServer}
          color="blue"
        />
        <KPICard
          title="Total Cost"
          value={formatCurrency(dashboardKPIs?.total_cost || 0)}
          subtitle={formatRelativeTime(dashboardKPIs?.time_range_start)}
          icon={FiDollarSign}
          color="green"
        />
        <KPICard
          title="Estimated Savings"
          value={formatCurrency(dashboardKPIs?.estimated_savings || 0)}
          subtitle={formatPercentage(dashboardKPIs?.savings_percentage || 0) + ' saved'}
          icon={FiTrendingDown}
          color="purple"
          trend={dashboardKPIs?.savings_percentage}
        />
        <KPICard
          title="Optimizations"
          value={formatNumber(dashboardKPIs?.total_optimizations || 0)}
          subtitle={`${formatNumber(dashboardKPIs?.successful_optimizations || 0)} successful`}
          icon={FiActivity}
          color="orange"
        />
      </div>

      {/* Charts Row */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Cost Time Series Chart */}
        <Card title="Cost Trend" subtitle="Daily cost over time">
          <ResponsiveContainer width="100%" height={300}>
            <LineChart data={costTimeSeries?.data_points || []}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis
                dataKey="timestamp"
                tickFormatter={(value) => new Date(value).toLocaleDateString()}
              />
              <YAxis tickFormatter={(value) => `$${value}`} />
              <Tooltip
                formatter={(value) => formatCurrency(value)}
                labelFormatter={(label) => new Date(label).toLocaleDateString()}
              />
              <Legend />
              <Line
                type="monotone"
                dataKey="value"
                stroke="#3b82f6"
                strokeWidth={2}
                name="Daily Cost"
              />
            </LineChart>
          </ResponsiveContainer>
        </Card>

        {/* Instance Distribution Chart */}
        <Card title="Instance Distribution" subtitle="By lifecycle and state">
          <div className="grid grid-cols-2 gap-4">
            {/* Spot vs On-Demand */}
            <div>
              <p className="text-sm font-medium text-gray-700 mb-2">Lifecycle</p>
              <ResponsiveContainer width="100%" height={150}>
                <PieChart>
                  <Pie
                    data={[
                      { name: 'Spot', value: dashboardKPIs?.spot_instances || 0 },
                      { name: 'On-Demand', value: dashboardKPIs?.on_demand_instances || 0 },
                    ]}
                    cx="50%"
                    cy="50%"
                    outerRadius={50}
                    fill="#8884d8"
                    dataKey="value"
                    label
                  >
                    <Cell fill="#a855f7" />
                    <Cell fill="#3b82f6" />
                  </Pie>
                  <Tooltip />
                </PieChart>
              </ResponsiveContainer>
            </div>

            {/* Instance States */}
            <div>
              <p className="text-sm font-medium text-gray-700 mb-2">State</p>
              <div className="space-y-2">
                <div className="flex justify-between items-center">
                  <span className="text-sm text-gray-600">Running</span>
                  <Badge color="green">{instanceMetrics?.running_instances || 0}</Badge>
                </div>
                <div className="flex justify-between items-center">
                  <span className="text-sm text-gray-600">Pending</span>
                  <Badge color="yellow">{instanceMetrics?.pending_instances || 0}</Badge>
                </div>
                <div className="flex justify-between items-center">
                  <span className="text-sm text-gray-600">Stopped</span>
                  <Badge color="red">{instanceMetrics?.stopped_instances || 0}</Badge>
                </div>
              </div>
            </div>
          </div>
        </Card>
      </div>

      {/* Cost Breakdown */}
      <Card title="Cost Breakdown" subtitle="Detailed cost analysis">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          <div className="text-center p-4 bg-blue-50 rounded-lg">
            <p className="text-sm font-medium text-gray-600">Total Cost</p>
            <p className="text-2xl font-bold text-blue-600 mt-1">
              {formatCurrency(costMetrics?.total_cost || 0)}
            </p>
          </div>
          <div className="text-center p-4 bg-purple-50 rounded-lg">
            <p className="text-sm font-medium text-gray-600">Spot Cost</p>
            <p className="text-2xl font-bold text-purple-600 mt-1">
              {formatCurrency(costMetrics?.spot_cost || 0)}
            </p>
            <p className="text-xs text-gray-500 mt-1">
              {costMetrics?.total_cost > 0
                ? formatPercentage((costMetrics?.spot_cost / costMetrics?.total_cost) * 100)
                : '0%'}{' '}
              of total
            </p>
          </div>
          <div className="text-center p-4 bg-gray-50 rounded-lg">
            <p className="text-sm font-medium text-gray-600">On-Demand Cost</p>
            <p className="text-2xl font-bold text-gray-600 mt-1">
              {formatCurrency(costMetrics?.on_demand_cost || 0)}
            </p>
            <p className="text-xs text-gray-500 mt-1">
              {costMetrics?.total_cost > 0
                ? formatPercentage((costMetrics?.on_demand_cost / costMetrics?.total_cost) * 100)
                : '0%'}{' '}
              of total
            </p>
          </div>
        </div>
      </Card>
    </div>
  );
};

export default Dashboard;
