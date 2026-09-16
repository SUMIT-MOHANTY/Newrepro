import { useEffect, useMemo, useState } from 'react';
import { AlertCircle, Building2, Calendar, CheckCircle2, Coins, Copy, Eye, EyeOff, KeyRound, Loader2, Plus, Save, ShieldCheck, Trash2, Users } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { API_BASE_URL, API_ENDPOINTS } from '../config';
import OrgTokenOpsPanel from '../components/OrgTokenOpsPanel';

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
    const [activeTab, setActiveTab] = useState('sso'); // 'sso' | 'access'
    const [form, setForm] = useState(DEFAULT_FORM);
    const [isLoading, setIsLoading] = useState(true);
    const [isSaving, setIsSaving] = useState(false);
    const [showSecret, setShowSecret] = useState(false);
    const [forbidden, setForbidden] = useState(false);
    const [error, setError] = useState('');
    const [success, setSuccess] = useState('');
    const [updatedAt, setUpdatedAt] = useState(null);
    const [onboardedAt, setOnboardedAt] = useState(null);

    /**
     * Converts a UTC datetime string from the backend to the user's
     * local timezone for display. Handles both timezone-aware strings
     * (e.g. "2024-01-15T10:30:00+00:00") and naive strings that are
     * actually UTC (e.g. "2024-01-15T10:30:00") by appending 'Z'.
     */
    const formatUTCToLocal = (utcDateString) => {
        if (!utcDateString) return '—';
        let dateStr = String(utcDateString);
        // If no timezone indicator is present, assume UTC by appending 'Z'
        if (!dateStr.endsWith('Z') && !/[+-]\d{2}:\d{2}$/.test(dateStr)) {
            dateStr = dateStr + 'Z';
        }
        return new Date(dateStr).toLocaleString(undefined, {
            dateStyle: 'medium',
            timeStyle: 'short',
        });
    };

    // RBAC roles + invites
    const [pages, setPages] = useState([]);
    const [roles, setRoles] = useState([]);
    const [rolesLoading, setRolesLoading] = useState(false);
    const [selectedRoleId, setSelectedRoleId] = useState(null);
    const [roleDraft, setRoleDraft] = useState({ name: '', description: '', allowed_paths: [] });
    const [roleSaving, setRoleSaving] = useState(false);
    const [roleDeleting, setRoleDeleting] = useState(false);

    const [inviteEmail, setInviteEmail] = useState('');
    const [inviteRoleId, setInviteRoleId] = useState(null);
    const [inviteCreating, setInviteCreating] = useState(false);
    const [inviteLink, setInviteLink] = useState('');
    const [invites, setInvites] = useState([]);
    const [invitesLoading, setInvitesLoading] = useState(false);
    const [invitesPage, setInvitesPage] = useState(1);
    const INVITES_PER_PAGE = 4;

    const [usersList, setUsersList] = useState([]);
    const [usersLoading, setUsersLoading] = useState(false);
    const [usersPage, setUsersPage] = useState(1);
    const USERS_PER_PAGE = 5;

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

                // Fetch onboarded_at date from org billing logs
                fetch(`${API_BASE_URL}/organization/billing-logs`, {
                    headers: { Authorization: `Bearer ${token}` },
                }).then(r => r.ok ? r.json() : null).then(bData => {
                    if (bData?.onboarded_at) {
                        setOnboardedAt(bData.onboarded_at);
                    }
                }).catch(() => {});
            } catch (err) {
                setError(err.message || 'Failed to load organization settings');
            } finally {
                setIsLoading(false);
            }
        };

        loadSettings();
    }, [navigate]);

    const loadAccessControl = async () => {
        const token = localStorage.getItem('token');
        if (!token) {
            navigate('/login');
            return;
        }
        setRolesLoading(true);
        try {
            const [pagesRes, rolesRes] = await Promise.all([
                fetch(API_ENDPOINTS.ORG_RBAC_PAGES, { headers: { Authorization: `Bearer ${token}` } }),
                fetch(API_ENDPOINTS.ORG_RBAC_ROLES, { headers: { Authorization: `Bearer ${token}` } }),
            ]);
            const pagesData = await pagesRes.json().catch(() => ([]));
            if (pagesRes.ok && Array.isArray(pagesData)) setPages(pagesData);
            const rolesData = await rolesRes.json().catch(() => ([]));
            if (!rolesRes.ok) {
                const msg = rolesData?.detail || 'Failed to load roles';
                throw new Error(msg);
            }
            setRoles(Array.isArray(rolesData) ? rolesData : []);

            const firstRoleId = Array.isArray(rolesData) && rolesData.length ? rolesData[0].id : null;
            setSelectedRoleId((prev) => prev ?? firstRoleId);
        } catch (e) {
            setError(e.message || 'Failed to load access control');
        } finally {
            setRolesLoading(false);
        }
    };

    const loadInvites = async () => {
        const token = localStorage.getItem('token');
        if (!token) return;
        setInvitesLoading(true);
        try {
            const res = await fetch(API_ENDPOINTS.ORG_INVITES, { headers: { Authorization: `Bearer ${token}` } });
            const data = await res.json().catch(() => ([]));
            if (!res.ok) throw new Error(data?.detail || 'Failed to load invites');
            setInvites(Array.isArray(data) ? data : []);
        } catch (e) {
            setError(e.message || 'Failed to load invites');
        } finally {
            setInvitesLoading(false);
        }
    };

    const loadUsers = async () => {
        const token = localStorage.getItem('token');
        if (!token) return;
        setUsersLoading(true);
        try {
            const res = await fetch(API_ENDPOINTS.ORG_USERS, { headers: { Authorization: `Bearer ${token}` } });
            const data = await res.json().catch(() => ([]));
            if (!res.ok) throw new Error(data?.detail || 'Failed to load users');
            setUsersList(Array.isArray(data) ? data : []);
        } catch (e) {
            setError(e.message || 'Failed to load users');
        } finally {
            setUsersLoading(false);
        }
    };

    useEffect(() => {
        if (!user?.is_org_admin) return;
        if (activeTab === 'access') {
            loadAccessControl();
            loadInvites();
        } else if (activeTab === 'users') {
            loadUsers();
        }
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [activeTab]);

    useEffect(() => {
        const selected = roles.find((r) => String(r.id) === String(selectedRoleId));
        if (!selected) return;
        setRoleDraft({
            name: selected.name || '',
            description: selected.description || '',
            allowed_paths: Array.isArray(selected.allowed_paths) ? selected.allowed_paths : [],
        });
        if (!inviteRoleId) {
            setInviteRoleId(selected.id);
        }
    }, [roles, selectedRoleId, inviteRoleId]);

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
                        <AlertCircle className="w-10 h-10 mx-auto text-app-status-warning mb-4" />
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
                <section className="bg-gradient-to-r from-blue-900 via-indigo-950 to-slate-900 text-white rounded-2xl border border-blue-500/25 p-6 shadow-xl relative overflow-hidden">
                    <div className="absolute top-0 right-0 -mr-16 -mt-16 w-64 h-64 bg-blue-500/10 rounded-full blur-3xl pointer-events-none" />
                    <div className="flex items-start justify-between gap-4 flex-wrap relative z-10">
                        <div>
                            <p className="text-[11px] uppercase tracking-[0.18em] text-blue-300 font-bold mb-2">Organization Identity</p>
                            <h2 className="text-2xl font-extrabold tracking-tight mb-1 text-white">SSO & Tenant Configuration</h2>
                            <p className="text-sm text-blue-100/80">
                                Configure your identity provider once and keep auth settings centralized for your organization.
                            </p>
                        </div>
                        <div className="flex items-center gap-3 flex-wrap">
                            {onboardedAt && (
                                <div className="px-4 py-2 rounded-xl bg-white/10 border border-white/20 text-left backdrop-blur-sm">
                                    <p className="text-[10px] uppercase tracking-wider text-emerald-300 font-bold mb-1 flex items-center gap-1">
                                        <Calendar className="w-3 h-3 text-emerald-400" /> Onboarded Date
                                    </p>
                                    <p className="text-sm font-bold text-emerald-100">
                                        {new Date(onboardedAt).toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' })}
                                    </p>
                                </div>
                            )}
                            <div className="px-4 py-2 rounded-xl bg-white/10 border border-white/20 text-left backdrop-blur-sm">
                                <p className="text-[10px] uppercase tracking-wider text-blue-200 font-bold mb-1">Organization</p>
                                <p className="text-sm font-bold text-white">{user?.organization_name || 'Unassigned Organization'}</p>
                            </div>
                        </div>
                    </div>
                </section>

                <section className="bg-white dark:bg-slate-900/90 rounded-2xl border border-slate-200 dark:border-slate-800 shadow-sm overflow-hidden">
                    <div className="px-5 py-3 border-b border-slate-200 dark:border-slate-800 bg-slate-50/60 dark:bg-slate-800/40 flex items-center justify-between gap-3 flex-wrap">
                        <div className="flex items-center gap-2">
                            <ShieldCheck className="w-4 h-4 text-app-primary" />
                            <h3 className="text-sm font-bold text-slate-900 dark:text-white uppercase tracking-widest">Organization Admin</h3>
                        </div>
                        {activeTab === 'sso' && updatedAt && (
                            <p className="text-xs text-slate-500 dark:text-slate-400">
                                Last updated: {formatUTCToLocal(updatedAt)}
                            </p>
                        )}
                        <div className="flex items-center gap-2">
                            <button
                                type="button"
                                onClick={() => setActiveTab('sso')}
                                className={`px-3.5 py-1.5 rounded-lg text-xs font-bold border transition-all cursor-pointer ${activeTab === 'sso'
                                    ? 'bg-blue-600 text-white border-blue-600 shadow-sm shadow-blue-500/20'
                                    : 'bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300 border-slate-200 dark:border-slate-700 hover:text-slate-900 dark:hover:text-white hover:bg-slate-200 dark:hover:bg-slate-700'
                                    }`}
                            >
                                SSO Settings
                            </button>
                            <button
                                type="button"
                                onClick={() => setActiveTab('access')}
                                className={`px-3.5 py-1.5 rounded-lg text-xs font-bold border transition-all cursor-pointer ${activeTab === 'access'
                                    ? 'bg-blue-600 text-white border-blue-600 shadow-sm shadow-blue-500/20'
                                    : 'bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300 border-slate-200 dark:border-slate-700 hover:text-slate-900 dark:hover:text-white hover:bg-slate-200 dark:hover:bg-slate-700'
                                    }`}
                            >
                                Roles & Invites
                            </button>
                            <button
                                type="button"
                                onClick={() => setActiveTab('users')}
                                className={`px-3.5 py-1.5 rounded-lg text-xs font-bold border transition-all cursor-pointer ${activeTab === 'users'
                                    ? 'bg-blue-600 text-white border-blue-600 shadow-sm shadow-blue-500/20'
                                    : 'bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300 border-slate-200 dark:border-slate-700 hover:text-slate-900 dark:hover:text-white hover:bg-slate-200 dark:hover:bg-slate-700'
                                    }`}
                            >
                                Users
                            </button>
                            <button
                                type="button"
                                onClick={() => setActiveTab('tokens')}
                                className={`px-3.5 py-1.5 rounded-lg text-xs font-bold border transition-all flex items-center gap-1.5 cursor-pointer ${activeTab === 'tokens'
                                    ? 'bg-blue-600 text-white border-blue-600 shadow-sm shadow-blue-500/20'
                                    : 'bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300 border-slate-200 dark:border-slate-700 hover:text-slate-900 dark:hover:text-white hover:bg-slate-200 dark:hover:bg-slate-700'
                                    }`}
                            >
                                <Coins className="w-3.5 h-3.5" />
                                Token Management
                            </button>
                        </div>
                    </div>

                    {activeTab === 'sso' ? (
                        <form onSubmit={handleSave} className="p-5 space-y-5">
                            {error && (
                                <div className="rounded-lg border border-red-200 dark:border-red-900/50 bg-red-50 dark:bg-red-950/30 px-3 py-2 text-sm text-red-600 dark:text-red-400 flex items-center gap-2">
                                    <AlertCircle className="w-4 h-4 shrink-0" />
                                    <span>{error}</span>
                                </div>
                            )}
                            {success && (
                                <div className="rounded-lg border border-emerald-200 dark:border-emerald-900/50 bg-emerald-50 dark:bg-emerald-950/30 px-3 py-2 text-sm text-emerald-600 dark:text-emerald-400 flex items-center gap-2">
                                    <CheckCircle2 className="w-4 h-4 shrink-0" />
                                    <span>{success}</span>
                                </div>
                            )}

                            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                <label className="block">
                                    <span className="text-[11px] font-bold text-slate-700 dark:text-slate-300 uppercase tracking-widest">SSO Provider</span>
                                    <select
                                        value={form.sso_provider || ''}
                                        onChange={(e) => handleChange('sso_provider', e.target.value)}
                                        className="mt-1 w-full px-3.5 py-2.5 border border-slate-300 dark:border-slate-700 rounded-lg bg-slate-50 dark:bg-slate-950/60 text-slate-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500/30 focus:border-blue-500 text-sm transition-colors"
                                    >
                                        {PROVIDERS.map((option) => (
                                             <option key={option.value} value={option.value} className="bg-white dark:bg-slate-900 text-slate-900 dark:text-white">{option.label}</option>
                                        ))}
                                    </select>
                                </label>
                                <label className="block">
                                    <span className="text-[11px] font-bold text-slate-700 dark:text-slate-300 uppercase tracking-widest">Tenant ID</span>
                                    <input
                                        type="text"
                                        value={form.tenant_id || ''}
                                        onChange={(e) => handleChange('tenant_id', e.target.value)}
                                        placeholder="e.g. 8f3b...."
                                        className="mt-1 w-full px-3.5 py-2.5 border border-slate-300 dark:border-slate-700 rounded-lg bg-slate-50 dark:bg-slate-950/60 text-slate-900 dark:text-white placeholder-slate-400 dark:placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-blue-500/30 focus:border-blue-500 text-sm transition-colors"
                                    />
                                </label>
                                <label className="block">
                                    <span className="text-[11px] font-bold text-slate-700 dark:text-slate-300 uppercase tracking-widest">Client ID</span>
                                    <input
                                        type="text"
                                        value={form.client_id || ''}
                                        onChange={(e) => handleChange('client_id', e.target.value)}
                                        placeholder="Application client id"
                                        className="mt-1 w-full px-3.5 py-2.5 border border-slate-300 dark:border-slate-700 rounded-lg bg-slate-50 dark:bg-slate-950/60 text-slate-900 dark:text-white placeholder-slate-400 dark:placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-blue-500/30 focus:border-blue-500 text-sm transition-colors"
                                    />
                                </label>
                                <label className="block">
                                    <span className="text-[11px] font-bold text-slate-700 dark:text-slate-300 uppercase tracking-widest">Client Secret</span>
                                    <div className="mt-1 relative">
                                        <input
                                            type={showSecret ? 'text' : 'password'}
                                            value={form.client_secret || ''}
                                            onChange={(e) => handleChange('client_secret', e.target.value)}
                                            placeholder="Application secret"
                                            className="w-full px-3.5 py-2.5 pr-11 border border-slate-300 dark:border-slate-700 rounded-lg bg-slate-50 dark:bg-slate-950/60 text-slate-900 dark:text-white placeholder-slate-400 dark:placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-blue-500/30 focus:border-blue-500 text-sm transition-colors"
                                        />
                                        <button
                                            type="button"
                                            onClick={() => setShowSecret((prev) => !prev)}
                                            className="absolute right-2 top-1/2 -translate-y-1/2 p-1 text-slate-400 hover:text-slate-200"
                                            aria-label={showSecret ? 'Hide client secret' : 'Show client secret'}
                                        >
                                            {showSecret ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                                        </button>
                                    </div>
                                </label>
                            </div>

                            <div className="flex items-center justify-between gap-4 rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50/60 dark:bg-slate-800/30 px-4 py-3">
                                <div className="flex items-center gap-2">
                                    <Building2 className="w-4 h-4 text-slate-500 dark:text-slate-400" />
                                    <span className="text-sm font-semibold text-slate-800 dark:text-slate-200">Enable SSO for this organization</span>
                                </div>
                                <button
                                    type="button"
                                    onClick={handleToggleSsoEnabled}
                                    disabled={isSaving}
                                    className={`inline-flex items-center rounded-full px-3.5 py-1 text-xs font-bold transition-colors ${form.sso_enabled
                                        ? 'bg-emerald-500 text-white border border-emerald-600 shadow-sm shadow-emerald-500/20'
                                        : 'bg-slate-200 dark:bg-slate-800 text-slate-600 dark:text-slate-400 border border-slate-300 dark:border-slate-700'
                                        } ${isSaving ? 'opacity-60 cursor-not-allowed' : 'cursor-pointer'}`}
                                >
                                    {form.sso_enabled ? 'Enabled' : 'Disabled'}
                                </button>
                            </div>

                            <div className="flex items-center justify-between gap-3 flex-wrap pt-2">
                                <div className="inline-flex items-center gap-2 text-xs text-slate-500 dark:text-slate-400">
                                    <KeyRound className="w-3.5 h-3.5" />
                                    <span>{hasAnySsoValue ? 'SSO fields detected' : 'No SSO values configured yet'}</span>
                                </div>
                                <button
                                    type="submit"
                                    disabled={isSaving}
                                    className="inline-flex items-center gap-2 rounded-lg px-4 py-2.5 text-sm font-bold text-white bg-blue-600 hover:bg-blue-500 shadow-md shadow-blue-500/20 disabled:opacity-60 disabled:cursor-not-allowed cursor-pointer transition-all active:scale-[0.98]"
                                >
                                    {isSaving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
                                    {isSaving ? 'Saving...' : 'Save Organization Settings'}
                                </button>
                            </div>
                        </form>
                    ) : activeTab === 'access' ? (
                        <div className="p-5 space-y-5">
                            {error && (
                                <div className="rounded-lg border border-red-200 bg-app-status-errorBg px-3 py-2 text-sm text-app-status-error flex items-center gap-2">
                                    <AlertCircle className="w-4 h-4" />
                                    <span>{error}</span>
                                </div>
                            )}
                            {success && (
                                <div className="rounded-lg border border-green-200 bg-app-status-successBg px-3 py-2 text-sm text-app-status-success flex items-center gap-2">
                                    <CheckCircle2 className="w-4 h-4" />
                                    <span>{success}</span>
                                </div>
                            )}

                            <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
                                <section className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900/90 overflow-hidden">
                                    <div className="px-4 py-3 border-b border-slate-200 dark:border-slate-800 bg-slate-50/60 dark:bg-slate-800/40 flex items-center justify-between">
                                        <div className="flex items-center gap-2">
                                            <ShieldCheck className="w-4 h-4 text-app-primary" />
                                            <h4 className="text-sm font-extrabold text-slate-900 dark:text-white tracking-wide">Roles & Page Access</h4>
                                        </div>
                                        <button
                                            type="button"
                                            onClick={() => {
                                                setSelectedRoleId(null);
                                                setRoleDraft({ name: '', description: '', allowed_paths: [] });
                                                setSuccess('');
                                                setError('');
                                            }}
                                            className="inline-flex items-center gap-2 rounded-lg px-3 py-1.5 text-xs font-bold bg-slate-100 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 hover:bg-slate-200 dark:hover:bg-slate-700 text-slate-800 dark:text-slate-200 transition-colors"
                                        >
                                            <Plus className="w-4 h-4" />
                                            New Role
                                        </button>
                                    </div>

                                    <div className="p-4 space-y-4">
                                        {rolesLoading ? (
                                            <div className="flex items-center gap-2 text-sm text-slate-500 dark:text-slate-400">
                                                <Loader2 className="w-4 h-4 animate-spin text-app-primary" />
                                                Loading roles...
                                            </div>
                                        ) : (
                                            <label className="block">
                                                <span className="text-[11px] font-bold text-slate-700 dark:text-slate-300 uppercase tracking-widest">Select Role</span>
                                                <select
                                                    value={selectedRoleId ?? ''}
                                                    onChange={(e) => setSelectedRoleId(e.target.value ? Number(e.target.value) : null)}
                                                    className="mt-1 w-full px-3.5 py-2.5 border border-slate-300 dark:border-slate-700 rounded-lg bg-slate-50 dark:bg-slate-950/60 text-slate-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500/30 focus:border-blue-500 text-sm transition-colors"
                                                >
                                                    <option value="" className="bg-white dark:bg-slate-900">Creating new role</option>
                                                    {roles.map((r) => (
                                                        <option key={r.id} value={r.id} className="bg-white dark:bg-slate-900">
                                                            {r.name}{r.is_system ? ' system' : ''}
                                                        </option>
                                                    ))}
                                                </select>
                                            </label>
                                        )}

                                        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                            <label className="block">
                                                <span className="text-[11px] font-bold text-slate-700 dark:text-slate-300 uppercase tracking-widest">Role Name</span>
                                                <input
                                                    type="text"
                                                    value={roleDraft.name}
                                                    onChange={(e) => setRoleDraft((p) => ({ ...p, name: e.target.value }))}
                                                    placeholder="e.g. Viewer"
                                                    className="mt-1 w-full px-3.5 py-2.5 border border-slate-300 dark:border-slate-700 rounded-lg bg-slate-50 dark:bg-slate-950/60 text-slate-900 dark:text-white placeholder-slate-400 dark:placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-blue-500/30 focus:border-blue-500 text-sm transition-colors"
                                                />
                                            </label>
                                            <label className="block">
                                                <span className="text-[11px] font-bold text-slate-700 dark:text-slate-300 uppercase tracking-widest">Description</span>
                                                <input
                                                    type="text"
                                                    value={roleDraft.description}
                                                    onChange={(e) => setRoleDraft((p) => ({ ...p, description: e.target.value }))}
                                                    placeholder="Optional"
                                                    className="mt-1 w-full px-3.5 py-2.5 border border-slate-300 dark:border-slate-700 rounded-lg bg-slate-50 dark:bg-slate-950/60 text-slate-900 dark:text-white placeholder-slate-400 dark:placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-blue-500/30 focus:border-blue-500 text-sm transition-colors"
                                                />
                                            </label>
                                        </div>

                                        <div className="rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50/60 dark:bg-slate-800/30 p-4">
                                            <p className="text-[11px] font-bold text-slate-700 dark:text-slate-300 uppercase tracking-widest mb-3">Page Access</p>
                                            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                                                {(pages || []).map((p) => {
                                                    const checked = (roleDraft.allowed_paths || []).includes(p.path);
                                                    return (
                                                        <label key={p.path} className="flex items-center gap-2 text-sm text-slate-800 dark:text-slate-200">
                                                            <input
                                                                type="checkbox"
                                                                checked={checked}
                                                                onChange={(e) => {
                                                                    const next = new Set(roleDraft.allowed_paths || []);
                                                                    if (e.target.checked) next.add(p.path);
                                                                    else next.delete(p.path);
                                                                    setRoleDraft((prev) => ({ ...prev, allowed_paths: Array.from(next) }));
                                                                }}
                                                                className="accent-blue-600 rounded"
                                                            />
                                                            <span className="truncate" title={p.path}>{p.label}</span>
                                                        </label>
                                                    );
                                                })}
                                            </div>
                                        </div>

                                        <div className="flex items-center justify-between gap-3 flex-wrap">
                                            <button
                                                type="button"
                                                disabled={roleSaving}
                                                onClick={async () => {
                                                    const token = localStorage.getItem('token');
                                                    if (!token) { navigate('/login'); return; }
                                                    setRoleSaving(true);
                                                    setError('');
                                                    setSuccess('');
                                                    try {
                                                        const isUpdate = Boolean(selectedRoleId);
                                                        const url = isUpdate ? API_ENDPOINTS.ORG_RBAC_ROLE(selectedRoleId) : API_ENDPOINTS.ORG_RBAC_ROLES;
                                                        const res = await fetch(url, {
                                                            method: isUpdate ? 'PUT' : 'POST',
                                                            headers: {
                                                                'Content-Type': 'application/json',
                                                                Authorization: `Bearer ${token}`,
                                                            },
                                                            body: JSON.stringify({
                                                                name: roleDraft.name || '',
                                                                description: roleDraft.description || '',
                                                                allowed_paths: roleDraft.allowed_paths || [],
                                                            }),
                                                        });
                                                        const data = await res.json().catch(() => ({}));
                                                        if (!res.ok) throw new Error(data.detail || 'Failed to save role');
                                                        setSuccess(isUpdate ? 'Role updated.' : 'Role created.');
                                                        await loadAccessControl();
                                                        if (!isUpdate && data?.id) setSelectedRoleId(data.id);
                                                    } catch (e) {
                                                        setError(e.message || 'Failed to save role');
                                                    } finally {
                                                        setRoleSaving(false);
                                                    }
                                                }}
                                                className="inline-flex items-center gap-2 rounded-lg px-4 py-2.5 text-sm font-bold text-white bg-blue-600 hover:bg-blue-500 shadow-sm disabled:opacity-60 disabled:cursor-not-allowed"
                                            >
                                                {roleSaving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
                                                {roleSaving ? 'Saving...' : 'Save Role'}
                                            </button>

                                            <button
                                                type="button"
                                                disabled={!selectedRoleId || roleDeleting}
                                                onClick={async () => {
                                                    if (!selectedRoleId) return;
                                                    const token = localStorage.getItem('token');
                                                    if (!token) { navigate('/login'); return; }
                                                    setRoleDeleting(true);
                                                    setError('');
                                                    setSuccess('');
                                                    try {
                                                        const res = await fetch(API_ENDPOINTS.ORG_RBAC_ROLE(selectedRoleId), {
                                                            method: 'DELETE',
                                                            headers: { Authorization: `Bearer ${token}` },
                                                        });
                                                        const data = await res.json().catch(() => ({}));
                                                        if (!res.ok) throw new Error(data.detail || 'Failed to delete role');
                                                        setSuccess('Role deleted.');
                                                        setSelectedRoleId(null);
                                                        setRoleDraft({ name: '', description: '', allowed_paths: [] });
                                                        await loadAccessControl();
                                                    } catch (e) {
                                                        setError(e.message || 'Failed to delete role');
                                                    } finally {
                                                        setRoleDeleting(false);
                                                    }
                                                }}
                                                className="inline-flex items-center gap-2 rounded-lg px-3.5 py-2.5 text-sm font-bold border border-red-300 dark:border-red-900/50 text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-950/30 disabled:opacity-60 disabled:cursor-not-allowed transition-colors"
                                            >
                                                {roleDeleting ? <Loader2 className="w-4 h-4 animate-spin" /> : <Trash2 className="w-4 h-4" />}
                                                Delete
                                            </button>
                                        </div>
                                    </div>
                                </section>

                                <section className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900/90 overflow-hidden">
                                    <div className="px-4 py-3 border-b border-slate-200 dark:border-slate-800 bg-slate-50/60 dark:bg-slate-800/40 flex items-center gap-2">
                                        <Users className="w-4 h-4 text-app-primary" />
                                        <h4 className="text-sm font-extrabold text-slate-900 dark:text-white tracking-wide">Invite Users</h4>
                                    </div>

                                    <div className="p-4 space-y-4">
                                        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                            <label className="block">
                                                <span className="text-[11px] font-bold text-slate-700 dark:text-slate-300 uppercase tracking-widest">Role</span>
                                                <select
                                                    value={inviteRoleId ?? ''}
                                                    onChange={(e) => setInviteRoleId(e.target.value ? Number(e.target.value) : null)}
                                                    className="mt-1 w-full px-3.5 py-2.5 border border-slate-300 dark:border-slate-700 rounded-lg bg-slate-50 dark:bg-slate-950/60 text-slate-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500/30 focus:border-blue-500 text-sm transition-colors"
                                                >
                                                    <option value="" disabled className="bg-white dark:bg-slate-900">Select a role</option>
                                                    {roles.map((r) => (
                                                        <option key={r.id} value={r.id} className="bg-white dark:bg-slate-900">{r.name}</option>
                                                    ))}
                                                </select>
                                            </label>
                                            <label className="block">
                                                <span className="text-[11px] font-bold text-slate-700 dark:text-slate-300 uppercase tracking-widest">Invite Email (optional)</span>
                                                <input
                                                    type="email"
                                                    value={inviteEmail}
                                                    onChange={(e) => setInviteEmail(e.target.value)}
                                                    placeholder="name@company.com"
                                                    className="mt-1 w-full px-3.5 py-2.5 border border-slate-300 dark:border-slate-700 rounded-lg bg-slate-50 dark:bg-slate-950/60 text-slate-900 dark:text-white placeholder-slate-400 dark:placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-blue-500/30 focus:border-blue-500 text-sm transition-colors"
                                                />
                                            </label>
                                        </div>

                                        <button
                                            type="button"
                                            disabled={inviteCreating || !inviteRoleId}
                                            onClick={async () => {
                                                const token = localStorage.getItem('token');
                                                if (!token) { navigate('/login'); return; }
                                                setInviteCreating(true);
                                                setError('');
                                                setSuccess('');
                                                setInviteLink('');
                                                try {
                                                    const res = await fetch(API_ENDPOINTS.ORG_INVITES, {
                                                        method: 'POST',
                                                        headers: {
                                                             'Content-Type': 'application/json',
                                                            Authorization: `Bearer ${token}`,
                                                        },
                                                        body: JSON.stringify({
                                                            email: inviteEmail.trim() || null,
                                                            role_id: inviteRoleId,
                                                            expires_in_days: 7,
                                                        }),
                                                    });
                                                    const data = await res.json().catch(() => ({}));
                                                    if (!res.ok) throw new Error(data.detail || 'Failed to create invite');
                                                    setInviteLink(data.invite_url || '');
                                                    setSuccess('Invite link created.');
                                                    setInvitesPage(1);
                                                    await loadInvites();
                                                } catch (e) {
                                                    setError(e.message || 'Failed to create invite');
                                                } finally {
                                                    setInviteCreating(false);
                                                }
                                            }}
                                            className="inline-flex items-center gap-2 rounded-lg px-4 py-2.5 text-sm font-bold text-white bg-blue-600 hover:bg-blue-500 shadow-md shadow-blue-500/20 disabled:opacity-60 disabled:cursor-not-allowed cursor-pointer transition-all active:scale-[0.98]"
                                        >
                                            {inviteCreating ? <Loader2 className="w-4 h-4 animate-spin" /> : <Plus className="w-4 h-4" />}
                                            {inviteCreating ? 'Creating...' : 'Create Invite Link'}
                                        </button>

                                        {inviteLink && (
                                            <div className="rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50/60 dark:bg-slate-800/30 p-4">
                                                <p className="text-[11px] font-bold text-slate-700 dark:text-slate-300 uppercase tracking-widest mb-2">Invite Link</p>
                                                <div className="flex items-center gap-2">
                                                    <input
                                                        type="text"
                                                        readOnly
                                                        value={inviteLink}
                                                        className="flex-1 px-3 py-2 border border-slate-300 dark:border-slate-700 rounded-lg bg-white dark:bg-slate-900 text-slate-900 dark:text-white text-sm"
                                                    />
                                                    <button
                                                        type="button"
                                                        onClick={async () => {
                                                            try {
                                                                await navigator.clipboard.writeText(inviteLink);
                                                                setSuccess('Invite link copied.');
                                                            } catch {
                                                                setError('Unable to copy link. Please copy manually.');
                                                            }
                                                        }}
                                                        className="inline-flex items-center gap-2 rounded-lg px-3.5 py-2 text-sm font-bold border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 hover:bg-slate-100 dark:hover:bg-slate-700 text-slate-800 dark:text-slate-200 transition-colors"
                                                    >
                                                        <Copy className="w-4 h-4" />
                                                        Copy
                                                    </button>
                                                </div>
                                            </div>
                                        )}

                                        <div className="rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50/60 dark:bg-slate-800/30 p-4">
                                            <div className="flex items-center justify-between gap-2 mb-3">
                                                <p className="text-[11px] font-bold text-slate-700 dark:text-slate-300 uppercase tracking-widest">Recent Invites</p>
                                                <button
                                                    type="button"
                                                    onClick={loadInvites}
                                                    className="text-xs font-bold text-app-primary hover:text-blue-400 cursor-pointer"
                                                >
                                                    Refresh
                                                </button>
                                            </div>
                                            {invitesLoading ? (
                                                <div className="flex items-center gap-2 text-sm text-slate-500 dark:text-slate-400">
                                                    <Loader2 className="w-4 h-4 animate-spin text-app-primary" />
                                                    Loading invites...
                                                </div>
                                            ) : invites.length === 0 ? (
                                                <p className="text-sm text-slate-500 dark:text-slate-400">No invites created yet.</p>
                                            ) : (
                                                <div className="space-y-2">
                                                    {invites.slice((invitesPage - 1) * INVITES_PER_PAGE, invitesPage * INVITES_PER_PAGE).map((inv) => (
                                                        <div key={inv.id} className="flex items-center justify-between gap-3 rounded-lg border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900/80 px-3.5 py-2.5">
                                                            <div className="min-w-0">
                                                                <p className="text-sm font-bold text-slate-900 dark:text-white truncate">
                                                                    {inv.email || 'Open invite'} · {inv.role_name}
                                                                </p>
                                                                <p className="text-xs text-slate-500 dark:text-slate-400 truncate">
                                                                    Expires: {formatUTCToLocal(inv.expires_at)}
                                                                </p>
                                                            </div>
                                                            <span className={`text-[11px] font-extrabold px-2.5 py-1 rounded-full border ${inv.accepted_at
                                                                ? 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30'
                                                                : 'bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400 border-slate-200 dark:border-slate-700'
                                                                }`}>
                                                                {inv.accepted_at ? 'Accepted' : 'Pending'}
                                                            </span>
                                                        </div>
                                                    ))}

                                                    {invites.length > INVITES_PER_PAGE && (
                                                        <div className="flex items-center justify-between gap-2 pt-2 px-1">
                                                            <p className="text-[10px] font-bold text-slate-500 dark:text-slate-400 uppercase">
                                                                Page {invitesPage} of {Math.ceil(invites.length / INVITES_PER_PAGE)}
                                                            </p>
                                                            <div className="flex items-center gap-1.5">
                                                                <button
                                                                    type="button"
                                                                    disabled={invitesPage === 1}
                                                                    onClick={() => setInvitesPage(p => Math.max(1, p - 1))}
                                                                    className="px-2.5 py-1 text-xs font-bold bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-md hover:bg-slate-100 dark:hover:bg-slate-700 disabled:opacity-40 text-slate-800 dark:text-slate-200 transition-colors"
                                                                >
                                                                    Prev
                                                                </button>
                                                                <button
                                                                    type="button"
                                                                    disabled={invitesPage >= Math.ceil(invites.length / INVITES_PER_PAGE)}
                                                                    onClick={() => setInvitesPage(p => p + 1)}
                                                                    className="px-2.5 py-1 text-xs font-bold bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-md hover:bg-slate-100 dark:hover:bg-slate-700 disabled:opacity-40 text-slate-800 dark:text-slate-200 transition-colors"
                                                                >
                                                                    Next
                                                                </button>
                                                            </div>
                                                        </div>
                                                    )}
                                                </div>
                                            )}
                                        </div>
                                    </div>
                                </section>
                            </div>
                        </div>
                    ) : activeTab === 'users' ? (
                        <div className="p-5">
                            <div className="flex items-center justify-between mb-4">
                                <div className="flex items-center gap-2">
                                    <Users className="w-4 h-4 text-app-primary" />
                                    <h4 className="text-sm font-extrabold text-slate-900 dark:text-white tracking-wide uppercase">Organization Users</h4>
                                </div>
                                <button
                                    type="button"
                                    onClick={loadUsers}
                                    className="text-xs font-bold text-app-primary hover:text-blue-400 cursor-pointer"
                                >
                                    Refresh List
                                </button>
                            </div>

                            {usersLoading ? (
                                <div className="bg-slate-50 dark:bg-slate-900/60 rounded-xl border border-slate-200 dark:border-slate-800 p-8 flex flex-col items-center justify-center gap-3">
                                    <Loader2 className="w-6 h-6 animate-spin text-app-primary" />
                                    <p className="text-sm text-slate-500 dark:text-slate-400 font-medium">Loading organization users...</p>
                                </div>
                            ) : usersList.length === 0 ? (
                                <div className="bg-slate-50 dark:bg-slate-900/60 rounded-xl border border-slate-200 dark:border-slate-800 p-8 text-center">
                                    <p className="text-sm text-slate-500 dark:text-slate-400 font-medium">No users found in your organization.</p>
                                </div>
                            ) : (
                                <div className="space-y-3">
                                    <div className="overflow-hidden rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900/90">
                                        <table className="w-full text-left text-sm border-collapse">
                                            <thead>
                                                <tr className="bg-slate-50/80 dark:bg-slate-800/60 border-b border-slate-200 dark:border-slate-800 text-[11px] font-bold text-slate-600 dark:text-slate-400 uppercase tracking-widest">
                                                    <th className="px-4 py-3">User</th>
                                                    <th className="px-4 py-3">Role</th>
                                                    <th className="px-4 py-3">Last Login</th>
                                                    <th className="px-4 py-3 text-right">Status</th>
                                                </tr>
                                            </thead>
                                            <tbody className="divide-y divide-slate-200 dark:divide-slate-800">
                                                {usersList.slice((usersPage - 1) * USERS_PER_PAGE, usersPage * USERS_PER_PAGE).map((u) => (
                                                    <tr key={u.id} className="hover:bg-slate-50/80 dark:hover:bg-slate-800/40 transition-colors">
                                                        <td className="px-4 py-4">
                                                            <div className="flex flex-col">
                                                                <span className="font-bold text-slate-900 dark:text-white">
                                                                    {u.first_name || u.last_name ? `${u.first_name || ''} ${u.last_name || ''}`.trim() : 'Unnamed User'}
                                                                </span>
                                                                <span className="text-xs text-slate-500 dark:text-slate-400">{u.email}</span>
                                                            </div>
                                                        </td>
                                                        <td className="px-4 py-4">
                                                            <div className="flex items-center gap-2">
                                                                <span className={`px-2.5 py-0.5 rounded text-[10px] font-bold ${u.is_org_admin
                                                                    ? 'bg-blue-500/15 text-blue-400 border border-blue-500/30'
                                                                    : 'bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300 border border-slate-200 dark:border-slate-700'
                                                                    }`}>
                                                                    {u.role_name || 'No Role'}
                                                                </span>
                                                            </div>
                                                        </td>
                                                        <td className="px-4 py-4 text-slate-500 dark:text-slate-400 text-xs">
                                                            {u.last_login ? formatUTCToLocal(u.last_login) : 'Never'}
                                                        </td>
                                                        <td className="px-4 py-4 text-right">
                                                            <span className="inline-flex items-center gap-1.5 px-2 py-1 rounded-full bg-emerald-500/10 text-emerald-500 text-[10px] font-bold uppercase border border-emerald-500/20">
                                                                <span className="w-1 h-1 rounded-full bg-emerald-500 animate-pulse"></span>
                                                                Active
                                                            </span>
                                                        </td>
                                                    </tr>
                                                ))}
                                            </tbody>
                                        </table>
                                    </div>

                                    {usersList.length > USERS_PER_PAGE && (
                                        <div className="flex items-center justify-between gap-4 px-1 pt-2">
                                            <p className="text-xs font-bold text-slate-500 dark:text-slate-400 uppercase">
                                                Showing {(usersPage - 1) * USERS_PER_PAGE + 1}-{Math.min(usersPage * USERS_PER_PAGE, usersList.length)} of {usersList.length} users
                                            </p>
                                            <div className="flex items-center gap-2">
                                                <button
                                                    type="button"
                                                    disabled={usersPage === 1}
                                                    onClick={() => setUsersPage(p => Math.max(1, p - 1))}
                                                    className="inline-flex items-center px-3 py-1.5 rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-xs font-bold text-slate-800 dark:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-700 disabled:opacity-40 transition-colors"
                                                >
                                                    Previous
                                                </button>
                                                <button
                                                    type="button"
                                                    disabled={usersPage >= Math.ceil(usersList.length / USERS_PER_PAGE)}
                                                    onClick={() => setUsersPage(p => p + 1)}
                                                    className="inline-flex items-center px-3 py-1.5 rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-xs font-bold text-slate-800 dark:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-700 disabled:opacity-40 transition-colors"
                                                >
                                                    Next
                                                </button>
                                            </div>
                                        </div>
                                    )}
                                </div>
                            )}
                        </div>
                    ) : (
                        <div className="p-5">
                            <OrgTokenOpsPanel user={user} />
                        </div>
                    )}
                </section>
            </div>
        </main>
    );
}
