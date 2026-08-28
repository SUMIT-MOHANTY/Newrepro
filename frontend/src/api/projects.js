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

const removeCachedTaskToken = (projectKey) => {
    if (!projectKey) return;
    try {
        const raw = localStorage.getItem(TASK_TOKEN_STORAGE_KEY);
        if (!raw) return;
        const parsed = JSON.parse(raw);
        if (!parsed || typeof parsed !== 'object' || !parsed[projectKey]) return;
        delete parsed[projectKey];
        localStorage.setItem(TASK_TOKEN_STORAGE_KEY, JSON.stringify(parsed));
    } catch {
        // Ignore cache cleanup failures.
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
    if (res.status === 404) return null;
    if (res.status === 403) {
        const errPayload = await res.json().catch(() => ({}));
        if (errPayload?.detail === 'CROSS_TENANT_PROJECT_ACCESS_DENIED' || (typeof errPayload?.detail === 'string' && errPayload.detail.includes('CROSS_TENANT_PROJECT_ACCESS_DENIED'))) {
            localStorage.removeItem('status_dashboard_selected_project_key');
            removeCachedTaskToken(projectKey);
            throw new Error('Project belongs to another organization. Please select a valid project.');
        }
    }
    if (!res.ok) throw new Error('Failed to fetch roadmap step');
    return res.json();
};

export const deleteProjectByIdentifier = async (identifier) => {
    if (!identifier) throw new Error('Project identifier is required');

    const headers = getAuthHeaders();
    const res = await fetch(API_ENDPOINTS.GOVERNANCE_DELETE(identifier), {
        method: 'DELETE',
        headers,
    });

    if (res.status === 401) {
        throw new Error('Unauthorized');
    }

    const payload = await res.json().catch(() => ({}));
    if (res.status === 403) {
        if (payload?.detail === 'CROSS_TENANT_PROJECT_ACCESS_DENIED' || (typeof payload?.detail === 'string' && payload.detail.includes('CROSS_TENANT_PROJECT_ACCESS_DENIED'))) {
            localStorage.removeItem('status_dashboard_selected_project_key');
            removeCachedTaskToken(identifier);
            throw new Error('Project belongs to another organization. Please select a valid project.');
        }
    }

    if (!res.ok) {
        throw new Error(payload?.detail || 'Failed to delete project');
    }

    removeCachedTaskToken(identifier);
    if (payload?.project_token && payload.project_token !== identifier) {
        removeCachedTaskToken(payload.project_token);
    }

    return payload;
};
