import React, { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { customAlert } from '../utils/modalHelpers';
import { Loader2, ArrowLeft, ExternalLink, RefreshCw, Maximize2, Minimize2, Globe, StopCircle, Smartphone, Monitor, Tablet } from 'lucide-react';
import { API_ENDPOINTS } from '../config';

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

    const handleDeploy = async () => {
        setIsDeploying(true);
        try {
            const params = projectId ? `?project_token=${projectId}` : '';
            const res = await fetch(`${API_ENDPOINTS.AGENT_PREVIEW_DEPLOY}${params}`, {
                method: 'POST',
                headers: {
                    'Authorization': `Bearer ${token}`,
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({}),
            });
            if (res.ok) {
                const data = await res.json();
                setPreviewStatus(data);
            } else {
                const err = await res.json().catch(() => ({}));
                customAlert(err.detail || 'Deploy failed', 'Deploy Failed');
            }
        } catch (e) {
            customAlert('Deploy failed: ' + e.message, 'Deploy Failed');
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
                    src={previewStatus.preview_url}
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
                            src={previewStatus.preview_url}
                            className="w-full border-0"
                            style={{ height: '100%' }}
                            title="App Preview"
                            sandbox="allow-scripts allow-same-origin allow-forms allow-popups allow-modals"
                        />
                    </div>
                </div>
            ) : previewStatus.status === 'deploying' ? (
                <div className="flex-1 flex items-center justify-center" style={{ height: 'calc(100vh - 56px)' }}>
                    <div className="text-center space-y-4">
                        <div className="relative">
                            <div className="w-20 h-20 rounded-full bg-violet-500/10 border-2 border-violet-500/30 flex items-center justify-center mx-auto">
                                <Loader2 className="w-8 h-8 text-violet-400 animate-spin" />
                            </div>
                            <div className="absolute inset-0 w-20 h-20 rounded-full border-2 border-violet-400/20 animate-ping mx-auto" />
                        </div>
                        <div>
                            <p className="text-lg font-semibold text-app-bg-card">Deploying your application...</p>
                            <p className="text-sm text-app-text-muted mt-1">Cloning, installing dependencies, and starting the server</p>
                        </div>
                        {previewStatus.logs && previewStatus.logs.length > 0 && (
                            <div className="mt-6 max-w-md mx-auto bg-app-text-main rounded-xl border border-app-text-main p-4">
                                <div className="space-y-1 font-mono text-[11px] text-left">
                                    {previewStatus.logs.slice(-5).map((log, i) => (
                                        <div key={i} className="text-app-text-light">
                                            <span className="text-violet-400 mr-1">›</span>
                                            {log.message}
                                        </div>
                                    ))}
                                </div>
                            </div>
                        )}
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
