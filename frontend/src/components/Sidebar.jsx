import React, { useState, useEffect } from 'react';
import { useNavigate, useLocation, useSearchParams } from 'react-router-dom';
import { X, Plus, FileCheck, History, Activity, Settings, User, LogOut, Trash2, Users, ShieldCheck, Globe, Check, Share2, CreditCard } from 'lucide-react';
import bourntecLogo from '../assets/bourntec_logo.png';
import { API_ENDPOINTS } from '../config';
import NewProjectModal from './NewProjectModal';
import ShareDocumentModal from './ShareDocumentModal';

export default function Sidebar({
    isSidebarOpen,
    setIsSidebarOpen,
    handleNewProject,
    projects,
    selectedProjectKey,
    handleSelectProject,
    getProjectSidebarSubtitle,
    currentView,
    setCurrentView,
    setShowSettings,
    user,
    handleLogout,
    handleDeleteProject,
    deletingProjectKey,
    isDarkMode = false,
    rbac,
    isShareMode = false,
    handleCreateShareProject,
}) {
    const navigate = useNavigate();
    const location = useLocation();
    const [searchParams, setSearchParams] = useSearchParams();
    const [navExpanded, setNavExpanded] = useState(true);
    // Agents state
    const [agents, setAgents] = useState([]);
    const [agentsLoading, setAgentsLoading] = useState(false);
    const [agentsError, setAgentsError] = useState(null);
    const [agentsExpanded, setAgentsExpanded] = useState(false);

    const [showNewProjectModal, setShowNewProjectModal] = useState(false);
    const [showShareDocumentModal, setShowShareDocumentModal] = useState(false);

    useEffect(() => {
        if (isShareMode && searchParams.get('create') === 'true') {
            // Clear the param
            const newParams = new URLSearchParams(searchParams);
            newParams.delete('create');
            setSearchParams(newParams, { replace: true });
        }
    }, [isShareMode, searchParams, setSearchParams]);

    useEffect(() => {
        if (!agentsExpanded) return;
        const fetchAgents = async () => {
            setAgentsLoading(true);
            const token = localStorage.getItem('token');
            try {
                const res = await fetch(API_ENDPOINTS.AGENTS, {
                    headers: { Authorization: `Bearer ${token}` },
                });
                if (!res.ok) throw new Error('Failed to fetch agents');
                const data = await res.json();
                setAgents(data?.agents || []);
                setAgentsError(null);
            } catch (e) {
                setAgentsError(e.message);
            } finally {
                setAgentsLoading(false);
            }
        };
        fetchAgents();
    }, [agentsExpanded]);

    const handleDeleteAgent = async (agentId) => {
        const token = localStorage.getItem('token');
        try {
            const res = await fetch(API_ENDPOINTS.AGENT_REMOVE(agentId), {
                method: 'DELETE',
                headers: { Authorization: `Bearer ${token}` },
            });
            if (!res.ok) throw new Error('Delete failed');
            // Refresh list locally
            setAgents((prev) => prev.filter((a) => a.id !== agentId));
        } catch (e) {
            console.error(e);
            setAgentsError(e.message);
        }
    };

    const canAccess = (path) => {
        if (!path) return true;
        if (rbac?.is_org_admin) return true;
        const allowed = Array.isArray(rbac?.allowed_paths) ? rbac.allowed_paths : null;
        if (!allowed) return true; // if RBAC not loaded, don't block UI

        let rbacPath = path;
        if (path.startsWith('/a/')) {
            rbacPath = '/dashboard';
        }

        return allowed.some((p) => p === rbacPath || (p && rbacPath.startsWith(p + '/')));
    };

    return (
        <>
            {isSidebarOpen && (
                <button
                    type="button"
                    aria-label="Close sidebar"
                    onClick={() => setIsSidebarOpen(false)}
                    className="fixed inset-0 z-[240] bg-black/40 transition-opacity duration-300 ease-in-out md:hidden"
                />
            )}

            <div className={`hidden md:block transition-[width] duration-300 ease-in-out flex-shrink-0 ${isSidebarOpen ? 'w-72' : 'w-0'}`} />

            <div
                className={`fixed inset-y-0 left-0 z-[250] w-72 bg-app-sidebar-bg border-r border-app-sidebar-bg flex flex-col text-app-border shadow-xl transition-transform duration-300 ease-in-out ${isSidebarOpen ? 'translate-x-0' : '-translate-x-full'}`}
            >
                <div className="h-16 flex items-center px-2 border-b border-app-sidebar-bg bg-app-sidebar-bg shrink-0">
                    <div className="flex items-center justify-between w-full">
                        <div className="flex items-center min-w-0">
                            <img
                                src={bourntecLogo}
                                alt="App Logo"
                                className="h-5 w-auto object-contain shrink-0"
                            />
                            <div className="h-5 w-0.5 bg-app-bg-card mx-3 shrink-0 rounded-full"></div>
                            <span className="text-sm font-bold text-white tracking-tight whitespace-nowrap truncate">DSuite</span>
                        </div>
                        <button
                            type="button"
                            onClick={() => setIsSidebarOpen(false)}
                            className="p-2 rounded-md text-app-border hover:text-app-bg-card hover:bg-app-text-label transition-colors"
                            aria-label="Close menu"
                        >
                            <X className="w-4 h-4" />
                        </button>
                    </div>
                </div>

                <div className="flex-1 overflow-y-auto px-4 py-6 custom-scrollbar">
                    {canAccess('/new-project') && (
                        <div className="mb-6">
                            <button
                                onClick={() => setShowNewProjectModal(true)}
                                className="flex items-center w-full px-4 py-3 text-sm font-bold text-white bg-app-primary rounded-lg hover:bg-app-primary-hover shadow-lg shadow-app-primary-dark/20 transition-all active:scale-95"
                            >
                                <Plus className="w-5 h-5 mr-2" />
                                New Project
                            </button>
                        </div>
                    )}

                    <div className="mb-6">
                        <div className="flex items-center justify-between mb-3 px-2">
                            <h3 className="text-xs font-semibold text-app-text-muted uppercase tracking-wider">
                                All Projects
                            </h3>
                        </div>
                        <div className="space-y-1">
                            {projects.length === 0 ? (
                                <p className="text-xs text-app-text-label px-2 italic">No projects yet.</p>
                            ) : (
                                projects.map((project) => {
                                    const canDelete = Boolean(project.projectToken || project.governanceResultId);
                                    return (
                                        <div key={project.key || project.project_token} className="flex items-center gap-1">
                                            <button
                                                onClick={() => handleSelectProject(project)}
                                                className={`flex-1 flex items-center px-2 py-2 text-sm font-medium rounded-md group transition-all text-left border ${selectedProjectKey === project.key ? 'bg-app-primary-dark/40 text-app-primary-light border-app-primary-dark' : 'border-transparent text-app-text-light hover:bg-app-text-label hover:text-app-bg-card'}
                                                `}
                                                title={project.name}
                                            >
                                                {project.type === 'share' ? (
                                                    <Share2 className={`w-4 h-4 mr-3 flex-shrink-0 transition-colors ${selectedProjectKey === project.key ? 'text-purple-400' : 'text-app-text-label group-hover:text-purple-400'}`} />
                                                ) : (
                                                    <History className={`w-4 h-4 mr-3 flex-shrink-0 transition-colors ${selectedProjectKey === project.key ? 'text-blue-400' : 'text-app-text-label group-hover:text-blue-400'}`} />
                                                )}
                                                <div className="min-w-0">
                                                    <p className="truncate">{project.name}</p>
                                                    <p className="text-[11px] text-app-text-muted truncate">
                                                        {project.type === 'standard' && project.status === 'analysis_complete'
                                                            ? `Locked - ${getProjectSidebarSubtitle(project)}`
                                                            : getProjectSidebarSubtitle(project)}
                                                    </p>
                                                </div>
                                            </button>
                                            {typeof handleDeleteProject === 'function' && canDelete && (
                                                <button
                                                    type="button"
                                                    onClick={() => handleDeleteProject(project)}
                                                    disabled={deletingProjectKey === project.key}
                                                    className={`p-2 rounded-md border transition-colors ${deletingProjectKey === project.key ? 'text-app-text-muted border-app-text-label cursor-not-allowed' : 'text-red-400 border-transparent hover:text-red-300 hover:bg-app-status-error/10'}`}
                                                    title={deletingProjectKey === project.key ? 'Deleting project...' : `Delete ${project.name || 'project'}`}
                                                    aria-label={`Delete ${project.name || 'project'}`}
                                                >
                                                    <Trash2 className="w-4 h-4" />
                                                </button>
                                            )}
                                        </div>
                                    );
                                })
                            )}
                        </div>
                    </div>
                </div>

                <div className="border-t border-app-sidebar-bg bg-app-sidebar-bg shrink-0">
                    <button
                        type="button"
                        onClick={() => setNavExpanded((v) => !v)}
                        className="flex items-center justify-between w-full px-4 py-3 text-xs font-semibold text-app-text-muted uppercase tracking-wider hover:text-white transition-colors"
                    >
                        <span>Navigation</span>
                        <svg
                            className={`w-3 h-3 transition-transform duration-200 ${navExpanded ? 'rotate-180' : ''}`}
                            fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}
                        >
                            <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
                        </svg>
                    </button>
                    <div className={`overflow-hidden transition-all duration-300 ease-in-out ${navExpanded ? 'max-h-96 opacity-100' : 'max-h-0 opacity-0'}`}>
                        <div className="px-4 pb-4">
                            {canAccess('/status-dashboard') && (
                                <button
                                    onClick={() => setCurrentView('statusDashboard')}
                                    className={`flex items-center w-full px-4 py-2 text-sm font-medium rounded-md transition-colors mb-2 ${currentView === 'statusDashboard'
                                        ? 'bg-app-primary-dark/40 text-app-primary-light border border-app-primary-dark'
                                        : `${isDarkMode ? 'text-app-text-label' : 'text-app-border'} hover:bg-app-text-label hover:text-white`}`}
                                >
                                    <Activity className="w-4 h-4 mr-3" />
                                    Status Dashboard
                                </button>
                            )}

                            {/* Billing page - Hidden until implementation is complete */}
                            {/* {canAccess('/billing') && (
                                <button onClick={() => {
                                    navigate('/billing');
                                }}
                                    className={`flex items-center w-full px-4 py-2 text-sm font-medium rounded-md transition-colors mb-2 ${location.pathname.startsWith('/billing')
                                        ? 'bg-app-primary-dark/40 text-blue-100 border border-app-primary-dark'
                                        : `${isDarkMode ? 'text-app-text-label' : 'text-app-border'} hover:bg-app-text-label hover:text-white`
                                        }`}
                                >
                                    <CreditCard className='w-4 h-4 mr-3' />
                                    Check Billing Details
                                </button>
                            )} */}

                            {user?.is_org_admin && canAccess('/organization-admin') && (
                                <button
                                    onClick={() => {
                                        setCurrentView('organizationAdmin');
                                    }}
                                    className={`flex items-center w-full px-4 py-2 text-sm font-medium rounded-md transition-colors mb-2 ${currentView === 'organizationAdmin'
                                        ? 'bg-app-primary-dark/40 text-blue-100 border border-app-primary-dark'
                                        : `${isDarkMode ? 'text-app-text-label' : 'text-app-border'} hover:bg-app-text-label hover:text-white`}`}
                                >
                                    <ShieldCheck className="w-4 h-4 mr-3" />
                                    Organization Admin
                                </button>
                            )}
                            {user?.is_org_admin && (
                                <button
                                    onClick={() => {
                                        navigate('/billing');
                                    }}
                                    className={`flex items-center w-full px-4 py-2 text-sm font-medium rounded-md transition-colors mb-2 ${location.pathname === '/billing'
                                        ? 'bg-app-primary-dark/40 text-blue-100 border border-app-primary-dark'
                                        : `${isDarkMode ? 'text-app-text-label' : 'text-app-border'} hover:bg-app-text-label hover:text-white`}`}
                                >
                                    <CreditCard className="w-4 h-4 mr-3" />
                                    Billing & Activity
                                </button>
                            )}
                            {user?.is_org_admin && canAccess('/governance-management') && (
                                <button
                                    onClick={() => {
                                        navigate('/governance-management');
                                    }}
                                    className={`flex items-center w-full px-4 py-2 text-sm font-medium rounded-md transition-colors mb-2 ${location.pathname === '/governance-management'
                                        ? 'bg-app-primary-dark/40 text-blue-100 border border-app-primary-dark'
                                        : `${isDarkMode ? 'text-app-text-label' : 'text-app-border'} hover:bg-app-text-label hover:text-white`}`}
                                >
                                    <FileCheck className="w-4 h-4 mr-3" />
                                    Governance
                                </button>
                            )}
                            {canAccess('/agents') && (
                                <button
                                    onClick={() => {
                                        navigate('/agents');
                                    }}
                                    className={`flex items-center w-full px-4 py-2 text-sm font-medium rounded-md transition-colors mb-2 ${location.pathname.startsWith('/agents')
                                        ? 'bg-app-primary-dark/40 text-blue-100 border border-app-primary-dark'
                                        : `${isDarkMode ? 'text-app-text-label' : 'text-app-border'} hover:bg-app-text-label hover:text-white`}`}
                                >
                                    <Users className="w-4 h-4 mr-3" />
                                    Agents
                                </button>
                            )}
                            {canAccess('/plugins') && (
                                <button
                                    onClick={() => {
                                        navigate('/plugins');
                                    }}
                                    className={`flex items-center w-full px-4 py-2 text-sm font-medium rounded-md transition-colors mb-2 ${location.pathname.startsWith('/plugins')
                                        ? 'bg-app-primary-dark/40 text-blue-100 border border-app-primary-dark'
                                        : `${isDarkMode ? 'text-app-text-label' : 'text-app-border'} hover:bg-app-text-label hover:text-white`}`}
                                >
                                    <Globe className="w-4 h-4 mr-3" />
                                    Plugins
                                </button>
                            )}
                            {/* <button
                                onClick={() => setShowSettings(true)}
                                className={`flex items-center w-full px-4 py-2 text-sm font-medium rounded-md hover:bg-app-text-label hover:text-white transition-colors mb-2 ${isDarkMode ? 'text-app-text-label' : 'text-app-border'}`}
                            >
                                <Settings className="w-4 h-4 mr-3" />
                                Settings
                            </button> */}
                            {user && (
                                <div className={`flex items-center w-full px-4 py-2 text-sm font-medium rounded-md hover:bg-app-text-label transition-colors justify-between bg-white/5 border border-white/10 ${isDarkMode ? 'text-app-text-label' : 'text-app-border'}`}>
                                    <div className="flex items-center overflow-hidden">
                                        <User className="w-4 h-4 mr-3 flex-shrink-0" />
                                        <span className="truncate w-24 text-xs" title={user.email}>{user.email}</span>
                                    </div>
                                    <button onClick={handleLogout} className="text-red-400 hover:text-red-300 p-1" title="Logout">
                                        <LogOut className="w-4 h-4" />
                                    </button>
                                </div>
                            )}


                        </div>
                    </div>
                </div>
            </div>

            {/* Modals - Rendered outside sidebar to appear centered on screen */}
            <NewProjectModal
                isOpen={showNewProjectModal}
                onClose={() => setShowNewProjectModal(false)}
                onStartWithBRD={() => {
                    setShowNewProjectModal(false);
                    if (handleNewProject) {
                        handleNewProject();
                    } else {
                        navigate('/new-project');
                    }
                }}
                onShareDocument={() => {
                    navigate('/share-doc?create=true');
                    setShowNewProjectModal(false);
                }}
            />

            <ShareDocumentModal
                isOpen={showShareDocumentModal}
                onClose={() => setShowShareDocumentModal(false)}
            />
        </>
    );
}
