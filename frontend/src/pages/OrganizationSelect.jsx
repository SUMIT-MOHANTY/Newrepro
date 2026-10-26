import React, { useState } from 'react';
import { ArrowRight, ShieldCheck, Loader2, Building } from 'lucide-react';
import { API_BASE_URL } from '../config';
import dsuiteLogo from '../assets/DSuite Gradient Ribbon Logo.png';

const OrganizationSelect = ({ organizations, tempToken, onSelectComplete }) => {
    const [selectedOrg, setSelectedOrg] = useState('');
    const [isLoading, setIsLoading] = useState(false);
    const [error, setError] = useState('');

    const handleSelect = async (orgName) => {
        setSelectedOrg(orgName);
        setError('');
        setIsLoading(true);

        const tokenToUse = tempToken || sessionStorage.getItem('temp_token') || localStorage.getItem('temp_token') || '';

        try {
            const response = await fetch(`${API_BASE_URL}/auth/select-organization`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': tokenToUse ? `Bearer ${tokenToUse}` : '',
                },
                body: JSON.stringify({ 
                    organization_name: orgName,
                    temp_token: tokenToUse || undefined,
                }),
            });

            if (!response.ok) {
                const errorData = await response.json().catch(() => ({}));
                throw new Error(errorData.detail || 'Failed to select organization. Please try again.');
            }

            const data = await response.json();
            sessionStorage.removeItem('temp_token');
            localStorage.removeItem('temp_token');
            onSelectComplete(data.access_token);
        } catch (err) {
            setError(err.message || 'An error occurred during selection.');
            setIsLoading(false);
        }
    };

    return (
        <div className="min-h-screen bg-gradient-to-br from-app-bg-page to-app-bg-muted flex items-center justify-center p-4 relative font-sans">
            {/* Top Left Logo Header */}
            <div className="absolute top-6 left-6 flex items-center space-x-4 z-10">
                <img
                    src={dsuiteLogo}
                    alt="DSuite Logo"
                    className="h-10 w-auto object-contain"
                />
                <div className="h-8 w-px bg-app-border"></div>
                <span className="text-xl font-bold text-app-text-main tracking-tight">DSuite</span>
            </div>

            {/* Selection Card with Glassmorphic design */}
            <div className="w-full max-w-lg bg-app-bg-card/70 backdrop-blur-md rounded-2xl p-8 border border-app-border-light shadow-2xl relative overflow-hidden transition-all duration-300">
                <div className="text-center mb-8">
                    <div className="inline-flex p-3.5 bg-app-primary/10 rounded-full text-app-primary mb-4 animate-pulse">
                        <Building className="h-8 w-8" />
                    </div>
                    <h2 className="text-3xl font-extrabold text-app-text-main tracking-tight mb-2">Select Organization</h2>
                    <p className="text-app-text-muted text-sm max-w-md mx-auto">
                        Your account is associated with multiple organizations. Please choose the organization profile you want to log into.
                    </p>
                </div>

                {error && (
                    <div className="mb-6 p-4 bg-app-status-errorBg border border-app-status-errorBg text-app-status-error text-sm rounded-xl flex items-center">
                        <svg className="w-5 h-5 mr-3 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                        </svg>
                        {error}
                    </div>
                )}

                <div className="space-y-4 max-h-[300px] overflow-y-auto pr-2 custom-scrollbar">
                    {organizations.map((org, index) => {
                        const isCurrentSelected = selectedOrg === org;
                        return (
                            <button
                                key={index}
                                onClick={() => !isLoading && handleSelect(org)}
                                disabled={isLoading}
                                className={`w-full text-left p-5 border rounded-xl flex items-center justify-between transition-all duration-300 transform ${
                                    isCurrentSelected
                                        ? 'border-app-primary bg-app-primary/5 ring-2 ring-app-primary/20 scale-[1.01]'
                                        : 'border-app-border bg-app-bg-card hover:bg-app-bg-muted hover:border-app-text-muted hover:scale-[1.01]'
                                } ${isLoading ? 'opacity-60 cursor-not-allowed transform-none' : 'cursor-pointer'}`}
                            >
                                <div className="flex items-center space-x-4">
                                    <div className={`p-2.5 rounded-lg transition-colors duration-300 ${isCurrentSelected ? 'bg-app-primary text-white' : 'bg-app-bg-muted text-app-text-muted'}`}>
                                        <Building className="h-5 w-5" />
                                    </div>
                                    <div>
                                        <h4 className="font-bold text-app-text-main leading-tight">{org}</h4>
                                        <p className="text-xs text-app-text-muted mt-0.5">Click to log into this workspace</p>
                                    </div>
                                </div>
                                <div className="flex items-center">
                                    {isLoading && isCurrentSelected ? (
                                        <Loader2 className="animate-spin h-5 w-5 text-app-primary" />
                                    ) : (
                                        <ArrowRight className={`h-5 w-5 transition-transform duration-300 ${isCurrentSelected ? 'text-app-primary translate-x-1' : 'text-app-text-light group-hover:translate-x-1'}`} />
                                    )}
                                </div>
                            </button>
                        );
                    })}
                </div>

                <div className="mt-8 pt-6 border-t border-app-border-light flex flex-col items-center gap-3">
                    <div className="text-center text-xs text-app-text-muted flex items-center justify-center">
                        <ShieldCheck className="h-4 w-4 mr-1.5 text-app-status-success" />
                        Secure organization login session powered by DSuite RBAC.
                    </div>
                    <button
                        type="button"
                        onClick={() => {
                            sessionStorage.removeItem('temp_token');
                            localStorage.removeItem('temp_token');
                            window.location.assign('/login');
                        }}
                        className="text-xs font-semibold text-app-primary hover:underline hover:text-app-primary-hover transition-colors"
                    >
                        ← Back to Sign In
                    </button>
                </div>
            </div>
        </div>
    );
};

export default OrganizationSelect;
