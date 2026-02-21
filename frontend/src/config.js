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
    GOVERNANCE_ROADMAP_STEP: (id) => `${API_BASE_URL}/governance/${id}/roadmap-step`,

    // GitHub
    GITHUB_AUTH_URL: `${API_BASE_URL}/github/auth-url`,
    GITHUB_CALLBACK: `${API_BASE_URL}/github/callback`,
    GITHUB_STATUS: `${API_BASE_URL}/github/status`,
    GITHUB_DISCONNECT: `${API_BASE_URL}/github/disconnect`,
    GITHUB_REPOS: `${API_BASE_URL}/github/repos`,
    GITHUB_REPO_CONTEXT: `${API_BASE_URL}/github/repo-context`,

    // AI Agents (Backend Docker Execution)
    AGENTS: `${API_BASE_URL}/agents`,
    AGENTS_TASKS: `${API_BASE_URL}/agents/tasks`,
    AGENT_STATUS: (agentId) => `${API_BASE_URL}/agents/${agentId}/status`,
    AGENT_RUN: (agentId) => `${API_BASE_URL}/agents/${agentId}/run`,
    AGENT_RESET: (agentId) => `${API_BASE_URL}/agents/${agentId}/reset`,

    // External Task Management API
    AGENT_AUTO_GENERATE: `${API_BASE_URL}/api/agent/auto-generate/`,
    AGENT_TASKS: `${API_BASE_URL}/api/agent/tasks-list/`,
    AGENT_CREATE_TASK: `${API_BASE_URL}/api/agent/tasks/`,
    AGENT_PROJECT_INFO: `${API_BASE_URL}/api/agent/project-info/`,
};

export default {
    API_BASE_URL,
    API_ENDPOINTS,
};
