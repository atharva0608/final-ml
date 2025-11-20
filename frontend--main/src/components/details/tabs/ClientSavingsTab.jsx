import React, { useState, useEffect } from 'react';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, AreaChart, Area, PieChart, Pie, Cell } from 'recharts';
import { DollarSign, BarChart3, TrendingUp, Download } from 'lucide-react';
import StatCard from '../../common/StatCard';
import LoadingSpinner from '../../common/LoadingSpinner';
import ErrorMessage from '../../common/ErrorMessage';
import Button from '../../common/Button';
import CustomTooltip from '../../common/CustomTooltip';
import api from '../../../services/api';

const ClientSavingsTab = ({ clientId }) => {
  const [savingsData, setSavingsData] = useState([]);
  const [totalSavings, setTotalSavings] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    const loadData = async () => {
      setLoading(true);
      setError(null);
      try {
        const [data, clientData] = await Promise.all([
          api.getSavings(clientId, 'monthly'),
          api.getClientDetails(clientId)
        ]);
        setSavingsData(data);
        setTotalSavings(clientData.totalSavings);
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

  const pieData = savingsData.slice(0, 6).map(d => ({
    name: d.name,
    value: d.savings
  }));

  const COLORS = ['#10b981', '#3b82f6', '#8b5cf6', '#f59e0b', '#ef4444', '#ec4899'];

  return (
    <div className="space-y-6">
      {/* Stats Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 md:gap-6">
        <StatCard 
          title="Total Savings" 
          value={`${(totalSavings / 1000).toFixed(1)}k`}
          icon={<DollarSign size={24} />}
          subtitle="Lifetime accumulated"
          change="+$2.3k this month"
          changeType="positive"
        />
        <StatCard 
          title="Monthly Average" 
          value={`${(totalSavings / 12 / 1000).toFixed(1)}k`}
          icon={<BarChart3 size={24} />}
          subtitle="Per month"
        />
        <StatCard 
          title="Savings Rate" 
          value="34.2%"
          icon={<TrendingUp size={24} />}
          subtitle="vs On-Demand"
        />
      </div>
      
      {/* Charts */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="bg-white p-4 md:p-6 rounded-xl shadow-sm border border-gray-200">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-lg font-bold text-gray-900">Monthly Savings Trend</h3>
            <Button 
              variant="outline" 
              size="sm" 
              icon={<Download size={16} />}
              onClick={() => api.exportSavings(clientId)}
            >
              Export
            </Button>
          </div>
          <ResponsiveContainer width="100%" height={300}>
            <BarChart data={savingsData}>
              <CartesianGrid strokeDasharray="3 3" vertical={false} />
              <XAxis dataKey="name" tick={{ fontSize: 12 }} />
              <YAxis tickFormatter={(value) => `${(value / 1000).toFixed(0)}k`} tick={{ fontSize: 12 }} />
              <Tooltip content={<CustomTooltip />} />
              <Bar dataKey="savings" fill="#10b981" radius={[8, 8, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
        
        <div className="bg-white p-4 md:p-6 rounded-xl shadow-sm border border-gray-200">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-lg font-bold text-gray-900">Savings Distribution</h3>
            <Button 
              variant="outline" 
              size="sm" 
              icon={<Download size={16} />}
              onClick={() => api.exportSavings(clientId)}
            >
              Export
            </Button>
          </div>
          <ResponsiveContainer width="100%" height={300}>
            <PieChart>
              <Pie
                data={pieData}
                cx="50%"
                cy="50%"
                labelLine={false}
                label={({ name, percent }) => `${name}: ${(percent * 100).toFixed(0)}%`}
                outerRadius={100}
                fill="#8884d8"
                dataKey="value"
              >
                {pieData.map((entry, index) => (
                  <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                ))}
              </Pie>
              <Tooltip />
              <Legend />
            </PieChart>
          </ResponsiveContainer>
        </div>
      </div>
      
      {/* Cost Comparison */}
      <div className="bg-white p-4 md:p-6 rounded-xl shadow-sm border border-gray-200">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-bold text-gray-900">Cost Comparison by Month</h3>
          <Button 
            variant="outline" 
            size="sm" 
            icon={<Download size={16} />}
            onClick={() => api.exportSavings(clientId)}
          >
            Export
          </Button>
        </div>
        <ResponsiveContainer width="100%" height={350}>
          <AreaChart data={savingsData}>
            <CartesianGrid strokeDasharray="3 3" vertical={false} />
            <XAxis dataKey="name" tick={{ fontSize: 12 }} />
            <YAxis tickFormatter={(value) => `${(value / 1000).toFixed(1)}k`} tick={{ fontSize: 12 }} />
            <Tooltip content={<CustomTooltip />} />
            <Legend />
            <Area 
              type="monotone" 
              dataKey="onDemandCost" 
              stackId="1" 
              stroke="#ef4444" 
              fill="#fecaca" 
              name="On-Demand Cost" 
            />
            <Area 
              type="monotone" 
              dataKey="modelCost" 
              stackId="1" 
              stroke="#3b82f6" 
              fill="#bfdbfe" 
              name="Optimized Cost" 
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
};

export default ClientSavingsTab;
