import { createContext, useContext, useEffect } from 'react';
import { useCustomModal } from '../hooks/useCustomModal';
import { MODAL_EVENTS } from '../utils/modalHelpers';
import CustomModal from '../components/CustomModal';

const ModalContext = createContext();

export const useModal = () => {
    const context = useContext(ModalContext);
    if (!context) {
        throw new Error('useModal must be used within a ModalProvider');
    }
    return context;
};

export const ModalProvider = ({ children }) => {
    const modal = useCustomModal();

    // Listen for global modal events
    useEffect(() => {
        const handleAlert = (event) => {
            const { message, title, resolve } = event.detail;
            modal.showAlert(message, title).then(resolve);
        };

        const handleConfirm = (event) => {
            const { message, title, resolve } = event.detail;
            modal.showConfirm(message, title).then(resolve);
        };

        const handleError = (event) => {
            const { message, title, resolve } = event.detail;
            modal.showError(message, title).then(resolve);
        };

        const handleSuccess = (event) => {
            const { message, title, resolve } = event.detail;
            modal.showSuccess(message, title).then(resolve);
        };

        const handleWarning = (event) => {
            const { message, title, resolve } = event.detail;
            modal.showWarning(message, title).then(resolve);
        };

        const handlePrompt = (event) => {
            const { message, title, defaultValue, placeholder, resolve } = event.detail;
            modal.showPrompt(message, title, defaultValue, placeholder).then(resolve);
        };

        window.addEventListener(MODAL_EVENTS.SHOW_ALERT, handleAlert);
        window.addEventListener(MODAL_EVENTS.SHOW_CONFIRM, handleConfirm);
        window.addEventListener(MODAL_EVENTS.SHOW_ERROR, handleError);
        window.addEventListener(MODAL_EVENTS.SHOW_SUCCESS, handleSuccess);
        window.addEventListener(MODAL_EVENTS.SHOW_WARNING, handleWarning);
        window.addEventListener(MODAL_EVENTS.SHOW_PROMPT, handlePrompt);

        return () => {
            window.removeEventListener(MODAL_EVENTS.SHOW_ALERT, handleAlert);
            window.removeEventListener(MODAL_EVENTS.SHOW_CONFIRM, handleConfirm);
            window.removeEventListener(MODAL_EVENTS.SHOW_ERROR, handleError);
            window.removeEventListener(MODAL_EVENTS.SHOW_SUCCESS, handleSuccess);
            window.removeEventListener(MODAL_EVENTS.SHOW_WARNING, handleWarning);
            window.removeEventListener(MODAL_EVENTS.SHOW_PROMPT, handlePrompt);
        };
    }, [modal]);

    return (
        <ModalContext.Provider value={modal}>
            {children}
            <CustomModal
                isOpen={modal.modalState.isOpen}
                onClose={modal.modalState.onClose}
                onConfirm={modal.modalState.onConfirm}
                title={modal.modalState.title}
                message={modal.modalState.message}
                type={modal.modalState.type}
                confirmText={modal.modalState.confirmText}
                cancelText={modal.modalState.cancelText}
                showCancel={modal.modalState.showCancel}
                size={modal.modalState.size}
                promptValue={modal.modalState.promptValue}
                onPromptChange={modal.modalState.onPromptChange}
                promptPlaceholder={modal.modalState.promptPlaceholder}
            />
        </ModalContext.Provider>
    );
};