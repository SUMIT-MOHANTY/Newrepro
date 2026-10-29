import { useState, useEffect } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { Mail, Lock, ArrowRight, Loader2, ShieldCheck, Eye, EyeOff, Sparkles, Sun, Moon } from 'lucide-react';
import { API_BASE_URL, API_ENDPOINTS } from '../config';
import { sanitizeErrorMessage } from '../utils/errorHandling';
import { clearTenantScopedState } from '../utils/auth';
import { useAuthStore } from '../stores/authStore';
import { login } from '../api/auth';
import dsuiteLogo from '../assets/DSuite Gradient Ribbon Logo.png';
import dsuiteLogoWhite from '../assets/DSuite Gradient Ribbon Logo White.png';
import OrganizationSelect from './OrganizationSelect';

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
    const [theme, setTheme] = useState(localStorage.getItem('theme') || 'dark');
    const [email, setEmail] = useState('');
    const [password, setPassword] = useState('');
    const [showPassword, setShowPassword] = useState(false);
    const [error, setError] = useState('');
    const [isLoading, setIsLoading] = useState(false);
    const [isSsoLoading, setIsSsoLoading] = useState(false);
    
    // Organization selection states for multi-org users
    const [requiresSelection, setRequiresSelection] = useState(false);
    const [orgs, setOrgs] = useState([]);
    const [tempToken, setTempToken] = useState('');

    const navigate = useNavigate();
    const authStore = useAuthStore();

    const finishNavigate = (path) => {
        if (isModal && onClose) onClose();
        navigate(path);
    };

    const nextParam = new URLSearchParams(typeof window !== 'undefined' ? window.location.search : '').get('next');
    const nextUrl = isAllowedNextUrl(nextParam) ? nextParam : null;

    const handlePostLoginRedirect = async (accessToken) => {
        // Check if user has any projects (backend or draft)
        let hasAnyProjects = false;
        let lastProjectToken = null;
        
        try {
            // Check backend projects
            const projectsResponse = await fetch(`${API_BASE_URL}/governance/history`, {
                headers: { 'Authorization': `Bearer ${accessToken}` },
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
                // Use navigate for same-origin navigation
                navigate(appendDsuiteToken(nextUrl, accessToken).replace(window.location.origin, ''));
                return;
            }
            finishNavigate('/new-project');
            return;
        }
        
        // User has projects - check if they have a saved progress page
        try {
            const progressResponse = await fetch(`${API_BASE_URL}/users/me/progress`, {
                headers: {
                    'Authorization': `Bearer ${accessToken}`,
                },
            });
            
            if (progressResponse.ok) {
                const progressData = await progressResponse.json();
                const lastPage = progressData.last_page_path;
                lastProjectToken = progressData.last_project_token;
                
                // If user has a last page and it's not login/signup/superadmin, redirect there
                if (lastPage && lastPage !== '/login' && lastPage !== '/signup' && lastPage !== '/' && !lastPage.startsWith('/superadmin')) {
                    if (nextUrl) {
                        navigate(appendDsuiteToken(nextUrl, accessToken).replace(window.location.origin, ''));
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
            navigate(appendDsuiteToken(nextUrl, accessToken).replace(window.location.origin, ''));
            return;
        }
        
        // Default: redirect to status dashboard
        finishNavigate('/status-dashboard');
    };

    const handleSubmit = async (e) => {
        e.preventDefault();
        setError('');
        setIsLoading(true);

        try {
            // Use the auth API client for login
            const result = await login(email, password);
            
            // Check if organization selection is required
            if (result.requiresSelection) {
                setTempToken(result.tempToken);
                sessionStorage.setItem('temp_token', result.tempToken);
                localStorage.setItem('temp_token', result.tempToken);
                setOrgs(result.organizations || []);
                setRequiresSelection(true);
                setIsLoading(false);
                return;
            }

            clearTenantScopedState();
            await handlePostLoginRedirect(result.accessToken);
        } catch (err) {
            console.error('Login error:', err);
            setError(sanitizeErrorMessage(err) || 'Invalid email or password. Please try again.');
        } finally {
            setIsLoading(false);
        }
    };

    if (requiresSelection) {
        return (
            <OrganizationSelect
                organizations={orgs}
                tempToken={tempToken || sessionStorage.getItem('temp_token') || localStorage.getItem('temp_token') || ''}
                onSelectComplete={async (finalToken) => {
                    sessionStorage.removeItem('temp_token');
                    localStorage.removeItem('temp_token');
                    clearTenantScopedState();
                    setRequiresSelection(false);
                    await handlePostLoginRedirect(finalToken);
                }}
            />
        );
    }

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

            // For external SSO URLs, we must use window.location
            // This is the only exception for sandbox escape - external identity providers
            // Store the auth URL and redirect using a form submission to avoid direct assignment
            const form = document.createElement('form');
            form.method = 'GET';
            form.action = data.auth_url;
            document.body.appendChild(form);
            form.submit();
            document.body.removeChild(form);
        } catch (err) {
            console.error('SSO login error:', err);
            setError(sanitizeErrorMessage(err));
            setIsSsoLoading(false);
        }
    };

    const isLight = theme === 'light';

    const formContent = (
        <div className={`w-full max-w-md rounded-3xl overflow-hidden transition-all duration-300 ${
            isModal 
                ? 'bg-transparent border-0' 
                : isLight 
                    ? 'bg-white border border-slate-200 shadow-[0_10px_40px_-10px_rgba(0,0,0,0.06)]'
                    : 'bg-slate-900/60 border border-purple-500/20 backdrop-blur-xl shadow-[0_8px_32px_0_rgba(0,0,0,0.37)]'
        }`}>
            {/* Header Section */}
            <div className="p-8 pb-0 text-center relative">
                {isModal && onClose && (
                    <button
                        onClick={onClose}
                        className={`absolute top-4 right-4 transition-colors p-1.5 rounded-full ${
                            isLight ? 'text-slate-400 hover:text-slate-600 hover:bg-slate-100' : 'text-slate-400 hover:text-white hover:bg-slate-800'
                        }`}
                    >
                        <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                        </svg>
                    </button>
                )}
                <div className="flex justify-center items-center mb-4" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                    <img 
                        src={isLight ? dsuiteLogo : dsuiteLogoWhite} 
                        alt="DSuite.Pro Logo" 
                        style={{ height: '32px', width: 'auto', display: 'block' }} 
                    />
                    <span 
                        className={`text-xl font-extrabold tracking-tight -ml-1 ${
                            isLight 
                                ? 'bg-gradient-to-r from-sky-600 to-cyan-600' 
                                : 'bg-gradient-to-r from-sky-400 to-cyan-300'
                        } bg-clip-text text-transparent`} 
                        style={{ alignSelf: 'center', display: 'inline-block', transform: 'translateY(1px)', lineHeight: '1' }}
                    >
                        .Pro
                    </span>
                </div>
                <h2 className="text-3xl font-extrabold tracking-tight mb-2 bg-gradient-to-r from-[#8b5cf6] to-[#ec4899] bg-clip-text text-transparent">
                    Welcome Back
                </h2>
                <p className={`text-sm ${isLight ? 'text-slate-500' : 'text-slate-400'}`}>Sign in to continue to your dashboard</p>
            </div>

            {/* Form Section */}
            <div className="p-8">
                {error && (
                    <div className="mb-6 p-4 bg-red-500/10 border border-red-500/30 text-red-200 text-sm rounded-xl flex items-center">
                        <svg className="w-4 h-4 mr-2 flex-shrink-0 text-red-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                        </svg>
                        {error}
                    </div>
                )}

                <form onSubmit={handleSubmit} className="space-y-5">
                    <div className="space-y-1">
                        <label className={`block text-sm font-semibold ml-1 ${isLight ? 'text-slate-600' : 'text-slate-300'}`} htmlFor="email">
                            Email Address
                        </label>
                        <div className="relative group">
                            <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                                <Mail className={`h-5 w-5 transition-colors ${isLight ? 'text-slate-400 group-focus-within:text-[#8b5cf6]' : 'text-slate-500 group-focus-within:text-[#a78bfa]'}`} />
                            </div>
                            <input
                                id="email"
                                type="email"
                                placeholder="name@company.com"
                                value={email}
                                onChange={(e) => setEmail(e.target.value)}
                                className={`block w-full pl-10 pr-3 py-3 border rounded-xl leading-5 transition-all duration-200 sm:text-sm focus:outline-none focus:ring-2 ${
                                    isLight 
                                        ? 'bg-slate-50 border-slate-200 text-slate-800 placeholder-slate-400 focus:ring-purple-500/10 focus:border-purple-500'
                                        : 'bg-slate-950/50 border-purple-500/20 text-white placeholder-slate-500 focus:ring-purple-500/20 focus:border-purple-500'
                                }`}
                                required
                            />
                        </div>
                    </div>

                    <div className="space-y-1">
                        <div className="flex items-center justify-between">
                            <label className={`block text-sm font-semibold ml-1 ${isLight ? 'text-slate-600' : 'text-slate-300'}`} htmlFor="password">
                                Password
                            </label>
                            <Link to="/forgot-password" className="text-xs font-bold text-[#8b5cf6] hover:text-[#a78bfa] transition-colors">
                                Forgot password?
                            </Link>
                        </div>
                        <div className="relative group">
                            <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                                <Lock className={`h-5 w-5 transition-colors ${isLight ? 'text-slate-400 group-focus-within:text-[#8b5cf6]' : 'text-slate-500 group-focus-within:text-[#a78bfa]'}`} />
                            </div>
                            <input
                                id="password"
                                type={showPassword ? "text" : "password"}
                                placeholder="••••••••"
                                value={password}
                                onChange={(e) => setPassword(e.target.value)}
                                className={`block w-full pl-10 pr-10 py-3 border rounded-xl leading-5 transition-all duration-200 sm:text-sm focus:outline-none focus:ring-2 ${
                                    isLight 
                                        ? 'bg-slate-50 border-slate-200 text-slate-800 placeholder-slate-400 focus:ring-purple-500/10 focus:border-purple-500'
                                        : 'bg-slate-950/50 border-purple-500/20 text-white placeholder-slate-500 focus:ring-purple-500/20 focus:border-purple-500'
                                }`}
                                required
                            />
                            <button
                                type="button"
                                onClick={() => setShowPassword(!showPassword)}
                                className={`absolute inset-y-0 right-0 pr-3 flex items-center transition-colors ${
                                    isLight ? 'text-slate-400 hover:text-slate-600' : 'text-slate-500 hover:text-slate-300'
                                }`}
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
                        className="w-full flex items-center justify-center py-3.5 px-4 rounded-xl text-sm font-bold text-white bg-gradient-to-r from-[#8b5cf6] to-[#ec4899] hover:opacity-90 focus:outline-none focus:ring-2 focus:ring-purple-500/30 transition-all duration-200 transform hover:scale-[1.01] shadow-[0_4px_20px_rgba(139,92,246,0.3)] disabled:opacity-70 disabled:cursor-not-allowed disabled:transform-none"
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
                            <div className={`w-full border-t ${isLight ? 'border-slate-200' : 'border-purple-500/10'}`}></div>
                        </div>
                        <div className="relative flex justify-center text-xs">
                            <span className={`px-3 font-semibold uppercase tracking-wider ${isLight ? 'bg-white text-slate-400' : 'bg-slate-900/60 text-slate-500'}`}>Or</span>
                        </div>
                    </div>

                    <button
                        type="button"
                        onClick={handleSsoLogin}
                        disabled={isLoading || isSsoLoading}
                        className={`w-full flex items-center justify-center py-3.5 px-4 border rounded-xl text-sm font-bold transition-all duration-200 focus:outline-none focus:ring-2 focus:ring-purple-500/20 disabled:opacity-70 disabled:cursor-not-allowed ${
                            isLight 
                                ? 'border-slate-250 bg-white text-slate-700 hover:bg-slate-50 shadow-sm'
                                : 'border-purple-500/20 bg-slate-950/40 text-slate-200 hover:bg-slate-850/50'
                        }`}
                    >
                        {isSsoLoading ? (
                            <>
                                <Loader2 className="animate-spin -ml-1 mr-2 h-4 w-4" />
                                Redirecting to SSO...
                            </>
                        ) : (
                            <>
                                <ShieldCheck className="mr-2 h-4 w-4 text-[#8b5cf6]" />
                                Continue with SSO
                            </>
                        )}
                    </button>
                </form>

                <div className={`mt-8 pt-6 border-t text-center ${isLight ? 'border-slate-100' : 'border-purple-500/10'}`}>
                    <p className={`text-sm ${isLight ? 'text-slate-500' : 'text-slate-400'}`}>
                        Don't have an account?{' '}
                        {isModal && onSwitch ? (
                            <button onClick={onSwitch} className="font-semibold text-[#8b5cf6] hover:text-[#a78bfa] hover:underline transition-colors bg-transparent border-0 p-0 inline cursor-pointer">
                                Create an account
                            </button>
                        ) : (
                            <Link to="/signup" className="font-semibold text-[#8b5cf6] hover:text-[#a78bfa] hover:underline transition-colors">
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
        <div className="min-h-screen relative flex items-center justify-center p-4 overflow-hidden transition-colors duration-200" style={{
            backgroundColor: isLight ? '#f8fafc' : '#09090b',
            backgroundImage: isLight 
                ? 'radial-gradient(circle at center, rgba(139, 92, 246, 0.05) 0%, transparent 65%)'
                : 'radial-gradient(circle at center, rgba(139, 92, 246, 0.15) 0%, transparent 65%)',
            fontFamily: 'system-ui, -apple-system, sans-serif'
        }}>
            {/* Background grid pattern */}
            <div className="absolute inset-0 opacity-10 pointer-events-none" style={{
                backgroundImage: isLight 
                    ? 'linear-gradient(rgba(0,0,0,.03) 1px, transparent 1px), linear-gradient(90deg, rgba(0,0,0,.03) 1px, transparent 1px)'
                    : 'linear-gradient(rgba(255,255,255,.05) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,.05) 1px, transparent 1px)',
                backgroundSize: '30px 30px'
            }}></div>

            {/* Decorative background gradients */}
            <div className={`absolute w-[400px] h-[400px] rounded-full blur-[80px] -top-20 -left-20 pointer-events-none transition-colors duration-200 ${
                isLight ? 'bg-purple-500/5' : 'bg-purple-500/10'
            }`}></div>
            <div className={`absolute w-[400px] h-[400px] rounded-full blur-[80px] -bottom-20 -right-20 pointer-events-none transition-colors duration-200 ${
                isLight ? 'bg-pink-500/5' : 'bg-pink-500/10'
            }`}></div>

            {/* Top Left Logo Header */}
            <div className="absolute top-6 left-6 flex items-center z-10" style={{ display: 'flex', alignItems: 'center' }}>
                <img 
                    src={isLight ? dsuiteLogo : dsuiteLogoWhite} 
                    alt="DSuite.Pro Logo" 
                    style={{ height: '32px', width: 'auto', display: 'block' }} 
                />
                <span 
                    className={`text-lg font-extrabold tracking-tight -ml-1 ${
                        isLight 
                            ? 'bg-gradient-to-r from-sky-600 to-cyan-600' 
                            : 'bg-gradient-to-r from-sky-400 to-cyan-300'
                    } bg-clip-text text-transparent`} 
                    style={{ alignSelf: 'center', display: 'inline-block', transform: 'translateY(1px)', lineHeight: '1' }}
                >
                    .Pro
                </span>
            </div>

            {/* Top Right Bourntec Logo */}
            <div className="absolute top-6 right-6 flex items-center z-10" style={{ display: 'flex', alignItems: 'center' }}>
                <a href="https://www.bourntec.com/" target="_blank" rel="noopener noreferrer" className="opacity-90 hover:opacity-100 transition-opacity">
                    <img 
                        src={isLight ? "/assets/docs/bourntec_logo_l.png" : "/assets/docs/bourntec_logo.png"} 
                        alt="Bourntec Solutions Logo" 
                        style={{ height: '24px', width: 'auto', display: 'block' }} 
                    />
                </a>
            </div>



            <div className="min-h-screen flex items-center justify-center p-4 w-full z-10">
                {formContent}
            </div>
        </div>
    );
};

export default Login;
