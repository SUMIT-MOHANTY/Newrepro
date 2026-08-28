import React, { useState, useEffect } from 'react';
import { 
    Coins, Building2, Shield, DollarSign, Activity, RefreshCw, 
    AlertCircle, CheckCircle2, Plus, Edit, Ban, Check, UserCheck, XCircle, Search
} from 'lucide-react';
import { API_ENDPOINTS } from '../config';

export default function SuperAdminTokenOps() {
    const [stats, setStats] = useState(null);
    const [organizations, setOrganizations] = useState([]);
    const [pricingList, setPricingList] = useState([]);
    const [paygRequests, setPaygRequests] = useState([]);
    const [quotaRequests, setQuotaRequests] = useState([]);
    const [loading, setLoading] = useState(true);
    const [actionLoading, setActionLoading] = useState(false);
    const [error, setError] = useState('');
    const [successMessage, setSuccessMessage] = useState('');
    const [toast, setToast] = useState(null); // { message: string, type: 'success' | 'error' }
    const [searchQuery, setSearchQuery] = useState('');
    const [activeTab, setActiveTab] = useState('wallets'); // 'wallets' | 'pricing' | 'requests'

    const showToast = (message, type = 'success') => {
        setToast({ message, type });
        setTimeout(() => {
            setToast((current) => current?.message === message ? null : current);
        }, 4500);
    };

    // Modals
    const [purchaseModal, setPurchaseModal] = useState({ open: false, orgName: '', amount: '', remarks: '' });
    const [pricingModal, setPricingModal] = useState({ open: false, modelName: '', price: '' });
    const [addModelModal, setAddModelModal] = useState({ open: false, modelName: '', price: '' });
    const [quotaDecisionModal, setQuotaDecisionModal] = useState({ open: false, request: null, approve: true, remarks: '' });
    const [graceModal, setGraceModal] = useState({ open: false, orgName: '', months: 3 });
    const [bulkGraceModal, setBulkGraceModal] = useState({ open: false, months: 3 });

    const formatCurrency = (amount, pricePerToken = 0.000007) => {
        return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format((amount || 0) * pricePerToken);
    };

    const getHeaders = () => {
        const token = localStorage.getItem('token');
        return {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json'
        };
    };

    const fetchData = async () => {
        setLoading(true);
        setError('');
        try {
            const headers = getHeaders();

            // 1. Fetch Global Overview KPIs
            try {
                const resStats = await fetch(API_ENDPOINTS.TOKENOPS_ADMIN_ANALYTICS, { headers });
                if (resStats.ok) {
                    const data = await resStats.json();
                    if (data.success && data.data) setStats(data.data);
                }
            } catch (e) {
                console.warn('Failed to load stats:', e);
            }

            // 2. Fetch Organizations
            try {
                const resOrgs = await fetch(API_ENDPOINTS.TOKENOPS_ADMIN_ORGS, { headers });
                if (resOrgs.ok) {
                    const data = await resOrgs.json();
                    if (data.success && data.data?.items) {
                        setOrganizations(data.data.items);
                    }
                }
            } catch (e) {
                console.warn('Failed to load orgs:', e);
            }

            // 3. Fetch Pricing
            try {
                const resPricing = await fetch(API_ENDPOINTS.TOKENOPS_ADMIN_PRICING, { headers });
                if (resPricing.ok) {
                    const data = await resPricing.json();
                    if (data.success && data.data) {
                        setPricingList(data.data);
                    }
                }
            } catch (e) {
                console.warn('Failed to load pricing:', e);
            }

            // 4. Fetch Quota Requests
            try {
                const resQuota = await fetch(API_ENDPOINTS.TOKENOPS_ADMIN_QUOTA_REQUESTS, { headers });
                if (resQuota.ok) {
                    const data = await resQuota.json();
                    if (data.success && data.data) {
                        setQuotaRequests(data.data);
                    }
                }
            } catch (e) {
                console.warn('Failed to load quota requests:', e);
            }
        } catch (err) {
            setError(err.message || 'Failed to load Super Admin TokenOps data.');
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchData();
    }, []);

    // Handle Quota Decision (Approve / Reject)
    const handleQuotaDecision = async (e) => {
        e.preventDefault();
        if (!quotaDecisionModal.request) return;
        setActionLoading(true);
        setError('');
        setSuccessMessage('');
        try {
            const req = quotaDecisionModal.request;
            const endpoint = quotaDecisionModal.approve
                ? API_ENDPOINTS.TOKENOPS_ADMIN_QUOTA_APPROVE(req.id)
                : API_ENDPOINTS.TOKENOPS_ADMIN_QUOTA_REJECT(req.id);

            const res = await fetch(endpoint, {
                method: 'POST',
                headers: getHeaders(),
                body: JSON.stringify({ remarks: quotaDecisionModal.remarks })
            });
            const data = await res.json();
            if (!res.ok || !data.success) {
                throw new Error(data.error?.message || 'Failed to process request');
            }
            const isApproved = quotaDecisionModal.approve;
            const successText = isApproved
                ? `🎉 Successfully approved ${req.request_type === 'TOKEN_INCREASE' ? `${Number(req.requested_tokens || 0).toLocaleString()} tokens for` : 'PAYG for'} ${req.organization_name}!`
                : `Request #${req.id} rejected.`;
            setSuccessMessage(successText);
            showToast(successText, isApproved ? 'success' : 'info');
            setQuotaDecisionModal({ open: false, request: null, approve: true, remarks: '' });
            fetchData();
        } catch (err) {
            setError(err.message);
            showToast(err.message || 'Failed to process request', 'error');
        } finally {
            setActionLoading(false);
        }
    };

    // Handle Purchase
    const handlePurchase = async (e) => {
        e.preventDefault();
        setActionLoading(true);
        setError('');
        setSuccessMessage('');
        try {
            const res = await fetch(API_ENDPOINTS.TOKENOPS_ADMIN_PURCHASE, {
                method: 'POST',
                headers: getHeaders(),
                body: JSON.stringify({
                    organization_name: purchaseModal.orgName,
                    token_amount: parseInt(purchaseModal.amount, 10),
                    remarks: purchaseModal.remarks
                })
            });
            const data = await res.json();
            if (!res.ok || !data.success) {
                throw new Error(data.error?.message || 'Failed to purchase tokens.');
            }
            const msg = `🎉 Successfully injected ${Number(purchaseModal.amount).toLocaleString()} tokens into ${purchaseModal.orgName}!`;
            setSuccessMessage(msg);
            showToast(msg, 'success');
            setPurchaseModal({ open: false, orgName: '', amount: '', remarks: '' });
            fetchData();
        } catch (err) {
            setError(err.message);
            showToast(err.message || 'Failed to inject tokens.', 'error');
        } finally {
            setActionLoading(false);
        }
    };

    // Handle Price Update
    const handlePriceUpdate = async (e) => {
        e.preventDefault();
        setActionLoading(true);
        setError('');
        setSuccessMessage('');
        try {
            const endpoint = typeof API_ENDPOINTS.TOKENOPS_ADMIN_PRICING_UPDATE === 'function'
                ? API_ENDPOINTS.TOKENOPS_ADMIN_PRICING_UPDATE(pricingModal.modelName)
                : `${API_ENDPOINTS.TOKENOPS_ADMIN_PRICING_UPDATE}/${encodeURIComponent(pricingModal.modelName)}`;

            const res = await fetch(endpoint, {
                method: 'PUT',
                headers: getHeaders(),
                body: JSON.stringify({
                    price_per_token: parseFloat(pricingModal.price)
                })
            });
            const data = await res.json();
            if (!res.ok || !data.success) {
                throw new Error(data.error?.message || 'Failed to update pricing.');
            }
            const msg = `✅ Pricing for ${pricingModal.modelName} updated to $${pricingModal.price} / token.`;
            setSuccessMessage(msg);
            showToast(msg, 'success');
            setPricingModal({ open: false, modelName: '', price: '' });
            fetchData();
        } catch (err) {
            setError(err.message);
            showToast(err.message || 'Failed to update pricing.', 'error');
        } finally {
            setActionLoading(false);
        }
    };

    // Handle Add Model
    const handleAddModel = async (e) => {
        e.preventDefault();
        setActionLoading(true);
        setError('');
        setSuccessMessage('');
        try {
            const res = await fetch(API_ENDPOINTS.TOKENOPS_ADMIN_PRICING_ADD, {
                method: 'POST',
                headers: getHeaders(),
                body: JSON.stringify({
                    model_name: addModelModal.modelName,
                    price_per_token: parseFloat(addModelModal.price)
                })
            });
            const data = await res.json();
            if (!res.ok || !data.success) {
                throw new Error(data.error?.message || 'Failed to add model pricing.');
            }
            const msg = `✅ Model ${addModelModal.modelName} registered successfully.`;
            setSuccessMessage(msg);
            showToast(msg, 'success');
            setAddModelModal({ open: false, modelName: '', price: '' });
            fetchData();
        } catch (err) {
            setError(err.message);
            showToast(err.message || 'Failed to add model pricing.', 'error');
        } finally {
            setActionLoading(false);
        }
    };

    // Handle Block/Unblock Org
    const handleToggleBlockOrg = async (orgName, currentBlocked) => {
        setActionLoading(true);
        setError('');
        try {
            const endpoint = currentBlocked
                ? API_ENDPOINTS.TOKENOPS_ADMIN_UNBLOCK_ORG
                : API_ENDPOINTS.TOKENOPS_ADMIN_BLOCK_ORG;
            const res = await fetch(endpoint, {
                method: 'POST',
                headers: getHeaders(),
                body: JSON.stringify({
                    organization_name: orgName
                })
            });
            const data = await res.json();
            if (!res.ok || !data.success) {
                throw new Error(data.error?.message || 'Failed to update org status.');
            }
            const msg = `Organization ${orgName} has been ${!currentBlocked ? 'blocked 🚫' : 'unblocked ✅'}.`;
            setSuccessMessage(msg);
            showToast(msg, !currentBlocked ? 'error' : 'success');
            fetchData();
        } catch (err) {
            setError(err.message);
            showToast(err.message || 'Failed to update org status.', 'error');
        } finally {
            setActionLoading(false);
        }
    };

    // Handle Set Grace Period
    const handleSetGracePeriod = async (e) => {
        e.preventDefault();
        setActionLoading(true);
        setError('');
        setSuccessMessage('');
        try {
            const res = await fetch(API_ENDPOINTS.TOKENOPS_ADMIN_GRACE_PERIOD, {
                method: 'POST',
                headers: getHeaders(),
                body: JSON.stringify({
                    organization_name: graceModal.orgName,
                    grace_period_months: parseInt(graceModal.months, 10)
                })
            });
            const data = await res.json();
            if (!res.ok || !data.success) {
                throw new Error(data.error?.message || 'Failed to update grace period.');
            }
            const msg = `🎉 Grace period of ${graceModal.months} month(s) set for ${graceModal.orgName}.`;
            setSuccessMessage(msg);
            showToast(msg, 'success');
            setGraceModal({ open: false, orgName: '', months: 3 });
            fetchData();
        } catch (err) {
            setError(err.message);
            showToast(err.message || 'Failed to update grace period.', 'error');
        } finally {
            setActionLoading(false);
        }
    };

    // Handle Bulk Set Grace Period
    const handleBulkSetGracePeriod = async (e) => {
        e.preventDefault();
        setActionLoading(true);
        setError('');
        setSuccessMessage('');
        try {
            const res = await fetch(API_ENDPOINTS.TOKENOPS_ADMIN_GRACE_PERIOD_BULK, {
                method: 'POST',
                headers: getHeaders(),
                body: JSON.stringify({
                    grace_period_months: parseInt(bulkGraceModal.months, 10)
                })
            });
            const data = await res.json();
            if (!res.ok || !data.success) {
                throw new Error(data.error?.message || 'Failed to apply bulk grace period.');
            }
            const msg = `🎉 Applied global grace period of ${bulkGraceModal.months} month(s) to all organizations (stored as setting for current and future PAYG transitions).`;
            setSuccessMessage(msg);
            showToast(msg, 'success');
            setBulkGraceModal({ open: false, months: 3 });
            fetchData();
        } catch (err) {
            setError(err.message);
            showToast(err.message || 'Failed to apply bulk grace period.', 'error');
        } finally {
            setActionLoading(false);
        }
    };

    const filteredOrgs = organizations.filter(o => 
        !searchQuery || o.organization_name.toLowerCase().includes(searchQuery.toLowerCase())
    );

    return (
        <div className="h-full overflow-y-auto custom-scrollbar p-4 sm:p-6 space-y-5 relative">
            {/* Floating Toast Notification */}
            {toast && (
                <div className="fixed top-6 right-6 z-[9999] max-w-md animate-in fade-in slide-in-from-top-4 duration-300 pointer-events-auto">
                    <div className={`flex items-center gap-3 px-4 py-3.5 rounded-2xl shadow-2xl border text-xs sm:text-sm font-medium ${
                        toast.type === 'success'
                            ? 'bg-emerald-600 text-white border-emerald-500 shadow-emerald-900/30'
                            : toast.type === 'error'
                            ? 'bg-rose-600 text-white border-rose-500 shadow-rose-900/30'
                            : 'bg-indigo-600 text-white border-indigo-500 shadow-indigo-900/30'
                    }`}>
                        {toast.type === 'success' ? (
                            <CheckCircle2 className="w-5 h-5 text-white shrink-0" />
                        ) : toast.type === 'error' ? (
                            <AlertCircle className="w-5 h-5 text-white shrink-0" />
                        ) : (
                            <Coins className="w-5 h-5 text-white shrink-0" />
                        )}
                        <span className="flex-1 font-semibold">{toast.message}</span>
                        <button
                            type="button"
                            onClick={() => setToast(null)}
                            className="text-white/80 hover:text-white hover:bg-white/20 rounded-lg p-1 transition cursor-pointer text-xs font-bold shrink-0"
                            aria-label="Dismiss notification"
                        >
                            ✕
                        </button>
                    </div>
                </div>
            )}

            {/* Header */}
            <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 bg-white dark:bg-slate-800 p-5 rounded-2xl border border-slate-200/80 dark:border-slate-700 shadow-sm">
                <div>
                    <h1 className="text-xl sm:text-2xl font-bold text-slate-900 dark:text-white flex items-center gap-2.5">
                        <Coins className="w-6 h-6 sm:w-7 sm:h-7 text-indigo-600 dark:text-indigo-400" />
                        TokenOps Super Admin Hub
                    </h1>
                    <p className="text-xs sm:text-sm text-slate-500 dark:text-slate-400 mt-1">
                        Global token management, organization quotas, model pricing, and PAYG governance.
                    </p>
                </div>
                <button 
                    onClick={fetchData} 
                    disabled={loading}
                    className="flex items-center gap-2 px-3.5 py-2 bg-slate-100 hover:bg-slate-200 dark:bg-slate-700 dark:hover:bg-slate-600 text-slate-700 dark:text-slate-200 rounded-xl transition text-xs font-semibold cursor-pointer shadow-sm"
                >
                    <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
                    <span>Refresh</span>
                </button>
            </div>

            {/* Alerts */}
            {error && (
                <div className="p-3.5 bg-rose-50 dark:bg-rose-950/40 border border-rose-200 dark:border-rose-800 rounded-xl flex items-center gap-2.5 text-rose-700 dark:text-rose-300 text-xs font-medium">
                    <AlertCircle className="w-4 h-4 flex-shrink-0" />
                    <span>{error}</span>
                </div>
            )}
            {successMessage && (
                <div className="p-3.5 bg-emerald-50 dark:bg-emerald-950/40 border border-emerald-200 dark:border-emerald-800 rounded-xl flex items-center gap-2.5 text-emerald-700 dark:text-emerald-300 text-xs font-medium">
                    <CheckCircle2 className="w-4 h-4 flex-shrink-0" />
                    <span>{successMessage}</span>
                </div>
            )}

            {/* Overview KPIs */}
            {stats && (
                <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
                    {/* Total Orgs */}
                    <div className="relative overflow-hidden bg-gradient-to-br from-white to-slate-50 dark:from-slate-800 dark:to-slate-850 p-3.5 rounded-xl border border-slate-250/60 dark:border-slate-700 shadow-sm hover:shadow-md hover:-translate-y-0.5 transition-all duration-200 flex items-center justify-between group">
                        <div className="min-w-0">
                            <span className="text-[10px] font-bold text-slate-400 dark:text-slate-500 uppercase tracking-wider block truncate">Total Orgs</span>
                            <div className="text-xl font-bold text-slate-850 dark:text-slate-100 mt-1">{stats.total_organizations}</div>
                        </div>
                        <div className="p-2 rounded-lg bg-slate-50 dark:bg-slate-700/50 text-slate-400 dark:text-slate-500 group-hover:bg-slate-100 dark:group-hover:bg-slate-700 transition-colors duration-200 shrink-0 ml-2">
                            <Building2 className="w-4 h-4" />
                        </div>
                    </div>

                    {/* Prepaid Orgs */}
                    <div className="relative overflow-hidden bg-gradient-to-br from-white to-indigo-50/10 dark:from-slate-800 dark:to-indigo-950/10 p-3.5 rounded-xl border border-indigo-100/50 dark:border-slate-700 shadow-sm hover:shadow-md hover:-translate-y-0.5 transition-all duration-200 flex items-center justify-between group">
                        <div className="min-w-0">
                            <span className="text-[10px] font-bold text-indigo-500 dark:text-indigo-400 uppercase tracking-wider block truncate">Prepaid Orgs</span>
                            <div className="text-xl font-bold text-indigo-700 dark:text-indigo-350 mt-1">{stats.prepaid_organizations}</div>
                        </div>
                        <div className="p-2 rounded-lg bg-indigo-50/50 dark:bg-indigo-950/30 text-indigo-600 dark:text-indigo-455 group-hover:bg-indigo-100/50 dark:group-hover:bg-indigo-900/30 transition-colors duration-200 shrink-0 ml-2">
                            <Coins className="w-4 h-4" />
                        </div>
                    </div>

                    {/* PAYG Orgs */}
                    <div className="relative overflow-hidden bg-gradient-to-br from-white to-amber-50/10 dark:from-slate-800 dark:to-amber-950/10 p-3.5 rounded-xl border border-amber-100/50 dark:border-slate-700 shadow-sm hover:shadow-md hover:-translate-y-0.5 transition-all duration-200 flex items-center justify-between group">
                        <div className="min-w-0">
                            <span className="text-[10px] font-bold text-amber-600 dark:text-amber-400 uppercase tracking-wider block truncate">PAYG Orgs</span>
                            <div className="text-xl font-bold text-amber-700 dark:text-amber-350 mt-1">{stats.payg_organizations}</div>
                        </div>
                        <div className="p-2 rounded-lg bg-amber-50/50 dark:bg-amber-950/30 text-amber-600 dark:text-amber-455 group-hover:bg-amber-100/50 dark:group-hover:bg-amber-900/30 transition-colors duration-200 shrink-0 ml-2">
                            <DollarSign className="w-4 h-4" />
                        </div>
                    </div>

                    {/* Blocked Orgs */}
                    <div className="relative overflow-hidden bg-gradient-to-br from-white to-rose-50/10 dark:from-slate-800 dark:to-rose-950/10 p-3.5 rounded-xl border border-rose-100/50 dark:border-slate-700 shadow-sm hover:shadow-md hover:-translate-y-0.5 transition-all duration-200 flex items-center justify-between group">
                        <div className="min-w-0">
                            <span className="text-[10px] font-bold text-rose-500 dark:text-rose-400 uppercase tracking-wider block truncate">Blocked Orgs</span>
                            <div className="text-xl font-bold text-rose-700 dark:text-rose-350 mt-1">{stats.blocked_organizations}</div>
                        </div>
                        <div className="p-2 rounded-lg bg-rose-50/50 dark:bg-rose-950/30 text-rose-600 dark:text-rose-455 group-hover:bg-rose-100/50 dark:group-hover:bg-rose-900/30 transition-colors duration-200 shrink-0 ml-2">
                            <Ban className="w-4 h-4" />
                        </div>
                    </div>

                    {/* Total Consumption Cost */}
                    <div className="relative overflow-hidden bg-gradient-to-br from-white to-emerald-50/10 dark:from-slate-800 dark:to-emerald-950/10 p-3.5 rounded-xl border border-emerald-100/50 dark:border-slate-700 shadow-sm hover:shadow-md hover:-translate-y-0.5 transition-all duration-200 flex items-center justify-between group">
                        <div className="min-w-0 flex-1">
                            <span className="text-[10px] font-bold text-emerald-600 dark:text-emerald-400 uppercase tracking-wider block truncate">Consumption Cost</span>
                            <div className="text-lg font-bold text-emerald-700 dark:text-emerald-350 mt-1 truncate">
                                {formatCurrency(stats.total_historical_cost, 1)}
                            </div>
                            <span className="text-[9px] text-slate-400 dark:text-slate-500 block truncate font-mono mt-0.5">
                                {Number(stats.total_tokens_consumed || 0).toLocaleString()} tokens
                            </span>
                        </div>
                        <div className="p-2 rounded-lg bg-emerald-50/50 dark:bg-emerald-950/30 text-emerald-600 dark:text-emerald-455 group-hover:bg-emerald-100/50 dark:group-hover:bg-emerald-900/30 transition-colors duration-200 shrink-0 ml-2">
                            <Activity className="w-4 h-4" />
                        </div>
                    </div>

                    {/* Total Requests */}
                    <div className="relative overflow-hidden bg-gradient-to-br from-white to-slate-50 dark:from-slate-800 dark:to-slate-850 p-3.5 rounded-xl border border-slate-250/60 dark:border-slate-700 shadow-sm hover:shadow-md hover:-translate-y-0.5 transition-all duration-200 flex items-center justify-between group">
                        <div className="min-w-0">
                            <span className="text-[10px] font-bold text-slate-400 dark:text-slate-500 uppercase tracking-wider block truncate">Total Requests</span>
                            <div className="text-xl font-bold text-slate-850 dark:text-slate-100 mt-1">{Number(stats.total_requests || 0).toLocaleString()}</div>
                        </div>
                        <div className="p-2 rounded-lg bg-slate-50 dark:bg-slate-700/50 text-slate-450 dark:text-slate-500 group-hover:bg-slate-100 dark:group-hover:bg-slate-700 transition-colors duration-200 shrink-0 ml-2">
                            <Activity className="w-4 h-4" />
                        </div>
                    </div>
                </div>
            )}

            {/* Navigation Tabs */}
            <div className="flex border-b border-slate-200 dark:border-slate-700 space-x-1 sm:space-x-2">
                <button
                    onClick={() => setActiveTab('wallets')}
                    className={`px-4 py-2.5 text-xs sm:text-sm font-semibold flex items-center gap-2 border-b-2 transition cursor-pointer ${
                        activeTab === 'wallets'
                            ? 'border-indigo-600 text-indigo-600 dark:text-indigo-400 dark:border-indigo-400'
                            : 'border-transparent text-slate-500 hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-200'
                    }`}
                >
                    <Building2 className="w-4 h-4" />
                    <span>Organization Wallets</span>
                    <span className="px-1.5 py-0.5 rounded-full text-[10px] bg-slate-100 dark:bg-slate-700 font-mono">
                        {organizations.length}
                    </span>
                </button>
                <button
                    onClick={() => setActiveTab('pricing')}
                    className={`px-4 py-2.5 text-xs sm:text-sm font-semibold flex items-center gap-2 border-b-2 transition cursor-pointer ${
                        activeTab === 'pricing'
                            ? 'border-indigo-600 text-indigo-600 dark:text-indigo-400 dark:border-indigo-400'
                            : 'border-transparent text-slate-500 hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-200'
                    }`}
                >
                    <DollarSign className="w-4 h-4" />
                    <span>Model Pricing</span>
                    <span className="px-1.5 py-0.5 rounded-full text-[10px] bg-slate-100 dark:bg-slate-700 font-mono">
                        {pricingList.length}
                    </span>
                </button>
                <button
                    onClick={() => setActiveTab('payg')}
                    className={`px-4 py-2.5 text-xs sm:text-sm font-semibold flex items-center gap-2 border-b-2 transition cursor-pointer ${
                        activeTab === 'payg'
                            ? 'border-indigo-600 text-indigo-600 dark:text-indigo-400 dark:border-indigo-400'
                            : 'border-transparent text-slate-500 hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-200'
                    }`}
                >
                    <Shield className="w-4 h-4" />
                    <span>Quota & PAYG Requests</span>
                    <span className="px-1.5 py-0.5 rounded-full text-[10px] bg-slate-100 dark:bg-slate-700 font-mono">
                        {quotaRequests.length}
                    </span>
                </button>
            </div>

            {/* TAB 1: Organization Wallets */}
            {activeTab === 'wallets' && (
                <div className="space-y-4">
                    <div className="flex justify-between items-center gap-4">
                        <div className="relative max-w-sm w-full">
                            <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
                            <input
                                type="text"
                                value={searchQuery}
                                onChange={(e) => setSearchQuery(e.target.value)}
                                placeholder="Search organizations..."
                                className="w-full pl-9 pr-4 py-2 text-xs sm:text-sm rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-900 dark:text-white shadow-sm focus:outline-none focus:ring-2 focus:ring-indigo-500/20"
                            />
                        </div>
                        <button
                            onClick={() => setBulkGraceModal({ open: true, months: 3 })}
                            className="px-3 py-2 bg-slate-100 hover:bg-slate-200 dark:bg-slate-700 dark:hover:bg-slate-600 text-slate-700 dark:text-slate-100 rounded-xl text-xs font-semibold flex items-center gap-1.5 transition border border-slate-200 dark:border-slate-600 shadow-sm cursor-pointer"
                            title="Apply a grace period rule to all organizations in bulk"
                        >
                            <Shield className="w-3.5 h-3.5" />
                            <span>Bulk Grace Period</span>
                        </button>
                    </div>

                    <div className="bg-white dark:bg-slate-800 rounded-xl border border-slate-200/80 dark:border-slate-700 overflow-hidden shadow-sm">
                        <div className="overflow-x-auto custom-scrollbar">
                            <table className="w-full text-left text-xs sm:text-sm">
                                <thead className="bg-slate-50 dark:bg-slate-750 text-slate-600 dark:text-slate-300 font-semibold border-b border-slate-200 dark:border-slate-700">
                                    <tr>
                                        <th className="px-4 py-3 min-w-[180px]">Organization</th>
                                        <th className="px-4 py-3 min-w-[120px]">Purchased Value</th>
                                        <th className="px-4 py-3 min-w-[120px]">Consumed Value</th>
                                        <th className="px-4 py-3 min-w-[120px]">Reserve Value</th>
                                        <th className="px-4 py-3 min-w-[120px]">Remaining Value</th>
                                        <th className="px-4 py-3 min-w-[120px]">Billing Mode</th>
                                        <th className="px-4 py-3 min-w-[170px]">PAYG Spend & Limits</th>
                                        <th className="px-4 py-3 min-w-[120px]">Grace Period</th>
                                        <th className="px-4 py-3 min-w-[90px]">Status</th>
                                        <th className="px-4 py-3 min-w-[180px] text-right">Actions</th>
                                    </tr>
                                </thead>
                                <tbody className="divide-y divide-slate-100 dark:divide-slate-700/60 text-slate-800 dark:text-slate-200">
                                    {filteredOrgs.length === 0 ? (
                                        <tr>
                                            <td colSpan="10" className="px-4 py-8 text-center text-slate-400">
                                                No organization wallets found.
                                            </td>
                                        </tr>
                                    ) : (
                                        filteredOrgs.map((org) => (
                                            <tr key={org.organization_name} className="hover:bg-indigo-50/30 dark:hover:bg-slate-700/30 transition-colors">
                                                <td className="px-4 py-3 font-semibold text-slate-900 dark:text-white flex items-center gap-2">
                                                    <Building2 className="w-4 h-4 text-slate-400 shrink-0" />
                                                    <span className="truncate">{org.organization_name}</span>
                                                </td>
                                                <td className="px-4 py-3">
                                                    <div className="font-semibold text-slate-900 dark:text-white">{formatCurrency(org.purchased_tokens, org.reference_price)}</div>
                                                    <div className="text-[10px] text-slate-500 font-mono mt-0.5">{Number(org.purchased_tokens || 0).toLocaleString()} tokens</div>
                                                </td>
                                                <td className="px-4 py-3">
                                                    <div className="font-semibold text-rose-600 dark:text-rose-400">{formatCurrency(org.consumed_tokens, org.reference_price)}</div>
                                                    <div className="text-[10px] text-slate-500 font-mono mt-0.5">{Number(org.consumed_tokens || 0).toLocaleString()} tokens</div>
                                                </td>
                                                <td className="px-4 py-3">
                                                    <div className="font-semibold text-indigo-600 dark:text-indigo-400">{formatCurrency(org.reserved_tokens, org.reference_price)}</div>
                                                    <div className="text-[10px] text-slate-500 font-mono mt-0.5">{Number(org.reserved_tokens || 0).toLocaleString()} tokens</div>
                                                </td>
                                                <td className="px-4 py-3">
                                                    <div className="font-bold text-emerald-600 dark:text-emerald-400">{formatCurrency(org.remaining_tokens, org.reference_price)}</div>
                                                    <div className="text-[10px] text-slate-500 font-mono mt-0.5">{Number(org.remaining_tokens || 0).toLocaleString()} tokens</div>
                                                </td>
                                                <td className="px-4 py-3">
                                                    {org.payg_enabled ? (
                                                        <span className="px-2 py-0.5 text-[11px] font-semibold rounded-full bg-amber-50 text-amber-700 border border-amber-200 dark:bg-amber-950/40 dark:text-amber-300 dark:border-amber-800">
                                                            PAYG Post-Paid
                                                        </span>
                                                    ) : (
                                                        <span className="px-2 py-0.5 text-[11px] font-semibold rounded-full bg-indigo-50 text-indigo-700 border border-indigo-200 dark:bg-indigo-950/40 dark:text-indigo-300 dark:border-indigo-800">
                                                            Prepaid
                                                        </span>
                                                    )}
                                                </td>
                                                <td className="px-4 py-3 min-w-[170px]">
                                                    {org.payg_enabled ? (
                                                        <div className="space-y-1">
                                                            <div className="flex items-center justify-between text-[11px]">
                                                                <span className="text-slate-500">Spend:</span>
                                                                <span className="font-bold text-amber-600 dark:text-amber-400 font-mono">
                                                                    ${Number(org.payg_current_spend_usd || 0).toFixed(2)}
                                                                    {Number(org.payg_reserved_spend_usd || 0) > 0 && (
                                                                        <span className="text-[10px] text-slate-400 ml-1">(+${Number(org.payg_reserved_spend_usd).toFixed(2)} res)</span>
                                                                    )}
                                                                </span>
                                                            </div>
                                                            <div className="flex items-center justify-between text-[10px] text-slate-500">
                                                                <span>Limits (S/H):</span>
                                                                <span className="font-mono">
                                                                    {org.payg_soft_limit_usd ? `$${Number(org.payg_soft_limit_usd).toFixed(0)}` : '∞'} / {org.payg_hard_limit_usd ? `$${Number(org.payg_hard_limit_usd).toFixed(0)}` : '∞'}
                                                                </span>
                                                            </div>
                                                            {org.payg_billing_email && (
                                                                <div className="text-[10px] text-slate-400 truncate max-w-[160px]" title={org.payg_billing_email}>
                                                                    ✉️ {org.payg_billing_email}
                                                                </div>
                                                            )}
                                                        </div>
                                                    ) : (
                                                        <span className="text-slate-400 dark:text-slate-500 text-xs">N/A (Prepaid)</span>
                                                    )}
                                                </td>
                                                <td className="px-4 py-3">
                                                    {org.payg_enabled ? (
                                                        <div className="flex items-center gap-1.5">
                                                            <span className="font-semibold text-slate-800 dark:text-slate-200">
                                                                {org.payg_grace_period_months} month{org.payg_grace_period_months > 1 ? 's' : ''}
                                                            </span>
                                                            <button
                                                                onClick={() => setGraceModal({ open: true, orgName: org.organization_name, months: org.payg_grace_period_months || 3 })}
                                                                className="p-1 hover:bg-slate-100 dark:hover:bg-slate-700 text-slate-400 hover:text-indigo-600 rounded transition cursor-pointer"
                                                                title="Edit Grace Period"
                                                            >
                                                                <Edit className="w-3.5 h-3.5" />
                                                            </button>
                                                        </div>
                                                    ) : (
                                                        <span className="text-slate-400 dark:text-slate-500 font-medium">N/A (Prepaid)</span>
                                                    )}
                                                </td>
                                                <td className="px-4 py-3">
                                                    {org.is_blocked ? (
                                                        <span className="px-2 py-0.5 text-[11px] font-semibold rounded-full bg-rose-50 text-rose-700 border border-rose-200 dark:bg-rose-950/40 dark:text-rose-300 dark:border-rose-800">
                                                            Blocked
                                                        </span>
                                                    ) : (
                                                        <span className="px-2 py-0.5 text-[11px] font-semibold rounded-full bg-emerald-50 text-emerald-700 border border-emerald-200 dark:bg-emerald-950/40 dark:text-emerald-300 dark:border-emerald-800">
                                                            Active
                                                        </span>
                                                    )}
                                                </td>
                                                <td className="px-4 py-3 text-right whitespace-nowrap">
                                                    <div className="flex items-center justify-end gap-1.5">
                                                        <button
                                                            onClick={() => setPurchaseModal({ open: true, orgName: org.organization_name, amount: '', remarks: '' })}
                                                            className="px-2.5 py-1.5 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg text-xs font-semibold inline-flex items-center gap-1 transition shadow-sm shrink-0 cursor-pointer"
                                                            title="Inject / Credit tokens to this organization"
                                                        >
                                                            <Plus className="w-3.5 h-3.5" />
                                                            <span>Inject Tokens</span>
                                                        </button>
                                                        <button
                                                            onClick={() => handleToggleBlockOrg(org.organization_name, org.is_blocked)}
                                                            className={`px-2.5 py-1.5 rounded-lg text-xs font-semibold inline-flex items-center gap-1 transition border shrink-0 cursor-pointer ${
                                                                org.is_blocked
                                                                    ? 'bg-emerald-50 hover:bg-emerald-100 text-emerald-700 border-emerald-300 dark:bg-emerald-950/60 dark:text-emerald-300 dark:border-emerald-800'
                                                                    : 'bg-rose-50 hover:bg-rose-100 text-rose-700 border-rose-200 dark:bg-rose-950/60 dark:text-rose-300 dark:border-rose-800'
                                                            }`}
                                                        >
                                                            {org.is_blocked ? <Check className="w-3.5 h-3.5" /> : <Ban className="w-3.5 h-3.5" />}
                                                            <span>{org.is_blocked ? 'Unblock' : 'Block'}</span>
                                                        </button>
                                                    </div>
                                                </td>
                                            </tr>
                                        ))
                                    )}
                                </tbody>
                            </table>
                        </div>
                    </div>
                </div>
            )}

            {/* TAB 2: Model Pricing Configuration */}
            {activeTab === 'pricing' && (
                <div className="space-y-4">
                    <div className="flex justify-between items-center">
                        <p className="text-xs sm:text-sm text-slate-500 dark:text-slate-400">
                            Configure cost per token rates across active and legacy AI models.
                        </p>
                        <button
                            onClick={() => setAddModelModal({ open: true, modelName: '', price: '' })}
                            className="px-3.5 py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-xl text-xs font-semibold flex items-center gap-1.5 transition shadow-sm cursor-pointer"
                        >
                            <Plus className="w-4 h-4" />
                            <span>Register Model</span>
                        </button>
                    </div>

                    <div className="bg-white dark:bg-slate-800 rounded-xl border border-slate-200/80 dark:border-slate-700 overflow-hidden shadow-sm">
                        <div className="overflow-x-auto custom-scrollbar">
                            <table className="w-full text-left text-xs sm:text-sm">
                                <thead className="bg-slate-50 dark:bg-slate-750 text-slate-600 dark:text-slate-300 font-semibold border-b border-slate-200 dark:border-slate-700">
                                    <tr>
                                        <th className="px-4 py-3 min-w-[180px]">Model Name</th>
                                        <th className="px-4 py-3 min-w-[140px]">Price Per Token (USD)</th>
                                        <th className="px-4 py-3 min-w-[140px]">Price Per 1M Tokens</th>
                                        <th className="px-4 py-3 min-w-[100px]">Active Status</th>
                                        <th className="px-4 py-3 min-w-[120px] text-right">Actions</th>
                                    </tr>
                                </thead>
                                <tbody className="divide-y divide-slate-100 dark:divide-slate-700/60 text-slate-800 dark:text-slate-200">
                                    {pricingList.length === 0 ? (
                                        <tr>
                                            <td colSpan="5" className="px-4 py-8 text-center text-slate-400">
                                                No pricing models registered. Click "Register Model" to add your first AI model.
                                            </td>
                                        </tr>
                                    ) : (
                                        pricingList.map((p) => (
                                            <tr key={p.model_name} className="hover:bg-indigo-50/30 dark:hover:bg-slate-700/30 transition-colors">
                                                <td className="px-4 py-3 font-bold text-slate-900 dark:text-white">{p.model_name}</td>
                                                <td className="px-4 py-3 font-mono">${p.price_per_token.toFixed(8)}</td>
                                                <td className="px-4 py-3 font-mono font-semibold text-indigo-600 dark:text-indigo-400">
                                                    ${(p.price_per_token * 1000000).toFixed(2)}
                                                </td>
                                                <td className="px-4 py-3">
                                                    {p.is_active ? (
                                                        <span className="px-2 py-0.5 text-[11px] font-semibold rounded-full bg-emerald-50 text-emerald-700 border border-emerald-200 dark:bg-emerald-950/40 dark:text-emerald-300 dark:border-emerald-800">
                                                            Active
                                                        </span>
                                                    ) : (
                                                        <span className="px-2 py-0.5 text-[11px] font-semibold rounded-full bg-slate-100 text-slate-600 border border-slate-200 dark:bg-slate-700 dark:text-slate-400 dark:border-slate-600">
                                                            Inactive
                                                        </span>
                                                    )}
                                                </td>
                                                <td className="px-4 py-3 text-right whitespace-nowrap">
                                                    <button
                                                        onClick={() => setPricingModal({ open: true, modelName: p.model_name, price: p.price_per_token.toString() })}
                                                        className="px-2.5 py-1.5 bg-slate-100 hover:bg-slate-200 dark:bg-slate-700 dark:hover:bg-slate-600 text-slate-700 dark:text-slate-200 rounded-lg text-xs font-semibold inline-flex items-center gap-1 transition cursor-pointer"
                                                    >
                                                        <Edit className="w-3.5 h-3.5" />
                                                        <span>Edit Rate</span>
                                                    </button>
                                                </td>
                                            </tr>
                                        ))
                                    )}
                                </tbody>
                            </table>
                        </div>
                    </div>
                </div>
            )}

            {/* TAB 3: Quota & PAYG Requests Queue */}
            {activeTab === 'payg' && (
                <div className="bg-white dark:bg-slate-800 rounded-xl border border-slate-200/80 dark:border-slate-700 overflow-hidden shadow-sm">
                    <div className="p-4 border-b border-slate-200 dark:border-slate-700 bg-slate-50/50 dark:bg-slate-800/50 flex items-center justify-between">
                        <div>
                            <h3 className="text-sm font-bold text-slate-900 dark:text-white">Organization Quota & PAYG Requests</h3>
                            <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">Review and approve token increases and PAYG enablement requests submitted by Org Admins.</p>
                        </div>
                        <button
                            onClick={fetchData}
                            className="px-3 py-1.5 text-xs font-semibold bg-white dark:bg-slate-700 border border-slate-200 dark:border-slate-600 rounded-lg hover:bg-slate-50 dark:hover:bg-slate-600 inline-flex items-center gap-1 text-slate-700 dark:text-slate-200 shadow-sm cursor-pointer"
                        >
                            <RefreshCw className="w-3.5 h-3.5" />
                            <span>Refresh</span>
                        </button>
                    </div>
                    <div className="overflow-x-auto custom-scrollbar">
                        <table className="w-full text-left text-xs sm:text-sm">
                            <thead className="bg-slate-50 dark:bg-slate-750 text-slate-600 dark:text-slate-300 font-semibold border-b border-slate-200 dark:border-slate-700">
                                <tr>
                                    <th className="px-4 py-3 min-w-[70px]">Req #</th>
                                    <th className="px-4 py-3 min-w-[160px]">Organization</th>
                                    <th className="px-4 py-3 min-w-[130px]">Request Type</th>
                                    <th className="px-4 py-3 min-w-[120px]">Requested Quota</th>
                                    <th className="px-4 py-3 min-w-[100px]">Requester</th>
                                    <th className="px-4 py-3 min-w-[180px]">Reason / Remarks</th>
                                    <th className="px-4 py-3 min-w-[100px]">Status</th>
                                    <th className="px-4 py-3 min-w-[170px] text-right">Actions</th>
                                </tr>
                            </thead>
                            <tbody className="divide-y divide-slate-100 dark:divide-slate-700/60 text-slate-800 dark:text-slate-200">
                                {quotaRequests.length === 0 ? (
                                    <tr>
                                        <td colSpan="8" className="px-4 py-8 text-center text-slate-400">
                                            No quota or PAYG requests found.
                                        </td>
                                    </tr>
                                ) : (
                                    quotaRequests.map((req) => (
                                        <tr key={req.id} className="hover:bg-indigo-50/30 dark:hover:bg-slate-700/30 transition-colors">
                                            <td className="px-4 py-3 font-mono font-semibold">#{req.id}</td>
                                            <td className="px-4 py-3 font-bold text-slate-900 dark:text-white flex items-center gap-1.5">
                                                <Building2 className="w-3.5 h-3.5 text-slate-400 shrink-0" />
                                                <span className="truncate">{req.organization_name}</span>
                                            </td>
                                            <td className="px-4 py-3">
                                                <span className={`px-2 py-0.5 text-[11px] font-semibold rounded-full border ${
                                                    req.request_type === 'TOKEN_INCREASE'
                                                        ? 'bg-indigo-50 text-indigo-700 border-indigo-200 dark:bg-indigo-950/40 dark:text-indigo-300 dark:border-indigo-800'
                                                        : 'bg-amber-50 text-amber-700 border-amber-200 dark:bg-amber-950/40 dark:text-amber-300 dark:border-amber-800'
                                                }`}>
                                                    {req.request_type === 'TOKEN_INCREASE' ? 'Token Increase' : 'PAYG Enable'}
                                                </span>
                                            </td>
                                            <td className="px-4 py-3 font-mono font-bold text-indigo-600 dark:text-indigo-400">
                                                {req.request_type === 'TOKEN_INCREASE'
                                                    ? `+${Number(req.requested_tokens || 0).toLocaleString()} tokens`
                                                    : 'Unlimited PAYG'
                                                }
                                            </td>
                                            <td className="px-4 py-3 text-slate-500 dark:text-slate-400 text-xs">User #{req.requested_by}</td>
                                            <td className="px-4 py-3 text-slate-600 dark:text-slate-300 text-xs max-w-xs truncate" title={req.remarks || ''}>
                                                {req.remarks || <span className="text-slate-400 italic">None provided</span>}
                                            </td>
                                            <td className="px-4 py-3">
                                                <span className={`px-2 py-0.5 text-[11px] font-semibold rounded-full border ${
                                                    req.status === 'APPROVED'
                                                        ? 'bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-950/40 dark:text-emerald-300 dark:border-emerald-800'
                                                        : req.status === 'REJECTED'
                                                        ? 'bg-rose-50 text-rose-700 border-rose-200 dark:bg-rose-950/40 dark:text-rose-300 dark:border-rose-800'
                                                        : 'bg-amber-50 text-amber-700 border-amber-200 dark:bg-amber-950/40 dark:text-amber-300 dark:border-amber-800'
                                                }`}>
                                                    {req.status}
                                                </span>
                                            </td>
                                            <td className="px-4 py-3 text-right whitespace-nowrap">
                                                {req.status === 'REQUESTED' ? (
                                                    <div className="flex items-center justify-end gap-1.5">
                                                        <button
                                                            onClick={() => setQuotaDecisionModal({ open: true, request: req, approve: true, remarks: '' })}
                                                            className="px-2.5 py-1.5 bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg text-xs font-semibold inline-flex items-center gap-1 transition shadow-sm cursor-pointer"
                                                        >
                                                            <UserCheck className="w-3.5 h-3.5" />
                                                            <span>Approve</span>
                                                        </button>
                                                        <button
                                                            onClick={() => setQuotaDecisionModal({ open: true, request: req, approve: false, remarks: '' })}
                                                            className="px-2.5 py-1.5 bg-rose-600 hover:bg-rose-700 text-white rounded-lg text-xs font-semibold inline-flex items-center gap-1 transition shadow-sm cursor-pointer"
                                                        >
                                                            <XCircle className="w-3.5 h-3.5" />
                                                            <span>Reject</span>
                                                        </button>
                                                    </div>
                                                ) : (
                                                    <span className="text-xs text-slate-400 font-mono">Completed</span>
                                                )}
                                            </td>
                                        </tr>
                                    ))
                                )}
                            </tbody>
                        </table>
                    </div>
                </div>
            )}

            {/* MODAL 1: Purchase / Inject Tokens Modal */}
            {purchaseModal.open && (
                <div className="fixed inset-0 bg-black/50 backdrop-blur-sm z-50 flex items-center justify-center p-4">
                    <div className="bg-white dark:bg-slate-800 rounded-2xl max-w-md w-full p-6 border border-slate-200 dark:border-slate-700 shadow-2xl">
                        <h3 className="text-lg font-bold text-slate-900 dark:text-white mb-2">
                            Inject / Increase Tokens: {purchaseModal.orgName}
                        </h3>
                        <p className="text-sm text-slate-500 mb-4">
                            Credit token quota directly to the organization's reserve balance.
                        </p>
                        <form onSubmit={handlePurchase} className="space-y-4">
                            <div>
                                <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                                    Token Amount (Input & Output total)
                                </label>
                                <input
                                    type="number"
                                    min="1"
                                    required
                                    value={purchaseModal.amount}
                                    onChange={(e) => setPurchaseModal({ ...purchaseModal, amount: e.target.value })}
                                    placeholder="e.g. 500000"
                                    className="w-full px-4 py-2 rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900 text-slate-900 dark:text-white font-mono"
                                />
                            </div>
                            <div>
                                <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                                    Invoice / Purchase Remarks
                                </label>
                                <input
                                    type="text"
                                    value={purchaseModal.remarks}
                                    onChange={(e) => setPurchaseModal({ ...purchaseModal, remarks: e.target.value })}
                                    placeholder="e.g. Manual Super Admin Quota Grant"
                                    className="w-full px-4 py-2 rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900 text-slate-900 dark:text-white"
                                />
                            </div>
                            <div className="flex justify-end gap-3 mt-6">
                                <button
                                    type="button"
                                    onClick={() => setPurchaseModal({ open: false, orgName: '', amount: '', remarks: '' })}
                                    className="px-4 py-2 text-sm text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-700 rounded-xl"
                                >
                                    Cancel
                                </button>
                                <button
                                    type="submit"
                                    disabled={actionLoading}
                                    className="px-4 py-2 text-sm font-semibold bg-indigo-600 hover:bg-indigo-700 text-white rounded-xl"
                                >
                                    {actionLoading ? 'Processing...' : 'Confirm Injection'}
                                </button>
                            </div>
                        </form>
                    </div>
                </div>
            )}

            {/* MODAL 2: Edit Pricing Modal */}
            {pricingModal.open && (
                <div className="fixed inset-0 bg-black/50 backdrop-blur-sm z-50 flex items-center justify-center p-4">
                    <div className="bg-white dark:bg-slate-800 rounded-2xl max-w-md w-full p-6 border border-slate-200 dark:border-slate-700 shadow-2xl">
                        <h3 className="text-lg font-bold text-slate-900 dark:text-white mb-2">
                            Update Model Pricing
                        </h3>
                        <p className="text-sm text-slate-500 mb-4">
                            Update price per token for model: <span className="font-semibold text-slate-700 dark:text-slate-300">{pricingModal.modelName}</span>
                        </p>
                        <form onSubmit={handlePriceUpdate} className="space-y-4">
                            <div>
                                <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                                    Price Per Token (USD)
                                </label>
                                <input
                                    type="number"
                                    step="0.00000001"
                                    min="0"
                                    required
                                    value={pricingModal.price}
                                    onChange={(e) => setPricingModal({ ...pricingModal, price: e.target.value })}
                                    placeholder="0.000007"
                                    className="w-full px-4 py-2 rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900 text-slate-900 dark:text-white font-mono"
                                />
                            </div>
                            <div className="flex justify-end gap-3 mt-6">
                                <button
                                    type="button"
                                    onClick={() => setPricingModal({ open: false, modelName: '', price: '' })}
                                    className="px-4 py-2 text-sm text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-700 rounded-xl"
                                >
                                    Cancel
                                </button>
                                <button
                                    type="submit"
                                    disabled={actionLoading}
                                    className="px-4 py-2 text-sm font-semibold bg-indigo-600 hover:bg-indigo-700 text-white rounded-xl"
                                >
                                    {actionLoading ? 'Updating...' : 'Save Pricing'}
                                </button>
                            </div>
                        </form>
                    </div>
                </div>
            )}

            {/* MODAL 3: Add Model Modal */}
            {addModelModal.open && (
                <div className="fixed inset-0 bg-black/50 backdrop-blur-sm z-50 flex items-center justify-center p-4">
                    <div className="bg-white dark:bg-slate-800 rounded-2xl max-w-md w-full p-6 border border-slate-200 dark:border-slate-700 shadow-2xl">
                        <h3 className="text-lg font-bold text-slate-900 dark:text-white mb-2">
                            Register New Model
                        </h3>
                        <p className="text-sm text-slate-500 mb-4">
                            Add a custom model identifier and initial price rate.
                        </p>
                        <form onSubmit={handleAddModel} className="space-y-4">
                            <div>
                                <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                                    Model Name
                                </label>
                                <input
                                    type="text"
                                    required
                                    value={addModelModal.modelName}
                                    onChange={(e) => setAddModelModal({ ...addModelModal, modelName: e.target.value })}
                                    placeholder="e.g. claude-3-7-sonnet"
                                    className="w-full px-4 py-2 rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900 text-slate-900 dark:text-white"
                                />
                            </div>
                            <div>
                                <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                                    Price Per Token (USD)
                                </label>
                                <input
                                    type="number"
                                    step="0.00000001"
                                    min="0"
                                    required
                                    value={addModelModal.price}
                                    onChange={(e) => setAddModelModal({ ...addModelModal, price: e.target.value })}
                                    placeholder="0.000007"
                                    className="w-full px-4 py-2 rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900 text-slate-900 dark:text-white font-mono"
                                />
                            </div>
                            <div className="flex justify-end gap-3 mt-6">
                                <button
                                    type="button"
                                    onClick={() => setAddModelModal({ open: false, modelName: '', price: '' })}
                                    className="px-4 py-2 text-sm text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-700 rounded-xl"
                                >
                                    Cancel
                                </button>
                                <button
                                    type="submit"
                                    disabled={actionLoading}
                                    className="px-4 py-2 text-sm font-semibold bg-indigo-600 hover:bg-indigo-700 text-white rounded-xl"
                                >
                                    {actionLoading ? 'Registering...' : 'Register Model'}
                                </button>
                            </div>
                        </form>
                    </div>
                </div>
            )}

            {/* MODAL 4: Quota & PAYG Decision Modal */}
            {quotaDecisionModal.open && quotaDecisionModal.request && (
                <div className="fixed inset-0 bg-black/50 backdrop-blur-sm z-50 flex items-center justify-center p-4">
                    <div className="bg-white dark:bg-slate-800 rounded-2xl max-w-md w-full p-6 border border-slate-200 dark:border-slate-700 shadow-2xl">
                        <h3 className="text-lg font-bold text-slate-900 dark:text-white mb-2">
                            {quotaDecisionModal.approve ? 'Approve Request' : 'Reject Request'}
                        </h3>
                        <div className="bg-slate-50 dark:bg-slate-900/50 p-4 rounded-xl mb-4 border border-slate-200 dark:border-slate-700 space-y-1 text-xs">
                            <div><span className="font-semibold text-slate-500">Organization:</span> <span className="font-bold text-slate-800 dark:text-slate-200">{quotaDecisionModal.request.organization_name}</span></div>
                            <div><span className="font-semibold text-slate-500">Type:</span> <span className="font-bold">{quotaDecisionModal.request.request_type}</span></div>
                            {quotaDecisionModal.request.request_type === 'TOKEN_INCREASE' && (
                                <div><span className="font-semibold text-slate-500">Tokens:</span> <span className="font-mono text-indigo-600 dark:text-indigo-400 font-bold">+{Number(quotaDecisionModal.request.requested_tokens || 0).toLocaleString()}</span></div>
                            )}
                            {quotaDecisionModal.request.remarks && (
                                <div className="pt-1"><span className="font-semibold text-slate-500">Org Reason:</span> <em>"{quotaDecisionModal.request.remarks}"</em></div>
                            )}
                        </div>
                        <form onSubmit={handleQuotaDecision} className="space-y-4">
                            <div>
                                <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                                    Super Admin Decision Remarks
                                </label>
                                <input
                                    type="text"
                                    value={quotaDecisionModal.remarks}
                                    onChange={(e) => setQuotaDecisionModal({ ...quotaDecisionModal, remarks: e.target.value })}
                                    placeholder="e.g. Approved per Q3 expansion plan"
                                    className="w-full px-4 py-2 rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900 text-slate-900 dark:text-white"
                                />
                            </div>
                            <div className="flex justify-end gap-3 mt-6">
                                <button
                                    type="button"
                                    onClick={() => setQuotaDecisionModal({ open: false, request: null, approve: true, remarks: '' })}
                                    className="px-4 py-2 text-sm text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-700 rounded-xl"
                                >
                                    Cancel
                                </button>
                                <button
                                    type="submit"
                                    disabled={actionLoading}
                                    className={`px-4 py-2 text-sm font-semibold text-white rounded-xl ${
                                        quotaDecisionModal.approve ? 'bg-emerald-600 hover:bg-emerald-700' : 'bg-rose-600 hover:bg-rose-700'
                                    }`}
                                >
                                    {actionLoading ? 'Processing...' : (quotaDecisionModal.approve ? 'Confirm Approval' : 'Confirm Rejection')}
                                </button>
                            </div>
                        </form>
                    </div>
                </div>
            )}

            {/* MODAL 5: Set Grace Period Modal */}
            {graceModal.open && (
                <div className="fixed inset-0 bg-slate-900/60 backdrop-blur-sm z-50 flex items-center justify-center p-4">
                    <div className="bg-white dark:bg-slate-800 rounded-2xl max-w-md w-full p-6 border border-slate-200/80 dark:border-slate-700 shadow-2xl animate-in zoom-in-95 duration-200">
                        <div className="flex items-center gap-3 mb-3">
                            <div className="p-2.5 rounded-xl bg-indigo-50 dark:bg-indigo-950/40 text-indigo-600 dark:text-indigo-400">
                                <Shield className="w-5 h-5" />
                            </div>
                            <div>
                                <h3 className="text-lg font-bold text-slate-900 dark:text-white">
                                    Set PAYG Grace Period
                                </h3>
                                <p className="text-xs text-slate-500 dark:text-slate-400">
                                    Define maximum months overdue allowed before suspension.
                                </p>
                            </div>
                        </div>

                        <p className="text-sm text-slate-600 dark:text-slate-350 mb-5 leading-relaxed">
                            Configure allowed overdue period for organization: <span className="font-bold text-indigo-600 dark:text-indigo-400">{graceModal.orgName}</span>.
                        </p>

                        <form onSubmit={handleSetGracePeriod} className="space-y-4">
                            <div>
                                <label className="block text-[11px] font-bold text-slate-400 dark:text-slate-500 uppercase tracking-wider mb-2">
                                    Grace Period (Months)
                                </label>
                                <input
                                    type="number"
                                    min="1"
                                    max="24"
                                    required
                                    value={graceModal.months}
                                    onChange={(e) => setGraceModal({ ...graceModal, months: e.target.value })}
                                    className="w-full px-4 py-2.5 rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900 text-slate-900 dark:text-white font-mono text-sm focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500 outline-none transition duration-155"
                                />
                            </div>
                            <div className="flex justify-end gap-3 pt-2">
                                <button
                                    type="button"
                                    onClick={() => setGraceModal({ open: false, orgName: '', months: 3 })}
                                    className="px-4 py-2 text-xs sm:text-sm font-semibold text-slate-550 hover:bg-slate-50 dark:hover:bg-slate-700/50 rounded-xl transition cursor-pointer"
                                >
                                    Cancel
                                </button>
                                <button
                                    type="submit"
                                    disabled={actionLoading}
                                    className="px-4.5 py-2 text-xs sm:text-sm font-semibold bg-indigo-600 hover:bg-indigo-700 text-white rounded-xl transition shadow-md shadow-indigo-600/10 cursor-pointer"
                                >
                                    {actionLoading ? 'Saving...' : 'Save Settings'}
                                </button>
                            </div>
                        </form>
                    </div>
                </div>
            )}

            {/* MODAL 6: Bulk Set Grace Period Modal */}
            {bulkGraceModal.open && (
                <div className="fixed inset-0 bg-slate-900/60 backdrop-blur-sm z-50 flex items-center justify-center p-4">
                    <div className="bg-white dark:bg-slate-800 rounded-2xl max-w-md w-full p-6 border border-slate-200/80 dark:border-slate-700 shadow-2xl animate-in zoom-in-95 duration-200">
                        <div className="flex items-center gap-3 mb-3">
                            <div className="p-2.5 rounded-xl bg-amber-50 dark:bg-amber-950/30 text-amber-600 dark:text-amber-400">
                                <Shield className="w-5 h-5" />
                            </div>
                            <div>
                                <h3 className="text-lg font-bold text-slate-900 dark:text-white">
                                    Bulk Set PAYG Grace Period
                                </h3>
                                <p className="text-xs text-slate-500 dark:text-slate-400">
                                    Set global overdue threshold for all tenants.
                                </p>
                            </div>
                        </div>

                        <div className="bg-amber-50 dark:bg-amber-950/20 border border-amber-200/85 dark:border-amber-900/60 rounded-xl p-3.5 flex items-start gap-2.5 mb-5 text-amber-800 dark:text-amber-300">
                            <AlertCircle className="w-5 h-5 shrink-0 text-amber-500 mt-0.5" />
                            <p className="text-xs leading-relaxed font-medium">
                                This will apply a global grace period threshold to all organizations in the system. The setting will activate automatically whenever a tenant is switched to PAYG mode.
                            </p>
                        </div>

                        <form onSubmit={handleBulkSetGracePeriod} className="space-y-4">
                            <div>
                                <label className="block text-[11px] font-bold text-slate-400 dark:text-slate-500 uppercase tracking-wider mb-2">
                                    Global Grace Period (Months)
                                </label>
                                <input
                                    type="number"
                                    min="1"
                                    max="24"
                                    required
                                    value={bulkGraceModal.months}
                                    onChange={(e) => setBulkGraceModal({ ...bulkGraceModal, months: e.target.value })}
                                    className="w-full px-4 py-2.5 rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900 text-slate-900 dark:text-white font-mono text-sm focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500 outline-none transition duration-155"
                                />
                            </div>
                            <div className="flex justify-end gap-3 pt-2">
                                <button
                                    type="button"
                                    onClick={() => setBulkGraceModal({ open: false, months: 3 })}
                                    className="px-4 py-2 text-xs sm:text-sm font-semibold text-slate-550 hover:bg-slate-50 dark:hover:bg-slate-700/50 rounded-xl transition cursor-pointer"
                                >
                                    Cancel
                                </button>
                                <button
                                    type="submit"
                                    disabled={actionLoading}
                                    className="px-4.5 py-2 text-xs sm:text-sm font-semibold bg-indigo-600 hover:bg-indigo-700 text-white rounded-xl transition shadow-md shadow-indigo-600/10 cursor-pointer"
                                >
                                    {actionLoading ? 'Applying...' : 'Apply to All'}
                                </button>
                            </div>
                        </form>
                    </div>
                </div>
            )}
        </div>
    );
}
