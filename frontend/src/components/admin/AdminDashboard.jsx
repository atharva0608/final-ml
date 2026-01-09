import React, { useState, useEffect } from 'react';
import { adminAPI } from '../../services/api';
import { Card, StatsCard } from '../shared';
import {
  FiUsers,
  FiServer,
  FiDollarSign,
  FiActivity,
  FiTrendingUp,
  FiZap
} from 'react-icons/fi';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer
} from 'recharts';

const AdminDashboard = () => {
  const [dashboardData, setDashboardData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchDashboardData();
  }, []);

  const fetchDashboardData = async () => {
    try {
      const response = await adminAPI.getDashboardStats();
      setDashboardData(response.data);
    } catch (error) {
      console.error('Failed to load dashboard stats:', error);
      setDashboardData(null);
    } finally {
      setLoading(false);
    }
  };

  if (loading) return <div className="p-6 text-center">Loading dashboard...</div>;

  if (!dashboardData) {
    return (
      <div className="space-y-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Command Center</h1>
          <p className="text-gray-600">Platform Overview & Live Pulse</p>
        </div>
        <Card className="p-8 text-center">
          <FiActivity className="w-12 h-12 text-gray-400 mx-auto mb-4" />
          <h3 className="text-lg font-semibold text-gray-700">Unable to Load Dashboard</h3>
          <p className="text-gray-500 mt-2">Please check your connection or try again later.</p>
        </Card>
      </div>
    );
  }

  const { stats, savings_chart, activity_feed } = dashboardData;

  // Transform backend stats to UI format
  const kpiStats = [
    { label: 'Total Active Clients', value: stats.active_users, change: `+${stats.recent_signups} this month`, icon: FiUsers, color: 'blue' },
    { label: 'Total EC2 Managed', value: stats.total_instances, change: `${stats.active_clusters} clusters`, icon: FiServer, color: 'purple' },
    { label: 'Total Savings Generated', value: `$${stats.total_savings.toLocaleString()}`, change: '+18%', icon: FiDollarSign, color: 'green' },
    { label: 'Platform Revenue (MRR)', value: '$48.2k', change: '+5%', icon: FiTrendingUp, color: 'indigo' },
  ];



  const getIconForType = (type) => {
    switch (type) {
      case 'optimization': return <FiZap className="text-green-500" />;
      case 'onboarding': return <FiServer className="text-blue-500" />;
      case 'config': return <FiActivity className="text-purple-500" />;
      default: return <FiActivity className="text-gray-500" />;
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Command Center</h1>
        <p className="text-gray-600">Platform Overview & Live Pulse</p>
      </div>

      {/* Global KPIs */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        {kpiStats.map((stat, index) => (
          <StatsCard key={index} {...stat} />
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Main Chart Area */}
        <div className="lg:col-span-2 space-y-6">
          <Card className="p-6">
            <h2 className="text-lg font-bold text-gray-900 mb-4">Savings Velocity</h2>
            <div className="h-80 w-full">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={savings_chart}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#E5E7EB" />
                  <XAxis dataKey="name" axisLine={false} tickLine={false} tick={{ fill: '#6B7280' }} />
                  <YAxis axisLine={false} tickLine={false} tick={{ fill: '#6B7280' }} tickFormatter={(value) => `$${value}`} />
                  <Tooltip
                    contentStyle={{ borderRadius: '8px', border: 'none', boxShadow: '0 4px 6px -1px rgba(0, 0, 0, 0.1)' }}
                    formatter={(value) => [`$${value}`, 'Savings']}
                  />
                  <Line type="monotone" dataKey="savings" stroke="#10B981" strokeWidth={3} dot={{ r: 4, strokeWidth: 2 }} activeDot={{ r: 6 }} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </Card>
        </div>

        {/* Live Activity Feed */}
        <div className="lg:col-span-1">
          <Card className="h-full">
            <div className="p-6 border-b border-gray-100 flex justify-between items-center">
              <h2 className="text-lg font-bold text-gray-900">Live Activity</h2>
              <span className="flex h-3 w-3 relative">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75"></span>
                <span className="relative inline-flex rounded-full h-3 w-3 bg-green-500"></span>
              </span>
            </div>
            <div className="p-6 space-y-6">
              {activity_feed.map((item) => (
                <div key={item.id} className="flex space-x-3">
                  <div className="mt-1 bg-gray-50 border border-gray-200 rounded-lg p-2 h-fit">
                    {getIconForType(item.type)}
                  </div>
                  <div>
                    <p className="text-sm font-medium text-gray-900">
                      {item.user} <span className="text-gray-400 font-normal">• {item.action}</span>
                    </p>
                    <p className="text-xs text-gray-500 mt-1">{item.detail}</p>
                    <p className="text-xs text-gray-400 mt-1">{item.time}</p>
                  </div>
                </div>
              ))}
            </div>
            <div className="p-4 border-t border-gray-100 bg-gray-50 rounded-b-lg text-center">
              <button className="text-sm text-blue-600 hover:text-blue-800 font-medium">View Global Audit Log</button>
            </div>
          </Card>
        </div>
      </div>
    </div>
  );
};

export default AdminDashboard;
