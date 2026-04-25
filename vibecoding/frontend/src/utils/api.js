/**
 * API utility functions for making authenticated requests.
 * These functions use axios defaults for authentication headers,
 * ensuring that refreshed tokens are automatically used.
 */

import axios from 'axios';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '/vibecoding';

/**
 * Make an authenticated API request.
 * Uses axios defaults for Authorization header, which is automatically
 * updated when tokens are refreshed by the interceptor.
 * 
 * @param {string} method - HTTP method (GET, POST, PUT, DELETE, etc.)
 * @param {string} endpoint - API endpoint (e.g., '/api/projects')
 * @param {object} options - Additional axios options (data, params, etc.)
 * @returns {Promise} Axios response
 */
export async function apiRequest(method, endpoint, options = {}) {
  const url = endpoint.startsWith('http') ? endpoint : `${API_BASE_URL}${endpoint}`;
  
  return axios({
    method,
    url,
    ...options
  });
}

/**
 * Convenience methods for common HTTP verbs
 */
export const api = {
  get: (endpoint, options = {}) => apiRequest('GET', endpoint, options),
  post: (endpoint, data, options = {}) => apiRequest('POST', endpoint, { ...options, data }),
  put: (endpoint, data, options = {}) => apiRequest('PUT', endpoint, { ...options, data }),
  delete: (endpoint, options = {}) => apiRequest('DELETE', endpoint, options),
  patch: (endpoint, data, options = {}) => apiRequest('PATCH', endpoint, { ...options, data }),
};

export default api;
