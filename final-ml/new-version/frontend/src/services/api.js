import axios from 'axios';

const API_URL = process.env.REACT_APP_API_URL || 'http://localhost:8000';

const api = axios.create({
    baseURL: API_URL,
    headers: {
        'Content-Type': 'application/json',
    },
});

// Add a request interceptor
api.interceptors.request.use(
    (config) => {
        const token = localStorage.getItem('token');
        if (token) {
            config.headers.Authorization = `Bearer ${token}`;
        }
        return config;
    },
    (error) => {
        return Promise.reject(error);
    }
);

export const authAPI = {
    login: (data) => api.post('/api/v1/auth/login', data),
    signup: (data) => api.post('/api/v1/auth/signup', data),
    me: () => api.get('/api/v1/auth/me'),
    refresh: (token) => api.post('/api/v1/auth/refresh', { refresh_token: token }),
    changePassword: (data) => api.post('/api/v1/auth/change-password', data),
};
export const authService = authAPI;

export const clusterAPI = {
    list: (params) => api.get('/api/v1/clusters', { params }),
    listClusters: (params) => api.get('/api/v1/clusters', { params }),
    getCluster: (id) => api.get(`/api/v1/clusters/${id}`),
    updateCluster: (id, data) => api.patch(`/api/v1/clusters/${id}`, data),
    deleteCluster: (id) => api.delete(`/api/v1/clusters/${id}`),
    getAgentInstall: (id) => api.get(`/api/v1/clusters/${id}/agent-install`),
};
export const clustersAPI = clusterAPI;

export const accountAPI = {
    list: (params) => api.get('/api/v1/accounts', { params }),
    create: (data) => api.post('/api/v1/accounts', data),
    validate: (id) => api.post(`/api/v1/accounts/${id}/validate`),
    delete: (id) => api.delete(`/api/v1/accounts/${id}`),
    setDefault: (id) => api.post(`/api/v1/accounts/${id}/set-default`),
};
export const accountsAPI = accountAPI;

export const adminAPI = {
    listClients: (params) => api.get('/api/v1/admin/clients', { params }),
    getClient: (id) => api.get(`/api/v1/admin/clients/${id}`),
    toggleClient: (id) => api.post(`/api/v1/admin/clients/${id}/toggle`),
    resetPassword: (id, data) => api.post(`/api/v1/admin/clients/${id}/reset-password`, data),
    getHealth: () => api.get('/api/v1/admin/health'),
    getStats: () => api.get('/api/v1/admin/stats'),
};

export const metricAPI = {
    getClusterMetrics: (id, params) => api.get(`/api/v1/metrics/cluster/${id}`, { params }),
    getGlobalMetrics: (params) => api.get('/api/v1/metrics/global', { params }),
    getSavingsData: (params) => api.get('/api/v1/metrics/savings', { params }),
    getActivityFeed: (params) => api.get('/api/v1/metrics/activity', { params }),
};
export const metricsAPI = metricAPI;

export const policyAPI = {
    listPolicies: (params) => api.get('/api/v1/policies', { params }),
    getPolicy: (id) => api.get(`/api/v1/policies/${id}`),
    createPolicy: (data) => api.post('/api/v1/policies', data),
    updatePolicy: (id, data) => api.put(`/api/v1/policies/${id}`, data),
    togglePolicy: (id) => api.post(`/api/v1/policies/${id}/toggle`),
};
export const policiesAPI = policyAPI;

export const hibernationAPI = {
    getSchedule: (clusterId) => api.get(`/api/v1/hibernation/schedule/${clusterId}`),
    updateSchedule: (clusterId, data) => api.put(`/api/v1/hibernation/schedule/${clusterId}`, data),
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
};
export const templatesAPI = templateAPI;

export const labAPI = {
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
export const labsAPI = labAPI;

export const settingsAPI = {
    getProfile: () => api.get('/api/v1/settings/profile'),
    updateProfile: (data) => api.patch('/api/v1/settings/profile', data),
    getIntegrations: () => api.get('/api/v1/settings/integrations'),
    addIntegration: (data) => api.post('/api/v1/settings/integrations', data),
    deleteIntegration: (id) => api.delete(`/api/v1/settings/integrations/${id}`),
};

export default api;
