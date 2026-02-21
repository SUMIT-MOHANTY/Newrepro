import React, { useState, useEffect, useCallback } from 'react';
import { Flag, Activity, CheckCircle, Clock, Menu, PlusCircle, X, ArrowRight, Bot, Shield, Cpu, Play, RefreshCw, Eye, ListTodo, AlertCircle, ChevronRight, Users, Calendar, Wallet, Tag, AlertTriangle, CheckCircle2, Loader2, Terminal } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import ProjectDropdown from './ProjectDropdown';
import { API_ENDPOINTS } from '../config';

export default function StatusDashboard({ projects = [] }) {
    const navigate = useNavigate();
    const [showModal, setShowModal] = useState(false);
    const [newProjectName, setNewProjectName] = useState('');
    const [selectedProjectKey, setSelectedProjectKey] = useState(projects[0]?.key || null);

    // AI Generation States
    const [isGeneratingTasks, setIsGeneratingTasks] = useState(false);
    const [generatedTasksCount, setGeneratedTasksCount] = useState(0);
    const [generationError, setGenerationError] = useState(null);

    // Task List States
    const [taskList, setTaskList] = useState([]);
    const [isLoadingTasks, setIsLoadingTasks] = useState(false);
    const [taskListError, setTaskListError] = useState(null);

    // Project Info from external API
    const [projectInfo, setProjectInfo] = useState(null);

    // Fetch tasks from the external API
    const fetchTasks = useCallback(async () => {
        setIsLoadingTasks(true);
        setTaskListError(null);
        try {
            const token = localStorage.getItem('token');
            const { API_ENDPOINTS } = await import('../config.js');
            const res = await fetch(API_ENDPOINTS.AGENT_TASKS, {
                headers: { 'Authorization': `Bearer ${token}` }
            });
            if (res.ok) {
                const data = await res.json();
                // Handle both array response and object with results/count
                if (Array.isArray(data)) {
                    setTaskList(data);
                    setGeneratedTasksCount(data.length);
                } else if (data && Array.isArray(data.results)) {
                    setTaskList(data.results);
                    setGeneratedTasksCount(data.count || data.results.length);
                } else if (data && typeof data.count === 'number') {
                    setGeneratedTasksCount(data.count);
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
        }
    }, []);

    // Fetch project info from external API
    const fetchProjectInfo = useCallback(async () => {
        try {
            const token = localStorage.getItem('token');
            const { API_ENDPOINTS } = await import('../config.js');
            const res = await fetch(API_ENDPOINTS.AGENT_PROJECT_INFO, {
                headers: { 'Authorization': `Bearer ${token}` }
            });
            if (res.ok) {
                const data = await res.json();
                setProjectInfo(data);
            }
        } catch (e) {
            console.error("Failed to load project info:", e);
        }
    }, []);

    useEffect(() => {
        fetchTasks();
        fetchProjectInfo();
    }, [fetchTasks, fetchProjectInfo]);

    // ── Agent State ──────────────────────────────────────────────────
    const [agents, setAgents] = useState([]);
    const [pendingTasks, setPendingTasks] = useState([]);
    const [completedTasks, setCompletedTasks] = useState([]);
    const [loadingAgents, setLoadingAgents] = useState(true);
    const [runningAgent, setRunningAgent] = useState(null); // agent_id currently being triggered
    const [showLogModal, setShowLogModal] = useState(null); // agent_id to show log for

    const token = localStorage.getItem('token');

    // ── Fetch agents & tasks ─────────────────────────────────────────
    const fetchAgents = useCallback(async () => {
        try {
            const res = await fetch(API_ENDPOINTS.AGENTS, {
                headers: { Authorization: `Bearer ${token}` },
            });
            if (res.ok) {
                const data = await res.json();
                setAgents(data.agents || []);
            }
        } catch (e) {
            console.error('Failed to fetch agents', e);
        }
    }, [token]);

    const fetchPendingTasks = useCallback(async () => {
        try {
            const res = await fetch(API_ENDPOINTS.AGENTS_TASKS, {
                headers: { Authorization: `Bearer ${token}` },
            });
            if (res.ok) {
                const data = await res.json();
                setPendingTasks(data.pending_tasks || []);
                setCompletedTasks(data.completed_tasks || []);
            }
        } catch (e) {
            console.error('Failed to fetch tasks', e);
        }
    }, [token]);

    useEffect(() => {
        const load = async () => {
            setLoadingAgents(true);
            await Promise.all([fetchAgents(), fetchPendingTasks()]);
            setLoadingAgents(false);
        };
        load();
    }, [fetchAgents, fetchTasks]);

    // Poll for updates while any agent is running
    useEffect(() => {
        const hasRunning = agents.some(a => a.status === 'running');
        if (!hasRunning) return;

        const interval = setInterval(() => {
            fetchAgents();
            fetchPendingTasks();
        }, 3000);
        return () => clearInterval(interval);
    }, [agents, fetchAgents, fetchTasks]);

    // ── Run Agent ────────────────────────────────────────────────────
    const handleRunAgent = async (agentId) => {
        if (runningAgent) return; // prevent double-clicks
        setRunningAgent(agentId);

        try {
            const res = await fetch(API_ENDPOINTS.AGENT_RUN(agentId), {
                method: 'POST',
                headers: { Authorization: `Bearer ${token}` },
            });
            const data = await res.json();
            if (!res.ok) {
                alert(data.detail || 'Failed to run agent');
            }
        } catch (e) {
            alert('Network error. Is the backend running?');
        } finally {
            setRunningAgent(null);
            fetchAgents();
            fetchPendingTasks();
        }
    };

    // ── Reset Agent ──────────────────────────────────────────────────
    const handleResetAgent = async (agentId) => {
        try {
            await fetch(API_ENDPOINTS.AGENT_RESET(agentId), {
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

    const handleGenerateTasks = async () => {
        if (!selectedProjectKey) return;
        setIsGeneratingTasks(true);
        setGenerationError(null);
        setGeneratedTasksCount(0);

        try {
            const token = localStorage.getItem('token');
            const { API_ENDPOINTS } = await import('../config.js');
            const response = await fetch(API_ENDPOINTS.AGENT_AUTO_GENERATE, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${token}`
                },
                body: JSON.stringify({
                    project_token: selectedProjectKey
                })
            });

            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.detail || 'Failed to generate tasks');
            }

            const data = await response.json();
            setGeneratedTasksCount(data.tasks_created || 0);
            // Refresh the task list and project info to show newly created tasks
            await fetchTasks();
            await fetchProjectInfo();
        } catch (err) {
            setGenerationError(err.message);
        } finally {
            setIsGeneratingTasks(false);
        }

    // ── Agent Card Config ────────────────────────────────────────────
    const agentConfig = {
        agent_01: {
            icon: CheckCircle,
            gradient: 'from-emerald-400 to-green-500',
            iconBg: 'from-emerald-400 to-green-600',
            shadow: 'shadow-emerald-200',
            accentColor: 'emerald',
            statLabels: ['Checks', 'Coverage', 'Avg Time'],
            statKeys: ['checks', 'coverage', 'avg_time'],
        },
        agent_02: {
            icon: Shield,
            gradient: 'from-amber-400 to-orange-500',
            iconBg: 'from-amber-400 to-orange-600',
            shadow: 'shadow-orange-200',
            accentColor: 'amber',
            statLabels: ['Risks', 'Critical', 'Avg Time'],
            statKeys: ['risks', 'critical', 'avg_time'],
        },
        agent_03: {
            icon: Cpu,
            gradient: 'from-blue-400 to-indigo-500',
            iconBg: 'from-blue-400 to-indigo-600',
            shadow: 'shadow-blue-200',
            accentColor: 'blue',
            statLabels: ['Sprints', 'Resources', 'Avg Time'],
            statKeys: ['sprints', 'resources', 'avg_time'],
        },
    };

    const statusColors = {
        idle: { dot: 'bg-gray-400', label: 'text-gray-500', text: 'IDLE' },
        running: { dot: 'bg-amber-500', label: 'text-amber-600', text: 'RUNNING', ping: true },
        completed: { dot: 'bg-emerald-500', label: 'text-emerald-600', text: 'DONE', ping: true },
        error: { dot: 'bg-red-500', label: 'text-red-600', text: 'ERROR' },
    };

    // ── Render Agent Card ────────────────────────────────────────────
    const renderAgentCard = (agent) => {
        if (agent.id === 'agent_03') {
            return (
                <div key={agent.id} className="bg-white rounded-xl shadow border border-gray-100 p-5 flex flex-col relative overflow-hidden group hover:shadow-lg transition-shadow">
                    <div className="absolute top-0 left-0 right-0 h-1 bg-gradient-to-r from-blue-400 to-indigo-500"></div>
                    <div className="flex items-start justify-between mb-4">
                        <div className="flex items-center gap-3">
                            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-blue-400 to-indigo-600 flex items-center justify-center shadow-lg shadow-blue-200">
                                <Cpu className="w-5 h-5 text-white" />
                            </div>
                            <div>
                                <h4 className="text-sm font-bold text-gray-900">Task Auto-Generator</h4>
                                <p className="text-[10px] text-gray-400 uppercase tracking-wider font-semibold">Agent 03</p>
                            </div>
                        </div>
                        <div className="flex items-center gap-1.5">
                            <span className="relative flex h-2.5 w-2.5">
                                <span className={`animate-ping absolute inline-flex h-full w-full rounded-full ${isGeneratingTasks ? 'bg-blue-400 opacity-75' : 'hidden'}`}></span>
                                <span className={`relative inline-flex rounded-full h-2.5 w-2.5 ${isGeneratingTasks ? 'bg-blue-500' : 'bg-gray-400'}`}></span>
                            </span>
                            <span className={`text-[10px] font-bold ${isGeneratingTasks ? 'text-blue-600' : 'text-gray-500'}`}>
                                {isGeneratingTasks ? 'RUNNING' : 'IDLE'}
                            </span>
                        </div>
                    </div>
                    <p className="text-xs text-gray-500 mb-4 leading-relaxed">
                        Analyzes the BRD Report to automatically generate external Projects, Tasks, Epics, Features, and User Stories via AI.
                    </p>
                    <div className="flex items-center gap-4 mb-4 py-2 px-3 bg-gray-50 rounded-lg">
                        <div className="text-center">
                            <p className="text-lg font-bold text-gray-800">{generatedTasksCount || '-'}</p>
                            <p className="text-[9px] text-gray-400 uppercase font-semibold">Generated</p>
                        </div>
                        <div className="w-px h-8 bg-gray-200"></div>
                        <div className="text-center">
                            <p className="text-lg font-bold text-blue-600">{projectInfo?.project?.project_wallet ?? '-'}</p>
                            <p className="text-[9px] text-gray-400 uppercase font-semibold">Budget</p>
                        </div>
                        <div className="w-px h-8 bg-gray-200"></div>
                        <div className="text-center">
                            <p className="text-sm font-bold text-gray-800">{projectInfo?.project?.deadline || '-'}</p>
                            <p className="text-[9px] text-gray-400 uppercase font-semibold">Deadline</p>
                        </div>
                    </div>
                    {isGeneratingTasks ? (
                        <div className="mb-4">
                            <div className="flex justify-between text-[10px] text-gray-400 mb-1">
                                <span>Building tasks from context...</span>
                                <span className="font-bold text-blue-600">Working</span>
                            </div>
                            <div className="w-full bg-gray-100 rounded-full h-1.5 overflow-hidden">
                                <div className="bg-gradient-to-r from-blue-400 to-indigo-500 h-full w-full animate-pulse rounded-full"></div>
                            </div>
                        </div>
                    ) : (
                        <div className="flex items-center justify-between text-[10px] text-gray-400 mb-4">
                            <span className="flex items-center gap-1">
                                <Clock className="w-3 h-3" />
                                Last run: {generatedTasksCount > 0 ? 'Just now' : 'Awaiting trigger'}
                            </span>
                            <span className="font-semibold text-gray-400">
                                {generationError ? <span className="text-red-500 truncate max-w-[100px]" title={generationError}>Failed</span> : generatedTasksCount > 0 ? <span className="text-green-500">Success</span> : 'Ready'}
                            </span>
                        </div>
                    )}
                    <div className="flex gap-2 mt-auto">
                        <button
                            onClick={handleGenerateTasks}
                            disabled={isGeneratingTasks || !selectedProjectKey}
                            className="flex-1 inline-flex items-center justify-center gap-1.5 px-3 py-2 text-xs font-bold text-white bg-gradient-to-r from-blue-500 to-indigo-600 rounded-lg shadow-sm hover:shadow-md hover:-translate-y-0.5 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
                        >
                            {isGeneratingTasks ? (
                                <><RefreshCw className="w-3 h-3 animate-spin" /> MAPPING</>
                            ) : (
                                <><Play className="w-3 h-3" /> Create Tasks</>
                            )}
                        </button>
                    </div>
                </div>
            );
        }

        const config = agentConfig[agent.id] || agentConfig.agent_01;
        const Icon = config.icon;
        const statusStyle = statusColors[agent.status] || statusColors.idle;
        const isRunning = agent.status === 'running';
        const isCompleted = agent.status === 'completed';
        const isError = agent.status === 'error';
        const canRun = (agent.status === 'idle' || agent.status === 'completed' || agent.status === 'error') && pendingTasks.length > 0;

        return (
            <div key={agent.id} className="bg-white rounded-xl shadow border border-gray-100 p-5 flex flex-col relative overflow-hidden group hover:shadow-lg transition-shadow">
                {/* Gradient accent bar */}
                <div className={`absolute top-0 left-0 right-0 h-1 bg-gradient-to-r ${config.gradient}`}></div>

                {/* Header */}
                <div className="flex items-start justify-between mb-4">
                    <div className="flex items-center gap-3">
                        <div className={`w-10 h-10 rounded-xl bg-gradient-to-br ${config.iconBg} flex items-center justify-center shadow-lg ${config.shadow}`}>
                            <Icon className="w-5 h-5 text-white" />
                        </div>
                        <div>
                            <h4 className="text-sm font-bold text-gray-900">{agent.name}</h4>
                            <p className="text-[10px] text-gray-400 uppercase tracking-wider font-semibold">{agent.id.replace('_', ' ').toUpperCase()}</p>
                        </div>
                    </div>
                    {/* Status dot */}
                    <div className="flex items-center gap-1.5">
                        <span className="relative flex h-2.5 w-2.5">
                            {statusStyle.ping && <span className={`animate-ping absolute inline-flex h-full w-full rounded-full ${statusStyle.dot} opacity-75`}></span>}
                            <span className={`relative inline-flex rounded-full h-2.5 w-2.5 ${statusStyle.dot}`}></span>
                        </span>
                        <span className={`text-[10px] font-bold ${statusStyle.label}`}>{statusStyle.text}</span>
                    </div>
                </div>

                {/* Current Task (if running) */}
                {isRunning && agent.current_task && (
                    <div className="mb-3 p-2 bg-amber-50 border border-amber-100 rounded-lg">
                        <p className="text-[10px] font-bold text-amber-700 uppercase tracking-wider mb-0.5">Working on</p>
                        <p className="text-xs font-medium text-amber-900 truncate">{agent.current_task.title}</p>
                    </div>
                )}

                {/* Last completed task */}
                {isCompleted && agent.last_result?.task && (
                    <div className="mb-3 p-2 bg-emerald-50 border border-emerald-100 rounded-lg">
                        <p className="text-[10px] font-bold text-emerald-700 uppercase tracking-wider mb-0.5">Completed</p>
                        <p className="text-xs font-medium text-emerald-900 truncate">{agent.last_result.task.title}</p>
                    </div>
                )}

                {/* Error state */}
                {isError && (
                    <div className="mb-3 p-2 bg-red-50 border border-red-100 rounded-lg">
                        <p className="text-[10px] font-bold text-red-700 uppercase tracking-wider mb-0.5 flex items-center gap-1">
                            <AlertTriangle className="w-3 h-3" /> Error
                        </p>
                        <p className="text-xs font-medium text-red-800 truncate">{agent.progress_message}</p>
                    </div>
                )}

                {/* Mini stats */}
                <div className="flex items-center gap-4 mb-4 py-2 px-3 bg-gray-50 rounded-lg">
                    {config.statKeys.map((key, idx) => (
                        <React.Fragment key={key}>
                            {idx > 0 && <div className="w-px h-8 bg-gray-200"></div>}
                            <div className="text-center flex-1">
                                <p className="text-lg font-bold text-gray-800">{agent.stats?.[key] ?? '—'}</p>
                                <p className="text-[9px] text-gray-400 uppercase font-semibold">{config.statLabels[idx]}</p>
                            </div>
                        </React.Fragment>
                    ))}
                </div>

                {/* Progress bar (running) */}
                {isRunning && (
                    <div className="mb-4">
                        <div className="flex justify-between text-[10px] text-gray-400 mb-1">
                            <span className="truncate max-w-[70%]">{agent.progress_message || 'Processing...'}</span>
                            <span className={`font-bold text-${config.accentColor}-600`}>{agent.progress}%</span>
                        </div>
                        <div className="w-full bg-gray-100 rounded-full h-1.5 overflow-hidden">
                            <div
                                className={`bg-gradient-to-r ${config.gradient} h-1.5 rounded-full transition-all duration-1000 ease-out`}
                                style={{ width: `${agent.progress}%` }}
                            ></div>
                        </div>
                    </div>
                )}

                {/* Last run info */}
                <div className="flex items-center justify-between text-[10px] text-gray-400 mb-4">
                    <span className="flex items-center gap-1">
                        <Clock className="w-3 h-3" />
                        {agent.last_run
                            ? `Last: ${new Date(agent.last_run).toLocaleTimeString()}`
                            : 'Never run'}
                    </span>
                    {isCompleted && agent.last_result?.exit_code === 0 && (
                        <span className="font-semibold text-emerald-500 flex items-center gap-0.5">
                            <CheckCircle2 className="w-3 h-3" /> Success
                        </span>
                    )}
                    {isRunning && (
                        <span className="font-semibold text-amber-500 flex items-center gap-1">
                            <RefreshCw className="w-3 h-3 animate-spin" /> In Progress
                        </span>
                    )}
                </div>

                {/* Actions */}
                <div className="flex gap-2 mt-auto">
                    {isRunning ? (
                        <button disabled className="flex-1 inline-flex items-center justify-center gap-1.5 px-3 py-2 text-xs font-bold text-gray-400 bg-gray-100 rounded-lg cursor-not-allowed">
                            <Loader2 className="w-3 h-3 animate-spin" /> Running...
                        </button>
                    ) : (
                        <button
                            onClick={() => handleRunAgent(agent.id)}
                            disabled={!canRun || runningAgent === agent.id}
                            className={`flex-1 inline-flex items-center justify-center gap-1.5 px-3 py-2 text-xs font-bold text-white rounded-lg shadow-sm transition-all ${canRun
                                    ? `bg-gradient-to-r ${config.gradient} hover:shadow-md hover:-translate-y-0.5`
                                    : 'bg-gray-300 cursor-not-allowed'
                                }`}
                            title={!canRun ? 'No pending tasks available' : `Run ${agent.name}`}
                        >
                            {runningAgent === agent.id ? (
                                <><Loader2 className="w-3 h-3 animate-spin" /> Starting...</>
                            ) : (
                                <><Play className="w-3 h-3" /> Run Agent</>
                            )}
                        </button>
                    )}
                    <button
                        onClick={() => setShowLogModal(agent.id)}
                        disabled={!agent.output_log || agent.output_log.length === 0}
                        className="inline-flex items-center justify-center gap-1 px-3 py-2 text-xs font-bold text-gray-600 bg-gray-100 rounded-lg hover:bg-gray-200 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                    >
                        <Terminal className="w-3 h-3" /> Log
                    </button>
                    {(isCompleted || isError) && (
                        <button
                            onClick={() => handleResetAgent(agent.id)}
                            className="inline-flex items-center justify-center gap-1 px-3 py-2 text-xs font-bold text-gray-600 bg-gray-100 rounded-lg hover:bg-gray-200 transition-colors"
                            title="Reset agent to idle"
                        >
                            <RefreshCw className="w-3 h-3" />
                        </button>
                    )}
                </div>
            </div>
        );
    };

    return (
        <div className="w-full min-h-full bg-gray-50 flex flex-col font-sans overflow-y-auto relative">
            {/* Top Graphic Header Area */}
            <div className="bg-white shadow">

                {/* Top spacer since title is now in global navbar */}
                <div className="pt-4"></div>
                <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center px-4 md:px-8 py-2 mb-2 gap-3">
                    <div className="flex items-center space-x-4 flex-shrink-0">
                        <div className="text-sm font-bold text-[#f27a24]">As of : {new Date().toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: '2-digit' })}</div>
                        <div className="text-sm font-bold text-gray-800 flex items-center">
                            <div className="w-4 h-4 bg-emerald-500 mr-2 rounded-sm shadow-sm inline-block"></div>
                            Overall: On Track
                        </div>
                    </div>
                    <ProjectDropdown
                        projects={projects}
                        selectedKey={selectedProjectKey}
                        onSelect={(proj) => setSelectedProjectKey(proj.key)}
                        className="w-full sm:w-72"
                    />
                </div>
            </div>

            {/* Empty State vs Full Data */}
            {projects.length === 0 ? (
                <div className="flex-1 p-4 md:p-6 flex flex-col items-center justify-center min-h-[500px]">
                    <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-10 max-w-md w-full text-center flex flex-col items-center">
                        <div className="w-20 h-20 bg-blue-50 rounded-full flex items-center justify-center mb-6 shadow-inner">
                            <PlusCircle className="w-10 h-10 text-blue-500" />
                        </div>
                        <h2 className="text-2xl font-extrabold text-gray-800 mb-2">No Projects Found</h2>
                        <p className="text-gray-500 mb-8 text-sm leading-relaxed">
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
            ) : (
                <div className="flex-1 p-4 md:p-6 flex flex-col gap-6">

                    {/* Top Metric Cards - Full Width */}
                    <div className="w-full flex flex-col gap-3 md:gap-4">
                        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                            <div className="bg-white p-4 rounded-xl shadow border border-gray-100 flex flex-col items-center justify-center relative">
                                <p className="text-xs font-bold text-gray-600 mb-1">Active Projects</p>
                                <h3 className="text-3xl font-bold text-gray-800 mb-0">5</h3>
                                <p className="text-[10px] text-gray-500 uppercase tracking-widest">Tracked</p>
                            </div>
                            <div className="bg-white p-4 rounded-xl shadow border border-gray-100 flex flex-col items-center justify-center relative">
                                <p className="text-xs font-bold text-gray-600 mb-1">Project Lifecycle</p>
                                <h3 className="text-3xl font-bold text-gray-800 mb-0">120</h3>
                                <p className="text-[10px] text-gray-500 uppercase tracking-widest">Days</p>
                            </div>
                            <div className="bg-white col-span-2 md:col-span-2 p-4 rounded-xl shadow border border-gray-100 flex flex-row items-center justify-around relative">
                                <div className="flex flex-col items-center">
                                    <p className="text-xs font-bold text-gray-600 mb-1">Documents Uploaded</p>
                                    <div className="flex items-center relative">
                                        <h3 className="text-3xl font-bold text-gray-800 mb-0">300+</h3>
                                        <div className="absolute top-0 -right-4 w-3 h-3 select-none text-red-500">✦</div>
                                    </div>
                                </div>
                                <div className="w-px h-12 bg-gray-200"></div>
                                <div className="flex flex-col items-center w-40">
                                    <p className="text-xs font-bold text-gray-600 mb-1">Documents Analyzed</p>
                                    <div className="flex items-center relative mb-2 w-full justify-center">
                                        <h3 className="text-3xl font-bold text-gray-800 mb-0">200+</h3>
                                        <div className="absolute top-0 -right-2 w-3 h-3 select-none text-red-500">✦</div>
                                    </div>
                                    <div className="w-full bg-gray-200 rounded-full h-2.5">
                                        <div className="bg-gray-800 h-2.5 rounded-full" style={{ width: '66%' }}></div>
                                    </div>
                                </div>
                            </div>
                        </div>

                        <div className="grid grid-cols-5 gap-3 mt-4">
                            <div className="bg-white p-3 rounded-xl shadow border border-gray-100 flex flex-col items-center justify-center">
                                <p className="text-[11px] font-bold text-gray-600 mb-1">Governance Findings</p>
                                <h3 className="text-2xl font-bold text-gray-800">28</h3>
                                <p className="text-[9px] text-gray-500 uppercase tracking-wide">Identified</p>
                            </div>
                            <div className="bg-white p-3 rounded-xl shadow border border-gray-100 flex flex-col items-center justify-center">
                                <p className="text-[11px] font-bold text-gray-600 mb-1 text-center leading-tight">High-Priority Issues</p>
                                <h3 className="text-2xl font-bold text-gray-800">3</h3>
                                <p className="text-[9px] text-gray-500 uppercase tracking-wide">Critical</p>
                            </div>
                            <div className="bg-white p-3 rounded-xl shadow border border-gray-100 flex flex-col items-center justify-center">
                                <p className="text-[11px] font-bold text-gray-600 mb-1">Pending Reviews</p>
                                <h3 className="text-2xl font-bold text-gray-800">4</h3>
                                <p className="text-[9px] text-gray-500 uppercase tracking-wide">Active</p>
                            </div>
                            <div className="bg-white p-3 rounded-xl shadow border border-gray-100 flex flex-col items-center justify-center">
                                <p className="text-[11px] font-bold text-gray-600 mb-1">Revisions Completed</p>
                                <h3 className="text-2xl font-bold text-gray-800">0</h3>
                                <p className="text-[9px] text-gray-500 uppercase tracking-wide">Resolved</p>
                            </div>
                            <div className="bg-white p-3 rounded-xl shadow border border-gray-100 flex flex-col items-center justify-center">
                                <p className="text-[11px] font-bold text-gray-600 mb-1">Action Items</p>
                                <h3 className="text-2xl font-bold text-gray-800">143</h3>
                                <p className="text-[9px] text-gray-500 uppercase tracking-wide">Tracked</p>
                            </div>
                        </div>
                    </div>

                    {/* Bottom Section: 2 Columns */}
                    <div className="flex flex-col lg:flex-row gap-6 w-full">

                        {/* Left Column (Main Content) */}
                        <div className="flex-1 space-y-6 min-w-0">

                            {/* KEY MILESTONES & DATES */}
                            <div className="bg-white rounded-xl shadow border border-gray-100 p-6 relative">
                                <div className="flex items-center mb-6">
                                    <div className="p-2 mr-3 bg-orange-50 rounded text-orange-500">
                                        <Flag className="w-5 h-5" />
                                    </div>
                                    <h3 className="text-[15px] font-bold text-[#f27a24] uppercase tracking-wide">KEY MILESTONES & DATES</h3>
                                </div>
                                <div className="overflow-hidden rounded-lg">
                                    <table className="min-w-full text-sm">
                                        <thead className="bg-[#fdf4e6]">
                                            <tr>
                                                <th className="px-4 py-3 text-left font-bold text-gray-800">Milestone</th>
                                                <th className="px-4 py-3 text-left font-bold text-gray-800">Status</th>
                                                <th className="px-4 py-3 text-left font-bold text-gray-800">Date</th>
                                            </tr>
                                        </thead>
                                        <tbody className="divide-y divide-gray-100 text-gray-600 font-medium">
                                            <tr>
                                                <td className="px-4 py-3">Project Kickoff</td>
                                                <td className="px-4 py-3">Completed</td>
                                                <td className="px-4 py-3">Jan 9, 2026</td>
                                            </tr>
                                            <tr>
                                                <td className="px-4 py-3">Tool Deployment & Data Enablement</td>
                                                <td className="px-4 py-3">Completed</td>
                                                <td className="px-4 py-3">Dec 27, 2025</td>
                                            </tr>
                                            <tr>
                                                <td className="px-4 py-3 break-words pr-8">Discovery & Domain Working Sessions (Core Infrastructure, Applications, and Cloud, Security etc)</td>
                                                <td className="px-4 py-3">Completed</td>
                                                <td className="px-4 py-3 whitespace-nowrap">Feb 9, 2026</td>
                                            </tr>
                                            <tr>
                                                <td className="px-4 py-3">Current Infrastructure Assessment</td>
                                                <td className="px-4 py-3">In Progress</td>
                                                <td className="px-4 py-3">Feb 2026</td>
                                            </tr>
                                            <tr>
                                                <td className="px-4 py-3 border-b-0">Assessment Data Consolidation & Validation</td>
                                                <td className="px-4 py-3 border-b-0">In Progress</td>
                                                <td className="px-4 py-3 border-b-0">Feb 2026</td>
                                            </tr>
                                        </tbody>
                                    </table>
                                </div>
                            </div>

                            {/* ACTUAL VS REMAINING WORK */}
                            <div className="bg-white rounded-xl shadow border border-gray-100 p-6 flex flex-col relative min-h-[300px]">
                                <div className="flex items-center mb-8">
                                    <div className="p-2 mr-3 bg-orange-50 rounded text-orange-500">
                                        <Activity className="w-5 h-5" />
                                    </div>
                                    <h3 className="text-[15px] font-bold text-[#f27a24] uppercase tracking-wide">ACTUAL VS REMAINING WORK</h3>
                                </div>

                                <div className="flex-1 flex items-end justify-center px-12 pb-6 relative">
                                    {/* Y Axis markings */}
                                    <div className="absolute left-10 flex flex-col justify-between h-[200px] bottom-6 text-xs font-bold text-gray-500 w-10 text-right pr-2">
                                        <span className="relative -top-2">80%</span>
                                        <span className="relative">40%</span>
                                        <span className="relative top-2">0%</span>
                                    </div>

                                    {/* Grid lines */}
                                    <div className="absolute left-20 right-40 flex flex-col justify-between h-[200px] bottom-6 pointer-events-none">
                                        <div className="w-full border-t border-gray-300"></div>
                                        <div className="w-full border-t border-gray-300"></div>
                                        <div className="w-full border-t border-gray-500"></div>
                                    </div>

                                    {/* The Stacked Bar */}
                                    <div className="w-[30%] min-w-[150px] relative z-10 flex flex-col justify-end">
                                        {/* Remaining Work (60%) */}
                                        <div className="bg-[#feebad] w-full h-[120px] relative flex items-center justify-center">
                                            <span className="text-orange-500 font-bold text-sm">60%</span>
                                        </div>
                                        {/* Work (40%) */}
                                        <div className="bg-[#424242] w-full h-[80px] relative flex items-center justify-center">
                                            <span className="text-white font-bold text-sm">40%</span>
                                        </div>
                                    </div>

                                    <div className="absolute bottom-[-15px] w-full text-center text-[10px] font-bold text-gray-500">
                                        Overall Assessment Progress
                                    </div>

                                    {/* Legend */}
                                    <div className="absolute right-10 bottom-20 flex flex-col gap-3">
                                        <div className="flex items-center">
                                            <div className="w-6 h-4 bg-[#feebad] mr-3"></div>
                                            <span className="text-sm text-gray-700 font-medium">Remaining Work</span>
                                        </div>
                                        <div className="flex items-center">
                                            <div className="w-6 h-4 bg-[#424242] mr-3"></div>
                                            <span className="text-sm text-gray-700 font-medium">Work</span>
                                        </div>
                                    </div>
                                </div>
                            </div>

                            {/* 5 Key Assessment Areas & progress */}
                            <div className="bg-white rounded-xl shadow border border-gray-100 p-6">
                                <div className="flex items-center mb-8">
                                    <div className="p-2 mr-3 bg-orange-50 rounded text-orange-500">
                                        <CheckCircle className="w-5 h-5" />
                                    </div>
                                    <h3 className="text-[15px] font-bold text-[#f27a24] uppercase tracking-wide">5 Key Assessment Areas & progress</h3>
                                </div>

                                <div className="space-y-6">
                                    {/* Bar 1 */}
                                    <div className="flex items-center">
                                        <div className="w-48 text-xs font-bold text-gray-800 flex items-center">
                                            <div className="mr-2 opacity-60"><Clock className="w-4 h-4" /></div>
                                            Infrastructure Assessment
                                        </div>
                                        <div className="flex-1 right-0 relative flex flex-col justify-center">
                                            <div className="text-right text-[10px] font-bold text-gray-800 mb-1 absolute -top-4 right-0">60%</div>
                                            <div className="w-full bg-[#fceacc] rounded-full h-3 flex overflow-hidden">
                                                <div className="bg-[#ea7032] h-full" style={{ width: '60%' }}></div>
                                            </div>
                                        </div>
                                    </div>

                                    {/* Bar 2 */}
                                    <div className="flex items-center">
                                        <div className="w-48 text-xs font-bold text-gray-800 flex items-center">
                                            <div className="mr-2 opacity-60"><Clock className="w-4 h-4" /></div>
                                            Application Dependency Map
                                        </div>
                                        <div className="flex-1 right-0 relative flex flex-col justify-center">
                                            <div className="text-right text-[10px] font-bold text-gray-800 mb-1 absolute -top-4 right-0">10%</div>
                                            <div className="w-full bg-[#fdf4e6] rounded-full h-3 flex overflow-hidden">
                                                <div className="bg-[#feebad] h-full" style={{ width: '10%' }}></div>
                                            </div>
                                        </div>
                                    </div>

                                    {/* Bar 3 */}
                                    <div className="flex items-center">
                                        <div className="w-48 text-xs font-bold text-gray-800 flex items-center">
                                            <div className="mr-2 opacity-60"><Clock className="w-4 h-4" /></div>
                                            Security & Compliance
                                        </div>
                                        <div className="flex-1 right-0 relative flex flex-col justify-center">
                                            <div className="text-right text-[10px] font-bold text-gray-800 mb-1 absolute -top-4 right-0">60%</div>
                                            <div className="w-full bg-[#e0e0e0] rounded-full h-3 flex overflow-hidden">
                                                <div className="bg-[#6b6b6b] h-full" style={{ width: '60%' }}></div>
                                            </div>
                                        </div>
                                    </div>

                                    {/* Bar 4 */}
                                    <div className="flex items-center">
                                        <div className="w-48 text-xs font-bold text-gray-800 flex items-center">
                                            <div className="mr-2 opacity-60"><Clock className="w-4 h-4" /></div>
                                            End User Computing
                                        </div>
                                        <div className="flex-1 right-0 relative flex flex-col justify-center">
                                            <div className="text-right text-[10px] font-bold text-gray-800 mb-1 absolute -top-4 right-0">60%</div>
                                            <div className="w-full bg-[#d0e0fb] rounded-full h-3 flex overflow-hidden">
                                                <div className="bg-[#0c2e64] h-full" style={{ width: '60%' }}></div>
                                            </div>
                                        </div>
                                    </div>

                                    {/* Bar 5 */}
                                    <div className="flex items-center">
                                        <div className="w-48 text-xs font-bold text-gray-800 flex items-center">
                                            <div className="mr-2 opacity-60"><Clock className="w-4 h-4" /></div>
                                            Performance & Cost Baseline
                                        </div>
                                        <div className="flex-1 right-0 relative flex flex-col justify-center">
                                            <div className="text-right text-[10px] font-bold text-gray-800 mb-1 absolute -top-4 right-0">10%</div>
                                            <div className="w-full bg-[#fdf4e6] rounded-full h-3 flex overflow-hidden">
                                                <div className="bg-[#feebad] h-full" style={{ width: '10%' }}></div>
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>

                        {/* Right Column (Sidebar Summary) */}
                        <div className="w-full shrink-0 lg:w-[320px] bg-white rounded-xl shadow border border-gray-100 p-4 md:p-6 flex flex-col items-center">
                            <h2 className="text-[22px] font-bold text-[#f27a24] mb-4">Project Status</h2>
                            <div className="w-full border-t-2 border-[#f27a24] mb-8 opacity-50"></div>

                            <div className="w-full mb-10 flex flex-col items-center relative">
                                <div className="absolute left-[-5px] top-0 text-green-500">
                                    <svg className="w-8 h-8" fill="currentColor" viewBox="0 0 24 24"><path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"></path></svg>
                                </div>
                                <div className="bg-white border rounded p-4 text-center w-5/6 mx-auto shadow-sm relative z-10">
                                    <p className="text-[10px] font-bold text-gray-800 uppercase mb-2">EXPECTED LAUNCH DATE</p>
                                    <h3 className="text-2xl font-black text-gray-900 mb-2">50 <span className="text-sm font-medium">Days</span></h3>
                                    <div className="flex items-center justify-center w-full mb-2">
                                        <div className="h-px bg-gray-300 w-full relative">
                                            <div className="absolute left-0 top-[-3px] w-2 h-2 bg-gray-400 rounded-full"></div>
                                            <div className="absolute right-0 top-[-3px] w-2 h-2 bg-gray-400 rounded-full"></div>
                                        </div>
                                    </div>
                                    <p className="text-xs italic text-gray-500">Tuesday, 31 March 2026</p>
                                </div>
                            </div>

                            <div className="w-full mb-10 flex flex-col items-center">
                                <div className="flex justify-center items-center w-full relative mb-1">
                                    <div className="absolute left-8 text-green-500">
                                        <Activity className="w-8 h-8" />
                                    </div>
                                    <div className="w-10 h-10 rounded-full bg-gradient-to-br from-green-400 to-green-600 shadow-lg shadow-green-500/30"></div>
                                </div>
                                <p className="text-sm font-bold text-gray-800 mt-2">Overall, Health</p>
                            </div>

                            <div className="w-full border-t border-gray-100 mb-8 w-4/5 mx-auto"></div>

                            {/* Circular Gauge 1 */}
                            <div className="mb-10 flex flex-col items-center relative w-full">
                                <div className="absolute left-8 text-orange-200">
                                    <svg className="w-8 h-8 opacity-50" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4"></path></svg>
                                </div>
                                <div className="relative w-24 h-24 mb-4">
                                    <svg className="w-24 h-24 transform -rotate-90">
                                        <circle cx="48" cy="48" r="40" stroke="#fdf4e6" strokeWidth="12" fill="none" />
                                        <circle cx="48" cy="48" r="40" stroke="#f27a24" strokeWidth="12" fill="none" strokeDasharray="251" strokeDashoffset="125.5" strokeLinecap="round" />
                                    </svg>
                                    <div className="absolute inset-0 flex items-center justify-center">
                                        <span className="text-xl font-bold text-gray-800">50%</span>
                                    </div>
                                </div>
                                <p className="text-[13px] font-bold text-gray-600">Decision Readiness</p>
                            </div>

                            <div className="w-full border-t border-gray-100 mb-8 w-4/5 mx-auto"></div>

                            {/* Circular Gauge 2 */}
                            <div className="mb-10 flex flex-col items-center relative w-full">
                                <div className="absolute left-8 text-gray-300">
                                    <svg className="w-6 h-6 opacity-70" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M5 13l4 4L19 7"></path></svg>
                                </div>
                                <div className="relative w-24 h-24 mb-4">
                                    <svg className="w-24 h-24 transform -rotate-90">
                                        <circle cx="48" cy="48" r="40" stroke="#f3f4f6" strokeWidth="12" fill="none" />
                                        <circle cx="48" cy="48" r="40" stroke="#9ca3af" strokeWidth="12" fill="none" strokeDasharray="251" strokeDashoffset="150.6" strokeLinecap="round" />
                                    </svg>
                                    <div className="absolute inset-0 flex items-center justify-center">
                                        <span className="text-xl font-bold text-gray-800">40%</span>
                                    </div>
                                </div>
                                <p className="text-[13px] font-bold text-gray-600">Project Progress</p>
                            </div>

                            <div className="w-full border-t border-gray-100 mb-8 w-4/5 mx-auto"></div>

                            {/* Circular Gauge 3 */}
                            <div className="mb-6 flex flex-col items-center relative w-full">
                                <div className="absolute left-6 text-gray-700">
                                    <svg className="w-8 h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M8 7v8a2 2 0 002 2h6M8 7V5a2 2 0 012-2h4.586a1 1 0 01.707.293l4.414 4.414a1 1 0 01.293.707V15a2 2 0 01-2 2h-2M8 7H6a2 2 0 00-2 2v10a2 2 0 002 2h8a2 2 0 002-2v-2"></path></svg>
                                </div>
                                <div className="relative w-24 h-24 mb-4">
                                    <svg className="w-24 h-24 transform -rotate-90">
                                        <circle cx="48" cy="48" r="40" stroke="#f3f4f6" strokeWidth="12" fill="none" />
                                        <circle cx="48" cy="48" r="40" stroke="#1f2937" strokeWidth="12" fill="none" strokeDasharray="251" strokeDashoffset="50.2" strokeLinecap="round" />
                                    </svg>
                                    <div className="absolute inset-0 flex items-center justify-center">
                                        <span className="text-xl font-bold text-gray-800">80%</span>
                                    </div>
                                </div>
                                <p className="text-[13px] font-bold text-gray-600">Phase Progress</p>
                            </div>
                        </div>
                    </div>

                    {/* ── AI AGENTS SECTION ── */}
                    <div className="w-full mt-6">
                        <div className="flex items-center justify-between mb-6">
                            <div className="flex items-center">
                                <div className="p-2 mr-3 bg-indigo-50 rounded text-indigo-500">
                                    <Bot className="w-5 h-5" />
                                </div>
                                <h3 className="text-[15px] font-bold text-[#f27a24] uppercase tracking-wide">AI Agents</h3>
                                <span className="ml-3 text-[10px] font-bold text-gray-400 uppercase tracking-wider bg-gray-100 px-2 py-0.5 rounded-full">
                                    {agents.filter(a => a.status === 'running').length} Running
                                </span>
                            </div>
                            <div className="flex items-center gap-2">
                                <span className="text-[10px] font-bold text-gray-400 uppercase tracking-wider bg-orange-50 text-orange-600 px-2.5 py-1 rounded-full">
                                    {pendingTasks.length} Pending Tasks
                                </span>
                                <button
                                    onClick={() => { fetchAgents(); fetchTasks(); }}
                                    className="text-gray-400 hover:text-gray-600 p-1 rounded hover:bg-gray-100 transition-colors"
                                    title="Refresh"
                                >
                                    <RefreshCw className="w-4 h-4" />
                                </button>
                            </div>
                        </div>

                        {/* Pending Tasks Preview */}
                        {pendingTasks.length > 0 && (
                            <div className="mb-5 bg-white rounded-xl shadow border border-gray-100 p-4">
                                <h4 className="text-xs font-bold text-gray-500 uppercase tracking-wider mb-3">Pending Tasks Queue</h4>
                                <div className="flex gap-2 overflow-x-auto pb-1 scrollbar-hide">
                                    {pendingTasks.slice(0, 5).map((task, idx) => (
                                        <div key={task.id} className="flex-shrink-0 bg-gray-50 border border-gray-100 rounded-lg px-3 py-2 min-w-[200px] max-w-[250px]">
                                            <div className="flex items-center gap-1.5 mb-1">
                                                <span className={`w-1.5 h-1.5 rounded-full ${task.priority === 'high' ? 'bg-red-400' : task.priority === 'medium' ? 'bg-amber-400' : 'bg-blue-400'}`}></span>
                                                <span className="text-[9px] font-bold text-gray-400 uppercase">{task.priority}</span>
                                            </div>
                                            <p className="text-xs font-medium text-gray-700 truncate">{task.title}</p>
                                        </div>
                                    ))}
                                    {pendingTasks.length > 5 && (
                                        <div className="flex-shrink-0 bg-gray-50 border border-gray-100 rounded-lg px-3 py-2 flex items-center">
                                            <span className="text-xs text-gray-400 font-bold">+{pendingTasks.length - 5} more</span>
                                        </div>
                                    )}
                                </div>
                            </div>
                        )}

                        {loadingAgents ? (
                            <div className="flex items-center justify-center py-12">
                                <Loader2 className="w-6 h-6 animate-spin text-gray-400 mr-2" />
                                <span className="text-sm text-gray-500">Loading agents...</span>
                            </div>
                        ) : (
                            <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
                                {agents.map(agent => renderAgentCard(agent))}
                            </div>
                        )}
                    </div>
                </div>
            )}

            {/* Agent Output Log Modal */}
            {showLogModal && (() => {
                const agent = agents.find(a => a.id === showLogModal);
                if (!agent) return null;
                return (
                    <div className="fixed inset-0 bg-gray-900/60 backdrop-blur-sm flex items-center justify-center p-4 z-[100]">
                        <div className="bg-gray-900 rounded-2xl shadow-xl w-full max-w-2xl overflow-hidden max-h-[80vh] flex flex-col">
                            <div className="px-5 py-4 border-b border-gray-700 flex items-center justify-between bg-gray-800">
                                <h3 className="font-bold text-white text-sm flex items-center gap-2">
                                    <Terminal className="w-4 h-4 text-green-400" />
                                    {agent.name} — Execution Log
                                </h3>
                                <button onClick={() => setShowLogModal(null)} className="text-gray-400 hover:text-white p-1 rounded transition-colors">
                                    <X className="w-5 h-5" />
                                </button>
                            </div>
                            <div className="flex-1 overflow-y-auto p-4 font-mono text-xs space-y-1 min-h-[300px]">
                                {agent.output_log && agent.output_log.length > 0 ? (
                                    agent.output_log.map((entry, idx) => (
                                        <div key={idx} className={`flex gap-2 ${entry.type === 'error' ? 'text-red-400' : entry.type === 'info' ? 'text-blue-400' : 'text-green-300'}`}>
                                            <span className="text-gray-600 select-none flex-shrink-0">{new Date(entry.time).toLocaleTimeString()}</span>
                                            <span className={`flex-shrink-0 font-bold uppercase w-12 text-right ${entry.type === 'error' ? 'text-red-500' : entry.type === 'info' ? 'text-blue-500' : 'text-green-500'}`}>
                                                [{entry.type}]
                                            </span>
                                            <span className="break-all">{entry.message}</span>
                                        </div>
                                    ))
                                ) : (
                                    <p className="text-gray-500 italic">No log entries yet.</p>
                                )}
                            </div>
                            {/* Generated code section */}
                            {agent.last_result?.generated_code && (
                                <div className="border-t border-gray-700 p-4">
                                    <details className="group">
                                        <summary className="text-[10px] font-bold text-gray-400 uppercase tracking-wider cursor-pointer hover:text-gray-300 flex items-center gap-1">
                                            <Eye className="w-3 h-3" /> View Generated Code ({agent.last_result.generated_code.split('\n').length} lines)
                                        </summary>
                                        <pre className="mt-2 text-xs text-green-300 bg-gray-800 rounded p-3 overflow-auto max-h-60 font-mono whitespace-pre-wrap">
                                            {agent.last_result.generated_code}
                                        </pre>
                                    </details>
                                </div>
                            )}
                        </div>
                    </div>
                );
            })()}

            {/* Generated Tasks Section */}
            {projects.length > 0 && (
                <div className="px-4 md:px-6 pb-6">
                    <div className="bg-white rounded-2xl shadow-sm border border-gray-100 overflow-hidden">
                        {/* Section Header */}
                        <div className="px-6 py-4 border-b border-gray-100 flex items-center justify-between bg-gradient-to-r from-gray-50/80 to-white">
                            <div className="flex items-center gap-3">
                                <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center shadow-lg shadow-indigo-200">
                                    <ListTodo className="w-4.5 h-4.5 text-white" />
                                </div>
                                <div>
                                    <h3 className="text-sm font-bold text-gray-900">Generated Tasks</h3>
                                    <p className="text-[10px] text-gray-400 uppercase tracking-wider font-semibold">
                                        {taskList.length} task{taskList.length !== 1 ? 's' : ''} from AI Auto-Generator
                                    </p>
                                </div>
                            </div>
                            <button
                                onClick={fetchTasks}
                                disabled={isLoadingTasks}
                                className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold text-gray-500 bg-gray-50 border border-gray-200 rounded-lg hover:bg-gray-100 hover:text-gray-700 transition-all disabled:opacity-50"
                            >
                                <RefreshCw className={`w-3 h-3 ${isLoadingTasks ? 'animate-spin' : ''}`} />
                                Refresh
                            </button>
                        </div>

                        {/* Task List Content */}
                        <div className="divide-y divide-gray-50">
                            {/* Loading State */}
                            {isLoadingTasks && taskList.length === 0 && (
                                <div className="p-8 flex flex-col items-center justify-center gap-3">
                                    <RefreshCw className="w-6 h-6 text-indigo-400 animate-spin" />
                                    <p className="text-sm text-gray-400 font-medium">Loading tasks...</p>
                                </div>
                            )}

                            {/* Error State */}
                            {taskListError && !isLoadingTasks && (
                                <div className="p-6 flex items-center gap-3 bg-red-50/50">
                                    <AlertCircle className="w-5 h-5 text-red-400 flex-shrink-0" />
                                    <p className="text-sm text-red-600 font-medium">{taskListError}</p>
                                </div>
                            )}

                            {/* Empty State */}
                            {!isLoadingTasks && !taskListError && taskList.length === 0 && (
                                <div className="p-10 flex flex-col items-center justify-center gap-2 text-center">
                                    <div className="w-14 h-14 bg-gray-50 rounded-full flex items-center justify-center mb-2">
                                        <ListTodo className="w-7 h-7 text-gray-300" />
                                    </div>
                                    <p className="text-sm font-bold text-gray-500">No tasks generated yet</p>
                                    <p className="text-xs text-gray-400 max-w-xs">
                                        Select a project and click "Create Tasks" on the Task Auto-Generator agent above to get started.
                                    </p>
                                </div>
                            )}

                            {/* Task Rows */}
                            {!isLoadingTasks && taskList.length > 0 && taskList.map((task, index) => {
                                const priorityStyles = {
                                    high: 'bg-red-50 text-red-700 border-red-200',
                                    medium: 'bg-amber-50 text-amber-700 border-amber-200',
                                    low: 'bg-green-50 text-green-700 border-green-200'
                                };
                                const typeStyles = {
                                    EPIC: 'bg-purple-100 text-purple-700',
                                    FEATURE: 'bg-blue-100 text-blue-700',
                                    STORY: 'bg-cyan-100 text-cyan-700',
                                    TASK: 'bg-gray-100 text-gray-700',
                                    BUG: 'bg-red-100 text-red-700'
                                };
                                const statusStyles = {
                                    'On Going': 'bg-blue-50 text-blue-700',
                                    'Completed': 'bg-green-50 text-green-700',
                                    'To Do': 'bg-gray-50 text-gray-600',
                                    'In Review': 'bg-amber-50 text-amber-700',
                                    'Blocked': 'bg-red-50 text-red-700'
                                };
                                const priority = (task.priority || 'medium').toLowerCase();
                                const taskType = (task.task_type || 'TASK').toUpperCase();
                                const progress = task.task_progress || 0;
                                const progressColor = progress >= 80 ? 'bg-green-500' : progress >= 40 ? 'bg-blue-500' : 'bg-amber-500';

                                return (
                                    <div
                                        key={task.id || index}
                                        className="px-6 py-4 hover:bg-gray-50/70 transition-colors group"
                                    >
                                        <div className="flex items-center gap-4">
                                            {/* Task Number + Flag */}
                                            <div className="flex items-center gap-1.5 flex-shrink-0">
                                                <div className="w-7 h-7 rounded-lg bg-gray-100 flex items-center justify-center">
                                                    <span className="text-[10px] font-bold text-gray-500">{index + 1}</span>
                                                </div>
                                                {task.is_flaged && (
                                                    <Flag className="w-3.5 h-3.5 text-orange-400 fill-orange-400" />
                                                )}
                                            </div>

                                            {/* Task Info */}
                                            <div className="flex-1 min-w-0">
                                                <div className="flex items-center gap-2 mb-0.5">
                                                    <h4 className="text-sm font-semibold text-gray-900 truncate">
                                                        {task.taskName || 'Untitled Task'}
                                                    </h4>
                                                    <span className={`inline-flex items-center px-1.5 py-0.5 rounded text-[9px] font-bold uppercase tracking-wide flex-shrink-0 ${typeStyles[taskType] || typeStyles.TASK}`}>
                                                        {taskType}
                                                    </span>
                                                    {task.is_completed && (
                                                        <CheckCircle className="w-3.5 h-3.5 text-green-500 flex-shrink-0" />
                                                    )}
                                                </div>
                                                <p className="text-xs text-gray-400 truncate max-w-md">
                                                    {task.description || 'No description'}
                                                </p>
                                            </div>

                                            {/* Status */}
                                            <div className="flex-shrink-0 hidden lg:block">
                                                <span className={`inline-flex items-center px-2 py-0.5 rounded-md text-[10px] font-bold ${statusStyles[task.taskStatus] || 'bg-gray-50 text-gray-600'}`}>
                                                    {task.taskStatus || 'Unknown'}
                                                </span>
                                            </div>

                                            {/* Priority */}
                                            <div className="flex-shrink-0">
                                                <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-bold border capitalize ${priorityStyles[priority] || priorityStyles.medium}`}>
                                                    {priority}
                                                </span>
                                            </div>

                                            {/* Assignees */}
                                            <div className="flex-shrink-0 hidden md:flex items-center gap-1" title={`Assigned to: ${(task.assignedTo || []).join(', ')}`}>
                                                <Users className="w-3.5 h-3.5 text-gray-400" />
                                                <div className="flex items-center gap-0.5">
                                                    {(task.assignedTo || []).map((name, i) => (
                                                        <span key={i} className="inline-flex items-center px-1.5 py-0.5 bg-indigo-50 text-indigo-700 rounded text-[9px] font-semibold">
                                                            {name}
                                                        </span>
                                                    ))}
                                                </div>
                                            </div>

                                            {/* Wallet */}
                                            <div className="flex-shrink-0 flex items-center gap-1" title={`Wallet: ${task.task_wallet || 0}`}>
                                                <Wallet className="w-3.5 h-3.5 text-gray-400" />
                                                <span className="text-[10px] font-semibold text-gray-500">{task.task_wallet || 0}</span>
                                            </div>

                                            {/* Days Left / Deadline */}
                                            <div className="flex-shrink-0 hidden md:flex items-center gap-1.5 text-[10px]">
                                                <Calendar className="w-3 h-3 text-gray-400" />
                                                <span className="text-gray-400">{task.deadline || '-'}</span>
                                                {task.days_left != null && (
                                                    <span className={`font-bold px-1.5 py-0.5 rounded-full ${task.days_left <= 3 ? 'bg-red-50 text-red-600' : task.days_left <= 7 ? 'bg-amber-50 text-amber-600' : 'bg-green-50 text-green-600'}`}>
                                                        {task.days_left}d left
                                                    </span>
                                                )}
                                            </div>
                                        </div>

                                        {/* Progress Bar */}
                                        <div className="mt-2 ml-[38px] flex items-center gap-3">
                                            <div className="flex-1 bg-gray-100 rounded-full h-1.5 overflow-hidden max-w-[200px]">
                                                <div
                                                    className={`${progressColor} h-1.5 rounded-full transition-all duration-500`}
                                                    style={{ width: `${Math.min(progress, 100)}%` }}
                                                ></div>
                                            </div>
                                            <span className="text-[10px] font-bold text-gray-500">{progress}%</span>
                                        </div>
                                    </div>
                                );
                            })}
                        </div>
                    </div>
                </div>
            )}

            {/* Add Project Modal */}
            {showModal && (
                <div className="fixed inset-0 bg-gray-900/50 backdrop-blur-sm flex items-center justify-center p-4 z-[100] animate-in fade-in duration-200">
                    <div className="bg-white rounded-2xl shadow-xl border border-gray-100 w-full max-w-md overflow-hidden animate-in zoom-in-95 duration-200">
                        <div className="px-6 py-5 border-b border-gray-100 flex items-center justify-between bg-gradient-to-r from-gray-50 to-white">
                            <h3 className="font-bold text-gray-900 text-lg flex items-center gap-2">
                                <PlusCircle className="w-5 h-5 text-blue-500" /> Create Project
                            </h3>
                            <button
                                type="button"
                                onClick={() => setShowModal(false)}
                                className="text-gray-400 hover:text-gray-700 hover:bg-gray-100 p-1.5 rounded-full transition-colors"
                            >
                                <X className="w-5 h-5" />
                            </button>
                        </div>
                        <div className="p-6">
                            <p className="text-sm text-gray-500 mb-4 font-medium">
                                Step 1 of Governance Track: Give your project a descriptive name to get started.
                            </p>
                            <label className="block text-[11px] font-bold text-gray-500 mb-2 uppercase tracking-widest">
                                Project Name <span className="text-red-400">*</span>
                            </label>
                            <input
                                type="text"
                                value={newProjectName}
                                onChange={(e) => setNewProjectName(e.target.value)}
                                autoFocus
                                onKeyDown={(e) => e.key === 'Enter' && handleCreateProject()}
                                placeholder="e.g. Customer Analytics Platform"
                                className="w-full px-4 py-3 border-2 border-gray-200 rounded-xl focus:ring-4 focus:ring-blue-100 focus:border-blue-400 text-sm bg-gray-50/50 text-gray-900 transition-all duration-200 placeholder:text-gray-300 font-medium mb-6"
                            />

                            <div className="flex items-center gap-3">
                                <button
                                    type="button"
                                    onClick={() => setShowModal(false)}
                                    className="flex-1 py-3 px-4 font-bold text-gray-600 bg-gray-50 hover:bg-gray-100 border border-gray-200 rounded-xl transition-colors"
                                >
                                    Cancel
                                </button>
                                <button
                                    type="button"
                                    onClick={handleCreateProject}
                                    disabled={!newProjectName.trim()}
                                    className="flex-1 py-3 px-4 font-bold text-white bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-700 hover:to-indigo-700 rounded-xl transition-colors shadow-lg shadow-blue-500/30 hover:shadow-blue-500/50 disabled:opacity-50 disabled:cursor-not-allowed flex justify-center items-center gap-2 group"
                                >
                                    Start track <ArrowRight className="w-4 h-4 group-hover:translate-x-1 transition-transform" />
                                </button>
                            </div>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}
}
