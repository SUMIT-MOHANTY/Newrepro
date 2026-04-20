/**
 * Modal Effects Utilities
 * Provides sound effects and haptic feedback for modals
 */

// Sound effects for different modal types
const MODAL_SOUNDS = {
    success: () => {
        // Create a pleasant success sound
        const audioContext = new (window.AudioContext || window.webkitAudioContext)();
        const oscillator = audioContext.createOscillator();
        const gainNode = audioContext.createGain();
        
        oscillator.connect(gainNode);
        gainNode.connect(audioContext.destination);
        
        oscillator.frequency.setValueAtTime(523.25, audioContext.currentTime); // C5
        oscillator.frequency.setValueAtTime(659.25, audioContext.currentTime + 0.1); // E5
        oscillator.frequency.setValueAtTime(783.99, audioContext.currentTime + 0.2); // G5
        
        gainNode.gain.setValueAtTime(0.1, audioContext.currentTime);
        gainNode.gain.exponentialRampToValueAtTime(0.01, audioContext.currentTime + 0.3);
        
        oscillator.start(audioContext.currentTime);
        oscillator.stop(audioContext.currentTime + 0.3);
    },
    
    error: () => {
        // Create an error sound
        const audioContext = new (window.AudioContext || window.webkitAudioContext)();
        const oscillator = audioContext.createOscillator();
        const gainNode = audioContext.createGain();
        
        oscillator.connect(gainNode);
        gainNode.connect(audioContext.destination);
        
        oscillator.frequency.setValueAtTime(200, audioContext.currentTime);
        oscillator.frequency.setValueAtTime(150, audioContext.currentTime + 0.1);
        
        gainNode.gain.setValueAtTime(0.1, audioContext.currentTime);
        gainNode.gain.exponentialRampToValueAtTime(0.01, audioContext.currentTime + 0.2);
        
        oscillator.start(audioContext.currentTime);
        oscillator.stop(audioContext.currentTime + 0.2);
    },
    
    warning: () => {
        // Create a warning sound
        const audioContext = new (window.AudioContext || window.webkitAudioContext)();
        const oscillator = audioContext.createOscillator();
        const gainNode = audioContext.createGain();
        
        oscillator.connect(gainNode);
        gainNode.connect(audioContext.destination);
        
        oscillator.frequency.setValueAtTime(440, audioContext.currentTime); // A4
        oscillator.frequency.setValueAtTime(440, audioContext.currentTime + 0.1);
        
        gainNode.gain.setValueAtTime(0.08, audioContext.currentTime);
        gainNode.gain.exponentialRampToValueAtTime(0.01, audioContext.currentTime + 0.15);
        
        oscillator.start(audioContext.currentTime);
        oscillator.stop(audioContext.currentTime + 0.15);
    },
    
    info: () => {
        // Create a subtle info sound
        const audioContext = new (window.AudioContext || window.webkitAudioContext)();
        const oscillator = audioContext.createOscillator();
        const gainNode = audioContext.createGain();
        
        oscillator.connect(gainNode);
        gainNode.connect(audioContext.destination);
        
        oscillator.frequency.setValueAtTime(800, audioContext.currentTime);
        
        gainNode.gain.setValueAtTime(0.05, audioContext.currentTime);
        gainNode.gain.exponentialRampToValueAtTime(0.01, audioContext.currentTime + 0.1);
        
        oscillator.start(audioContext.currentTime);
        oscillator.stop(audioContext.currentTime + 0.1);
    }
};

/**
 * Play sound effect for modal type
 * @param {string} type - Modal type (success, error, warning, info, confirm, prompt)
 * @param {boolean} enabled - Whether sound is enabled
 */
export const playModalSound = (type, enabled = true) => {
    if (!enabled || !window.AudioContext && !window.webkitAudioContext) return;
    
    try {
        const soundType = type === 'confirm' || type === 'prompt' ? 'info' : type;
        if (MODAL_SOUNDS[soundType]) {
            MODAL_SOUNDS[soundType]();
        }
    } catch (error) {
        console.warn('Could not play modal sound:', error);
    }
};

/**
 * Trigger haptic feedback if available
 * @param {string} type - Modal type
 * @param {boolean} enabled - Whether haptic feedback is enabled
 */
export const triggerHapticFeedback = (type, enabled = true) => {
    if (!enabled || !navigator.vibrate) return;
    
    try {
        switch (type) {
            case 'success':
                navigator.vibrate([50, 50, 100]); // Short-short-long
                break;
            case 'error':
                navigator.vibrate([100, 50, 100, 50, 100]); // Long-short-long-short-long
                break;
            case 'warning':
                navigator.vibrate([100, 100, 100]); // Long-long-long
                break;
            case 'confirm':
            case 'prompt':
                navigator.vibrate(50); // Single short vibration
                break;
            default:
                navigator.vibrate(25); // Very short vibration
                break;
        }
    } catch (error) {
        console.warn('Could not trigger haptic feedback:', error);
    }
};

/**
 * Get modal preferences from localStorage
 */
export const getModalPreferences = () => {
    try {
        const prefs = localStorage.getItem('modalPreferences');
        return prefs ? JSON.parse(prefs) : {
            soundEnabled: false, // Disabled by default to avoid annoying users
            hapticEnabled: true,
            animationsEnabled: true
        };
    } catch {
        return {
            soundEnabled: false,
            hapticEnabled: true,
            animationsEnabled: true
        };
    }
};

/**
 * Save modal preferences to localStorage
 */
export const setModalPreferences = (preferences) => {
    try {
        localStorage.setItem('modalPreferences', JSON.stringify(preferences));
    } catch (error) {
        console.warn('Could not save modal preferences:', error);
    }
};