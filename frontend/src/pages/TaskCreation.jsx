import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
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

const PLAN_CREATION_STEPS = ['Creating Sprint', 'Creating Milestone', 'Creating Tasks'];
const PROCESS_MODE_STORAGE_KEY = 'status_dashboard_process_mode_map';
const GENERATED_TASK_PLAN_STORAGE_KEY_PREFIX = 'task_creation_generated_plan_';
const TASK_TOKEN_STORAGE_KEY = 'status_dashboard_task_token_cache';

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

function getCachedTaskToken(projectKey) {
    if (!projectKey) return null;
    const cache = readTaskTokenCache();
    const entry = cache[projectKey];
    if (!entry || !entry.token) return null;
    if (entry.expiresAt) {
        const now = Math.floor(Date.now() / 1000);
        if (entry.expiresAt <= now) {
            delete cache[projectKey];
            localStorage.setItem(TASK_TOKEN_STORAGE_KEY, JSON.stringify(cache));
            return null;
        }
    }
    return entry.token;
}

function cacheTaskToken(projectKey, token) {
    if (!projectKey || !token) return;
    const cache = readTaskTokenCache();
    cache[projectKey] = {
        token,
        expiresAt: decodeJwtExpiry(token),
    };
    localStorage.setItem(TASK_TOKEN_STORAGE_KEY, JSON.stringify(cache));
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

function readGeneratedTaskPlan(projectKey) {
    if (!projectKey) return null;
    try {
        const raw = localStorage.getItem(`${GENERATED_TASK_PLAN_STORAGE_KEY_PREFIX}${projectKey}`);
        if (!raw) return null;
        const parsed = JSON.parse(raw);
        return parsed && typeof parsed === 'object' ? parsed : null;
    } catch {
        return null;
    }
}

function writeGeneratedTaskPlan(projectKey, payload) {
    if (!projectKey || !payload) return;
    try {
        localStorage.setItem(
            `${GENERATED_TASK_PLAN_STORAGE_KEY_PREFIX}${projectKey}`,
            JSON.stringify(payload)
        );
    } catch {
        // Ignore storage errors.
    }
}

function formatCsvCell(value) {
    const text = String(value ?? '');
    return `"${text.replace(/"/g, '""')}"`;
}

function buildTaskPreviewCsv(tasks) {
    if (!Array.isArray(tasks) || tasks.length === 0) return '';

    const columns = [
        'project_id',
        'project_name',
        'task_id',
        'parent_id',
        'type',
        'title',
        'description',
        'status',
        'priority',
        'story_points',
        'sprint_id',
        'sprint_name',
        'milestone_id',
        'reporter',
        'assignee',
        'resource_names',
        'planned_start',
        'planned_end',
        'estimated_hours',
        'wbs',
        'level',
        'dependencies',
        'checklists',
    ];

    const lines = [columns.map(formatCsvCell).join(',')];

    tasks.forEach((task) => {
        const row = columns.map((column) => {
            const value = task?.[column];

            if (column === 'resource_names' && Array.isArray(value)) {
                return formatCsvCell(value.join(' | '));
            }
            if (column === 'dependencies' && Array.isArray(value)) {
                return formatCsvCell(value.join(' | '));
            }
            if (column === 'checklists' && Array.isArray(value)) {
                const flattened = value.map((checklist) => {
                    const title = String(checklist?.title || '').trim();
                    const items = Array.isArray(checklist?.items)
                        ? checklist.items.map((item) => {
                            if (item && typeof item === 'object') {
                                const text = String(item.text || item.title || '').trim();
                                return text ? `${text}${item.completed ? ' [done]' : ''}` : '';
                            }
                            return String(item || '').trim();
                        }).filter(Boolean).join(' | ')
                        : '';
                    return title ? `${title}: ${items}` : items;
                }).join(' || ');
                return formatCsvCell(flattened);
            }
            return formatCsvCell(value ?? '');
        });
        lines.push(row.join(','));
    });

    return lines.join('\n');
}

function getPreviewJsonForDisplay(previewJson) {
    if (Array.isArray(previewJson)) {
        return previewJson.map((task) => {
            if (!task || typeof task !== 'object') {
                return task;
            }

            const rawChecklist = task.checklist;
            if (typeof rawChecklist !== 'string' || !rawChecklist.trim()) {
                return task;
            }

            try {
                const parsedChecklist = JSON.parse(rawChecklist);
                return {
                    ...task,
                    checklist: parsedChecklist,
                };
            } catch {
                return task;
            }
        });
    }

    if (!previewJson || typeof previewJson !== 'object') {
        return previewJson;
    }

    const tasks = Array.isArray(previewJson.tasks) ? previewJson.tasks : [];
    return {
        ...previewJson,
        tasks: tasks.map((task) => {
            if (!task || typeof task !== 'object') {
                return task;
            }

            const rawChecklist = task.checklist;
            if (typeof rawChecklist !== 'string' || !rawChecklist.trim()) {
                return task;
            }

            try {
                const parsedChecklist = JSON.parse(rawChecklist);
                return {
                    ...task,
                    checklist: parsedChecklist,
                };
            } catch {
                return task;
            }
        }),
    };
}


export default function TaskCreation({
    projects = [],
    selectedProjectKey,
}) {
    const navigate = useNavigate();
    const location = useLocation();
    const token = localStorage.getItem('token');

    const [hasCompletedInitialBootstrap, setHasCompletedInitialBootstrap] = useState(false);

    const [projectDeadline, setProjectDeadline] = useState('');
    const [sprints, setSprints] = useState([]);
    const [milestones, setMilestones] = useState([]);
    const [tasks, setTasks] = useState([]);
    const [generatedTaskPlan, setGeneratedTaskPlan] = useState(null);
    const [taskTotalCount, setTaskTotalCount] = useState(0);
    const [isLoading, setIsLoading] = useState(false);
    const [isGenerating, setIsGenerating] = useState(false);
    const [error, setError] = useState('');
    const [success, setSuccess] = useState('');
    const [creationStageIndex, setCreationStageIndex] = useState(0);
    const [liveCreatedTaskCount, setLiveCreatedTaskCount] = useState(0);
    const autoStartRunKeysRef = useRef(new Set());
    const [customRules, setCustomRules] = useState(() => {
        if (selectedProjectKey) {
            return localStorage.getItem(`custom_rules_${selectedProjectKey}`) || '';
        }
        return '';
    });

    const selectedProject = useMemo(
        () => projects.find((p) => p.key === selectedProjectKey) || null,
        [projects, selectedProjectKey]
    );

    const processMode = useMemo(() => {
        const map = readProcessModeMap();
        return selectedProjectKey ? map[selectedProjectKey] || 'ai_first' : 'ai_first';
    }, [selectedProjectKey]);

    const previewJson = useMemo(() => {
        if (Array.isArray(generatedTaskPlan?.preview_json)) {
            return generatedTaskPlan.preview_json;
        }
        if (generatedTaskPlan?.preview_json && typeof generatedTaskPlan.preview_json === 'object') {
            return generatedTaskPlan.preview_json;
        }
        return Array.isArray(generatedTaskPlan?.tasks) ? generatedTaskPlan.tasks : [];
    }, [generatedTaskPlan]);

    const previewJsonForDisplay = useMemo(
        () => getPreviewJsonForDisplay(previewJson),
        [previewJson]
    );

    const previewCsv = useMemo(
        () => buildTaskPreviewCsv(Array.isArray(previewJson) ? previewJson : (Array.isArray(previewJson?.tasks) ? previewJson.tasks : [])),
        [previewJson]
    );

    const hydrateGeneratedPlan = useCallback((payload) => {
        const nextPayload = payload && typeof payload === 'object' ? payload : null;
        const nextTasks = Array.isArray(nextPayload?.tasks) ? nextPayload.tasks : [];
        const nextSprints = Array.isArray(nextPayload?.sprints) ? nextPayload.sprints : [];
        const nextMilestones = Array.isArray(nextPayload?.milestones) ? nextPayload.milestones : [];

        setGeneratedTaskPlan(nextPayload);
        setTasks(nextTasks);
        setTaskTotalCount(nextTasks.length);
        setSprints(
            nextSprints.map((sprint) => ({
                ...sprint,
                id: sprint.id || sprint.sprint_id,
                name: sprint.name || sprint.sprint_name || 'Sprint',
            }))
        );
        setMilestones(
            nextMilestones.map((milestone) => ({
                ...milestone,
                id: milestone.id || milestone.milestone_id,
                name: milestone.name || milestone.milestone_name || 'Milestone',
            }))
        );

        const fallbackDeadline = nextTasks[0]?.planned_end || nextTasks[0]?.deadline || '';
        setProjectDeadline(nextPayload?.project_deadline || fallbackDeadline || '');
    }, []);

    useEffect(() => {
        if (!selectedProjectKey) {
            setHasCompletedInitialBootstrap(true);
            setGeneratedTaskPlan(null);
            return;
        }
        setHasCompletedInitialBootstrap(false);
        setProjectDeadline('');
        setSprints([]);
        setMilestones([]);
        setTasks([]);
        setGeneratedTaskPlan(null);
        setTaskTotalCount(0);
        setError('');
        setSuccess('');
    }, [selectedProjectKey]);

    useEffect(() => {
        if (selectedProjectKey) {
            const saved = localStorage.getItem(`custom_rules_${selectedProjectKey}`) || '';
            setCustomRules(saved);
        }
    }, [selectedProjectKey]);

    useEffect(() => {
        if (selectedProjectKey) {
            localStorage.setItem(`custom_rules_${selectedProjectKey}`, customRules);
        }
    }, [selectedProjectKey, customRules]);

    const buildHeaders = useCallback(() => {
        return { Authorization: `Bearer ${token}` };
    }, [token]);

    const resolveTaskToken = useCallback(async () => {
        if (!selectedProjectKey) return null;

        const cachedToken = getCachedTaskToken(selectedProjectKey);
        if (cachedToken) return cachedToken;

        const clientId = selectedProject?.client_id;
        const clientSecret = selectedProject?.client_secret;
        if (!clientId || !clientSecret) {
            return null;
        }

        const res = await fetch(API_ENDPOINTS.TASK_TOKEN, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ client_id: clientId, client_secret: clientSecret }),
        });
        if (!res.ok) {
            throw new Error('Failed to fetch task token');
        }

        const data = await res.json().catch(() => ({}));
        const fetchedToken = typeof data?.access === 'string' ? data.access : '';
        if (!fetchedToken) {
            throw new Error('Task token is missing from token response');
        }

        cacheTaskToken(selectedProjectKey, fetchedToken);
        return fetchedToken;
    }, [selectedProjectKey, selectedProject]);

    const loadData = useCallback(async () => {
        if (!selectedProjectKey) {
            setHasCompletedInitialBootstrap(true);
            return null;
        }
        setIsLoading(true);
        setError('');
        try {
            const storedPlan = readGeneratedTaskPlan(selectedProjectKey);
            hydrateGeneratedPlan(storedPlan);
            return {
                sprints: Array.isArray(storedPlan?.sprints) ? storedPlan.sprints : [],
                milestones: Array.isArray(storedPlan?.milestones) ? storedPlan.milestones : [],
                tasks: Array.isArray(storedPlan?.tasks) ? storedPlan.tasks : [],
                taskTotalCount: Array.isArray(storedPlan?.tasks) ? storedPlan.tasks.length : 0,
                projectDeadline: storedPlan?.project_deadline || '',
            };
        } catch (e) {
            setError(e?.message || 'Failed to load generated task plan');
            return null;
        } finally {
            setIsLoading(false);
            setHasCompletedInitialBootstrap(true);
        }
    }, [selectedProjectKey, hydrateGeneratedPlan]);

    useEffect(() => {
        loadData();
    }, [loadData]);

    useEffect(() => {
        if (!isGenerating) {
            setCreationStageIndex(0);
            setLiveCreatedTaskCount(0);
        }
    }, [isGenerating]);

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

    const handleMasterCreate = useCallback(async () => {
        if (!selectedProjectKey) {
            setError('Select a project before creating tasks.');
            return;
        }

        setIsGenerating(true);
        setError('');
        setSuccess('');
        setCreationStageIndex(0);
        setLiveCreatedTaskCount(0);

        try {
            const taskToken = await resolveTaskToken();
            if (!taskToken) {
                throw new Error('Task token is required before uploading generated tasks.');
            }

            const headers = {
                ...buildHeaders(),
                'Content-Type': 'application/json',
                'X-Task-Token': taskToken,
            };

            setCreationStageIndex(1);
            let prerequisites = null;
            try {
                const saved = localStorage.getItem(`prerequisites_completed_${selectedProjectKey}`);
                if (saved) {
                    const parsed = JSON.parse(saved);
                    const items = Array.isArray(parsed?.items) ? parsed.items : [];
                    prerequisites = items
                        .map((item) => sanitizePrerequisiteForAiPayload(item))
                        .filter((item) => item.name || item.description);
                }
            } catch {
                prerequisites = null;
            }

            const generatePayload = {
                project_token: selectedProjectKey,
                auto_create_plan: true,
                custom_rules: customRules,
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

            writeGeneratedTaskPlan(selectedProjectKey, generateJson);
            hydrateGeneratedPlan(generateJson);

            const createdCount = Array.isArray(generateJson?.tasks)
                ? generateJson.tasks.length
                : (generateJson?.tasks_created ?? 0);
            const backendMessage =
                typeof generateJson?.message === 'string' ? generateJson.message : '';

            if (backendMessage) {
                setSuccess(backendMessage);
            } else {
                setSuccess(`Generated ${createdCount} task preview item(s).`);
            }
            setLiveCreatedTaskCount(createdCount);
            setCreationStageIndex(2);
        } catch (e) {
            setError(e?.message || 'Task creation failed');
        } finally {
            setIsGenerating(false);
        }
    }, [selectedProjectKey, buildHeaders, customRules, hydrateGeneratedPlan, resolveTaskToken]);

    useEffect(() => {
        const shouldAutoStart = Boolean(location.state?.autoStartTaskCreation);
        if (!shouldAutoStart) return;
        if (!selectedProjectKey) return;
        if (isGenerating) return;

        const runKey = `${selectedProjectKey}:${location.key}`;
        if (autoStartRunKeysRef.current.has(runKey)) return;
        autoStartRunKeysRef.current.add(runKey);

        let isCancelled = false;
        (async () => {
            const snapshot = await loadData();
            if (isCancelled) return;
            if (!snapshot) return;
            if (Array.isArray(snapshot?.tasks) && snapshot.tasks.length > 0) {
                setSuccess(`Found ${snapshot.tasks.length} existing task(s).`);
                return;
            }
            await handleMasterCreate();
        })();

        return () => {
            isCancelled = true;
        };
    }, [
        location.state,
        location.key,
        selectedProjectKey,
        isGenerating,
        loadData,
        handleMasterCreate,
    ]);

    const handleStartProcess = () => {
        if (processMode === 'ai_assist') {
            window.location.href = 'vscode:extension/bourntec-Solutions.n-mod-vscode-assistant';
        } else {
            navigate('/resource-onboarding', { state: { processMode } });
        }
    };

    const showInitialProjectLoader = Boolean(selectedProjectKey) && !hasCompletedInitialBootstrap && isLoading;

    if (showInitialProjectLoader) {
        return (
            <div className="h-full min-h-[70vh] bg-gradient-to-br from-slate-50 via-gray-50 to-blue-50/30">
                <div className="fixed inset-0 z-[300] bg-slate-950/55 backdrop-blur-sm flex items-center justify-center px-4">
                    <div className="w-full max-w-md rounded-2xl border border-slate-200 bg-white shadow-2xl p-6 text-center" style={{ filter: 'none', backdropFilter: 'none' }}>
                        <div className="flex justify-center">
                            <Loader2 className="w-8 h-8 text-indigo-600 animate-spin" />
                        </div>
                        <h3 className="mt-4 text-lg font-extrabold text-slate-900">Loading Task Creation</h3>
                        <p className="mt-2 text-sm text-slate-600">
                            Loading the local task preview for <span className="font-semibold text-slate-800">{selectedProject?.name || 'selected project'}</span>.
                        </p>
                        <p className="mt-1 text-xs text-slate-500">
                            The page will open as soon as the saved preview is ready.
                        </p>
                    </div>
                </div>
            </div>
        );
    }

    return (
        <>
            <div className={`h-full overflow-y-auto bg-gradient-to-br from-slate-50 via-gray-50 to-blue-50/30 ${isGenerating ? 'blur-sm' : ''}`}>
                <div className="max-w-6xl mx-auto px-4 py-6 space-y-6">
                    <div className="bg-white rounded-2xl border border-app-border-light shadow-sm p-5">
                        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4">
                            <div>
                                <p className="text-xs font-semibold uppercase tracking-widest text-app-text-muted">Master Agent Planner</p>
                                <h2 className="text-2xl font-extrabold text-app-text-main mt-1">Create Sprint, Milestone, and Tasks</h2>
                                <p className="text-sm text-app-text-muted mt-2">
                                    Project: <span className="font-semibold text-app-text-main">{selectedProject?.name || 'Not selected'}</span>
                                </p>
                                {processMode === 'ai_assist' && (
                                    <div className="mt-3 flex items-center gap-2 px-3 py-1.5 bg-indigo-50 border border-indigo-100 rounded-lg text-xs font-semibold text-indigo-700">
                                        <Sparkles className="w-3.5 h-3.5" />
                                        <span>AI Assist Active: You will be redirected to VS Code's N-Mod Ext.</span>
                                    </div>
                                )}
                            </div>
                            <button
                                onClick={handleStartProcess}
                                className="inline-flex items-center gap-2 px-5 py-2.5 text-sm font-bold text-white bg-gradient-to-r from-emerald-500 to-green-600 rounded-lg shadow hover:shadow-lg transition-all"
                            >
                                Start the Process
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
                            Master Agent will generate the task JSON, upload it to the external batch task API, and show the same payload on this page.
                        </p>
                        <div className="text-xs text-app-text-muted bg-app-bg-muted rounded-lg px-3 py-2 border border-app-border-light">
                            Project deadline: <span className="font-semibold text-app-text-main">{projectDeadline || 'Not available'}</span>
                        </div>
                        <button
                            onClick={handleMasterCreate}
                            disabled={!selectedProjectKey || isGenerating}
                            className={`w-full inline-flex items-center justify-center gap-2 px-4 py-3 rounded-lg font-bold text-sm transition-colors ${(!selectedProjectKey || isGenerating)
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
                        {/* {selectedProjectKey && (
                            <p className="text-xs text-blue-700 bg-blue-50 border border-blue-200 rounded-lg px-3 py-2">
                                The generated task JSON is uploaded to the batch task API, stored locally for this project, and shown below.
                            </p>
                        )} */}
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

                    {/* <div className="bg-white rounded-2xl border border-app-border-light shadow-sm p-5">
                        <div className="flex items-center justify-between mb-4">
                            <h3 className="text-sm font-bold text-app-text-main">Generated JSON Preview</h3>
                            {generatedTaskPlan && (
                                <span className="text-xs font-semibold text-app-text-muted">
                                    {Array.isArray(generatedTaskPlan?.tasks) ? generatedTaskPlan.tasks.length : 0} item(s)
                                </span>
                            )}
                        </div>
                        {generatedTaskPlan ? (
                            <div className="space-y-4">
                                <pre className="max-h-[420px] overflow-auto rounded-xl bg-slate-950 px-4 py-4 text-xs leading-6 text-slate-100">
                                    {JSON.stringify(previewJsonForDisplay, null, 2)}
                                </pre>
                                <div>
                                    <h4 className="mb-3 text-sm font-bold text-app-text-main">Generated CSV Preview</h4>
                                    <pre className="max-h-[320px] overflow-auto rounded-xl bg-slate-950 px-4 py-4 text-xs leading-6 text-emerald-100">
                                        {previewCsv}
                                    </pre>
                                </div>
                            </div>
                        ) : (
                            <div className="py-10 text-center text-sm text-app-text-muted">
                                No generated JSON yet. Run Create Tasks to preview the payload.
                            </div>
                        )}
                    </div> */}


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
                            <div className="py-10 text-center text-sm text-app-text-muted">Loading generated task plan...</div>
                        ) : groupedTasks.length === 0 ? (
                            <div className="py-10 text-center text-sm text-app-text-muted">No generated tasks found yet.</div>
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
                                                            <div key={task.id || task.task_id || task.taskName} className="border border-app-border rounded-lg px-3 py-2 bg-white">
                                                                <p className="text-sm font-semibold text-app-text-main">{task.title || task.taskName || 'Untitled Task'}</p>
                                                                <div className="mt-1 flex flex-wrap items-center gap-3 text-xs text-app-text-muted">
                                                                    <span className="inline-flex items-center gap-1">
                                                                        <Flag className="w-3 h-3" />
                                                                        {task.priority || 'medium'}
                                                                    </span>
                                                                    <span className="inline-flex items-center gap-1">
                                                                        <CalendarDays className="w-3 h-3" />
                                                                        {task.planned_end || task.deadline || 'No deadline'}
                                                                    </span>
                                                                    <span className="rounded-full bg-slate-100 px-2 py-0.5 font-semibold uppercase tracking-wide text-[10px] text-slate-700">
                                                                        {task.type || task.task_type || 'task'}
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
            {isGenerating && (
                <div className="fixed top-[120px] md:top-[180px] left-0 md:left-72 right-0 bottom-0 z-[200] flex items-start justify-center pt-8 px-4 pointer-events-none" style={{ filter: 'none', backdropFilter: 'none' }}>
                    <div className="w-full max-w-xl rounded-2xl border border-slate-200 bg-white shadow-2xl p-6 sm:p-7 pointer-events-auto" style={{ filter: 'none', backdropFilter: 'none' }}>
                        <div className="flex items-center gap-3">
                            <Loader2 className="w-6 h-6 text-indigo-600 animate-spin" />
                            <h3 className="text-lg font-extrabold text-slate-900">AI Plan Generation In Progress</h3>
                        </div>
                        <p className="mt-2 text-sm text-slate-600">
                            Generating a local task preview for <span className="font-semibold text-slate-800">{selectedProject?.name || 'selected project'}</span>. Please wait.
                        </p>
                        <div className="mt-4 rounded-xl border border-indigo-100 bg-indigo-50 px-4 py-3 flex items-center justify-between">
                            <span className="text-sm font-semibold text-indigo-900">Preview tasks generated</span>
                            <span className="text-2xl font-extrabold text-indigo-700 tabular-nums">{liveCreatedTaskCount}</span>
                        </div>
                        <div className="mt-5 space-y-3">
                            {PLAN_CREATION_STEPS.map((stepLabel, idx) => {
                                const isDone = idx < creationStageIndex;
                                const isActive = idx === creationStageIndex;
                                return (
                                    <div
                                        key={stepLabel}
                                        className={`flex items-center gap-3 rounded-lg border px-3 py-2 ${isDone
                                            ? 'border-emerald-200 bg-emerald-50'
                                            : isActive
                                                ? 'border-indigo-200 bg-indigo-50'
                                                : 'border-slate-200 bg-slate-50'
                                            }`}
                                    >
                                        {isDone ? (
                                            <CheckCircle2 className="w-4 h-4 text-emerald-600" />
                                        ) : isActive ? (
                                            <Loader2 className="w-4 h-4 text-indigo-600 animate-spin" />
                                        ) : (
                                            <span className="inline-block w-3 h-3 rounded-full border border-slate-300 bg-white" />
                                        )}
                                        <span className={`text-sm font-semibold ${isDone ? 'text-emerald-700' : isActive ? 'text-indigo-700' : 'text-slate-500'}`}>
                                            {stepLabel}
                                        </span>
                                    </div>
                                );
                            })}
                        </div>
                        <p className="mt-4 text-xs text-slate-500">
                            Actions are temporarily locked until task plan creation completes.
                        </p>
                    </div>
                </div>
            )}
        </>
    );
}
