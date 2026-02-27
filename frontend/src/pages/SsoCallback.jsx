import { useEffect } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { AlertCircle, Loader2, ShieldCheck } from 'lucide-react';

export default function SsoCallback() {
    const navigate = useNavigate();
    const params = new URLSearchParams(typeof window !== 'undefined' ? window.location.search : '');
    const token = params.get('token');
    const errorParam = params.get('error');
    const error = errorParam || (!token ? 'Could not complete SSO login. Missing response from identity provider.' : '');

    useEffect(() => {
        if (token) {
            localStorage.setItem('token', token);
            navigate('/status-dashboard', { replace: true });
        }
    }, [navigate, token]);

    const isProcessing = !error;

    return (
        <div className="min-h-screen bg-gradient-to-br from-slate-50 to-slate-100 flex items-center justify-center p-4">
            <div className="w-full max-w-md bg-app-bg-card border border-app-border-light rounded-2xl shadow-xl p-7 text-center">
                {isProcessing ? (
                    <>
                        <div className="inline-flex items-center justify-center h-12 w-12 rounded-xl bg-app-primary/10 mb-4">
                            <Loader2 className="w-6 h-6 text-app-primary animate-spin" />
                        </div>
                        <h1 className="text-xl font-bold text-app-text-main mb-2">Signing you in</h1>
                        <p className="text-sm text-app-text-muted">Please wait while we finish your SSO login.</p>
                    </>
                ) : (
                    <>
                        <div className="inline-flex items-center justify-center h-12 w-12 rounded-xl bg-red-50 mb-4">
                            <AlertCircle className="w-6 h-6 text-red-500" />
                        </div>
                        <h1 className="text-xl font-bold text-app-text-main mb-2">SSO sign-in failed</h1>
                        <p className="text-sm text-app-text-muted mb-5">{error}</p>
                        <Link
                            to="/login"
                            className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-app-primary text-white text-sm font-semibold hover:bg-app-primary-hover transition-colors"
                        >
                            <ShieldCheck className="w-4 h-4" />
                            Back to Login
                        </Link>
                    </>
                )}
            </div>
        </div>
    );
}
