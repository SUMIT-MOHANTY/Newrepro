import { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { Mail, Lock, User, Building2, Loader2, ArrowRight } from 'lucide-react';
import { API_ENDPOINTS } from '../config';
import logo from '../assets/logo.png';

const Signup = ({ isModal = false, onClose, onSwitch }) => {
    const [firstName, setFirstName] = useState('');
    const [lastName, setLastName] = useState('');
    const [organizationName, setOrganizationName] = useState('');
    const [email, setEmail] = useState('');
    const [password, setPassword] = useState('');
    const [error, setError] = useState('');
    const [isLoading, setIsLoading] = useState(false);
    const navigate = useNavigate();

    const handleSubmit = async (e) => {
        e.preventDefault();
        setError('');
        setIsLoading(true);

        try {
            const response = await fetch(API_ENDPOINTS.USERS, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    first_name: firstName,
                    last_name: lastName,
                    organization_name: organizationName,
                    email,
                    password,
                }),
            });

            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.detail || 'Signup failed');
            }

            if (isModal && onClose) onClose();
            navigate('/login');
        } catch (err) {
            setError(err.message);
        } finally {
            setIsLoading(false);
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
                <h2 className="text-2xl font-bold text-app-text-main tracking-tight mb-2">Register Organization</h2>
                <p className="text-app-text-muted text-sm">Create your admin account and configure enterprise SSO</p>
            </div>

            {/* Form Section */}
            <div className="p-8">
                {error && (
                    <div className="mb-6 p-4 bg-app-status-errorBg border border-app-status-errorBg text-app-status-error text-sm rounded-lg flex items-center">
                        <svg className="w-4 h-4 mr-2 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                        </svg>
                        {error}
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
                                    required
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
                                    required
                                />
                            </div>
                        </div>
                    </div>

                    <div className="space-y-1">
                        <label className="block text-sm font-semibold text-app-text-label ml-1" htmlFor="organizationName">
                            Organization Name
                        </label>
                        <div className="relative group">
                            <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                                <Building2 className="h-5 w-5 text-app-text-light group-focus-within:text-app-primary transition-colors" />
                            </div>
                            <input
                                id="organizationName"
                                type="text"
                                placeholder="Acme Technologies"
                                value={organizationName}
                                onChange={(e) => setOrganizationName(e.target.value)}
                                className="block w-full pl-10 pr-3 py-3 border border-app-border rounded-xl leading-5 bg-app-bg-page placeholder-slate-400 focus:outline-none focus:bg-app-bg-card focus:ring-2 focus:ring-app-primary/20 focus:border-app-primary transition-all duration-200 sm:text-sm"
                                required
                            />
                        </div>
                    </div>

                    <div className="space-y-1">
                        <label className="block text-sm font-semibold text-app-text-label ml-1" htmlFor="email">
                            Business Email
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
                                className="block w-full pl-10 pr-3 py-3 border border-app-border rounded-xl leading-5 bg-app-bg-page placeholder-slate-400 focus:outline-none focus:bg-app-bg-card focus:ring-2 focus:ring-app-primary/20 focus:border-app-primary transition-all duration-200 sm:text-sm"
                                required
                            />
                        </div>
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
                        disabled={isLoading}
                        className="w-full flex items-center justify-center py-3.5 px-4 border border-transparent rounded-xl shadow-md text-sm font-bold text-app-bg-card bg-app-primary hover:bg-app-primary-hover focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-app-primary transition-all duration-200 transform hover:scale-[1.01] disabled:opacity-70 disabled:cursor-not-allowed disabled:transform-none"
                    >
                        {isLoading ? (
                            <>
                                <Loader2 className="animate-spin -ml-1 mr-2 h-4 w-4" />
                                Registering...
                            </>
                        ) : (
                            <>
                                Create Admin Account
                                <ArrowRight className="ml-2 h-4 w-4" />
                            </>
                        )}
                    </button>
                </form>

                <div className="mt-8 pt-6 border-t border-app-border-light text-center">
                    <p className="text-sm text-app-text-muted">
                        Already have an account?{' '}
                        {isModal && onSwitch ? (
                            <button onClick={onSwitch} className="font-semibold text-app-primary hover:text-app-primary hover:underline transition-colors bg-transparent border-0 p-0 inline cursor-pointer">
                                Sign in instead
                            </button>
                        ) : (
                            <Link to="/login" className="font-semibold text-app-primary hover:text-app-primary hover:underline transition-colors">
                                Sign in instead
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
                <img src={logo} alt="DSuite Logo" className="h-10 w-auto object-contain" />
                <div className="h-8 w-px bg-app-border"></div>
                <span className="text-xl font-bold text-app-text-main tracking-tight">DSuite</span>
            </div>

            <div className="min-h-screen flex items-center justify-center p-4">
                {formContent}
            </div>
        </div>
    );
};

export default Signup;
