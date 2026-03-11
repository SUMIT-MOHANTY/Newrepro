import { useEffect, useMemo, useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { Mail, User, Loader2, ArrowRight, Lock, AlertCircle, CheckCircle2 } from 'lucide-react';
import { API_ENDPOINTS } from '../config';
import logo from '../assets/logo.png';
import bourntecLogo from '../assets/bourntec_logo.png';

const getTokenFromUrl = () => {
    try {
        const params = new URLSearchParams(window.location.search);
        return (params.get('token') || '').trim();
    } catch {
        return '';
    }
};

export default function InviteSignup() {
    const navigate = useNavigate();
    const [token, setToken] = useState('');
    const [invitePreview, setInvitePreview] = useState(null);
    const [previewLoading, setPreviewLoading] = useState(false);
    const [firstName, setFirstName] = useState('');
    const [lastName, setLastName] = useState('');
    const [email, setEmail] = useState('');
    const [password, setPassword] = useState('');
    const [error, setError] = useState('');
    const [success, setSuccess] = useState('');
    const [isLoading, setIsLoading] = useState(false);

    useEffect(() => {
        const t = getTokenFromUrl();
        setToken(t);
        if (!t) {
            setError('Invite token is missing from the link.');
        }
    }, []);

    useEffect(() => {
        if (!token) return;
        setPreviewLoading(true);
        fetch(`${API_ENDPOINTS.ORG_INVITE_PREVIEW}?token=${encodeURIComponent(token)}`)
            .then((res) => res.json().then((data) => ({ ok: res.ok, data })))
            .then(({ ok, data }) => {
                if (!ok) throw new Error(data?.detail || 'Unable to load invite details.');
                setInvitePreview(data || null);
                const restrictedEmail = (data?.email || '').trim();
                if (restrictedEmail) {
                    setEmail(restrictedEmail);
                }
                if (data?.accepted_at) {
                    setError('This invite link was already used.');
                } else if (data?.expires_at && new Date(data.expires_at).getTime() < Date.now()) {
                    setError('This invite link has expired.');
                }
            })
            .catch((e) => {
                setError(e.message || 'Unable to load invite details.');
                setInvitePreview(null);
            })
            .finally(() => setPreviewLoading(false));
    }, [token]);

    const canSubmit = useMemo(() => {
        return Boolean(token && email.trim() && password);
    }, [token, email, password]);

    const handleSubmit = async (e) => {
        e.preventDefault();
        if (!canSubmit) return;
        setError('');
        setSuccess('');
        setIsLoading(true);
        try {
            const response = await fetch(API_ENDPOINTS.ORG_INVITE_ACCEPT, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    token,
                    email: email.trim().toLowerCase(),
                    password,
                    first_name: firstName.trim() || undefined,
                    last_name: lastName.trim() || undefined,
                }),
            });
            const data = await response.json().catch(() => ({}));
            if (!response.ok) {
                throw new Error(data.detail || 'Unable to join organization.');
            }
            if (!data.access_token) {
                throw new Error('Invite accepted, but login token was not returned.');
            }
            localStorage.setItem('token', data.access_token);
            setSuccess(`Welcome! You joined ${data.organization_name || 'the organization'} as ${data.role_name || 'a member'}.`);
            setTimeout(() => navigate('/status-dashboard'), 250);
        } catch (err) {
            setError(err.message || 'Unable to join organization.');
        } finally {
            setIsLoading(false);
        }
    };

    return (
        <div className="min-h-screen bg-gradient-to-br from-app-bg-page to-app-bg-muted relative">
            <div className="absolute top-6 left-6 flex items-center space-x-4 z-10">
                <img
                    src={typeof document !== 'undefined' && document.documentElement.classList.contains('dark') ? bourntecLogo : logo}
                    alt="DSuite Logo"
                    className="h-10 w-auto object-contain"
                />
                <div className="h-8 w-px bg-app-border"></div>
                <span className="text-xl font-bold text-app-text-main tracking-tight">DSuite</span>
            </div>

            <div className="min-h-screen flex items-center justify-center p-4">
                <div className="w-full max-w-md bg-app-bg-card rounded-2xl overflow-hidden shadow-xl border border-app-border-light">
                    <div className="bg-app-bg-card p-8 pb-0 text-center relative">
                        <h2 className="text-2xl font-bold text-app-text-main tracking-tight mb-2">Join Organization</h2>
                        <p className="text-app-text-muted text-sm">
                            {previewLoading
                                ? 'Loading invite details...'
                                : invitePreview?.organization_name
                                    ? <>You’re joining <span className="font-bold text-app-text-main">{invitePreview.organization_name}</span>{invitePreview?.role_name ? <> as <span className="font-bold text-app-text-main">{invitePreview.role_name}</span></> : null}.</>
                                    : 'Complete your account to accept the invite.'}
                        </p>
                    </div>

                    <div className="p-8">
                        {error && (
                            <div className="mb-6 p-4 bg-app-status-errorBg border border-app-status-errorBg text-app-status-error text-sm rounded-lg flex items-center">
                                <AlertCircle className="w-4 h-4 mr-2 flex-shrink-0" />
                                {error}
                            </div>
                        )}
                        {success && (
                            <div className="mb-6 p-4 bg-app-status-successBg border border-green-200 text-app-status-success text-sm rounded-lg flex items-center">
                                <CheckCircle2 className="w-4 h-4 mr-2 flex-shrink-0" />
                                {success}
                            </div>
                        )}

                        <form onSubmit={handleSubmit} className="space-y-5">
                            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                                <div className="space-y-1">
                                    <label className="block text-sm font-semibold text-app-text-label ml-1" htmlFor="firstName">
                                        First Name
                                    </label>
                                    <div className="relative group">
                                        <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                                            <User className="h-5 w-5 text-app-text-light group-focus-within:text-app-primary transition-colors" />
                                        </div>
                                        <input
                                            id="firstName"
                                            type="text"
                                            placeholder="John"
                                            value={firstName}
                                            onChange={(e) => setFirstName(e.target.value)}
                                            className="block w-full pl-10 pr-3 py-3 border border-app-border rounded-xl leading-5 bg-app-bg-page placeholder-slate-400 focus:outline-none focus:bg-app-bg-card focus:ring-2 focus:ring-app-primary/20 focus:border-app-primary transition-all duration-200 sm:text-sm"
                                        />
                                    </div>
                                </div>
                                <div className="space-y-1">
                                    <label className="block text-sm font-semibold text-app-text-label ml-1" htmlFor="lastName">
                                        Last Name
                                    </label>
                                    <div className="relative group">
                                        <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                                            <User className="h-5 w-5 text-app-text-light group-focus-within:text-app-primary transition-colors" />
                                        </div>
                                        <input
                                            id="lastName"
                                            type="text"
                                            placeholder="Doe"
                                            value={lastName}
                                            onChange={(e) => setLastName(e.target.value)}
                                            className="block w-full pl-10 pr-3 py-3 border border-app-border rounded-xl leading-5 bg-app-bg-page placeholder-slate-400 focus:outline-none focus:bg-app-bg-card focus:ring-2 focus:ring-app-primary/20 focus:border-app-primary transition-all duration-200 sm:text-sm"
                                        />
                                    </div>
                                </div>
                            </div>

                            <div className="space-y-1">
                                <label className="block text-sm font-semibold text-app-text-label ml-1" htmlFor="email">
                                    Email
                                </label>
                                <div className="relative group">
                                    <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                                        <Mail className="h-5 w-5 text-app-text-light group-focus-within:text-app-primary transition-colors" />
                                    </div>
                                    <input
                                        id="email"
                                        type="email"
                                        placeholder="you@company.com"
                                        value={email}
                                        onChange={(e) => setEmail(e.target.value)}
                                        disabled={Boolean(invitePreview?.email)}
                                        className="block w-full pl-10 pr-3 py-3 border border-app-border rounded-xl leading-5 bg-app-bg-page placeholder-slate-400 focus:outline-none focus:bg-app-bg-card focus:ring-2 focus:ring-app-primary/20 focus:border-app-primary transition-all duration-200 sm:text-sm"
                                        required
                                    />
                                </div>
                                {invitePreview?.email && (
                                    <p className="text-[11px] text-app-text-muted mt-1 ml-1">
                                        This invite link is restricted to <span className="font-bold">{invitePreview.email}</span>.
                                    </p>
                                )}
                            </div>

                            <div className="space-y-1">
                                <label className="block text-sm font-semibold text-app-text-label ml-1" htmlFor="password">
                                    Password
                                </label>
                                <div className="relative group">
                                    <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                                        <Lock className="h-5 w-5 text-app-text-light group-focus-within:text-app-primary transition-colors" />
                                    </div>
                                    <input
                                        id="password"
                                        type="password"
                                        placeholder="••••••••"
                                        value={password}
                                        onChange={(e) => setPassword(e.target.value)}
                                        className="block w-full pl-10 pr-3 py-3 border border-app-border rounded-xl leading-5 bg-app-bg-page placeholder-slate-400 focus:outline-none focus:bg-app-bg-card focus:ring-2 focus:ring-app-primary/20 focus:border-app-primary transition-all duration-200 sm:text-sm"
                                        required
                                    />
                                </div>
                            </div>

                            <button
                                type="submit"
                                disabled={isLoading || !canSubmit}
                                className="w-full flex items-center justify-center py-3.5 px-4 border border-transparent rounded-xl shadow-md text-sm font-bold text-white bg-app-primary hover:bg-app-primary-hover focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-app-primary transition-all duration-200 transform hover:scale-[1.01] disabled:opacity-70 disabled:cursor-not-allowed disabled:transform-none"
                            >
                                {isLoading ? (
                                    <>
                                        <Loader2 className="animate-spin -ml-1 mr-2 h-4 w-4" />
                                        Joining...
                                    </>
                                ) : (
                                    <>
                                        Accept Invite
                                        <ArrowRight className="ml-2 h-4 w-4" />
                                    </>
                                )}
                            </button>
                        </form>

                        <div className="mt-8 pt-6 border-t border-app-border-light text-center">
                            <p className="text-sm text-app-text-muted">
                                Already have an account?{' '}
                                <Link to="/login" className="font-semibold text-app-primary hover:text-app-primary hover:underline transition-colors">
                                    Sign in instead
                                </Link>
                            </p>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
}

