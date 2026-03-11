import React, { useState, useEffect } from 'react';
import { useSearchParams, useNavigate, Link } from 'react-router-dom';
import { Lock, Eye, EyeOff, Loader2, CheckCircle2, ShieldCheck, AlertCircle } from 'lucide-react';
import { API_ENDPOINTS } from '../config';

const ResetPassword = () => {
    const [searchParams] = useSearchParams();
    const navigate = useNavigate();
    const token = searchParams.get('token');

    const [password, setPassword] = useState('');
    const [confirmPassword, setConfirmPassword] = useState('');
    const [showPassword, setShowPassword] = useState(false);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState('');
    const [success, setSuccess] = useState(false);

    useEffect(() => {
        if (!token) {
            setError('Missing reset token. Please check your link.');
        }
    }, [token]);

    const handleSubmit = async (e) => {
        e.preventDefault();
        if (password !== confirmPassword) {
            setError('Passwords do not match');
            return;
        }
        if (password.length < 6) {
            setError('Password must be at least 6 characters long');
            return;
        }

        setLoading(true);
        setError('');

        try {
            const response = await fetch(API_ENDPOINTS.RESET_PASSWORD, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ token, new_password: password }),
            });

            const data = await response.json();
            if (!response.ok) throw new Error(data.detail || 'Failed to reset password');

            setSuccess(true);
            setTimeout(() => {
                navigate('/login');
            }, 3000);
        } catch (err) {
            setError(err.message);
        } finally {
            setLoading(false);
        }
    };

    if (success) {
        return (
            <div className="min-h-screen bg-app-bg-page flex items-center justify-center p-4">
                <div className="max-width-md w-full max-w-[420px] text-center">
                    <div className="bg-app-bg-card border border-app-border rounded-2xl p-8 shadow-xl shadow-black/10">
                        <div className="inline-flex items-center justify-center w-16 h-16 rounded-full bg-emerald-500/10 mb-6">
                            <CheckCircle2 className="w-8 h-8 text-emerald-500" />
                        </div>
                        <h2 className="text-2xl font-extrabold text-app-text-main mb-2">Password Reset!</h2>
                        <p className="text-app-text-muted mb-8 font-medium">
                            Your password has been successfully updated. Redirecting to login...
                        </p>
                        <Link
                            to="/login"
                            className="inline-flex items-center justify-center w-full px-4 py-3 bg-app-primary hover:bg-app-primary-hover text-white rounded-xl font-bold transition-all"
                        >
                            Log In Now
                        </Link>
                    </div>
                </div>
            </div>
        );
    }

    return (
        <div className="min-h-screen bg-app-bg-page flex items-center justify-center p-4">
            <div className="max-width-md w-full max-w-[420px]">
                {/* Header */}
                <div className="text-center mb-8">
                    <div className="inline-flex items-center justify-center w-16 h-16 rounded-2xl bg-app-primary/10 mb-4">
                        <ShieldCheck className="w-8 h-8 text-app-primary" />
                    </div>
                    <h1 className="text-2xl font-extrabold text-app-text-main tracking-tight">Set New Password</h1>
                    <p className="text-app-text-muted mt-2 text-sm font-medium">
                        Secure your account with a strong password.
                    </p>
                </div>

                <div className="bg-app-bg-card border border-app-border rounded-2xl p-6 shadow-xl shadow-black/10">
                    {!token ? (
                        <div className="text-center py-4">
                            <div className="inline-flex items-center justify-center w-12 h-12 rounded-full bg-red-500/10 mb-4">
                                <AlertCircle className="w-6 h-6 text-red-500" />
                            </div>
                            <h3 className="text-lg font-bold text-app-text-main mb-2">Invalid Link</h3>
                            <p className="text-sm text-app-text-muted mb-6">
                                The reset link appears to be invalid or missing a token.
                            </p>
                            <Link to="/forgot-password" size="sm" className="text-app-primary font-bold text-sm">Request a new link</Link>
                        </div>
                    ) : (
                        <form onSubmit={handleSubmit} className="space-y-5">
                            <div>
                                <label className="block text-xs font-bold text-app-text-muted uppercase tracking-widest mb-1.5 ml-1">
                                    New Password
                                </label>
                                <div className="relative group">
                                    <div className="absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none text-app-text-muted group-focus-within:text-app-primary transition-colors">
                                        <Lock className="w-4 h-4" />
                                    </div>
                                    <input
                                        type={showPassword ? "text" : "password"}
                                        required
                                        value={password}
                                        onChange={(e) => setPassword(e.target.value)}
                                        placeholder="Min. 6 characters"
                                        className="w-full pl-10 pr-12 py-3 bg-app-bg-page border border-app-border rounded-xl text-app-text-main placeholder:text-app-text-muted/50 focus:outline-none focus:ring-2 focus:ring-app-primary/20 focus:border-app-primary transition-all text-sm font-medium"
                                    />
                                    <button
                                        type="button"
                                        onClick={() => setShowPassword(!showPassword)}
                                        className="absolute inset-y-0 right-0 pr-3.5 flex items-center text-app-text-muted hover:text-app-text-main transition-colors"
                                    >
                                        {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                                    </button>
                                </div>
                            </div>

                            <div>
                                <label className="block text-xs font-bold text-app-text-muted uppercase tracking-widest mb-1.5 ml-1">
                                    Confirm Password
                                </label>
                                <div className="relative group">
                                    <div className="absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none text-app-text-muted group-focus-within:text-app-primary transition-colors">
                                        <Lock className="w-4 h-4" />
                                    </div>
                                    <input
                                        type={showPassword ? "text" : "password"}
                                        required
                                        value={confirmPassword}
                                        onChange={(e) => setConfirmPassword(e.target.value)}
                                        placeholder="Repeat new password"
                                        className="w-full pl-10 pr-4 py-3 bg-app-bg-page border border-app-border rounded-xl text-app-text-main placeholder:text-app-text-muted/50 focus:outline-none focus:ring-2 focus:ring-app-primary/20 focus:border-app-primary transition-all text-sm font-medium"
                                    />
                                </div>
                            </div>

                            {error && (
                                <div className="p-3 rounded-lg bg-red-500/10 border border-red-500/20 text-xs font-bold text-red-500">
                                    {error}
                                </div>
                            )}

                            <button
                                type="submit"
                                disabled={loading}
                                className="w-full flex items-center justify-center gap-2 bg-app-primary hover:bg-app-primary-hover disabled:opacity-50 text-white font-bold py-3 px-4 rounded-xl transition-all shadow-lg shadow-app-primary/10"
                            >
                                {loading ? (
                                    <>
                                        <Loader2 className="animate-spin w-4 h-4" />
                                        Updating Password...
                                    </>
                                ) : (
                                    'Reset Password'
                                )}
                            </button>
                        </form>
                    )}
                </div>
            </div>
        </div>
    );
};

export default ResetPassword;
