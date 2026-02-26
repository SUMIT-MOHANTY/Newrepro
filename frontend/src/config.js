// API Configuration
// Uses environment variables with fallback defaults

export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

// API Endpoints
export const API_ENDPOINTS = {
    // Auth
    TOKEN: `${API_BASE_URL}/token`,
    TASK_TOKEN: `${API_BASE_URL}/api/token/task/`,
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
    GOVERNANCE_PREREQUISITES_COMPLETE: (id) => `${API_BASE_URL}/governance/${id}/prerequisites-complete`,

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
    AGENT_RUN_ALL: `${API_BASE_URL}/agents/run-all`,
    AGENT_ADD: `${API_BASE_URL}/agents/add`,
    AGENT_UPDATE: (agentId) => `${API_BASE_URL}/agents/${agentId}`,
    AGENT_REMOVE: (agentId) => `${API_BASE_URL}/agents/${agentId}`,

    // External Task Management API
    AGENT_AUTO_GENERATE: `${API_BASE_URL}/api/agent/auto-generate/`,
    AGENT_TASKS: `${API_BASE_URL}/api/agent/tasks-list/`,
    AGENT_CREATE_TASK: `${API_BASE_URL}/api/agent/tasks/`,
    AGENT_PROJECT_INFO: `${API_BASE_URL}/api/agent/project-info/`,
    AGENT_DASHBOARD: `${API_BASE_URL}/api/agent/dashboard/`,

    // Knowledge Graph + RAG
    KG_INDEX: `${API_BASE_URL}/api/knowledge-graph/index`,
    KG_STATUS: (projectToken) => `${API_BASE_URL}/api/knowledge-graph/status/${projectToken}`,
    KG_QUERY: `${API_BASE_URL}/api/knowledge-graph/query`,
    KG_STATS: (projectToken) => `${API_BASE_URL}/api/knowledge-graph/stats/${projectToken}`,
    KG_DELETE: (projectToken) => `${API_BASE_URL}/api/knowledge-graph/${projectToken}`,
    KG_AGENT_CONTEXT: `${API_BASE_URL}/api/knowledge-graph/agent-context`,
};

export default {
    API_BASE_URL,
    API_ENDPOINTS,
};
