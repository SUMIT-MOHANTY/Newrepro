import { clearDraftProjects } from './draftProjects';

const PUBLIC_AUTH_PATHS = new Set(['/login', '/signup', '/', '/sso/callback']);

let isAuthRedirectInProgress = false;

export const clearTenantScopedState = () => {
    localStorage.removeItem('status_dashboard_selected_project_key');
    localStorage.removeItem('status_dashboard_task_token_cache');
    localStorage.removeItem('active_org');
    localStorage.removeItem('active_analysis_job_id');
    localStorage.removeItem('active_analysis_project_key');
    localStorage.removeItem('governancePassed');
    localStorage.removeItem('governanceResult');
    localStorage.removeItem('governanceContext');
    localStorage.removeItem('repoContext');
    localStorage.removeItem('analysisResult');
    sessionStorage.removeItem('governanceResult');
    sessionStorage.removeItem('governanceContext');
    sessionStorage.removeItem('brd_project_states');
    sessionStorage.removeItem('dsuite_return_path');
    sessionStorage.removeItem('dsuite_return_project');
    clearDraftProjects();
};

export const clearAuthData = () => {
    localStorage.removeItem('token');
    localStorage.removeItem('is_super_admin');
    clearTenantScopedState();
};

// Store the redirect path for use by React Router
let pendingRedirectPath = null;

export const getPendingRedirect = () => {
    const path = pendingRedirectPath;
    pendingRedirectPath = null;
    return path;
};

// Safe check for public paths without using window.location
const isPublicPath = (path) => {
    if (!path) return false;
    return PUBLIC_AUTH_PATHS.has(path);
};

export const logoutAndRedirect = (currentPath) => {
    clearAuthData();

    // Use provided currentPath or default to root
    const path = currentPath || '/';
    
    if (isAuthRedirectInProgress) return;
    if (isPublicPath(path)) return;

    isAuthRedirectInProgress = true;
    // Store redirect path instead of using window.location.replace
    // This allows React Router's Navigate component to handle the redirect
    pendingRedirectPath = '/login';
    // Dispatch a custom event that components can listen for
    if (typeof window !== 'undefined') {
        window.dispatchEvent(new CustomEvent('auth:redirect-required', { detail: { path: '/login' } }));
    }
};

// Get auth token from localStorage
export const getAuthToken = () => {
    if (typeof window === 'undefined') return null;
    return localStorage.getItem('token');
};

// Set auth token in localStorage
export const setAuthToken = (token) => {
    if (typeof window === 'undefined') return;
    localStorage.setItem('token', token);
};

// Check if user is authenticated
export const isAuthenticated = () => {
    const token = getAuthToken();
    return !!token && !isTokenExpired(token);
};

// Decode JWT token to check expiration
export const getTokenExpiration = (token) => {
    if (!token) return null;
    
    try {
        const base64Url = token.split('.')[1];
        const base64 = base64Url.replace(/-/g, '+').replace(/_/g, '/');
        const jsonPayload = decodeURIComponent(
            atob(base64)
                .split('')
                .map((c) => '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2))
                .join('')
        );
        const payload = JSON.parse(jsonPayload);
        return payload.exp ? payload.exp * 1000 : null; // Convert to milliseconds
    } catch (error) {
        console.error('[Auth] Failed to decode token:', error);
        return null;
    }
};

// Check if token is expired or will expire soon
export const isTokenExpired = (token, bufferMinutes = 5) => {
    const expiration = getTokenExpiration(token);
    if (!expiration) return true;
    
    const now = Date.now();
    const bufferMs = bufferMinutes * 60 * 1000;
    return now >= (expiration - bufferMs);
};

// Get time until token expires (in minutes)
export const getTimeUntilExpiration = (token) => {
    const expiration = getTokenExpiration(token);
    if (!expiration) return 0;
    
    const now = Date.now();
    const diff = expiration - now;
    return Math.floor(diff / 60000); // Convert to minutes
};
