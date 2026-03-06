import { useState, useEffect, useCallback } from 'react';
import { API_ENDPOINTS } from '../config';

const AzureDevOpsIcon = ({ className = 'w-5 h-5' }) => (
    <svg viewBox="0 0 16 16" aria-hidden="true" className={className} role="img">
        <path
            fill="#0078D4"
            d="M15 3.622v8.512L11.5 15l-5.425-1.975v1.958L3.004 10.97l8.951.7V4.005L15 3.622zm-2.984.428L6.994 1v2.001L2.382 4.356 1 6.13v4.029l1.978.873V5.869l9.038-1.818z"
        />
    </svg>
);

const AzureDevOpsIntegration = ({
    onRepoContextReady,
    repoContext,
    onClearRepo,
    onRepoSelected,
    inline = false,
}) => {
    const [connected, setConnected] = useState(false);
    const [azureUsername, setAzureUsername] = useState('');
    const [repos, setRepos] = useState([]);
    const [loadingRepos, setLoadingRepos] = useState(false);
    const [selectedRepo, setSelectedRepo] = useState(null);
    const [fetchingContext, setFetchingContext] = useState(false);
    const [showRepoList, setShowRepoList] = useState(false);
    const [searchFilter, setSearchFilter] = useState('');
    const [connectError, setConnectError] = useState('');

    const getToken = () => localStorage.getItem('token');

    const checkStatus = useCallback(async () => {
        try {
            const resp = await fetch(API_ENDPOINTS.AZURE_DEVOPS_STATUS, {
                headers: { Authorization: `Bearer ${getToken()}` },
            });
            if (!resp.ok) return;
            const data = await resp.json();
            setConnected(Boolean(data.connected));
            setAzureUsername(data.azure_devops_username || '');
        } catch (e) {
            console.warn('Azure DevOps status check failed:', e);
        }
    }, []);

    useEffect(() => {
        checkStatus();
    }, [checkStatus]);

    const handleConnect = async () => {
        setConnectError('');
        try {
            const resp = await fetch(API_ENDPOINTS.AZURE_DEVOPS_AUTH_URL, {
                headers: { Authorization: `Bearer ${getToken()}` },
            });
            if (!resp.ok) {
                const errData = await resp.json().catch(() => ({}));
                let message = errData.detail || `Failed to get Azure DevOps auth URL (HTTP ${resp.status})`;
                if (String(message).includes('AZURE_DEVOPS_CLIENT_ID')) {
                    message = 'Azure DevOps OAuth is not configured on backend (missing AZURE_DEVOPS_CLIENT_ID).';
                }
                throw new Error(message);
            }
            const data = await resp.json();
            if (!data?.url) {
                throw new Error('Azure DevOps auth URL is missing in backend response.');
            }
            window.location.href = data.url;
        } catch (e) {
            setConnectError(e.message || 'Unable to start Azure DevOps OAuth.');
            console.error('Azure DevOps connect error:', e);
        }
    };

    const handleDisconnect = async () => {
        try {
            await fetch(API_ENDPOINTS.AZURE_DEVOPS_DISCONNECT, {
                method: 'POST',
                headers: { Authorization: `Bearer ${getToken()}` },
            });
            setConnected(false);
            setAzureUsername('');
            setRepos([]);
            setSelectedRepo(null);
            setShowRepoList(false);
            if (onClearRepo) onClearRepo();
        } catch (e) {
            console.error('Azure DevOps disconnect error:', e);
        }
    };

    const loadRepos = async () => {
        setLoadingRepos(true);
        try {
            const resp = await fetch(API_ENDPOINTS.AZURE_DEVOPS_REPOS, {
                headers: { Authorization: `Bearer ${getToken()}` },
            });
            if (!resp.ok) throw new Error('Failed to fetch Azure DevOps repositories');
            const data = await resp.json();
            setRepos(Array.isArray(data.repos) ? data.repos : []);
            setShowRepoList(true);
        } catch (e) {
            console.error('Azure DevOps repository list error:', e);
        } finally {
            setLoadingRepos(false);
        }
    };

    const handleSelectRepo = async (repo) => {
        if (onRepoSelected) onRepoSelected(repo);
        setSelectedRepo(repo);
        setShowRepoList(false);
        setFetchingContext(true);
        try {
            const repoUrl = repo.repo_url || repo.html_url || '';
            const branch = repo.default_branch || 'main';
            const resp = await fetch(API_ENDPOINTS.AZURE_DEVOPS_REPO_CONTEXT, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    Authorization: `Bearer ${getToken()}`,
                },
                body: JSON.stringify({
                    repo_url: repoUrl,
                    branch,
                }),
            });
            if (!resp.ok) {
                const err = await resp.json().catch(() => ({}));
                throw new Error(err.detail || 'Failed to build Azure DevOps repository context');
            }
            const data = await resp.json();
            if (onRepoContextReady) {
                onRepoContextReady({
                    repo: data.repo || repo.full_name,
                    branch: data.branch || branch,
                    context: data.context,
                    provider: 'azure-devops',
                    url: data.url || repoUrl,
                    description: repo.description || '',
                });
            }
        } catch (e) {
            console.error('Azure DevOps repository context error:', e);
        } finally {
            setFetchingContext(false);
        }
    };

    const filteredRepos = repos.filter((r) =>
        String(r.name || '').toLowerCase().includes(searchFilter.toLowerCase()) ||
        String(r.description || '').toLowerCase().includes(searchFilter.toLowerCase()) ||
        String(r.full_name || '').toLowerCase().includes(searchFilter.toLowerCase())
    );

    if (inline) {
        if (!connected) {
            return (
                <div className="space-y-1.5">
                    <button
                        type="button"
                        onClick={handleConnect}
                        className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold text-app-text-label bg-app-bg-muted rounded-lg hover:bg-app-bg-hover transition-all active:scale-95 border border-app-border"
                    >
                        <AzureDevOpsIcon className="w-3.5 h-3.5" />
                        Connect Azure DevOps
                    </button>
                    {connectError && (
                        <p className="max-w-[320px] text-[11px] font-medium text-app-status-error">{connectError}</p>
                    )}
                </div>
            );
        }

        return (
            <div className="relative">
                <div className="flex items-center gap-1.5">
                    {selectedRepo ? (
                        <button
                            type="button"
                            onClick={() => {
                                setSelectedRepo(null);
                                if (onClearRepo) onClearRepo();
                                setShowRepoList(false);
                            }}
                            className="inline-flex items-center gap-1.5 px-2.5 py-1.5 text-xs font-semibold text-emerald-700 bg-app-status-successBg rounded-lg border border-emerald-200 hover:bg-emerald-100 transition-all max-w-[220px]"
                            title={`${selectedRepo.full_name} - click to change`}
                        >
                            {fetchingContext ? (
                                <span className="animate-spin inline-block w-3 h-3 border-2 border-emerald-600 border-t-transparent rounded-full"></span>
                            ) : (
                                <AzureDevOpsIcon className="w-3.5 h-3.5 text-app-status-success flex-shrink-0" />
                            )}
                            <span className="truncate">{selectedRepo.name}</span>
                            {repoContext && <span className="text-app-status-success flex-shrink-0">OK</span>}
                        </button>
                    ) : (
                        <button
                            type="button"
                            onClick={showRepoList ? () => setShowRepoList(false) : loadRepos}
                            disabled={loadingRepos}
                            className="inline-flex items-center gap-1.5 px-2.5 py-1.5 text-xs font-semibold text-app-text-label bg-app-bg-muted rounded-lg border border-app-border hover:bg-app-bg-hover transition-all disabled:opacity-50"
                        >
                            {loadingRepos ? (
                                <span className="animate-spin inline-block w-3 h-3 border-2 border-gray-500 border-t-transparent rounded-full"></span>
                            ) : (
                                <AzureDevOpsIcon className="w-3.5 h-3.5 flex-shrink-0" />
                            )}
                            <span className="hidden sm:inline">{azureUsername || 'Azure DevOps'}</span>
                            <span className="sm:hidden">Repo</span>
                        </button>
                    )}
                    <button
                        type="button"
                        onClick={handleDisconnect}
                        className="p-1 text-app-text-light hover:text-app-status-error rounded hover:bg-app-status-errorBg transition-colors"
                        title="Disconnect Azure DevOps"
                    >
                        <svg xmlns="http://www.w3.org/2000/svg" className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                            <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                        </svg>
                    </button>
                </div>

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
                                        className="w-full flex items-center gap-3 px-3 py-2.5 text-left hover:bg-app-primary-light border-b border-gray-50 last:border-b-0 transition-colors"
                                    >
                                        <AzureDevOpsIcon className="w-4 h-4 text-app-text-light flex-shrink-0" />
                                        <div className="min-w-0 flex-1">
                                            <p className="text-xs font-semibold text-app-text-main truncate">{repo.name}</p>
                                            <p className="text-[11px] text-app-text-muted truncate">{repo.full_name}</p>
                                        </div>
                                    </button>
                                ))
                            )}
                        </div>
                    </div>
                )}
            </div>
        );
    }

    if (!connected) {
        return (
            <div className="space-y-2">
                <button
                    type="button"
                    onClick={handleConnect}
                    className="w-full inline-flex items-center justify-center gap-2 px-4 py-2.5 text-sm font-semibold text-white bg-app-primary rounded-lg hover:bg-app-primary-dark transition-colors"
                >
                    <AzureDevOpsIcon className="w-4 h-4" />
                    Connect Azure DevOps
                </button>
                {connectError && (
                    <p className="text-xs font-medium text-app-status-error">{connectError}</p>
                )}
            </div>
        );
    }

    return (
        <div className="space-y-3">
            <div className="flex items-center justify-between rounded-lg border border-app-border-light bg-app-bg-page/60 px-3 py-2">
                <div className="flex items-center gap-2 min-w-0">
                    <AzureDevOpsIcon className="w-4 h-4 text-app-primary flex-shrink-0" />
                    <span className="text-xs font-semibold text-app-text-main truncate">
                        {azureUsername || 'Connected'}
                    </span>
                </div>
                <button
                    type="button"
                    onClick={handleDisconnect}
                    className="text-xs font-semibold text-app-status-error hover:text-red-700"
                >
                    Disconnect
                </button>
            </div>

            <button
                type="button"
                onClick={showRepoList ? () => setShowRepoList(false) : loadRepos}
                disabled={loadingRepos || fetchingContext}
                className="w-full inline-flex items-center justify-center gap-2 px-4 py-2.5 text-sm font-semibold text-app-text-main bg-app-bg-muted rounded-lg border border-app-border hover:bg-app-bg-hover disabled:opacity-60 transition-colors"
            >
                {loadingRepos ? (
                    <span className="animate-spin inline-block w-3.5 h-3.5 border-2 border-app-text-main border-t-transparent rounded-full"></span>
                ) : (
                    <AzureDevOpsIcon className="w-4 h-4" />
                )}
                {selectedRepo ? `Selected: ${selectedRepo.name}` : 'Select Repository'}
            </button>

            {showRepoList && (
                <div className="border border-app-border rounded-xl overflow-hidden bg-app-bg-card">
                    <div className="p-2 border-b border-app-border-light">
                        <input
                            type="text"
                            value={searchFilter}
                            onChange={(e) => setSearchFilter(e.target.value)}
                            placeholder="Search repositories..."
                            className="w-full px-3 py-2 text-xs border border-app-border rounded-md focus:ring-1 focus:ring-app-primary focus:border-app-primary bg-app-bg-card"
                        />
                    </div>
                    <div className="max-h-64 overflow-y-auto">
                        {filteredRepos.length === 0 ? (
                            <p className="text-xs text-app-text-light p-4 text-center">No repositories found.</p>
                        ) : (
                            filteredRepos.map((repo) => (
                                <button
                                    key={repo.id}
                                    type="button"
                                    onClick={() => handleSelectRepo(repo)}
                                    className="w-full flex items-center gap-3 px-3 py-2.5 text-left hover:bg-app-primary-light border-b border-gray-50 last:border-b-0 transition-colors"
                                >
                                    <AzureDevOpsIcon className="w-4 h-4 text-app-text-light flex-shrink-0" />
                                    <div className="min-w-0 flex-1">
                                        <p className="text-xs font-semibold text-app-text-main truncate">{repo.name}</p>
                                        <p className="text-[11px] text-app-text-muted truncate">{repo.full_name}</p>
                                    </div>
                                </button>
                            ))
                        )}
                    </div>
                </div>
            )}
        </div>
    );
};

export default AzureDevOpsIntegration;
