import React, { useState, useEffect } from 'react';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, AreaChart, Area, LineChart, Line, PieChart, Pie, Cell } from 'recharts';
import { Zap, Server, BarChart3, TrendingUp, History } from 'lucide-react';
import StatCard from '../../common/StatCard';
import LoadingSpinner from '../../common/LoadingSpinner';
import ErrorMessage from '../../common/ErrorMessage';
import EmptyState from '../../common/EmptyState';
import Badge from '../../common/Badge';
import CustomTooltip from '../../common/CustomTooltip';
import api from '../../../services/api';

const ClientOverviewTab = ({ clientId }) => {
  const [client, setClient] = useState(null);
  const [history, setHistory] = useState([]);
  const [savingsData, setSavingsData] = useState([]);
  const [chartData, setChartData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    const loadData = async () => {
      setLoading(true);
      setError(null);
      try {
        const [clientData, historyData, savings, charts] = await Promise.all([
          api.getClientDetails(clientId),
          api.getSwitchHistory(clientId),
          api.getSavings(clientId, 'monthly'),
          api.getClientChartData(clientId)
        ]);
        setClient(clientData);
        setHistory(historyData.slice(0, 10));
        setSavingsData(savings);
        setChartData(charts);
      } catch (err) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    };
    loadData();
  }, [clientId]);

  if (loading) {
    return <div className="flex justify-center items-center h-64"><LoadingSpinner /></div>;
  }

  if (error) {
    return <ErrorMessage message={error} />;
  }

  const COLORS = ['#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#ec4899'];

  return (
    <div className="space-y-6">
      {/* Stats Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 md:gap-6">
        <StatCard 
          title="Instances" 
          value={client.instances} 
          icon={<Zap size={24} />}
          subtitle="Active monitoring"
        />
        <StatCard 
          title="Agents" 
          value={`${client.agentsOnline}/${client.agentsTotal}`} 
          icon={<Server size={24} />}
          subtitle="Online/Total"
        />
        <StatCard 
          title="Monthly Savings" 
          value={`${(client.totalSavings / 12 / 1000).toFixed(1)}k`}
          icon={<BarChart3 size={24} />}
          subtitle="Average per month"
        />
        <StatCard 
          title="Lifetime Savings" 
          value={`${(client.totalSavings / 1000).toFixed(1)}k`}
          icon={<TrendingUp size={24} />}
          subtitle="Total accumulated"
        />
      </div>
      
      {/* Charts Grid */}
      {chartData && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <div className="bg-white p-4 md:p-6 rounded-xl shadow-sm border border-gray-200">
            <h3 className="text-lg font-bold text-gray-900 mb-4">Savings Trend</h3>
            <ResponsiveContainer width="100%" height={300}>
              <AreaChart data={chartData.savingsTrend}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="month" tick={{ fontSize: 12 }} />
                <YAxis tickFormatter={(value) => `${(value / 1000).toFixed(0)}k`} tick={{ fontSize: 12 }} />
                <Tooltip content={<CustomTooltip />} />
                <Legend />
                <Area type="monotone" dataKey="baseline" stackId="1" stroke="#ef4444" fill="#fecaca" name="Baseline Cost" />
                <Area type="monotone" dataKey="actual" stackId="1" stroke="#3b82f6" fill="#bfdbfe" name="Actual Cost" />
              </AreaChart>
            </ResponsiveContainer>
          </div>

          <div className="bg-white p-4 md:p-6 rounded-xl shadow-sm border border-gray-200">
            <h3 className="text-lg font-bold text-gray-900 mb-4">Instance Mode Distribution</h3>
            <ResponsiveContainer width="100%" height={300}>
              <PieChart>
                <Pie
                  data={chartData.modeDistribution}
                  cx="50%"
                  cy="50%"
                  labelLine={false}
                  label={({ mode, count }) => `${mode}: ${count}`}
                  outerRadius={100}
                  fill="#8884d8"
                  dataKey="count"
                >
                  {chartData.modeDistribution.map((entry, index) => (
                    <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip />
                <Legend />
              </PieChart>
            </ResponsiveContainer>
          </div>

          <div className="bg-white p-4 md:p-6 rounded-xl shadow-sm border border-gray-200">
            <h3 className="text-lg font-bold text-gray-900 mb-4">Switch Frequency (30 Days)</h3>
            <ResponsiveContainer width="100%" height={300}>
              <LineChart data={chartData.switchFrequency}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="date" tick={{ fontSize: 10 }} angle={-45} textAnchor="end" height={80} />
                <YAxis />
                <Tooltip />
                <Legend />
                <Line type="monotone" dataKey="switches" stroke="#8b5cf6" strokeWidth={2} name="Switches" />
              </LineChart>
            </ResponsiveContainer>
          </div>

          <div className="bg-white p-4 md:p-6 rounded-xl shadow-sm border border-gray-200">
            <h3 className="text-lg font-bold text-gray-900 mb-4">Monthly Cost Comparison</h3>
            <ResponsiveContainer width="100%" height={300}>
              <BarChart data={savingsData.slice(0, 6)}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="name" tick={{ fontSize: 12 }} />
                <YAxis tickFormatter={(value) => `${(value / 1000).toFixed(0)}k`} tick={{ fontSize: 12 }} />
                <Tooltip content={<CustomTooltip />} />
                <Legend />
                <Bar dataKey="onDemandCost" fill="#ef4444" name="On-Demand" radius={[8, 8, 0, 0]} />
                <Bar dataKey="modelCost" fill="#10b981" name="Optimized" radius={[8, 8, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}
      
      {/* Recent Switch History */}
      <div className="bg-white p-4 md:p-6 rounded-xl shadow-sm border border-gray-200">
        <h3 className="text-lg font-bold text-gray-900 mb-4">Recent Switch History</h3>
        {history.length === 0 ? (
          <EmptyState
            icon={<History size={48} />}
            title="No Switch History"
            description="No switches have been performed yet"
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full">
              <thead>
                <tr className="border-b border-gray-200">
                  <th className="text-left py-3 px-4 text-xs font-semibold text-gray-600 uppercase">Time</th>
                  <th className="text-left py-3 px-4 text-xs font-semibold text-gray-600 uppercase">Instance</th>
                  <th className="text-left py-3 px-4 text-xs font-semibold text-gray-600 uppercase">From → To</th>
                  <th className="text-left py-3 px-4 text-xs font-semibold text-gray-600 uppercase">Trigger</th>
                  <th className="text-left py-3 px-4 text-xs font-semibold text-gray-600 uppercase">Impact</th>
                </tr>
              </thead>
              <tbody>
                {history.map(sw => (
                  <tr key={sw.id} className="border-b border-gray-100 hover:bg-gray-50">
                    <td className="py-3 px-4 text-sm text-gray-600">
                      {new Date(sw.timestamp).toLocaleString()}
                    </td>
                    <td className="py-3 px-4 text-sm font-mono text-gray-500">{sw.instanceId}</td>
                    <td className="py-3 px-4 text-sm">
                      <div className="flex items-center space-x-2">
                        <Badge variant={sw.fromMode === 'ondemand' ? 'danger' : 'success'}>
                          {sw.fromMode}
                        </Badge>
                        <span className="text-gray-400">→</span>
                        <Badge variant={sw.toMode === 'ondemand' ? 'danger' : 'success'}>
                          {sw.toMode}
                        </Badge>
                      </div>
                    </td>
                    <td className="py-3 px-4">
                      <Badge variant={sw.trigger === 'manual' ? 'warning' : 'info'}>
                        {sw.trigger}
                      </Badge>
                    </td>
                    <td className="py-3 px-4 text-sm font-bold">
                      <span className={sw.savingsImpact >= 0 ? 'text-green-600' : 'text-red-600'}>
                        ${sw.savingsImpact.toFixed(4)}
                      </span>
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

export default ClientOverviewTab;
