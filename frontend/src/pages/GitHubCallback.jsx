import { useEffect, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { API_ENDPOINTS } from '../config';

/**
 * This page handles the GitHub OAuth callback redirect.
 * GitHub redirects here with ?code=... after the user authorises.
 * We exchange the code for a token via our backend and redirect back to dashboard.
 */
const GitHubCallback = () => {
    const [searchParams] = useSearchParams();
    const navigate = useNavigate();
    const [status, setStatus] = useState('Connecting to GitHub...');

    useEffect(() => {
        const code = searchParams.get('code');
        if (!code) {
            setStatus('Missing authorization code. Please try again.');
            return;
        }

        const exchange = async () => {
            try {
                const token = localStorage.getItem('token');
                const resp = await fetch(API_ENDPOINTS.GITHUB_CALLBACK, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        Authorization: `Bearer ${token}`,
                    },
                    body: JSON.stringify({ code }),
                });
                if (!resp.ok) {
                    const err = await resp.json().catch(() => ({}));
                    throw new Error(err.detail || 'Failed to connect GitHub');
                }
                const data = await resp.json();
                setStatus(`Connected as ${data.github_username}! Redirecting...`);
                // Small delay so user sees the success message
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
                <div className="mx-auto w-12 h-12 mb-4">
                    <svg viewBox="0 0 98 96" xmlns="http://www.w3.org/2000/svg" className="w-12 h-12">
                        <path fillRule="evenodd" clipRule="evenodd" d="M48.854 0C21.839 0 0 22 0 49.217c0 21.756 13.993 40.172 33.405 46.69 2.427.49 3.316-1.059 3.316-2.362 0-1.141-.08-5.052-.08-9.127-13.59 2.934-16.42-5.867-16.42-5.867-2.184-5.704-5.42-7.17-5.42-7.17-4.448-3.015.324-3.015.324-3.015 4.934.326 7.523 5.052 7.523 5.052 4.367 7.496 11.404 5.378 14.235 4.074.404-3.178 1.699-5.378 3.074-6.6-10.839-1.141-22.243-5.378-22.243-24.283 0-5.378 1.94-9.778 5.014-13.2-.485-1.222-2.184-6.275.486-13.038 0 0 4.125-1.304 13.426 5.052a46.97 46.97 0 0 1 12.214-1.63c4.125 0 8.33.571 12.213 1.63 9.302-6.356 13.427-5.052 13.427-5.052 2.67 6.763.97 11.816.485 13.038 3.155 3.422 5.015 7.822 5.015 13.2 0 18.905-11.404 23.06-22.324 24.283 1.78 1.548 3.316 4.481 3.316 9.126 0 6.6-.08 11.897-.08 13.526 0 1.304.89 2.853 3.316 2.364 19.412-6.52 33.405-24.935 33.405-46.691C97.707 22 75.788 0 48.854 0z" fill="#24292f" />
                    </svg>
                </div>
                <p className="text-lg font-semibold text-app-text-main mb-2">GitHub OAuth</p>
                <p className="text-sm text-app-text-label">{status}</p>
            </div>
        </div>
    );
};

export default GitHubCallback;
