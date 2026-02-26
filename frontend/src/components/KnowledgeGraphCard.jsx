import React, { useState, useEffect, useCallback } from 'react';
import { Database, Search, GitBranch, Loader2, CheckCircle, XCircle, Network, Trash2, RefreshCw } from 'lucide-react';
import { API_ENDPOINTS } from '../config';

/**
 * Knowledge Graph Status Card
 * Shows the indexing status and allows users to index a repo,
 * query the KG, and view graph statistics.
 */
export default function KnowledgeGraphCard({ selectedProjectKey, token, taskToken, repoUrl }) {
    const [kgStatus, setKgStatus] = useState(null);
    const [isLoading, setIsLoading] = useState(false);
    const [isIndexing, setIsIndexing] = useState(false);
    const [indexError, setIndexError] = useState(null);
    const [queryText, setQueryText] = useState('');
    const [queryResult, setQueryResult] = useState(null);
    const [isQuerying, setIsQuerying] = useState(false);
    const [showQuery, setShowQuery] = useState(false);

    // Fetch KG status
    const fetchStatus = useCallback(async () => {
        if (!selectedProjectKey || !token) return;
        setIsLoading(true);
        try {
            const res = await fetch(API_ENDPOINTS.KG_STATUS(selectedProjectKey), {
                headers: { Authorization: `Bearer ${token}` },
            });
            if (res.ok) {
                const data = await res.json();
                setKgStatus(data);
            }
        } catch (e) {
            console.error('Failed to fetch KG status:', e);
        } finally {
            setIsLoading(false);
        }
    }, [selectedProjectKey, token]);

    useEffect(() => {
        fetchStatus();
    }, [fetchStatus]);

    // Poll while indexing
    useEffect(() => {
        if (!isIndexing) return;
        const interval = setInterval(fetchStatus, 3000);
        return () => clearInterval(interval);
    }, [isIndexing, fetchStatus]);

    // Stop polling when ready
    useEffect(() => {
        if (kgStatus?.is_ready && isIndexing) {
            setIsIndexing(false);
        }
    }, [kgStatus, isIndexing]);

    // Index repo
    const handleIndex = async () => {
        if (!repoUrl) {
            setIndexError('No repository URL configured. Set git repo on an agent first.');
            return;
        }
        setIsIndexing(true);
        setIndexError(null);
        try {
            const headers = {
                Authorization: `Bearer ${token}`,
                'Content-Type': 'application/json',
            };
            if (taskToken) headers['x-task-token'] = selectedProjectKey;

            const res = await fetch(API_ENDPOINTS.KG_INDEX, {
                method: 'POST',
                headers,
                body: JSON.stringify({
                    repo_url: repoUrl,
                    branch: 'main',
                }),
            });
            if (!res.ok) {
                const err = await res.json().catch(() => ({}));
                throw new Error(err.detail || 'Indexing failed');
            }
        } catch (e) {
            setIndexError(e.message);
            setIsIndexing(false);
        }
    };

    // Query the KG
    const handleQuery = async () => {
        if (!queryText.trim()) return;
        setIsQuerying(true);
        setQueryResult(null);
        try {
            const headers = {
                Authorization: `Bearer ${token}`,
                'Content-Type': 'application/json',
            };
            if (taskToken) headers['x-task-token'] = selectedProjectKey;

            const res = await fetch(API_ENDPOINTS.KG_QUERY, {
                method: 'POST',
                headers,
                body: JSON.stringify({
                    query: queryText,
                    mode: 'hybrid',
                }),
            });
            if (res.ok) {
                const data = await res.json();
                setQueryResult(data);
            } else {
                const err = await res.json().catch(() => ({}));
                setQueryResult({ status: 'error', error: err.detail || 'Query failed' });
            }
        } catch (e) {
            setQueryResult({ status: 'error', error: e.message });
        } finally {
            setIsQuerying(false);
        }
    };

    // Delete index
    const handleDelete = async () => {
        if (!window.confirm('Delete the Knowledge Graph index for this project?')) return;
        try {
            await fetch(API_ENDPOINTS.KG_DELETE(selectedProjectKey), {
                method: 'DELETE',
                headers: { Authorization: `Bearer ${token}` },
            });
            setKgStatus(null);
            setQueryResult(null);
        } catch (e) {
            console.error('Delete failed:', e);
        }
    };

    const isReady = kgStatus?.is_ready;
    const ragStatus = kgStatus?.rag_status;
    const graphStats = kgStatus?.graph_stats;
    const statusText = ragStatus?.status || 'not_started';

    const statusConfig = {
        not_started: { color: 'gray', label: 'Not Indexed', icon: <Database className="w-4 h-4" /> },
        indexing: { color: 'amber', label: 'Indexing...', icon: <Loader2 className="w-4 h-4 animate-spin" /> },
        ready: { color: 'emerald', label: 'Ready', icon: <CheckCircle className="w-4 h-4" /> },
        error: { color: 'red', label: 'Error', icon: <XCircle className="w-4 h-4" /> },
    };
    const cfg = statusConfig[statusText] || statusConfig.not_started;

    return (
        <div className="w-full mt-6 lg:col-start-1 min-w-0">
            <div className="flex items-center justify-between mb-4">
                <div className="flex items-center">
                    <div className="p-2 mr-3 rounded" style={{ background: 'linear-gradient(135deg, #6366f120, #8b5cf620)' }}>
                        <Network className="w-5 h-5" style={{ color: '#7c3aed' }} />
                    </div>
                    <h3 className="text-[15px] font-bold uppercase tracking-wide" style={{ color: '#7c3aed' }}>
                        Knowledge Graph
                    </h3>
                    <span
                        className={`ml-3 text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full border`}
                        style={{
                            color: cfg.color === 'emerald' ? '#059669' : cfg.color === 'amber' ? '#d97706' : cfg.color === 'red' ? '#dc2626' : '#6b7280',
                            background: cfg.color === 'emerald' ? '#ecfdf5' : cfg.color === 'amber' ? '#fffbeb' : cfg.color === 'red' ? '#fef2f2' : '#f9fafb',
                            borderColor: cfg.color === 'emerald' ? '#a7f3d0' : cfg.color === 'amber' ? '#fde68a' : cfg.color === 'red' ? '#fecaca' : '#e5e7eb',
                        }}
                    >
                        <span className="inline-flex items-center gap-1">
                            {cfg.icon} {cfg.label}
                        </span>
                    </span>
                </div>
            </div>

            <div className="bg-white rounded-xl shadow border border-gray-100 p-5">
                {/* Status & Actions Row */}
                <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
                    <div className="flex items-center gap-2 text-xs text-gray-500">
                        {ragStatus?.indexed_chunks > 0 && (
                            <span className="inline-flex items-center gap-1 px-2 py-1 bg-violet-50 text-violet-600 rounded-full font-semibold text-[10px]">
                                <Database className="w-3 h-3" /> {ragStatus.indexed_chunks} chunks indexed
                            </span>
                        )}
                        {graphStats && (
                            <>
                                <span className="inline-flex items-center gap-1 px-2 py-1 bg-blue-50 text-blue-600 rounded-full font-semibold text-[10px]">
                                    {graphStats.total_nodes} nodes
                                </span>
                                <span className="inline-flex items-center gap-1 px-2 py-1 bg-cyan-50 text-cyan-600 rounded-full font-semibold text-[10px]">
                                    {graphStats.total_edges} edges
                                </span>
                                {graphStats.languages?.length > 0 && (
                                    <span className="inline-flex items-center gap-1 px-2 py-1 bg-green-50 text-green-600 rounded-full font-semibold text-[10px]">
                                        {graphStats.languages.join(', ')}
                                    </span>
                                )}
                            </>
                        )}
                    </div>

                    <div className="flex items-center gap-2">
                        {!isReady && (
                            <button
                                onClick={handleIndex}
                                disabled={isIndexing || !repoUrl}
                                className={`inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-bold rounded-lg transition-all ${isIndexing
                                    ? 'bg-amber-100 text-amber-700 cursor-wait'
                                    : !repoUrl
                                        ? 'bg-gray-100 text-gray-400 cursor-not-allowed'
                                        : 'bg-gradient-to-r from-violet-500 to-purple-600 text-white shadow-md hover:shadow-lg hover:scale-105'
                                    }`}
                            >
                                {isIndexing ? (
                                    <><Loader2 className="w-3 h-3 animate-spin" /> Indexing...</>
                                ) : (
                                    <><GitBranch className="w-3 h-3" /> Index Repository</>
                                )}
                            </button>
                        )}
                        {isReady && (
                            <>
                                <button
                                    onClick={() => setShowQuery(!showQuery)}
                                    className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-bold bg-gradient-to-r from-violet-500 to-purple-600 text-white rounded-lg shadow-md hover:shadow-lg hover:scale-105 transition-all"
                                >
                                    <Search className="w-3 h-3" /> Query
                                </button>
                                <button
                                    onClick={fetchStatus}
                                    disabled={isLoading}
                                    className="inline-flex items-center gap-1 px-2 py-1.5 text-xs font-bold text-gray-500 bg-gray-100 rounded-lg hover:bg-gray-200 transition-colors"
                                >
                                    <RefreshCw className={`w-3 h-3 ${isLoading ? 'animate-spin' : ''}`} />
                                </button>
                                <button
                                    onClick={handleDelete}
                                    className="inline-flex items-center gap-1 px-2 py-1.5 text-xs font-bold text-red-500 bg-red-50 rounded-lg hover:bg-red-100 transition-colors"
                                    title="Delete index"
                                >
                                    <Trash2 className="w-3 h-3" />
                                </button>
                            </>
                        )}
                    </div>
                </div>

                {/* Indexing progress */}
                {isIndexing && ragStatus?.status === 'indexing' && (
                    <div className="mb-4">
                        <div className="flex justify-between text-[10px] text-gray-400 mb-1">
                            <span>Indexing codebase...</span>
                            <span className="font-bold text-violet-600">
                                {ragStatus.indexed_chunks} / {ragStatus.total_chunks || '?'} chunks
                            </span>
                        </div>
                        <div className="w-full bg-gray-100 rounded-full h-1.5 overflow-hidden">
                            <div
                                className="bg-gradient-to-r from-violet-400 to-purple-500 h-1.5 rounded-full transition-all duration-1000"
                                style={{
                                    width: ragStatus.total_chunks
                                        ? `${Math.round((ragStatus.indexed_chunks / ragStatus.total_chunks) * 100)}%`
                                        : '30%'
                                }}
                            />
                        </div>
                    </div>
                )}

                {/* Graph stats detail when ready */}
                {isReady && graphStats && (
                    <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-4">
                        {Object.entries(graphStats.node_types || {}).map(([type, count]) => (
                            <div key={type} className="text-center p-2 bg-gray-50 rounded-lg">
                                <p className="text-lg font-bold text-gray-800">{count}</p>
                                <p className="text-[9px] text-gray-400 uppercase font-semibold">{type}s</p>
                            </div>
                        ))}
                    </div>
                )}

                {/* Error */}
                {indexError && (
                    <div className="mt-3 px-3 py-2 bg-red-50 border border-red-100 rounded-lg text-xs text-red-600">
                        <XCircle className="w-3 h-3 inline mr-1" /> {indexError}
                    </div>
                )}

                {/* Query interface */}
                {showQuery && isReady && (
                    <div className="mt-4 border-t border-gray-100 pt-4">
                        <div className="flex gap-2">
                            <input
                                type="text"
                                value={queryText}
                                onChange={(e) => setQueryText(e.target.value)}
                                onKeyDown={(e) => e.key === 'Enter' && handleQuery()}
                                placeholder="Ask about your codebase... (e.g., 'How does authentication work?')"
                                className="flex-1 px-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-violet-300 focus:border-violet-400"
                            />
                            <button
                                onClick={handleQuery}
                                disabled={isQuerying || !queryText.trim()}
                                className={`inline-flex items-center gap-1.5 px-4 py-2 text-xs font-bold rounded-lg transition-all ${isQuerying
                                    ? 'bg-violet-100 text-violet-700 cursor-wait'
                                    : !queryText.trim()
                                        ? 'bg-gray-100 text-gray-400 cursor-not-allowed'
                                        : 'bg-gradient-to-r from-violet-500 to-purple-600 text-white shadow hover:shadow-lg'
                                    }`}
                            >
                                {isQuerying ? <Loader2 className="w-3 h-3 animate-spin" /> : <Search className="w-3 h-3" />}
                                Search
                            </button>
                        </div>

                        {queryResult && (
                            <div className="mt-3 p-3 bg-gray-50 rounded-lg border border-gray-100 max-h-[300px] overflow-y-auto">
                                {queryResult.status === 'error' ? (
                                    <p className="text-xs text-red-500">{queryResult.error}</p>
                                ) : (
                                    <pre className="text-xs text-gray-700 whitespace-pre-wrap font-mono leading-5">
                                        {typeof queryResult.context === 'string'
                                            ? queryResult.context
                                            : JSON.stringify(queryResult, null, 2)}
                                    </pre>
                                )}
                            </div>
                        )}
                    </div>
                )}

                {/* Not indexed - show CTA */}
                {!isReady && !isIndexing && (
                    <div className="text-center py-4">
                        <Network className="w-8 h-8 mx-auto mb-2 text-gray-300" />
                        <p className="text-xs text-gray-400 mb-1">No Knowledge Graph indexed for this project</p>
                        <p className="text-[10px] text-gray-400">
                            Index your repo to enable AI agents with deep codebase context
                        </p>
                    </div>
                )}
            </div>
        </div>
    );
}
