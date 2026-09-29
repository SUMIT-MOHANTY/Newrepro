import React, { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import {
    Search,
    ChevronDown,
    ChevronRight,
    Filter,
    ArrowUpDown,
    Calendar,
    Check,
    CheckSquare,
    Square,
    MoreVertical,
    Play,
    ArrowRight,
    Info,
    Sparkles,
    RefreshCw,
    Loader2,
    FolderKanban,
    LayoutGrid,
    List,
    Minus,
    CheckCircle2,
    AlertCircle,
    AlertTriangle,
    Lock,
    Tag,
    X,
    FileText,
    Layers,
    Clock,
    ListTodo,
    Plus,
} from 'lucide-react';
import { API_ENDPOINTS, API_BASE_URL } from '../config';
import { getDraftProject } from '../utils/draftProjects';
import { getCachedTaskToken, setCachedTaskToken as cacheTaskToken } from '../utils/tokenCache';

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

const DEFAULT_SPRINTS = [
    { id: 'sprint_1', name: 'Sprint 1', subtitle: 'Foundation & Interactive Prototype', total: 7, done: 0, due: '2026-10-02' },
    { id: 'sprint_2', name: 'Sprint 2', subtitle: 'Core Services & Authentication', total: 7, done: 0, due: '2026-10-06' },
    { id: 'sprint_3', name: 'Sprint 3', subtitle: 'Real-time System & Full Integration', total: 8, done: 0, due: '2026-10-10' },
    { id: 'sprint_4', name: 'Sprint 4', subtitle: 'Production Readiness & Optimization', total: 6, done: 0, due: '2026-10-16' },
];

export default function TaskCreation({
    projects = [],
    selectedProjectKey,
}) {
    const navigate = useNavigate();
    const location = useLocation();
    const queryClient = useQueryClient();
    const token = localStorage.getItem('token');

    // Project state
    const [projectDropdownOpen, setProjectDropdownOpen] = useState(false);
    const selectedProject = useMemo(
        () => projects.find((p) => p.key === selectedProjectKey) || null,
        [projects, selectedProjectKey]
    );

    // Data state
    const [tasks, setTasks] = useState([]);
    const [sprints, setSprints] = useState([]);
    const [milestones, setMilestones] = useState([]);
    const [isLoading, setIsLoading] = useState(false);
    const [isGenerating, setIsGenerating] = useState(false);
    const [error, setError] = useState('');
    const [success, setSuccess] = useState('');

    // Active views & filters
    const [viewMode, setViewMode] = useState('board'); // 'board' | 'list'
    const [activeSprintIndex, setActiveSprintIndex] = useState(0);
    const [searchQuery, setSearchQuery] = useState('');
    const [filterType, setFilterType] = useState('ALL'); // 'ALL' | 'FEATURE' | 'TASK' | 'BUG'
    const [filterPriority, setFilterPriority] = useState('ALL'); // 'ALL' | 'high' | 'medium' | 'low'
    const [filterDropdownOpen, setFilterDropdownOpen] = useState(false);
    const [sortAsc, setSortAsc] = useState(true);
    const [activeMenuTaskId, setActiveMenuTaskId] = useState(null);
    const [draggingTaskId, setDraggingTaskId] = useState(null);
    const [dragOverColumn, setDragOverColumn] = useState(null);

    // Generation status polling
    const [generationStatus, setGenerationStatus] = useState({
        is_generating: false,
        status: 'idle',
        current_sprint: 0,
        current_sprint_name: '',
        total_sprints: 4,
        progress_percent: 0,
        status_message: 'Initializing...',
        released_sprints: [],
        released_tasks: []
    });

    const [projectType, setProjectType] = useState(() => {
        if (selectedProjectKey) {
            return localStorage.getItem(`project_type_${selectedProjectKey}`) || 'greenfield';
        }
        return 'greenfield';
    });

    const buildHeaders = useCallback(() => {
        return { Authorization: `Bearer ${token}` };
    }, [token]);

    // Load data from backend
    const loadData = useCallback(async () => {
        if (!selectedProjectKey) return;
        setIsLoading(true);
        setError('');

        try {
            const res = await fetch(`${API_BASE_URL}/api/agent/tasks/local/?project_token=${encodeURIComponent(selectedProjectKey)}&page=1&page_size=200`, {
                headers: buildHeaders(),
            });

            if (res.ok) {
                const data = await res.json();
                const fetchedTasks = Array.isArray(data?.tasks) ? data.tasks : [];
                setTasks(fetchedTasks);

                // Derive sprints from tasks
                const sprintMap = new Map();
                const milestoneMap = new Map();

                fetchedTasks.forEach(t => {
                    const sName = t.sprint || 'Sprint 1';
                    if (!sprintMap.has(sName)) {
                        sprintMap.set(sName, { id: sName, name: sName, tasks: [] });
                    }
                    sprintMap.get(sName).tasks.push(t);

                    const mName = t.milestone || 'General';
                    if (!milestoneMap.has(mName)) {
                        milestoneMap.set(mName, { id: mName, name: mName });
                    }
                });

                if (sprintMap.size > 0) {
                    const derivedSprints = Array.from(sprintMap.values()).map((s, idx) => {
                        const total = s.tasks.length;
                        const done = s.tasks.filter(t => (t.status || 'TODO').toUpperCase() === 'DONE').length;
                        const defaultInfo = DEFAULT_SPRINTS[idx] || DEFAULT_SPRINTS[0];
                        return {
                            id: s.id,
                            name: s.name,
                            subtitle: s.tasks[0]?.description?.slice(0, 40) || defaultInfo.subtitle,
                            total,
                            done,
                            due: s.tasks[0]?.deadline || defaultInfo.due,
                        };
                    });
                    setSprints(derivedSprints);
                } else {
                    setSprints(DEFAULT_SPRINTS);
                }

                setMilestones(Array.from(milestoneMap.values()));
            }
        } catch (err) {
            console.error('Failed to load local tasks:', err);
            setError('Failed to load tasks. Please refresh.');
        } finally {
            setIsLoading(false);
        }
    }, [selectedProjectKey, buildHeaders]);

    useEffect(() => {
        loadData();
    }, [loadData]);

    // Active sprint
    const activeSprint = useMemo(() => {
        if (sprints.length > 0 && sprints[activeSprintIndex]) {
            return sprints[activeSprintIndex];
        }
        return DEFAULT_SPRINTS[0];
    }, [sprints, activeSprintIndex]);

    // Filter tasks for the active sprint & filters
    const displayedTasks = useMemo(() => {
        return tasks.filter(t => {
            // Sprint filter
            if (activeSprint) {
                const taskSprint = String(t.sprint || '').toLowerCase();
                const activeSprintName = String(activeSprint.name || '').toLowerCase();
                if (taskSprint && !taskSprint.includes(activeSprintName) && !activeSprintName.includes(taskSprint)) {
                    // Check if index matches
                    if (sprints.length > 0 && t.sprint !== sprints[activeSprintIndex]?.id && t.sprint !== sprints[activeSprintIndex]?.name) {
                        return false;
                    }
                }
            }

            // Type filter
            if (filterType !== 'ALL') {
                const type = String(t.task_type || t.type || '').toUpperCase();
                if (type !== filterType) return false;
            }

            // Priority filter
            if (filterPriority !== 'ALL') {
                const p = String(t.priority || 'medium').toLowerCase();
                if (p !== filterPriority.toLowerCase()) return false;
            }

            // Search query
            if (searchQuery.trim()) {
                const q = searchQuery.toLowerCase();
                const name = String(t.taskName || t.task_name || t.title || '').toLowerCase();
                const id = String(t.task_id || '').toLowerCase();
                const desc = String(t.description || '').toLowerCase();
                if (!name.includes(q) && !id.includes(q) && !desc.includes(q)) return false;
            }

            return true;
        }).sort((a, b) => {
            const dateA = a.deadline || a.planned_start || '';
            const dateB = b.deadline || b.planned_start || '';
            return sortAsc ? dateA.localeCompare(dateB) : dateB.localeCompare(dateA);
        });
    }, [tasks, activeSprint, activeSprintIndex, sprints, filterType, filterPriority, searchQuery, sortAsc]);

    // Group active sprint tasks into columns: To Do, In Progress, Blocked, Done
    const columnsData = useMemo(() => {
        const todo = [];
        const inProgress = [];
        const blocked = [];
        const done = [];

        displayedTasks.forEach(t => {
            const status = (t.status || 'TODO').toUpperCase();
            if (status === 'DONE' || status === 'COMPLETED') {
                done.push(t);
            } else if (status === 'BLOCKED' || status === 'FAILED') {
                blocked.push(t);
            } else if (status === 'IN_PROGRESS') {
                inProgress.push(t);
            } else {
                todo.push(t);
            }
        });

        return { todo, inProgress, blocked, done };
    }, [displayedTasks]);

    // Selection handlers
    const handleSelectAll = () => {
        setTasks(prev => prev.map(t => ({ ...t, selected: true })));
    };

    const handleDeselectAll = () => {
        setTasks(prev => prev.map(t => ({ ...t, selected: false })));
    };

    const handleToggleTaskSelect = (taskId) => {
        setTasks(prev => prev.map(t => (t.task_id === taskId || t.id === taskId) ? { ...t, selected: !t.selected } : t));
    };

    // Change task status (1-click move)
    const handleUpdateTaskStatus = async (taskId, newStatus) => {
        try {
            setTasks(prev => prev.map(t => (t.task_id === taskId || t.id === taskId) ? { ...t, status: newStatus } : t));
            setActiveMenuTaskId(null);

            await fetch(`${API_BASE_URL}/api/agent/tasks/${encodeURIComponent(taskId)}/status/`, {
                method: 'PATCH',
                headers: {
                    ...buildHeaders(),
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ status: newStatus }),
            });
        } catch (err) {
            console.error('Failed to update task status:', err);
        }
    };

    // Generate tasks via AI
    const handleMasterCreate = async () => {
        if (!selectedProjectKey) {
            setError('Please select a project first.');
            return;
        }

        setIsGenerating(true);
        setError('');
        setSuccess('');

        try {
            const pollInterval = setInterval(async () => {
                try {
                    const statusRes = await fetch(`${API_BASE_URL}/api/agent/tasks/generation-status/${selectedProjectKey}`, {
                        headers: buildHeaders(),
                    });
                    if (statusRes.ok) {
                        const statusData = await statusRes.json();
                        setGenerationStatus(statusData);
                        if (Array.isArray(statusData.released_tasks) && statusData.released_tasks.length > 0) {
                            setTasks(prev => {
                                const existingIds = new Set(prev.map(t => t.task_id));
                                const newTasks = statusData.released_tasks.filter(t => !existingIds.has(t.task_id));
                                return newTasks.length > 0 ? [...prev, ...newTasks] : prev;
                            });
                        }
                    }
                } catch {
                    // silent
                }
            }, 5000);

            const res = await fetch(API_ENDPOINTS.AGENT_TASKS_GENERATE_LOCAL, {
                method: 'POST',
                headers: {
                    ...buildHeaders(),
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    project_token: selectedProjectKey,
                    project_type: projectType,
                    process_mode: 'ai_first',
                    auto_create_plan: true,
                }),
            });

            clearInterval(pollInterval);

            if (!res.ok) {
                const errData = await res.json().catch(() => ({}));
                throw new Error(errData.detail || 'Failed to generate sprint plan');
            }

            setSuccess('AI Sprint Plan generated successfully!');
            await loadData();
        } catch (err) {
            setError(err.message || 'Generation failed. Please try again.');
        } finally {
            setIsGenerating(false);
        }
    };

    // Start execution on selected tasks
    const handleStartSelectedTasks = async () => {
        const selectedCount = tasks.filter(t => t.selected).length;
        if (selectedCount === 0) {
            // Auto select all in active sprint if none selected
            handleSelectAll();
        }
        navigate('/agents', {
            state: {
                projectToken: selectedProjectKey,
                startSprint: activeSprint.name,
            }
        });
    };

    // Calculate progress percent for active sprint
    const sprintStats = useMemo(() => {
        const total = displayedTasks.length;
        const done = columnsData.done.length;
        const percent = total > 0 ? Math.round((done / total) * 100) : 0;
        return { total, done, percent };
    }, [displayedTasks, columnsData]);

    return (
        <div className="w-full bg-[#F8FAFC] text-slate-800 font-sans p-3 sm:p-5 pb-20 flex flex-col select-none">
            {/* ── 1. COMPACT TOP HEADER BAR ── */}
            <div className="flex flex-col xl:flex-row xl:items-center justify-between gap-3 mb-3">
                <div>
                    <div className="flex items-center gap-2">
                        {/* Project dropdown */}
                        <div className="relative inline-block">
                            <button
                                onClick={() => setProjectDropdownOpen(!projectDropdownOpen)}
                                className="flex items-center gap-1.5 text-base sm:text-lg font-bold text-slate-900 hover:text-blue-600 transition-colors focus:outline-none"
                            >
                                <span>{selectedProject?.name || 'Project Roadmap'}</span>
                                <ChevronDown className="w-3.5 h-3.5 text-slate-500" />
                            </button>

                            {projectDropdownOpen && (
                                <div className="absolute top-full left-0 mt-1.5 w-60 bg-white border border-slate-200 rounded-xl shadow-xl z-50 py-1 animate-in fade-in zoom-in-95 duration-100">
                                    <div className="px-3 py-1 text-[10px] font-bold text-slate-400 uppercase tracking-wider">
                                        Switch Project
                                    </div>
                                    {projects.map((p) => (
                                        <button
                                            key={p.key}
                                            onClick={() => {
                                                setProjectDropdownOpen(false);
                                                navigate(`/task-creation?project=${encodeURIComponent(p.key)}`);
                                            }}
                                            className={`w-full text-left px-3 py-1.5 text-xs flex items-center justify-between hover:bg-slate-50 transition-colors ${
                                                p.key === selectedProjectKey ? 'font-bold text-blue-600 bg-blue-50/50' : 'text-slate-700'
                                            }`}
                                        >
                                            <span className="truncate">{p.name}</span>
                                            {p.key === selectedProjectKey && <Check className="w-3.5 h-3.5 text-blue-600" />}
                                        </button>
                                    ))}
                                </div>
                            )}
                        </div>

                        <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-blue-50 text-blue-700 border border-blue-200">
                            {sprints.length || 4} Sprints
                        </span>
                        <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-slate-100 text-slate-600 border border-slate-200">
                            {tasks.length} Work Items
                        </span>
                    </div>
                </div>

                {/* Right controls: Board, List, Filter, Due Date beside search bar towards left, plus search bar & Re-Generate */}
                <div className="flex flex-wrap items-center gap-2">
                    {/* View Switcher: Board vs List */}
                    <div className="flex items-center bg-slate-100 border border-slate-200 rounded-lg p-0.5 shadow-2xs">
                        <button
                            onClick={() => setViewMode('board')}
                            className={`flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-semibold transition-all ${
                                viewMode === 'board'
                                    ? 'bg-blue-600 text-white shadow-xs'
                                    : 'text-slate-600 hover:text-slate-900'
                            }`}
                        >
                            <LayoutGrid className="w-3.5 h-3.5" />
                            <span>Board</span>
                        </button>
                        <button
                            onClick={() => setViewMode('list')}
                            className={`flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-semibold transition-all ${
                                viewMode === 'list'
                                    ? 'bg-blue-600 text-white shadow-xs'
                                    : 'text-slate-600 hover:text-slate-900'
                            }`}
                        >
                            <List className="w-3.5 h-3.5" />
                            <span>List</span>
                        </button>
                    </div>

                    {/* Filter Dropdown */}
                    <div className="relative">
                        <button
                            onClick={() => setFilterDropdownOpen(!filterDropdownOpen)}
                            className="bg-white border border-slate-200 text-slate-700 text-xs font-medium px-2.5 py-1 rounded-lg shadow-2xs hover:bg-slate-50 flex items-center gap-1.5 transition-colors"
                        >
                            <Filter className="w-3.5 h-3.5 text-slate-500" />
                            <span>Filter</span>
                            {(filterType !== 'ALL' || filterPriority !== 'ALL') && (
                                <span className="w-1.5 h-1.5 rounded-full bg-blue-600" />
                            )}
                        </button>

                        {filterDropdownOpen && (
                            <div className="absolute right-0 top-full mt-1.5 w-48 bg-white border border-slate-200 rounded-xl shadow-xl z-50 p-2 text-xs">
                                <div className="font-bold text-[10px] text-slate-400 uppercase tracking-wider px-2 py-1">Task Type</div>
                                {['ALL', 'FEATURE', 'TASK', 'BUG'].map(t => (
                                    <button
                                        key={t}
                                        onClick={() => { setFilterType(t); setFilterDropdownOpen(false); }}
                                        className={`w-full text-left px-2 py-1 rounded flex items-center justify-between ${filterType === t ? 'bg-blue-50 text-blue-600 font-bold' : 'hover:bg-slate-50 text-slate-700'}`}
                                    >
                                        <span>{t}</span>
                                        {filterType === t && <Check className="w-3 h-3 text-blue-600" />}
                                    </button>
                                ))}

                                <div className="font-bold text-[10px] text-slate-400 uppercase tracking-wider px-2 py-1 mt-2 border-t border-slate-100">Priority</div>
                                {['ALL', 'high', 'medium', 'low'].map(p => (
                                    <button
                                        key={p}
                                        onClick={() => { setFilterPriority(p); setFilterDropdownOpen(false); }}
                                        className={`w-full text-left px-2 py-1 rounded capitalize flex items-center justify-between ${filterPriority === p ? 'bg-blue-50 text-blue-600 font-bold' : 'hover:bg-slate-50 text-slate-700'}`}
                                    >
                                        <span>{p}</span>
                                        {filterPriority === p && <Check className="w-3 h-3 text-blue-600" />}
                                    </button>
                                ))}
                            </div>
                        )}
                    </div>

                    {/* Due Date Sort */}
                    <button
                        onClick={() => setSortAsc(!sortAsc)}
                        className="bg-white border border-slate-200 text-slate-700 text-xs font-medium px-2.5 py-1 rounded-lg shadow-2xs hover:bg-slate-50 flex items-center gap-1.5 transition-colors"
                    >
                        <ArrowUpDown className="w-3.5 h-3.5 text-slate-500" />
                        <span>Due Date</span>
                    </button>

                    {/* Search bar */}
                    <div className="relative">
                        <Search className="w-3.5 h-3.5 absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-400" />
                        <input
                            type="text"
                            placeholder="Search tasks, features, or sprints..."
                            value={searchQuery}
                            onChange={(e) => setSearchQuery(e.target.value)}
                            className="bg-white border border-slate-200 rounded-lg pl-8 pr-7 py-1 text-xs text-slate-700 placeholder-slate-400 focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 w-52 sm:w-60 shadow-2xs transition-all"
                        />
                        {searchQuery && (
                            <button
                                onClick={() => setSearchQuery('')}
                                className="absolute right-2 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600"
                            >
                                <X className="w-3 h-3" />
                            </button>
                        )}
                    </div>

                    {/* AI Plan Generation Action */}
                    <button
                        onClick={handleMasterCreate}
                        disabled={isGenerating}
                        className="bg-blue-600 hover:bg-blue-700 text-white font-semibold text-xs px-3 py-1 rounded-lg shadow-sm flex items-center gap-1.5 transition-colors"
                    >
                        {isGenerating ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Sparkles className="w-3.5 h-3.5" />}
                        <span>{tasks.length === 0 ? 'Generate Plan' : 'Re-Generate'}</span>
                    </button>
                </div>
            </div>

            {/* ── 2. COMPACT HORIZONTAL SPRINT CARDS ── */}
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-2 mb-2.5">
                {(sprints.length > 0 ? sprints : DEFAULT_SPRINTS).slice(0, 4).map((sprint, idx) => {
                    const isActive = activeSprintIndex === idx;
                    const sprintTasks = tasks.filter(t => {
                        const ts = String(t.sprint || '').toLowerCase();
                        const sn = String(sprint.name || '').toLowerCase();
                        return ts.includes(sn) || sn.includes(ts) || t.sprint === sprint.id;
                    });
                    const total = sprintTasks.length || sprint.total || 7;
                    const done = sprintTasks.filter(t => (t.status || '').toUpperCase() === 'DONE').length;

                    const defaultInfo = DEFAULT_SPRINTS[idx] || DEFAULT_SPRINTS[0];
                    let label = sprint.name || `Sprint ${idx + 1}`;
                    if (!label.includes(':')) {
                        const sub = sprint.subtitle || defaultInfo.subtitle;
                        if (sub && !label.toLowerCase().includes(sub.toLowerCase())) {
                            label = `${label}: ${sub}`;
                        }
                    }

                    return (
                        <div
                            key={sprint.id || idx}
                            onClick={() => setActiveSprintIndex(idx)}
                            className={`rounded-lg py-2 px-3 transition-all cursor-pointer flex items-center justify-between gap-2 ${
                                isActive
                                    ? 'bg-blue-600 text-white shadow-sm border border-blue-600'
                                    : 'bg-white border border-slate-200 text-slate-800 shadow-2xs hover:border-slate-300 hover:shadow-xs'
                            }`}
                        >
                            <span className={`text-xs font-bold truncate leading-tight ${isActive ? 'text-white' : 'text-slate-800'}`} title={label}>
                                {label}
                            </span>
                            <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded-full shrink-0 ${
                                isActive ? 'bg-blue-500/70 text-white' : 'text-slate-500 font-mono bg-slate-100'
                            }`}>
                                {done}/{total}
                            </span>
                        </div>
                    );
                })}
            </div>

            {/* ── 3. SELECTION & ACTION TOOLBAR ── */}
            <div className="flex flex-wrap items-center justify-between gap-2.5 mb-2.5">
                <div className="flex items-center space-x-3">
                    <label className="flex items-center space-x-1.5 text-xs font-semibold text-slate-700 cursor-pointer select-none">
                        <input
                            type="checkbox"
                            checked={displayedTasks.length > 0 && displayedTasks.every(t => t.selected)}
                            onChange={(e) => e.target.checked ? handleSelectAll() : handleDeselectAll()}
                            className="rounded border-slate-300 text-blue-600 focus:ring-blue-500 w-3.5 h-3.5 cursor-pointer"
                        />
                        <span>Select All</span>
                    </label>
                    <button
                        onClick={handleDeselectAll}
                        className="text-xs font-semibold text-blue-600 hover:underline cursor-pointer"
                    >
                        Deselect All
                    </button>
                    {tasks.filter(t => t.selected).length > 0 && (
                        <span className="text-[10px] font-bold text-blue-700 bg-blue-50 px-2 py-0.5 rounded-full border border-blue-200">
                            {tasks.filter(t => t.selected).length} selected
                        </span>
                    )}
                </div>
            </div>

            {/* Error or Success banners */}
            {error && (
                <div className="mb-4 p-3 bg-rose-50 border border-rose-200 rounded-lg text-rose-700 text-xs flex items-center justify-between">
                    <div className="flex items-center gap-2">
                        <AlertCircle className="w-4 h-4 text-rose-500" />
                        <span>{error}</span>
                    </div>
                    <button onClick={() => setError('')}><X className="w-4 h-4" /></button>
                </div>
            )}
            {success && (
                <div className="mb-4 p-3 bg-emerald-50 border border-emerald-200 rounded-lg text-emerald-700 text-xs flex items-center justify-between">
                    <div className="flex items-center gap-2">
                        <CheckCircle2 className="w-4 h-4 text-emerald-500" />
                        <span>{success}</span>
                    </div>
                    <button onClick={() => setSuccess('')}><X className="w-4 h-4" /></button>
                </div>
            )}

            {/* ── 4. MAIN BOARD AREA OR LIST VIEW ── */}
            {isLoading ? (
                <div className="flex-1 flex flex-col items-center justify-center py-24 text-slate-400">
                    <Loader2 className="w-8 h-8 animate-spin text-blue-600 mb-3" />
                    <span className="text-sm font-medium text-slate-600">Loading sprint tasks...</span>
                </div>
            ) : tasks.length === 0 ? (
                <div className="flex-1 bg-white border border-slate-200 rounded-2xl p-12 text-center flex flex-col items-center justify-center shadow-xs">
                    <FolderKanban className="w-12 h-12 text-slate-300 mb-4" />
                    <h3 className="text-base font-bold text-slate-800 mb-1">No Tasks Generated Yet</h3>
                    <p className="text-xs text-slate-500 max-w-md mb-6 leading-relaxed">
                        Ready to plan your application? Use our high-speed AI Sprint Planner to generate full architecture, API services, frontend UI, and QA test tasks.
                    </p>
                    <button
                        onClick={handleMasterCreate}
                        disabled={isGenerating}
                        className="bg-blue-600 hover:bg-blue-700 text-white font-semibold text-xs px-5 py-2.5 rounded-xl shadow-md shadow-blue-500/20 flex items-center gap-2 transition-all"
                    >
                        {isGenerating ? <Loader2 className="w-4 h-4 animate-spin" /> : <Sparkles className="w-4 h-4" />}
                        <span>Generate Sprint Roadmap with AI</span>
                    </button>
                </div>
            ) : viewMode === 'list' ? (
                /* ── TABLE / LIST VIEW (FULL LENGTH, WHOLE PAGE SCROLLABLE) ── */
                <div className="w-full bg-white rounded-xl border border-slate-200 shadow-xs overflow-hidden">
                    <div className="overflow-x-auto">
                        <table className="w-full text-left text-xs">
                            <thead className="bg-slate-50 border-b border-slate-200 text-slate-500 font-bold uppercase tracking-wider text-[10px] sticky top-0 z-10 shadow-2xs">
                                <tr>
                                    <th className="py-2.5 px-3 w-10 text-center">
                                        <input
                                            type="checkbox"
                                            checked={displayedTasks.length > 0 && displayedTasks.every(t => t.selected)}
                                            onChange={(e) => e.target.checked ? handleSelectAll() : handleDeselectAll()}
                                            className="rounded border-slate-300 text-blue-600 focus:ring-blue-500 w-3.5 h-3.5 cursor-pointer"
                                        />
                                    </th>
                                    <th className="py-2.5 px-3 w-28">Task ID</th>
                                    <th className="py-2.5 px-3">Title</th>
                                    <th className="py-2.5 px-3 w-24">Type</th>
                                    <th className="py-2.5 px-3 w-24">Priority</th>
                                    <th className="py-2.5 px-3 w-36">Sprint</th>
                                    <th className="py-2.5 px-3 w-28">Due Date</th>
                                    <th className="py-2.5 px-3 w-28">Status</th>
                                </tr>
                            </thead>
                            <tbody className="divide-y divide-slate-100 text-slate-700">
                                {displayedTasks.map(t => (
                                    <tr
                                        key={t.id || t.task_id}
                                        className={`hover:bg-blue-50/40 transition-colors ${t.selected ? 'bg-blue-50/20' : ''}`}
                                    >
                                        <td className="py-2.5 px-3 text-center">
                                            <input
                                                type="checkbox"
                                                checked={Boolean(t.selected)}
                                                onChange={() => handleToggleTaskSelect(t.task_id)}
                                                className="rounded border-slate-300 text-blue-600 focus:ring-blue-500 w-3.5 h-3.5 cursor-pointer"
                                            />
                                        </td>
                                        <td className="py-2.5 px-3 font-mono font-bold text-slate-900 text-xs">{t.task_id}</td>
                                        <td className="py-2.5 px-3 font-medium text-slate-800">{t.taskName || t.task_name || t.title}</td>
                                        <td className="py-2.5 px-3">
                                            <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                                                (t.task_type || '').toUpperCase() === 'FEATURE'
                                                    ? 'bg-purple-100 text-purple-700'
                                                    : 'bg-blue-100 text-blue-700'
                                            }`}>
                                                {t.task_type || 'TASK'}
                                            </span>
                                        </td>
                                        <td className="py-2.5 px-3">
                                            <span className={`capitalize font-semibold text-[11px] ${
                                                String(t.priority).toLowerCase() === 'high' ? 'text-red-600' :
                                                String(t.priority).toLowerCase() === 'medium' ? 'text-amber-600' : 'text-emerald-600'
                                            }`}>
                                                • {t.priority || 'medium'}
                                            </span>
                                        </td>
                                        <td className="py-2.5 px-3 text-slate-500 text-[11px]">{t.sprint || 'Sprint 1'}</td>
                                        <td className="py-2.5 px-3 text-slate-500 text-[11px]">{t.deadline || '2026-10-02'}</td>
                                        <td className="py-2.5 px-3">
                                            <span className={`font-semibold uppercase text-[10px] px-2 py-0.5 rounded ${
                                                (t.status || '').toUpperCase() === 'DONE' ? 'bg-emerald-100 text-emerald-700' :
                                                (t.status || '').toUpperCase() === 'IN_PROGRESS' ? 'bg-blue-100 text-blue-700' :
                                                (t.status || '').toUpperCase() === 'BLOCKED' ? 'bg-rose-100 text-rose-700' :
                                                'bg-slate-100 text-slate-700'
                                            }`}>
                                                {t.status || 'TODO'}
                                            </span>
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>

                    {/* Bottom summary bar of the table */}
                    <div className="px-4 py-2.5 bg-slate-50/90 border-t border-slate-200 text-xs text-slate-500 flex items-center justify-between">
                        <span className="font-medium text-[11px]">
                            Showing {displayedTasks.length} {displayedTasks.length === 1 ? 'task' : 'tasks'} in {activeSprint.name}
                        </span>
                        <div className="flex items-center gap-3">
                            <span className="text-slate-400 font-medium text-[11px]">
                                {displayedTasks.filter(t => t.selected).length} selected
                            </span>
                            <button
                                onClick={handleStartSelectedTasks}
                                className="bg-blue-600 hover:bg-blue-700 text-white font-semibold text-xs py-1 px-3 rounded-md transition-colors flex items-center gap-1.5 shadow-2xs"
                            >
                                <Play className="w-3 h-3 fill-current" />
                                <span>Start Selected</span>
                            </button>
                        </div>
                    </div>
                </div>
            ) : (
                /* ── KANBAN BOARD VIEW (FULL LENGTH & FULL WIDTH, WHOLE PAGE SCROLLABLE) ── */
                <div className="w-full flex flex-col lg:flex-row gap-4 items-stretch">
                    {/* The 4 Columns */}
                    <div className="flex-1 w-full grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-3 items-stretch">
                        {/* ── COLUMN 1: TO DO ── */}
                        <div
                            onDragOver={(e) => {
                                e.preventDefault();
                                e.dataTransfer.dropEffect = 'move';
                                if (dragOverColumn !== 'TODO') setDragOverColumn('TODO');
                            }}
                            onDragLeave={(e) => {
                                if (e.currentTarget.contains(e.relatedTarget)) return;
                                setDragOverColumn(null);
                            }}
                            onDrop={(e) => {
                                e.preventDefault();
                                setDragOverColumn(null);
                                const taskId = e.dataTransfer.getData('text/plain') || draggingTaskId;
                                if (taskId) handleUpdateTaskStatus(taskId, 'TODO');
                                setDraggingTaskId(null);
                            }}
                            className={`rounded-xl border p-2.5 flex flex-col h-full min-h-[520px] shadow-2xs transition-all duration-150 ${
                                dragOverColumn === 'TODO'
                                    ? 'bg-blue-50/80 border-blue-400 ring-2 ring-blue-400/50 shadow-md'
                                    : 'bg-[#F1F5F9]/70 border-slate-200/90'
                            }`}
                        >
                            <div className="flex items-center justify-between px-2 py-1 mb-1.5 shrink-0">
                                <span className="font-bold text-xs text-slate-800">To Do</span>
                                <span className="text-[11px] text-slate-500 font-medium bg-slate-200/60 px-1.5 py-0.5 rounded">{columnsData.todo.length} items</span>
                            </div>

                            {columnsData.todo.length === 0 ? (
                                <div className="flex-1 flex flex-col items-center justify-center text-center p-4 py-12">
                                    <div className="w-10 h-10 rounded-full border border-slate-200/90 flex items-center justify-center text-slate-400 mb-2.5 bg-white shadow-2xs">
                                        <ListTodo className="w-4 h-4 text-slate-400" />
                                    </div>
                                    <h5 className="font-bold text-xs text-slate-700">No tasks to do</h5>
                                    <p className="text-[10px] text-slate-400 mt-1 max-w-[170px] leading-tight">All tasks in this sprint have been moved or completed.</p>
                                </div>
                            ) : (
                                <>
                                    {/* Milestone Group Subheader */}
                                    <div className="flex items-center justify-between px-1 py-1 mb-2 text-xs font-semibold text-slate-700 shrink-0">
                                        <label className="flex items-center space-x-1.5 cursor-pointer truncate">
                                            <input
                                                type="checkbox"
                                                checked={columnsData.todo.length > 0 && columnsData.todo.every(t => t.selected)}
                                                onChange={(e) => {
                                                    const sel = e.target.checked;
                                                    setTasks(prev => prev.map(t => columnsData.todo.some(ct => ct.task_id === t.task_id) ? { ...t, selected: sel } : t));
                                                }}
                                                className="rounded border-slate-300 text-blue-600 focus:ring-blue-500 w-3.5 h-3.5"
                                            />
                                            <span className="truncate text-[11px]">{columnsData.todo[0]?.milestone || 'Project Foundation'}</span>
                                        </label>
                                        <span className="text-[11px] text-slate-400 font-mono shrink-0 ml-1">
                                            0/{columnsData.todo.length}
                                        </span>
                                    </div>

                                    {/* Task Cards - natural full length */}
                                    <div className="space-y-2">
                                        {columnsData.todo.map((task) => (
                                            <TaskCardItem
                                                key={task.id || task.task_id}
                                                task={task}
                                                onToggleSelect={() => handleToggleTaskSelect(task.task_id)}
                                                isDragging={draggingTaskId === (task.task_id || task.id)}
                                                onDragStart={(id) => setDraggingTaskId(id)}
                                                onDragEnd={() => {
                                                    setDraggingTaskId(null);
                                                    setDragOverColumn(null);
                                                }}
                                            />
                                        ))}
                                    </div>
                                </>
                            )}
                        </div>

                        {/* ── COLUMN 2: IN PROGRESS ── */}
                        <div
                            onDragOver={(e) => {
                                e.preventDefault();
                                e.dataTransfer.dropEffect = 'move';
                                if (dragOverColumn !== 'IN_PROGRESS') setDragOverColumn('IN_PROGRESS');
                            }}
                            onDragLeave={(e) => {
                                if (e.currentTarget.contains(e.relatedTarget)) return;
                                setDragOverColumn(null);
                            }}
                            onDrop={(e) => {
                                e.preventDefault();
                                setDragOverColumn(null);
                                const taskId = e.dataTransfer.getData('text/plain') || draggingTaskId;
                                if (taskId) handleUpdateTaskStatus(taskId, 'IN_PROGRESS');
                                setDraggingTaskId(null);
                            }}
                            className={`rounded-xl border p-2.5 flex flex-col h-full min-h-[520px] shadow-2xs transition-all duration-150 ${
                                dragOverColumn === 'IN_PROGRESS'
                                    ? 'bg-blue-100/70 border-blue-400 ring-2 ring-blue-500/50 shadow-md'
                                    : 'bg-[#EFF6FF]/50 border-blue-100'
                            }`}
                        >
                            <div className="flex items-center justify-between px-2 py-1 mb-1.5 shrink-0">
                                <span className="font-bold text-xs text-blue-700">In Progress</span>
                                <span className="text-[11px] text-blue-600 font-medium bg-blue-100/70 px-1.5 py-0.5 rounded">{columnsData.inProgress.length} items</span>
                            </div>

                            {columnsData.inProgress.length === 0 ? (
                                <div className="flex-1 flex flex-col items-center justify-center text-center p-4 py-12">
                                    <div className="w-10 h-10 rounded-full border border-blue-200/80 flex items-center justify-center text-blue-500 mb-2.5 bg-white shadow-2xs">
                                        <Clock className="w-4 h-4 text-blue-500" />
                                    </div>
                                    <h5 className="font-bold text-xs text-slate-700">No tasks in progress</h5>
                                    <p className="text-[10px] text-slate-400 mt-1 max-w-[170px] leading-tight">Tasks currently being worked on will appear here.</p>
                                </div>
                            ) : (
                                <>
                                    {/* Milestone Group Subheader */}
                                    <div className="flex items-center justify-between px-1 py-1 mb-2 text-xs font-semibold text-slate-700 shrink-0">
                                        <label className="flex items-center space-x-1.5 cursor-pointer truncate">
                                            <input
                                                type="checkbox"
                                                checked={columnsData.inProgress.length > 0 && columnsData.inProgress.every(t => t.selected)}
                                                onChange={(e) => {
                                                    const sel = e.target.checked;
                                                    setTasks(prev => prev.map(t => columnsData.inProgress.some(ct => ct.task_id === t.task_id) ? { ...t, selected: sel } : t));
                                                }}
                                                className="rounded border-slate-300 text-blue-600 focus:ring-blue-500 w-3.5 h-3.5"
                                            />
                                            <ChevronDown className="w-3 h-3 text-slate-500 shrink-0" />
                                            <span className="truncate text-[11px]">{columnsData.inProgress[0]?.milestone || 'Core Implementation'}</span>
                                        </label>
                                        <span className="text-[11px] text-slate-400 font-mono shrink-0 ml-1">
                                            0/{columnsData.inProgress.length}
                                        </span>
                                    </div>

                                    {/* Task Cards - natural full length */}
                                    <div className="space-y-2">
                                        {columnsData.inProgress.map((task) => (
                                            <TaskCardItem
                                                key={task.id || task.task_id}
                                                task={task}
                                                onToggleSelect={() => handleToggleTaskSelect(task.task_id)}
                                                isDragging={draggingTaskId === (task.task_id || task.id)}
                                                onDragStart={(id) => setDraggingTaskId(id)}
                                                onDragEnd={() => {
                                                    setDraggingTaskId(null);
                                                    setDragOverColumn(null);
                                                }}
                                            />
                                        ))}
                                    </div>
                                </>
                            )}
                        </div>

                        {/* ── COLUMN 3: BLOCKED ── */}
                        <div
                            onDragOver={(e) => {
                                e.preventDefault();
                                e.dataTransfer.dropEffect = 'move';
                                if (dragOverColumn !== 'BLOCKED') setDragOverColumn('BLOCKED');
                            }}
                            onDragLeave={(e) => {
                                if (e.currentTarget.contains(e.relatedTarget)) return;
                                setDragOverColumn(null);
                            }}
                            onDrop={(e) => {
                                e.preventDefault();
                                setDragOverColumn(null);
                                const taskId = e.dataTransfer.getData('text/plain') || draggingTaskId;
                                if (taskId) handleUpdateTaskStatus(taskId, 'BLOCKED');
                                setDraggingTaskId(null);
                            }}
                            className={`rounded-xl border p-2.5 flex flex-col h-full min-h-[520px] shadow-2xs transition-all duration-150 ${
                                dragOverColumn === 'BLOCKED'
                                    ? 'bg-rose-100/60 border-rose-300 ring-2 ring-rose-400/50 shadow-md'
                                    : 'bg-[#FFF1F2]/40 border-rose-100'
                            }`}
                        >
                            <div className="flex items-center justify-between px-2 py-1 mb-1.5 shrink-0">
                                <span className="font-bold text-xs text-rose-600">Blocked</span>
                                <span className="text-[11px] text-rose-500 font-medium bg-rose-100/70 px-1.5 py-0.5 rounded">{columnsData.blocked.length} items</span>
                            </div>

                            {columnsData.blocked.length === 0 ? (
                                <div className="flex-1 flex flex-col items-center justify-center text-center p-4 py-12">
                                    <div className="w-10 h-10 rounded-full border border-slate-200/90 flex items-center justify-center text-slate-400 mb-2.5 bg-white shadow-2xs">
                                        <Minus className="w-4 h-4 text-slate-400" />
                                    </div>
                                    <h5 className="font-bold text-xs text-slate-700">No blocked tasks</h5>
                                    <p className="text-[10px] text-slate-400 mt-1 max-w-[170px] leading-tight">Tasks that are blocked will appear here.</p>
                                </div>
                            ) : (
                                <div className="space-y-2">
                                    {columnsData.blocked.map((task) => (
                                        <TaskCardItem
                                            key={task.id || task.task_id}
                                            task={task}
                                            onToggleSelect={() => handleToggleTaskSelect(task.task_id)}
                                            isDragging={draggingTaskId === (task.task_id || task.id)}
                                            onDragStart={(id) => setDraggingTaskId(id)}
                                            onDragEnd={() => {
                                                setDraggingTaskId(null);
                                                setDragOverColumn(null);
                                            }}
                                        />
                                    ))}
                                </div>
                            )}
                        </div>

                        {/* ── COLUMN 4: DONE ── */}
                        <div
                            onDragOver={(e) => {
                                e.preventDefault();
                                e.dataTransfer.dropEffect = 'move';
                                if (dragOverColumn !== 'DONE') setDragOverColumn('DONE');
                            }}
                            onDragLeave={(e) => {
                                if (e.currentTarget.contains(e.relatedTarget)) return;
                                setDragOverColumn(null);
                            }}
                            onDrop={(e) => {
                                e.preventDefault();
                                setDragOverColumn(null);
                                const taskId = e.dataTransfer.getData('text/plain') || draggingTaskId;
                                if (taskId) handleUpdateTaskStatus(taskId, 'DONE');
                                setDraggingTaskId(null);
                            }}
                            className={`rounded-xl border p-2.5 flex flex-col h-full min-h-[520px] shadow-2xs transition-all duration-150 ${
                                dragOverColumn === 'DONE'
                                    ? 'bg-emerald-100/60 border-emerald-300 ring-2 ring-emerald-400/50 shadow-md'
                                    : 'bg-[#F0FDF4]/50 border-emerald-100'
                            }`}
                        >
                            <div className="flex items-center justify-between px-2 py-1 mb-1.5 shrink-0">
                                <span className="font-bold text-xs text-emerald-600">Done</span>
                                <span className="text-[11px] text-emerald-600 font-medium bg-emerald-100/70 px-1.5 py-0.5 rounded">{columnsData.done.length} items</span>
                            </div>

                            {columnsData.done.length === 0 ? (
                                <div className="flex-1 flex flex-col items-center justify-center text-center p-4 py-12">
                                    <div className="w-10 h-10 rounded-full border border-emerald-200/90 text-emerald-500 flex items-center justify-center mb-2.5 bg-white shadow-2xs">
                                        <Check className="w-4 h-4 text-emerald-600 stroke-[2.5]" />
                                    </div>
                                    <h5 className="font-bold text-xs text-slate-700">No completed tasks</h5>
                                    <p className="text-[10px] text-slate-400 mt-1 max-w-[170px] leading-tight">Completed tasks will appear here.</p>
                                </div>
                            ) : (
                                <div className="space-y-2">
                                    {columnsData.done.map((task) => (
                                        <TaskCardItem
                                            key={task.id || task.task_id}
                                            task={task}
                                            onToggleSelect={() => handleToggleTaskSelect(task.task_id)}
                                            isDragging={draggingTaskId === (task.task_id || task.id)}
                                            onDragStart={(id) => setDraggingTaskId(id)}
                                            onDragEnd={() => {
                                                setDraggingTaskId(null);
                                                setDragOverColumn(null);
                                            }}
                                        />
                                    ))}
                                </div>
                            )}
                        </div>
                    </div>

                    {/* ── RIGHT SIDEBAR: SPRINT PROGRESS (STICKY ON DESKTOP, NATURAL FULL HEIGHT) ── */}
                    <div className="w-full lg:w-72 bg-white rounded-xl border border-slate-200 p-3.5 shadow-2xs flex flex-col shrink-0 space-y-3.5 lg:sticky lg:top-4">
                        <h4 className="font-bold text-xs text-slate-800 tracking-tight">Sprint Progress</h4>

                        {/* Donut progress ring */}
                        <div className="flex items-center justify-between">
                            <div className="flex items-center gap-2.5">
                                <div className="relative w-9 h-9 flex items-center justify-center">
                                    <svg className="w-full h-full transform -rotate-90" viewBox="0 0 36 36">
                                        <path
                                            className="text-slate-100"
                                            strokeWidth="3.5"
                                            stroke="currentColor"
                                            fill="none"
                                            d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
                                        />
                                        <path
                                            className="text-emerald-500 transition-all duration-500 ease-out"
                                            strokeDasharray={`${sprintStats.percent}, 100`}
                                            strokeWidth="3.5"
                                            strokeLinecap="round"
                                            stroke="currentColor"
                                            fill="none"
                                            d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
                                        />
                                    </svg>
                                </div>
                                <div>
                                    <div className="font-bold text-xs text-slate-800 truncate max-w-[120px]">{activeSprint.name || 'Sprint 1'}</div>
                                    <div className="text-[11px] text-slate-400 font-medium">{sprintStats.done} / {sprintStats.total}</div>
                                </div>
                            </div>
                            <span className="font-bold text-xs text-slate-900">{sprintStats.percent}%</span>
                        </div>

                        <p className="text-[11px] text-slate-600 font-medium line-clamp-2">
                            {activeSprint.subtitle || 'Visual Prototype & Core Infrastructure'}
                        </p>

                        <div className="text-[11px] text-slate-400 flex items-center gap-1.5 pb-2 border-b border-slate-100">
                            <Calendar className="w-3 h-3 text-slate-400" />
                            <span>Due: {activeSprint.due || '2026-10-02'}</span>
                        </div>

                        {/* Milestone Section */}
                        <div className="pb-2 border-b border-slate-100">
                            <div className="text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-1">Milestone</div>
                            <div className="text-xs font-semibold text-slate-700 hover:text-blue-600 cursor-pointer flex items-center justify-between">
                                <span className="truncate">{columnsData.todo[0]?.milestone || columnsData.inProgress[0]?.milestone || 'Foundation Setup'}</span>
                                <ChevronRight className="w-3.5 h-3.5 text-slate-400 shrink-0" />
                            </div>
                            <div className="text-[10px] text-slate-400 font-mono mt-0.5">
                                {sprintStats.done} / {sprintStats.total}
                            </div>
                        </div>

                        {/* Task Types */}
                        <div className="pb-2 border-b border-slate-100 space-y-1">
                            <div className="text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-0.5">Task Types</div>
                            <div className="flex items-center gap-2 text-xs text-slate-600">
                                <span className="p-0.5 rounded bg-purple-100 text-purple-600">
                                    <FileText className="w-3 h-3" />
                                </span>
                                <span className="text-[11px]">Feature</span>
                            </div>
                            <div className="flex items-center gap-2 text-xs text-slate-600">
                                <span className="p-0.5 rounded bg-blue-100 text-blue-600">
                                    <CheckSquare className="w-3 h-3" />
                                </span>
                                <span className="text-[11px]">Task</span>
                            </div>
                        </div>

                        {/* Priority */}
                        <div className="pb-2 border-b border-slate-100">
                            <div className="text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-1">Priority</div>
                            <div className="flex items-center gap-3 text-[11px] text-slate-600">
                                <div className="flex items-center gap-1">
                                    <span className="w-1.5 h-1.5 rounded-full bg-red-500" />
                                    <span>High</span>
                                </div>
                                <div className="flex items-center gap-1">
                                    <span className="w-1.5 h-1.5 rounded-full bg-amber-400" />
                                    <span>Medium</span>
                                </div>
                                <div className="flex items-center gap-1">
                                    <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
                                    <span>Low</span>
                                </div>
                            </div>
                        </div>

                        {/* Action Buttons */}
                        <div className="space-y-1.5 pt-1">
                            <button
                                onClick={handleStartSelectedTasks}
                                className="w-full bg-blue-600 hover:bg-blue-700 text-white font-semibold text-xs py-2 px-3 rounded-lg flex items-center justify-center gap-1.5 shadow-sm transition-all"
                            >
                                <Play className="w-3 h-3 fill-current" />
                                <span>Start Selected Tasks</span>
                            </button>

                            <button
                                onClick={() => navigate('/agents', { state: { projectToken: selectedProjectKey } })}
                                className="w-full bg-white border border-slate-200 hover:bg-slate-50 text-slate-700 font-semibold text-xs py-1.5 px-3 rounded-lg flex items-center justify-center gap-1.5 transition-all shadow-2xs"
                            >
                                <ArrowRight className="w-3 h-3 text-slate-500" />
                                <span>Move to Next Phase</span>
                            </button>
                        </div>

                        {/* Info Callout */}
                        <div className="bg-blue-50/70 border border-blue-100 rounded-lg p-2 text-[10px] text-blue-900 flex items-start gap-1.5 leading-relaxed">
                            <Info className="w-3.5 h-3.5 text-blue-600 shrink-0 mt-0.5" />
                            <span>Tasks started here will be picked up by AI agents and tracked automatically.</span>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}

// ── REUSABLE TASK CARD COMPONENT (NATIVE DRAG & DROP, CLEAN CARD) ──
function TaskCardItem({ task, onToggleSelect, isDragging, onDragStart, onDragEnd }) {
    const type = (task.task_type || task.type || 'FEATURE').toUpperCase();
    const isFeature = type === 'FEATURE';
    const prio = String(task.priority || 'medium').toLowerCase();
    const isHigh = prio === 'high' || prio === 'urgent' || prio === 'critical';
    const isMedium = prio === 'medium';
    const dueDate = task.deadline || task.planned_start || '2026-10-02';

    return (
        <div
            draggable={true}
            onDragStart={(e) => {
                e.dataTransfer.setData('text/plain', task.task_id || task.id);
                e.dataTransfer.effectAllowed = 'move';
                onDragStart?.(task.task_id || task.id);
            }}
            onDragEnd={() => {
                onDragEnd?.();
            }}
            className={`bg-white border rounded-lg p-2.5 shadow-2xs hover:shadow-xs transition-all relative cursor-grab active:cursor-grabbing select-none ${
                isDragging
                    ? 'opacity-40 scale-[0.98] border-dashed border-blue-400 shadow-none'
                    : 'border-slate-200/90 hover:border-slate-300'
            }`}
        >
            <div className="flex items-start gap-2">
                {/* Square selection checkbox */}
                <input
                    type="checkbox"
                    checked={Boolean(task.selected)}
                    onChange={(e) => {
                        e.stopPropagation();
                        onToggleSelect();
                    }}
                    onClick={(e) => e.stopPropagation()}
                    className="rounded border-slate-300 text-blue-600 focus:ring-blue-500 w-3.5 h-3.5 mt-0.5 cursor-pointer shrink-0"
                />

                {/* Card content */}
                <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-1.5 min-w-0">
                        <span className="text-slate-400 shrink-0">
                            {isFeature ? <FileText className="w-3.5 h-3.5 text-purple-500 shrink-0" /> : <CheckSquare className="w-3.5 h-3.5 text-blue-500 shrink-0" />}
                        </span>
                        <h5 className="font-bold text-xs text-slate-800 leading-snug truncate" title={task.taskName || task.task_name || task.title}>
                            {task.taskName || task.task_name || task.title || 'Task'}
                        </h5>
                    </div>

                    {/* Type badge */}
                    <div className="mt-1.5">
                        <span className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[9px] font-bold ${
                            isFeature
                                ? 'bg-purple-100/80 text-purple-700'
                                : 'bg-blue-100/80 text-blue-700'
                        }`}>
                            <span className="w-1.5 h-1.5 rounded-full bg-current opacity-70" />
                            {type}
                        </span>
                    </div>

                    {/* Metadata: Priority dot + Due date */}
                    <div className="flex items-center justify-between gap-2 mt-2 pt-1.5 border-t border-slate-100 text-[10px] text-slate-500">
                        <div className="flex items-center gap-1 font-semibold">
                            <span className={`w-1.5 h-1.5 rounded-full ${isHigh ? 'bg-red-500' : isMedium ? 'bg-amber-400' : 'bg-emerald-500'}`} />
                            <span className={isHigh ? 'text-red-600' : isMedium ? 'text-amber-600' : 'text-emerald-600'}>
                                {isHigh ? 'High' : isMedium ? 'Medium' : 'Low'}
                            </span>
                        </div>

                        <div className="flex items-center gap-1 text-slate-400 font-mono text-[10px]">
                            <Calendar className="w-3 h-3 text-slate-400" />
                            <span>Due: {dueDate}</span>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
}
