import { useEffect, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { API_ENDPOINTS } from '../config';

const AzureDevOpsCallback = () => {
    const [searchParams] = useSearchParams();
    const navigate = useNavigate();
    const [status, setStatus] = useState('Connecting to Azure DevOps...');

    useEffect(() => {
        const code = searchParams.get('code');
        if (!code) {
            setStatus('Missing authorization code. Please try again.');
            return;
        }

        const exchange = async () => {
            try {
                const token = localStorage.getItem('token');
                const resp = await fetch(API_ENDPOINTS.AZURE_DEVOPS_CALLBACK, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        Authorization: `Bearer ${token}`,
                    },
                    body: JSON.stringify({ code }),
                });
                if (!resp.ok) {
                    const err = await resp.json().catch(() => ({}));
                    throw new Error(err.detail || 'Failed to connect Azure DevOps');
                }
                const data = await resp.json();
                const userLabel = data.azure_devops_username || 'Azure DevOps';
                setStatus(`Connected as ${userLabel}. Redirecting...`);
                setTimeout(() => navigate('/dashboard'), 1200);
            } catch (e) {
                setStatus(`Error: ${e.message}`);
            }
        };

        exchange();
    }, [searchParams, navigate]);

    return (
        <div className="min-h-screen flex items-center justify-center bg-app-bg-page">
            <div className="bg-app-bg-card rounded-2xl shadow-lg border border-app-border-light p-10 max-w-md text-center">
                <div className="mx-auto w-12 h-12 mb-4 flex items-center justify-center">
                    <svg viewBox="0 0 16 16" aria-hidden="true" className="w-12 h-12" role="img">
                        <path
                            fill="#0078D4"
                            d="M15 3.622v8.512L11.5 15l-5.425-1.975v1.958L3.004 10.97l8.951.7V4.005L15 3.622zm-2.984.428L6.994 1v2.001L2.382 4.356 1 6.13v4.029l1.978.873V5.869l9.038-1.818z"
                        />
                    </svg>
                </div>
                <p className="text-lg font-semibold text-app-text-main mb-2">Azure DevOps OAuth</p>
                <p className="text-sm text-app-text-label">{status}</p>
            </div>
        </div>
    );
};

export default AzureDevOpsCallback;

