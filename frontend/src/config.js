// API Configuration
// Uses environment variables with fallback defaults

export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';
export const VIBE_WORKSPACE_URL = import.meta.env.VITE_VIBE_WORKSPACE_URL || 'http://localhost:5174/vibecoding';

// API Endpoints
export const API_ENDPOINTS = {
    // Auth
    TOKEN: `${API_BASE_URL}/token`,
    SSO_START: `${API_BASE_URL}/auth/sso/start`,
    OAUTH_CLIENTS: `${API_BASE_URL}/oauth/clients`,
    OAUTH_PLUGIN_LAUNCH: (clientId) => `${API_BASE_URL}/oauth/plugins/${clientId}/launch`,
    TASK_TOKEN: `${API_BASE_URL}/api/token/task/`,
    USERS: `${API_BASE_URL}/users/`,
    USERS_ME: `${API_BASE_URL}/users/me`,
    ORG_SSO_SETTINGS: `${API_BASE_URL}/organization/sso-settings`,
    ORG_RBAC_PAGES: `${API_BASE_URL}/organization/rbac/pages`,
    ORG_RBAC_ME: `${API_BASE_URL}/organization/rbac/me`,
    ORG_RBAC_ROLES: `${API_BASE_URL}/organization/rbac/roles`,
    ORG_RBAC_ROLE: (roleId) => `${API_BASE_URL}/organization/rbac/roles/${roleId}`,
    ORG_RBAC_REQUEST_ACCESS: `${API_BASE_URL}/organization/rbac/request-access`,
    ORG_RBAC_PAGE_ACCESS_INFO: (path) => `${API_BASE_URL}/organization/rbac/page-access-info?path=${path}`,
    ORG_INVITES: `${API_BASE_URL}/organization/invites`,
    ORG_USERS: `${API_BASE_URL}/organization/users`,
    ORG_INVITE_PREVIEW: `${API_BASE_URL}/organization/invites/preview`,
    ORG_INVITE_ACCEPT: `${API_BASE_URL}/organization/invites/accept`,
    ORG_AGENT_QUOTA: `${API_BASE_URL}/organization/agent-quota`,
    ORG_AGENT_QUOTA_INCREASE: `${API_BASE_URL}/organization/agent-quota/increase`,
    FORGOT_PASSWORD: `${API_BASE_URL}/auth/forgot-password`,
    RESET_PASSWORD: `${API_BASE_URL}/auth/reset-password`,

    // Super Admin
    SUPERADMIN_DASHBOARD_STATS: `${API_BASE_URL}/api/superadmin/dashboard-stats`,
    SUPERADMIN_ORGANIZATIONS: `${API_BASE_URL}/api/superadmin/organizations`,
    SUPERADMIN_ORG_CAPACITY: (orgName) => `${API_BASE_URL}/api/superadmin/organizations/${encodeURIComponent(orgName)}/capacity`,
    SUPERADMIN_CAPACITY_REQUESTS: `${API_BASE_URL}/api/superadmin/capacity-requests`,
    SUPERADMIN_CAPACITY_REQUEST_APPROVE: (id) => `${API_BASE_URL}/api/superadmin/capacity-requests/${id}/approve`,
    SUPERADMIN_CAPACITY_REQUEST_REJECT: (id) => `${API_BASE_URL}/api/superadmin/capacity-requests/${id}/reject`,
    SUPERADMIN_AUDIT_LOGS: `${API_BASE_URL}/api/superadmin/audit-logs`,
    ORG_CAPACITY_REQUEST: `${API_BASE_URL}/api/organization/capacity-request`,
    ORG_CAPACITY_REQUESTS: `${API_BASE_URL}/api/organization/capacity-requests`,
    AGENT_PROJECT_REQUESTS: `${API_BASE_URL}/api/agent/project-requests`,
    AGENT_CAPACITY_INCREASE_REQUEST: `${API_BASE_URL}/api/agent/capacity-increase-request`,

    // Documents
    DOCUMENTS_UPLOAD: `${API_BASE_URL}/documents/upload`,
    DOCUMENTS_UPLOAD_ANALYZE: `${API_BASE_URL}/documents/upload-and-analyze`,
    DOCUMENTS_EXTRACT_URL: `${API_BASE_URL}/documents/extract-from-url`,
    
    // Share Document
    SHARE_DOC: `${API_BASE_URL}/api/share-doc`,
    SHARE_DOC_STATS: `${API_BASE_URL}/api/share-doc/stats`,
    SHARE_PROJECTS: `${API_BASE_URL}/api/share-projects`,
    SHARE_PROJECT: (projectToken) => `${API_BASE_URL}/api/share-projects/${projectToken}`,
    SHARE_PROJECT_UPLOAD_FILES: (projectToken) => `${API_BASE_URL}/api/share-projects/${projectToken}/upload-files`,
    SHARE_PROJECT_DELETE_FILE: (projectToken, fileId) => `${API_BASE_URL}/api/share-projects/${projectToken}/files/${fileId}`,
    SHARED_DOCUMENT: (shareToken) => `${API_BASE_URL}/api/shared/${shareToken}`,
    SHARED_DOCUMENT_DOWNLOAD: (shareToken, fileId) => `${API_BASE_URL}/api/shared/${shareToken}/download/${fileId}`,
    SHARED_DOCUMENT_VIEW: (shareToken, fileId) => `${API_BASE_URL}/api/shared/${shareToken}/view/${fileId}`,

    // Chat Messages
    CHAT_MESSAGES_SAVE: `${API_BASE_URL}/chat/messages`,
    CHAT_MESSAGES_GET: (documentId) => `${API_BASE_URL}/chat/messages/${documentId}`,
    CHAT_MESSAGES_DELETE: (documentId) => `${API_BASE_URL}/chat/messages/${documentId}`,

    // AI
    AI_CONFIG: `${API_BASE_URL}/ai/config`,
    AI_ANALYZE: `${API_BASE_URL}/ai/analyze`,
    // New chat endpoint used by the AssistantBot component
    AI_CHAT: `${API_BASE_URL}/api/agent/assistant`,
    AI_CHAT_STREAM: `${API_BASE_URL}/api/agent/assistant/stream`,
    HISTORY: `${API_BASE_URL}/history`,
    HISTORY_ITEM: (id) => `${API_BASE_URL}/history/${id}`,

    // Governance
    GOVERNANCE_QUESTIONS: `${API_BASE_URL}/governance/questions`,
    GOVERNANCE_SUBMIT: `${API_BASE_URL}/governance/submit`,
    GOVERNANCE_HISTORY: `${API_BASE_URL}/governance/history`,
    GOVERNANCE_RESULT: (id) => `${API_BASE_URL}/governance/result/${id}`,
    GOVERNANCE_DELETE: (id) => `${API_BASE_URL}/governance/${id}`,
    GOVERNANCE_REVISION_REASON: (id) => `${API_BASE_URL}/governance/${id}/revision-reason`,
    GOVERNANCE_ROADMAP_STEP: (id) => `${API_BASE_URL}/governance/${id}/roadmap-step`,
    GOVERNANCE_PREREQUISITES_COMPLETE: (id) => `${API_BASE_URL}/governance/${id}/prerequisites-complete`,
    GOVERNANCE_CLAUDE_MD_FILES: (id) => `${API_BASE_URL}/governance/${id}/claude-md-files`,
    GOVERNANCE_SKILLS_MD_FILES: (id) => `${API_BASE_URL}/governance/${id}/skills-md-files`,
    GOVERNANCE_ELICITATION_TECHNIQUES: (id) => `${API_BASE_URL}/api/projects/${id}/elicitation-techniques`,
    GOVERNANCE_QUESTION_ALL: `${API_BASE_URL}/governance/questions/all`,
    GOVERNANCE_QUESTION_CREATE: `${API_BASE_URL}/governance/questions`,
    GOVERNANCE_QUESTION_UPDATE: (id) => `${API_BASE_URL}/governance/questions/${id}`,
    GOVERNANCE_QUESTION_DELETE: (id) => `${API_BASE_URL}/governance/questions/${id}`,

    // Projects
    PROJECT_ENSURE: `${API_BASE_URL}/api/projects/ensure`,

    // GitHub
    GITHUB_AUTH_URL: `${API_BASE_URL}/github/auth-url`,
    GITHUB_CALLBACK: `${API_BASE_URL}/github/callback`,
    GITHUB_STATUS: `${API_BASE_URL}/github/status`,
    GITHUB_DISCONNECT: `${API_BASE_URL}/github/disconnect`,
    GITHUB_REPOS: `${API_BASE_URL}/github/repos`,
    GITHUB_REPO_CONTEXT: `${API_BASE_URL}/github/repo-context`,
    AZURE_DEVOPS_AUTH_URL: `${API_BASE_URL}/azure-devops/auth-url`,
    AZURE_DEVOPS_CALLBACK: `${API_BASE_URL}/azure-devops/callback`,
    AZURE_DEVOPS_STATUS: `${API_BASE_URL}/azure-devops/status`,
    AZURE_DEVOPS_DISCONNECT: `${API_BASE_URL}/azure-devops/disconnect`,
    AZURE_DEVOPS_REPOS: `${API_BASE_URL}/azure-devops/repos`,
    AZURE_DEVOPS_REPO_CONTEXT: `${API_BASE_URL}/azure-devops/repo-context`,
    AZURE_DEVOPS_SAVE_CREDENTIALS: `${API_BASE_URL}/azure-devops/save-credentials`,
    AZURE_DEVOPS_GET_CREDENTIALS: `${API_BASE_URL}/azure-devops/credentials`,
    AZURE_DEVOPS_LIST_PROJECT_REPOS: `${API_BASE_URL}/azure-devops/list-project-repos`,
    
    // Git Validation
    GIT_VALIDATE_CONNECTION: `${API_BASE_URL}/git/validate-connection`,

    // AI Agents (Backend Docker Execution)
    AGENTS: `${API_BASE_URL}/agents`,
    AGENTS_TASKS: `${API_BASE_URL}/agents/tasks`,
    AGENT_STATUS: (agentId) => {
        console.warn(`⚠️  Individual agent status endpoint called for ${agentId}. Consider using /agents endpoint for better performance.`);
        return `${API_BASE_URL}/agents/${agentId}/status`;
    },
    AGENT_RUN: (agentId) => `${API_BASE_URL}/agents/${agentId}/run`,
    AGENT_RESET: (agentId) => `${API_BASE_URL}/agents/${agentId}/reset`,
    AGENT_RUN_ALL: `${API_BASE_URL}/agents/run-all`,
    AGENT_ADD: `${API_BASE_URL}/agents/add`,
    AGENT_UPDATE: (agentId) => `${API_BASE_URL}/agents/${agentId}`,
    AGENT_REMOVE: (agentId) => `${API_BASE_URL}/agents/${agentId}`,

    // Preview Deploy
    AGENT_PREVIEW_DEPLOY: `${API_BASE_URL}/agents/preview/deploy`,
    AGENT_PREVIEW_STATUS: `${API_BASE_URL}/agents/preview/status`,
    AGENT_PREVIEW_STOP: `${API_BASE_URL}/agents/preview/stop`,
    AGENT_PREVIEW_FIX: `${API_BASE_URL}/agents/preview/fix`,
    AGENT_PREVIEW_WS: (projectToken) => `${API_BASE_URL.replace('http', 'ws')}/ws/preview/${projectToken}`,

    // External Task Management API
    AGENT_AUTO_GENERATE: `${API_BASE_URL}/api/agent/auto-generate/`,
    AGENT_TASKS_GENERATE_LOCAL: `${API_BASE_URL}/api/agent/tasks/generate-local/`,
    AGENT_TASKS_LOCAL: `${API_BASE_URL}/api/agent/tasks/local/`,
    AGENT_TASKS_SAVE_LOCAL: `${API_BASE_URL}/api/agent/tasks/save-local/`,
    AGENT_TASKS_SYNC: `${API_BASE_URL}/api/agent/tasks/sync/`,
    AGENT_TASKS_SELECTION: `${API_BASE_URL}/api/agent/tasks/selection/`,
    AGENT_PROJECT_CONFIG: `${API_BASE_URL}/api/agent/project-config/`,
    AGENT_PROJECT_BOOTSTRAP: `${API_BASE_URL}/api/agent/project-bootstrap/`,
    AGENT_TASKS: `${API_BASE_URL}/api/agent/tasks-list/`,
    AGENT_TASKS_TOTAL: `${API_BASE_URL}/api/agent/tasks-total-list/`,
    AGENT_CREATE_TASK: `${API_BASE_URL}/api/agent/tasks/`,
    AGENT_SPRINTS: `${API_BASE_URL}/api/agent/sprints/`,
    AGENT_MILESTONES: `${API_BASE_URL}/api/agent/milestones/`,
    AGENT_PROJECT_INFO: `${API_BASE_URL}/api/agent/project-info/`,
    AGENT_DASHBOARD: `${API_BASE_URL}/api/agent/dashboard/`,

    // VibeCoding Handoff
    VIBECODING_HANDOFF: `${API_BASE_URL}/api/vibecoding/handoff-token`,

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
