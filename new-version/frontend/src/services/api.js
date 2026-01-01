/**
 * API Client
 *
 * Axios-based API client with authentication and error handling
 */
import axios from 'axios';
import toast from 'react-hot-toast';

// API base URL - configured from environment variable
const API_BASE_URL = process.env.REACT_APP_API_URL || 'http://localhost:8000/api/v1';

// Create axios instance
const apiClient = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
  timeout: 30000, // 30 seconds
});

// Request interceptor - add auth token
apiClient.interceptors.request.use(
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

// Response interceptor - handle errors and token refresh
apiClient.interceptors.response.use(
  (response) => {
    return response;
  },
  async (error) => {
    const originalRequest = error.config;

    // Handle 401 Unauthorized - token expired
    if (error.response?.status === 401 && !originalRequest._retry) {
      originalRequest._retry = true;

      try {
        const refreshToken = localStorage.getItem('refresh_token');
        if (refreshToken) {
          const response = await axios.post(`${API_BASE_URL}/auth/refresh`, {
            refresh_token: refreshToken,
          });

          const { access_token, refresh_token } = response.data;
          localStorage.setItem('access_token', access_token);
          localStorage.setItem('refresh_token', refresh_token);

          // Retry original request with new token
          originalRequest.headers.Authorization = `Bearer ${access_token}`;
          return apiClient(originalRequest);
        }
      } catch (refreshError) {
        // Refresh failed - logout user
        localStorage.removeItem('access_token');
        localStorage.removeItem('refresh_token');
        localStorage.removeItem('user');
        window.location.href = '/login';
        return Promise.reject(refreshError);
      }
    }

    // Handle other errors
    const errorMessage = error.response?.data?.message || error.message || 'An error occurred';

    // Don't show toast for certain errors (to avoid spam)
    if (!originalRequest.silent) {
      toast.error(errorMessage);
    }

    return Promise.reject(error);
  }
);

// Authentication API
export const authAPI = {
  signup: (data) => apiClient.post('/auth/signup', data),
  login: (data) => apiClient.post('/auth/login', data),
  logout: () => apiClient.post('/auth/logout'),
  getMe: () => apiClient.get('/auth/me'),
  changePassword: (data) => apiClient.post('/auth/change-password', data),
  refresh: (refreshToken) => apiClient.post('/auth/refresh', { refresh_token: refreshToken }),
};

// Cluster API
export const clusterAPI = {
  discover: (accountId) => apiClient.post('/clusters/discover', null, { params: { account_id: accountId } }),
  create: (data) => apiClient.post('/clusters', data),
  list: (params) => apiClient.get('/clusters', { params }),
  get: (id) => apiClient.get(`/clusters/${id}`),
  update: (id, data) => apiClient.patch(`/clusters/${id}`, data),
  delete: (id) => apiClient.delete(`/clusters/${id}`),
  getAgentInstall: (id) => apiClient.get(`/clusters/${id}/agent-install`),
  heartbeat: (id) => apiClient.post(`/clusters/${id}/heartbeat`),
};

// Template API
export const templateAPI = {
  create: (data) => apiClient.post('/templates', data),
  list: (params) => apiClient.get('/templates', { params }),
  get: (id) => apiClient.get(`/templates/${id}`),
  update: (id, data) => apiClient.patch(`/templates/${id}`, data),
  delete: (id) => apiClient.delete(`/templates/${id}`),
  setDefault: (id) => apiClient.post(`/templates/${id}/set-default`),
};

// Policy API
export const policyAPI = {
  create: (data) => apiClient.post('/policies', data),
  list: (params) => apiClient.get('/policies', { params }),
  get: (id) => apiClient.get(`/policies/${id}`),
  getByCluster: (clusterId) => apiClient.get(`/policies/cluster/${clusterId}`),
  update: (id, data) => apiClient.patch(`/policies/${id}`, data),
  delete: (id) => apiClient.delete(`/policies/${id}`),
  toggle: (id) => apiClient.post(`/policies/${id}/toggle`),
};

// Hibernation API
export const hibernationAPI = {
  create: (data) => apiClient.post('/hibernation', data),
  list: (params) => apiClient.get('/hibernation', { params }),
  get: (id) => apiClient.get(`/hibernation/${id}`),
  getByCluster: (clusterId) => apiClient.get(`/hibernation/cluster/${clusterId}`),
  update: (id, data) => apiClient.patch(`/hibernation/${id}`, data),
  delete: (id) => apiClient.delete(`/hibernation/${id}`),
  toggle: (id) => apiClient.post(`/hibernation/${id}/toggle`),
};

// Metrics API
export const metricsAPI = {
  getDashboard: (params) => apiClient.get('/metrics/dashboard', { params }),
  getCost: (params) => apiClient.get('/metrics/cost', { params }),
  getInstances: (params) => apiClient.get('/metrics/instances', { params }),
  getCostTimeSeries: (params) => apiClient.get('/metrics/cost/timeseries', { params }),
  getCluster: (clusterId) => apiClient.get(`/metrics/cluster/${clusterId}`),
};

// Audit API
export const auditAPI = {
  list: (params) => apiClient.get('/audit', { params }),
  get: (id) => apiClient.get(`/audit/${id}`),
};

// Admin API
export const adminAPI = {
  listClients: (params) => apiClient.get('/admin/clients', { params }),
  getClient: (id) => apiClient.get(`/admin/clients/${id}`),
  toggleClient: (id) => apiClient.post(`/admin/clients/${id}/toggle`),
  resetPassword: (id, data) => apiClient.post(`/admin/clients/${id}/reset-password`, data),
  getStats: () => apiClient.get('/admin/stats'),
};

// Lab API
export const labAPI = {
  create: (data) => apiClient.post('/lab/experiments', data),
  list: (params) => apiClient.get('/lab/experiments', { params }),
  get: (id) => apiClient.get(`/lab/experiments/${id}`),
  update: (id, data) => apiClient.patch(`/lab/experiments/${id}`, data),
  delete: (id) => apiClient.delete(`/lab/experiments/${id}`),
  start: (id) => apiClient.post(`/lab/experiments/${id}/start`),
  stop: (id) => apiClient.post(`/lab/experiments/${id}/stop`),
  getResults: (id) => apiClient.get(`/lab/experiments/${id}/results`),
};

export default apiClient;
