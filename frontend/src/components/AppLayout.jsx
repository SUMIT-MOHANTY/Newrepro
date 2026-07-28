import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { API_ENDPOINTS, API_BASE_URL } from '../config';
import { clearAuthData } from '../utils/auth';
import { customError } from '../utils/modalHelpers';
import { useModal } from '../contexts/ModalContext';
import { Menu, Settings, Moon, Sun, Lock, Mail, ShieldAlert, CheckCircle, BookOpen } from 'lucide-react';
import Sidebar from './Sidebar';
import RoadmapHeader from './RoadmapHeader';
import AgentsPage from './AgentsPage';
import AIConfig from '../components/AIConfig';
import AssistantBot from '../components/AssistantBot';
import { useProgressTracking } from '../hooks/useProgressTracking';

import { useProjects, useRoadmapData, useInvalidateProjects } from '../hooks/useProjects';
import { fetchRoadmapStep, deleteProjectByIdentifier } from '../api/projects';
import ProjectDropdown from './ProjectDropdown';
import RoleDropdown from './RoleDropdown';
import { getDraftProject, removeDraftProject } from '../utils/draftProjects';

const DASHBOARD_ROLES = [
    { value: 'cxo', label: 'Executive Summary Dashboard', description: 'High-level executive snapshot' },
    { value: 'project', label: 'Project Dashboard', description: 'PM, team lead, delivery' },
];
const ROLE_STORAGE_KEY = 'status_dashboard_selected_role';
const PROJECT_STORAGE_KEY = 'status_dashboard_selected_project_key';

const DEFAULT_ROADMAP = {
    steps: [
        'Project Initiation',
        'Requirement Screening',
        'Governance',
        'Agent Analysis',
        'Prerequisite Classification',
        'Task Creation',
        'Resource Onboarding',
        'On Flight',
        'Complete',
    ],
    current_step: 0,
    step_statuses: ['active', 'pending', 'pending', 'pending', 'pending', 'pending', 'pending', 'pending', 'pending'],
    failed_step: null,
};

/**
 * AppLayout – Shared layout wrapper providing the sidebar/navbar
 * uniformly across all authenticated pages.
 *
 * It manages: user auth, sidebar state, project list for sidebar navigation,
 * and currentView. The actual page content is rendered as children.
 */
export default function AppLayout({ children }) {
    const navigate = useNavigate();
    const location = useLocation();

    const [user, setUser] = useState(null);
    const [rbac, setRbac] = useState(null);
    const [isSidebarOpen, setIsSidebarOpen] = useState(true);
    const [projects, setProjects] = useState([]);
    const [shareProjects, setShareProjects] = useState([]);
    const [deletingProjectKey, setDeletingProjectKey] = useState('');

    const [selectedProjectKey, setSelectedProjectKey] = useState(() => {
        try {
            return localStorage.getItem(PROJECT_STORAGE_KEY) || '';
        } catch {
            return '';
        }
    });

    const unifiedProjects = useMemo(() => {
        const standard = projects.filter(p => !p.is_archived).map(p => ({ ...p, type: 'standard', timestamp: new Date(p.submissionDate || p.createdAt || p.latestDocument?.upload_date || 0).getTime() }));
        const shared = shareProjects.filter(p => !p.is_archived).map(p => ({ ...p, type: 'share', key: p.project_token, name: p.project_name, timestamp: new Date(p.created_at || 0).getTime() }));
        return [...standard, ...shared].sort((a, b) => b.timestamp - a.timestamp);
    }, [projects, shareProjects]);
    const [showSettings, setShowSettings] = useState(false);
    const [isNewProjectMode, setIsNewProjectMode] = useState(false);
    const [pluginClients, setPluginClients] = useState([]);
    const [launchingPluginId, setLaunchingPluginId] = useState('');

    const [isDarkMode, setIsDarkMode] = useState(() => {
        return localStorage.getItem('theme') === 'dark';
    });

    useEffect(() => {
        if (isDarkMode) {
            document.documentElement.classList.add('dark');
            localStorage.setItem('theme', 'dark');
        } else {
            document.documentElement.classList.remove('dark');
            localStorage.setItem('theme', 'light');
        }
    }, [isDarkMode]);

    const [selectedRole, setSelectedRole] = useState(() => {
        try {
            const storedRole = localStorage.getItem(ROLE_STORAGE_KEY);
            return DASHBOARD_ROLES.some((role) => role.value === storedRole) ? storedRole : 'project';
        } catch {
            return 'project';
        }
    });

    // Global AI configuration (shared across pages)
    const [aiConfig, setAiConfig] = useState(() => {
        try {
            const raw = localStorage.getItem('aiConfig');
            if (raw) {
                const parsed = JSON.parse(raw);
                // Ensure we always have expected shape
                return {
                    apiUrl: parsed.apiUrl || '',
                    apiKey: parsed.apiKey || '',
                    model: parsed.model || '',
                    // stream flag is used by AgentAnalysis; default false if missing
                    stream: typeof parsed.stream === 'boolean' ? parsed.stream : false,
                };
            }
        } catch {
            // ignore malformed storage
        }
        return { apiUrl: '', apiKey: '', model: '', stream: false };
    });

    useEffect(() => {
        try {
            localStorage.setItem('aiConfig', JSON.stringify(aiConfig));
        } catch {
            // ignore storage failures
        }
    }, [aiConfig]);

    useEffect(() => {
        if (!DASHBOARD_ROLES.some((r) => r.value === selectedRole)) {
            setSelectedRole('project');
            return;
        }
        try {
            localStorage.setItem(ROLE_STORAGE_KEY, selectedRole);
        } catch {
            // Ignore storage access errors in restricted browser contexts.
        }
    }, [selectedRole]);

    useEffect(() => {
        try {
            if (selectedProjectKey) {
                localStorage.setItem(PROJECT_STORAGE_KEY, selectedProjectKey);
            } else {
                localStorage.removeItem(PROJECT_STORAGE_KEY);
            }
        } catch {
            // Ignore storage errors in restricted browser contexts.
        }
    }, [selectedProjectKey]);

    const [requestingAccess, setRequestingAccess] = useState(false);
    const [requestSuccess, setRequestSuccess] = useState(false);
    const [authorizedRoles, setAuthorizedRoles] = useState([]);

    const invalidateProjects = useInvalidateProjects();
    const modal = useModal();

    // Track user progress automatically
    useProgressTracking(selectedProjectKey, true);

    const currentView = location.pathname === '/status-dashboard' ? 'statusDashboard'
        : location.pathname === '/organization-admin' ? 'organizationAdmin'
            : location.pathname === '/new-project' || location.pathname.startsWith('/new-project/') ? 'governance'
                : location.pathname === '/prerequisites' ? 'prerequisites'
                    : location.pathname === '/task-creation' ? 'taskCreation'
                        : location.pathname === '/resource-onboarding' ? 'resourceOnboarding'
                            : location.pathname === '/agent-analysis' ? 'agentAnalysis'
                                : location.pathname === '/governance-management' ? 'governanceManagement'
                                    : location.pathname === '/agents' ? 'agents'
                                        : location.pathname === '/plugins' ? 'plugins'
                                            : location.pathname.startsWith('/share-doc') ? 'shareDoc'
                                                : location.pathname.startsWith('/billing') ? 'billing'
                                                    : 'main';

    const isShareMode = location.pathname.startsWith('/share-doc');



    const getViewLabel = useCallback((view) => {
        switch (view) {
            case 'statusDashboard': return 'Project Status Dashboard';
            case 'organizationAdmin': return 'Organization Admin';
            case 'governance': return 'Project Setup & Governance';
            case 'prerequisites': return 'Prerequisite Classification';
            case 'taskCreation': return 'Task Creation Planner';
            case 'resourceOnboarding': return 'Resource Onboarding';
            case 'agentAnalysis': return 'Agent Analysis';
            case 'governanceManagement': return 'Governance Management';
            case 'agents': return 'Agents';
            case 'plugins': return 'Plugins';
            case 'billing': return 'Billing';
            default: return 'Requirements Analyzer';
        }
    }, []);

    const handleRequestAccess = async () => {
        if (!user || requestingAccess) return;
        setRequestingAccess(true);
        try {
            const token = localStorage.getItem('token');
            const response = await fetch(API_ENDPOINTS.ORG_RBAC_REQUEST_ACCESS, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${token}`
                },
                body: JSON.stringify({
                    path: location.pathname,
                    section_name: getViewLabel(currentView)
                })
            });
            if (response.ok) {
                setRequestSuccess(true);
                setTimeout(() => setRequestSuccess(false), 5000);
            }
        } catch (error) {
            console.error('Failed to request access:', error);
        } finally {
            setRequestingAccess(false);
        }
    };

    const setCurrentView = useCallback((view) => {
        if (view === 'statusDashboard') {
            navigate('/status-dashboard');
        } else if (view === 'organizationAdmin') {
            navigate('/organization-admin');
        } else if (view === 'governance') {
            navigate('/new-project');
        } else if (view === 'prerequisites') {
            navigate('/prerequisites');
        } else if (view === 'taskCreation') {
            navigate('/task-creation');
        } else if (view === 'resourceOnboarding') {
            navigate('/resource-onboarding');
        } else {
            navigate('/dashboard');
        }
    }, [navigate]);

    const handleLogout = useCallback(() => {
        setIsSidebarOpen(false);
        clearAuthData();
        navigate('/login');
    }, [navigate]);

    // Fetch user
    useEffect(() => {
        const token = localStorage.getItem('token');
        if (!token) { navigate('/login'); return; }

        fetch(API_ENDPOINTS.USERS_ME, {
            headers: { Authorization: `Bearer ${token}` }
        })
            .then(res => {
                if (!res.ok) throw new Error('Unauthorized');
                return res.json();
            })
            .then(data => {
                setUser(data);
                if (data?.is_super_admin) {
                    localStorage.setItem('is_super_admin', 'true');
                } else {
                    localStorage.removeItem('is_super_admin');
                }

                // Check if user is returning from VibeCoding
                const returnPath = sessionStorage.getItem('dsuite_return_path');
                const returnProject = sessionStorage.getItem('dsuite_return_project');

                if (returnPath && returnPath !== '/dashboard' && returnPath !== '/' && returnPath !== '/share-brd') {
                    console.log('🔙 Returning from VibeCoding, restoring path:', returnPath);

                    // Restore project selection if available
                    if (returnProject) {
                        setSelectedProjectKey(returnProject);
                        localStorage.setItem(PROJECT_STORAGE_KEY, returnProject);
                    }

                    // Clear the flags
                    sessionStorage.removeItem('dsuite_return_path');
                    sessionStorage.removeItem('dsuite_return_project');

                    // Navigate to the saved path
                    navigate(returnPath, { replace: true });
                }
            })
            .catch(() => handleLogout());
    }, [handleLogout, navigate]);

    // Fetch RBAC info once user is loaded
    useEffect(() => {
        if (!user) return;
        const token = localStorage.getItem('token');
        if (!token) return;
        fetch(API_ENDPOINTS.ORG_RBAC_ME, {
            headers: { Authorization: `Bearer ${token}` },
        })
            .then((res) => {
                if (!res.ok) throw new Error('Unauthorized');
                return res.json();
            })
            .then((data) => setRbac(data))
            .catch(() => setRbac({ is_org_admin: !!user?.is_org_admin, allowed_paths: [], role_name: null }));
    }, [user]);

    // Evaluate RBAC access synchronously to prevent render flashes
    const hasAccessError = useMemo(() => {
        if (!user || !rbac) return false;

        const path = location.pathname || '/';
        if (path === '/app' || path.startsWith('/app/') || path.startsWith('/share-doc')) return false;
        if (rbac?.is_org_admin) return false;

        const allowed = Array.isArray(rbac?.allowed_paths) ? rbac.allowed_paths : [];
        let rbacPath = path;
        if (path.startsWith('/a/')) {
            rbacPath = '/dashboard';
        }

        const isAllowed = allowed.some((p) => p === rbacPath || (p && rbacPath.startsWith(p + '/')));
        return !isAllowed;
    }, [user, rbac, location.pathname]);

    // Fetch roles that have access to current page
    useEffect(() => {
        if (!hasAccessError || !user) return;
        const token = localStorage.getItem('token');
        fetch(API_ENDPOINTS.ORG_RBAC_PAGE_ACCESS_INFO(location.pathname), {
            headers: { Authorization: `Bearer ${token}` }
        })
            .then(res => res.json())
            .then(data => setAuthorizedRoles(data.role_names || []))
            .catch(err => console.error('Failed to fetch role info:', err));
    }, [hasAccessError, location.pathname, user]);

    const fetchPluginClients = useCallback(() => {
        const token = localStorage.getItem('token');
        if (!token) return;

        fetch(API_ENDPOINTS.OAUTH_CLIENTS, {
            headers: { Authorization: `Bearer ${token}` },
        })
            .then((res) => {
                if (!res.ok) throw new Error('Failed to load plugins');
                return res.json();
            })
            .then((data) => {
                if (Array.isArray(data)) {
                    setPluginClients(data);
                } else {
                    setPluginClients([]);
                }
            })
            .catch(() => {
                setPluginClients([]);
            });
    }, []);

    useEffect(() => {
        if (!user) return;
        fetchPluginClients();
    }, [fetchPluginClients, user]);

    const fetchShareProjects = useCallback(async () => {
        const token = localStorage.getItem('token');
        if (!token) return;
        try {
            const response = await fetch(API_ENDPOINTS.SHARE_PROJECTS, {
                headers: { 'Authorization': `Bearer ${token}` }
            });
            if (response.ok) {
                const data = await response.json();
                setShareProjects(data);
            }
        } catch (error) {
            console.error('Error loading share projects:', error);
        }
    }, []);

    // Handle share mode detection
    useEffect(() => {
        if (isShareMode) {
            // If we're in share mode, make sure the sidebar project list is refreshed
            fetchShareProjects();
        }
    }, [isShareMode, fetchShareProjects]);

    useEffect(() => {
        if (isShareMode && user) {
            fetchShareProjects();
        }
    }, [isShareMode, user, fetchShareProjects]);

    const { data: generatedProjects = [], isLoading: isProjectsLoading, isError: isProjectsError, error: projectsError } = useProjects();

    useEffect(() => {
        setTimeout(() => {
            if (isProjectsError && projectsError?.message === 'Unauthorized') {
                handleLogout();
            } else if (generatedProjects) {
                setProjects(generatedProjects);
            }
        }, 0);
    }, [generatedProjects, isProjectsError, projectsError, handleLogout]);

    useEffect(() => {
        if (isNewProjectMode) return;
        if ((!projects || projects.length === 0) && (!shareProjects || shareProjects.length === 0)) {
            return;
        }

        const queueProjectSelection = (projectKey) => {
            setTimeout(() => setSelectedProjectKey(projectKey), 0);
        };

        const projectTokenFromPath = (() => {
            const match = location.pathname.match(/^\/a\/([^/?#]+)/);
            if (match) return decodeURIComponent(match[1]);

            // For share mode, check search params
            if (isShareMode) {
                const params = new URLSearchParams(location.search);
                return params.get('project') || '';
            }
            return '';
        })();

        const byPath = projectTokenFromPath
            ? unifiedProjects.find(
                (project) =>
                    project.key === projectTokenFromPath ||
                    project.projectToken === projectTokenFromPath
            )
            : null;
        const draftByPath = projectTokenFromPath ? getDraftProject(projectTokenFromPath) : null;

        if (byPath && byPath.key !== selectedProjectKey) {
            queueProjectSelection(byPath.key);
            return;
        }

        if (draftByPath) {
            if (draftByPath.key !== selectedProjectKey) {
                queueProjectSelection(draftByPath.key);
            }
            return;
        }

        if (selectedProjectKey && unifiedProjects.some((project) => project.key === selectedProjectKey)) {
            return;
        }

        if (selectedProjectKey && getDraftProject(selectedProjectKey)) {
            return;
        }

        let governanceContext = null;
        try {
            const raw =
                sessionStorage.getItem('governanceContext') ||
                localStorage.getItem('governanceContext');
            if (raw) governanceContext = JSON.parse(raw);
        } catch {
            governanceContext = null;
        }

        const byStored = (() => {
            try {
                const storedKey = localStorage.getItem(PROJECT_STORAGE_KEY);
                if (!storedKey) return null;
                return projects.find((project) => project.key === storedKey) || null;
            } catch {
                return null;
            }
        })();

        const byGovToken = governanceContext?.project_token
            ? projects.find(
                (project) =>
                    project.key === String(governanceContext.project_token) ||
                    project.projectToken === String(governanceContext.project_token)
            )
            : null;

        const byGovId = governanceContext?.result_id
            ? projects.find(
                (project) =>
                    String(project.governanceResultId || '') === String(governanceContext.result_id)
            )
            : null;

        const byGovName = governanceContext?.project_name
            ? projects.find(
                (project) =>
                    String(project.name || '').trim().toLowerCase() ===
                    String(governanceContext.project_name || '').trim().toLowerCase()
            )
            : null;

        const fallback =
            byPath ||
            byStored ||
            byGovToken ||
            byGovId ||
            byGovName ||
            projects[0];

        if (fallback?.key && fallback.key !== selectedProjectKey) {
            queueProjectSelection(fallback.key);
        }
    }, [projects, selectedProjectKey, location.pathname, isNewProjectMode]);

    const [storageNonce, forceUpdate] = React.useReducer(x => x + 1, 0);
    const { data: roadmapDataResult, refetch: refetchRoadmapData } = useRoadmapData(selectedProjectKey);
    // Refetch roadmap whenever we land on pages where the step may have changed (Resource Onboarding or Status Dashboard)
    useEffect(() => {
        if (selectedProjectKey && ['/resource-onboarding', '/status-dashboard', '/a/'].some(p => location.pathname.startsWith(p))) {
            // Add a small delay to ensure backend has processed any state changes
            const timer = setTimeout(() => {
                refetchRoadmapData();
            }, 500);
            return () => clearTimeout(timer);
        }
    }, [location.pathname, selectedProjectKey, refetchRoadmapData]);
    const lastNavigatedProjectRef = React.useRef(null);
    const lastSyncedProjectKeyRef = React.useRef(null);

    // Navigate to the appropriate page based on roadmap step when project is selected
    // IMPORTANT: This effect should ONLY navigate on initial page load or when landing
    // on a project URL (/a/{token}). When the user is already on a valid step page
    // and switches projects via the dropdown, we stay on the same step and let the
    // step component reload its own data for the new project.
    useEffect(() => {
        // Skip automatic redirection when a navigation was explicitly triggered
        // from GovernanceForm after project creation. This prevents the AppLayout
        // effect from overriding the intended navigation to Requirement Screening.
        const skipRedirect = sessionStorage.getItem('skipAppLayoutRedirect') === 'true';
        if (skipRedirect) {
            sessionStorage.removeItem('skipAppLayoutRedirect');
            return;
        }

        // If we are already on the Requirement Screening page, do not redirect
        if (location.pathname.startsWith('/dashboard')) {
            return;
        }

        if (!selectedProjectKey || isNewProjectMode || isShareMode) return;

        // FIRST: Check if governance was all skipped (score 5) - if so, block ALL navigation
        const isAllSkippedCase = roadmapDataResult &&
            roadmapDataResult.weighted_score === 5.0 &&
            roadmapDataResult.classification === 'ENTERPRISE';

        if (isAllSkippedCase) {
            const allowedRoutes = ['/new-project/governance', '/new-project', '/dashboard'];
            const isAllowedRoute = allowedRoutes.some(route => location.pathname.startsWith(route));

            if (!isAllowedRoute) {
                navigate('/new-project/governance', { replace: true });
                lastNavigatedProjectRef.current = selectedProjectKey;
            }
            return;
        }

        if (!roadmapDataResult) return;

        // Skip if we already navigated for this project
        if (lastNavigatedProjectRef.current === selectedProjectKey) return;

        // If user is already on a valid step page, DON'T auto-navigate away.
        // The step components will handle reloading their own data when
        // selectedProjectKey changes.
        const validStepPages = [
            '/new-project',
            '/dashboard',
            '/new-project/governance',
            '/agent-analysis',
            '/prerequisites',
            '/task-creation',
            '/resource-onboarding',
            '/status-dashboard',
        ];
        const isOnValidStepPage = validStepPages.some(page => location.pathname.startsWith(page));
        if (isOnValidStepPage) {
            lastNavigatedProjectRef.current = selectedProjectKey;
            return; // Stay on current step, let the component reload for the new project
        }

        const stepLabel = roadmapDataResult.current_step_label;
        if (!stepLabel) return;

        const stepLabelToRoute = {
            'Project Initiation': '/new-project',
            'Requirement Screening': '/dashboard',
            'Governance': '/new-project/governance',
            'Agent Analysis': '/agent-analysis',
            'Prerequisite Classification': '/prerequisites',
            'Task Creation': '/task-creation',
            'Resource Onboarding': '/resource-onboarding',
            'On Flight': '/status-dashboard',
            'Complete': '/status-dashboard',
            'Upload Documents': '/share-doc?step=1',
            'Configure Access': '/share-doc?step=2',
            'Share & Invite': '/share-doc?step=3',
            'Track Status': '/share-doc?step=4',
        };

        const targetRoute = stepLabelToRoute[stepLabel];
        if (!targetRoute) return;

        // Only navigate if we're on a project URL (/a/{token}) or a non-step page
        const isOnProjectUrl = location.pathname.startsWith('/a/');
        const isOnSpecialPage = ['/agents', '/organization-admin', '/plugins', '/billing'].includes(location.pathname);

        if (isOnProjectUrl && !isOnSpecialPage) {
            lastNavigatedProjectRef.current = selectedProjectKey;
            // CRITICAL: If the roadmap says Agent Analysis but governance is
            // PENDING (governance questionnaire not actually completed),
            // navigate to Requirement Screening (/dashboard) instead.
            const govClassification = String(selectedProject?.classification || '').trim().toUpperCase();
            const isPendingGovernance = !govClassification || ['PENDING', 'N/A', ''].includes(govClassification);
            const effectiveRoute = (targetRoute === '/agent-analysis' && isPendingGovernance)
                ? '/dashboard'
                : targetRoute;
            navigate(effectiveRoute);
        }
    }, [selectedProjectKey, roadmapDataResult, isNewProjectMode, isShareMode, location.pathname, navigate]);

    // Sync governanceContext and repoContext in sessionStorage/localStorage globally when selectedProjectKey changes
    useEffect(() => {
        if (!selectedProjectKey || selectedProjectKey === lastSyncedProjectKeyRef.current) return;
        lastSyncedProjectKeyRef.current = selectedProjectKey;

        // Immediately clear previous project's transient context before fetching target project's context
        sessionStorage.removeItem('governanceContext');
        sessionStorage.removeItem('governanceResult');
        sessionStorage.removeItem('repoContext');
        sessionStorage.removeItem('analysisResult');
        localStorage.removeItem('governanceContext');
        localStorage.removeItem('governanceResult');
        localStorage.removeItem('repoContext');
        localStorage.removeItem('analysisResult');

        const syncProjectStorage = async () => {
            const token = localStorage.getItem('token');
            if (!token) return;

            try {
                // Determine target identifier (prefer governanceResultId, fallback to project token)
                const projectFromList = projects.find((project) => project.key === selectedProjectKey);
                const identifier = projectFromList?.governanceResultId || selectedProjectKey;

                // 1. Fetch governance result from backend for selected project
                const govRes = await fetch(`${API_BASE_URL}/governance/result/${identifier}`, {
                    headers: { Authorization: `Bearer ${token}` }
                });

                if (govRes.ok) {
                    const data = await govRes.json();
                    if (data && data.id) {
                        const normalizedDimensionScores = {
                            business_value: data.dimension_scores?.business_value ?? 0,
                            data_sensitivity: data.dimension_scores?.data_sensitivity ?? 0,
                            integration_complexity: data.dimension_scores?.integration_complexity ?? 0,
                            operational_impact: data.dimension_scores?.operational_impact ?? 0,
                            ai_risk: data.dimension_scores?.ai_risk ?? 0,
                            ownership: data.dimension_scores?.ownership ?? 0,
                        };
                        const formattedAnswers = Array.isArray(data.answers)
                            ? data.answers.map((answer) => ({
                                question_id: answer.question_id,
                                score: answer.score,
                                selected_option: answer.selected_option || '',
                            }))
                            : [];
                        const fallbackDesc = (cls) => {
                            if (cls === 'SANDBOX') return 'Sandbox Approved - Low governance required';
                            if (cls === 'CONTROLLED_SANDBOX') return 'Controlled Sandbox (Fusion) - Standard template required';
                            if (cls === 'ENTERPRISE') return 'Enterprise Build - Full IT oversight required';
                            return 'Governance classification unavailable';
                        };

                        const govCtx = {
                            project_name: data.project_name || '',
                            result_id: data.id || null,
                            submission_date: data.submission_date,
                            classification: data.classification,
                            classification_description: data.classification_description || fallbackDesc(data.classification),
                            weighted_score: data.weighted_score,
                            recommendation: data.recommendation,
                            hard_stops: data.hard_stops || [],
                            answers: formattedAnswers,
                            dimension_scores: normalizedDimensionScores,
                        };

                        sessionStorage.setItem('governanceContext', JSON.stringify(govCtx));
                        sessionStorage.setItem('governanceResult', JSON.stringify(data));
                        localStorage.setItem('governanceContext', JSON.stringify(govCtx));
                        localStorage.setItem('governanceResult', JSON.stringify(data));
                        window.dispatchEvent(new Event('storage'));
                    }
                }
            } catch (e) {
                console.warn('Failed to sync governance storage for project:', e);
            }

            try {
                // 2. Fetch repo git config from backend for selected project
                const configRes = await fetch(`${API_BASE_URL}/api/projects/${selectedProjectKey}/git-config`, {
                    headers: { Authorization: `Bearer ${token}` }
                });

                if (configRes.ok) {
                    const configData = await configRes.json();
                    if (configData && configData.source_repo_url) {
                        const repoContextObj = {
                            repo: configData.source_repo_url,
                            provider: (configData.source_repo_url.includes('dev.azure.com') || configData.source_repo_url.includes('visualstudio.com')) ? 'azure-devops' : 'github',
                            context: ''
                        };
                        sessionStorage.setItem('repoContext', JSON.stringify(repoContextObj));
                        localStorage.setItem('repoContext', JSON.stringify(repoContextObj));
                        window.dispatchEvent(new Event('storage'));
                    }
                }
            } catch (e) {
                console.warn('Failed to sync repo storage for project:', e);
            }
        };

        syncProjectStorage();
    }, [selectedProjectKey, projects]);
    const hasServerRoadmap = !!roadmapDataResult;
    let roadmapData = roadmapDataResult || DEFAULT_ROADMAP;

    // Fast-fail the UI stepper if the project classification is Enterprise (meaning it's blocked from task agent workflow)
    const selectedProject = (() => {
        const projectFromList = projects.find((project) => project.key === selectedProjectKey) || null;
        const persistedDraftProject = getDraftProject(selectedProjectKey);
        if (!projectFromList) return persistedDraftProject || null;
        if (!persistedDraftProject) return projectFromList;

        // Prioritize backend credentials over draft - backend is source of truth
        const backendClientId = projectFromList.client_id || null;
        const backendClientSecret = projectFromList.client_secret || null;
        const finalClientId = (backendClientId && backendClientId.trim()) ? backendClientId : (persistedDraftProject?.client_id || null);
        const finalClientSecret = (backendClientSecret && backendClientSecret.trim()) ? backendClientSecret : (persistedDraftProject?.client_secret || null);

        return {
            ...persistedDraftProject,
            ...projectFromList,
            // Explicitly use backend credentials first, fallback to draft only if backend is null/empty
            client_id: finalClientId,
            client_secret: finalClientSecret,
            status: projectFromList.status === 'analysis_complete' || persistedDraftProject.status === 'analysis_complete'
                ? 'analysis_complete'
                : projectFromList.status,
        };
    })();
    const hasSelectedProjectGovernance = useMemo(() => {
        const _ = storageNonce;

        if (selectedProject?.governanceResultId) return true;

        const candidateIds = new Set(
            [
                selectedProjectKey,
                selectedProject?.key,
                selectedProject?.projectToken,
                selectedProject?.governanceResultId != null ? String(selectedProject.governanceResultId) : null,
            ]
                .filter(Boolean)
                .map((value) => String(value))
        );
        const selectedName = String(selectedProject?.name || '').trim().toLowerCase();

        const matchesStoredContext = (rawValue) => {
            if (!rawValue) return false;

            try {
                const parsed = JSON.parse(rawValue);
                const contextIds = [
                    parsed?.project_token,
                    parsed?.result_id != null ? String(parsed.result_id) : null,
                ]
                    .filter(Boolean)
                    .map((value) => String(value));

                if (contextIds.some((value) => candidateIds.has(value))) {
                    return true;
                }

                const contextName = String(parsed?.project_name || '').trim().toLowerCase();
                return Boolean(selectedName && contextName && selectedName === contextName);
            } catch {
                return false;
            }
        };

        return matchesStoredContext(sessionStorage.getItem('governanceContext'))
            || matchesStoredContext(localStorage.getItem('governanceContext'));
    }, [selectedProjectKey, selectedProject, storageNonce]);

    if (selectedProject?.classification === 'ENTERPRISE') {
        roadmapData = {
            ...roadmapData,
            current_step: 2,
            failed_step: 2,
            step_statuses: ['completed', 'completed', 'failed', 'pending', 'pending', 'pending', 'pending', 'pending', 'pending']
        };
    }

    // Keep "On Flight" emphasis on Status Dashboard.
    // On Task Creation page, keep the roadmap focused on Task Creation
    // until deploy stage starts.
    const roadmapDataForView = useMemo(() => {
        if (!roadmapData) return roadmapData;

        // Before governance has been submitted, drive the tracker from the current route.
        if (currentView === 'governance' && !hasServerRoadmap) {
            const steps = Array.isArray(roadmapData.steps) && roadmapData.steps.length > 0
                ? roadmapData.steps
                : DEFAULT_ROADMAP.steps;
            const statuses = Array(steps.length).fill('pending');
            const screeningIndex = steps.indexOf('Requirement Screening');
            const governanceIndex = steps.indexOf('Governance');
            const isGovernanceRoute = location.pathname.startsWith('/new-project/governance');
            const hasUploadedRequirements = Boolean(selectedProject?.latestDocument || selectedProject?.documents?.length);

            if (!isGovernanceRoute) {
                statuses[0] = 'active';
            } else {
                statuses[0] = 'completed';
                if (hasUploadedRequirements && screeningIndex !== -1) statuses[screeningIndex] = 'completed';
                if (governanceIndex !== -1) statuses[governanceIndex] = 'active';
            }

            return {
                ...roadmapData,
                steps,
                current_step: isGovernanceRoute && governanceIndex !== -1 ? governanceIndex : 0,
                step_statuses: statuses,
            };
        }

        if (currentView !== 'taskCreation') return roadmapData;

        const statuses = Array.isArray(roadmapData.step_statuses)
            ? [...roadmapData.step_statuses]
            : null;
        const steps = Array.isArray(roadmapData.steps) && roadmapData.steps.length > 0
            ? roadmapData.steps
            : DEFAULT_ROADMAP.steps;

        if (!statuses || !steps.length) return roadmapData;

        const onFlightIndex = steps.indexOf('On Flight');
        if (onFlightIndex === -1 || statuses.length <= onFlightIndex) {
            return roadmapData;
        }

        const completeStarted = statuses[onFlightIndex] === 'active' || statuses[onFlightIndex] === 'completed';
        if (completeStarted) return roadmapData;

        const taskIndex = steps.indexOf('Task Creation');
        const prereqIndex = steps.indexOf('Prerequisite Classification');

        if (
            taskIndex === -1 ||
            prereqIndex === -1 ||
            statuses.length <= taskIndex ||
            statuses.length <= prereqIndex
        ) {
            return roadmapData;
        }

        if (statuses[taskIndex] === 'active' || statuses[taskIndex] === 'completed') {
            const nextStatuses = [...statuses];
            nextStatuses[taskIndex] = 'pending';
            nextStatuses[prereqIndex] = 'active';
            return {
                ...roadmapData,
                current_step: prereqIndex,
                current_step_label: steps[prereqIndex] || 'Task Creation',
                step_statuses: nextStatuses,
            };
        }

        return roadmapData;
    }, [roadmapData, currentView, hasServerRoadmap, location.pathname, selectedProject]);

    // Watch for storage changes to keep roadmap synced with the governance wizard on /new-project
    useEffect(() => {
        const handleStorage = () => forceUpdate();
        window.addEventListener('storage', handleStorage);
        // Custom event for same-tab storage changes (sessionStorage doesn't trigger 'storage' in same tab)
        const originalSetItem = sessionStorage.setItem;
        sessionStorage.setItem = function () {
            originalSetItem.apply(this, arguments);
            handleStorage();
        };
        return () => {
            window.removeEventListener('storage', handleStorage);
            sessionStorage.setItem = originalSetItem;
        };
    }, []);

    // Drive the active roadmap step from the frontend route (UI-only logic)
    // BUT: If we have server roadmap data, use the server's current_step instead
    // EXCEPT: When on specific pages (governance, agent-analysis), always show that page's step
    const forcedRoadmapStepIndex = useMemo(() => {
        const path = location.pathname;

        // Dummy reference to satisfy linter and ensure memo updates on storage event
        const _ = storageNonce;

        const steps = Array.isArray(roadmapData?.steps) && roadmapData.steps.length > 0
            ? roadmapData.steps
            : DEFAULT_ROADMAP.steps;

        const idx = (label) => {
            const i = steps.indexOf(label);
            return i === -1 ? null : i;
        };

        // Priority 1: Check current route first - specific pages should always show their step
        if (path === '/new-project' || path.startsWith('/new-project/')) {
            if (path.startsWith('/new-project/governance')) {
                return idx('Governance') ?? 2;
            }
            return idx('Project Initiation') ?? 0;
        }

        if (path === '/prerequisites') return idx('Prerequisite Classification') ?? 4;
        if (path === '/task-creation') return idx('Task Creation') ?? 5;
        if (path === '/resource-onboarding') return idx('Resource Onboarding') ?? 6;
        if (path === '/status-dashboard') {
            const completeIndex = idx('Complete');
            const onFlightIndex = idx('On Flight');
            if (
                completeIndex !== null &&
                roadmapData?.current_step >= completeIndex
            ) {
                return completeIndex;
            }
            return onFlightIndex ?? completeIndex ?? (steps.length - 1);
        }

        if (path === '/dashboard' || path.startsWith('/a/')) {
            const showingResults = !!sessionStorage.getItem('dashboard_showing_results');
            // Upload form → Requirement Screening; Analysis results → Agent Analysis
            const reqIdx = idx('Requirement Screening') ?? 1;
            const governanceIdx = idx('Governance') ?? 2;
            const agentIdx = idx('Agent Analysis') ?? 3;
            if (showingResults) {
                return hasSelectedProjectGovernance ? agentIdx : governanceIdx;
            }
            // When on dashboard upload form (not showing results), always show Requirement Screening
            return reqIdx;
        }

        // Agent Analysis page should always show Agent Analysis as active
        if (path === '/agent-analysis') {
            const agentIdx = idx('Agent Analysis') ?? 3;
            return agentIdx;
        }

        // Priority 2: If we have server roadmap data and no specific route match, use server's current_step
        if (hasServerRoadmap && roadmapData?.current_step !== undefined && roadmapData?.current_step !== null) {
            return roadmapData.current_step;
        }

        return null;
    }, [location.pathname, roadmapData?.current_step, roadmapData?.steps, storageNonce, hasSelectedProjectGovernance, hasServerRoadmap]);

    // When the focused step is already done, render it green+highlighted instead of yellow
    const forcedStepCompleted = useMemo(() => {
        const path = location.pathname;
        if (path === '/dashboard' || path.startsWith('/a/')) {
            const showingResults = !!sessionStorage.getItem('dashboard_showing_results');
            return showingResults && hasSelectedProjectGovernance;
        }
        return false;
    }, [location.pathname, hasSelectedProjectGovernance]);

    // Backward compatibility for components expecting the old fetch logic
    const fetchRoadmapData = useCallback(() => {
        if (selectedProjectKey) {
            refetchRoadmapData();
        }
    }, [selectedProjectKey, refetchRoadmapData]);

    const fetchProjects = useCallback(() => {
        invalidateProjects();
    }, [invalidateProjects]);

    const handleDeleteProject = useCallback(async (project) => {
        const key = project.key || project.projectToken;
        if (!key || deletingProjectKey) return;

        // Step 1: Ask for confirmation
        const confirmed = await modal.showConfirm(
            `Are you sure you want to delete "${project.name || 'this project'}"?`,
            'Delete Project'
        );
        if (!confirmed) return;

        setDeletingProjectKey(key);

        // Remove project from local state immediately
        setProjects(prev => prev.filter(p => p.key !== key && p.projectToken !== key));
        setShareProjects(prev => prev.filter(p => p.project_token !== key && p.key !== key));
        if (selectedProjectKey === key) {
            setSelectedProjectKey('');
        }

        try {
            // Use projectToken (backend token) as primary identifier; governanceResultId as secondary
            // For pre-governance projects (no governance submitted yet), governanceResultId may exist
            // because the backend creates a GovernanceResponse row with an auto-generated id.
            const identifier = project.projectToken || project.governanceResultId || project.key;
            await deleteProjectByIdentifier(String(identifier));
            removeDraftProject(key);
            if (project.projectToken) removeDraftProject(project.projectToken);
            if (project.governanceResultId) removeDraftProject(project.governanceResultId);
            invalidateProjects();
        } catch (err) {
            console.error('Failed to delete project:', err);
            customError('Failed to delete project: ' + (err.message || 'Unknown error'));
        } finally {
            setDeletingProjectKey('');
        }
    }, [deletingProjectKey, selectedProjectKey, invalidateProjects, modal]);

    const handleNewProject = useCallback(() => {
        // Reset roadmap immediately and enter "new project" mode
        setSelectedProjectKey('');
        setIsNewProjectMode(true);
        localStorage.removeItem('governancePassed');
        localStorage.removeItem('governanceResult');
        localStorage.removeItem('governanceContext');
        localStorage.removeItem('repoContext');
        localStorage.removeItem('analysisResult');
        sessionStorage.removeItem('governanceResult');
        sessionStorage.removeItem('governanceContext');
        sessionStorage.removeItem('repoContext');
        sessionStorage.removeItem('analysisResult');
        sessionStorage.removeItem('dashboard_showing_results');
        window.dispatchEvent(new Event('storage'));
        navigate('/new-project?new=' + Date.now());
    }, [navigate]);

    const handleSelectProject = async (project) => {
        if (!project) return;
        setIsNewProjectMode(false);

        // Determine if the user is currently on a valid step page
        const validStepPages = [
            '/new-project',
            '/dashboard',
            '/new-project/governance',
            '/agent-analysis',
            '/prerequisites',
            '/task-creation',
            '/resource-onboarding',
            '/status-dashboard',
        ];
        const isOnValidStepPage = validStepPages.some(page => location.pathname.startsWith(page));

        // Reset sync ref so the sync effect re-runs for the new project
        lastSyncedProjectKeyRef.current = null;

        // Update the selected project key — this triggers all step components
        // to reload their data for the new project via their useEffect deps
        setSelectedProjectKey(project.key);

        // Refresh roadmap data for the sidebar stepper
        try {
            const identifier = project.projectToken || project.key;
            await fetchRoadmapStep(identifier);
            refetchRoadmapData();
        } catch (error) {
            console.error('Failed to fetch roadmap for project:', error);
        }

        // If the user is already on a valid step page, STAY THERE.
        // The step component will detect the selectedProjectKey change and
        // reload its own data. This is the key fix for smooth project switching.
        if (isOnValidStepPage) {
            return;
        }

        // If user is NOT on a step page (e.g. on /a/{token} or root), navigate
        // to the project's current roadmap step
        try {
            const identifier = project.projectToken || project.key;
            const roadmapResponse = await fetchRoadmapStep(identifier);
            if (roadmapResponse && roadmapResponse.current_step_label) {
                const stepLabelToRoute = {
                    'Project Initiation': '/new-project',
                    'Requirement Screening': '/dashboard',
                    'Governance': '/new-project/governance',
                    'Agent Analysis': '/agent-analysis',
                    'Prerequisite Classification': '/prerequisites',
                    'Task Creation': '/task-creation',
                    'Resource Onboarding': '/resource-onboarding',
                    'On Flight': '/status-dashboard',
                    'Complete': '/status-dashboard',
                    'Upload Documents': '/share-doc?step=1',
                    'Configure Access': '/share-doc?step=2',
                    'Share & Invite': '/share-doc?step=3',
                    'Track Status': '/share-doc?step=4',
                };
                const targetRoute = stepLabelToRoute[roadmapResponse.current_step_label];
                if (targetRoute) {
                    // CRITICAL: If the roadmap says Agent Analysis but governance is
                    // PENDING (governance questionnaire not actually completed),
                    // redirect to Requirement Screening (/dashboard) instead.
                    // This prevents old projects with only uploaded text (no analysis)
                    // from being redirected to Agent Analysis prematurely.
                    const govClassification = String(project.classification || '').trim().toUpperCase();
                    const isPendingGovernance = !govClassification || ['PENDING', 'N/A', ''].includes(govClassification);
                    const effectiveRoute = (targetRoute === '/agent-analysis' && isPendingGovernance)
                        ? '/dashboard'
                        : targetRoute;
                    navigate(effectiveRoute);
                    return;
                }
            }
        } catch (error) {
            console.error('Failed to fetch roadmap for navigation:', error);
        }

        // Fallback
        const targetPath = project.projectToken ? `/a/${project.projectToken}` : `/a/${project.key}`;
        if (location.pathname !== targetPath) {
            navigate(targetPath);
        }
    };

    const handleSelectShareProject = (project) => {
        const token = project.project_token || project.key;
        if (!token) return;

        setSelectedProjectKey(token);

        // Determine target step (default to 1 if not set)
        const step = project.current_step || 1;
        navigate(`/share-doc?step=${step}&project=${token}`);
    };

    const handleCreateShareProject = async (name) => {
        const token = localStorage.getItem('token');
        try {
            const response = await fetch(API_ENDPOINTS.SHARE_PROJECTS, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${token}`
                },
                body: JSON.stringify({
                    project_name: name,
                    description: 'Shared Documents'
                })
            });

            if (response.ok) {
                const data = await response.json();
                setShareProjects(prev => [data.project, ...prev]);
                setSelectedProjectKey(data.project.project_token);
                return data.project;
            }
        } catch (err) {
            console.error('Failed to create share project:', err);
        }
        return null;
    };

    const getProjectSidebarSubtitle = (project) => {
        if (project.classification && project.classification !== 'N/A') return project.classification;
        if (project.latestDocument) return `${project.documents.length} revision${project.documents.length !== 1 ? 's' : ''}`;
        return 'No uploads yet';
    };

    const handleOpenPlugin = useCallback(async (clientId) => {
        const token = localStorage.getItem('token');
        if (!token || !clientId) return;

        setLaunchingPluginId(clientId);
        try {
            const response = await fetch(API_ENDPOINTS.OAUTH_PLUGIN_LAUNCH(clientId), {
                headers: { Authorization: `Bearer ${token}` },
            });
            const data = await response.json().catch(() => ({}));
            if (!response.ok || !data.launch_url) {
                throw new Error(data.detail || 'Unable to launch plugin.');
            }
            window.location.assign(data.launch_url);
        } catch (err) {
            fetchPluginClients();
            customError(err.message || 'Unable to launch plugin.');
        } finally {
            setLaunchingPluginId('');
        }
    }, [fetchPluginClients]);

    if (!user || !rbac) {
        return (
            <div className="flex items-center justify-center min-h-screen bg-app-bg-muted">
                <div className="text-app-text-label">Loading...</div>
            </div>
        );
    }

    const layoutProps = {
        user, isSidebarOpen, setIsSidebarOpen, projects,
        projectsLoading: isProjectsLoading,
        selectedProjectKey, setSelectedProjectKey,
        showSettings, setShowSettings,
        aiConfig, setAiConfig,
        currentView, setCurrentView,
        handleLogout, fetchHistory: fetchProjects,
        handleNewProject, handleSelectProject,
        getProjectSidebarSubtitle,
        roadmapData, fetchRoadmapData,
        isNewProjectMode, setIsNewProjectMode,
        selectedRole, setSelectedRole,
        rbac,
        isShareMode,
        handleCreateShareProject,
        unifiedProjects,
    };

    return (
        <div className="flex h-screen bg-app-bg-page overflow-hidden font-sans">                        <Sidebar
                isSidebarOpen={isSidebarOpen}
                setIsSidebarOpen={setIsSidebarOpen}
                handleNewProject={handleNewProject}
                projects={layoutProps.unifiedProjects}
                selectedProjectKey={selectedProjectKey}
                handleSelectProject={(p) => p.type === 'share' ? handleSelectShareProject(p) : handleSelectProject(p)}
                getProjectSidebarSubtitle={(p) => p.type === 'share' ? `${p.document_count || 0} docs` : getProjectSidebarSubtitle(p)}
                currentView={currentView}
                setCurrentView={setCurrentView}
                setShowSettings={setShowSettings}
                user={user}
                handleLogout={handleLogout}
                pluginClients={pluginClients}
                launchingPluginId={launchingPluginId}
                handleOpenPlugin={handleOpenPlugin}
                isDarkMode={isDarkMode}
                rbac={rbac}
                isShareMode={isShareMode}
                handleCreateShareProject={handleCreateShareProject}
                handleDeleteProject={handleDeleteProject}
                deletingProjectKey={deletingProjectKey}
            />

            <div className="flex-1 min-w-0 flex flex-col overflow-hidden relative w-full bg-app-bg-page h-full transition-all duration-300 ease-in-out">
                {/* Global Top Navbar */}
                <header className="bg-[#1c355e] text-white px-4 md:px-6 py-3 flex items-center justify-between shadow-md z-[250] shrink-0">
                    <div className="flex items-center gap-3 md:gap-4 w-full">
                        {!isSidebarOpen && (
                            <button
                                type="button"
                                onClick={() => setIsSidebarOpen(true)}
                                className="p-1.5 md:p-2 bg-white/10 hover:bg-white/20 rounded-md shadow-sm text-white/80 hover:text-white transition-colors border border-white/20 cursor-pointer flex-shrink-0"
                                aria-label="Open menu"
                            >
                                <Menu className="w-4 h-4 md:w-5 md:h-5" />
                            </button>
                        )}
                        <div className="flex-1 min-w-0 flex items-center justify-between">
                            <div className="min-w-0 truncate">
                                <h1 className="text-lg md:text-2xl lg:text-3xl font-bold tracking-wide truncate">
                                    {currentView === 'statusDashboard' ? 'Project Status Dashboard' :
                                        currentView === 'organizationAdmin' ? 'Organization Admin' :
                                            currentView === 'governance' ? 'Project Setup & Governance' :
                                                currentView === 'prerequisites' ? 'Prerequisite Classification' :
                                                    currentView === 'taskCreation' ? 'Task Creation Planner' :
                                                        currentView === 'resourceOnboarding' ? 'Resource Onboarding' :
                                                            currentView === 'agentAnalysis' ? 'Agent Analysis' :
                                                                currentView === 'shareDoc' ? 'Secure Document Share' :
                                                                    'Requirements Analyzer'}
                                </h1>
                                <h2 className="text-[10px] md:text-sm italic text-white/60 mt-0.5 md:mt-1 truncate">
                                    {currentView === 'statusDashboard' ? '' :
                                        currentView === 'organizationAdmin' ? 'Identity & SSO Configuration' :
                                            currentView === 'governance' ? 'Project initiation and late-stage governance review' :
                                                currentView === 'prerequisites' ? 'AI-Identified Requirements & Credentials' :
                                                    currentView === 'taskCreation' ? 'Sprint, Milestone, and Task Generation' :
                                                        currentView === 'resourceOnboarding' ? 'Onboard AI agents for this project' :
                                                            currentView === 'agentAnalysis' ? 'Executive Summary & Agent Analysis' :
                                                                currentView === 'shareDoc' ? 'Upload, Manage, and Share Project Documents' :
                                                                    'Project Insight & AI Assessment'}
                                </h2>
                            </div>

                            {/* Right-side Controls Group */}
                            <div className="flex items-center gap-4 ml-4 shrink-0">
                                {(currentView === 'statusDashboard' || currentView === 'prerequisites' || currentView === 'governance' || currentView === 'taskCreation' || currentView === 'resourceOnboarding' || currentView === 'agentAnalysis' || currentView === 'main' || currentView === 'shareDoc') && location.pathname !== '/agents' && location.pathname !== '/plugins' && (
                                    <div className="flex flex-row-reverse gap-3 items-center bg-white/10 p-1.5 rounded-lg border border-white/20">
                                        <div className="w-48 sm:w-56">
                                            <ProjectDropdown
                                                projects={layoutProps.unifiedProjects}
                                                selectedKey={selectedProjectKey}
                                                onSelect={(proj) => {
                                                    if (!proj?.key || proj.key === selectedProjectKey) return;
                                                    if (proj.type === 'share') {
                                                        handleSelectShareProject(proj);
                                                    } else {
                                                        handleSelectProject(proj);
                                                    }
                                                }}
                                                onDelete={handleDeleteProject}
                                                deletingKey={deletingProjectKey}
                                                theme="dark"
                                            />
                                        </div>
                                        {currentView === 'statusDashboard' && (
                                            <>
                                                <div className="w-px h-5 bg-white/20"></div>
                                                <div className="w-48">
                                                    <RoleDropdown
                                                        roles={DASHBOARD_ROLES}
                                                        selectedRole={selectedRole}
                                                        onSelect={(roleValue) => setSelectedRole(roleValue)}
                                                        theme="dark"
                                                    />
                                                </div>
                                            </>
                                        )}
                                    </div>
                                )}

                                {/* User Docs Button */}
                                <button
                                    type="button"
                                    onClick={() => navigate('/docs')}
                                    className="hidden sm:flex items-center gap-2 px-3 py-1.5 bg-white/10 hover:bg-white/20 rounded-md text-white/80 hover:text-white transition-colors border border-white/20 text-sm font-medium cursor-pointer"
                                    aria-label="User Documentation"
                                >
                                    <BookOpen className="w-4 h-4" />
                                    <span>User Docs</span>
                                </button>

                                {/* Theme Toggle Button */}
                                <button
                                    type="button"
                                    onClick={() => setIsDarkMode(!isDarkMode)}
                                    className="p-1.5 md:p-2 rounded-md text-white/60 hover:text-white hover:bg-white/10 transition-colors border border-transparent hover:border-white/20 flex-shrink-0 cursor-pointer"
                                    aria-label="Toggle Dark Mode"
                                >
                                    {isDarkMode ? <Sun className="w-4 h-4 md:w-5 md:h-5" /> : <Moon className="w-4 h-4 md:w-5 md:h-5" />}
                                </button>
                            </div>
                        </div>
                    </div>
                </header>

                {/* ── Project-level Roadmap Stepper — shown on all pages except /agents, /plugins, and /superadmin/* ── */}
                {
                    roadmapDataForView && location.pathname !== '/agents' && location.pathname !== '/plugins' && location.pathname !== '/share-doc' && !location.pathname.startsWith('/superadmin') && (
                        <div className="bg-app-bg-card border-b border-app-border-light shadow-sm shrink-0 overflow-x-auto z-[240] relative">
                            <RoadmapHeader
                                steps={roadmapDataForView.steps || []}
                                currentStep={roadmapDataForView.current_step || 0}
                                stepStatuses={roadmapDataForView.step_statuses || null}
                                failedStep={roadmapDataForView.failed_step ?? null}
                                activeStepIndex={forcedRoadmapStepIndex}
                                activeStepCompleted={forcedStepCompleted}
                                selectedProjectKey={selectedProjectKey}
                            />
                        </div>
                    )
                }

                <div className="flex-1 flex flex-col min-h-0 overflow-hidden">
                    {hasAccessError ? (
                        <div className="flex flex-col items-center justify-center h-full text-center px-6 bg-app-bg-page relative z-[200] animate-in fade-in duration-500">
                            <div className="w-24 h-24 mb-8 bg-app-status-errorBg text-app-status-error flex items-center justify-center rounded-3xl shadow-lg border border-red-200/50 relative overflow-hidden group">
                                <div className="absolute inset-0 bg-red-500/10 opacity-0 group-hover:opacity-100 transition-opacity duration-300" />
                                <Lock className="w-10 h-10 relative z-10" />
                                <ShieldAlert className="w-6 h-6 absolute top-3 right-3 text-red-400 animate-pulse" />
                            </div>

                            <h2 className="text-3xl font-black text-app-text-main mb-4 tracking-tight">Access Restricted</h2>

                            <div className="max-w-md space-y-6">
                                <p className="text-app-text-light leading-relaxed">
                                    You don't have access to the <span className="text-app-primary font-bold px-2 py-1 bg-app-primary/5 rounded-lg border border-app-primary/10">{getViewLabel(currentView)}</span> section.
                                </p>

                                <div className="py-8 px-6 bg-app-bg-card border border-app-border rounded-2xl shadow-xl relative group">
                                    <div className="absolute -top-3 left-1/2 -translate-x-1/2 px-4 py-1 bg-app-primary text-white text-[10px] font-black uppercase tracking-widest rounded-full shadow-lg">
                                        Action Required
                                    </div>

                                    <p className="text-sm text-app-text-label mb-4 font-bold leading-relaxed">
                                        Request these roles to proceed with this step:
                                    </p>

                                    {authorizedRoles.length > 0 && (
                                        <div className="mb-6 p-4 bg-app-bg-muted/50 rounded-xl border border-app-border-light text-left">
                                            <div className="flex flex-wrap gap-2">
                                                {authorizedRoles.map(role => (
                                                    <span key={role} className="text-[11px] font-bold text-app-primary bg-app-primary/10 px-2 py-0.5 rounded border border-app-primary/20">
                                                        {role}
                                                    </span>
                                                ))}
                                                <span className="text-[11px] font-bold text-app-status-error bg-app-status-errorBg px-2 py-0.5 rounded border border-app-status-error/20">
                                                    Org Admin
                                                </span>
                                            </div>
                                        </div>
                                    )}

                                    <p className="text-xs text-app-text-muted mb-6 leading-loose">
                                        Click below to notify users holding these roles that you need action to continue the project workflow.
                                    </p>

                                    <button
                                        onClick={handleRequestAccess}
                                        disabled={requestingAccess || requestSuccess}
                                        className={`w-full flex items-center justify-center gap-3 px-8 py-4 rounded-xl font-bold transition-all transform active:scale-95 shadow-xl ${requestSuccess
                                            ? 'bg-app-status-successBg text-app-status-success border border-app-status-success/30 cursor-default'
                                            : 'bg-app-primary hover:bg-app-primary-hover text-white hover:shadow-app-primary/20'
                                            } ${requestingAccess ? 'opacity-70 cursor-wait' : ''}`}
                                    >
                                        {requestingAccess ? (
                                            <div className="w-5 h-5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                                        ) : requestSuccess ? (
                                            <>
                                                <CheckCircle className="w-5 h-5" />
                                                Request Sent Successfully
                                            </>
                                        ) : (
                                            <>
                                                <Mail className="w-5 h-5" />
                                                Send Request to Admin
                                            </>
                                        )}
                                    </button>

                                    {requestSuccess && (
                                        <p className="mt-4 text-[11px] font-bold text-app-status-success animate-in fade-in slide-in-from-top-2">
                                            Administrators have been notified via email.
                                        </p>
                                    )}
                                </div>
                            </div>
                        </div>
                    ) : (
                        typeof children === 'function'
                            ? children(layoutProps)
                            : React.Children.map(children, child =>
                                React.isValidElement(child)
                                    ? React.cloneElement(child, layoutProps)
                                    : child
                            )
                    )}
                </div>
            </div >

            {/* Global AI Config Modal - available on all pages */}
            {
                showSettings && (
                    <div className="fixed inset-0 z-[300] flex items-center justify-center p-4">
                        {/* Backdrop with blur */}
                        <div
                            className="absolute inset-0 bg-black/70 backdrop-blur-md"
                            onClick={() => setShowSettings(false)}
                        />
                        {/* Modal Content */}
                        <div className="relative z-[301] bg-app-bg-card rounded-xl shadow-2xl w-full max-w-md overflow-hidden transform transition-all scale-100">
                            <div className="p-5 border-b border-app-border-light flex justify-between items-center bg-app-bg-page/50">
                                <h2 className="font-bold text-lg text-app-text-main flex items-center">
                                    <Settings className="w-5 h-5 mr-2 text-app-primary" />
                                    AI Configuration
                                </h2>
                                <button
                                    onClick={() => setShowSettings(false)}
                                    className="text-app-text-light hover:text-app-text-label transition-colors text-xl leading-none w-6 h-6 flex items-center justify-center rounded hover:bg-app-bg-muted"
                                >
                                    ✕
                                </button>
                            </div>
                            <div className="p-6">
                                <AIConfig config={aiConfig} onConfigChange={setAiConfig} />
                            </div>
                            <div className="p-4 bg-app-bg-page border-t border-app-border-light flex justify-end">
                                <button
                                    onClick={() => setShowSettings(false)}
                                    className="px-5 py-2 bg-app-primary text-white rounded-lg hover:bg-app-primary-hover font-medium text-sm transition-colors shadow-md active:scale-95"
                                >
                                    Done
                                </button>
                            </div>
                        </div>
                    </div>
                )
            }
            {/* Deleting loading overlay — non-dismissible, shown while deletingProjectKey is set */}
            {deletingProjectKey && (
                <div className="fixed inset-0 z-[9999] flex items-center justify-center bg-black/50 backdrop-blur-sm">
                    <div className="bg-app-bg-card rounded-2xl shadow-2xl border border-app-border p-8 flex flex-col items-center gap-4 min-w-[260px]">
                        <div className="w-10 h-10 border-[3px] border-app-primary border-t-transparent rounded-full animate-spin" />
                        <p className="text-sm font-semibold text-app-text-main">Deleting project...</p>
                    </div>
                </div>
            )}
            {/* AI Assistant Bot - available on all pages */}
            <AssistantBot />
        </div >
    );
}
