import { useEffect, useMemo, useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { Mail, User, Loader2, ArrowRight, Lock, AlertCircle, CheckCircle2, ShieldCheck } from 'lucide-react';
import { API_ENDPOINTS } from '../config';
import { clearTenantScopedState } from '../utils/auth';
import dsuiteLogo from '../assets/DSuite Gradient Ribbon Logo.png';

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
    const [isExistingUser, setIsExistingUser] = useState(false);
    const [checkingUser, setCheckingUser] = useState(false);
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
                if (data?.user_exists) {
                    setIsExistingUser(true);
                    if (data.first_name) setFirstName(data.first_name);
                    if (data.last_name) setLastName(data.last_name);
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

    const checkExistingUser = async (emailVal) => {
        const clean = (emailVal || '').trim().toLowerCase();
        if (!clean || !clean.includes('@')) return;
        try {
            setCheckingUser(true);
            const res = await fetch(`${API_ENDPOINTS.ORG_INVITE_CHECK_USER}?email=${encodeURIComponent(clean)}`);
            if (res.ok) {
                const d = await res.json();
                if (d?.exists) {
                    setIsExistingUser(true);
                    if (d.first_name) setFirstName(d.first_name);
                    if (d.last_name) setLastName(d.last_name);
                } else {
                    setIsExistingUser(false);
                }
            }
        } catch (err) {
            console.debug('Failed to check user:', err);
        } finally {
            setCheckingUser(false);
        }
    };

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
            clearTenantScopedState();
            localStorage.setItem('token', data.access_token);
            if (data.organization_name) {
                localStorage.setItem('active_org', data.organization_name);
            }
            setSuccess(`Welcome! You joined ${data.organization_name || 'the organization'} as ${data.role_name || 'a member'}.`);
            // Redirect to dashboard of the newly joined organization
            setTimeout(() => navigate('/status-dashboard'), 350);
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
                    src={dsuiteLogo}
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

                        {isExistingUser && (
                            <div className="mb-6 p-3.5 bg-blue-50/80 dark:bg-blue-950/40 border border-blue-200 dark:border-blue-800 rounded-xl flex items-start space-x-3 text-xs text-blue-800 dark:text-blue-300">
                                <ShieldCheck className="w-5 h-5 text-blue-600 dark:text-blue-400 mt-0.5 flex-shrink-0" />
                                <div className="space-y-0.5">
                                    <p className="font-semibold text-blue-900 dark:text-blue-200">Existing DSuite Profile Found</p>
                                    <p className="leading-relaxed text-blue-700 dark:text-blue-300">
                                        Your name has been prefilled from your account and cannot be modified. Enter your existing password to join this workspace.
                                    </p>
                                </div>
                            </div>
                        )}

                        <form onSubmit={handleSubmit} className="space-y-5">
                            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                                <div className="space-y-1">
                                    <div className="flex items-center justify-between ml-1">
                                        <label className="block text-sm font-semibold text-app-text-label" htmlFor="firstName">
                                            First Name
                                        </label>
                                        {isExistingUser && (
                                            <span className="text-[11px] font-medium text-slate-400 dark:text-slate-500">Locked</span>
                                        )}
                                    </div>
                                    <div className="relative group">
                                        <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                                            <User className={`h-5 w-5 ${isExistingUser ? 'text-slate-400' : 'text-app-text-light group-focus-within:text-app-primary'} transition-colors`} />
                                        </div>
                                        <input
                                            id="firstName"
                                            type="text"
                                            placeholder="John"
                                            value={firstName}
                                            onChange={(e) => setFirstName(e.target.value)}
                                            disabled={isExistingUser}
                                            readOnly={isExistingUser}
                                            className={`block w-full pl-10 pr-3 py-3 border border-app-border rounded-xl leading-5 sm:text-sm transition-all duration-200 ${
                                                isExistingUser
                                                    ? 'bg-slate-100 dark:bg-slate-800/60 text-slate-600 dark:text-slate-400 cursor-not-allowed select-none font-medium'
                                                    : 'bg-app-bg-page placeholder-slate-400 focus:outline-none focus:bg-app-bg-card focus:ring-2 focus:ring-app-primary/20 focus:border-app-primary'
                                            }`}
                                        />
                                    </div>
                                </div>
                                <div className="space-y-1">
                                    <div className="flex items-center justify-between ml-1">
                                        <label className="block text-sm font-semibold text-app-text-label" htmlFor="lastName">
                                            Last Name
                                        </label>
                                        {isExistingUser && (
                                            <span className="text-[11px] font-medium text-slate-400 dark:text-slate-500">Locked</span>
                                        )}
                                    </div>
                                    <div className="relative group">
                                        <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                                            <User className={`h-5 w-5 ${isExistingUser ? 'text-slate-400' : 'text-app-text-light group-focus-within:text-app-primary'} transition-colors`} />
                                        </div>
                                        <input
                                            id="lastName"
                                            type="text"
                                            placeholder="Doe"
                                            value={lastName}
                                            onChange={(e) => setLastName(e.target.value)}
                                            disabled={isExistingUser}
                                            readOnly={isExistingUser}
                                            className={`block w-full pl-10 pr-3 py-3 border border-app-border rounded-xl leading-5 sm:text-sm transition-all duration-200 ${
                                                isExistingUser
                                                    ? 'bg-slate-100 dark:bg-slate-800/60 text-slate-600 dark:text-slate-400 cursor-not-allowed select-none font-medium'
                                                    : 'bg-app-bg-page placeholder-slate-400 focus:outline-none focus:bg-app-bg-card focus:ring-2 focus:ring-app-primary/20 focus:border-app-primary'
                                            }`}
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
                                        onBlur={(e) => {
                                            if (!invitePreview?.email) {
                                                checkExistingUser(e.target.value);
                                            }
                                        }}
                                        disabled={Boolean(invitePreview?.email)}
                                        className="block w-full pl-10 pr-3 py-3 border border-app-border rounded-xl leading-5 bg-app-bg-page placeholder-slate-400 focus:outline-none focus:bg-app-bg-card focus:ring-2 focus:ring-app-primary/20 focus:border-app-primary transition-all duration-200 sm:text-sm"
                                        required
                                    />
                                    {checkingUser && (
                                        <div className="absolute inset-y-0 right-0 pr-3 flex items-center pointer-events-none">
                                            <Loader2 className="h-4 w-4 text-app-primary animate-spin" />
                                        </div>
                                    )}
                                </div>
                                {invitePreview?.email && (
                                    <p className="text-[11px] text-app-text-muted mt-1 ml-1">
                                        This invite link is restricted to <span className="font-bold">{invitePreview.email}</span>.
                                    </p>
                                )}
                            </div>

                            <div className="space-y-1">
                                <label className="block text-sm font-semibold text-app-text-label ml-1" htmlFor="password">
                                    {isExistingUser ? 'Account Password' : 'Password'}
                                </label>
                                <div className="relative group">
                                    <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                                        <Lock className="h-5 w-5 text-app-text-light group-focus-within:text-app-primary transition-colors" />
                                    </div>
                                    <input
                                        id="password"
                                        type="password"
                                        placeholder={isExistingUser ? 'Enter your existing account password' : '••••••••'}
                                        value={password}
                                        onChange={(e) => setPassword(e.target.value)}
                                        className="block w-full pl-10 pr-3 py-3 border border-app-border rounded-xl leading-5 bg-app-bg-page placeholder-slate-400 focus:outline-none focus:bg-app-bg-card focus:ring-2 focus:ring-app-primary/20 focus:border-app-primary transition-all duration-200 sm:text-sm"
                                        required
                                    />
                                </div>
                                <p className="text-[11px] text-app-text-muted mt-1 ml-1">
                                    {isExistingUser
                                        ? 'Enter your current account password to verify your credentials and join this workspace.'
                                        : 'Create a secure password for your new account.'}
                                </p>
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
                                        {isExistingUser ? 'Join Organization' : 'Accept Invite'}
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


