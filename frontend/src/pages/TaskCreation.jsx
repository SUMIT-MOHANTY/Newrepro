import { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
    ArrowRight,
    CalendarDays,
    CheckCircle2,
    Flag,
    FolderKanban,
    Loader2,
    Milestone,
    RefreshCw,
    Sparkles,
} from 'lucide-react';
import { API_ENDPOINTS } from '../config';

const TASK_TOKEN_STORAGE_KEY = 'status_dashboard_task_token_cache';
const TOKEN_REFRESH_THRESHOLD_SECONDS = 300;

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

function getCachedTaskToken(projectKey) {
    if (!projectKey) return null;
    const cache = readTaskTokenCache();
    const entry = cache[projectKey];
    if (!entry || !entry.token) return null;
    if (entry.expiresAt) {
        const now = Math.floor(Date.now() / 1000);
        if (entry.expiresAt <= now) {
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

function formatDate(dateValue) {
    const d = new Date(dateValue);
    if (Number.isNaN(d.getTime())) return '';
    return d.toISOString().slice(0, 10);
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

function getErrorMessage(errorPayload, fallback) {
    if (!errorPayload) return fallback;
    if (typeof errorPayload.detail === 'string') return errorPayload.detail;
    if (typeof errorPayload.error === 'string') return errorPayload.error;
    return fallback;
}

export default function TaskCreation({
    projects = [],
    selectedProjectKey,
    fetchRoadmapData,
}) {
    const navigate = useNavigate();
    const token = localStorage.getItem('token');

    const [taskToken, setTaskToken] = useState(null);
    const [taskTokenProjectKey, setTaskTokenProjectKey] = useState(null);
    const hasValidTaskToken = Boolean(taskToken) && taskTokenProjectKey === selectedProjectKey;

    const [projectDeadline, setProjectDeadline] = useState('');
    const [sprints, setSprints] = useState([]);
    const [milestones, setMilestones] = useState([]);
    const [tasks, setTasks] = useState([]);
    const [isLoading, setIsLoading] = useState(false);
    const [isGenerating, setIsGenerating] = useState(false);
    const [error, setError] = useState('');
    const [success, setSuccess] = useState('');

    const selectedProject = useMemo(
        () => projects.find((p) => p.key === selectedProjectKey) || null,
        [projects, selectedProjectKey]
    );
    const hasProjectCredentials = Boolean(selectedProject?.client_id && selectedProject?.client_secret);

    useEffect(() => {
        if (!selectedProjectKey) return;
        const cached = getCachedTaskToken(selectedProjectKey);
        if (cached?.token) {
            setTaskToken(cached.token);
            setTaskTokenProjectKey(selectedProjectKey);
        } else {
            setTaskToken(null);
            setTaskTokenProjectKey(null);
        }
    }, [selectedProjectKey]);

    useEffect(() => {
        let isMounted = true;
        const fetchTaskToken = async () => {
            if (!selectedProjectKey || !selectedProject) return;

            const clientId = selectedProject.client_id;
            const clientSecret = selectedProject.client_secret;
            if (!clientId || !clientSecret) return;

            const cached = getCachedTaskToken(selectedProjectKey);
            const shouldRefresh =
                !cached?.token ||
                !cached?.expiresAt ||
                (cached.expiresAt - Math.floor(Date.now() / 1000)) <= TOKEN_REFRESH_THRESHOLD_SECONDS;
            if (!shouldRefresh) return;

            try {
                const res = await fetch(API_ENDPOINTS.TASK_TOKEN, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ client_id: clientId, client_secret: clientSecret }),
                });
                if (!res.ok) return;
                const data = await res.json();
                if (!isMounted) return;
                setTaskToken(data.access);
                setTaskTokenProjectKey(selectedProjectKey);
                cacheTaskToken(selectedProjectKey, data.access);
            } catch {
                // Ignore token refresh failures; user can retry.
            }
        };

        fetchTaskToken();
        return () => {
            isMounted = false;
        };
    }, [selectedProjectKey, selectedProject]);

    const buildHeaders = useCallback(() => {
        const headers = { Authorization: `Bearer ${token}` };
        if (hasValidTaskToken) headers['x-task-token'] = taskToken;
        return headers;
    }, [token, hasValidTaskToken, taskToken]);

    const loadData = useCallback(async () => {
        if (!selectedProjectKey || !hasValidTaskToken) return;
        setIsLoading(true);
        setError('');
        try {
            const headers = buildHeaders();
            const [sprintRes, milestoneRes, taskRes, projectInfoRes] = await Promise.all([
                fetch(API_ENDPOINTS.AGENT_SPRINTS, { headers }),
                fetch(API_ENDPOINTS.AGENT_MILESTONES, { headers }),
                fetch(API_ENDPOINTS.AGENT_TASKS, { headers }),
                fetch(API_ENDPOINTS.AGENT_PROJECT_INFO, { headers }),
            ]);

            const sprintData = sprintRes.ok ? await sprintRes.json() : { sprints: [] };
            const milestoneData = milestoneRes.ok ? await milestoneRes.json() : { milestones: [] };
            const taskData = taskRes.ok ? await taskRes.json() : { results: [] };
            const projectInfoData = projectInfoRes.ok ? await projectInfoRes.json() : {};

            setSprints(Array.isArray(sprintData?.sprints) ? sprintData.sprints : []);
            setMilestones(Array.isArray(milestoneData?.milestones) ? milestoneData.milestones : []);
            if (Array.isArray(taskData)) {
                setTasks(taskData);
            } else if (Array.isArray(taskData?.results)) {
                setTasks(taskData.results);
            } else {
                setTasks([]);
            }

            const deadline = projectInfoData?.project?.deadline;
            if (deadline) {
                const normalized = formatDate(deadline);
                setProjectDeadline(normalized);
            }
        } catch (e) {
            setError(e?.message || 'Failed to load sprint/milestone/task data');
        } finally {
            setIsLoading(false);
        }
    }, [selectedProjectKey, hasValidTaskToken, buildHeaders]);

    useEffect(() => {
        loadData();
    }, [loadData]);

    const groupedTasks = useMemo(() => {
        const sprintById = new Map(sprints.map((s) => [String(s.id), s]));
        const milestoneById = new Map(milestones.map((m) => [String(m.id), m]));
        const groups = new Map();

        tasks.forEach((task) => {
            const sprintId = extractEntityId(task, 'sprint');
            const milestoneId = extractEntityId(task, 'milestone');
            const sprintKey = sprintId != null ? String(sprintId) : 'unassigned_sprint';
            const milestoneKey = milestoneId != null ? String(milestoneId) : 'unassigned_milestone';

            if (!groups.has(sprintKey)) {
                groups.set(sprintKey, {
                    sprint: sprintId != null
                        ? (sprintById.get(String(sprintId)) || { id: sprintId, name: `Sprint #${sprintId}` })
                        : { id: 'unassigned_sprint', name: 'Unassigned Sprint' },
                    milestones: new Map(),
                });
            }

            const sprintGroup = groups.get(sprintKey);
            if (!sprintGroup.milestones.has(milestoneKey)) {
                sprintGroup.milestones.set(milestoneKey, {
                    milestone: milestoneId != null
                        ? (milestoneById.get(String(milestoneId)) || { id: milestoneId, name: `Milestone #${milestoneId}` })
                        : { id: 'unassigned_milestone', name: 'Unassigned Milestone' },
                    tasks: [],
                });
            }

            sprintGroup.milestones.get(milestoneKey).tasks.push(task);
        });

        return Array.from(groups.values());
    }, [tasks, sprints, milestones]);

    const handleMasterCreate = async () => {
        if (!selectedProjectKey) {
            setError('Select a project before creating tasks.');
            return;
        }
        if (!hasValidTaskToken) {
            setError('Task token is not ready. Please wait and try again.');
            return;
        }

        setIsGenerating(true);
        setError('');
        setSuccess('');

        try {
            const headers = {
                ...buildHeaders(),
                'Content-Type': 'application/json',
            };

            let prerequisites = null;
            try {
                const saved = localStorage.getItem(`prerequisites_completed_${selectedProjectKey}`);
                if (saved) {
                    const parsed = JSON.parse(saved);
                    prerequisites = Array.isArray(parsed?.items) ? parsed.items : null;
                }
            } catch {
                prerequisites = null;
            }

            const generatePayload = {
                project_token: selectedProjectKey,
                auto_create_plan: true,
            };
            if (prerequisites && prerequisites.length > 0) {
                generatePayload.prerequisites = prerequisites;
            }

            const generateRes = await fetch(API_ENDPOINTS.AGENT_AUTO_GENERATE, {
                method: 'POST',
                headers,
                body: JSON.stringify(generatePayload),
            });
            const generateJson = await generateRes.json().catch(() => ({}));
            if (!generateRes.ok) {
                throw new Error(getErrorMessage(generateJson, 'Failed to auto-generate tasks'));
            }

            const createdCount = generateJson?.tasks_created ?? 0;
            const createdSprintName =
                generateJson?.created_sprint?.name || generateJson?.created_sprint?.sprint?.name || null;
            const createdMilestoneName =
                generateJson?.created_milestone?.name || generateJson?.created_milestone?.milestone?.name || null;
            const backendMessage =
                typeof generateJson?.message === 'string' ? generateJson.message : '';

            if (createdSprintName && createdMilestoneName) {
                setSuccess(
                    `AI created sprint "${createdSprintName}", milestone "${createdMilestoneName}", and ${createdCount} task(s).`
                );
            } else if (backendMessage) {
                setSuccess(backendMessage);
            } else {
                setSuccess(`Created ${createdCount} task(s).`);
            }
            await loadData();
            if (fetchRoadmapData) await fetchRoadmapData(selectedProjectKey);
        } catch (e) {
            setError(e?.message || 'Task creation failed');
        } finally {
            setIsGenerating(false);
        }
    };

    return (
        <div className="h-full overflow-y-auto bg-gradient-to-br from-slate-50 via-gray-50 to-blue-50/30">
            <div className="max-w-6xl mx-auto px-4 py-6 space-y-6">
                <div className="bg-white rounded-2xl border border-app-border-light shadow-sm p-5">
                    <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4">
                        <div>
                            <p className="text-xs font-semibold uppercase tracking-widest text-app-text-muted">Master Agent Planner</p>
                            <h2 className="text-2xl font-extrabold text-app-text-main mt-1">Create Sprint, Milestone, and Tasks</h2>
                            <p className="text-sm text-app-text-muted mt-2">
                                Project: <span className="font-semibold text-app-text-main">{selectedProject?.name || 'Not selected'}</span>
                            </p>
                        </div>
                        <button
                            onClick={() => navigate('/status-dashboard')}
                            className="inline-flex items-center gap-2 px-5 py-2.5 text-sm font-bold text-white bg-gradient-to-r from-emerald-500 to-green-600 rounded-lg shadow hover:shadow-lg transition-all"
                        >
                            Go to Status Dashboard
                            <ArrowRight className="w-4 h-4" />
                        </button>
                    </div>
                </div>

                <div className="bg-white rounded-2xl border border-app-border-light shadow-sm p-5 space-y-4">
                    <h3 className="text-sm font-bold text-app-text-main flex items-center gap-2">
                        <FolderKanban className="w-4 h-4 text-blue-600" />
                        AI Planning
                    </h3>
                    <p className="text-sm text-app-text-muted">
                        Master Agent will automatically create a sprint, create a milestone inside it, then generate tasks under that milestone.
                    </p>
                    <div className="text-xs text-app-text-muted bg-app-bg-muted rounded-lg px-3 py-2 border border-app-border-light">
                        Project deadline: <span className="font-semibold text-app-text-main">{projectDeadline || 'Not available'}</span>
                    </div>
                    <button
                        onClick={handleMasterCreate}
                        disabled={!selectedProjectKey || !hasProjectCredentials || !hasValidTaskToken || isGenerating}
                        className={`w-full inline-flex items-center justify-center gap-2 px-4 py-3 rounded-lg font-bold text-sm transition-colors ${
                            (!selectedProjectKey || !hasProjectCredentials || !hasValidTaskToken || isGenerating)
                                ? 'bg-gray-300 text-gray-500 cursor-not-allowed'
                                : 'bg-gradient-to-r from-blue-600 to-indigo-600 text-white hover:from-blue-700 hover:to-indigo-700'
                        }`}
                    >
                        {isGenerating ? <Loader2 className="w-4 h-4 animate-spin" /> : <Sparkles className="w-4 h-4" />}
                        {isGenerating ? 'Creating Plan...' : 'Create Tasks (AI Auto Plan)'}
                    </button>
                    {!selectedProjectKey && (
                        <p className="text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2">
                            No project selected. Select a project from the sidebar or top project dropdown.
                        </p>
                    )}
                    {selectedProjectKey && !hasProjectCredentials && (
                        <p className="text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2">
                            Task API credentials are missing for this project. Open the project in Dashboard and ensure external project credentials are configured.
                        </p>
                    )}
                    {selectedProjectKey && hasProjectCredentials && !hasValidTaskToken && (
                        <p className="text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2">
                            Loading task token for the selected project...
                        </p>
                    )}
                    {error && (
                        <p className="text-xs text-red-700 bg-red-50 border border-red-200 rounded-lg px-3 py-2">{error}</p>
                    )}
                    {success && (
                        <p className="text-xs text-emerald-700 bg-emerald-50 border border-emerald-200 rounded-lg px-3 py-2 flex items-start gap-2">
                            <CheckCircle2 className="w-4 h-4 mt-0.5 shrink-0" />
                            <span>{success}</span>
                        </p>
                    )}
                </div>

                <div className="bg-white rounded-2xl border border-app-border-light shadow-sm p-5">
                    <div className="flex items-center justify-between mb-4">
                        <h3 className="text-sm font-bold text-app-text-main">Tasks Grouped by Sprint / Milestone</h3>
                        <button
                            onClick={loadData}
                            disabled={isLoading}
                            className="inline-flex items-center gap-2 px-3 py-2 rounded-lg text-xs font-bold bg-app-bg-muted text-app-text-main hover:bg-app-bg-hover"
                        >
                            {isLoading ? <Loader2 className="w-3 h-3 animate-spin" /> : <RefreshCw className="w-3 h-3" />}
                            Refresh
                        </button>
                    </div>

                    {isLoading ? (
                        <div className="py-10 text-center text-sm text-app-text-muted">Loading sprint and task data...</div>
                    ) : groupedTasks.length === 0 ? (
                        <div className="py-10 text-center text-sm text-app-text-muted">No tasks found yet.</div>
                    ) : (
                        <div className="space-y-4">
                            {groupedTasks.map((sprintGroup) => (
                                <div key={`s-${sprintGroup.sprint.id}`} className="border border-app-border rounded-xl overflow-hidden">
                                    <div className="px-4 py-3 bg-blue-50 border-b border-app-border-light flex items-center gap-3">
                                        <FolderKanban className="w-4 h-4 text-blue-700" />
                                        <p className="text-sm font-bold text-blue-900">{sprintGroup.sprint.name}</p>
                                    </div>
                                    <div className="p-4 space-y-3">
                                        {Array.from(sprintGroup.milestones.values()).map((milestoneGroup) => (
                                            <div key={`m-${milestoneGroup.milestone.id}`} className="border border-app-border rounded-lg">
                                                <div className="px-3 py-2 bg-violet-50 border-b border-app-border-light flex items-center gap-2">
                                                    <Milestone className="w-4 h-4 text-violet-700" />
                                                    <p className="text-xs font-bold text-violet-900">{milestoneGroup.milestone.name}</p>
                                                </div>
                                                <div className="p-3 space-y-2">
                                                    {milestoneGroup.tasks.map((task) => (
                                                        <div key={task.id || task.taskName} className="border border-app-border rounded-lg px-3 py-2 bg-white">
                                                            <p className="text-sm font-semibold text-app-text-main">{task.taskName || task.title || 'Untitled Task'}</p>
                                                            <div className="mt-1 flex flex-wrap items-center gap-3 text-xs text-app-text-muted">
                                                                <span className="inline-flex items-center gap-1">
                                                                    <Flag className="w-3 h-3" />
                                                                    {task.priority || 'medium'}
                                                                </span>
                                                                <span className="inline-flex items-center gap-1">
                                                                    <CalendarDays className="w-3 h-3" />
                                                                    {task.deadline || 'No deadline'}
                                                                </span>
                                                            </div>
                                                        </div>
                                                    ))}
                                                </div>
                                            </div>
                                        ))}
                                    </div>
                                </div>
                            ))}
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
}
