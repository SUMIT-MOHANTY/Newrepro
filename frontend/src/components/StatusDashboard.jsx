import React, { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { customAlert } from '../utils/modalHelpers';
import { Flag, Activity, CheckCircle, Clock, Menu, PlusCircle, X, ArrowRight, Bot, Shield, Cpu, Play, RefreshCw, Eye, ListTodo, AlertCircle, ChevronRight, Users, Calendar, Wallet, Tag, AlertTriangle, CheckCircle2, Loader2, Terminal, Pencil, GitBranch, Globe, ExternalLink, StopCircle, Rocket } from 'lucide-react';
import { useLocation, useNavigate } from 'react-router-dom';
import Skeleton, { SkeletonTheme } from 'react-loading-skeleton';
import 'react-loading-skeleton/dist/skeleton.css';

import { API_ENDPOINTS } from '../config';
import { getNeutralAgentLabel, getNeutralAgentName } from '../utils/agentNames';
import AgentChatPanel from './AgentChatPanel';
import kaktoxLogo from '../assets/Kaktox.png';
import nModLogo from '../assets/N-Mod-icon.png';
import masterLogo from '../assets/logo1.png';
import cloudIcon from '../assets/cloud-icon.png';
// import KnowledgeGraphCard from './KnowledgeGraphCard';
// import PrStatusCard from './PrStatusCard';

const PROJECT_STORAGE_KEY = 'status_dashboard_selected_project_key';
const TASK_TOKEN_STORAGE_KEY = 'status_dashboard_task_token_cache';
const ROLE_STORAGE_KEY = 'status_dashboard_selected_role';
const PROCESS_MODE_STORAGE_KEY = 'status_dashboard_process_mode_map';
const DEFAULT_PROCESS_MODE = 'coexistence';
const TOKEN_REFRESH_THRESHOLD_SECONDS = 300;
const TOKEN_CACHE_MIN_TTL_SECONDS = 0;
const DASHBOARD_ROLES = [
    { value: 'cxo', label: 'Executive Summary Dashboard', description: 'High-level executive snapshot' },
    { value: 'project', label: 'Project Dashboard' },
];

function decodeJwtExpiry(token) {
    try {
        const parts = token.split('.');
        if (parts.length < 2) return null;
        const payloadB64 = parts[1].replace(/-/g, '+').replace(/_/g, '/');
        const padded = payloadB64 + '='.repeat((4 - (payloadB64.length % 4)) % 4);
        const payload = JSON.parse(atob(padded));
        return typeof payload.exp === 'number' ? payload.exp : null;
    } catch {
        return null;
    }
}

function readTaskTokenCache() {
    try {
        const raw = localStorage.getItem(TASK_TOKEN_STORAGE_KEY);
        if (!raw) return {};
        const parsed = JSON.parse(raw);
        return parsed && typeof parsed === 'object' ? parsed : {};
    } catch {
        return {};
    }
}

function writeTaskTokenCache(cache) {
    try {
        localStorage.setItem(TASK_TOKEN_STORAGE_KEY, JSON.stringify(cache));
    } catch {
        // Ignore storage errors.
    }
}

function getCachedTaskToken(projectKey, minTtlSeconds = 0) {
    if (!projectKey) return null;
    const cache = readTaskTokenCache();
    const entry = cache[projectKey];
    if (!entry || !entry.token) return null;

    if (entry.expiresAt) {
        const now = Math.floor(Date.now() / 1000);
        if (entry.expiresAt <= now + minTtlSeconds) {
            delete cache[projectKey];
            writeTaskTokenCache(cache);
            return null;
        }
    }
    return entry;
}

function cacheTaskToken(projectKey, token) {
    if (!projectKey || !token) return;
    const cache = readTaskTokenCache();
    cache[projectKey] = {
        token,
        expiresAt: decodeJwtExpiry(token),
    };
    writeTaskTokenCache(cache);
}

function readProcessModeMap() {
    try {
        const raw = localStorage.getItem(PROCESS_MODE_STORAGE_KEY);
        if (!raw) return {};
        const parsed = JSON.parse(raw);
        return parsed && typeof parsed === 'object' ? parsed : {};
    } catch {
        return {};
    }
}

function writeProcessModeMap(map) {
    try {
        localStorage.setItem(PROCESS_MODE_STORAGE_KEY, JSON.stringify(map));
    } catch {
        // Ignore storage errors.
    }
}

function getProcessModeForProject(projectKey) {
    if (!projectKey) return DEFAULT_PROCESS_MODE;
    const map = readProcessModeMap();
    return map[projectKey] || DEFAULT_PROCESS_MODE;
}

function setProcessModeForProject(projectKey, mode) {
    if (!projectKey || !mode) return;
    const map = readProcessModeMap();
    map[projectKey] = mode;
    writeProcessModeMap(map);
}

function extractEntityId(item, key) {
    const direct = item?.[key];
    if (direct && typeof direct === 'object') {
        if (direct.id != null) return direct.id;
        if (direct[`${key}_id`] != null) return direct[`${key}_id`];
    }
    if (direct != null && direct !== '') return direct;
    const fallback = item?.[`${key}_id`];
    if (fallback != null && fallback !== '') return fallback;
    return null;
}

function getTaskSprintLabel(task) {
    // Prioritize sprint_name from API response
    if (task?.sprint_name && task.sprint_name !== '') {
        return task.sprint_name;
    }
    const sprint = task?.sprint;
    if (sprint && typeof sprint === 'object') {
        if (sprint.name) return sprint.name;
        if (sprint.id != null) return `Sprint #${sprint.id}`;
    }
    const sprintId = extractEntityId(task, 'sprint');
    if (sprintId != null && sprintId !== '') return `Sprint #${sprintId}`;
    return 'Unassigned';
}

function toNumber(value) {
    const n = Number(value);
    return Number.isFinite(n) ? n : Number.POSITIVE_INFINITY;
}

function toDateKey(value) {
    if (!value) return '9999-12-31';
    const text = String(value).slice(0, 10);
    return /^\d{4}-\d{2}-\d{2}$/.test(text) ? text : '9999-12-31';
}

function sanitizePrerequisiteForAiPayload(item = {}) {
    const safe = {
        name: String(item.name || '').trim() || 'Unknown',
        description: String(item.description || '').trim(),
        category: String(item.category || 'other').trim() || 'other',
        priority: String(item.priority || 'medium').trim() || 'medium',
        fieldType: String(item.fieldType || 'text').trim() || 'text',
        provided: Boolean(item.provided),
    };

    const isSecret = Boolean(item.containsSecret);
    safe.containsSecret = isSecret;

    const value = String(item.userValue || '').trim();
    const fileName = String(item.userFileName || '').trim();
    if (!isSecret) {
        if (value) safe.userValue = value;
        if (fileName) safe.userFileName = fileName;
    }

    return safe;
}

export default function StatusDashboard({ projects = [], projectsLoading = false, selectedProjectKey, selectedRole, fetchRoadmapData }) {
    const navigate = useNavigate();
    const location = useLocation();
    const queryClient = useQueryClient();
    const [showModal, setShowModal] = useState(false);
    const [newProjectName, setNewProjectName] = useState('');
    // Props for selectedProjectKey and selectedRole are now passed in, so we no longer
    // keep local state for them.
    // However, Dashboard.jsx might not be passing default if not given, so we rely on AppLayout as the source of truth.

    const token = localStorage.getItem('token');

    // ── Agent State (Docker Agents) ──────────────────────────────────
    const [runningAgent, setRunningAgent] = useState(null);
    const [showLogModal, setShowLogModal] = useState(null);

    const [gitModalAgent, setGitModalAgent] = useState(null);
    const [gitRepoUrl, setGitRepoUrl] = useState('');
    const [gitToken, setGitToken] = useState('');

    const [agentsGitConfig, setAgentsGitConfig] = useState({});
    const [editingAgentId, setEditingAgentId] = useState(null);
    const [editingAgentName, setEditingAgentName] = useState('');
    const [editingAgentRepoUrl, setEditingAgentRepoUrl] = useState('');
    const [editingAgentToken, setEditingAgentToken] = useState('');
    const [isSavingAgentName, setIsSavingAgentName] = useState(false);
    const [showAddAgentModal, setShowAddAgentModal] = useState(false);
    const [agentQuota, setAgentQuota] = useState(null);
    const [agentQuotaLoading, setAgentQuotaLoading] = useState(false);
    const [agentQuotaError, setAgentQuotaError] = useState('');
    const [sharedAgentsToAdd, setSharedAgentsToAdd] = useState('');
    const [dedicatedAgentsToAdd, setDedicatedAgentsToAdd] = useState('');
    const [sharedTestAgentsToAdd, setSharedTestAgentsToAdd] = useState('');
    const [dedicatedTestAgentsToAdd, setDedicatedTestAgentsToAdd] = useState('');
    const [isAddingAgents, setIsAddingAgents] = useState(false);
    const [addAgentModalError, setAddAgentModalError] = useState('');

    // ── Preview Deploy State ─────────────────────────────────────────
    const [previewStatus, setPreviewStatus] = useState({ status: 'none' });
    const [isDeploying, setIsDeploying] = useState(false);
    const [isFixing, setIsFixing] = useState(false);
    const [showPreviewLogs, setShowPreviewLogs] = useState(false);
    const [processMode, setProcessMode] = useState(() => getProcessModeForProject(localStorage.getItem(PROJECT_STORAGE_KEY) || ''));

    // ── External Task API State ──────────────────────────────────────
    const [isGeneratingTasks, setIsGeneratingTasks] = useState(false);
    const [taskList, setTaskList] = useState([]);
    const [isLoadingTasks, setIsLoadingTasks] = useState(false);
    const [taskListError, setTaskListError] = useState(null);
    const [totalTaskCount, setTotalTaskCount] = useState(0);
    const [nextPageUrl, setNextPageUrl] = useState(null);
    const [isLoadingMore, setIsLoadingMore] = useState(false);

    const sortedTaskList = useMemo(() => {
        const copy = [...taskList];
        copy.sort((a, b) => {
            const aSprint = extractEntityId(a, 'sprint');
            const bSprint = extractEntityId(b, 'sprint');
            const aMilestone = extractEntityId(a, 'milestone');
            const bMilestone = extractEntityId(b, 'milestone');
            return (
                toNumber(aSprint) - toNumber(bSprint) ||
                toNumber(aMilestone) - toNumber(bMilestone) ||
                toDateKey(a.startdate || a.start_date).localeCompare(toDateKey(b.startdate || b.start_date)) ||
                toDateKey(a.deadline).localeCompare(toDateKey(b.deadline)) ||
                String(a.taskName || a.title || '').localeCompare(String(b.taskName || b.title || ''))
            );
        });
        return copy;
    }, [taskList]);

    const sprintCount = useMemo(() => {
        const sprints = new Set();
        sortedTaskList.forEach((task) => {
            const sprintId = extractEntityId(task, 'sprint');
            if (sprintId != null && sprintId !== '') sprints.add(String(sprintId));
        });
        return sprints.size;
    }, [sortedTaskList]);
    const autoAiAssistRunRef = useRef(new Set());

    const selectedProjectKeyRef = useRef(selectedProjectKey);
    const dashboardRequestIdRef = useRef(0);

    const isInitialProjectsLoading = projectsLoading && projects.length === 0;

    const withProjectToken = useCallback((url) => {
        if (!selectedProjectKey) return url;
        const parsed = new URL(url);
        parsed.searchParams.set('project_token', selectedProjectKey);
        return parsed.toString();
    }, [selectedProjectKey]);

    // ── Dynamic Task Token State ─────────────────────────────────────
    const [taskToken, setTaskToken] = useState(() => {
        try {
            const initialProjectKey = localStorage.getItem(PROJECT_STORAGE_KEY);
            return getCachedTaskToken(initialProjectKey, TOKEN_CACHE_MIN_TTL_SECONDS)?.token || null;
        } catch {
            return null;
        }
    });
    const [taskTokenProjectKey, setTaskTokenProjectKey] = useState(() => {
        try {
            const initialProjectKey = localStorage.getItem(PROJECT_STORAGE_KEY);
            return getCachedTaskToken(initialProjectKey, TOKEN_CACHE_MIN_TTL_SECONDS)?.token ? initialProjectKey : null;
        } catch {
            return null;
        }
    });
    const hasValidTaskToken = Boolean(taskToken) && taskTokenProjectKey === selectedProjectKey;

    const { data: agents = [], isFetching: isLoadingAgents } = useQuery({
        queryKey: ['agents', selectedProjectKey],
        queryFn: async () => {
            const url = new URL(API_ENDPOINTS.AGENTS);
            if (selectedProjectKey) url.searchParams.set('project_token', selectedProjectKey);
            const res = await fetch(url.toString(), {
                headers: { Authorization: `Bearer ${token}` },
            });
            if (!res.ok) throw new Error('Failed to fetch agents');
            
            // Check for server-suggested polling interval
            const pollingInterval = res.headers.get('X-Polling-Interval');
            if (pollingInterval) {
                localStorage.setItem('agent-polling-interval', pollingInterval);
            }
            
            const data = await res.json();
            const fetchedAgents = data.agents || [];

            // The main /agents endpoint already provides complete status information
            // No need to call individual agent status endpoints - this was causing excessive API calls
            return fetchedAgents;
        },
        enabled: !!token,
        // Always poll every 5s when any agent is running, 15s otherwise
        refetchInterval: (query) => {
            // query.state.data is the array returned by queryFn
            const agentList = query?.state?.data ?? [];
            const hasRunning = Array.isArray(agentList) && agentList.some(a => a?.status === 'running');
            return hasRunning ? 5000 : 15000;
        },
        refetchIntervalInBackground: true,
    });
    const hasGlobalGitConfigured = agents.some(agent => Boolean(agent.git_repo_url && agent.has_git_token));
    const devAgents = useMemo(() => {
        const parseAgentNumber = (agentId) => {
            const match = String(agentId || '').match(/(\d+)$/);
            if (!match) return Number.MAX_SAFE_INTEGER;
            return Number.parseInt(match[1], 10);
        };

        return [...agents]
            .filter(agent => agent.agent_kind !== 'system')
            .sort((a, b) => {
                const aNumber = parseAgentNumber(a.id);
                const bNumber = parseAgentNumber(b.id);
                if (aNumber !== bNumber) return aNumber - bNumber;
                return String(a.id).localeCompare(String(b.id));
            });
    }, [agents]);

    const orderedAgents = useMemo(() => {
        const systemAgents = agents.filter(agent => agent.agent_kind === 'system');
        return [
            ...systemAgents,
            ...devAgents,
        ];
    }, [agents, devAgents]);

    const getAgentDisplayName = useCallback((agent) => {
        if (!agent) return 'Agent';
        return getNeutralAgentName(agent);
    }, []);

    const setAgents = useCallback((updater) => {
        queryClient.setQueryData(['agents', selectedProjectKey], updater);
    }, [queryClient, selectedProjectKey]);

    const { data: projectInfo = null, isFetching: isLoadingProjectInfo } = useQuery({
        queryKey: ['projectInfo', selectedProjectKey, taskToken],
        queryFn: async () => {
            const headers = { 'Authorization': `Bearer ${token}` };
            if (taskToken) headers['x-task-token'] = taskToken;
            const res = await fetch(API_ENDPOINTS.AGENT_PROJECT_INFO, { headers });
            if (!res.ok) throw new Error('Failed to fetch project info');
            return await res.json();
        },
        enabled: !!token && hasValidTaskToken,
    });

    const { data: dashboardData = null, isFetching: isLoadingDashboardData } = useQuery({
        queryKey: ['dashboardData', selectedProjectKey, taskToken],
        queryFn: async () => {
            const headers = { 'Authorization': `Bearer ${token}` };
            if (taskToken) headers['x-task-token'] = taskToken;
            const res = await fetch(API_ENDPOINTS.AGENT_DASHBOARD, { headers });
            if (!res.ok) throw new Error('Failed to fetch dashboard data');
            return await res.json();
        },
        enabled: !!token && hasValidTaskToken,
    });

    const isDashboardSkeletonVisible = projects.length > 0 && !dashboardData && (isLoadingAgents || isLoadingProjectInfo || isLoadingDashboardData);

    useEffect(() => {
        selectedProjectKeyRef.current = selectedProjectKey;
    }, [selectedProjectKey]);

    useEffect(() => {
        if (!selectedProjectKey) {
            setProcessMode(DEFAULT_PROCESS_MODE);
            return;
        }
        const incomingMode = location.state?.processMode;
        const normalizedMode = ['ai_first', 'ai_assist', 'developer_only', 'coexistence', 'vibe_coding'].includes(incomingMode)
            ? incomingMode
            : getProcessModeForProject(selectedProjectKey);
        setProcessMode(normalizedMode);
        setProcessModeForProject(selectedProjectKey, normalizedMode);
    }, [selectedProjectKey, location.state]);

    const isAiAssistMode = processMode === 'ai_assist' || processMode === 'ai_first';
    const isDeveloperOnlyMode = processMode === 'developer_only';

    useEffect(() => {
        if (!selectedProjectKey) {
            setTaskToken(null);
            setTaskTokenProjectKey(null);
            return;
        }
        const cached = getCachedTaskToken(selectedProjectKey, TOKEN_CACHE_MIN_TTL_SECONDS);
        setTaskToken(cached?.token || null);
        setTaskTokenProjectKey(cached?.token ? selectedProjectKey : null);
    }, [selectedProjectKey]);

    // Role logic is handled centrally by AppLayout


    useEffect(() => {
        let isMounted = true;
        const fetchTaskToken = async () => {
            if (!selectedProjectKey) {
                return;
            }

            const cached = getCachedTaskToken(selectedProjectKey, TOKEN_CACHE_MIN_TTL_SECONDS);
            const hasCachedToken = Boolean(cached?.token);
            if (hasCachedToken && isMounted) {
                setTaskToken(cached.token);
                setTaskTokenProjectKey(selectedProjectKey);
            }
            if (projects.length === 0) {
                return;
            }

            const proj = projects.find(p => p.key === selectedProjectKey);
            const clientId = proj?.client_id;
            const clientSecret = proj?.client_secret;

            if (!clientId || !clientSecret) {
                if (!hasCachedToken && isMounted) {
                    setTaskToken(null);
                    setTaskTokenProjectKey(null);
                }
                return;
            }

            const shouldRefresh =
                !hasCachedToken ||
                !cached?.expiresAt ||
                (cached.expiresAt - Math.floor(Date.now() / 1000)) <= TOKEN_REFRESH_THRESHOLD_SECONDS;
            if (!shouldRefresh) {
                return;
            }
            try {
                const res = await fetch(API_ENDPOINTS.TASK_TOKEN, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ client_id: clientId, client_secret: clientSecret })
                });
                if (res.ok && isMounted) {
                    const data = await res.json();
                    setTaskToken(data.access);
                    setTaskTokenProjectKey(selectedProjectKey);
                    cacheTaskToken(selectedProjectKey, data.access);
                } else if (isMounted) {
                    if (!hasCachedToken) {
                        setTaskToken(null);
                        setTaskTokenProjectKey(null);
                    }
                }
            } catch (e) {
                console.error("Error fetching task token", e);
                if (!hasCachedToken && isMounted) {
                    setTaskToken(null);
                    setTaskTokenProjectKey(null);
                }
            }
        };

        fetchTaskToken();

        return () => {
            isMounted = false;
        };
    }, [selectedProjectKey, projects]);

    // ── Fetch agents (Docker agent backend) ──────────────────────────
    const fetchAgents = useCallback(() => {
        queryClient.invalidateQueries({ queryKey: ['agents', selectedProjectKey] });
    }, [queryClient, selectedProjectKey]);

    const clampAgentCount = useCallback((value, max = 1000) => {
        const n = Number(value);
        if (!Number.isFinite(n)) return 0;
        return Math.max(0, Math.min(max, Math.floor(n)));
    }, []);

    const refreshRoadmap = useCallback(async () => {
        if (!fetchRoadmapData || !selectedProjectKey) return;
        try {
            await fetchRoadmapData(selectedProjectKey);
        } catch (e) {
            console.error('Roadmap refresh failed', e);
        }
    }, [fetchRoadmapData, selectedProjectKey]);

    // ── Fetch tasks (External API) ───────────────────────────────────
    const fetchTasks = useCallback(async (append = false, page = 1, silent = false) => {
        if (!hasValidTaskToken) {
            setTaskList([]);
            setTotalTaskCount(0);

            return;
        }

        if (append) {
            if (!silent) setIsLoadingMore(true);
        } else {
            if (!silent) setIsLoadingTasks(true);
        }

        setTaskListError(null);
        try {
            const url = page > 1 ? `${API_ENDPOINTS.AGENT_TASKS}?page=${page}` : API_ENDPOINTS.AGENT_TASKS;
            const headers = { 'Authorization': `Bearer ${token}` };
            if (hasValidTaskToken) headers['x-task-token'] = taskToken;

            const res = await fetch(url, { headers });
            if (res.ok) {
                const data = await res.json();
                if (Array.isArray(data)) {
                    setTaskList(data);
                    setTotalTaskCount(data.length);

                } else if (data && Array.isArray(data.results)) {
                    if (append) {
                        setTaskList(prev => [...prev, ...data.results]);
                    } else {
                        setTaskList(data.results);
                    }
                    setTotalTaskCount(data.count || data.results.length);

                    setNextPageUrl(data.next);
                } else if (data && typeof data.count === 'number') {
                    setTotalTaskCount(data.count);

                }
            } else {
                const errData = await res.json().catch(() => ({}));
                setTaskListError(errData.detail || 'Failed to fetch tasks');
            }
        } catch (e) {
            console.error("Failed to load tasks:", e);
            setTaskListError(e.message);
        } finally {
            setIsLoadingTasks(false);
            setIsLoadingMore(false);
        }
    }, [token, taskToken, hasValidTaskToken]);

    useEffect(() => {
        dashboardRequestIdRef.current += 1;
    }, [selectedProjectKey]);

    const getPageFromUrl = (url) => {
        if (!url) return null;
        const urlObj = new URL(url);
        return urlObj.searchParams.get('page');
    };

    useEffect(() => {
        const load = async () => {
            if (selectedProjectKey && !hasValidTaskToken) return;
            await fetchTasks();
        };
        load();
    }, [fetchTasks, selectedProjectKey, hasValidTaskToken]);

    // useQuery refetchInterval above handles polling — no separate interval needed

    // ── Run Agent (Docker execution) ─────────────────────────────────
    const handleRunAgentClick = (agent) => {
        if (agent.agent_kind === 'system') return;
        // For private repos, require both URL and PAT. For public repos, only URL is needed.
        const needsRepoUrl = !agent.git_repo_url;
        const needsPatForPrivateRepo = agent.git_repo_url && !agent.is_public_repo && !agent.has_git_token;
        
        if (needsRepoUrl || needsPatForPrivateRepo) {
            navigate('/prerequisites');
            return;
        }

        handleRunAgent(agent.id);
    };

    const handleRunAgent = async (agentId, repoUrl = null, repoToken = null) => {
        setRunningAgent(agentId);
        setGitModalAgent(null); // close modal if open

        // Optimistically update UI to show it's running immediately
        setAgents(prev => prev.map(a => a.id === agentId ? { ...a, status: 'running', progress: 0, progress_message: 'Starting agent...' } : a));

        const body = repoUrl && repoToken ? { git_repo_url: repoUrl, git_token: repoToken } : {};
        try {
            const headers = {
                'Authorization': `Bearer ${token}`,
                'Content-Type': 'application/json'
            };
            if (hasValidTaskToken) headers['x-task-token'] = taskToken;
            await fetch(withProjectToken(API_ENDPOINTS.AGENT_RUN(agentId)), {
                method: 'POST',
                headers,
                body: Object.keys(body).length > 0 ? JSON.stringify(body) : undefined,
            });
            await fetchAgents();
            await fetchTasks(false, 1, true);
            await refreshRoadmap();
        } catch (e) {
            console.error('Run failed', e);
        } finally {
            setRunningAgent(null);
        }
    };

    const startEditingAgentName = (agent) => {
        setEditingAgentId(agent.id);
        setEditingAgentName(agent.name || '');
        setEditingAgentRepoUrl(agent.git_repo_url || '');
        setEditingAgentToken('');
    };

    const cancelEditingAgentName = () => {
        setEditingAgentId(null);
        setEditingAgentName('');
        setEditingAgentRepoUrl('');
        setEditingAgentToken('');
    };

    const saveAgentName = async () => {
        if (!editingAgentId) return;
        const nextName = editingAgentName.trim();
        if (!nextName) return;
        const nextRepo = editingAgentRepoUrl.trim();
        const nextToken = editingAgentToken.trim();
        const payload = { name: nextName, git_repo_url: nextRepo };
        if (nextToken) {
            payload.git_token = nextToken;
        }
        setIsSavingAgentName(true);
        try {
            const res = await fetch(withProjectToken(API_ENDPOINTS.AGENT_UPDATE(editingAgentId)), {
                method: 'POST',
                headers: {
                    'Authorization': `Bearer ${token}`,
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(payload)
            });
            if (!res.ok) {
                const errData = await res.json().catch(() => ({}));
                throw new Error(errData.detail || 'Failed to update agent settings');
            }
            await fetchAgents();
        } catch (e) {
            console.error('Update agent settings failed', e);
        } finally {
            setIsSavingAgentName(false);
            cancelEditingAgentName();
        }
    };

    // ── Reset Agent ──────────────────────────────────────────────────
    const handleResetAgent = async (agentId) => {
        try {
            await fetch(withProjectToken(API_ENDPOINTS.AGENT_RESET(agentId)), {
                method: 'POST',
                headers: { Authorization: `Bearer ${token}` },
            });
            fetchAgents();
        } catch (e) {
            console.error('Reset failed', e);
        }
    };


    const handleCreateProject = () => {
        if (!newProjectName.trim()) return;
        navigate(`/new-project?projectName=${encodeURIComponent(newProjectName.trim())}`);
    };

    // ── Run All Agents ────────────────────────────────────────────────
    const [runningAll, setRunningAll] = useState(false);

    const handleRunAll = useCallback(async () => {
        const idleAgents = agents.filter(a => a.status === 'idle' && a.agent_kind !== 'system');
        if (idleAgents.length === 0) return;

        // Check for missing config: require repo URL for all, and PAT only for private repos
        const missingConfig = idleAgents.filter(agent => {
            const needsRepoUrl = !agent.git_repo_url;
            const needsPatForPrivateRepo = agent.git_repo_url && !agent.is_public_repo && !agent.has_git_token;
            return needsRepoUrl || needsPatForPrivateRepo;
        });
        
        if (missingConfig.length > 0) {
            navigate('/prerequisites');
            return;
        }

        setGitModalAgent(null);
        setRunningAll(true);
        setAgents(prev => prev.map(a => (a.status === 'idle' && a.agent_kind !== 'system')
            ? { ...a, status: 'running', progress: 0, progress_message: 'Starting agent...' }
            : a));

        try {
            const headers = { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' };
            if (hasValidTaskToken) headers['x-task-token'] = taskToken;
            await fetch(withProjectToken(API_ENDPOINTS.AGENT_RUN_ALL), {
                method: 'POST',
                headers,
                body: JSON.stringify({}),
            });
            await fetchAgents();
            await fetchTasks(false, 1, true);
            await refreshRoadmap();
        } catch (e) {
            console.error('Run all failed', e);
        } finally {
            setRunningAll(false);
        }
    }, [agents, token, hasValidTaskToken, taskToken, withProjectToken, fetchAgents, fetchTasks, refreshRoadmap, navigate]);

    useEffect(() => {
        if (!isAiAssistMode) return;
        if (!selectedProjectKey) return;
        if (isLoadingAgents || runningAll) return;
        if (gitModalAgent) return;
        if (!hasValidTaskToken) return;
        if (agents.some(a => a.status === 'running')) return;

        const idleAgents = agents.filter(a => a.status === 'idle' && a.agent_kind !== 'system');
        if (idleAgents.length === 0) return;

        const autoKey = `${selectedProjectKey}:${processMode}`;
        if (autoAiAssistRunRef.current.has(autoKey)) return;
        autoAiAssistRunRef.current.add(autoKey);
        handleRunAll();
    }, [isAiAssistMode, selectedProjectKey, isLoadingAgents, runningAll, gitModalAgent, hasValidTaskToken, agents, processMode, handleRunAll]);

    const submitMultiAgentConfig = async () => {
        const globalConfig = agentsGitConfig.__global__ || {};
        setGitModalAgent(null);
        setRunningAll(true);
        setAgents(prev => prev.map(a => (a.status === 'idle' && a.agent_kind !== 'system')
            ? { ...a, status: 'running', progress: 0, progress_message: 'Starting agent...' }
            : a));
        try {
            const headers = { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' };
            if (hasValidTaskToken) headers['x-task-token'] = taskToken;
            await fetch(withProjectToken(API_ENDPOINTS.AGENT_RUN_ALL), {
                method: 'POST',
                headers,
                body: JSON.stringify({ agents_config: { __global__: globalConfig } }),
            });
            await fetchAgents();
            await fetchTasks(false, 1, true);
            await refreshRoadmap();
        } catch (e) {
            console.error('Run all failed with config', e);
        } finally {
            setRunningAll(false);
        }
    };

    // ── Add/Remove Agent ─────────────────────────────────────────────
    const handleAddAgent = () => {
        setSharedAgentsToAdd('');
        setDedicatedAgentsToAdd('');
        setSharedTestAgentsToAdd('');
        setDedicatedTestAgentsToAdd('');
        setAddAgentModalError('');
        setAgentQuotaError('');
        setShowAddAgentModal(true);
        setAgentQuotaLoading(true);
        fetch(API_ENDPOINTS.ORG_AGENT_QUOTA, {
            headers: { Authorization: `Bearer ${token}` },
        })
            .then(async (res) => {
                const data = await res.json().catch(() => ({}));
                if (!res.ok) throw new Error(data.detail || 'Failed to load organization capacity');
                setAgentQuota(data);
            })
            .catch((e) => {
                setAgentQuota(null);
                setAgentQuotaError(e.message || 'Failed to load organization capacity');
            })
            .finally(() => {
                setAgentQuotaLoading(false);
            });
    };

    const submitAddAgent = async () => {
        // Use dev/test-specific quotas and current project usage, similar to ResourceOnboarding / AgentsPage
        const sharedDevQuota = Number(agentQuota?.shared_dev_quota ?? 0);
        const dedicatedDevQuota = Number(agentQuota?.dedicated_dev_quota ?? 0);
        const sharedTestQuota = Number(agentQuota?.shared_test_quota ?? 0);
        const dedicatedTestQuota = Number(agentQuota?.dedicated_test_quota ?? 0);

        const sharedDevUsed = agents.filter(
            (a) => a.id?.startsWith('shared_') && (!a.sub_type || a.sub_type === 'dev')
        ).length;
        const dedicatedDevUsed = agents.filter(
            (a) => a.id?.startsWith('dedicated_') && (!a.sub_type || a.sub_type === 'dev')
        ).length;
        const sharedTestUsed = agents.filter(
            (a) => a.id?.startsWith('shared_') && a.sub_type === 'test'
        ).length;
        const dedicatedTestUsed = agents.filter(
            (a) => a.id?.startsWith('dedicated_') && a.sub_type === 'test'
        ).length;

        const sharedDevAvailable = Math.max(0, sharedDevQuota - sharedDevUsed);
        const dedicatedDevAvailable = Math.max(0, dedicatedDevQuota - dedicatedDevUsed);
        const sharedTestAvailable = Math.max(0, sharedTestQuota - sharedTestUsed);
        const dedicatedTestAvailable = Math.max(0, dedicatedTestQuota - dedicatedTestUsed);

        const sharedDevInput = String(sharedAgentsToAdd).trim() || '0';
        const dedicatedDevInput = String(dedicatedAgentsToAdd).trim() || '0';
        const sharedTestInput = String(sharedTestAgentsToAdd).trim() || '0';
        const dedicatedTestInput = String(dedicatedTestAgentsToAdd).trim() || '0';

        const sharedDevCount = clampAgentCount(Number(sharedDevInput), sharedDevAvailable);
        const dedicatedDevCount = clampAgentCount(Number(dedicatedDevInput), dedicatedDevAvailable);
        const sharedTestCount = clampAgentCount(Number(sharedTestInput), sharedTestAvailable);
        const dedicatedTestCount = clampAgentCount(Number(dedicatedTestInput), dedicatedTestAvailable);

        if (!selectedProjectKey) {
            setAddAgentModalError('Select a project before adding agents.');
            return;
        }
        if (
            sharedDevCount === 0 &&
            dedicatedDevCount === 0 &&
            sharedTestCount === 0 &&
            dedicatedTestCount === 0
        ) {
            setAddAgentModalError('Enter at least one shared or dedicated dev/test agent to add.');
            return;
        }
        if (
            sharedDevCount > sharedDevAvailable ||
            dedicatedDevCount > dedicatedDevAvailable ||
            sharedTestCount > sharedTestAvailable ||
            dedicatedTestCount > dedicatedTestAvailable
        ) {
            setAddAgentModalError('Requested count exceeds available dev/test organization capacity.');
            return;
        }

        setIsAddingAgents(true);
        setAddAgentModalError('');
        try {
            const headers = {
                'Authorization': `Bearer ${token}`,
                'Content-Type': 'application/json'
            };
            if (hasValidTaskToken) headers['x-task-token'] = taskToken;

            const createOne = async (kind, subType) => {
                const url = new URL(API_ENDPOINTS.AGENT_ADD);
                url.searchParams.set('project_token', selectedProjectKey);
                const res = await fetch(url.toString(), {
                    method: 'POST',
                    headers,
                    // New system expects sub_type for capacity accounting – we create Dev/Test agents here.
                    body: JSON.stringify({ kind, sub_type: subType }),
                });
                const data = await res.json().catch(() => ({}));
                if (!res.ok) {
                    throw new Error(data.detail || `Failed to add ${kind} agent`);
                }
                return data?.agent?.id || null;
            };

            const createdAgentIds = [];
            for (let i = 0; i < sharedDevCount; i += 1) {
                const createdId = await createOne('shared', 'dev');
                if (createdId) createdAgentIds.push(createdId);
            }
            for (let i = 0; i < dedicatedDevCount; i += 1) {
                const createdId = await createOne('dedicated', 'dev');
                if (createdId) createdAgentIds.push(createdId);
            }
            for (let i = 0; i < sharedTestCount; i += 1) {
                const createdId = await createOne('shared', 'test');
                if (createdId) createdAgentIds.push(createdId);
            }
            for (let i = 0; i < dedicatedTestCount; i += 1) {
                const createdId = await createOne('dedicated', 'test');
                if (createdId) createdAgentIds.push(createdId);
            }

            if (createdAgentIds.length > 0 && hasGlobalGitConfigured && taskList.some(t => (t.taskStatus || '').toLowerCase() !== 'completed')) {
                for (const agentId of createdAgentIds) {
                    try {
                        await fetch(withProjectToken(API_ENDPOINTS.AGENT_RUN(agentId)), {
                            method: 'POST',
                            headers,
                        });
                    } catch (e) {
                        console.error('Auto-start failed for agent', agentId, e);
                    }
                }
            }

            const quotaRes = await fetch(API_ENDPOINTS.ORG_AGENT_QUOTA, {
                headers: { Authorization: `Bearer ${token}` },
            });
            const quotaData = await quotaRes.json().catch(() => null);
            if (quotaRes.ok && quotaData) {
                setAgentQuota(quotaData);
            }

            setShowAddAgentModal(false);
            setSharedAgentsToAdd('');
            setDedicatedAgentsToAdd('');
            setSharedTestAgentsToAdd('');
            setDedicatedTestAgentsToAdd('');
            fetchAgents();
            fetchTasks(false, 1, true);
            refreshRoadmap();
        } catch (e) {
            console.error('Add agent failed', e);
            setAddAgentModalError(e.message || 'Failed to add agents');
        } finally {
            setIsAddingAgents(false);
        }
    };

    // const handleRemoveAgent = async (agentId) => {
    //     try {
    //         await fetch(API_ENDPOINTS.AGENT_REMOVE(agentId), {
    //             method: 'DELETE',
    //             headers: { 'Authorization': `Bearer ${token}` },
    //         });
    //         fetchAgents();
    //     } catch (e) {
    //         console.error('Remove agent failed', e);
    //     }
    // };

    // ── Preview Deploy Handlers ──────────────────────────────────────
    const fetchPreviewStatus = useCallback(async () => {
        if (!token) return;
        try {
            const params = selectedProjectKey ? `?project_token=${selectedProjectKey}` : '';
            const res = await fetch(`${API_ENDPOINTS.AGENT_PREVIEW_STATUS}${params}`, {
                headers: { 'Authorization': `Bearer ${token}` },
            });
            if (res.ok) {
                const data = await res.json();
                setPreviewStatus(data);
            }
        } catch (e) {
            console.error('Preview status fetch failed', e);
        }
    }, [token, selectedProjectKey]);

    // Poll preview status when deploying or running
    useEffect(() => {
        if (previewStatus.status === 'deploying' || previewStatus.status === 'running') {
            const interval = setInterval(fetchPreviewStatus, 3000);
            return () => clearInterval(interval);
        }
    }, [previewStatus.status, fetchPreviewStatus]);

    useEffect(() => {
        const status = (previewStatus?.status || '').toLowerCase();
        if (!status || status === 'none') return;
        refreshRoadmap();
    }, [previewStatus?.status, refreshRoadmap]);

    // Check preview status on mount
    useEffect(() => {
        if (token && selectedProjectKey) {
            fetchPreviewStatus();
        }
    }, [token, selectedProjectKey, fetchPreviewStatus]);

    const handleDeployPreview = async () => {
        setIsDeploying(true);
        try {
            const params = selectedProjectKey ? `?project_token=${selectedProjectKey}` : '';
            const res = await fetch(`${API_ENDPOINTS.AGENT_PREVIEW_DEPLOY}${params}`, {
                method: 'POST',
                headers: {
                    'Authorization': `Bearer ${token}`,
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({}),
            });
            if (res.ok) {
                const data = await res.json();
                setPreviewStatus(data);
            } else {
                const err = await res.json().catch(() => ({}));
                customAlert(err.detail || 'Deploy failed', 'Deploy Failed');
            }
        } catch (e) {
            console.error('Deploy preview failed', e);
            customAlert('Deploy failed: ' + e.message, 'Deploy Failed');
        } finally {
            setIsDeploying(false);
        }
    };

    const handleFixWithAI = async () => {
        setIsFixing(true);
        try {
            const params = selectedProjectKey ? `?project_token=${selectedProjectKey}` : '';
            const res = await fetch(`${API_ENDPOINTS.AGENT_PREVIEW_FIX}${params}`, {
                method: 'POST',
                headers: {
                    'Authorization': `Bearer ${token}`,
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({}),
            });
            if (res.ok) {
                const data = await res.json();
                setPreviewStatus(data);
            } else {
                const err = await res.json().catch(() => ({}));
                customAlert(err.detail || 'Fix failed', 'Fix Failed');
            }
        } catch (e) {
            console.error('Fix preview failed', e);
            customAlert('Fix failed: ' + e.message, 'Fix Failed');
        } finally {
            setIsFixing(false);
        }
    };

    const handleStopPreview = async () => {
        try {
            const params = selectedProjectKey ? `?project_token=${selectedProjectKey}` : '';
            await fetch(`${API_ENDPOINTS.AGENT_PREVIEW_STOP}${params}`, {
                method: 'POST',
                headers: { 'Authorization': `Bearer ${token}` },
            });
            setPreviewStatus({ status: 'stopped' });
        } catch (e) {
            console.error('Stop preview failed', e);
        }
    };

    // ── Agent Card Config ────────────────────────────────────────────
    const agentConfig = {
        agent_01: {
            icon: <CheckCircle className="w-5 h-5 text-white" />,
            gradient: 'from-emerald-400 to-app-status-success',
            shadow: 'shadow-emerald-200',
            accent: 'from-emerald-400 to-app-status-success',
            color: 'emerald',
            stats: ['checks', 'coverage', 'avg_time'],
            statLabels: { checks: 'Checks', coverage: 'Coverage', avg_time: 'Duration' },
        },
        agent_02: {
            icon: <Shield className="w-5 h-5 text-white" />,
            gradient: 'from-emerald-400 to-app-status-success',
            shadow: 'shadow-emerald-200',
            accent: 'from-emerald-400 to-app-status-success',
            color: 'emerald',
            stats: ['risks', 'critical', 'avg_time'],
            statLabels: { risks: 'Risks', critical: 'Critical', avg_time: 'Duration' },
        },
        G_agent_01: {
            icon: <GitBranch className="w-5 h-5 text-white" />,
            gradient: 'from-app-primary to-app-primary',
            shadow: 'shadow-app-primary-ring',
            accent: 'from-app-primary to-app-primary',
            color: 'indigo',
            stats: ['avg_time'],
            statLabels: { avg_time: 'Duration' },
        },
        M_agent_01: {
            icon: <Bot className="w-5 h-5 text-white" />,
            logo: masterLogo,
            gradient: 'from-app-bg-page to-app-bg-muted',
            shadow: 'shadow-app-bg-hover',
            accent: 'from-fuchsia-500 to-app-status-error',
            color: 'fuchsia',
            stats: ['avg_time'],
            statLabels: { avg_time: 'Duration' },
        },

    };


    // ── Render Agent Card ────────────────────────────────────────────
    const renderAgentCard = (agent) => {
        const isSystemAgent = agent.agent_kind === 'system';
        const isGitManager = agent.id === 'G_agent_01';
        const isMasterAgent = agent.id === 'M_agent_01';
        const isTest = agent.sub_type === 'test';
        const isShared = agent.id?.startsWith('shared_');
        const isDedicated = agent.id?.startsWith('dedicated_');
        const agentType = isShared ? 'Shared' : isDedicated ? 'Dedicated' : null;
        const displayName = getAgentDisplayName(agent);
        let cfg = agentConfig[agent.id] || agentConfig.agent_01;

        if (isTest) {
            cfg = {
                ...cfg,
                gradient: 'from-orange-400 to-orange-600',
                accent: 'from-orange-400 to-orange-600',
                shadow: 'shadow-orange-200',
                color: 'orange',
                logo: kaktoxLogo,
            };
        }

        const Icon = cfg.icon;
        // Use logo for specific agents, or dev agents use N-Mod logo
        const useLogo = cfg.logo || (isShared || isDedicated);
        const logoSrc = cfg.logo || (useLogo ? nModLogo : null);
        const isRunning = agent.status === 'running';
        const isCompleted = agent.status === 'completed';
        const isError = agent.status === 'error';
        const isIdle = agent.status === 'idle';
        const statusColor = isRunning ? cfg.color : isCompleted ? 'emerald' : isError ? 'red' : 'gray';
        const canRun = taskList.filter(t => (t.taskStatus || '').toLowerCase() !== 'completed').length > 0;

        return (
            <div key={agent.id} className="bg-app-bg-card rounded-xl shadow border border-app-border-light p-4 flex flex-col relative overflow-hidden group hover:shadow-lg transition-shadow">
                <div className={`absolute top-0 left-0 right-0 h-1 bg-gradient-to-r ${cfg.accent}`}></div>

                <div className="flex items-start justify-between mb-4 gap-2">
                    <div className="flex items-center gap-3 min-w-0 flex-1">
                        <div className={`flex-shrink-0 w-10 h-10 rounded-xl ${useLogo ? 'bg-app-bg-page border border-app-border' : `bg-gradient-to-br ${cfg.gradient}`} flex items-center justify-center shadow-lg ${cfg.shadow} ${useLogo ? 'p-1.5' : ''}`}>
                            {useLogo && logoSrc ? (
                                <img src={logoSrc} alt={displayName} className="w-full h-full object-contain" />
                            ) : (
                                Icon
                            )}
                        </div>
                        <div className="min-w-0 flex-1">
                            <div className="flex items-center gap-1.5 flex-wrap">
                                <h4 className="text-sm font-bold text-app-text-main truncate">
                                    {displayName}
                                </h4>
                                {!isSystemAgent && agent.sub_type && (
                                    <span className={`flex-shrink-0 px-2 py-0.5 text-[9px] font-bold rounded-full uppercase tracking-wider ${isTest
                                        ? 'bg-orange-100 text-orange-600 border border-orange-200'
                                        : 'bg-blue-100 text-blue-600 border border-blue-200'
                                        }`}>
                                        {agent.sub_type}
                                    </span>
                                )}
                                {agentType && (
                                    <span className={`flex-shrink-0 px-2 py-0.5 text-[9px] font-bold rounded-full uppercase tracking-wider ${isShared
                                        ? 'bg-app-status-successBg text-app-status-success border border-emerald-200'
                                        : 'bg-app-primary-light text-app-primary-hover border border-app-primary-ring'
                                        }`}>
                                        {agentType}
                                    </span>
                                )}
                            </div>
                            <p className="text-[10px] text-app-text-light uppercase tracking-wider font-semibold truncate">{!isSystemAgent && agent.sub_type && `${agent.sub_type} `}{getNeutralAgentLabel(agent)}</p>
                            {!isSystemAgent && (
                                <p className="text-[10px] text-app-text-light truncate">
                                    Git: {agent.git_repo_url ? 'URL saved' : 'URL missing'} | PAT: {agent.has_git_token ? 'saved' : agent.is_public_repo ? 'not needed (public)' : 'missing'}
                                </p>
                            )}
                        </div>
                    </div>
                    {/* Status + actions — stacks vertically so buttons never get clipped */}
                    <div className="flex flex-col items-end gap-1.5 flex-shrink-0">
                        {/* Status indicator */}
                        <div className="flex items-center gap-1.5">
                            {isRunning && (
                                <span className="relative flex h-2.5 w-2.5">
                                    <span className={`animate-ping absolute inline-flex h-full w-full rounded-full bg-${statusColor}-400 opacity-75`}></span>
                                    <span className={`relative inline-flex rounded-full h-2.5 w-2.5 bg-${statusColor}-500`}></span>
                                </span>
                            )}
                            <span className={`text-[10px] font-bold text-${statusColor}-${isIdle ? '500' : '600'} whitespace-nowrap`}>
                                {isRunning ? 'RUNNING' : (isIdle ? 'IDLE' : (isCompleted ? 'COMPLETED' : (isError ? 'ERROR' : 'NOT STARTED')))}
                            </span>
                        </div>
                        {/* Action buttons */}
                        <div className="flex items-center gap-1">
                            {!isSystemAgent && (
                                (isIdle || isCompleted || isError) ? (
                                    <button
                                        onClick={() => handleRunAgentClick(agent)}
                                        disabled={!canRun || runningAgent === agent.id}
                                        className={`inline-flex items-center justify-center gap-1 px-2 py-1 text-[10px] font-bold text-white rounded shadow-sm transition-all whitespace-nowrap ${canRun
                                            ? `bg-gradient-to-r ${cfg.gradient} hover:shadow-md`
                                            : 'bg-app-border cursor-not-allowed'
                                            }`}
                                        title={!canRun ? 'No pending tasks available' : `Run ${displayName}`}
                                    >
                                        {runningAgent === agent.id ? (<><Loader2 className="w-2.5 h-2.5 animate-spin" /> Starting</>) : (<><Play className="w-2.5 h-2.5" /> Run</>)}
                                    </button>
                                ) : (
                                    <button
                                        onClick={() => handleResetAgent(agent.id)}
                                        className="inline-flex items-center justify-center gap-1 px-2 py-1 text-[10px] font-bold text-white bg-app-status-error hover:bg-app-status-error rounded shadow-sm whitespace-nowrap"
                                        title="Stop agent"
                                    >
                                        <StopCircle className="w-2.5 h-2.5" /> Stop
                                    </button>
                                )
                            )}
                            <button
                                onClick={() => setShowLogModal(agent.id)}
                                className="inline-flex items-center justify-center gap-1 px-2 py-1 text-[10px] font-bold text-app-text-label bg-app-bg-muted rounded hover:bg-app-bg-hover transition-colors whitespace-nowrap"
                            >
                                <Terminal className="w-2.5 h-2.5" /> Log
                            </button>
                            {!isSystemAgent && (isCompleted || isError) && (
                                <button
                                    onClick={() => handleResetAgent(agent.id)}
                                    className="inline-flex items-center justify-center gap-1 px-2 py-1 text-[10px] font-bold text-app-text-label bg-app-bg-muted rounded hover:bg-app-bg-hover transition-colors"
                                    title="Reset agent to idle"
                                >
                                    <RefreshCw className="w-2.5 h-2.5" />
                                </button>
                            )}
                        </div>
                    </div>
                </div>

                {/* Stats */}
                <div className="flex items-center gap-3 mb-3 py-1.5 px-2.5 bg-app-bg-page rounded-lg">
                    {cfg.stats.map((key, idx) => (
                        <React.Fragment key={key}>
                            {idx > 0 && <div className="w-px h-8 bg-app-bg-hover"></div>}
                            <div className="text-center">
                                <p className="text-lg font-bold text-app-text-main">{agent.stats?.[key] ?? '—'}</p>
                                <p className="text-[9px] text-app-text-light uppercase font-semibold">{cfg.statLabels[key]}</p>
                            </div>
                        </React.Fragment>
                    ))}
                </div>

                {/* Progress bar when running */}
                {isRunning && (
                    <div className="mb-4">
                        <div className="flex justify-between text-[10px] text-app-text-light mb-1">
                            <span className="truncate max-w-[180px]">{agent.progress_message || 'Processing...'}</span>
                            <span className={`font-bold text-${cfg.color}-600`}>{agent.progress}%</span>
                        </div>
                        <div className="w-full bg-app-bg-muted rounded-full h-1.5 overflow-hidden">
                            <div className={`bg-gradient-to-r ${cfg.accent} h-1.5 rounded-full transition-all duration-1000 ease-out`} style={{ width: `${agent.progress}%` }}></div>
                        </div>
                    </div>
                )}

                {/* Status summary (without last run time) */}
                <div className="flex items-center justify-end text-[10px] text-app-text-light mb-4">
                    {isCompleted && <span className="font-semibold text-app-status-success">✓ Completed</span>}
                    {isError && <span className="font-semibold text-app-status-error">✗ Error</span>}
                </div>
                {/* Error details when agent has errored */}
                {isError && agent.progress_message && (
                    <div className="mb-3 px-3 py-2 bg-app-status-errorBg border border-red-200 rounded-lg">
                        <p className="text-[11px] text-app-status-error font-medium break-all leading-relaxed">
                            {agent.progress_message}
                        </p>
                    </div>
                )}
            </div >
        );
    };

    const handleGenerateTasks = async () => {
        if (!selectedProjectKey) return;
        setIsGeneratingTasks(true);


        try {
            const token = localStorage.getItem('token');
            const { API_ENDPOINTS } = await import('../config.js');
            const headers = {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${token}`
            };
            if (hasValidTaskToken) headers['x-task-token'] = taskToken;

            // Include prerequisites data if available
            let prerequisitesPayload = null;
            try {
                const savedPrereqs = localStorage.getItem(`prerequisites_completed_${selectedProjectKey}`);
                if (savedPrereqs) {
                    const parsed = JSON.parse(savedPrereqs);
                    const parsedItems = Array.isArray(parsed?.items) ? parsed.items : [];
                    prerequisitesPayload = parsedItems
                        .map((item) => sanitizePrerequisiteForAiPayload(item))
                        .filter((item) => item.name || item.description);
                }
            } catch { /* ignore */ }

            const requestBody = {
                project_token: selectedProjectKey,
                process_mode: processMode,
            };
            if (prerequisitesPayload && prerequisitesPayload.length > 0) {
                requestBody.prerequisites = prerequisitesPayload;
            }

            const response = await fetch(API_ENDPOINTS.AGENT_AUTO_GENERATE, {
                method: 'POST',
                headers,
                body: JSON.stringify(requestBody)
            });

            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.detail || 'Failed to generate tasks');
            }

            await response.json();

            // Refresh the task list and project info to show newly created tasks
            await fetchTasks();
            await queryClient.invalidateQueries({ queryKey: ['projectInfo', selectedProjectKey, taskToken] });
        } catch (err) {
            console.error(err.message);
        } finally {
            setIsGeneratingTasks(false);
        }
    };



    const renderDashboardSkeleton = () => (
        <SkeletonTheme baseColor="#e5e7eb" highlightColor="#f3f4f6">
            <div className="flex-1 p-3 sm:p-4 md:p-5 flex flex-col gap-4">
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                    {[0, 1, 2, 3].map((idx) => (
                        <div key={idx} className="bg-app-bg-card p-4 rounded-xl shadow border border-app-border-light">
                            <Skeleton height={12} width="45%" />
                            <div className="mt-2">
                                <Skeleton height={30} width="70%" />
                            </div>
                            <div className="mt-2">
                                <Skeleton height={10} width="35%" />
                            </div>
                        </div>
                    ))}
                </div>

                <div className="grid grid-cols-1 lg:grid-cols-[minmax(0,1fr)_320px] gap-4 md:gap-5 w-full items-start">
                    <div className="space-y-4 lg:col-start-1 w-full min-w-0">
                        <div className="bg-app-bg-card rounded-xl shadow border border-app-border-light p-5">
                            <Skeleton height={20} width={220} />
                            <div className="mt-5 space-y-3">
                                {[0, 1, 2, 3].map((i) => (
                                    <div key={i} className="grid grid-cols-3 gap-4">
                                        <Skeleton height={14} />
                                        <Skeleton height={14} />
                                        <Skeleton height={14} />
                                    </div>
                                ))}
                            </div>
                        </div>

                        <div className="bg-app-bg-card rounded-xl shadow border border-app-border-light p-5">
                            <Skeleton height={20} width={260} />
                            <div className="mt-6 flex items-end justify-center gap-6">
                                <Skeleton height={160} width={120} />
                                <div className="space-y-3">
                                    <div className="flex items-center gap-2">
                                        <Skeleton height={14} width={24} />
                                        <Skeleton height={12} width={140} />
                                    </div>
                                    <div className="flex items-center gap-2">
                                        <Skeleton height={14} width={24} />
                                        <Skeleton height={12} width={140} />
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>

                    <div className="w-full bg-app-bg-card rounded-xl shadow border border-app-border-light p-4 md:p-5 flex flex-col items-center lg:col-start-2">
                        <Skeleton height={28} width={170} />
                        <div className="w-full mt-4 mb-6">
                            <Skeleton height={2} />
                        </div>
                        <Skeleton circle width={96} height={96} />
                        <div className="mt-3">
                            <Skeleton height={14} width={130} />
                        </div>
                        <div className="w-full mt-6 space-y-5">
                            {[0, 1, 2].map((i) => (
                                <div key={i} className="flex flex-col items-center">
                                    <Skeleton circle width={92} height={92} />
                                    <div className="mt-3">
                                        <Skeleton height={12} width={120} />
                                    </div>
                                </div>
                            ))}
                        </div>
                    </div>
                </div>

                <div className="w-full mt-4 lg:col-span-2 min-w-0">
                    <div className="flex items-center justify-between mb-4">
                        <Skeleton height={24} width={180} />
                        <div className="flex items-center gap-2">
                            <Skeleton height={28} width={90} />
                            <Skeleton height={28} width={80} />
                            <Skeleton height={28} width={90} />
                        </div>
                    </div>
                    <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-4">
                        {[0, 1, 2].map((idx) => (
                            <div key={idx} className="bg-app-bg-card rounded-xl shadow border border-app-border-light p-4">
                                <div className="flex items-center justify-between">
                                    <Skeleton circle width={40} height={40} />
                                    <Skeleton height={12} width={56} />
                                </div>
                                <div className="mt-4">
                                    <Skeleton height={14} width="70%" />
                                </div>
                                <div className="mt-2">
                                    <Skeleton height={10} width="45%" />
                                </div>
                                <div className="mt-5 space-y-2">
                                    <Skeleton height={8} />
                                    <Skeleton height={8} />
                                </div>
                                <div className="mt-5 flex gap-2">
                                    <Skeleton height={30} width={80} />
                                    <Skeleton height={30} width={80} />
                                </div>
                            </div>
                        ))}
                    </div>
                </div>
            </div>
        </SkeletonTheme>
    );

    const renderGeneratedTasksSkeleton = () => (
        <SkeletonTheme baseColor="#e5e7eb" highlightColor="#f3f4f6">
            <div className="px-4 md:px-6 pb-6">
                <div className="bg-app-bg-card rounded-2xl shadow-sm border border-app-border-light overflow-hidden">
                    <div className="px-6 py-4 border-b border-app-border-light flex items-center justify-between bg-gradient-to-r from-app-bg-page/80 to-app-bg-card">
                        <div className="flex items-center gap-3">
                            <Skeleton circle width={36} height={36} />
                            <div>
                                <Skeleton height={14} width={140} />
                                <div className="mt-1">
                                    <Skeleton height={10} width={220} />
                                </div>
                            </div>
                        </div>
                        <Skeleton height={28} width={86} />
                    </div>

                    <div className="hidden md:block bg-app-bg-page/50 border-b border-app-border-light px-6 py-2.5">
                        <div style={{ display: 'grid', gridTemplateColumns: '40px 1fr 140px 90px 80px 120px 60px 130px', gap: '8px', alignItems: 'center' }}>
                            {[0, 1, 2, 3, 4, 5, 6, 7].map((idx) => (
                                <Skeleton key={idx} height={10} />
                            ))}
                        </div>
                    </div>

                    <div className="divide-y divide-app-bg-page p-4 md:p-0">
                        {[0, 1, 2, 3, 4, 5].map((row) => (
                            <div key={row} className="px-6 py-3">
                                <div className="hidden md:grid" style={{ gridTemplateColumns: '40px 1fr 140px 90px 80px 120px 60px 130px', gap: '8px', alignItems: 'center' }}>
                                    <Skeleton height={10} width={18} />
                                    <div>
                                        <Skeleton height={13} width="58%" />
                                        <div className="mt-1">
                                            <Skeleton height={10} width="72%" />
                                        </div>
                                    </div>
                                    <Skeleton height={10} width={110} />
                                    <Skeleton height={18} width={70} />
                                    <Skeleton height={18} width={62} />
                                    <Skeleton height={12} width={92} />
                                    <Skeleton height={10} width={42} />
                                    <Skeleton height={10} width={94} />
                                </div>
                                <div className="md:hidden space-y-2">
                                    <Skeleton height={14} />
                                    <Skeleton height={10} width="70%" />
                                </div>
                            </div>
                        ))}
                    </div>
                </div>
            </div>
        </SkeletonTheme>
    );

    const selectedRoleMeta = DASHBOARD_ROLES.find((role) => role.value === selectedRole) || DASHBOARD_ROLES[1];
    const overallHealth = dashboardData?.project_status?.overall_health || 'Unknown';
    const lateTaskCount = dashboardData?.tasks?.late_tasks?.length || 0;
    const upcomingTaskCount = dashboardData?.tasks?.upcoming_tasks_next_period?.length || 0;
    const dueThisWeekCount = dashboardData?.tasks?.due_this_week?.length || 0;
    const inProgressTaskCount = dashboardData?.tasks?.in_progress?.length || 0;
    const completedTaskCount = dashboardData?.tasks?.recently_completed?.length || 0;
    const projectWallet = Number(projectInfo?.project?.project_wallet || 0) || 0;
    const usedWallet = (taskList || []).reduce((total, task) => total + (Number(task?.task_wallet) || 0), 0);
    const remainingWallet = Math.max(projectWallet - usedWallet, 0);
    const launchConfidence = overallHealth === 'Good' ? 'High'
        : overallHealth === 'At Risk' ? 'Medium'
            : 'Low';
    const cxoRiskLabel = lateTaskCount > 0 || overallHealth === 'Critical' ? 'High'
        : overallHealth === 'At Risk' ? 'Medium'
            : 'Low';
    const workCompletedPct = Math.max(0, Math.min(100, Number(dashboardData?.actual_vs_remaining_work?.work_completed_percentage ?? 0)));
    const workRemainingPct = Math.max(0, Math.min(100, Number(dashboardData?.actual_vs_remaining_work?.work_remaining_percentage ?? 0)));
    const workTotalPct = workCompletedPct + workRemainingPct;
    const donutCompletedPct = workTotalPct > 0 ? (workCompletedPct / workTotalPct) * 100 : 0;
    const donutRemainingPct = workTotalPct > 0 ? (workRemainingPct / workTotalPct) * 100 : 0;
    const donutRadius = 56;
    const donutCircumference = 2 * Math.PI * donutRadius;
    const donutCompletedLength = (donutCompletedPct / 100) * donutCircumference;
    const donutRemainingLength = (donutRemainingPct / 100) * donutCircumference;
    const workCompletedDisplay = Number.isFinite(workCompletedPct) ? Number(workCompletedPct.toFixed(1)) : 0;
    const workRemainingDisplay = Number.isFinite(workRemainingPct) ? Number(workRemainingPct.toFixed(1)) : 0;
    const salesSignals = [
        {
            label: 'Pipeline Stage',
            value: dashboardData?.sales?.pipeline_stage || dashboardData?.project?.status || 'Backend field needed',
        },
        {
            label: 'Deal Owner',
            value: dashboardData?.sales?.deal_owner || 'Backend field needed',
        },
        {
            label: 'Win Probability',
            value: dashboardData?.sales?.win_probability || 'Backend field needed',
        },
        {
            label: 'Booked Revenue',
            value: dashboardData?.sales?.booked_revenue || 'Backend field needed',
        },
    ];

    // Dev/Test-agent specific remaining capacity for the Add Agents modal
    const sharedDevAvailableForModal = useMemo(() => {
        if (!agentQuota) return 0;
        const sharedDevQuota = Number(agentQuota.shared_dev_quota ?? 0);
        const sharedDevUsed = agents.filter(
            (a) => a.id?.startsWith('shared_') && (!a.sub_type || a.sub_type === 'dev')
        ).length;
        return Math.max(0, sharedDevQuota - sharedDevUsed);
    }, [agentQuota, agents]);

    const dedicatedDevAvailableForModal = useMemo(() => {
        if (!agentQuota) return 0;
        const dedicatedDevQuota = Number(agentQuota.dedicated_dev_quota ?? 0);
        const dedicatedDevUsed = agents.filter(
            (a) => a.id?.startsWith('dedicated_') && (!a.sub_type || a.sub_type === 'dev')
        ).length;
        return Math.max(0, dedicatedDevQuota - dedicatedDevUsed);
    }, [agentQuota, agents]);

    const sharedTestAvailableForModal = useMemo(() => {
        if (!agentQuota) return 0;
        const sharedTestQuota = Number(agentQuota.shared_test_quota ?? 0);
        const sharedTestUsed = agents.filter(
            (a) => a.id?.startsWith('shared_') && a.sub_type === 'test'
        ).length;
        return Math.max(0, sharedTestQuota - sharedTestUsed);
    }, [agentQuota, agents]);

    const dedicatedTestAvailableForModal = useMemo(() => {
        if (!agentQuota) return 0;
        const dedicatedTestQuota = Number(agentQuota.dedicated_test_quota ?? 0);
        const dedicatedTestUsed = agents.filter(
            (a) => a.id?.startsWith('dedicated_') && a.sub_type === 'test'
        ).length;
        return Math.max(0, dedicatedTestQuota - dedicatedTestUsed);
    }, [agentQuota, agents]);

    return (
        <div className="w-full h-full bg-app-bg-page flex flex-col font-sans overflow-y-auto relative">
            {/* Top Graphic Header Area */}
            <div className="bg-app-bg-card shadow">

                {/* Top spacer since title is now in global navbar */}
                <div className="pt-2 md:pt-3"></div>
                <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center px-3 sm:px-4 md:px-6 py-1.5 mb-1 gap-2">
                    <div className="flex items-center space-x-4 flex-shrink-0">
                        {projects.length > 0 && (
                            <>
                                <div className="text-sm font-bold text-[#f27a24]">As of : {dashboardData?.generated_at ? new Date(dashboardData.generated_at).toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: '2-digit' }) : new Date().toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: '2-digit' })}</div>
                                <div className="text-sm font-bold text-app-text-main flex items-center">
                                    <div className={`w-4 h-4 mr-2 rounded-sm shadow-sm inline-block ${dashboardData?.project_status?.overall_health === 'Good' ? 'bg-app-status-success' : dashboardData?.project_status?.overall_health === 'At Risk' ? 'bg-app-status-warning' : 'bg-app-status-error'}`}></div>
                                    Overall: {dashboardData?.project_status?.overall_health ?? '—'}
                                </div>
                            </>
                        )}
                    </div>
                    {/* Dropdowns have been moved to AppLayout global navbar */}
                </div>
            </div>

            {/* Empty State vs Full Data */}
            {isInitialProjectsLoading ? (
                renderDashboardSkeleton()
            ) : projects.length === 0 ? (
                <div className="flex-1 p-3 sm:p-4 md:p-5 flex flex-col items-center justify-center min-h-[360px]">
                    <div className="bg-app-bg-card rounded-2xl shadow-sm border border-app-border-light p-10 max-w-md w-full text-center flex flex-col items-center">
                        <div className="w-20 h-20 bg-app-primary-light rounded-full flex items-center justify-center mb-6 shadow-inner">
                            <PlusCircle className="w-10 h-10 text-app-primary" />
                        </div>
                        <h2 className="text-2xl font-extrabold text-app-text-main mb-2">No Projects Found</h2>
                        <p className="text-app-text-muted mb-8 text-sm leading-relaxed">
                            It looks like you haven't created any screening assessments yet. Add a new project to start tracking your progress and metrics.
                        </p>
                        <button
                            type="button"
                            onClick={() => setShowModal(true)}
                            className="inline-flex items-center gap-2 bg-gradient-to-r from-app-primary to-app-primary text-white font-bold py-3.5 px-8 rounded-full shadow-lg shadow-app-primary/30 hover:shadow-app-primary/50 hover:-translate-y-0.5 transition-all w-full justify-center"
                        >
                            <PlusCircle className="w-5 h-5" />
                            <span>Add New Project</span>
                        </button>
                    </div>
                </div>
            ) : isDashboardSkeletonVisible ? (
                renderDashboardSkeleton()
            ) : (
                <div className="flex-1 p-3 sm:p-4 md:p-5 flex flex-col gap-4">
                    <div className="bg-app-bg-card rounded-xl border border-app-border-light shadow-sm px-4 py-3 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
                        <div>
                            <p className="text-[10px] uppercase tracking-widest font-bold text-app-text-light">Active Role View</p>
                            <p className="text-sm font-bold text-app-text-main">{selectedRoleMeta.label}</p>
                        </div>
                        <p className="text-xs text-app-text-muted">{selectedRoleMeta.description}</p>
                    </div>

                    {selectedRole === 'cxo' && (
                        <>


                            <div className="grid grid-cols-2 lg:grid-cols-5 gap-4">
                                <div className="bg-app-bg-card rounded-xl border border-app-border-light p-4 shadow-sm">
                                    <p className="text-[11px] font-bold text-app-text-muted uppercase tracking-wide">Overall Health</p>
                                    <p className="text-2xl font-bold text-app-text-main mt-2">{overallHealth}</p>
                                </div>
                                <div className="bg-app-bg-card rounded-xl border border-app-border-light p-4 shadow-sm">
                                    <p className="text-[11px] font-bold text-app-text-muted uppercase tracking-wide">Launch Confidence</p>
                                    <p className="text-2xl font-bold text-app-text-main mt-2">{launchConfidence}</p>
                                </div>
                                <div className="bg-app-bg-card rounded-xl border border-app-border-light p-4 shadow-sm">
                                    <p className="text-[11px] font-bold text-app-text-muted uppercase tracking-wide">Completion</p>
                                    <p className="text-2xl font-bold text-app-text-main mt-2">{dashboardData?.kpi?.completion_percentage ?? 0}%</p>
                                </div>
                                <div className="bg-app-bg-card rounded-xl border border-app-border-light p-4 shadow-sm">
                                    <p className="text-[11px] font-bold text-app-text-muted uppercase tracking-wide">Launch In</p>
                                    <p className="text-2xl font-bold text-app-text-main mt-2">{dashboardData?.project_status?.days_until_launch ?? 0} days</p>
                                </div>
                                <div className="bg-app-bg-card rounded-xl border border-app-border-light p-4 shadow-sm">
                                    <p className="text-[11px] font-bold text-app-text-muted uppercase tracking-wide">Project Budget</p>
                                    <p className="text-2xl font-bold text-app-text-main mt-2">{projectInfo?.project?.project_wallet ?? '-'}</p>
                                </div>
                            </div>

                            <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 md:gap-5">
                                <div className="lg:col-span-2 bg-app-bg-card rounded-xl shadow border border-app-border-light p-5">
                                    <div className="flex items-center mb-5">
                                        <Flag className="w-4 h-4 text-orange-500 mr-2" />
                                        <h3 className="text-sm font-bold text-app-text-main uppercase tracking-wide">Milestone Visibility</h3>
                                    </div>
                                    <div className="overflow-auto rounded-lg border border-app-border-light" style={{ maxHeight: '320px' }}>
                                        <table className="min-w-full text-sm">
                                            <thead className="bg-orange-50 sticky top-0 z-10">
                                                <tr>
                                                    <th className="px-4 py-3 text-left font-bold text-app-text-label">Milestone</th>
                                                    <th className="px-4 py-3 text-left font-bold text-app-text-label">Status</th>
                                                    <th className="px-4 py-3 text-left font-bold text-app-text-label">Date</th>
                                                </tr>
                                            </thead>
                                            <tbody className="divide-y divide-app-bg-muted text-app-text-label">
                                                {(dashboardData?.milestones?.completed || []).map((milestone) => (
                                                    <tr key={`done-${milestone.id}`}>
                                                        <td className="px-4 py-3">{milestone.name}</td>
                                                        <td className="px-4 py-3 text-app-status-success font-semibold">Completed</td>
                                                        <td className="px-4 py-3">{milestone.deadline || '-'}</td>
                                                    </tr>
                                                ))}
                                                {(dashboardData?.milestones?.key_milestones_and_dates || []).map((milestone) => (
                                                    <tr key={`open-${milestone.id}`}>
                                                        <td className="px-4 py-3">{milestone.name}</td>
                                                        <td className="px-4 py-3 text-app-status-warning font-semibold">In Progress</td>
                                                        <td className="px-4 py-3">{milestone.deadline || '-'}</td>
                                                    </tr>
                                                ))}
                                                {!(dashboardData?.milestones?.completed?.length || dashboardData?.milestones?.key_milestones_and_dates?.length) && (
                                                    <tr>
                                                        <td className="px-4 py-6 text-center text-app-text-light italic" colSpan="3">No milestone records available</td>
                                                    </tr>
                                                )}
                                            </tbody>
                                        </table>
                                    </div>
                                </div>

                                <div className="space-y-4">
                                    <div className="bg-app-bg-card rounded-xl border border-app-border-light p-5 shadow-sm">
                                        <p className="text-[11px] font-bold text-app-text-muted uppercase tracking-wide">Risk Exposure</p>
                                        <p className="text-3xl font-bold text-app-text-main mt-2">{cxoRiskLabel}</p>
                                        <p className="text-xs text-app-text-muted mt-1">{lateTaskCount} late task(s) currently flagged</p>
                                    </div>
                                    <div className="bg-app-bg-card rounded-xl border border-app-border-light p-5 shadow-sm">
                                        <p className="text-[11px] font-bold text-app-text-muted uppercase tracking-wide">Workload Split</p>
                                        <p className="text-2xl font-bold text-app-text-main mt-2">
                                            {dashboardData?.actual_vs_remaining_work?.work_completed_percentage ?? 0}% complete
                                        </p>
                                        <p className="text-xs text-app-text-muted mt-1">
                                            {dashboardData?.actual_vs_remaining_work?.work_remaining_percentage ?? 0}% remaining effort
                                        </p>
                                    </div>
                                    <div className="bg-app-bg-card rounded-xl border border-app-border-light p-5 shadow-sm">
                                        <p className="text-[11px] font-bold text-app-text-muted uppercase tracking-wide">Task Distribution</p>
                                        <p className="text-2xl font-bold text-app-text-main mt-2">{dashboardData?.summary_statistics?.total_tasks ?? 0}</p>
                                        <p className="text-xs text-app-text-muted mt-1">
                                            {dashboardData?.summary_statistics?.in_progress_tasks ?? 0} in progress, {dashboardData?.summary_statistics?.completed_tasks ?? 0} completed
                                        </p>
                                    </div>
                                </div>
                            </div>
                        </>
                    )}

                    {selectedRole === 'sales' && (
                        <>
                            <div className="rounded-2xl bg-gradient-to-r from-orange-500 to-app-status-warning text-white p-6 shadow-lg">
                                <p className="text-[11px] uppercase tracking-[0.2em] text-orange-100 font-bold mb-2">Commercial Snapshot</p>
                                <h3 className="text-2xl font-bold">Sales Commitment Dashboard</h3>
                                <p className="text-sm text-orange-100 mt-2">
                                    Delivery commitments, budget posture, and deal-facing metrics for customer communication.
                                </p>
                            </div>

                            <div className="grid grid-cols-2 lg:grid-cols-5 gap-4">
                                <div className="bg-app-bg-card rounded-xl border border-app-border-light p-4 shadow-sm">
                                    <p className="text-[11px] font-bold text-app-text-muted uppercase tracking-wide">Project Status</p>
                                    <p className="text-xl font-bold text-app-text-main mt-2">{dashboardData?.project?.status || '-'}</p>
                                </div>
                                <div className="bg-app-bg-card rounded-xl border border-app-border-light p-4 shadow-sm">
                                    <p className="text-[11px] font-bold text-app-text-muted uppercase tracking-wide">Total Wallet</p>
                                    <p className="text-xl font-bold text-app-text-main mt-2">{projectInfo?.project?.project_wallet ?? '-'}</p>
                                </div>
                                <div className="bg-app-bg-card rounded-xl border border-app-border-light p-4 shadow-sm">
                                    <p className="text-[11px] font-bold text-app-text-muted uppercase tracking-wide">Consumed Wallet</p>
                                    <p className="text-xl font-bold text-app-text-main mt-2">{usedWallet}</p>
                                </div>
                                <div className="bg-app-bg-card rounded-xl border border-app-border-light p-4 shadow-sm">
                                    <p className="text-[11px] font-bold text-app-text-muted uppercase tracking-wide">Remaining Wallet</p>
                                    <p className="text-xl font-bold text-app-text-main mt-2">{remainingWallet}</p>
                                </div>
                                <div className="bg-app-bg-card rounded-xl border border-app-border-light p-4 shadow-sm">
                                    <p className="text-[11px] font-bold text-app-text-muted uppercase tracking-wide">Delivery Team</p>
                                    <p className="text-xl font-bold text-app-text-main mt-2">{projectInfo?.team_members?.length ?? 0}</p>
                                </div>
                            </div>

                            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 md:gap-5">
                                <div className="bg-app-bg-card rounded-xl border border-app-border-light shadow-sm p-5">
                                    <div className="flex items-center mb-5">
                                        <Calendar className="w-4 h-4 text-orange-500 mr-2" />
                                        <h3 className="text-sm font-bold text-app-text-main uppercase tracking-wide">Client-Facing Delivery Commitments</h3>
                                    </div>
                                    <div className="space-y-3">
                                        <div className="flex items-center justify-between p-3 rounded-lg bg-orange-50">
                                            <span className="text-sm font-semibold text-app-text-label">Due This Week</span>
                                            <span className="text-lg font-bold text-orange-600">{dueThisWeekCount}</span>
                                        </div>
                                        <div className="flex items-center justify-between p-3 rounded-lg bg-app-bg-page">
                                            <span className="text-sm font-semibold text-app-text-label">Upcoming Next Period</span>
                                            <span className="text-lg font-bold text-app-text-main">{upcomingTaskCount}</span>
                                        </div>
                                        <div className="flex items-center justify-between p-3 rounded-lg bg-app-status-errorBg">
                                            <span className="text-sm font-semibold text-app-text-label">Late Tasks</span>
                                            <span className="text-lg font-bold text-app-status-error">{lateTaskCount}</span>
                                        </div>
                                        <div className="flex items-center justify-between p-3 rounded-lg bg-app-primary-light">
                                            <span className="text-sm font-semibold text-app-text-label">In Progress</span>
                                            <span className="text-lg font-bold text-app-primary">{inProgressTaskCount}</span>
                                        </div>
                                    </div>
                                </div>

                                <div className="bg-app-bg-card rounded-xl border border-app-border-light shadow-sm p-5">
                                    <div className="flex items-center mb-5">
                                        <Tag className="w-4 h-4 text-orange-500 mr-2" />
                                        <h3 className="text-sm font-bold text-app-text-main uppercase tracking-wide">Delivery Readiness</h3>
                                    </div>
                                    <div className="space-y-4">
                                        <div className="p-3 rounded-lg bg-app-bg-page border border-app-border-light">
                                            <p className="text-[11px] font-bold text-app-text-muted uppercase tracking-wide">Expected Launch Date</p>
                                            <p className="text-sm font-bold text-app-text-main mt-1">
                                                {dashboardData?.project_status?.expected_launch_date
                                                    ? new Date(dashboardData.project_status.expected_launch_date).toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: '2-digit' })
                                                    : '-'}
                                            </p>
                                        </div>
                                        <div className="p-3 rounded-lg bg-app-bg-page border border-app-border-light">
                                            <p className="text-[11px] font-bold text-app-text-muted uppercase tracking-wide">Completion Status</p>
                                            <p className="text-sm font-bold text-app-text-main mt-1">
                                                {dashboardData?.kpi?.completion_percentage ?? 0}% complete, {completedTaskCount} recently completed
                                            </p>
                                        </div>
                                        <div className="p-3 rounded-lg bg-app-bg-page border border-app-border-light">
                                            <p className="text-[11px] font-bold text-app-text-muted uppercase tracking-wide">Overall Health Signal</p>
                                            <p className="text-sm font-bold text-app-text-main mt-1">{overallHealth}</p>
                                        </div>
                                    </div>
                                </div>
                            </div>

                            <div className="bg-app-bg-card rounded-xl border border-app-border-light shadow-sm p-5">
                                <h3 className="text-sm font-bold text-app-text-main uppercase tracking-wide mb-4">Sales Signals</h3>
                                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                                    {salesSignals.map((signal) => (
                                        <div key={signal.label} className="rounded-lg border border-app-border-light bg-app-bg-page p-4">
                                            <p className="text-[11px] font-bold text-app-text-muted uppercase tracking-wide">{signal.label}</p>
                                            <p className="text-sm font-bold text-app-text-main mt-2">{signal.value}</p>
                                        </div>
                                    ))}
                                </div>
                                <p className="text-xs text-app-text-muted mt-4">
                                    Fields showing "Backend field needed" can be connected once sales data APIs are available.
                                </p>
                            </div>
                        </>
                    )}

                    {selectedRole === 'project' && (
                        <>

                            {/* Top Metric Cards - Compact Full Width */}
                            <div className="w-full mb-4">
                                <div className="grid grid-cols-2 lg:grid-cols-4 xl:grid-cols-8 gap-3">
                                    {/* Project Info - Spans 2 */}
                                    <div className="bg-gradient-to-br from-app-bg-card to-app-bg-page/50 p-3.5 rounded-xl shadow-sm border border-app-border-light flex flex-col justify-center col-span-2">
                                        <div className="flex justify-between items-start mb-2">
                                            <p className="text-[10px] font-bold text-app-text-label uppercase tracking-widest flex items-center gap-1.5"><Tag className="w-3 h-3 text-indigo-400" /> Project</p>
                                            <span className="text-[9px] px-2 py-0.5 bg-app-primary-light text-app-primary rounded uppercase tracking-widest font-black border border-app-primary-light">{dashboardData?.project?.status ?? '—'}</span>
                                        </div>
                                        <h3 className="text-sm font-bold text-app-text-main truncate mb-1 pl-0.5">{dashboardData?.project?.name ?? '—'}</h3>
                                        <div className="flex items-center gap-1.5 pl-0.5">
                                            <Clock className="w-3.5 h-3.5 text-app-text-muted" />
                                            <p className="text-[10px] font-semibold text-app-text-muted">{dashboardData?.kpi?.duration_days ?? 0} Days Duration</p>
                                        </div>
                                    </div>

                                    {/* Hours Logged - Spans 2 */}
                                    <div className="bg-gradient-to-br from-app-bg-card to-app-bg-page/50 p-3.5 rounded-xl shadow-sm border border-app-border-light flex flex-col justify-center col-span-2">
                                        <p className="text-[10px] font-bold text-app-text-label uppercase tracking-widest mb-1 pl-0.5">Hours Logged</p>
                                        <div className="flex items-center justify-between mb-1.5 pl-0.5">
                                            <h3 className="text-xl font-black text-app-text-main mb-0">{dashboardData?.kpi?.total_hours_logged ?? 0}</h3>
                                            <span className="text-xs font-black text-app-primary">{dashboardData?.kpi?.work_complete_percentage ?? 0}%</span>
                                        </div>
                                        <div className="w-full bg-app-primary-light rounded-full h-1.5">
                                            <div className="bg-gradient-to-r from-indigo-400 to-app-primary h-1.5 rounded-full" style={{ width: `${dashboardData?.kpi?.work_complete_percentage ?? 0}%` }}></div>
                                        </div>
                                    </div>

                                    {/* Active Sprints */}
                                    <div className="bg-app-bg-card p-3 rounded-xl shadow-sm border border-app-border-light flex flex-col justify-center hover:border-app-primary-ring transition-colors">
                                        <p className="text-[10px] font-bold text-app-text-label uppercase tracking-wider mb-1 flex items-center gap-1"><RefreshCw className="w-3 h-3" /> Sprints</p>
                                        <h3 className="text-xl font-black text-app-text-main mb-0.5">{dashboardData?.summary_statistics?.active_sprints ?? 0} <span className="text-xs text-app-text-light font-medium tracking-normal">/ {dashboardData?.summary_statistics?.total_sprints ?? 0}</span></h3>
                                        <p className="text-[9px] font-semibold text-app-text-muted uppercase tracking-wider">Active</p>
                                    </div>

                                    {/* Pending */}
                                    <div className="bg-app-bg-card p-3 rounded-xl shadow-sm border border-app-border-light flex flex-col justify-center hover:border-amber-200 transition-colors">
                                        <p className="text-[10px] font-bold text-app-text-label uppercase tracking-wider mb-1 flex items-center gap-1"><AlertCircle className="w-3 h-3 text-app-status-warning" /> Pending</p>
                                        <h3 className="text-xl font-black text-app-status-warning mb-0.5">{dashboardData?.summary_statistics?.pending_tasks ?? 0}</h3>
                                        <p className="text-[9px] font-semibold text-app-text-muted uppercase tracking-wider">Tasks</p>
                                    </div>

                                    {/* In Progress */}
                                    <div className="bg-app-bg-card p-3 rounded-xl shadow-sm border border-app-border-light flex flex-col justify-center hover:border-app-primary-ring transition-colors">
                                        <p className="text-[10px] font-bold text-app-text-label uppercase tracking-wider mb-1 flex items-center gap-1"><Activity className="w-3 h-3 text-app-primary" /> In Progress</p>
                                        <h3 className="text-xl font-black text-app-primary mb-0.5">{dashboardData?.summary_statistics?.in_progress_tasks ?? 0}</h3>
                                        <p className="text-[9px] font-semibold text-app-text-muted uppercase tracking-wider">Tasks</p>
                                    </div>

                                    {/* Completed */}
                                    <div className="bg-app-bg-card p-3 rounded-xl shadow-sm border border-app-border-light flex flex-col justify-center hover:border-green-200 transition-colors">
                                        <p className="text-[10px] font-bold text-app-text-label uppercase tracking-wider mb-1 flex items-center gap-1"><CheckCircle className="w-3 h-3 text-app-status-success" /> Completed</p>
                                        <h3 className="text-xl font-black text-app-status-success mb-0.5">{dashboardData?.summary_statistics?.completed_tasks ?? 0}</h3>
                                        <p className="text-[9px] font-semibold text-app-text-muted uppercase tracking-wider">/ {dashboardData?.summary_statistics?.total_tasks ?? 0} Total</p>
                                    </div>
                                </div>
                            </div>

                            {/* Bottom Section: 2 Columns */}
                            <div className="grid grid-cols-1 lg:grid-cols-[minmax(0,1fr)_320px] gap-4 md:gap-5 w-full items-start">

                                {/* Left Column (Main Content) */}
                                <div className="space-y-4 lg:col-start-1 w-full min-w-0">

                                    <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                                        {/* KEY MILESTONES & DATES */}
                                        <div className="bg-app-bg-card rounded-xl shadow-sm border border-app-border-light p-5 relative flex flex-col min-h-[270px] md:min-h-[340px] lg:min-h-[410px]">
                                            <div className="flex items-center gap-2 mb-4">
                                                <Flag className="w-4 h-4 text-orange-500" />
                                                <h3 className="text-sm font-bold text-app-text-main uppercase tracking-widest">Milestones & Dates</h3>
                                            </div>
                                            <div className="overflow-auto rounded border border-app-border-light flex-1">
                                                <table className="min-w-full text-xs">
                                                    <thead className="bg-app-bg-page sticky top-0 z-10 border-b border-app-border-light">
                                                        <tr className="text-app-text-muted uppercase tracking-widest">
                                                            <th className="px-3 py-2 text-left font-bold w-1/2">Milestone</th>
                                                            <th className="px-3 py-2 text-left font-bold w-1/4">Status</th>
                                                            <th className="px-3 py-2 text-right font-bold w-1/4">Date</th>
                                                        </tr>
                                                    </thead>
                                                    <tbody className="divide-y divide-app-bg-page text-app-text-label font-medium">
                                                        {dashboardData?.milestones?.completed?.map(ms => (
                                                            <tr key={ms.id} className="hover:bg-app-bg-page/50">
                                                                <td className="px-3 py-2 truncate max-w-[150px]">{ms.name}</td>
                                                                <td className="px-3 py-2 text-app-status-success font-semibold"><span className="bg-app-status-successBg px-1.5 py-0.5 rounded text-[10px]">Done</span></td>
                                                                <td className="px-3 py-2 text-right">{ms.deadline}</td>
                                                            </tr>
                                                        ))}
                                                        {dashboardData?.milestones?.key_milestones_and_dates?.map(ms => (
                                                            <tr key={ms.id} className="hover:bg-app-bg-page/50">
                                                                <td className="px-3 py-2 truncate max-w-[150px] text-app-text-main">{ms.name}</td>
                                                                <td className="px-3 py-2 text-orange-600 font-semibold"><span className="bg-orange-50 px-1.5 py-0.5 rounded text-[10px]">Active</span></td>
                                                                <td className="px-3 py-2 text-right whitespace-nowrap">{ms.deadline}</td>
                                                            </tr>
                                                        ))}
                                                        {(!dashboardData?.milestones?.completed?.length && !dashboardData?.milestones?.key_milestones_and_dates?.length) && (
                                                            <tr>
                                                                <td className="px-3 py-4 text-center text-app-text-light italic" colSpan="3">No milestones available</td>
                                                            </tr>
                                                        )}
                                                    </tbody>
                                                </table>
                                            </div>
                                        </div>

                                        {/* ACTUAL VS REMAINING WORK */}
                                        <div className="bg-app-bg-card rounded-xl shadow-sm border border-app-border-light p-5 flex flex-col relative min-h-[270px] md:min-h-[340px] lg:min-h-[410px]">
                                            <div className="flex items-center gap-2 mb-4">
                                                <Activity className="w-4 h-4 text-orange-500" />
                                                <h3 className="text-sm font-bold text-app-text-main uppercase tracking-widest">Work: Actual vs Remaining</h3>
                                            </div>

                                            <div className="flex-1 flex flex-col items-center justify-center gap-4">
                                                <div className="relative w-[210px] h-[210px] flex items-center justify-center">
                                                    <svg viewBox="0 0 160 160" className="w-[190px] h-[190px]">
                                                        <circle
                                                            cx="80"
                                                            cy="80"
                                                            r={donutRadius}
                                                            fill="none"
                                                            stroke="#e5e7eb"
                                                            strokeWidth="18"
                                                        />
                                                        <circle
                                                            cx="80"
                                                            cy="80"
                                                            r={donutRadius}
                                                            fill="none"
                                                            stroke="#fef3c7"
                                                            strokeWidth="18"
                                                            strokeLinecap="round"
                                                            strokeDasharray={`${donutCompletedLength} ${donutCircumference}`}
                                                            transform="rotate(-90 80 80)"
                                                        />
                                                        <circle
                                                            cx="80"
                                                            cy="80"
                                                            r={donutRadius}
                                                            fill="none"
                                                            stroke="#000000"
                                                            strokeWidth="18"
                                                            strokeLinecap="round"
                                                            strokeDasharray={`${donutRemainingLength} ${donutCircumference}`}
                                                            strokeDashoffset={-donutCompletedLength}
                                                            transform="rotate(-90 80 80)"
                                                        />
                                                    </svg>
                                                    <div className="absolute text-center">
                                                        <p className="text-2xl font-black text-app-text-main">{workCompletedDisplay}%</p>
                                                        <p className="text-[10px] font-bold uppercase tracking-widest text-app-text-muted">Completed</p>
                                                    </div>
                                                </div>
                                                <div className="grid grid-cols-2 gap-2 w-full max-w-[260px]">
                                                    <div className="rounded-lg border border-app-status-warningBg bg-app-status-warningBg/60 px-3 py-2 text-center">
                                                        <p className="text-[10px] uppercase tracking-widest font-bold text-app-status-warning">Completed</p>
                                                        <p className="text-sm font-black text-app-status-warning">{workCompletedDisplay}%</p>
                                                    </div>
                                                    <div className="rounded-lg border border-black bg-black px-3 py-2 text-center">
                                                        <p className="text-[10px] uppercase tracking-widest font-bold text-app-bg-hover">Remaining</p>
                                                        <p className="text-sm font-black text-white">{workRemainingDisplay}%</p>
                                                    </div>
                                                </div>
                                            </div>
                                        </div>
                                    </div>
                                </div>

                                {/* Right Column (Sidebar Summary) */}
                                <div className="w-full bg-gradient-to-b from-app-bg-card to-app-bg-page/50 rounded-xl shadow-sm border border-app-border-light p-5 lg:col-start-2">
                                    <h2 className="text-[13px] font-bold text-app-text-main uppercase tracking-widest mb-4 flex items-center gap-2"><Activity className="w-4 h-4 text-app-primary" /> Project Status</h2>

                                    <div className="flex flex-col gap-4">
                                        {/* Launch Date */}
                                        <div className="bg-app-bg-card border border-app-border-light rounded-lg p-3 text-center shadow-sm relative overflow-hidden">
                                            <div className="absolute top-0 left-0 w-full h-1 bg-app-primary"></div>
                                            <p className="text-[9px] font-bold text-app-text-muted uppercase tracking-widest mb-1.5 mt-1">Expected Launch Date</p>
                                            <h3 className="text-2xl font-black text-app-primary mb-0.5">{dashboardData?.project_status?.days_until_launch ?? 0} <span className="text-[10px] font-semibold text-app-text-light uppercase tracking-widest">Days</span></h3>
                                            <p className="text-[10px] font-semibold text-app-text-muted">{dashboardData?.project_status?.expected_launch_date ? new Date(dashboardData.project_status.expected_launch_date).toLocaleDateString('en-US', { weekday: 'short', year: 'numeric', month: 'short', day: 'numeric' }) : '—'}</p>
                                        </div>

                                        {/* Overall Health */}
                                        <div className="flex items-center justify-between p-3 bg-app-bg-card border border-app-border-light rounded-lg shadow-sm">
                                            <div className="flex items-center gap-3">
                                                <div className={`w-8 h-8 rounded-full flex items-center justify-center ${dashboardData?.project_status?.overall_health === 'Good' ? 'bg-app-status-successBg text-app-status-success' : dashboardData?.project_status?.overall_health === 'At Risk' ? 'bg-app-status-warningBg text-app-status-warning' : 'bg-app-status-errorBg text-app-status-error'}`}>
                                                    <Activity className="w-4 h-4" />
                                                </div>
                                                <div>
                                                    <p className="text-[9px] font-bold text-app-text-muted uppercase tracking-widest">Overall Health</p>
                                                    <p className="text-sm font-black text-app-text-main">{dashboardData?.project_status?.overall_health ?? '—'}</p>
                                                </div>
                                            </div>
                                        </div>

                                        <div className="border-t border-app-border-light my-1"></div>

                                        {/* Progress Meters */}
                                        <div className="flex flex-col gap-4">
                                            {/* Completion Rate */}
                                            <div>
                                                <div className="flex justify-between items-center mb-1.5">
                                                    <p className="text-[10px] font-bold text-app-text-label uppercase tracking-widest flex items-center gap-1.5"><CheckCircle className="w-3.5 h-3.5 text-app-status-success" /> Completion</p>
                                                    <span className="text-xs font-black text-app-status-success">{dashboardData?.kpi?.completion_percentage ?? 0}%</span>
                                                </div>
                                                <div className="w-full bg-app-bg-muted rounded-full h-2">
                                                    <div className="bg-gradient-to-r from-emerald-400 to-app-status-success h-2 rounded-full" style={{ width: `${dashboardData?.kpi?.completion_percentage ?? 0}%` }}></div>
                                                </div>
                                            </div>

                                            {/* Project Progress */}
                                            <div>
                                                <div className="flex justify-between items-center mb-1.5">
                                                    <p className="text-[10px] font-bold text-app-text-label uppercase tracking-widest flex items-center gap-1.5"><Flag className="w-3.5 h-3.5 text-app-primary" /> Project Prog.</p>
                                                    <span className="text-xs font-black text-app-primary">{dashboardData?.project_status?.project_progress ?? 0}%</span>
                                                </div>
                                                <div className="w-full bg-app-bg-muted rounded-full h-2">
                                                    <div className="bg-gradient-to-r from-blue-400 to-app-primary h-2 rounded-full" style={{ width: `${dashboardData?.project_status?.project_progress ?? 0}%` }}></div>
                                                </div>
                                            </div>

                                            {/* Sprint Progress */}
                                            <div>
                                                <div className="flex justify-between items-center mb-1.5">
                                                    <p className="text-[10px] font-bold text-app-text-label uppercase tracking-widest flex items-center gap-1.5"><RefreshCw className="w-3.5 h-3.5 text-app-primary" /> Sprint Prog.</p>
                                                    <span className="text-xs font-black text-app-primary">
                                                        {(() => {
                                                            const activeSprint = dashboardData?.sprint_status?.find(s => s.status === "On Going") || dashboardData?.sprint_status?.[0];
                                                            if (activeSprint && (activeSprint.actual_work + activeSprint.remaining_work) > 0) {
                                                                return Math.round((activeSprint.actual_work / (activeSprint.actual_work + activeSprint.remaining_work)) * 100) + '%';
                                                            }
                                                            return '0%';
                                                        })()}
                                                    </span>
                                                </div>
                                                <div className="w-full bg-app-bg-muted rounded-full h-2">
                                                    <div className="bg-gradient-to-r from-indigo-400 to-purple-500 h-2 rounded-full" style={{
                                                        width: (() => {
                                                            const activeSprint = dashboardData?.sprint_status?.find(s => s.status === "On Going") || dashboardData?.sprint_status?.[0];
                                                            if (activeSprint && (activeSprint.actual_work + activeSprint.remaining_work) > 0) {
                                                                return Math.round((activeSprint.actual_work / (activeSprint.actual_work + activeSprint.remaining_work)) * 100) + '%';
                                                            }
                                                            return '0%';
                                                        })()
                                                    }}></div>
                                                </div>
                                            </div>
                                        </div>
                                    </div>
                                </div>

                                {/* Task Tables Section - matching screenshot layout */}
                                {dashboardData?.tasks && (
                                    <div className="mt-4 space-y-4 lg:col-span-2 w-full min-w-0">
                                        {/* Row 1: Late Tasks + Upcoming Tasks (Next Period) */}
                                        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                                            {/* Late Tasks Table */}
                                            <div className="bg-app-bg-card rounded-xl shadow-sm border border-app-border-light p-4 flex flex-col min-h-[240px] md:min-h-[260px] lg:min-h-[280px]">
                                                <div className="flex items-center gap-1.5 mb-3">
                                                    <AlertCircle className="w-4 h-4 text-app-status-error" />
                                                    <h3 className="text-sm font-bold text-app-text-main uppercase tracking-widest">Late Tasks</h3>
                                                </div>
                                                <div className="overflow-auto rounded border border-app-border-light" style={{ maxHeight: '240px' }}>
                                                    <table className="min-w-full text-xs">
                                                        <thead className="sticky top-0 z-10 bg-app-bg-page border-b border-app-border-light">
                                                            <tr className="text-app-text-muted uppercase tracking-widest">
                                                                <th className="px-3 py-2 text-left font-bold w-10">#</th>
                                                                <th className="px-3 py-2 text-left font-bold">Task</th>
                                                                <th className="px-3 py-2 text-right font-bold w-24">Target</th>
                                                            </tr>
                                                        </thead>
                                                        <tbody className="divide-y divide-app-bg-page bg-app-bg-card">
                                                            {(dashboardData.tasks.late_tasks || []).map((task, idx) => (
                                                                <tr key={task.id} className="hover:bg-app-status-errorBg/50 transition-colors">
                                                                    <td className="px-3 py-2 text-app-text-muted font-medium">{idx + 1}</td>
                                                                    <td className="px-3 py-2 text-app-text-main font-medium truncate max-w-[200px]">{task.name || task.description || 'Untitled'}</td>
                                                                    <td className="px-3 py-2 text-right text-app-status-error font-semibold whitespace-nowrap">{task.deadline ? new Date(task.deadline).toLocaleDateString('en-US', { month: 'short', day: '2-digit' }) : '—'}</td>
                                                                </tr>
                                                            ))}
                                                            {(!dashboardData.tasks.late_tasks || dashboardData.tasks.late_tasks.length === 0) && (
                                                                <tr><td colSpan="3" className="px-3 py-4 text-center text-app-text-light italic font-medium">No late tasks</td></tr>
                                                            )}
                                                        </tbody>
                                                    </table>
                                                </div>
                                            </div>

                                            {/* Upcoming Tasks (Next Period) Table */}
                                            <div className="bg-app-bg-card rounded-xl shadow-sm border border-app-border-light p-4 flex flex-col">
                                                <div className="flex items-center gap-1.5 mb-3">
                                                    <Calendar className="w-4 h-4 text-app-primary" />
                                                    <h3 className="text-sm font-bold text-app-text-main uppercase tracking-widest">Upcoming</h3>
                                                </div>
                                                <div className="overflow-auto rounded border border-app-border-light" style={{ maxHeight: '200px' }}>
                                                    <table className="min-w-full text-xs">
                                                        <thead className="sticky top-0 z-10 bg-app-bg-page border-b border-app-border-light">
                                                            <tr className="text-app-text-muted uppercase tracking-widest">
                                                                <th className="px-3 py-2 text-left font-bold w-10">#</th>
                                                                <th className="px-3 py-2 text-left font-bold">Task</th>
                                                                <th className="px-3 py-2 text-right font-bold w-24">Target</th>
                                                            </tr>
                                                        </thead>
                                                        <tbody className="divide-y divide-app-bg-page bg-app-bg-card">
                                                            {(dashboardData.tasks.upcoming_tasks_next_period || []).map((task, idx) => (
                                                                <tr key={task.id} className="hover:bg-app-primary-light/50 transition-colors">
                                                                    <td className="px-3 py-2 text-app-text-muted font-medium">{idx + 1}</td>
                                                                    <td className="px-3 py-2 text-app-text-main font-medium truncate max-w-[200px]">{task.name || task.description || 'Untitled'}</td>
                                                                    <td className="px-3 py-2 text-right text-app-text-muted font-semibold whitespace-nowrap">{task.target_date ? new Date(task.target_date).toLocaleDateString('en-US', { month: 'short', day: '2-digit' }) : '—'}</td>
                                                                </tr>
                                                            ))}
                                                            {(!dashboardData.tasks.upcoming_tasks_next_period || dashboardData.tasks.upcoming_tasks_next_period.length === 0) && (
                                                                <tr><td colSpan="3" className="px-3 py-4 text-center text-app-text-light italic font-medium">No upcoming tasks</td></tr>
                                                            )}
                                                        </tbody>
                                                    </table>
                                                </div>
                                            </div>
                                        </div>

                                        {/* Row 2: Due This Week + In Progress / Recently Completed */}
                                        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 items-start">
                                            {/* Due This Week Table */}
                                            <div className="bg-app-bg-card rounded-xl shadow-sm border border-app-border-light p-4 flex flex-col">
                                                <div className="flex items-center gap-1.5 mb-3">
                                                    <AlertTriangle className="w-4 h-4 text-app-status-warning" />
                                                    <h3 className="text-sm font-bold text-app-text-main uppercase tracking-widest">Due This Week</h3>
                                                </div>
                                                <div className="overflow-auto rounded border border-app-border-light" style={{ height: '200px' }}>
                                                    <table className="min-w-full text-xs">
                                                        <thead className="sticky top-0 z-10 bg-app-bg-page border-b border-app-border-light">
                                                            <tr className="text-app-text-muted uppercase tracking-widest">
                                                                <th className="px-3 py-2 text-left font-bold w-10">#</th>
                                                                <th className="px-3 py-2 text-left font-bold">Task</th>
                                                                <th className="px-3 py-2 text-center font-bold w-16">Prog</th>
                                                                <th className="px-3 py-2 text-right font-bold w-20">Due</th>
                                                            </tr>
                                                        </thead>
                                                        <tbody className="divide-y divide-app-bg-page bg-app-bg-card">
                                                            {(dashboardData.tasks.due_this_week || []).map((task, idx) => (
                                                                <tr key={task.id} className="hover:bg-app-status-warningBg/50 transition-colors">
                                                                    <td className="px-3 py-2 text-app-text-muted font-medium">{idx + 1}</td>
                                                                    <td className="px-3 py-2 text-app-text-main font-medium truncate max-w-[150px]">{task.name || task.description || 'Untitled'}</td>
                                                                    <td className="px-3 py-2 text-center text-app-primary font-bold">{task.progress ?? 0}%</td>
                                                                    <td className="px-3 py-2 text-right text-app-text-muted font-semibold whitespace-nowrap">{task.deadline ? new Date(task.deadline).toLocaleDateString('en-US', { month: 'short', day: '2-digit' }) : '—'}</td>
                                                                </tr>
                                                            ))}
                                                            {(!dashboardData.tasks.due_this_week || dashboardData.tasks.due_this_week.length === 0) && (
                                                                <tr><td colSpan="4" className="px-3 py-4 text-center text-app-text-light italic font-medium">No tasks due this week</td></tr>
                                                            )}
                                                        </tbody>
                                                    </table>
                                                </div>
                                            </div>

                                            {/* In Progress + Recently Completed Table */}
                                            <div className="bg-app-bg-card rounded-xl shadow-sm border border-app-border-light p-4 flex flex-col">
                                                <div className="flex items-center gap-1.5 mb-3">
                                                    <Activity className="w-4 h-4 text-app-status-success" />
                                                    <h3 className="text-sm font-bold text-app-text-main uppercase tracking-widest">Active & Done</h3>
                                                </div>
                                                <div className="overflow-auto rounded border border-app-border-light" style={{ maxHeight: '200px' }}>
                                                    <table className="min-w-full text-xs">
                                                        <thead className="sticky top-0 z-10 bg-app-bg-page border-b border-app-border-light">
                                                            <tr className="text-app-text-muted uppercase tracking-widest">
                                                                <th className="px-3 py-2 text-left font-bold w-10">#</th>
                                                                <th className="px-3 py-2 text-left font-bold">Task</th>
                                                                <th className="px-3 py-2 text-right font-bold w-20">Status</th>
                                                            </tr>
                                                        </thead>
                                                        <tbody className="divide-y divide-app-bg-page bg-app-bg-card">
                                                            {(dashboardData.tasks.in_progress || []).map((task, idx) => (
                                                                <tr key={task.id} className="hover:bg-app-primary-light/50 transition-colors">
                                                                    <td className="px-3 py-2 text-app-text-muted font-medium">{idx + 1}</td>
                                                                    <td className="px-3 py-2 text-app-text-main font-medium truncate max-w-[150px]">{task.name || task.description || 'Untitled'}</td>
                                                                    <td className="px-3 py-2 text-right"><span className="inline-block px-1.5 py-0.5 bg-app-primary-light text-app-primary border border-app-primary-light text-[10px] font-bold rounded uppercase">{task.progress ?? 0}%</span></td>
                                                                </tr>
                                                            ))}
                                                            {(dashboardData.tasks.recently_completed || []).map((task, idx) => (
                                                                <tr key={task.id} className="hover:bg-app-status-successBg/50 transition-colors">
                                                                    <td className="px-3 py-2 text-app-text-light font-medium">{(dashboardData.tasks.in_progress?.length || 0) + idx + 1}</td>
                                                                    <td className="px-3 py-2 text-app-text-light font-medium line-through truncate max-w-[150px]">{task.name || task.description || 'Untitled'}</td>
                                                                    <td className="px-3 py-2 text-right"><span className="inline-block px-1.5 py-0.5 bg-app-status-successBg text-app-status-success border border-app-status-successBg text-[10px] font-bold rounded uppercase">Done</span></td>
                                                                </tr>
                                                            ))}
                                                            {(!dashboardData.tasks.in_progress?.length && !dashboardData.tasks.recently_completed?.length) && (
                                                                <tr><td colSpan="3" className="px-3 py-4 text-center text-app-text-light italic font-medium">No tasks in progress or recently completed</td></tr>
                                                            )}
                                                        </tbody>
                                                    </table>
                                                </div>
                                            </div>
                                        </div>
                                    </div>
                                )}

                                {/* ── KNOWLEDGE GRAPH & CI/CD SECTION ── */}
                                {/*
                                  Temporarily hidden as requested:
                                  - Knowledge Graph
                                  - CI/CD Pipeline (Pre-Compilation & Linting card)
                                */}
                                {/*
                                <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mt-6">
                                    <div className="w-full min-w-0">
                                        <KnowledgeGraphCard
                                            selectedProjectKey={selectedProjectKey}
                                            token={token}
                                            taskToken={taskToken}
                                            repoUrl={agents.find(a => a.git_repo_url)?.git_repo_url || ''}
                                        />
                                    </div>
                                    <div className="w-full min-w-0">
                                        <PrStatusCard selectedProjectKey={selectedProjectKey} />
                                    </div>
                                </div>
                                */}

                                {/* ── AI AGENTS SECTION ── */}
                                {!isDeveloperOnlyMode && (
                                    <div className="w-full mt-4 lg:col-span-2 min-w-0">
                                        <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between mb-4">
                                            <div className="flex items-center flex-wrap">
                                                <div className="p-2 mr-3 bg-app-primary-light rounded text-app-primary">
                                                    <Bot className="w-5 h-5" />
                                                </div>
                                                <h3 className="text-[15px] font-bold text-[#f27a24] uppercase tracking-wide">AI Agents</h3>
                                                <span className="ml-3 text-[10px] font-bold text-app-primary-hover uppercase tracking-wider bg-app-primary-light px-2 py-0.5 rounded-full">
                                                    {isAiAssistMode ? 'AI-First' : 'Coexistence'}
                                                </span>
                                                <span className="ml-3 text-[10px] font-bold text-app-text-light uppercase tracking-wider bg-app-bg-muted px-2 py-0.5 rounded-full">
                                                    {agents.filter(a => a.status === 'running').length} Running
                                                </span>
                                            </div>
                                            <div className="flex items-center flex-wrap gap-2 lg:justify-end">
                                                <span className="text-[10px] font-bold text-app-text-light uppercase tracking-wider bg-orange-50 text-orange-600 px-2.5 py-1 rounded-full">
                                                    {totalTaskCount} Available Tasks
                                                </span>
                                                <button
                                                    onClick={() => handleRunAll()}
                                                    disabled={runningAll || agents.filter(a => a.status === 'idle' && a.agent_kind !== 'system').length === 0}
                                                    className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-bold uppercase tracking-wide transition-all duration-200 ${runningAll || agents.filter(a => a.status === 'idle' && a.agent_kind !== 'system').length === 0
                                                        ? 'bg-app-bg-hover text-app-text-light cursor-not-allowed'
                                                        : 'bg-gradient-to-r from-orange-500 to-app-status-warning text-white shadow-md hover:shadow-lg hover:scale-105'
                                                        }`}
                                                    title="Run all idle agents simultaneously"
                                                >
                                                    {runningAll ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Play className="w-3.5 h-3.5" />}
                                                    {runningAll ? 'Starting...' : 'Run All'}
                                                </button>
                                                <button
                                                    onClick={() => handleAddAgent()}
                                                    className="flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-xs font-bold text-app-primary bg-app-primary-light hover:bg-app-primary-light transition-colors"
                                                    title="Add a new agent"
                                                >
                                                    <PlusCircle className="w-3.5 h-3.5" />
                                                    Add Agent
                                                </button>
                                                <button
                                                    onClick={() => { fetchAgents(); fetchTasks(); }}
                                                    className="text-app-text-light hover:text-app-text-label p-1 rounded hover:bg-app-bg-muted transition-colors"
                                                    title="Refresh"
                                                >
                                                    <RefreshCw className="w-4 h-4" />
                                                </button>
                                            </div>
                                        </div>

                                        <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-4">
                                            {orderedAgents.map(agent => renderAgentCard(agent))}

                                            {/* ── Preview Deploy Section (Tile Format) ────────────────────── */}
                                            <div className="bg-app-bg-card rounded-xl shadow border border-app-border-light p-4 flex flex-col relative overflow-hidden group hover:shadow-lg transition-shadow h-full">
                                                <div className="absolute top-0 left-0 right-0 h-1 bg-gradient-to-r from-violet-500 to-purple-600"></div>

                                                <div className="flex items-start justify-between mb-4">
                                                    <div className="flex items-center gap-3">
                                                        <div className="w-10 h-10 rounded-xl bg-app-bg-page border border-app-border flex items-center justify-center shadow-lg shadow-app-bg-hover p-1.5">
                                                            <Globe className="w-full h-full text-violet-600" />
                                                        </div>
                                                        <div>
                                                            <h4 className="text-sm font-bold text-app-text-main">Deploy Agent</h4>
                                                            <p className="text-[10px] text-app-text-light uppercase tracking-wider font-semibold">agent/integration</p>
                                                        </div>
                                                    </div>
                                                    <div className="flex items-center">
                                                        {previewStatus.status === 'running' && (
                                                            <span className="flex items-center gap-1.5 px-2 py-0.5 rounded-full bg-app-status-successBg text-app-status-success text-[10px] font-bold uppercase tracking-wider">
                                                                <span className="w-1.5 h-1.5 rounded-full bg-app-status-success animate-pulse" />
                                                                Live
                                                            </span>
                                                        )}
                                                        {previewStatus.status === 'deploying' && (
                                                            <span className="flex items-center gap-1.5 px-2 py-0.5 rounded-full bg-app-status-warningBg text-app-status-warning text-[10px] font-bold uppercase tracking-wider">
                                                                <Loader2 className="w-3 h-3 animate-spin" />
                                                                Deploying...
                                                            </span>
                                                        )}
                                                    </div>
                                                </div>

                                                <div className="flex-1 flex flex-col justify-end">
                                                    {previewStatus.status === 'running' && previewStatus.preview_url ? (
                                                        <div className="space-y-3">
                                                            <div className="flex flex-col gap-2">
                                                                <a
                                                                    href={`/app/${selectedProjectKey}`}
                                                                    target="_blank"
                                                                    rel="noopener noreferrer"
                                                                    className="flex items-center justify-center gap-2 w-full py-2 rounded-lg bg-app-primary-light text-app-primary-hover font-semibold text-xs hover:bg-app-primary-light transition-colors"
                                                                >
                                                                    <ExternalLink className="w-3.5 h-3.5" />
                                                                    Open Preview
                                                                </a>
                                                                <div className="flex bg-app-bg-muted rounded-lg p-2 justify-between items-center text-[10px]">
                                                                    <code className="text-app-text-main font-mono truncate mr-2">/app/{selectedProjectKey}</code>
                                                                    <span className="text-app-text-light shrink-0">{previewStatus.stack} project</span>
                                                                </div>
                                                            </div>

                                                            <div className="flex items-center gap-2">
                                                                <button
                                                                    onClick={handleDeployPreview}
                                                                    disabled={isDeploying}
                                                                    className="flex-1 flex items-center justify-center gap-1.5 py-1.5 rounded-lg bg-app-primary-light text-app-primary text-[10px] font-bold hover:bg-app-primary-light transition-colors"
                                                                >
                                                                    <RefreshCw className={`w-3 h-3 ${isDeploying ? 'animate-spin' : ''}`} />
                                                                    Redeploy
                                                                </button>
                                                                <button
                                                                    onClick={handleStopPreview}
                                                                    className="flex-1 flex items-center justify-center gap-1.5 py-1.5 rounded-lg bg-app-status-errorBg text-app-status-error text-[10px] font-bold hover:bg-app-status-errorBg transition-colors"
                                                                >
                                                                    <StopCircle className="w-3 h-3" />
                                                                    Stop
                                                                </button>
                                                                <button
                                                                    onClick={() => setShowPreviewLogs(!showPreviewLogs)}
                                                                    className="px-2.5 py-1.5 rounded-lg bg-app-bg-hover text-app-text-light hover:text-app-text-main hover:bg-app-bg-muted transition-colors"
                                                                    title="View Logs"
                                                                >
                                                                    <Terminal className="w-3.5 h-3.5" />
                                                                </button>
                                                            </div>

                                                            {showPreviewLogs && previewStatus.logs && (
                                                                <div className="mt-2 bg-app-text-main rounded-lg p-2 max-h-32 overflow-y-auto">
                                                                    <div className="space-y-0.5 font-mono text-[9px]">
                                                                        {previewStatus.logs.map((log, i) => (
                                                                            <div key={i} className="text-app-text-light">
                                                                                <span className="text-app-text-label mr-1">[{new Date(log.time).toLocaleTimeString()}]</span>
                                                                                {log.message}
                                                                            </div>
                                                                        ))}
                                                                    </div>
                                                                    {previewStatus.server_log && (
                                                                        <div className="mt-1 pt-1 border-t border-app-text-main">
                                                                            <pre className="text-[9px] text-emerald-400 whitespace-pre-wrap">{previewStatus.server_log}</pre>
                                                                        </div>
                                                                    )}
                                                                </div>
                                                            )}
                                                        </div>
                                                    ) : previewStatus.status === 'deploying' ? (
                                                        <div className="space-y-3">
                                                            <div className="flex items-center gap-2 text-app-text-main justify-center py-2">
                                                                <Loader2 className="w-4 h-4 animate-spin text-app-primary" />
                                                                <span className="text-[11px] font-medium">Deploying preview...</span>
                                                            </div>
                                                            {previewStatus.logs && previewStatus.logs.length > 0 && (
                                                                <div className="bg-app-text-main rounded-lg p-2 h-20 overflow-y-auto">
                                                                    <div className="space-y-0.5 font-mono text-[9px]">
                                                                        {previewStatus.logs.map((log, i) => (
                                                                            <div key={i} className="text-app-text-light">
                                                                                <span className="text-violet-400 mr-1">›</span>
                                                                                {log.message}
                                                                            </div>
                                                                        ))}
                                                                    </div>
                                                                </div>
                                                            )}
                                                        </div>
                                                    ) : previewStatus.status === 'error' ? (
                                                        <div className="space-y-3">
                                                            <div className="flex items-center gap-1.5 text-app-status-error text-xs font-semibold justify-center bg-app-status-errorBg p-2 rounded-lg">
                                                                <AlertCircle className="w-3.5 h-3.5" />
                                                                <span>Deployment Failed</span>
                                                            </div>
                                                            {previewStatus.logs && previewStatus.logs.length > 0 && (
                                                                <div className="bg-app-text-main rounded-lg p-2 max-h-24 overflow-y-auto">
                                                                    <div className="space-y-0.5 font-mono text-[9px]">
                                                                        {previewStatus.logs.slice(-5).map((log, i) => (
                                                                            <div key={i} className="text-red-400/80">
                                                                                {log.message}
                                                                            </div>
                                                                        ))}
                                                                    </div>
                                                                </div>
                                                            )}
                                                            <div className="flex items-center gap-2">
                                                                <button
                                                                    onClick={handleDeployPreview}
                                                                    disabled={isDeploying || isFixing}
                                                                    className="flex-1 flex items-center justify-center gap-1.5 py-1.5 rounded-lg bg-app-bg-hover text-app-text-main text-[10px] font-bold hover:bg-app-bg-muted transition-colors disabled:opacity-50"
                                                                >
                                                                    <RefreshCw className={`w-3 h-3 ${isDeploying ? 'animate-spin' : ''}`} />
                                                                    Retry
                                                                </button>
                                                                <button
                                                                    onClick={handleFixWithAI}
                                                                    disabled={isDeploying || isFixing}
                                                                    className="flex-[2] flex items-center justify-center gap-1.5 py-1.5 rounded-lg bg-app-status-successBg text-app-status-success text-[10px] font-bold hover:bg-app-status-successBg transition-colors disabled:opacity-50"
                                                                >
                                                                    {isFixing ? <Loader2 className="w-3 h-3 animate-spin" /> : <Bot className="w-3 h-3" />}
                                                                    AI Fix
                                                                </button>
                                                            </div>
                                                        </div>
                                                    ) : (
                                                        <div className="flex flex-col items-center justify-center py-4 bg-app-bg-muted rounded-xl">
                                                            <Rocket className="w-6 h-6 text-app-text-light mb-2 opacity-50" />                                                            <p className="text-[11px] text-app-text-light text-center font-medium mb-3 px-4">
                                                                View a live version of the integration branch
                                                            </p>
                                                            <button
                                                                onClick={handleDeployPreview}
                                                                disabled={isDeploying}
                                                                className="flex items-center justify-center gap-1.5 w-full max-w-[140px] py-1.5 rounded-lg bg-app-primary text-white text-[10px] font-bold hover:bg-app-primary transition-colors disabled:opacity-50"
                                                            >
                                                                {isDeploying ? <Loader2 className="w-3 h-3 animate-spin" /> : <Rocket className="w-3 h-3" />}
                                                                {isDeploying ? 'Deploying...' : 'Deploy Preview'}
                                                            </button>
                                                        </div>
                                                    )}
                                                </div>
                                            </div>

                                        </div>
                                    </div>
                                )}

                                {/* ── Agent Communication Panel (shows when agents are running) ────────────────────── */}
                                {!isDeveloperOnlyMode && orderedAgents.some(a => a.status === 'running') && selectedProjectKey && (
                                    <div className="w-full mt-4 lg:col-span-2 min-w-0">
                                        <AgentChatPanel projectToken={selectedProjectKey} />
                                    </div>
                                )}

                                {/* Render bottom spacer */}

                                {isDeveloperOnlyMode && (
                                    <div className="w-full mt-4 lg:col-span-2 min-w-0">
                                        <div className="bg-app-bg-card rounded-xl shadow border border-app-border-light p-4">
                                            <div className="flex items-center gap-2">
                                                <Cpu className="w-4 h-4 text-app-text-label" />
                                                <h3 className="text-sm font-bold text-app-text-main uppercase tracking-wide">Developer Only Mode</h3>
                                            </div>
                                            <p className="text-xs text-app-text-light mt-2">
                                                AI agents are hidden for this project in Developer Only mode.
                                            </p>
                                        </div>
                                    </div>
                                )}
                                {/* Closes CSS grid layout */}
                            </div>
                        </>
                    )}
                </div>

            )
            }
            {
                showLogModal && (() => {
                    const agent = agents.find(a => a.id === showLogModal);
                    if (!agent) return null;
                    const logs = agent.output_log || [];
                    const result = agent.last_result;
                    return (
                        <div className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4 z-[300] animate-in fade-in duration-200">
                            <div className="bg-slate-900 text-slate-100 rounded-2xl shadow-2xl border border-slate-800 w-full max-w-3xl max-h-[80vh] flex flex-col overflow-hidden animate-in zoom-in-95 duration-200">
                                <div className="px-6 py-4 border-b border-slate-800 flex items-center justify-between bg-slate-800/50">
                                    <div className="flex items-center gap-3">
                                        <Terminal className="w-5 h-5 text-green-400" />
                                        <h3 className="font-bold text-white text-sm">{getAgentDisplayName(agent)} — Execution Log</h3>
                                        {agent.status === 'running' && (
                                            <span className="flex items-center gap-1 text-[10px] text-green-400 font-bold">
                                                <span className="relative flex h-2 w-2">
                                                    <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75"></span>
                                                    <span className="relative inline-flex rounded-full h-2 w-2 bg-green-500"></span>
                                                </span>
                                                LIVE
                                            </span>
                                        )}
                                    </div>
                                    <button onClick={() => setShowLogModal(null)} className="text-slate-400 hover:text-white p-1 rounded hover:bg-slate-800 transition-colors">
                                        <X className="w-5 h-5" />
                                    </button>
                                </div>
                                <div
                                    className="flex-1 overflow-y-auto p-4 font-mono text-xs leading-relaxed space-y-0.5"
                                    ref={(el) => { if (el) el.scrollTop = el.scrollHeight; }}
                                >
                                    {logs.length === 0 ? (
                                        <p className="text-app-text-muted text-center py-8">No logs yet. Run the agent to see output here.</p>
                                    ) : logs.map((log, idx) => {
                                        const isInfoOrWarning = log.type === 'info' || log.type === 'warning';
                                        let formattedTime = null;
                                        if (log.time) {
                                            const d = new Date(log.time);
                                            const year = d.getFullYear();
                                            const month = String(d.getMonth() + 1).padStart(2, '0');
                                            const day = String(d.getDate()).padStart(2, '0');
                                            const hours = String(d.getHours()).padStart(2, '0');
                                            const minutes = String(d.getMinutes()).padStart(2, '0');
                                            const seconds = String(d.getSeconds()).padStart(2, '0');
                                            formattedTime = `${year}-${month}-${day} ${hours}:${minutes}:${seconds}`;
                                        }

                                        return (
                                            <div key={idx} className={`flex items-start gap-2 ${log.type === 'error' ? 'text-red-400' : log.type === 'output' ? 'text-green-300' : 'text-blue-300'}`}>
                                                {isInfoOrWarning && formattedTime && (
                                                    <span className="text-app-text-muted flex-shrink-0 select-none opacity-80" title={log.time}>
                                                        [{formattedTime}]
                                                    </span>
                                                )}
                                                <span className="text-app-text-label flex-shrink-0 select-none">[{log.type}]</span>
                                                <span className="break-all">{log.message}</span>
                                            </div>
                                        );
                                    })}
                                </div>
                                {result?.generated_code && (
                                    <div className="border-t border-app-text-label">
                                        <details className="group" open>
                                            <summary className="px-4 py-2 text-xs font-bold text-emerald-400 cursor-pointer hover:text-emerald-300 select-none flex items-center gap-2">
                                                <span className="w-2 h-2 bg-emerald-400 rounded-full"></span>
                                                View Project Structure ({(result.generated_code.match(/FILE:/g) || []).length} files captured)
                                            </summary>
                                            <pre className="px-4 py-3 overflow-x-auto text-[10px] text-green-200 bg-slate-950/50 max-h-96 overflow-y-auto whitespace-pre-wrap">
                                                {result.generated_code}
                                            </pre>
                                        </details>
                                    </div>
                                )}
                                {result?.builder_scripts && (
                                    <div className="border-t border-app-text-label">
                                        <details className="group">
                                            <summary className="px-4 py-2 text-xs font-bold text-blue-400 cursor-pointer hover:text-blue-300 select-none flex items-center gap-2">
                                                <span className="w-2 h-2 bg-blue-400 rounded-full"></span>
                                                View Builder Scripts ({result.builder_scripts.split('\n').length} lines of AI-generated code)
                                            </summary>
                                            <pre className="px-4 py-3 overflow-x-auto text-[10px] text-app-primary-ring bg-slate-950/50 max-h-60 overflow-y-auto whitespace-pre-wrap">
                                                {result.builder_scripts}
                                            </pre>
                                        </details>
                                    </div>
                                )}
                            </div>
                        </div>
                    );
                })()
            }
            {/* Generated Tasks Section */}
            {
                projects.length > 0 && selectedRole === 'project' && (
                    isDashboardSkeletonVisible && taskList.length === 0 ? (
                        renderGeneratedTasksSkeleton()
                    ) : (
                        <div className="px-4 md:px-6 pb-6">
                            <div className="bg-app-bg-card rounded-2xl shadow-sm border border-app-border-light overflow-hidden">
                                <div className="px-6 py-4 border-b border-app-border-light flex items-center justify-between bg-gradient-to-r from-app-bg-page/80 to-app-bg-card">
                                    <div className="flex items-center gap-3">
                                        <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-app-primary to-purple-600 flex items-center justify-center shadow-lg shadow-app-primary-ring">
                                            <ListTodo className="w-4 h-4 text-white" />
                                        </div>
                                        <div>
                                            <h3 className="text-sm font-bold text-app-text-main">Generated Tasks</h3>
                                            <p className="text-[10px] text-app-text-light uppercase tracking-wider font-semibold">
                                                {taskList.length} of {totalTaskCount} task{totalTaskCount !== 1 ? 's' : ''} from NXDUNE{taskList.length > 0 ? ` • ${sprintCount} sprint${sprintCount !== 1 ? 's' : ''}` : ''}
                                            </p>
                                        </div>
                                    </div>
                                    <button onClick={() => fetchTasks(false, 1, false)} disabled={isLoadingTasks} className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold text-app-text-muted bg-app-bg-page border border-app-border rounded-lg hover:bg-app-bg-muted hover:text-app-text-label transition-all disabled:opacity-50">
                                        <RefreshCw className={`w-3 h-3 ${isLoadingTasks ? 'animate-spin' : ''}`} /> Refresh
                                    </button>
                                </div>


                                <div className="hidden md:block bg-app-bg-page/50 border-b border-app-border-light px-6 py-2.5">
                                    <div style={{ display: 'grid', gridTemplateColumns: '40px 1fr 120px 140px 90px 80px 120px 60px 130px', gap: '8px', alignItems: 'center' }}>
                                        <div className="text-[10px] font-bold text-app-text-light uppercase tracking-wider">#</div>
                                        <div className="text-[10px] font-bold text-app-text-light uppercase tracking-wider">Task Information</div>
                                        <div className="text-[10px] font-bold text-app-text-light uppercase tracking-wider">Sprint</div>
                                        <div className="text-[10px] font-bold text-app-text-light uppercase tracking-wider text-center">Completion</div>
                                        <div className="text-[10px] font-bold text-app-text-light uppercase tracking-wider">Status</div>
                                        <div className="text-[10px] font-bold text-app-text-light uppercase tracking-wider">Priority</div>
                                        <div className="text-[10px] font-bold text-app-text-light uppercase tracking-wider">Assignees</div>
                                        <div className="text-[10px] font-bold text-app-text-light uppercase tracking-wider">Wallet</div>
                                        <div className="text-[10px] font-bold text-app-text-light uppercase tracking-wider">Deadline</div>
                                    </div>
                                </div>

                                <div className="divide-y divide-app-bg-page">
                                    {isLoadingTasks && taskList.length === 0 && (
                                        <div className="p-6 space-y-4">
                                            {[0, 1, 2, 3].map((row) => (
                                                <div key={row} className="grid grid-cols-1 md:grid-cols-[40px_1fr_120px_140px_90px_80px_120px_60px_130px] gap-2 items-center">
                                                    <Skeleton height={10} width={18} />
                                                    <div>
                                                        <Skeleton height={13} width="52%" />
                                                        <div className="mt-1">
                                                            <Skeleton height={10} width="70%" />
                                                        </div>
                                                    </div>
                                                    <Skeleton height={18} width={90} />
                                                    <Skeleton height={10} width={108} />
                                                    <Skeleton height={18} width={72} />
                                                    <Skeleton height={18} width={64} />
                                                    <Skeleton height={12} width={90} />
                                                    <Skeleton height={10} width={42} />
                                                    <Skeleton height={10} width={90} />
                                                </div>
                                            ))}
                                        </div>
                                    )}
                                    {taskListError && !isLoadingTasks && (
                                        <div className="p-6 flex items-center gap-3 bg-app-status-errorBg/50">
                                            <AlertCircle className="w-5 h-5 text-red-400 flex-shrink-0" />
                                            <p className="text-sm text-app-status-error font-medium">{taskListError}</p>
                                        </div>
                                    )}
                                    {!isLoadingTasks && !taskListError && taskList.length === 0 && (
                                        <div className="p-10 flex flex-col items-center justify-center gap-2 text-center">
                                            <div className="w-14 h-14 bg-app-bg-page rounded-full flex items-center justify-center mb-2">
                                                <ListTodo className="w-7 h-7 text-app-border" />
                                            </div>
                                            <p className="text-sm font-bold text-app-text-muted">No tasks generated yet</p>
                                            <p className="text-xs text-app-text-light max-w-xs">Select a project and start the process from Task Creation to begin.</p>
                                        </div>
                                    )}
                                    {!isLoadingTasks && taskList.length > 0 && (
                                        <div className="overflow-y-auto" style={{ maxHeight: '600px' }}>
                                            {sortedTaskList.map((task, index) => {
                                                const priorityStyles = { high: 'bg-app-status-errorBg text-app-status-error border-red-200', medium: 'bg-app-status-warningBg text-app-status-warning border-amber-200', low: 'bg-app-status-successBg text-app-status-success border-green-200' };
                                                const typeStyles = { EPIC: 'bg-purple-100 text-purple-700', FEATURE: 'bg-app-primary-light text-app-primary-hover', STORY: 'bg-cyan-100 text-cyan-700', TASK: 'bg-app-bg-muted text-app-text-label', BUG: 'bg-app-status-errorBg text-app-status-error' };
                                                const statusStyles = { 'On Going': 'bg-app-primary-light text-app-primary-hover', 'Completed': 'bg-app-status-successBg text-app-status-success', 'To Do': 'bg-app-bg-page text-app-text-label', 'In Review': 'bg-app-status-warningBg text-app-status-warning', 'Blocked': 'bg-app-status-errorBg text-app-status-error' };
                                                const priority = (task.priority || 'medium').toLowerCase();
                                                const taskType = (task.task_type || 'TASK').toUpperCase();
                                                const progress = task.task_progress || 0;
                                                const progressColor = progress >= 80 ? 'bg-app-status-success' : progress >= 40 ? 'bg-app-primary' : 'bg-app-status-warning';
                                                const sprintLabel = getTaskSprintLabel(task);

                                                return (
                                                    <div key={task.id || index} className="px-6 py-3 hover:bg-app-bg-page/70 transition-colors group">
                                                        <div className="hidden md:grid" style={{ gridTemplateColumns: '40px 1fr 120px 140px 90px 80px 120px 60px 130px', gap: '8px', alignItems: 'center' }}>
                                                            {/* # */}
                                                            <div className="flex items-center gap-1.5">
                                                                <span className="text-[10px] font-bold text-app-text-light">{(index + 1).toString().padStart(2, '0')}</span>
                                                                {task.is_flaged && <Flag className="w-3 h-3 text-orange-400 fill-orange-400" />}
                                                            </div>

                                                            {/* Task Name & Desc */}
                                                            <div className="min-w-0 pr-4">
                                                                <div className="flex items-center gap-2 mb-0.5">
                                                                    <h4 className="text-sm font-bold text-app-text-main truncate" title={task.taskName}>{task.taskName || 'Untitled Task'}</h4>
                                                                    <span className={`inline-flex items-center px-1.5 py-0.5 rounded text-[8px] font-black uppercase tracking-widest ${typeStyles[taskType] || typeStyles.TASK}`}>{taskType}</span>
                                                                </div>
                                                                <p className="text-xs text-app-text-light truncate max-w-[900px]" title={task.description}>{task.description || 'No description'}</p>
                                                            </div>

                                                            {/* Sprint */}
                                                            <div>
                                                                <span className="inline-flex items-center px-2 py-0.5 rounded-md text-[10px] font-bold bg-app-primary-light text-app-primary-hover border border-app-primary-ring">
                                                                    {sprintLabel}
                                                                </span>
                                                            </div>

                                                            {/* Progress */}
                                                            <div className="flex items-center gap-3 justify-center">
                                                                <div className="flex-1 bg-app-bg-muted rounded-full h-1.5 overflow-hidden max-w-[80px]">
                                                                    <div className={`${progressColor} h-1.5 rounded-full transition-all duration-500`} style={{ width: `${Math.min(progress, 100)}%` }}></div>
                                                                </div>
                                                                <span className="text-[10px] font-bold text-app-text-label w-6">{progress}%</span>
                                                            </div>

                                                            {/* Status */}
                                                            <div>
                                                                <span className={`inline-flex items-center px-2 py-0.5 rounded-md text-[10px] font-bold ${statusStyles[task.taskStatus] || 'bg-app-bg-page text-app-text-label'}`}>{task.taskStatus || 'Unknown'}</span>
                                                            </div>

                                                            {/* Priority */}
                                                            <div>
                                                                <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-bold border capitalize ${priorityStyles[priority] || priorityStyles.medium}`}>{priority}</span>
                                                            </div>

                                                            {/* Assignees */}
                                                            <div className="flex items-center gap-1 overflow-hidden">
                                                                <Users className="w-3 h-3 text-app-border flex-shrink-0" />
                                                                <div className="flex flex-wrap gap-0.5 max-h-8 overflow-hidden">
                                                                    {(task.assignedTo || []).slice(0, 2).map((name, i) => (
                                                                        <span key={i} className="inline-flex items-center px-1.5 py-0.5 bg-app-primary-light text-app-primary-hover rounded text-[9px] font-bold truncate max-w-[45px]">{name}</span>
                                                                    ))}
                                                                    {(task.assignedTo || []).length > 2 && <span className="text-[9px] font-bold text-app-text-light">+{(task.assignedTo || []).length - 2}</span>}
                                                                </div>
                                                            </div>

                                                            {/* Wallet */}
                                                            <div className="flex items-center gap-1">
                                                                <Wallet className="w-3 h-3 text-app-border" />
                                                                <span className="text-[10px] font-bold text-app-text-muted">{task.task_wallet || 0}</span>
                                                            </div>

                                                            {/* Deadline */}
                                                            <div className="flex flex-col gap-0.5">
                                                                <div className="flex items-center gap-1 text-[10px] font-bold text-app-text-muted">
                                                                    <Calendar className="w-3 h-3 text-app-border" />
                                                                    <span>{task.deadline || '-'}</span>
                                                                </div>
                                                                {task.days_left != null && (
                                                                    <span className={`text-[9px] font-black uppercase tracking-tighter ${task.days_left <= 3 ? 'text-app-status-error' : task.days_left <= 7 ? 'text-app-status-warning' : 'text-app-status-success'}`}>{task.days_left}d remaining</span>
                                                                )}
                                                            </div>
                                                        </div>

                                                        {/* Mobile View */}
                                                        <div className="md:hidden space-y-2">
                                                            <div className="flex justify-between items-start">
                                                                <h4 className="text-sm font-bold text-app-text-main line-clamp-1">{task.taskName}</h4>
                                                                <span className={`px-1.5 py-0.5 rounded text-[8px] font-black ${typeStyles[taskType]}`}>{taskType}</span>
                                                            </div>
                                                            <div className="flex justify-between items-center text-[10px]">
                                                                <div className="flex items-center gap-2">
                                                                    <span className={`px-2 py-0.5 rounded font-bold ${statusStyles[task.taskStatus]}`}>{task.taskStatus}</span>
                                                                    <span className="font-bold text-app-text-muted">{progress}%</span>
                                                                </div>
                                                                <span className="font-bold text-app-primary">${task.task_wallet || 0}</span>
                                                            </div>
                                                            <div className="text-[10px] text-app-text-light">
                                                                Sprint: <span className="font-semibold text-app-text-label">{sprintLabel}</span>
                                                            </div>
                                                        </div>
                                                    </div>
                                                );
                                            })}
                                        </div>
                                    )}


                                    {/* Load More Button */}
                                    {nextPageUrl && (
                                        <div className="px-6 py-4 flex justify-center border-t border-app-border-light">
                                            <button
                                                onClick={() => {
                                                    const page = getPageFromUrl(nextPageUrl);
                                                    if (page) fetchTasks(true, page);
                                                }}
                                                disabled={isLoadingMore}
                                                className="inline-flex items-center gap-2 px-6 py-2.5 text-sm font-semibold text-app-primary bg-app-primary-light border border-app-primary-ring rounded-xl hover:bg-app-primary-light hover:shadow-sm transition-all disabled:opacity-50 disabled:cursor-not-allowed"
                                            >
                                                {isLoadingMore ? (
                                                    <><RefreshCw className="w-4 h-4 animate-spin" /> Loading more...</>
                                                ) : (
                                                    <><ChevronRight className="w-4 h-4" /> Load More ({taskList.length} of {totalTaskCount})</>
                                                )}
                                            </button>
                                        </div>
                                    )}
                                </div>
                            </div>
                        </div>
                    )
                )
            }

            {/* Add Project Modal */}
            {
                showModal && (
                    <div className="fixed inset-0 bg-black/50 backdrop-blur-sm flex items-center justify-center p-4 z-[300] animate-in fade-in duration-200">
                        <div className="bg-app-bg-card rounded-2xl shadow-xl border border-app-border-light w-full max-w-md overflow-hidden animate-in zoom-in-95 duration-200">
                            <div className="px-6 py-5 border-b border-app-border-light flex items-center justify-between bg-gradient-to-r from-app-bg-page to-app-bg-card">
                                <h3 className="font-bold text-app-text-main text-lg flex items-center gap-2">
                                    <PlusCircle className="w-5 h-5 text-app-primary" /> Create Project
                                </h3>
                                <button type="button" onClick={() => setShowModal(false)} className="text-app-text-light hover:text-app-text-label hover:bg-app-bg-muted p-1.5 rounded-full transition-colors">
                                    <X className="w-5 h-5" />
                                </button>
                            </div>
                            <div className="p-6">
                                <p className="text-sm text-app-text-muted mb-4 font-medium">Step 1 of Requirement Screening Track: Give your project a descriptive name to get started.</p>
                                <label className="block text-[11px] font-bold text-app-text-muted mb-2 uppercase tracking-widest">Project Name <span className="text-red-400">*</span></label>
                                <input type="text" value={newProjectName} onChange={(e) => setNewProjectName(e.target.value)} autoFocus onKeyDown={(e) => e.key === 'Enter' && handleCreateProject()} placeholder="e.g. Customer Analytics Platform" className="w-full px-4 py-3 border-2 border-app-border rounded-xl focus:ring-4 focus:ring-app-primary-light focus:border-blue-400 text-sm bg-app-bg-page/50 text-app-text-main transition-all duration-200 placeholder:text-app-border font-medium mb-6" />
                                <div className="flex items-center gap-3">
                                    <button type="button" onClick={() => setShowModal(false)} className="flex-1 py-3 px-4 font-bold text-app-text-label bg-app-bg-page hover:bg-app-bg-muted border border-app-border rounded-xl transition-colors">Cancel</button>
                                    <button type="button" onClick={handleCreateProject} disabled={!newProjectName.trim()} className="flex-1 py-3 px-4 font-bold text-white bg-gradient-to-r from-app-primary to-app-primary hover:from-app-primary-hover hover:to-app-primary-hover rounded-xl transition-colors shadow-lg shadow-app-primary/30 hover:shadow-app-primary/50 disabled:opacity-50 disabled:cursor-not-allowed flex justify-center items-center gap-2 group">
                                        Start track <ArrowRight className="w-4 h-4 group-hover:translate-x-1 transition-transform" />
                                    </button>
                                </div>
                            </div>
                        </div>
                    </div>
                )
            }

            {/* Edit Agent Modal */}
            {
                editingAgentId && (
                    <div className="fixed inset-0 bg-black/50 backdrop-blur-sm flex items-center justify-center p-4 z-[300] animate-in fade-in duration-200">
                        <div className="bg-app-bg-card rounded-2xl shadow-xl border border-app-border-light w-full max-w-md overflow-hidden animate-in zoom-in-95 duration-200">
                            <div className="px-6 py-5 border-b border-app-border-light flex items-center justify-between bg-gradient-to-r from-app-bg-page to-app-bg-card">
                                <h3 className="font-bold text-app-text-main text-lg flex items-center gap-2">
                                    <Pencil className="w-5 h-5 text-app-primary" /> Edit Agent Settings
                                </h3>
                                <button type="button" onClick={cancelEditingAgentName} className="text-app-text-light hover:text-app-text-label hover:bg-app-bg-muted p-1.5 rounded-full transition-colors">
                                    <X className="w-5 h-5" />
                                </button>
                            </div>
                            <div className="p-6">
                                <p className="text-sm text-app-text-muted mb-4 font-medium">Update agent name. Git repository URL and PAT are global per project and apply to all agents.</p>

                                <label className="block text-[11px] font-bold text-app-text-muted mb-2 uppercase tracking-widest">Agent Name <span className="text-red-400">*</span></label>
                                <input
                                    type="text"
                                    value={editingAgentName}
                                    onChange={(e) => setEditingAgentName(e.target.value)}
                                    className="w-full px-4 py-3 border-2 border-app-border rounded-xl focus:ring-4 focus:ring-app-primary-light focus:border-indigo-400 text-sm bg-app-bg-page/50 text-app-text-main transition-all duration-200 placeholder:text-app-border font-medium mb-4"
                                />

                                <label className="block text-[11px] font-bold text-app-text-muted mb-2 uppercase tracking-widest">Git Repository URL</label>
                                <input
                                    type="text"
                                    value={editingAgentRepoUrl}
                                    onChange={(e) => setEditingAgentRepoUrl(e.target.value)}
                                    placeholder="https://github.com/org/repo.git"
                                    className="w-full px-4 py-3 border-2 border-app-border rounded-xl focus:ring-4 focus:ring-app-primary-light focus:border-indigo-400 text-sm bg-app-bg-page/50 text-app-text-main transition-all duration-200 placeholder:text-app-border font-medium mb-4"
                                />

                                <label className="block text-[11px] font-bold text-app-text-muted mb-2 uppercase tracking-widest">Global Personal Access Token</label>
                                <input
                                    type="password"
                                    value={editingAgentToken}
                                    onChange={(e) => setEditingAgentToken(e.target.value)}
                                    placeholder="Leave blank to keep existing PAT"
                                    className="w-full px-4 py-3 border-2 border-app-border rounded-xl focus:ring-4 focus:ring-app-primary-light focus:border-indigo-400 text-sm bg-app-bg-page/50 text-app-text-main transition-all duration-200 placeholder:text-app-border font-medium"
                                />
                                <p className="text-xs text-app-text-light mt-2 mb-6">Leave token blank if you do not want to change it.</p>

                                <div className="flex items-center gap-3">
                                    <button type="button" onClick={cancelEditingAgentName} disabled={isSavingAgentName} className="flex-1 py-3 px-4 font-bold text-app-text-label bg-app-bg-page hover:bg-app-bg-muted border border-app-border rounded-xl transition-colors disabled:opacity-50">Cancel</button>
                                    <button type="button" onClick={saveAgentName} disabled={isSavingAgentName || !editingAgentName.trim()} className="flex-1 py-3 px-4 font-bold text-white bg-gradient-to-r from-app-primary to-app-primary hover:from-app-primary-hover hover:to-app-primary-hover rounded-xl transition-colors shadow-lg shadow-app-primary/30 disabled:opacity-50 disabled:cursor-not-allowed flex justify-center items-center gap-2">
                                        {isSavingAgentName ? <><Loader2 className="w-4 h-4 animate-spin" /> Saving...</> : 'Save Changes'}
                                    </button>
                                </div>
                            </div>
                        </div>
                    </div>
                )
            }

            {/* Add Agent Modal */}
            {
                showAddAgentModal && (
                    <div className="fixed inset-0 z-[300] flex items-center justify-center p-4">
                        {/* Backdrop with blur */}
                        <div
                            className="absolute inset-0 bg-black/70 backdrop-blur-md"
                            onClick={() => setShowAddAgentModal(false)}
                        />
                        {/* Modal Content */}
                        <div className="relative z-[301] bg-app-bg-card rounded-2xl shadow-xl border border-app-border-light w-full max-w-lg overflow-hidden animate-in zoom-in-95 duration-200">
                            <div className="px-6 py-5 border-b border-app-border-light flex items-center justify-between bg-gradient-to-r from-app-bg-page to-app-bg-card">
                                <h3 className="font-bold text-app-text-main text-lg flex items-center gap-2">
                                    <PlusCircle className="w-5 h-5 text-app-primary" /> Add Dev Agents
                                </h3>
                                <button type="button" onClick={() => setShowAddAgentModal(false)} className="text-app-text-light hover:text-app-text-label hover:bg-app-bg-muted p-1.5 rounded-full transition-colors">
                                    <X className="w-5 h-5" />
                                </button>
                            </div>
                            <div className="p-6">
                                <p className="text-sm text-app-text-muted mb-5 font-medium">
                                    Add shared and dedicated Dev and Test agents for the current project. Master Agent and Git Manager stay available by default.
                                </p>

                                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                    {/* DEV AGENTS CARD (Shared + Dedicated) */}
                                    <div className="rounded-xl border border-emerald-200 bg-app-status-successBg/60 p-4">
                                        <div className="flex items-center justify-between gap-3 mb-3">
                                            <div>
                                                <p className="text-sm font-bold text-emerald-900">Dev Agents</p>
                                                <p className="text-[10px] text-app-status-success whitespace-nowrap">
                                                    Shared: {agentQuotaLoading ? '...' : sharedDevAvailableForModal} • Dedicated: {agentQuotaLoading ? '...' : dedicatedDevAvailableForModal}
                                                </p>
                                            </div>
                                            <Users className="w-5 h-5 text-app-status-success" />
                                        </div>
                                        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                                            <div>
                                                <label className="block text-[10px] font-bold text-emerald-800 mb-1 uppercase tracking-widest">
                                                    Shared
                                                </label>
                                                <input
                                                    type="number"
                                                    min="0"
                                                    max={sharedDevAvailableForModal}
                                                    value={sharedAgentsToAdd}
                                                    onChange={(e) => {
                                                        const val = e.target.value;
                                                        if (val === '' || /^\d+$/.test(val)) {
                                                            setSharedAgentsToAdd(val);
                                                        }
                                                    }}
                                                    onBlur={(e) => {
                                                        const val = e.target.value;
                                                        if (val === '') {
                                                            setSharedAgentsToAdd('');
                                                        } else {
                                                            const num = clampAgentCount(Number(val), sharedDevAvailableForModal);
                                                            setSharedAgentsToAdd(num.toString());
                                                        }
                                                    }}
                                                    placeholder="0"
                                                    className="w-full px-4 py-2.5 border border-emerald-200 rounded-xl focus:ring-4 focus:ring-app-status-successBg focus:border-emerald-400 text-sm bg-app-bg-card text-app-text-main font-bold"
                                                />
                                            </div>
                                            <div>
                                                <label className="block text-[10px] font-bold text-emerald-800 mb-1 uppercase tracking-widest">
                                                    Dedicated
                                                </label>
                                                <input
                                                    type="number"
                                                    min="0"
                                                    max={dedicatedDevAvailableForModal}
                                                    value={dedicatedAgentsToAdd}
                                                    onChange={(e) => {
                                                        const val = e.target.value;
                                                        if (val === '' || /^\d+$/.test(val)) {
                                                            setDedicatedAgentsToAdd(val);
                                                        }
                                                    }}
                                                    onBlur={(e) => {
                                                        const val = e.target.value;
                                                        if (val === '') {
                                                            setDedicatedAgentsToAdd('');
                                                        } else {
                                                            const num = clampAgentCount(Number(val), dedicatedDevAvailableForModal);
                                                            setDedicatedAgentsToAdd(num.toString());
                                                        }
                                                    }}
                                                    placeholder="0"
                                                    className="w-full px-4 py-2.5 border border-emerald-200 rounded-xl focus:ring-4 focus:ring-app-status-successBg focus:border-emerald-400 text-sm bg-app-bg-card text-app-text-main font-bold"
                                                />
                                            </div>
                                        </div>
                                    </div>

                                    {/* TEST AGENTS CARD (Shared + Dedicated) */}
                                    <div className="rounded-xl border border-app-primary-ring bg-app-primary-light/60 p-4">
                                        <div className="flex items-center justify-between gap-3 mb-3">
                                            <div>
                                                <p className="text-sm font-bold text-app-primary-dark">Test Agents</p>
                                                <p className="text-[10px] text-app-primary-hover whitespace-nowrap">
                                                    Shared: {agentQuotaLoading ? '...' : sharedTestAvailableForModal} • Dedicated: {agentQuotaLoading ? '...' : dedicatedTestAvailableForModal}
                                                </p>
                                            </div>
                                            <Bot className="w-5 h-5 text-app-primary" />
                                        </div>
                                        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                                            <div>
                                                <label className="block text-[10px] font-bold text-app-primary-dark mb-1 uppercase tracking-widest">
                                                    Shared
                                                </label>
                                                <input
                                                    type="number"
                                                    min="0"
                                                    max={sharedTestAvailableForModal}
                                                    value={sharedTestAgentsToAdd}
                                                    onChange={(e) => {
                                                        const val = e.target.value;
                                                        if (val === '' || /^\d+$/.test(val)) {
                                                            setSharedTestAgentsToAdd(val);
                                                        }
                                                    }}
                                                    onBlur={(e) => {
                                                        const val = e.target.value;
                                                        if (val === '') {
                                                            setSharedTestAgentsToAdd('');
                                                        } else {
                                                            const num = clampAgentCount(Number(val), sharedTestAvailableForModal);
                                                            setSharedTestAgentsToAdd(num.toString());
                                                        }
                                                    }}
                                                    placeholder="0"
                                                    className="w-full px-4 py-2.5 border border-app-primary-ring rounded-xl focus:ring-4 focus:ring-app-primary-light focus:border-blue-400 text-sm bg-app-bg-card text-app-text-main font-bold"
                                                />
                                            </div>
                                            <div>
                                                <label className="block text-[10px] font-bold text-app-primary-dark mb-1 uppercase tracking-widest">
                                                    Dedicated
                                                </label>
                                                <input
                                                    type="number"
                                                    min="0"
                                                    max={dedicatedTestAvailableForModal}
                                                    value={dedicatedTestAgentsToAdd}
                                                    onChange={(e) => {
                                                        const val = e.target.value;
                                                        if (val === '' || /^\d+$/.test(val)) {
                                                            setDedicatedTestAgentsToAdd(val);
                                                        }
                                                    }}
                                                    onBlur={(e) => {
                                                        const val = e.target.value;
                                                        if (val === '') {
                                                            setDedicatedTestAgentsToAdd('');
                                                        } else {
                                                            const num = clampAgentCount(Number(val), dedicatedTestAvailableForModal);
                                                            setDedicatedTestAgentsToAdd(num.toString());
                                                        }
                                                    }}
                                                    placeholder="0"
                                                    className="w-full px-4 py-2.5 border border-app-primary-ring rounded-xl focus:ring-4 focus:ring-app-primary-light focus:border-blue-400 text-sm bg-app-bg-card text-app-text-main font-bold"
                                                />
                                            </div>
                                        </div>
                                    </div>
                                </div>

                                {(agentQuotaLoading || agentQuotaError || addAgentModalError || !hasGlobalGitConfigured) && (
                                    <div className="mt-4 space-y-2">
                                        {agentQuotaLoading && (
                                            <p className="text-xs text-app-text-light">Loading available capacity...</p>
                                        )}
                                        {agentQuotaError && (
                                            <p className="text-xs text-app-status-warning bg-app-status-warningBg border border-amber-200 rounded-lg px-3 py-2">{agentQuotaError}</p>
                                        )}
                                        {addAgentModalError && (
                                            <p className="text-xs text-app-status-error bg-app-status-errorBg border border-red-200 rounded-lg px-3 py-2">{addAgentModalError}</p>
                                        )}
                                        {!hasGlobalGitConfigured && (
                                            <p className="text-xs text-amber-800 bg-app-status-warningBg border border-amber-200 rounded-lg px-3 py-2">
                                                Agents will be added now. Configure global Git in prerequisites if you want them to auto-start immediately.
                                            </p>
                                        )}
                                    </div>
                                )}

                                <div className="flex items-center gap-3 mt-6">
                                    <button type="button" onClick={() => setShowAddAgentModal(false)} disabled={isAddingAgents} className="flex-1 py-3 px-4 font-bold text-app-text-label bg-app-bg-page hover:bg-app-bg-muted border border-app-border rounded-xl transition-colors disabled:opacity-50">Cancel</button>
                                    <button
                                        type="button"
                                        onClick={submitAddAgent}
                                        disabled={isAddingAgents || agentQuotaLoading}
                                        className="flex-1 py-3 px-4 font-bold text-white bg-gradient-to-r from-app-primary to-app-primary hover:from-app-primary-hover hover:to-app-primary-hover rounded-xl transition-colors shadow-lg shadow-app-primary/30 disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
                                    >
                                        {isAddingAgents ? <Loader2 className="w-4 h-4 animate-spin" /> : <PlusCircle className="w-4 h-4" />}
                                        {isAddingAgents ? 'Adding...' : 'Add Agents'}
                                    </button>
                                </div>
                            </div>
                        </div>
                    </div>
                )
            }

            {/* Git Configuration Modal */}
            {
                gitModalAgent && (
                    <div className="fixed inset-0 bg-black/50 backdrop-blur-sm flex items-center justify-center p-4 z-[300] animate-in fade-in duration-200">
                        <div className="bg-app-bg-card rounded-2xl shadow-xl border border-app-border-light w-full max-w-lg max-h-[90vh] flex flex-col overflow-hidden animate-in zoom-in-95 duration-200">
                            <div className="px-6 py-5 border-b border-app-border-light flex items-center justify-between bg-gradient-to-r from-app-bg-page to-app-bg-card">
                                <h3 className="font-bold text-app-text-main text-lg flex items-center gap-2">
                                    <Bot className="w-5 h-5 text-app-primary" /> {gitModalAgent.id === '__run_all_setup__' ? 'Configure Global Git' : 'Git Configuration'}
                                </h3>
                                <button type="button" onClick={() => setGitModalAgent(null)} className="text-app-text-light hover:text-app-text-label hover:bg-app-bg-muted p-1.5 rounded-full transition-colors">
                                    <X className="w-5 h-5" />
                                </button>
                            </div>
                            <div className="p-6 overflow-y-auto">
                                {gitModalAgent.id === '__run_all_setup__' ? (
                                    <>
                                        <p className="text-sm text-app-text-muted mb-6 font-medium">
                                            {`To run ${gitModalAgent.missingConfig.length} agent(s), provide one global Git repository. PAT is optional for public repositories.`}
                                        </p>
                                        <div className="p-4 border border-app-primary-light bg-app-primary-light/30 rounded-xl">
                                            <label className="block text-[10px] font-bold text-app-text-muted mb-1.5 uppercase tracking-widest">Git Repository URL <span className="text-red-400">*</span></label>
                                            <input
                                                type="text"
                                                value={agentsGitConfig.__global__?.git_repo_url || ''}
                                                onChange={(e) => setAgentsGitConfig({
                                                    ...agentsGitConfig,
                                                    __global__: {
                                                        ...agentsGitConfig.__global__,
                                                        git_repo_url: e.target.value,
                                                    },
                                                })}
                                                placeholder="https://github.com/org/repo.git"
                                                className="w-full px-3 py-2 border border-app-border rounded-lg focus:ring-2 focus:ring-app-primary-light focus:border-indigo-400 text-xs bg-app-bg-card text-app-text-main mb-3"
                                            />

                                            <label className="block text-[10px] font-bold text-app-text-muted mb-1.5 uppercase tracking-widest">Global Personal Access Token <span className="text-gray-400">(optional for public repos)</span></label>
                                            <input
                                                type="password"
                                                value={agentsGitConfig.__global__?.git_token || ''}
                                                onChange={(e) => setAgentsGitConfig({
                                                    ...agentsGitConfig,
                                                    __global__: {
                                                        ...agentsGitConfig.__global__,
                                                        git_token: e.target.value,
                                                    },
                                                })}
                                                placeholder="ghp_..."
                                                className="w-full px-3 py-2 border border-app-border rounded-lg focus:ring-2 focus:ring-app-primary-light focus:border-indigo-400 text-xs bg-app-bg-card text-app-text-main"
                                            />
                                        </div>
                                    </>
                                ) : (
                                    <>
                                        <p className="text-sm text-app-text-muted mb-4 font-medium">To run <b>{getAgentDisplayName(gitModalAgent)}</b>, provide global Git settings that all agents in this project will use.</p>

                                        <label className="block text-[11px] font-bold text-app-text-muted mb-2 uppercase tracking-widest">Git Repository URL <span className="text-red-400">*</span></label>
                                        <input type="text" value={gitRepoUrl} onChange={(e) => setGitRepoUrl(e.target.value)} placeholder="https://github.com/org/repo.git" className="w-full px-4 py-3 border-2 border-app-border rounded-xl focus:ring-4 focus:ring-app-primary-light focus:border-indigo-400 text-sm bg-app-bg-page/50 text-app-text-main transition-all duration-200 placeholder:text-app-border font-medium mb-4" />

                                        <label className="block text-[11px] font-bold text-app-text-muted mb-2 uppercase tracking-widest">Global Personal Access Token <span className="text-red-400">*</span></label>
                                        <input type="password" value={gitToken} onChange={(e) => setGitToken(e.target.value)} placeholder="ghp_..." className="w-full px-4 py-3 border-2 border-app-border rounded-xl focus:ring-4 focus:ring-app-primary-light focus:border-indigo-400 text-sm bg-app-bg-page/50 text-app-text-main transition-all duration-200 placeholder:text-app-border font-medium mb-6" />
                                    </>
                                )}
                            </div>
                            <div className="px-6 py-4 border-t border-app-border-light bg-app-bg-page flex items-center gap-3">
                                <button type="button" onClick={() => setGitModalAgent(null)} className="flex-1 py-3 px-4 font-bold text-app-text-label bg-app-bg-card hover:bg-app-bg-muted border border-app-border rounded-xl transition-colors">Cancel</button>
                                <button type="button" onClick={() => {
                                    if (gitModalAgent.id === '__run_all_setup__') {
                                        submitMultiAgentConfig();
                                    } else {
                                        handleRunAgent(gitModalAgent.id, gitRepoUrl, gitToken);
                                    }
                                }} disabled={gitModalAgent.id === '__run_all_setup__' ? (!agentsGitConfig.__global__?.git_repo_url?.trim() || !agentsGitConfig.__global__?.git_token?.trim()) : (!gitRepoUrl.trim() || !gitToken.trim())} className="flex-1 py-3 px-4 font-bold text-white bg-gradient-to-r from-app-primary to-app-primary hover:from-app-primary-hover hover:to-app-primary-hover rounded-xl transition-colors shadow-lg shadow-app-primary/30 hover:shadow-app-primary/50 disabled:opacity-50 disabled:cursor-not-allowed flex justify-center items-center gap-2 group">
                                    <Play className="w-4 h-4" /> {gitModalAgent.id === '__run_all_setup__' ? 'Start All Agents' : 'Start Agent'}
                                </button>
                            </div>
                        </div>
                    </div>
                )
            }
        </div >
    );
}
