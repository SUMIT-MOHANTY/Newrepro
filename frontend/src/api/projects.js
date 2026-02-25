import { API_ENDPOINTS } from '../config';

const getAuthHeaders = () => {
    const token = localStorage.getItem('token');
    return { Authorization: `Bearer ${token}` };
};

export const fetchProjectsData = async () => {
    const headers = getAuthHeaders();
    if (!headers.Authorization.includes('null') && !headers.Authorization.includes('undefined')) {
        const [govRes, histRes] = await Promise.all([
            fetch(API_ENDPOINTS.GOVERNANCE_HISTORY, { headers }),
            fetch(API_ENDPOINTS.HISTORY, { headers }),
        ]);

        if (govRes.status === 401 || histRes.status === 401) {
            throw new Error('Unauthorized');
        }

        const govPayload = govRes.ok ? await govRes.json() : {};
        const historyPayload = histRes.ok ? await histRes.json() : [];

        return { govPayload, historyPayload };
    }
    throw new Error('No token found');
};

export const fetchRoadmapStep = async (projectKey) => {
    if (!projectKey) return null;
    const headers = getAuthHeaders();
    const res = await fetch(API_ENDPOINTS.GOVERNANCE_ROADMAP_STEP(projectKey), { headers });
    if (!res.ok) throw new Error('Failed to fetch roadmap step');
    return res.json();
};
