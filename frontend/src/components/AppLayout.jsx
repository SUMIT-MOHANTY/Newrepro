import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { API_ENDPOINTS } from '../config';
import { clearAuthData } from '../utils/auth';
import { Menu, Settings } from 'lucide-react';
import Sidebar from './Sidebar';
import RoadmapHeader from './RoadmapHeader';

import { useProjects, useRoadmapData, useInvalidateProjects } from '../hooks/useProjects';
import ProjectDropdown from './ProjectDropdown';
import RoleDropdown from './RoleDropdown';

const DASHBOARD_ROLES = [
    { value: 'cxo', label: 'Executive Summary Dashboard', description: 'High-level executive snapshot' },
    { value: 'project', label: 'Project Dashboard', description: 'PM, team lead, delivery' },
];
const ROLE_STORAGE_KEY = 'status_dashboard_selected_role';

const DEFAULT_ROADMAP = {
    steps: ['Project Setup', 'Requirement Screening', 'AI Analysis', 'Prerequisite Classification', 'Task Creation', 'Agent Execution', 'Complete'],
    current_step: 0,
    step_statuses: ['active', 'pending', 'pending', 'pending', 'pending', 'pending', 'pending'],
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
    const [selectedProjectKey, setSelectedProjectKey] = useState('');
    const [showSettings, setShowSettings] = useState(false);
    const [isNewProjectMode, setIsNewProjectMode] = useState(false);

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
            // eslint-disable-next-line react-hooks/set-state-in-effect
            setSelectedRole('project');
            return;
        }
        try {
            localStorage.setItem(ROLE_STORAGE_KEY, selectedRole);
        } catch {
            // Ignore storage access errors in restricted browser contexts.
        }
    }, [selectedRole]);

    const invalidateProjects = useInvalidateProjects();

    const currentView = location.pathname === '/status-dashboard' ? 'statusDashboard'
        : location.pathname === '/organization-admin' ? 'organizationAdmin'
            : location.pathname === '/governance' ? 'governance'
                : location.pathname === '/prerequisites' ? 'prerequisites'
                    : 'main';

    const setCurrentView = useCallback((view) => {
        if (view === 'statusDashboard') {
            navigate('/status-dashboard');
        } else if (view === 'organizationAdmin') {
            navigate('/organization-admin');
        } else if (view === 'governance') {
            navigate('/governance');
        } else if (view === 'prerequisites') {
            navigate('/prerequisites');
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

    const { data: roadmapDataResult, refetch: refetchRoadmapData } = useRoadmapData(selectedProjectKey);
    let roadmapData = roadmapDataResult || DEFAULT_ROADMAP;

    // Fast-fail the UI stepper if the project classification is Enterprise (meaning it's blocked from task agent workflow)
    const selectedProject = projects.find(p => p.key === selectedProjectKey);
    if (selectedProject?.classification === 'ENTERPRISE') {
        roadmapData = {
            ...roadmapData,
            current_step: 1,
            failed_step: 1,
            step_statuses: ['completed', 'failed', 'pending', 'pending', 'pending', 'pending']
        };
    }

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
        navigate('/governance?new=' + Date.now());
    }, [navigate]);

    const handleSelectProject = (project) => {
        if (!project) return;
        setIsNewProjectMode(false);
        setSelectedProjectKey(project.key);
        const targetPath = project.projectToken ? `/a/${project.projectToken}` : `/a/${project.key}`;
        if (location.pathname !== targetPath) navigate(targetPath);
    };

    const getProjectSidebarSubtitle = (project) => {
        if (project.classification && project.classification !== 'N/A') return project.classification;
        if (project.latestDocument) return `${project.documents.length} revision${project.documents.length !== 1 ? 's' : ''}`;
        return 'No uploads yet';
    };

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
            />

            <div className="flex-1 min-w-0 flex flex-col overflow-hidden relative w-full bg-app-bg-page h-full transition-all duration-300 ease-in-out">
                {/* Global Top Navbar */}
                <header className="bg-[#1c355e] text-white px-4 md:px-6 py-3 flex items-center justify-between shadow-md z-20 shrink-0">
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
                                        currentView === 'governance' ? 'Project Requirement Screening' :
                                            currentView === 'prerequisites' ? 'Prerequisite Classification' :
                                                'BRD Requirements Analyzer'}
                                </h1>
                                <h2 className="text-[10px] md:text-sm italic text-app-border mt-0.5 md:mt-1 truncate">
                                    {currentView === 'statusDashboard' ? '' :
                                        currentView === 'organizationAdmin' ? 'Identity & SSO Configuration' :
                                        currentView === 'governance' ? 'Screening & Configuration' :
                                            currentView === 'prerequisites' ? 'AI-Identified Requirements & Credentials' :
                                                'Project Insight & AI Assessment'}
                                </h2>
                            </div>

                            {currentView === 'statusDashboard' && (
                                <div className="flex flex-row gap-3 ml-4 shrink-0 items-center bg-white/10 p-1.5 rounded-lg border border-white/20">
                                    <div className="w-48">
                                        <RoleDropdown
                                            roles={DASHBOARD_ROLES}
                                            selectedRole={selectedRole}
                                            onSelect={(roleValue) => setSelectedRole(roleValue)}
                                            theme="dark"
                                        />
                                    </div>
                                    <div className="w-px h-5 bg-white/20"></div>
                                    <div className="w-48 sm:w-56">
                                        <ProjectDropdown
                                            projects={projects}
                                            selectedKey={selectedProjectKey}
                                            onSelect={(proj) => {
                                                if (!proj?.key || proj.key === selectedProjectKey) return;
                                                setSelectedProjectKey(proj.key);
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

                {/* ── Project-level Roadmap Stepper — shown on all pages ── */}
                {roadmapData && (
                    <div className="bg-app-bg-card border-b border-app-border-light shadow-sm shrink-0 overflow-x-auto">
                        <RoadmapHeader
                            steps={roadmapData.steps || []}
                            currentStep={roadmapData.current_step || 0}
                            stepStatuses={roadmapData.step_statuses || null}
                            failedStep={roadmapData.failed_step ?? null}
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
