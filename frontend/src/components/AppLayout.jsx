import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { API_ENDPOINTS } from '../config';
import { clearAuthData } from '../utils/auth';
import { Menu, Settings } from 'lucide-react';
import Sidebar from './Sidebar';

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

    const currentView = location.pathname === '/status-dashboard' ? 'statusDashboard'
        : location.pathname === '/governance' ? 'governance'
            : 'main';

    const setCurrentView = useCallback((view) => {
        if (view === 'statusDashboard') {
            navigate('/status-dashboard');
        } else if (view === 'governance') {
            navigate('/governance');
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

    // Fetch projects for sidebar
    const fetchProjects = useCallback(async () => {
        try {
            const token = localStorage.getItem('token');
            // Fetch governance history
            const govRes = await fetch(API_ENDPOINTS.GOVERNANCE_HISTORY, {
                headers: { Authorization: `Bearer ${token}` }
            });
            if (govRes.status === 401) { handleLogout(); return; }
            const govPayload = govRes.ok ? await govRes.json() : {};
            const submissions = Array.isArray(govPayload?.submissions) ? govPayload.submissions : [];

            // Fetch document history
            const histRes = await fetch(API_ENDPOINTS.HISTORY, {
                headers: { Authorization: `Bearer ${token}` }
            });
            if (histRes.status === 401) { handleLogout(); return; }
            const history = histRes.ok ? await histRes.json() : [];

            // Build project map
            const normalizeProjectName = (name) =>
                String(name || '').trim().toLowerCase().replace(/\s+/g, ' ');

            const projectMap = new Map();

            submissions.forEach((sub) => {
                const key = sub.project_token || String(sub.id);
                projectMap.set(key, {
                    key,
                    governanceResultId: sub.id,
                    projectToken: sub.project_token,
                    name: sub.project_name || `Project #${sub.id}`,
                    classification: sub.classification || 'N/A',
                    weightedScore: sub.weighted_score ?? null,
                    submissionDate: sub.submission_date || null,
                    documents: [],
                    latestDocument: null,
                    latestRevision: 0,
                    status: 'ready_for_upload',
                    pendingRevisionReason: sub.pending_revision_reason || null,
                });
            });

            (Array.isArray(history) ? history : []).forEach((doc) => {
                let parsedAnalysis = null;
                try { parsedAnalysis = doc?.analysis_result ? JSON.parse(doc.analysis_result) : null; } catch { /* ignore */ }

                const meta = parsedAnalysis?.projectMeta || {};
                const govMeta = parsedAnalysis?.governanceContext || {};
                const projectName = meta.project_name || govMeta.project_name || 'Unassigned Project';
                const governanceResultId = meta.governance_result_id || govMeta.result_id || null;
                const projectToken = meta.project_token || govMeta.project_token || null;

                let targetKey = projectToken || null;
                if (!targetKey || !projectMap.has(targetKey)) {
                    const byId = governanceResultId
                        ? Array.from(projectMap.values()).find(p => p.governanceResultId === governanceResultId)
                        : null;
                    if (byId) targetKey = byId.key;
                }
                if (!targetKey || !projectMap.has(targetKey)) {
                    const byName = Array.from(projectMap.values()).find(
                        p => normalizeProjectName(p.name) === normalizeProjectName(projectName)
                    );
                    if (byName) targetKey = byName.key;
                }
                if (!targetKey || !projectMap.has(targetKey)) {
                    targetKey = projectToken || (governanceResultId ? String(governanceResultId) : `doc-${doc.id}`);
                    if (!projectMap.has(targetKey)) {
                        projectMap.set(targetKey, {
                            key: targetKey, governanceResultId: governanceResultId, projectToken,
                            name: projectName, classification: 'N/A', weightedScore: null,
                            submissionDate: null, documents: [], latestDocument: null,
                            latestRevision: 0, status: 'ready_for_upload',
                        });
                    }
                }
                const project = projectMap.get(targetKey);
                project.documents.push(doc);
                if (!project.latestDocument) project.latestDocument = doc;
            });

            const builtProjects = Array.from(projectMap.values())
                .map(project => {
                    const docs = [...project.documents].sort(
                        (a, b) => new Date(b.upload_date || 0).getTime() - new Date(a.upload_date || 0).getTime()
                    );
                    return { ...project, documents: docs, latestDocument: docs[0] || null, latestRevision: docs.length, status: docs.length > 0 ? 'analysis_complete' : 'ready_for_upload' };
                })
                .sort((a, b) => {
                    const aDate = new Date(a.submissionDate || a.latestDocument?.upload_date || 0).getTime();
                    const bDate = new Date(b.submissionDate || b.latestDocument?.upload_date || 0).getTime();
                    return bDate - aDate;
                });

            setProjects(builtProjects);
        } catch (err) {
            console.error('Error fetching projects for layout:', err);
        }
    }, [handleLogout]);

    useEffect(() => {
        const load = async () => { await fetchProjects(); };
        load();
    }, [fetchProjects]);

    const handleNewProject = useCallback(() => {
        setSelectedProjectKey('');
        localStorage.removeItem('governancePassed');
        localStorage.removeItem('governanceResult');
        localStorage.removeItem('governanceContext');
        sessionStorage.removeItem('governanceResult');
        sessionStorage.removeItem('governanceContext');
        navigate('/governance?new=' + Date.now()); // Ensure unique search param to force change
    }, [navigate]);

    const handleSelectProject = (project) => {
        if (!project) return;
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
            <div className="flex items-center justify-center min-h-screen bg-gray-100">
                <div className="text-gray-600">Loading...</div>
            </div>
        );
    }

    const layoutProps = {
        user, isSidebarOpen, setIsSidebarOpen, projects,
        selectedProjectKey, setSelectedProjectKey,
        showSettings, setShowSettings,
        currentView, setCurrentView,
        handleLogout, fetchHistory: fetchProjects,
        handleNewProject, handleSelectProject,
        getProjectSidebarSubtitle,
    };

    return (
        <div className="flex h-screen bg-gray-50 overflow-hidden font-sans">
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

            <div className="flex-1 min-w-0 flex flex-col overflow-hidden relative w-full bg-gray-50 h-full transition-all duration-300 ease-in-out">
                {/* Global Top Navbar */}
                <header className="bg-[#1c355e] text-white px-4 md:px-6 py-3 flex items-center justify-between shadow-md z-20 shrink-0">
                    <div className="flex items-center gap-3 md:gap-4 w-full">
                        {!isSidebarOpen && (
                            <button
                                type="button"
                                onClick={() => setIsSidebarOpen(true)}
                                className="p-1.5 md:p-2 bg-white/10 hover:bg-white/20 rounded-md shadow-sm text-gray-100 hover:text-white transition-colors border border-white/20 cursor-pointer flex-shrink-0"
                                aria-label="Open menu"
                            >
                                <Menu className="w-4 h-4 md:w-5 md:h-5" />
                            </button>
                        )}
                        <div className="flex-1 min-w-0 flex items-center justify-between">
                            <div className="min-w-0 truncate">
                                <h1 className="text-lg md:text-2xl lg:text-3xl font-bold tracking-wide truncate">
                                    {currentView === 'statusDashboard' ? 'Project Status Dashboard' :
                                        currentView === 'governance' ? 'Project Governance' :
                                            'BRD Requirements Analyzer'}
                                </h1>
                                <h2 className="text-[10px] md:text-sm italic text-gray-300 mt-0.5 md:mt-1 truncate">
                                    {currentView === 'statusDashboard' ? 'Epic Hub Assessment Report' :
                                        currentView === 'governance' ? 'Questionnaire & Configuration' :
                                            'Project Insight & AI Assessment'}
                                </h2>
                            </div>

                            {/* Status Pipeline graphic top right - ONLY shown on statusDashboard */}
                            {/* {currentView === 'statusDashboard' && (
                                <div className="text-[9px] md:text-xs font-bold text-gray-700 flex items-center space-x-1.5 bg-white px-2 md:px-3 py-1.5 rounded-full shadow-md border border-gray-100 whitespace-nowrap ml-4 shrink-0 hidden sm:flex">
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
                                className="p-1.5 md:p-2 ml-4 rounded-md text-gray-300 hover:text-white hover:bg-white/10 transition-colors border border-transparent hover:border-white/20 flex-shrink-0"
                                aria-label="Open settings"
                            >
                                <Settings className="w-4 h-4 md:w-5 md:h-5" />
                            </button> */}
                        </div>
                    </div>
                </header>

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
