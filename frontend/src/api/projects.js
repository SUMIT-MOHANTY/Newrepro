import { API_ENDPOINTS } from '../config';

const TASK_TOKEN_STORAGE_KEY = 'status_dashboard_task_token_cache';

const getAuthHeaders = () => {
    const token = localStorage.getItem('token');
    return { Authorization: `Bearer ${token}` };
};

const getCachedTaskToken = (projectKey) => {
    if (!projectKey) return null;
    try {
        const raw = localStorage.getItem(TASK_TOKEN_STORAGE_KEY);
        if (!raw) return null;
        const parsed = JSON.parse(raw);
        if (!parsed || typeof parsed !== 'object') return null;

        const entry = parsed[projectKey];
        if (!entry || !entry.token) return null;

        if (entry.expiresAt) {
            const now = Math.floor(Date.now() / 1000);
            if (entry.expiresAt <= now) {
                delete parsed[projectKey];
                localStorage.setItem(TASK_TOKEN_STORAGE_KEY, JSON.stringify(parsed));
                return null;
            }
        }
        return entry.token;
    } catch {
        return null;
    }
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
    const taskToken = getCachedTaskToken(projectKey);
    if (taskToken) headers['x-task-token'] = taskToken;
    const res = await fetch(API_ENDPOINTS.GOVERNANCE_ROADMAP_STEP(projectKey), { headers });
    if (!res.ok) throw new Error('Failed to fetch roadmap step');
    return res.json();
};
