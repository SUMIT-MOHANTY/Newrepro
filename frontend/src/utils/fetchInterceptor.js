import { logoutAndRedirect } from './auth';

let interceptorInstalled = false;

export const installUnauthorizedResponseInterceptor = () => {
    if (interceptorInstalled) return;
    if (typeof window === 'undefined' || typeof window.fetch !== 'function') return;

    const nativeFetch = window.fetch.bind(window);

    window.fetch = async (...args) => {
        const response = await nativeFetch(...args);

        if (response.status === 401) {
            logoutAndRedirect();
        }

        return response;
    };

    interceptorInstalled = true;
};

