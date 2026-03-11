import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import { Mail, ArrowLeft, Loader2, CheckCircle2 } from 'lucide-react';
import { API_ENDPOINTS } from '../config';

const ForgotPassword = () => {
    const [email, setEmail] = useState('');
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState('');
    const [success, setSuccess] = useState(false);

    const handleSubmit = async (e) => {
        e.preventDefault();
        setLoading(true);
        setError('');

        try {
            const response = await fetch(API_ENDPOINTS.FORGOT_PASSWORD, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ email }),
            });

            const data = await response.json();
            if (!response.ok) throw new Error(data.detail || 'Something went wrong');

            setSuccess(true);
        } catch (err) {
            setError(err.message);
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="min-h-screen bg-app-bg-page flex items-center justify-center p-4">
            <div className="max-width-md w-full max-w-[420px]">
                {/* Logo / Header */}
                <div className="text-center mb-8">
                    <div className="inline-flex items-center justify-center w-16 h-16 rounded-2xl bg-app-primary/10 mb-4">
                        <Mail className="w-8 h-8 text-app-primary" />
                    </div>
                    <h1 className="text-2xl font-extrabold text-app-text-main tracking-tight">Forgot Password?</h1>
                    <p className="text-app-text-muted mt-2 text-sm font-medium">
                        No worries, we'll send you reset instructions.
                    </p>
                </div>

                <div className="bg-app-bg-card border border-app-border rounded-2xl p-6 shadow-xl shadow-black/10">
                    {success ? (
                        <div className="text-center py-4">
                            <div className="inline-flex items-center justify-center w-12 h-12 rounded-full bg-emerald-500/10 mb-4">
                                <CheckCircle2 className="w-6 h-6 text-emerald-500" />
                            </div>
                            <h3 className="text-lg font-bold text-app-text-main mb-2">Check your email</h3>
                            <p className="text-sm text-app-text-muted mb-6 leading-relaxed">
                                if <span className="text-app-text-main font-bold">{email}</span> is registered, you'll receive a password reset link shortly.
                            </p>
                            <Link
                                to="/login"
                                className="inline-flex items-center justify-center w-full px-4 py-2.5 bg-app-primary hover:bg-app-primary-hover text-white rounded-xl font-bold transition-all gap-2"
                            >
                                <ArrowLeft className="w-4 h-4" />
                                Back to Sign In
                            </Link>
                        </div>
                    ) : (
                        <form onSubmit={handleSubmit} className="space-y-5">
                            <div>
                                <label className="block text-xs font-bold text-app-text-muted uppercase tracking-widest mb-1.5 ml-1">
                                    Email Address
                                </label>
                                <div className="relative group">
                                    <div className="absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none text-app-text-muted group-focus-within:text-app-primary transition-colors">
                                        <Mail className="w-4 h-4" />
                                    </div>
                                    <input
                                        type="email"
                                        required
                                        value={email}
                                        onChange={(e) => setEmail(e.target.value)}
                                        placeholder="name@company.com"
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
                                        Sending Instructions...
                                    </>
                                ) : (
                                    'Send Reset Link'
                                )}
                            </button>

                            <Link
                                to="/login"
                                className="flex items-center justify-center gap-2 text-sm font-bold text-app-text-muted hover:text-app-primary transition-colors mt-2"
                            >
                                <ArrowLeft className="w-4 h-4" />
                                Back to Sign In
                            </Link>
                        </form>
                    )}
                </div>
            </div>
        </div>
    );
};

export default ForgotPassword;
