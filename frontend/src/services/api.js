/**
 * API Service for Spot Optimizer Platform
 * Handles all backend API calls
 */

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

class ApiError extends Error {
    constructor(message, status, data) {
        super(message);
        this.name = 'ApiError';
        this.status = status;
        this.data = data;
    }
}

async function fetchApi(endpoint, options = {}) {
    const url = `${API_BASE_URL}${endpoint}`;
    const config = {
        headers: {
            'Content-Type': 'application/json',
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
        if (error instanceof ApiError) throw error;
        throw new ApiError('Network error', 0, { message: error.message });
    }
}

// Health Check
export async function healthCheck() {
    return fetchApi('/health');
}

// Sandbox API
export async function createSandboxSession(sessionData) {
    return fetchApi('/api/v1/sandbox/sessions', {
        method: 'POST',
        body: JSON.stringify(sessionData),
    });
}

export async function getSandboxSession(sessionId) {
    return fetchApi(`/api/v1/sandbox/sessions/${sessionId}`);
}

export async function evaluateInstance(sessionId) {
    return fetchApi(`/api/v1/sandbox/sessions/${sessionId}/evaluate`, {
        method: 'POST',
    });
}

export async function getSessionActions(sessionId) {
    return fetchApi(`/api/v1/sandbox/sessions/${sessionId}/actions`);
}

export async function getSessionSavings(sessionId) {
    return fetchApi(`/api/v1/sandbox/sessions/${sessionId}/savings`);
}

export async function endSandboxSession(sessionId) {
    return fetchApi(`/api/v1/sandbox/sessions/${sessionId}`, {
        method: 'DELETE',
    });
}

// Instance Evaluation (non-sandbox)
export async function evaluateInstanceDirect(instanceData) {
    return fetchApi('/api/v1/evaluate', {
        method: 'POST',
        body: JSON.stringify(instanceData),
    });
}

export { ApiError };
