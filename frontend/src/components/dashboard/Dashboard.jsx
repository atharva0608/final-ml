/**
 * Client Dashboard Component
 * User-specific cluster optimization metrics and cost savings
 *
 * Features:
 * - Dynamic widget-based layout customized by role and user preferences
 * - Role-Based Access Control integration
 * - Real-time metrics
 */
import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useDashboard } from '../../hooks/useDashboard';
import { Card, Button } from '../shared';
import { formatCurrency, formatPercentage } from '../../utils/formatters';
import {
  FiRefreshCw, FiAlertCircle, FiCheck, FiX, FiUsers, FiBriefcase,
  FiLayout, FiSave, FiPlus, FiMinusCircle
} from 'react-icons/fi';
import toast from 'react-hot-toast';
import { auditAPI, clusterAPI, authAPI, accountsAPI } from '../../services/api';
import { useAuthStore } from '../../store/useStore';

// Widget System
import { renderWidget } from './widgetRegistry';
import { getDefaultLayout, WIDGET_METADATA, getWidgetsForRole } from './roleDefaults';
import AccessRequestModal from '../approvals/AccessRequestModal';

// Invitation Acceptance Modal Component
const InvitationModal = ({ user, onAccept, onDecline, loading }) => {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Backdrop with blur */}
      <div className="absolute inset-0 bg-gray-900/50 backdrop-blur-sm" />

      {/* Modal */}
      <div className="relative bg-white rounded-2xl shadow-2xl p-8 max-w-md w-full mx-4 border border-gray-200">
        <div className="flex justify-center mb-6">
          <div className="w-16 h-16 bg-blue-100 rounded-full flex items-center justify-center">
            <FiUsers className="w-8 h-8 text-blue-600" />
          </div>
        </div>

        <h2 className="text-2xl font-bold text-gray-900 text-center mb-2">
          You've Been Invited!
        </h2>
        <p className="text-gray-600 text-center mb-6">
          Please confirm your membership to continue
        </p>

        <div className="bg-gray-50 rounded-xl p-4 mb-6 space-y-3">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 bg-blue-100 rounded-lg flex items-center justify-center">
              <FiBriefcase className="w-5 h-5 text-blue-600" />
            </div>
            <div>
              <p className="text-xs text-gray-500 uppercase tracking-wide">Organization</p>
              <p className="font-semibold text-gray-900">{user?.organization_name || 'Your Organization'}</p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 bg-purple-100 rounded-lg flex items-center justify-center">
              <FiUsers className="w-5 h-5 text-purple-600" />
            </div>
            <div>
              <p className="text-xs text-gray-500 uppercase tracking-wide">Your Role</p>
              <p className="font-semibold text-gray-900">{user?.role?.replace('_', ' ') || 'Team Member'}</p>
            </div>
          </div>
        </div>

        <div className="flex gap-3">
          <Button variant="outline" className="flex-1" icon={<FiX className="w-4 h-4" />} onClick={onDecline} disabled={loading}>
            Decline
          </Button>
          <Button variant="primary" className="flex-1" icon={<FiCheck className="w-4 h-4" />} onClick={onAccept} disabled={loading}>
            {loading ? 'Accepting...' : 'Accept & Join'}
          </Button>
        </div>
      </div>
    </div>
  );
};

const Dashboard = () => {
  const navigate = useNavigate();
  const { user, updateUser, updatePreferences, logout } = useAuthStore();
  const { dashboardKPIs, costTimeSeries, loading, refreshDashboard } = useDashboard();

  // Local Data State
  const [activityFeed, setActivityFeed] = useState([]);
  const [savingsProjectionData, setSavingsProjectionData] = useState([]);
  const [clusters, setClusters] = useState([]);
  const [accounts, setAccounts] = useState([]);
  const [inviteLoading, setInviteLoading] = useState(false);
  const [tenants, setTenants] = useState([]); // For Super Admin
  const [dataLoading, setDataLoading] = useState(true);

  // Layout State
  const [activeLayout, setActiveLayout] = useState([]);
  const [isEditing, setIsEditing] = useState(false);
  const [showWidgetDrawer, setShowWidgetDrawer] = useState(false);
  const [availableWidgets, setAvailableWidgets] = useState([]);

  // Access Modal State
  const [showAccessModal, setShowAccessModal] = useState(false);

  // Check if user has pending invitation
  const showInvitationModal = user?.status === 'PENDING_INVITE';

  // Initialize Layout
  useEffect(() => {
    if (user?.role) {
      // 1. Get user preferences or fallback to role defaults
      const savedLayout = user.preferences?.dashboard_layout;
      const defaultLayout = getDefaultLayout(user.role);
      setActiveLayout(savedLayout || defaultLayout);

      // 2. Load available widgets for this role (for the Customization Drawer)
      setAvailableWidgets(getWidgetsForRole(user.role));
    }
  }, [user]);

  // Fetch Data (Consolidated)
  useEffect(() => {
    const fetchData = async () => {
      setDataLoading(true);
      try {
        // Common Data
        const logsRes = await auditAPI.list({ limit: 5 });
        const logs = logsRes.data.logs || [];
        setActivityFeed(logs.map(log => ({
          id: log.id,
          action: log.event_name || log.event || log.action,
          resource: log.resource_id || log.resource_type || 'System',
          status: (log.status || log.outcome) === 'success' ? 'success' : (log.status || log.outcome) === 'error' ? 'error' : 'info',
          time: new Date(log.created_at || log.timestamp)
        })));

        if (user?.role === 'SUPER_ADMIN') {
          // Fetch Tenants List
          const clientsRes = await auditAPI.listClients({ limit: 5 });
          // setTenants(...)
        } else {
          // Fetch Clusters & Accounts for standard users
          const clustersRes = await clusterAPI.listClusters();
          setClusters(clustersRes.data.clusters || []);
          const accountsRes = await accountsAPI.list();
          setAccounts(accountsRes.data || []);
        }

      } catch (error) {
        console.error('Failed to fetch dashboard data:', error);
      } finally {
        setDataLoading(false);
      }
    };
    fetchData();
  }, [user?.role]);

  // Update Savings Data
  useEffect(() => {
    if (costTimeSeries?.length > 0) {
      setSavingsProjectionData(costTimeSeries);
    } else {
      setSavingsProjectionData([]);
    }
  }, [costTimeSeries]);

  // Invitation Handlers
  const handleAcceptInvitation = async () => {
    setInviteLoading(true);
    try {
      await authAPI.respondToInvitation({ accept: true });
      toast.success("Welcome to the team!");
      updateUser({ ...user, status: 'ACTIVE' });
    } catch (error) {
      toast.error("Failed to accept invitation");
    } finally {
      setInviteLoading(false);
    }
  };

  const handleDeclineInvitation = async () => {
    setInviteLoading(true);
    try {
      await authAPI.respondToInvitation({ accept: false });
      toast.success("Invitation declined");
      logout();
      navigate('/login');
    } catch (error) {
      toast.error("Failed to decline invitation");
    } finally {
      setInviteLoading(false);
    }
  };

  const handleRefresh = async () => {
    await refreshDashboard();
    toast.success('Dashboard refreshed');
  };

  // Layout Customization Handlers
  const toggleEditMode = () => {
    setIsEditing(!isEditing);
    setShowWidgetDrawer(false);
  };

  const removeWidget = (widgetKey) => {
    setActiveLayout(prev => prev.filter(k => k !== widgetKey));
  };

  const addWidget = (widgetKey) => {
    if (!activeLayout.includes(widgetKey)) {
      setActiveLayout([...activeLayout, widgetKey]);
    }
  };

  const saveLayout = async () => {
    try {
      await authAPI.updatePreferences({ dashboard_layout: activeLayout });
      // Update local store optmistically
      updatePreferences({ dashboard_layout: activeLayout });
      setIsEditing(false);
      setShowWidgetDrawer(false);
      toast.success("Dashboard layout saved");
    } catch (error) {
      console.error("Failed to save layout:", error);
      toast.error("Failed to save layout");
    }
  };

  // Widget Data Mapper (Provides data to widgets dynamically)
  const getWidgetData = (key) => {
    switch (key) {
      case 'cost_kpi':
        return {
          current_spend: dashboardKPIs?.total_cost || 0,
          previous_spend: dashboardKPIs?.previous_month_cost || 0,
          label: 'Current Month Spend'
        };
      case 'savings_kpi':
        return {
          net_savings: dashboardKPIs?.estimated_savings || 0,
          savings_percentage: (dashboardKPIs?.optimization_rate || 0) / 100
        };
      case 'savings_chart':
        return { chartData: savingsProjectionData };
      case 'fleet_composition':
        return { chartData: [] };
      case 'activity_feed':
      case 'global_audit':
        return { activities: activityFeed };
      case 'cluster_health':
      case 'my_resources':
        return { clusters: clusters };
      case 'pending_approvals':
      case 'my_tickets':
        return { tickets: [] };
      case 'platform_health':
        return { metrics: { metrics: { uptime: '99.99%', active_workers: 4 } } };
      case 'tenant_list':
        return { tenants: tenants };
      default:
        return {};
    }
  };

  if (loading && !dashboardKPIs && user?.role !== 'SUPER_ADMIN') {
    return (
      <div className="flex items-center justify-center h-96">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
      </div>
    );
  }

  // Show onboarding card checks
  const canConnectDirectly = ['ORG_ADMIN', 'CLIENT', 'TEAM_LEAD'].includes(user?.role);
  // Allow everyone to see the button, but restricted roles see JIT modal
  const hasNoData = !loading && !dataLoading && accounts.length === 0 && user?.role !== 'SUPER_ADMIN';

  const handleConnectClick = () => {
    const allowedRoles = ['ORG_ADMIN', 'CLIENT', 'TEAM_LEAD'];
    if (allowedRoles.includes(user?.role)) {
      navigate('/onboarding');
    } else {
      setShowAccessModal(true);
    }
  };

  return (
    <>
      <AccessRequestModal
        isOpen={showAccessModal}
        onClose={() => setShowAccessModal(false)}
        resourceName="Add AWS Account"
        actionType="CONNECT_AWS_ACCOUNT"
        onSuccess={() => {
          setShowAccessModal(false);
          toast.success("Request sent to Team Lead");
        }}
      />

      {showInvitationModal && (
        <InvitationModal
          user={user}
          onAccept={handleAcceptInvitation}
          onDecline={handleDeclineInvitation}
          loading={inviteLoading}
        />
      )}

      <div className="space-y-6">
        {/* Header with Customization Controls */}
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">Dashboard</h1>
            <p className="text-gray-600">{user?.role === 'SUPER_ADMIN' ? 'Platform Overview' : 'Overview of your infrastructure'}</p>
          </div>

          <div className="flex items-center gap-2">
            {isEditing ? (
              <>
                <Button variant="outline" onClick={() => setShowWidgetDrawer(!showWidgetDrawer)} icon={<FiPlus />}>
                  Add Widget
                </Button>
                <Button variant="primary" onClick={saveLayout} icon={<FiSave />}>
                  Save Layout
                </Button>
              </>
            ) : (
              <Button variant="ghost" onClick={toggleEditMode} icon={<FiLayout />}>
                Customize
              </Button>
            )}
            <Button variant="outline" icon={<FiRefreshCw className={loading ? 'animate-spin' : ''} />} onClick={handleRefresh}>
              Refresh
            </Button>
          </div>
        </div>

        {/* Customization Drawer */}
        {showWidgetDrawer && isEditing && (
          <Card className="bg-gray-50 border-blue-100 mb-6 animate-fadeIn">
            <div className="flex justify-between items-center mb-4">
              <h3 className="font-semibold text-gray-900">Add Widgets</h3>
              <Button size="sm" variant="ghost" onClick={() => setShowWidgetDrawer(false)} icon={<FiX />} />
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
              {availableWidgets.map((widget) => {
                const isActive = activeLayout.includes(widget.key);
                return (
                  <div key={widget.key} className={`p-3 rounded-lg border flex items-center justify-between ${isActive ? 'bg-blue-50 border-blue-200' : 'bg-white border-gray-200'}`}>
                    <div className="flex items-center gap-3">
                      <div>
                        <p className="font-medium text-sm">{widget.name}</p>
                        <p className="text-xs text-gray-500">{widget.description}</p>
                      </div>
                    </div>
                    {isActive ? (
                      <span className="text-xs font-medium text-blue-600 flex items-center"><FiCheck className="mr-1" /> Added</span>
                    ) : (
                      <Button size="xs" variant="outline" onClick={() => addWidget(widget.key)} icon={<FiPlus />}>Add</Button>
                    )}
                  </div>
                );
              })}
            </div>
          </Card>
        )}

        {/* Onboarding Notice */}
        {hasNoData && !isEditing && (
          <Card className="bg-blue-50 border-blue-200">
            <div className="flex items-start space-x-3">
              <FiAlertCircle className="w-5 h-5 text-blue-600 flex-shrink-0 mt-0.5" />
              <div className="flex-1">
                <h3 className="font-semibold text-blue-900">Welcome! Connect your AWS account to get started</h3>
                <p className="text-sm text-blue-700 mt-1">
                  Connect your AWS account to discover clusters, optimize costs, and track savings.
                </p>
                <div className="mt-3">
                  <Button variant="primary" size="sm" onClick={handleConnectClick}>
                    Connect AWS Account →
                  </Button>
                </div>
              </div>
            </div>
          </Card>
        )}

        {/* Dynamic Widget Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
          {activeLayout.map((widgetKey) => {
            const isWide = ['savings_chart', 'activity_feed', 'global_audit', 'tenant_list', 'cluster_map'].includes(widgetKey);
            const colSpan = isWide ? 'md:col-span-2' : 'md:col-span-1';

            return (
              <div key={widgetKey} className={`relative ${colSpan} animate-fadeIn`}>
                {renderWidget(widgetKey, getWidgetData(widgetKey))}
                {isEditing && (
                  <button
                    onClick={() => removeWidget(widgetKey)}
                    className="absolute -top-2 -right-2 bg-red-100 text-red-600 p-1.5 rounded-full hover:bg-red-200 shadow-sm border border-red-200 z-10 transition-transform hover:scale-110"
                    title="Remove Widget"
                  >
                    <FiMinusCircle className="w-4 h-4" />
                  </button>
                )}
              </div>
            );
          })}
        </div>

        {activeLayout.length === 0 && (
          <div className="text-center py-12 bg-gray-50 rounded-xl border-2 border-dashed border-gray-200">
            <p className="text-gray-500">No widgets added.</p>
            <Button variant="outline" className="mt-2" onClick={() => { setIsEditing(true); setShowWidgetDrawer(true); }}>
              Add Your First Widget
            </Button>
          </div>
        )}
      </div>
    </>
  );
};

export default Dashboard;
