import { useState } from 'react';
import { useNavigate, Link, useLocation } from 'react-router-dom';
import { Mail, Lock, ArrowRight, Loader2, ShieldCheck, Eye, EyeOff } from 'lucide-react';
import { API_BASE_URL, API_ENDPOINTS } from '../config';
import { sanitizeErrorMessage } from '../utils/errorHandling';
import logo from '../assets/logo.png';
import bourntecLogo from '../assets/bourntec_logo.png';

const isAllowedNextUrl = (nextUrl) => {
    if (!nextUrl) return false;
    try {
        const absolute = new URL(nextUrl, window.location.origin);
        const apiBase = new URL(API_BASE_URL, window.location.origin);
        return absolute.origin === apiBase.origin && absolute.pathname === '/oauth/authorize';
    } catch {
        return false;
    }
};

const appendDsuiteToken = (url, token) => {
    const parsed = new URL(url, window.location.origin);
    parsed.searchParams.set('dsuite_token', token);
    return parsed.toString();
};

const Login = ({ isModal = false, onClose, onSwitch }) => {
    const [email, setEmail] = useState('');
    const [password, setPassword] = useState('');
    const [showPassword, setShowPassword] = useState(false);
    const [error, setError] = useState('');
    const [isLoading, setIsLoading] = useState(false);
    const [isSsoLoading, setIsSsoLoading] = useState(false);
    const navigate = useNavigate();

    const finishNavigate = (path) => {
        if (isModal && onClose) onClose();
        navigate(path);
    };

    const nextParam = new URLSearchParams(typeof window !== 'undefined' ? window.location.search : '').get('next');
    const nextUrl = isAllowedNextUrl(nextParam) ? nextParam : null;

    const handleSubmit = async (e) => {
        e.preventDefault();
        setError('');
        setIsLoading(true);

        const formData = new FormData();
        formData.append('username', email);
        formData.append('password', password);

        try {
            const response = await fetch(API_ENDPOINTS.TOKEN, {
                method: 'POST',
                body: formData,
            });

            if (!response.ok) {
                throw new Error('Login failed');
            }

            const data = await response.json();
            localStorage.setItem('token', data.access_token);
            
            // First, check if user has any projects (backend or draft)
            let hasAnyProjects = false;
            let lastProjectToken = null;
            
            try {
                // Check backend projects
                const projectsResponse = await fetch(`${API_BASE_URL}/governance/history`, {
                    headers: { 'Authorization': `Bearer ${data.access_token}` },
                });
                
                if (projectsResponse.ok) {
                    const projectsData = await projectsResponse.json();
                    const submissions = projectsData.submissions || [];
                    hasAnyProjects = submissions.length > 0;
                }
                
                // Check draft projects in localStorage
                if (!hasAnyProjects) {
                    const draftProjectsRaw = localStorage.getItem('draft_projects');
                    if (draftProjectsRaw) {
                        try {
                            const draftProjects = JSON.parse(draftProjectsRaw);
                            hasAnyProjects = Array.isArray(draftProjects) && draftProjects.length > 0;
                        } catch {
                            // Ignore parse errors
                        }
                    }
                }
            } catch (projectCheckError) {
                console.debug('Could not check projects:', projectCheckError);
            }
            
            // If no projects exist at all, redirect to new project page
            if (!hasAnyProjects) {
                if (nextUrl) {
                    window.location.assign(appendDsuiteToken(nextUrl, data.access_token));
                    return;
                }
                finishNavigate('/new-project');
                return;
            }
            
            // User has projects - check if they have a saved progress page
            try {
                const progressResponse = await fetch(`${API_BASE_URL}/users/me/progress`, {
                    headers: {
                        'Authorization': `Bearer ${data.access_token}`,
                    },
                });
                
                if (progressResponse.ok) {
                    const progressData = await progressResponse.json();
                    const lastPage = progressData.last_page_path;
                    lastProjectToken = progressData.last_project_token;
                    
                    // If user has a last page and it's not login/signup, redirect there
                    if (lastPage && lastPage !== '/login' && lastPage !== '/signup' && lastPage !== '/') {
                        if (nextUrl) {
                            window.location.assign(appendDsuiteToken(nextUrl, data.access_token));
                        } else {
                            finishNavigate(lastPage);
                        }
                        return;
                    }
                }
            } catch (progressError) {
                console.debug('Could not fetch user progress:', progressError);
                // Continue with default navigation
            }
            
            if (nextUrl) {
                window.location.assign(appendDsuiteToken(nextUrl, data.access_token));
                return;
            }
            
            // Default: redirect to status dashboard
            finishNavigate('/status-dashboard');
        } catch {
            setError('Invalid email or password. Please try again.');
        } finally {
            setIsLoading(false);
        }
    };

    const handleSsoLogin = async () => {
        setError('');
        if (!email.trim()) {
            setError('Enter your business email first to continue with SSO.');
            return;
        }

        setIsSsoLoading(true);
        try {
            const response = await fetch(API_ENDPOINTS.SSO_START, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    email: email.trim().toLowerCase(),
                    next: nextUrl || undefined,
                }),
            });

            const data = await response.json().catch(() => ({}));
            if (!response.ok || !data.auth_url) {
                throw new Error(data.detail || 'SSO is not configured for this account.');
            }

            window.location.assign(data.auth_url);
        } catch (err) {
            console.error('SSO login error:', err);
            setError(sanitizeErrorMessage(err));
            setIsSsoLoading(false);
        }
    };

    const formContent = (
        <div className={`w-full max-w-md bg-app-bg-card rounded-2xl overflow-hidden ${isModal ? 'shadow-none border-0' : 'shadow-xl border border-app-border-light'}`}>
            {/* Header Section */}
            <div className="bg-app-bg-card p-8 pb-0 text-center relative">
                {isModal && onClose && (
                    <button
                        onClick={onClose}
                        className="absolute top-4 right-4 text-app-text-light hover:text-app-text-label transition-colors p-1 rounded-full hover:bg-app-bg-muted"
                    >
                        <svg xmlns="http://www.w3.org/2000/svg" className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                        </svg>
                    </button>
                )}
                <h2 className="text-2xl font-bold text-app-text-main tracking-tight mb-2">Welcome Back</h2>
                <p className="text-app-text-muted text-sm">Sign in to continue to your dashboard</p>
            </div>

            {/* Form Section */}
            <div className="p-8">
                {error && (
                    <div className="mb-6 p-4 bg-app-status-errorBg border border-app-status-errorBg text-app-status-error text-sm rounded-lg flex items-center">
                        <svg className="w-4 h-4 mr-2 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                        </svg>
                        {error}
                    </div>
                )}

                <form onSubmit={handleSubmit} className="space-y-5">
                    <div className="space-y-1">
                        <label className="block text-sm font-semibold text-app-text-label ml-1" htmlFor="email">
                            Email Address
                        </label>
                        <div className="relative group">
                            <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                                <Mail className="h-5 w-5 text-app-text-light group-focus-within:text-app-primary transition-colors" />
                            </div>
                            <input
                                id="email"
                                type="email"
                                placeholder="name@company.com"
                                value={email}
                                onChange={(e) => setEmail(e.target.value)}
                                className="block w-full pl-10 pr-3 py-3 border border-app-border rounded-xl leading-5 bg-app-bg-page placeholder-slate-400 focus:outline-none focus:bg-app-bg-card focus:ring-2 focus:ring-app-primary/20 focus:border-app-primary transition-all duration-200 sm:text-sm"
                                required
                            />
                        </div>
                    </div>

                    <div className="space-y-1">
                        <div className="flex items-center justify-between">
                            <label className="block text-sm font-semibold text-app-text-label ml-1" htmlFor="password">
                                Password
                            </label>
                            <Link to="/forgot-password" size="sm" className="text-xs font-bold text-app-primary hover:text-app-primary-hover transition-colors">
                                Forgot password?
                            </Link>
                        </div>
                        <div className="relative group">
                            <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                                <Lock className="h-5 w-5 text-app-text-light group-focus-within:text-app-primary transition-colors" />
                            </div>
                            <input
                                id="password"
                                type={showPassword ? "text" : "password"}
                                placeholder="••••••••"
                                value={password}
                                onChange={(e) => setPassword(e.target.value)}
                                className="block w-full pl-10 pr-10 py-3 border border-app-border rounded-xl leading-5 bg-app-bg-page placeholder-slate-400 focus:outline-none focus:bg-app-bg-card focus:ring-2 focus:ring-app-primary/20 focus:border-app-primary transition-all duration-200 sm:text-sm"
                                required
                            />
                            <button
                                type="button"
                                onClick={() => setShowPassword(!showPassword)}
                                className="absolute inset-y-0 right-0 pr-3 flex items-center text-app-text-light hover:text-app-text-label transition-colors"
                            >
                                {showPassword ? (
                                    <EyeOff className="h-5 w-5" />
                                ) : (
                                    <Eye className="h-5 w-5" />
                                )}
                            </button>
                        </div>
                    </div>

                    <button
                        type="submit"
                        disabled={isLoading || isSsoLoading}
                        className="w-full flex items-center justify-center py-3.5 px-4 border border-transparent rounded-xl shadow-md text-sm font-bold text-white bg-app-primary hover:bg-app-primary-hover focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-app-primary transition-all duration-200 transform hover:scale-[1.01] disabled:opacity-70 disabled:cursor-not-allowed disabled:transform-none"
                    >
                        {isLoading ? (
                            <>
                                <Loader2 className="animate-spin -ml-1 mr-2 h-4 w-4" />
                                Signing in...
                            </>
                        ) : (
                            <>
                                Sign In
                                <ArrowRight className="ml-2 h-4 w-4" />
                            </>
                        )}
                    </button>

                    <div className="relative py-1">
                        <div className="absolute inset-0 flex items-center">
                            <div className="w-full border-t border-app-border-light"></div>
                        </div>
                        <div className="relative flex justify-center text-xs">
                            <span className="bg-app-bg-card px-3 text-app-text-muted font-semibold uppercase tracking-wider">Or</span>
                        </div>
                    </div>

                    <button
                        type="button"
                        onClick={handleSsoLogin}
                        disabled={isLoading || isSsoLoading}
                        className="w-full flex items-center justify-center py-3.5 px-4 border border-app-border rounded-xl text-sm font-bold text-app-text-main bg-app-bg-page hover:bg-app-bg-muted focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-app-primary transition-all duration-200 disabled:opacity-70 disabled:cursor-not-allowed"
                    >
                        {isSsoLoading ? (
                            <>
                                <Loader2 className="animate-spin -ml-1 mr-2 h-4 w-4" />
                                Redirecting to SSO...
                            </>
                        ) : (
                            <>
                                <ShieldCheck className="mr-2 h-4 w-4 text-app-primary" />
                                Continue with SSO
                            </>
                        )}
                    </button>
                </form>

                <div className="mt-8 pt-6 border-t border-app-border-light text-center">
                    <p className="text-sm text-app-text-muted">
                        Don't have an account?{' '}
                        {isModal && onSwitch ? (
                            <button onClick={onSwitch} className="font-semibold text-app-primary hover:text-app-primary hover:underline transition-colors bg-transparent border-0 p-0 inline cursor-pointer">
                                Create an account
                            </button>
                        ) : (
                            <Link to="/signup" className="font-semibold text-app-primary hover:text-app-primary hover:underline transition-colors">
                                Create an account
                            </Link>
                        )}
                    </p>
                </div>
            </div>
        </div>
    );

    if (isModal) {
        return formContent;
    }

    return (
        <div className="min-h-screen bg-gradient-to-br from-app-bg-page to-app-bg-muted relative">
            {/* Top Left Logo Header */}
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
                {formContent}
            </div>
        </div>
    );
};

export default Login;
