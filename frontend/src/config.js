// API Configuration
// Uses environment variables with fallback defaults

export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

// API Endpoints
export const API_ENDPOINTS = {
    // Auth
    TOKEN: `${API_BASE_URL}/token`,
    USERS: `${API_BASE_URL}/users/`,
    USERS_ME: `${API_BASE_URL}/users/me`,

    // Documents
    DOCUMENTS_UPLOAD: `${API_BASE_URL}/documents/upload`,
    DOCUMENTS_UPLOAD_ANALYZE: `${API_BASE_URL}/documents/upload-and-analyze`,

    // AI
    AI_CONFIG: `${API_BASE_URL}/ai/config`,
    AI_ANALYZE: `${API_BASE_URL}/ai/analyze`,
    HISTORY: `${API_BASE_URL}/history`,

    // Governance
    GOVERNANCE_QUESTIONS: `${API_BASE_URL}/governance/questions`,
    GOVERNANCE_SUBMIT: `${API_BASE_URL}/governance/submit`,
    GOVERNANCE_HISTORY: `${API_BASE_URL}/governance/history`,
    GOVERNANCE_RESULT: (id) => `${API_BASE_URL}/governance/result/${id}`,
    GOVERNANCE_REVISION_REASON: (id) => `${API_BASE_URL}/governance/${id}/revision-reason`,
};

export default {
    API_BASE_URL,
    API_ENDPOINTS,
};
