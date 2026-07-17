import { clearDraftProjects } from './draftProjects';

const PUBLIC_AUTH_PATHS = new Set(['/login', '/signup', '/', '/sso/callback']);

let isAuthRedirectInProgress = false;

export const clearAuthData = () => {
    localStorage.removeItem('token');
    localStorage.removeItem('governancePassed');
    localStorage.removeItem('governanceResult');
    localStorage.removeItem('governanceContext');
    sessionStorage.removeItem('governanceResult');
    sessionStorage.removeItem('governanceContext');
    sessionStorage.removeItem('brd_project_states');
    clearDraftProjects();
};

export const logoutAndRedirect = () => {
    clearAuthData();

    if (typeof window === 'undefined') return;
    if (isAuthRedirectInProgress) return;

    const currentPath = window.location.pathname || '/';
    if (PUBLIC_AUTH_PATHS.has(currentPath)) return;

    isAuthRedirectInProgress = true;
    window.location.replace('/login');
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

