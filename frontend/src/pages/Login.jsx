import { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { Mail, Lock, ArrowRight, Loader2 } from 'lucide-react';
import { API_ENDPOINTS } from '../config';
import logo from '../assets/logo.png';

const Login = ({ isModal = false, onClose, onSwitch }) => {
    const [email, setEmail] = useState('');
    const [password, setPassword] = useState('');
    const [error, setError] = useState('');
    const [isLoading, setIsLoading] = useState(false);
    const navigate = useNavigate();

    const finishNavigate = (path) => {
        if (isModal && onClose) onClose();
        navigate(path);
    };

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
            finishNavigate('/status-dashboard');
        } catch {
            setError('Invalid email or password. Please try again.');
        } finally {
            setIsLoading(false);
        }
    };

    const formContent = (
        <div className={`w-full max-w-md bg-white rounded-2xl overflow-hidden ${isModal ? 'shadow-none border-0' : 'shadow-xl border border-slate-100'}`}>
            {/* Header Section */}
            <div className="bg-white p-8 pb-0 text-center relative">
                {isModal && onClose && (
                    <button
                        onClick={onClose}
                        className="absolute top-4 right-4 text-slate-400 hover:text-slate-600 transition-colors p-1 rounded-full hover:bg-slate-100"
                    >
                        <svg xmlns="http://www.w3.org/2000/svg" className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                        </svg>
                    </button>
                )}
                <h2 className="text-2xl font-bold text-slate-800 tracking-tight mb-2">Welcome Back</h2>
                <p className="text-slate-500 text-sm">Sign in to continue to your dashboard</p>
            </div>

            {/* Form Section */}
            <div className="p-8">
                {error && (
                    <div className="mb-6 p-4 bg-red-50 border border-red-100 text-red-600 text-sm rounded-lg flex items-center">
                        <svg className="w-4 h-4 mr-2 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                        </svg>
                        {error}
                    </div>
                )}

                <form onSubmit={handleSubmit} className="space-y-5">
                    <div className="space-y-1">
                        <label className="block text-sm font-semibold text-slate-700 ml-1" htmlFor="email">
                            Email Address
                        </label>
                        <div className="relative group">
                            <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                                <Mail className="h-5 w-5 text-slate-400 group-focus-within:text-blue-500 transition-colors" />
                            </div>
                            <input
                                id="email"
                                type="email"
                                placeholder="name@company.com"
                                value={email}
                                onChange={(e) => setEmail(e.target.value)}
                                className="block w-full pl-10 pr-3 py-3 border border-slate-200 rounded-xl leading-5 bg-slate-50 placeholder-slate-400 focus:outline-none focus:bg-white focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 transition-all duration-200 sm:text-sm"
                                required
                            />
                        </div>
                    </div>

                    <div className="space-y-1">
                        <div className="flex items-center justify-between">
                            <label className="block text-sm font-semibold text-slate-700 ml-1" htmlFor="password">
                                Password
                            </label>
                        </div>
                        <div className="relative group">
                            <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                                <Lock className="h-5 w-5 text-slate-400 group-focus-within:text-blue-500 transition-colors" />
                            </div>
                            <input
                                id="password"
                                type="password"
                                placeholder="••••••••"
                                value={password}
                                onChange={(e) => setPassword(e.target.value)}
                                className="block w-full pl-10 pr-3 py-3 border border-slate-200 rounded-xl leading-5 bg-slate-50 placeholder-slate-400 focus:outline-none focus:bg-white focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 transition-all duration-200 sm:text-sm"
                                required
                            />
                        </div>
                    </div>

                    <button
                        type="submit"
                        disabled={isLoading}
                        className="w-full flex items-center justify-center py-3.5 px-4 border border-transparent rounded-xl shadow-md text-sm font-bold text-white bg-blue-600 hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 transition-all duration-200 transform hover:scale-[1.01] disabled:opacity-70 disabled:cursor-not-allowed disabled:transform-none"
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
                </form>

                <div className="mt-8 pt-6 border-t border-slate-100 text-center">
                    <p className="text-sm text-slate-500">
                        Don't have an account?{' '}
                        {isModal && onSwitch ? (
                            <button onClick={onSwitch} className="font-semibold text-blue-600 hover:text-blue-500 hover:underline transition-colors bg-transparent border-0 p-0 inline cursor-pointer">
                                Create an account
                            </button>
                        ) : (
                            <Link to="/signup" className="font-semibold text-blue-600 hover:text-blue-500 hover:underline transition-colors">
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
        <div className="min-h-screen bg-gradient-to-br from-slate-50 to-slate-100 relative">
            {/* Top Left Logo Header */}
            <div className="absolute top-6 left-6 flex items-center space-x-4 z-10">
                <img src={logo} alt="DSuite Logo" className="h-10 w-auto object-contain" />
                <div className="h-8 w-px bg-slate-300"></div>
                <span className="text-xl font-bold text-slate-800 tracking-tight">DSuite</span>
            </div>

            <div className="min-h-screen flex items-center justify-center p-4">
                {formContent}
            </div>
        </div>
    );
};

export default Login;
