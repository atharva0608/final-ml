import axios from 'axios';

// Use REACT_APP_API_URL env var when set (local dev with explicit backend URL).
// In Docker, VITE_API_URL is passed but not read by CRA — so fall back to ''
// (empty string = relative URL) which routes through the Nginx proxy at /api.
const API_URL = process.env.REACT_APP_API_URL || '';

const api = axios.create({
    baseURL: API_URL,
    headers: {
        'Content-Type': 'application/json',
    },
});

export { api };

// Add a request interceptor
api.interceptors.request.use(
    (config) => {
        const token = localStorage.getItem('access_token');
        if (token) {
            config.headers.Authorization = `Bearer ${token}`;
        }
        return config;
    },
    (error) => {
        return Promise.reject(error);
    }
);

// Add a response interceptor for Global Error Handling
api.interceptors.response.use(
    (response) => response,
    (error) => {
        // Handle 401 Unauthorized (Expired token or missing auth)
        if (error.response && error.response.status === 401) {
            // Clear local storage and redirect if not already on login page
            if (!window.location.pathname.includes('/login')) {
                localStorage.clear();
                window.location.href = '/login';
            }
        }

        // Check for JIT Logic Interception (403 + detail flag)
        if (error.response && error.response.status === 403) {
            const data = error.response.data;
            // The backend sends `details: { required_ticket: true, ... }`
            if (data.details && data.details.required_ticket) {
                // Dispatch custom event for UI to catch
                const event = new CustomEvent('governance:required', {
                    detail: data.details
                });
                window.dispatchEvent(event);
            }
        }
        return Promise.reject(error);
    }
);

export const authAPI = {
    login: (data) => api.post('/api/v1/auth/login', data),
    signup: (data) => api.post('/api/v1/auth/signup', data),
    me: () => api.get('/api/v1/auth/me'),
    refresh: (token) => api.post('/api/v1/auth/refresh', { refresh_token: token }),
    changePassword: (data) => api.post('/api/v1/auth/change-password', data),
    updateProfile: (data) => api.put('/api/v1/auth/profile', data),
    respondToInvitation: (data) => api.post('/api/v1/auth/invitation-response', data),
    // Dashboard Preferences
    getPreferences: () => api.get('/api/v1/users/me/preferences'),
    updatePreferences: (preferences) => api.patch('/api/v1/users/me/preferences', preferences),
    // Standardized Organization Connection Info
    getConnectionInfo: () => api.get('/api/v1/organization/connection-info'),
    regenerateConnectionInfo: () => api.post('/api/v1/organization/connection-info/regenerate'),
};
export const authService = authAPI;

export const clusterAPI = {
    list: (params) => api.get('/api/v1/clusters', { params }),
    listClusters: (params) => api.get('/api/v1/clusters', { params }),
    getCluster: (id) => api.get(`/api/v1/clusters/${id}`),
    updateCluster: (id, data) => api.patch(`/api/v1/clusters/${id}`, data),
    deleteCluster: (id) => api.delete(`/api/v1/clusters/${id}`),
    getAgentInstall: (id) => api.get(`/api/v1/clusters/${id}/agent-install`),
    getNodes: (clusterId) => api.get(`/api/v1/clusters/${clusterId}/nodes`),
    connectAWS: (data) => api.post('/api/v1/clusters/connect-aws', data),
    generateInstallScript: (data) => api.post('/api/v1/clusters/install-script', data),
    verifyConnection: (clusterId) => api.post(`/api/v1/clusters/verify/${clusterId}`),
    updateResourceCosts: (clusterId, costs) => api.post(`/api/v1/clusters/${clusterId}/costs`, costs),
    autoInstallAgent: (clusterId) => api.post(`/api/v1/clusters/${clusterId}/auto-install`),
    updateAgent: (clusterId) => api.post(`/api/v1/clusters/${clusterId}/update-agent`),
    discover: () => api.post('/api/v1/clusters/discover'),
    toggleAutoRebalance: (clusterId, enabled) => api.patch(`/api/v1/clusters/${clusterId}/auto-rebalance`, null, { params: { enabled } }),
    getUtilization: (clusterId) => api.get(`/api/v1/clusters/${clusterId}/utilization`),
    getWorkloadType: (clusterId) => api.get(`/api/v1/clusters/${clusterId}/workload-type`),
    getNodesDetailed: (clusterId) => api.get(`/api/v1/clusters/${clusterId}/nodes/detailed`),
    disconnectAgent: (clusterId) => api.post(`/api/v1/clusters/${clusterId}/agent/disconnect`),
    removeAgent: (clusterId) => api.delete(`/api/v1/clusters/${clusterId}/agent`),
    optimize: (clusterId) => api.post(`/api/v1/clusters/${clusterId}/optimize`),
    fallback: (clusterId) => api.post(`/api/v1/clusters/${clusterId}/fallback`),
    getOptimizationSettings: (clusterId) => api.get(`/api/v1/clusters/${clusterId}/optimization-settings`),
    updateOptimizationSettings: (clusterId, settings) => api.put(`/api/v1/clusters/${clusterId}/optimization-settings`, settings),
    getWarmSpareStatus: (clusterId) => api.get(`/api/v1/atharvaai/v3/substitute/${clusterId}`),
};
export const clustersAPI = clusterAPI;

export const accountAPI = {
    list: (params) => api.get('/api/v1/accounts', { params }),
    create: (data) => api.post('/api/v1/accounts', data),
    validate: (id) => api.post(`/api/v1/accounts/${id}/validate`),
    setDefault: (id) => api.post(`/api/v1/accounts/${id}/set-default`),
    approve: (id) => api.post(`/api/v1/accounts/${id}/approve`),
    delete: (id) => api.delete(`/api/v1/accounts/${id}`),
};
export const accountsAPI = accountAPI;

export const adminAPI = {
    listClients: (params) => api.get('/api/v1/admin/clients', { params }),
    listOrganizations: (params) => api.get('/api/v1/admin/organizations', { params }),
    getOrganizations: (page, query) => api.get('/api/v1/admin/organizations', { params: { page, query } }),
    toggleOrg: (id) => api.post(`/api/v1/admin/organizations/${id}/toggle`),
    getClient: (id) => api.get(`/api/v1/admin/clients/${id}`),
    toggleClient: (id) => api.post(`/api/v1/admin/clients/${id}/toggle`),
    resetPassword: (id, data) => api.post(`/api/v1/admin/clients/${id}/reset-password`, data),
    getHealth: () => api.get('/api/v1/admin/health'),
    getStats: () => api.get('/api/v1/admin/stats'),
    getDashboardStats: () => api.get('/api/v1/admin/dashboard'),
    impersonate: (orgId) => api.post(`/api/v1/admin/impersonate`, { organization_id: orgId }),
    getBilling: () => api.get('/api/v1/admin/billing'),
    getOrganization: (id) => api.get(`/api/v1/admin/organizations/${id}`),
    getAgentFleet: () => api.get('/api/v1/admin/agent-fleet'),
    getCircuitBreakers: () => api.get('/api/v1/admin/circuit-breakers'),
    resetCircuitBreaker: (clusterId) => api.post(`/api/v1/admin/circuit-breakers/${clusterId}/reset`),
};

export const metricAPI = {
    getDashboard: (params) => api.get('/api/v1/metrics/dashboard', { params }),
    getCost: (params) => api.get('/api/v1/metrics/cost', { params }),
    getInstances: (params) => api.get('/api/v1/metrics/instances', { params }),
    getCostTimeSeries: (params) => api.get('/api/v1/metrics/cost/timeseries', { params }),
    getClusterMetrics: (id, params) => api.get(`/api/v1/metrics/cluster/${id}`, { params }),
    getSavings: (params) => api.get('/api/v1/metrics/savings', { params }),
    getOverview: () => api.get('/api/v1/metrics/overview'),
    getTeamSummary: (teamId) => api.get(`/api/v1/metrics/teams/${teamId}/summary`),
    getAccountSummary: (accountId) => api.get(`/api/v1/metrics/accounts/${accountId}/summary`),
    // Task 7.6: Rejection counters for decision engine
    getRejectionCounters: (clusterId) => api.get(`/api/v1/metrics/rejections/${clusterId}`),
};
export const metricsAPI = metricAPI;

export const optimizationAPI = {
    getRightsizing: (clusterId, params = {}) => api.get('/api/v1/pod-metrics/right-sizing/recommendations', {
        params: { cluster_id: clusterId, ...params }
    }),
    getEnrichedRightsizing: (clusterId, params = {}) => api.get('/api/v1/pod-metrics/rightsizing/enriched', {
        params: { cluster_id: clusterId, ...params }
    }),
    applyRecommendation: (id) => api.post(`/api/v1/optimization/apply/${id}`),
    applyRightsizingValidated: (instanceId, targetType, targetAz) =>
        api.post(`/api/v1/optimization/apply/${instanceId}/validated`, null, {
            params: { target_instance_type: targetType, target_az: targetAz }
        }),
    getSavingsRealized: () => api.get('/api/v1/optimization/savings/realized'),
    batchApplyRecommendations: (data) => api.post('/api/v1/optimization/rightsizing/batch-apply', data),
    getInstanceMetrics: (instanceId, days = 14) => api.get('/api/v1/pod-metrics/', {
        params: { instance_id: instanceId, days }
    }),
};

export const policyAPI = {
    listPolicies: (params) => api.get('/api/v1/policies', { params }),
    getPolicy: (id) => api.get(`/api/v1/policies/cluster/${id}`), // Fixed: use cluster endpoint
    createPolicy: (data) => api.post('/api/v1/policies', data),
    updatePolicy: (id, data) => api.put(`/api/v1/policies/${id}`, data),
    togglePolicy: (id) => api.post(`/api/v1/policies/${id}/toggle`),
};
export const policiesAPI = policyAPI;

export const hibernationAPI = {
    list: (params) => api.get('/api/v1/hibernation/schedules', { params }),
    getByCluster: (clusterId) => api.get('/api/v1/hibernation/schedules', { params: { cluster_id: clusterId } }),
    create: (data) => api.post('/api/v1/hibernation/schedules', data),
    update: (id, data) => api.put(`/api/v1/hibernation/schedules/${id}`, data),
    delete: (id) => api.delete(`/api/v1/hibernation/schedules/${id}`),
    toggle: (id) => api.post(`/api/v1/hibernation/schedules/${id}/toggle`),
    override: (id, data) => api.post(`/api/v1/hibernation/schedules/${id}/override`, data),
    getStrategies: () => api.get('/api/v1/hibernation/strategies'),
};

export const auditAPI = {
    list: (params) => api.get('/api/v1/audit/logs', { params }),
    exportLogs: (params) => api.get('/api/v1/audit/export', { params }),
};

export const templateAPI = {
    list: (params) => api.get('/api/v1/templates', { params }),
    get: (id) => api.get(`/api/v1/templates/${id}`),
    create: (data) => api.post('/api/v1/templates', data),
    update: (id, data) => api.put(`/api/v1/templates/${id}`, data),
    delete: (id) => api.delete(`/api/v1/templates/${id}`),
    setDefault: (id) => api.post(`/api/v1/templates/${id}/set-default`),
    getOptions: () => api.get('/api/v1/templates/options'),
    getDefault: () => api.get('/api/v1/templates/default'),
};
export const templatesAPI = templateAPI;

export const nodeTemplateAPI = {
    // Global Registry
    getGlobalTemplates: () => api.get(`/api/v1/node-templates`),
    createGlobalTemplate: (data) => api.post(`/api/v1/node-templates`, data),
    deleteGlobalTemplate: (id) => api.delete(`/api/v1/node-templates/${id}`),
    getVersions: (templateId) => api.get(`/api/v1/node-templates/${templateId}/versions`),
    createVersion: (templateId, data) => api.post(`/api/v1/node-templates/${templateId}/versions`, data),

    // Cluster Mappings
    getActiveMapping: (clusterId) => api.get(`/api/v1/clusters/${clusterId}/node-template/active`),
    assignToCluster: (clusterId, templateId, versionId) => api.post(`/api/v1/clusters/${clusterId}/node-template/assign`, { template_id: templateId, version_id: versionId }),

    // Validation
    validate: (data) => api.post(`/api/v1/node-templates/validate`, data),
};

export const experimentsAPI = {
    list: (params) => api.get('/api/v1/lab/experiments', { params }),
    listExperiments: (params) => api.get('/api/v1/lab/experiments', { params }),
    getExperiment: (id) => api.get(`/api/v1/lab/experiments/${id}`),
    createExperiment: (data) => api.post('/api/v1/lab/experiments', data),
    start: (id) => api.post(`/api/v1/lab/experiments/${id}/start`),
    startExperiment: (id) => api.post(`/api/v1/lab/experiments/${id}/start`),
    stop: (id) => api.post(`/api/v1/lab/experiments/${id}/stop`),
    stopExperiment: (id) => api.post(`/api/v1/lab/experiments/${id}/stop`),
    getResults: (id) => api.get(`/api/v1/lab/experiments/${id}/results`),
};
export const labAPI = experimentsAPI;

export const onboardingAPI = {
    getState: () => api.get('/api/v1/onboarding/state'),
    getAwsLink: (mode) => api.get(`/api/v1/onboarding/aws-link?mode=${mode || 'FULL_ACCESS'}`),
    getTemplate: (mode) => api.get(`/api/v1/onboarding/template?mode=${mode || 'FULL_ACCESS'}`, { responseType: 'blob' }),
    verify: (roleArn) => api.post('/api/v1/onboarding/verify', { role_arn: roleArn }),
    skip: () => api.post('/api/v1/onboarding/skip'),
};

export const organizationAPI = {
    getMembers: () => api.get('/api/v1/organization/members'),
    getInvitations: () => api.get('/api/v1/organization/invitations'),
    inviteMember: (email, role, access_level) => api.post('/api/v1/organization/members', { email, role, access_level }),
    removeMember: (userId) => api.delete(`/api/v1/organization/members/${userId}`),
    updateMemberRole: (userId, role, access_level) => api.patch(`/api/v1/organization/members/${userId}`, { role, access_level }),
};

export const teamAPI = {
    list: () => api.get('/api/v1/teams/'),
    get: (id) => api.get(`/api/v1/teams/${id}`),
    create: (name) => api.post('/api/v1/teams/', { name }),
    rename: (id, name) => api.put(`/api/v1/teams/${id}/rename`, { name }),
    assign: (teamId, memberId) => api.post(`/api/v1/teams/${teamId}/assign`, { member_id: memberId }),
    remove: (teamId, memberId) => api.post(`/api/v1/teams/${teamId}/remove`, { member_id: memberId }),
    invite: (teamId, email, role = "MEMBER", fullName = null) => api.post(`/api/v1/teams/${teamId}/invite`, { email, role, full_name: fullName }),
    getStats: (teamId) => api.get(`/api/v1/teams/${teamId}/stats`),
    updateGovernance: (teamId, config) => api.put(`/api/v1/teams/${teamId}/governance`, { config: config }),
    updateMemberPermissions: (teamId, memberId, permissions) => api.put(`/api/v1/teams/${teamId}/members/${memberId}/permissions`, { permissions }),
};

export const userAPI = {
    updateProfile: (data) => api.patch('/api/v1/users/me', data),
    updatePermissions: (userId, permissions) => api.post(`/api/v1/users/${userId}/permissions`, { permissions }),
    updatePreferences: (preferences) => api.patch('/api/v1/users/me/preferences', preferences),
};

export const billingAPI = {
    getStatus: () => api.get('/api/v1/billing/status'),
    getCostSummary: (params) => api.get('/api/v1/billing/costs/summary', { params }),
    createPortalSession: () => api.post('/api/v1/billing/create-portal-session'),
};

export const hygieneAPI = {
    scan: (accountId, params) => api.get(`/api/v1/hygiene/scan/${accountId}`, {
        params,
        paramsSerializer: {
            indexes: null // Serializes arrays as 'regions=value' instead of 'regions[]=value'
        }
    }),
    execute: (payload, accountId) => api.post(`/api/v1/hygiene/action?account_id=${accountId}`, payload),
    checkDependencies: (accountId, resourceType, resourceId, region) => api.get('/api/v1/hygiene/check-dependencies', {
        params: { account_id: accountId, resource_type: resourceType, resource_id: resourceId, region }
    }),
    discover: (accountId, resourceType, region) => api.get('/api/v1/hygiene/discover', {
        params: { account_id: accountId, resource_type: resourceType, region }
    }),
    // NEW: Total cost and cost services endpoints
    getTotalCost: (accountId) => api.get('/api/v1/hygiene/total-cost', {
        params: accountId ? { account_id: accountId } : {}
    }),
    getCostServices: (accountId) => api.get('/api/v1/hygiene/cost-services', {
        params: accountId ? { account_id: accountId } : {}
    }),
    getScanHistory: (accountId, days = 7) => api.get('/api/v1/hygiene/scan-history', {
        params: { account_id: accountId, days }
    }),
};

// AtharvaAi Pool Selection & Termination Monitoring API
export const atharvaaiAPI = {
    // Pool Rankings - Get ML-scored pool recommendations
    getRankings: (template, region = 'ap-south-1', limit = 10, clusterId = null, currentNodeContext = null) => {
        const params = { region, limit };
        if (clusterId) params.cluster_id = clusterId;

        // Add current node context for real savings calculation
        if (currentNodeContext) {
            if (currentNodeContext.instance_type) params.current_instance_type = currentNodeContext.instance_type;
            if (currentNodeContext.lifecycle) params.current_instance_lifecycle = currentNodeContext.lifecycle;
        }

        return api.post('/api/v1/atharvaai/pools/rankings', template, { params });
    },

    // Get rankings using a saved template ID
    getRankingsForTemplate: (templateId, region = 'ap-south-1', limit = 10) =>
        api.post('/api/v1/atharvaai/pools/rankings', null, {
            params: { template_id: templateId, region, limit }
        }),

    // Get globally flagged risky pools (System B)
    getBlacklist: () => api.get('/api/v1/atharvaai/blacklist'),

    // Check if specific pool is blacklisted
    checkBlacklist: (instanceType, az) =>
        api.get('/api/v1/atharvaai/blacklist/check', {
            params: { instance_type: instanceType, az }
        }),

    // Get auto-rebalancing status (System B)
    getRebalancingStatus: (clusterId = null, limit = 10) =>
        api.get('/api/v1/atharvaai/rebalancing/status', {
            params: clusterId ? { cluster_id: clusterId, limit } : { limit }
        }),

    // Health check
    getHealth: () => api.get('/api/v1/atharvaai/health'),

    // Effective Configuration
    getEffectiveConfiguration: (clusterId) => api.get(`/api/v1/atharvaai/clusters/${clusterId}/effective-configuration`),

    // Node-Specific Rankings (To be implemented in backend)
    getNodeRecommendations: (clusterId) => api.get(`/api/v1/atharvaai/clusters/${clusterId}/node-recommendations`),

    // Cluster Impact (To be implemented in backend)
    getClusterImpact: (clusterId) => api.get(`/api/v1/atharvaai/clusters/${clusterId}/impact`),

    // Enriched volatility status (includes az_pressure map)
    getVolatilityStatusEnriched: () => api.get('/api/v1/atharvaai/volatility/status'),
};
export const cleanupAPI = hygieneAPI;

export const approvalsAPI = {
    create: (data) => api.post('/api/v1/approvals/', data),
    delegate: (data) => api.post('/api/v1/approvals/delegate', data),
    acceptGrant: (id) => api.post(`/api/v1/approvals/${id}/accept`),
    rejectGrant: (id) => api.post(`/api/v1/approvals/${id}/reject`),
    list: (status) => api.get('/api/v1/approvals/', { params: { status } }),
    getActiveWindow: () => api.get('/api/v1/approvals/active-window'),
    approve: (id) => api.post(`/api/v1/approvals/${id}/approve`),
    reject: (id) => api.post(`/api/v1/approvals/${id}/reject`),  // Reject pending request
    revoke: (id) => api.post(`/api/v1/approvals/${id}/revoke`),
    // JIT Feature Access
    createJITRequest: (data) => api.post('/api/v1/approvals/jit-request', data),
    getMyJITApprovals: () => api.get('/api/v1/approvals/my-jit-approvals'),
    getMyJITTickets: () => api.get('/api/v1/approvals/my-jit-approvals'), // Alias
};
export const approvalAPI = approvalsAPI;

export const governanceAPI = {
    getPolicies: () => api.get('/api/v1/governance/policies'),
    updatePolicies: (data) => api.patch('/api/v1/governance/policies', data),
    runAutopilot: (accountId) => api.post(`/api/v1/governance/run-autopilot?account_id=${accountId}`),
};

export const rolesAPI = {
    listPermissions: () => api.get('/api/v1/roles/permissions'),
    listRoles: () => api.get('/api/v1/roles'),
    getRole: (id) => api.get(`/api/v1/roles/${id}`),
    createRole: (data) => api.post('/api/v1/roles', data),
    updateRole: (id, data) => api.put(`/api/v1/roles/${id}`, data),
    deleteRole: (id) => api.delete(`/api/v1/roles/${id}`),
    assignRole: (userId, roleId) => api.post('/api/v1/roles/assign', { user_id: userId, role_id: roleId }),
    assignRole: (userId, roleId) => api.post('/api/v1/roles/assign', { user_id: userId, role_id: roleId }),
    seed: () => api.post('/api/v1/roles/seed'),
};

// Legacy aliases for backwards compatibility
export const ticketAPI = approvalsAPI;
export const ticketsAPI = approvalsAPI;

export const permissionAPI = {
    check: (featureId, resourceId = null) => api.post('/api/v1/permissions/check', {
        feature_id: featureId,
        resource_id: resourceId
    }),
    getMyFeatures: () => api.get('/api/v1/permissions/my-features'),
    revokeFeature: (userId, featureId) => api.post(`/api/v1/permissions/${userId}/revoke-feature/${featureId}`),
    getFeatureRegistry: () => api.get('/api/v1/permissions/feature-registry'),
};
export const permissionsAPI = permissionAPI;

// ── Karpenter Auto-Optimization ──────────────────────────────────────────
export const karpenterAPI = {
    getStatus: () => api.get('/api/v1/karpenter/status'),
    getConfig: (clusterId) => api.get(`/api/v1/karpenter/config?cluster_id=${clusterId}`),
    saveConfig: (data) => api.post('/api/v1/karpenter/config', data),
    updateConfig: (clusterId, data) => api.patch(`/api/v1/karpenter/config/${clusterId}`, data),
    deploy: (data) => api.post('/api/v1/karpenter/deploy', data),
    toggle: (clusterId, enabled) => api.post(`/api/v1/karpenter/toggle/${clusterId}`, { enabled }),
    getActivity: (clusterId, limit = 20) => api.get('/api/v1/karpenter/activity', { params: { cluster_id: clusterId, limit } }),
    getStats: (period = 'week') => api.get('/api/v1/karpenter/stats', { params: { period } }),

    // Dry-run recommendations (mode-aware)
    getRecommendations: (clusterId = null, statusFilter = null) => api.get('/api/v1/karpenter/recommendations', {
        params: { cluster_id: clusterId, status_filter: statusFilter }
    }),
    applyRecommendation: (recommendationId, data) => api.post(`/api/v1/karpenter/apply-recommendation/${recommendationId}`, data),
    batchApplyRecommendations: (instanceIds) => api.post('/api/v1/karpenter/apply-recommendations/batch', { instance_ids: instanceIds }),

    // Mode management
    switchMode: (clusterId, mode) => api.patch(`/api/v1/karpenter/mode/${clusterId}`, { mode }),

    // Execution Plan & History
    getExecutionPlan: (clusterId = null) => api.get('/api/v1/karpenter/execution-plan', { params: { cluster_id: clusterId } }),
    getHistory: (clusterId = null) => api.get('/api/v1/karpenter/history', { params: { cluster_id: clusterId } }),

    // Karpenter install / uninstall (runs via agent DaemonSet inside the cluster)
    installKarpenter: (clusterId, data = {}) => api.post(`/api/v1/karpenter/clusters/${clusterId}/install`, data),
    uninstallKarpenter: (clusterId) => api.delete(`/api/v1/karpenter/clusters/${clusterId}/install`),
    getInstallStatus: (clusterId) => api.get(`/api/v1/karpenter/clusters/${clusterId}/install-status`),

    // Detect whether Karpenter is installed in-cluster
    detectKarpenter: (clusterId) => api.get(`/api/v1/karpenter/detect/${clusterId}`),
};

// ── Native Spot (No-Karpenter) — ASG MixedInstancesPolicy ────────────────────
export const nativeSpotAPI = {
    getStatus: (clusterId, nodegroupName = null) =>
        api.get(`/api/v1/karpenter/native-spot/status/${clusterId}`,
                { params: nodegroupName ? { nodegroup_name: nodegroupName } : {} }),
    enable: (clusterId, opts = {}) =>
        api.post(`/api/v1/karpenter/native-spot/enable/${clusterId}`, opts),
    revert: (clusterId, opts = {}) =>
        api.post(`/api/v1/karpenter/native-spot/revert/${clusterId}`, opts),
};

// ── Tag Governance APIs ──────────────────────────────────────────────────────
export const tagPolicyAPI = {
    list: () => api.get('/api/v1/tags/policies/'),
    create: (data) => api.post('/api/v1/tags/policies/', data),
    update: (id, data) => api.put(`/api/v1/tags/policies/${id}`, data),
    delete: (id) => api.delete(`/api/v1/tags/policies/${id}`),
    toggle: (id) => api.patch(`/api/v1/tags/policies/${id}/toggle`),
};

export const tagTemplateAPI = {
    list: () => api.get('/api/v1/tags/templates/'),
    create: (data) => api.post('/api/v1/tags/templates/', data),
    get: (id) => api.get(`/api/v1/tags/templates/${id}`),
    update: (id, data) => api.put(`/api/v1/tags/templates/${id}`, data),
    delete: (id) => api.delete(`/api/v1/tags/templates/${id}`),
};

export const tagAutomationAPI = {
    listRules: () => api.get('/api/v1/tags/automation/rules'),
    createRule: (data) => api.post('/api/v1/tags/automation/rules', data),
    updateRule: (id, data) => api.put(`/api/v1/tags/automation/rules/${id}`, data),
    deleteRule: (id) => api.delete(`/api/v1/tags/automation/rules/${id}`),
    toggleRule: (id) => api.patch(`/api/v1/tags/automation/rules/${id}/toggle`),
    getLog: (params) => api.get('/api/v1/tags/automation/log', { params }),
};

export const tagScoringAPI = {
    getConfig: () => api.get('/api/v1/tags/scoring/config'),
    saveConfig: (data) => api.put('/api/v1/tags/scoring/config', data),
    preview: (params) => api.get('/api/v1/tags/scoring/preview', { params }),
};

export const tagComplianceAPI = {
    getSummary: (params) => api.get('/api/v1/tags/compliance/summary', { params }),
    listResources: (params) => api.get('/api/v1/tags/compliance/resources', { params }),
    getHeatmap: (params) => api.get('/api/v1/tags/compliance/heatmap', { params }),
};

export const atharvaAiAPI = {
    getVolatilityStatus: () => api.get('/api/v1/atharvaai/volatility/status'),
    getHealth: () => api.get('/api/v1/atharvaai/health'),
    getRankings: () => api.post('/api/v1/atharvaai/pools/rankings', { architecture: ["amd64", "arm64"], vcpu_min: 2, vcpu_max: 64, memory_gb_min: 4, memory_gb_max: 256, allowed_families: null, allowed_sizes: null, allowed_azs: null, excluded_instance_types: null }, { params: { region: 'ap-south-1', limit: 10 } }),
    getBlacklistStatus: () => api.get('/api/v1/atharvaai/blacklist'),
};

// Decision Engine v3 API
export const decisionEngineAPI = {
    // Legacy endpoints (keep for backwards compatibility)
    getLogs: (clusterId) => api.get('/api/v1/decision/logs', { params: { cluster_id: clusterId } }),
    getDryRunBudget: () => api.get('/api/v1/dryrun/budget'),
    getCooldownStatus: (clusterId) => api.get(`/api/v1/cooldown/${clusterId}`),
    getExecutionStatus: (clusterId) => api.get(`/api/v1/execution/status/${clusterId}`),
    getSubstituteStatus: (clusterId) => api.get(`/api/v1/substitute/status/${clusterId}`),
    getClassification: (clusterId) => api.get(`/api/v1/clusters/${clusterId}/classification`),
    updateOptimizationMode: (clusterId, mode) => api.patch(`/api/v1/clusters/${clusterId}`, { optimization_mode: mode }),

    // Decision Engine v3 endpoints
    getGlobalIntelligenceStatus: (region) => api.get('/api/v1/atharvaai/v3/global-intelligence/status', { params: { region } }),
    getDiversityStatus: (clusterId) => api.get(`/api/v1/atharvaai/v3/diversity/${clusterId}`),
    getCooldownStatusV3: (clusterId) => api.get(`/api/v1/atharvaai/v3/cooldown/${clusterId}`),
    getSubstituteStatusV3: (clusterId) => api.get(`/api/v1/atharvaai/v3/substitute/${clusterId}`),
    getStateMachine: (clusterId) => api.get(`/api/v1/atharvaai/v3/state-machine/${clusterId}`),
    setOptimizationMode: (clusterId, mode) => api.put(`/api/v1/atharvaai/v3/cluster/${clusterId}/optimization-mode`, null, { params: { mode } }),
    upgradeModelVersion: (clusterId, version) => api.put(`/api/v1/atharvaai/v3/cluster/${clusterId}/model-version`, null, { params: { version } }),
    getDecisionMetrics: () => api.get('/api/v1/atharvaai/v3/metrics'),
    getWorkloadStatus: (clusterId) => api.get(`/api/v1/atharvaai/v3/workload-status/${clusterId}`),
    deploySubstitute: (clusterId, targetNodeName) => api.post(`/api/v1/karpenter/v3/substitute/${clusterId}/deploy`, null, { params: { target_node_name: targetNodeName } }),
    getSubstituteStatusDetailed: (clusterId) => api.get(`/api/v1/karpenter/v3/substitute/${clusterId}/status`),
    getCooldownDetailed: (clusterId) => api.get(`/api/v1/karpenter/v3/cooldown/${clusterId}`),
};

// ── Optimizer Coordinator API ─────────────────────────────────────────
export const optimizerCoordinatorAPI = {
    getStatus: (clusterId) =>
        api.get(`/api/v1/optimizer/status/${clusterId}`),
    triggerEvaluation: (clusterId) =>
        api.post(`/api/v1/optimizer/evaluate/${clusterId}`),
    listProposals: (clusterId, status) =>
        api.get(`/api/v1/optimizer/proposals/${clusterId}`, { params: status ? { status } : {} }),
    approveProposal: (proposalId) =>
        api.post(`/api/v1/optimizer/proposals/${proposalId}/approve`),
    rejectProposal: (proposalId, reason) =>
        api.post(`/api/v1/optimizer/proposals/${proposalId}/reject`, { reason }),
    getComparison: (proposalId) =>
        api.get(`/api/v1/optimizer/comparison/${proposalId}`),
    initializeCluster: (clusterId) =>
        api.post(`/api/v1/optimizer/initialize/${clusterId}`),
    getTrustPhase: (clusterId) =>
        api.get(`/api/v1/optimizer/trust-phase/${clusterId}`),
    getResizeGuardStatus: (clusterId) =>
        api.get(`/api/v1/optimizer/resize-guard/${clusterId}`),
    getCircuitBreakerStatus: (clusterId) =>
        api.get(`/api/v1/optimizer/circuit-breaker/${clusterId}`),
};

// ── Pool Rotation API ──────────────────────────────────────────────────
export const poolRotationAPI = {
    getStatus: (clusterId) =>
        api.get(`/api/v1/pool-rotation/status/${clusterId}`),
    checkRotation: (clusterId, region) =>
        api.post(`/api/v1/pool-rotation/check/${clusterId}`, region ? { region } : {}),
    forceRotation: (clusterId, region) =>
        api.post(`/api/v1/pool-rotation/force/${clusterId}`, region ? { region } : {}),
};

// ── Multi-Cluster Fleet API ─────────────────────────────────────────────
export const multiClusterAPI = {
    getSummary: () => api.get('/api/v1/multi-cluster/summary'),
    getActions: (limit = 50) => api.get('/api/v1/multi-cluster/actions', { params: { limit } }),
    getTrends: (days = 30) => api.get('/api/v1/multi-cluster/trends', { params: { days } }),
};


export default api;
