import { useEffect, useState } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { isTokenExpired, getTimeUntilExpiration, logoutAndRedirect } from '../utils/auth';
import { AlertCircle, Clock } from 'lucide-react';

const PUBLIC_PATHS = ['/login', '/signup', '/', '/sso/callback', '/forgot-password', '/reset-password', '/invite'];

const SessionMonitor = () => {
    const navigate = useNavigate();
    const location = useLocation();
    const [showWarning, setShowWarning] = useState(false);
    const [minutesLeft, setMinutesLeft] = useState(null);

    useEffect(() => {
        // Don't monitor on public pages
        if (PUBLIC_PATHS.includes(location.pathname)) {
            return;
        }

        const token = localStorage.getItem('token');
        if (!token) {
            return;
        }

        // Check token expiration every minute
        const checkInterval = setInterval(() => {
            const token = localStorage.getItem('token');
            if (!token) {
                clearInterval(checkInterval);
                return;
            }

            const timeLeft = getTimeUntilExpiration(token);
            setMinutesLeft(timeLeft);

            // Show warning if less than 10 minutes left
            if (timeLeft <= 10 && timeLeft > 0) {
                setShowWarning(true);
            } else if (timeLeft <= 0) {
                // Token expired - logout
                clearInterval(checkInterval);
                logoutAndRedirect();
            } else {
                setShowWarning(false);
            }
        }, 60000); // Check every minute

        // Initial check
        const timeLeft = getTimeUntilExpiration(token);
        setMinutesLeft(timeLeft);
        if (timeLeft <= 10 && timeLeft > 0) {
            setShowWarning(true);
        } else if (timeLeft <= 0) {
            logoutAndRedirect();
        }

        return () => clearInterval(checkInterval);
    }, [location.pathname, navigate]);

    if (!showWarning || minutesLeft === null || minutesLeft <= 0) {
        return null;
    }

    return (
        <div className="fixed top-4 right-4 z-[9999] max-w-md animate-slide-in-right">
            <div className="bg-amber-50 border-2 border-amber-300 rounded-xl shadow-lg p-4 flex items-start gap-3">
                <div className="w-10 h-10 rounded-lg bg-amber-100 flex items-center justify-center flex-shrink-0">
                    <Clock className="w-5 h-5 text-amber-600" />
                </div>
                <div className="flex-1 min-w-0">
                    <h3 className="text-amber-900 font-bold text-sm mb-1 flex items-center gap-2">
                        Session Expiring Soon
                    </h3>
                    <p className="text-amber-800 text-xs leading-relaxed mb-3">
                        Your session will expire in <span className="font-bold">{minutesLeft} minute{minutesLeft !== 1 ? 's' : ''}</span>. 
                        Save your work to avoid losing progress.
                    </p>
                    <button
                        onClick={() => setShowWarning(false)}
                        className="text-xs font-semibold text-amber-700 hover:text-amber-900 underline"
                    >
                        Dismiss
                    </button>
                </div>
                <button
                    onClick={() => setShowWarning(false)}
                    className="text-amber-600 hover:text-amber-800 transition-colors"
                >
                    <AlertCircle className="w-4 h-4" />
                </button>
            </div>
        </div>
    );
};

export default SessionMonitor;
