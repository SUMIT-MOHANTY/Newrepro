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
    ChevronDown,
    ChevronRight,
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

if (typeof document !== 'undefined') {
    const existingStyle = document.getElementById('progress-slide-style');
    if (!existingStyle) {
        const styleTag = document.createElement('style');
        styleTag.id = 'progress-slide-style';
        styleTag.textContent = `
            @keyframes progressSlide {
                0% { transform: translateX(-100%); }
                100% { transform: translateX(100%); }
            }
        `;
        document.head.appendChild(styleTag);
    }
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

    const [collapsedSprints, setCollapsedSprints] = useState({});
    const toggleSprint = (sprintId) => {
        setCollapsedSprints(prev => ({
            ...prev,
            [sprintId]: !prev[sprintId]
        }));
    };

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
            const selectedTasksToSync = tasks.filter(t => t.selected && !t.synced_to_nxdune);
            
            if (selectedTasksToSync.length === 0) {
                setError('No tasks selected for sync. Please select at least one task.');
                setIsSyncing(false);
                return;
            }
            
            // Save selections/tasks to backend first
            await saveSelectionsToDb();
            
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

    const saveSelectionsToDb = useCallback(async () => {
        if (!selectedProjectKey) return;
        if (!Array.isArray(tasks) || tasks.length === 0) return;

        const res = await fetch(API_ENDPOINTS.AGENT_TASKS_SAVE_LOCAL, {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${token}`,
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                project_token: selectedProjectKey,
                tasks: tasks,
            }),
        });

        if (!res.ok) {
            const data = await res.json().catch(() => ({}));
            const errorMsg = typeof data.detail === 'string'
                ? data.detail
                : (typeof data.message === 'string' ? data.message : 'Failed to save tasks locally');
            throw new Error(errorMsg);
        }
        
        await loadData(1);
    }, [selectedProjectKey, tasks, token, loadData]);

    const handleSaveSelection = useCallback(async () => {
        if (!selectedProjectKey) {
            setError('Select a project before saving.');
            return;
        }
        setIsLoading(true);
        setError('');
        setSuccess('');
        try {
            await saveSelectionsToDb();
            setSuccess('Task selection saved successfully locally. Click "Start the Process" at the top right to proceed.');
        } catch (e) {
            setError(e?.message || 'Failed to save task selection.');
        } finally {
            setIsLoading(false);
        }
    }, [selectedProjectKey, saveSelectionsToDb]);

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

    const handleStartProcess = useCallback(async () => {
        if (!selectedProjectKey) return;
        setIsLoading(true);
        setError('');
        setSuccess('');
        try {
            if (tasks.length > 0) {
                await saveSelectionsToDb();
            }
            if (processMode === 'ai_assist') {
                window.location.href = 'vscode:extension/bourntec-Solutions.n-mod-vscode-assistant';
            } else {
                navigate('/resource-onboarding', { state: { processMode } });
            }
        } catch (e) {
            setError(e?.message || 'Failed to save task selection.');
        } finally {
            setIsLoading(false);
        }
    }, [selectedProjectKey, tasks, saveSelectionsToDb, processMode, navigate]);

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
                        <div className="flex justify-center mb-5">
                            <div className="w-12 h-12 rounded-xl bg-app-primary-light/50 border border-app-primary-ring flex items-center justify-center animate-pulse shadow-sm shadow-app-primary/10">
                                <Sparkles className="w-6 h-6 text-app-primary" />
                            </div>
                        </div>
                        <h3 className="text-lg font-bold text-app-text-main">Loading Task Creation</h3>
                        <p className="mt-2 text-sm text-app-text-label leading-relaxed">
                            {isResolvingTaskToken || isLoadingProjectInfo
                                ? <>Fetching project information for <span className="font-semibold text-app-text-main">{selectedProject?.name || 'selected project'}</span>.</>
                                : <>Loading the local task preview for <span className="font-semibold text-app-text-main">{selectedProject?.name || 'selected project'}</span>.</>
                            }
                        </p>
                        <p className="mt-1.5 text-xs text-app-text-muted">
                            {isResolvingTaskToken || isLoadingProjectInfo
                                ? 'Please wait while we fetch the project details...'
                                : 'The page will open as soon as the saved preview is ready.'
                            }
                        </p>
                        <div className="mt-5 w-28 mx-auto bg-app-border-light/40 rounded-full h-1.5 overflow-hidden relative">
                            <div className="bg-app-primary h-full w-full rounded-full absolute inset-0 animate-[progressSlide_1.5s_infinite_linear]"></div>
                        </div>
                    </div>
                </div>
            </div>
        );
    }

    return (
        <>
            <div className={`h-full overflow-y-auto bg-gradient-to-br from-app-bg-page via-app-bg-page to-app-primary-light/10 ${isGenerating ? 'blur-sm' : ''}`}>
                <div className="max-w-6xl mx-auto px-4 py-6 space-y-6">
                    {/* Top Premium Gradient Banner Header */}
                    <div className="relative overflow-hidden rounded-2xl bg-gradient-to-r from-slate-900 via-indigo-950 to-blue-950 text-white shadow-xl border border-indigo-500/10 p-6 sm:p-7">
                        <div className="absolute top-0 right-0 w-64 h-64 bg-app-primary/10 rounded-full blur-3xl -mr-16 -mt-16 pointer-events-none"></div>
                        <div className="absolute bottom-0 left-0 w-48 h-48 bg-indigo-500/5 rounded-full blur-2xl -ml-16 -mb-16 pointer-events-none"></div>
                        
                        <div className="relative flex flex-col md:flex-row md:items-center justify-between gap-6">
                            <div>
                                <div className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-white/10 border border-white/10 text-[10px] font-extrabold tracking-widest uppercase text-indigo-200">
                                    <Sparkles className="w-3 h-3 text-indigo-300 animate-pulse" />
                                    Master Agent Planner
                                </div>
                                <h2 className="text-2xl sm:text-3xl font-black tracking-tight mt-3">Create Sprint, Milestone & Tasks</h2>
                                <p className="text-sm text-slate-300 mt-2 flex items-center gap-2">
                                    <span>Project:</span>
                                    <span className="px-2 py-0.5 rounded bg-indigo-500/20 border border-indigo-500/30 text-white font-semibold text-xs">
                                        {selectedProject?.name || 'Not selected'}
                                    </span>
                                </p>
                                <div className="flex flex-wrap gap-2 mt-3 text-xs text-slate-400">
                                    <span className="flex items-center gap-1">
                                        Mode: <span className="font-semibold text-white">
                                            {processMode === 'ai_first' ? 'AI-First' :
                                                processMode === 'coexistence' ? 'Coexistence' :
                                                    processMode === 'developer_only' ? 'Developer Only' :
                                                        processMode === 'ai_assist' ? 'AI Assist' :
                                                            processMode === 'vibe_coding' ? 'Vibe Coding' :
                                                                processMode}
                                        </span>
                                    </span>
                                </div>
                                {processMode === 'ai_assist' && (
                                    <div className="mt-4 inline-flex items-center gap-2 px-3 py-1.5 bg-indigo-500/25 border border-indigo-500/35 rounded-lg text-xs font-semibold text-indigo-200">
                                        <Sparkles className="w-3.5 h-3.5 text-indigo-300 animate-bounce" />
                                        <span>AI Assist Active: You will be redirected to VS Code's N-Mod Extension.</span>
                                    </div>
                                )}
                            </div>
                            <button
                                onClick={handleStartProcess}
                                className="group inline-flex items-center justify-center gap-2 px-6 py-3.5 text-sm font-extrabold text-white bg-gradient-to-r from-emerald-500 to-teal-600 hover:from-emerald-600 hover:to-teal-700 rounded-xl shadow-lg shadow-emerald-500/20 active:scale-95 duration-200 shrink-0 border-0"
                            >
                                Start the Process
                                <ArrowRight className="w-4 h-4 group-hover:translate-x-1 transition-transform" />
                            </button>
                        </div>
                    </div>

                    {/* AI Planning & Configuration Section */}
                    <div className="bg-app-bg-card rounded-2xl border border-app-border-light shadow-md p-6 space-y-5 relative overflow-hidden">
                        <div className="absolute top-0 left-0 w-1 h-full bg-app-primary"></div>
                        <div className="flex items-center justify-between border-b border-app-border-light pb-3">
                            <h3 className="text-sm font-bold text-app-text-main flex items-center gap-2">
                                <Sparkles className="w-4 h-4 text-app-primary" />
                                AI Planner Config
                            </h3>
                            <span className="text-xs text-app-text-muted">Generate & customize your plan strategy</span>
                        </div>
                        
                        <p className="text-sm text-app-text-label leading-relaxed">
                            The Master Agent parses project context to generate a structured Sprint/Milestone task model, uploads the results to the external task API, and tracks it dynamically.
                        </p>
                        
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                            {/* Deadline Display */}
                            <div className="flex items-center gap-3 px-4 py-3 bg-app-bg-page border border-app-border-light rounded-xl">
                                <CalendarDays className="w-5 h-5 text-indigo-500 shrink-0" />
                                <div className="min-w-0 flex-1">
                                    <p className="text-[10px] font-bold text-app-text-muted uppercase tracking-wider">Project Deadline</p>
                                    <p className="text-sm font-semibold text-app-text-main truncate mt-0.5">
                                        {projectDeadline || 'Not specified'}
                                    </p>
                                </div>
                            </div>
                            
                            {/* Strategy Select */}
                            <div className="flex items-center gap-3 px-4 py-3 bg-app-bg-page border border-app-border-light rounded-xl">
                                <FolderKanban className="w-5 h-5 text-app-primary shrink-0" />
                                <div className="min-w-0 flex-1">
                                    <p className="text-[10px] font-bold text-app-text-muted uppercase tracking-wider">Plan Strategy</p>
                                    <select
                                        value={projectType}
                                        onChange={(e) => handleProjectTypeChange(e.target.value)}
                                        className="w-full bg-transparent border-0 p-0 text-sm font-semibold text-app-primary-hover focus:outline-none focus:ring-0 mt-0.5 cursor-pointer"
                                    >
                                        <option value="greenfield">Greenfield (New Build)</option>
                                        <option value="brownfield">Brownfield (Enhancement)</option>
                                        <option value="modernization">Modernization (Migration)</option>
                                    </select>
                                </div>
                            </div>
                        </div>

                        {projectType !== 'greenfield' && (
                            <div className="text-xs px-4 py-3 bg-blue-500/10 border border-blue-500/20 text-blue-600 dark:text-blue-400 rounded-xl flex items-center gap-2.5">
                                <Sparkles className="w-4 h-4 text-blue-500 animate-pulse shrink-0" />
                                <span>Auto-detected <strong>{projectType === 'brownfield' ? 'Brownfield' : 'Modernization'}</strong> development pattern based on repository architecture.</span>
                            </div>
                        )}
                        
                        <div className="space-y-3 pt-2">
                            <button
                                onClick={handleMasterCreate}
                                disabled={!selectedProjectKey || isGenerating || isLoadingProjectInfo || isResolvingTaskToken}
                                className={`inline-flex items-center gap-2 px-4 py-2 rounded-lg font-semibold text-sm transition-all duration-200 active:scale-95 ${
                                    (!selectedProjectKey || isGenerating || isLoadingProjectInfo || isResolvingTaskToken)
                                        ? 'bg-app-border text-app-text-muted cursor-not-allowed border border-app-border'
                                        : 'bg-app-primary hover:bg-app-primary-hover text-white shadow-sm hover:shadow-md'
                                }`}
                            >
                                {isGenerating ? (
                                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                                ) : (isLoadingProjectInfo || isResolvingTaskToken) ? (
                                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                                ) : (
                                    <Sparkles className="w-3.5 h-3.5" />
                                )}
                                {isGenerating ? 'Creating Plan...' : (isLoadingProjectInfo || isResolvingTaskToken) ? 'Loading...' : 'Create Tasks (AI Auto Plan)'}
                            </button>

                            {!selectedProjectKey && (
                                <p className="text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2">
                                    No project selected. Select a project from the sidebar to initialize planning.
                                </p>
                            )}

                            {selectedProjectKey && (isLoadingProjectInfo || isResolvingTaskToken) && (
                                <div className="text-xs text-app-primary bg-app-primary-light border border-app-primary-ring rounded-lg px-3 py-2 flex items-center gap-2">
                                    <Loader2 className="w-3.5 h-3.5 shrink-0 animate-spin" />
                                    <span>Retrieving project context. Creating tasks will be unlocked shortly.</span>
                                </div>
                            )}

                            {selectedProjectKey && tasks.length > 0 && !isLoadingProjectInfo && !isResolvingTaskToken && (
                                <div className="text-xs text-emerald-800 bg-emerald-50 border border-emerald-200 rounded-lg px-3 py-2 flex items-center gap-2">
                                    <CheckCircle2 className="w-3.5 h-3.5 shrink-0 text-emerald-600" />
                                    <span>Task roadmap generated. Modify selections, sync, or regenerate below.</span>
                                </div>
                            )}

                            {selectedProjectKey && tasks.length > 0 && !isLoadingProjectInfo && !isResolvingTaskToken && (
                                <div className="flex flex-wrap items-center gap-2 pt-1">
                                    {tasks.some(t => !t.synced_to_nxdune && t.selected) && taskToken && (
                                        <button
                                            onClick={handleSync}
                                            disabled={isSyncing || isLoading}
                                            className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-lg font-semibold text-xs transition-all duration-200 bg-emerald-600 hover:bg-emerald-700 text-white shadow-sm active:scale-95 disabled:opacity-60 disabled:cursor-not-allowed"
                                        >
                                            {isSyncing ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <RefreshCw className="w-3.5 h-3.5" />}
                                            {isSyncing ? 'Syncing...' : `Sync ${tasks.filter(t => !t.synced_to_nxdune && t.selected).length} to NXDUNE`}
                                        </button>
                                    )}
                                    <button
                                        onClick={handleSaveSelection}
                                        disabled={isLoading || isSyncing}
                                        className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-lg font-semibold text-xs transition-all duration-200 bg-indigo-600 hover:bg-indigo-700 text-white shadow-sm active:scale-95 disabled:opacity-60 disabled:cursor-not-allowed"
                                    >
                                        {isLoading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <CheckCircle2 className="w-3.5 h-3.5" />}
                                        {isLoading ? 'Saving...' : tasks.some(t => t.selected) ? `Save Selection (${tasks.filter(t => t.selected).length})` : 'Save Selection'}
                                    </button>
                                </div>
                            )}
                        </div>

                        {error && (
                            <div className="text-xs text-app-status-error bg-app-status-errorBg border border-red-200 rounded-xl px-4 py-3">{error}</div>
                        )}
                        {success && (
                            <div className="text-xs text-app-status-success bg-app-status-successBg border border-emerald-200 rounded-xl px-4 py-3 flex items-start gap-2.5">
                                <CheckCircle2 className="w-4 h-4 shrink-0 text-emerald-500 mt-0.5" />
                                <span>{success}</span>
                            </div>
                        )}
                    </div>

                    {/* Task Tree Grid / Accordion Grouping */}
                    <div className="bg-app-bg-card rounded-2xl border border-app-border-light shadow-md p-6 space-y-6">
                        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-app-border-light pb-4">
                            <div>
                                <h3 className="text-base font-extrabold text-app-text-main">Project Roadmap</h3>
                                <p className="text-xs text-app-text-muted mt-1">Sprints, milestones, and development work items</p>
                            </div>
                            <div className="flex flex-wrap items-center gap-2">
                                {tasks.length > 0 && tasks.some(t => !t.synced_to_nxdune) && (
                                    <>
                                        <button
                                            onClick={() => handleBulkSelection(true)}
                                            disabled={isLoading}
                                            className="px-3.5 py-2 rounded-lg text-xs font-bold bg-app-primary hover:bg-app-primary-hover text-white transition-all shadow-sm"
                                        >
                                            Select All
                                        </button>
                                        <button
                                            onClick={() => handleBulkSelection(false)}
                                            disabled={isLoading}
                                            className="px-3.5 py-2 rounded-lg text-xs font-bold bg-app-bg-page border border-app-border text-app-text-main hover:bg-app-bg-hover transition-all"
                                        >
                                            Deselect All
                                        </button>
                                    </>
                                )}
                                <button
                                    onClick={() => loadData(1)}
                                    disabled={isLoading}
                                    className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-lg text-xs font-bold bg-app-bg-page border border-app-border text-app-text-main hover:bg-app-bg-hover transition-all"
                                >
                                    {isLoading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <RefreshCw className="w-3.5 h-3.5" />}
                                    Refresh
                                </button>
                            </div>
                        </div>

                        {isLoading ? (
                            <div className="py-12 text-center text-sm text-app-text-muted flex flex-col items-center justify-center gap-2">
                                <Loader2 className="w-8 h-8 text-app-primary animate-spin" />
                                <span>Loading generated roadmap...</span>
                            </div>
                        ) : groupedTasks.length === 0 ? (
                            <div className="py-16 text-center text-sm text-app-text-muted border border-dashed border-app-border rounded-xl bg-app-bg-page/50">
                                <FolderKanban className="w-10 h-10 text-app-text-muted mx-auto opacity-40 mb-3" />
                                <p className="font-semibold">No tasks generated yet</p>
                                <p className="text-xs text-app-text-muted mt-1">Use the config card above to generate sprint tasks with AI.</p>
                            </div>
                        ) : (
                            <div className="space-y-5">
                                {groupedTasks.map((sprintGroup) => {
                                    const isCollapsed = collapsedSprints[sprintGroup.sprint.id];
                                    const sprintTasks = tasks.filter(t => {
                                        const taskSprintId = extractEntityId(t, 'sprint');
                                        const taskSprintKey = taskSprintId != null ? String(taskSprintId) : 'unassigned_sprint';
                                        return taskSprintKey === String(sprintGroup.sprint.id);
                                    });
                                    const selectedSprintTasksCount = sprintTasks.filter(t => t.selected).length;

                                    return (
                                        <div 
                                            key={`s-${sprintGroup.sprint.id}`} 
                                            className="border border-app-border-light rounded-xl overflow-hidden shadow-sm bg-app-bg-page/20"
                                        >
                                            {/* Collapsible Sprint Header */}
                                            <div className="px-4 py-3 bg-app-primary-light/50 border-b border-app-border-light flex items-center justify-between gap-3 hover:bg-app-primary-light/60 transition-colors select-none">
                                                <div className="flex items-center gap-3">
                                                    <input
                                                        type="checkbox"
                                                        checked={isSprintFullySelected(sprintGroup.sprint.id)}
                                                        onChange={(e) => handleSprintSelection(sprintGroup.sprint.id, e.target.checked)}
                                                        className="w-4.5 h-4.5 text-app-primary border-app-border rounded focus:ring-app-primary focus:ring-2 cursor-pointer"
                                                        title="Select all tasks in this sprint"
                                                        onClick={(e) => e.stopPropagation()}
                                                    />
                                                    <div 
                                                        onClick={() => toggleSprint(sprintGroup.sprint.id)}
                                                        className="flex items-center gap-2 cursor-pointer"
                                                    >
                                                        <FolderKanban className="w-4 h-4 text-app-primary-dark" />
                                                        <p className="text-sm font-extrabold text-app-primary-dark">{sprintGroup.sprint.name}</p>
                                                    </div>
                                                    <span className="px-2 py-0.5 text-[10px] font-extrabold rounded-full bg-app-primary-light text-app-primary-hover border border-app-primary-light">
                                                        {selectedSprintTasksCount} / {sprintTasks.length} Selected
                                                    </span>
                                                </div>
                                                <button
                                                    onClick={() => toggleSprint(sprintGroup.sprint.id)}
                                                    className="p-1 rounded hover:bg-app-primary-light transition-colors text-app-primary-dark"
                                                >
                                                    {isCollapsed ? (
                                                        <ChevronRight className="w-4.5 h-4.5" />
                                                    ) : (
                                                        <ChevronDown className="w-4.5 h-4.5" />
                                                    )}
                                                </button>
                                            </div>

                                            {/* Sprints Content Panel */}
                                            {!isCollapsed && (
                                                <div className="p-4 space-y-4">
                                                    {Array.from(sprintGroup.milestones.values()).map((milestoneGroup) => {
                                                        const milestoneTasks = milestoneGroup.tasks;
                                                        const selectedMilestoneCount = milestoneTasks.filter(t => t.selected).length;

                                                        return (
                                                            <div key={`m-${milestoneGroup.milestone.id}`} className="flex gap-4">
                                                                {/* Timeline vertical node line indicator */}
                                                                <div className="hidden sm:flex flex-col items-center shrink-0">
                                                                    <div className="w-7 h-7 rounded-full bg-violet-100 border border-violet-200 flex items-center justify-center text-violet-700 shadow-sm">
                                                                        <Milestone className="w-3.5 h-3.5" />
                                                                    </div>
                                                                    <div className="w-[1.5px] flex-1 bg-gradient-to-b from-violet-200 via-slate-100 to-transparent mt-2"></div>
                                                                </div>

                                                                {/* Milestone Card content */}
                                                                <div className="flex-1 border border-app-border-light rounded-xl overflow-hidden bg-app-bg-card shadow-sm">
                                                                    <div className="px-4 py-2.5 bg-violet-500/5 border-b border-app-border-light flex items-center justify-between gap-3">
                                                                        <div className="flex items-center gap-2.5">
                                                                            <input
                                                                                type="checkbox"
                                                                                checked={isMilestoneFullySelected(sprintGroup.sprint.id, milestoneGroup.milestone.id)}
                                                                                onChange={(e) => handleMilestoneSelection(sprintGroup.sprint.id, milestoneGroup.milestone.id, e.target.checked)}
                                                                                className="w-4 h-4 text-violet-600 border-violet-300 rounded focus:ring-violet-500 focus:ring-2 cursor-pointer"
                                                                                title="Select all tasks in this milestone"
                                                                            />
                                                                            <span className="text-xs font-black tracking-wide text-violet-900 uppercase">
                                                                                {milestoneGroup.milestone.name}
                                                                            </span>
                                                                        </div>
                                                                        <span className="text-[10px] font-bold text-violet-600">
                                                                            {selectedMilestoneCount} / {milestoneTasks.length} Work Items
                                                                        </span>
                                                                    </div>
                                                                    
                                                                    <div className="p-3 space-y-2.5">
                                                                        {milestoneTasks.map((task) => {
                                                                            const prio = String(task.priority || 'medium').toLowerCase();
                                                                            const isHigh = prio.includes('high');
                                                                            const isLow = prio.includes('low');

                                                                            return (
                                                                                <div 
                                                                                    key={task.id || task.task_id || task.taskName} 
                                                                                    className={`group border rounded-xl p-3 bg-app-bg-card flex items-start gap-3 hover:-translate-y-0.5 hover:shadow-md transition-all duration-200 ${
                                                                                        task.selected 
                                                                                            ? 'border-indigo-200 bg-indigo-50/5' 
                                                                                            : 'border-app-border-light'
                                                                                    }`}
                                                                                >
                                                                                    <input
                                                                                        type="checkbox"
                                                                                        checked={task.selected || false}
                                                                                        disabled={task.synced_to_nxdune}
                                                                                        onChange={(e) => handleTaskSelection(task.id, e.target.checked)}
                                                                                        className="mt-1 w-4.5 h-4.5 text-app-primary border-app-border rounded focus:ring-app-primary focus:ring-2 disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer"
                                                                                    />
                                                                                    
                                                                                    <div className="flex-1 min-w-0">
                                                                                        <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-2">
                                                                                            <p className="text-sm font-bold text-app-text-main leading-snug truncate">
                                                                                                {task.title || task.taskName || 'Untitled Task'}
                                                                                            </p>
                                                                                            <div className="flex items-center gap-1.5 shrink-0">
                                                                                                 {task.synced_to_nxdune && (
                                                                                                     <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full bg-emerald-100 text-emerald-700 dark:bg-emerald-950/30 dark:text-emerald-400 text-[9px] font-extrabold uppercase tracking-wider border border-emerald-200/30">
                                                                                                         <CheckCircle2 className="w-2.5 h-2.5" />
                                                                                                         Synced
                                                                                                     </span>
                                                                                                 )}
                                                                                                 {task.selected && !task.synced_to_nxdune && (
                                                                                                     <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full bg-indigo-100 text-indigo-700 dark:bg-indigo-950/30 dark:text-indigo-400 text-[9px] font-extrabold uppercase tracking-wider border border-indigo-200/30">
                                                                                                         <CheckCircle2 className="w-2.5 h-2.5" />
                                                                                                         Saved Locally
                                                                                                     </span>
                                                                                                 )}
                                                                                            </div>
                                                                                        </div>
                                                                                        
                                                                                        <div className="mt-2.5 flex flex-wrap items-center gap-x-4 gap-y-1.5 text-xs text-app-text-muted">
                                                                                            <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-md font-semibold text-[10px] uppercase border ${
                                                                                                isHigh 
                                                                                                    ? 'bg-red-500/10 text-red-600 border-red-500/20' 
                                                                                                    : isLow 
                                                                                                        ? 'bg-emerald-500/10 text-emerald-600 border-emerald-500/20' 
                                                                                                        : 'bg-amber-500/10 text-amber-600 border-amber-500/20'
                                                                                            }`}>
                                                                                                <Flag className="w-2.8 h-2.8 shrink-0" />
                                                                                                {task.priority || 'medium'}
                                                                                            </span>
                                                                                            <span className="inline-flex items-center gap-1 text-[11px]">
                                                                                                <CalendarDays className="w-3.5 h-3.5 text-slate-400" />
                                                                                                Due: {task.planned_end || task.deadline || 'No deadline'}
                                                                                            </span>
                                                                                            <span className="rounded bg-app-bg-page border border-app-border-light px-2 py-0.5 font-bold uppercase tracking-widest text-[9px] text-app-text-label shrink-0">
                                                                                                {task.type || task.task_type || 'task'}
                                                                                            </span>
                                                                                        </div>
                                                                                    </div>
                                                                                </div>
                                                                            );
                                                                        })}
                                                                    </div>
                                                                </div>
                                                            </div>
                                                        );
                                                    })}
                                                </div>
                                            )}
                                        </div>
                                    );
                                })}

                                {pagination.count > 0 && (
                                    <div className="mt-6 flex flex-col sm:flex-row items-center justify-between border-t border-app-border-light pt-5 px-1 gap-4">
                                        <div className="text-xs font-medium text-app-text-muted">
                                            Showing <span className="font-extrabold text-app-text-main">{tasks.length}</span> of <span className="font-extrabold text-app-text-main">{pagination.count}</span> tasks
                                        </div>
                                        <div className="flex items-center gap-2">
                                            <button
                                                onClick={() => loadData(pagination.currentPage - 1)}
                                                disabled={!pagination.previous || isLoading}
                                                className={`px-4 py-2 text-xs font-bold rounded-xl border transition-all duration-250 ${!pagination.previous || isLoading
                                                    ? 'border-app-border text-app-text-muted cursor-not-allowed opacity-40 bg-app-bg-page'
                                                    : 'border-app-border bg-app-bg-card text-app-text-main hover:bg-app-bg-hover active:scale-95'
                                                    }`}
                                            >
                                                Previous
                                            </button>
                                            <div className="flex items-center justify-center min-w-[2.2rem] h-8 rounded-lg bg-indigo-50 text-indigo-700 text-xs font-black border border-indigo-100">
                                                {pagination.currentPage}
                                            </div>
                                            <button
                                                onClick={() => loadData(pagination.currentPage + 1)}
                                                disabled={!pagination.next || isLoading}
                                                className={`px-4 py-2 text-xs font-bold rounded-xl border transition-all duration-250 ${!pagination.next || isLoading
                                                    ? 'border-app-border text-app-text-muted cursor-not-allowed opacity-40 bg-app-bg-page'
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

            {/* Premium Frosted AI Generating Progress Modal Overlay */}
            {isGenerating && (
                <div className="fixed inset-0 z-[300] bg-slate-950/60 backdrop-blur-md flex items-center justify-center p-4">
                    <div className="w-full max-w-lg rounded-2xl border border-indigo-500/10 bg-app-bg-card shadow-2xl p-6 sm:p-8 text-center animate-fade-in relative overflow-hidden" style={{ filter: 'none', backdropFilter: 'none' }}>
                        <div className="absolute top-0 left-0 w-full h-1 bg-gradient-to-r from-blue-500 via-indigo-500 to-purple-500 animate-pulse"></div>
                        <div className="flex justify-center mb-4">
                            <div className="relative">
                                <div className="absolute -inset-1 rounded-full bg-app-primary/30 blur animate-ping"></div>
                                <div className="relative w-12 h-12 rounded-full bg-indigo-50 border border-indigo-100 flex items-center justify-center text-indigo-500">
                                    <Sparkles className="w-6 h-6 text-indigo-500 animate-pulse" />
                                </div>
                            </div>
                        </div>
                        <h3 className="text-xl font-black text-app-text-main tracking-tight">AI Plan Generation In Progress</h3>
                        <p className="mt-2.5 text-sm text-app-text-label leading-relaxed">
                            Parsing the BRD artifacts to design custom sprints, milestones, and development checklists for <span className="font-semibold text-app-text-main">{selectedProject?.name || 'your project'}</span>.
                        </p>
                        
                        <div className="mt-6 space-y-3.5">
                            {PLAN_CREATION_STEPS.map((stepLabel, idx) => {
                                const isDone = idx < creationStageIndex;
                                const isActive = idx === creationStageIndex;
                                return (
                                    <div
                                        key={stepLabel}
                                        className={`flex items-center gap-3.5 rounded-xl border px-4 py-3 text-left transition-all duration-300 ${isDone
                                            ? 'border-emerald-100 bg-emerald-50/20 dark:bg-emerald-950/15'
                                            : isActive
                                                ? 'border-indigo-100 bg-indigo-50/20 dark:bg-indigo-950/15 ring-2 ring-indigo-500/10'
                                                : 'border-app-border-light bg-app-bg-page/50 opacity-55'
                                            }`}
                                    >
                                        {isDone ? (
                                            <CheckCircle2 className="w-5 h-5 text-emerald-500 shrink-0" />
                                        ) : isActive ? (
                                            <Loader2 className="w-5 h-5 text-indigo-500 animate-spin shrink-0" />
                                        ) : (
                                            <div className="w-5 h-5 rounded-full border border-app-border bg-app-bg-page shrink-0" />
                                        )}
                                        <div className="min-w-0 flex-1">
                                            <span className={`text-sm font-bold block ${isDone ? 'text-emerald-700 dark:text-emerald-400' : isActive ? 'text-indigo-700 dark:text-indigo-400' : 'text-app-text-muted'}`}>
                                                {stepLabel}
                                            </span>
                                            {isActive && (
                                                <span className="text-[10px] text-app-text-muted block mt-0.5 animate-pulse">Running planning algorithms...</span>
                                            )}
                                        </div>
                                    </div>
                                );
                            })}
                        </div>
                        <p className="mt-5 text-[11px] text-app-text-muted italic">
                            Planning operations are locked until task structure layout settles.
                        </p>
                    </div>
                </div>
            )}
        </>
    );
}
