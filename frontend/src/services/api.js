/**
 * Unified API Client for Spot Optimizer Platform
 * Uses fetch() API with axios-style interface
 * Last Updated: 2025-12-26 (P-2025-12-26-005)
 */

// ============================================================================
// Configuration
// ============================================================================

const isProduction = import.meta.env.PROD;
const API_BASE_URL = isProduction
    ? '/api'
    : (import.meta.env.VITE_API_URL || 'http://localhost:8000/api');

console.log(`🔌 API Connected to: ${API_BASE_URL} (${isProduction ? 'PRODUCTION' : 'DEVELOPMENT'})`);

// ============================================================================
// Core HTTP Client with Axios-Style Interface
// ============================================================================

class ApiClient {
    constructor(baseURL) {
        this.baseURL = baseURL;
    }

    async request(method, endpoint, options = {}) {
        const url = endpoint.startsWith('http') ? endpoint : `${this.baseURL}${endpoint}`;
        const token = localStorage.getItem('auth_token');

        const config = {
            method,
            headers: {
                'Content-Type': 'application/json',
                ...(token && { 'Authorization': `Bearer ${token}` }),
                ...options.headers,
            },
            ...options,
        };

        // Add body for POST/PUT/PATCH requests
        if (options.body && typeof options.body === 'object' && !(options.body instanceof FormData)) {
            config.body = JSON.stringify(options.body);
        }

        try {
            const response = await fetch(url, config);

            // Handle 204 No Content
            if (response.status === 204) {
                return { data: null, status: 204, statusText: 'No Content' };
            }

            const data = await response.json().catch(() => null);

            if (!response.ok) {
                throw new Error(data?.detail || data?.message || `HTTP ${response.status}: ${response.statusText}`);
            }

            return { data, status: response.status, statusText: response.statusText };
        } catch (error) {
            console.error(`API ${method} ${endpoint} failed:`, error);
            throw error;
        }
    }

    // Axios-style methods
    async get(endpoint, config = {}) {
        return this.request('GET', endpoint, config);
    }

    async post(endpoint, body, config = {}) {
        return this.request('POST', endpoint, { ...config, body });
    }

    async put(endpoint, body, config = {}) {
        return this.request('PUT', endpoint, { ...config, body });
    }

    async patch(endpoint, body, config = {}) {
        return this.request('PATCH', endpoint, { ...config, body });
    }

    async delete(endpoint, config = {}) {
        return this.request('DELETE', endpoint, config);
    }
}

// Create singleton instance
const api = new ApiClient(API_BASE_URL);

// ============================================================================
// Authentication Helper Functions
// ============================================================================

export function setAuthToken(token) {
    localStorage.setItem('auth_token', token);
}

export function clearAuthToken() {
    localStorage.removeItem('auth_token');
}

export function getAuthToken() {
    return localStorage.getItem('auth_token');
}

// ============================================================================
// Legacy Named Export Functions (for backward compatibility)
// ============================================================================

// Auth
export async function login(identifier, password) {
    const res = await api.post('/v1/auth/login', { identifier, password });
    return res.data;
}

export async function register(userData) {
    const res = await api.post('/v1/auth/register', userData);
    return res.data;
}

export async function getProfile() {
    const res = await api.get('/v1/auth/profile');
    return res.data;
}

export async function verifyToken() {
    const res = await api.get('/v1/auth/verify');
    return res.data;
}

// Client Accounts
export async function getConnectedAccounts() {
    const res = await api.get('/v1/client/accounts');
    return res.data;
}

export async function disconnectAccount(accountId) {
    const res = await api.delete(`/v1/client/accounts/${accountId}`);
    return res.data;
}

// Client Dashboard
export async function getClientDashboard() {
    const res = await api.get('/v1/client/dashboard');
    return res.data;
}

// Onboarding
export async function createOnboardingRequest() {
    const res = await api.post('/v1/onboarding/create');
    return res.data;
}

export async function getOnboardingTemplate(accountId) {
    const res = await api.get(`/v1/onboarding/template/${accountId}`);
    return res.data;
}

export async function verifyOnboarding(accountId, roleArn) {
    const res = await api.post(`/v1/onboarding/${accountId}/verify`, { role_arn: roleArn });
    return res.data;
}

export async function getDiscoveryStatus(accountId) {
    const res = await api.get(`/v1/onboarding/${accountId}/discovery`);
    return res.data;
}

export async function connectWithCredentials(accessKey, secretKey, region) {
    const res = await api.post('/v1/onboarding/connect/credentials', {
        access_key: accessKey,
        secret_key: secretKey,
        region: region
    });
    return res.data;
}

// Lab Mode
export async function getInstances(accountId = null) {
    const query = accountId ? `?account_id=${accountId}` : '';
    const res = await api.get(`/v1/lab/instances${query}`);
    return res.data;
}

export async function getInstance(instanceId) {
    const res = await api.get(`/v1/lab/instances/${instanceId}`);
    return res.data;
}

export async function getModels() {
    const res = await api.get('/v1/lab/models');
    return res.data;
}

export async function activateModel(modelId) {
    const res = await api.put(`/v1/lab/models/${modelId}/activate`);
    return res.data;
}

// Admin
export async function getUsers() {
    const res = await api.get('/v1/admin/users');
    return res.data;
}

export async function createClient(clientData) {
    const res = await api.post('/v1/admin/clients', clientData);
    return res.data;
}

export const createUser = createClient; // Alias

// ============================================================================
// Default Export (Axios-style API object)
// ============================================================================

export default api;
