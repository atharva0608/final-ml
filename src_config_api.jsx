// ==============================================================================
// API CONFIGURATION - AUTO-DETECTION
// ==============================================================================
// This configuration automatically detects the correct backend URL:
// - In production (EC2): Uses the EC2 instance's public IP
// - In development: Uses localhost:5000
// - Can be overridden with VITE_API_URL environment variable during build
// ==============================================================================

// Method 1: Environment variable set during build (highest priority)
const ENV_API_URL = import.meta.env.VITE_API_URL;

// Method 2: Auto-detect from current browser location
const getAutoDetectedURL = () => {
  // If we're in the browser
  if (typeof window !== 'undefined') {
    const { protocol, hostname } = window.location;

    // If running on localhost (development), connect to localhost:5000
    if (hostname === 'localhost' || hostname === '127.0.0.1') {
      return 'http://localhost:5000';
    }

    // Otherwise, use the current hostname with port 5000 (production on EC2)
    return `${protocol}//${hostname}:5000`;
  }

  // Fallback for SSR or non-browser environments
  return 'http://localhost:5000';
};

// Final configuration with priority:
// 1. Environment variable (VITE_API_URL) - set during build
// 2. Auto-detected from window.location
export const API_CONFIG = {
  BASE_URL: ENV_API_URL || getAutoDetectedURL(),
};

// Log the configuration in development
if (import.meta.env.DEV) {
  console.log('[API Config] Using BASE_URL:', API_CONFIG.BASE_URL);
  console.log('[API Config] Source:', ENV_API_URL ? 'Environment Variable' : 'Auto-detected');
}
