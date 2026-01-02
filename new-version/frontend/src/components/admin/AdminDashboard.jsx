/**
 * Admin Dashboard Component
 * Platform-wide statistics and monitoring for super admins
 */
import React, { useState, useEffect } from 'react';
import { adminAPI } from '../../services/api';
import { Card, Button, Badge } from '../shared';
import { FiUsers, FiServer, FiDollarSign, FiActivity, FiRefreshCw, FiTrendingUp, FiCpu } from 'react-icons/fi';
import toast from 'react-hot-toast';
import { formatCurrency, formatNumber, formatDate } from '../../utils/formatters';
import { LineChart, Line, BarChart, Bar, PieChart, Pie, Cell, ResponsiveContainer, XAxis, YAxis, Tooltip, Legend } from 'recharts';

const COLORS = ['#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6'];

const AdminDashboard = () => {
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  useEffect(() => {
    fetchStats();
  }, []);

  const fetchStats = async () => {
    setLoading(true);
    try {
      const response = await adminAPI.getStats();
      setStats(response.data.stats);
    } catch (error) {
      toast.error('Failed to load platform statistics');
    } finally {
      setLoading(false);
    }
  };

  const handleRefresh = async () => {
    setRefreshing(true);
    await fetchStats();
    setRefreshing(false);
    toast.success('Statistics refreshed');
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-3xl font-bold text-gray-900">Admin Dashboard</h1>
          <p className="text-gray-600 mt-1">Platform-wide statistics and monitoring</p>
        </div>
        <Button
          variant="outline"
          icon={<FiRefreshCw className={refreshing ? 'animate-spin' : ''} />}
          onClick={handleRefresh}
          disabled={refreshing}
        >
          Refresh
        </Button>
      </div>

      {/* Key Metrics */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        <Card className="bg-gradient-to-br from-blue-50 to-blue-100 border-blue-200">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-blue-600 mb-1">Total Clients</p>
              <p className="text-3xl font-bold text-blue-900">
                {formatNumber(stats?.total_clients || 0)}
              </p>
              <p className="text-xs text-blue-600 mt-2">
                {formatNumber(stats?.active_clients || 0)} active
              </p>
            </div>
            <div className="w-12 h-12 bg-blue-500 rounded-full flex items-center justify-center">
              <FiUsers className="w-6 h-6 text-white" />
            </div>
          </div>
        </Card>

        <Card className="bg-gradient-to-br from-green-50 to-green-100 border-green-200">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-green-600 mb-1">Total Clusters</p>
              <p className="text-3xl font-bold text-green-900">
                {formatNumber(stats?.total_clusters || 0)}
              </p>
              <p className="text-xs text-green-600 mt-2">
                {formatNumber(stats?.active_clusters || 0)} active
              </p>
            </div>
            <div className="w-12 h-12 bg-green-500 rounded-full flex items-center justify-center">
              <FiServer className="w-6 h-6 text-white" />
            </div>
          </div>
        </Card>

        <Card className="bg-gradient-to-br from-purple-50 to-purple-100 border-purple-200">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-purple-600 mb-1">Total Instances</p>
              <p className="text-3xl font-bold text-purple-900">
                {formatNumber(stats?.total_instances || 0)}
              </p>
              <p className="text-xs text-purple-600 mt-2">
                {stats?.spot_percentage || 0}% spot
              </p>
            </div>
            <div className="w-12 h-12 bg-purple-500 rounded-full flex items-center justify-center">
              <FiCpu className="w-6 h-6 text-white" />
            </div>
          </div>
        </Card>

        <Card className="bg-gradient-to-br from-orange-50 to-orange-100 border-orange-200">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-orange-600 mb-1">Platform Savings</p>
              <p className="text-3xl font-bold text-orange-900">
                {formatCurrency(stats?.total_savings || 0)}
              </p>
              <p className="text-xs text-orange-600 mt-2">This month</p>
            </div>
            <div className="w-12 h-12 bg-orange-500 rounded-full flex items-center justify-center">
              <FiDollarSign className="w-6 h-6 text-white" />
            </div>
          </div>
        </Card>
      </div>

      {/* Charts Row */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Client Growth */}
        <Card>
          <h3 className="text-lg font-semibold text-gray-900 mb-4 flex items-center gap-2">
            <FiTrendingUp className="w-5 h-5" />
            Client Growth (Last 30 Days)
          </h3>
          {stats?.client_growth_data ? (
            <ResponsiveContainer width="100%" height={250}>
              <LineChart data={stats.client_growth_data}>
                <XAxis dataKey="date" stroke="#9ca3af" fontSize={12} />
                <YAxis stroke="#9ca3af" fontSize={12} />
                <Tooltip
                  contentStyle={{ backgroundColor: '#fff', border: '1px solid #e5e7eb', borderRadius: '8px' }}
                />
                <Legend />
                <Line type="monotone" dataKey="clients" stroke="#3b82f6" strokeWidth={2} name="Total Clients" />
                <Line type="monotone" dataKey="active" stroke="#10b981" strokeWidth={2} name="Active" />
              </LineChart>
            </ResponsiveContainer>
          ) : (
            <div className="h-64 flex items-center justify-center text-gray-500">
              No growth data available
            </div>
          )}
        </Card>

        {/* Instance Distribution */}
        <Card>
          <h3 className="text-lg font-semibold text-gray-900 mb-4 flex items-center gap-2">
            <FiActivity className="w-5 h-5" />
            Instance Distribution
          </h3>
          {stats?.instance_distribution ? (
            <ResponsiveContainer width="100%" height={250}>
              <PieChart>
                <Pie
                  data={[
                    { name: 'Spot', value: stats.total_spot_instances || 0 },
                    { name: 'On-Demand', value: stats.total_on_demand_instances || 0 },
                  ]}
                  cx="50%"
                  cy="50%"
                  labelLine={false}
                  label={({ name, percent }) => `${name}: ${(percent * 100).toFixed(0)}%`}
                  outerRadius={80}
                  fill="#8884d8"
                  dataKey="value"
                >
                  {[0, 1].map((entry, index) => (
                    <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip />
              </PieChart>
            </ResponsiveContainer>
          ) : (
            <div className="h-64 flex items-center justify-center text-gray-500">
              No distribution data available
            </div>
          )}
        </Card>
      </div>

      {/* Cost Savings by Client */}
      <Card>
        <h3 className="text-lg font-semibold text-gray-900 mb-4">Top Clients by Savings</h3>
        {stats?.top_clients_by_savings && stats.top_clients_by_savings.length > 0 ? (
          <ResponsiveContainer width="100%" height={300}>
            <BarChart data={stats.top_clients_by_savings}>
              <XAxis dataKey="email" stroke="#9ca3af" fontSize={12} />
              <YAxis stroke="#9ca3af" fontSize={12} />
              <Tooltip
                contentStyle={{ backgroundColor: '#fff', border: '1px solid #e5e7eb', borderRadius: '8px' }}
                formatter={(value) => formatCurrency(value)}
              />
              <Legend />
              <Bar dataKey="savings" fill="#10b981" name="Savings" />
              <Bar dataKey="cost" fill="#3b82f6" name="Current Cost" />
            </BarChart>
          </ResponsiveContainer>
        ) : (
          <div className="h-64 flex items-center justify-center text-gray-500">
            No savings data available
          </div>
        )}
      </Card>

      {/* Platform Health */}
      <Card>
        <h3 className="text-lg font-semibold text-gray-900 mb-4">Platform Health</h3>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-6">
          <div className="text-center">
            <div className="text-sm text-gray-600 mb-2">API Success Rate</div>
            <div className="text-3xl font-bold text-green-600">
              {stats?.api_success_rate?.toFixed(1) || 0}%
            </div>
          </div>
          <div className="text-center">
            <div className="text-sm text-gray-600 mb-2">Avg Response Time</div>
            <div className="text-3xl font-bold text-blue-600">
              {stats?.avg_response_time || 0}ms
            </div>
          </div>
          <div className="text-center">
            <div className="text-sm text-gray-600 mb-2">Active Optimizations</div>
            <div className="text-3xl font-bold text-purple-600">
              {formatNumber(stats?.active_optimizations || 0)}
            </div>
          </div>
          <div className="text-center">
            <div className="text-sm text-gray-600 mb-2">Agent Uptime</div>
            <div className="text-3xl font-bold text-orange-600">
              {stats?.agent_uptime?.toFixed(1) || 0}%
            </div>
          </div>
        </div>
      </Card>

      {/* Recent Activity */}
      <Card>
        <h3 className="text-lg font-semibold text-gray-900 mb-4">Recent Client Activity</h3>
        {stats?.recent_signups && stats.recent_signups.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-200">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Client
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Status
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Clusters
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Instances
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Joined
                  </th>
                </tr>
              </thead>
              <tbody className="bg-white divide-y divide-gray-200">
                {stats.recent_signups.map((client) => (
                  <tr key={client.id} className="hover:bg-gray-50">
                    <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900">
                      {client.email}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap">
                      <Badge color={client.is_active ? 'green' : 'gray'}>
                        {client.is_active ? 'Active' : 'Inactive'}
                      </Badge>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-600">
                      {formatNumber(client.cluster_count || 0)}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-600">
                      {formatNumber(client.instance_count || 0)}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-600">
                      {formatDate(client.created_at)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="text-center py-8 text-gray-500">No recent activity</div>
        )}
      </Card>
    </div>
  );
};

export default AdminDashboard;
