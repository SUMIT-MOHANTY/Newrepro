import React, { useState, useEffect } from 'react';
import { useNavigate, useLocation, useSearchParams } from 'react-router-dom';
import { X, Plus, Share2, History, Trash2, Activity, ShieldCheck, FileCheck, Users, CreditCard, Coins, Globe, LifeBuoy, User, LogOut } from 'lucide-react';
import dsuiteLogo from '../assets/DSuite Gradient Ribbon Logo.png';
import dsuiteLogoWhite from '../assets/DSuite Gradient Ribbon Logo White.png';
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
    // Support tickets unread state
    const [unreadTicketsCount, setUnreadTicketsCount] = useState(0);

    // Agents state
    const [agents, setAgents] = useState([]);
    const [agentsLoading, setAgentsLoading] = useState(false);
    const [agentsError, setAgentsError] = useState(null);
    const [agentsExpanded, setAgentsExpanded] = useState(false);

    const [showNewProjectModal, setShowNewProjectModal] = useState(false);
    const [showShareDocumentModal, setShowShareDocumentModal] = useState(false);

    useEffect(() => {
        const token = localStorage.getItem('token');
        if (!token) return;

        const fetchUnread = async () => {
            try {
                const res = await fetch(API_ENDPOINTS.SUPPORT_TICKET_UNREAD, {
                    headers: { Authorization: `Bearer ${token}` }
                });
                if (res.ok) {
                    const data = await res.json();
                    setUnreadTicketsCount(data.unread_count || 0);
                }
            } catch {
                // silent
            }
        };

        fetchUnread();
        const handleUnreadSync = () => fetchUnread();
        window.addEventListener('dsuite-ticket-unread-sync', handleUnreadSync);
        const interval = setInterval(fetchUnread, 120000); // Relaxed background check
        return () => {
            clearInterval(interval);
            window.removeEventListener('dsuite-ticket-unread-sync', handleUnreadSync);
        };
    }, [location.pathname]);

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

    const isSuperAdmin = user?.is_super_admin === true || rbac?.role_name === 'Super Admin' || localStorage.getItem('is_super_admin') === 'true';

    const canAccess = (path) => {
        if (!path) return true;
        if (isSuperAdmin) return true;
        if (rbac?.is_org_admin) return true;
        if (path === '/tickets' || path.startsWith('/tickets') || path === '/superadmin/tickets' || path === '/docs') return true;
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
                        <div 
                            className="flex items-center min-w-0 cursor-pointer select-none"
                            onClick={() => navigate('/dashboard')}
                        >
                            <img
                                src={dsuiteLogoWhite}
                                alt="DSuite.Pro Logo"
                                className="h-7 w-auto object-contain shrink-0"
                            />
                            <span className="text-[15px] font-extrabold tracking-tight -ml-1 text-transparent bg-clip-text bg-gradient-to-r from-sky-400 to-cyan-300 select-none">
                                .Pro
                            </span>
                        </div>
                        <button
                            type="button"
                            onClick={() => setIsSidebarOpen(false)}
                            className="p-2 rounded-md text-slate-400 hover:text-white hover:bg-white/10 transition-colors"
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
                                    // Only project owner or org admin can delete
                                    const isOwner = user && project.owner_id && Number(project.owner_id) === Number(user.id);
                                    const isAdmin = user?.is_org_admin === true;
                                    const hasToken = Boolean(project.projectToken || project.governanceResultId);
                                    const canDelete = hasToken && (isOwner || isAdmin);
                                    return (
                                        <div key={project.key || project.project_token} className="flex items-center gap-1 w-full min-w-0">
                                            <button
                                                onClick={() => handleSelectProject(project)}
                                                className={`flex-1 min-w-0 flex items-center px-2.5 py-2 text-sm font-medium rounded-lg group transition-all text-left border ${selectedProjectKey === project.key 
                                                    ? 'bg-blue-600/25 text-blue-200 border-blue-500/50 shadow-sm' 
                                                    : 'border-transparent text-slate-300 hover:bg-white/10 hover:text-white'
                                                }`}
                                                title={project.name}
                                            >
                                                {project.type === 'share' ? (
                                                    <Share2 className={`w-4 h-4 mr-3 flex-shrink-0 transition-colors ${selectedProjectKey === project.key ? 'text-purple-400' : 'text-slate-400 group-hover:text-purple-400'}`} />
                                                ) : (
                                                    <History className={`w-4 h-4 mr-3 flex-shrink-0 transition-colors ${selectedProjectKey === project.key ? 'text-blue-400' : 'text-slate-400 group-hover:text-blue-400'}`} />
                                                )}
                                                <div className="min-w-0 flex-1">
                                                    <p className="truncate font-semibold">{project.name}</p>
                                                    <p className={`text-[11px] truncate ${selectedProjectKey === project.key ? 'text-blue-300/80' : 'text-slate-400'}`}>
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
                                                    className={`flex-shrink-0 p-2 rounded-md border transition-colors ${deletingProjectKey === project.key ? 'text-slate-500 border-slate-700 cursor-not-allowed' : 'text-red-400 border-transparent hover:text-red-300 hover:bg-red-500/15'}`}
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

                    {/* Navigation Section */}
                    <div className="border-t border-white/10 pt-4 mt-6">
                        <button
                            type="button"
                            onClick={() => setNavExpanded((v) => !v)}
                            className="flex items-center justify-between w-full px-2 py-2 text-xs font-semibold text-slate-400 uppercase tracking-wider hover:text-white transition-colors cursor-pointer rounded-lg hover:bg-white/5"
                        >
                            <span>Navigation</span>
                            <svg
                                className={`w-3 h-3 transition-transform duration-200 ${navExpanded ? 'rotate-180' : ''}`}
                                fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}
                            >
                                <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
                            </svg>
                        </button>
                        <div className={`transition-all duration-300 ease-in-out ${navExpanded ? 'block opacity-100 mt-2' : 'hidden opacity-0'}`}>
                            <div className="space-y-1">
                                {canAccess('/status-dashboard') && (
                                    <button
                                        onClick={() => setCurrentView('statusDashboard')}
                                        className={`flex items-center w-full px-3.5 py-2 text-sm font-medium rounded-lg transition-all mb-1 cursor-pointer ${currentView === 'statusDashboard'
                                            ? 'bg-blue-600/25 text-blue-200 border border-blue-500/50 shadow-sm'
                                            : 'text-slate-300 hover:bg-white/10 hover:text-white'}`}
                                    >
                                        <Activity className="w-4 h-4 mr-3 text-blue-400" />
                                        Status Dashboard
                                    </button>
                                )}

                                {user?.is_org_admin && canAccess('/organization-admin') && (
                                    <button
                                        onClick={() => {
                                            setCurrentView('organizationAdmin');
                                        }}
                                        className={`flex items-center w-full px-3.5 py-2 text-sm font-medium rounded-lg transition-all mb-1 cursor-pointer ${currentView === 'organizationAdmin'
                                            ? 'bg-blue-600/25 text-blue-200 border border-blue-500/50 shadow-sm'
                                            : 'text-slate-300 hover:bg-white/10 hover:text-white'}`}
                                    >
                                        <ShieldCheck className="w-4 h-4 mr-3 text-emerald-400" />
                                        Organization Admin
                                    </button>
                                )}

                                {/* Super Admin Nav Section */}
                                {isSuperAdmin && (
                                    <div className="my-3 pt-3 border-t border-purple-500/20">
                                        <p className="px-2 mb-2 text-[10px] font-bold text-purple-400 uppercase tracking-wider">Super Admin</p>
                                        <button
                                            onClick={() => navigate('/superadmin/dashboard')}
                                            className={`flex items-center w-full px-4 py-2 text-sm font-medium rounded-md transition-colors mb-1.5 ${location.pathname === '/superadmin/dashboard' ? 'bg-purple-600/30 text-purple-200 border border-purple-500/40' : 'text-purple-300 hover:bg-purple-900/30'}`}
                                        >
                                            <ShieldCheck className="w-4 h-4 mr-3 text-purple-400" />
                                            Dashboard
                                        </button>
                                        <button
                                            onClick={() => navigate('/superadmin/requests')}
                                            className={`flex items-center w-full px-4 py-2 text-sm font-medium rounded-md transition-colors mb-1.5 ${location.pathname === '/superadmin/requests' ? 'bg-purple-600/30 text-purple-200 border border-purple-500/40' : 'text-purple-300 hover:bg-purple-900/30'}`}
                                        >
                                            <FileCheck className="w-4 h-4 mr-3 text-purple-400" />
                                            Agent Capacity Requests
                                        </button>
                                        <button
                                            onClick={() => navigate('/superadmin/organizations')}
                                            className={`flex items-center w-full px-4 py-2 text-sm font-medium rounded-md transition-colors mb-1.5 ${location.pathname === '/superadmin/organizations' ? 'bg-purple-600/30 text-purple-200 border border-purple-500/40' : 'text-purple-300 hover:bg-purple-900/30'}`}
                                        >
                                            <Users className="w-4 h-4 mr-3 text-purple-400" />
                                            Organizations
                                        </button>
                                        <button
                                            onClick={() => navigate('/superadmin/global-billing')}
                                            className={`flex items-center w-full px-4 py-2 text-sm font-medium rounded-md transition-colors mb-1.5 ${location.pathname === '/superadmin/global-billing' ? 'bg-purple-600/30 text-purple-200 border border-purple-500/40' : 'text-purple-300 hover:bg-purple-900/30'}`}
                                        >
                                            <CreditCard className="w-4 h-4 mr-3 text-purple-400" />
                                            Global Billing Dashboard
                                        </button>
                                        <button
                                            onClick={() => navigate('/superadmin/tokenops')}
                                            className={`flex items-center w-full px-4 py-2 text-sm font-medium rounded-md transition-colors mb-1.5 ${location.pathname === '/superadmin/tokenops' ? 'bg-purple-600/30 text-purple-200 border border-purple-500/40' : 'text-purple-300 hover:bg-purple-900/30'}`}
                                        >
                                            <Coins className="w-4 h-4 mr-3 text-purple-400" />
                                            TokenOps Hub
                                        </button>
                                        <button
                                            onClick={() => navigate('/superadmin/roles')}
                                            className={`flex items-center w-full px-4 py-2 text-sm font-medium rounded-md transition-colors mb-1.5 ${location.pathname === '/superadmin/roles' ? 'bg-purple-600/30 text-purple-200 border border-purple-500/40' : 'text-purple-300 hover:bg-purple-900/30'}`}
                                        >
                                            <ShieldCheck className="w-4 h-4 mr-3 text-purple-400" />
                                            Roles & Permissions
                                        </button>
                                        <button
                                            onClick={() => navigate('/superadmin/logs')}
                                            className={`flex items-center w-full px-4 py-2 text-sm font-medium rounded-md transition-colors mb-1.5 ${location.pathname === '/superadmin/logs' ? 'bg-purple-600/30 text-purple-200 border border-purple-500/40' : 'text-purple-300 hover:bg-purple-900/30'}`}
                                        >
                                            <Activity className="w-4 h-4 mr-3 text-purple-400" />
                                            Audit Logs
                                        </button>
                                    </div>
                                )}
                                {(user?.is_org_admin || canAccess('/billing')) && (
                                    <button
                                        onClick={() => {
                                            navigate('/billing');
                                        }}
                                        className={`flex items-center w-full px-3.5 py-2 text-sm font-medium rounded-lg transition-all mb-1 cursor-pointer ${location.pathname === '/billing'
                                            ? 'bg-blue-600/25 text-blue-200 border border-blue-500/50 shadow-sm'
                                            : 'text-slate-300 hover:bg-white/10 hover:text-white'}`}
                                    >
                                        <CreditCard className="w-4 h-4 mr-3 text-amber-400" />
                                        Billing & Activity
                                    </button>
                                )}
                                {canAccess('/governance-management') && (
                                    <button
                                        onClick={() => {
                                            navigate('/governance-management');
                                        }}
                                        className={`flex items-center w-full px-3.5 py-2 text-sm font-medium rounded-lg transition-all mb-1 cursor-pointer ${location.pathname === '/governance-management'
                                            ? 'bg-blue-600/25 text-blue-200 border border-blue-500/50 shadow-sm'
                                            : 'text-slate-300 hover:bg-white/10 hover:text-white'}`}
                                    >
                                        <FileCheck className="w-4 h-4 mr-3 text-indigo-400" />
                                        Governance
                                    </button>
                                )}
                                {canAccess('/agents') && (
                                    <button
                                        onClick={() => {
                                            navigate('/agents');
                                        }}
                                        className={`flex items-center w-full px-3.5 py-2 text-sm font-medium rounded-lg transition-all mb-1 cursor-pointer ${location.pathname.startsWith('/agents')
                                            ? 'bg-blue-600/25 text-blue-200 border border-blue-500/50 shadow-sm'
                                            : 'text-slate-300 hover:bg-white/10 hover:text-white'}`}
                                    >
                                        <Users className="w-4 h-4 mr-3 text-sky-400" />
                                        Agents
                                    </button>
                                )}
                                {canAccess('/plugins') && (
                                    <button
                                        onClick={() => {
                                            navigate('/plugins');
                                        }}
                                        className={`flex items-center w-full px-3.5 py-2 text-sm font-medium rounded-lg transition-all mb-1 cursor-pointer ${location.pathname.startsWith('/plugins')
                                            ? 'bg-blue-600/25 text-blue-200 border border-blue-500/50 shadow-sm'
                                            : 'text-slate-300 hover:bg-white/10 hover:text-white'}`}
                                    >
                                        <Globe className="w-4 h-4 mr-3 text-purple-400" />
                                        Plugins
                                    </button>
                                )}

                                {/* Support Tickets - Cleanly positioned as the last navigation item */}
                                <button
                                    onClick={() => {
                                        navigate('/tickets');
                                    }}
                                    className={`flex items-center justify-between w-full px-3.5 py-2 text-sm font-medium rounded-lg transition-all mb-1 cursor-pointer ${location.pathname === '/tickets' || location.pathname === '/superadmin/tickets'
                                        ? 'bg-purple-600/25 text-purple-200 border border-purple-500/50 shadow-sm'
                                        : 'text-slate-300 hover:bg-white/10 hover:text-white'}`}
                                >
                                    <div className="flex items-center min-w-0">
                                        <LifeBuoy className="w-4 h-4 mr-3 text-pink-400 flex-shrink-0" />
                                        <span className="truncate">Support Tickets</span>
                                    </div>
                                    {unreadTicketsCount > 0 && (
                                        <span className="px-1.5 py-0.5 text-[10px] font-extrabold rounded-full bg-rose-500 text-white shadow-sm shadow-rose-500/50 animate-pulse">
                                            {unreadTicketsCount}
                                        </span>
                                    )}
                                </button>
                            </div>
                        </div>
                    </div>
                </div>

                {user && (
                    <div className="p-3 border-t border-white/10 bg-app-sidebar-bg shrink-0">
                        <div className="flex items-center w-full px-3 py-2 text-sm font-medium rounded-lg bg-white/5 border border-white/10 text-slate-200">
                            <div className="flex items-center min-w-0 flex-1 mr-2">
                                <User className="w-4 h-4 mr-2 text-purple-400 flex-shrink-0" />
                                <span className="truncate text-xs font-semibold text-slate-200" title={user.email}>{user.email}</span>
                            </div>
                            <button 
                                onClick={handleLogout} 
                                className="text-red-400 hover:text-red-300 hover:bg-red-500/10 p-1.5 rounded-md transition-colors shrink-0 flex items-center" 
                                title="Logout"
                            >
                                <LogOut className="w-4 h-4" />
                            </button>
                        </div>
                    </div>
                )}
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
