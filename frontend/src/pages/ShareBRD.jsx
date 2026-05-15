import { useState, useEffect } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import {
    Upload, Settings as SettingsIcon, Mail, Activity, FileText, Trash2, Calendar, Lock,
    Eye, EyeOff, CheckCircle, X, Download, ExternalLink, FolderPlus, Folder,
    PlusCircle, ArrowRight, Copy, RefreshCw, TrendingUp, Users, BarChart2,
    Clock, Globe, Shield, AlertCircle, ChevronDown, ChevronUp, Link2
} from 'lucide-react';
import { API_ENDPOINTS } from '../config';
import RoadmapHeader from '../components/RoadmapHeader';

const ShareBRD = ({ selectedProjectKey, handleCreateShareProject: parentHandleCreateShareProject }) => {
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

    // Configuration state
    const [shareConfig, setShareConfig] = useState({
        dashboardAccess: 'once',
        expirationTime: 'no-expiration',
        requirePassword: false,
        password: '',
        canDownload: true
    });

    // Email sharing state
    const [recipientEmails, setRecipientEmails] = useState([]);
    const [emailInput, setEmailInput] = useState('');
    const [selectedFiles, setSelectedFiles] = useState([]);
    const [sending, setSending] = useState(false);
    const [shareLink, setShareLink] = useState('');
    const [shareToken, setShareToken] = useState('');
    const [copySuccess, setCopySuccess] = useState(false);

    // Status tracking state
    const [shareStats, setShareStats] = useState(null);
    const [loadingStats, setLoadingStats] = useState(false);
    const [expandedRecipient, setExpandedRecipient] = useState(null);

    // Roadmap configuration
    const roadmapSteps = ['Project Initiation', 'Upload Documents', 'Configure Access', 'Share & Invite', 'Track Status'];

    useEffect(() => {
        setCurrentStep(stepParam);
    }, [stepParam]);

    // Handle project selection from sidebar
    useEffect(() => {
        if (selectedProjectKey) {
            setSelectedProjectToken(selectedProjectKey);
            
            // Try to find the project to restore its last step
            const project = shareProjects.find(p => p.project_token === selectedProjectKey);
            
            if (project) {
                if (typeof project.current_step === 'number' && project.current_step > 0) {
                    setCurrentStep(project.current_step);
                } else {
                    setCurrentStep(1);
                }
            }
        } else {
            setSelectedProjectToken('');
            setCurrentStep(0);
        }
    }, [selectedProjectKey]);

    // Update currentStep once shareProjects are loaded if they weren't before
    useEffect(() => {
        if (selectedProjectKey && shareProjects.length > 0 && currentStep === 1) {
            const project = shareProjects.find(p => p.project_token === selectedProjectKey);
            if (project && typeof project.current_step === 'number' && project.current_step > 1) {
                setCurrentStep(project.current_step);
            }
        }
    }, [shareProjects]);

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
            if (!selectedProjectToken) {
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
                expirationTime: 'no-expiration',
                requirePassword: false,
                password: '',
                canDownload: true
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
                            canDownload: latestDoc.can_download !== undefined ? latestDoc.can_download : true
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
                navigate(`/share-brd?step=1&project=${project.project_token}`);
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
            setRecipientEmails(prev => [...prev, emailInput.trim()]);
            setEmailInput('');
        }
    };

    const removeEmailRecipient = (index) => {
        setRecipientEmails(prev => prev.filter((_, i) => i !== index));
    };

    const handleGenerateLink = async () => {
        setSending(true);
        try {
            const token = localStorage.getItem('token');
            const formData = new FormData();
            uploadedFiles.forEach(fileObj => {
                if (selectedFiles.includes(fileObj.id)) formData.append('files', fileObj.file);
            });
            formData.append('config', JSON.stringify(shareConfig));
            formData.append('recipients', JSON.stringify(recipientEmails));
            if (selectedProjectToken) formData.append('project_token', selectedProjectToken);

            const response = await fetch(API_ENDPOINTS.SHARE_BRD, {
                method: 'POST',
                headers: { 'Authorization': `Bearer ${token}` },
                body: formData
            });
            if (!response.ok) throw new Error('Failed to generate share link');
            const data = await response.json();
            setShareLink(data.share_url);
            setShareToken(data.share_token);
            navigate('/share-brd?step=4');
        } catch (error) {
            console.error('Error generating share link:', error);
            alert('Failed to generate share link. Please try again.');
        } finally {
            setSending(false);
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
            const response = await fetch(`${API_ENDPOINTS.SHARE_BRD_STATS}?token=${shareToken}`, {
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

    const goToStep = (step) => navigate(`/share-brd?step=${step}`);

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
        recipientEmails.forEach(email => {
            statsMap[email] = { views: 0, downloads: 0, lastAccess: null, locations: [] };
        });

        if (shareStats?.access_log) {
            shareStats.access_log.forEach(log => {
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

    const totalViews = shareStats?.access_count || 0;
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
                                        <p className="text-[11px] text-app-text-light mt-2 ml-1">This name will be used to identify your screening assessment.</p>
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
                    <div className="space-y-6">
                        <div>
                            <h2 className="text-2xl font-bold text-app-text-main mb-2">Upload Your Documents</h2>
                            <p className="text-sm text-app-text-muted">Upload your Business Requirements Documents or any related files you want to share</p>
                        </div>
                        <div
                            onDragOver={handleDragOver}
                            onDragLeave={handleDragLeave}
                            onDrop={handleDrop}
                            className={`border-2 border-dashed rounded-xl p-8 text-center transition-all ${isDragging ? 'border-app-primary bg-app-primary/5' : 'border-app-border bg-app-bg-card hover:border-app-primary/50'}`}
                        >
                            <Upload className="w-20 h-20 mx-auto mb-4 text-app-text-muted" />
                            <p className="text-xl font-semibold text-app-text-main mb-2">Drop your files here</p>
                            <p className="text-sm text-app-text-muted mb-4">or click to browse</p>
                            <input type="file" multiple onChange={handleFileInput} className="hidden" id="file-upload" accept=".pdf,.doc,.docx,.txt,.md,.xlsx,.xls,.ppt,.pptx" />
                            <label htmlFor="file-upload" className="inline-flex items-center px-8 py-4 bg-app-primary text-white rounded-lg hover:bg-app-primary-hover transition-colors cursor-pointer font-medium text-lg">
                                <Upload className="w-6 h-6 mr-2" />Choose Files
                            </label>
                            <p className="text-xs text-app-text-muted mt-6">Supports: PDF, DOC, DOCX, TXT, MD, XLSX, XLS, PPT, PPTX</p>
                        </div>
                        {uploadedFiles.length > 0 && (
                            <div className="bg-app-bg-card rounded-xl border border-app-border p-6">
                                <h3 className="text-lg font-semibold text-app-text-main mb-4">Uploaded Files ({uploadedFiles.length})</h3>
                                <div className="space-y-3">
                                    {uploadedFiles.map(file => (
                                        <div key={file.id} className="flex items-center justify-between p-4 bg-app-bg-page rounded-lg border border-app-border hover:border-app-primary transition-colors">
                                            <div className="flex items-center space-x-4 flex-1 min-w-0">
                                                <FileText className="w-6 h-6 text-app-primary flex-shrink-0" />
                                                <div className="flex-1 min-w-0">
                                                    <p className="text-sm font-medium text-app-text-main truncate">{file.name}</p>
                                                    <p className="text-xs text-app-text-muted">{formatFileSize(file.size)}</p>
                                                </div>
                                            </div>
                                            <button onClick={() => removeFile(file.id)} className="p-2 text-red-400 hover:text-red-300 hover:bg-red-400/10 rounded-lg transition-colors">
                                                <Trash2 className="w-5 h-5" />
                                            </button>
                                        </div>
                                    ))}
                                </div>
                            </div>
                        )}
                        <div className="flex justify-end">
                            <button
                                onClick={() => goToStep(2)}
                                disabled={uploadedFiles.length === 0}
                                className="px-8 py-3 bg-app-primary text-white rounded-lg hover:bg-app-primary-hover transition-colors font-medium disabled:opacity-50 disabled:cursor-not-allowed"
                            >
                                Next: Configure Access
                            </button>
                        </div>
                    </div>
                )}

                {/* Step 2: Configure Access */}
                {currentStep === 2 && (
                    <div className="space-y-6">
                        <div>
                            <h2 className="text-2xl font-bold text-app-text-main mb-2">Configure Access Settings</h2>
                            <p className="text-sm text-app-text-muted">Set access permissions and security options for your shared documents</p>
                        </div>
                        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                            <div className="bg-app-bg-card p-6 rounded-xl border border-app-border">
                                <label className="block text-base font-semibold text-app-text-main mb-4">
                                    <Eye className="w-5 h-5 inline mr-2" />Share Dashboard Access
                                </label>
                                <div className="space-y-3">
                                    {[
                                        { value: 'once', label: 'Accessible only once', desc: 'Link expires after first access' },
                                        { value: 'always', label: 'Accessible always', desc: 'Link remains active until expiration' }
                                    ].map(opt => (
                                        <label key={opt.value} className="flex items-start space-x-3 p-4 rounded-lg border-2 border-app-border hover:bg-app-bg-hover cursor-pointer transition-colors">
                                            <input type="radio" name="dashboardAccess" value={opt.value} checked={shareConfig.dashboardAccess === opt.value}
                                                onChange={(e) => setShareConfig(prev => ({ ...prev, dashboardAccess: e.target.value }))}
                                                className="w-5 h-5 text-app-primary mt-0.5" />
                                            <div className="flex-1">
                                                <p className="text-sm font-medium text-app-text-main">{opt.label}</p>
                                                <p className="text-xs text-app-text-muted mt-1">{opt.desc}</p>
                                            </div>
                                        </label>
                                    ))}
                                </div>
                            </div>
                            <div className="bg-app-bg-card p-6 rounded-xl border border-app-border">
                                <label className="block text-base font-semibold text-app-text-main mb-4">
                                    <Calendar className="w-5 h-5 inline mr-2" />Expiration Time
                                </label>
                                <select
                                    value={shareConfig.expirationTime}
                                    onChange={(e) => setShareConfig(prev => ({ ...prev, expirationTime: e.target.value }))}
                                    className="w-full px-4 py-3 bg-app-bg-page border border-app-border rounded-lg text-app-text-main focus:outline-none focus:ring-2 focus:ring-app-primary focus:border-app-primary"
                                >
                                    <option value="no-expiration">No Expiration</option>
                                    <option value="24h">24 Hours</option>
                                    <option value="7d">7 Days</option>
                                    <option value="30d">30 Days</option>
                                </select>
                            </div>
                            <div className="bg-app-bg-card p-6 rounded-xl border border-app-border">
                                <label className="flex items-center justify-between mb-4">
                                    <span className="text-base font-semibold text-app-text-main">
                                        <Lock className="w-5 h-5 inline mr-2" />Password Protection
                                    </span>
                                    <button
                                        onClick={() => setShareConfig(prev => ({ ...prev, requirePassword: !prev.requirePassword }))}
                                        className={`relative inline-flex h-7 w-14 items-center rounded-full transition-colors ${shareConfig.requirePassword ? 'bg-app-primary' : 'bg-app-border'}`}
                                    >
                                        <span className={`inline-block h-5 w-5 transform rounded-full bg-white transition-transform ${shareConfig.requirePassword ? 'translate-x-8' : 'translate-x-1'}`} />
                                    </button>
                                </label>
                                {shareConfig.requirePassword && (
                                    <input type="text" value={shareConfig.password}
                                        onChange={(e) => setShareConfig(prev => ({ ...prev, password: e.target.value }))}
                                        placeholder="Enter password"
                                        className="w-full px-4 py-3 bg-app-bg-page border border-app-border rounded-lg text-app-text-main placeholder-app-text-muted focus:outline-none focus:ring-2 focus:ring-app-primary focus:border-app-primary"
                                    />
                                )}
                            </div>
                            <div className="bg-app-bg-card p-6 rounded-xl border border-app-border">
                                <label className="flex items-center justify-between mb-4">
                                    <span className="text-base font-semibold text-app-text-main">
                                        <Download className="w-5 h-5 inline mr-2" />Allow Downloads
                                    </span>
                                    <button
                                        onClick={() => setShareConfig(prev => ({ ...prev, canDownload: !prev.canDownload }))}
                                        className={`relative inline-flex h-7 w-14 items-center rounded-full transition-colors ${shareConfig.canDownload ? 'bg-app-primary' : 'bg-app-border'}`}
                                    >
                                        <span className={`inline-block h-5 w-5 transform rounded-full bg-white transition-transform ${shareConfig.canDownload ? 'translate-x-8' : 'translate-x-1'}`} />
                                    </button>
                                </label>
                                <p className="text-sm text-app-text-muted">
                                    {shareConfig.canDownload ? 'Recipients can download files to their device' : 'Recipients can only view files online, downloads are disabled'}
                                </p>
                            </div>
                        </div>
                        <div className="flex justify-between">
                            <button onClick={() => goToStep(1)} className="px-8 py-3 border border-app-border text-app-text-main rounded-lg hover:bg-app-bg-hover transition-colors font-medium">Back</button>
                            <button onClick={() => goToStep(3)} className="px-8 py-3 bg-app-primary text-white rounded-lg hover:bg-app-primary-hover transition-colors font-medium">Next: Share & Invite</button>
                        </div>
                    </div>
                )}

                {/* Step 3: Share & Invite */}
                {currentStep === 3 && (
                    <div className="space-y-6">
                        <div>
                            <h2 className="text-2xl font-bold text-app-text-main mb-2">Share with Recipients</h2>
                            <p className="text-sm text-app-text-muted">Enter email addresses of people you want to share these documents with</p>
                        </div>
                        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                            <div className="bg-app-bg-card p-6 rounded-xl border border-app-border">
                                <h3 className="text-base font-semibold text-app-text-main mb-4">Documents to Share ({selectedFiles.length})</h3>
                                <div className="space-y-2 max-h-80 overflow-y-auto">
                                    {uploadedFiles.filter(f => selectedFiles.includes(f.id)).map(file => (
                                        <div key={file.id} className="flex items-center space-x-3 p-3 bg-app-bg-page rounded-lg">
                                            <FileText className="w-5 h-5 text-app-primary flex-shrink-0" />
                                            <div className="flex-1 min-w-0">
                                                <p className="text-sm text-app-text-main truncate">{file.name}</p>
                                                <p className="text-xs text-app-text-muted">{formatFileSize(file.size)}</p>
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            </div>
                            <div className="bg-app-bg-card p-6 rounded-xl border border-app-border">
                                <label className="block text-base font-semibold text-app-text-main mb-4">
                                    <Mail className="w-5 h-5 inline mr-2" />Recipient Email Addresses
                                </label>
                                <div className="flex space-x-2 mb-4">
                                    <input type="email" value={emailInput} onChange={(e) => setEmailInput(e.target.value)}
                                        onKeyPress={(e) => e.key === 'Enter' && addEmailRecipient()}
                                        placeholder="Enter email address"
                                        className="flex-1 px-4 py-3 bg-app-bg-page border border-app-border rounded-lg text-app-text-main placeholder-app-text-muted focus:outline-none focus:ring-2 focus:ring-app-primary focus:border-app-primary"
                                    />
                                    <button onClick={addEmailRecipient} className="px-6 py-3 bg-app-primary text-white rounded-lg hover:bg-app-primary-hover transition-colors font-medium">Add</button>
                                </div>
                                {recipientEmails.length > 0 && (
                                    <div className="space-y-2 max-h-60 overflow-y-auto">
                                        <p className="text-xs text-app-text-muted mb-2">Recipients ({recipientEmails.length}):</p>
                                        {recipientEmails.map((email, index) => (
                                            <div key={index} className="flex items-center justify-between p-3 bg-app-bg-page rounded-lg">
                                                <span className="text-sm text-app-text-main">{email}</span>
                                                <button onClick={() => removeEmailRecipient(index)} className="p-1 text-red-400 hover:text-red-300 hover:bg-red-400/10 rounded transition-colors">
                                                    <X className="w-4 h-4" />
                                                </button>
                                            </div>
                                        ))}
                                    </div>
                                )}
                            </div>
                        </div>
                        <div className="flex justify-between">
                            <button onClick={() => goToStep(2)} className="px-8 py-3 border border-app-border text-app-text-main rounded-lg hover:bg-app-bg-hover transition-colors font-medium">Back</button>
                            <button
                                onClick={handleGenerateLink}
                                disabled={sending || uploadedFiles.length === 0}
                                className="px-8 py-3 bg-app-primary text-white rounded-lg hover:bg-app-primary-hover transition-colors font-medium disabled:opacity-50 disabled:cursor-not-allowed"
                            >
                                {sending ? 'Generating...' : 'Generate Link & Send Invites'}
                            </button>
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
                                    label: 'Documents', value: selectedFiles.length,
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
                                    label: 'Downloads', value: totalDownloads,
                                    icon: Download, color: 'text-amber-400', bg: 'bg-amber-400/10',
                                    hidden: !shareConfig.canDownload
                                },
                            ].filter(m => !m.hidden).map((metric) => (
                                <div key={metric.label} className="bg-app-bg-card border border-app-border rounded-xl p-4 flex items-center gap-3">
                                    <div className={`w-10 h-10 ${metric.bg} rounded-lg flex items-center justify-center flex-shrink-0`}>
                                        <metric.icon className={`w-5 h-5 ${metric.color}`} />
                                    </div>
                                    <div className="min-w-0">
                                        <p className="text-2xl font-bold text-app-text-main leading-none">{metric.value}</p>
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

                            {/* Table header */}
                            <div className="grid grid-cols-12 px-5 py-2 bg-app-bg-page/50 border-b border-app-border text-[10px] font-bold uppercase tracking-wider text-app-text-muted">
                                <div className="col-span-5">Recipient</div>
                                <div className="col-span-2 text-center">Status</div>
                                <div className="col-span-2 text-center">Views</div>
                                {shareConfig.canDownload && <div className="col-span-2 text-center">Downloads</div>}
                                <div className={`${shareConfig.canDownload ? 'col-span-1' : 'col-span-3'} text-right`}>Last Seen</div>
                            </div>

                            {/* Table rows */}
                            <div className="divide-y divide-app-border">
                                {(() => {
                                    const entities = [...recipientEmails];
                                    const hasAnonymous = (shareStats?.access_log || []).some(l => !l.email);
                                    if (hasAnonymous) entities.push('Anonymous');
                                    
                                    return entities.map((identity, index) => {
                                        const isAnonymous = identity === 'Anonymous';
                                        const stats = isAnonymous 
                                            ? (shareStats?.access_log || [])
                                                .filter(l => !l.email)
                                                .reduce((acc, curr) => ({
                                                    views: acc.views + (curr.action === 'view' ? 1 : 0),
                                                    downloads: acc.downloads + (curr.action === 'download' ? 1 : 0),
                                                    lastAccess: !acc.lastAccess || new Date(curr.accessed_at) > new Date(acc.lastAccess) ? curr.accessed_at : acc.lastAccess
                                                }), { views: 0, downloads: 0, lastAccess: null })
                                            : recipientStats[identity] || { views: 0, downloads: 0, lastAccess: null };

                                        const isActive = stats.views > 0 || stats.downloads > 0;
                                        const isExpanded = expandedRecipient === identity;

                                        // Get this entity's log entries
                                        const recipientLog = (shareStats?.access_log || [])
                                            .filter(l => isAnonymous ? !l.email : (l.email === identity))
                                            .sort((a, b) => new Date(b.accessed_at) - new Date(a.accessed_at))
                                            .slice(0, 5);
                                        
                                        const label = isAnonymous ? 'Public / Anonymous' : identity;
                                        const email = isAnonymous ? null : identity;

                                    return (
                                        <div key={index}>
                                            <div
                                                className="grid grid-cols-12 px-5 py-3 items-center hover:bg-app-bg-hover/40 transition-colors cursor-pointer"
                                                onClick={() => setExpandedRecipient(isExpanded ? null : email)}
                                            >
                                                {/* Email */}
                                                <div className="col-span-5 flex items-center gap-2.5 min-w-0">
                                                    <div className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold flex-shrink-0 ${isActive ? 'bg-app-primary/10 text-app-primary' : 'bg-app-bg-page text-app-text-muted'}`}>
                                                        {email ? email[0].toUpperCase() : '?'}
                                                    </div>
                                                    <div className="min-w-0">
                                                        <p className="text-xs font-medium text-app-text-main truncate">{label}</p>
                                                        {stats.locations && stats.locations.length > 0 && (
                                                            <p className="text-[10px] text-app-text-muted flex items-center gap-1">
                                                                <Globe className="w-2.5 h-2.5" />{stats.locations[0]}
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
                                                <div className="col-span-2 text-center">
                                                    <span className={`text-sm font-semibold ${stats.views > 0 ? 'text-emerald-400' : 'text-app-text-muted'}`}>
                                                        {stats.views}
                                                    </span>
                                                </div>

                                                {/* Downloads */}
                                                {shareConfig.canDownload && (
                                                    <div className="col-span-2 text-center">
                                                        <span className={`text-sm font-semibold ${stats.downloads > 0 ? 'text-amber-400' : 'text-app-text-muted'}`}>
                                                            {stats.downloads}
                                                        </span>
                                                    </div>
                                                )}

                                                {/* Last seen */}
                                                <div className={`${shareConfig.canDownload ? 'col-span-1' : 'col-span-3'} text-right flex items-center justify-end gap-1`}>
                                                    <span className="text-[10px] text-app-text-muted">{formatTimeAgo(stats.lastAccess)}</span>
                                                    {recipientLog.length > 0 && (
                                                        isExpanded ? <ChevronUp className="w-3 h-3 text-app-text-muted" /> : <ChevronDown className="w-3 h-3 text-app-text-muted" />
                                                    )}
                                                </div>
                                            </div>

                                            {/* Expanded per-recipient log */}
                                            {isExpanded && recipientLog.length > 0 && (
                                                <div className="mx-5 mb-3 rounded-lg border border-app-border overflow-hidden">
                                                    <div className="bg-app-bg-page px-4 py-2 text-[10px] font-bold uppercase tracking-wider text-app-text-muted border-b border-app-border grid grid-cols-3">
                                                        <span>Action</span>
                                                        <span>File</span>
                                                        <span className="text-right">Time</span>
                                                    </div>
                                                    {recipientLog.map((log, li) => (
                                                        <div key={li} className="grid grid-cols-3 px-4 py-2 text-xs border-b border-app-border/50 last:border-0 hover:bg-app-bg-hover/30 transition-colors">
                                                            <span className={`flex items-center gap-1.5 font-medium ${log.action === 'download' ? 'text-amber-400' : 'text-emerald-400'}`}>
                                                                {log.action === 'download' ? <Download className="w-3 h-3" /> : <Eye className="w-3 h-3" />}
                                                                {log.action === 'download' ? 'Downloaded' : 'Viewed'}
                                                            </span>
                                                            <span className="text-app-text-muted truncate">{log.filename || '—'}</span>
                                                            <span className="text-app-text-muted text-right">{formatDateTime(log.accessed_at)}</span>
                                                        </div>
                                                    ))}
                                                </div>
                                            )}
                                        </div>
                                    );
                                })})()}
                            </div>
                        </div>

                        {/* ── Recent access log (compact) ── */}
                        {shareStats?.access_log && shareStats.access_log.length > 0 && (
                            <div className="bg-app-bg-card border border-app-border rounded-xl overflow-hidden">
                                <div className="px-5 py-3.5 border-b border-app-border flex items-center gap-2">
                                    <Clock className="w-4 h-4 text-app-text-muted" />
                                    <h3 className="text-sm font-semibold text-app-text-main">Recent Activity</h3>
                                </div>
                                <div className="divide-y divide-app-border max-h-52 overflow-y-auto">
                                    {[...shareStats.access_log]
                                        .sort((a, b) => new Date(b.accessed_at) - new Date(a.accessed_at))
                                        .slice(0, 10)
                                        .map((log, index) => (
                                            <div key={index} className="flex items-center justify-between px-5 py-2.5 hover:bg-app-bg-hover/40 transition-colors">
                                                <div className="flex items-center gap-3 min-w-0">
                                                    <div className={`w-6 h-6 rounded-full flex items-center justify-center flex-shrink-0 ${log.action === 'download' ? 'bg-amber-400/10' : 'bg-emerald-400/10'}`}>
                                                        {log.action === 'download'
                                                            ? <Download className="w-3 h-3 text-amber-400" />
                                                            : <Eye className="w-3 h-3 text-emerald-400" />
                                                        }
                                                    </div>
                                                    <div className="min-w-0">
                                                        <p className="text-xs text-app-text-main truncate">
                                                            <span className="font-medium">{log.email || log.ip_address || 'Anonymous'}</span>
                                                            {log.action === 'download' ? ' downloaded' : ' viewed'}
                                                            {log.filename && <span className="text-app-text-muted"> · {log.filename}</span>}
                                                        </p>
                                                    </div>
                                                </div>
                                                <span className="text-[10px] text-app-text-muted flex-shrink-0 ml-4">{formatTimeAgo(log.accessed_at)}</span>
                                            </div>
                                        ))}
                                </div>
                            </div>
                        )}

                        {/* ── Footer action ── */}
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

export default ShareBRD;