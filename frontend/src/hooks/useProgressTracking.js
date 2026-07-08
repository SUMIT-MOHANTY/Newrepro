import { useEffect } from 'react';
import { useLocation } from 'react-router-dom';
import { API_BASE_URL } from '../config';

/**
 * Hook to automatically track user's progress (last visited page)
 * @param {string} projectToken - Current project token (optional)
 * @param {boolean} enabled - Whether tracking is enabled (default: true)
 */
export const useProgressTracking = (projectToken = null, enabled = true) => {
    const location = useLocation();

    useEffect(() => {
        if (!enabled) return;

        const updateProgress = async () => {
            try {
                const token = localStorage.getItem('token');
                if (!token) return; // User not logged in

                const params = new URLSearchParams();
                params.append('page_path', location.pathname);
                if (projectToken) {
                    params.append('project_token', projectToken);
                }

                await fetch(`${API_BASE_URL}/users/me/progress?${params.toString()}`, {
                    method: 'PUT',
                    headers: {
                        'Authorization': `Bearer ${token}`,
                    },
                });
            } catch (error) {
                // Silently fail - progress tracking is not critical
                console.debug('Progress tracking failed:', error);
            }
        };

        // Debounce the update to avoid too many requests
        const timeoutId = setTimeout(updateProgress, 1000);

        return () => clearTimeout(timeoutId);
    }, [location.pathname, projectToken, enabled]);
};

/**
 * Get user's last visited page
 * @returns {Promise<{last_page_path: string, last_project_token: string}>}
 */
export const getUserProgress = async () => {
    try {
        const token = localStorage.getItem('token');
        if (!token) return null;

        const response = await fetch(`${API_BASE_URL}/users/me/progress`, {
            headers: {
                'Authorization': `Bearer ${token}`,
            },
        });

        if (!response.ok) return null;

        return await response.json();
    } catch (error) {
        console.error('Failed to get user progress:', error);
        return null;
    }
};
