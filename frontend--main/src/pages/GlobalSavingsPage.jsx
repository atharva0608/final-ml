import React, { useState, useEffect } from 'react';
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';
import { DollarSign, BarChart3, TrendingUp } from 'lucide-react';
import StatCard from '../components/common/StatCard';
import LoadingSpinner from '../components/common/LoadingSpinner';
import CustomTooltip from '../components/common/CustomTooltip';
import api from '../services/api';

const GlobalSavingsPage = () => {
  const [savingsData, setSavingsData] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const loadData = async () => {
      setLoading(true);
      try {
        const clients = await api.getAllClients();
        const aggregated = [];
        
        for (let i = 0; i < 12; i++) {
          const monthTotal = clients.reduce((sum, c) => sum + (c.totalSavings / 12), 0);
          aggregated.push({
            name: new Date(2025, i, 1).toLocaleDateString('en', { month: 'short' }),
            savings: monthTotal * (0.8 + Math.random() * 0.4),
            onDemandCost: monthTotal * 2.5,
            modelCost: monthTotal * 1.5
          });
        }
        
        setSavingsData(aggregated);
      } catch (error) {
        console.error('Failed to load savings:', error);
      } finally {
        setLoading(false);
      }
    };
    loadData();
  }, []);

  if (loading) {
    return <div className="flex justify-center items-center h-64"><LoadingSpinner /></div>;
  }

  const totalSavings = savingsData.reduce((sum, d) => sum + d.savings, 0);

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 md:gap-6">
        <StatCard 
          title="YTD Savings" 
          value={`${(totalSavings / 1000).toFixed(1)}k`}
          icon={<DollarSign size={24} />}
          subtitle="Year to date"
        />
        <StatCard 
          title="Monthly Avg" 
          value={`${(totalSavings / 12 / 1000).toFixed(1)}k`}
          icon={<BarChart3 size={24} />}
          subtitle="Average per month"
        />
        <StatCard 
          title="Projected Annual" 
          value={`${(totalSavings / 1000).toFixed(0)}k`}
          icon={<TrendingUp size={24} />}
          subtitle="Based on current rate"
        />
      </div>

      <div className="bg-white p-4 md:p-6 rounded-xl shadow-sm border border-gray-200">
        <h3 className="text-lg font-bold text-gray-900 mb-4">Global Savings Trend</h3>
        <ResponsiveContainer width="100%" height={400}>
          <AreaChart data={savingsData}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="name" />
            <YAxis tickFormatter={(value) => `${(value / 1000).toFixed(0)}k`} />
            <Tooltip content={<CustomTooltip />} />
            <Legend />
            <Area type="monotone" dataKey="onDemandCost" stackId="1" stroke="#ef4444" fill="#fecaca" name="On-Demand Cost" />
            <Area type="monotone" dataKey="modelCost" stackId="1" stroke="#3b82f6" fill="#bfdbfe" name="Optimized Cost" />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
};

export default GlobalSavingsPage;
