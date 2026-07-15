import { useState, useEffect, useCallback } from 'react';
import { API_ENDPOINTS } from '../config';

/**
 * GitHubIntegration – A card/inline widget that lets users:
 *  1. Connect / disconnect their GitHub account (OAuth)
 *  2. Browse & select a repository
 *  3. Fetch repo context and surface it for AI analysis
 *
 *  Props:
 *    inline  – if true, renders as a compact button suitable for a tab bar
 */
const GitHubIcon = ({ className = "w-5 h-5" }) => (
    <svg viewBox="0 0 98 96" xmlns="http://www.w3.org/2000/svg" className={className}>
        <path fillRule="evenodd" clipRule="evenodd"
            d="M48.854 0C21.839 0 0 22 0 49.217c0 21.756 13.993 40.172 33.405 46.69 2.427.49 3.316-1.059 3.316-2.362 0-1.141-.08-5.052-.08-9.127-13.59 2.934-16.42-5.867-16.42-5.867-2.184-5.704-5.42-7.17-5.42-7.17-4.448-3.015.324-3.015.324-3.015 4.934.326 7.523 5.052 7.523 5.052 4.367 7.496 11.404 5.378 14.235 4.074.404-3.178 1.699-5.378 3.074-6.6-10.839-1.141-22.243-5.378-22.243-24.283 0-5.378 1.94-9.778 5.014-13.2-.485-1.222-2.184-6.275.486-13.038 0 0 4.125-1.304 13.426 5.052a46.97 46.97 0 0 1 12.214-1.63c4.125 0 8.33.571 12.213 1.63 9.302-6.356 13.427-5.052 13.427-5.052 2.67 6.763.97 11.816.485 13.038 3.155 3.422 5.015 7.822 5.015 13.2 0 18.905-11.404 23.06-22.324 24.283 1.78 1.548 3.316 4.481 3.316 9.126 0 6.6-.08 11.897-.08 13.526 0 1.304.89 2.853 3.316 2.364 19.412-6.52 33.405-24.935 33.405-46.691C97.707 22 75.788 0 48.854 0z"
            fill="currentColor" />
    </svg>
);

const GitHubIntegration = ({ onRepoContextReady, repoContext, onClearRepo, onRepoSelected, inline = false }) => {
    const [connected, setConnected] = useState(false);
    const [githubUsername, setGithubUsername] = useState('');
    const [repos, setRepos] = useState([]);
    const [loadingRepos, setLoadingRepos] = useState(false);
    const [selectedRepo, setSelectedRepo] = useState(null);
    const [fetchingContext, setFetchingContext] = useState(false);
    const [showRepoList, setShowRepoList] = useState(false);
    const [searchFilter, setSearchFilter] = useState('');

    const getToken = () => localStorage.getItem('token');

    // Check GitHub connection on mount
    const checkStatus = useCallback(async () => {
        try {
            const resp = await fetch(API_ENDPOINTS.GITHUB_STATUS, {
                headers: { Authorization: `Bearer ${getToken()}` },
            });
            if (resp.ok) {
                const data = await resp.json();
                setConnected(data.connected);
                setGithubUsername(data.github_username || '');
            }
        } catch (e) {
            console.warn('GitHub status check failed:', e);
        }
    }, []);

    useEffect(() => {
        checkStatus();
    }, [checkStatus]);

    // Connect to GitHub via OAuth
    const handleConnect = async () => {
        try {
            const resp = await fetch(API_ENDPOINTS.GITHUB_AUTH_URL, {
                headers: { Authorization: `Bearer ${getToken()}` },
            });
            if (!resp.ok) throw new Error('Failed to get auth URL');
            const data = await resp.json();
            window.location.href = data.url;
        } catch (e) {
            console.error('GitHub connect error:', e);
        }
    };

    // Disconnect from GitHub
    const handleDisconnect = async () => {
        try {
            await fetch(API_ENDPOINTS.GITHUB_DISCONNECT, {
                method: 'POST',
                headers: { Authorization: `Bearer ${getToken()}` },
            });
            setConnected(false);
            setGithubUsername('');
            setRepos([]);
            setSelectedRepo(null);
            setShowRepoList(false);
            if (onClearRepo) onClearRepo();
        } catch (e) {
            console.error('Disconnect error:', e);
        }
    };

    // Load repos list
    const loadRepos = async () => {
        setLoadingRepos(true);
        try {
            const resp = await fetch(API_ENDPOINTS.GITHUB_REPOS, {
                headers: { Authorization: `Bearer ${getToken()}` },
            });
            if (!resp.ok) throw new Error('Failed to fetch repos');
            const data = await resp.json();
            setRepos(data.repos || []);
            setShowRepoList(true);
        } catch (e) {
            console.error('Load repos error:', e);
        } finally {
            setLoadingRepos(false);
        }
    };

    // Fetch repo context for AI
    const handleSelectRepo = async (repo) => {
        if (onRepoSelected) onRepoSelected(repo);
        setSelectedRepo(repo);
        setShowRepoList(false);
        setFetchingContext(true);
        try {
            const [owner, repoName] = repo.full_name.split('/');
            
            // First validate the connection
            const validateResp = await fetch(API_ENDPOINTS.GIT_VALIDATE_CONNECTION, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    Authorization: `Bearer ${getToken()}`,
                },
                body: JSON.stringify({
                    repo_url: `https://github.com/${repo.full_name}.git`,
                    pat: null, // Using OAuth token from user session
                    provider: 'github',
                }),
            });
            
            if (!validateResp.ok) {
                const errorData = await validateResp.json();
                throw new Error(errorData.detail || 'Failed to validate repository');
            }
            
            // Now fetch the actual context
            const resp = await fetch(API_ENDPOINTS.GITHUB_REPO_CONTEXT, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    Authorization: `Bearer ${getToken()}`,
                },
                body: JSON.stringify({
                    owner,
                    repo: repoName,
                    branch: repo.default_branch || 'main',
                }),
            });
            if (!resp.ok) throw new Error('Failed to build repo context');
            const data = await resp.json();
            if (onRepoContextReady) {
                onRepoContextReady({
                    repo: repo.full_name,
                    branch: repo.default_branch || 'main',
                    context: data.context,
                    language: repo.language,
                    description: repo.description,
                });
            }
        } catch (e) {
            console.error('Repo context error:', e);
            // Show error to user
            alert(`Failed to load repository: ${e.message}`);
        } finally {
            setFetchingContext(false);
        }
    };

    const filteredRepos = repos.filter(r =>
        r.name.toLowerCase().includes(searchFilter.toLowerCase()) ||
        (r.description || '').toLowerCase().includes(searchFilter.toLowerCase())
    );

    /* ═══════════════════════════════════════════════════════
       INLINE MODE — compact button for tab bar
       ═══════════════════════════════════════════════════════ */
    if (inline) {
        // Not connected — show compact "Connect GitHub" button
        if (!connected) {
            return (
                <button
                    type="button"
                    onClick={handleConnect}
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold text-app-text-label bg-app-bg-muted rounded-lg hover:bg-app-bg-hover transition-all active:scale-95 border border-app-border"
                >
                    <GitHubIcon className="w-3.5 h-3.5" />
                    Connect GitHub
                </button>
            );
        }

        // Connected — show username + repo picker
        return (
            <div className="relative">
                <div className="flex items-center gap-1.5">
                    {/* Repo badge or picker trigger */}
                    {selectedRepo ? (
                        <button
                            type="button"
                            onClick={() => { setSelectedRepo(null); if (onClearRepo) onClearRepo(); setShowRepoList(false); }}
                            className="inline-flex items-center gap-1.5 px-2.5 py-1.5 text-xs font-semibold text-app-status-success bg-app-status-successBg rounded-lg border border-emerald-200 hover:bg-app-status-successBg transition-all max-w-[200px]"
                            title={`${selectedRepo.full_name} — click to change`}
                        >
                            {fetchingContext ? (
                                <span className="animate-spin inline-block w-3 h-3 border-2 border-app-status-success border-t-transparent rounded-full"></span>
                            ) : (
                                <GitHubIcon className="w-3.5 h-3.5 text-app-status-success flex-shrink-0" />
                            )}
                            <span className="truncate">{selectedRepo.name}</span>
                            {repoContext && <span className="text-app-status-success flex-shrink-0">✓</span>}
                        </button>
                    ) : (
                        <button
                            type="button"
                            onClick={showRepoList ? () => setShowRepoList(false) : loadRepos}
                            disabled={loadingRepos}
                            className="inline-flex items-center gap-1.5 px-2.5 py-1.5 text-xs font-semibold text-app-text-label bg-app-bg-muted rounded-lg border border-app-border hover:bg-app-bg-hover transition-all disabled:opacity-50"
                        >
                            {loadingRepos ? (
                                <span className="animate-spin inline-block w-3 h-3 border-2 border-app-text-muted border-t-transparent rounded-full"></span>
                            ) : (
                                <GitHubIcon className="w-3.5 h-3.5 flex-shrink-0" />
                            )}
                            <span className="hidden sm:inline">@{githubUsername}</span>
                            <span className="sm:hidden">Repo</span>
                        </button>
                    )}
                    {/* Disconnect */}
                    <button
                        type="button"
                        onClick={handleDisconnect}
                        className="p-1 text-app-text-light hover:text-app-status-error rounded hover:bg-app-status-errorBg transition-colors"
                        title="Disconnect GitHub"
                    >
                        <svg xmlns="http://www.w3.org/2000/svg" className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" /></svg>
                    </button>
                </div>

                {/* Floating repo dropdown */}
                {showRepoList && (
                    <div className="absolute right-0 top-full mt-2 w-80 border border-app-border rounded-xl overflow-hidden bg-app-bg-card shadow-xl z-50">
                        <div className="p-2 border-b border-app-border-light">
                            <input
                                type="text"
                                value={searchFilter}
                                onChange={(e) => setSearchFilter(e.target.value)}
                                placeholder="Search repositories..."
                                className="w-full px-3 py-1.5 text-xs border border-app-border rounded-md focus:ring-1 focus:ring-app-primary focus:border-app-primary bg-app-bg-card"
                                autoFocus
                            />
                        </div>
                        <div className="max-h-56 overflow-y-auto">
                            {filteredRepos.length === 0 ? (
                                <p className="text-xs text-app-text-light p-4 text-center">No repositories found.</p>
                            ) : (
                                filteredRepos.map((repo) => (
                                    <button
                                        key={repo.id}
                                        type="button"
                                        onClick={() => handleSelectRepo(repo)}
                                        className="w-full flex items-center gap-3 px-3 py-2.5 text-left hover:bg-app-primary-light border-b border-app-bg-page last:border-b-0 transition-colors"
                                    >
                                        <svg xmlns="http://www.w3.org/2000/svg" className="w-4 h-4 text-app-text-light flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}><path strokeLinecap="round" strokeLinejoin="round" d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" /></svg>
                                        <div className="min-w-0 flex-1">
                                            <p className="text-xs font-semibold text-app-text-main truncate">{repo.name}</p>
                                            <p className="text-[11px] text-app-text-muted truncate">
                                                {repo.description || 'No description'}
                                                {repo.language && ` • ${repo.language}`}
                                                {repo.private && ' • 🔒'}
                                            </p>
                                        </div>
                                        <span className="text-[10px] text-app-text-light flex-shrink-0">⭐ {repo.stargazers_count}</span>
                                    </button>
                                ))
                            )}
                        </div>
                        <div className="p-2 border-t border-app-border-light text-center">
                            <button type="button" onClick={() => setShowRepoList(false)} className="text-xs text-app-text-muted hover:text-app-text-label font-medium">Cancel</button>
                        </div>
                    </div>
                )}
            </div>
        );
    }

    /* ═══════════════════════════════════════════════════════
       CARD MODE — full-width card (original layout)
       ═══════════════════════════════════════════════════════ */

    // ─── Not Connected ───
    if (!connected) {
        return (
            <div className="rounded-xl border border-app-border bg-app-bg-card p-4 hover:shadow-md transition-shadow">
                <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3">
                        <div className="p-2 bg-app-text-main rounded-lg">
                            <GitHubIcon className="w-5 h-5 text-app-bg-card" />
                        </div>
                        <div>
                            <p className="text-sm font-semibold text-app-text-main">GitHub Repository</p>
                            <p className="text-xs text-app-text-muted">Connect to enhance AI analysis with your codebase</p>
                        </div>
                    </div>
                    <button
                        onClick={handleConnect}
                        className="inline-flex items-center gap-2 px-4 py-2 text-sm font-semibold text-app-bg-card bg-app-text-main rounded-lg hover:bg-app-text-label transition-all active:scale-95 shadow-sm"
                    >
                        <GitHubIcon className="w-4 h-4" />
                        Connect GitHub
                    </button>
                </div>
            </div>
        );
    }

    // ─── Connected ───
    return (
        <div className="rounded-xl border border-app-border bg-app-bg-card p-4 hover:shadow-md transition-shadow">
            {/* Header */}
            <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-3">
                    <div className="p-2 bg-app-text-main rounded-lg relative">
                        <GitHubIcon className="w-5 h-5 text-app-bg-card" />
                        <div className="absolute -bottom-0.5 -right-0.5 w-3 h-3 bg-app-status-success rounded-full border-2 border-app-bg-card"></div>
                    </div>
                    <div>
                        <p className="text-sm font-semibold text-app-text-main">GitHub Connected</p>
                        <p className="text-xs text-app-text-muted">@{githubUsername}</p>
                    </div>
                </div>
                <div className="flex items-center gap-2">
                    {!showRepoList && !selectedRepo && (
                        <button
                            onClick={loadRepos}
                            disabled={loadingRepos}
                            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold text-app-primary-hover bg-app-primary-light rounded-lg hover:bg-app-primary-light transition-all disabled:opacity-50"
                        >
                            {loadingRepos ? (
                                <span className="animate-spin inline-block w-3 h-3 border-2 border-app-primary border-t-transparent rounded-full"></span>
                            ) : (
                                <svg xmlns="http://www.w3.org/2000/svg" className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" /></svg>
                            )}
                            Select Repo
                        </button>
                    )}
                    <button
                        onClick={handleDisconnect}
                        className="p-1.5 text-app-text-light hover:text-app-status-error rounded-md hover:bg-app-status-errorBg transition-colors"
                        title="Disconnect GitHub"
                    >
                        <svg xmlns="http://www.w3.org/2000/svg" className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" /></svg>
                    </button>
                </div>
            </div>

            {/* Selected Repo Badge */}
            {selectedRepo && !showRepoList && (
                <div className="flex items-center justify-between bg-app-status-successBg border border-emerald-200 rounded-lg p-3 mt-2">
                    <div className="flex items-center gap-2 min-w-0">
                        <div className="w-2 h-2 rounded-full bg-app-status-success flex-shrink-0"></div>
                        <div className="min-w-0">
                            <p className="text-xs font-semibold text-emerald-900 truncate">{selectedRepo.full_name}</p>
                            <p className="text-[11px] text-app-status-success">
                                {selectedRepo.language && `${selectedRepo.language} • `}
                                {selectedRepo.default_branch}
                                {repoContext ? ' • Context loaded ✓' : ''}
                            </p>
                        </div>
                    </div>
                    <div className="flex items-center gap-1.5 flex-shrink-0">
                        {fetchingContext && (
                            <span className="animate-spin inline-block w-4 h-4 border-2 border-app-status-success border-t-transparent rounded-full"></span>
                        )}
                        <button
                            onClick={() => { setSelectedRepo(null); if (onClearRepo) onClearRepo(); setShowRepoList(false); }}
                            className="text-xs text-app-status-success hover:text-emerald-900 font-medium"
                        >
                            Change
                        </button>
                    </div>
                </div>
            )}

            {/* Repo List Dropdown */}
            {showRepoList && (
                <div className="mt-2 border border-app-border rounded-lg overflow-hidden bg-app-bg-page">
                    <div className="p-2 border-b border-app-border">
                        <input
                            type="text"
                            value={searchFilter}
                            onChange={(e) => setSearchFilter(e.target.value)}
                            placeholder="Search repositories..."
                            className="w-full px-3 py-1.5 text-xs border border-app-border rounded-md focus:ring-1 focus:ring-app-primary focus:border-app-primary bg-app-bg-card"
                            autoFocus
                        />
                    </div>
                    <div className="max-h-56 overflow-y-auto">
                        {filteredRepos.length === 0 ? (
                            <p className="text-xs text-app-text-light p-4 text-center">No repositories found.</p>
                        ) : (
                            filteredRepos.map((repo) => (
                                <button
                                    key={repo.id}
                                    onClick={() => handleSelectRepo(repo)}
                                    className="w-full flex items-center gap-3 px-3 py-2.5 text-left hover:bg-app-primary-light border-b border-app-border-light last:border-b-0 transition-colors"
                                >
                                    <svg xmlns="http://www.w3.org/2000/svg" className="w-4 h-4 text-app-text-light flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}><path strokeLinecap="round" strokeLinejoin="round" d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" /></svg>
                                    <div className="min-w-0 flex-1">
                                        <p className="text-xs font-semibold text-app-text-main truncate">{repo.name}</p>
                                        <p className="text-[11px] text-app-text-muted truncate">
                                            {repo.description || 'No description'}
                                            {repo.language && ` • ${repo.language}`}
                                            {repo.private && ' • 🔒 Private'}
                                        </p>
                                    </div>
                                    <span className="text-[10px] text-app-text-light flex-shrink-0">⭐ {repo.stargazers_count}</span>
                                </button>
                            ))
                        )}
                    </div>
                    <div className="p-2 border-t border-app-border text-center">
                        <button
                            onClick={() => setShowRepoList(false)}
                            className="text-xs text-app-text-muted hover:text-app-text-label font-medium"
                        >
                            Cancel
                        </button>
                    </div>
                </div>
            )}
        </div>
    );
};

export default GitHubIntegration;
