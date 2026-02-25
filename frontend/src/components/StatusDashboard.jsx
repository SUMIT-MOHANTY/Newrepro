import React, { useState, useEffect, useCallback, useRef } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Flag, Activity, CheckCircle, Clock, Menu, PlusCircle, X, ArrowRight, Bot, Shield, Cpu, Play, RefreshCw, Eye, ListTodo, AlertCircle, ChevronRight, Users, Calendar, Wallet, Tag, AlertTriangle, CheckCircle2, Loader2, Terminal, Pencil, GitBranch } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import Skeleton, { SkeletonTheme } from 'react-loading-skeleton';
import 'react-loading-skeleton/dist/skeleton.css';

import { API_ENDPOINTS } from '../config';

const PROJECT_STORAGE_KEY = 'status_dashboard_selected_project_key';
const TASK_TOKEN_STORAGE_KEY = 'status_dashboard_task_token_cache';
const ROLE_STORAGE_KEY = 'status_dashboard_selected_role';
const TOKEN_REFRESH_THRESHOLD_SECONDS = 300;
const TOKEN_CACHE_MIN_TTL_SECONDS = 0;
const DASHBOARD_ROLES = [
    { value: 'cxo', label: 'CXO Dashboard', description: 'Executive snapshot' },
    { value: 'project', label: 'Project Dashboard', description: 'PM, team lead, delivery' },
    { value: 'sales', label: 'Sales Dashboard', description: 'Commercial and commitments' },
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

export default function StatusDashboard({ projects = [], projectsLoading = false, selectedProjectKey, setSelectedProjectKey, selectedRole, setSelectedRole }) {
    const navigate = useNavigate();
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
    const [newAgentConfig, setNewAgentConfig] = useState({ name: '', git_repo_url: '', git_token: '' });

    // ── External Task API State ──────────────────────────────────────
    const [isGeneratingTasks, setIsGeneratingTasks] = useState(false);
    const [taskList, setTaskList] = useState([]);
    const [isLoadingTasks, setIsLoadingTasks] = useState(false);
    const [taskListError, setTaskListError] = useState(null);
    const [totalTaskCount, setTotalTaskCount] = useState(0);
    const [nextPageUrl, setNextPageUrl] = useState(null);
    const [isLoadingMore, setIsLoadingMore] = useState(false);

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
            const data = await res.json();
            return data.agents || [];
        },
        enabled: !!token,
    });

    const setAgents = useCallback((updater) => {
        queryClient.setQueryData(['agents', selectedProjectKey], updater);
    }, [queryClient, selectedProjectKey]);

    const { isFetching: isLoadingProjectInfo } = useQuery({
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

    // Poll while agents are running
    useEffect(() => {
        const hasRunning = agents.some(a => a.status === 'running');
        if (!hasRunning) return;
        const interval = setInterval(() => {
            fetchAgents(true);
            fetchTasks(false, 1, true); // silent reload
        }, 3000);
        return () => clearInterval(interval);
    }, [agents, fetchAgents, fetchTasks]);

    // ── Run Agent (Docker execution) ─────────────────────────────────
    const handleRunAgentClick = (agent) => {
        if (agent.id === 'agent_03') return;
        const needsConfig = !agent.git_repo_url || !agent.has_git_token;
        if (needsConfig) {
            setGitRepoUrl(agent.git_repo_url || '');
            setGitToken('');
            setGitModalAgent(agent);
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
        navigate(`/governance?projectName=${encodeURIComponent(newProjectName.trim())}`);
    };

    // ── Run All Agents ────────────────────────────────────────────────
    const [runningAll, setRunningAll] = useState(false);

    const handleRunAll = async () => {
        const idleAgents = agents.filter(a => a.status === 'idle' && a.id !== 'agent_03');
        if (idleAgents.length === 0) return;

        const missingConfig = idleAgents.filter(agent => !agent.git_repo_url || !agent.has_git_token);
        if (missingConfig.length > 0) {
            const initialMap = {};
            const existingRepo = agents.find(a => a.git_repo_url)?.git_repo_url || '';
            missingConfig.forEach(agent => {
                initialMap[agent.id] = {
                    git_repo_url: agent.git_repo_url || existingRepo,
                    git_token: '',
                };
            });
            setAgentsGitConfig(initialMap);
            setGitModalAgent({ id: '__run_all_setup__', name: 'Configure Specific Agents', missingConfig });
            return;
        }

        setGitModalAgent(null);
        setRunningAll(true);
        setAgents(prev => prev.map(a => a.status === 'idle' ? { ...a, status: 'running', progress: 0, progress_message: 'Starting agent...' } : a));

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
        } catch (e) {
            console.error('Run all failed', e);
        } finally {
            setRunningAll(false);
        }
    };

    const submitMultiAgentConfig = async () => {
        setGitModalAgent(null);
        setRunningAll(true);
        setAgents(prev => prev.map(a => a.status === 'idle' ? { ...a, status: 'running', progress: 0, progress_message: 'Starting agent...' } : a));
        try {
            const headers = { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' };
            if (hasValidTaskToken) headers['x-task-token'] = taskToken;
            await fetch(withProjectToken(API_ENDPOINTS.AGENT_RUN_ALL), {
                method: 'POST',
                headers,
                body: JSON.stringify({ agents_config: agentsGitConfig }),
            });
            await fetchAgents();
            await fetchTasks(false, 1, true);
        } catch (e) {
            console.error('Run all failed with config', e);
        } finally {
            setRunningAll(false);
        }
    };

    // ── Add/Remove Agent ─────────────────────────────────────────────
    const handleAddAgent = () => {
        setShowAddAgentModal(true);
    };

    const submitAddAgent = async () => {
        setShowAddAgentModal(false);
        try {
            await fetch(withProjectToken(API_ENDPOINTS.AGENT_ADD), {
                method: 'POST',
                headers: {
                    'Authorization': `Bearer ${token}`,
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(newAgentConfig),
            });
            setNewAgentConfig({ name: '', git_repo_url: '', git_token: '' });
            fetchAgents();
        } catch (e) {
            console.error('Add agent failed', e);
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

    // ── Agent Card Config ────────────────────────────────────────────
    const agentConfig = {
        agent_01: {
            icon: <CheckCircle className="w-5 h-5 text-white" />,
            gradient: 'from-emerald-400 to-green-600',
            shadow: 'shadow-emerald-200',
            accent: 'from-emerald-400 to-green-500',
            color: 'emerald',
            stats: ['checks', 'coverage', 'avg_time'],
            statLabels: { checks: 'Checks', coverage: 'Coverage', avg_time: 'Duration' },
        },
        agent_02: {
            icon: <Shield className="w-5 h-5 text-white" />,
            gradient: 'from-amber-400 to-orange-600',
            shadow: 'shadow-orange-200',
            accent: 'from-amber-400 to-orange-500',
            color: 'amber',
            stats: ['risks', 'critical', 'avg_time'],
            statLabels: { risks: 'Risks', critical: 'Critical', avg_time: 'Duration' },
        },
        agent_03: {
            icon: <GitBranch className="w-5 h-5 text-white" />,
            gradient: 'from-indigo-500 to-blue-600',
            shadow: 'shadow-indigo-200',
            accent: 'from-indigo-500 to-blue-500',
            color: 'indigo',
            stats: ['avg_time'],
            statLabels: { avg_time: 'Duration' },
        },
    };


    // ── Render Agent Card ────────────────────────────────────────────
    const renderAgentCard = (agent) => {
        const isGitManager = agent.id === 'agent_03';
        const cfg = agentConfig[agent.id] || agentConfig.agent_01;
        const Icon = cfg.icon;
        const isRunning = agent.status === 'running';
        const isCompleted = agent.status === 'completed';
        const isError = agent.status === 'error';
        const isIdle = agent.status === 'idle';
        const statusColor = isRunning ? cfg.color : isCompleted ? 'emerald' : isError ? 'red' : 'gray';
        const canRun = taskList.filter(t => (t.taskStatus || '').toLowerCase() !== 'completed').length > 0;

        return (
            <div key={agent.id} className="bg-app-bg-card rounded-xl shadow border border-app-border-light p-5 flex flex-col relative overflow-hidden group hover:shadow-lg transition-shadow">
                <div className={`absolute top-0 left-0 right-0 h-1 bg-gradient-to-r ${cfg.accent}`}></div>

                <div className="flex items-start justify-between mb-4">
                    <div className="flex items-center gap-3">
                        <div className={`w-10 h-10 rounded-xl bg-gradient-to-br ${cfg.gradient} flex items-center justify-center shadow-lg ${cfg.shadow}`}>
                            {Icon}
                        </div>
                        <div>
                            <div className="flex items-center gap-2">
                                <h4 className="text-sm font-bold text-app-text-main">
                                    {isGitManager ? 'Git Manager' : agent.name}
                                </h4>
                                {!isGitManager && (
                                    <button
                                        type="button"
                                        onClick={() => startEditingAgentName(agent)}
                                        className="p-1 rounded-md text-app-text-light hover:text-app-text-label hover:bg-app-bg-muted"
                                        title="Edit agent settings"
                                    >
                                        <Pencil className="w-3.5 h-3.5" />
                                    </button>
                                )}
                            </div>
                            <p className="text-[10px] text-app-text-light uppercase tracking-wider font-semibold">{agent.id.replace('_', ' ').toUpperCase()}</p>
                            {!isGitManager && (
                                <p className="text-[10px] text-app-text-light">
                                    Git: {agent.git_repo_url ? 'URL saved' : 'URL missing'} | PAT: {agent.has_git_token ? 'saved' : 'missing'}
                                </p>
                            )}
                        </div>
                    </div>
                    <div className="flex items-center gap-1.5">
                        {isRunning && (
                            <span className="relative flex h-2.5 w-2.5">
                                <span className={`animate-ping absolute inline-flex h-full w-full rounded-full bg-${statusColor}-400 opacity-75`}></span>
                                <span className={`relative inline-flex rounded-full h-2.5 w-2.5 bg-${statusColor}-500`}></span>
                            </span>
                        )}
                        <span className={`text-[10px] font-bold text-${statusColor}-${isIdle ? '500' : '600'}`}>
                            {agent.status?.toUpperCase() || 'IDLE'}
                        </span>
                    </div>
                </div>

                {/* Stats */}
                <div className="flex items-center gap-4 mb-4 py-2 px-3 bg-app-bg-page rounded-lg">
                    {cfg.stats.map((key, idx) => (
                        <React.Fragment key={key}>
                            {idx > 0 && <div className="w-px h-8 bg-app-bg-hover"></div>}
                            <div className="text-center">
                                <p className="text-lg font-bold text-gray-800">{agent.stats?.[key] ?? '—'}</p>
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

                {/* Last run info */}
                <div className="flex items-center justify-between text-[10px] text-app-text-light mb-4">
                    <span className="flex items-center gap-1">
                        <Clock className="w-3 h-3" />
                        {agent.last_run ? `Last: ${new Date(agent.last_run).toLocaleTimeString()}` : 'Not run yet'}
                    </span>
                    {isCompleted && <span className="font-semibold text-app-status-success">✓ Completed</span>}
                    {isError && <span className="font-semibold text-app-status-error">✗ Error</span>}
                </div>

                {/* Actions */}
                <div className="flex gap-2 mt-auto">
                    {!isGitManager && (
                        (isIdle || isCompleted || isError) ? (
                            <button
                                onClick={() => handleRunAgentClick(agent)}
                                disabled={!canRun || runningAgent === agent.id}
                                className={`flex-1 inline-flex items-center justify-center gap-1.5 px-3 py-2 text-xs font-bold text-white rounded-lg shadow-sm transition-all ${canRun
                                    ? `bg-gradient-to-r ${cfg.gradient} hover:shadow-md hover:-translate-y-0.5`
                                    : 'bg-gray-300 cursor-not-allowed'
                                    }`}
                                title={!canRun ? 'No pending tasks available' : `Run ${agent.name}`}
                            >
                                {runningAgent === agent.id ? (<><Loader2 className="w-3 h-3 animate-spin" /> Starting...</>) : (<><Play className="w-3 h-3" /> Run Agent</>)}
                            </button>
                        ) : (
                            <button disabled className="flex-1 inline-flex items-center justify-center gap-1.5 px-3 py-2 text-xs font-bold text-app-text-light bg-app-bg-muted rounded-lg cursor-not-allowed">
                                <RefreshCw className="w-3 h-3 animate-spin" /> Running...
                            </button>
                        )
                    )}
                    <button
                        onClick={() => setShowLogModal(agent.id)}
                        className="inline-flex items-center justify-center gap-1 px-3 py-2 text-xs font-bold text-app-text-label bg-app-bg-muted rounded-lg hover:bg-app-bg-hover transition-colors"
                    >
                        <Terminal className="w-3 h-3" /> Log
                    </button>
                    {!isGitManager && (isCompleted || isError) && (
                        <button
                            onClick={() => handleResetAgent(agent.id)}
                            className="inline-flex items-center justify-center gap-1 px-3 py-2 text-xs font-bold text-app-text-label bg-app-bg-muted rounded-lg hover:bg-app-bg-hover transition-colors"
                            title="Reset agent to idle"
                        >
                            <RefreshCw className="w-3 h-3" />
                        </button>
                    )}
                </div>
            </div>
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

            const response = await fetch(API_ENDPOINTS.AGENT_AUTO_GENERATE, {
                method: 'POST',
                headers,
                body: JSON.stringify({
                    project_token: selectedProjectKey
                })
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
            <div className="flex-1 p-4 md:p-6 flex flex-col gap-6">
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

                <div className="grid grid-cols-1 lg:grid-cols-[minmax(0,1fr)_320px] gap-6 w-full items-start">
                    <div className="space-y-6 lg:col-start-1 w-full min-w-0">
                        <div className="bg-app-bg-card rounded-xl shadow border border-app-border-light p-6">
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

                        <div className="bg-app-bg-card rounded-xl shadow border border-app-border-light p-6">
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

                    <div className="w-full bg-app-bg-card rounded-xl shadow border border-app-border-light p-4 md:p-6 flex flex-col items-center lg:col-start-2 lg:row-span-4 sticky top-6">
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

                <div className="w-full mt-6 lg:col-start-1 min-w-0">
                    <div className="flex items-center justify-between mb-6">
                        <Skeleton height={24} width={180} />
                        <div className="flex items-center gap-2">
                            <Skeleton height={28} width={90} />
                            <Skeleton height={28} width={80} />
                            <Skeleton height={28} width={90} />
                        </div>
                    </div>
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
                        {[0, 1, 2].map((idx) => (
                            <div key={idx} className="bg-app-bg-card rounded-xl shadow border border-app-border-light p-5">
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
                    <div className="px-6 py-4 border-b border-app-border-light flex items-center justify-between bg-gradient-to-r from-gray-50/80 to-white">
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

                    <div className="divide-y divide-gray-50 p-4 md:p-0">
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

    return (
        <div className="w-full min-h-full bg-app-bg-page flex flex-col font-sans overflow-y-auto relative">
            {/* Top Graphic Header Area */}
            <div className="bg-app-bg-card shadow">

                {/* Top spacer since title is now in global navbar */}
                <div className="pt-4"></div>
                <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center px-4 md:px-8 py-2 mb-2 gap-3">
                    <div className="flex items-center space-x-4 flex-shrink-0">
                        {projects.length > 0 && (
                            <>
                                <div className="text-sm font-bold text-[#f27a24]">As of : {dashboardData?.generated_at ? new Date(dashboardData.generated_at).toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: '2-digit' }) : new Date().toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: '2-digit' })}</div>
                                <div className="text-sm font-bold text-gray-800 flex items-center">
                                    <div className={`w-4 h-4 mr-2 rounded-sm shadow-sm inline-block ${dashboardData?.project_status?.overall_health === 'Good' ? 'bg-emerald-500' : dashboardData?.project_status?.overall_health === 'At Risk' ? 'bg-amber-500' : 'bg-red-500'}`}></div>
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
                <div className="flex-1 p-4 md:p-6 flex flex-col items-center justify-center min-h-[500px]">
                    <div className="bg-app-bg-card rounded-2xl shadow-sm border border-app-border-light p-10 max-w-md w-full text-center flex flex-col items-center">
                        <div className="w-20 h-20 bg-app-primary-light rounded-full flex items-center justify-center mb-6 shadow-inner">
                            <PlusCircle className="w-10 h-10 text-blue-500" />
                        </div>
                        <h2 className="text-2xl font-extrabold text-gray-800 mb-2">No Projects Found</h2>
                        <p className="text-app-text-muted mb-8 text-sm leading-relaxed">
                            It looks like you haven't created any governance assessments yet. Add a new project to start tracking your progress and metrics.
                        </p>
                        <button
                            type="button"
                            onClick={() => setShowModal(true)}
                            className="inline-flex items-center gap-2 bg-gradient-to-r from-blue-600 to-indigo-600 text-white font-bold py-3.5 px-8 rounded-full shadow-lg shadow-blue-500/30 hover:shadow-blue-500/50 hover:-translate-y-0.5 transition-all w-full justify-center"
                        >
                            <PlusCircle className="w-5 h-5" />
                            <span>Add New Project</span>
                        </button>
                    </div>
                </div>
            ) : isDashboardSkeletonVisible ? (
                renderDashboardSkeleton()
            ) : (
                <div className="flex-1 p-4 md:p-6 flex flex-col gap-6">
                    <div className="bg-white rounded-xl border border-gray-100 shadow-sm px-4 py-3 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
                        <div>
                            <p className="text-[10px] uppercase tracking-widest font-bold text-gray-400">Active Role View</p>
                            <p className="text-sm font-bold text-gray-900">{selectedRoleMeta.label}</p>
                        </div>
                        <p className="text-xs text-gray-500">{selectedRoleMeta.description}</p>
                    </div>

                    {selectedRole === 'cxo' && (
                        <>
                            <div className="rounded-2xl bg-gradient-to-r from-slate-900 to-slate-700 text-white p-6 shadow-lg">
                                <p className="text-[11px] uppercase tracking-[0.2em] text-slate-200 font-bold mb-2">Executive Overview</p>
                                <h3 className="text-2xl font-bold">Portfolio Decision Dashboard</h3>
                                <p className="text-sm text-slate-200 mt-2">
                                    Strategic snapshot with health, launch readiness, milestone movement, and delivery risk.
                                </p>
                            </div>

                            <div className="grid grid-cols-2 lg:grid-cols-5 gap-4">
                                <div className="bg-white rounded-xl border border-gray-100 p-4 shadow-sm">
                                    <p className="text-[11px] font-bold text-gray-500 uppercase tracking-wide">Overall Health</p>
                                    <p className="text-2xl font-bold text-gray-900 mt-2">{overallHealth}</p>
                                </div>
                                <div className="bg-white rounded-xl border border-gray-100 p-4 shadow-sm">
                                    <p className="text-[11px] font-bold text-gray-500 uppercase tracking-wide">Launch Confidence</p>
                                    <p className="text-2xl font-bold text-gray-900 mt-2">{launchConfidence}</p>
                                </div>
                                <div className="bg-white rounded-xl border border-gray-100 p-4 shadow-sm">
                                    <p className="text-[11px] font-bold text-gray-500 uppercase tracking-wide">Completion</p>
                                    <p className="text-2xl font-bold text-gray-900 mt-2">{dashboardData?.kpi?.completion_percentage ?? 0}%</p>
                                </div>
                                <div className="bg-white rounded-xl border border-gray-100 p-4 shadow-sm">
                                    <p className="text-[11px] font-bold text-gray-500 uppercase tracking-wide">Launch In</p>
                                    <p className="text-2xl font-bold text-gray-900 mt-2">{dashboardData?.project_status?.days_until_launch ?? 0} days</p>
                                </div>
                                <div className="bg-white rounded-xl border border-gray-100 p-4 shadow-sm">
                                    <p className="text-[11px] font-bold text-gray-500 uppercase tracking-wide">Project Budget</p>
                                    <p className="text-2xl font-bold text-gray-900 mt-2">{projectInfo?.project?.project_wallet ?? '-'}</p>
                                </div>
                            </div>

                            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                                <div className="lg:col-span-2 bg-white rounded-xl shadow border border-gray-100 p-6">
                                    <div className="flex items-center mb-5">
                                        <Flag className="w-4 h-4 text-orange-500 mr-2" />
                                        <h3 className="text-sm font-bold text-gray-900 uppercase tracking-wide">Milestone Visibility</h3>
                                    </div>
                                    <div className="overflow-auto rounded-lg border border-gray-100" style={{ maxHeight: '320px' }}>
                                        <table className="min-w-full text-sm">
                                            <thead className="bg-orange-50 sticky top-0 z-10">
                                                <tr>
                                                    <th className="px-4 py-3 text-left font-bold text-gray-700">Milestone</th>
                                                    <th className="px-4 py-3 text-left font-bold text-gray-700">Status</th>
                                                    <th className="px-4 py-3 text-left font-bold text-gray-700">Date</th>
                                                </tr>
                                            </thead>
                                            <tbody className="divide-y divide-gray-100 text-gray-700">
                                                {(dashboardData?.milestones?.completed || []).map((milestone) => (
                                                    <tr key={`done-${milestone.id}`}>
                                                        <td className="px-4 py-3">{milestone.name}</td>
                                                        <td className="px-4 py-3 text-emerald-600 font-semibold">Completed</td>
                                                        <td className="px-4 py-3">{milestone.deadline || '-'}</td>
                                                    </tr>
                                                ))}
                                                {(dashboardData?.milestones?.key_milestones_and_dates || []).map((milestone) => (
                                                    <tr key={`open-${milestone.id}`}>
                                                        <td className="px-4 py-3">{milestone.name}</td>
                                                        <td className="px-4 py-3 text-amber-600 font-semibold">In Progress</td>
                                                        <td className="px-4 py-3">{milestone.deadline || '-'}</td>
                                                    </tr>
                                                ))}
                                                {!(dashboardData?.milestones?.completed?.length || dashboardData?.milestones?.key_milestones_and_dates?.length) && (
                                                    <tr>
                                                        <td className="px-4 py-6 text-center text-gray-400 italic" colSpan="3">No milestone records available</td>
                                                    </tr>
                                                )}
                                            </tbody>
                                        </table>
                                    </div>
                                </div>

                                <div className="space-y-4">
                                    <div className="bg-white rounded-xl border border-gray-100 p-5 shadow-sm">
                                        <p className="text-[11px] font-bold text-gray-500 uppercase tracking-wide">Risk Exposure</p>
                                        <p className="text-3xl font-bold text-gray-900 mt-2">{cxoRiskLabel}</p>
                                        <p className="text-xs text-gray-500 mt-1">{lateTaskCount} late task(s) currently flagged</p>
                                    </div>
                                    <div className="bg-white rounded-xl border border-gray-100 p-5 shadow-sm">
                                        <p className="text-[11px] font-bold text-gray-500 uppercase tracking-wide">Workload Split</p>
                                        <p className="text-2xl font-bold text-gray-900 mt-2">
                                            {dashboardData?.actual_vs_remaining_work?.work_completed_percentage ?? 0}% complete
                                        </p>
                                        <p className="text-xs text-gray-500 mt-1">
                                            {dashboardData?.actual_vs_remaining_work?.work_remaining_percentage ?? 0}% remaining effort
                                        </p>
                                    </div>
                                    <div className="bg-white rounded-xl border border-gray-100 p-5 shadow-sm">
                                        <p className="text-[11px] font-bold text-gray-500 uppercase tracking-wide">Task Distribution</p>
                                        <p className="text-2xl font-bold text-gray-900 mt-2">{dashboardData?.summary_statistics?.total_tasks ?? 0}</p>
                                        <p className="text-xs text-gray-500 mt-1">
                                            {dashboardData?.summary_statistics?.in_progress_tasks ?? 0} in progress, {dashboardData?.summary_statistics?.completed_tasks ?? 0} completed
                                        </p>
                                    </div>
                                </div>
                            </div>
                        </>
                    )}

                    {selectedRole === 'sales' && (
                        <>
                            <div className="rounded-2xl bg-gradient-to-r from-orange-500 to-amber-500 text-white p-6 shadow-lg">
                                <p className="text-[11px] uppercase tracking-[0.2em] text-orange-100 font-bold mb-2">Commercial Snapshot</p>
                                <h3 className="text-2xl font-bold">Sales Commitment Dashboard</h3>
                                <p className="text-sm text-orange-100 mt-2">
                                    Delivery commitments, budget posture, and deal-facing metrics for customer communication.
                                </p>
                            </div>

                            <div className="grid grid-cols-2 lg:grid-cols-5 gap-4">
                                <div className="bg-white rounded-xl border border-gray-100 p-4 shadow-sm">
                                    <p className="text-[11px] font-bold text-gray-500 uppercase tracking-wide">Project Status</p>
                                    <p className="text-xl font-bold text-gray-900 mt-2">{dashboardData?.project?.status || '-'}</p>
                                </div>
                                <div className="bg-white rounded-xl border border-gray-100 p-4 shadow-sm">
                                    <p className="text-[11px] font-bold text-gray-500 uppercase tracking-wide">Total Wallet</p>
                                    <p className="text-xl font-bold text-gray-900 mt-2">{projectInfo?.project?.project_wallet ?? '-'}</p>
                                </div>
                                <div className="bg-white rounded-xl border border-gray-100 p-4 shadow-sm">
                                    <p className="text-[11px] font-bold text-gray-500 uppercase tracking-wide">Consumed Wallet</p>
                                    <p className="text-xl font-bold text-gray-900 mt-2">{usedWallet}</p>
                                </div>
                                <div className="bg-white rounded-xl border border-gray-100 p-4 shadow-sm">
                                    <p className="text-[11px] font-bold text-gray-500 uppercase tracking-wide">Remaining Wallet</p>
                                    <p className="text-xl font-bold text-gray-900 mt-2">{remainingWallet}</p>
                                </div>
                                <div className="bg-white rounded-xl border border-gray-100 p-4 shadow-sm">
                                    <p className="text-[11px] font-bold text-gray-500 uppercase tracking-wide">Delivery Team</p>
                                    <p className="text-xl font-bold text-gray-900 mt-2">{projectInfo?.team_members?.length ?? 0}</p>
                                </div>
                            </div>

                            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                                <div className="bg-white rounded-xl border border-gray-100 shadow-sm p-6">
                                    <div className="flex items-center mb-5">
                                        <Calendar className="w-4 h-4 text-orange-500 mr-2" />
                                        <h3 className="text-sm font-bold text-gray-900 uppercase tracking-wide">Client-Facing Delivery Commitments</h3>
                                    </div>
                                    <div className="space-y-3">
                                        <div className="flex items-center justify-between p-3 rounded-lg bg-orange-50">
                                            <span className="text-sm font-semibold text-gray-700">Due This Week</span>
                                            <span className="text-lg font-bold text-orange-600">{dueThisWeekCount}</span>
                                        </div>
                                        <div className="flex items-center justify-between p-3 rounded-lg bg-gray-50">
                                            <span className="text-sm font-semibold text-gray-700">Upcoming Next Period</span>
                                            <span className="text-lg font-bold text-gray-900">{upcomingTaskCount}</span>
                                        </div>
                                        <div className="flex items-center justify-between p-3 rounded-lg bg-red-50">
                                            <span className="text-sm font-semibold text-gray-700">Late Tasks</span>
                                            <span className="text-lg font-bold text-red-600">{lateTaskCount}</span>
                                        </div>
                                        <div className="flex items-center justify-between p-3 rounded-lg bg-blue-50">
                                            <span className="text-sm font-semibold text-gray-700">In Progress</span>
                                            <span className="text-lg font-bold text-blue-600">{inProgressTaskCount}</span>
                                        </div>
                                    </div>
                                </div>

                                <div className="bg-white rounded-xl border border-gray-100 shadow-sm p-6">
                                    <div className="flex items-center mb-5">
                                        <Tag className="w-4 h-4 text-orange-500 mr-2" />
                                        <h3 className="text-sm font-bold text-gray-900 uppercase tracking-wide">Delivery Readiness</h3>
                                    </div>
                                    <div className="space-y-4">
                                        <div className="p-3 rounded-lg bg-gray-50 border border-gray-100">
                                            <p className="text-[11px] font-bold text-gray-500 uppercase tracking-wide">Expected Launch Date</p>
                                            <p className="text-sm font-bold text-gray-900 mt-1">
                                                {dashboardData?.project_status?.expected_launch_date
                                                    ? new Date(dashboardData.project_status.expected_launch_date).toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: '2-digit' })
                                                    : '-'}
                                            </p>
                                        </div>
                                        <div className="p-3 rounded-lg bg-gray-50 border border-gray-100">
                                            <p className="text-[11px] font-bold text-gray-500 uppercase tracking-wide">Completion Status</p>
                                            <p className="text-sm font-bold text-gray-900 mt-1">
                                                {dashboardData?.kpi?.completion_percentage ?? 0}% complete, {completedTaskCount} recently completed
                                            </p>
                                        </div>
                                        <div className="p-3 rounded-lg bg-gray-50 border border-gray-100">
                                            <p className="text-[11px] font-bold text-gray-500 uppercase tracking-wide">Overall Health Signal</p>
                                            <p className="text-sm font-bold text-gray-900 mt-1">{overallHealth}</p>
                                        </div>
                                    </div>
                                </div>
                            </div>

                            <div className="bg-white rounded-xl border border-gray-100 shadow-sm p-6">
                                <h3 className="text-sm font-bold text-gray-900 uppercase tracking-wide mb-4">Sales Signals</h3>
                                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                                    {salesSignals.map((signal) => (
                                        <div key={signal.label} className="rounded-lg border border-gray-100 bg-gray-50 p-4">
                                            <p className="text-[11px] font-bold text-gray-500 uppercase tracking-wide">{signal.label}</p>
                                            <p className="text-sm font-bold text-gray-900 mt-2">{signal.value}</p>
                                        </div>
                                    ))}
                                </div>
                                <p className="text-xs text-gray-500 mt-4">
                                    Fields showing "Backend field needed" can be connected once sales data APIs are available.
                                </p>
                            </div>
                        </>
                    )}

                    {selectedRole === 'project' && (
                        <>

                            {/* Top Metric Cards - Full Width */}
                            <div className="w-full flex flex-col gap-3 md:gap-4">
                                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                                    <div className="bg-app-bg-card p-4 rounded-xl shadow border border-app-border-light flex flex-col items-center justify-center relative">
                                        <p className="text-xs font-bold text-app-text-label mb-1">Project</p>
                                        <h3 className="text-xl font-bold text-gray-800 mb-0 truncate max-w-full px-1">{dashboardData?.project?.name ?? '—'}</h3>
                                        <p className="text-[10px] text-app-text-muted uppercase tracking-widest">{dashboardData?.project?.status ?? '—'}</p>
                                    </div>
                                    <div className="bg-app-bg-card p-4 rounded-xl shadow border border-app-border-light flex flex-col items-center justify-center relative">
                                        <p className="text-xs font-bold text-app-text-label mb-1">Project Duration</p>
                                        <h3 className="text-3xl font-bold text-gray-800 mb-0">{dashboardData?.kpi?.duration_days ?? 0}</h3>
                                        <p className="text-[10px] text-app-text-muted uppercase tracking-widest">Days</p>
                                    </div>
                                    <div className="bg-app-bg-card col-span-2 md:col-span-2 p-4 rounded-xl shadow border border-app-border-light flex flex-row items-center justify-around relative">
                                        <div className="flex flex-col items-center">
                                            <p className="text-xs font-bold text-app-text-label mb-1">Total Sprints</p>
                                            <div className="flex items-center relative">
                                                <h3 className="text-3xl font-bold text-gray-800 mb-0">{dashboardData?.summary_statistics?.total_sprints ?? 0}</h3>
                                            </div>
                                        </div>
                                        <div className="w-px h-12 bg-app-bg-hover"></div>
                                        <div className="flex flex-col items-center w-40">
                                            <p className="text-xs font-bold text-app-text-label mb-1">Hours Logged</p>
                                            <div className="flex items-center relative mb-2 w-full justify-center">
                                                <h3 className="text-3xl font-bold text-gray-800 mb-0">{dashboardData?.kpi?.total_hours_logged ?? 0}</h3>
                                            </div>
                                            <div className="w-full bg-app-bg-hover rounded-full h-2.5">
                                                <div className="bg-app-text-label h-2.5 rounded-full" style={{ width: `${dashboardData?.kpi?.work_complete_percentage ?? 0}%` }}></div>
                                            </div>
                                        </div>
                                    </div>
                                </div>

                                <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3 mt-4">
                                    <div className="bg-app-bg-card p-3 rounded-xl shadow border border-app-border-light flex flex-col items-center justify-center">
                                        <p className="text-[11px] font-bold text-app-text-label mb-1">Active Sprints</p>
                                        <h3 className="text-2xl font-bold text-gray-800">{dashboardData?.summary_statistics?.active_sprints ?? 0}</h3>
                                        <p className="text-[9px] text-app-text-muted uppercase tracking-wide">Running</p>
                                    </div>
                                    <div className="bg-app-bg-card p-3 rounded-xl shadow border border-app-border-light flex flex-col items-center justify-center">
                                        <p className="text-[11px] font-bold text-app-text-label mb-1 text-center leading-tight">In Progress</p>
                                        <h3 className="text-2xl font-bold text-gray-800">{dashboardData?.summary_statistics?.in_progress_tasks ?? 0}</h3>
                                        <p className="text-[9px] text-app-text-muted uppercase tracking-wide">Tasks</p>
                                    </div>
                                    <div className="bg-app-bg-card p-3 rounded-xl shadow border border-app-border-light flex flex-col items-center justify-center">
                                        <p className="text-[11px] font-bold text-app-text-label mb-1">Pending Tasks</p>
                                        <h3 className="text-2xl font-bold text-gray-800">{dashboardData?.summary_statistics?.pending_tasks ?? 0}</h3>
                                        <p className="text-[9px] text-app-text-muted uppercase tracking-wide">Awaiting</p>
                                    </div>
                                    <div className="bg-app-bg-card p-3 rounded-xl shadow border border-app-border-light flex flex-col items-center justify-center">
                                        <p className="text-[11px] font-bold text-app-text-label mb-1">Completed</p>
                                        <h3 className="text-2xl font-bold text-gray-800">{dashboardData?.summary_statistics?.completed_tasks ?? 0}</h3>
                                        <p className="text-[9px] text-app-text-muted uppercase tracking-wide">Done</p>
                                    </div>
                                    <div className="bg-app-bg-card p-3 rounded-xl shadow border border-app-border-light flex flex-col items-center justify-center">
                                        <p className="text-[11px] font-bold text-app-text-label mb-1">Total Tasks</p>
                                        <h3 className="text-2xl font-bold text-gray-800">{dashboardData?.summary_statistics?.total_tasks ?? 0}</h3>
                                        <p className="text-[9px] text-app-text-muted uppercase tracking-wide">Tracked</p>
                                    </div>
                                </div>
                            </div>

                            {/* Bottom Section: 2 Columns */}
                            <div className="grid grid-cols-1 lg:grid-cols-[minmax(0,1fr)_320px] gap-6 w-full items-start">

                                {/* Left Column (Main Content) */}
                                <div className="space-y-6 lg:col-start-1 w-full min-w-0">

                                    {/* KEY MILESTONES & DATES */}
                                    <div className="bg-app-bg-card rounded-xl shadow border border-app-border-light p-6 relative">
                                        <div className="flex items-center mb-6">
                                            <div className="p-2 mr-3 bg-orange-50 rounded text-orange-500">
                                                <Flag className="w-5 h-5" />
                                            </div>
                                            <h3 className="text-[15px] font-bold text-[#f27a24] uppercase tracking-wide">KEY MILESTONES & DATES</h3>
                                        </div>
                                        <div className="overflow-auto rounded-lg border border-app-border-light" style={{ maxHeight: '320px' }}>
                                            <table className="min-w-full text-sm">
                                                <colgroup><col style={{ width: '30%' }} /><col style={{ width: '35%' }} /><col style={{ width: '35%' }} /></colgroup>
                                                <thead className="bg-[#fdf4e6] sticky top-0 z-10">
                                                    <tr>
                                                        <th className="px-4 py-3 text-left font-bold text-gray-800">Milestone</th>
                                                        <th className="px-4 py-3 text-left font-bold text-gray-800">Status</th>
                                                        <th className="px-4 py-3 text-left font-bold text-gray-800">Date</th>
                                                    </tr>
                                                </thead>
                                                <tbody className="divide-y divide-gray-100 text-app-text-label font-medium">
                                                    {dashboardData?.milestones?.completed?.map(ms => (
                                                        <tr key={ms.id}>
                                                            <td className="px-4 py-3">{ms.name}</td>
                                                            <td className="px-4 py-3 text-app-status-success">Completed</td>
                                                            <td className="px-4 py-3">{ms.deadline}</td>
                                                        </tr>
                                                    ))}
                                                    {dashboardData?.milestones?.key_milestones_and_dates?.map(ms => (
                                                        <tr key={ms.id}>
                                                            <td className="px-4 py-3 break-words pr-8">{ms.name}</td>
                                                            <td className="px-4 py-3 text-orange-500">In Progress</td>
                                                            <td className="px-4 py-3 whitespace-nowrap">{ms.deadline}</td>
                                                        </tr>
                                                    ))}
                                                    {(!dashboardData?.milestones?.completed?.length && !dashboardData?.milestones?.key_milestones_and_dates?.length) && (
                                                        <tr>
                                                            <td className="px-4 py-3" colSpan="3">No milestones available</td>
                                                        </tr>
                                                    )}
                                                </tbody>
                                            </table>
                                        </div>
                                    </div>

                                    {/* ACTUAL VS REMAINING WORK */}
                                    <div className="bg-app-bg-card rounded-xl shadow border border-app-border-light p-6 flex flex-col relative">
                                        <div className="flex items-center mb-8">
                                            <div className="p-2 mr-3 bg-orange-50 rounded text-orange-500">
                                                <Activity className="w-5 h-5" />
                                            </div>
                                            <h3 className="text-[15px] font-bold text-[#f27a24] uppercase tracking-wide">ACTUAL VS REMAINING WORK</h3>
                                        </div>

                                        <div className="flex-1 flex items-end justify-center px-12 mb-8 relative">
                                            <div className="absolute left-10 flex flex-col justify-between h-[200px] bottom-0 text-xs font-bold text-app-text-muted w-10 text-right pr-2">
                                                <span className="relative -top-2">100%</span>
                                                <span className="relative">50%</span>
                                                <span className="relative top-2">0%</span>
                                            </div>

                                            {/* Grid lines */}
                                            <div className="absolute left-20 right-40 flex flex-col justify-between h-[200px] bottom-0 pointer-events-none">
                                                <div className="w-full border-t border-app-border"></div>
                                                <div className="w-full border-t border-app-border"></div>
                                                <div className="w-full border-t border-gray-500"></div>
                                            </div>

                                            {/* The Stacked Bar */}
                                            <div className="w-[30%] min-w-[150px] relative z-10 flex flex-col justify-end h-[200px]">
                                                {/* Remaining Work */}
                                                <div className="bg-[#feebad] w-full relative flex items-center justify-center" style={{ height: `${Math.max(dashboardData?.actual_vs_remaining_work?.work_remaining_percentage ?? 0, 5)}%`, minHeight: '20px' }}>
                                                    <span className="text-orange-500 font-bold text-sm">{dashboardData?.actual_vs_remaining_work?.work_remaining_percentage ?? 0}%</span>
                                                </div>
                                                {/* Completed Work */}
                                                <div className="bg-[#424242] w-full relative flex items-center justify-center" style={{ height: `${Math.max(dashboardData?.actual_vs_remaining_work?.work_completed_percentage ?? 0, 5)}%`, minHeight: '20px' }}>
                                                    <span className="text-white font-bold text-sm">{dashboardData?.actual_vs_remaining_work?.work_completed_percentage ?? 0}%</span>
                                                </div>
                                            </div>

                                            <div className="absolute bottom-[-25px] w-full text-center text-[10px] font-bold text-app-text-muted">
                                                Overall Assessment Progress
                                            </div>

                                            {/* Legend */}
                                            <div className="absolute right-10 bottom-20 flex flex-col gap-3">
                                                <div className="flex items-center">
                                                    <div className="w-6 h-4 bg-[#feebad] mr-3"></div>
                                                    <span className="text-sm text-app-text-label font-medium">Remaining Work</span>
                                                </div>
                                                <div className="flex items-center">
                                                    <div className="w-6 h-4 bg-[#424242] mr-3"></div>
                                                    <span className="text-sm text-app-text-label font-medium">Completed Work</span>
                                                </div>
                                            </div>
                                        </div>
                                    </div>


                                </div>

                                {/* Right Column (Sidebar Summary) */}
                                <div className="w-full bg-app-bg-card rounded-xl shadow border border-app-border-light p-4 md:p-6 flex flex-col items-center lg:col-start-2 lg:row-span-4 sticky top-6">
                                    <h2 className="text-[22px] font-bold text-[#f27a24] mb-4">Project Status</h2>
                                    <div className="w-full border-t-2 border-[#f27a24] mb-8 opacity-50"></div>

                                    <div className="w-full mb-10 flex flex-col items-center relative">
                                        <div className="absolute left-[-5px] top-0 text-app-status-success">
                                            <svg className="w-8 h-8" fill="currentColor" viewBox="0 0 24 24"><path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"></path></svg>
                                        </div>
                                        <div className="bg-app-bg-card border rounded p-4 text-center w-5/6 mx-auto shadow-sm relative z-10">
                                            <p className="text-[10px] font-bold text-gray-800 uppercase mb-2">EXPECTED LAUNCH DATE</p>
                                            <h3 className="text-2xl font-black text-app-text-main mb-2">{dashboardData?.project_status?.days_until_launch ?? 0} <span className="text-sm font-medium">Days</span></h3>
                                            <div className="flex items-center justify-center w-full mb-2">
                                                <div className="h-px bg-gray-300 w-full relative">
                                                    <div className="absolute left-0 top-[-3px] w-2 h-2 bg-gray-400 rounded-full"></div>
                                                    <div className="absolute right-0 top-[-3px] w-2 h-2 bg-gray-400 rounded-full"></div>
                                                </div>
                                            </div>
                                            <p className="text-xs italic text-app-text-muted">{dashboardData?.project_status?.expected_launch_date ? new Date(dashboardData.project_status.expected_launch_date).toLocaleDateString('en-US', { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' }) : '—'}</p>
                                        </div>
                                    </div>

                                    <div className="w-full mb-10 flex flex-col items-center">
                                        <div className="flex justify-center items-center w-full relative mb-1">
                                            <div className={`absolute left-8 ${dashboardData?.project_status?.overall_health === 'Good' ? 'text-app-status-success' : dashboardData?.project_status?.overall_health === 'At Risk' ? 'text-app-status-warning' : 'text-app-status-error'}`}>
                                                <Activity className="w-8 h-8" />
                                            </div>
                                            <div className={`w-10 h-10 rounded-full shadow-lg ${dashboardData?.project_status?.overall_health === 'Good' ? 'bg-gradient-to-br from-green-400 to-green-600 shadow-green-500/30' : dashboardData?.project_status?.overall_health === 'At Risk' ? 'bg-gradient-to-br from-amber-400 to-amber-600 shadow-amber-500/30' : 'bg-gradient-to-br from-red-400 to-red-600 shadow-red-500/30'}`}></div>
                                        </div>
                                        <p className="text-sm font-bold text-gray-800 mt-2">Overall Health: {dashboardData?.project_status?.overall_health ?? '—'}</p>
                                    </div>

                                    <div className="w-full border-t border-app-border-light mb-8 w-4/5 mx-auto"></div>

                                    {/* Circular Gauge 1 */}
                                    <div className="mb-10 flex flex-col items-center relative w-full">
                                        <div className="absolute left-8 text-orange-200">
                                            <svg className="w-8 h-8 opacity-50" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4"></path></svg>
                                        </div>
                                        <div className="relative w-24 h-24 mb-4">
                                            <svg className="w-24 h-24 transform -rotate-90">
                                                <circle cx="48" cy="48" r="40" stroke="#fdf4e6" strokeWidth="12" fill="none" />
                                                <circle cx="48" cy="48" r="40" stroke="#f27a24" strokeWidth="12" fill="none" strokeDasharray="251" strokeDashoffset={251 - (251 * (dashboardData?.kpi?.completion_percentage ?? 0)) / 100} strokeLinecap="round" />
                                            </svg>
                                            <div className="absolute inset-0 flex items-center justify-center">
                                                <span className="text-xl font-bold text-gray-800">{dashboardData?.kpi?.completion_percentage ?? 0}%</span>
                                            </div>
                                        </div>
                                        <p className="text-[13px] font-bold text-app-text-label">Completion Rate</p>
                                    </div>

                                    <div className="w-full border-t border-app-border-light mb-8 w-4/5 mx-auto"></div>

                                    {/* Circular Gauge 2 */}
                                    <div className="mb-10 flex flex-col items-center relative w-full">
                                        <div className="absolute left-8 text-app-border">
                                            <svg className="w-6 h-6 opacity-70" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M5 13l4 4L19 7"></path></svg>
                                        </div>
                                        <div className="relative w-24 h-24 mb-4">
                                            <svg className="w-24 h-24 transform -rotate-90">
                                                <circle cx="48" cy="48" r="40" stroke="#f3f4f6" strokeWidth="12" fill="none" />
                                                <circle cx="48" cy="48" r="40" stroke="#9ca3af" strokeWidth="12" fill="none" strokeDasharray="251" strokeDashoffset={251 - (251 * (dashboardData?.project_status?.project_progress ?? 0)) / 100} strokeLinecap="round" />
                                            </svg>
                                            <div className="absolute inset-0 flex items-center justify-center">
                                                <span className="text-xl font-bold text-gray-800">{dashboardData?.project_status?.project_progress ?? 0}%</span>
                                            </div>
                                        </div>
                                        <p className="text-[13px] font-bold text-app-text-label">Project Progress</p>
                                    </div>

                                    <div className="w-full border-t border-app-border-light mb-8 w-4/5 mx-auto"></div>

                                    {/* Circular Gauge 3 */}
                                    <div className="mb-6 flex flex-col items-center relative w-full">
                                        <div className="absolute left-6 text-app-text-label">
                                            <svg className="w-8 h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M8 7v8a2 2 0 002 2h6M8 7V5a2 2 0 012-2h4.586a1 1 0 01.707.293l4.414 4.414a1 1 0 01.293.707V15a2 2 0 01-2 2h-2M8 7H6a2 2 0 00-2 2v10a2 2 0 002 2h8a2 2 0 002-2v-2"></path></svg>
                                        </div>
                                        <div className="relative w-24 h-24 mb-4">
                                            <svg className="w-24 h-24 transform -rotate-90">
                                                <circle cx="48" cy="48" r="40" stroke="#f3f4f6" strokeWidth="12" fill="none" />
                                                {(() => {
                                                    const activeSprint = dashboardData?.sprint_status?.find(s => s.status === "On Going") || dashboardData?.sprint_status?.[0];
                                                    let sprintProgress = 0;
                                                    if (activeSprint && (activeSprint.actual_work + activeSprint.remaining_work) > 0) {
                                                        sprintProgress = Math.round((activeSprint.actual_work / (activeSprint.actual_work + activeSprint.remaining_work)) * 100);
                                                    }
                                                    return (
                                                        <circle cx="48" cy="48" r="40" stroke="#1f2937" strokeWidth="12" fill="none" strokeDasharray="251" strokeDashoffset={251 - (251 * sprintProgress) / 100} strokeLinecap="round" />
                                                    );
                                                })()}
                                            </svg>
                                            <div className="absolute inset-0 flex items-center justify-center">
                                                <span className="text-xl font-bold text-gray-800">
                                                    {(() => {
                                                        const activeSprint = dashboardData?.sprint_status?.find(s => s.status === "On Going") || dashboardData?.sprint_status?.[0];
                                                        if (activeSprint && (activeSprint.actual_work + activeSprint.remaining_work) > 0) {
                                                            return Math.round((activeSprint.actual_work / (activeSprint.actual_work + activeSprint.remaining_work)) * 100) + '%';
                                                        }
                                                        return '0%';
                                                    })()}
                                                </span>
                                            </div>
                                        </div>
                                        <p className="text-[13px] font-bold text-app-text-label">Sprint Progress</p>
                                    </div>
                                </div>

                                {/* Task Tables Section - matching screenshot layout */}
                                {dashboardData?.tasks && (
                                    <div className="mt-8 space-y-6 lg:col-start-1 w-full min-w-0">
                                        {/* Row 1: Late Tasks + Upcoming Tasks (Next Period) */}
                                        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                                            {/* Late Tasks Table */}
                                            <div className="bg-[#f8f9fa] rounded-xl shadow border border-app-border p-6">
                                                <h3 className="text-[17px] font-bold text-[#f27a24] mb-4">Late Tasks</h3>
                                                <div className="overflow-auto rounded-lg border border-app-border" style={{ minHeight: '150px', maxHeight: '320px' }}>
                                                    <table className="min-w-full text-sm">
                                                        <thead className="sticky top-0 z-10">
                                                            <tr className="bg-[#f27a24] text-white">
                                                                <th className="px-4 py-2.5 text-left font-bold text-xs w-12">#</th>
                                                                <th className="px-4 py-2.5 text-left font-bold text-xs">Task Description</th>
                                                                <th className="px-4 py-2.5 text-right font-bold text-xs w-28">Target</th>
                                                            </tr>
                                                        </thead>
                                                        <tbody className="divide-y divide-gray-100 bg-app-bg-card">
                                                            {(dashboardData.tasks.late_tasks || []).map((task, idx) => (
                                                                <tr key={task.id} className="hover:bg-app-status-errorBg/50">
                                                                    <td className="px-4 py-3 text-app-text-label font-semibold">{idx + 1}</td>
                                                                    <td className="px-4 py-3 text-gray-800 font-medium">{task.name || task.description || 'Untitled'}</td>
                                                                    <td className="px-4 py-3 text-right text-app-text-label font-semibold whitespace-nowrap">{task.deadline ? new Date(task.deadline).toLocaleDateString('en-US', { month: 'short', day: '2-digit', year: 'numeric' }) : '—'}</td>
                                                                </tr>
                                                            ))}
                                                            {(!dashboardData.tasks.late_tasks || dashboardData.tasks.late_tasks.length === 0) && (
                                                                <tr><td colSpan="3" className="px-4 py-6 text-center text-app-text-light italic">No late tasks</td></tr>
                                                            )}
                                                        </tbody>
                                                    </table>
                                                </div>
                                            </div>

                                            {/* Upcoming Tasks (Next Period) Table */}
                                            <div className="bg-[#f8f9fa] rounded-xl shadow border border-app-border p-6">
                                                <h3 className="text-[17px] font-bold text-[#f27a24] mb-4">Upcoming Tasks (Next Period)</h3>
                                                <div className="overflow-auto rounded-lg border border-app-border" style={{ minHeight: '150px', maxHeight: '320px' }}>
                                                    <table className="min-w-full text-sm">
                                                        <thead className="sticky top-0 z-10">
                                                            <tr className="bg-[#f27a24] text-white">
                                                                <th className="px-4 py-2.5 text-left font-bold text-xs w-12">#</th>
                                                                <th className="px-4 py-2.5 text-left font-bold text-xs">Task Description</th>
                                                                <th className="px-4 py-2.5 text-right font-bold text-xs w-28">Target</th>
                                                            </tr>
                                                        </thead>
                                                        <tbody className="divide-y divide-gray-100 bg-app-bg-card">
                                                            {(dashboardData.tasks.upcoming_tasks_next_period || []).map((task, idx) => (
                                                                <tr key={task.id} className="hover:bg-app-bg-page">
                                                                    <td className="px-4 py-3 text-app-text-label font-semibold">{idx + 1}</td>
                                                                    <td className="px-4 py-3 text-gray-800 font-medium">{task.name || task.description || 'Untitled'}</td>
                                                                    <td className="px-4 py-3 text-right text-app-text-label font-semibold whitespace-nowrap">{task.target_date ? new Date(task.target_date).toLocaleDateString('en-US', { month: 'short', day: '2-digit', year: 'numeric' }) : '—'}</td>
                                                                </tr>
                                                            ))}
                                                            {(!dashboardData.tasks.upcoming_tasks_next_period || dashboardData.tasks.upcoming_tasks_next_period.length === 0) && (
                                                                <tr><td colSpan="3" className="px-4 py-6 text-center text-app-text-light italic">No upcoming tasks</td></tr>
                                                            )}
                                                        </tbody>
                                                    </table>
                                                </div>
                                            </div>
                                        </div>

                                        {/* Row 2: Due This Week + In Progress / Recently Completed */}
                                        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                                            {/* Due This Week Table */}
                                            <div className="bg-[#f8f9fa] rounded-xl shadow border border-app-border p-6">
                                                <h3 className="text-[17px] font-bold text-[#f27a24] mb-4">Due This Week</h3>
                                                <div className="overflow-auto rounded-lg border border-app-border" style={{ minHeight: '150px', maxHeight: '320px' }}>
                                                    <table className="min-w-full text-sm">
                                                        <thead className="sticky top-0 z-10">
                                                            <tr className="bg-[#f27a24] text-white">
                                                                <th className="px-4 py-2.5 text-left font-bold text-xs w-12">#</th>
                                                                <th className="px-4 py-2.5 text-left font-bold text-xs">Task Description</th>
                                                                <th className="px-4 py-2.5 text-center font-bold text-xs w-20">Progress</th>
                                                                <th className="px-4 py-2.5 text-right font-bold text-xs w-28">Deadline</th>
                                                            </tr>
                                                        </thead>
                                                        <tbody className="divide-y divide-gray-100 bg-app-bg-card">
                                                            {(dashboardData.tasks.due_this_week || []).map((task, idx) => (
                                                                <tr key={task.id} className="hover:bg-orange-50/50">
                                                                    <td className="px-4 py-3 text-app-text-label font-semibold">{idx + 1}</td>
                                                                    <td className="px-4 py-3 text-gray-800 font-medium">{task.name || task.description || 'Untitled'}</td>
                                                                    <td className="px-4 py-3 text-center text-app-text-label font-bold">{task.progress ?? 0}%</td>
                                                                    <td className="px-4 py-3 text-right text-app-text-label font-semibold whitespace-nowrap">{task.deadline ? new Date(task.deadline).toLocaleDateString('en-US', { month: 'short', day: '2-digit', year: 'numeric' }) : '—'}</td>
                                                                </tr>
                                                            ))}
                                                            {(!dashboardData.tasks.due_this_week || dashboardData.tasks.due_this_week.length === 0) && (
                                                                <tr><td colSpan="4" className="px-4 py-6 text-center text-app-text-light italic">No tasks due this week</td></tr>
                                                            )}
                                                        </tbody>
                                                    </table>
                                                </div>
                                            </div>

                                            {/* In Progress + Recently Completed Table */}
                                            <div className="bg-[#f8f9fa] rounded-xl shadow border border-app-border p-6">
                                                <h3 className="text-[17px] font-bold text-[#f27a24] mb-4">In Progress & Recently Completed</h3>
                                                <div className="overflow-auto rounded-lg border border-app-border" style={{ minHeight: '150px', maxHeight: '320px' }}>
                                                    <table className="min-w-full text-sm">
                                                        <thead className="sticky top-0 z-10">
                                                            <tr className="bg-[#f27a24] text-white">
                                                                <th className="px-4 py-2.5 text-left font-bold text-xs w-12">#</th>
                                                                <th className="px-4 py-2.5 text-left font-bold text-xs">Task Description</th>
                                                                <th className="px-4 py-2.5 text-right font-bold text-xs w-24">Status</th>
                                                            </tr>
                                                        </thead>
                                                        <tbody className="divide-y divide-gray-100 bg-app-bg-card">
                                                            {(dashboardData.tasks.in_progress || []).map((task, idx) => (
                                                                <tr key={task.id} className="hover:bg-app-primary-light/50">
                                                                    <td className="px-4 py-3 text-app-text-label font-semibold">{idx + 1}</td>
                                                                    <td className="px-4 py-3 text-gray-800 font-medium">{task.name || task.description || 'Untitled'}</td>
                                                                    <td className="px-4 py-3 text-right"><span className="inline-block px-2 py-0.5 bg-app-primary-light text-app-primary-hover text-xs font-bold rounded">{task.progress ?? 0}%</span></td>
                                                                </tr>
                                                            ))}
                                                            {(dashboardData.tasks.recently_completed || []).map((task, idx) => (
                                                                <tr key={task.id} className="hover:bg-app-status-successBg/50">
                                                                    <td className="px-4 py-3 text-app-text-light font-semibold">{(dashboardData.tasks.in_progress?.length || 0) + idx + 1}</td>
                                                                    <td className="px-4 py-3 text-app-text-light font-medium line-through">{task.name || task.description || 'Untitled'}</td>
                                                                    <td className="px-4 py-3 text-right"><span className="inline-block px-2 py-0.5 bg-green-100 text-green-700 text-xs font-bold rounded">Done</span></td>
                                                                </tr>
                                                            ))}
                                                            {(!dashboardData.tasks.in_progress?.length && !dashboardData.tasks.recently_completed?.length) && (
                                                                <tr><td colSpan="3" className="px-4 py-6 text-center text-app-text-light italic">No tasks in progress or recently completed</td></tr>
                                                            )}
                                                        </tbody>
                                                    </table>
                                                </div>
                                            </div>
                                        </div>
                                    </div>
                                )}

                                {/* ── AI AGENTS SECTION ── */}
                                <div className="w-full mt-6 lg:col-start-1 min-w-0">
                                    <div className="flex items-center justify-between mb-6">
                                        <div className="flex items-center">
                                            <div className="p-2 mr-3 bg-app-primary-light rounded text-indigo-500">
                                                <Bot className="w-5 h-5" />
                                            </div>
                                            <h3 className="text-[15px] font-bold text-[#f27a24] uppercase tracking-wide">AI Agents</h3>
                                            <span className="ml-3 text-[10px] font-bold text-app-text-light uppercase tracking-wider bg-app-bg-muted px-2 py-0.5 rounded-full">
                                                {agents.filter(a => a.status === 'running').length} Running
                                            </span>
                                        </div>
                                        <div className="flex items-center gap-2">
                                            <span className="text-[10px] font-bold text-app-text-light uppercase tracking-wider bg-orange-50 text-orange-600 px-2.5 py-1 rounded-full">
                                                {taskList.filter(t => (t.taskStatus || '').toLowerCase() !== 'completed').length} Available Tasks
                                            </span>
                                            <button
                                                onClick={handleRunAll}
                                                disabled={runningAll || agents.filter(a => a.status === 'idle' && a.id !== 'agent_03').length === 0}
                                                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-bold uppercase tracking-wide transition-all duration-200 ${runningAll || agents.filter(a => a.status === 'idle' && a.id !== 'agent_03').length === 0
                                                    ? 'bg-app-bg-hover text-app-text-light cursor-not-allowed'
                                                    : 'bg-gradient-to-r from-orange-500 to-amber-500 text-white shadow-md hover:shadow-lg hover:scale-105'
                                                    }`}
                                                title="Run all idle agents simultaneously"
                                            >
                                                {runningAll ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Play className="w-3.5 h-3.5" />}
                                                {runningAll ? 'Starting...' : 'Run All'}
                                            </button>
                                            <button
                                                onClick={handleGenerateTasks}
                                                disabled={isGeneratingTasks || !selectedProjectKey}
                                                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-bold uppercase tracking-wide transition-all duration-200 ${isGeneratingTasks || !selectedProjectKey
                                                    ? 'bg-app-bg-hover text-app-text-light cursor-not-allowed'
                                                    : 'bg-gradient-to-r from-blue-500 to-indigo-600 text-white shadow-md hover:shadow-lg hover:scale-105'
                                                    }`}
                                                title="Generate tasks from selected project"
                                            >
                                                {isGeneratingTasks ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Play className="w-3.5 h-3.5" />}
                                                {isGeneratingTasks ? 'Mapping...' : 'Create Tasks'}
                                            </button>
                                            <button
                                                onClick={() => handleAddAgent()}
                                                className="flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-xs font-bold text-app-primary bg-app-primary-light hover:bg-indigo-100 transition-colors"
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

                                    <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
                                        {agents.map(agent => renderAgentCard(agent))}
                                    </div>
                                </div>
                                {/* Closes CSS grid layout */}
                            </div>
                        </>
                    )}
                </div>

            )
            }
            {showLogModal && (() => {
                const agent = agents.find(a => a.id === showLogModal);
                if (!agent) return null;
                const logs = agent.output_log || [];
                const result = agent.last_result;
                return (
                    <div className="fixed inset-0 bg-app-text-main/60 backdrop-blur-sm flex items-center justify-center p-4 z-[100] animate-in fade-in duration-200">
                        <div className="bg-app-text-main text-gray-100 rounded-2xl shadow-2xl border border-gray-700 w-full max-w-3xl max-h-[80vh] flex flex-col overflow-hidden animate-in zoom-in-95 duration-200">
                            <div className="px-6 py-4 border-b border-gray-700 flex items-center justify-between bg-app-text-label">
                                <div className="flex items-center gap-3">
                                    <Terminal className="w-5 h-5 text-green-400" />
                                    <h3 className="font-bold text-white text-sm">{agent.name} — Execution Log</h3>
                                </div>
                                <button onClick={() => setShowLogModal(null)} className="text-app-text-light hover:text-white p-1 rounded hover:bg-gray-700 transition-colors">
                                    <X className="w-5 h-5" />
                                </button>
                            </div>
                            <div className="flex-1 overflow-y-auto p-4 font-mono text-xs leading-relaxed space-y-0.5">
                                {logs.length === 0 ? (
                                    <p className="text-app-text-muted text-center py-8">No logs yet. Run the agent to see output here.</p>
                                ) : logs.map((log, idx) => (
                                    <div key={idx} className={`flex items-start gap-2 ${log.type === 'error' ? 'text-red-400' : log.type === 'output' ? 'text-green-300' : 'text-blue-300'}`}>
                                        <span className="text-app-text-label flex-shrink-0 select-none">[{log.type}]</span>
                                        <span className="break-all">{log.message}</span>
                                    </div>
                                ))}
                            </div>
                            {result?.generated_code && (
                                <div className="border-t border-gray-700">
                                    <details className="group" open>
                                        <summary className="px-4 py-2 text-xs font-bold text-emerald-400 cursor-pointer hover:text-emerald-300 select-none flex items-center gap-2">
                                            <span className="w-2 h-2 bg-emerald-400 rounded-full"></span>
                                            View Project Structure ({(result.generated_code.match(/FILE:/g) || []).length} files created in Docker)
                                        </summary>
                                        <pre className="px-4 py-3 overflow-x-auto text-[10px] text-green-200 bg-gray-950 max-h-96 overflow-y-auto whitespace-pre-wrap">
                                            {result.generated_code}
                                        </pre>
                                    </details>
                                </div>
                            )}
                            {result?.builder_scripts && (
                                <div className="border-t border-gray-700">
                                    <details className="group">
                                        <summary className="px-4 py-2 text-xs font-bold text-blue-400 cursor-pointer hover:text-blue-300 select-none flex items-center gap-2">
                                            <span className="w-2 h-2 bg-blue-400 rounded-full"></span>
                                            View Builder Scripts ({result.builder_scripts.split('\n').length} lines of AI-generated code)
                                        </summary>
                                        <pre className="px-4 py-3 overflow-x-auto text-[10px] text-app-primary-ring bg-gray-950 max-h-60 overflow-y-auto whitespace-pre-wrap">
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
                                <div className="px-6 py-4 border-b border-app-border-light flex items-center justify-between bg-gradient-to-r from-gray-50/80 to-white">
                                    <div className="flex items-center gap-3">
                                        <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center shadow-lg shadow-indigo-200">
                                            <ListTodo className="w-4 h-4 text-white" />
                                        </div>
                                        <div>
                                            <h3 className="text-sm font-bold text-app-text-main">Generated Tasks</h3>
                                            <p className="text-[10px] text-app-text-light uppercase tracking-wider font-semibold">
                                                {taskList.length} of {totalTaskCount} task{totalTaskCount !== 1 ? 's' : ''} from AI Auto-Generator
                                            </p>
                                        </div>
                                    </div>
                                    <button onClick={() => fetchTasks(false, 1, false)} disabled={isLoadingTasks} className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold text-app-text-muted bg-app-bg-page border border-app-border rounded-lg hover:bg-app-bg-muted hover:text-app-text-label transition-all disabled:opacity-50">
                                        <RefreshCw className={`w-3 h-3 ${isLoadingTasks ? 'animate-spin' : ''}`} /> Refresh
                                    </button>
                                </div>


                                <div className="hidden md:block bg-app-bg-page/50 border-b border-app-border-light px-6 py-2.5">
                                    <div style={{ display: 'grid', gridTemplateColumns: '40px 1fr 140px 90px 80px 120px 60px 130px', gap: '8px', alignItems: 'center' }}>
                                        <div className="text-[10px] font-bold text-app-text-light uppercase tracking-wider">#</div>
                                        <div className="text-[10px] font-bold text-app-text-light uppercase tracking-wider">Task Information</div>
                                        <div className="text-[10px] font-bold text-app-text-light uppercase tracking-wider text-center">Completion</div>
                                        <div className="text-[10px] font-bold text-app-text-light uppercase tracking-wider">Status</div>
                                        <div className="text-[10px] font-bold text-app-text-light uppercase tracking-wider">Priority</div>
                                        <div className="text-[10px] font-bold text-app-text-light uppercase tracking-wider">Assignees</div>
                                        <div className="text-[10px] font-bold text-app-text-light uppercase tracking-wider">Wallet</div>
                                        <div className="text-[10px] font-bold text-app-text-light uppercase tracking-wider">Deadline</div>
                                    </div>
                                </div>

                                <div className="divide-y divide-gray-50">
                                    {isLoadingTasks && taskList.length === 0 && (
                                        <div className="p-6 space-y-4">
                                            {[0, 1, 2, 3].map((row) => (
                                                <div key={row} className="grid grid-cols-1 md:grid-cols-[40px_1fr_140px_90px_80px_120px_60px_130px] gap-2 items-center">
                                                    <Skeleton height={10} width={18} />
                                                    <div>
                                                        <Skeleton height={13} width="52%" />
                                                        <div className="mt-1">
                                                            <Skeleton height={10} width="70%" />
                                                        </div>
                                                    </div>
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
                                            <p className="text-xs text-app-text-light max-w-xs">Select a project and click "Create Tasks" above to get started.</p>
                                        </div>
                                    )}
                                    {!isLoadingTasks && taskList.length > 0 && (
                                        <div className="overflow-y-auto" style={{ maxHeight: '600px' }}>
                                            {taskList.map((task, index) => {
                                                const priorityStyles = { high: 'bg-app-status-errorBg text-red-700 border-red-200', medium: 'bg-app-status-warningBg text-amber-700 border-amber-200', low: 'bg-app-status-successBg text-green-700 border-green-200' };
                                                const typeStyles = { EPIC: 'bg-purple-100 text-purple-700', FEATURE: 'bg-app-primary-light text-app-primary-hover', STORY: 'bg-cyan-100 text-cyan-700', TASK: 'bg-app-bg-muted text-app-text-label', BUG: 'bg-red-100 text-red-700' };
                                                const statusStyles = { 'On Going': 'bg-app-primary-light text-app-primary-hover', 'Completed': 'bg-app-status-successBg text-green-700', 'To Do': 'bg-app-bg-page text-app-text-label', 'In Review': 'bg-app-status-warningBg text-amber-700', 'Blocked': 'bg-app-status-errorBg text-red-700' };
                                                const priority = (task.priority || 'medium').toLowerCase();
                                                const taskType = (task.task_type || 'TASK').toUpperCase();
                                                const progress = task.task_progress || 0;
                                                const progressColor = progress >= 80 ? 'bg-green-500' : progress >= 40 ? 'bg-blue-500' : 'bg-amber-500';

                                                return (
                                                    <div key={task.id || index} className="px-6 py-3 hover:bg-app-bg-page/70 transition-colors group">
                                                        <div className="hidden md:grid" style={{ gridTemplateColumns: '40px 1fr 140px 90px 80px 120px 60px 130px', gap: '8px', alignItems: 'center' }}>
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
                                                className="inline-flex items-center gap-2 px-6 py-2.5 text-sm font-semibold text-app-primary bg-app-primary-light border border-indigo-200 rounded-xl hover:bg-indigo-100 hover:shadow-sm transition-all disabled:opacity-50 disabled:cursor-not-allowed"
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
                )}

            {/* Add Project Modal */}
            {
                showModal && (
                    <div className="fixed inset-0 bg-app-text-main/50 backdrop-blur-sm flex items-center justify-center p-4 z-[100] animate-in fade-in duration-200">
                        <div className="bg-app-bg-card rounded-2xl shadow-xl border border-app-border-light w-full max-w-md overflow-hidden animate-in zoom-in-95 duration-200">
                            <div className="px-6 py-5 border-b border-app-border-light flex items-center justify-between bg-gradient-to-r from-gray-50 to-white">
                                <h3 className="font-bold text-app-text-main text-lg flex items-center gap-2">
                                    <PlusCircle className="w-5 h-5 text-blue-500" /> Create Project
                                </h3>
                                <button type="button" onClick={() => setShowModal(false)} className="text-app-text-light hover:text-app-text-label hover:bg-app-bg-muted p-1.5 rounded-full transition-colors">
                                    <X className="w-5 h-5" />
                                </button>
                            </div>
                            <div className="p-6">
                                <p className="text-sm text-app-text-muted mb-4 font-medium">Step 1 of Governance Track: Give your project a descriptive name to get started.</p>
                                <label className="block text-[11px] font-bold text-app-text-muted mb-2 uppercase tracking-widest">Project Name <span className="text-red-400">*</span></label>
                                <input type="text" value={newProjectName} onChange={(e) => setNewProjectName(e.target.value)} autoFocus onKeyDown={(e) => e.key === 'Enter' && handleCreateProject()} placeholder="e.g. Customer Analytics Platform" className="w-full px-4 py-3 border-2 border-app-border rounded-xl focus:ring-4 focus:ring-blue-100 focus:border-blue-400 text-sm bg-app-bg-page/50 text-app-text-main transition-all duration-200 placeholder:text-app-border font-medium mb-6" />
                                <div className="flex items-center gap-3">
                                    <button type="button" onClick={() => setShowModal(false)} className="flex-1 py-3 px-4 font-bold text-app-text-label bg-app-bg-page hover:bg-app-bg-muted border border-app-border rounded-xl transition-colors">Cancel</button>
                                    <button type="button" onClick={handleCreateProject} disabled={!newProjectName.trim()} className="flex-1 py-3 px-4 font-bold text-white bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-700 hover:to-indigo-700 rounded-xl transition-colors shadow-lg shadow-blue-500/30 hover:shadow-blue-500/50 disabled:opacity-50 disabled:cursor-not-allowed flex justify-center items-center gap-2 group">
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
                    <div className="fixed inset-0 bg-app-text-main/50 backdrop-blur-sm flex items-center justify-center p-4 z-[100] animate-in fade-in duration-200">
                        <div className="bg-app-bg-card rounded-2xl shadow-xl border border-app-border-light w-full max-w-md overflow-hidden animate-in zoom-in-95 duration-200">
                            <div className="px-6 py-5 border-b border-app-border-light flex items-center justify-between bg-gradient-to-r from-gray-50 to-white">
                                <h3 className="font-bold text-app-text-main text-lg flex items-center gap-2">
                                    <Pencil className="w-5 h-5 text-indigo-500" /> Edit Agent Settings
                                </h3>
                                <button type="button" onClick={cancelEditingAgentName} className="text-app-text-light hover:text-app-text-label hover:bg-app-bg-muted p-1.5 rounded-full transition-colors">
                                    <X className="w-5 h-5" />
                                </button>
                            </div>
                            <div className="p-6">
                                <p className="text-sm text-app-text-muted mb-4 font-medium">Update agent name, Git repository URL, and Personal Access Token.</p>

                                <label className="block text-[11px] font-bold text-app-text-muted mb-2 uppercase tracking-widest">Agent Name <span className="text-red-400">*</span></label>
                                <input
                                    type="text"
                                    value={editingAgentName}
                                    onChange={(e) => setEditingAgentName(e.target.value)}
                                    className="w-full px-4 py-3 border-2 border-app-border rounded-xl focus:ring-4 focus:ring-indigo-100 focus:border-indigo-400 text-sm bg-app-bg-page/50 text-app-text-main transition-all duration-200 placeholder:text-app-border font-medium mb-4"
                                />

                                <label className="block text-[11px] font-bold text-app-text-muted mb-2 uppercase tracking-widest">Git Repository URL</label>
                                <input
                                    type="text"
                                    value={editingAgentRepoUrl}
                                    onChange={(e) => setEditingAgentRepoUrl(e.target.value)}
                                    placeholder="https://github.com/org/repo.git"
                                    className="w-full px-4 py-3 border-2 border-app-border rounded-xl focus:ring-4 focus:ring-indigo-100 focus:border-indigo-400 text-sm bg-app-bg-page/50 text-app-text-main transition-all duration-200 placeholder:text-app-border font-medium mb-4"
                                />

                                <label className="block text-[11px] font-bold text-app-text-muted mb-2 uppercase tracking-widest">Personal Access Token</label>
                                <input
                                    type="password"
                                    value={editingAgentToken}
                                    onChange={(e) => setEditingAgentToken(e.target.value)}
                                    placeholder="Leave blank to keep existing PAT"
                                    className="w-full px-4 py-3 border-2 border-app-border rounded-xl focus:ring-4 focus:ring-indigo-100 focus:border-indigo-400 text-sm bg-app-bg-page/50 text-app-text-main transition-all duration-200 placeholder:text-app-border font-medium"
                                />
                                <p className="text-xs text-app-text-light mt-2 mb-6">Leave token blank if you do not want to change it.</p>

                                <div className="flex items-center gap-3">
                                    <button type="button" onClick={cancelEditingAgentName} disabled={isSavingAgentName} className="flex-1 py-3 px-4 font-bold text-app-text-label bg-app-bg-page hover:bg-app-bg-muted border border-app-border rounded-xl transition-colors disabled:opacity-50">Cancel</button>
                                    <button type="button" onClick={saveAgentName} disabled={isSavingAgentName || !editingAgentName.trim()} className="flex-1 py-3 px-4 font-bold text-white bg-gradient-to-r from-indigo-600 to-blue-600 hover:from-indigo-700 hover:to-blue-700 rounded-xl transition-colors shadow-lg shadow-indigo-500/30 disabled:opacity-50 disabled:cursor-not-allowed flex justify-center items-center gap-2">
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
                    <div className="fixed inset-0 bg-app-text-main/50 backdrop-blur-sm flex items-center justify-center p-4 z-[100] animate-in fade-in duration-200">
                        <div className="bg-app-bg-card rounded-2xl shadow-xl border border-app-border-light w-full max-w-md overflow-hidden animate-in zoom-in-95 duration-200">
                            <div className="px-6 py-5 border-b border-app-border-light flex items-center justify-between bg-gradient-to-r from-gray-50 to-white">
                                <h3 className="font-bold text-app-text-main text-lg flex items-center gap-2">
                                    <PlusCircle className="w-5 h-5 text-indigo-500" /> Add New Agent
                                </h3>
                                <button type="button" onClick={() => setShowAddAgentModal(false)} className="text-app-text-light hover:text-app-text-label hover:bg-app-bg-muted p-1.5 rounded-full transition-colors">
                                    <X className="w-5 h-5" />
                                </button>
                            </div>
                            <div className="p-6">
                                <label className="block text-[11px] font-bold text-app-text-muted mb-2 uppercase tracking-widest">Agent Name (optional)</label>
                                <input type="text" value={newAgentConfig.name} onChange={(e) => setNewAgentConfig({ ...newAgentConfig, name: e.target.value })} placeholder="e.g. Code Reviewer" className="w-full px-4 py-3 border-2 border-app-border rounded-xl focus:ring-4 focus:ring-indigo-100 focus:border-indigo-400 text-sm bg-app-bg-page/50 text-app-text-main transition-all duration-200 placeholder:text-app-border font-medium mb-4" />

                                <label className="block text-[11px] font-bold text-app-text-muted mb-2 uppercase tracking-widest">Git Repository URL</label>
                                <input type="text" value={newAgentConfig.git_repo_url} onChange={(e) => setNewAgentConfig({ ...newAgentConfig, git_repo_url: e.target.value })} placeholder="https://github.com/org/repo.git" className="w-full px-4 py-3 border-2 border-app-border rounded-xl focus:ring-4 focus:ring-indigo-100 focus:border-indigo-400 text-sm bg-app-bg-page/50 text-app-text-main transition-all duration-200 placeholder:text-app-border font-medium mb-4" />

                                <label className="block text-[11px] font-bold text-app-text-muted mb-2 uppercase tracking-widest">Personal Access Token <span className="text-red-400">*</span></label>
                                <input type="password" value={newAgentConfig.git_token} onChange={(e) => setNewAgentConfig({ ...newAgentConfig, git_token: e.target.value })} placeholder="ghp_..." className="w-full px-4 py-3 border-2 border-app-border rounded-xl focus:ring-4 focus:ring-indigo-100 focus:border-indigo-400 text-sm bg-app-bg-page/50 text-app-text-main transition-all duration-200 placeholder:text-app-border font-medium mb-6" />

                                <div className="flex items-center gap-3">
                                    <button type="button" onClick={() => setShowAddAgentModal(false)} className="flex-1 py-3 px-4 font-bold text-app-text-label bg-app-bg-page hover:bg-app-bg-muted border border-app-border rounded-xl transition-colors">Cancel</button>
                                    <button type="button" onClick={submitAddAgent} disabled={!newAgentConfig.git_token.trim()} className="flex-1 py-3 px-4 font-bold text-white bg-gradient-to-r from-indigo-600 to-blue-600 hover:from-indigo-700 hover:to-blue-700 rounded-xl transition-colors shadow-lg shadow-indigo-500/30">
                                        Add Agent
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
                    <div className="fixed inset-0 bg-app-text-main/50 backdrop-blur-sm flex items-center justify-center p-4 z-[100] animate-in fade-in duration-200">
                        <div className="bg-app-bg-card rounded-2xl shadow-xl border border-app-border-light w-full max-w-lg max-h-[90vh] flex flex-col overflow-hidden animate-in zoom-in-95 duration-200">
                            <div className="px-6 py-5 border-b border-app-border-light flex items-center justify-between bg-gradient-to-r from-gray-50 to-white">
                                <h3 className="font-bold text-app-text-main text-lg flex items-center gap-2">
                                    <Bot className="w-5 h-5 text-indigo-500" /> {gitModalAgent.id === '__run_all_setup__' ? 'Configure Agents' : 'Git Configuration'}
                                </h3>
                                <button type="button" onClick={() => setGitModalAgent(null)} className="text-app-text-light hover:text-app-text-label hover:bg-app-bg-muted p-1.5 rounded-full transition-colors">
                                    <X className="w-5 h-5" />
                                </button>
                            </div>
                            <div className="p-6 overflow-y-auto">
                                {gitModalAgent.id === '__run_all_setup__' ? (
                                    <>
                                        <p className="text-sm text-app-text-muted mb-6 font-medium">To run simultaneously, the following agents require Git configuration.</p>
                                        <div className="space-y-6">
                                            {gitModalAgent.missingConfig.map(agent => (
                                                <div key={agent.id} className="p-4 border border-indigo-100 bg-app-primary-light/30 rounded-xl">
                                                    <h4 className="text-sm font-bold text-indigo-900 mb-3">{agent.name || agent.id}</h4>

                                                    <label className="block text-[10px] font-bold text-app-text-muted mb-1.5 uppercase tracking-widest">Git Repository URL <span className="text-red-400">*</span></label>
                                                    <input type="text" value={agentsGitConfig[agent.id]?.git_repo_url || ''} onChange={(e) => setAgentsGitConfig({ ...agentsGitConfig, [agent.id]: { ...agentsGitConfig[agent.id], git_repo_url: e.target.value } })} placeholder="https://github.com/org/repo.git" className="w-full px-3 py-2 border border-app-border rounded-lg focus:ring-2 focus:ring-indigo-100 focus:border-indigo-400 text-xs bg-app-bg-card text-app-text-main mb-3" />

                                                    <label className="block text-[10px] font-bold text-app-text-muted mb-1.5 uppercase tracking-widest">Personal Access Token <span className="text-red-400">*</span></label>
                                                    <input type="password" value={agentsGitConfig[agent.id]?.git_token || ''} onChange={(e) => setAgentsGitConfig({ ...agentsGitConfig, [agent.id]: { ...agentsGitConfig[agent.id], git_token: e.target.value } })} placeholder="ghp_..." className="w-full px-3 py-2 border border-app-border rounded-lg focus:ring-2 focus:ring-indigo-100 focus:border-indigo-400 text-xs bg-app-bg-card text-app-text-main" />
                                                </div>
                                            ))}
                                        </div>
                                    </>
                                ) : (
                                    <>
                                        <p className="text-sm text-app-text-muted mb-4 font-medium">To run <b>{gitModalAgent.name}</b>, please provide a Git repository where the agent can push its work.</p>

                                        <label className="block text-[11px] font-bold text-app-text-muted mb-2 uppercase tracking-widest">Git Repository URL <span className="text-red-400">*</span></label>
                                        <input type="text" value={gitRepoUrl} onChange={(e) => setGitRepoUrl(e.target.value)} placeholder="https://github.com/org/repo.git" className="w-full px-4 py-3 border-2 border-app-border rounded-xl focus:ring-4 focus:ring-indigo-100 focus:border-indigo-400 text-sm bg-app-bg-page/50 text-app-text-main transition-all duration-200 placeholder:text-app-border font-medium mb-4" />

                                        <label className="block text-[11px] font-bold text-app-text-muted mb-2 uppercase tracking-widest">Personal Access Token <span className="text-red-400">*</span></label>
                                        <input type="password" value={gitToken} onChange={(e) => setGitToken(e.target.value)} placeholder="ghp_..." className="w-full px-4 py-3 border-2 border-app-border rounded-xl focus:ring-4 focus:ring-indigo-100 focus:border-indigo-400 text-sm bg-app-bg-page/50 text-app-text-main transition-all duration-200 placeholder:text-app-border font-medium mb-6" />
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
                                }} disabled={gitModalAgent.id === '__run_all_setup__' ? gitModalAgent.missingConfig.some(a => !agentsGitConfig[a.id]?.git_repo_url?.trim() || !agentsGitConfig[a.id]?.git_token?.trim()) : (!gitRepoUrl.trim() || !gitToken.trim())} className="flex-1 py-3 px-4 font-bold text-white bg-gradient-to-r from-indigo-600 to-blue-600 hover:from-indigo-700 hover:to-blue-700 rounded-xl transition-colors shadow-lg shadow-indigo-500/30 hover:shadow-indigo-500/50 disabled:opacity-50 disabled:cursor-not-allowed flex justify-center items-center gap-2 group">
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
