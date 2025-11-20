import React, { useState, useEffect, useCallback } from 'react';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, 
  AreaChart, Area, LineChart, Line, PieChart, Pie, Cell, RadarChart, PolarGrid,
  PolarAngleAxis, PolarRadiusAxis, Radar
} from 'recharts';
import {
  LayoutDashboard, Users, Server, Zap, BarChart3, History, AlertCircle,
  ChevronDown, ChevronRight, Search, Bell, CheckCircle, XCircle, Activity,
  Power, PowerOff, RefreshCw, Filter, Calendar, Download, Settings,
  Trash2, TrendingUp, DollarSign, Clock, Database, Cpu, Save, X, Eye,
  Menu, Shield, AlertTriangle, ChevronLeft, FileText, Globe, HardDrive,
  Play, Pause, RotateCw, Monitor, Package, Plus, Copy, Key, UserPlus
} from 'lucide-react';

// ==============================================================================
// API CONFIGURATION
// ==============================================================================

const API_CONFIG = {
  BASE_URL: 'http://13.203.97.250:5000',
};

// ==============================================================================
// COMPLETE API CLIENT - Updated with new client management methods
// ==============================================================================

class APIClient {
  constructor(baseUrl) {
    this.baseUrl = baseUrl;
  }

  async request(endpoint, options = {}) {
    try {
      const response = await fetch(`${this.baseUrl}${endpoint}`, {
        ...options,
        headers: {
          'Content-Type': 'application/json',
          ...options.headers,
        },
      });

      if (!response.ok) {
        const error = await response.json().catch(() => ({}));
        throw new Error(error.error || `API Error: ${response.status}`);
      }

      return await response.json();
    } catch (error) {
      console.error(`API Request Failed: ${endpoint}`, error);
      throw error;
    }
  }

  // Admin APIs
  async getGlobalStats() { return this.request('/api/admin/stats'); }
  async getAllClients() { return this.request('/api/admin/clients'); }
  async getRecentActivity() { return this.request('/api/admin/activity'); }
  async getSystemHealth() { return this.request('/api/admin/system-health'); }
  async getPoolStatistics() { return this.request('/api/admin/pool-statistics'); }
  async getAgentHealth() { return this.request('/api/admin/agent-health'); }
  async exportGlobalStats() { window.open(`${this.baseUrl}/api/admin/export/global-stats`, '_blank'); }

  // NEW: Client Management APIs
  async createClient(name) {
    return this.request('/api/admin/clients/create', {
      method: 'POST',
      body: JSON.stringify({ name }),
    });
  }

  async deleteClient(clientId) {
    return this.request(`/api/admin/clients/${clientId}`, {
      method: 'DELETE',
    });
  }

  async regenerateClientToken(clientId) {
    return this.request(`/api/admin/clients/${clientId}/regenerate-token`, {
      method: 'POST',
    });
  }

  async getClientToken(clientId) {
    return this.request(`/api/admin/clients/${clientId}/token`);
  }

  // Notification APIs
  async getNotifications(clientId = null, limit = 10) {
    const params = new URLSearchParams();
    if (clientId) params.append('client_id', clientId);
    params.append('limit', limit);
    return this.request(`/api/notifications?${params}`);
  }
  
  async markNotificationRead(notifId) {
    return this.request(`/api/notifications/${notifId}/mark-read`, { method: 'POST' });
  }
  
  async markAllNotificationsRead(clientId = null) {
    return this.request('/api/notifications/mark-all-read', {
      method: 'POST',
      body: JSON.stringify({ client_id: clientId }),
    });
  }

  // Search API
  async globalSearch(query) {
    return this.request(`/api/search?q=${encodeURIComponent(query)}`);
  }

  // Client APIs
  async getClientDetails(clientId) { return this.request(`/api/client/${clientId}`); }
  async getAgents(clientId) { return this.request(`/api/client/${clientId}/agents`); }
  async getClientChartData(clientId) { return this.request(`/api/client/${clientId}/stats/charts`); }
  
  async toggleAgent(agentId, enabled) {
    return this.request(`/api/client/agents/${agentId}/toggle-enabled`, {
      method: 'POST',
      body: JSON.stringify({ enabled }),
    });
  }

  async updateAgentSettings(agentId, settings) {
    return this.request(`/api/client/agents/${agentId}/settings`, {
      method: 'POST',
      body: JSON.stringify(settings),
    });
  }

  async updateAgentConfig(agentId, config) {
    return this.request(`/api/client/agents/${agentId}/config`, {
      method: 'POST',
      body: JSON.stringify(config),
    });
  }

  async getAgentStatistics(agentId) {
    return this.request(`/api/client/agents/${agentId}/statistics`);
  }

  async getInstances(clientId, filters = {}) {
    const params = new URLSearchParams(
      Object.entries(filters).filter(([_, v]) => v && v !== 'all')
    );
    const query = params.toString() ? `?${params}` : '';
    return this.request(`/api/client/${clientId}/instances${query}`);
  }

  async getInstancePricing(instanceId) {
    return this.request(`/api/client/instances/${instanceId}/pricing`);
  }

  async getInstanceMetrics(instanceId) {
    return this.request(`/api/client/instances/${instanceId}/metrics`);
  }

  async getPriceHistory(instanceId, days = 7, interval = 'hour') {
    return this.request(`/api/client/instances/${instanceId}/price-history?days=${days}&interval=${interval}`);
  }

  async forceSwitch(instanceId, body) {
    return this.request(`/api/client/instances/${instanceId}/force-switch`, {
      method: 'POST',
      body: JSON.stringify(body),
    });
  }

  async getSavings(clientId, range = 'monthly') {
    return this.request(`/api/client/${clientId}/savings?range=${range}`);
  }

  async getSwitchHistory(clientId, instanceId = null) {
    const query = instanceId ? `?instance_id=${instanceId}` : '';
    return this.request(`/api/client/${clientId}/switch-history${query}`);
  }

  async exportSavings(clientId) {
    window.open(`${this.baseUrl}/api/client/${clientId}/export/savings`, '_blank');
  }

  async exportSwitchHistory(clientId) {
    window.open(`${this.baseUrl}/api/client/${clientId}/export/switch-history`, '_blank');
  }

  async healthCheck() {
    return this.request('/health');
  }

  async getInstanceLogs(instanceId, limit = 50) {
    return this.request(`/api/client/instances/${instanceId}/logs?limit=${limit}`);
  }

  async getAllInstancesGlobal(filters = {}) {
    const params = new URLSearchParams(
      Object.entries(filters).filter(([_, v]) => v && v !== 'all')
    );
    const query = params.toString() ? `?${params}` : '';
    return this.request(`/api/admin/instances${query}`);
  }

  async getAllAgentsGlobal() {
    return this.request('/api/admin/agents');
  }
}

const api = new APIClient(API_CONFIG.BASE_URL);

// ==============================================================================
// REUSABLE UI COMPONENTS
// ==============================================================================

const LoadingSpinner = ({ size = 'md' }) => {
  const sizeClasses = { sm: 'w-4 h-4', md: 'w-8 h-8', lg: 'w-12 h-12' };
  return (
    <div className={`animate-spin rounded-full border-t-2 border-b-2 border-blue-500 ${sizeClasses[size]}`}></div>
  );
};

const StatCard = ({ title, value, icon, change, changeType, subtitle, className = '' }) => (
  <div className={`bg-white p-4 md:p-5 rounded-xl shadow-sm border border-gray-200 hover:shadow-md transition-all duration-200 ${className}`}>
    <div className="flex items-center justify-between">
      <div className="flex-1 min-w-0">
        <p className="text-xs font-medium text-gray-500 uppercase tracking-wide truncate">{title}</p>
        <p className="text-2xl md:text-3xl font-bold text-gray-900 mt-2 truncate">{value}</p>
        {subtitle && <p className="text-xs text-gray-500 mt-1 truncate">{subtitle}</p>}
        {change && (
          <p className={`text-sm font-medium mt-2 ${changeType === 'positive' ? 'text-green-600' : 'text-red-600'}`}>
            {change}
          </p>
        )}
      </div>
      <div className="bg-gradient-to-br from-blue-500 to-blue-600 text-white p-3 md:p-4 rounded-xl shadow-lg flex-shrink-0 ml-2">
        {icon}
      </div>
    </div>
  </div>
);

const Badge = ({ children, variant = 'default' }) => {
  const variants = {
    default: 'bg-gray-100 text-gray-800',
    success: 'bg-green-100 text-green-800',
    danger: 'bg-red-100 text-red-800',
    warning: 'bg-yellow-100 text-yellow-800',
    info: 'bg-blue-100 text-blue-800',
  };
  return (
    <span className={`px-2.5 py-1 rounded-full text-xs font-semibold whitespace-nowrap ${variants[variant]}`}>
      {children}
    </span>
  );
};

const Button = ({ children, onClick, variant = 'primary', size = 'md', disabled, icon, loading, className = '' }) => {
  const variants = {
    primary: 'bg-blue-600 hover:bg-blue-700 text-white',
    secondary: 'bg-gray-600 hover:bg-gray-700 text-white',
    success: 'bg-green-600 hover:bg-green-700 text-white',
    danger: 'bg-red-600 hover:bg-red-700 text-white',
    outline: 'border-2 border-gray-300 hover:bg-gray-50 text-gray-700',
  };
  const sizes = {
    sm: 'px-3 py-1.5 text-xs',
    md: 'px-4 py-2 text-sm',
    lg: 'px-6 py-3 text-base',
  };
  
  return (
    <button
      onClick={onClick}
      disabled={disabled || loading}
      className={`flex items-center justify-center space-x-2 rounded-lg font-medium transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed ${variants[variant]} ${sizes[size]} ${className}`}
    >
      {loading ? (
        <LoadingSpinner size="sm" />
      ) : (
        <>
          {icon && <span className="flex-shrink-0">{icon}</span>}
          <span className="truncate">{children}</span>
        </>
      )}
    </button>
  );
};

const ToggleSwitch = ({ enabled, onChange, label }) => {
  const handleClick = (e) => {
    e.preventDefault();
    e.stopPropagation();
    onChange(!enabled);
  };

  return (
    <button
      type="button"
      onClick={handleClick}
      className={`relative inline-flex items-center h-6 rounded-full w-11 transition-colors focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 ${
        enabled ? 'bg-blue-600' : 'bg-gray-300'
      }`}
    >
      <span className="sr-only">{label}</span>
      <span
        className={`inline-block w-4 h-4 transform bg-white rounded-full transition-transform ${
          enabled ? 'translate-x-6' : 'translate-x-1'
        }`}
      />
    </button>
  );
};

const CustomTooltip = ({ active, payload, label }) => {
  if (active && payload && payload.length) {
    return (
      <div className="bg-white p-4 rounded-lg shadow-xl border border-gray-200">
        <p className="font-semibold text-gray-800 mb-2">{label}</p>
        {payload.map((entry, index) => (
          <p key={`item-${index}`} style={{ color: entry.color }} className="text-sm font-medium">
            {`${entry.name}: ${typeof entry.value === 'number' ? entry.value.toLocaleString(undefined, { style: 'currency', currency: 'USD' }) : entry.value}`}
          </p>
        ))}
      </div>
    );
  }
  return null;
};

const ErrorMessage = ({ message, onRetry }) => (
  <div className="bg-red-50 border-2 border-red-200 rounded-lg p-4">
    <div className="flex items-start space-x-3">
      <AlertCircle className="text-red-600 flex-shrink-0" size={20} />
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium text-red-800">Error</p>
        <p className="text-sm text-red-600 mt-1 break-words">{message}</p>
      </div>
      {onRetry && (
        <Button variant="danger" size="sm" onClick={onRetry}>
          Retry
        </Button>
      )}
    </div>
  </div>
);

const EmptyState = ({ icon, title, description }) => (
  <div className="flex flex-col items-center justify-center py-12 text-gray-400">
    {icon}
    <p className="text-lg font-medium text-gray-600 mt-4">{title}</p>
    {description && <p className="text-sm text-gray-500 mt-1 text-center px-4">{description}</p>}
  </div>
);

// ==============================================================================
// NEW: ADD CLIENT MODAL COMPONENT
// ==============================================================================

const AddClientModal = ({ onClose, onSuccess }) => {
  const [clientName, setClientName] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [createdClient, setCreatedClient] = useState(null);
  const [copied, setCopied] = useState(false);

  const handleCreate = async () => {
    if (!clientName.trim()) {
      setError('Client name is required');
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const result = await api.createClient(clientName.trim());
      setCreatedClient(result.client);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleCopyToken = () => {
    if (createdClient?.token) {
      navigator.clipboard.writeText(createdClient.token);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  const handleClose = () => {
    if (createdClient) {
      onSuccess();
    }
    onClose();
  };

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-xl shadow-2xl w-full max-w-lg max-h-[90vh] overflow-y-auto">
        {/* Modal Header */}
        <div className="p-6 border-b border-gray-200 sticky top-0 bg-white">
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-3">
              <div className="bg-blue-100 p-2 rounded-lg">
                <UserPlus size={24} className="text-blue-600" />
              </div>
              <div>
                <h3 className="text-xl font-bold text-gray-900">
                  {createdClient ? 'Client Created!' : 'Add New Client'}
                </h3>
                <p className="text-sm text-gray-500 mt-1">
                  {createdClient 
                    ? 'Save the token below - it won\'t be shown again'
                    : 'Create a new client account with auto-generated token'}
                </p>
              </div>
            </div>
            <button onClick={handleClose} className="text-gray-400 hover:text-gray-600 transition-colors">
              <X size={24} />
            </button>
          </div>
        </div>

        {/* Modal Body */}
        <div className="p-6">
          {!createdClient ? (
            // Creation Form
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Client Name *
                </label>
                <input
                  type="text"
                  value={clientName}
                  onChange={(e) => setClientName(e.target.value)}
                  placeholder="e.g., Acme Corporation"
                  className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent text-sm"
                  onKeyPress={(e) => e.key === 'Enter' && handleCreate()}
                  autoFocus
                />
                <p className="text-xs text-gray-500 mt-2">
                  A unique client ID and secure token will be auto-generated
                </p>
              </div>

              {error && (
                <div className="bg-red-50 border border-red-200 rounded-lg p-3">
                  <div className="flex items-center space-x-2">
                    <AlertCircle size={16} className="text-red-600" />
                    <p className="text-sm text-red-600">{error}</p>
                  </div>
                </div>
              )}
            </div>
          ) : (
            // Success View with Token Display
            <div className="space-y-4">
              <div className="bg-green-50 border border-green-200 rounded-lg p-4">
                <div className="flex items-center space-x-2 mb-2">
                  <CheckCircle size={20} className="text-green-600" />
                  <p className="text-sm font-semibold text-green-800">Client Created Successfully!</p>
                </div>
              </div>

              <div className="space-y-3">
                <div>
                  <label className="block text-xs font-semibold text-gray-600 uppercase mb-1">
                    Client ID
                  </label>
                  <div className="bg-gray-50 px-4 py-3 rounded-lg border border-gray-200">
                    <code className="text-sm font-mono text-gray-800">{createdClient.id}</code>
                  </div>
                </div>

                <div>
                  <label className="block text-xs font-semibold text-gray-600 uppercase mb-1">
                    Client Name
                  </label>
                  <div className="bg-gray-50 px-4 py-3 rounded-lg border border-gray-200">
                    <span className="text-sm text-gray-800">{createdClient.name}</span>
                  </div>
                </div>

                <div>
                  <label className="block text-xs font-semibold text-gray-600 uppercase mb-1">
                    Client Token (API Key)
                  </label>
                  <div className="relative">
                    <div className="bg-yellow-50 px-4 py-3 rounded-lg border-2 border-yellow-300 pr-24">
                      <code className="text-sm font-mono text-gray-800 break-all">
                        {createdClient.token}
                      </code>
                    </div>
                    <button
                      onClick={handleCopyToken}
                      className="absolute right-2 top-1/2 -translate-y-1/2 bg-white px-3 py-1.5 rounded border border-gray-300 hover:bg-gray-50 transition-colors flex items-center space-x-1"
                    >
                      {copied ? (
                        <>
                          <CheckCircle size={14} className="text-green-600" />
                          <span className="text-xs font-medium text-green-600">Copied!</span>
                        </>
                      ) : (
                        <>
                          <Copy size={14} className="text-gray-600" />
                          <span className="text-xs font-medium text-gray-600">Copy</span>
                        </>
                      )}
                    </button>
                  </div>
                  <div className="mt-2 bg-yellow-50 border border-yellow-200 rounded p-3">
                    <div className="flex items-start space-x-2">
                      <AlertTriangle size={16} className="text-yellow-600 flex-shrink-0 mt-0.5" />
                      <p className="text-xs text-yellow-800">
                        <strong>Important:</strong> Save this token securely! It will be used by the agent to authenticate with the server. You can regenerate it later, but all existing agents will need to be updated.
                      </p>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Modal Footer */}
        <div className="p-6 border-t border-gray-200 flex justify-end space-x-3 sticky bottom-0 bg-white">
          {!createdClient ? (
            <>
              <Button variant="outline" onClick={onClose} disabled={loading}>
                Cancel
              </Button>
              <Button
                variant="primary"
                onClick={handleCreate}
                loading={loading}
                icon={<Plus size={16} />}
              >
                Create Client
              </Button>
            </>
          ) : (
            <Button variant="success" onClick={handleClose} icon={<CheckCircle size={16} />}>
              Done
            </Button>
          )}
        </div>
      </div>
    </div>
  );
};

// ==============================================================================
// NEW: VIEW TOKEN MODAL COMPONENT
// ==============================================================================

const ViewTokenModal = ({ client, onClose, onRegenerate }) => {
  const [token, setToken] = useState(null);
  const [loading, setLoading] = useState(true);
  const [regenerating, setRegenerating] = useState(false);
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    loadToken();
  }, [client.id]);

  const loadToken = async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await api.getClientToken(client.id);
      setToken(result.token);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleRegenerate = async () => {
    if (!window.confirm(
      `⚠️ WARNING: Regenerating the token will invalidate the current token.\n\n` +
      `All agents using the old token will lose connection and need to be updated.\n\n` +
      `Are you sure you want to continue?`
    )) {
      return;
    }

    setRegenerating(true);
    try {
      const result = await api.regenerateClientToken(client.id);
      setToken(result.token);
      if (onRegenerate) onRegenerate();
      alert('✓ Token regenerated successfully!\n\nMake sure to update all agents with the new token.');
    } catch (err) {
      alert('Failed to regenerate token: ' + err.message);
    } finally {
      setRegenerating(false);
    }
  };

  const handleCopy = () => {
    if (token) {
      navigator.clipboard.writeText(token);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-xl shadow-2xl w-full max-w-lg">
        <div className="p-6 border-b border-gray-200">
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-3">
              <div className="bg-yellow-100 p-2 rounded-lg">
                <Key size={24} className="text-yellow-600" />
              </div>
              <div>
                <h3 className="text-xl font-bold text-gray-900">Client Token</h3>
                <p className="text-sm text-gray-500 mt-1">{client.name}</p>
              </div>
            </div>
            <button onClick={onClose} className="text-gray-400 hover:text-gray-600">
              <X size={24} />
            </button>
          </div>
        </div>

        <div className="p-6">
          {loading ? (
            <div className="flex justify-center py-8">
              <LoadingSpinner />
            </div>
          ) : error ? (
            <ErrorMessage message={error} onRetry={loadToken} />
          ) : (
            <div className="space-y-4">
              <div>
                <label className="block text-xs font-semibold text-gray-600 uppercase mb-2">
                  API Token
                </label>
                <div className="relative">
                  <div className="bg-gray-50 px-4 py-3 rounded-lg border border-gray-300 pr-24">
                    <code className="text-sm font-mono text-gray-800 break-all">{token}</code>
                  </div>
                  <button
                    onClick={handleCopy}
                    className="absolute right-2 top-1/2 -translate-y-1/2 bg-white px-3 py-1.5 rounded border border-gray-300 hover:bg-gray-50 flex items-center space-x-1"
                  >
                    {copied ? (
                      <>
                        <CheckCircle size={14} className="text-green-600" />
                        <span className="text-xs font-medium text-green-600">Copied!</span>
                      </>
                    ) : (
                      <>
                        <Copy size={14} className="text-gray-600" />
                        <span className="text-xs font-medium text-gray-600">Copy</span>
                      </>
                    )}
                  </button>
                </div>
              </div>

              <div className="bg-orange-50 border border-orange-200 rounded-lg p-3">
                <div className="flex items-start space-x-2">
                  <AlertTriangle size={16} className="text-orange-600 flex-shrink-0 mt-0.5" />
                  <p className="text-xs text-orange-800">
                    Keep this token secure. Anyone with this token can register agents and access this client's data.
                  </p>
                </div>
              </div>
            </div>
          )}
        </div>

        <div className="p-6 border-t border-gray-200 flex justify-between">
          <Button
            variant="danger"
            size="sm"
            onClick={handleRegenerate}
            loading={regenerating}
            icon={<RefreshCw size={14} />}
          >
            Regenerate Token
          </Button>
          <Button variant="outline" onClick={onClose}>
            Close
          </Button>
        </div>
      </div>
    </div>
  );
};

// ==============================================================================
// NEW: DELETE CLIENT CONFIRMATION MODAL
// ==============================================================================

const DeleteClientModal = ({ client, onClose, onSuccess }) => {
  const [confirmName, setConfirmName] = useState('');
  const [loading, setLoading] = useState(false);

  const handleDelete = async () => {
    if (confirmName !== client.name) {
      alert('Client name does not match. Please type the exact client name to confirm deletion.');
      return;
    }

    setLoading(true);
    try {
      await api.deleteClient(client.id);
      alert(`✓ Client "${client.name}" has been deleted successfully.`);
      onSuccess();
      onClose();
    } catch (err) {
      alert('Failed to delete client: ' + err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-xl shadow-2xl w-full max-w-md">
        <div className="p-6 border-b border-gray-200">
          <div className="flex items-center space-x-3">
            <div className="bg-red-100 p-2 rounded-lg">
              <Trash2 size={24} className="text-red-600" />
            </div>
            <div>
              <h3 className="text-xl font-bold text-gray-900">Delete Client</h3>
              <p className="text-sm text-gray-500 mt-1">This action cannot be undone</p>
            </div>
          </div>
        </div>

        <div className="p-6 space-y-4">
          <div className="bg-red-50 border border-red-200 rounded-lg p-4">
            <p className="text-sm text-red-800">
              <strong>Warning:</strong> Deleting this client will permanently remove:
            </p>
            <ul className="list-disc list-inside text-sm text-red-700 mt-2 space-y-1">
              <li>All agents and their configurations</li>
              <li>All instances and their history</li>
              <li>All switch events and savings data</li>
              <li>All notifications and system events</li>
            </ul>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Type <strong>"{client.name}"</strong> to confirm deletion:
            </label>
            <input
              type="text"
              value={confirmName}
              onChange={(e) => setConfirmName(e.target.value)}
              placeholder="Enter client name"
              className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-red-500 focus:border-transparent text-sm"
            />
          </div>
        </div>

        <div className="p-6 border-t border-gray-200 flex justify-end space-x-3">
          <Button variant="outline" onClick={onClose} disabled={loading}>
            Cancel
          </Button>
          <Button
            variant="danger"
            onClick={handleDelete}
            loading={loading}
            disabled={confirmName !== client.name}
            icon={<Trash2 size={16} />}
          >
            Delete Client
          </Button>
        </div>
      </div>
    </div>
  );
};
// ==============================================================================
// NOTIFICATION PANEL
// ==============================================================================

const NotificationPanel = ({ isOpen, onClose, clientId = null }) => {
  const [notifications, setNotifications] = useState([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (isOpen) {
      loadNotifications();
    }
  }, [isOpen, clientId]);

  const loadNotifications = async () => {
    setLoading(true);
    try {
      const data = await api.getNotifications(clientId, 20);
      setNotifications(data);
    } catch (error) {
      console.error('Failed to load notifications:', error);
    } finally {
      setLoading(false);
    }
  };

  const markAsRead = async (notifId) => {
    try {
      await api.markNotificationRead(notifId);
      setNotifications(prev => 
        prev.map(n => n.id === notifId ? {...n, isRead: true} : n)
      );
    } catch (error) {
      console.error('Failed to mark as read:', error);
    }
  };

  const markAllAsRead = async () => {
    try {
      await api.markAllNotificationsRead(clientId);
      setNotifications(prev => prev.map(n => ({...n, isRead: true})));
    } catch (error) {
      console.error('Failed to mark all as read:', error);
    }
  };

  if (!isOpen) return null;

  const unreadCount = notifications.filter(n => !n.isRead).length;

  return (
    <>
      <div className="fixed inset-0 bg-black bg-opacity-50 z-50" onClick={onClose}></div>
      <div className="fixed right-0 top-0 h-full w-96 bg-white shadow-2xl z-50 overflow-hidden flex flex-col">
        <div className="p-4 border-b border-gray-200 flex items-center justify-between">
          <div>
            <h3 className="text-lg font-bold text-gray-900">Notifications</h3>
            {unreadCount > 0 && (
              <p className="text-sm text-gray-500">{unreadCount} unread</p>
            )}
          </div>
          <div className="flex items-center space-x-2">
            {unreadCount > 0 && (
              <button
                onClick={markAllAsRead}
                className="text-sm text-blue-600 hover:text-blue-800"
              >
                Mark all read
              </button>
            )}
            <button onClick={onClose} className="text-gray-400 hover:text-gray-600">
              <X size={20} />
            </button>
          </div>
        </div>
        
        <div className="flex-1 overflow-y-auto">
          {loading ? (
            <div className="flex justify-center items-center h-64">
              <LoadingSpinner />
            </div>
          ) : notifications.length === 0 ? (
            <EmptyState
              icon={<Bell size={48} />}
              title="No notifications"
              description="You're all caught up!"
            />
          ) : (
            <div className="divide-y divide-gray-100">
              {notifications.map(notif => (
                <div
                  key={notif.id}
                  className={`p-4 hover:bg-gray-50 cursor-pointer transition-colors ${
                    !notif.isRead ? 'bg-blue-50' : ''
                  }`}
                  onClick={() => !notif.isRead && markAsRead(notif.id)}
                >
                  <div className="flex items-start space-x-3">
                    <div className={`flex-shrink-0 w-2 h-2 rounded-full mt-2 ${
                      !notif.isRead ? 'bg-blue-600' : 'bg-gray-300'
                    }`}></div>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm text-gray-900 break-words">{notif.message}</p>
                      <p className="text-xs text-gray-500 mt-1">
                        {new Date(notif.time).toLocaleString()}
                      </p>
                    </div>
                    <Badge variant={
                      notif.severity === 'error' ? 'danger' :
                      notif.severity === 'warning' ? 'warning' : 'info'
                    }>
                      {notif.severity}
                    </Badge>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </>
  );
};

// ==============================================================================
// SEARCH RESULTS PANEL
// ==============================================================================

const SearchResultsPanel = ({ isOpen, onClose, query, onSelectResult }) => {
  const [results, setResults] = useState({ clients: [], instances: [], agents: [] });
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (isOpen && query && query.length >= 2) {
      performSearch();
    } else {
      setResults({ clients: [], instances: [], agents: [] });
    }
  }, [isOpen, query]);

  const performSearch = async () => {
    setLoading(true);
    try {
      const data = await api.globalSearch(query);
      setResults(data);
    } catch (error) {
      console.error('Search failed:', error);
    } finally {
      setLoading(false);
    }
  };

  if (!isOpen) return null;

  const totalResults = results.clients.length + results.instances.length + results.agents.length;

  return (
    <>
      <div className="fixed inset-0 bg-black bg-opacity-50 z-40" onClick={onClose}></div>
      <div className="fixed top-20 left-1/2 transform -translate-x-1/2 w-full max-w-2xl bg-white rounded-lg shadow-2xl z-50 max-h-96 overflow-hidden">
        <div className="p-4 border-b border-gray-200">
          <div className="flex items-center justify-between">
            <h3 className="text-lg font-bold text-gray-900">
              Search Results {query && `for "${query}"`}
            </h3>
            <button onClick={onClose} className="text-gray-400 hover:text-gray-600">
              <X size={20} />
            </button>
          </div>
          {totalResults > 0 && (
            <p className="text-sm text-gray-500 mt-1">{totalResults} results found</p>
          )}
        </div>
        
        <div className="overflow-y-auto max-h-80">
          {loading ? (
            <div className="flex justify-center items-center h-40">
              <LoadingSpinner />
            </div>
          ) : totalResults === 0 ? (
            <div className="p-8">
              <EmptyState
                icon={<Search size={48} />}
                title="No results found"
                description={query ? `No matches for "${query}"` : 'Enter a search query'}
              />
            </div>
          ) : (
            <div className="divide-y divide-gray-100">
              {results.clients.length > 0 && (
                <div className="p-4">
                  <h4 className="text-sm font-semibold text-gray-700 mb-2">Clients</h4>
                  {results.clients.map(item => (
                    <div
                      key={item.id}
                      onClick={() => {
                        onSelectResult('client', item.id);
                        onClose();
                      }}
                      className="p-3 hover:bg-gray-50 rounded-lg cursor-pointer mb-2"
                    >
                      <div className="flex items-center justify-between">
                        <div>
                          <p className="text-sm font-medium text-gray-900">{item.name}</p>
                          <p className="text-xs text-gray-500">{item.id}</p>
                        </div>
                        <Badge variant={item.status === 'active' ? 'success' : 'danger'}>
                          {item.status}
                        </Badge>
                      </div>
                    </div>
                  ))}
                </div>
              )}
              
              {results.instances.length > 0 && (
                <div className="p-4">
                  <h4 className="text-sm font-semibold text-gray-700 mb-2">Instances</h4>
                  {results.instances.map(item => (
                    <div
                      key={item.id}
                      onClick={() => {
                        onSelectResult('instance', item.id);
                        onClose();
                      }}
                      className="p-3 hover:bg-gray-50 rounded-lg cursor-pointer mb-2"
                    >
                      <p className="text-sm font-medium text-gray-900">{item.name}</p>
                      <p className="text-xs text-gray-500">{item.client}</p>
                    </div>
                  ))}
                </div>
              )}
              
              {results.agents.length > 0 && (
                <div className="p-4">
                  <h4 className="text-sm font-semibold text-gray-700 mb-2">Agents</h4>
                  {results.agents.map(item => (
                    <div
                      key={item.id}
                      onClick={() => {
                        onSelectResult('agent', item.id);
                        onClose();
                      }}
                      className="p-3 hover:bg-gray-50 rounded-lg cursor-pointer mb-2"
                    >
                      <div className="flex items-center justify-between">
                        <div>
                          <p className="text-sm font-medium text-gray-900">{item.name}</p>
                          <p className="text-xs text-gray-500">{item.client}</p>
                        </div>
                        <Badge variant={item.status === 'online' ? 'success' : 'danger'}>
                          {item.status}
                        </Badge>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </>
  );
};

// ==============================================================================
// SIDEBAR COMPONENT
// ==============================================================================

const AdminSidebar = ({ clients, onSelectClient, activeClientId, onSelectPage, activePage, isOpen, onClose }) => {
  const menuItems = [
    { id: 'overview', label: 'Overview', icon: <LayoutDashboard size={18} /> },
    { id: 'clients', label: 'Clients', icon: <Users size={18} /> },
    { id: 'agents', label: 'All Agents', icon: <Server size={18} /> },
    { id: 'instances', label: 'All Instances', icon: <Zap size={18} /> },
    { id: 'savings', label: 'Global Savings', icon: <BarChart3 size={18} /> },
    { id: 'activity', label: 'Activity Log', icon: <History size={18} /> },
    { id: 'health', label: 'System Health', icon: <Activity size={18} /> },
  ];

  return (
    <>
      {isOpen && (
        <div 
          className="fixed inset-0 bg-black bg-opacity-50 z-40 lg:hidden"
          onClick={onClose}
        />
      )}
      
      <div className={`fixed top-0 left-0 h-screen bg-gradient-to-b from-gray-900 to-gray-800 text-white shadow-2xl overflow-y-auto z-50 transition-transform duration-300 ease-in-out ${
        isOpen ? 'translate-x-0' : '-translate-x-full'
      } lg:translate-x-0 w-72`}>
        <div className="p-6 border-b border-gray-700 flex-shrink-0">
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-3">
              <div className="bg-blue-600 p-2 rounded-lg">
                <Zap size={24} />
              </div>
              <div>
                <h1 className="text-xl font-bold">SmartDevops</h1>
                <p className="text-xs text-gray-400">Admin Dashboard</p>
              </div>
            </div>
            <button onClick={onClose} className="lg:hidden text-gray-400 hover:text-white">
              <X size={24} />
            </button>
          </div>
        </div>
        
        <nav className="p-3 flex-shrink-0">
          <ul className="space-y-1">
            {menuItems.map(item => {
              const isActive = activePage === item.id;
              return (
                <li key={item.id}>
                  <button
                    onClick={() => {
                      onSelectPage(item.id);
                      if (window.innerWidth < 1024) onClose();
                    }}
                    className={`flex items-center w-full px-4 py-3 rounded-lg text-sm font-medium transition-all duration-200 ${
                      isActive 
                        ? 'bg-blue-600 text-white shadow-lg' 
                        : 'text-gray-300 hover:bg-gray-700 hover:text-white'
                    }`}
                  >
                    {item.icon}
                    <span className="ml-3">{item.label}</span>
                  </button>
                </li>
              );
            })}
          </ul>
        </nav>
        
        <div className="p-3 mt-2 border-t border-gray-700 flex-1 overflow-y-auto">
          <h2 className="px-4 py-2 text-xs font-semibold text-gray-400 uppercase tracking-wider">
            Active Clients ({clients.length})
          </h2>
          <ul className="mt-2 space-y-1">
            {clients.length === 0 ? (
              <div className="flex justify-center p-4">
                <LoadingSpinner size="sm" />
              </div>
            ) : (
              clients.map(client => (
                <li key={client.id}>
                  <button
                    onClick={() => {
                      onSelectClient(client.id);
                      if (window.innerWidth < 1024) onClose();
                    }}
                    className={`flex items-center justify-between w-full px-4 py-3 rounded-lg text-sm transition-all duration-200 ${
                      activeClientId === client.id 
                        ? 'bg-blue-600 text-white shadow-lg' 
                        : 'text-gray-300 hover:bg-gray-700 hover:text-white'
                    }`}
                  >
                    <div className="flex items-center space-x-3 flex-1 min-w-0">
                      <div className={`w-2 h-2 rounded-full flex-shrink-0 ${client.status === 'active' ? 'bg-green-400' : 'bg-red-400'}`}></div>
                      <span className="truncate">{client.name}</span>
                    </div>
                    <Badge variant={client.status === 'active' ? 'success' : 'danger'}>
                      {client.instances}
                    </Badge>
                  </button>
                </li>
              ))
            )}
          </ul>
        </div>
        
        <div className="p-4 border-t border-gray-700 flex-shrink-0">
          <div className="text-xs text-gray-400 space-y-1">
            <p>© 2025 SmartDevops</p>
          </div>
        </div>
      </div>
    </>
  );
};

// ==============================================================================
// HEADER COMPONENT
// ==============================================================================

const AdminHeader = ({ stats, onRefresh, lastRefresh, onMenuToggle }) => {
  const [searchQuery, setSearchQuery] = useState('');
  const [showSearch, setShowSearch] = useState(false);
  const [showNotifications, setShowNotifications] = useState(false);
  const [unreadCount, setUnreadCount] = useState(0);

  useEffect(() => {
    loadUnreadCount();
    const interval = setInterval(loadUnreadCount, 30000);
    return () => clearInterval(interval);
  }, []);

  const loadUnreadCount = async () => {
    try {
      const notifications = await api.getNotifications(null, 50);
      setUnreadCount(notifications.filter(n => !n.isRead).length);
    } catch (error) {
      console.error('Failed to load unread count:', error);
    }
  };

  const handleSearchResultSelect = (type, id) => {
    console.log('Selected:', type, id);
  };

  return (
    <>
      <header className="bg-white border-b border-gray-200 shadow-sm">
        <div className="p-4 md:p-6">
          <div className="flex items-center justify-between mb-4 md:mb-6">
            <div className="flex items-center space-x-3">
              <button 
                onClick={onMenuToggle}
                className="lg:hidden text-gray-600 hover:text-gray-900"
              >
                <Menu size={24} />
              </button>
              <div>
                <h2 className="text-xl md:text-2xl font-bold text-gray-900">Dashboard Overview</h2>
                <p className="text-xs md:text-sm text-gray-500 mt-1 hidden sm:block">Real-time monitoring and management</p>
              </div>
            </div>
            <div className="flex items-center space-x-2 md:space-x-4">
              <div className="relative hidden md:block">
                <Search size={18} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
                <input
                  type="text"
                  placeholder="Search..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  onFocus={() => setShowSearch(true)}
                  className="pl-10 pr-4 py-2.5 w-64 xl:w-80 rounded-lg border border-gray-300 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent text-sm"
                />
              </div>
              <Button 
                variant="outline" 
                size="sm" 
                icon={<RefreshCw size={16} />} 
                onClick={onRefresh}
                className="hidden sm:flex"
              >
                Refresh
              </Button>
              <button 
                className="relative p-2 text-gray-500 hover:text-gray-700 hover:bg-gray-100 rounded-lg transition-colors"
                onClick={() => setShowNotifications(true)}
              >
                <Bell size={20} />
                {unreadCount > 0 && (
                  <span className="absolute top-1 right-1 w-5 h-5 bg-red-500 rounded-full text-white text-xs flex items-center justify-center">
                    {unreadCount > 9 ? '9+' : unreadCount}
                  </span>
                )}
              </button>
              <div className="hidden sm:flex items-center space-x-2 px-3 py-2 bg-gray-50 rounded-lg">
                <span className={`w-3 h-3 rounded-full ${stats?.backendHealth === 'Healthy' ? 'bg-green-500 animate-pulse' : 'bg-red-500'}`}></span>
                <span className="text-sm font-medium text-gray-700">{stats?.backendHealth || 'Loading...'}</span>
              </div>
            </div>
          </div>
          
          {stats && (
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-2 md:gap-4">
              {[
                { label: 'Accounts', value: stats.totalAccounts, color: 'blue', icon: <Users size={20} /> },
                { label: 'Agents', value: `${stats.agentsOnline}/${stats.agentsTotal}`, color: 'green', icon: <Server size={20} /> },
                { label: 'Pools', value: stats.poolsCovered, color: 'purple', icon: <Database size={20} /> },
                { label: 'Savings', value: `${(stats.totalSavings / 1000).toFixed(1)}k`, color: 'emerald', icon: <DollarSign size={20} /> },
                { label: 'Switches', value: stats.totalSwitches, color: 'orange', icon: <RefreshCw size={20} /> },
                { label: 'Auto/Manual', value: `${stats.modelSwitches}/${stats.manualSwitches}`, color: 'cyan', icon: <Activity size={20} /> },
              ].map((stat, idx) => (
                <div key={idx} className={`bg-gradient-to-br from-${stat.color}-50 to-${stat.color}-100 p-3 md:p-4 rounded-xl border border-${stat.color}-200`}>
                  <div className="flex items-center justify-between">
                    <div className="flex-1 min-w-0">
                      <p className={`text-xs text-${stat.color}-600 font-semibold uppercase truncate`}>{stat.label}</p>
                      <p className={`text-lg md:text-2xl font-bold text-${stat.color}-900 mt-1 truncate`}>{stat.value}</p>
                    </div>
                    <div className={`text-${stat.color}-600 flex-shrink-0 ml-2`}>{stat.icon}</div>
                  </div>
                </div>
              ))}
            </div>
          )}
          
          {lastRefresh && (
            <p className="text-xs text-gray-400 mt-4">Last updated: {new Date(lastRefresh).toLocaleTimeString()}</p>
          )}
        </div>
      </header>

      <SearchResultsPanel
        isOpen={showSearch}
        onClose={() => setShowSearch(false)}
        query={searchQuery}
        onSelectResult={handleSearchResultSelect}
      />

      <NotificationPanel
        isOpen={showNotifications}
        onClose={() => {
          setShowNotifications(false);
          loadUnreadCount();
        }}
      />
    </>
  );
};
// ==============================================================================
// INSTANCE DETAIL PANEL WITH MANUAL CONTROLS
// ==============================================================================

const InstanceDetailPanel = ({ instanceId, clientId, onClose }) => {
  const [pricing, setPricing] = useState(null);
  const [metrics, setMetrics] = useState(null);
  const [priceHistory, setPriceHistory] = useState([]);
  const [loading, setLoading] = useState(true);
  const [switching, setSwitching] = useState(null);
  const [error, setError] = useState(null);
  const [showFallback, setShowFallback] = useState(false);

  useEffect(() => {
    const loadData = async () => {
      setLoading(true);
      setError(null);
      try {
        const [pricingData, metricsData] = await Promise.all([
          api.getInstancePricing(instanceId),
          api.getInstanceMetrics(instanceId)
        ]);
        setPricing(pricingData);
        setMetrics(metricsData);
        
        try {
          const historyData = await api.getPriceHistory(instanceId, 7, 'hour');
          setPriceHistory(historyData);
        } catch (histError) {
          console.warn('Price history not available:', histError);
          setPriceHistory([]);
        }
      } catch (err) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    };
    loadData();
  }, [instanceId]);

  const handleForceSwitch = async (body) => {
    const target = body.target === 'ondemand' ? 'On-Demand' : `Pool ${body.pool_id}`;
    
    if (!window.confirm(`Force switch to ${target}?\n\nThis will queue a command for the agent to execute on its next check cycle.`)) {
      return;
    }

    setSwitching(body.target === 'ondemand' ? 'ondemand' : body.pool_id);
    try {
      await api.forceSwitch(instanceId, body);
      alert(`✓ Switch command queued successfully!\n\nTarget: ${target}\n\nThe agent will execute this switch within ~1 minute.`);
      if (onClose) onClose();
    } catch (err) {
      alert(`✗ Failed to queue switch: ${err.message}\n\nPlease ensure the agent is online and try again.`);
    } finally {
      setSwitching(null);
    }
  };

  if (loading) {
    return (
      <tr className="bg-gray-50">
        <td colSpan="10" className="p-8">
          <div className="flex justify-center"><LoadingSpinner /></div>
        </td>
      </tr>
    );
  }

  if (error) {
    return (
      <tr className="bg-red-50">
        <td colSpan="10" className="p-6">
          <ErrorMessage message={error} />
        </td>
      </tr>
    );
  }

  return (
    <tr className="bg-gray-50">
      <td colSpan="10" className="p-4 md:p-6">
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 md:gap-6">
          {/* Metrics Column */}
          <div className="space-y-4">
            <div className="flex items-center justify-between mb-2">
              <h4 className="text-md font-bold text-gray-900">Instance Metrics</h4>
              <button onClick={onClose} className="text-gray-400 hover:text-gray-600">
                <X size={18} />
              </button>
            </div>
            {metrics && (
              <div className="space-y-3">
                <div className="bg-white p-4 rounded-lg border border-gray-200">
                  <div className="flex items-center justify-between mb-1">
                    <p className="text-xs text-gray-500">Uptime</p>
                    <Clock size={14} className="text-gray-400" />
                  </div>
                  <p className="text-2xl font-bold text-gray-900">{metrics.uptimeHours}h</p>
                </div>
                
                <div className="bg-white p-4 rounded-lg border border-gray-200">
                  <p className="text-xs text-gray-500 mb-1">Total Switches</p>
                  <p className="text-2xl font-bold text-gray-900">{metrics.totalSwitches}</p>
                  <p className="text-xs text-gray-500 mt-1">
                    {metrics.switchesLast7Days} in last 7 days
                  </p>
                </div>
                
                <div className="bg-white p-4 rounded-lg border-2 border-green-200 bg-green-50">
                  <p className="text-xs text-green-600 font-semibold mb-1">Total Savings</p>
                  <p className="text-2xl font-bold text-green-700">
                    ${metrics.totalSavings.toFixed(2)}
                  </p>
                  <p className="text-xs text-green-600 mt-1">
                    ${(metrics.savingsLast30Days || 0).toFixed(2)} last 30 days
                  </p>
                </div>
                
                <div className="bg-white p-4 rounded-lg border border-gray-200">
                  <p className="text-xs text-gray-500 mb-1">Current Prices</p>
                  <div className="space-y-2 mt-2">
                    <div className="flex justify-between text-sm">
                      <span className="text-gray-600">Spot:</span>
                      <span className="font-bold text-gray-900">${metrics.spotPrice.toFixed(4)}</span>
                    </div>
                    <div className="flex justify-between text-sm">
                      <span className="text-gray-600">On-Demand:</span>
                      <span className="font-bold text-gray-900">${metrics.onDemandPrice.toFixed(4)}</span>
                    </div>
                  </div>
                </div>
              </div>
            )}
          </div>
          
          {/* Available Options Column */}
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <h4 className="text-md font-bold text-gray-900">Available Options</h4>
              <button
                onClick={() => setShowFallback(!showFallback)}
                className="text-xs text-blue-600 hover:text-blue-800 font-medium"
              >
                {showFallback ? 'Hide' : 'Show'} Fallback
              </button>
            </div>
            {pricing && (
              <>
                {showFallback && (
                  <div className="bg-white p-4 rounded-lg border-2 border-red-200 shadow-sm">
                    <div className="flex justify-between items-center mb-3">
                      <div>
                        <p className="text-sm font-semibold text-red-700">On-Demand (Fallback)</p>
                        <p className="text-2xl font-bold text-gray-900 mt-1">
                          ${pricing.onDemand.price.toFixed(4)}
                        </p>
                        <p className="text-xs text-gray-500 mt-1">Guaranteed availability</p>
                      </div>
                      <Button
                        variant="danger"
                        size="sm"
                        onClick={() => handleForceSwitch({ target: 'ondemand' })}
                        loading={switching === 'ondemand'}
                      >
                        Switch
                      </Button>
                    </div>
                  </div>
                )}
                
                <div className="space-y-2 max-h-96 overflow-y-auto pr-1">
                  <p className="text-xs font-semibold text-gray-600 uppercase mb-2">
                    Spot Pools ({pricing.pools.length})
                  </p>
                  {pricing.pools.map((pool, idx) => (
                    <div 
                      key={pool.id} 
                      className={`bg-white p-4 rounded-lg border-2 transition-all ${
                        idx === 0 
                          ? 'border-blue-300 shadow-md' 
                          : 'border-gray-200 hover:border-blue-200'
                      }`}
                    >
                      <div className="flex justify-between items-center">
                        <div className="flex-1 min-w-0">
                          {idx === 0 && (
                            <Badge variant="success" className="mb-2">Best Price</Badge>
                          )}
                          <p className="text-xs font-mono text-blue-600 mb-1 truncate">
                            {pool.id}
                          </p>
                          <p className="text-xl font-bold text-gray-900">
                            ${pool.price.toFixed(4)}
                          </p>
                          <div className="flex items-center space-x-2 mt-1">
                            <p className="text-xs font-semibold text-green-600">
                              {pool.savings.toFixed(1)}% savings
                            </p>
                            <p className="text-xs text-gray-500">
                              ${(pricing.onDemand.price - pool.price).toFixed(4)}/hr
                            </p>
                          </div>
                        </div>
                        <Button
                          variant={idx === 0 ? 'success' : 'primary'}
                          size="sm"
                          onClick={() => handleForceSwitch({ target: 'pool', pool_id: pool.id })}
                          loading={switching === pool.id}
                        >
                          Switch
                        </Button>
                      </div>
                    </div>
                  ))}
                </div>
              </>
            )}
          </div>
          
          {/* Price History Chart Column */}
          <div className="bg-white p-4 rounded-lg border border-gray-200">
            <h4 className="text-md font-bold text-gray-900 mb-4">
              Price History (7 Days)
            </h4>
            {priceHistory.length > 0 ? (
              <ResponsiveContainer width="100%" height={350}>
                <LineChart data={priceHistory}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis 
                    dataKey="time" 
                    tick={{ fontSize: 10 }}
                    angle={-45}
                    textAnchor="end"
                    height={80}
                  />
                  <YAxis tick={{ fontSize: 10 }} />
                  <Tooltip />
                  <Legend />
                  <Line 
                    type="monotone" 
                    dataKey="avgPrice" 
                    stroke="#3b82f6" 
                    strokeWidth={2} 
                    name="Avg Price" 
                    dot={false}
                  />
                  <Line 
                    type="monotone" 
                    dataKey="minPrice" 
                    stroke="#10b981" 
                    strokeWidth={1} 
                    strokeDasharray="3 3"
                    name="Min Price" 
                    dot={false}
                  />
                  <Line 
                    type="monotone" 
                    dataKey="maxPrice" 
                    stroke="#ef4444" 
                    strokeWidth={1} 
                    strokeDasharray="3 3"
                    name="Max Price" 
                    dot={false}
                  />
                </LineChart>
              </ResponsiveContainer>
            ) : (
              <EmptyState
                icon={<BarChart3 size={48} />}
                title="No Price History"
                description="Price history data is not available for this instance"
              />
            )}
          </div>
        </div>
      </td>
    </tr>
  );
};

// ==============================================================================
// AGENT CONFIG MODAL
// ==============================================================================

const AgentConfigModal = ({ agent, onClose, onSave }) => {
  const [config, setConfig] = useState({
    min_savings_percent: 15,
    risk_threshold: 0.3,
    max_switches_per_week: 10,
    min_pool_duration_hours: 2,
  });
  const [saving, setSaving] = useState(false);

  const handleSave = async () => {
    setSaving(true);
    try {
      await api.updateAgentConfig(agent.id, config);
      onSave();
      onClose();
    } catch (error) {
      alert('Failed to save configuration: ' + error.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-xl shadow-2xl w-full max-w-2xl max-h-[90vh] overflow-y-auto">
        <div className="p-6 border-b border-gray-200 sticky top-0 bg-white">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="text-xl font-bold text-gray-900">Agent Configuration</h3>
              <p className="text-sm text-gray-500 mt-1 font-mono break-all">{agent.id}</p>
            </div>
            <button onClick={onClose} className="text-gray-400 hover:text-gray-600 transition-colors">
              <X size={24} />
            </button>
          </div>
        </div>
        
        <div className="p-6 space-y-6">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Minimum Savings Percentage
            </label>
            <input
              type="number"
              value={config.min_savings_percent}
              onChange={(e) => setConfig({...config, min_savings_percent: parseFloat(e.target.value)})}
              className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              min="0"
              max="100"
              step="0.1"
            />
            <p className="text-xs text-gray-500 mt-1">Only switch if savings exceed this percentage</p>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Risk Threshold
            </label>
            <input
              type="number"
              value={config.risk_threshold}
              onChange={(e) => setConfig({...config, risk_threshold: parseFloat(e.target.value)})}
              className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              min="0"
              max="1"
              step="0.01"
            />
            <p className="text-xs text-gray-500 mt-1">Maximum acceptable risk score (0-1)</p>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Max Switches Per Week
            </label>
            <input
              type="number"
              value={config.max_switches_per_week}
              onChange={(e) => setConfig({...config, max_switches_per_week: parseInt(e.target.value)})}
              className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              min="1"
              max="50"
            />
            <p className="text-xs text-gray-500 mt-1">Prevent excessive switching</p>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Min Pool Duration (hours)
            </label>
            <input
              type="number"
              value={config.min_pool_duration_hours}
              onChange={(e) => setConfig({...config, min_pool_duration_hours: parseInt(e.target.value)})}
              className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              min="1"
              max="24"
            />
            <p className="text-xs text-gray-500 mt-1">Minimum time before considering another switch</p>
          </div>
        </div>
        
        <div className="p-6 border-t border-gray-200 flex justify-end space-x-3 sticky bottom-0 bg-white">
          <Button variant="outline" onClick={onClose} disabled={saving}>
            Cancel
          </Button>
          <Button variant="primary" onClick={handleSave} loading={saving} icon={<Save size={16} />}>
            Save Configuration
          </Button>
        </div>
      </div>
    </div>
  );
};
// ==============================================================================
// CLIENT DETAIL TABS WITH ENHANCED CHARTS
// ==============================================================================

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

const ClientAgentsTab = ({ clientId }) => {
  const [agents, setAgents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedAgent, setSelectedAgent] = useState(null);
  const [showConfigModal, setShowConfigModal] = useState(false);
  const [error, setError] = useState(null);

  const loadAgents = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.getAgents(clientId);
      setAgents(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [clientId]);

  useEffect(() => {
    loadAgents();
  }, [loadAgents]);

  const handleToggle = async (agentId, currentEnabled) => {
    try {
      await api.toggleAgent(agentId, !currentEnabled);
      await loadAgents();
    } catch (error) {
      alert('Failed to toggle agent: ' + error.message);
    }
  };

  const handleSettingToggle = async (agentId, setting, currentValue) => {
    try {
      await api.updateAgentSettings(agentId, { [setting]: !currentValue });
      
      setAgents(prev => prev.map(agent => 
        agent.id === agentId 
          ? { ...agent, [setting]: !currentValue }
          : agent
      ));
    } catch (error) {
      alert('Failed to update settings: ' + error.message);
      await loadAgents();
    }
  };

  const openConfigModal = (agent) => {
    setSelectedAgent(agent);
    setShowConfigModal(true);
  };

  if (loading) {
    return <div className="flex justify-center items-center h-64"><LoadingSpinner /></div>;
  }

  if (error) {
    return <ErrorMessage message={error} onRetry={loadAgents} />;
  }

  return (
    <>
      <div className="bg-white p-4 md:p-6 rounded-xl shadow-sm border border-gray-200">
        <div className="flex items-center justify-between mb-6">
          <h3 className="text-lg font-bold text-gray-900">Agents Management</h3>
          <Badge variant="info">{agents.length} Total</Badge>
        </div>
        
        {agents.length === 0 ? (
          <EmptyState
            icon={<Server size={48} />}
            title="No Agents Found"
            description="No agents are registered for this client"
          />
        ) : (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {agents.map(agent => (
              <div key={agent.id} className="border border-gray-200 rounded-lg p-5 hover:shadow-md transition-all">
                <div className="flex items-start justify-between mb-4">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center space-x-3 mb-2">
                      <h4 className="font-mono text-sm font-bold text-gray-900 truncate">{agent.id}</h4>
                      {agent.status === 'online' ? (
                        <CheckCircle size={18} className="text-green-500 flex-shrink-0" />
                      ) : (
                        <XCircle size={18} className="text-red-500 flex-shrink-0" />
                      )}
                    </div>
                    <p className="text-xs text-gray-500">
                      Last heartbeat: {agent.lastHeartbeat ? new Date(agent.lastHeartbeat).toLocaleString() : 'Never'}
                    </p>
                    <p className="text-xs text-gray-500 mt-1">
                      Managing {agent.instanceCount} instance{agent.instanceCount !== 1 ? 's' : ''}
                    </p>
                  </div>
                  <Badge variant={agent.enabled ? 'success' : 'danger'}>
                    {agent.enabled ? 'Enabled' : 'Disabled'}
                  </Badge>
                </div>
                
                <div className="space-y-3 mb-4">
                  <div className="flex items-center justify-between p-3 bg-gray-50 rounded-lg">
                    <span className="text-sm font-medium text-gray-700">Auto Switch</span>
                    <ToggleSwitch
                      enabled={agent.auto_switch_enabled}
                      onChange={() => handleSettingToggle(agent.id, 'auto_switch_enabled', agent.auto_switch_enabled)}
                      label="Auto Switch"
                    />
                  </div>
                  
                  <div className="flex items-center justify-between p-3 bg-gray-50 rounded-lg">
                    <span className="text-sm font-medium text-gray-700">Auto Terminate</span>
                    <ToggleSwitch
                      enabled={agent.auto_terminate_enabled}
                      onChange={() => handleSettingToggle(agent.id, 'auto_terminate_enabled', agent.auto_terminate_enabled)}
                      label="Auto Terminate"
                    />
                  </div>
                </div>
                
                <div className="flex space-x-2">
                  <Button
                    variant={agent.enabled ? 'danger' : 'success'}
                    size="sm"
                    onClick={() => handleToggle(agent.id, agent.enabled)}
                    icon={agent.enabled ? <PowerOff size={14} /> : <Power size={14} />}
                    className="flex-1"
                  >
                    {agent.enabled ? 'Disable' : 'Enable'}
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => openConfigModal(agent)}
                    icon={<Settings size={14} />}
                  >
                    Configure
                  </Button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
      
      {showConfigModal && selectedAgent && (
        <AgentConfigModal
          agent={selectedAgent}
          onClose={() => setShowConfigModal(false)}
          onSave={loadAgents}
        />
      )}
    </>
  );
};

const ClientInstancesTab = ({ clientId }) => {
  const [instances, setInstances] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedInstanceId, setSelectedInstanceId] = useState(null);
  const [filters, setFilters] = useState({ status: 'all', mode: 'all', search: '' });
  const [error, setError] = useState(null);

  const loadInstances = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.getInstances(clientId, filters);
      setInstances(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [clientId, filters]);

  useEffect(() => {
    loadInstances();
  }, [loadInstances]);

  const toggleInstanceDetail = (instanceId) => {
    setSelectedInstanceId(prevId => prevId === instanceId ? null : instanceId);
  };

  if (error) {
    return <ErrorMessage message={error} onRetry={loadInstances} />;
  }

  return (
    <div className="space-y-4">
      {/* Filters */}
      <div className="bg-white p-4 rounded-xl shadow-sm border border-gray-200">
        <div className="flex flex-col sm:flex-row sm:flex-wrap items-stretch sm:items-center gap-4">
          <select
            value={filters.status}
            onChange={(e) => setFilters({...filters, status: e.target.value})}
            className="px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent text-sm"
          >
            <option value="all">All Status</option>
            <option value="active">Active</option>
            <option value="terminated">Terminated</option>
          </select>
          
          <select
            value={filters.mode}
            onChange={(e) => setFilters({...filters, mode: e.target.value})}
            className="px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent text-sm"
          >
            <option value="all">All Modes</option>
            <option value="spot">Spot</option>
            <option value="ondemand">On-Demand</option>
          </select>
          
          <div className="relative flex-1 min-w-[200px]">
            <Search size={18} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
            <input
              type="text"
              placeholder="Search instances..."
              value={filters.search}
              onChange={(e) => setFilters({...filters, search: e.target.value})}
              className="w-full pl-10 pr-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent text-sm"
            />
          </div>
          
          <Button variant="outline" size="sm" icon={<RefreshCw size={16} />} onClick={loadInstances}>
            Refresh
          </Button>
        </div>
      </div>
      
      {/* Instances Table */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="min-w-full">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>
                <th className="py-3 px-4 text-left text-xs font-semibold text-gray-600 uppercase w-10"></th>
                <th className="py-3 px-4 text-left text-xs font-semibold text-gray-600 uppercase">Instance ID</th>
                <th className="py-3 px-4 text-left text-xs font-semibold text-gray-600 uppercase">Type</th>
                <th className="py-3 px-4 text-left text-xs font-semibold text-gray-600 uppercase">AZ</th>
                <th className="py-3 px-4 text-left text-xs font-semibold text-gray-600 uppercase">Mode</th>
                <th className="py-3 px-4 text-left text-xs font-semibold text-gray-600 uppercase">Pool</th>
                <th className="py-3 px-4 text-left text-xs font-semibold text-gray-600 uppercase">Current Price</th>
                <th className="py-3 px-4 text-left text-xs font-semibold text-gray-600 uppercase">Savings</th>
                <th className="py-3 px-4 text-left text-xs font-semibold text-gray-600 uppercase">Last Switch</th>
                <th className="py-3 px-4 text-left text-xs font-semibold text-gray-600 uppercase">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {loading ? (
                <tr>
                  <td colSpan="10" className="text-center py-8">
                    <LoadingSpinner />
                  </td>
                </tr>
              ) : instances.length === 0 ? (
                <tr>
                  <td colSpan="10" className="text-center py-8">
                    <EmptyState
                      icon={<Zap size={48} />}
                      title="No Instances Found"
                      description="No instances match your filter criteria"
                    />
                  </td>
                </tr>
              ) : (
                instances.map(inst => (
                  <React.Fragment key={inst.id}>
                    <tr className="hover:bg-gray-50 transition-colors">
                      <td className="py-4 px-4">
                        <button onClick={() => toggleInstanceDetail(inst.id)}>
                          {selectedInstanceId === inst.id ? (
                            <ChevronDown size={18} className="text-gray-400" />
                          ) : (
                            <ChevronRight size={18} className="text-gray-400" />
                          )}
                        </button>
                      </td>
                      <td className="py-4 px-4">
                        <span className="text-sm font-mono text-gray-700">{inst.id}</span>
                      </td>
                      <td className="py-4 px-4 text-sm text-gray-700">{inst.type}</td>
                      <td className="py-4 px-4 text-sm text-gray-500">{inst.az}</td>
                      <td className="py-4 px-4">
                        <Badge variant={inst.mode === 'ondemand' ? 'danger' : 'success'}>
                          {inst.mode}
                        </Badge>
                      </td>
                      <td className="py-4 px-4 text-sm font-mono text-gray-500">{inst.poolId}</td>
                      <td className="py-4 px-4 text-sm font-semibold text-gray-900">
                        ${inst.spotPrice.toFixed(4)}
                      </td>
                      <td className="py-4 px-4 text-sm font-bold text-green-600">
                        {(((inst.onDemandPrice - inst.spotPrice) / inst.onDemandPrice) * 100).toFixed(1)}%
                      </td>
                      <td className="py-4 px-4 text-sm text-gray-500">
                        {inst.lastSwitch ? new Date(inst.lastSwitch).toLocaleString() : 'Never'}
                      </td>
                      <td className="py-4 px-4">
                        <button
                          onClick={() => toggleInstanceDetail(inst.id)}
                          className="text-blue-600 hover:text-blue-800 text-sm font-medium"
                        >
                          {selectedInstanceId === inst.id ? 'Hide' : 'Manage'}
                        </button>
                      </td>
                    </tr>
                    {selectedInstanceId === inst.id && (
                      <InstanceDetailPanel 
                        instanceId={inst.id} 
                        clientId={clientId}
                        onClose={() => setSelectedInstanceId(null)}
                      />
                    )}
                  </React.Fragment>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};
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

const ClientHistoryTab = ({ clientId }) => {
  const [history, setHistory] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    const loadHistory = async () => {
      setLoading(true);
      setError(null);
      try {
        const data = await api.getSwitchHistory(clientId);
        setHistory(data);
      } catch (err) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    };
    loadHistory();
  }, [clientId]);

  if (loading) {
    return <div className="flex justify-center items-center h-64"><LoadingSpinner /></div>;
  }

  if (error) {
    return <ErrorMessage message={error} />;
  }

  return (
    <div className="bg-white p-4 md:p-6 rounded-xl shadow-sm border border-gray-200">
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between mb-6 gap-4">
        <h3 className="text-lg font-bold text-gray-900">Complete Switch History</h3>
        <div className="flex flex-wrap gap-2">
          <Button 
            variant="outline" 
            size="sm" 
            icon={<Download size={16} />}
            onClick={() => api.exportSwitchHistory(clientId)}
          >
            Export CSV
          </Button>
          <Badge variant="info">{history.length} Total</Badge>
        </div>
      </div>
      
      {history.length === 0 ? (
        <EmptyState
          icon={<History size={48} />}
          title="No Switch History"
          description="No switches have been performed yet"
        />
      ) : (
        <div className="overflow-x-auto">
          <table className="min-w-full">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>
                <th className="text-left py-3 px-4 text-xs font-semibold text-gray-600 uppercase">Time</th>
                <th className="text-left py-3 px-4 text-xs font-semibold text-gray-600 uppercase">Instance</th>
                <th className="text-left py-3 px-4 text-xs font-semibold text-gray-600 uppercase">From → To</th>
                <th className="text-left py-3 px-4 text-xs font-semibold text-gray-600 uppercase">Pools</th>
                <th className="text-left py-3 px-4 text-xs font-semibold text-gray-600 uppercase">Trigger</th>
                <th className="text-left py-3 px-4 text-xs font-semibold text-gray-600 uppercase">Price</th>
                <th className="text-left py-3 px-4 text-xs font-semibold text-gray-600 uppercase">Impact</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {history.map(sw => (
                <tr key={sw.id} className="hover:bg-gray-50">
                  <td className="py-3 px-4 text-sm text-gray-600">
                    {new Date(sw.timestamp).toLocaleString()}
                  </td>
                  <td className="py-3 px-4 text-sm font-mono text-gray-500">
                    {sw.instanceId}
                  </td>
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
                  <td className="py-3 px-4 text-xs font-mono text-gray-500">
                    <div>{sw.fromPool}</div>
                    <div className="text-gray-400">→ {sw.toPool}</div>
                  </td>
                  <td className="py-3 px-4">
                    <Badge variant={sw.trigger === 'manual' ? 'warning' : 'info'}>
                      {sw.trigger}
                    </Badge>
                  </td>
                  <td className="py-3 px-4 text-sm font-semibold text-gray-900">
                    ${sw.price.toFixed(4)}
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
  );
};

// ==============================================================================
// CLIENT DETAIL VIEW
// ==============================================================================

const ClientDetailView = ({ clientId, onBack }) => {
  const [activeTab, setActiveTab] = useState('overview');
  const [client, setClient] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const loadClient = async () => {
      setLoading(true);
      try {
        const data = await api.getClientDetails(clientId);
        setClient(data);
      } catch (error) {
        console.error('Failed to load client:', error);
      } finally {
        setLoading(false);
      }
    };
    loadClient();
  }, [clientId]);

  const tabs = [
    { id: 'overview', label: 'Overview', icon: <LayoutDashboard size={16} /> },
    { id: 'agents', label: 'Agents', icon: <Server size={16} /> },
    { id: 'instances', label: 'Instances', icon: <Zap size={16} /> },
    { id: 'savings', label: 'Savings', icon: <BarChart3 size={16} /> },
    { id: 'history', label: 'History', icon: <History size={16} /> },
  ];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="bg-white p-4 md:p-6 rounded-xl shadow-sm border border-gray-200">
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
          <div className="flex items-center space-x-4">
            <Button variant="outline" size="sm" onClick={onBack} icon={<ChevronLeft size={16} />}>
              Back
            </Button>
            <div>
              <h2 className="text-xl md:text-2xl font-bold text-gray-900">
                {loading ? 'Loading...' : client?.name}
              </h2>
              <p className="text-sm text-gray-500 mt-1 font-mono break-all">{clientId}</p>
            </div>
          </div>
          {client && (
            <div className="flex items-center space-x-4">
              <div className="text-right">
                <p className="text-sm text-gray-500">Total Savings</p>
                <p className="text-xl md:text-2xl font-bold text-green-600">
                  ${(client.totalSavings / 1000).toFixed(1)}k
                </p>
              </div>
              <Badge variant={client.status === 'active' ? 'success' : 'danger'}>
                {client.status}
              </Badge>
            </div>
          )}
        </div>
        
        {/* Tabs */}
        <div className="flex space-x-2 mt-6 border-b border-gray-200 overflow-x-auto">
          {tabs.map(tab => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`flex items-center space-x-2 px-4 py-3 text-sm font-medium transition-all border-b-2 whitespace-nowrap ${
                activeTab === tab.id
                  ? 'border-blue-600 text-blue-600'
                  : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
              }`}
            >
              {tab.icon}
              <span>{tab.label}</span>
            </button>
          ))}
        </div>
      </div>
      
      {/* Tab Content */}
      <div>
        {activeTab === 'overview' && <ClientOverviewTab clientId={clientId} />}
        {activeTab === 'agents' && <ClientAgentsTab clientId={clientId} />}
        {activeTab === 'instances' && <ClientInstancesTab clientId={clientId} />}
        {activeTab === 'savings' && <ClientSavingsTab clientId={clientId} />}
        {activeTab === 'history' && <ClientHistoryTab clientId={clientId} />}
      </div>
    </div>
  );
};
// ==============================================================================
// ADMIN PAGES
// ==============================================================================

const AdminOverview = () => {
  const [activity, setActivity] = useState([]);
  const [stats, setStats] = useState(null);
  const [clients, setClients] = useState([]);
  const [loading, setLoading] = useState(true);
  
  useEffect(() => {
    const loadData = async () => {
      setLoading(true);
      try {
        const [activityData, statsData, clientsData] = await Promise.all([
          api.getRecentActivity(),
          api.getGlobalStats(),
          api.getAllClients()
        ]);
        setActivity(activityData);
        setStats(statsData);
        setClients(clientsData);
      } catch (error) {
        console.error('Failed to load overview data:', error);
      } finally {
        setLoading(false);
      }
    };
    loadData();
    
    const interval = setInterval(loadData, 30000);
    return () => clearInterval(interval);
  }, []);

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

// ==============================================================================
// UPDATED: ALL CLIENTS PAGE WITH ADD CLIENT FEATURE
// ==============================================================================

const AllClientsPage = ({ onSelectClient }) => {
  const [clients, setClients] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [showAddModal, setShowAddModal] = useState(false);
  const [showTokenModal, setShowTokenModal] = useState(false);
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [selectedClient, setSelectedClient] = useState(null);

  const loadClients = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.getAllClients();
      setClients(data);
    } catch (error) {
      console.error('Failed to load clients:', error);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadClients();
  }, [loadClients]);

  const filteredClients = clients.filter(c => 
    c.name.toLowerCase().includes(search.toLowerCase()) ||
    c.id.toLowerCase().includes(search.toLowerCase())
  );

  const handleViewToken = (client, e) => {
    e.stopPropagation();
    setSelectedClient(client);
    setShowTokenModal(true);
  };

  const handleDeleteClient = (client, e) => {
    e.stopPropagation();
    setSelectedClient(client);
    setShowDeleteModal(true);
  };

  return (
    <>
      <div className="space-y-6">
        <div className="bg-white p-4 md:p-6 rounded-xl shadow-sm border border-gray-200">
          <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 mb-6">
            <div>
              <h3 className="text-lg font-bold text-gray-900">All Clients</h3>
              <p className="text-sm text-gray-500 mt-1">Manage client accounts and tokens</p>
            </div>
            <div className="flex flex-col sm:flex-row gap-3 w-full sm:w-auto">
              <div className="relative flex-1 sm:w-64">
                <Search size={18} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
                <input
                  type="text"
                  placeholder="Search clients..."
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  className="w-full pl-10 pr-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent text-sm"
                />
              </div>
              <Button
                variant="primary"
                size="md"
                icon={<Plus size={18} />}
                onClick={() => setShowAddModal(true)}
              >
                Add Client
              </Button>
            </div>
          </div>

          {loading ? (
            <div className="flex justify-center items-center h-64"><LoadingSpinner /></div>
          ) : filteredClients.length === 0 ? (
            <EmptyState
              icon={<Users size={48} />}
              title="No Clients Found"
              description={search ? `No clients match "${search}"` : 'Click "Add Client" to create your first client'}
            />
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {filteredClients.map(client => (
                <div 
                  key={client.id}
                  className="border border-gray-200 rounded-lg p-5 hover:shadow-lg transition-all cursor-pointer bg-gradient-to-br from-white to-gray-50 relative group"
                >
                  {/* Card Header with Actions */}
                  <div className="flex items-start justify-between mb-4">
                    <div 
                      className="flex-1 min-w-0 cursor-pointer"
                      onClick={() => onSelectClient(client.id)}
                    >
                      <h4 className="text-lg font-bold text-gray-900 truncate">{client.name}</h4>
                      <p className="text-xs text-gray-500 font-mono mt-1 break-all">{client.id}</p>
                    </div>
                    <div className="flex items-center space-x-1">
                      <Badge variant={client.status === 'active' ? 'success' : 'danger'}>
                        {client.status}
                      </Badge>
                    </div>
                  </div>

                  {/* Client Stats */}
                  <div 
                    className="grid grid-cols-2 gap-4 mb-4 cursor-pointer"
                    onClick={() => onSelectClient(client.id)}
                  >
                    <div>
                      <p className="text-xs text-gray-500">Instances</p>
                      <p className="text-xl font-bold text-gray-900">{client.instances}</p>
                    </div>
                    <div>
                      <p className="text-xs text-gray-500">Agents</p>
                      <p className="text-xl font-bold text-gray-900">
                        <span className="text-green-600">{client.agentsOnline}</span>
                        <span className="text-gray-400">/{client.agentsTotal}</span>
                      </p>
                    </div>
                  </div>

                  {/* Savings */}
                  <div 
                    className="pt-4 border-t border-gray-200 cursor-pointer"
                    onClick={() => onSelectClient(client.id)}
                  >
                    <p className="text-xs text-gray-500">Total Savings</p>
                    <p className="text-2xl font-bold text-green-600">${(client.totalSavings / 1000).toFixed(1)}k</p>
                  </div>

                  {/* Action Buttons - Always visible */}
                  <div className="mt-4 pt-4 border-t border-gray-200 flex space-x-2">
                    <Button
                      variant="outline"
                      size="sm"
                      icon={<Key size={14} />}
                      onClick={(e) => handleViewToken(client, e)}
                      className="flex-1"
                    >
                      Token
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      icon={<Eye size={14} />}
                      onClick={() => onSelectClient(client.id)}
                      className="flex-1"
                    >
                      View
                    </Button>
                    <Button
                      variant="danger"
                      size="sm"
                      icon={<Trash2 size={14} />}
                      onClick={(e) => handleDeleteClient(client, e)}
                    >
                      Delete
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Modals */}
      {showAddModal && (
        <AddClientModal
          onClose={() => setShowAddModal(false)}
          onSuccess={loadClients}
        />
      )}

      {showTokenModal && selectedClient && (
        <ViewTokenModal
          client={selectedClient}
          onClose={() => {
            setShowTokenModal(false);
            setSelectedClient(null);
          }}
          onRegenerate={loadClients}
        />
      )}

      {showDeleteModal && selectedClient && (
        <DeleteClientModal
          client={selectedClient}
          onClose={() => {
            setShowDeleteModal(false);
            setSelectedClient(null);
          }}
          onSuccess={loadClients}
        />
      )}
    </>
  );
};
const AllAgentsPage = () => {
  const [agents, setAgents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('all');

  useEffect(() => {
    const loadAgents = async () => {
      setLoading(true);
      try {
        const data = await api.getAllAgentsGlobal();
        setAgents(data);
      } catch (error) {
        console.error('Failed to load agents:', error);
      } finally {
        setLoading(false);
      }
    };
    loadAgents();
  }, []);

  const filteredAgents = agents.filter(a => {
    const matchesSearch = a.id.toLowerCase().includes(search.toLowerCase()) ||
                         (a.hostname && a.hostname.toLowerCase().includes(search.toLowerCase()));
    const matchesStatus = statusFilter === 'all' || a.status === statusFilter;
    return matchesSearch && matchesStatus;
  });

  return (
    <div className="space-y-6">
      <div className="bg-white p-4 md:p-6 rounded-xl shadow-sm border border-gray-200">
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 mb-6">
          <h3 className="text-lg font-bold text-gray-900">All Agents</h3>
          <div className="flex flex-col sm:flex-row gap-2 w-full sm:w-auto">
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              className="px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 text-sm"
            >
              <option value="all">All Status</option>
              <option value="online">Online</option>
              <option value="offline">Offline</option>
            </select>
            <div className="relative flex-1 sm:w-64">
              <Search size={18} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
              <input
                type="text"
                placeholder="Search agents..."
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="w-full pl-10 pr-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 text-sm"
              />
            </div>
          </div>
        </div>

        {loading ? (
          <div className="flex justify-center items-center h-64"><LoadingSpinner /></div>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full">
              <thead className="bg-gray-50 border-b border-gray-200">
                <tr>
                  <th className="text-left py-3 px-4 text-xs font-semibold text-gray-600 uppercase">Agent ID</th>
                  <th className="text-left py-3 px-4 text-xs font-semibold text-gray-600 uppercase">Client</th>
                  <th className="text-left py-3 px-4 text-xs font-semibold text-gray-600 uppercase">Status</th>
                  <th className="text-left py-3 px-4 text-xs font-semibold text-gray-600 uppercase">Hostname</th>
                  <th className="text-left py-3 px-4 text-xs font-semibold text-gray-600 uppercase">Instances</th>
                  <th className="text-left py-3 px-4 text-xs font-semibold text-gray-600 uppercase">Last Heartbeat</th>
                  <th className="text-left py-3 px-4 text-xs font-semibold text-gray-600 uppercase">Version</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {filteredAgents.map(agent => (
                  <tr key={agent.id} className="hover:bg-gray-50">
                    <td className="py-3 px-4 text-sm font-mono text-gray-700">{agent.id}</td>
                    <td className="py-3 px-4 text-sm text-gray-700">{agent.clientName}</td>
                    <td className="py-3 px-4">
                      <Badge variant={agent.status === 'online' ? 'success' : 'danger'}>
                        {agent.status}
                      </Badge>
                    </td>
                    <td className="py-3 px-4 text-sm text-gray-600">{agent.hostname || 'N/A'}</td>
                    <td className="py-3 px-4 text-sm text-gray-700">{agent.instanceCount || 0}</td>
                    <td className="py-3 px-4 text-sm text-gray-600">
                      {agent.lastHeartbeat ? new Date(agent.lastHeartbeat).toLocaleString() : 'Never'}
                    </td>
                    <td className="py-3 px-4 text-sm text-gray-600">{agent.agentVersion || 'N/A'}</td>
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

const AllInstancesPage = () => {
  const [instances, setInstances] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filters, setFilters] = useState({ status: 'all', mode: 'all', search: '' });

  useEffect(() => {
    const loadInstances = async () => {
      setLoading(true);
      try {
        const data = await api.getAllInstancesGlobal(filters);
        setInstances(data);
      } catch (error) {
        console.error('Failed to load instances:', error);
      } finally {
        setLoading(false);
      }
    };
    loadInstances();
  }, [filters]);

  return (
    <div className="space-y-6">
      <div className="bg-white p-4 rounded-xl shadow-sm border border-gray-200">
        <div className="flex flex-col sm:flex-row sm:flex-wrap items-stretch sm:items-center gap-4">
          <select
            value={filters.status}
            onChange={(e) => setFilters({...filters, status: e.target.value})}
            className="px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 text-sm"
          >
            <option value="all">All Status</option>
            <option value="active">Active</option>
            <option value="terminated">Terminated</option>
          </select>
          
          <select
            value={filters.mode}
            onChange={(e) => setFilters({...filters, mode: e.target.value})}
            className="px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 text-sm"
          >
            <option value="all">All Modes</option>
            <option value="spot">Spot</option>
            <option value="ondemand">On-Demand</option>
          </select>
          
          <div className="relative flex-1 min-w-[200px]">
            <Search size={18} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
            <input
              type="text"
              placeholder="Search instances..."
              value={filters.search}
              onChange={(e) => setFilters({...filters, search: e.target.value})}
              className="w-full pl-10 pr-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 text-sm"
            />
          </div>
        </div>
      </div>

      <div className="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="min-w-full">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>
                <th className="text-left py-3 px-4 text-xs font-semibold text-gray-600 uppercase">Instance ID</th>
                <th className="text-left py-3 px-4 text-xs font-semibold text-gray-600 uppercase">Client</th>
                <th className="text-left py-3 px-4 text-xs font-semibold text-gray-600 uppercase">Type</th>
                <th className="text-left py-3 px-4 text-xs font-semibold text-gray-600 uppercase">Region</th>
                <th className="text-left py-3 px-4 text-xs font-semibold text-gray-600 uppercase">Mode</th>
                <th className="text-left py-3 px-4 text-xs font-semibold text-gray-600 uppercase">Price</th>
                <th className="text-left py-3 px-4 text-xs font-semibold text-gray-600 uppercase">Savings</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {loading ? (
                <tr>
                  <td colSpan="7" className="text-center py-8">
                    <LoadingSpinner />
                  </td>
                </tr>
              ) : instances.length === 0 ? (
                <tr>
                  <td colSpan="7" className="text-center py-8">
                    <EmptyState
                      icon={<Zap size={48} />}
                      title="No Instances Found"
                      description="No instances match your filter criteria"
                    />
                  </td>
                </tr>
              ) : (
                instances.map(inst => (
                  <tr key={inst.id} className="hover:bg-gray-50">
                    <td className="py-3 px-4 text-sm font-mono text-gray-700">{inst.id}</td>
                    <td className="py-3 px-4 text-sm text-gray-700">{inst.clientName}</td>
                    <td className="py-3 px-4 text-sm text-gray-700">{inst.type}</td>
                    <td className="py-3 px-4 text-sm text-gray-600">{inst.region}</td>
                    <td className="py-3 px-4">
                      <Badge variant={inst.mode === 'ondemand' ? 'danger' : 'success'}>
                        {inst.mode}
                      </Badge>
                    </td>
                    <td className="py-3 px-4 text-sm font-semibold text-gray-900">
                      ${inst.spotPrice.toFixed(4)}
                    </td>
                    <td className="py-3 px-4 text-sm font-bold text-green-600">
                      {(((inst.onDemandPrice - inst.spotPrice) / inst.onDemandPrice) * 100).toFixed(1)}%
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};

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

const ActivityLogPage = () => {
  const [activity, setActivity] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const loadActivity = async () => {
      setLoading(true);
      try {
        const data = await api.getRecentActivity();
        setActivity(data);
      } catch (error) {
        console.error('Failed to load activity:', error);
      } finally {
        setLoading(false);
      }
    };
    loadActivity();
  }, []);

  const icons = {
    switch: <RefreshCw size={20} className="text-blue-500" />,
    agent: <Server size={20} className="text-green-500" />,
    event: <AlertCircle size={20} className="text-yellow-500" />,
  };

  return (
    <div className="bg-white p-4 md:p-6 rounded-xl shadow-sm border border-gray-200">
      <h3 className="text-lg font-bold text-gray-900 mb-6">System Activity Log</h3>
      {loading ? (
        <div className="flex justify-center items-center h-64"><LoadingSpinner /></div>
      ) : activity.length === 0 ? (
        <EmptyState
          icon={<History size={48} />}
          title="No Activity"
          description="No recent system activity"
        />
      ) : (
        <div className="space-y-3">
          {activity.map(item => (
            <div key={item.id} className="flex items-start space-x-4 p-4 bg-gray-50 rounded-lg hover:bg-gray-100 transition-colors">
              <span className="flex-shrink-0 w-12 h-12 flex items-center justify-center bg-white rounded-lg shadow-sm border border-gray-200">
                {icons[item.type] || <AlertCircle size={20} className="text-gray-500" />}
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
  );
};

const SystemHealthPage = () => {
  const [health, setHealth] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const loadHealth = async () => {
      setLoading(true);
      try {
        const data = await api.getSystemHealth();
        setHealth(data);
      } catch (error) {
        console.error('Failed to load health:', error);
      } finally {
        setLoading(false);
      }
    };
    loadHealth();
  }, []);

  if (loading) {
    return <div className="flex justify-center items-center h-64"><LoadingSpinner /></div>;
  }

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 md:gap-6">
        <StatCard 
          title="API Status" 
          value={health?.apiStatus || 'Unknown'}
          icon={<Activity size={24} />}
          subtitle="Response time: 45ms"
        />
        <StatCard 
          title="Database" 
          value={health?.database || 'Connected'}
          icon={<Database size={24} />}
          subtitle="Pool: 8/10 active"
        />
        <StatCard 
          title="Decision Engine" 
          value={health?.decisionEngine || 'Loaded'}
          icon={<Cpu size={24} />}
          subtitle="ML models ready"
        />
        <StatCard 
          title="Uptime" 
          value="99.9%"
          icon={<Clock size={24} />}
          subtitle="Last 30 days"
        />
      </div>

      <div className="bg-white p-4 md:p-6 rounded-xl shadow-sm border border-gray-200">
        <h3 className="text-lg font-bold text-gray-900 mb-6">System Components</h3>
        <div className="space-y-4">
          {[
            { name: 'Web Server', status: 'Healthy', uptime: '99.9%' },
            { name: 'Database Server', status: 'Healthy', uptime: '100%' },
            { name: 'Decision Engine', status: 'Healthy', uptime: '99.8%' },
            { name: 'Agent Communication', status: 'Healthy', uptime: '99.7%' },
            { name: 'Background Jobs', status: 'Healthy', uptime: '100%' },
          ].map((component, idx) => (
            <div key={idx} className="flex items-center justify-between p-4 bg-gray-50 rounded-lg">
              <div className="flex items-center space-x-4">
                <div className="w-3 h-3 bg-green-500 rounded-full animate-pulse"></div>
                <div>
                  <p className="text-sm font-medium text-gray-900">{component.name}</p>
                  <p className="text-xs text-gray-500">Uptime: {component.uptime}</p>
                </div>
              </div>
              <Badge variant="success">{component.status}</Badge>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};

// ==============================================================================
// MAIN APP COMPONENT
// ==============================================================================

const App = () => {
  const [activePage, setActivePage] = useState('overview');
  const [selectedClientId, setSelectedClientId] = useState(null);
  const [clients, setClients] = useState([]);
  const [stats, setStats] = useState(null);
  const [lastRefresh, setLastRefresh] = useState(null);
  const [sidebarOpen, setSidebarOpen] = useState(false);

  const loadData = useCallback(async () => {
    try {
      const [clientsData, statsData] = await Promise.all([
        api.getAllClients(),
        api.getGlobalStats()
      ]);
      setClients(clientsData);
      setStats(statsData);
      setLastRefresh(new Date().toISOString());
    } catch (error) {
      console.error('Failed to load data:', error);
    }
  }, []);

  useEffect(() => {
    loadData();
    const interval = setInterval(loadData, 60000);
    return () => clearInterval(interval);
  }, [loadData]);

  const handleSelectClient = (clientId) => {
    setSelectedClientId(clientId);
    setActivePage('client-detail');
    setSidebarOpen(false);
  };

  const handleBackToOverview = () => {
    setSelectedClientId(null);
    setActivePage('overview');
  };

  const handlePageChange = (page) => {
    setActivePage(page);
    setSelectedClientId(null);
  };

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Sidebar */}
      <AdminSidebar
        clients={clients}
        onSelectClient={handleSelectClient}
        activeClientId={selectedClientId}
        onSelectPage={handlePageChange}
        activePage={activePage}
        isOpen={sidebarOpen}
        onClose={() => setSidebarOpen(false)}
      />
      
      {/* Main Content Area */}
      <div className="lg:ml-72 min-h-screen">
        {/* Header */}
        <AdminHeader
          stats={stats}
          onRefresh={loadData}
          lastRefresh={lastRefresh}
          onMenuToggle={() => setSidebarOpen(true)}
        />
        
        {/* Page Content */}
        <main className="p-4 md:p-6">
          {activePage === 'overview' && <AdminOverview />}
          {activePage === 'clients' && <AllClientsPage onSelectClient={handleSelectClient} />}
          {activePage === 'agents' && <AllAgentsPage />}
          {activePage === 'instances' && <AllInstancesPage />}
          {activePage === 'savings' && <GlobalSavingsPage />}
          {activePage === 'activity' && <ActivityLogPage />}
          {activePage === 'health' && <SystemHealthPage />}
          {activePage === 'client-detail' && selectedClientId && (
            <ClientDetailView
              clientId={selectedClientId}
              onBack={handleBackToOverview}
            />
          )}
        </main>
      </div>
    </div>
  );
};

export default App;
