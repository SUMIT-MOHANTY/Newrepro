import { useState } from 'react';
import { X, FileText, Share2, Upload, Settings as SettingsIcon, Send, CheckCircle } from 'lucide-react';

const NewProjectModal = ({ isOpen, onClose, onStartWithBRD, onShareBRD }) => {
    if (!isOpen) return null;

    return (
        <div className="fixed inset-0 z-[9999] flex items-center justify-center p-4">
            {/* Backdrop */}
            <div
                className="absolute inset-0 bg-black/60 backdrop-blur-sm"
                onClick={onClose}
            />

            {/* Modal */}
            <div
                className="relative w-full max-w-2xl bg-app-bg-card rounded-2xl shadow-2xl border border-app-border overflow-hidden"
                style={{ animation: 'modalIn 0.2s cubic-bezier(0.34,1.56,0.64,1)' }}
                onClick={(e) => e.stopPropagation()}
            >
                {/* Header */}
                <div className="flex items-center justify-between px-6 py-4 border-b border-app-border bg-gradient-to-r from-app-primary/10 to-app-primary-dark/10">
                    <h2 className="text-xl font-bold text-app-text-main">Create New Project</h2>
                    <button
                        onClick={onClose}
                        className="p-2 rounded-lg text-app-text-light hover:text-app-text-main hover:bg-app-bg-hover transition-colors"
                    >
                        <X className="w-5 h-5" />
                    </button>
                </div>

                {/* Content */}
                <div className="p-6">
                    <p className="text-sm text-app-text-muted mb-6">
                        Choose how you want to start your project
                    </p>

                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                        {/* Start with BRD Option */}
                        <button
                            onClick={() => {
                                onStartWithBRD();
                                onClose();
                            }}
                            className="group relative p-6 rounded-xl border-2 border-app-border hover:border-app-primary bg-app-bg-page hover:bg-app-bg-card transition-all duration-300 text-left"
                        >
                            <div className="flex flex-col items-center text-center space-y-4">
                                <div className="w-16 h-16 rounded-full bg-app-primary/10 flex items-center justify-center group-hover:bg-app-primary/20 transition-colors">
                                    <FileText className="w-8 h-8 text-app-primary" />
                                </div>
                                <div>
                                    <h3 className="text-lg font-bold text-app-text-main mb-2">
                                        Start with BRD
                                    </h3>
                                    <p className="text-sm text-app-text-muted">
                                        Upload your Business Requirements Document and let AI analyze it to create a complete project roadmap
                                    </p>
                                </div>
                            </div>
                            <div className="absolute inset-0 rounded-xl bg-gradient-to-br from-app-primary/5 to-transparent opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none" />
                        </button>

                        {/* Share Your BRD Option */}
                        <button
                            onClick={() => {
                                onShareBRD();
                                // Don't close modal here - let the parent handle navigation
                            }}
                            className="group relative p-6 rounded-xl border-2 border-app-border hover:border-app-primary bg-app-bg-page hover:bg-app-bg-card transition-all duration-300 text-left"
                        >
                            <div className="flex flex-col items-center text-center space-y-4">
                                <div className="w-16 h-16 rounded-full bg-app-primary/10 flex items-center justify-center group-hover:bg-app-primary/20 transition-colors">
                                    <Share2 className="w-8 h-8 text-app-primary" />
                                </div>
                                <div>
                                    <h3 className="text-lg font-bold text-app-text-main mb-2">
                                        Share Your BRD
                                    </h3>
                                    <p className="text-sm text-app-text-muted">
                                        Upload and share your documents with team members or stakeholders via secure links
                                    </p>
                                </div>
                            </div>
                            <div className="absolute inset-0 rounded-xl bg-gradient-to-br from-app-primary/5 to-transparent opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none" />
                        </button>
                    </div>
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

export default NewProjectModal;
