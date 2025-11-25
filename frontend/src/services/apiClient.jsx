// ==============================================================================
// COMPLETE API CLIENT - Synchronized with Backend (Latest)
// Repository: https://github.com/atharva0608/final-ml
// Last Sync: 2025-11-19
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

  // ==============================================================================
  // ADMIN APIs
  // ==============================================================================

  async getGlobalStats() {
    return this.request('/api/admin/stats');
  }

  async getAllClients() {
    return this.request('/api/admin/clients');
  }

  async getRecentActivity() {
    return this.request('/api/admin/activity');
  }

  async getSystemHealth() {
    return this.request('/api/admin/system-health');
  }

  // NEW: Client Growth Chart (Task 4)
  async getClientsGrowth(days = 30) {
    return this.request(`/api/admin/clients/growth?days=${days}`);
  }

  // NEW: Upload Decision Engine Files
  async uploadDecisionEngine(files) {
    const formData = new FormData();
    files.forEach(file => {
      formData.append('files', file);
    });

    try {
      const response = await fetch(`${this.baseUrl}/api/admin/decision-engine/upload`, {
        method: 'POST',
        body: formData,
        // Don't set Content-Type header - browser will set it with boundary
      });

      if (!response.ok) {
        const error = await response.json().catch(() => ({}));
        throw new Error(error.error || `Upload failed: ${response.status}`);
      }

      return await response.json();
    } catch (error) {
      console.error('Decision Engine upload failed:', error);
      throw error;
    }
  }

  // NEW: Upload ML Model Files
  async uploadMLModels(files) {
    const formData = new FormData();
    files.forEach(file => {
      formData.append('files', file);
    });

    try {
      const response = await fetch(`${this.baseUrl}/api/admin/ml-models/upload`, {
        method: 'POST',
        body: formData,
        // Don't set Content-Type header - browser will set it with boundary
      });

      if (!response.ok) {
        const error = await response.json().catch(() => ({}));
        throw new Error(error.error || `Upload failed: ${response.status}`);
      }

      return await response.json();
    } catch (error) {
      console.error('ML Models upload failed:', error);
      throw error;
    }
  }

  // NEW: Activate ML Models (RED RESTART button)
  async activateMLModels(sessionId) {
    return this.request('/api/admin/ml-models/activate', {
      method: 'POST',
      body: JSON.stringify({ sessionId }),
    });
  }

  // NEW: Fallback to Previous ML Models
  async fallbackMLModels() {
    return this.request('/api/admin/ml-models/fallback', {
      method: 'POST',
    });
  }

  // NEW: Get ML Model Sessions
  async getMLModelSessions() {
    return this.request('/api/admin/ml-models/sessions');
  }

  // NEW: Get All Instances (Admin Level)
  async getAllInstancesGlobal(filters = {}) {
    const params = new URLSearchParams(
      Object.entries(filters).filter(([_, v]) => v && v !== 'all')
    );
    const query = params.toString() ? `?${params}` : '';
    return this.request(`/api/admin/instances${query}`);
  }

  // NEW: Get All Agents (Admin Level)
  async getAllAgentsGlobal(filters = {}) {
    const params = new URLSearchParams(
      Object.entries(filters).filter(([_, v]) => v && v !== 'all')
    );
    const query = params.toString() ? `?${params}` : '';
    return this.request(`/api/admin/agents${query}`);
  }

  // ==============================================================================
  // CLIENT MANAGEMENT APIs
  // ==============================================================================

  async createClient(name, email = null) {
    const body = { name };
    if (email) body.email = email;
    return this.request('/api/admin/clients/create', {
      method: 'POST',
      body: JSON.stringify(body),
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

  // ==============================================================================
  // NOTIFICATION APIs
  // ==============================================================================

  async getNotifications(clientId = null, limit = 10) {
    const params = new URLSearchParams();
    if (clientId) params.append('client_id', clientId);
    params.append('limit', limit);
    return this.request(`/api/notifications?${params}`);
  }

  async markNotificationRead(notifId) {
    return this.request(`/api/notifications/${notifId}/mark-read`, {
      method: 'POST'
    });
  }

  async markAllNotificationsRead(clientId = null) {
    return this.request('/api/notifications/mark-all-read', {
      method: 'POST',
      body: JSON.stringify({ client_id: clientId }),
    });
  }

  // ==============================================================================
  // CLIENT APIs
  // ==============================================================================

  async getClientDetails(clientId) {
    return this.request(`/api/client/${clientId}`);
  }

  async getAgents(clientId) {
    return this.request(`/api/client/${clientId}/agents`);
  }

  async getClientChartData(clientId) {
    return this.request(`/api/client/${clientId}/stats/charts`);
  }

  async getInstances(clientId, filters = {}) {
    const params = new URLSearchParams(
      Object.entries(filters).filter(([_, v]) => v && v !== 'all')
    );
    const query = params.toString() ? `?${params}` : '';
    return this.request(`/api/client/${clientId}/instances${query}`);
  }

  async getSavings(clientId, range = 'monthly') {
    return this.request(`/api/client/${clientId}/savings?range=${range}`);
  }

  async getSwitchHistory(clientId, instanceId = null) {
    const query = instanceId ? `?instance_id=${instanceId}` : '';
    return this.request(`/api/client/${clientId}/switch-history${query}`);
  }

  // NEW: Agent Decisions (Task 7)
  async getAgentDecisions(clientId) {
    return this.request(`/api/client/${clientId}/agents/decisions`);
  }

  // ==============================================================================
  // AGENT APIs
  // ==============================================================================

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

  // UPDATED: Agent Config with Replica Settings and Auto-Terminate
  async updateAgentConfig(agentId, config) {
    return this.request(`/api/client/agents/${agentId}/config`, {
      method: 'POST',
      body: JSON.stringify({
        terminateWaitMinutes: config.terminateWaitMinutes,
        autoSwitchEnabled: config.autoSwitchEnabled,
        manualReplicaEnabled: config.manualReplicaEnabled,
        autoTerminateEnabled: config.autoTerminateEnabled,
      }),
    });
  }

  // NEW: Delete Agent
  async deleteAgent(agentId) {
    return this.request(`/api/client/agents/${agentId}`, {
      method: 'DELETE',
    });
  }

  // NEW: Get Agent History (including deleted agents)
  async getAgentHistory(clientId) {
    return this.request(`/api/client/${clientId}/agents/history`);
  }

  // ==============================================================================
  // REPLICA MANAGEMENT APIs
  // ==============================================================================

  async getClientReplicas(clientId) {
    return this.request(`/api/client/${clientId}/replicas`);
  }

  async getAgentReplicas(agentId) {
    return this.request(`/api/agents/${agentId}/replicas`);
  }

  async createReplica(agentId, options = {}) {
    return this.request(`/api/agents/${agentId}/replicas`, {
      method: 'POST',
      body: JSON.stringify(options),
    });
  }

  async promoteReplica(agentId, replicaId, options = {}) {
    return this.request(`/api/agents/${agentId}/replicas/${replicaId}/promote`, {
      method: 'POST',
      body: JSON.stringify(options),
    });
  }

  async deleteReplica(agentId, replicaId) {
    return this.request(`/api/agents/${agentId}/replicas/${replicaId}`, {
      method: 'DELETE',
    });
  }

  async updateReplicaSyncStatus(agentId, replicaId, status) {
    return this.request(`/api/agents/${agentId}/replicas/${replicaId}/sync-status`, {
      method: 'POST',
      body: JSON.stringify(status),
    });
  }

  // ==============================================================================
  // INSTANCE APIs
  // ==============================================================================

  async getInstancePricing(instanceId) {
    return this.request(`/api/client/instances/${instanceId}/pricing`);
  }

  async getInstanceMetrics(instanceId) {
    return this.request(`/api/client/instances/${instanceId}/metrics`);
  }

  // NEW: Get Available Options for Instance (Task 5)
  async getInstanceAvailableOptions(instanceId) {
    return this.request(`/api/client/instances/${instanceId}/available-options`);
  }

  // UPDATED: Force Switch with Pool/Type support (Task 5)
  async forceSwitch(instanceId, body) {
    return this.request(`/api/client/instances/${instanceId}/force-switch`, {
      method: 'POST',
      body: JSON.stringify(body),
    });
  }

  // ==============================================================================
  // HEALTH CHECK
  // ==============================================================================

  async healthCheck() {
    return this.request('/health');
  }

  // ==============================================================================
  // INSTANCE PRICE HISTORY
  // ==============================================================================

  async getPriceHistory(instanceId, days = 7, interval = 'hour') {
    return this.request(`/api/client/instances/${instanceId}/price-history?days=${days}&interval=${interval}`);
  }

  // ==============================================================================
  // LEGACY/MOCK METHODS - Kept for compatibility
  // ==============================================================================

  async globalSearch(query) {
    console.warn('globalSearch: Backend endpoint not implemented, returning mock data');
    return { clients: [], instances: [], agents: [] };
  }

  async getAgentStatistics(agentId) {
    console.warn('getAgentStatistics: Backend endpoint not implemented, returning mock data');
    return { totalDecisions: 0, successRate: 0 };
  }

  async getInstanceLogs(instanceId, limit = 50) {
    console.warn('getInstanceLogs: Backend endpoint not implemented, returning empty array');
    return [];
  }

  async exportSavings(clientId) {
    window.open(`${this.baseUrl}/api/client/${clientId}/export/savings`, '_blank');
  }

  async exportSwitchHistory(clientId) {
    window.open(`${this.baseUrl}/api/client/${clientId}/export/switch-history`, '_blank');
  }

  async exportGlobalStats() {
    window.open(`${this.baseUrl}/api/admin/export/global-stats`, '_blank');
  }

  async getPoolStatistics() {
    console.warn('getPoolStatistics: Backend endpoint not implemented, returning mock data');
    return { total: 0, active: 0, regions: [] };
  }

  async getAgentHealth() {
    console.warn('getAgentHealth: Backend endpoint not implemented, returning mock data');
    return { online: 0, offline: 0, total: 0 };
  }
}

export default APIClient;
