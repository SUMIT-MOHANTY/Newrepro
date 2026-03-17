import { useEffect, useRef } from 'react';
import { X, AlertTriangle, CheckCircle2, Info, AlertCircle, HelpCircle } from 'lucide-react';

const TYPE_CONFIG = {
    info: {
        icon: Info,
        iconColor: 'text-app-primary',
        iconBg: 'bg-app-primary-light',
        accent: 'bg-app-primary',
        btn: 'bg-app-primary hover:bg-app-primary-hover text-white',
    },
    success: {
        icon: CheckCircle2,
        iconColor: 'text-app-status-success',
        iconBg: 'bg-app-status-successBg',
        accent: 'bg-app-status-success',
        btn: 'bg-app-status-success hover:opacity-90 text-white',
    },
    warning: {
        icon: AlertTriangle,
        iconColor: 'text-app-status-warning',
        iconBg: 'bg-app-status-warningBg',
        accent: 'bg-app-status-warning',
        btn: 'bg-app-status-warning hover:opacity-90 text-white',
    },
    error: {
        icon: AlertCircle,
        iconColor: 'text-app-status-error',
        iconBg: 'bg-app-status-errorBg',
        accent: 'bg-app-status-error',
        btn: 'bg-app-status-error hover:opacity-90 text-white',
    },
    confirm: {
        icon: HelpCircle,
        iconColor: 'text-app-primary',
        iconBg: 'bg-app-primary-light',
        accent: 'bg-app-primary',
        btn: 'bg-app-primary hover:bg-app-primary-hover text-white',
    },
    prompt: {
        icon: HelpCircle,
        iconColor: 'text-app-primary',
        iconBg: 'bg-app-primary-light',
        accent: 'bg-app-primary',
        btn: 'bg-app-primary hover:bg-app-primary-hover text-white',
    },
};

const DEFAULT_TITLES = {
    info: 'Information',
    success: 'Success',
    warning: 'Warning',
    error: 'Error',
    confirm: 'Confirm Action',
    prompt: 'Input Required',
};

const CustomModal = ({
    isOpen,
    onClose,
    onConfirm,
    title,
    message,
    type = 'info',
    confirmText = 'OK',
    cancelText = 'Cancel',
    showCancel = false,
    size = 'md',
    promptValue = '',
    onPromptChange,
    promptPlaceholder = '',
}) => {
    const inputRef = useRef(null);

    useEffect(() => {
        const handleEsc = (e) => { if (e.key === 'Escape' && isOpen) onClose(); };
        document.addEventListener('keydown', handleEsc);
        return () => document.removeEventListener('keydown', handleEsc);
    }, [isOpen, onClose]);

    useEffect(() => {
        if (isOpen) {
            document.body.style.overflow = 'hidden';
            if (type === 'prompt') {
                setTimeout(() => inputRef.current?.focus(), 50);
            }
        } else {
            document.body.style.overflow = '';
        }
        return () => { document.body.style.overflow = ''; };
    }, [isOpen, type]);

    if (!isOpen) return null;

    const cfg = TYPE_CONFIG[type] || TYPE_CONFIG.info;
    const Icon = cfg.icon;

    const sizeClass = { sm: 'max-w-sm', md: 'max-w-md', lg: 'max-w-lg', xl: 'max-w-xl' }[size] ?? 'max-w-md';

    const handleConfirm = () => (onConfirm ? onConfirm() : onClose());
    const showCancelBtn = showCancel || type === 'confirm' || type === 'prompt';

    return (
        <div className="fixed inset-0 z-[9999] flex items-center justify-center p-4">
            {/* Backdrop */}
            <div
                className="absolute inset-0 bg-app-text-main/50 backdrop-blur-sm"
                onClick={onClose}
            />

            {/* Panel */}
            <div
                className={`relative w-full ${sizeClass} bg-app-bg-card rounded-2xl shadow-2xl border border-app-border overflow-hidden`}
                style={{ animation: 'modalIn 0.2s cubic-bezier(0.34,1.56,0.64,1)' }}
                onClick={(e) => e.stopPropagation()}
            >
                {/* Accent bar */}
                <div className={`h-1 w-full ${cfg.accent}`} />

                {/* Header */}
                <div className="flex items-start gap-3 px-5 pt-5 pb-4">
                    <div className={`flex-shrink-0 w-9 h-9 rounded-xl flex items-center justify-center ${cfg.iconBg}`}>
                        <Icon className={`w-5 h-5 ${cfg.iconColor}`} />
                    </div>
                    <div className="flex-1 min-w-0 pt-0.5">
                        <h3 className="text-sm font-semibold text-app-text-main leading-tight">
                            {title || DEFAULT_TITLES[type]}
                        </h3>
                        {message && (
                            <p className="mt-1.5 text-sm text-app-text-muted leading-relaxed whitespace-pre-wrap">
                                {message}
                            </p>
                        )}
                    </div>
                    <button
                        onClick={onClose}
                        className="flex-shrink-0 w-7 h-7 rounded-lg flex items-center justify-center text-app-text-light hover:text-app-text-main hover:bg-app-bg-hover transition-colors"
                    >
                        <X className="w-4 h-4" />
                    </button>
                </div>

                {/* Prompt input */}
                {type === 'prompt' && (
                    <div className="px-5 pb-4">
                        <input
                            ref={inputRef}
                            type="text"
                            value={promptValue}
                            onChange={(e) => onPromptChange?.(e.target.value)}
                            placeholder={promptPlaceholder}
                            className="w-full px-3 py-2.5 text-sm bg-app-bg-page border border-app-border rounded-xl text-app-text-main placeholder-app-text-light focus:outline-none focus:ring-2 focus:ring-app-primary-ring focus:border-app-primary transition-all"
                            onKeyDown={(e) => { if (e.key === 'Enter') handleConfirm(); }}
                        />
                    </div>
                )}

                {/* Footer */}
                <div className="flex items-center justify-end gap-2 px-5 py-3.5 bg-app-bg-muted border-t border-app-border">
                    {showCancelBtn && (
                        <button
                            onClick={onClose}
                            className="px-4 py-2 text-xs font-semibold rounded-lg border border-app-border bg-app-bg-card text-app-text-label hover:bg-app-bg-hover hover:text-app-text-main transition-all"
                        >
                            {cancelText}
                        </button>
                    )}
                    <button
                        onClick={handleConfirm}
                        className={`px-4 py-2 text-xs font-semibold rounded-lg transition-all shadow-sm ${cfg.btn}`}
                    >
                        {confirmText}
                    </button>
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

export default CustomModal;
