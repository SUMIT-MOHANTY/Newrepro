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

