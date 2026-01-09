/**
 * Client Dashboard Component
 * User-specific cluster optimization metrics and cost savings
 *
 * Features (from feature_mapping.md Part 2.1):
 * - client-home-kpi-reuse-indep-view-spend: Monthly Spend KPI (user's own spend)
 * - client-home-kpi-reuse-indep-view-savings: Net Savings KPI
 * - client-home-chart-unique-indep-view-proj: Savings Projection Bar Chart (Unoptimized vs Optimized)
 * - client-home-chart-unique-indep-view-comp: Fleet Composition Pie Chart (Instance Family Ratios)
 * - client-home-feed-unique-indep-view-live: Real-Time Activity Feed (Action Logs)
 */
import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  BarChart, Bar, PieChart, Pie, Cell, XAxis, YAxis, CartesianGrid,
  Tooltip, Legend, ResponsiveContainer
} from 'recharts';
import { useDashboard } from '../../hooks/useDashboard';
import { Card, Button, Badge } from '../shared';
import { formatCurrency, formatNumber, formatPercentage, formatRelativeTime } from '../../utils/formatters';
import {
  FiServer, FiDollarSign, FiTrendingDown, FiActivity, FiRefreshCw,
  FiPieChart, FiBarChart2, FiClock, FiAlertCircle
} from 'react-icons/fi';
import toast from 'react-hot-toast';

const COLORS = ['#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#06b6d4'];

const Dashboard = () => {
  const navigate = useNavigate();
  const { dashboardKPIs, costMetrics, instanceMetrics, costTimeSeries, loading, refreshDashboard } = useDashboard();
  const [activityFeed, setActivityFeed] = useState([]);

  // Mock activity feed (client-home-feed-unique-indep-view-live)
  useEffect(() => {
    setActivityFeed([
      { id: 1, action: 'Cluster discovered', cluster: 'prod-cluster', time: '2 minutes ago', type: 'info' },
      { id: 2, action: 'Node optimized', cluster: 'staging-cluster', time: '15 minutes ago', type: 'success' },
      { id: 3, action: 'Template updated', cluster: 'dev-cluster', time: '1 hour ago', type: 'info' },
      { id: 4, action: 'Cost alert', cluster: 'prod-cluster', time: '3 hours ago', type: 'warning' },
    ]);
  }, []);

  // Mock data for savings projection (client-home-chart-unique-indep-view-proj)
  const savingsProjectionData = [
    { month: 'Jan', unoptimized: 4500, optimized: 2800 },
    { month: 'Feb', unoptimized: 4200, optimized: 2600 },
    { month: 'Mar', unoptimized: 4800, optimized: 3000 },
    { month: 'Apr', unoptimized: 5100, optimized: 3200 },
    { month: 'May', unoptimized: 4900, optimized: 3100 },
    { month: 'Jun', unoptimized: 5300, optimized: 3400 },
  ];



  const KPICard = ({ title, value, subtitle, icon: Icon, color = 'blue', trend = null, onClick }) => (
    <Card className="hover:shadow-lg transition-shadow cursor-pointer" onClick={onClick}>
      <div className="flex items-start justify-between">
        <div>
          <p className="text-sm font-medium text-gray-600">{title}</p>
          <p className={`text-3xl font-bold text-${color}-600 mt-2`}>{value}</p>
          {subtitle && <p className="text-sm text-gray-500 mt-1">{subtitle}</p>}
          {trend && (
            <div className="flex items-center mt-2">
              <span className={`text-sm font-medium ${trend > 0 ? 'text-red-600' : 'text-green-600'}`}>
                {trend > 0 ? '↑' : '↓'} {Math.abs(trend)}%
              </span>
              <span className="text-xs text-gray-500 ml-2">vs last month</span>
            </div>
          )}
        </div>
        <div className={`p-3 bg-${color}-100 rounded-lg`}>
          <Icon className={`w-6 h-6 text-${color}-600`} />
        </div>
      </div>
    </Card>
  );

  const handleRefresh = async () => {
    await refreshDashboard();
    toast.success('Dashboard refreshed');
  };

  if (loading && !dashboardKPIs) {
    return (
      <div className="flex items-center justify-center h-96">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
      </div>
    );
  }

  // Check if user needs to connect AWS account
  const hasNoData = !dashboardKPIs || dashboardKPIs.total_instances === 0;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-3xl font-bold text-gray-900">Dashboard</h1>
          <p className="text-gray-600 mt-1">Monitor your cluster optimization and cost savings</p>
        </div>
        <Button
          variant="outline"
          icon={<FiRefreshCw className={loading ? 'animate-spin' : ''} />}
          onClick={handleRefresh}
          disabled={loading}
        >
          Refresh
        </Button>
      </div>

      {/* Onboarding Notice */}
      {hasNoData && (
        <Card className="bg-blue-50 border-blue-200">
          <div className="flex items-start space-x-3">
            <FiAlertCircle className="w-5 h-5 text-blue-600 flex-shrink-0 mt-0.5" />
            <div className="flex-1">
              <h3 className="font-semibold text-blue-900">Welcome! Connect your AWS account to get started</h3>
              <p className="text-sm text-blue-700 mt-1">
                Connect your AWS account to discover clusters, optimize costs, and track savings.
              </p>
              <div className="mt-3">
                <Button
                  variant="primary"
                  size="sm"
                  onClick={() => navigate('/settings/integrations')}
                >
                  Connect AWS Account →
                </Button>
              </div>
            </div>
          </div>
        </Card>
      )}

      {/* KPI Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        <KPICard
          title="Net Savings"
          value={formatCurrency(dashboardKPIs?.estimated_savings || 0)}
          subtitle="This month"
          icon={FiTrendingDown}
          color="green"
          trend={-8}
        />
        <KPICard
          title="Current Spend Rate"
          value={formatCurrency(dashboardKPIs?.total_cost || 0)}
          subtitle="Projected end-of-month"
          icon={FiDollarSign}
          color="blue"
          trend={-12}
          onClick={() => navigate('/audit')}
        />
        <KPICard
          title="Efficiency Score"
          value={formatPercentage((dashboardKPIs?.optimization_rate || 0) / 100)}
          subtitle="Resource Usage / Requests"
          icon={FiActivity}
          color="orange"
        />
        <KPICard
          title="Spot Coverage"
          value={formatPercentage(0.65)} // Mock value for now
          subtitle="Workloads on Spot"
          icon={FiPieChart}
          color="purple"
          trend={5}
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Savings Projection Chart */}
        <Card>
          <div className="flex items-center justify-between mb-4">
            <div>
              <h2 className="text-xl font-bold text-gray-900">Savings Projection</h2>
              <p className="text-sm text-gray-600">Daily spend vs On-Demand baseline</p>
            </div>
            <FiBarChart2 className="w-5 h-5 text-gray-400" />
          </div>
          <ResponsiveContainer width="100%" height={300}>
            <BarChart data={savingsProjectionData}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="month" />
              <YAxis />
              <Tooltip formatter={(value) => formatCurrency(value)} />
              <Legend />
              <Bar dataKey="unoptimized" fill="#ef4444" name="On-Demand Cost" />
              <Bar dataKey="optimized" fill="#10b981" name="Actual Spend" />
            </BarChart>
          </ResponsiveContainer>
        </Card>

        {/* Cluster Map */}
        <Card>
          <div className="flex items-center justify-between mb-4">
            <div>
              <h2 className="text-xl font-bold text-gray-900">Cluster Map</h2>
              <p className="text-sm text-gray-600">High-level status of connected clusters</p>
            </div>
            <FiServer className="w-5 h-5 text-gray-400" />
          </div>
          <div className="grid grid-cols-2 gap-4 h-[300px] overflow-y-auto">
            {/* Mock Cluster Status Cards */}
            {['prod-cluster-us-east-1', 'staging-cluster-eu-central-1', 'dev-cluster-us-west-2'].map((cluster, i) => (
              <div key={cluster} className="p-4 border border-gray-200 rounded-lg flex flex-col justify-between hover:bg-gray-50 transition-colors">
                <div className="flex items-start justify-between">
                  <div>
                    <h3 className="font-medium text-gray-900 truncate" title={cluster}>{cluster}</h3>
                    <p className="text-xs text-gray-500 mt-1">v1.27.3 • 12 nodes</p>
                  </div>
                  <span className={`flex h-3 w-3 rounded-full ${i === 0 ? 'bg-green-500' : i === 1 ? 'bg-green-500' : 'bg-red-500'}`} title={i === 2 ? 'Disconnected' : 'Connected'} />
                </div>
                <div className="mt-4 flex items-center justify-between text-xs">
                  <span className="text-gray-500">Heartbeat: {i === 2 ? '5m ago' : 'Live'}</span>
                  <Button size="xs" variant="ghost" onClick={() => navigate('/clusters')}>View</Button>
                </div>
              </div>
            ))}
          </div>
        </Card>
      </div>

      {/* Real-Time Activity Feed (client-home-feed-unique-indep-view-live) */}
      <Card>
        <div className="flex items-center justify-between mb-4">
          <div>
            <h2 className="text-xl font-bold text-gray-900">Recent Activity</h2>
            <p className="text-sm text-gray-600">Real-time action logs</p>
          </div>
          <FiClock className="w-5 h-5 text-gray-400" />
        </div>
        <div className="space-y-3">
          {activityFeed.length === 0 ? (
            <p className="text-sm text-gray-500 text-center py-8">No recent activity</p>
          ) : (
            activityFeed.map((item) => (
              <div key={item.id} className="flex items-center justify-between p-3 bg-gray-50 rounded-lg hover:bg-gray-100 transition-colors">
                <div className="flex items-center space-x-3">
                  <div className={`w-2 h-2 rounded-full ${item.type === 'success' ? 'bg-green-500' :
                    item.type === 'warning' ? 'bg-yellow-500' :
                      item.type === 'error' ? 'bg-red-500' : 'bg-blue-500'
                    }`} />
                  <div>
                    <p className="text-sm font-medium text-gray-900">{item.action}</p>
                    <p className="text-xs text-gray-600">{item.cluster}</p>
                  </div>
                </div>
                <span className="text-xs text-gray-500">{item.time}</span>
              </div>
            ))
          )}
        </div>
        <div className="mt-4 text-center">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => navigate('/audit')}
          >
            View Full Audit Log →
          </Button>
        </div>
      </Card>

      {/* Quick Actions */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <Card className="hover:shadow-lg transition-shadow cursor-pointer" onClick={() => navigate('/clusters')}>
          <div className="flex items-start space-x-4">
            <div className="w-10 h-10 bg-blue-100 rounded-lg flex items-center justify-center">
              <FiServer className="w-5 h-5 text-blue-600" />
            </div>
            <div>
              <h3 className="font-semibold text-gray-900">Manage Clusters</h3>
              <p className="text-sm text-gray-600 mt-1">
                Discover and optimize your Kubernetes clusters
              </p>
              <p className="text-xs text-blue-600 mt-2 font-medium">
                View clusters →
              </p>
            </div>
          </div>
        </Card>

        <Card className="hover:shadow-lg transition-shadow cursor-pointer" onClick={() => navigate('/templates')}>
          <div className="flex items-start space-x-4">
            <div className="w-10 h-10 bg-green-100 rounded-lg flex items-center justify-center">
              <FiPieChart className="w-5 h-5 text-green-600" />
            </div>
            <div>
              <h3 className="font-semibold text-gray-900">Node Templates</h3>
              <p className="text-sm text-gray-600 mt-1">
                Configure instance selection rules
              </p>
              <p className="text-xs text-green-600 mt-2 font-medium">
                Manage templates →
              </p>
            </div>
          </div>
        </Card>

        <Card className="hover:shadow-lg transition-shadow cursor-pointer" onClick={() => navigate('/policies')}>
          <div className="flex items-start space-x-4">
            <div className="w-10 h-10 bg-purple-100 rounded-lg flex items-center justify-center">
              <FiActivity className="w-5 h-5 text-purple-600" />
            </div>
            <div>
              <h3 className="font-semibold text-gray-900">Optimization Policies</h3>
              <p className="text-sm text-gray-600 mt-1">
                Configure automation rules
              </p>
              <p className="text-xs text-purple-600 mt-2 font-medium">
                Edit policies →
              </p>
            </div>
          </div>
        </Card>
      </div>
    </div>
  );
};

export default Dashboard;
