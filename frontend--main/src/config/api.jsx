// ==============================================================================
// API CONFIGURATION - Auto-Detection
// ==============================================================================

// Auto-detect backend URL based on current location
const getAutoDetectedURL = () => {
  // In browser environment
  if (typeof window !== 'undefined') {
    const { protocol, hostname } = window.location;

    // If running on localhost, use localhost backend
    if (hostname === 'localhost' || hostname === '127.0.0.1') {
      return 'http://localhost:5000';
    }

    // Otherwise, use same hostname as frontend with port 5000
    return `${protocol}//${hostname}:5000`;
  }

  // Fallback for server-side rendering
  return 'http://localhost:5000';
};

// Support environment variable override for build time
const ENV_API_URL = import.meta.env.VITE_API_URL;

export const API_CONFIG = {
  BASE_URL: ENV_API_URL || getAutoDetectedURL(),
};
