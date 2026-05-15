import { useState, useEffect } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import {
    Upload, Settings as SettingsIcon, Mail, Activity, FileText, Trash2, Calendar, Lock,
    Eye, EyeOff, CheckCircle, X, Download, ExternalLink, FolderPlus, Folder,
    PlusCircle, ArrowRight, Copy, RefreshCw, TrendingUp, Users, BarChart2,
    Clock, Globe, Shield, AlertCircle, ChevronDown, ChevronUp, ChevronLeft, ChevronRight, Link2, Send
} from 'lucide-react';
import { API_ENDPOINTS } from '../config';
import RoadmapHeader from '../components/RoadmapHeader';

const ShareDocument = ({ selectedProjectKey, handleCreateShareProject: parentHandleCreateShareProject }) => {
    const navigate = useNavigate();
    const [searchParams] = useSearchParams();
    const stepParam = parseInt(searchParams.get('step') || '0');

    const [currentStep, setCurrentStep] = useState(stepParam);
    const [uploadedFiles, setUploadedFiles] = useState([]);
    const [isDragging, setIsDragging] = useState(false);

    // Project selection state
    const [shareProjects, setShareProjects] = useState([]);
    const [selectedProjectToken, setSelectedProjectToken] = useState('');
    const [loadingProjects, setLoadingProjects] = useState(true);

    const [projectName, setProjectName] = useState('');
    const [creatingProject, setCreatingProject] = useState(false);
    const [projectError, setProjectError] = useState('');
    const [showCreateModal, setShowCreateModal] = useState(false);

    const [shareConfig, setShareConfig] = useState({
        dashboardAccess: 'once',
        expirationTime: 'no-expiration',
        expirationDays: 7,
        expirationDate: '',
        requirePassword: false,
        password: '',
        viewLimit: 5,
        canDownload: true,
        allowAnonymous: true
    });

    // Email sharing state
    const [recipientEmails, setRecipientEmails] = useState([]);
    const [emailInput, setEmailInput] = useState('');
    const [recipientAccessLevel, setRecipientAccessLevel] = useState('view');
    const [selectedFiles, setSelectedFiles] = useState([]);
    const [sharing, setSharing] = useState(false);
    const [shareLink, setShareLink] = useState('');
    const [shareToken, setShareToken] = useState('');
    const [shareError, setShareError] = useState('');
    const [copySuccess, setCopySuccess] = useState(false);

    // Status tracking state
    const [shareStats, setShareStats] = useState(null);
    const [loadingStats, setLoadingStats] = useState(false);
    const [expandedRecipient, setExpandedRecipient] = useState(null);
    const [trackingPage, setTrackingPage] = useState(1);
    const TRACKING_PAGE_SIZE = 5;

    // Roadmap configuration
    const roadmapSteps = ['Project Initiation', 'Upload Documents', 'Configure Access', 'Share & Invite', 'Track Status'];

    useEffect(() => {
        setCurrentStep(stepParam);
    }, [stepParam]);

    // Handle project selection from sidebar
    useEffect(() => {
        if (selectedProjectKey) {
            setSelectedProjectToken(selectedProjectKey);

            // Only restore project step if no step is specified in URL
            if (stepParam === 0) {
                const project = shareProjects.find(p => p.project_token === selectedProjectKey);
                if (project) {
                    if (typeof project.current_step === 'number' && project.current_step > 0) {
                        setCurrentStep(project.current_step);
                    } else {
                        setCurrentStep(1);
                    }
                }
            }
        } else {
            setSelectedProjectToken('');
            if (stepParam === 0) {
                setCurrentStep(0);
            }
        }
    }, [selectedProjectKey, shareProjects]);

    // Update currentStep once shareProjects are loaded if they weren't before
    useEffect(() => {
        if (stepParam === 0 && selectedProjectKey && shareProjects.length > 0 && currentStep === 1) {
            const project = shareProjects.find(p => p.project_token === selectedProjectKey);
            if (project && typeof project.current_step === 'number' && project.current_step > 1) {
                setCurrentStep(project.current_step);
            }
        }
    }, [selectedProjectKey, shareProjects.length, currentStep, stepParam]);

    // Persist current step to backend
    useEffect(() => {
        if (!selectedProjectToken || currentStep === 0) return;
        const updateStep = async () => {
            try {
                const token = localStorage.getItem('token');
                const response = await fetch(API_ENDPOINTS.SHARE_PROJECT(selectedProjectToken), {
                    method: 'PATCH',
                    headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
                    body: JSON.stringify({ current_step: currentStep })
                });
                if (response.ok) {
                    setShareProjects(prev => prev.map(p =>
                        p.project_token === selectedProjectToken ? { ...p, current_step: currentStep } : p
                    ));
                }
            } catch (err) {
                console.error('Failed to persist current step:', err);
            }
        };
        const timer = setTimeout(updateStep, 500);
        return () => clearTimeout(timer);
    }, [currentStep, selectedProjectToken]);

    // Fetch and restore project details (files, recipients, etc.)
    useEffect(() => {
        const fetchProjectDetails = async () => {
            if (!selectedProjectToken || !selectedProjectToken.startsWith('share_')) {
                // Clear state if no project selected
                setUploadedFiles([]);
                setSelectedFiles([]);
                setRecipientEmails([]);
                setShareLink('');
                setShareToken('');
                return;
            }

            // Clear state immediately when project changes to prevent leakage
            setUploadedFiles([]);
            setSelectedFiles([]);
            setRecipientEmails([]);
            setShareLink('');
            setShareToken('');
            setShareConfig({
                dashboardAccess: 'once',
                expirationDays: 7,
                expirationDate: '',
                requirePassword: false,
                password: '',
                viewLimit: 5,
                canDownload: true,
                allowAnonymous: true
            });

            try {
                const token = localStorage.getItem('token');
                const response = await fetch(API_ENDPOINTS.SHARE_PROJECT(selectedProjectToken), {
                    headers: { 'Authorization': `Bearer ${token}` }
                });
                if (response.ok) {
                    const data = await response.json();
                    const latestDoc = data.documents[0]; // Most recent first
                    if (latestDoc) {
                        // Restore state from the latest shared document
                        setUploadedFiles(latestDoc.files.map(f => ({
                            id: f.id,
                            name: f.original_filename,
                            size: f.file_size,
                            type: f.file_type,
                            isStored: true
                        })));
                        setSelectedFiles(latestDoc.files.map(f => f.id));
                        setRecipientEmails(latestDoc.recipients || []);
                        setShareConfig(prev => ({
                            ...prev,
                            dashboardAccess: latestDoc.access_type || 'once',
                            viewLimit: latestDoc.view_limit || 5,
                            canDownload: latestDoc.can_download !== undefined ? latestDoc.can_download : true,
                            allowAnonymous: latestDoc.allow_anonymous !== undefined ? latestDoc.allow_anonymous : true,
                            expirationDate: latestDoc.expires_at ? latestDoc.expires_at.split('T')[0] : ''
                        }));

                        const frontendUrl = window.location.origin;
                        setShareLink(`${frontendUrl}/shared/${latestDoc.share_token}`);
                        setShareToken(latestDoc.share_token);
                    }
                }
            } catch (err) {
                console.error('Failed to fetch project details:', err);
            }
        };

        fetchProjectDetails();
    }, [selectedProjectToken]);

    useEffect(() => { loadShareProjects(); }, []);

    const loadShareProjects = async () => {
        setLoadingProjects(true);
        try {
            const token = localStorage.getItem('token');
            const response = await fetch(API_ENDPOINTS.SHARE_PROJECTS, {
                headers: { 'Authorization': `Bearer ${token}` }
            });
            if (response.ok) {
                const data = await response.json();
                setShareProjects(data);
            }
        } catch (error) {
            console.error('Error loading share projects:', error);
        } finally {
            setLoadingProjects(false);
        }
    };

    const handleCreateProject = async () => {
        if (!projectName.trim()) { setProjectError('Project name is required'); return; }
        setCreatingProject(true);
        setProjectError('');
        try {
            let project;
            if (parentHandleCreateShareProject) {
                project = await parentHandleCreateShareProject(projectName.trim());
            } else {
                const token = localStorage.getItem('token');
                const response = await fetch(API_ENDPOINTS.SHARE_PROJECTS, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
                    body: JSON.stringify({ project_name: projectName.trim(), description: 'Shared Documents' })
                });
                if (!response.ok) {
                    const data = await response.json();
                    throw new Error(data.detail || 'Failed to create share project');
                }
                const data = await response.json();
                project = data.project;
                setShareProjects(prev => [project, ...prev]);
            }
            if (project) {
                setSelectedProjectToken(project.project_token);
                setProjectName('');
                setShowCreateModal(false);
                navigate(`/share-doc?step=1&project=${project.project_token}`);
            }
        } catch (err) {
            console.error(err);
            setProjectError(err.message || 'Failed to create project');
        } finally {
            setCreatingProject(false);
        }
    };

    const handleDragOver = (e) => { e.preventDefault(); setIsDragging(true); };
    const handleDragLeave = (e) => { e.preventDefault(); setIsDragging(false); };
    const handleDrop = (e) => {
        e.preventDefault();
        setIsDragging(false);
        handleFiles(Array.from(e.dataTransfer.files));
    };
    const handleFileInput = (e) => handleFiles(Array.from(e.target.files));

    const handleFiles = (files) => {
        const newFiles = files.map(file => ({
            id: Math.random().toString(36).substr(2, 9),
            file, name: file.name, size: file.size, type: file.type,
            uploadedAt: new Date().toISOString()
        }));
        setUploadedFiles(prev => [...prev, ...newFiles]);
        setSelectedFiles(prev => [...prev, ...newFiles.map(f => f.id)]);
    };

    const removeFile = (fileId) => {
        setUploadedFiles(prev => prev.filter(f => f.id !== fileId));
        setSelectedFiles(prev => prev.filter(id => id !== fileId));
    };

    const formatFileSize = (bytes) => {
        if (bytes === 0) return '0 Bytes';
        const k = 1024;
        const sizes = ['Bytes', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return Math.round(bytes / Math.pow(k, i) * 100) / 100 + ' ' + sizes[i];
    };

    const addEmailRecipient = () => {
        if (emailInput.trim() && /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(emailInput.trim())) {
            const email = emailInput.trim();
            setRecipientEmails(prev => [...prev, {
                email,
                access_level: recipientAccessLevel
            }]);
            setEmailInput('');
        }
    };

    const removeEmailRecipient = (indexToRemove) => {
        setRecipientEmails(prev => prev.filter((_, index) => index !== indexToRemove));
    };

    const handleShare = async () => {
        if (!selectedProjectToken || !selectedProjectToken.startsWith('share_')) {
            alert('Please select or create a valid Share Project first.');
            return;
        }
        setSharing(true);
        setShareError('');
        try {
            const token = localStorage.getItem('token');
            const formData = new FormData();
            uploadedFiles.forEach(fileObj => {
                if (selectedFiles.includes(fileObj.id) && fileObj.file) {
                    formData.append('files', fileObj.file);
                }
            });
            formData.append('config', JSON.stringify(shareConfig));
            formData.append('recipients', JSON.stringify(recipientEmails));
            if (selectedProjectToken) formData.append('project_token', selectedProjectToken);

            const response = await fetch(API_ENDPOINTS.SHARE_DOC, {
                method: 'POST',
                headers: { 'Authorization': `Bearer ${token}` },
                body: formData
            });
            if (!response.ok) throw new Error('Failed to generate share link');
            const data = await response.json();
            setShareLink(data.share_url);
            setShareToken(data.share_token);
            goToStep(4);
        } catch (error) {
            console.error('Error generating share link:', error);
            alert('Failed to generate share link. Please try again.');
        } finally {
            setSharing(false);
        }
    };

    const copyToClipboard = async (text) => {
        try {
            await navigator.clipboard.writeText(text);
            setCopySuccess(true);
            setTimeout(() => setCopySuccess(false), 2000);
        } catch (err) {
            console.error('Failed to copy:', err);
        }
    };

    const loadShareStats = async () => {
        if (!shareToken) return;
        setLoadingStats(true);
        try {
            const token = localStorage.getItem('token');
            const response = await fetch(`${API_ENDPOINTS.SHARE_DOC_STATS}?token=${shareToken}`, {
                headers: { 'Authorization': `Bearer ${token}` }
            });
            if (response.ok) {
                const data = await response.json();
                setShareStats(data);
            }
        } catch (error) {
            console.error('Error loading stats:', error);
        } finally {
            setLoadingStats(false);
        }
    };

    useEffect(() => {
        if (currentStep === 4 && shareToken) {
            loadShareStats();
            const interval = setInterval(loadShareStats, 15000);
            return () => clearInterval(interval);
        }
    }, [currentStep, shareToken]);

    const goToStep = (step) => {
        const params = new URLSearchParams();
        params.set('step', step.toString());
        if (selectedProjectToken) {
            params.set('project', selectedProjectToken);
        }
        navigate(`/share-doc?${params.toString()}`);
    };

    const formatTimeAgo = (dateString) => {
        if (!dateString) return 'Never';
        const diff = Date.now() - new Date(dateString).getTime();
        const mins = Math.floor(diff / 60000);
        if (mins < 1) return 'Just now';
        if (mins < 60) return `${mins}m ago`;
        const hrs = Math.floor(mins / 60);
        if (hrs < 24) return `${hrs}h ago`;
        return `${Math.floor(hrs / 24)}d ago`;
    };

    const formatDateTime = (dateString) => {
        if (!dateString) return '—';
        return new Date(dateString).toLocaleString('en-US', {
            month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit'
        });
    };

    // Build per-recipient stats from access_log
    const getRecipientStats = () => {
        const statsMap = {};
        recipientEmails.forEach(recipient => {
            const email = typeof recipient === 'string' ? recipient : recipient.email;
            statsMap[email] = { views: 0, downloads: 0, lastAccess: null, locations: [] };
        });

        if (shareStats?.access_log) {
            shareStats.access_log.forEach(log => {
                // Include all views including dashboard
                const email = log.email || log.user_email;
                if (email && statsMap[email]) {
                    if (log.action === 'download') {
                        statsMap[email].downloads++;
                    } else {
                        statsMap[email].views++;
                    }
                    if (!statsMap[email].lastAccess || new Date(log.accessed_at) > new Date(statsMap[email].lastAccess)) {
                        statsMap[email].lastAccess = log.accessed_at;
                    }
                    if (log.ip_address && !statsMap[email].locations.includes(log.ip_address)) {
                        statsMap[email].locations.push(log.ip_address);
                    }
                }
            });
        }
        return statsMap;
    };

    const totalViews = (shareStats?.access_log || []).filter(l => l.action === 'view').length;
    const totalDownloads = shareStats?.download_count || 0;
    const recipientStats = getRecipientStats();
    const engagedCount = Object.values(recipientStats).filter(s => s.views > 0 || s.downloads > 0).length;

    return (
        <div className="h-screen overflow-y-auto bg-app-bg-page">
            <div className="bg-app-bg-card border-b border-app-border">
                <RoadmapHeader
                    steps={roadmapSteps}
                    currentStep={currentStep}
                    selectedProjectKey={selectedProjectToken}
                />
            </div>

            <div className="max-w-5xl mx-auto px-4 py-1">

                {/* Step 0: Project Details */}
                {currentStep === 0 && (
                    <div className="max-w-4xl mx-auto py-8 animate-in fade-in slide-in-from-bottom-2 duration-500">
                        <div className="bg-app-bg-card/90 backdrop-blur-xl rounded-2xl shadow-lg shadow-app-bg-hover/40 border border-app-border-light overflow-hidden relative">
                            <div className="absolute top-0 left-0 right-0 h-[3px] bg-gradient-to-r from-app-primary via-app-primary to-purple-500" />
                            <div className="p-6 sm:p-8">
                                <div className="mb-6">
                                    <h2 className="text-xl font-bold text-app-text-main mb-1.5 tracking-tight">Project Details</h2>
                                    <p className="text-app-text-light text-sm leading-relaxed">Give your project a descriptive name to get started.</p>
                                </div>
                                <div className="space-y-4">
                                    <div>
                                        <label className="block text-[11px] font-bold text-app-text-muted mb-2 uppercase tracking-widest">
                                            Project Name <span className="text-red-400">*</span>
                                        </label>
                                        <div className="relative group">
                                            <input
                                                type="text"
                                                value={projectName}
                                                onChange={(e) => { setProjectName(e.target.value); if (projectError) setProjectError(''); }}
                                                autoFocus
                                                onKeyDown={(e) => e.key === 'Enter' && handleCreateProject()}
                                                placeholder="e.g. Customer Analytics Platform"
                                                className="w-full px-4 py-3 border-2 border-app-border rounded-xl focus:ring-4 focus:ring-app-primary-light focus:border-blue-400 text-sm bg-app-bg-page/50 text-app-text-main transition-all duration-200 placeholder:text-app-border hover:border-app-border font-medium"
                                            />
                                        </div>
                                        <p className="text-[11px] text-app-text-light mt-2 ml-1">This name will be used to identify the project</p>
                                    </div>
                                    {projectError && <p className="text-red-400 text-[10px] font-bold uppercase tracking-wider">{projectError}</p>}
                                    <div className="flex justify-end pt-2">
                                        <button
                                            onClick={handleCreateProject}
                                            disabled={creatingProject || !projectName.trim()}
                                            className="px-8 py-3 font-bold text-white bg-app-primary hover:bg-app-primary-hover rounded-xl transition-all shadow-lg shadow-app-primary/20 hover:shadow-app-primary/40 disabled:opacity-50 disabled:cursor-not-allowed flex justify-center items-center gap-2 group transform active:scale-[0.98]"
                                        >
                                            {creatingProject ? (
                                                <div className="w-5 h-5 border-3 border-white/20 border-t-white rounded-full animate-spin" />
                                            ) : (
                                                <><span>Continue</span><ArrowRight className="w-4 h-4 group-hover:translate-x-1 transition-transform" /></>
                                            )}
                                        </button>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                )}

                {/* Step 1: Upload Documents */}
                {currentStep === 1 && (
                    <div className="space-y-4 animate-in fade-in slide-in-from-bottom-2 duration-400">
                        <div className="flex items-center justify-between">
                            <div>
                                <h2 className="text-xl font-bold text-app-text-main">Upload Documents</h2>
                                <p className="text-xs text-app-text-muted">Attach files you want to share with recipients</p>
                            </div>
                        </div>

                        <div
                            onDragOver={handleDragOver}
                            onDragLeave={handleDragLeave}
                            onDrop={handleDrop}
                            className={`border-2 border-dashed rounded-xl p-6 text-center transition-all ${isDragging ? 'border-app-primary bg-app-primary/5' : 'border-app-border bg-app-bg-card hover:border-app-primary/40'}`}
                        >
                            <Upload className="w-12 h-12 mx-auto mb-3 text-app-text-muted opacity-60" />
                            <p className="text-base font-semibold text-app-text-main mb-1">Drop files here or click to browse</p>
                            <input type="file" multiple onChange={handleFileInput} className="hidden" id="file-upload" accept=".pdf,.doc,.docx,.txt,.md,.xlsx,.xls,.ppt,.pptx" />
                            <label htmlFor="file-upload" className="inline-flex items-center px-5 py-2.5 bg-app-primary/10 text-app-primary border border-app-primary/20 rounded-lg hover:bg-app-primary hover:text-white transition-all cursor-pointer font-bold text-sm mt-2">
                                <Upload className="w-4 h-4 mr-2" />Select Files
                            </label>
                            <p className="text-[10px] text-app-text-muted mt-4 opacity-70 italic">Supports: PDF, DOCX, TXT, Excel, PPT</p>
                        </div>

                        {uploadedFiles.length > 0 && (
                            <div className="bg-app-bg-card rounded-xl border border-app-border p-4">
                                <h3 className="text-xs font-bold text-app-text-muted uppercase tracking-wider mb-3">Attached Files ({uploadedFiles.length})</h3>
                                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                                    {uploadedFiles.map(file => (
                                        <div key={file.id} className="flex items-center justify-between px-3 py-2 bg-app-bg-page border border-app-border rounded-lg group hover:border-app-primary/40 transition-colors">
                                            <div className="flex items-center gap-2.5 min-w-0">
                                                <div className="w-8 h-8 rounded-lg bg-app-primary/5 flex items-center justify-center flex-shrink-0">
                                                    <FileText className="w-4 h-4 text-app-primary" />
                                                </div>
                                                <div className="min-w-0">
                                                    <p className="text-xs font-semibold text-app-text-main truncate max-w-[120px]">{file.name}</p>
                                                    <p className="text-[10px] text-app-text-muted">{formatFileSize(file.size)}</p>
                                                </div>
                                            </div>
                                            <button onClick={() => removeFile(file.id)} className="p-1.5 text-app-text-muted hover:text-red-400 hover:bg-red-400/10 rounded-md transition-colors opacity-0 group-hover:opacity-100">
                                                <Trash2 className="w-3.5 h-3.5" />
                                            </button>
                                        </div>
                                    ))}
                                </div>
                            </div>
                        )}

                        <div className="flex justify-end pt-2">
                            <button
                                onClick={() => goToStep(2)}
                                disabled={uploadedFiles.length === 0}
                                className="px-6 py-2.5 bg-app-primary text-white rounded-lg hover:bg-app-primary-hover transition-all font-bold text-sm shadow-md shadow-app-primary/20 disabled:opacity-50 disabled:grayscale"
                            >
                                Continue to Access Control
                            </button>
                        </div>
                    </div>
                )}

                {/* Step 2: Configure Access */}
                {currentStep === 2 && (
                    <div className="space-y-6 animate-in fade-in slide-in-from-bottom-2 duration-400">
                        <div className="flex items-center justify-between">
                            <div>
                                <h2 className="text-xl font-bold text-app-text-main">Access Control</h2>
                                <p className="text-xs text-app-text-muted">Define how recipients can interact with your shared documents</p>
                            </div>
                        </div>

                        <div className="grid grid-cols-1 gap-6">
                            {/* Dashboard Access / Persistence */}
                            <div className="bg-app-bg-card/50 backdrop-blur-md p-6 rounded-2xl border border-app-border shadow-sm flex flex-col gap-4">
                                <label className="text-[11px] font-bold text-app-text-muted uppercase tracking-widest flex items-center gap-2">
                                    <Clock className="w-3.5 h-3.5 text-app-primary" /> Share Persistence
                                </label>

                                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                    {/* Limited View Option */}
                                    <div
                                        onClick={() => setShareConfig(prev => ({ ...prev, dashboardAccess: 'once' }))}
                                        className={`p-4 rounded-xl border transition-all cursor-pointer flex flex-col justify-between ${shareConfig.dashboardAccess === 'once' ? 'bg-app-primary/5 border-app-primary/40 ring-1 ring-app-primary/20' : 'bg-app-bg-page border-app-border hover:border-app-primary/20'}`}
                                    >
                                        <div className="flex items-center justify-between mb-2">
                                            <div className="flex items-start gap-3">
                                                <div className={`mt-0.5 w-4 h-4 rounded-full border-2 flex items-center justify-center transition-all ${shareConfig.dashboardAccess === 'once' ? 'border-app-primary' : 'border-app-border'}`}>
                                                    {shareConfig.dashboardAccess === 'once' && <div className="w-2 h-2 rounded-full bg-app-primary" />}
                                                </div>
                                                <div>
                                                    <p className="text-sm font-bold text-app-text-main">Limited View</p>
                                                    <p className="text-[10px] text-app-text-muted">Expires after a set number of days</p>
                                                </div>
                                            </div>
                                            <Clock className={`w-4 h-4 transition-colors ${shareConfig.dashboardAccess === 'once' ? 'text-app-primary' : 'text-app-text-muted opacity-20'}`} />
                                        </div>

                                        {shareConfig.dashboardAccess === 'once' && (
                                            <div className="mt-4 animate-in slide-in-from-top-2 duration-200" onClick={(e) => e.stopPropagation()}>
                                                <div className="flex items-center gap-2">
                                                    <div className="flex flex-col gap-1 flex-1">
                                                        <div className="flex items-center gap-2 bg-app-bg-card border border-app-border rounded-lg px-2 py-1.5 group relative">
                                                            <span className="text-[8px] font-bold text-app-text-muted uppercase tracking-tighter whitespace-nowrap">Days:</span>
                                                            <input
                                                                type="number"
                                                                min="1"
                                                                max="365"
                                                                value={shareConfig.expirationDays || 7}
                                                                onChange={(e) => setShareConfig(prev => ({ ...prev, expirationDays: parseInt(e.target.value) || 1 }))}
                                                                className="w-full bg-transparent border-none text-center text-xs font-bold text-app-primary p-0 focus:ring-0"
                                                            />
                                                            <div className="absolute -top-8 left-1/2 -translate-x-1/2 px-2 py-1 bg-app-text-main text-white text-[8px] rounded opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none whitespace-nowrap z-10">
                                                                Days until link expires
                                                            </div>
                                                        </div>
                                                    </div>

                                                    <div className="flex flex-col gap-1 flex-1">
                                                        <div className="flex items-center gap-2 bg-app-bg-card border border-app-border rounded-lg px-2 py-1.5 group relative">
                                                            <span className="text-[8px] font-bold text-app-text-muted uppercase tracking-tighter whitespace-nowrap">Opens:</span>
                                                            <input
                                                                type="number"
                                                                min="1"
                                                                max="1000"
                                                                value={shareConfig.viewLimit || 5}
                                                                onChange={(e) => setShareConfig(prev => ({ ...prev, viewLimit: parseInt(e.target.value) || 1 }))}
                                                                className="w-full bg-transparent border-none text-center text-xs font-bold text-app-primary p-0 focus:ring-0"
                                                            />
                                                            <div className="absolute -top-8 left-1/2 -translate-x-1/2 px-2 py-1 bg-app-text-main text-white text-[8px] rounded opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none whitespace-nowrap z-10">
                                                                Total views allowed
                                                            </div>
                                                        </div>
                                                    </div>
                                                </div>
                                            </div>
                                        )}
                                    </div>

                                    {/* Indefinite Access Option */}
                                    <div
                                        onClick={() => setShareConfig(prev => ({ ...prev, dashboardAccess: 'always' }))}
                                        className={`flex items-center justify-between p-4 rounded-xl border transition-all cursor-pointer ${shareConfig.dashboardAccess === 'always' ? 'bg-app-primary/5 border-app-primary/40 ring-1 ring-app-primary/20' : 'bg-app-bg-page border-app-border hover:border-app-primary/20'}`}
                                    >
                                        <div className="flex items-start gap-3">
                                            <div className={`mt-0.5 w-4 h-4 rounded-full border-2 flex items-center justify-center transition-all ${shareConfig.dashboardAccess === 'always' ? 'border-app-primary' : 'border-app-border'}`}>
                                                {shareConfig.dashboardAccess === 'always' && <div className="w-2 h-2 rounded-full bg-app-primary" />}
                                            </div>
                                            <div>
                                                <p className="text-sm font-bold text-app-text-main">Indefinite Access</p>
                                                <p className="text-[10px] text-app-text-muted">Stay active indefinitely until manual removal</p>
                                            </div>
                                        </div>
                                        <Activity className={`w-4 h-4 transition-colors ${shareConfig.dashboardAccess === 'always' ? 'text-app-primary' : 'text-app-text-muted opacity-20'}`} />
                                    </div>
                                </div>

                            </div>

                            {/* Features Box */}
                            <div className="bg-app-bg-card/50 backdrop-blur-md p-6 rounded-2xl border border-app-border shadow-sm space-y-5">
                                <label className="text-[11px] font-bold text-app-text-muted uppercase tracking-widest flex items-center gap-2">
                                    <Shield className="w-3.5 h-3.5 text-app-primary" /> Advanced Features
                                </label>

                                <div className="space-y-4">
                                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                        {/* Password Protection */}
                                        <div className={`p-4 rounded-xl border transition-all ${shareConfig.requirePassword ? 'bg-app-primary/5 border-app-primary/30' : 'bg-app-bg-page/50 border-app-border'}`}>
                                            <div className="flex items-center justify-between mb-3">
                                                <div className="flex items-center gap-3">
                                                    <div className={`w-8 h-8 rounded-lg flex items-center justify-center transition-colors ${shareConfig.requirePassword ? 'bg-app-primary text-white' : 'bg-app-border/30 text-app-text-muted'}`}>
                                                        <Lock className="w-4 h-4" />
                                                    </div>
                                                    <div>
                                                        <p className="text-xs font-bold text-app-text-main">Password Protection</p>
                                                        <p className="text-[9px] text-app-text-muted">Require password to access content</p>
                                                    </div>
                                                </div>
                                                <button
                                                    onClick={() => setShareConfig(prev => ({ ...prev, requirePassword: !prev.requirePassword }))}
                                                    className={`relative inline-flex h-5 w-10 items-center rounded-full transition-all duration-300 ${shareConfig.requirePassword ? 'bg-app-primary' : 'bg-app-border'}`}
                                                >
                                                    <span className={`inline-block h-3.5 w-3.5 transform rounded-full bg-white transition-transform duration-300 ${shareConfig.requirePassword ? 'translate-x-5.5' : 'translate-x-1'}`} />
                                                </button>
                                            </div>

                                            {shareConfig.requirePassword && (
                                                <div className="animate-in slide-in-from-top-2 duration-300">
                                                    <div className="relative">
                                                        <input
                                                            type="text"
                                                            value={shareConfig.password}
                                                            onChange={(e) => setShareConfig(prev => ({ ...prev, password: e.target.value }))}
                                                            placeholder="Create a strong password"
                                                            className="w-full px-4 py-2 bg-app-bg-card border border-app-border rounded-lg text-xs text-app-text-main font-mono placeholder:font-sans focus:ring-2 focus:ring-app-primary/20 focus:border-app-primary/40 transition-all shadow-inner"
                                                        />
                                                        <button
                                                            onClick={() => setShareConfig(prev => ({ ...prev, password: Math.random().toString(36).slice(-8) }))}
                                                            className="absolute right-2 top-1/2 -translate-y-1/2 p-1 text-app-primary hover:bg-app-primary/10 rounded-md transition-colors"
                                                            title="Generate random password"
                                                        >
                                                            <RefreshCw className="w-3 h-3" />
                                                        </button>
                                                    </div>
                                                </div>
                                            )}
                                        </div>

                                        {/* Auto-Expiration Date */}
                                        <div className="p-4 rounded-xl border border-app-border bg-app-bg-page/50 flex flex-col gap-3 justify-center">
                                            <div className="flex items-center gap-3">
                                                <div className="w-8 h-8 bg-app-primary/10 rounded-lg flex items-center justify-center">
                                                    <Calendar className="w-4 h-4 text-app-primary" />
                                                </div>
                                                <div>
                                                    <p className="text-xs font-bold text-app-text-main">Auto-Expiration Date</p>
                                                    <p className="text-[9px] text-app-text-muted">Specific date for link deactivation</p>
                                                </div>
                                            </div>
                                            <div className="relative group">
                                                <input
                                                    type="date"
                                                    value={shareConfig.expirationDate || ''}
                                                    onChange={(e) => setShareConfig(prev => ({ ...prev, expirationDate: e.target.value }))}
                                                    className="w-full px-4 py-2 bg-app-bg-card border border-app-border rounded-lg text-xs text-app-text-main font-medium focus:ring-2 focus:ring-app-primary/20 focus:border-app-primary/40 transition-all appearance-none cursor-pointer"
                                                />
                                                <Calendar className="absolute right-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-app-text-muted pointer-events-none group-hover:text-app-primary transition-colors" />
                                            </div>
                                        </div>
                                    </div>

                                </div>
                            </div>
                        </div>

                        <div className="flex justify-between items-center pt-4">
                            <button onClick={() => goToStep(1)} className="px-6 py-2.5 text-sm font-bold text-app-text-muted hover:text-app-text-main transition-all flex items-center gap-2 group">
                                <ArrowRight className="w-4 h-4 rotate-180 group-hover:-translate-x-1 transition-transform" /> Back
                            </button>
                            <button
                                onClick={() => goToStep(3)}
                                className="px-10 py-3 bg-app-primary text-white rounded-xl hover:bg-app-primary-hover transition-all font-bold text-sm shadow-xl shadow-app-primary/20 hover:shadow-app-primary/30 transform active:scale-[0.98]"
                            >
                                Continue to Invite
                            </button>
                        </div>
                    </div>
                )}

                {/* Step 3: Share & Invite */}
                {currentStep === 3 && (
                    <div className="space-y-6 animate-in fade-in slide-in-from-bottom-2 duration-400">
                        <div>
                            <h2 className="text-xl font-bold text-app-text-main">Invite Recipients</h2>
                            <p className="text-xs text-app-text-muted">Send unique tracking links and configure individual download permissions</p>
                        </div>

                        {/* Anonymous Access Section */}
                        <div className={`bg-app-bg-card/80 backdrop-blur-sm p-6 rounded-2xl border transition-all duration-500 ${shareConfig.allowAnonymous ? 'border-app-primary/30 shadow-md shadow-app-primary/5' : 'border-app-border opacity-80'}`}>
                            <div className="flex items-center justify-between mb-4">
                                <div className="flex items-center gap-4">
                                    <div className={`w-12 h-12 rounded-2xl flex items-center justify-center transition-all duration-500 ${shareConfig.allowAnonymous ? 'bg-app-primary text-white shadow-lg shadow-app-primary/30 rotate-0' : 'bg-app-bg-page text-app-text-muted rotate-12'}`}>
                                        <Globe className="w-6 h-6" />
                                    </div>
                                    <div>
                                        <h3 className="text-base font-bold text-app-text-main">Anonymous Access Link</h3>
                                        <p className="text-xs text-app-text-muted">Publicly shareable link for broad distribution</p>
                                    </div>
                                </div>
                                <button
                                    onClick={() => setShareConfig(prev => ({ ...prev, allowAnonymous: !prev.allowAnonymous }))}
                                    className={`relative inline-flex h-6 w-12 items-center rounded-full transition-all duration-500 ${shareConfig.allowAnonymous ? 'bg-app-primary' : 'bg-app-border'}`}
                                >
                                    <span className={`inline-block h-4.5 w-4.5 transform rounded-full bg-white transition-transform duration-500 ${shareConfig.allowAnonymous ? 'translate-x-6.5' : 'translate-x-1'}`} />
                                </button>
                            </div>

                            {shareConfig.allowAnonymous && (
                                <div className="space-y-4 animate-in fade-in slide-in-from-top-4 duration-500 delay-100">
                                    <div className="flex flex-col sm:flex-row gap-4">
                                        <div className="flex-1 flex items-center gap-3 bg-app-bg-page/50 border border-dashed border-app-primary/30 rounded-xl px-4 py-3 group">
                                            <Link2 className="w-4 h-4 text-app-primary" />
                                            <span className="text-xs text-app-text-main truncate font-mono select-all">
                                                {shareLink || 'Link will be generated on share'}
                                            </span>
                                            {shareLink && (
                                                <button onClick={() => copyToClipboard(shareLink)} className="p-2 text-app-primary hover:bg-app-primary/10 rounded-lg transition-all active:scale-90">
                                                    {copySuccess ? <CheckCircle className="w-4 h-4 text-green-500" /> : <Copy className="w-4 h-4" />}
                                                </button>
                                            )}
                                        </div>

                                        <div className="flex items-center gap-4 bg-app-bg-page/80 border border-app-border rounded-xl px-4 py-2">
                                            <div className="flex items-center gap-2">
                                                <Download className={`w-3.5 h-3.5 transition-colors ${shareConfig.canDownload ? 'text-green-500' : 'text-app-text-muted'}`} />
                                                <span className="text-[11px] font-bold text-app-text-main whitespace-nowrap">Downloads</span>
                                            </div>
                                            <button
                                                onClick={() => setShareConfig(prev => ({ ...prev, canDownload: !prev.canDownload }))}
                                                className={`relative inline-flex h-4 w-8 items-center rounded-full transition-all duration-300 ${shareConfig.canDownload ? 'bg-green-500' : 'bg-app-border'}`}
                                            >
                                                <span className={`inline-block h-2.5 w-2.5 transform rounded-full bg-white transition-transform duration-300 ${shareConfig.canDownload ? 'translate-x-4.5' : 'translate-x-1'}`} />
                                            </button>
                                        </div>
                                    </div>
                                </div>
                            )}
                        </div>

                        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
                            {/* Personal Invitations */}
                            <div className="lg:col-span-12 space-y-4">
                                <div className="bg-app-bg-card p-6 rounded-2xl border border-app-border shadow-sm space-y-6">
                                    <div className="flex items-center justify-between">
                                        <h3 className="text-sm font-bold text-app-text-main flex items-center gap-2 uppercase tracking-wider">
                                            <Users className="w-4 h-4 text-app-primary" /> Other Invities
                                        </h3>
                                        <span className="text-[10px] font-bold text-app-text-muted bg-app-bg-page px-2 py-0.5 rounded-full border border-app-border">
                                            {recipientEmails.length} recipients
                                        </span>
                                    </div>

                                    <div className="flex flex-col gap-3">
                                        <div className="flex items-center gap-3 px-4 py-3 bg-app-bg-page border border-app-border rounded-xl focus-within:ring-2 focus-within:ring-app-primary/20 focus-within:border-app-primary/40 transition-all shadow-inner group">
                                            <Mail className="w-4 h-4 text-app-text-muted group-focus-within:text-app-primary transition-colors" />
                                            <input
                                                type="email"
                                                value={emailInput}
                                                onChange={(e) => setEmailInput(e.target.value)}
                                                onKeyDown={(e) => e.key === 'Enter' && addEmailRecipient()}
                                                placeholder="Enter recipient email address..."
                                                className="flex-1 bg-transparent border-none p-0 text-xs text-app-text-main placeholder:text-app-text-muted/40 focus:ring-0"
                                            />
                                        </div>

                                        <div className="flex items-center justify-between gap-3">
                                            <div className="flex items-center gap-4 bg-app-bg-page border border-app-border rounded-xl px-4 py-2.5">
                                                <div className="flex items-center gap-2">
                                                    <Download className={`w-3.5 h-3.5 transition-colors ${recipientAccessLevel === 'download' ? 'text-green-500' : 'text-app-text-muted'}`} />
                                                    <span className="text-[11px] font-bold text-app-text-main">Allow Download</span>
                                                </div>
                                                <button
                                                    onClick={() => setRecipientAccessLevel(prev => prev === 'download' ? 'view' : 'download')}
                                                    className={`relative inline-flex h-4 w-8 items-center rounded-full transition-all duration-300 ${recipientAccessLevel === 'download' ? 'bg-green-500' : 'bg-app-border'}`}
                                                >
                                                    <span className={`inline-block h-2.5 w-2.5 transform rounded-full bg-white transition-transform duration-300 ${recipientAccessLevel === 'download' ? 'translate-x-4.5' : 'translate-x-1'}`} />
                                                </button>
                                            </div>

                                            <button
                                                onClick={addEmailRecipient}
                                                disabled={!emailInput.trim()}
                                                className="px-6 py-2.5 bg-app-primary text-white rounded-xl hover:bg-app-primary-hover disabled:opacity-50 disabled:grayscale transition-all font-bold text-xs flex items-center gap-2 shadow-lg shadow-app-primary/20 active:scale-[0.98]"
                                            >
                                                <PlusCircle className="w-4 h-4" /> Add Recipient
                                            </button>
                                        </div>
                                    </div>

                                    <div className="space-y-2 max-h-[300px] overflow-y-auto pr-2 custom-scrollbar animate-in fade-in duration-500">
                                        {recipientEmails.length > 0 ? (
                                            recipientEmails.map((recipient, index) => (
                                                <div key={index} className="flex items-center justify-between p-3.5 bg-app-bg-page/40 border border-app-border rounded-xl group hover:border-app-primary/30 hover:bg-app-bg-page transition-all duration-200">
                                                    <div className="flex items-center gap-4 min-w-0">
                                                        <div className="w-10 h-10 rounded-xl bg-app-primary/10 flex items-center justify-center text-sm font-bold text-app-primary flex-shrink-0 group-hover:scale-105 transition-transform">
                                                            {recipient.email[0].toUpperCase()}
                                                        </div>
                                                        <div className="min-w-0">
                                                            <p className="text-sm font-bold text-app-text-main truncate">{recipient.email}</p>
                                                            <div className="flex items-center gap-2 mt-0.5">
                                                                <span className={`text-[9px] px-2 py-0.5 rounded-full font-bold uppercase tracking-tighter ${recipient.access_level === 'download' ? 'bg-green-500/10 text-green-500 border border-green-500/20' : 'bg-blue-500/10 text-blue-500 border border-blue-500/20'}`}>
                                                                    {recipient.access_level === 'download' ? 'Download' : 'View Only'}
                                                                </span>
                                                            </div>
                                                        </div>
                                                    </div>

                                                    <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                                                        <button
                                                            onClick={() => {
                                                                const newLevel = recipient.access_level === 'download' ? 'view' : 'download';
                                                                setRecipientEmails(prev => prev.map((r, i) => i === index ? { ...r, access_level: newLevel } : r));
                                                            }}
                                                            className="p-2 text-app-text-muted hover:text-app-primary hover:bg-app-primary/10 rounded-lg transition-all"
                                                            title="Toggle Download Permission"
                                                        >
                                                            <RefreshCw className="w-3.5 h-3.5" />
                                                        </button>
                                                        <button
                                                            onClick={() => removeEmailRecipient(index)}
                                                            className="p-2 text-app-text-muted hover:text-red-400 hover:bg-red-400/10 rounded-lg transition-all"
                                                        >
                                                            <X className="w-4 h-4" />
                                                        </button>
                                                    </div>
                                                </div>
                                            ))
                                        ) : (
                                            <div className="py-12 text-center border-2 border-dashed border-app-border rounded-2xl bg-app-bg-page/20">
                                                <Users className="w-10 h-10 mx-auto mb-3 text-app-text-muted opacity-20" />
                                                <p className="text-xs text-app-text-muted font-medium">No personal invites added yet</p>
                                            </div>
                                        )}
                                    </div>
                                </div>
                            </div>
                        </div>

                        {/* Share Summary at bottom */}
                        <div className="mt-8 animate-in fade-in slide-in-from-bottom-4 duration-500">
                            <div className="bg-app-bg-card p-8 rounded-3xl border border-app-border shadow-xl shadow-app-primary/5">
                                <div className="flex flex-col lg:flex-row gap-8">
                                    <div className="flex-1 space-y-6">
                                        <h3 className="text-[11px] font-bold text-app-text-muted uppercase tracking-widest flex items-center gap-2">
                                            <FileText className="w-4 h-4 text-app-primary" /> Final Review Summary
                                        </h3>

                                        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                                            <div className="bg-app-bg-page/50 rounded-2xl p-5 border border-app-border flex flex-col gap-3">
                                                <span className="text-[10px] font-bold text-app-text-muted uppercase tracking-tighter">Documents</span>
                                                <div className="space-y-2 max-h-32 overflow-y-auto pr-2 custom-scrollbar">
                                                    {uploadedFiles.filter(f => selectedFiles.includes(f.id)).map(file => (
                                                        <div key={file.id} className="flex items-center gap-3 p-2 bg-app-bg-card/50 border border-app-border rounded-xl">
                                                            <FileText className="w-3.5 h-3.5 text-app-primary" />
                                                            <p className="text-[11px] font-bold text-app-text-main truncate">{file.name}</p>
                                                        </div>
                                                    ))}
                                                </div>
                                            </div>

                                            <div className="bg-app-bg-page/50 rounded-2xl p-5 border border-app-border space-y-4">
                                                <div>
                                                    <p className="text-[10px] font-bold text-app-text-muted uppercase tracking-tighter mb-1">Persistence</p>
                                                    <p className="text-sm font-bold text-app-text-main">
                                                        {shareConfig.dashboardAccess === 'once' ? (
                                                            <span>{shareConfig.expirationDays || 7} Days / {shareConfig.viewLimit || 5} Opens</span>
                                                        ) : (
                                                            'Indefinite Access'
                                                        )}
                                                    </p>
                                                </div>
                                                <div>
                                                    <p className="text-[10px] font-bold text-app-text-muted uppercase tracking-tighter mb-1">Security</p>
                                                    <p className="text-sm font-bold text-app-text-main">
                                                        {shareConfig.requirePassword ? 'Password Protected' : 'No Password Required'}
                                                    </p>
                                                </div>
                                            </div>

                                            <div className="bg-app-bg-page/50 rounded-2xl p-5 border border-app-border space-y-4">
                                                <div>
                                                    <p className="text-[10px] font-bold text-app-text-muted uppercase tracking-tighter mb-1">Recipients</p>
                                                    <p className="text-sm font-bold text-app-text-main">
                                                        {recipientEmails.length} Email Invites
                                                    </p>
                                                </div>
                                                <div>
                                                    <p className="text-[10px] font-bold text-app-text-muted uppercase tracking-tighter mb-1">Anonymous Access</p>
                                                    <p className="text-sm font-bold text-app-text-main">
                                                        {shareConfig.allowAnonymous ? 'Enabled' : 'Disabled'}
                                                    </p>
                                                </div>
                                            </div>
                                        </div>
                                    </div>

                                    <div className="lg:w-80 flex flex-col justify-center gap-4 lg:border-l lg:border-app-border lg:pl-8">
                                        <p className="text-[11px] text-app-text-muted italic leading-relaxed text-center lg:text-left">
                                            Unique tracking links will be sent to each recipient. Both public and private links use their own individual access permissions.
                                        </p>
                                        <div className="flex flex-col gap-3">
                                            <button
                                                onClick={handleShare}
                                                disabled={sharing || (recipientEmails.length === 0 && !shareConfig.allowAnonymous)}
                                                className="w-full py-4 bg-gradient-to-r from-app-primary to-blue-600 hover:from-app-primary-hover hover:to-blue-700 text-white rounded-2xl transition-all font-bold text-sm shadow-xl shadow-app-primary/20 flex items-center justify-center gap-3 transform active:scale-[0.98] disabled:opacity-50 disabled:grayscale"
                                            >
                                                {sharing ? <div className="w-5 h-5 border-3 border-white/20 border-t-white rounded-full animate-spin" /> : <><Send className="w-4 h-4" /> Share & Invite Now</>}
                                            </button>
                                            <button onClick={() => goToStep(2)} className="w-full py-2.5 text-xs font-bold text-app-text-muted hover:text-app-text-main hover:bg-app-bg-page rounded-xl transition-all">
                                                Adjust Settings
                                            </button>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                )}

                {/* ─────────────────────────────────────────────────────────────
                    Step 5: Track Status — Redesigned Dashboard
                ───────────────────────────────────────────────────────────── */}
                {currentStep === 4 && (
                    <div className="py-4 space-y-4">

                        {/* ── Success banner + share link ── */}
                        <div className="bg-app-bg-card border border-app-border rounded-xl overflow-hidden">
                            {/* Top accent */}
                            <div className="h-1 bg-gradient-to-r from-green-500 via-emerald-400 to-teal-400" />
                            <div className="px-5 py-4 flex flex-col sm:flex-row sm:items-center gap-4">
                                <div className="flex items-center gap-3 flex-1 min-w-0">
                                    <div className="w-9 h-9 bg-green-500/10 rounded-lg flex items-center justify-center flex-shrink-0">
                                        <CheckCircle className="w-5 h-5 text-green-400" />
                                    </div>
                                    <div className="min-w-0">
                                        <p className="text-sm font-semibold text-app-text-main">Documents Shared Successfully</p>
                                        <p className="text-xs text-app-text-muted">Invite emails sent · Link is active</p>
                                    </div>
                                </div>

                                {shareLink && (
                                    <div className="flex items-center gap-2 flex-1 min-w-0 sm:max-w-md">
                                        <div className="flex-1 min-w-0 flex items-center gap-2 px-3 py-2 bg-app-bg-page border border-app-border rounded-lg">
                                            <Link2 className="w-3.5 h-3.5 text-app-text-muted flex-shrink-0" />
                                            <span className="text-xs text-app-text-muted truncate flex-1">{shareLink}</span>
                                        </div>
                                        <button
                                            onClick={() => copyToClipboard(shareLink)}
                                            className={`flex items-center gap-1.5 px-3 py-2 rounded-lg text-xs font-medium transition-all flex-shrink-0 ${copySuccess ? 'bg-green-500/10 text-green-400 border border-green-500/20' : 'bg-app-primary text-white hover:bg-app-primary-hover'}`}
                                        >
                                            {copySuccess ? <><CheckCircle className="w-3.5 h-3.5" />Copied</> : <><Copy className="w-3.5 h-3.5" />Copy</>}
                                        </button>
                                        <a href={shareLink} target="_blank" rel="noopener noreferrer"
                                            className="p-2 border border-app-border rounded-lg text-app-text-muted hover:text-app-text-main hover:bg-app-bg-hover transition-colors flex-shrink-0">
                                            <ExternalLink className="w-3.5 h-3.5" />
                                        </a>
                                    </div>
                                )}
                            </div>
                        </div>

                        {/* ── Metric cards ── */}
                        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
                            {[
                                {
                                    label: 'Documents', value: uploadedFiles.length,
                                    icon: FileText, color: 'text-blue-400', bg: 'bg-blue-400/10'
                                },
                                {
                                    label: 'Recipients', value: recipientEmails.length,
                                    icon: Users, color: 'text-purple-400', bg: 'bg-purple-400/10'
                                },
                                {
                                    label: 'Total Views', value: totalViews,
                                    icon: Eye, color: 'text-emerald-400', bg: 'bg-emerald-400/10',
                                    sub: `${engagedCount} engaged`
                                },
                                {
                                    label: 'Downloads',
                                    value: (!shareConfig.canDownload && !recipientEmails.some(r => r.access_level === 'download')) ? 'Blocked' : totalDownloads,
                                    icon: (!shareConfig.canDownload && !recipientEmails.some(r => r.access_level === 'download')) ? Lock : Download,
                                    color: (!shareConfig.canDownload && !recipientEmails.some(r => r.access_level === 'download')) ? 'text-red-400' : 'text-amber-400',
                                    bg: (!shareConfig.canDownload && !recipientEmails.some(r => r.access_level === 'download')) ? 'bg-red-400/10' : 'bg-amber-400/10'
                                },
                            ].map((metric) => (
                                <div key={metric.label} className="bg-app-bg-card border border-app-border rounded-xl p-4 flex items-center gap-3">
                                    <div className={`w-10 h-10 ${metric.bg} rounded-lg flex items-center justify-center flex-shrink-0`}>
                                        <metric.icon className={`w-5 h-5 ${metric.color}`} />
                                    </div>
                                    <div className="min-w-0">
                                        <p className={`font-bold text-app-text-main leading-none ${metric.value === 'Blocked' ? 'text-lg' : 'text-2xl'}`}>{metric.value}</p>
                                        <p className="text-xs text-app-text-muted mt-0.5">{metric.label}</p>
                                        {metric.sub && <p className="text-[10px] text-app-text-muted mt-0.5 opacity-70">{metric.sub}</p>}
                                    </div>
                                </div>
                            ))}
                        </div>

                        {/* ── Recipients tracking table ── */}
                        <div className="bg-app-bg-card border border-app-border rounded-xl overflow-hidden">
                            <div className="px-5 py-3.5 border-b border-app-border flex items-center justify-between">
                                <div className="flex items-center gap-2">
                                    <Activity className="w-4 h-4 text-app-text-muted" />
                                    <h3 className="text-sm font-semibold text-app-text-main">Recipient Activity</h3>
                                    <span className="px-2 py-0.5 bg-app-bg-page border border-app-border rounded-full text-[10px] font-medium text-app-text-muted">
                                        {recipientEmails.length}
                                    </span>
                                </div>
                                <button
                                    onClick={loadShareStats}
                                    disabled={loadingStats}
                                    className="flex items-center gap-1.5 text-xs text-app-text-muted hover:text-app-text-main transition-colors"
                                >
                                    <RefreshCw className={`w-3.5 h-3.5 ${loadingStats ? 'animate-spin' : ''}`} />
                                    {loadingStats ? 'Refreshing' : 'Refresh'}
                                </button>
                            </div>

                            <div className="grid grid-cols-12 px-5 py-2 bg-app-bg-page/50 border-b border-app-border text-[10px] font-bold uppercase tracking-wider text-app-text-muted">
                                <div className="col-span-6">Recipient</div>
                                <div className="col-span-2 text-center">Status</div>
                                <div className="col-span-2 text-center">Views</div>
                                <div className="col-span-2 text-center">Downloads</div>
                            </div>

                            {/* Table rows */}
                            <div className="divide-y divide-app-border">
                                {(() => {
                                    const entities = [...recipientEmails].map(e => (typeof e === 'string' ? e : e.email));
                                    const hasAnonymousViews = (shareStats?.access_log || []).some(l => !l.email);
                                    if (shareConfig.allowAnonymous || hasAnonymousViews) entities.push('Anonymous');

                                    // Pre-calculate stats for sorting
                                    const entitiesWithStats = entities.map(emailStr => {
                                        const isAnonymous = emailStr === 'Anonymous';

                                        // Calculate stats from log
                                        const relevantLogs = (shareStats?.access_log || [])
                                            .filter(l => (isAnonymous ? !l.email : (l.email === emailStr)));

                                        const stats = relevantLogs.reduce((acc, curr) => ({
                                            views: acc.views + (curr.action === 'view' ? 1 : 0),
                                            downloads: acc.downloads + (curr.action === 'download' ? 1 : 0),
                                            lastAccess: !acc.lastAccess || new Date(curr.accessed_at) > new Date(acc.lastAccess) ? curr.accessed_at : acc.lastAccess,
                                            latestIp: !acc.lastAccess || new Date(curr.accessed_at) > new Date(acc.lastAccess) ? curr.ip_address : acc.latestIp
                                        }), { views: 0, downloads: 0, lastAccess: null, latestIp: null });

                                        // Determine individual download permission
                                        let canDownload = false;
                                        if (isAnonymous) {
                                            canDownload = shareConfig.allowAnonymous && shareConfig.canDownload;
                                        } else {
                                            const rec = recipientEmails.find(r => r.email === emailStr);
                                            canDownload = rec ? rec.access_level === 'download' : false;
                                        }

                                        return { emailStr, isAnonymous, stats, canDownload };
                                    });

                                    entitiesWithStats.sort((a, b) => {
                                        const dateA = a.stats.lastAccess ? new Date(a.stats.lastAccess).getTime() : 0;
                                        const dateB = b.stats.lastAccess ? new Date(b.stats.lastAccess).getTime() : 0;
                                        return dateB - dateA;
                                    });

                                    const totalRecords = entitiesWithStats.length;
                                    const totalPages = Math.ceil(totalRecords / TRACKING_PAGE_SIZE);
                                    const startIndex = (trackingPage - 1) * TRACKING_PAGE_SIZE;
                                    const pagedEntities = entitiesWithStats.slice(startIndex, startIndex + TRACKING_PAGE_SIZE);

                                    return (
                                        <>
                                            <div className="divide-y divide-app-border">
                                                {pagedEntities.map(({ emailStr, isAnonymous, stats, canDownload }, index) => {
                                                    const isActive = stats.views > 0 || stats.downloads > 0;
                                                    const isExpanded = expandedRecipient === emailStr;
                                                    const label = isAnonymous ? 'Public / Anonymous' : emailStr;

                                                    const recipientLog = (shareStats?.access_log || [])
                                                        .filter(l => (isAnonymous ? !l.email : (l.email === emailStr)))
                                                        .sort((a, b) => new Date(b.accessed_at) - new Date(a.accessed_at))
                                                        .slice(0, 10);

                                                    return (
                                                        <div key={index} className="border-b border-app-border last:border-0">
                                                            <div
                                                                className="grid grid-cols-12 px-5 py-3 items-center hover:bg-app-bg-hover/40 transition-colors cursor-pointer"
                                                                onClick={() => setExpandedRecipient(isExpanded ? null : emailStr)}
                                                            >
                                                                {/* Email */}
                                                                <div className="col-span-6 flex items-center gap-2.5 min-w-0">
                                                                    <div className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold flex-shrink-0 ${isActive ? 'bg-app-primary/10 text-app-primary' : 'bg-app-bg-page text-app-text-muted'}`}>
                                                                        {label ? label[0].toUpperCase() : '?'}
                                                                    </div>
                                                                    <div className="min-w-0">
                                                                        <p className="text-xs font-medium text-app-text-main truncate">{label}</p>
                                                                        {stats.lastAccess && (
                                                                            <p className="text-[10px] text-app-text-muted opacity-70">
                                                                                {formatTimeAgo(stats.lastAccess)}
                                                                            </p>
                                                                        )}
                                                                    </div>
                                                                </div>

                                                                {/* Status */}
                                                                <div className="col-span-2 flex justify-center">
                                                                    {isActive ? (
                                                                        <span className="inline-flex items-center gap-1 px-2 py-0.5 bg-green-500/10 border border-green-500/20 text-green-400 text-[10px] font-medium rounded-full">
                                                                            <span className="w-1.5 h-1.5 rounded-full bg-green-400 inline-block" />Viewed
                                                                        </span>
                                                                    ) : (
                                                                        <span className="inline-flex items-center gap-1 px-2 py-0.5 bg-app-bg-page border border-app-border text-app-text-muted text-[10px] font-medium rounded-full">
                                                                            <span className="w-1.5 h-1.5 rounded-full bg-app-text-muted inline-block opacity-50" />Invited
                                                                        </span>
                                                                    )}
                                                                </div>

                                                                {/* Views */}
                                                                <div className="col-span-2 text-center text-xs text-app-text-main font-medium">
                                                                    {stats.views}
                                                                </div>

                                                                {/* Downloads */}
                                                                <div className="col-span-2 text-center text-xs text-app-text-main font-medium">
                                                                    {!canDownload ? (
                                                                        <span className="text-red-400/50 italic">Blocked</span>
                                                                    ) : stats.downloads}
                                                                </div>
                                                            </div>

                                                            {/* Expanded per-recipient log */}
                                                            {isExpanded && recipientLog.length > 0 && (
                                                                <div className="mx-5 mb-3 rounded-lg border border-app-border overflow-hidden bg-app-bg-page/40 animate-in fade-in slide-in-from-top-1 duration-200">
                                                                    <div className="bg-app-bg-page px-4 py-2 text-[10px] font-bold uppercase tracking-wider text-app-text-muted border-b border-app-border grid grid-cols-12">
                                                                        <span className="col-span-3">Action</span>
                                                                        <span className="col-span-6">File</span>
                                                                        <span className="col-span-3 text-right">Time</span>
                                                                    </div>
                                                                    {recipientLog.map((log, li) => (
                                                                        <div key={li} className="grid grid-cols-12 px-4 py-2 text-xs border-b border-app-border/50 last:border-0 hover:bg-app-bg-hover/30 transition-colors items-center">
                                                                            <span className={`col-span-3 flex items-center gap-1.5 font-medium ${log.action === 'download' ? 'text-amber-400' : 'text-emerald-400'}`}>
                                                                                {log.action === 'download' ? <Download className="w-3 h-3" /> : <Eye className="w-3 h-3" />}
                                                                                {log.action === 'download' ? 'Downloaded' : 'Viewed'}
                                                                            </span>
                                                                            <span className="col-span-6 text-app-text-muted truncate pr-2">{log.filename || 'Dashboard'}</span>
                                                                            <span className="col-span-3 text-app-text-muted text-right text-[10px]">{formatDateTime(log.accessed_at)}</span>
                                                                        </div>
                                                                    ))}
                                                                </div>
                                                            )}
                                                        </div>
                                                    );
                                                })}
                                            </div>
                                            {totalPages > 1 && (
                                                <div className="px-5 py-3 bg-app-bg-page/30 flex items-center justify-between border-t border-app-border">
                                                    <p className="text-[10px] text-app-text-muted">
                                                        Showing {startIndex + 1}-{Math.min(startIndex + TRACKING_PAGE_SIZE, totalRecords)} of {totalRecords}
                                                    </p>
                                                    <div className="flex gap-2">
                                                        <button
                                                            disabled={trackingPage === 1}
                                                            onClick={(e) => { e.stopPropagation(); setTrackingPage(p => Math.max(1, p - 1)); }}
                                                            className="p-1.5 text-app-text-muted hover:text-app-text-main disabled:opacity-30 transition-colors"
                                                        >
                                                            <ChevronLeft className="w-4 h-4" />
                                                        </button>
                                                        <button
                                                            disabled={trackingPage === totalPages}
                                                            onClick={(e) => { e.stopPropagation(); setTrackingPage(p => Math.min(totalPages, p + 1)); }}
                                                            className="p-1.5 text-app-text-muted hover:text-app-text-main disabled:opacity-30 transition-colors"
                                                        >
                                                            <ChevronRight className="w-4 h-4" />
                                                        </button>
                                                    </div>
                                                </div>
                                            )}
                                        </>
                                    );
                                })()}
                            </div>
                        </div>

                        <div className="flex justify-center gap-4 pb-4">
                            <button
                                onClick={() => goToStep(3)}
                                className="px-6 py-2.5 bg-app-bg-page border border-app-border text-app-text-main rounded-lg hover:bg-app-bg-hover transition-colors font-medium text-sm"
                            >
                                Back to Sharing
                            </button>
                            <button
                                onClick={() => navigate('/dashboard')}
                                className="px-6 py-2.5 bg-app-primary text-white rounded-lg hover:bg-app-primary-hover transition-colors font-medium text-sm"
                            >
                                Back to Dashboard
                            </button>
                        </div>
                    </div>
                )}

            </div>
        </div>
    );
};

export default ShareDocument;