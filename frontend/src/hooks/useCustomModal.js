import { useState, useCallback } from 'react';

export const useCustomModal = () => {
    const [modalState, setModalState] = useState({
        isOpen: false,
        title: '',
        message: '',
        type: 'info',
        confirmText: 'OK',
        cancelText: 'Cancel',
        showCancel: false,
        size: 'md',
        promptValue: '',
        promptPlaceholder: '',
        onConfirm: null,
        onClose: null,
        onPromptChange: null
    });

    const showModal = useCallback((options) => {
        return new Promise((resolve) => {
            const promptValue = options.type === 'prompt' ? (options.defaultValue || '') : '';
            
            setModalState({
                isOpen: true,
                title: options.title || '',
                message: options.message || '',
                type: options.type || 'info',
                confirmText: options.confirmText || 'OK',
                cancelText: options.cancelText || 'Cancel',
                showCancel: options.showCancel || false,
                size: options.size || 'md',
                promptValue,
                promptPlaceholder: options.placeholder || '',
                onConfirm: () => {
                    setModalState(prev => ({ ...prev, isOpen: false }));
                    if (options.type === 'prompt') {
                        resolve(modalState.promptValue || promptValue);
                    } else {
                        resolve(true);
                    }
                },
                onClose: () => {
                    setModalState(prev => ({ ...prev, isOpen: false }));
                    resolve(options.type === 'prompt' ? null : false);
                },
                onPromptChange: (value) => {
                    setModalState(prev => ({ ...prev, promptValue: value }));
                }
            });
        });
    }, [modalState.promptValue]);

    const hideModal = useCallback(() => {
        setModalState(prev => ({ ...prev, isOpen: false }));
    }, []);

    // Convenience methods
    const showAlert = useCallback((message, title = 'Alert', type = 'info') => {
        return showModal({
            title,
            message,
            type,
            confirmText: 'OK',
            showCancel: false
        });
    }, [showModal]);

    const showConfirm = useCallback((message, title = 'Confirm') => {
        return showModal({
            title,
            message,
            type: 'confirm',
            confirmText: 'OK',
            cancelText: 'Cancel',
            showCancel: true
        });
    }, [showModal]);

    const showError = useCallback((message, title = 'Error') => {
        return showModal({
            title,
            message,
            type: 'error',
            confirmText: 'OK',
            showCancel: false
        });
    }, [showModal]);

    const showSuccess = useCallback((message, title = 'Success') => {
        return showModal({
            title,
            message,
            type: 'success',
            confirmText: 'OK',
            showCancel: false
        });
    }, [showModal]);

    const showWarning = useCallback((message, title = 'Warning') => {
        return showModal({
            title,
            message,
            type: 'warning',
            confirmText: 'OK',
            showCancel: false
        });
    }, [showModal]);

    const showPrompt = useCallback((message, title = 'Input Required', defaultValue = '', placeholder = '') => {
        return showModal({
            title,
            message,
            type: 'prompt',
            confirmText: 'OK',
            cancelText: 'Cancel',
            showCancel: true,
            defaultValue,
            placeholder
        });
    }, [showModal]);

    return {
        modalState,
        showModal,
        hideModal,
        showAlert,
        showConfirm,
        showError,
        showSuccess,
        showWarning,
        showPrompt
    };
};