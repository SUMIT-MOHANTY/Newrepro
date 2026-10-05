import React, { useState, useEffect, useCallback, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { customAlert } from '../utils/modalHelpers';
import { Loader2, ArrowLeft, ExternalLink, RefreshCw, Maximize2, Minimize2, Globe, StopCircle, Smartphone, Monitor, Tablet } from 'lucide-react';
import { API_ENDPOINTS, API_BASE_URL } from '../config';
import ExecutionStream from '../components/ExecutionStream';

const DEVICE_SIZES = [
    { id: 'desktop', label: 'Desktop', icon: Monitor, width: '100%', height: '100%' },
    { id: 'tablet', label: 'Tablet', icon: Tablet, width: '768px', height: '100%' },
    { id: 'mobile', label: 'Mobile', icon: Smartphone, width: '375px', height: '100%' },
];

export default function AppPreview() {
    const { projectId } = useParams();
    const navigate = useNavigate();
    const token = localStorage.getItem('token');

    const [previewStatus, setPreviewStatus] = useState({ status: 'loading' });
    const [isDeploying, setIsDeploying] = useState(false);
    const [isFullscreen, setIsFullscreen] = useState(false);
    const [selectedDevice, setSelectedDevice] = useState('desktop');
    const [iframeKey, setIframeKey] = useState(0);
    const [previewSteps, setPreviewSteps] = useState([]);
    const wsRef = useRef(null);

    const fetchStatus = useCallback(async () => {
        if (!token) return;
        try {
            const params = projectId ? `?project_token=${projectId}` : '';
            const res = await fetch(`${API_ENDPOINTS.AGENT_PREVIEW_STATUS}${params}`, {
                headers: { 'Authorization': `Bearer ${token}` },
            });
            if (res.ok) {
                const data = await res.json();
                setPreviewStatus(data);
            }
        } catch (e) {
            console.error('Preview status fetch failed', e);
        }
    }, [token, projectId]);

    // Poll while deploying
    useEffect(() => {
        fetchStatus();
    }, [fetchStatus]);

    useEffect(() => {
        if (previewStatus.status === 'deploying') {
            const interval = setInterval(fetchStatus, 3000);
            return () => clearInterval(interval);
        }
    }, [previewStatus.status, fetchStatus]);

    // WebSocket event streaming for real-time deploy logs
    useEffect(() => {
        if (!projectId || (previewStatus.status !== 'deploying' && !isDeploying)) {
            if (wsRef.current) {
                wsRef.current.close();
                wsRef.current = null;
            }
            return;
        }

        const wsUrl = API_ENDPOINTS.AGENT_PREVIEW_WS(projectId);
        const ws = new WebSocket(wsUrl);
        wsRef.current = ws;

        ws.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                const eventType = data.event_type || data.type;
                const msg = data.content || data.message || '';
                const payload = data.payload || {};

                if (data.metadata?.status === 'success' || eventType === 'preview_ready' || eventType === 'session_completed') {
                    setPreviewStatus(prev => ({
                        ...prev,
                        status: 'running',
                        preview_url: data.metadata?.preview_url || payload?.preview_url || `/app/${projectId}/`,
                    }));
                } else if (data.metadata?.status === 'error' || eventType === 'session_failed') {
                    setPreviewStatus(prev => ({
                        ...prev,
                        status: 'error',
                    }));
                }

                if (msg) {
                    const isFile = Boolean(
                        payload.is_file ||
                        msg.startsWith('Writing') ||
                        msg.startsWith('Editing') ||
                        msg.startsWith('Reading') ||
                        msg.startsWith('Created') ||
                        eventType === 'tool_called'
                    );
                    const isThinking = eventType === 'thinking' || msg.startsWith('Thinking:');
                    const isPreview = Boolean(eventType === 'preview_ready' || (data.metadata?.status === 'success' && data.metadata?.preview_url));

                    let label = msg;
                    if (isThinking) {
                        label = msg.replace(/^Thinking:\s*/, '');
                    } else if (eventType === 'git_clone_started') {
                        label = `Cloning repository: ${payload.repo_url || ''}`;
                    } else if (eventType === 'git_clone_completed') {
                        label = `Repository synchronized (${payload.branch || 'main'})`;
                    } else if (eventType === 'build_started') {
                        label = 'Building and compiling application sandbox...';
                    } else if (eventType === 'build_completed') {
                        label = 'Sandbox build & dependency verification passed';
                    }

                    const stepItem = {
                        id: `step-${Date.now()}-${Math.random().toString(36).substring(2, 7)}`,
                        label: label,
                        isFile: isFile,
                        status: (data.metadata?.status === 'error' || eventType === 'session_failed') ? 'error' : 'done',
                        kind: isPreview ? 'preview' : (isThinking ? 'thinking' : (isFile ? 'file' : 'log')),
                        tool_name: payload.tool || payload.tool_name,
                        args: payload.args,
                        details: payload.output || payload.details || payload.result,
                        timestamp: data.timestamp || new Date().toISOString(),
                    };

                    setPreviewSteps(prev => [...prev, stepItem]);
                }
            } catch (err) {
                console.error('[Preview WS] Failed to parse message:', err);
            }
        };

        return () => {
            if (wsRef.current) {
                wsRef.current.close();
                wsRef.current = null;
            }
        };
    }, [projectId, previewStatus.status, isDeploying]);

    const handleDeploy = async () => {
        const activeToken = token || localStorage.getItem('token');
        if (!activeToken) {
            customAlert('You must be logged in to deploy preview. Please log in again.', 'Authentication Required');
            setIsDeploying(false);
            return;
        }

        try {
            const params = projectId ? `?project_token=${encodeURIComponent(projectId)}` : '';
            const res = await fetch(`${API_ENDPOINTS.AGENT_PREVIEW_DEPLOY}${params}`, {
                method: 'POST',
                headers: {
                    'Authorization': `Bearer ${activeToken}`,
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    project_token: projectId,
                }),
            });
            if (res.ok) {
                const data = await res.json();
                setPreviewStatus(data);
            } else {
                const err = await res.json().catch(() => ({}));
                customAlert(err.detail || 'Deploy failed', 'Deploy Failed');
            }
        } catch (e) {
            console.error('Deploy preview failed', e);
            const msg = e.message === 'Failed to fetch'
                ? 'Backend server on http://localhost:8000 is unreachable or restarting. Please ensure the backend is running.'
                : e.message;
            customAlert('Deploy failed: ' + msg, 'Deploy Failed');
        } finally {
            setIsDeploying(false);
        }
    };

    const handleStop = async () => {
        const params = projectId ? `?project_token=${projectId}` : '';
        await fetch(`${API_ENDPOINTS.AGENT_PREVIEW_STOP}${params}`, {
            method: 'POST',
            headers: { 'Authorization': `Bearer ${token}` },
        });
        setPreviewStatus({ status: 'stopped' });
    };

    const appUrl = `${window.location.origin}/app/${projectId}`;
    const deviceConfig = DEVICE_SIZES.find(d => d.id === selectedDevice) || DEVICE_SIZES[0];

    // Fullscreen mode
    if (isFullscreen && previewStatus.status === 'running' && previewStatus.preview_url) {
        return (
            <div className="fixed inset-0 z-[200] bg-black">
                <div className="absolute top-0 left-0 right-0 h-10 bg-app-text-main/80 backdrop-blur flex items-center justify-between px-4 z-10">
                    <div className="flex items-center gap-2">
                        <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
                        <span className="text-xs text-app-border font-mono">{appUrl}</span>
                    </div>
                    <button
                        onClick={() => setIsFullscreen(false)}
                        className="p-1.5 rounded-lg hover:bg-app-text-label text-app-text-light hover:text-app-bg-card transition-all"
                    >
                        <Minimize2 className="w-4 h-4" />
                    </button>
                </div>
                <iframe
                    key={iframeKey}
                    src={`${API_BASE_URL}/app/${projectId}/`}
                    className="w-full h-full pt-10 border-0"
                    title="App Preview"
                    sandbox="allow-scripts allow-same-origin allow-forms allow-popups allow-modals"
                />
            </div>
        );
    }

    return (
        <div className="min-h-screen bg-gradient-to-br from-app-text-main via-app-text-main to-app-text-main text-app-bg-card">
            {/* Top Bar */}
            <div className="sticky top-0 z-50 bg-app-text-main/80 backdrop-blur-xl border-b border-app-text-main/50">
                <div className="max-w-[1800px] mx-auto px-6 h-14 flex items-center justify-between">
                    <div className="flex items-center gap-4">
                        <button
                            onClick={() => navigate(-1)}
                            className="flex items-center gap-1.5 text-app-text-light hover:text-app-bg-card text-sm transition-colors"
                        >
                            <ArrowLeft className="w-4 h-4" />
                            Back
                        </button>
                        <div className="h-5 w-px bg-app-text-label" />
                        <div className="flex items-center gap-2">
                            <Globe className="w-4 h-4 text-violet-400" />
                            <span className="font-semibold text-sm">App Preview</span>
                            {previewStatus.status === 'running' && (
                                <span className="flex items-center gap-1 px-2 py-0.5 rounded-full bg-app-status-success/10 border border-app-status-success/30 text-emerald-400 text-[10px] font-bold">
                                    <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
                                    LIVE
                                </span>
                            )}
                        </div>
                    </div>

                    {previewStatus.status === 'running' && (
                        <div className="flex items-center gap-3">
                            {/* Device Switcher */}
                            <div className="flex items-center gap-1 bg-app-text-label/50 rounded-xl p-1 border border-app-text-label/50">
                                {DEVICE_SIZES.map(device => (
                                    <button
                                        key={device.id}
                                        onClick={() => setSelectedDevice(device.id)}
                                        className={`p-1.5 rounded-lg transition-all ${selectedDevice === device.id
                                            ? 'bg-violet-600 text-app-bg-card shadow-lg shadow-violet-600/20'
                                            : 'text-app-text-muted hover:text-app-border hover:bg-app-text-label/50'
                                            }`}
                                        title={device.label}
                                    >
                                        <device.icon className="w-4 h-4" />
                                    </button>
                                ))}
                            </div>

                            <div className="h-5 w-px bg-app-text-label" />

                            <button
                                onClick={() => setIframeKey(k => k + 1)}
                                className="p-2 rounded-lg bg-app-text-label/50 border border-app-text-label/50 text-app-text-light hover:text-app-bg-card hover:bg-app-text-label transition-all"
                                title="Refresh"
                            >
                                <RefreshCw className="w-4 h-4" />
                            </button>
                            <button
                                onClick={() => setIsFullscreen(true)}
                                className="p-2 rounded-lg bg-app-text-label/50 border border-app-text-label/50 text-app-text-light hover:text-app-bg-card hover:bg-app-text-label transition-all"
                                title="Fullscreen"
                            >
                                <Maximize2 className="w-4 h-4" />
                            </button>
                            <a
                                href={`/app/${projectId}`}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="p-2 rounded-lg bg-app-text-label/50 border border-app-text-label/50 text-app-text-light hover:text-app-bg-card hover:bg-app-text-label transition-all"
                                title="Open in new tab"
                            >
                                <ExternalLink className="w-4 h-4" />
                            </a>
                            <button
                                onClick={handleStop}
                                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-app-status-error/10 border border-app-status-error/30 text-red-400 text-xs font-semibold hover:bg-app-status-error/20 transition-all"
                            >
                                <StopCircle className="w-3.5 h-3.5" />
                                Stop
                            </button>
                        </div>
                    )}
                </div>
            </div>

            {/* Content */}
            {previewStatus.status === 'running' && previewStatus.preview_url ? (
                <div className="flex-1 flex items-start justify-center p-6" style={{ height: 'calc(100vh - 56px)' }}>
                    <div
                        className="bg-app-text-main rounded-2xl border border-app-text-label/50 overflow-hidden shadow-2xl transition-all duration-300"
                        style={{
                            width: deviceConfig.width,
                            height: deviceConfig.height,
                            maxWidth: '100%',
                        }}
                    >
                        <iframe
                            key={iframeKey}
                            // Force proxy URL instead of calling the docker port directly as requested.
                            src={`${API_BASE_URL}/app/${projectId}/`}
                            className="w-full border-0"
                            style={{ height: '100%' }}
                            title="App Preview"
                            sandbox="allow-scripts allow-same-origin allow-forms allow-popups allow-modals"
                        />
                    </div>
                </div>
            ) : previewStatus.status === 'deploying' ? (
                <div className="flex-1 flex flex-col items-center justify-center p-6 overflow-y-auto" style={{ minHeight: 'calc(100vh - 56px)' }}>
                    <div className="w-full max-w-2xl space-y-6 py-8">
                        <div className="text-center space-y-3">
                            <div className="relative inline-block">
                                <div className="w-16 h-16 rounded-2xl bg-violet-500/10 border-2 border-violet-500/30 flex items-center justify-center mx-auto shadow-lg shadow-violet-500/10">
                                    <Loader2 className="w-7 h-7 text-violet-400 animate-spin" />
                                </div>
                            </div>
                            <div>
                                <h3 className="text-lg font-bold text-app-bg-card">Deploying Application in Sandbox</h3>
                                <p className="text-xs text-app-text-muted mt-0.5">Cloning repository, detecting tech stack, running build, and serving preview on port 80.</p>
                            </div>
                        </div>

                        {previewSteps.length > 0 ? (
                            <ExecutionStream
                                steps={previewSteps}
                                isLive={true}
                            />
                        ) : previewStatus.logs && previewStatus.logs.length > 0 ? (
                            <div className="bg-app-text-main rounded-xl border border-app-text-main p-4 shadow-xl">
                                <div className="space-y-1 font-mono text-[11px] text-left">
                                    {previewStatus.logs.slice(-6).map((log, i) => (
                                        <div key={i} className="text-app-text-light flex items-center gap-1.5">
                                            <span className="text-violet-400">›</span>
                                            {log.message}
                                        </div>
                                    ))}
                                </div>
                            </div>
                        ) : null}
                    </div>
                </div>
            ) : (
                <div className="flex-1 flex items-center justify-center" style={{ height: 'calc(100vh - 56px)' }}>
                    <div className="text-center space-y-6 max-w-md">
                        <div className="p-6 rounded-2xl bg-violet-500/5 border border-violet-500/10 inline-block">
                            <Globe className="w-16 h-16 text-violet-400 mx-auto" />
                        </div>
                        <div>
                            <h2 className="text-2xl font-bold text-app-bg-card">Preview Your Application</h2>
                            <p className="text-app-text-light text-sm mt-2 leading-relaxed">
                                Deploy the <code className="px-1.5 py-0.5 bg-app-text-label rounded text-violet-300 text-xs">agent/integration</code> branch
                                and preview it right here.
                            </p>
                        </div>
                        <button
                            onClick={handleDeploy}
                            disabled={isDeploying}
                            className="inline-flex items-center gap-2.5 px-8 py-3.5 rounded-2xl bg-gradient-to-r from-violet-600 to-purple-600 text-app-bg-card font-bold text-sm shadow-xl shadow-violet-600/25 hover:shadow-violet-600/40 hover:scale-[1.03] transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed"
                        >
                            {isDeploying ? (
                                <Loader2 className="w-5 h-5 animate-spin" />
                            ) : (
                                <Globe className="w-5 h-5" />
                            )}
                            {isDeploying ? 'Deploying...' : 'Deploy & Preview'}
                        </button>
                        {previewStatus.status === 'error' && (
                            <p className="text-red-400 text-xs mt-2">Previous deploy failed. Try again.</p>
                        )}
                    </div>
                </div>
            )}
        </div>
    );
}
