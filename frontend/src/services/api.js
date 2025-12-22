// Detect production vs development environment
const isProduction = import.meta.env.PROD;

// In production, use relative path '/api' so Nginx handles the proxy
// In development, point directly to localhost:8000
const API_BASE_URL = isProduction
    ? '/api'
    : (import.meta.env.VITE_API_URL || 'http://localhost:8000');

console.log(`🔌 API Connected to: ${API_BASE_URL} (${isProduction ? 'PRODUCTION' : 'DEVELOPMENT'})`);

class ApiError extends Error {
    constructor(message, status, data) {
        super(message);
        this.name = 'ApiError';
        this.status = status;
        this.data = data;
    }
}

// ============================================================================
// HTTP Client
// ============================================================================

async function fetchApi(endpoint, options = {}) {
    const url = `${API_BASE_URL}${endpoint}`;

    // Get token from localStorage
    const token = localStorage.getItem('auth_token');

    const config = {
        headers: {
            'Content-Type': 'application/json',
            ...(token && { 'Authorization': `Bearer ${token}` }),
            ...options.headers,
        },
        ...options,
    };

    try {
        const response = await fetch(url, config);
        const data = await response.json();

        if (!response.ok) {
            throw new ApiError(
                data.detail || 'API request failed',
                response.status,
                data
            );
        }

        return data;
    } catch (error) {
        if (error instanceof ApiError) {
            throw error;
        }
        throw new ApiError(error.message, 0, null);
    }
}

// ============================================================================
// Authentication API
// ============================================================================

export async function login(identifier, password) {
    return fetchApi('/v1/auth/login', {
        method: 'POST',
        body: JSON.stringify({ identifier, password }),
    });
}

export async function register(userData) {
    return fetchApi('/v1/auth/register', {
        method: 'POST',
        body: JSON.stringify(userData),
    });
}

export async function getProfile() {
    return fetchApi('/v1/auth/profile');
}

export async function verifyToken() {
    return fetchApi('/v1/auth/verify');
}

// ============================================================================
// Lab Mode API
// ============================================================================

export async function getInstances(accountId = null) {
    const query = accountId ? `?account_id=${accountId}` : '';
    return fetchApi(`/v1/lab/instances${query}`);
}

export async function getInstance(instanceId) {
    return fetchApi(`/v1/lab/instances/${instanceId}`);
}

export async function assignModelToInstance(instanceId, modelVersion) {
    return fetchApi('/v1/lab/assign-model', {
        method: 'POST',
        body: JSON.stringify({
            instance_id: instanceId,
            model_version: modelVersion,
        }),
    });
}

export async function setPipelineMode(instanceId, pipelineMode) {
    return fetchApi(`/v1/lab/instances/${instanceId}/pipeline-mode`, {
        method: 'PUT',
        body: JSON.stringify({ pipeline_mode: pipelineMode }),
    });
}

export async function toggleShadowMode(instanceId, enabled) {
    return fetchApi(`/v1/lab/instances/${instanceId}/shadow-mode`, {
        method: 'PUT',
        body: JSON.stringify({ is_shadow_mode: enabled }),
    });
}

export async function getModels() {
    return fetchApi('/v1/lab/models');
}

export async function acceptModel(modelId) {
    return fetchApi(`/v1/lab/models/${modelId}/accept`, {
        method: 'PUT'
    });
}

export async function enableModel(modelId) {
    return fetchApi(`/v1/lab/models/${modelId}/enable`, {
        method: 'PUT'
    });
}

export async function activateModel(modelId) {
    return fetchApi(`/v1/lab/models/${modelId}/activate`, {
        method: 'PUT'
    });
}

export async function graduateModel(modelId) {
    return fetchApi(`/v1/lab/models/${modelId}/graduate`, {
        method: 'PUT'
    });
}

export async function rejectModel(modelId) {
    return fetchApi(`/v1/lab/models/${modelId}/reject`, {
        method: 'PUT'
    });
}

export async function uploadModel(formData) {
    // For file uploads, we need to handle headers specially
    // Don't set Content-Type - let browser set it with boundary
    // But we still need the Authorization header
    const token = localStorage.getItem('auth_token');
    const url = `${API_BASE_URL}/v1/lab/models/upload`;

    try {
        const response = await fetch(url, {
            method: 'POST',
            headers: {
                ...(token && { 'Authorization': `Bearer ${token}` }),
                // Don't set Content-Type for FormData - browser will add it with boundary
            },
            body: formData,
        });

        const data = await response.json();

        if (!response.ok) {
            throw new ApiError(
                data.detail || 'Upload failed',
                response.status,
                data
            );
        }

        return data;
    } catch (error) {
        if (error instanceof ApiError) {
            throw error;
        }
        throw new ApiError(error.message, 0, null);
    }
}

export async function getExperimentLogs(instanceId, limit = 50) {
    return fetchApi(`/v1/lab/experiments/${instanceId}?limit=${limit}`);
}

export async function getModelPerformance(modelId) {
    return fetchApi(`/v1/lab/experiments/model/${modelId}`);
}

export async function getPipelineStatus(instanceId) {
    return fetchApi(`/v1/lab/pipeline-status/${instanceId}`);
}

// ============================================================================
// Account Management API
// ============================================================================

export async function getAccounts() {
    return fetchApi('/v1/lab/accounts');
}

export async function createAccount(accountData) {
    return fetchApi('/v1/lab/accounts', {
        method: 'POST',
        body: JSON.stringify(accountData),
    });
}

export async function updateAccount(accountId, accountData) {
    return fetchApi(`/v1/lab/accounts/${accountId}`, {
        method: 'PUT',
        body: JSON.stringify(accountData),
    });
}

export async function validateAccountAccess(accountId) {
    return fetchApi(`/v1/lab/accounts/${accountId}/validate`);
}

// ============================================================================
// Live Operations API
// ============================================================================

export async function getLiveMetrics() {
    return fetchApi('/v1/metrics/live');
}

export async function getActivityFeed(limit = 20) {
    return fetchApi(`/v1/metrics/activity?limit=${limit}`);
}

export async function getPipelineStats() {
    return fetchApi('/v1/metrics/pipeline-stats');
}

// ============================================================================
// Client Management API (for Admin)
// ============================================================================

export async function getClients() {
    return fetchApi('/v1/admin/clients');
}

export async function createClient(clientData) {
    return fetchApi('/v1/admin/clients', {
        method: 'POST',
        body: JSON.stringify(clientData),
    });
}

export async function getClientDetails(clientId) {
    return fetchApi(`/v1/admin/clients/${clientId}`);
}

// ============================================================================
// User Management API (for Admin)
// ============================================================================

export async function getUsers() {
    return fetchApi('/v1/admin/users');
}

export async function updateUserStatus(userId, isActive) {
    return fetchApi(`/v1/admin/users/${userId}/status`, {
        method: 'PUT',
        body: JSON.stringify({ is_active: isActive }),
    });
}

export async function updateUserRole(userId, role) {
    return fetchApi(`/v1/admin/users/${userId}/role`, {
        method: 'PUT',
        body: JSON.stringify({ role }),
    });
}

export async function deleteUser(userId) {
    return fetchApi(`/v1/admin/users/${userId}`, {
        method: 'DELETE',
    });
}


export const createUser = createClient;

// ============================================================================
// WebSocket Connection
// ============================================================================

export function connectWebSocket(instanceId, onMessage, onError) {
    const wsUrl = API_BASE_URL.replace('http', 'ws');
    const ws = new WebSocket(`${wsUrl}/v1/ws/lab/${instanceId}`);

    ws.onmessage = (event) => {
        try {
            const data = JSON.parse(event.data);
            onMessage(data);
        } catch (error) {
            console.error('WebSocket parse error:', error);
        }
    };

    ws.onerror = (error) => {
        console.error('WebSocket error:', error);
        if (onError) onError(error);
    };

    ws.onopen = () => {
        console.log('WebSocket connected to instance:', instanceId);
    };

    ws.onclose = () => {
        console.log('WebSocket disconnected from instance:', instanceId);
    };

    return ws;
}

// ============================================================================
// Evaluation API (Manual Trigger)
// ============================================================================

export async function evaluateInstance(instanceId) {
    return fetchApi(`/v1/lab/instances/${instanceId}/evaluate`, {
        method: 'POST',
    });
}

// ============================================================================
// Admin API - System Monitoring
// ============================================================================

/**
 * Get system-wide health overview
 * @returns {Promise<Object>} System overview with all components
 */
export async function getSystemOverview() {
    return fetchApi('/v1/admin/health/overview');
}

/**
 * Get logs for a specific component
 * @param {string} component - Component name (web_scraper, price_scraper, etc.)
 * @param {number} limit - Number of logs to return (default: 5)
 * @param {string} level - Filter by log level (optional)
 * @returns {Promise<Object>} Component health and logs
 */
export async function getComponentLogs(component, limit = 5, level = null) {
    const params = new URLSearchParams({ limit: limit.toString() });
    if (level) params.append('level', level);

    return fetchApi(`/v1/admin/logs/${component}?${params.toString()}`);
}

/**
 * Get recent logs from all components
 * @param {number} limit - Number of logs to return (default: 20)
 * @param {string} level - Filter by log level (optional)
 * @returns {Promise<Array>} Recent log entries
 */
export async function getRecentLogs(limit = 20, level = null) {
    const params = new URLSearchParams({ limit: limit.toString() });
    if (level) params.append('level', level);

    return fetchApi(`/v1/admin/logs/all/recent?${params.toString()}`);
}

/**
 * Get log statistics for the last 24 hours
 * @returns {Promise<Object>} Log statistics
 */
export async function getLogStatistics() {
    return fetchApi('/v1/admin/stats');
}

/**
 * Clean up old logs
 * @param {number} days - Number of days to keep (default: 7)
 * @returns {Promise<Object>} Cleanup result
 */
export async function cleanupOldLogs(days = 7) {
    return fetchApi(`/v1/admin/logs/cleanup?days=${days}`, {
        method: 'POST'
    });
}

// ============================================================================
// V3.1 Production API (Waste, Governance, Approvals)
// ============================================================================

export async function getWaste() {
    return fetchApi('/v1/waste');
}

export async function triggerWasteScan() {
    return fetchApi('/v1/waste/scan', { method: 'POST' });
}

export async function getSecurityAudit() {
    return fetchApi('/v1/governance/audit');
}

export async function getUnauthorizedInstances() {
    return fetchApi('/v1/governance/unauthorized');
}

export async function getPendingApprovals() {
    return fetchApi('/v1/approvals/pending');
}

export async function approveRequest(requestId) {
    return fetchApi(`/v1/approvals/${requestId}/approve`, { method: 'POST' });
}

export async function rejectRequest(requestId) {
    return fetchApi(`/v1/approvals/${requestId}/reject`, { method: 'POST' });
}

export async function setSpotMarketStatus(disabled) {
    return fetchApi('/v1/admin/system/spot-status', {
        method: 'PUT',
        body: JSON.stringify({ disabled })
    });
}

export async function triggerRebalance() {
    return fetchApi('/v1/admin/system/rebalance', {
        method: 'POST'
    });
}

// ============================================================================
// Client Onboarding
// ============================================================================

export async function createOnboardingRequest() {
    return fetchApi('/v1/onboarding/create', { method: 'POST' });
}

export async function getOnboardingTemplate(accountId) {
    return fetchApi(`/v1/onboarding/template/${accountId}`);
}

export async function verifyOnboarding(accountId, roleArn) {
    return fetchApi(`/v1/onboarding/${accountId}/verify`, {
        method: 'POST',
        body: JSON.stringify({ role_arn: roleArn })
    });
}

export async function getDiscoveryStatus(accountId) {
    return fetchApi(`/v1/onboarding/${accountId}/discovery`);
}

// ============================================================================
// Helper Functions
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

// Export API client
export default {
    // Auth
    login,
    register,
    getProfile,
    verifyToken,
    setAuthToken,
    clearAuthToken,
    getAuthToken,

    // Lab Mode
    getInstances,
    getInstance,
    assignModelToInstance,
    setPipelineMode,
    toggleShadowMode,
    getModels,
    acceptModel,
    graduateModel,
    enableModel,
    activateModel,
    rejectModel,
    uploadModel,
    getExperimentLogs,
    getModelPerformance,
    getPipelineStatus,
    evaluateInstance,

    // Accounts
    getAccounts,
    createAccount,
    updateAccount,
    validateAccountAccess,

    // Live Operations
    getLiveMetrics,
    getActivityFeed,
    getPipelineStats,

    // Admin - System Monitoring
    getSystemOverview,
    getComponentLogs,
    getRecentLogs,
    getLogStatistics,
    cleanupOldLogs,

    // Admin
    getClients,
    createClient,
    getClientDetails,

    // User Management
    getUsers,
    createUser,
    updateUserStatus,
    updateUserRole,
    deleteUser,

    // Waste & Governance
    getWaste,
    triggerWasteScan,
    getSecurityAudit,
    getUnauthorizedInstances,
    getPendingApprovals,
    approveRequest,
    rejectRequest,
    setSpotMarketStatus,
    triggerRebalance,

    // Client Onboarding
    createOnboardingRequest,
    getOnboardingTemplate,
    verifyOnboarding,
    getDiscoveryStatus,

    // WebSocket
    connectWebSocket,

    // Client Dashboard
    getClientDashboard,

    // Admin System Controls
    getSpotMarketStatus,
    getSystemHealth,
};

// ============================================================================
// Client Dashboard API
// ============================================================================

export async function getClientDashboard() {
    return fetchApi('/v1/client/dashboard');
}

export async function getSpotMarketStatus() {
    return fetchApi('/v1/admin/system/spot-market');
}

export async function getSystemHealth() {
    return fetchApi('/v1/admin/health/overview');
}
