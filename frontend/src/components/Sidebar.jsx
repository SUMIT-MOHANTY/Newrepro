import React from 'react';
import { X, Plus, History, Activity, Settings, User, LogOut, ShieldCheck } from 'lucide-react';
import bourntecLogo from '../assets/bourntec_logo.png';

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
    handleLogout
}) {
    return (
        <>
            {/* Mobile Overlay */}
            {isSidebarOpen && (
                <button
                    type="button"
                    aria-label="Close sidebar"
                    onClick={() => setIsSidebarOpen(false)}
                    className="fixed inset-0 z-30 bg-black/40 transition-opacity duration-300 ease-in-out md:hidden"
                />
            )}

            {/* Main Desktop Spacer to push the layout smoothly without squishing the sidebar content */}
            <div className={`hidden md:block transition-[width] duration-300 ease-in-out flex-shrink-0 ${isSidebarOpen ? 'w-72' : 'w-0'}`} />

            {/* Animated Sidebar */}
            <div
                className={`fixed inset-y-0 left-0 z-40 w-72 bg-app-text-main border-r border-gray-800 flex flex-col text-app-border shadow-xl transition-transform duration-300 ease-in-out ${isSidebarOpen ? 'translate-x-0' : '-translate-x-full'
                    }`}
            >
                {/* Header */}
                <div className="h-16 flex items-center px-2 border-b border-gray-800 bg-app-text-main shrink-0">
                    <div className="flex items-center justify-between w-full">
                        <div className="flex items-center min-w-0">
                            <img src={bourntecLogo} alt="App Logo" className="h-5 w-auto object-contain shrink-0" />
                            <div className="h-5 w-0.5 bg-app-bg-card mx-3 shrink-0 rounded-full"></div>
                            <span className="text-sm font-bold text-white tracking-tight whitespace-nowrap truncate">DSuite</span>
                        </div>
                        <button
                            type="button"
                            onClick={() => setIsSidebarOpen(false)}
                            className="p-2 rounded-md text-app-border hover:text-white hover:bg-app-text-label transition-colors"
                            aria-label="Close menu"
                        >
                            <X className="w-4 h-4" />
                        </button>
                    </div>
                </div>

                {/* Main scrollable area */}
                <div className="flex-1 overflow-y-auto px-4 py-6 custom-scrollbar">
                    <button
                        onClick={handleNewProject}
                        className="flex items-center w-full px-4 py-3 mb-6 text-sm font-bold text-white bg-app-primary rounded-lg hover:bg-app-primary-hover shadow-lg shadow-blue-900/20 transition-all active:scale-95"
                    >
                        <Plus className="w-5 h-5 mr-2" />
                        New Project
                    </button>

                    <div className="mb-6">
                        <h3 className="text-xs font-semibold text-app-text-muted uppercase tracking-wider mb-3 px-2">Projects</h3>
                        <div className="space-y-1">
                            {projects.length === 0 ? (
                                <p className="text-xs text-app-text-label px-2 italic">No projects yet.</p>
                            ) : (
                                projects.map((project) => (
                                    <button
                                        key={project.key}
                                        onClick={() => handleSelectProject(project)}
                                        className={`w-full flex items-center px-2 py-2 text-sm font-medium rounded-md group transition-all text-left border ${selectedProjectKey === project.key && currentView === 'main'
                                            ? 'bg-blue-900/40 text-blue-100 border-blue-800'
                                            : 'border-transparent text-app-text-light hover:bg-app-text-label hover:text-white'
                                            }`}
                                        title={project.name}
                                    >
                                        <History className={`w-4 h-4 mr-3 flex-shrink-0 transition-colors ${selectedProjectKey === project.key && currentView === 'main' ? 'text-blue-400' : 'text-app-text-label group-hover:text-blue-400'}`} />
                                        <div className="min-w-0">
                                            <p className="truncate">{project.name}</p>
                                            <p className="text-[11px] text-app-text-muted truncate">
                                                {project.status === 'analysis_complete'
                                                    ? `Locked • ${getProjectSidebarSubtitle(project)}`
                                                    : getProjectSidebarSubtitle(project)}
                                            </p>
                                        </div>
                                    </button>
                                ))
                            )}
                        </div>
                    </div>
                </div>

                {/* Footer area */}
                <div className="p-4 border-t border-gray-800 bg-app-text-main shrink-0">
                    <button
                        onClick={() => {
                            setCurrentView('statusDashboard');
                        }}
                        className={`flex items-center w-full px-4 py-2 text-sm font-medium rounded-md transition-colors mb-2 ${currentView === 'statusDashboard' ? 'bg-blue-900/40 text-blue-100 border border-blue-800' : 'text-app-border hover:bg-app-text-label hover:text-white'
                            }`}
                    >
                        <Activity className="w-4 h-4 mr-3" />
                        Status Dashboard
                    </button>
                    {user?.is_org_admin && (
                        <button
                            onClick={() => {
                                setCurrentView('organizationAdmin');
                            }}
                            className={`flex items-center w-full px-4 py-2 text-sm font-medium rounded-md transition-colors mb-2 ${currentView === 'organizationAdmin' ? 'bg-indigo-900/40 text-indigo-100 border border-indigo-800' : 'text-app-border hover:bg-app-text-label hover:text-white'
                                }`}
                        >
                            <ShieldCheck className="w-4 h-4 mr-3" />
                            Organization Admin
                        </button>
                    )}
                    <button
                        onClick={() => {
                            setShowSettings(true);
                        }}
                        className="flex items-center w-full px-4 py-2 text-sm font-medium text-app-border rounded-md hover:bg-app-text-label hover:text-white transition-colors mb-2"
                    >
                        <Settings className="w-4 h-4 mr-3" />
                        Settings
                    </button>
                    {user && (
                        <div className="flex items-center w-full px-4 py-2 text-sm font-medium text-app-border rounded-md hover:bg-app-text-label transition-colors justify-between bg-app-text-label/50">
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
        </>
    );
}
