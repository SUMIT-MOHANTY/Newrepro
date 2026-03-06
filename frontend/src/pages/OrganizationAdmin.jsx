import { useEffect, useMemo, useState } from 'react';
import { AlertCircle, Building2, CheckCircle2, Eye, EyeOff, KeyRound, Loader2, Save, ShieldCheck } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { API_ENDPOINTS } from '../config';

const PROVIDERS = [
    { value: 'azure_ad', label: 'Azure AD / Entra ID' },
    { value: 'okta', label: 'Okta' },
    { value: 'auth0', label: 'Auth0' },
    { value: 'custom_oidc', label: 'Custom OIDC' },
];

const DEFAULT_FORM = {
    sso_provider: 'azure_ad',
    tenant_id: '',
    client_id: '',
    client_secret: '',
    authority_url: '',
    redirect_uri: '',
    logout_url: '',
    scopes: 'openid profile email',
    domain_hint: '',
    sso_enabled: false,
};

const normalizeSettings = (data = {}) => ({
    ...DEFAULT_FORM,
    ...data,
    sso_provider: data.sso_provider || DEFAULT_FORM.sso_provider,
    tenant_id: data.tenant_id || '',
    client_id: data.client_id || '',
    client_secret: data.client_secret || '',
    authority_url: data.authority_url || '',
    redirect_uri: data.redirect_uri || '',
    logout_url: data.logout_url || '',
    scopes: data.scopes || DEFAULT_FORM.scopes,
    domain_hint: data.domain_hint || '',
    sso_enabled: Boolean(data.sso_enabled),
});

export default function OrganizationAdmin({ user }) {
    const navigate = useNavigate();
    const [form, setForm] = useState(DEFAULT_FORM);
    const [isLoading, setIsLoading] = useState(true);
    const [isSaving, setIsSaving] = useState(false);
    const [showSecret, setShowSecret] = useState(false);
    const [forbidden, setForbidden] = useState(false);
    const [error, setError] = useState('');
    const [success, setSuccess] = useState('');
    const [updatedAt, setUpdatedAt] = useState(null);

    const hasAnySsoValue = useMemo(() => (
        Boolean(form.client_id || form.tenant_id || form.authority_url || form.redirect_uri)
    ), [form.client_id, form.tenant_id, form.authority_url, form.redirect_uri]);

    useEffect(() => {
        const token = localStorage.getItem('token');
        if (!token) {
            navigate('/login');
            return;
        }

        const loadSettings = async () => {
            setIsLoading(true);
            setError('');
            try {
                const response = await fetch(API_ENDPOINTS.ORG_SSO_SETTINGS, {
                    headers: { Authorization: `Bearer ${token}` },
                });
                if (response.status === 403) {
                    setForbidden(true);
                    return;
                }
                if (!response.ok) {
                    const data = await response.json().catch(() => ({}));
                    throw new Error(data.detail || 'Failed to load organization settings');
                }
                const data = await response.json();
                setForm(normalizeSettings(data));
                setUpdatedAt(data.updated_at || null);
            } catch (err) {
                setError(err.message || 'Failed to load organization settings');
            } finally {
                setIsLoading(false);
            }
        };

        loadSettings();
    }, [navigate]);

    const handleChange = (field, value) => {
        setForm((prev) => ({ ...prev, [field]: value }));
        if (success) setSuccess('');
    };

    const persistSettings = async (payload, successMessage = 'Organization SSO settings saved successfully.') => {
        const token = localStorage.getItem('token');
        if (!token) {
            navigate('/login');
            return false;
        }

        // Authority URL and Redirect URI are backend-managed only and should not
        // be updated from the frontend payload. They will be derived from env/tenant.
        const {
            authority_url: _authorityUrl,
            redirect_uri: _redirectUri,
            ...sanitizedPayload
        } = payload || {};

        setIsSaving(true);
        setError('');
        setSuccess('');

        try {
            const response = await fetch(API_ENDPOINTS.ORG_SSO_SETTINGS, {
                method: 'PUT',
                headers: {
                    'Content-Type': 'application/json',
                    Authorization: `Bearer ${token}`,
                },
                body: JSON.stringify(sanitizedPayload),
            });
            if (!response.ok) {
                const data = await response.json().catch(() => ({}));
                throw new Error(data.detail || 'Failed to save organization settings');
            }
            const data = await response.json();
            setForm(normalizeSettings(data));
            setUpdatedAt(data.updated_at || null);
            setSuccess(successMessage);
            return true;
        } catch (err) {
            setError(err.message || 'Failed to save organization settings');
            return false;
        } finally {
            setIsSaving(false);
        }
    };

    const handleSave = async (e) => {
        e.preventDefault();
        await persistSettings(form);
    };

    const handleToggleSsoEnabled = async () => {
        if (isSaving) return;

        const nextEnabled = !form.sso_enabled;
        const previousForm = form;
        const nextForm = { ...form, sso_enabled: nextEnabled };
        setForm(nextForm);

        const saved = await persistSettings(
            nextForm,
            nextEnabled ? 'SSO has been enabled for this organization.' : 'SSO has been disabled for this organization.',
        );
        if (!saved) {
            setForm(previousForm);
        }
    };

    if (isLoading) {
        return (
            <main className="flex-1 h-full overflow-y-auto bg-app-bg-page p-3 sm:p-4 md:p-6 w-full">
                <div className="max-w-5xl mx-auto">
                    <div className="bg-app-bg-card rounded-xl border border-app-border-light p-8 flex items-center justify-center gap-3">
                        <Loader2 className="w-5 h-5 animate-spin text-app-primary" />
                        <p className="text-sm font-semibold text-app-text-label">Loading organization admin settings...</p>
                    </div>
                </div>
            </main>
        );
    }

    if (forbidden) {
        return (
            <main className="flex-1 h-full overflow-y-auto bg-app-bg-page p-3 sm:p-4 md:p-6 w-full">
                <div className="max-w-3xl mx-auto">
                    <div className="bg-app-bg-card rounded-xl border border-app-border-light p-8 text-center">
                        <AlertCircle className="w-10 h-10 mx-auto text-amber-500 mb-4" />
                        <h2 className="text-xl font-bold text-app-text-main mb-2">Organization Admin Access Required</h2>
                        <p className="text-sm text-app-text-muted">
                            Your account does not have organization admin privileges for configuring SSO settings.
                        </p>
                    </div>
                </div>
            </main>
        );
    }

    return (
        <main className="flex-1 h-full overflow-y-auto bg-app-bg-page p-3 sm:p-4 md:p-6 w-full">
            <div className="max-w-5xl mx-auto space-y-4">
                <section className="bg-gradient-to-r from-[#1f3763] to-[#2f548f] text-white rounded-2xl border border-blue-900/30 p-6 shadow-lg">
                    <div className="flex items-start justify-between gap-4 flex-wrap">
                        <div>
                            <p className="text-[11px] uppercase tracking-[0.18em] text-blue-200 font-bold mb-2">Organization Identity</p>
                            <h2 className="text-2xl font-extrabold tracking-tight mb-1">SSO & Tenant Configuration</h2>
                            <p className="text-sm text-blue-100">
                                Configure your identity provider once and keep auth settings centralized for your organization.
                            </p>
                        </div>
                        <div className="px-4 py-2 rounded-xl bg-white/10 border border-white/20">
                            <p className="text-[10px] uppercase tracking-wider text-blue-100 font-bold mb-1">Organization</p>
                            <p className="text-sm font-bold">{user?.organization_name || 'Unassigned Organization'}</p>
                        </div>
                    </div>
                </section>

                <section className="bg-app-bg-card rounded-2xl border border-app-border-light shadow-sm overflow-hidden">
                    <div className="px-5 py-4 border-b border-app-border-light bg-app-bg-page/60 flex items-center justify-between gap-3 flex-wrap">
                        <div className="flex items-center gap-2">
                            <ShieldCheck className="w-4 h-4 text-app-primary" />
                            <h3 className="text-sm font-bold text-app-text-main uppercase tracking-widest">Admin Settings</h3>
                        </div>
                        {updatedAt && (
                            <p className="text-xs text-app-text-light">
                                Last updated: {new Date(updatedAt).toLocaleString()}
                            </p>
                        )}
                    </div>

                    <form onSubmit={handleSave} className="p-5 space-y-5">
                        {error && (
                            <div className="rounded-lg border border-red-200 bg-app-status-errorBg px-3 py-2 text-sm text-app-status-error flex items-center gap-2">
                                <AlertCircle className="w-4 h-4" />
                                <span>{error}</span>
                            </div>
                        )}
                        {success && (
                            <div className="rounded-lg border border-green-200 bg-app-status-successBg px-3 py-2 text-sm text-green-700 flex items-center gap-2">
                                <CheckCircle2 className="w-4 h-4" />
                                <span>{success}</span>
                            </div>
                        )}

                        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                            <label className="block">
                                <span className="text-[11px] font-bold text-app-text-muted uppercase tracking-widest">SSO Provider</span>
                                <select
                                    value={form.sso_provider || ''}
                                    onChange={(e) => handleChange('sso_provider', e.target.value)}
                                    className="mt-1 w-full px-3 py-2.5 border border-app-border rounded-lg bg-app-bg-page text-app-text-main focus:outline-none focus:ring-2 focus:ring-indigo-100 focus:border-indigo-400 text-sm"
                                >
                                    {PROVIDERS.map((option) => (
                                        <option key={option.value} value={option.value}>{option.label}</option>
                                    ))}
                                </select>
                            </label>
                            <label className="block">
                                <span className="text-[11px] font-bold text-app-text-muted uppercase tracking-widest">Tenant ID</span>
                                <input
                                    type="text"
                                    value={form.tenant_id || ''}
                                    onChange={(e) => handleChange('tenant_id', e.target.value)}
                                    placeholder="e.g. 8f3b...."
                                    className="mt-1 w-full px-3 py-2.5 border border-app-border rounded-lg bg-app-bg-page text-app-text-main focus:outline-none focus:ring-2 focus:ring-indigo-100 focus:border-indigo-400 text-sm"
                                />
                            </label>
                            <label className="block">
                                <span className="text-[11px] font-bold text-app-text-muted uppercase tracking-widest">Client ID</span>
                                <input
                                    type="text"
                                    value={form.client_id || ''}
                                    onChange={(e) => handleChange('client_id', e.target.value)}
                                    placeholder="Application client id"
                                    className="mt-1 w-full px-3 py-2.5 border border-app-border rounded-lg bg-app-bg-page text-app-text-main focus:outline-none focus:ring-2 focus:ring-indigo-100 focus:border-indigo-400 text-sm"
                                />
                            </label>
                            <label className="block">
                                <span className="text-[11px] font-bold text-app-text-muted uppercase tracking-widest">Client Secret</span>
                                <div className="mt-1 relative">
                                    <input
                                        type={showSecret ? 'text' : 'password'}
                                        value={form.client_secret || ''}
                                        onChange={(e) => handleChange('client_secret', e.target.value)}
                                        placeholder="Application secret"
                                        className="w-full px-3 py-2.5 pr-11 border border-app-border rounded-lg bg-app-bg-page text-app-text-main focus:outline-none focus:ring-2 focus:ring-indigo-100 focus:border-indigo-400 text-sm"
                                    />
                                    <button
                                        type="button"
                                        onClick={() => setShowSecret((prev) => !prev)}
                                        className="absolute right-2 top-1/2 -translate-y-1/2 p-1 text-app-text-light hover:text-app-text-label"
                                        aria-label={showSecret ? 'Hide client secret' : 'Show client secret'}
                                    >
                                        {showSecret ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                                    </button>
                                </div>
                            </label>
                            {/* Authority URL, Redirect URI, Logout URL, Scopes, and Domain Hint
                                are intentionally hidden from the UI.
                                They are still part of the form state and persisted in the backend,
                                but are managed behind the scenes instead of being configured here. */}
                        </div>

                        <div className="flex items-center justify-between gap-4 rounded-xl border border-app-border-light bg-app-bg-page/50 px-4 py-3">
                            <div className="flex items-center gap-2">
                                <Building2 className="w-4 h-4 text-app-text-muted" />
                                <span className="text-sm font-semibold text-app-text-label">Enable SSO for this organization</span>
                            </div>
                            <button
                                type="button"
                                onClick={handleToggleSsoEnabled}
                                disabled={isSaving}
                                className={`inline-flex items-center rounded-full px-3 py-1 text-xs font-bold transition-colors ${
                                    form.sso_enabled
                                        ? 'bg-emerald-100 text-emerald-700 border border-emerald-200'
                                        : 'bg-app-bg-card text-app-text-muted border border-app-border'
                                } ${isSaving ? 'opacity-60 cursor-not-allowed' : ''}`}
                            >
                                {form.sso_enabled ? 'Enabled' : 'Disabled'}
                            </button>
                        </div>

                        <div className="flex items-center justify-between gap-3 flex-wrap pt-2">
                            <div className="inline-flex items-center gap-2 text-xs text-app-text-light">
                                <KeyRound className="w-3.5 h-3.5" />
                                <span>{hasAnySsoValue ? 'SSO fields detected' : 'No SSO values configured yet'}</span>
                            </div>
                            <button
                                type="submit"
                                disabled={isSaving}
                                className="inline-flex items-center gap-2 rounded-lg px-4 py-2.5 text-sm font-bold text-white bg-gradient-to-r from-indigo-600 to-blue-600 hover:from-indigo-700 hover:to-blue-700 disabled:opacity-60 disabled:cursor-not-allowed"
                            >
                                {isSaving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
                                {isSaving ? 'Saving...' : 'Save Organization Settings'}
                            </button>
                        </div>
                    </form>
                </section>
            </div>
        </main>
    );
}
