import React, { useState, useEffect } from 'react';
import { Users, Server, Database, TrendingUp, AlertCircle, RefreshCw, CheckCircle, Zap, DollarSign, Download, Copy } from 'lucide-react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Area, AreaChart } from 'recharts';
import StatCard from '../components/common/StatCard';
import LoadingSpinner from '../components/common/LoadingSpinner';
import EmptyState from '../components/common/EmptyState';
import Badge from '../components/common/Badge';
import Button from '../components/common/Button';
import api from '../services/api';

const AdminOverview = () => {
  const [activity, setActivity] = useState([]);
  const [stats, setStats] = useState(null);
  const [clients, setClients] = useState([]);
  const [clientGrowth, setClientGrowth] = useState([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const loadData = async () => {
    setLoading(true);
    try {
      const [activityData, statsData, clientsData, growthData] = await Promise.all([
        api.getRecentActivity(),
        api.getGlobalStats(),
        api.getAllClients(),
        api.getClientsGrowth(30)
      ]);
      setActivity(activityData);
      setStats(statsData);
      setClients(clientsData);
      setClientGrowth(growthData);
    } catch (error) {
      console.error('Failed to load overview data:', error);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  useEffect(() => {
    loadData();

    const interval = setInterval(loadData, 30000);
    return () => clearInterval(interval);
  }, []);

  const handleRefresh = async () => {
    setRefreshing(true);
    await loadData();
  };

  const handleExport = () => {
    const exportData = {
      timestamp: new Date().toISOString(),
      stats: stats,
      clients: clients,
      activity: activity
    };
    const blob = new Blob([JSON.stringify(exportData, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `dashboard-stats-${new Date().toISOString().split('T')[0]}.json`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  const handleCopy = async () => {
    const copyData = {
      timestamp: new Date().toISOString(),
      stats: stats,
      topClients: clients.sort((a, b) => b.totalSavings - a.totalSavings).slice(0, 5)
    };
    try {
      await navigator.clipboard.writeText(JSON.stringify(copyData, null, 2));
      alert('Dashboard stats copied to clipboard!');
    } catch (error) {
      console.error('Failed to copy:', error);
      alert('Failed to copy to clipboard');
    }
  };

  const icons = {
    switch: <RefreshCw size={16} className="text-blue-500" />,
    agent: <Server size={16} className="text-green-500" />,
    event: <AlertCircle size={16} className="text-yellow-500" />,
  };

  const topClients = clients
    .sort((a, b) => b.totalSavings - a.totalSavings)
    .slice(0, 5);

  return (
    <div className="space-y-6">
      {/* Dashboard Header with Action Buttons */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-2xl font-bold text-gray-900">Dashboard Overview</h2>
          <p className="text-sm text-gray-500 mt-1">Real-time system monitoring and statistics</p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            icon={refreshing ? <RefreshCw size={16} className="animate-spin" /> : <RefreshCw size={16} />}
            onClick={handleRefresh}
            disabled={refreshing}
          >
            {refreshing ? 'Refreshing...' : 'Refresh'}
          </Button>
          <Button
            variant="outline"
            size="sm"
            icon={<Download size={16} />}
            onClick={handleExport}
          >
            Export
          </Button>
          <Button
            variant="outline"
            size="sm"
            icon={<Copy size={16} />}
            onClick={handleCopy}
          >
            Copy
          </Button>
        </div>
      </div>

      {/* Stats Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 md:gap-6">
        <StatCard 
          title="Total Clients" 
          value={stats?.totalAccounts || 0} 
          icon={<Users size={28} />}
          subtitle="Active accounts"
        />
        <StatCard 
          title="Agents Online" 
          value={stats ? `${stats.agentsOnline}/${stats.agentsTotal}` : '...'} 
          icon={<Server size={28} />}
          subtitle="Live monitoring"
        />
        <StatCard 
          title="Spot Pools" 
          value={stats?.poolsCovered || 0} 
          icon={<Database size={28} />}
          subtitle="Available pools"
        />
        <StatCard 
          title="Total Savings" 
          value={stats ? `${(stats.totalSavings / 1000).toFixed(1)}k` : '$0'} 
          icon={<TrendingUp size={28} />}
          subtitle="Year to date"
          change="+12.5% from last month"
          changeType="positive"
        />
      </div>

      {/* Client Growth Chart */}
      <div className="bg-white p-4 md:p-6 rounded-xl shadow-sm border border-gray-200">
        <div className="flex items-center justify-between mb-6">
          <div>
            <h3 className="text-lg font-bold text-gray-900">Client Growth (30 Days)</h3>
            <p className="text-sm text-gray-500 mt-1">Daily client registration trend</p>
          </div>
          <Badge variant="success">
            <TrendingUp size={14} className="inline mr-1" />
            Growing
          </Badge>
        </div>
        {loading ? (
          <div className="flex justify-center items-center h-64"><LoadingSpinner /></div>
        ) : clientGrowth.length === 0 ? (
          <EmptyState
            icon={<TrendingUp size={48} />}
            title="No Growth Data"
            description="Client growth data will appear here once available"
          />
        ) : (
          <ResponsiveContainer width="100%" height={300}>
            <AreaChart data={clientGrowth}>
              <defs>
                <linearGradient id="colorClients" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#3B82F6" stopOpacity={0.3}/>
                  <stop offset="95%" stopColor="#3B82F6" stopOpacity={0}/>
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
              <XAxis
                dataKey="date"
                stroke="#6b7280"
                style={{ fontSize: '12px' }}
              />
              <YAxis
                stroke="#6b7280"
                style={{ fontSize: '12px' }}
              />
              <Tooltip
                contentStyle={{
                  backgroundColor: '#fff',
                  border: '1px solid #e5e7eb',
                  borderRadius: '8px',
                  padding: '8px'
                }}
              />
              <Area
                type="monotone"
                dataKey="count"
                stroke="#3B82F6"
                strokeWidth={2}
                fillOpacity={1}
                fill="url(#colorClients)"
              />
            </AreaChart>
          </ResponsiveContainer>
        )}
      </div>

      {/* Activity and Quick Stats */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 bg-white p-4 md:p-6 rounded-xl shadow-sm border border-gray-200">
          <div className="flex items-center justify-between mb-6">
            <h3 className="text-lg font-bold text-gray-900">System Activity</h3>
            <Badge variant="info">Real-time</Badge>
          </div>
          {loading ? (
            <div className="flex justify-center items-center h-80"><LoadingSpinner /></div>
          ) : activity.length === 0 ? (
            <EmptyState
              icon={<AlertCircle size={48} />}
              title="No Recent Activity"
              description="No events have been recorded recently"
            />
          ) : (
            <div className="space-y-3 max-h-80 overflow-y-auto pr-2">
              {activity.map(item => (
                <div key={item.id} className="flex items-start space-x-4 p-4 bg-gray-50 rounded-lg hover:bg-gray-100 transition-colors">
                  <span className="flex-shrink-0 w-10 h-10 flex items-center justify-center bg-white rounded-lg shadow-sm border border-gray-200">
                    {icons[item.type] || <AlertCircle size={16} className="text-gray-500" />}
                  </span>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-gray-900 break-words">{item.text}</p>
                    <p className="text-xs text-gray-500 mt-1">{item.time}</p>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
        
        <div className="bg-white p-4 md:p-6 rounded-xl shadow-sm border border-gray-200">
          <h3 className="text-lg font-bold text-gray-900 mb-6">Quick Stats</h3>
          <div className="space-y-4">
            <div className="p-4 bg-gradient-to-r from-green-50 to-green-100 rounded-lg border border-green-200">
              <div className="flex justify-between items-center mb-2">
                <span className="text-sm font-medium text-green-900">Success Rate</span>
                <CheckCircle size={18} className="text-green-600" />
              </div>
              <p className="text-2xl font-bold text-green-700">
                {stats ? ((stats.modelSwitches / Math.max(stats.totalSwitches, 1)) * 100).toFixed(1) : 0}%
              </p>
              <p className="text-xs text-green-600 mt-1">Auto-switch accuracy</p>
            </div>
            
            <div className="p-4 bg-gradient-to-r from-blue-50 to-blue-100 rounded-lg border border-blue-200">
              <div className="flex justify-between items-center mb-2">
                <span className="text-sm font-medium text-blue-900">Spot Usage</span>
                <Zap size={18} className="text-blue-600" />
              </div>
              <p className="text-2xl font-bold text-blue-700">87.3%</p>
              <p className="text-xs text-blue-600 mt-1">Average utilization</p>
            </div>
            
            <div className="p-4 bg-gradient-to-r from-purple-50 to-purple-100 rounded-lg border border-purple-200">
              <div className="flex justify-between items-center mb-2">
                <span className="text-sm font-medium text-purple-900">Avg Savings</span>
                <DollarSign size={18} className="text-purple-600" />
              </div>
              <p className="text-2xl font-bold text-purple-700">
                ${stats ? (stats.totalSavings / 12 / 1000).toFixed(1) : 0}k
              </p>
              <p className="text-xs text-purple-600 mt-1">Per month</p>
            </div>
          </div>
        </div>
      </div>

      {/* Top Clients Table */}
      <div className="bg-white p-4 md:p-6 rounded-xl shadow-sm border border-gray-200">
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between mb-6 gap-4">
          <h3 className="text-lg font-bold text-gray-900">Top Clients by Savings</h3>
          <Button variant="outline" size="sm" icon={<Download size={16} />} onClick={() => api.exportGlobalStats()}>
            Export
          </Button>
        </div>
        {topClients.length === 0 ? (
          <EmptyState
            icon={<Users size={48} />}
            title="No Clients Found"
            description="No clients are registered yet"
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full">
              <thead>
                <tr className="border-b border-gray-200">
                  <th className="text-left py-3 px-4 text-xs font-semibold text-gray-600 uppercase">Rank</th>
                  <th className="text-left py-3 px-4 text-xs font-semibold text-gray-600 uppercase">Client</th>
                  <th className="text-left py-3 px-4 text-xs font-semibold text-gray-600 uppercase">Instances</th>
                  <th className="text-left py-3 px-4 text-xs font-semibold text-gray-600 uppercase">Agents</th>
                  <th className="text-left py-3 px-4 text-xs font-semibold text-gray-600 uppercase">Savings</th>
                  <th className="text-left py-3 px-4 text-xs font-semibold text-gray-600 uppercase">Status</th>
                </tr>
              </thead>
              <tbody>
                {topClients.map((client, idx) => (
                  <tr key={client.id} className="border-b border-gray-100 hover:bg-gray-50">
                    <td className="py-4 px-4">
                      <div className={`w-8 h-8 rounded-lg flex items-center justify-center text-white font-bold ${
                        idx === 0 ? 'bg-yellow-500' : idx === 1 ? 'bg-gray-400' : idx === 2 ? 'bg-orange-600' : 'bg-gray-300'
                      }`}>
                        {idx + 1}
                      </div>
                    </td>
                    <td className="py-4 px-4">
                      <div>
                        <p className="text-sm font-medium text-gray-900">{client.name}</p>
                        <p className="text-xs text-gray-500 font-mono break-all">{client.id}</p>
                      </div>
                    </td>
                    <td className="py-4 px-4 text-sm text-gray-700">{client.instances}</td>
                    <td className="py-4 px-4 text-sm text-gray-700">
                      <span className="text-green-600 font-medium">{client.agentsOnline}</span>
                      <span className="text-gray-400">/{client.agentsTotal}</span>
                    </td>
                    <td className="py-4 px-4 text-sm font-bold text-green-600">
                      ${(client.totalSavings / 1000).toFixed(1)}k
                    </td>
                    <td className="py-4 px-4">
                      <Badge variant={client.status === 'active' ? 'success' : 'danger'}>
                        {client.status}
                      </Badge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
};

export default AdminOverview;
