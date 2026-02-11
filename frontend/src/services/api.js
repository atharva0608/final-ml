import axios from 'axios';

const API_URL = process.env.REACT_APP_API_URL || 'http://localhost:8000';

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
    discover: () => api.post('/api/v1/clusters/discover'),
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
    getBilling: () => api.get('/api/v1/admin/billing'),
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
};
export const metricsAPI = metricAPI;

export const optimizationAPI = {
    getRightsizing: (clusterId) => api.get(`/api/v1/optimization/rightsizing/${clusterId}`),
    applyRecommendation: (id) => api.post(`/api/v1/optimization/apply/${id}`),
};

export const healthAPI = {
    getSystemHealth: () => api.get('/api/v1/health/system'),
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
};
export const templatesAPI = templateAPI;

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

export const settingsAPI = {
    getProfile: () => api.get('/api/v1/settings/profile'),
    updateProfile: (data) => api.patch('/api/v1/settings/profile', data),
    getIntegrations: () => api.get('/api/v1/settings/integrations'),
    addIntegration: (data) => api.post('/api/v1/settings/integrations', data),
    deleteIntegration: (id) => api.delete(`/api/v1/settings/integrations/${id}`),
};

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

export default api;

