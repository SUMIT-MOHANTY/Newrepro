import React, { useState, useEffect, useCallback } from 'react';
import { Flag, Activity, CheckCircle, Clock, Menu, PlusCircle, X, ArrowRight, Bot, Shield, Cpu, Play, RefreshCw, Eye, AlertTriangle, CheckCircle2, Loader2, Terminal, ListTodo, AlertCircle, Users, Calendar, Wallet } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import ProjectDropdown from './ProjectDropdown';
import { API_ENDPOINTS } from '../config';

export default function StatusDashboard({ projects = [] }) {
    const navigate = useNavigate();
    const [showModal, setShowModal] = useState(false);
    const [newProjectName, setNewProjectName] = useState('');
    const [selectedProjectKey, setSelectedProjectKey] = useState(projects[0]?.key || null);

    // ── Agent State (Backend Docker Execution) ───────────────────────
    const [agents, setAgents] = useState([]);
    const [loadingAgents, setLoadingAgents] = useState(true);
    const [runningAgent, setRunningAgent] = useState(null);
    const [showLogModal, setShowLogModal] = useState(null);

    // ── Git Config Modal State ───────────────────────────────────────
    const [gitModalAgent, setGitModalAgent] = useState(null);
    const [gitRepoUrl, setGitRepoUrl] = useState('');
    const [gitToken, setGitToken] = useState('');

    // ── External Task API State (tasks come from external API now) ───
    const [isGeneratingTasks, setIsGeneratingTasks] = useState(false);
    const [generatedTasksCount, setGeneratedTasksCount] = useState(0);
    const [generationError, setGenerationError] = useState(null);
    const [taskList, setTaskList] = useState([]);
    const [isLoadingTasks, setIsLoadingTasks] = useState(false);
    const [taskListError, setTaskListError] = useState(null);

    const token = localStorage.getItem('token');

    // ── Fetch agents (our Docker agent backend) ──────────────────────
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
        } finally {
            setLoadingAgents(false);
        }
    }, [token]);

    // ── Fetch external tasks (from task management API) ──────────────
    const fetchExternalTasks = useCallback(async () => {
        setIsLoadingTasks(true);
        setTaskListError(null);
        try {
            const res = await fetch(API_ENDPOINTS.AGENT_TASKS, {
                headers: { 'Authorization': `Bearer ${token}` }
            });
            if (res.ok) {
                const data = await res.json();
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
    }, [token]);

    useEffect(() => {
        fetchAgents();
        fetchExternalTasks();
    }, [fetchAgents, fetchExternalTasks]);

    // Poll while agents are running
    useEffect(() => {
        const hasRunning = agents.some(a => a.status === 'running');
        if (!hasRunning) return;
        const interval = setInterval(() => {
            fetchAgents();
        }, 3000);
        return () => clearInterval(interval);
    }, [agents, fetchAgents]);

    // ── Run Agent (Docker execution) ─────────────────────────────────
    const handleRunAgentClick = (agent) => {
        if (!agent.git_repo_url) {
            setGitRepoUrl('');
            setGitToken('');
            setGitModalAgent(agent);
        } else {
            handleRunAgent(agent.id);
        }
    };

    const handleRunAgent = async (agentId, repoUrl = null, repoToken = null) => {
        setRunningAgent(agentId);
        setGitModalAgent(null); // close modal if open
        const body = repoUrl ? { git_repo_url: repoUrl, git_token: repoToken } : {};
        try {
            await fetch(API_ENDPOINTS.AGENT_RUN(agentId), {
                method: 'POST',
                headers: {
                    'Authorization': `Bearer ${token}`,
                    'Content-Type': 'application/json'
                },
                body: Object.keys(body).length > 0 ? JSON.stringify(body) : undefined,
            });
            fetchAgents();
        } catch (e) {
            console.error('Run failed', e);
        } finally {
            setRunningAgent(null);
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

    // ── Generate tasks via external API ──────────────────────────────
    const handleGenerateTasks = async () => {
        if (!selectedProjectKey) return;
        setIsGeneratingTasks(true);
        setGenerationError(null);
        setGeneratedTasksCount(0);

        try {
            const response = await fetch(API_ENDPOINTS.AGENT_AUTO_GENERATE, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${token}`
                },
                body: JSON.stringify({
                    project_token: selectedProjectKey,
                })
            });

            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.detail || 'Failed to generate tasks');
            }

            const data = await response.json();
            setGeneratedTasksCount(data.tasks_created || 0);
            await fetchExternalTasks();
        } catch (err) {
            setGenerationError(err.message);
        } finally {
            setIsGeneratingTasks(false);
        }
    };

    const handleCreateProject = () => {
        if (!newProjectName.trim()) return;
        navigate(`/governance?projectName=${encodeURIComponent(newProjectName.trim())}`);
    };

    // ── Agent Card Config ────────────────────────────────────────────
    const agentConfig = {
        agent_01: {
            icon: <CheckCircle className="w-5 h-5 text-white" />,
            gradient: 'from-emerald-400 to-green-600',
            shadow: 'shadow-emerald-200',
            accent: 'from-emerald-400 to-green-500',
            color: 'emerald',
            description: 'Validates BRD completeness, checks for missing requirements, ambiguities, and ensures all acceptance criteria are well-defined.',
            stats: ['checks', 'coverage', 'avg_time'],
            statLabels: { checks: 'Checks', coverage: 'Coverage', avg_time: 'Duration' },
        },
        agent_02: {
            icon: <Shield className="w-5 h-5 text-white" />,
            gradient: 'from-amber-400 to-orange-600',
            shadow: 'shadow-orange-200',
            accent: 'from-amber-400 to-orange-500',
            color: 'amber',
            description: 'Identifies technical, business, and operational risks. Analyzes dependencies, integration complexity, and security vulnerabilities.',
            stats: ['risks', 'critical', 'avg_time'],
            statLabels: { risks: 'Risks', critical: 'Critical', avg_time: 'Duration' },
        },
        agent_03: {
            icon: <Cpu className="w-5 h-5 text-white" />,
            gradient: 'from-blue-400 to-indigo-600',
            shadow: 'shadow-blue-200',
            accent: 'from-blue-400 to-indigo-500',
            color: 'blue',
            description: 'Estimates sprint count, team size, and timeline. Breaks down requirements into manageable development phases.',
            stats: ['sprints', 'resources', 'avg_time'],
            statLabels: { sprints: 'Sprints', resources: 'Resources', avg_time: 'Duration' },
        },
    };

    // ── Render Agent Card ────────────────────────────────────────────
    const renderAgentCard = (agent) => {
        const cfg = agentConfig[agent.id] || agentConfig.agent_01;
        const isRunning = agent.status === 'running';
        const isCompleted = agent.status === 'completed';
        const isError = agent.status === 'error';
        const isIdle = agent.status === 'idle';
        const statusColor = isRunning ? cfg.color : isCompleted ? 'emerald' : isError ? 'red' : 'gray';

        return (
            <div key={agent.id} className="bg-white rounded-xl shadow border border-gray-100 p-5 flex flex-col relative overflow-hidden group hover:shadow-lg transition-shadow">
                <div className={`absolute top-0 left-0 right-0 h-1 bg-gradient-to-r ${cfg.accent}`}></div>

                <div className="flex items-start justify-between mb-4">
                    <div className="flex items-center gap-3">
                        <div className={`w-10 h-10 rounded-xl bg-gradient-to-br ${cfg.gradient} flex items-center justify-center shadow-lg ${cfg.shadow}`}>
                            {cfg.icon}
                        </div>
                        <div>
                            <h4 className="text-sm font-bold text-gray-900">{agent.name}</h4>
                            <p className="text-[10px] text-gray-400 uppercase tracking-wider font-semibold">{agent.id.replace('_', ' ').toUpperCase()}</p>
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

                <p className="text-xs text-gray-500 mb-4 leading-relaxed">{cfg.description}</p>

                {/* Stats */}
                <div className="flex items-center gap-4 mb-4 py-2 px-3 bg-gray-50 rounded-lg">
                    {cfg.stats.map((key, idx) => (
                        <React.Fragment key={key}>
                            {idx > 0 && <div className="w-px h-8 bg-gray-200"></div>}
                            <div className="text-center">
                                <p className="text-lg font-bold text-gray-800">{agent.stats?.[key] ?? '—'}</p>
                                <p className="text-[9px] text-gray-400 uppercase font-semibold">{cfg.statLabels[key]}</p>
                            </div>
                        </React.Fragment>
                    ))}
                </div>

                {/* Progress bar when running */}
                {isRunning && (
                    <div className="mb-4">
                        <div className="flex justify-between text-[10px] text-gray-400 mb-1">
                            <span className="truncate max-w-[180px]">{agent.progress_message || 'Processing...'}</span>
                            <span className={`font-bold text-${cfg.color}-600`}>{agent.progress}%</span>
                        </div>
                        <div className="w-full bg-gray-100 rounded-full h-1.5 overflow-hidden">
                            <div className={`bg-gradient-to-r ${cfg.accent} h-1.5 rounded-full transition-all duration-1000 ease-out`} style={{ width: `${agent.progress}%` }}></div>
                        </div>
                    </div>
                )}

                {/* Last run info */}
                <div className="flex items-center justify-between text-[10px] text-gray-400 mb-4">
                    <span className="flex items-center gap-1">
                        <Clock className="w-3 h-3" />
                        {agent.last_run ? `Last: ${new Date(agent.last_run).toLocaleTimeString()}` : 'Not run yet'}
                    </span>
                    {isCompleted && <span className="font-semibold text-emerald-500">✓ Completed</span>}
                    {isError && <span className="font-semibold text-red-500">✗ Error</span>}
                </div>

                {/* Actions */}
                <div className="flex gap-2 mt-auto">
                    {isIdle || isCompleted || isError ? (
                        <button
                            onClick={() => handleRunAgentClick(agent)}
                            disabled={runningAgent === agent.id || taskList.length === 0}
                            className={`flex-1 inline-flex items-center justify-center gap-1.5 px-3 py-2 text-xs font-bold text-white bg-gradient-to-r ${cfg.accent} rounded-lg shadow-sm hover:shadow-md hover:-translate-y-0.5 transition-all disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:translate-y-0`}
                        >
                            {runningAgent === agent.id ? (<><Loader2 className="w-3 h-3 animate-spin" /> Starting...</>) : (<><Play className="w-3 h-3" /> Run Agent</>)}
                        </button>
                    ) : (
                        <button disabled className="flex-1 inline-flex items-center justify-center gap-1.5 px-3 py-2 text-xs font-bold text-gray-400 bg-gray-100 rounded-lg cursor-not-allowed">
                            <RefreshCw className="w-3 h-3 animate-spin" /> Running...
                        </button>
                    )}
                    <button
                        onClick={() => setShowLogModal(agent.id)}
                        className="inline-flex items-center justify-center gap-1 px-3 py-2 text-xs font-bold text-gray-600 bg-gray-100 rounded-lg hover:bg-gray-200 transition-colors"
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

    // ── Task Auto-Generator Card (Agent 03 — External API) ───────────
    const renderTaskGeneratorCard = () => (
        <div className="bg-white rounded-xl shadow border border-gray-100 p-5 flex flex-col relative overflow-hidden group hover:shadow-lg transition-shadow">
            <div className="absolute top-0 left-0 right-0 h-1 bg-gradient-to-r from-blue-400 to-indigo-500"></div>

            <div className="flex items-start justify-between mb-4">
                <div className="flex items-center gap-3">
                    <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-blue-400 to-indigo-600 flex items-center justify-center shadow-lg shadow-blue-200">
                        <Cpu className="w-5 h-5 text-white" />
                    </div>
                    <div>
                        <h4 className="text-sm font-bold text-gray-900">Task Auto-Generator</h4>
                        <p className="text-[10px] text-gray-400 uppercase tracking-wider font-semibold">AGENT 03</p>
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
                Analyzes BRD Report to auto-generate Projects, Tasks, Epics, Features, and User Stories via AI and external task management API.
            </p>

            <div className="flex items-center gap-4 mb-4 py-2 px-3 bg-gray-50 rounded-lg">
                <div className="text-center">
                    <p className="text-lg font-bold text-gray-800">{generatedTasksCount || '—'}</p>
                    <p className="text-[9px] text-gray-400 uppercase font-semibold">Generated</p>
                </div>
                <div className="w-px h-8 bg-gray-200"></div>
                <div className="text-center">
                    <p className="text-lg font-bold text-blue-600">Auto</p>
                    <p className="text-[9px] text-gray-400 uppercase font-semibold">Mode</p>
                </div>
                <div className="w-px h-8 bg-gray-200"></div>
                <div className="text-center">
                    <p className="text-lg font-bold text-gray-800">API</p>
                    <p className="text-[9px] text-gray-400 uppercase font-semibold">Source</p>
                </div>
            </div>

            {isGeneratingTasks ? (
                <div className="mb-4">
                    <div className="flex justify-between text-[10px] text-gray-400 mb-1">
                        <span>Building tasks from BRD context...</span>
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
                        {generatedTasksCount > 0 ? 'Last run: Just now' : 'Awaiting trigger'}
                    </span>
                    <span className="font-semibold">
                        {generationError ? <span className="text-red-500" title={generationError}>Failed</span> : generatedTasksCount > 0 ? <span className="text-green-500">Success</span> : 'Ready'}
                    </span>
                </div>
            )}

            <div className="flex gap-2 mt-auto">
                <button
                    onClick={handleGenerateTasks}
                    disabled={isGeneratingTasks || !selectedProjectKey}
                    className="flex-1 inline-flex items-center justify-center gap-1.5 px-3 py-2 text-xs font-bold text-white bg-gradient-to-r from-blue-500 to-indigo-600 rounded-lg shadow-sm hover:shadow-md hover:-translate-y-0.5 transition-all disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:translate-y-0"
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

    return (
        <div className="w-full min-h-full bg-gray-50 flex flex-col font-sans overflow-y-auto relative">
            <div className="bg-white shadow">
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

                <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3 px-4 md:px-8 pb-4">
                    {[
                        { label: 'Total Projects', value: projects.length, color: 'text-indigo-600' },
                        { label: 'Documents Analyzed', value: projects.reduce((s, p) => s + (p.totalDocuments || 0), 0), color: 'text-blue-600' },
                        { label: 'Available Tasks', value: taskList.length, color: 'text-orange-600' },
                        { label: 'Agents Active', value: agents.filter(a => a.status === 'running').length, color: 'text-emerald-600' },
                        { label: 'Tasks Generated', value: generatedTasksCount, color: 'text-green-600' },
                        { label: 'External Tasks', value: generatedTasksCount, color: 'text-purple-600' },
                    ].map((metric, i) => (
                        <div key={i} className="bg-gray-50 rounded-xl p-3 flex flex-col items-center justify-center text-center">
                            <span className={`text-2xl font-bold ${metric.color}`}>{metric.value}</span>
                            <span className="text-[9px] font-bold text-gray-400 uppercase tracking-wider mt-0.5">{metric.label}</span>
                        </div>
                    ))}
                </div>
            </div>

            {projects.length === 0 ? (
                <div className="flex-1 flex flex-col items-center justify-center text-center p-12">
                    <div className="w-20 h-20 rounded-full bg-gray-100 flex items-center justify-center mb-4">
                        <Bot className="w-10 h-10 text-gray-300" />
                    </div>
                    <h3 className="text-lg font-bold text-gray-900 mb-2">No projects yet</h3>
                    <p className="text-gray-500 text-sm mb-6">Create your first project to start AI-powered analysis</p>
                    <button onClick={() => setShowModal(true)} className="inline-flex items-center gap-2 px-5 py-3 bg-gradient-to-r from-blue-600 to-indigo-600 text-white font-bold rounded-xl shadow-lg hover:shadow-xl transition-all">
                        <PlusCircle className="w-5 h-5" /> Create Project
                    </button>
                </div>
            ) : (
                <div className="p-4 md:p-6">
                    <div className="mb-6">
                        <div className="flex items-center justify-between mb-4">
                            <div className="flex items-center gap-3">
                                <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-gray-800 to-gray-900 flex items-center justify-center shadow">
                                    <Bot className="w-5 h-5 text-white" />
                                </div>
                                <h3 className="text-[15px] font-bold text-[#f27a24] uppercase tracking-wide">AI Agents</h3>
                                <span className="text-[10px] font-bold text-gray-400 uppercase tracking-wider bg-gray-100 px-2 py-0.5 rounded-full">
                                    {agents.filter(a => a.status === 'running').length} Running
                                </span>
                            </div>
                            <div className="flex items-center gap-2">
                                <span className="text-[10px] font-bold text-gray-400 uppercase tracking-wider bg-orange-50 text-orange-600 px-2.5 py-1 rounded-full">
                                    {taskList.filter(t => (t.taskStatus || '').toLowerCase() !== 'completed').length} Available Tasks
                                </span>
                                <button
                                    onClick={() => { fetchAgents(); fetchExternalTasks(); }}
                                    className="text-gray-400 hover:text-gray-600 p-1 rounded hover:bg-gray-100 transition-colors"
                                    title="Refresh"
                                >
                                    <RefreshCw className="w-4 h-4" />
                                </button>
                            </div>
                        </div>

                        {taskList.length > 0 && (
                            <div className="mb-5 bg-white rounded-xl shadow border border-gray-100 p-4">
                                <h4 className="text-xs font-bold text-gray-500 uppercase tracking-wider mb-3">Tasks Queue (from External API)</h4>
                                <div className="flex gap-2 overflow-x-auto pb-1 scrollbar-hide">
                                    {taskList.filter(t => (t.taskStatus || '').toLowerCase() !== 'completed').slice(0, 5).map((task, idx) => (
                                        <div key={task.id || idx} className="flex-shrink-0 bg-gray-50 border border-gray-100 rounded-lg px-3 py-2 min-w-[200px] max-w-[250px]">
                                            <div className="flex items-center gap-1.5 mb-1">
                                                <span className={`w-1.5 h-1.5 rounded-full ${(task.priority || '').toLowerCase() === 'high' ? 'bg-red-400' : (task.priority || '').toLowerCase() === 'medium' ? 'bg-amber-400' : 'bg-blue-400'}`}></span>
                                                <span className="text-[9px] font-bold text-gray-400 uppercase">{task.priority || 'medium'}</span>
                                            </div>
                                            <p className="text-xs font-medium text-gray-700 truncate">{task.taskName || task.title || 'Untitled'}</p>
                                        </div>
                                    ))}
                                    {taskList.filter(t => (t.taskStatus || '').toLowerCase() !== 'completed').length > 5 && (
                                        <div className="flex-shrink-0 bg-gray-50 border border-gray-100 rounded-lg px-3 py-2 flex items-center">
                                            <span className="text-xs text-gray-400 font-bold">+{taskList.filter(t => (t.taskStatus || '').toLowerCase() !== 'completed').length - 5} more</span>
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
                            <>
                                <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
                                    {agents.filter(a => a.id !== 'agent_03').map(agent => renderAgentCard(agent))}
                                    {renderTaskGeneratorCard()}
                                </div>
                                <p className="text-[10px] text-gray-400 mt-2 italic">Agents fetch tasks live from the external Task API. Each run creates its own isolated Docker container.</p>
                            </>
                        )}
                    </div>
                </div>
            )}

            {/* Agent Output Log Modal */}
            {showLogModal && (() => {
                const agent = agents.find(a => a.id === showLogModal);
                if (!agent) return null;
                const logs = agent.output_log || [];
                const result = agent.last_result;
                return (
                    <div className="fixed inset-0 bg-gray-900/60 backdrop-blur-sm flex items-center justify-center p-4 z-[100] animate-in fade-in duration-200">
                        <div className="bg-gray-900 text-gray-100 rounded-2xl shadow-2xl border border-gray-700 w-full max-w-3xl max-h-[80vh] flex flex-col overflow-hidden animate-in zoom-in-95 duration-200">
                            <div className="px-6 py-4 border-b border-gray-700 flex items-center justify-between bg-gray-800">
                                <div className="flex items-center gap-3">
                                    <Terminal className="w-5 h-5 text-green-400" />
                                    <h3 className="font-bold text-white text-sm">{agent.name} — Execution Log</h3>
                                </div>
                                <button onClick={() => setShowLogModal(null)} className="text-gray-400 hover:text-white p-1 rounded hover:bg-gray-700 transition-colors">
                                    <X className="w-5 h-5" />
                                </button>
                            </div>
                            <div className="flex-1 overflow-y-auto p-4 font-mono text-xs leading-relaxed space-y-0.5">
                                {logs.length === 0 ? (
                                    <p className="text-gray-500 text-center py-8">No logs yet. Run the agent to see output here.</p>
                                ) : logs.map((log, idx) => (
                                    <div key={idx} className={`flex items-start gap-2 ${log.type === 'error' ? 'text-red-400' : log.type === 'output' ? 'text-green-300' : 'text-blue-300'}`}>
                                        <span className="text-gray-600 flex-shrink-0 select-none">[{log.type}]</span>
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
                                        <pre className="px-4 py-3 overflow-x-auto text-[10px] text-blue-200 bg-gray-950 max-h-60 overflow-y-auto whitespace-pre-wrap">
                                            {result.builder_scripts}
                                        </pre>
                                    </details>
                                </div>
                            )}
                        </div>
                    </div>
                );
            })()}

            {/* Generated Tasks Section (from External API) */}
            {projects.length > 0 && (
                <div className="px-4 md:px-6 pb-6">
                    <div className="bg-white rounded-2xl shadow-sm border border-gray-100 overflow-hidden">
                        <div className="px-6 py-4 border-b border-gray-100 flex items-center justify-between bg-gradient-to-r from-gray-50/80 to-white">
                            <div className="flex items-center gap-3">
                                <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center shadow-lg shadow-indigo-200">
                                    <ListTodo className="w-4 h-4 text-white" />
                                </div>
                                <div>
                                    <h3 className="text-sm font-bold text-gray-900">Generated Tasks</h3>
                                    <p className="text-[10px] text-gray-400 uppercase tracking-wider font-semibold">
                                        {taskList.length} task{taskList.length !== 1 ? 's' : ''} from AI Auto-Generator
                                    </p>
                                </div>
                            </div>
                            <button onClick={fetchExternalTasks} disabled={isLoadingTasks} className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold text-gray-500 bg-gray-50 border border-gray-200 rounded-lg hover:bg-gray-100 hover:text-gray-700 transition-all disabled:opacity-50">
                                <RefreshCw className={`w-3 h-3 ${isLoadingTasks ? 'animate-spin' : ''}`} /> Refresh
                            </button>
                        </div>

                        <div className="divide-y divide-gray-50">
                            {isLoadingTasks && taskList.length === 0 && (
                                <div className="p-8 flex flex-col items-center justify-center gap-3">
                                    <RefreshCw className="w-6 h-6 text-indigo-400 animate-spin" />
                                    <p className="text-sm text-gray-400 font-medium">Loading tasks...</p>
                                </div>
                            )}
                            {taskListError && !isLoadingTasks && (
                                <div className="p-6 flex items-center gap-3 bg-red-50/50">
                                    <AlertCircle className="w-5 h-5 text-red-400 flex-shrink-0" />
                                    <p className="text-sm text-red-600 font-medium">{taskListError}</p>
                                </div>
                            )}
                            {!isLoadingTasks && !taskListError && taskList.length === 0 && (
                                <div className="p-10 flex flex-col items-center justify-center gap-2 text-center">
                                    <div className="w-14 h-14 bg-gray-50 rounded-full flex items-center justify-center mb-2">
                                        <ListTodo className="w-7 h-7 text-gray-300" />
                                    </div>
                                    <p className="text-sm font-bold text-gray-500">No tasks generated yet</p>
                                    <p className="text-xs text-gray-400 max-w-xs">Select a project and click "Create Tasks" on the Task Auto-Generator agent above to get started.</p>
                                </div>
                            )}
                            {!isLoadingTasks && taskList.length > 0 && taskList.map((task, index) => {
                                const priorityStyles = { high: 'bg-red-50 text-red-700 border-red-200', medium: 'bg-amber-50 text-amber-700 border-amber-200', low: 'bg-green-50 text-green-700 border-green-200' };
                                const typeStyles = { EPIC: 'bg-purple-100 text-purple-700', FEATURE: 'bg-blue-100 text-blue-700', STORY: 'bg-cyan-100 text-cyan-700', TASK: 'bg-gray-100 text-gray-700', BUG: 'bg-red-100 text-red-700' };
                                const statusStyles = { 'On Going': 'bg-blue-50 text-blue-700', 'Completed': 'bg-green-50 text-green-700', 'To Do': 'bg-gray-50 text-gray-600', 'In Review': 'bg-amber-50 text-amber-700', 'Blocked': 'bg-red-50 text-red-700' };
                                const priority = (task.priority || 'medium').toLowerCase();
                                const taskType = (task.task_type || 'TASK').toUpperCase();
                                const progress = task.task_progress || 0;
                                const progressColor = progress >= 80 ? 'bg-green-500' : progress >= 40 ? 'bg-blue-500' : 'bg-amber-500';

                                return (
                                    <div key={task.id || index} className="px-6 py-4 hover:bg-gray-50/70 transition-colors group">
                                        <div className="flex items-center gap-4">
                                            <div className="flex items-center gap-1.5 flex-shrink-0">
                                                <div className="w-7 h-7 rounded-lg bg-gray-100 flex items-center justify-center">
                                                    <span className="text-[10px] font-bold text-gray-500">{index + 1}</span>
                                                </div>
                                                {task.is_flaged && <Flag className="w-3.5 h-3.5 text-orange-400 fill-orange-400" />}
                                            </div>
                                            <div className="flex-1 min-w-0">
                                                <div className="flex items-center gap-2 mb-0.5">
                                                    <h4 className="text-sm font-semibold text-gray-900 truncate">{task.taskName || 'Untitled Task'}</h4>
                                                    <span className={`inline-flex items-center px-1.5 py-0.5 rounded text-[9px] font-bold uppercase tracking-wide flex-shrink-0 ${typeStyles[taskType] || typeStyles.TASK}`}>{taskType}</span>
                                                    {task.is_completed && <CheckCircle className="w-3.5 h-3.5 text-green-500 flex-shrink-0" />}
                                                </div>
                                                <p className="text-xs text-gray-400 truncate max-w-md">{task.description || 'No description'}</p>
                                            </div>
                                            <div className="flex-shrink-0 hidden lg:block">
                                                <span className={`inline-flex items-center px-2 py-0.5 rounded-md text-[10px] font-bold ${statusStyles[task.taskStatus] || 'bg-gray-50 text-gray-600'}`}>{task.taskStatus || 'Unknown'}</span>
                                            </div>
                                            <div className="flex-shrink-0">
                                                <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-bold border capitalize ${priorityStyles[priority] || priorityStyles.medium}`}>{priority}</span>
                                            </div>
                                            <div className="flex-shrink-0 hidden md:flex items-center gap-1" title={`Assigned to: ${(task.assignedTo || []).join(', ')}`}>
                                                <Users className="w-3.5 h-3.5 text-gray-400" />
                                                <div className="flex items-center gap-0.5">
                                                    {(task.assignedTo || []).map((name, i) => (
                                                        <span key={i} className="inline-flex items-center px-1.5 py-0.5 bg-indigo-50 text-indigo-700 rounded text-[9px] font-semibold">{name}</span>
                                                    ))}
                                                </div>
                                            </div>
                                            <div className="flex-shrink-0 flex items-center gap-1" title={`Wallet: ${task.task_wallet || 0}`}>
                                                <Wallet className="w-3.5 h-3.5 text-gray-400" />
                                                <span className="text-[10px] font-semibold text-gray-500">{task.task_wallet || 0}</span>
                                            </div>
                                            <div className="flex-shrink-0 hidden md:flex items-center gap-1.5 text-[10px]">
                                                <Calendar className="w-3 h-3 text-gray-400" />
                                                <span className="text-gray-400">{task.deadline || '-'}</span>
                                                {task.days_left != null && (
                                                    <span className={`font-bold px-1.5 py-0.5 rounded-full ${task.days_left <= 3 ? 'bg-red-50 text-red-600' : task.days_left <= 7 ? 'bg-amber-50 text-amber-600' : 'bg-green-50 text-green-600'}`}>{task.days_left}d left</span>
                                                )}
                                            </div>
                                        </div>
                                        <div className="mt-2 ml-[38px] flex items-center gap-3">
                                            <div className="flex-1 bg-gray-100 rounded-full h-1.5 overflow-hidden max-w-[200px]">
                                                <div className={`${progressColor} h-1.5 rounded-full transition-all duration-500`} style={{ width: `${Math.min(progress, 100)}%` }}></div>
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
                            <button type="button" onClick={() => setShowModal(false)} className="text-gray-400 hover:text-gray-700 hover:bg-gray-100 p-1.5 rounded-full transition-colors">
                                <X className="w-5 h-5" />
                            </button>
                        </div>
                        <div className="p-6">
                            <p className="text-sm text-gray-500 mb-4 font-medium">Step 1 of Governance Track: Give your project a descriptive name to get started.</p>
                            <label className="block text-[11px] font-bold text-gray-500 mb-2 uppercase tracking-widest">Project Name <span className="text-red-400">*</span></label>
                            <input type="text" value={newProjectName} onChange={(e) => setNewProjectName(e.target.value)} autoFocus onKeyDown={(e) => e.key === 'Enter' && handleCreateProject()} placeholder="e.g. Customer Analytics Platform" className="w-full px-4 py-3 border-2 border-gray-200 rounded-xl focus:ring-4 focus:ring-blue-100 focus:border-blue-400 text-sm bg-gray-50/50 text-gray-900 transition-all duration-200 placeholder:text-gray-300 font-medium mb-6" />
                            <div className="flex items-center gap-3">
                                <button type="button" onClick={() => setShowModal(false)} className="flex-1 py-3 px-4 font-bold text-gray-600 bg-gray-50 hover:bg-gray-100 border border-gray-200 rounded-xl transition-colors">Cancel</button>
                                <button type="button" onClick={handleCreateProject} disabled={!newProjectName.trim()} className="flex-1 py-3 px-4 font-bold text-white bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-700 hover:to-indigo-700 rounded-xl transition-colors shadow-lg shadow-blue-500/30 hover:shadow-blue-500/50 disabled:opacity-50 disabled:cursor-not-allowed flex justify-center items-center gap-2 group">
                                    Start track <ArrowRight className="w-4 h-4 group-hover:translate-x-1 transition-transform" />
                                </button>
                            </div>
                        </div>
                    </div>
                </div>
            )}

            {/* Git Configuration Modal */}
            {gitModalAgent && (
                <div className="fixed inset-0 bg-gray-900/50 backdrop-blur-sm flex items-center justify-center p-4 z-[100] animate-in fade-in duration-200">
                    <div className="bg-white rounded-2xl shadow-xl border border-gray-100 w-full max-w-md overflow-hidden animate-in zoom-in-95 duration-200">
                        <div className="px-6 py-5 border-b border-gray-100 flex items-center justify-between bg-gradient-to-r from-gray-50 to-white">
                            <h3 className="font-bold text-gray-900 text-lg flex items-center gap-2">
                                <Bot className="w-5 h-5 text-indigo-500" /> Git Configuration
                            </h3>
                            <button type="button" onClick={() => setGitModalAgent(null)} className="text-gray-400 hover:text-gray-700 hover:bg-gray-100 p-1.5 rounded-full transition-colors">
                                <X className="w-5 h-5" />
                            </button>
                        </div>
                        <div className="p-6">
                            <p className="text-sm text-gray-500 mb-4 font-medium">To run <b>{gitModalAgent.name}</b>, please provide a Git repository where the agent can push its work.</p>

                            <label className="block text-[11px] font-bold text-gray-500 mb-2 uppercase tracking-widest">Git Repository URL <span className="text-red-400">*</span></label>
                            <input type="text" value={gitRepoUrl} onChange={(e) => setGitRepoUrl(e.target.value)} placeholder="https://github.com/org/repo.git" className="w-full px-4 py-3 border-2 border-gray-200 rounded-xl focus:ring-4 focus:ring-indigo-100 focus:border-indigo-400 text-sm bg-gray-50/50 text-gray-900 transition-all duration-200 placeholder:text-gray-300 font-medium mb-4" />

                            <label className="block text-[11px] font-bold text-gray-500 mb-2 uppercase tracking-widest">Personal Access Token (optional)</label>
                            <input type="password" value={gitToken} onChange={(e) => setGitToken(e.target.value)} placeholder="ghp_..." className="w-full px-4 py-3 border-2 border-gray-200 rounded-xl focus:ring-4 focus:ring-indigo-100 focus:border-indigo-400 text-sm bg-gray-50/50 text-gray-900 transition-all duration-200 placeholder:text-gray-300 font-medium mb-6" />
                            <p className="text-xs text-gray-400 mb-6 italic">This token is used by the Docker container to clone and push code. It is securely handled and forgotten if the container crashes.</p>

                            <div className="flex items-center gap-3">
                                <button type="button" onClick={() => setGitModalAgent(null)} className="flex-1 py-3 px-4 font-bold text-gray-600 bg-gray-50 hover:bg-gray-100 border border-gray-200 rounded-xl transition-colors">Cancel</button>
                                <button type="button" onClick={() => handleRunAgent(gitModalAgent.id, gitRepoUrl, gitToken)} disabled={!gitRepoUrl.trim()} className="flex-1 py-3 px-4 font-bold text-white bg-gradient-to-r from-indigo-600 to-blue-600 hover:from-indigo-700 hover:to-blue-700 rounded-xl transition-colors shadow-lg shadow-indigo-500/30 hover:shadow-indigo-500/50 disabled:opacity-50 disabled:cursor-not-allowed flex justify-center items-center gap-2 group">
                                    <Play className="w-4 h-4" /> Start Agent
                                </button>
                            </div>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}
