import React, { useState, useEffect } from 'react';
import { Volume2, VolumeX, Smartphone, Settings, Eye, EyeOff } from 'lucide-react';
import { getModalPreferences, setModalPreferences, playModalSound, triggerHapticFeedback } from '../utils/modalEffects';

const ModalSettings = ({ isOpen, onClose }) => {
    const [preferences, setPreferences] = useState(getModalPreferences());

    useEffect(() => {
        if (isOpen) {
            setPreferences(getModalPreferences());
        }
    }, [isOpen]);

    const updatePreference = (key, value) => {
        const newPrefs = { ...preferences, [key]: value };
        setPreferences(newPrefs);
        setModalPreferences(newPrefs);
        
        // Test the setting immediately
        if (key === 'soundEnabled' && value) {
            playModalSound('info', true);
        }
        if (key === 'hapticEnabled' && value) {
            triggerHapticFeedback('info', true);
        }
    };

    if (!isOpen) return null;

    return (
        <div className="fixed inset-0 z-[500] overflow-y-auto">
            <div 
                className="fixed inset-0 bg-black/60 backdrop-blur-sm transition-all duration-300"
                onClick={onClose}
            />
            
            <div className="flex min-h-full items-center justify-center p-4">
                <div 
                    className="relative w-full max-w-md transform overflow-hidden rounded-3xl bg-white dark:bg-gray-900 shadow-2xl transition-all duration-300 border-t-4 border-blue-500"
                    onClick={(e) => e.stopPropagation()}
                >
                    {/* Header */}
                    <div className="bg-gradient-to-br from-blue-50 via-indigo-50 to-purple-50 dark:from-blue-900/20 dark:via-indigo-900/20 dark:to-purple-900/20 px-8 py-8 text-center relative overflow-hidden">
                        <div className="absolute top-0 left-0 w-32 h-32 bg-white/10 rounded-full -translate-x-16 -translate-y-16 animate-pulse"></div>
                        <div className="absolute bottom-0 right-0 w-24 h-24 bg-white/10 rounded-full translate-x-12 translate-y-12 animate-pulse" style={{ animationDelay: '1s' }}></div>
                        
                        <div className="inline-flex items-center justify-center w-20 h-20 bg-gradient-to-br from-blue-100 to-blue-200 dark:from-blue-900/30 dark:to-blue-800/30 rounded-full mb-4 shadow-lg">
                            <Settings className="w-10 h-10 text-blue-500" />
                        </div>
                        
                        <h3 className="text-xl font-bold text-gray-900 dark:text-white mb-2">
                            Modal Settings
                        </h3>
                        <p className="text-sm text-gray-600 dark:text-gray-400">
                            Customize your modal experience
                        </p>
                    </div>

                    {/* Settings */}
                    <div className="px-8 py-6 space-y-6">
                        {/* Sound Settings */}
                        <div className="flex items-center justify-between">
                            <div className="flex items-center gap-3">
                                {preferences.soundEnabled ? (
                                    <Volume2 className="w-5 h-5 text-blue-500" />
                                ) : (
                                    <VolumeX className="w-5 h-5 text-gray-400" />
                                )}
                                <div>
                                    <p className="font-medium text-gray-900 dark:text-white">Sound Effects</p>
                                    <p className="text-sm text-gray-500 dark:text-gray-400">Play sounds when modals appear</p>
                                </div>
                            </div>
                            <button
                                onClick={() => updatePreference('soundEnabled', !preferences.soundEnabled)}
                                className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
                                    preferences.soundEnabled ? 'bg-blue-600' : 'bg-gray-200 dark:bg-gray-700'
                                }`}
                            >
                                <span
                                    className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                                        preferences.soundEnabled ? 'translate-x-6' : 'translate-x-1'
                                    }`}
                                />
                            </button>
                        </div>

                        {/* Haptic Feedback */}
                        <div className="flex items-center justify-between">
                            <div className="flex items-center gap-3">
                                <Smartphone className={`w-5 h-5 ${preferences.hapticEnabled ? 'text-blue-500' : 'text-gray-400'}`} />
                                <div>
                                    <p className="font-medium text-gray-900 dark:text-white">Haptic Feedback</p>
                                    <p className="text-sm text-gray-500 dark:text-gray-400">Vibrate on mobile devices</p>
                                </div>
                            </div>
                            <button
                                onClick={() => updatePreference('hapticEnabled', !preferences.hapticEnabled)}
                                className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
                                    preferences.hapticEnabled ? 'bg-blue-600' : 'bg-gray-200 dark:bg-gray-700'
                                }`}
                            >
                                <span
                                    className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                                        preferences.hapticEnabled ? 'translate-x-6' : 'translate-x-1'
                                    }`}
                                />
                            </button>
                        </div>

                        {/* Animations */}
                        <div className="flex items-center justify-between">
                            <div className="flex items-center gap-3">
                                {preferences.animationsEnabled ? (
                                    <Eye className="w-5 h-5 text-blue-500" />
                                ) : (
                                    <EyeOff className="w-5 h-5 text-gray-400" />
                                )}
                                <div>
                                    <p className="font-medium text-gray-900 dark:text-white">Animations</p>
                                    <p className="text-sm text-gray-500 dark:text-gray-400">Enable smooth animations</p>
                                </div>
                            </div>
                            <button
                                onClick={() => updatePreference('animationsEnabled', !preferences.animationsEnabled)}
                                className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
                                    preferences.animationsEnabled ? 'bg-blue-600' : 'bg-gray-200 dark:bg-gray-700'
                                }`}
                            >
                                <span
                                    className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                                        preferences.animationsEnabled ? 'translate-x-6' : 'translate-x-1'
                                    }`}
                                />
                            </button>
                        </div>
                    </div>

                    {/* Footer */}
                    <div className="px-8 py-6 bg-gradient-to-r from-gray-50 to-gray-100 dark:from-gray-800/50 dark:to-gray-900/50 flex justify-center">
                        <button
                            onClick={onClose}
                            className="px-8 py-3 text-sm font-semibold text-white bg-gradient-to-r from-blue-500 to-blue-600 hover:from-blue-600 hover:to-blue-700 rounded-xl focus:outline-none focus:ring-4 focus:ring-blue-500/20 hover:scale-105 transition-all duration-200 shadow-lg hover:shadow-xl"
                        >
                            Done
                        </button>
                    </div>
                </div>
            </div>
        </div>
    );
};

export default ModalSettings;