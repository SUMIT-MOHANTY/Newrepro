import React, { useState } from 'react';
import { useModal } from '../contexts/ModalContext';
import { customAlert, customConfirm, customError, customSuccess, customWarning, customPrompt } from '../utils/modalHelpers';
import ModalSettings from './ModalSettings';
import { Settings } from 'lucide-react';

/**
 * Example component demonstrating how to use the custom modal system
 * This replaces browser's alert(), confirm(), prompt(), etc. with custom styled modals
 */
const ModalExample = () => {
    const [showSettings, setShowSettings] = useState(false);
    // Method 1: Using the useModal hook (within React components)
    const { showAlert, showConfirm, showError, showSuccess, showWarning, showPrompt } = useModal();

    const handleReactHookExamples = async () => {
        // Simple alert
        await showAlert('This is a beautiful custom alert message with enhanced styling!', 'Welcome');
        
        // Confirm dialog
        const confirmed = await showConfirm('Do you want to proceed with this action? This will demonstrate the confirm modal.', 'Confirm Action');
        if (confirmed) {
            await showSuccess('You confirmed the action! This success modal looks great.', 'Action Confirmed');
        } else {
            await showWarning('Action was cancelled. This is how warnings look.', 'Action Cancelled');
        }
        
        // Prompt dialog
        const userInput = await showPrompt('Please enter your name to see the prompt modal in action:', 'User Information', 'John Doe', 'Enter your full name...');
        if (userInput) {
            await showSuccess(`Hello, ${userInput}! Your input was: "${userInput}"`, 'Welcome!');
        }
        
        // Error message
        await showError('This is how error messages look in the new modal system. Much better than browser alerts!', 'Error Example');
    };

    // Method 2: Using global helper functions (can be used anywhere)
    const handleGlobalHelperExamples = async () => {
        // These can be called from anywhere in your app, even outside React components
        await customAlert('This is a global alert using the helper function!', 'Global Alert');
        
        const result = await customConfirm('Are you sure you want to delete this item? This action cannot be undone.', 'Delete Confirmation');
        if (result) {
            await customSuccess('Item deleted successfully! The operation completed without errors.', 'Deletion Complete');
        }
        
        // Prompt for user input
        const reason = await customPrompt('Please provide a reason for this change:', 'Input Required', '', 'Enter your reason here...');
        if (reason) {
            await customSuccess(`Reason provided: "${reason}"\n\nThank you for providing the details!`, 'Reason Recorded');
        }
        
        await customWarning('This is a warning message using the global helper function.', 'Warning Example');
        await customError('This is an error message using the global helper function.', 'Error Example');
    };

    const handleShowAllTypes = async () => {
        await showSuccess('Success! Everything is working perfectly.', 'Success Modal');
        await showWarning('Warning! Please check your input.', 'Warning Modal');
        await showError('Error! Something went wrong.', 'Error Modal');
        await showAlert('Information: This is an info modal.', 'Info Modal');
        
        const confirmed = await showConfirm('Do you want to continue?', 'Confirmation Modal');
        if (confirmed) {
            const input = await showPrompt('Enter some text:', 'Prompt Modal', 'Default text', 'Type something...');
            if (input) {
                await showSuccess(`You entered: "${input}"`, 'Input Received');
            }
        }
    };

    return (
        <div className="p-8 max-w-4xl mx-auto space-y-8">
            <div className="text-center">
                <h2 className="text-3xl font-bold text-gray-900 dark:text-white mb-4">Beautiful Custom Modals</h2>
                <p className="text-gray-600 dark:text-gray-400 mb-6">
                    Experience the new and improved modal system with beautiful animations, sound effects, and haptic feedback.
                </p>
                
                <button
                    onClick={() => setShowSettings(true)}
                    className="inline-flex items-center gap-2 px-4 py-2 bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-300 rounded-lg hover:bg-gray-200 dark:hover:bg-gray-700 transition-colors"
                >
                    <Settings className="w-4 h-4" />
                    Modal Settings
                </button>
            </div>
            
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                <div className="bg-white dark:bg-gray-800 rounded-2xl p-6 shadow-lg border border-gray-200 dark:border-gray-700">
                    <h3 className="text-lg font-semibold mb-4 text-gray-900 dark:text-white">React Hook Methods</h3>
                    <p className="text-sm text-gray-600 dark:text-gray-400 mb-4">
                        Use these methods within React components for the best integration.
                    </p>
                    <button
                        onClick={handleReactHookExamples}
                        className="w-full px-4 py-3 bg-gradient-to-r from-blue-500 to-blue-600 text-white rounded-xl hover:from-blue-600 hover:to-blue-700 transition-all duration-200 font-semibold shadow-lg hover:shadow-xl hover:scale-105"
                    >
                        Test React Hook Methods
                    </button>
                </div>
                
                <div className="bg-white dark:bg-gray-800 rounded-2xl p-6 shadow-lg border border-gray-200 dark:border-gray-700">
                    <h3 className="text-lg font-semibold mb-4 text-gray-900 dark:text-white">Global Helper Methods</h3>
                    <p className="text-sm text-gray-600 dark:text-gray-400 mb-4">
                        Use these anywhere in your app, even outside React components.
                    </p>
                    <button
                        onClick={handleGlobalHelperExamples}
                        className="w-full px-4 py-3 bg-gradient-to-r from-green-500 to-green-600 text-white rounded-xl hover:from-green-600 hover:to-green-700 transition-all duration-200 font-semibold shadow-lg hover:shadow-xl hover:scale-105"
                    >
                        Test Global Helper Methods
                    </button>
                </div>

                <div className="bg-white dark:bg-gray-800 rounded-2xl p-6 shadow-lg border border-gray-200 dark:border-gray-700">
                    <h3 className="text-lg font-semibold mb-4 text-gray-900 dark:text-white">All Modal Types</h3>
                    <p className="text-sm text-gray-600 dark:text-gray-400 mb-4">
                        See all different modal types and their beautiful designs.
                    </p>
                    <button
                        onClick={handleShowAllTypes}
                        className="w-full px-4 py-3 bg-gradient-to-r from-purple-500 to-purple-600 text-white rounded-xl hover:from-purple-600 hover:to-purple-700 transition-all duration-200 font-semibold shadow-lg hover:shadow-xl hover:scale-105"
                    >
                        Show All Modal Types
                    </button>
                </div>
            </div>
            
            <div className="bg-gradient-to-r from-gray-50 to-gray-100 dark:from-gray-800 dark:to-gray-900 rounded-2xl p-8 border border-gray-200 dark:border-gray-700">
                <h3 className="text-xl font-bold mb-6 text-gray-900 dark:text-white">Features</h3>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                    <div>
                        <h4 className="font-semibold text-gray-900 dark:text-white mb-2">🎨 Beautiful Design</h4>
                        <ul className="text-sm text-gray-600 dark:text-gray-400 space-y-1">
                            <li>• Gradient backgrounds and shadows</li>
                            <li>• Type-specific colors and icons</li>
                            <li>• Smooth animations and transitions</li>
                            <li>• Dark mode support</li>
                        </ul>
                    </div>
                    <div>
                        <h4 className="font-semibold text-gray-900 dark:text-white mb-2">🔧 Enhanced Features</h4>
                        <ul className="text-sm text-gray-600 dark:text-gray-400 space-y-1">
                            <li>• Sound effects (optional)</li>
                            <li>• Haptic feedback on mobile</li>
                            <li>• Keyboard navigation (ESC, Enter)</li>
                            <li>• Focus management</li>
                        </ul>
                    </div>
                    <div>
                        <h4 className="font-semibold text-gray-900 dark:text-white mb-2">♿ Accessibility</h4>
                        <ul className="text-sm text-gray-600 dark:text-gray-400 space-y-1">
                            <li>• Screen reader friendly</li>
                            <li>• Proper ARIA labels</li>
                            <li>• Focus trapping</li>
                            <li>• High contrast support</li>
                        </ul>
                    </div>
                    <div>
                        <h4 className="font-semibold text-gray-900 dark:text-white mb-2">📱 Responsive</h4>
                        <ul className="text-sm text-gray-600 dark:text-gray-400 space-y-1">
                            <li>• Mobile-optimized layouts</li>
                            <li>• Touch-friendly buttons</li>
                            <li>• Adaptive sizing</li>
                            <li>• Backdrop blur effects</li>
                        </ul>
                    </div>
                </div>
            </div>

            <ModalSettings isOpen={showSettings} onClose={() => setShowSettings(false)} />
        </div>
    );
};

export default ModalExample;