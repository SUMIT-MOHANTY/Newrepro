import { API_BASE_URL, API_ENDPOINTS } from '../config';
import { useAuthStore } from '../stores/authStore';

// Create axios-like API client with JWT interceptors
class AuthAPIClient {
  constructor() {
    this.baseURL = API_BASE_URL;
    this.defaultHeaders = {
      'Content-Type': 'application/json',
    };
  }

  // Get current auth token from store
  getAuthToken() {
    const { accessToken } = useAuthStore.getState();
    return accessToken;
  }

  // Build request headers with optional auth
  buildHeaders(requireAuth = true) {
    const headers = { ...this.defaultHeaders };
    
    if (requireAuth) {
      const token = this.getAuthToken();
      if (token) {
        headers['Authorization'] = `Bearer ${token}`;
      }
    }
    
    return headers;
  }

  // Generic request method with JWT injection
  async request(endpoint, options = {}) {
    const { requireAuth = true, ...fetchOptions } = options;
    
    const url = endpoint.startsWith('http') ? endpoint : `${this.baseURL}${endpoint}`;
    
    const headers = {
      ...this.buildHeaders(requireAuth),
      ...fetchOptions.headers,
    };

    const config = {
      ...fetchOptions,
      headers,
    };

    try {
      const response = await fetch(url, config);
      
      // Handle 401 Unauthorized - token expired or invalid
      if (response.status === 401) {
        // Try to refresh token
        const refreshed = await this.refreshToken();
        if (refreshed) {
          // Retry the original request with new token
          const retryHeaders = {
            ...fetchOptions.headers,
            'Authorization': `Bearer ${this.getAuthToken()}`,
          };
          const retryResponse = await fetch(url, {
            ...fetchOptions,
            headers: retryHeaders,
          });
          return this.handleResponse(retryResponse);
        } else {
          // Refresh failed, logout user
          useAuthStore.getState().logout();
          // Return a special error that the caller can handle for navigation
          const error = new Error('Session expired. Please login again.');
          error.status = 401;
          error.requiresRedirect = true;
          throw error;
        }
      }

      return this.handleResponse(response);
    } catch (error) {
      console.error('[AuthAPI] Request failed:', error);
      throw error;
    }
  }

  // Handle API response
  async handleResponse(response) {
    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      const error = new Error(errorData.detail || errorData.message || `HTTP ${response.status}`);
      error.status = response.status;
      error.data = errorData;
      throw error;
    }
    
    // Handle empty responses
    if (response.status === 204) {
      return null;
    }
    
    return response.json();
  }

  // POST request
  async post(endpoint, data, options = {}) {
    return this.request(endpoint, {
      method: 'POST',
      body: JSON.stringify(data),
      ...options,
    });
  }

  // GET request
  async get(endpoint, options = {}) {
    return this.request(endpoint, {
      method: 'GET',
      ...options,
    });
  }

  // PUT request
  async put(endpoint, data, options = {}) {
    return this.request(endpoint, {
      method: 'PUT',
      body: JSON.stringify(data),
      ...options,
    });
  }

  // PATCH request
  async patch(endpoint, data, options = {}) {
    return this.request(endpoint, {
      method: 'PATCH',
      body: JSON.stringify(data),
      ...options,
    });
  }

  // DELETE request
  async delete(endpoint, options = {}) {
    return this.request(endpoint, {
      method: 'DELETE',
      ...options,
    });
  }

  // Refresh access token using refresh token
  async refreshToken() {
    const { refreshToken } = useAuthStore.getState();
    
    if (!refreshToken) {
      return false;
    }

    try {
      const response = await fetch(`${this.baseURL}/auth/token/refresh`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ refresh_token: refreshToken }),
      });

      if (!response.ok) {
        return false;
      }

      const data = await response.json();
      
      // Update tokens in store
      useAuthStore.getState().updateTokens({
        access_token: data.access_token,
        refresh_token: data.refresh_token || refreshToken,
        expires_in: data.expires_in,
      });

      return true;
    } catch (error) {
      console.error('[AuthAPI] Token refresh failed:', error);
      return false;
    }
  }

  // ==================== AUTH ENDPOINTS ====================

  // Login with email/password
  async login(username, password) {
    const formData = new FormData();
    formData.append('username', username);
    formData.append('password', password);

    const response = await fetch(API_ENDPOINTS.TOKEN, {
      method: 'POST',
      body: formData,
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(errorData.detail || 'Invalid credentials');
    }

    const data = await response.json();
    
    // Check if organization selection is required
    if (data.requires_selection) {
      return {
        requiresSelection: true,
        tempToken: data.access_token,
        organizations: data.organizations || [],
      };
    }

    // Store tokens and user data
    useAuthStore.getState().login(
      {
        access_token: data.access_token,
        refresh_token: data.refresh_token,
        expires_in: data.expires_in || 3600,
      },
      data.user || null
    );

    return {
      requiresSelection: false,
      accessToken: data.access_token,
      user: data.user,
    };
  }

  // Register new user
  async register(userData) {
    const response = await fetch(API_ENDPOINTS.USERS, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(userData),
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(errorData.detail || 'Registration failed');
    }

    const data = await response.json();
    
    // If registration returns tokens, auto-login
    if (data.access_token) {
      useAuthStore.getState().login(
        {
          access_token: data.access_token,
          refresh_token: data.refresh_token,
          expires_in: data.expires_in || 3600,
        },
        data.user || null
      );
    }

    return data;
  }

  // Logout user
  async logout() {
    const { accessToken } = useAuthStore.getState();
    
    // Call logout endpoint if token exists
    if (accessToken) {
      try {
        await fetch(`${this.baseURL}/auth/logout`, {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${accessToken}`,
          },
        });
      } catch (error) {
        console.warn('[AuthAPI] Logout endpoint call failed:', error);
      }
    }

    // Clear local auth state
    useAuthStore.getState().logout();
  }

  // Get current user profile
  async getCurrentUser() {
    return this.get(API_ENDPOINTS.USERS_ME);
  }

  // Update user profile
  async updateUser(userData) {
    return this.put(API_ENDPOINTS.USERS_ME, userData);
  }

  // Change password
  async changePassword(passwordData) {
    return this.post(`${this.baseURL}/users/me/password`, passwordData);
  }

  // Delete user account
  async deleteAccount() {
    return this.delete(API_ENDPOINTS.USERS_ME);
  }

  // Request password reset
  async forgotPassword(email) {
    const response = await fetch(API_ENDPOINTS.FORGOT_PASSWORD, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ email }),
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(errorData.detail || 'Failed to send reset email');
    }

    return response.json();
  }

  // Confirm password reset
  async resetPassword(token, newPassword) {
    const response = await fetch(API_ENDPOINTS.RESET_PASSWORD, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ token, new_password: newPassword }),
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(errorData.detail || 'Failed to reset password');
    }

    return response.json();
  }

  // Select organization (for multi-org users)
  async selectOrganization(orgId, tempToken) {
    const response = await fetch(`${this.baseURL}/auth/select-organization`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${tempToken}`,
      },
      body: JSON.stringify({ organization_id: orgId }),
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(errorData.detail || 'Failed to select organization');
    }

    const data = await response.json();
    
    // Store final tokens
    useAuthStore.getState().login(
      {
        access_token: data.access_token,
        refresh_token: data.refresh_token,
        expires_in: data.expires_in || 3600,
      },
      data.user || null
    );

    return data;
  }

  // Start SSO login - returns the auth URL for the caller to handle navigation
  async startSSO(email, nextUrl = null) {
    const response = await fetch(API_ENDPOINTS.SSO_START, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        email: email.trim().toLowerCase(),
        next: nextUrl || undefined,
      }),
    });

    const data = await response.json().catch(() => ({}));
    
    if (!response.ok || !data.auth_url) {
      throw new Error(data.detail || 'SSO is not configured for this account');
    }

    return data;
  }
}

// Create singleton instance
export const authAPI = new AuthAPIClient();

// Export individual methods for convenience
export const login = (username, password) => authAPI.login(username, password);
export const register = (userData) => authAPI.register(userData);
export const logout = () => authAPI.logout();
export const getCurrentUser = () => authAPI.getCurrentUser();
export const updateUser = (userData) => authAPI.updateUser(userData);
export const changePassword = (passwordData) => authAPI.changePassword(passwordData);
export const deleteAccount = () => authAPI.deleteAccount();
export const forgotPassword = (email) => authAPI.forgotPassword(email);
export const resetPassword = (token, newPassword) => authAPI.resetPassword(token, newPassword);
export const selectOrganization = (orgId, tempToken) => authAPI.selectOrganization(orgId, tempToken);
export const startSSO = (email, nextUrl) => authAPI.startSSO(email, nextUrl);
export const refreshToken = () => authAPI.refreshToken();

export default authAPI;
