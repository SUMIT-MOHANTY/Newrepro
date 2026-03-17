/**
 * Global modal helpers that can be used without React context
 * These functions will dispatch custom events that the ModalProvider listens to
 */

// Custom event types
const MODAL_EVENTS = {
    SHOW_ALERT: 'custom-modal-alert',
    SHOW_CONFIRM: 'custom-modal-confirm',
    SHOW_ERROR: 'custom-modal-error',
    SHOW_SUCCESS: 'custom-modal-success',
    SHOW_WARNING: 'custom-modal-warning',
    SHOW_PROMPT: 'custom-modal-prompt'
};

/**
 * Show an alert modal (replacement for window.alert)
 * @param {string} message - The message to display
 * @param {string} title - Optional title
 * @returns {Promise<boolean>} - Always resolves to true
 */
export const customAlert = (message, title = 'Alert') => {
    return new Promise((resolve) => {
        const event = new CustomEvent(MODAL_EVENTS.SHOW_ALERT, {
            detail: { message, title, resolve }
        });
        window.dispatchEvent(event);
    });
};

/**
 * Show a confirm modal (replacement for window.confirm)
 * @param {string} message - The message to display
 * @param {string} title - Optional title
 * @returns {Promise<boolean>} - Resolves to true if confirmed, false if cancelled
 */
export const customConfirm = (message, title = 'Confirm') => {
    return new Promise((resolve) => {
        const event = new CustomEvent(MODAL_EVENTS.SHOW_CONFIRM, {
            detail: { message, title, resolve }
        });
        window.dispatchEvent(event);
    });
};

/**
 * Show an error modal
 * @param {string} message - The error message to display
 * @param {string} title - Optional title
 * @returns {Promise<boolean>} - Always resolves to true
 */
export const customError = (message, title = 'Error') => {
    return new Promise((resolve) => {
        const event = new CustomEvent(MODAL_EVENTS.SHOW_ERROR, {
            detail: { message, title, resolve }
        });
        window.dispatchEvent(event);
    });
};

/**
 * Show a success modal
 * @param {string} message - The success message to display
 * @param {string} title - Optional title
 * @returns {Promise<boolean>} - Always resolves to true
 */
export const customSuccess = (message, title = 'Success') => {
    return new Promise((resolve) => {
        const event = new CustomEvent(MODAL_EVENTS.SHOW_SUCCESS, {
            detail: { message, title, resolve }
        });
        window.dispatchEvent(event);
    });
};

/**
 * Show a warning modal
 * @param {string} message - The warning message to display
 * @param {string} title - Optional title
 * @returns {Promise<boolean>} - Always resolves to true
 */
export const customWarning = (message, title = 'Warning') => {
    return new Promise((resolve) => {
        const event = new CustomEvent(MODAL_EVENTS.SHOW_WARNING, {
            detail: { message, title, resolve }
        });
        window.dispatchEvent(event);
    });
};

/**
 * Show a prompt modal (replacement for window.prompt)
 * @param {string} message - The message to display
 * @param {string} title - Optional title
 * @param {string} defaultValue - Default input value
 * @param {string} placeholder - Input placeholder text
 * @returns {Promise<string|null>} - Resolves to input value if confirmed, null if cancelled
 */
export const customPrompt = (message, title = 'Input Required', defaultValue = '', placeholder = '') => {
    return new Promise((resolve) => {
        const event = new CustomEvent(MODAL_EVENTS.SHOW_PROMPT, {
            detail: { message, title, defaultValue, placeholder, resolve }
        });
        window.dispatchEvent(event);
    });
};

// Export event types for use in ModalProvider
export { MODAL_EVENTS };