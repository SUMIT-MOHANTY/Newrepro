/**
 * Utility functions for handling and sanitizing error messages
 * to provide user-friendly error messages instead of technical details
 */

/**
 * Sanitizes error messages to be user-friendly
 * @param {Error|string|any} error - The error to sanitize
 * @returns {string} - User-friendly error message
 */
export const sanitizeErrorMessage = (error) => {
    if (!error) return 'An unexpected error occurred. Please try again.';
    
    const errorMessage = typeof error === 'string' ? error : error.message || String(error);
    
    // Database/SQL errors
    if (errorMessage.includes('UNIQUE constraint failed') || 
        errorMessage.includes('IntegrityError') || 
        errorMessage.includes('sqlite3.IntegrityError') ||
        errorMessage.includes('governance_responses.project_token') ||
        errorMessage.includes('UNIQUE constraint') ||
        errorMessage.includes('duplicate key')) {
        return 'This project has already been processed. Please refresh the page or contact support if the issue persists.';
    }
    
    // Network/API errors
    if (errorMessage.includes('Failed to fetch') || 
        errorMessage.includes('NetworkError') ||
        errorMessage.includes('ERR_NETWORK') ||
        errorMessage.includes('net::') ||
        errorMessage.toLowerCase().includes('offline')) {
        return 'Network connection error. Please check your internet connection and try again.';
    }
    
    // Authentication errors
    if (errorMessage.includes('401') || 
        errorMessage.includes('Unauthorized') ||
        errorMessage.includes('Authentication failed')) {
        return 'Your session has expired. Please log in again.';
    }
    
    // Server errors
    if (errorMessage.includes('500') || 
        errorMessage.includes('Internal Server Error') ||
        errorMessage.includes('Server Error')) {
        return 'Server is temporarily unavailable. Please try again in a few moments.';
    }
    
    // Timeout errors
    if (errorMessage.includes('timeout') || 
        errorMessage.includes('TIMEOUT')) {
        return 'Request timed out. Please try again.';
    }
    
    // Permission/access errors
    if (errorMessage.includes('403') || 
        errorMessage.includes('Forbidden') ||
        errorMessage.includes('Access denied')) {
        return 'You do not have permission to perform this action.';
    }
    
    // Git/repository errors
    if (errorMessage.includes('git') || 
        errorMessage.includes('repository') ||
        errorMessage.includes('clone')) {
        return 'Repository access error. Please check your Git URL and credentials.';
    }
    
    // Generic API errors - clean up technical details
    if (errorMessage.includes('Failed to') && errorMessage.length > 100) {
        return 'Operation failed. Please try again or contact support if the problem continues.';
    }
    
    // If it's a short, user-friendly message, keep it
    if (errorMessage.length < 100 && !errorMessage.includes('(') && !errorMessage.includes('[')) {
        return errorMessage;
    }
    
    // Default fallback for any other technical errors
    return 'Something went wrong. Please try again or contact support if the issue persists.';
};

/**
 * Logs the original error for debugging while returning a sanitized message
 * @param {Error|string|any} error - The error to handle
 * @param {string} context - Context about where the error occurred
 * @returns {string} - User-friendly error message
 */
export const handleError = (error, context = 'Unknown') => {
    console.error(`Error in ${context}:`, error);
    return sanitizeErrorMessage(error);
};

/**
 * Common error messages for specific scenarios
 */
export const ERROR_MESSAGES = {
    NETWORK: 'Network connection error. Please check your internet connection and try again.',
    AUTH: 'Your session has expired. Please log in again.',
    SERVER: 'Server is temporarily unavailable. Please try again in a few moments.',
    PERMISSION: 'You do not have permission to perform this action.',
    NOT_FOUND: 'The requested resource was not found.',
    VALIDATION: 'Please check your input and try again.',
    GENERIC: 'Something went wrong. Please try again or contact support if the issue persists.'
};