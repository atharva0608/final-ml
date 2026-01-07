/**
 * Admin Dashboard Component
 * Platform-wide statistics and monitoring for SUPER ADMIN only
 *
 * Features (from feature_mapping.md Part 3):
 * - admin-dash-kpi-reuse-indep-view-global: Global Business Metrics (Total Spend across ALL clients)
 * - admin-dash-traffic-reuse-indep-view-health: System Health Lights (DB/Redis/Workers)
 * - Quick links to Client Registry, System Health, The Lab
 */
import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { adminAPI } from '../../services/api';
import { Card, Button, Badge } from '../shared';
import {
  FiUsers, FiServer, FiDollarSign, FiActivity, FiRefreshCw,
  FiDatabase, FiCpu, FiAlertCircle, FiCheckCircle, FiSettings
} from 'react-icons/fi';
import toast from 'react-hot-toast';
import { formatCurrency, formatNumber } from '../../utils/formatters';

const AdminDashboard = () => {
  const navigate = useNavigate();
  const [stats, setStats] = useState(null);
  const [health, setHealth] = useState(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  useEffect(() => {
    fetchDashboardData();
  }, []);

  const fetchDashboardData = async () => {
    setLoading(true);
    try {
      // Fetch platform-wide statistics
      const [statsRes, healthRes] = await Promise.all([
        adminAPI.getStats().catch(() => ({ data: { stats: null } })),
        adminAPI.getHealth().catch(() => ({ data: { health: null } }))
      ]);

      setStats(statsRes.data.stats || {
        total_clients: 0,
        active_clients: 0,
        total_clusters: 0,
        total_spend: 0,
        total_savings: 0,
        total_instances: 0
      });

      setHealth(healthRes.data.health || {
        database: 'unknown',
        redis: 'unknown',
        workers: 'unknown'
      });
    } catch (error) {
      console.error('Failed to load admin dashboard:', error);
      toast.error('Failed to load platform statistics');
    } finally {
      setLoading(false);
    }
  };

  const handleRefresh = async () => {
    setRefreshing(true);
    await fetchDashboardData();
    setRefreshing(false);
    toast.success('Dashboard refreshed');
  };

  const HealthIndicator = ({ service, status }) => {
    const getStatusColor = (status) => {
      if (status === 'healthy' || status === 'up') return 'green';
      if (status === 'degraded') return 'yellow';
      return 'red';
    };

    const color = getStatusColor(status);
    const Icon = status === 'healthy' || status === 'up' ? FiCheckCircle : FiAlertCircle;

    return (
      <div className="flex items-center space-x-2">
        <Icon className={`w-5 h-5 text-${color}-500`} />
        <span className="text-sm font-medium text-gray-700 capitalize">{service}</span>
        <Badge variant={color === 'green' ? 'success' : color === 'yellow' ? 'warning' : 'danger'}>
          {status || 'unknown'}
        </Badge>
      </div>
    );
  };

  if (loading) {
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
          <h1 className="text-3xl font-bold text-gray-900">Platform Administration</h1>
          <p className="text-gray-600 mt-1">
            Super Admin Dashboard • Platform-wide Monitoring & Management
          </p>
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

      {/* Global Business Metrics (admin-dash-kpi-reuse-indep-view-global) */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        <Card className="bg-gradient-to-br from-blue-50 to-blue-100 border-blue-200">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-blue-600 mb-1">Total Clients</p>
              <p className="text-3xl font-bold text-blue-900">
                {formatNumber(stats.total_clients)}
              </p>
              <p className="text-xs text-blue-600 mt-2">
                {formatNumber(stats.active_clients)} active
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
              <p className="text-sm font-medium text-green-600 mb-1">Platform Spend</p>
              <p className="text-3xl font-bold text-green-900">
                {formatCurrency(stats.total_spend)}
              </p>
              <p className="text-xs text-green-600 mt-2">Across all clients</p>
            </div>
            <div className="w-12 h-12 bg-green-500 rounded-full flex items-center justify-center">
              <FiDollarSign className="w-6 h-6 text-white" />
            </div>
          </div>
        </Card>

        <Card className="bg-gradient-to-br from-purple-50 to-purple-100 border-purple-200">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-purple-600 mb-1">Total Savings</p>
              <p className="text-3xl font-bold text-purple-900">
                {formatCurrency(stats.total_savings)}
              </p>
              <p className="text-xs text-purple-600 mt-2">Platform-wide</p>
            </div>
            <div className="w-12 h-12 bg-purple-500 rounded-full flex items-center justify-center">
              <FiActivity className="w-6 h-6 text-white" />
            </div>
          </div>
        </Card>

        <Card className="bg-gradient-to-br from-orange-50 to-orange-100 border-orange-200">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-orange-600 mb-1">Total Clusters</p>
              <p className="text-3xl font-bold text-orange-900">
                {formatNumber(stats.total_clusters)}
              </p>
              <p className="text-xs text-orange-600 mt-2">
                {formatNumber(stats.total_instances)} instances
              </p>
            </div>
            <div className="w-12 h-12 bg-orange-500 rounded-full flex items-center justify-center">
              <FiServer className="w-6 h-6 text-white" />
            </div>
          </div>
        </Card>
      </div>

      {/* System Health Monitoring (admin-dash-traffic-reuse-indep-view-health) */}
      <Card>
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-xl font-bold text-gray-900">System Health</h2>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => navigate('/admin/health')}
          >
            View Details →
          </Button>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className="p-4 bg-gray-50 rounded-lg">
            <HealthIndicator service="Database" status={health.database} />
          </div>
          <div className="p-4 bg-gray-50 rounded-lg">
            <HealthIndicator service="Redis Cache" status={health.redis} />
          </div>
          <div className="p-4 bg-gray-50 rounded-lg">
            <HealthIndicator service="Celery Workers" status={health.workers} />
          </div>
        </div>
      </Card>

      {/* Quick Actions */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <Card className="hover:shadow-lg transition-shadow cursor-pointer" onClick={() => navigate('/admin/clients')}>
          <div className="flex items-start space-x-4">
            <div className="w-10 h-10 bg-blue-100 rounded-lg flex items-center justify-center">
              <FiUsers className="w-5 h-5 text-blue-600" />
            </div>
            <div>
              <h3 className="font-semibold text-gray-900">Client Registry</h3>
              <p className="text-sm text-gray-600 mt-1">
                Manage users, feature flags, and permissions
              </p>
              <p className="text-xs text-blue-600 mt-2 font-medium">
                View {stats.total_clients} clients →
              </p>
            </div>
          </div>
        </Card>

        <Card className="hover:shadow-lg transition-shadow cursor-pointer" onClick={() => navigate('/admin/health')}>
          <div className="flex items-start space-x-4">
            <div className="w-10 h-10 bg-green-100 rounded-lg flex items-center justify-center">
              <FiDatabase className="w-5 h-5 text-green-600" />
            </div>
            <div>
              <h3 className="font-semibold text-gray-900">System Health</h3>
              <p className="text-sm text-gray-600 mt-1">
                Monitor infrastructure and worker queues
              </p>
              <p className="text-xs text-green-600 mt-2 font-medium">
                View system status →
              </p>
            </div>
          </div>
        </Card>

        <Card className="hover:shadow-lg transition-shadow cursor-pointer" onClick={() => navigate('/lab')}>
          <div className="flex items-start space-x-4">
            <div className="w-10 h-10 bg-purple-100 rounded-lg flex items-center justify-center">
              <FiCpu className="w-5 h-5 text-purple-600" />
            </div>
            <div>
              <h3 className="font-semibold text-gray-900">The Lab</h3>
              <p className="text-sm text-gray-600 mt-1">
                ML model A/B testing and deployment
              </p>
              <p className="text-xs text-purple-600 mt-2 font-medium">
                Manage experiments →
              </p>
            </div>
          </div>
        </Card>
      </div>

      {/* Platform Notice */}
      <Card className="bg-yellow-50 border-yellow-200">
        <div className="flex items-start space-x-3">
          <FiAlertCircle className="w-5 h-5 text-yellow-600 flex-shrink-0 mt-0.5" />
          <div>
            <h3 className="font-semibold text-yellow-900">Super Admin Access</h3>
            <p className="text-sm text-yellow-700 mt-1">
              You have platform-wide administrative access. All changes affect multiple clients.
              Use caution when modifying feature flags or deleting client data.
            </p>
          </div>
        </div>
      </Card>
    </div>
  );
};

export default AdminDashboard;
