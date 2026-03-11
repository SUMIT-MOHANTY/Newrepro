import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
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
import { upsertDraftProject, getDraftProject } from '../utils/draftProjects';
import { getCachedTaskToken, setCachedTaskToken as cacheTaskToken } from '../utils/tokenCache';

const PLAN_CREATION_STEPS = ['Creating Tasks'];
const PROCESS_MODE_STORAGE_KEY = 'status_dashboard_process_mode_map';
const GENERATED_TASK_PLAN_STORAGE_KEY_PREFIX = 'task_creation_generated_plan_';

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

function extractEntityName(item, key) {
    const direct = item?.[key];
    if (direct && typeof direct === 'object') {
        const nestedName = String(direct.name || direct[`${key}_name`] || '').trim();
        if (nestedName) return nestedName;
    }
    const fallback = String(item?.[`${key}_name`] || '').trim();
    return fallback || '';
}

function getErrorMessage(errorPayload, fallback) {
    if (!errorPayload) return fallback;

    // Extract error message from various possible formats
    let errorMessage = '';
    if (typeof errorPayload.detail === 'string') {
        errorMessage = errorPayload.detail;
    } else if (typeof errorPayload.error === 'string') {
        errorMessage = errorPayload.error;
    } else if (typeof errorPayload.message === 'string') {
        errorMessage = errorPayload.message;
    } else {
        return fallback;
    }

    // Convert technical error messages to user-friendly ones
    if (errorMessage.toLowerCase().includes('already exists')) {
        // Extract entity type and name if possible
        const sprintMatch = errorMessage.match(/sprint.*?"([^"]+)"|sprint.*?name\s+["']([^"']+)["']/i);
        const milestoneMatch = errorMessage.match(/milestone.*?"([^"]+)"|milestone.*?name\s+["']([^"']+)["']/i);

        if (sprintMatch) {
            const sprintName = sprintMatch[1] || sprintMatch[2];
            return sprintName
                ? `A sprint named "${sprintName}" already exists in this project. The system will use the existing sprint.`
                : 'A sprint with this name already exists in this project. The system will use the existing sprint.';
        } else if (milestoneMatch) {
            const milestoneName = milestoneMatch[1] || milestoneMatch[2];
            return milestoneName
                ? `A milestone named "${milestoneName}" already exists in this project. The system will use the existing milestone.`
                : 'A milestone with this name already exists in this project. The system will use the existing milestone.';
        } else {
            return 'This item already exists in the project. The system will continue with the existing item.';
        }
    }

    return errorMessage || fallback;
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

function normalizePrerequisiteKey(name) {
    const raw = String(name || '').trim();
    if (!raw) return '';
    return raw
        .toLowerCase()
        .replace(/[^\w]+/g, '_')
        .replace(/^_+|_+$/g, '');
}

function buildPrerequisitesObjectFromStorage(projectKey) {
    if (!projectKey) return [];
    try {
        const saved = localStorage.getItem(`prerequisites_completed_${projectKey}`);
        if (!saved) return [];
        const parsed = JSON.parse(saved);
        const items = Array.isArray(parsed?.items) ? parsed.items : [];
        return items
            .filter((item) => item && item.provided)
            .map((item) => sanitizePrerequisiteForAiPayload(item))
            .filter((item) => item.name || item.description);
    } catch {
        return [];
    }
}

function readRepoLinkUrlForProject(projectKey) {
    if (!projectKey) return '';
    const storageKey = `repo_context_meta_${projectKey}`;
    const raw = sessionStorage.getItem(storageKey) || localStorage.getItem(storageKey);
    if (!raw) return '';
    try {
        const parsed = JSON.parse(raw);
        return String(parsed?.url || '').trim();
    } catch {
        return '';
    }
}

function parseJsonSafely(value) {
    try {
        return JSON.parse(value);
    } catch {
        return null;
    }
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
    const queryClient = useQueryClient();
    const token = localStorage.getItem('token');

    const [hasCompletedInitialBootstrap, setHasCompletedInitialBootstrap] = useState(false);
    const [taskToken, setTaskToken] = useState(null);
    const [isResolvingTaskToken, setIsResolvingTaskToken] = useState(false);

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
    const [projectType, setProjectType] = useState('greenfield');
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
    const hasProjectClientCredentials = Boolean(
        selectedProject?.client_id && selectedProject?.client_secret
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
        setTaskToken(null);
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

        // If the project has its own credentials, we should prefer a token derived from them.
        // Reason: earlier screens (Prerequisites) may have fetched a token using org/default creds.
        // If that token was cached, using it here can return "random" project/task data until relogin.
        const cachedToken = getCachedTaskToken(selectedProjectKey);
        if (cachedToken && !hasProjectClientCredentials) return cachedToken;

        // Check both selectedProject and draftProject for credentials
        const draftProject = getDraftProject(selectedProjectKey);
        const clientId = selectedProject?.client_id || draftProject?.client_id;
        const clientSecret = selectedProject?.client_secret || draftProject?.client_secret;

        if (!clientId || !clientSecret) {
            // Fall back to cached token if we have one but no credentials to refresh with.
            if (cachedToken) return cachedToken;
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
    }, [selectedProjectKey, selectedProject, hasProjectClientCredentials]);

    // Resolve task token on mount and when project changes
    useEffect(() => {
        if (!selectedProjectKey) {
            setTaskToken(null);
            setIsResolvingTaskToken(false);
            return;
        }

        setIsResolvingTaskToken(true);
        resolveTaskToken()
            .then((token) => {
                setTaskToken(token);
            })
            .catch((err) => {
                console.error('Failed to resolve task token:', err);
                setTaskToken(null);
            })
            .finally(() => {
                setIsResolvingTaskToken(false);
            });
    }, [selectedProjectKey, resolveTaskToken]);

    // Fetch project info whenever task token is available OR if we have credentials
    // This ensures project info is fetched even if token resolution is in progress
    const draftProject = useMemo(() => getDraftProject(selectedProjectKey), [selectedProjectKey]);
    const hasCredentials = useMemo(() => {
        return !!(selectedProject?.client_id || draftProject?.client_id);
    }, [selectedProject?.client_id, draftProject?.client_id]);

    const { data: projectInfo = null, isFetching: isLoadingProjectInfo } = useQuery({
        queryKey: ['projectInfo', selectedProjectKey, taskToken, hasCredentials],
        queryFn: async () => {
            const headers = { 'Authorization': `Bearer ${token}` };
            // Use taskToken if available, otherwise try to get one
            let tokenToUse = taskToken;
            if (!tokenToUse && hasCredentials) {
                // Try to resolve token if we have credentials but token not resolved yet
                const clientId = selectedProject?.client_id || draftProject?.client_id;
                const clientSecret = selectedProject?.client_secret || draftProject?.client_secret;
                if (clientId && clientSecret) {
                    try {
                        const tokenRes = await fetch(API_ENDPOINTS.TASK_TOKEN, {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ client_id: clientId, client_secret: clientSecret }),
                        });
                        if (tokenRes.ok) {
                            const tokenData = await tokenRes.json();
                            tokenToUse = tokenData?.access;
                            if (tokenToUse) {
                                cacheTaskToken(selectedProjectKey, tokenToUse);
                                setTaskToken(tokenToUse);
                            }
                        }
                    } catch (err) {
                        console.warn('Failed to get token for project info:', err);
                    }
                }
            }
            if (tokenToUse) headers['x-task-token'] = tokenToUse;
            const res = await fetch(API_ENDPOINTS.AGENT_PROJECT_INFO, { headers });
            if (!res.ok) throw new Error('Failed to fetch project info');
            return await res.json();
        },
        enabled: !!token && !!selectedProjectKey && (!!taskToken || hasCredentials),
    });

    // Update project deadline from project info when available
    useEffect(() => {
        const deadline = projectInfo?.project?.deadline || projectInfo?.deadline;
        if (deadline) {
            setProjectDeadline(deadline);
        }
    }, [projectInfo]);

    const loadData = useCallback(async () => {
        if (!selectedProjectKey) {
            setHasCompletedInitialBootstrap(true);
            return null;
        }
        setIsLoading(true);
        setError('');
        try {
            // First, try to fetch tasks from backend API if we have a task token
            let backendTasks = null;
            if (taskToken) {
                try {
                    const headers = { 'Authorization': `Bearer ${token}` };
                    if (taskToken) headers['x-task-token'] = taskToken;

                    const tasksRes = await fetch(API_ENDPOINTS.AGENT_TASKS_TOTAL, { headers });
                    if (tasksRes.ok) {
                        const tasksData = await tasksRes.json();
                        // Handle both array and paginated response formats
                        const tasksList = Array.isArray(tasksData)
                            ? tasksData
                            : (Array.isArray(tasksData?.results) ? tasksData.results : []);

                        if (tasksList.length > 0) {
                            // Group tasks by sprint and milestone for display
                            const sprintsMap = new Map();
                            const milestonesMap = new Map();

                            tasksList.forEach((task) => {
                                const sprintId = extractEntityId(task, 'sprint');
                                const milestoneId = extractEntityId(task, 'milestone');
                                const sprintName = extractEntityName(task, 'sprint');
                                const milestoneName = extractEntityName(task, 'milestone');

                                if (sprintId != null) {
                                    const sprint = task.sprint;
                                    if (sprint && typeof sprint === 'object') {
                                        sprintsMap.set(String(sprintId), {
                                            id: sprintId,
                                            name: sprint.name || sprint.sprint_name || sprintName || `Sprint #${sprintId}`,
                                        });
                                    } else if (!sprintsMap.has(String(sprintId))) {
                                        sprintsMap.set(String(sprintId), {
                                            id: sprintId,
                                            name: sprintName || `Sprint #${sprintId}`,
                                        });
                                    }
                                }

                                if (milestoneId != null) {
                                    const milestone = task.milestone;
                                    if (milestone && typeof milestone === 'object') {
                                        milestonesMap.set(String(milestoneId), {
                                            id: milestoneId,
                                            name: milestone.name || milestone.milestone_name || milestoneName || `Milestone #${milestoneId}`,
                                        });
                                    } else if (!milestonesMap.has(String(milestoneId))) {
                                        milestonesMap.set(String(milestoneId), {
                                            id: milestoneId,
                                            name: milestoneName || `Milestone #${milestoneId}`,
                                        });
                                    }
                                }
                            });

                            // Build the plan structure from backend data
                            backendTasks = {
                                tasks: tasksList,
                                sprints: Array.from(sprintsMap.values()),
                                milestones: Array.from(milestonesMap.values()),
                                project_deadline: projectInfo?.project?.deadline || projectInfo?.deadline || projectDeadline || '',
                            };

                            // Save to localStorage for offline access
                            writeGeneratedTaskPlan(selectedProjectKey, backendTasks);
                        }
                    }
                } catch (fetchError) {
                    // If backend fetch fails, fallback to localStorage
                    console.warn('Failed to fetch tasks from backend, using localStorage:', fetchError);
                }
            }

            // Use backend data if available, otherwise fallback to localStorage
            const planToUse = backendTasks || readGeneratedTaskPlan(selectedProjectKey);

            if (planToUse) {
                hydrateGeneratedPlan(planToUse);
                return {
                    sprints: Array.isArray(planToUse?.sprints) ? planToUse.sprints : [],
                    milestones: Array.isArray(planToUse?.milestones) ? planToUse.milestones : [],
                    tasks: Array.isArray(planToUse?.tasks) ? planToUse.tasks : [],
                    taskTotalCount: Array.isArray(planToUse?.tasks) ? planToUse.tasks.length : 0,
                    projectDeadline: planToUse?.project_deadline || '',
                };
            }

            return {
                sprints: [],
                milestones: [],
                tasks: [],
                taskTotalCount: 0,
                projectDeadline: '',
            };
        } catch (e) {
            setError(e?.message || 'Failed to load generated task plan');
            return null;
        } finally {
            setIsLoading(false);
        }
    }, [selectedProjectKey, hydrateGeneratedPlan, taskToken, token, projectInfo, projectDeadline]);

    // Load data when project key changes or when task token becomes available
    useEffect(() => {
        // Only load if we have completed initial bootstrap (project info loaded)
        if (hasCompletedInitialBootstrap) {
            loadData();
        }
    }, [loadData, hasCompletedInitialBootstrap, taskToken]);

    // Mark bootstrap as complete only when project info is loaded (or if no project selected)
    useEffect(() => {
        if (!selectedProjectKey) {
            setHasCompletedInitialBootstrap(true);
            return;
        }

        const hasClientCredentials = selectedProject?.client_id && selectedProject?.client_secret;

        // Determine what we're waiting for:
        const waitingForToken = hasClientCredentials && isResolvingTaskToken;
        const waitingForProjectInfo = hasClientCredentials && taskToken && isLoadingProjectInfo;
        const waitingForData = isLoading;

        // If we're not waiting for anything, check if we can complete bootstrap
        if (!waitingForToken && !waitingForData) {
            if (hasClientCredentials) {
                // Need to wait for project info if we have a task token
                if (taskToken) {
                    // Project info query is enabled and has completed (either success or error)
                    // isLoadingProjectInfo will be false when query completes (even on error)
                    if (!isLoadingProjectInfo) {
                        setHasCompletedInitialBootstrap(true);
                    }
                } else if (!isResolvingTaskToken) {
                    // Token resolution failed or not available, but we tried
                    // Allow to continue (project info will fail but that's okay)
                    setHasCompletedInitialBootstrap(true);
                }
            } else {
                // No client credentials, no need to fetch project info
                setHasCompletedInitialBootstrap(true);
            }
        }
    }, [selectedProjectKey, taskToken, projectInfo, isResolvingTaskToken, isLoadingProjectInfo, isLoading, selectedProject]);

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
            const sprintName = extractEntityName(task, 'sprint');
            const milestoneName = extractEntityName(task, 'milestone');
            const sprintKey = sprintId != null ? String(sprintId) : 'unassigned_sprint';
            const milestoneKey = milestoneId != null ? String(milestoneId) : 'unassigned_milestone';

            if (!groups.has(sprintKey)) {
                groups.set(sprintKey, {
                    sprint: sprintId != null
                        ? (sprintById.get(String(sprintId)) || { id: sprintId, name: sprintName || `Sprint #${sprintId}` })
                        : { id: 'unassigned_sprint', name: 'Unassigned Sprint' },
                    milestones: new Map(),
                });
            }

            const sprintGroup = groups.get(sprintKey);
            if (!sprintGroup.milestones.has(milestoneKey)) {
                sprintGroup.milestones.set(milestoneKey, {
                    milestone: milestoneId != null
                        ? (milestoneById.get(String(milestoneId)) || { id: milestoneId, name: milestoneName || `Milestone #${milestoneId}` })
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
            // First, try to resolve task token from existing credentials
            let taskToken = await resolveTaskToken();

            // Project creation is handled inside the backend auto-generate endpoint.
            // This ensures the project deadline is derived strictly from the selected process_mode.
            if (!taskToken) {
                throw new Error('Task token is required. Please ensure the project has been created in the task management system with valid credentials.');
            }

            // Save project-config for this project (multipart) before generating tasks.
            try {
                const latestDoc = selectedProject?.latestDocument || null;
                const fullAnalysedObj = latestDoc?.analysis_result
                    ? (parseJsonSafely(latestDoc.analysis_result) || {})
                    : {};
                const analysedObj = fullAnalysedObj.analysis
                    ? { analysis: fullAnalysedObj.analysis }
                    : fullAnalysedObj;
                const governanceObj = fullAnalysedObj.governanceContext || {};

                const prerequisitesObj = buildPrerequisitesObjectFromStorage(selectedProjectKey);
                const repoLinkUrl = readRepoLinkUrlForProject(selectedProjectKey);

                const inputText =
                    String(latestDoc?.full_content || '').trim()
                    || String(latestDoc?.content_preview || '').trim();

                const formData = new FormData();
                formData.append('mode', processMode || 'ai_first');
                formData.append('project_token', selectedProjectKey);
                formData.append('prerequisites', JSON.stringify(prerequisitesObj || {}));
                formData.append('analysed_file', JSON.stringify(analysedObj || {}));
                formData.append('governance', JSON.stringify(governanceObj));
                if (repoLinkUrl) formData.append('repo_link_url', repoLinkUrl);

                if (inputText) {
                    const blob = new Blob([inputText], { type: 'text/plain' });
                    const filenameBase = String(latestDoc?.filename || 'requirements').replace(/[^\w.-]+/g, '_');
                    formData.append('input_file', blob, `${filenameBase || 'requirements'}.txt`);
                }

                const cfgRes = await fetch(API_ENDPOINTS.AGENT_PROJECT_CONFIG, {
                    method: 'PUT',
                    headers: {
                        ...buildHeaders(),
                        'X-Task-Token': taskToken,
                    },
                    body: formData,
                });

                if (!cfgRes.ok) {
                    const cfgJson = await cfgRes.json().catch(() => ({}));
                    console.warn('Project config save failed:', cfgJson);
                    throw new Error(getErrorMessage(cfgJson, 'Failed to save project config'));
                }
                const cfgJson = await cfgRes.json().catch(() => ({}));
                setSuccess(cfgJson?.message || 'Task creation started and will shortly appear here in the list.');
            } catch (cfgErr) {
                console.warn('Project config save error:', cfgErr);
                throw cfgErr;
            }

            // NOTE: Keep the existing task generation logic in code, but do NOT call it for now.
            // Return early after saving project config.
            return;

            const headers = {
                ...buildHeaders(),
                'Content-Type': 'application/json',
                'X-Task-Token': taskToken,
            };

            let prerequisites = null;
            try {
                const saved = localStorage.getItem(`prerequisites_completed_${selectedProjectKey}`);
                if (saved) {
                    const parsed = JSON.parse(saved);
                    const items = Array.isArray(parsed?.items) ? parsed.items : [];
                    // Only include prerequisites that were marked as provided/checked in the prerequisites screen.
                    prerequisites = items
                        .filter((item) => item?.provided)
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
                project_type: projectType,
                process_mode: processMode,
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
                const errorMsg = getErrorMessage(generateJson, 'Failed to auto-generate tasks');
                // If it's an "already exists" error, treat it as a warning, not a failure
                if (errorMsg.toLowerCase().includes('already exists') || errorMsg.toLowerCase().includes('will use the existing')) {
                    // Continue processing - this is not a critical error
                    console.warn('Sprint/milestone already exists, continuing with existing items:', errorMsg);
                } else {
                    throw new Error(errorMsg);
                }
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
            setCreationStageIndex(1);
        } catch (e) {
            setError(e?.message || 'Task creation failed');
        } finally {
            setIsGenerating(false);
        }
    }, [selectedProjectKey, selectedProject, buildHeaders, customRules, hydrateGeneratedPlan, resolveTaskToken, projectInfo, token, projectDeadline]);

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

    const showInitialProjectLoader = Boolean(selectedProjectKey) && (
        !hasCompletedInitialBootstrap ||
        isLoading ||
        isResolvingTaskToken ||
        isLoadingProjectInfo
    );

    if (showInitialProjectLoader) {
        return (
            <div className="h-full min-h-[70vh] bg-gradient-to-br from-app-bg-page via-app-bg-page to-app-primary-light/30">
                <div className="fixed inset-0 z-[300] bg-black/60 backdrop-blur-sm flex items-center justify-center px-4">
                    <div className="w-full max-w-md rounded-2xl border border-app-border bg-app-bg-card shadow-2xl p-6 text-center" style={{ filter: 'none', backdropFilter: 'none' }}>
                        <div className="flex justify-center">
                            <Loader2 className="w-8 h-8 text-app-primary animate-spin" />
                        </div>
                        <h3 className="mt-4 text-lg font-extrabold text-app-text-main">Loading Task Creation</h3>
                        <p className="mt-2 text-sm text-app-text-label">
                            {isResolvingTaskToken || isLoadingProjectInfo
                                ? <>Fetching project information for <span className="font-semibold text-app-text-main">{selectedProject?.name || 'selected project'}</span>.</>
                                : <>Loading the local task preview for <span className="font-semibold text-app-text-main">{selectedProject?.name || 'selected project'}</span>.</>
                            }
                        </p>
                        <p className="mt-1 text-xs text-app-text-muted">
                            {isResolvingTaskToken || isLoadingProjectInfo
                                ? 'Please wait while we fetch the project details...'
                                : 'The page will open as soon as the saved preview is ready.'
                            }
                        </p>
                    </div>
                </div>
            </div>
        );
    }

    return (
        <>
            <div className={`h-full overflow-y-auto bg-gradient-to-br from-app-bg-page via-app-bg-page to-app-primary-light/30 ${isGenerating ? 'blur-sm' : ''}`}>
                <div className="max-w-6xl mx-auto px-4 py-6 space-y-6">
                    <div className="bg-app-bg-card rounded-2xl border border-app-border-light shadow-sm p-5">
                        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4">
                            <div>
                                <p className="text-xs font-semibold uppercase tracking-widest text-app-text-muted">Master Agent Planner</p>
                                <h2 className="text-2xl font-extrabold text-app-text-main mt-1">Create Sprint, Milestone, and Tasks</h2>
                                <p className="text-sm text-app-text-muted mt-2">
                                    Project: <span className="font-semibold text-app-text-main">{selectedProject?.name || 'Not selected'}</span>
                                </p>
                                <p className="text-xs text-app-text-muted mt-1">
                                    Mode: <span className="font-semibold text-app-text-main">
                                        {processMode === 'ai_first' ? 'AI-First' :
                                            processMode === 'coexistence' ? 'Coexistence' :
                                                processMode === 'developer_only' ? 'Developer Only' :
                                                    processMode === 'ai_assist' ? 'AI Assist' :
                                                        processMode === 'vibe_coding' ? 'Vibe Coding' :
                                                            processMode}
                                    </span>
                                </p>
                                {processMode === 'ai_assist' && (
                                    <div className="mt-3 flex items-center gap-2 px-3 py-1.5 bg-app-primary-light border border-app-primary-light rounded-lg text-xs font-semibold text-app-primary-hover">
                                        <Sparkles className="w-3.5 h-3.5" />
                                        <span>AI Assist Active: You will be redirected to VS Code's N-Mod Ext.</span>
                                    </div>
                                )}
                            </div>
                            <button
                                onClick={handleStartProcess}
                                className="inline-flex items-center gap-2 px-5 py-2.5 text-sm font-bold text-white bg-gradient-to-r from-app-status-success to-app-status-success rounded-lg shadow hover:shadow-lg transition-all"
                            >
                                Start the Process
                                <ArrowRight className="w-4 h-4" />
                            </button>
                        </div>
                    </div>

                    <div className="bg-app-bg-card rounded-2xl border border-app-border-light shadow-sm p-5 space-y-4">
                        <h3 className="text-sm font-bold text-app-text-main flex items-center gap-2">
                            <FolderKanban className="w-4 h-4 text-app-primary" />
                            AI Planning
                        </h3>
                        <p className="text-sm text-app-text-muted">
                            Master Agent will generate the task JSON, upload it to the external batch task API, and show the same payload on this page.
                        </p>
                        <div className="text-xs text-app-text-muted bg-app-bg-muted rounded-lg px-3 py-2 border border-app-border-light flex items-center justify-between">
                            <span>Project deadline: <span className="font-semibold text-app-text-main">{projectDeadline || 'Not available'}</span></span>
                            <div className="flex items-center gap-2">
                                <span className="text-[10px] uppercase font-bold text-app-text-muted">Strategy:</span>
                                <select
                                    value={projectType}
                                    onChange={(e) => setProjectType(e.target.value)}
                                    className="bg-app-bg-card border border-app-border rounded px-2 py-0.5 text-xs font-semibold text-app-primary-hover focus:outline-none focus:ring-1 focus:ring-app-primary"
                                >
                                    <option value="greenfield">Greenfield (New Build)</option>
                                    <option value="brownfield">Brownfield (Enhancement)</option>
                                    <option value="modernization">Modernization (Migration)</option>
                                </select>
                            </div>
                        </div>

                        <button
                            onClick={handleMasterCreate}
                            disabled={!selectedProjectKey || isGenerating || projectInfo?.tasks_created === true}
                            className={`w-full inline-flex items-center justify-center gap-2 px-4 py-3 rounded-lg font-bold text-sm transition-colors ${(!selectedProjectKey || isGenerating || projectInfo?.tasks_created === true)
                                ? 'bg-app-border text-app-text-muted cursor-not-allowed'
                                : 'bg-gradient-to-r from-app-primary to-app-primary text-app-bg-card hover:from-app-primary-hover hover:to-app-primary-hover'
                                }`}
                        >
                            {isGenerating ? <Loader2 className="w-4 h-4 animate-spin" /> : <Sparkles className="w-4 h-4" />}
                            {isGenerating ? 'Creating Plan...' : projectInfo?.tasks_created === true ? 'Tasks Already Created' : 'Create Tasks (AI Auto Plan)'}
                        </button>
                        {!selectedProjectKey && (
                            <p className="text-xs text-app-status-warning bg-app-status-warningBg border border-amber-200 rounded-lg px-3 py-2">
                                No project selected. Select a project from the sidebar or top project dropdown.
                            </p>
                        )}
                        {selectedProjectKey && projectInfo?.tasks_created === true && (
                            <p className="text-xs text-app-primary-hover bg-app-primary-light border border-app-primary-ring rounded-lg px-3 py-2 flex items-start gap-2">
                                <CheckCircle2 className="w-4 h-4 mt-0.5 shrink-0" />
                                <span>Tasks have already been created for this project. You can view them below or refresh to see the latest tasks.</span>
                            </p>
                        )}
                        {/* {selectedProjectKey && (
                            <p className="text-xs text-app-primary-hover bg-app-primary-light border border-app-primary-ring rounded-lg px-3 py-2">
                                The generated task JSON is uploaded to the batch task API, stored locally for this project, and shown below.
                            </p>
                        )} */}
                        {error && (
                            <p className="text-xs text-app-status-error bg-app-status-errorBg border border-red-200 rounded-lg px-3 py-2">{error}</p>
                        )}
                        {success && (
                            <p className="text-xs text-app-status-success bg-app-status-successBg border border-emerald-200 rounded-lg px-3 py-2 flex items-start gap-2">
                                <CheckCircle2 className="w-4 h-4 mt-0.5 shrink-0" />
                                <span>{success}</span>
                            </p>
                        )}
                    </div>

                    {/* <div className="bg-app-bg-card rounded-2xl border border-app-border-light shadow-sm p-5">
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
                                <pre className="max-h-[420px] overflow-auto rounded-xl bg-slate-900 px-4 py-4 text-xs leading-6 text-app-primary-light font-mono border border-slate-800">
                                    {JSON.stringify(previewJsonForDisplay, null, 2)}
                                </pre>
                                <div>
                                    <h4 className="mb-3 text-sm font-bold text-app-text-main">Generated CSV Preview</h4>
                                    <pre className="max-h-[320px] overflow-auto rounded-xl bg-slate-900 px-4 py-4 text-xs leading-6 text-emerald-400 font-mono border border-slate-800">
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


                    <div className="bg-app-bg-card rounded-2xl border border-app-border-light shadow-sm p-5">
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
                                        <div className="px-4 py-3 bg-app-primary-light border-b border-app-border-light flex items-center gap-3">
                                            <FolderKanban className="w-4 h-4 text-app-primary-hover" />
                                            <p className="text-sm font-bold text-app-primary-dark">{sprintGroup.sprint.name}</p>
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
                                                            <div key={task.id || task.task_id || task.taskName} className="border border-app-border rounded-lg px-3 py-2 bg-app-bg-card">
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
                                                                    <span className="rounded-full bg-app-bg-muted px-2 py-0.5 font-semibold uppercase tracking-wide text-[10px] text-app-text-label">
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
                <div className="fixed inset-0 z-[200] flex items-center justify-center p-4 pointer-events-none" style={{ filter: 'none', backdropFilter: 'none', paddingTop: '15%' }}>
                    <div className="w-full max-w-xl rounded-2xl border border-app-border bg-app-bg-card shadow-2xl p-6 sm:p-7 pointer-events-auto" style={{ filter: 'none', backdropFilter: 'none' }}>
                        <div className="flex items-center gap-3">
                            <Loader2 className="w-6 h-6 text-app-primary animate-spin" />
                            <h3 className="text-lg font-extrabold text-app-text-main">AI Plan Generation In Progress</h3>
                        </div>
                        <p className="mt-2 text-sm text-app-text-label">
                            Generating a local task preview for <span className="font-semibold text-app-text-main">{selectedProject?.name || 'selected project'}</span>. Please wait.
                        </p>
                        <div className="mt-4 rounded-xl border border-app-primary-light bg-app-primary-light px-4 py-3 flex items-center justify-between">
                            <span className="text-sm font-semibold text-app-primary-dark">Preview tasks generated</span>
                            <span className="text-2xl font-extrabold text-app-primary-hover tabular-nums">{liveCreatedTaskCount}</span>
                        </div>
                        <div className="mt-5 space-y-3">
                            {PLAN_CREATION_STEPS.map((stepLabel, idx) => {
                                const isDone = idx < creationStageIndex;
                                const isActive = idx === creationStageIndex;
                                return (
                                    <div
                                        key={stepLabel}
                                        className={`flex items-center gap-3 rounded-lg border px-3 py-2 ${isDone
                                            ? 'border-emerald-200 bg-app-status-successBg'
                                            : isActive
                                                ? 'border-app-primary-ring bg-app-primary-light'
                                                : 'border-app-border bg-app-bg-page'
                                            }`}
                                    >
                                        {isDone ? (
                                            <CheckCircle2 className="w-4 h-4 text-app-status-success" />
                                        ) : isActive ? (
                                            <Loader2 className="w-4 h-4 text-app-primary animate-spin" />
                                        ) : (
                                            <span className="inline-block w-3 h-3 rounded-full border border-app-border bg-app-bg-card" />
                                        )}
                                        <span className={`text-sm font-semibold ${isDone ? 'text-app-status-success' : isActive ? 'text-app-primary-hover' : 'text-app-text-muted'}`}>
                                            {stepLabel}
                                        </span>
                                    </div>
                                );
                            })}
                        </div>
                        <p className="mt-4 text-xs text-app-text-muted">
                            Actions are temporarily locked until task plan creation completes.
                        </p>
                    </div>
                </div>
            )}
        </>
    );
}
