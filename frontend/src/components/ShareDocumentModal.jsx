import { useState, useCallback } from 'react';
import { X, Upload, Settings as SettingsIcon, Send, CheckCircle, FileText, Trash2, Eye, EyeOff, Calendar, Lock, Unlock, Mail } from 'lucide-react';
import { API_ENDPOINTS } from '../config';

const ShareDocumentModal = ({ isOpen, onClose }) => {
    const [currentStep, setCurrentStep] = useState(1);
    const [uploadedFiles, setUploadedFiles] = useState([]);
    const [isDragging, setIsDragging] = useState(false);
    const [uploading, setUploading] = useState(false);
    
    // Configuration state
    const [shareConfig, setShareConfig] = useState({
        dashboardAccess: 'once', // 'once' or 'always'
        expirationTime: 'no-expiration', // 'no-expiration', '24h', '7d', '30d'
        requirePassword: false,
        password: ''
    });
    
    // Email sharing state
    const [recipientEmails, setRecipientEmails] = useState(['']);
    const [emailInput, setEmailInput] = useState('');
    const [selectedFiles, setSelectedFiles] = useState([]);
    const [sending, setSending] = useState(false);
    const [shareLink, setShareLink] = useState('');
    const [linkGenerated, setLinkGenerated] = useState(false);

    const handleDragOver = (e) => {
        e.preventDefault();
        setIsDragging(true);
    };

    const handleDragLeave = (e) => {
        e.preventDefault();
        setIsDragging(false);
    };

    const handleFiles = (files) => {
        const newFiles = files.map(file => ({
            id: Math.random().toString(36).substr(2, 9),
            file: file,
            name: file.name,
            size: file.size,
            type: file.type,
            uploadedAt: new Date().toISOString()
        }));
        
        setUploadedFiles(prev => [...prev, ...newFiles]);
        setSelectedFiles(prev => [...prev, ...newFiles.map(f => f.id)]);
    };

    const handleDrop = useCallback((e) => {
        e.preventDefault();
        setIsDragging(false);
        
        const files = Array.from(e.dataTransfer.files);
        handleFiles(files);
    }, []);

    const handleFileInput = (e) => {
        const files = Array.from(e.target.files);
        handleFiles(files);
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
            
            // Add files
            uploadedFiles.forEach(fileObj => {
                if (selectedFiles.includes(fileObj.id)) {
                    formData.append('files', fileObj.file);
                }
            });
            
            // Add configuration
            formData.append('config', JSON.stringify(shareConfig));
            formData.append('recipients', JSON.stringify(recipientEmails.filter(e => e.trim())));
            
            const response = await fetch(API_ENDPOINTS.SHARE_DOC || '/api/share-doc', {
                method: 'POST',
                headers: {
                    'Authorization': `Bearer ${token}`
                },
                body: formData
            });
            
            if (!response.ok) throw new Error('Failed to generate share link');
            
            const data = await response.json();
            setShareLink(data.share_url || data.link);
            setLinkGenerated(true);
            setCurrentStep(4);
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
            alert('Link copied to clipboard!');
        } catch (err) {
            console.error('Failed to copy:', err);
        }
    };

    const resetModal = () => {
        setCurrentStep(1);
        setUploadedFiles([]);
        setSelectedFiles([]);
        setRecipientEmails(['']);
        setEmailInput('');
        setShareLink('');
        setLinkGenerated(false);
        setShareConfig({
            dashboardAccess: 'once',
            expirationTime: 'no-expiration',
            requirePassword: false,
            password: ''
        });
    };

    const handleClose = () => {
        resetModal();
        onClose();
    };

    const steps = [
        { number: 1, label: 'Upload Document', icon: Upload },
        { number: 2, label: 'Configure', icon: SettingsIcon },
        { number: 3, label: 'Share', icon: Mail },
        { number: 4, label: 'On Flight', icon: Send }
    ];

    if (!isOpen) return null;

    return (
        <div className="fixed inset-0 z-[9999] flex items-center justify-center p-4">
            {/* Backdrop */}
            <div
                className="absolute inset-0 bg-black/60 backdrop-blur-sm"
                onClick={handleClose}
            />

            {/* Modal */}
            <div
                className="relative w-full max-w-4xl bg-app-bg-card rounded-2xl shadow-2xl border border-app-border overflow-hidden max-h-[90vh] flex flex-col"
                style={{ animation: 'modalIn 0.2s cubic-bezier(0.34,1.56,0.64,1)' }}
                onClick={(e) => e.stopPropagation()}
            >
                {/* Header */}
                <div className="flex items-center justify-between px-6 py-4 border-b border-app-border bg-gradient-to-r from-app-primary/10 to-app-primary-dark/10 flex-shrink-0">
                    <h2 className="text-xl font-bold text-app-text-main">Share Your Document</h2>
                    <button
                        onClick={handleClose}
                        className="p-2 rounded-lg text-app-text-light hover:text-app-text-main hover:bg-app-bg-hover transition-colors"
                    >
                        <X className="w-5 h-5" />
                    </button>
                </div>

                {/* Roadmap Stepper */}
                <div className="px-6 py-4 border-b border-app-border bg-app-bg-page flex-shrink-0">
                    <div className="flex items-center justify-between max-w-3xl mx-auto">
                        {steps.map((step, index) => {
                            const StepIcon = step.icon;
                            const isActive = currentStep === step.number;
                            const isCompleted = currentStep > step.number;
                            
                            return (
                                <div key={step.number} className="flex items-center flex-1">
                                    <div className="flex flex-col items-center flex-1">
                                        <div className={`w-12 h-12 rounded-full flex items-center justify-center border-2 transition-all ${
                                            isCompleted 
                                                ? 'bg-green-500 border-green-500 text-white' 
                                                : isActive 
                                                    ? 'bg-app-primary border-app-primary text-white shadow-lg' 
                                                    : 'bg-app-bg-card border-app-border text-app-text-muted'
                                        }`}>
                                            {isCompleted ? (
                                                <CheckCircle className="w-6 h-6" />
                                            ) : (
                                                <StepIcon className="w-6 h-6" />
                                            )}
                                        </div>
                                        <span className={`text-xs mt-2 font-medium ${
                                            isActive ? 'text-app-text-main' : 'text-app-text-muted'
                                        }`}>
                                            {step.label}
                                        </span>
                                    </div>
                                    {index < steps.length - 1 && (
                                        <div className={`h-0.5 flex-1 mx-2 ${
                                            currentStep > step.number ? 'bg-green-500' : 'bg-app-border'
                                        }`} />
                                    )}
                                </div>
                            );
                        })}
                    </div>
                </div>

                {/* Content */}
                <div className="flex-1 overflow-y-auto p-6">
                    {/* Step 1: Upload Document */}
                    {currentStep === 1 && (
                        <div className="space-y-6">
                            <div>
                                <h3 className="text-lg font-bold text-app-text-main mb-2">Upload Your Documents</h3>
                                <p className="text-sm text-app-text-muted">
                                    Upload your Business Requirements Documents or any related files you want to share
                                </p>
                            </div>

                            {/* Drop Zone */}
                            <div
                                onDragOver={handleDragOver}
                                onDragLeave={handleDragLeave}
                                onDrop={handleDrop}
                                className={`border-2 border-dashed rounded-xl p-12 text-center transition-all ${
                                    isDragging 
                                        ? 'border-app-primary bg-app-primary/5' 
                                        : 'border-app-border bg-app-bg-page hover:border-app-primary/50'
                                }`}
                            >
                                <Upload className="w-16 h-16 mx-auto mb-4 text-app-text-muted" />
                                <p className="text-lg font-semibold text-app-text-main mb-2">
                                    Drop your files here
                                </p>
                                <p className="text-sm text-app-text-muted mb-4">
                                    or click to browse
                                </p>
                                <input
                                    type="file"
                                    multiple
                                    onChange={handleFileInput}
                                    className="hidden"
                                    id="file-upload"
                                    accept=".pdf,.doc,.docx,.txt,.md,.xlsx,.xls,.ppt,.pptx"
                                />
                                <label
                                    htmlFor="file-upload"
                                    className="inline-flex items-center px-6 py-3 bg-app-primary text-white rounded-lg hover:bg-app-primary-hover transition-colors cursor-pointer font-medium"
                                >
                                    <Upload className="w-5 h-5 mr-2" />
                                    Choose Files
                                </label>
                                <p className="text-xs text-app-text-muted mt-4">
                                    Supports: PDF, DOC, DOCX, TXT, MD, XLSX, XLS, PPT, PPTX
                                </p>
                            </div>

                            {/* Uploaded Files List */}
                            {uploadedFiles.length > 0 && (
                                <div className="space-y-3">
                                    <h4 className="text-sm font-semibold text-app-text-main">
                                        Uploaded Files ({uploadedFiles.length})
                                    </h4>
                                    <div className="space-y-2">
                                        {uploadedFiles.map(file => (
                                            <div
                                                key={file.id}
                                                className="flex items-center justify-between p-3 bg-app-bg-page rounded-lg border border-app-border"
                                            >
                                                <div className="flex items-center space-x-3 flex-1 min-w-0">
                                                    <FileText className="w-5 h-5 text-app-primary flex-shrink-0" />
                                                    <div className="flex-1 min-w-0">
                                                        <p className="text-sm font-medium text-app-text-main truncate">
                                                            {file.name}
                                                        </p>
                                                        <p className="text-xs text-app-text-muted">
                                                            {formatFileSize(file.size)}
                                                        </p>
                                                    </div>
                                                </div>
                                                <button
                                                    onClick={() => removeFile(file.id)}
                                                    className="p-2 text-red-400 hover:text-red-300 hover:bg-red-400/10 rounded-lg transition-colors"
                                                >
                                                    <Trash2 className="w-4 h-4" />
                                                </button>
                                            </div>
                                        ))}
                                    </div>
                                </div>
                            )}
                        </div>
                    )}

                    {/* Step 2: Configure */}
                    {currentStep === 2 && (
                        <div className="space-y-6">
                            <div>
                                <h3 className="text-lg font-bold text-app-text-main mb-2">Configure Sharing Settings</h3>
                                <p className="text-sm text-app-text-muted">
                                    Set access permissions and security options for your shared documents
                                </p>
                            </div>

                            <div className="space-y-6">
                                {/* Dashboard Access */}
                                <div className="bg-app-bg-page p-4 rounded-xl border border-app-border">
                                    <label className="block text-sm font-semibold text-app-text-main mb-3">
                                        Share Dashboard
                                    </label>
                                    <div className="space-y-2">
                                        <label className="flex items-center space-x-3 p-3 rounded-lg border border-app-border hover:bg-app-bg-card cursor-pointer transition-colors">
                                            <input
                                                type="radio"
                                                name="dashboardAccess"
                                                value="once"
                                                checked={shareConfig.dashboardAccess === 'once'}
                                                onChange={(e) => setShareConfig(prev => ({ ...prev, dashboardAccess: e.target.value }))}
                                                className="w-4 h-4 text-app-primary"
                                            />
                                            <div className="flex-1">
                                                <p className="text-sm font-medium text-app-text-main">Accessible only once</p>
                                                <p className="text-xs text-app-text-muted">Link expires after first access</p>
                                            </div>
                                        </label>
                                        <label className="flex items-center space-x-3 p-3 rounded-lg border border-app-border hover:bg-app-bg-card cursor-pointer transition-colors">
                                            <input
                                                type="radio"
                                                name="dashboardAccess"
                                                value="always"
                                                checked={shareConfig.dashboardAccess === 'always'}
                                                onChange={(e) => setShareConfig(prev => ({ ...prev, dashboardAccess: e.target.value }))}
                                                className="w-4 h-4 text-app-primary"
                                            />
                                            <div className="flex-1">
                                                <p className="text-sm font-medium text-app-text-main">Accessible always</p>
                                                <p className="text-xs text-app-text-muted">Link remains active until expiration</p>
                                            </div>
                                        </label>
                                    </div>
                                </div>

                                {/* Expiration Time */}
                                <div className="bg-app-bg-page p-4 rounded-xl border border-app-border">
                                    <label className="block text-sm font-semibold text-app-text-main mb-3">
                                        <Calendar className="w-4 h-4 inline mr-2" />
                                        Expiration Time
                                    </label>
                                    <select
                                        value={shareConfig.expirationTime}
                                        onChange={(e) => setShareConfig(prev => ({ ...prev, expirationTime: e.target.value }))}
                                        className="w-full px-4 py-2.5 bg-app-bg-card border border-app-border rounded-lg text-app-text-main focus:outline-none focus:ring-2 focus:ring-app-primary focus:border-app-primary"
                                    >
                                        <option value="no-expiration">No Expiration</option>
                                        <option value="24h">24 Hours</option>
                                        <option value="7d">7 Days</option>
                                        <option value="30d">30 Days</option>
                                    </select>
                                </div>

                                {/* Password Protection */}
                                <div className="bg-app-bg-page p-4 rounded-xl border border-app-border">
                                    <label className="flex items-center justify-between mb-3">
                                        <span className="text-sm font-semibold text-app-text-main">
                                            <Lock className="w-4 h-4 inline mr-2" />
                                            Password Protection
                                        </span>
                                        <button
                                            onClick={() => setShareConfig(prev => ({ ...prev, requirePassword: !prev.requirePassword }))}
                                            className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
                                                shareConfig.requirePassword ? 'bg-app-primary' : 'bg-app-border'
                                            }`}
                                        >
                                            <span
                                                className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                                                    shareConfig.requirePassword ? 'translate-x-6' : 'translate-x-1'
                                                }`}
                                            />
                                        </button>
                                    </label>
                                    {shareConfig.requirePassword && (
                                        <input
                                            type="text"
                                            value={shareConfig.password}
                                            onChange={(e) => setShareConfig(prev => ({ ...prev, password: e.target.value }))}
                                            placeholder="Enter password"
                                            className="w-full px-4 py-2.5 bg-app-bg-card border border-app-border rounded-lg text-app-text-main placeholder-app-text-muted focus:outline-none focus:ring-2 focus:ring-app-primary focus:border-app-primary"
                                        />
                                    )}
                                </div>
                            </div>
                        </div>
                    )}

                    {/* Step 3: Share */}
                    {currentStep === 3 && (
                        <div className="space-y-6">
                            <div>
                                <h3 className="text-lg font-bold text-app-text-main mb-2">Share with Recipients</h3>
                                <p className="text-sm text-app-text-muted">
                                    Enter email addresses of people you want to share these documents with
                                </p>
                            </div>

                            {/* Selected Files Summary */}
                            <div className="bg-app-bg-page p-4 rounded-xl border border-app-border">
                                <h4 className="text-sm font-semibold text-app-text-main mb-3">
                                    Documents to Share ({selectedFiles.length})
                                </h4>
                                <div className="space-y-2 max-h-40 overflow-y-auto">
                                    {uploadedFiles.filter(f => selectedFiles.includes(f.id)).map(file => (
                                        <div key={file.id} className="flex items-center space-x-2 text-sm">
                                            <FileText className="w-4 h-4 text-app-primary flex-shrink-0" />
                                            <span className="text-app-text-main truncate">{file.name}</span>
                                            <span className="text-app-text-muted text-xs">({formatFileSize(file.size)})</span>
                                        </div>
                                    ))}
                                </div>
                            </div>

                            {/* Email Input */}
                            <div className="bg-app-bg-page p-4 rounded-xl border border-app-border">
                                <label className="block text-sm font-semibold text-app-text-main mb-3">
                                    <Mail className="w-4 h-4 inline mr-2" />
                                    Recipient Email Addresses
                                </label>
                                <div className="flex space-x-2 mb-3">
                                    <input
                                        type="email"
                                        value={emailInput}
                                        onChange={(e) => setEmailInput(e.target.value)}
                                        onKeyPress={(e) => e.key === 'Enter' && addEmailRecipient()}
                                        placeholder="Enter email address"
                                        className="flex-1 px-4 py-2.5 bg-app-bg-card border border-app-border rounded-lg text-app-text-main placeholder-app-text-muted focus:outline-none focus:ring-2 focus:ring-app-primary focus:border-app-primary"
                                    />
                                    <button
                                        onClick={addEmailRecipient}
                                        className="px-4 py-2.5 bg-app-primary text-white rounded-lg hover:bg-app-primary-hover transition-colors font-medium"
                                    >
                                        Add
                                    </button>
                                </div>
                                
                                {/* Email List */}
                                {recipientEmails.length > 0 && recipientEmails.some(e => e.trim()) && (
                                    <div className="space-y-2">
                                        <p className="text-xs text-app-text-muted">Recipients:</p>
                                        <div className="space-y-1">
                                            {recipientEmails.filter(e => e.trim()).map((email, index) => (
                                                <div
                                                    key={index}
                                                    className="flex items-center justify-between p-2 bg-app-bg-card rounded-lg"
                                                >
                                                    <span className="text-sm text-app-text-main">{email}</span>
                                                    <button
                                                        onClick={() => removeEmailRecipient(index)}
                                                        className="p-1 text-red-400 hover:text-red-300 hover:bg-red-400/10 rounded transition-colors"
                                                    >
                                                        <X className="w-4 h-4" />
                                                    </button>
                                                </div>
                                            ))}
                                        </div>
                                    </div>
                                )}
                            </div>
                        </div>
                    )}

                    {/* Step 4: On Flight */}
                    {currentStep === 4 && (
                        <div className="space-y-6">
                            <div className="text-center py-8">
                                <div className="w-20 h-20 bg-green-500/10 rounded-full flex items-center justify-center mx-auto mb-4">
                                    <CheckCircle className="w-10 h-10 text-green-500" />
                                </div>
                                <h3 className="text-2xl font-bold text-app-text-main mb-2">
                                    Documents Shared Successfully!
                                </h3>
                                <p className="text-sm text-app-text-muted">
                                    Your share link has been generated and emails have been sent to recipients
                                </p>
                            </div>

                            {/* Share Link */}
                            {shareLink && (
                                <div className="bg-app-bg-page p-4 rounded-xl border border-app-border">
                                    <label className="block text-sm font-semibold text-app-text-main mb-3">
                                        Share Link
                                    </label>
                                    <div className="flex space-x-2">
                                        <input
                                            type="text"
                                            value={shareLink}
                                            readOnly
                                            className="flex-1 px-4 py-2.5 bg-app-bg-card border border-app-border rounded-lg text-app-text-main"
                                        />
                                        <button
                                            onClick={() => copyToClipboard(shareLink)}
                                            className="px-4 py-2.5 bg-app-primary text-white rounded-lg hover:bg-app-primary-hover transition-colors font-medium"
                                        >
                                            Copy
                                        </button>
                                    </div>
                                </div>
                            )}

                            {/* Summary */}
                            <div className="grid grid-cols-2 gap-4">
                                <div className="bg-app-bg-page p-4 rounded-xl border border-app-border">
                                    <p className="text-xs text-app-text-muted mb-1">Documents Shared</p>
                                    <p className="text-2xl font-bold text-app-text-main">{selectedFiles.length}</p>
                                </div>
                                <div className="bg-app-bg-page p-4 rounded-xl border border-app-border">
                                    <p className="text-xs text-app-text-muted mb-1">Recipients</p>
                                    <p className="text-2xl font-bold text-app-text-main">
                                        {recipientEmails.filter(e => e.trim()).length}
                                    </p>
                                </div>
                            </div>

                            {/* Recipients List */}
                            {recipientEmails.filter(e => e.trim()).length > 0 && (
                                <div className="bg-app-bg-page p-4 rounded-xl border border-app-border">
                                    <p className="text-sm font-semibold text-app-text-main mb-3">
                                        Email sent to:
                                    </p>
                                    <div className="space-y-1">
                                        {recipientEmails.filter(e => e.trim()).map((email, index) => (
                                            <div key={index} className="flex items-center space-x-2 text-sm text-app-text-muted">
                                                <CheckCircle className="w-4 h-4 text-green-500" />
                                                <span>{email}</span>
                                            </div>
                                        ))}
                                    </div>
                                </div>
                            )}
                        </div>
                    )}
                </div>

                {/* Footer */}
                <div className="flex items-center justify-between px-6 py-4 border-t border-app-border bg-app-bg-page flex-shrink-0">
                    <button
                        onClick={() => {
                            if (currentStep === 1) {
                                handleClose();
                            } else if (currentStep === 4) {
                                handleClose();
                            } else {
                                setCurrentStep(prev => prev - 1);
                            }
                        }}
                        className="px-4 py-2 text-sm font-medium text-app-text-label hover:text-app-text-main transition-colors"
                    >
                        {currentStep === 4 ? 'Close' : currentStep === 1 ? 'Cancel' : 'Back'}
                    </button>
                    
                    {currentStep < 4 && (
                        <button
                            onClick={() => {
                                if (currentStep === 1 && uploadedFiles.length === 0) {
                                    alert('Please upload at least one document');
                                    return;
                                }
                                if (currentStep === 3) {
                                    handleGenerateLink();
                                } else {
                                    setCurrentStep(prev => prev + 1);
                                }
                            }}
                            disabled={sending || (currentStep === 1 && uploadedFiles.length === 0)}
                            className="px-6 py-2 bg-app-primary text-white rounded-lg hover:bg-app-primary-hover transition-colors font-medium disabled:opacity-50 disabled:cursor-not-allowed"
                        >
                            {sending ? 'Generating...' : currentStep === 3 ? 'Generate Link & Send' : 'Next'}
                        </button>
                    )}
                </div>
            </div>

            <style>{`
                @keyframes modalIn {
                    from { opacity: 0; transform: scale(0.94) translateY(8px); }
                    to   { opacity: 1; transform: scale(1)    translateY(0);   }
                }
            `}</style>
        </div>
    );
};

export default ShareDocumentModal;
