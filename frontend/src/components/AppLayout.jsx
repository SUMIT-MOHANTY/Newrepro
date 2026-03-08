import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { API_ENDPOINTS } from '../config';
import { clearAuthData } from '../utils/auth';
import { Menu, Settings } from 'lucide-react';
import Sidebar from './Sidebar';
import RoadmapHeader from './RoadmapHeader';
import AgentsPage from './AgentsPage';

import { useProjects, useRoadmapData, useInvalidateProjects } from '../hooks/useProjects';
import { fetchRoadmapStep } from '../api/projects';
import ProjectDropdown from './ProjectDropdown';
import RoleDropdown from './RoleDropdown';
import { getDraftProject } from '../utils/draftProjects';

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
    const [isSidebarOpen, setIsSidebarOpen] = useState(true);
    const [projects, setProjects] = useState([]);
    const [selectedProjectKey, setSelectedProjectKey] = useState(() => {
        try {
            return localStorage.getItem(PROJECT_STORAGE_KEY) || '';
        } catch {
            return '';
        }
    });
    const [showSettings, setShowSettings] = useState(false);
    const [isNewProjectMode, setIsNewProjectMode] = useState(false);
    const [pluginClients, setPluginClients] = useState([]);
    const [launchingPluginId, setLaunchingPluginId] = useState('');

    const [selectedRole, setSelectedRole] = useState(() => {
        try {
            const storedRole = localStorage.getItem(ROLE_STORAGE_KEY);
            return DASHBOARD_ROLES.some((role) => role.value === storedRole) ? storedRole : 'project';
        } catch {
            return 'project';
        }
    });

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

    const invalidateProjects = useInvalidateProjects();

    const currentView = location.pathname === '/status-dashboard' ? 'statusDashboard'
        : location.pathname === '/organization-admin' ? 'organizationAdmin'
            : location.pathname === '/new-project' || location.pathname.startsWith('/new-project/') ? 'governance'
                : location.pathname === '/prerequisites' ? 'prerequisites'
                    : location.pathname === '/task-creation' ? 'taskCreation'
                        : location.pathname === '/resource-onboarding' ? 'resourceOnboarding'
                            : location.pathname === '/agent-analysis' ? 'agentAnalysis'
                                : 'main';

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
            .then(data => setUser(data))
            .catch(() => handleLogout());
    }, [handleLogout, navigate]);

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
        if (!projects || projects.length === 0) {
            return;
        }

        const queueProjectSelection = (projectKey) => {
            setTimeout(() => setSelectedProjectKey(projectKey), 0);
        };

        const projectTokenFromPath = (() => {
            const match = location.pathname.match(/^\/a\/([^/?#]+)/);
            return match ? decodeURIComponent(match[1]) : '';
        })();

        const byPath = projectTokenFromPath
            ? projects.find(
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

        if (selectedProjectKey && projects.some((project) => project.key === selectedProjectKey)) {
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
    
  // Navigate to the appropriate page based on roadmap step when project is selected
  useEffect(() => {
    if (!selectedProjectKey || isNewProjectMode) return;

    // FIRST: Check if governance was all skipped (score 5) - if so, block ALL navigation
    // This check now relies on roadmapDataResult.classification from the backend
    const isAllSkippedCase = roadmapDataResult &&
      roadmapDataResult.weighted_score === 5.0 &&
      roadmapDataResult.classification === 'ENTERPRISE';

    // If all skipped, block ALL routes except governance-related pages
    if (isAllSkippedCase) {
      const allowedRoutes = ['/new-project/governance', '/new-project', '/dashboard'];
      const isAllowedRoute = allowedRoutes.some(route => location.pathname.startsWith(route));

      if (!isAllowedRoute) {
        // Redirect to governance page if trying to access any other route
        navigate('/new-project/governance', { replace: true });
        lastNavigatedProjectRef.current = selectedProjectKey; // Prevent re-navigation loop
      }
      return; // Stop here - don't process roadmap navigation
    }

    // Continue with normal roadmap navigation only if NOT all skipped
    if (!roadmapDataResult) return;
        
        // Skip if we already navigated for this project
        if (lastNavigatedProjectRef.current === selectedProjectKey) return;
        
        const stepLabel = roadmapDataResult.current_step_label;
        if (!stepLabel) return;
        
        // Map step label to route
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
        };
        
        const targetRoute = stepLabelToRoute[stepLabel];
        if (!targetRoute) return;
        
        // Special handling for Agent Analysis: Don't auto-navigate unless user clicked "Proceed to Agent Analysis"
        // This prevents auto-redirect when viewing Governance score page
        if (targetRoute === '/agent-analysis') {
            const shouldStartAnalysis = sessionStorage.getItem('shouldStartAnalysis') === 'true';
            const isOnGovernancePage = location.pathname === '/new-project/governance' || location.pathname.startsWith('/new-project/governance');
            
            // Don't auto-navigate to Agent Analysis if:
            // 1. User is on Governance page (viewing score)
            // 2. Flag is not set (user hasn't clicked "Proceed to Agent Analysis")
            if (isOnGovernancePage || !shouldStartAnalysis) {
                return; // Stay on current page, don't navigate
            }
        }
        
        // Special handling for Prerequisites: Don't auto-navigate from Agent Analysis page
        // User should manually click "Review Prerequisites" button to navigate
        if (targetRoute === '/prerequisites') {
            const isOnAgentAnalysisPage = location.pathname === '/agent-analysis' || location.pathname.startsWith('/agent-analysis');
            
            // Don't auto-navigate to Prerequisites if user is on Agent Analysis page
            // Let them manually click the button to navigate
            if (isOnAgentAnalysisPage) {
                return; // Stay on Agent Analysis page, don't auto-navigate
            }
        }
        
        // Navigate if:
        // 1. We're on a project URL (/a/{token}) - redirect to step page
        // 2. We're not on the correct step page already
        // 3. We're not on special pages like /agents
        const isOnProjectUrl = location.pathname.startsWith('/a/');
        const isOnTargetRoute = location.pathname.startsWith(targetRoute);
        const isOnSpecialPage = ['/agents', '/organization-admin', '/plugins'].includes(location.pathname);
        
        if ((isOnProjectUrl || !isOnTargetRoute) && !isOnSpecialPage) {
            lastNavigatedProjectRef.current = selectedProjectKey;
            navigate(targetRoute);
        }
    }, [selectedProjectKey, roadmapDataResult, isNewProjectMode, location.pathname, navigate]);
    
    // Reset navigation tracking when project changes
    useEffect(() => {
        lastNavigatedProjectRef.current = null;
    }, [selectedProjectKey]);
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
            return hasSelectedProjectGovernance ? agentIdx : reqIdx;
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

    const handleNewProject = useCallback(() => {
        // Reset roadmap immediately and enter "new project" mode
        setSelectedProjectKey('');
        setIsNewProjectMode(true);
        localStorage.removeItem('governancePassed');
        localStorage.removeItem('governanceResult');
        localStorage.removeItem('governanceContext');
        sessionStorage.removeItem('governanceResult');
        sessionStorage.removeItem('governanceContext');
        navigate('/new-project?new=' + Date.now());
    }, [navigate]);

    const handleSelectProject = async (project) => {
        if (!project) return;
        setIsNewProjectMode(false);
        setSelectedProjectKey(project.key);
        
        // Fetch roadmap data to determine which page to navigate to
        try {
            // Prefer the project token if it exists – the backend uses this to locate the project
            const identifier = project.projectToken || project.key;
            const roadmapResponse = await fetchRoadmapStep(identifier);
            if (roadmapResponse && roadmapResponse.current_step_label) {
                const stepLabel = roadmapResponse.current_step_label;
                
                // Map step label to route (same mapping as before)
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
                };
                const targetRoute = stepLabelToRoute[stepLabel];
                if (targetRoute) {
                    // Always navigate to the target route (even if we are already there) to force a refresh
                    navigate(targetRoute);
                    // Ensure we have the freshest roadmap data for the newly selected project
                    refetchRoadmapData();
                    return;
                }
            }
        } catch (error) {
            console.error('Failed to fetch roadmap for navigation:', error);
        }
        
        // Fallback – navigate to the generic project URL (uses token if available)
        const targetPath = project.projectToken ? `/a/${project.projectToken}` : `/a/${project.key}`;
        if (location.pathname !== targetPath) {
            navigate(targetPath);
            refetchRoadmapData();
        }
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
            window.alert(err.message || 'Unable to launch plugin.');
        } finally {
            setLaunchingPluginId('');
        }
    }, [fetchPluginClients]);

    if (!user) {
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
        currentView, setCurrentView,
        handleLogout, fetchHistory: fetchProjects,
        handleNewProject, handleSelectProject,
        getProjectSidebarSubtitle,
        roadmapData, fetchRoadmapData,
        isNewProjectMode, setIsNewProjectMode,
        selectedRole, setSelectedRole,
    };

    return (
        <div className="flex h-screen bg-app-bg-page overflow-hidden font-sans">
            <Sidebar
                isSidebarOpen={isSidebarOpen}
                setIsSidebarOpen={setIsSidebarOpen}
                handleNewProject={handleNewProject}
                projects={projects}
                selectedProjectKey={selectedProjectKey}
                handleSelectProject={handleSelectProject}
                getProjectSidebarSubtitle={getProjectSidebarSubtitle}
                currentView={currentView}
                setCurrentView={setCurrentView}
                setShowSettings={setShowSettings}
                user={user}
                handleLogout={handleLogout}
                pluginClients={pluginClients}
                launchingPluginId={launchingPluginId}
                handleOpenPlugin={handleOpenPlugin}
            />

            <div className="flex-1 min-w-0 flex flex-col overflow-hidden relative w-full bg-app-bg-page h-full transition-all duration-300 ease-in-out">
                {/* Global Top Navbar */}
                <header className="bg-[#1c355e] text-white px-4 md:px-6 py-3 flex items-center justify-between shadow-md z-[250] shrink-0">
                    <div className="flex items-center gap-3 md:gap-4 w-full">
                        {!isSidebarOpen && (
                            <button
                                type="button"
                                onClick={() => setIsSidebarOpen(true)}
                                className="p-1.5 md:p-2 bg-app-bg-card/10 hover:bg-app-bg-card/20 rounded-md shadow-sm text-gray-100 hover:text-white transition-colors border border-white/20 cursor-pointer flex-shrink-0"
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
                                                            'Requirements Analyzer'}
                                </h1>
                                <h2 className="text-[10px] md:text-sm italic text-app-border mt-0.5 md:mt-1 truncate">
                                    {currentView === 'statusDashboard' ? '' :
                                        currentView === 'organizationAdmin' ? 'Identity & SSO Configuration' :
                                        currentView === 'governance' ? 'Project initiation and late-stage governance review' :
                                            currentView === 'prerequisites' ? 'AI-Identified Requirements & Credentials' :
                                                currentView === 'taskCreation' ? 'Sprint, Milestone, and Task Generation' :
                                                    currentView === 'resourceOnboarding' ? 'Onboard AI agents for this project' :
                                                        currentView === 'agentAnalysis' ? 'Executive Summary & Agent Analysis' :
                                                            'Project Insight & AI Assessment'}
                                </h2>
                            </div>

                            {(currentView === 'statusDashboard' || currentView === 'prerequisites' || currentView === 'main') && location.pathname !== '/agents' && location.pathname !== '/plugins' && (
                                <div className="flex flex-row gap-3 ml-4 shrink-0 items-center bg-white/10 p-1.5 rounded-lg border border-white/20">
                                    {currentView === 'statusDashboard' && (
                                        <>
                                            <div className="w-48">
                                                <RoleDropdown
                                                    roles={DASHBOARD_ROLES}
                                                    selectedRole={selectedRole}
                                                    onSelect={(roleValue) => setSelectedRole(roleValue)}
                                                    theme="dark"
                                                />
                                            </div>
                                            <div className="w-px h-5 bg-white/20"></div>
                                        </>
                                    )}
                                    <div className="w-48 sm:w-56">
                                        <ProjectDropdown
                                            projects={projects}
                                            selectedKey={selectedProjectKey}
                                            onSelect={(proj) => {
                                                if (!proj?.key || proj.key === selectedProjectKey) return;
                                                handleSelectProject(proj);
                                            }}
                                            theme="dark"
                                        />
                                    </div>
                                </div>
                            )}

                            {/* Status Pipeline graphic top right - ONLY shown on statusDashboard */}
                            {/* {currentView === 'statusDashboard' && (
                                <div className="text-[9px] md:text-xs font-bold text-app-text-label flex items-center space-x-1.5 bg-app-bg-card px-2 md:px-3 py-1.5 rounded-full shadow-md border border-app-border-light whitespace-nowrap ml-4 shrink-0 hidden sm:flex">
                                    <div className="flex items-center"><span className="w-2.5 h-2.5 md:w-3 md:h-3 bg-gray-400 rounded-full mr-1"></span><span className="hidden md:inline">KICK-OFF</span></div>
                                    <div className="flex items-center"><span className="w-2.5 h-2.5 md:w-3 md:h-3 bg-orange-200 rounded-full mr-1"></span><span className="hidden md:inline">PREPARE</span></div>
                                    <div className="flex items-center"><span className="w-2.5 h-2.5 md:w-3 md:h-3 bg-yellow-400 rounded-full mr-1"></span><span className="hidden md:inline">INTERVIEW</span></div>
                                    <div className="flex items-center"><span className="w-2.5 h-2.5 md:w-3 md:h-3 bg-blue-500 rounded-full mr-1"></span><span className="hidden md:inline">APPRAISED</span></div>
                                    <div className="flex items-center"><span className="w-2.5 h-2.5 md:w-3 md:h-3 bg-green-500 rounded-full"></span></div>
                                </div>
                            )} */}

                            {/* Settings Button (Global) */}
                            {/* <button
                                type="button"
                                onClick={() => setShowSettings(true)}
                                className="p-1.5 md:p-2 ml-4 rounded-md text-app-border hover:text-white hover:bg-app-bg-card/10 transition-colors border border-transparent hover:border-white/20 flex-shrink-0"
                                aria-label="Open settings"
                            >
                                <Settings className="w-4 h-4 md:w-5 md:h-5" />
                            </button> */}
                        </div>
                    </div>
                </header>

{/* ── Project-level Roadmap Stepper — shown on all pages except /agents and /plugins ── */}
{roadmapDataForView && location.pathname !== '/agents' && location.pathname !== '/plugins' && (
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
                )}

                <div className="flex-1 h-full overflow-hidden">
                    {typeof children === 'function'
                        ? children(layoutProps)
                        : React.Children.map(children, child =>
                            React.isValidElement(child)
                                ? React.cloneElement(child, layoutProps)
                                : child
                        )
                    }
                </div>
            </div >
        </div >
    );
}
