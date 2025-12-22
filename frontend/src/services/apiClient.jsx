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
  // SEARCH & STATISTICS APIs
  // ==============================================================================

  async globalSearch(query) {
    if (!query || query.trim().length < 2) {
      return { clients: [], instances: [], agents: [] };
    }
    return this.request(`/api/admin/search?q=${encodeURIComponent(query)}`);
  }

  async getAgentStatistics(agentId) {
    return this.request(`/api/agents/${agentId}/statistics`);
  }

  async getInstanceLogs(instanceId, limit = 100) {
    return this.request(`/api/client/instances/${instanceId}/logs`);
  }

  async getPoolStatistics() {
    return this.request('/api/admin/pools/statistics');
  }

  async getAgentHealthSummary() {
    return this.request('/api/admin/agents/health-summary');
  }

  // Deprecated: Use getAgentHealthSummary instead
  async getAgentHealth() {
    console.warn('getAgentHealth is deprecated, use getAgentHealthSummary instead');
    return this.getAgentHealthSummary();
  }

  // ==============================================================================
  // EXPORT APIs
  // ==============================================================================

  async exportSavings(clientId) {
    window.open(`${this.baseUrl}/api/client/${clientId}/export/savings`, '_blank');
  }

  async exportSwitchHistory(clientId) {
    window.open(`${this.baseUrl}/api/client/${clientId}/export/switch-history`, '_blank');
  }

  async exportGlobalStats() {
    window.open(`${this.baseUrl}/api/admin/export/global-stats`, '_blank');
  }

  // ==============================================================================
  // SYSTEM MONITOR & HEALTH APIs
  // ==============================================================================

  async getSystemOverview() {
    return this.request('/api/v1/admin/health/overview');
  }

  async getComponentLogs(component, limit = 50) {
    return this.request(`/api/v1/admin/logs/${component}?limit=${limit}`);
  }

  // ==============================================================================
  // GOVERNANCE APIs
  // ==============================================================================

  async getUnauthorizedInstances() {
    return this.request('/api/governance/unauthorized');
  }

  async applyInstanceActions(flaggedInstances) {
    return this.request('/api/governance/instances/apply', {
      method: 'POST',
      body: JSON.stringify({ flagged_instances: flaggedInstances }),
    });
  }

  // ==============================================================================
  // AUTHENTICATION APIs
  // ==============================================================================

  async register(userData) {
    return this.request('/api/v1/auth/register', {
      method: 'POST',
      body: JSON.stringify(userData),
    });
  }

  // ==============================================================================
  // USER MANAGEMENT APIs
  // ==============================================================================

  async getUsers() {
    return this.request('/api/v1/admin/users');
  }

  async createUser(userData) {
    return this.request('/api/v1/admin/clients', {
      method: 'POST',
      body: JSON.stringify(userData),
    });
  }

  async updateUser(userId, userData) {
    return this.request(`/api/v1/admin/users/${userId}`, {
      method: 'PUT',
      body: JSON.stringify(userData),
    });
  }

  async deleteUser(userId) {
    return this.request(`/api/v1/admin/users/${userId}`, {
      method: 'DELETE',
    });
  }

  // ==============================================================================
  // ACTIVITY FEED APIs
  // ==============================================================================

  async getActivityFeed(limit = 20) {
    return this.request(`/api/admin/activity?limit=${limit}`);
  }

  // ==============================================================================
  // ADMIN CONTROL APIs
  // ==============================================================================

  async setSpotMarketStatus(enabled) {
    return this.request('/api/admin/override/spot-market', {
      method: 'POST',
      body: JSON.stringify({ enabled }),
    });
  }

  async recomputeRiskScores() {
    return this.request('/api/admin/recompute-risk', {
      method: 'POST',
    });
  }

  async updateAdminProfile(profileData) {
    return this.request('/api/admin/profile', {
      method: 'PUT',
      body: JSON.stringify(profileData),
    });
  }

  // ==============================================================================
  // ONBOARDING APIs
  // ==============================================================================

  async getOnboardingTemplate() {
    return this.request('/api/v1/onboarding/template');
  }

  async getDiscoveryStatus(accountId = null) {
    const query = accountId ? `?account_id=${accountId}` : '';
    return this.request(`/api/v1/onboarding/discovery/status${query}`);
  }

  async createOnboardingRequest(data) {
    return this.request('/api/v1/onboarding/create', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async completeDiscovery(accountId) {
    return this.request(`/api/v1/onboarding/discovery/complete/${accountId}`, {
      method: 'POST',
    });
  }

  async getClientDashboardSummary(accountId) {
    return this.request(`/api/v1/onboarding/${accountId}/dashboard-summary`);
  }

  // ==============================================================================
  // LAB & EXPERIMENT APIs
  // ==============================================================================

  async getExperimentLogs(instanceId, limit = 30) {
    return this.request(`/api/v1/lab/experiments/${instanceId}?limit=${limit}`);
  }

  async getModels() {
    return this.request('/api/v1/lab/models');
  }

  async activateModel(modelId) {
    return this.request(`/api/v1/lab/models/${modelId}/activate`, {
      method: 'POST',
    });
  }

  // ==============================================================================
  // CLIENT-SPECIFIC APIs (for Client Dashboard)
  // ==============================================================================

  async getClients() {
    // Alias for getAllClients, but can be customized later
    return this.getAllClients();
  }

  async getClientTopology(clientId) {
    return this.request(`/api/client/${clientId}/topology`);
  }

  async getClientSavingsOverview(clientId, mode = 'total', clusterId = null) {
    const params = new URLSearchParams({ mode });
    if (clusterId) params.append('cluster_id', clusterId);
    return this.request(`/api/client/${clientId}/savings-overview?${params}`);
  }

  async getClientClusters(clientId) {
    return this.request(`/api/client/${clientId}/clusters`);
  }

  async getClusterInstances(clientId, clusterId) {
    return this.request(`/api/client/${clientId}/clusters/${clusterId}/instances`);
  }

  // ==============================================================================
  // FORCE ON-DEMAND APIs (3 Levels)
  // ==============================================================================

  async forceInstanceOnDemand(instanceId, durationHours) {
    return this.request(`/api/client/instances/${instanceId}/force-on-demand`, {
      method: 'POST',
      body: JSON.stringify({ duration_hours: durationHours }),
    });
  }

  async forceClusterOnDemand(clusterId, durationHours) {
    return this.request(`/api/client/clusters/${clusterId}/force-on-demand`, {
      method: 'POST',
      body: JSON.stringify({ duration_hours: durationHours }),
    });
  }

  async forceClientOnDemand(clientId, durationHours) {
    return this.request(`/api/client/${clientId}/force-on-demand-all`, {
      method: 'POST',
      body: JSON.stringify({ duration_hours: durationHours }),
    });
  }

  // ==============================================================================
  // STORAGE CLEANUP APIs
  // ==============================================================================

  async getUnmappedVolumes() {
    return this.request('/api/storage/unmapped-volumes');
  }

  async cleanupVolumes(volumeIds) {
    return this.request('/api/storage/volumes/cleanup', {
      method: 'POST',
      body: JSON.stringify({ volume_ids: volumeIds }),
    });
  }

  async getAmiSnapshots() {
    return this.request('/api/storage/ami-snapshots');
  }

  async cleanupSnapshots(snapshotIds) {
    return this.request('/api/storage/snapshots/cleanup', {
      method: 'POST',
      body: JSON.stringify({ snapshot_ids: snapshotIds }),
    });
  }

  // ==============================================================================
  // METRICS APIs (Dedicated Endpoints)
  // ==============================================================================

  async getActiveInstancesMetric() {
    return this.request('/api/metrics/active-instances');
  }

  async getRiskDetectedMetric() {
    return this.request('/api/metrics/risk-detected');
  }

  async getCostSavingsMetric() {
    return this.request('/api/metrics/cost-savings');
  }

  async getOptimizationRateMetric() {
    return this.request('/api/metrics/optimization-rate');
  }

  async getSystemLoadMetric() {
    return this.request('/api/metrics/system-load');
  }

  async getPerformanceMetrics(instanceId = null) {
    const query = instanceId ? `?instance_id=${instanceId}` : '';
    return this.request(`/api/metrics/performance${query}`);
  }

  // ==============================================================================
  // PIPELINE APIs
  // ==============================================================================

  async getPipelineFunnel() {
    return this.request('/api/pipeline/funnel');
  }

  async getPipelineStatus() {
    return this.request('/api/pipeline/status');
  }
}

export default APIClient;
