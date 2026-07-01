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
import { API_ENDPOINTS, API_BASE_URL } from '../config';
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

    // CRITICAL FIX: Initialize based on whether we have a project selected
    // If we have a project, start with false to show loader immediately
    // If no project, start with true to skip loader
    const [hasCompletedInitialBootstrap, setHasCompletedInitialBootstrap] = useState(!selectedProjectKey);
    const [taskToken, setTaskToken] = useState(null);
    // CRITICAL FIX: Start with true to show loader immediately on mount
    const [isResolvingTaskToken, setIsResolvingTaskToken] = useState(true);

    const [projectDeadline, setProjectDeadline] = useState('');
    const [sprints, setSprints] = useState([]);
    const [milestones, setMilestones] = useState([]);
    const [tasks, setTasks] = useState([]);
    const [generatedTaskPlan, setGeneratedTaskPlan] = useState(null);
    const [isLoading, setIsLoading] = useState(false);
    const [isGenerating, setIsGenerating] = useState(false);
    const [isSyncing, setIsSyncing] = useState(false);
    const [error, setError] = useState('');
    const [success, setSuccess] = useState('');
    const [creationStageIndex, setCreationStageIndex] = useState(0);
    const [liveCreatedTaskCount, setLiveCreatedTaskCount] = useState(0);
    const [projectType, setProjectType] = useState(() => {
        if (selectedProjectKey) {
            return localStorage.getItem(`project_type_${selectedProjectKey}`) || 'greenfield';
        }
        return 'greenfield';
    });

    useEffect(() => {
        if (selectedProjectKey) {
            const savedType = localStorage.getItem(`project_type_${selectedProjectKey}`);
            if (savedType) {
                setProjectType(savedType);
            } else {
                setProjectType('greenfield');
            }
        }
    }, [selectedProjectKey]);

    const handleProjectTypeChange = (val) => {
        setProjectType(val);
        if (selectedProjectKey) {
            localStorage.setItem(`project_type_${selectedProjectKey}`, val);
            
            // Persist the user's manual change in DB
            const userToken = localStorage.getItem('token');
            fetch(`${API_BASE_URL}/api/agent/projects/${selectedProjectKey}/project-type`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${userToken}`
                },
                body: JSON.stringify({ project_type: val })
            }).then(res => {
                if (res.ok) {
                    console.log(`Saved manual project type change to DB: ${val}`);
                }
            }).catch(err => {
                console.error("Failed to save project type change:", err);
            });
        }
    };

    const [pagination, setPagination] = useState({
        count: 0,
        next: null,
        previous: null,
        currentPage: 1
    });
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

        // Handle both flat array and paginated response (results field)
        const nextTasks = Array.isArray(nextPayload?.tasks)
            ? nextPayload.tasks
            : (Array.isArray(nextPayload?.results) ? nextPayload.results : []);

        const nextSprints = Array.isArray(nextPayload?.sprints) ? nextPayload.sprints : [];
        const nextMilestones = Array.isArray(nextPayload?.milestones) ? nextPayload.milestones : [];

        const paginationInfo = nextPayload?.pagination || {
            count: nextPayload?.count || nextTasks.length || 0,
            next: nextPayload?.next || null,
            previous: nextPayload?.previous || null,
            currentPage: nextPayload?.pagination?.currentPage || 1
        };

        setGeneratedTaskPlan(nextPayload);
        setTasks(nextTasks);
        setPagination(paginationInfo);
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

    const loadData = useCallback(async (page = 1) => {
        if (!selectedProjectKey) {
            setHasCompletedInitialBootstrap(true);
            return null;
        }
        setIsLoading(true);
        setError('');
        try {
            // Fetch from our local tasks API
            const headers = { 'Authorization': `Bearer ${token}` };
            const url = new URL(API_ENDPOINTS.AGENT_TASKS_LOCAL);
            url.searchParams.set('project_token', selectedProjectKey);
            url.searchParams.set('page', page);

            const tasksRes = await fetch(url.toString(), { headers });

            if (tasksRes.ok) {
                const tasksData = await tasksRes.json();
                const tasksList = Array.isArray(tasksData?.tasks) ? tasksData.tasks : [];

                if (tasksList.length > 0) {
                    // Build sprints and milestones maps from task data
                    const sprintsMap = new Map();
                    const milestonesMap = new Map();

                    tasksList.forEach((task) => {
                        const sprintVal = task.sprint || 'new';
                        const milestoneVal = task.milestone || 'main';

                        if (!sprintsMap.has(String(sprintVal))) {
                            sprintsMap.set(String(sprintVal), {
                                id: sprintVal,
                                name: sprintVal === 'new' ? 'Sprint 1' : String(sprintVal),
                            });
                        }
                        if (!milestonesMap.has(String(milestoneVal))) {
                            milestonesMap.set(String(milestoneVal), {
                                id: milestoneVal,
                                name: milestoneVal === 'main' ? 'Main Milestone' : String(milestoneVal),
                            });
                        }
                    });

                    const plan = {
                        tasks: tasksList,
                        sprints: Array.from(sprintsMap.values()),
                        milestones: Array.from(milestonesMap.values()),
                        project_deadline: projectInfo?.project?.deadline || projectInfo?.deadline || projectDeadline || '',
                        pagination: {
                            count: tasksData.count || tasksList.length,
                            next: tasksData.next || null,
                            previous: tasksData.previous || null,
                            currentPage: page,
                        }
                    };

                    setPagination(plan.pagination);
                    writeGeneratedTaskPlan(selectedProjectKey, plan);
                    hydrateGeneratedPlan(plan);

                    return {
                        sprints: plan.sprints,
                        milestones: plan.milestones,
                        tasks: tasksList,
                        projectDeadline: plan.project_deadline,
                    };
                }
            } else {
                console.warn('Local tasks API failed, falling back to localStorage');
            }

            // Fallback to localStorage if API returns empty or fails
            const cached = readGeneratedTaskPlan(selectedProjectKey);
            if (cached) {
                hydrateGeneratedPlan(cached);
                return {
                    sprints: Array.isArray(cached?.sprints) ? cached.sprints : [],
                    milestones: Array.isArray(cached?.milestones) ? cached.milestones : [],
                    tasks: Array.isArray(cached?.tasks) ? cached.tasks : [],
                    projectDeadline: cached?.project_deadline || '',
                };
            }

            return { sprints: [], milestones: [], tasks: [], projectDeadline: '' };

        } catch (e) {
            setError(e?.message || 'Failed to load tasks');
            return null;
        } finally {
            setIsLoading(false);
        }
    }, [selectedProjectKey, hydrateGeneratedPlan, token, projectInfo, projectDeadline]);

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

    // Helper to check if all tasks in a sprint are selected
    const isSprintFullySelected = useCallback((sprintId) => {
        const sprintTasks = tasks.filter(t => {
            const taskSprintId = extractEntityId(t, 'sprint');
            const taskSprintKey = taskSprintId != null ? String(taskSprintId) : 'unassigned_sprint';
            return taskSprintKey === String(sprintId) && !t.synced_to_nxdune;
        });
        return sprintTasks.length > 0 && sprintTasks.every(t => t.selected);
    }, [tasks]);

    // Helper to check if all tasks in a milestone are selected
    const isMilestoneFullySelected = useCallback((sprintId, milestoneId) => {
        const milestoneTasks = tasks.filter(t => {
            const taskSprintId = extractEntityId(t, 'sprint');
            const taskMilestoneId = extractEntityId(t, 'milestone');
            const taskSprintKey = taskSprintId != null ? String(taskSprintId) : 'unassigned_sprint';
            const taskMilestoneKey = taskMilestoneId != null ? String(taskMilestoneId) : 'unassigned_milestone';
            return taskSprintKey === String(sprintId) && taskMilestoneKey === String(milestoneId) && !t.synced_to_nxdune;
        });
        return milestoneTasks.length > 0 && milestoneTasks.every(t => t.selected);
    }, [tasks]);

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

            // Task token is optional for local AI generation — only needed for NXDUNE sync.
            // We proceed without it; the backend will skip sync if no token is available.

            // Now proceed with task generation
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

            // Retrieve user branch name if stored for brownfield projects
            let storedBranch = null;
            try {
                const storedRaw = localStorage.getItem(`repo_context_meta_${selectedProjectKey}`) || sessionStorage.getItem(`repo_context_meta_${selectedProjectKey}`);
                if (storedRaw) {
                    const parsed = JSON.parse(storedRaw);
                    storedBranch = parsed.userBranch || parsed.branch;
                }
            } catch (err) {
                console.warn('Failed to parse stored repo context branch:', err);
            }

            const generatePayload = {
                project_token: selectedProjectKey,
                auto_create_plan: true,
                custom_rules: customRules,
                project_type: projectType,
                process_mode: processMode,
                branch: storedBranch || null,
            };

            if (prerequisites && prerequisites.length > 0) {
                generatePayload.prerequisites = prerequisites;
            }

            // Use new local task generation endpoint
            const generateRes = await fetch(API_ENDPOINTS.AGENT_TASKS_GENERATE_LOCAL, {
                method: 'POST',
                headers,
                body: JSON.stringify(generatePayload),
            });
            const generateJson = await generateRes.json().catch(() => ({}));
            if (!generateRes.ok) {
                const errorMsg = getErrorMessage(generateJson, 'Failed to generate tasks');
                if (errorMsg.toLowerCase().includes('already exists') || errorMsg.toLowerCase().includes('will use the existing')) {
                    console.warn('Sprint/milestone already exists, continuing:', errorMsg);
                } else {
                    throw new Error(errorMsg);
                }
            }

            // Reload from DB instead of using localStorage
            await loadData(1);

            const createdCount = Array.isArray(generateJson?.tasks)
                ? generateJson.tasks.length
                : (generateJson?.tasks_created ?? 0);
            const backendMessage =
                typeof generateJson?.message === 'string' ? generateJson.message : '';
            const syncedToNxdune = generateJson?.synced_to_nxdune === true;
            const syncError = generateJson?.sync_error;

            if (backendMessage) {
                setSuccess(backendMessage + (syncedToNxdune ? ' ✅ Synced to NXDUNE.' : ''));
            } else {
                setSuccess(`Generated ${createdCount} task preview item(s).` + (syncedToNxdune ? ' ✅ Synced to NXDUNE.' : ''));
            }
            if (!syncedToNxdune && syncError) {
                console.warn('NXDUNE sync failed:', syncError);
                setError(`Tasks generated but NXDUNE sync failed: ${syncError}`);
            }
            setLiveCreatedTaskCount(createdCount);
            setCreationStageIndex(1);
        } catch (e) {
            setError(e?.message || 'Task creation failed');
        } finally {
            setIsGenerating(false);
        }
    }, [selectedProjectKey, selectedProject, buildHeaders, customRules, hydrateGeneratedPlan, resolveTaskToken, projectInfo, token, projectDeadline]);

    const handleSync = useCallback(async () => {
        if (!selectedProjectKey || !taskToken) return;
        setIsSyncing(true);
        setError('');
        setSuccess('');
        try {
            // First, save all selected tasks to the backend
            const selectedTaskIds = tasks.filter(t => t.selected && !t.synced_to_nxdune).map(t => t.id);
            
            if (selectedTaskIds.length === 0) {
                setError('No tasks selected for sync. Please select at least one task.');
                setIsSyncing(false);
                return;
            }
            
            // Save selections to backend
            const selectionRes = await fetch(API_ENDPOINTS.AGENT_TASKS_SELECTION, {
                method: 'PATCH',
                headers: {
                    'Authorization': `Bearer ${token}`,
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    task_ids: selectedTaskIds,
                    selected: true,
                    project_token: selectedProjectKey,
                }),
            });
            
            if (!selectionRes.ok) {
                const data = await selectionRes.json().catch(() => ({}));
                const errorMsg = typeof data.detail === 'string' 
                    ? data.detail 
                    : (typeof data.message === 'string' ? data.message : 'Failed to save task selection');
                console.error('Selection API error:', data);
                setError(errorMsg);
                setIsSyncing(false);
                return;
            }
            
            // Now sync to NxDune
            const url = new URL(API_ENDPOINTS.AGENT_TASKS_SYNC);
            url.searchParams.set('project_token', selectedProjectKey);
            const res = await fetch(url.toString(), {
                method: 'POST',
                headers: { Authorization: `Bearer ${token}`, 'x-task-token': taskToken },
            });
            const data = await res.json().catch(() => ({}));
            if (res.ok && data.status === 'success') {
                const warningMsg = data.warning ? ` (${data.warning})` : '';
                setSuccess(`✅ Synced ${data.synced} task(s) to NXDUNE.${warningMsg}`);
                await loadData();
            } else {
                const msg = data.detail || data.message || data.error || 'Sync failed';
                setError(`Sync failed: ${msg}`);
            }
        } catch (e) {
            setError(e?.message || 'Sync failed');
        } finally {
            setIsSyncing(false);
        }
    }, [selectedProjectKey, taskToken, token, loadData, tasks]);

    const handleTaskSelection = useCallback((taskId, selected) => {
        // Update local state only - no API call yet
        setTasks(prevTasks => 
            prevTasks.map(t => 
                t.id === taskId ? { ...t, selected } : t
            )
        );
    }, []);

    const handleBulkSelection = useCallback((selectAll) => {
        // Update local state only - no API call yet
        setTasks(prevTasks => 
            prevTasks.map(t => 
                !t.synced_to_nxdune ? { ...t, selected: selectAll } : t
            )
        );
    }, []);

    const handleSprintSelection = useCallback((sprintId, selected) => {
        // Select/deselect all tasks in a specific sprint
        setTasks(prevTasks => 
            prevTasks.map(t => {
                const taskSprintId = extractEntityId(t, 'sprint');
                const taskSprintKey = taskSprintId != null ? String(taskSprintId) : 'unassigned_sprint';
                
                if (taskSprintKey === String(sprintId) && !t.synced_to_nxdune) {
                    return { ...t, selected };
                }
                return t;
            })
        );
    }, []);

    const handleMilestoneSelection = useCallback((sprintId, milestoneId, selected) => {
        // Select/deselect all tasks in a specific milestone within a sprint
        setTasks(prevTasks => 
            prevTasks.map(t => {
                const taskSprintId = extractEntityId(t, 'sprint');
                const taskMilestoneId = extractEntityId(t, 'milestone');
                const taskSprintKey = taskSprintId != null ? String(taskSprintId) : 'unassigned_sprint';
                const taskMilestoneKey = taskMilestoneId != null ? String(taskMilestoneId) : 'unassigned_milestone';
                
                if (taskSprintKey === String(sprintId) && taskMilestoneKey === String(milestoneId) && !t.synced_to_nxdune) {
                    return { ...t, selected };
                }
                return t;
            })
        );
    }, []);

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
                                    onChange={(e) => handleProjectTypeChange(e.target.value)}
                                    className="bg-app-bg-card border border-app-border rounded px-2 py-0.5 text-xs font-semibold text-app-primary-hover focus:outline-none focus:ring-1 focus:ring-app-primary"
                                >
                                    <option value="greenfield">Greenfield (New Build)</option>
                                    <option value="brownfield">Brownfield (Enhancement)</option>
                                    <option value="modernization">Modernization (Migration)</option>
                                </select>
                            </div>
                        </div>

                        {projectType !== 'greenfield' && (
                            <div className="text-xs px-3 py-2 bg-blue-500/10 border border-blue-500/20 text-blue-400 rounded-lg flex items-center gap-2">
                                <Sparkles className="w-3.5 h-3.5 text-blue-400 animate-pulse" />
                                <span>Auto-detected <strong>{projectType === 'brownfield' ? 'Brownfield' : 'Modernization'}</strong> development from repository analysis.</span>
                            </div>
                        )}

                        <button
                            onClick={handleMasterCreate}
                            disabled={!selectedProjectKey || isGenerating || isLoadingProjectInfo || isResolvingTaskToken}
                            className={`w-full inline-flex items-center justify-center gap-2 px-4 py-3 rounded-lg font-bold text-sm transition-colors ${(!selectedProjectKey || isGenerating || isLoadingProjectInfo || isResolvingTaskToken)
                                ? 'bg-app-border text-app-text-muted cursor-not-allowed'
                                : 'bg-gradient-to-r from-app-primary to-app-primary text-app-bg-card hover:from-app-primary-hover hover:to-app-primary-hover'
                                }`}
                        >
                            {isGenerating ? <Loader2 className="w-4 h-4 animate-spin" /> : (isLoadingProjectInfo || isResolvingTaskToken) ? <Loader2 className="w-4 h-4 animate-spin" /> : <Sparkles className="w-4 h-4" />}
                            {isGenerating ? 'Creating Plan...' : (isLoadingProjectInfo || isResolvingTaskToken) ? 'Loading Project Info...' : 'Create Tasks (AI Auto Plan)'}
                        </button>
                        {!selectedProjectKey && (
                            <p className="text-xs text-app-status-warning bg-app-status-warningBg border border-amber-200 rounded-lg px-3 py-2">
                                No project selected. Select a project from the sidebar or top project dropdown.
                            </p>
                        )}
                        {selectedProjectKey && (isLoadingProjectInfo || isResolvingTaskToken) && (
                            <p className="text-xs text-app-primary-hover bg-app-primary-light border border-app-primary-ring rounded-lg px-3 py-2 flex items-start gap-2">
                                <Loader2 className="w-4 h-4 mt-0.5 shrink-0 animate-spin" />
                                <span>Loading project information and deadline. Please wait before creating tasks...</span>
                            </p>
                        )}
                        {selectedProjectKey && tasks.length > 0 && !isLoadingProjectInfo && !isResolvingTaskToken && (
                            <p className="text-xs text-app-primary-hover bg-app-primary-light border border-app-primary-ring rounded-lg px-3 py-2 flex items-start gap-2">
                                <CheckCircle2 className="w-4 h-4 mt-0.5 shrink-0" />
                                <span>Tasks have been created for this project. You can regenerate them or view existing tasks below.</span>
                            </p>
                        )}
                        {tasks.some(t => !t.synced_to_nxdune && t.selected) && taskToken && !isLoadingProjectInfo && !isResolvingTaskToken && (
                            <button
                                onClick={handleSync}
                                disabled={isSyncing}
                                className="w-full inline-flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg font-bold text-sm transition-colors bg-gradient-to-r from-emerald-600 to-emerald-700 text-white hover:from-emerald-700 hover:to-emerald-800 disabled:opacity-60 disabled:cursor-not-allowed"
                            >
                                {isSyncing ? <Loader2 className="w-4 h-4 animate-spin" /> : <RefreshCw className="w-4 h-4" />}
                                {isSyncing ? 'Syncing...' : `Sync ${tasks.filter(t => !t.synced_to_nxdune && t.selected).length} selected task(s) to NXDUNE`}
                            </button>
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
                            <div className="flex items-center gap-2">
                                {tasks.length > 0 && tasks.some(t => !t.synced_to_nxdune) && (
                                    <>
                                        <button
                                            onClick={() => handleBulkSelection(true)}
                                            disabled={isLoading}
                                            className="inline-flex items-center gap-2 px-3 py-2 rounded-lg text-xs font-bold bg-app-primary text-white hover:bg-app-primary-hover disabled:opacity-50"
                                        >
                                            Select All
                                        </button>
                                        <button
                                            onClick={() => handleBulkSelection(false)}
                                            disabled={isLoading}
                                            className="inline-flex items-center gap-2 px-3 py-2 rounded-lg text-xs font-bold bg-app-bg-muted text-app-text-main hover:bg-app-bg-hover disabled:opacity-50"
                                        >
                                            Deselect All
                                        </button>
                                    </>
                                )}
                                <button
                                    onClick={() => loadData(1)}
                                    disabled={isLoading}
                                    className="inline-flex items-center gap-2 px-3 py-2 rounded-lg text-xs font-bold bg-app-bg-muted text-app-text-main hover:bg-app-bg-hover"
                                >
                                    {isLoading ? <Loader2 className="w-3 h-3 animate-spin" /> : <RefreshCw className="w-3 h-3" />}
                                    Refresh
                                </button>
                            </div>
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
                                            <input
                                                type="checkbox"
                                                checked={isSprintFullySelected(sprintGroup.sprint.id)}
                                                onChange={(e) => handleSprintSelection(sprintGroup.sprint.id, e.target.checked)}
                                                className="w-4 h-4 text-app-primary border-app-border rounded focus:ring-app-primary focus:ring-2"
                                                title="Select all tasks in this sprint"
                                            />
                                            <FolderKanban className="w-4 h-4 text-app-primary-hover" />
                                            <p className="text-sm font-bold text-app-primary-dark">{sprintGroup.sprint.name}</p>
                                        </div>
                                        <div className="p-4 space-y-3">
                                            {Array.from(sprintGroup.milestones.values()).map((milestoneGroup) => (
                                                <div key={`m-${milestoneGroup.milestone.id}`} className="border border-app-border rounded-lg">
                                                    <div className="px-3 py-2 bg-violet-50 border-b border-app-border-light flex items-center gap-2">
                                                        <input
                                                            type="checkbox"
                                                            checked={isMilestoneFullySelected(sprintGroup.sprint.id, milestoneGroup.milestone.id)}
                                                            onChange={(e) => handleMilestoneSelection(sprintGroup.sprint.id, milestoneGroup.milestone.id, e.target.checked)}
                                                            className="w-4 h-4 text-violet-600 border-violet-300 rounded focus:ring-violet-500 focus:ring-2"
                                                            title="Select all tasks in this milestone"
                                                        />
                                                        <Milestone className="w-4 h-4 text-violet-700" />
                                                        <p className="text-xs font-bold text-violet-900">{milestoneGroup.milestone.name}</p>
                                                    </div>
                                                    <div className="p-3 space-y-2">
                                                        {milestoneGroup.tasks.map((task) => (
                                                            <div key={task.id || task.task_id || task.taskName} className="border border-app-border rounded-lg px-3 py-2 bg-app-bg-card flex items-start gap-3">
                                                                <input
                                                                    type="checkbox"
                                                                    checked={task.selected || false}
                                                                    disabled={task.synced_to_nxdune}
                                                                    onChange={(e) => handleTaskSelection(task.id, e.target.checked)}
                                                                    className="mt-1 w-4 h-4 text-app-primary border-app-border rounded focus:ring-app-primary focus:ring-2 disabled:opacity-50 disabled:cursor-not-allowed"
                                                                />
                                                                <div className="flex-1">
                                                                    <div className="flex items-start justify-between gap-2">
                                                                        <p className="text-sm font-semibold text-app-text-main">{task.title || task.taskName || 'Untitled Task'}</p>
                                                                        {task.synced_to_nxdune && (
                                                                            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-700 text-[10px] font-bold uppercase tracking-wide">
                                                                                <CheckCircle2 className="w-3 h-3" />
                                                                                Synced
                                                                            </span>
                                                                        )}
                                                                    </div>
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
                                                            </div>
                                                        ))}
                                                    </div>
                                                </div>
                                            ))}
                                        </div>
                                    </div>
                                ))}

                                {pagination.count > 0 && (
                                    <div className="mt-6 flex items-center justify-between border-t border-app-border-light pt-4 px-1">
                                        <div className="text-xs text-app-text-muted">
                                            Showing <span className="font-semibold text-app-text-main">{tasks.length}</span> of <span className="font-semibold text-app-text-main">{pagination.count}</span> tasks
                                        </div>
                                        <div className="flex items-center gap-2">
                                            <button
                                                onClick={() => loadData(pagination.currentPage - 1)}
                                                disabled={!pagination.previous || isLoading}
                                                className={`px-3 py-1.5 text-xs font-bold rounded-lg border transition-all ${!pagination.previous || isLoading
                                                    ? 'border-app-border text-app-text-muted cursor-not-allowed opacity-50'
                                                    : 'border-app-border bg-app-bg-card text-app-text-main hover:bg-app-bg-hover active:scale-95'
                                                    }`}
                                            >
                                                Previous
                                            </button>
                                            <div className="flex items-center justify-center min-w-[2rem] h-8 rounded-lg bg-app-primary-light text-app-primary-hover text-xs font-extrabold">
                                                {pagination.currentPage}
                                            </div>
                                            <button
                                                onClick={() => loadData(pagination.currentPage + 1)}
                                                disabled={!pagination.next || isLoading}
                                                className={`px-3 py-1.5 text-xs font-bold rounded-lg border transition-all ${!pagination.next || isLoading
                                                    ? 'border-app-border text-app-text-muted cursor-not-allowed opacity-50'
                                                    : 'border-app-border bg-app-bg-card text-app-text-main hover:bg-app-bg-hover active:scale-95'
                                                    }`}
                                            >
                                                Next
                                            </button>
                                        </div>
                                    </div>
                                )}
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
                        {/* <div className="mt-4 rounded-xl border border-app-primary-light bg-app-primary-light px-4 py-3 flex items-center justify-between">
                            <span className="text-sm font-semibold text-app-primary-dark">Preview tasks generated</span>
                            <span className="text-2xl font-extrabold text-app-primary-hover tabular-nums">{liveCreatedTaskCount}</span>
                        </div> */}
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
