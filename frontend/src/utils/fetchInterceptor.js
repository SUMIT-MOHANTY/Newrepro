import { logoutAndRedirect } from './auth';

let interceptorInstalled = false;
let consecutiveUnauthorizedCount = 0;
const UNAUTHORIZED_THRESHOLD = 2; // Only logout after 2 consecutive 401s

// Track which endpoints should NOT trigger logout (background/polling endpoints)
const NON_CRITICAL_ENDPOINTS = [
    '/agent/status',
    '/coordination/monitor',
    '/projects/history',
    '/governance/history',
];

const isNonCriticalEndpoint = (url) => {
    if (!url) return false;
    return NON_CRITICAL_ENDPOINTS.some(endpoint => url.includes(endpoint));
};

export const installUnauthorizedResponseInterceptor = () => {
    if (interceptorInstalled) return;
    if (typeof window === 'undefined' || typeof window.fetch !== 'function') return;

    const nativeFetch = window.fetch.bind(window);

    window.fetch = async (...args) => {
        const response = await nativeFetch(...args);

        if (response.status === 401) {
            const url = args[0]?.toString() || '';
            
            // Don't logout for non-critical endpoints (background polling, etc.)
            if (isNonCriticalEndpoint(url)) {
                console.warn(`[Auth] 401 from non-critical endpoint: ${url} - not logging out`);
                return response;
            }

            // Increment consecutive unauthorized count
            consecutiveUnauthorizedCount++;
            
            // Only logout after multiple consecutive 401s to avoid false positives
            if (consecutiveUnauthorizedCount >= UNAUTHORIZED_THRESHOLD) {
                console.warn(`[Auth] ${consecutiveUnauthorizedCount} consecutive 401s - logging out`);
                logoutAndRedirect();
            } else {
                console.warn(`[Auth] 401 detected (${consecutiveUnauthorizedCount}/${UNAUTHORIZED_THRESHOLD}) - not logging out yet`);
            }
        } else if (response.ok) {
            // Reset counter on successful response
            consecutiveUnauthorizedCount = 0;
        }

        return response;
    };

    interceptorInstalled = true;
};


