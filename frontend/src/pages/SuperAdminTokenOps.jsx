import React, { useState, useEffect } from 'react';
import { 
    Coins, Building2, Shield, DollarSign, Activity, RefreshCw, 
    AlertCircle, CheckCircle2, Plus, Edit, Ban, Check, UserCheck, XCircle, Search,
    BarChart2, TrendingUp, PieChart, AlertTriangle, ArrowUpRight, Zap, Award, 
    Sparkles, Clock, Sliders, ChevronRight, Info, Calendar, ArrowRight, Eye, Layers
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
    const [activeTab, setActiveTab] = useState('analytics'); // 'analytics' | 'wallets' | 'pricing' | 'payg'

    // Analytics Tab State
    const [trendRange, setTrendRange] = useState('30d'); // '7d' | '30d' | '90d'
    const [trendMetric, setTrendMetric] = useState('tokens'); // 'tokens' | 'cost' | 'requests' | 'infra_cost'
    const [trendsData, setTrendsData] = useState(null);
    const [hoveredPoint, setHoveredPoint] = useState(null);
    const [modelsData, setModelsData] = useState([]);
    const [topOrgsData, setTopOrgsData] = useState(null);
    const [topOrgsSort, setTopOrgsSort] = useState('tokens'); // 'tokens' | 'cost' | 'requests'
    const [topOrgsBillingFilter, setTopOrgsBillingFilter] = useState('all'); // 'all' | 'PAYG' | 'Prepaid' | 'blocked'
    const [alertsData, setAlertsData] = useState(null);
    const [alertTypeFilter, setAlertTypeFilter] = useState('all'); // 'all' | 'critical' | 'warning' | 'action'
    const [chartMode, setChartMode] = useState('line'); // 'line' | 'bar'
    const [orgChartFilter, setOrgChartFilter] = useState('all');
    const [analyticsLoading, setAnalyticsLoading] = useState(false);
    const [analyticsError, setAnalyticsError] = useState('');

    // Organization Drill-down Modal State
    const [selectedOrgModal, setSelectedOrgModal] = useState(null);
    const [orgDetailLoading, setOrgDetailLoading] = useState(false);
    const [orgDetailData, setOrgDetailData] = useState(null);

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
    const [limitsModal, setLimitsModal] = useState({ open: false, orgName: '', softLimit: '', hardLimit: '', billingEmail: '' });

    const formatCurrency = (amount, pricePerToken = 0.000007) => {
        return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format((amount || 0) * pricePerToken);
    };

    const formatDateOrdinal = (dateStr) => {
        if (!dateStr) return '';
        let day, monthIndex;
        const parts = String(dateStr).split('-');
        if (parts.length === 3) {
            monthIndex = parseInt(parts[1], 10) - 1;
            day = parseInt(parts[2], 10);
        } else if (parts.length === 2) {
            monthIndex = parseInt(parts[0], 10) - 1;
            day = parseInt(parts[1], 10);
        } else {
            const d = new Date(dateStr);
            if (isNaN(d.getTime())) return dateStr;
            day = d.getDate();
            monthIndex = d.getMonth();
        }

        if (isNaN(day) || isNaN(monthIndex) || monthIndex < 0 || monthIndex > 11) {
            return dateStr;
        }

        const months = [
            'January', 'February', 'March', 'April', 'May', 'June',
            'July', 'August', 'September', 'October', 'November', 'December'
        ];

        const getOrdinal = (n) => {
            const s = ["th", "st", "nd", "rd"];
            const v = n % 100;
            return n + (s[(v - 20) % 10] || s[v] || s[0]);
        };

        return `${getOrdinal(day)} ${months[monthIndex]}`;
    };

    const getHeaders = () => {
        const token = localStorage.getItem('token');
        return {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json'
        };
    };

    const fetchAnalyticsData = async (range = trendRange) => {
        setAnalyticsLoading(true);
        setAnalyticsError('');
        try {
            const headers = getHeaders();
            const [trendsRes, modelsRes, topOrgsRes, alertsRes] = await Promise.all([
                fetch(API_ENDPOINTS.TOKENOPS_ADMIN_ANALYTICS_TRENDS(range), { headers }),
                fetch(API_ENDPOINTS.TOKENOPS_ADMIN_ANALYTICS_MODELS, { headers }),
                fetch(API_ENDPOINTS.TOKENOPS_ADMIN_ANALYTICS_TOP_ORGS(10), { headers }),
                fetch(API_ENDPOINTS.TOKENOPS_ADMIN_ANALYTICS_ALERTS, { headers })
            ]);

            if (trendsRes.ok) {
                const json = await trendsRes.json();
                if (json.success && json.data) setTrendsData(json.data);
            }
            if (modelsRes.ok) {
                const json = await modelsRes.json();
                if (json.success && json.data) setModelsData(json.data);
            }
            if (topOrgsRes.ok) {
                const json = await topOrgsRes.json();
                if (json.success && json.data) setTopOrgsData(json.data);
            }
            if (alertsRes.ok) {
                const json = await alertsRes.json();
                if (json.success && json.data) setAlertsData(json.data);
            }
        } catch (err) {
            setAnalyticsError(err.message || 'Failed to load analytics telemetry.');
        } finally {
            setAnalyticsLoading(false);
        }
    };

    const handleOpenOrgDrilldown = async (orgName) => {
        setSelectedOrgModal(orgName);
        setOrgDetailLoading(true);
        setOrgDetailData(null);
        try {
            const headers = getHeaders();
            const res = await fetch(API_ENDPOINTS.TOKENOPS_ADMIN_ANALYTICS_ORG(orgName), { headers });
            if (res.ok) {
                const json = await res.json();
                if (json.success && json.data) setOrgDetailData(json.data);
            }
        } catch (err) {
            console.warn('Failed to load org details:', err);
        } finally {
            setOrgDetailLoading(false);
        }
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
        fetchAnalyticsData(trendRange);
    }, [trendRange]);

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
                 ? `🎉 Successfully approved ${req.request_type === 'TOKEN_INCREASE' ? `${Number(req.requested_tokens || 0).toLocaleString()} tokens for` : req.request_type === 'PAYG_DISABLEMENT' ? 'Prepaid Switch for' : 'PAYG for'} ${req.organization_name}!`
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

    // Handle PAYG Limits Update
    const handleUpdateLimits = async (e) => {
        e.preventDefault();
        setActionLoading(true);
        setError('');
        setSuccessMessage('');
        try {
            const res = await fetch(API_ENDPOINTS.TOKENOPS_ADMIN_LIMITS, {
                method: 'POST',
                headers: getHeaders(),
                body: JSON.stringify({
                    organization_name: limitsModal.orgName,
                    soft_limit_usd: limitsModal.softLimit ? parseFloat(limitsModal.softLimit) : null,
                    hard_limit_usd: limitsModal.hardLimit ? parseFloat(limitsModal.hardLimit) : null,
                    billing_email: limitsModal.billingEmail ? limitsModal.billingEmail.trim() : null
                })
            });
            const data = await res.json();
            if (!res.ok || !data.success) {
                throw new Error(data.error?.message || 'Failed to update PAYG limits.');
            }
            const msg = `🎉 Successfully updated PAYG limits for ${limitsModal.orgName}!`;
            setSuccessMessage(msg);
            showToast(msg, 'success');
            setLimitsModal({ open: false, orgName: '', softLimit: '', hardLimit: '', billingEmail: '' });
            fetchData();
        } catch (err) {
            setError(err.message);
            showToast(err.message || 'Failed to update PAYG limits.', 'error');
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

            {/* Actions Toolbar */}
            <div className="flex justify-end items-center pb-1">
                <button 
                    onClick={fetchData} 
                    disabled={loading}
                    className="flex items-center gap-2 px-3.5 py-1.5 bg-white dark:bg-slate-800 hover:bg-slate-100 dark:hover:bg-slate-700 border border-slate-200/80 dark:border-slate-700 text-slate-700 dark:text-slate-200 rounded-xl transition text-xs font-semibold cursor-pointer shadow-sm"
                >
                    <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
                    <span>Refresh Data</span>
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

            {/* Overview KPIs (8 Cards) */}
            {stats && (
                <div className="grid grid-cols-2 md:grid-cols-4 2xl:grid-cols-8 gap-3">
                    {/* 1. Total Orgs */}
                    <div className="bg-white dark:bg-slate-800 p-3 rounded-xl border border-slate-200 dark:border-slate-700 shadow-sm hover:shadow-md transition flex flex-col justify-between min-h-[95px]">
                        <div className="flex items-start justify-between gap-1.5">
                            <span className="text-[10px] font-bold text-slate-400 dark:text-slate-500 uppercase tracking-wider leading-tight">Total Orgs</span>
                            <Building2 className="w-3.5 h-3.5 text-slate-400 flex-shrink-0 mt-0.5" />
                        </div>
                        <div className="text-base sm:text-lg font-bold text-slate-800 dark:text-slate-100 mt-1">{stats.total_organizations}</div>
                        <div className="text-[9px] text-slate-500 flex items-center gap-1 mt-0.5 whitespace-nowrap">
                            <span className="text-indigo-600 font-semibold">{stats.prepaid_organizations} prep</span> · <span className="text-amber-600 font-semibold">{stats.payg_organizations} payg</span>
                        </div>
                    </div>

                    {/* 2. Tokens Consumed */}
                    <div className="bg-white dark:bg-slate-800 p-3 rounded-xl border border-slate-200 dark:border-slate-700 shadow-sm hover:shadow-md transition flex flex-col justify-between min-h-[95px]">
                        <div className="flex items-start justify-between gap-1.5">
                            <span className="text-[10px] font-bold text-indigo-500 dark:text-indigo-400 uppercase tracking-wider leading-tight">Tokens Burned</span>
                            <Coins className="w-3.5 h-3.5 text-indigo-500 flex-shrink-0 mt-0.5" />
                        </div>
                        <div className="text-base sm:text-lg font-bold text-indigo-700 dark:text-indigo-300 mt-1">
                            {Number(stats.total_tokens_consumed || 0).toLocaleString()}
                        </div>
                        <span className="text-[9px] text-slate-400 leading-tight">Total prompt + comp</span>
                    </div>

                    {/* 3. Consumption Cost */}
                    <div className="bg-white dark:bg-slate-800 p-3 rounded-xl border border-slate-200 dark:border-slate-700 shadow-sm hover:shadow-md transition flex flex-col justify-between min-h-[95px]">
                        <div className="flex items-start justify-between gap-1.5">
                            <span className="text-[10px] font-bold text-emerald-600 dark:text-emerald-400 uppercase tracking-wider leading-tight">Platform Cost</span>
                            <DollarSign className="w-3.5 h-3.5 text-emerald-500 flex-shrink-0 mt-0.5" />
                        </div>
                        <div className="text-base sm:text-lg font-bold text-emerald-700 dark:text-emerald-300 mt-1">
                            ${Number(stats.total_historical_cost || 0).toFixed(2)}
                        </div>
                        <span className="text-[9px] text-slate-400 leading-tight">Across all AI calls</span>
                    </div>

                    {/* 4. PAYG Spend */}
                    <div className="bg-white dark:bg-slate-800 p-3 rounded-xl border border-slate-200 dark:border-slate-700 shadow-sm hover:shadow-md transition flex flex-col justify-between min-h-[95px]">
                        <div className="flex items-start justify-between gap-1.5">
                            <span className="text-[10px] font-bold text-amber-600 dark:text-amber-400 uppercase tracking-wider leading-tight">PAYG Spend</span>
                            <DollarSign className="w-3.5 h-3.5 text-amber-500 flex-shrink-0 mt-0.5" />
                        </div>
                        <div className="text-base sm:text-lg font-bold text-amber-700 dark:text-amber-300 mt-1">
                            ${Number(stats.total_payg_current_spend_usd || 0).toFixed(2)}
                        </div>
                        <span className="text-[9px] text-amber-600 font-semibold leading-tight">{stats.payg_organizations} active orgs</span>
                    </div>

                    {/* 5. Total Requests */}
                    <div className="bg-white dark:bg-slate-800 p-3 rounded-xl border border-slate-200 dark:border-slate-700 shadow-sm hover:shadow-md transition flex flex-col justify-between min-h-[95px]">
                        <div className="flex items-start justify-between gap-1.5">
                            <span className="text-[10px] font-bold text-slate-400 dark:text-slate-500 uppercase tracking-wider leading-tight">Total Requests</span>
                            <Activity className="w-3.5 h-3.5 text-slate-400 flex-shrink-0 mt-0.5" />
                        </div>
                        <div className="text-base sm:text-lg font-bold text-slate-800 dark:text-slate-100 mt-1">
                            {Number(stats.total_requests || 0).toLocaleString()}
                        </div>
                        <span className="text-[9px] text-slate-400 leading-tight">LLM API calls</span>
                    </div>

                    {/* 6. Pending Quota */}
                    <div 
                        onClick={() => setActiveTab('payg')}
                        className={`bg-white dark:bg-slate-800 p-3 rounded-xl border shadow-sm hover:shadow-md transition flex flex-col justify-between min-h-[95px] cursor-pointer group ${
                            (stats.pending_quota_requests || 0) > 0 ? 'border-amber-300 dark:border-amber-700 bg-amber-50/20' : 'border-slate-200 dark:border-slate-700'
                        }`}
                    >
                        <div className="flex items-start justify-between gap-1.5">
                            <span className="text-[10px] font-bold text-amber-600 dark:text-amber-400 uppercase tracking-wider leading-tight">Quota Requests</span>
                            <Clock className="w-3.5 h-3.5 text-amber-500 group-hover:scale-110 transition flex-shrink-0 mt-0.5" />
                        </div>
                        <div className="text-base sm:text-lg font-bold text-amber-700 dark:text-amber-300 mt-1">{stats.pending_quota_requests || 0}</div>
                        <span className="text-[9px] text-amber-600 font-semibold flex items-center gap-0.5 leading-tight">
                            Review <ChevronRight className="w-2.5 h-2.5" />
                        </span>
                    </div>

                    {/* 7. Limit Warnings & Breaches */}
                    <div className={`bg-white dark:bg-slate-800 p-3 rounded-xl border shadow-sm hover:shadow-md transition flex flex-col justify-between min-h-[95px] ${
                        (stats.payg_limit_breaches || 0) > 0 ? 'border-rose-300 dark:border-rose-700 bg-rose-50/20' : 'border-slate-200 dark:border-slate-700'
                    }`}>
                        <div className="flex items-start justify-between gap-1.5">
                            <span className="text-[10px] font-bold text-rose-500 dark:text-rose-400 uppercase tracking-wider leading-tight">Limit Breaches</span>
                            <AlertTriangle className="w-3.5 h-3.5 text-rose-500 flex-shrink-0 mt-0.5" />
                        </div>
                        <div className="text-base sm:text-lg font-bold text-rose-700 dark:text-rose-300 mt-1">{stats.payg_limit_breaches || 0}</div>
                        <span className="text-[9px] text-rose-500 font-semibold leading-tight">Hard limit exceed</span>
                    </div>

                    {/* 8. Low Balance / Blocked */}
                    <div className="bg-white dark:bg-slate-800 p-3 rounded-xl border border-slate-200 dark:border-slate-700 shadow-sm hover:shadow-md transition flex flex-col justify-between min-h-[95px]">
                        <div className="flex items-start justify-between gap-1.5">
                            <span className="text-[10px] font-bold text-slate-400 dark:text-slate-500 uppercase tracking-wider leading-tight">Health / Holds</span>
                            <Ban className="w-3.5 h-3.5 text-slate-400 flex-shrink-0 mt-0.5" />
                        </div>
                        <div className="text-base sm:text-lg font-bold text-slate-800 dark:text-slate-100 mt-1">
                            {stats.blocked_organizations || 0}
                        </div>
                        <span className="text-[9px] text-slate-500 leading-tight">
                            {stats.low_balance_organizations || 0} low balance
                        </span>
                    </div>
                </div>
            )}

            {/* Navigation Tabs */}
            <div className="flex border-b border-slate-200 dark:border-slate-700 space-x-1 sm:space-x-2">
                <button
                    onClick={() => setActiveTab('analytics')}
                    className={`px-4 py-2.5 text-xs sm:text-sm font-semibold flex items-center gap-2 border-b-2 transition cursor-pointer ${
                        activeTab === 'analytics'
                            ? 'border-indigo-600 text-indigo-600 dark:text-indigo-400 dark:border-indigo-400'
                            : 'border-transparent text-slate-500 hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-200'
                    }`}
                >
                    <BarChart2 className="w-4 h-4" />
                    <span>Analytics Dashboard</span>
                    {alertsData?.total_alerts > 0 && (
                        <span className="px-1.5 py-0.5 rounded-full text-[10px] bg-rose-100 text-rose-700 dark:bg-rose-950/60 dark:text-rose-300 font-bold">
                            {alertsData.total_alerts}
                        </span>
                    )}
                </button>
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


            {/* TAB 0: Analytics Dashboard */}
            {activeTab === 'analytics' && (
                <div className="space-y-5">

                    {/* ── Section Header ── */}
                    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                        <div>
                            <h2 className="text-base font-bold text-slate-900 dark:text-white flex items-center gap-2">
                                <BarChart2 className="w-5 h-5 text-indigo-500" />
                                Platform Analytics Hub
                            </h2>
                            <p className="text-xs text-slate-400 mt-0.5">Real-time insight into token operations, cost exposure, and tenant health across all organizations.</p>
                        </div>
                        <div className="flex items-center gap-2">
                            <button onClick={() => fetchAnalyticsData(trendRange)} className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold bg-slate-100 dark:bg-slate-700 hover:bg-indigo-50 dark:hover:bg-indigo-950/50 text-slate-600 dark:text-slate-300 hover:text-indigo-600 rounded-xl border border-slate-200 dark:border-slate-600 transition cursor-pointer">
                                <RefreshCw className={`w-3.5 h-3.5 ${analyticsLoading ? 'animate-spin' : ''}`} />
                                Refresh
                            </button>
                            {/* Range Switcher */}
                            <div className="flex bg-slate-100 dark:bg-slate-700/60 p-1 rounded-xl text-xs font-semibold">
                                {['7d', '30d', '90d'].map((r) => (
                                    <button key={r} onClick={() => setTrendRange(r)}
                                        className={`px-2.5 py-1 rounded-lg uppercase tracking-wider transition cursor-pointer ${trendRange === r ? 'bg-indigo-600 text-white shadow-sm' : 'text-slate-500 hover:text-slate-800 dark:text-slate-300'}`}>
                                        {r}
                                    </button>
                                ))}
                            </div>
                        </div>
                    </div>

                    {analyticsError && (
                        <div className="p-3 bg-rose-50 dark:bg-rose-950/30 border border-rose-200 dark:border-rose-800 rounded-xl text-xs text-rose-700 dark:text-rose-300 flex items-center gap-2">
                            <AlertCircle className="w-4 h-4 shrink-0" />{analyticsError}
                        </div>
                    )}

                    {/* ── KPI Summary Row ── */}
                    {(() => {
                        const pts = trendsData?.points || [];
                        const totalTokens = pts.reduce((s, p) => s + (p.total_tokens || 0), 0);
                        const totalCost = pts.reduce((s, p) => s + (p.cost_usd || 0), 0);
                        const totalReqs = pts.reduce((s, p) => s + (p.request_count || 0), 0);
                        const activeOrgCount = topOrgsData?.by_tokens?.length || 0;
                        const pendingActions = (alertsData?.action_required?.length || 0) + (alertsData?.critical?.length || 0);
                        const dailyAvgCost = pts.length > 0 ? totalCost / pts.length : 0;
                        const kpis = [
                            { label: 'Platform Spend', value: `$${totalCost.toFixed(2)}`, sub: `$${dailyAvgCost.toFixed(3)}/day avg`, color: 'emerald', icon: DollarSign },
                            { label: 'Total Tokens', value: totalTokens >= 1e6 ? `${(totalTokens/1e6).toFixed(2)}M` : totalTokens >= 1e3 ? `${(totalTokens/1e3).toFixed(1)}K` : String(totalTokens), sub: `${totalReqs.toLocaleString()} requests`, color: 'indigo', icon: Zap },
                            { label: 'Active Orgs', value: activeOrgCount, sub: `in selected period`, color: 'violet', icon: Building2 },
                            { label: 'Pending Actions', value: pendingActions, sub: `${alertsData?.warning?.length || 0} warnings`, color: pendingActions > 0 ? 'rose' : 'slate', icon: AlertTriangle },
                        ];
                        const colorMap = {
                            emerald: 'text-emerald-600 dark:text-emerald-400 bg-emerald-50 dark:bg-emerald-950/30 border-emerald-200 dark:border-emerald-800',
                            indigo: 'text-indigo-600 dark:text-indigo-400 bg-indigo-50 dark:bg-indigo-950/30 border-indigo-200 dark:border-indigo-800',
                            violet: 'text-violet-600 dark:text-violet-400 bg-violet-50 dark:bg-violet-950/30 border-violet-200 dark:border-violet-800',
                            rose: 'text-rose-600 dark:text-rose-400 bg-rose-50 dark:bg-rose-950/30 border-rose-200 dark:border-rose-800',
                            slate: 'text-slate-500 dark:text-slate-400 bg-slate-50 dark:bg-slate-800 border-slate-200 dark:border-slate-700',
                        };
                        return (
                            <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
                                {kpis.map(k => {
                                    const cls = colorMap[k.color];
                                    const Icon = k.icon;
                                    return (
                                        <div key={k.label} className={`rounded-2xl border p-4 flex flex-col gap-1 shadow-sm ${cls}`}>
                                            <div className="flex items-center justify-between">
                                                <span className="text-[10px] font-bold uppercase tracking-wider opacity-70">{k.label}</span>
                                                <Icon className="w-4 h-4 opacity-60" />
                                            </div>
                                            <div className="text-2xl font-black mt-1">{analyticsLoading ? '—' : k.value}</div>
                                            <div className="text-[10px] opacity-60 font-semibold">{k.sub}</div>
                                        </div>
                                    );
                                })}
                            </div>
                        );
                    })()}

                    {/* ── Trend Chart ── */}
                    <div className="bg-white dark:bg-slate-800 p-5 sm:p-6 rounded-2xl border border-slate-200/80 dark:border-slate-700 shadow-sm space-y-4">
                        <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-3">
                            <div>
                                <h3 className="text-base font-bold text-slate-900 dark:text-white flex items-center gap-2">
                                    <TrendingUp className="w-5 h-5 text-indigo-500" />Platform Consumption Trends
                                </h3>
                                <p className="text-xs text-slate-400 mt-0.5">Daily aggregates across all organizations. Use filters to narrow by metric, chart style, or specific org.</p>
                            </div>
                            <div className="flex flex-wrap items-center gap-2">
                                {/* Chart Mode */}
                                <div className="flex bg-slate-100 dark:bg-slate-700/60 p-1 rounded-xl text-xs font-semibold">
                                    {[{v:'line', label:'Line'},{v:'bar', label:'Bar'}].map(m => (
                                        <button key={m.v} onClick={() => setChartMode(m.v)}
                                            className={`px-2.5 py-1 rounded-lg transition cursor-pointer ${chartMode === m.v ? 'bg-white dark:bg-slate-800 text-indigo-600 shadow-sm' : 'text-slate-500 hover:text-slate-800 dark:text-slate-300'}`}>
                                            {m.label}
                                        </button>
                                    ))}
                                </div>
                                {/* Metric Switcher */}
                                <div className="flex bg-slate-100 dark:bg-slate-700/60 p-1 rounded-xl text-xs font-semibold">
                                    {[
                                        {v:'tokens', label:'Tokens', col:'text-indigo-600'},
                                        {v:'cost', label:'Cost ($)', col:'text-emerald-600'},
                                        {v:'requests', label:'Requests', col:'text-amber-600'},
                                        {v:'infra_cost', label:'Infra ($)', col:'text-violet-600'},
                                    ].map(m => (
                                        <button key={m.v} onClick={() => setTrendMetric(m.v)}
                                            className={`px-2.5 py-1 rounded-lg transition cursor-pointer ${trendMetric === m.v ? `bg-white dark:bg-slate-800 ${m.col} shadow-sm` : 'text-slate-500 hover:text-slate-800 dark:text-slate-300'}`}>
                                            {m.label}
                                        </button>
                                    ))}
                                </div>
                                {/* Org Filter */}
                                {topOrgsData?.by_tokens?.length > 0 && (
                                    <select value={orgChartFilter} onChange={e => setOrgChartFilter(e.target.value)}
                                        className="text-xs px-2 py-1.5 rounded-xl border border-slate-200 dark:border-slate-600 bg-white dark:bg-slate-800 text-slate-700 dark:text-slate-300 focus:outline-none focus:ring-2 focus:ring-indigo-500/20 cursor-pointer">
                                        <option value="all">All Orgs</option>
                                        {topOrgsData.by_tokens.map(o => <option key={o.organization_name} value={o.organization_name}>{o.organization_name}</option>)}
                                    </select>
                                )}
                            </div>
                        </div>

                        {/* Summary Strip */}
                        {trendsData?.points && (
                            <div className="grid grid-cols-3 gap-3 bg-slate-50 dark:bg-slate-900/50 p-3 rounded-xl border border-slate-100 dark:border-slate-750">
                                {[
                                    { label: 'Period Total', val: (() => {
                                        const pts = trendsData.points;
                                        if (trendMetric === 'tokens') {
                                            const total = Number(pts.reduce((a,p)=>a+p.total_tokens,0));
                                            return `${total.toLocaleString()} ${total === 1 ? 'token' : 'tokens'}`;
                                        }
                                        if (trendMetric === 'cost') return `$${pts.reduce((a,p)=>a+p.cost_usd,0).toFixed(2)}`;
                                        if (trendMetric === 'infra_cost') return `$${pts.reduce((a,p)=>a+(p.infra_cost_usd||0),0).toFixed(2)}`;
                                        return `${pts.reduce((a,p)=>a+p.request_count,0).toLocaleString()} reqs`;
                                    })()},
                                    { label: 'Daily Avg', val: (() => {
                                        const pts = trendsData.points; const n = pts.length || 1;
                                        if (trendMetric === 'tokens') {
                                            const avg = Math.round(pts.reduce((a,p)=>a+p.total_tokens,0)/n);
                                            return `${avg.toLocaleString()} ${avg === 1 ? 'token' : 'tokens'}/day`;
                                        }
                                        if (trendMetric === 'cost') return `$${(pts.reduce((a,p)=>a+p.cost_usd,0)/n).toFixed(3)}/day`;
                                        if (trendMetric === 'infra_cost') return `$${(pts.reduce((a,p)=>a+(p.infra_cost_usd||0),0)/n).toFixed(3)}/day`;
                                        return `${Math.round(pts.reduce((a,p)=>a+p.request_count,0)/n).toLocaleString()} reqs/day`;
                                    })()},
                                    { label: 'Peak Day', val: (() => {
                                        const pts = trendsData.points;
                                        const peak = [...pts].sort((a,b) => {
                                            const va = trendMetric==='tokens'?a.total_tokens:trendMetric==='cost'?a.cost_usd:trendMetric==='infra_cost'?(a.infra_cost_usd||0):a.request_count;
                                            const vb = trendMetric==='tokens'?b.total_tokens:trendMetric==='cost'?b.cost_usd:trendMetric==='infra_cost'?(b.infra_cost_usd||0):b.request_count;
                                            return vb-va;
                                        })[0];
                                        if (!peak) return '—';
                                        const v = trendMetric==='tokens'
                                            ? `${Number(peak.total_tokens).toLocaleString()} ${Number(peak.total_tokens) === 1 ? 'token' : 'tokens'}`
                                            : trendMetric==='cost'
                                            ? `$${Number(peak.cost_usd).toFixed(2)}`
                                            : trendMetric==='infra_cost'
                                            ? `$${Number(peak.infra_cost_usd||0).toFixed(2)}`
                                            : `${peak.request_count} reqs`;
                                        const formattedDate = formatDateOrdinal(peak.date);
                                        return formattedDate ? `${v} (${formattedDate})` : v;
                                    })()},
                                ].map(s => (
                                    <div key={s.label}>
                                        <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider block">{s.label}</span>
                                        <div className="text-sm font-bold text-slate-800 dark:text-slate-100 mt-0.5 truncate" title={s.val}>{s.val}</div>
                                    </div>
                                ))}
                            </div>
                        )}

                        {/* Chart */}
                        {analyticsLoading ? (
                            <div className="h-64 flex flex-col items-center justify-center text-slate-400 gap-2">
                                <RefreshCw className="w-6 h-6 animate-spin text-indigo-500" />
                                <span className="text-xs">Aggregating platform metrics...</span>
                            </div>
                        ) : trendsData?.points && trendsData.points.length > 0 ? (() => {
                            const pts = trendsData.points;
                            const W=800, H=230, pL=55, pR=20, pT=20, pB=35;
                            const pw=W-pL-pR, ph=H-pT-pB;
                            const col = trendMetric==='cost'?'#10b981':trendMetric==='requests'?'#f59e0b':trendMetric==='infra_cost'?'#8b5cf6':'#6366f1';
                            const vals = pts.map(p => trendMetric==='tokens'?p.total_tokens:trendMetric==='cost'?p.cost_usd:trendMetric==='infra_cost'?(p.infra_cost_usd||0):p.request_count);
                            const maxV = Math.max(...vals, 0.001);
                            const coords = pts.map((p,i) => {
                                const v = vals[i];
                                return { x: pL+(i/Math.max(pts.length-1,1))*pw, y: pT+ph-(v/maxV)*ph, point:p, val:v };
                            });
                            const linePath = coords.map((c,i)=>`${i===0?'M':'L'} ${c.x.toFixed(1)} ${c.y.toFixed(1)}`).join(' ');
                            const areaPath = `${linePath} L ${coords[coords.length-1].x.toFixed(1)} ${(pT+ph).toFixed(1)} L ${coords[0].x.toFixed(1)} ${(pT+ph).toFixed(1)} Z`;
                            const barW = Math.max(3, (pw/pts.length)*0.65);
                            const gridLvls = [1,0.75,0.5,0.25,0];
                            const fmtY = v => trendMetric==='tokens'?(v>=1e6?`${(v/1e6).toFixed(1)}M`:v>=1e3?`${(v/1e3).toFixed(0)}K`:`${Math.round(v)}`):trendMetric==='cost'||trendMetric==='infra_cost'?`$${v.toFixed(2)}`:`${Math.round(v)}`;
                            return (
                                <div className="relative">
                                    <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-60 overflow-visible">
                                        <defs>
                                            <linearGradient id="ag2" x1="0" y1="0" x2="0" y2="1">
                                                <stop offset="0%" stopColor={col} stopOpacity="0.28"/>
                                                <stop offset="100%" stopColor={col} stopOpacity="0"/>
                                            </linearGradient>
                                        </defs>
                                        {gridLvls.map((lvl,idx)=>{
                                            const y=pT+ph*(1-lvl);
                                            return (
                                                <g key={idx}>
                                                    <line x1={pL} y1={y} x2={W-pR} y2={y} stroke="currentColor" className="text-slate-200 dark:text-slate-700/50" strokeDasharray="3 3"/>
                                                    <text x={pL-8} y={y+3} textAnchor="end" className="text-[9px] fill-slate-400 dark:fill-slate-500 font-mono">{fmtY(maxV*lvl)}</text>
                                                </g>
                                            );
                                        })}
                                        {chartMode==='bar' ? (
                                            coords.map((c,i)=>(
                                                <g key={i} onMouseEnter={()=>setHoveredPoint(c.point)} onMouseLeave={()=>setHoveredPoint(null)} className="cursor-pointer">
                                                    <rect x={c.x-barW/2} y={c.y} width={barW} height={(pT+ph)-c.y}
                                                        fill={hoveredPoint?.date===c.point.date?col:col} opacity={hoveredPoint?.date===c.point.date?1:0.7}
                                                        rx="2"
                                                        style={{transition:'opacity 0.15s'}}/>
                                                </g>
                                            ))
                                        ) : (
                                            <>
                                                <path d={areaPath} fill="url(#ag2)"/>
                                                <path d={linePath} fill="none" stroke={col} strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"/>
                                                {coords.map((c,i)=>{
                                                    const isH=hoveredPoint?.date===c.point.date;
                                                    return (
                                                        <g key={i} className="cursor-pointer" onMouseEnter={()=>setHoveredPoint(c.point)} onMouseLeave={()=>{}}>
                                                            {isH&&<line x1={c.x} y1={pT} x2={c.x} y2={pT+ph} stroke={col} strokeWidth="1.5" strokeDasharray="3 3"/>}
                                                            <circle cx={c.x} cy={c.y} r={isH?5:(pts.length<=14?3:2)} fill={isH?col:col} opacity={isH?1:0.8} stroke="white" strokeWidth={isH?2:0}/>
                                                            <rect x={c.x-(pw/pts.length)/2} y={pT} width={pw/pts.length} height={ph} fill="transparent"/>
                                                        </g>
                                                    );
                                                })}
                                            </>
                                        )}
                                        {coords.map((c,i)=>{
                                            const step=Math.max(1,Math.floor(pts.length/8));
                                            if(i%step===0||i===pts.length-1){
                                                const d=c.point.date?.split('-');
                                                const s=d?.length===3?`${d[1]}/${d[2]}`:c.point.date;
                                                return <text key={i} x={c.x} y={pT+ph+18} textAnchor="middle" className="text-[9px] fill-slate-400 dark:fill-slate-500 font-mono">{s}</text>;
                                            } return null;
                                        })}
                                    </svg>
                                    {/* Hover Tooltip */}
                                    {hoveredPoint && (
                                        <div className="mt-3 p-3 bg-slate-900 text-white rounded-xl shadow-xl border border-slate-700 text-xs flex flex-wrap items-center justify-between gap-4">
                                            <div className="flex items-center gap-2">
                                                <Calendar className="w-3.5 h-3.5 text-indigo-400"/>
                                                <span className="font-bold">{hoveredPoint.date}</span>
                                            </div>
                                            <div className="flex items-center gap-4">
                                                <div><span className="text-[10px] text-slate-400 block">Tokens</span><span className="font-bold text-indigo-300 font-mono">{Number(hoveredPoint.total_tokens).toLocaleString()}</span></div>
                                                <div><span className="text-[10px] text-slate-400 block">Prompt/Comp</span><span className="text-slate-300 font-mono text-[11px]">{Number(hoveredPoint.prompt_tokens).toLocaleString()} / {Number(hoveredPoint.completion_tokens).toLocaleString()}</span></div>
                                                <div><span className="text-[10px] text-slate-400 block">Cost</span><span className="font-bold text-emerald-400 font-mono">${Number(hoveredPoint.cost_usd).toFixed(4)}</span></div>
                                                {hoveredPoint.infra_cost_usd != null && <div><span className="text-[10px] text-slate-400 block">Infra</span><span className="font-bold text-violet-400 font-mono">${Number(hoveredPoint.infra_cost_usd).toFixed(4)}</span></div>}
                                                <div><span className="text-[10px] text-slate-400 block">Requests</span><span className="font-bold text-amber-400 font-mono">{hoveredPoint.request_count}</span></div>
                                            </div>
                                            <button onClick={()=>setHoveredPoint(null)} className="text-slate-400 hover:text-white text-[10px] px-1.5 py-0.5 rounded bg-slate-800 hover:bg-slate-700 transition cursor-pointer">✕</button>
                                        </div>
                                    )}
                                </div>
                            );
                        })() : (
                            <div className="h-48 flex items-center justify-center text-slate-400 text-xs border border-dashed border-slate-200 dark:border-slate-700 rounded-xl">No activity data for this time range.</div>
                        )}
                    </div>

                    {/* ── 2-col: Model Distribution + Billing Mode ── */}
                    <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">

                        {/* Model Distribution (2/3 width) */}
                        <div className="lg:col-span-2 bg-white dark:bg-slate-800 p-5 rounded-2xl border border-slate-200/80 dark:border-slate-700 shadow-sm space-y-4">
                            <div className="flex items-center justify-between">
                                <div>
                                    <h3 className="text-base font-bold text-slate-900 dark:text-white flex items-center gap-2">
                                        <PieChart className="w-4 h-4 text-indigo-500"/>AI Model Usage &amp; Efficiency
                                    </h3>
                                    <p className="text-xs text-slate-400 mt-0.5">Token share, spend, and cost-per-1K-token efficiency per model.</p>
                                </div>
                                <span className="text-[10px] text-slate-400 font-mono bg-slate-100 dark:bg-slate-700 px-2 py-0.5 rounded-lg">{modelsData.length} models</span>
                            </div>
                            {modelsData.length === 0 ? (
                                <div className="py-10 text-center text-slate-400 text-xs border border-dashed border-slate-200 dark:border-slate-700 rounded-xl">No model usage recorded yet.</div>
                            ) : (
                                <div className="space-y-3 max-h-80 overflow-y-auto pr-1 custom-scrollbar">
                                    {modelsData.map((m,idx) => {
                                        const palettes=[
                                            {bar:'bg-indigo-500',badge:'bg-indigo-50 text-indigo-700 dark:bg-indigo-950/40 dark:text-indigo-300 border-indigo-200 dark:border-indigo-800'},
                                            {bar:'bg-emerald-500',badge:'bg-emerald-50 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-300 border-emerald-200 dark:border-emerald-800'},
                                            {bar:'bg-amber-500',badge:'bg-amber-50 text-amber-700 dark:bg-amber-950/40 dark:text-amber-300 border-amber-200 dark:border-amber-800'},
                                            {bar:'bg-violet-500',badge:'bg-violet-50 text-violet-700 dark:bg-violet-950/40 dark:text-violet-300 border-violet-200 dark:border-violet-800'},
                                            {bar:'bg-rose-500',badge:'bg-rose-50 text-rose-700 dark:bg-rose-950/40 dark:text-rose-300 border-rose-200 dark:border-rose-800'},
                                            {bar:'bg-cyan-500',badge:'bg-cyan-50 text-cyan-700 dark:bg-cyan-950/40 dark:text-cyan-300 border-cyan-200 dark:border-cyan-800'},
                                        ];
                                        const c=palettes[idx%palettes.length];
                                        const costPer1k = m.total_tokens>0 ? (m.cost_usd/m.total_tokens)*1000 : 0;
                                        const isTop = idx===0;
                                        const isMostExpensive = modelsData.reduce((prev,cur)=>prev.cost_usd>cur.cost_usd?prev:cur)===m;
                                        return (
                                            <div key={m.model} className="p-3 bg-slate-50 dark:bg-slate-900/40 rounded-xl border border-slate-100 dark:border-slate-750 space-y-2 hover:border-indigo-200 dark:hover:border-indigo-800 transition">
                                                <div className="flex justify-between items-start gap-2">
                                                    <div className="flex items-center gap-2 flex-wrap min-w-0">
                                                        <span className={`px-2 py-0.5 rounded-lg text-xs font-mono font-semibold border truncate ${c.badge}`}>{m.model}</span>
                                                        {isTop && <span className="px-1.5 py-0.2 rounded text-[9px] font-bold bg-amber-100 text-amber-700 dark:bg-amber-950/50 dark:text-amber-300">Most Used</span>}
                                                        {isMostExpensive && !isTop && <span className="px-1.5 py-0.2 rounded text-[9px] font-bold bg-rose-100 text-rose-700 dark:bg-rose-950/50 dark:text-rose-300">Highest Spend</span>}
                                                    </div>
                                                    <div className="text-right shrink-0">
                                                        <span className="text-xs font-bold text-slate-800 dark:text-slate-200 font-mono">{m.percentage}%</span>
                                                        <span className="text-[10px] text-emerald-600 dark:text-emerald-400 font-mono block">${Number(m.cost_usd).toFixed(3)}</span>
                                                    </div>
                                                </div>
                                                <div className="w-full bg-slate-200 dark:bg-slate-700 h-1.5 rounded-full overflow-hidden">
                                                    <div className={`h-full ${c.bar} transition-all duration-500`} style={{width:`${Math.min(100,Math.max(2,m.percentage))}%`}}/>
                                                </div>
                                                <div className="flex justify-between text-[10px] text-slate-500 font-mono">
                                                    <span>Prompt: {Number(m.prompt_tokens).toLocaleString()}</span>
                                                    <span>Comp: {Number(m.completion_tokens).toLocaleString()}</span>
                                                    <span className="font-semibold text-slate-700 dark:text-slate-300">Total: {Number(m.total_tokens).toLocaleString()}</span>
                                                    <span className="text-violet-600 dark:text-violet-400">${costPer1k.toFixed(4)}/1K tok</span>
                                                </div>
                                                <div className="text-[10px] text-slate-400">{m.request_count} requests</div>
                                            </div>
                                        );
                                    })}
                                </div>
                            )}
                        </div>

                        {/* Billing Mode Distribution (1/3 width) */}
                        <div className="bg-white dark:bg-slate-800 p-5 rounded-2xl border border-slate-200/80 dark:border-slate-700 shadow-sm space-y-4">
                            <div>
                                <h3 className="text-base font-bold text-slate-900 dark:text-white flex items-center gap-2">
                                    <Layers className="w-4 h-4 text-indigo-500"/>Billing Mode Split
                                </h3>
                                <p className="text-xs text-slate-400 mt-0.5">Tenant distribution across billing types.</p>
                            </div>
                            {(() => {
                                const orgs = topOrgsData?.by_tokens || [];
                                const payg = orgs.filter(o=>o.billing_mode==='PAYG').length;
                                const prepaid = orgs.filter(o=>o.billing_mode!=='PAYG').length;
                                const blocked = orgs.filter(o=>o.is_blocked).length;
                                const total = orgs.length || 1;
                                const pct = n => Math.round((n/total)*100);
                                const modes = [
                                    {label:'PAYG', count:payg, pct:pct(payg), color:'bg-amber-500', text:'text-amber-700 dark:text-amber-300', bg:'bg-amber-50 dark:bg-amber-950/30'},
                                    {label:'Prepaid', count:prepaid, pct:pct(prepaid), color:'bg-indigo-500', text:'text-indigo-700 dark:text-indigo-300', bg:'bg-indigo-50 dark:bg-indigo-950/30'},
                                    {label:'Blocked', count:blocked, pct:pct(blocked), color:'bg-rose-500', text:'text-rose-700 dark:text-rose-300', bg:'bg-rose-50 dark:bg-rose-950/30'},
                                ];
                                // SVG Donut
                                const donutR=50, cx=70, cy=70, strokeW=18;
                                const circum=2*Math.PI*donutR;
                                let offset=0;
                                const donutSegs=[
                                    {pct:payg/total, col:'#f59e0b'},
                                    {pct:prepaid/total, col:'#6366f1'},
                                    {pct:blocked/total, col:'#f43f5e'},
                                ];
                                return (
                                    <div className="space-y-4">
                                        <div className="flex justify-center">
                                            <svg width="140" height="140" viewBox="0 0 140 140">
                                                <circle cx={cx} cy={cy} r={donutR} fill="none" stroke="currentColor" className="text-slate-100 dark:text-slate-700" strokeWidth={strokeW}/>
                                                {donutSegs.map((s,i)=>{
                                                    const dash=s.pct*circum;
                                                    const gap=circum-dash;
                                                    const el=<circle key={i} cx={cx} cy={cy} r={donutR} fill="none" stroke={s.col} strokeWidth={strokeW} strokeDasharray={`${dash} ${gap}`} strokeDashoffset={-offset} transform={`rotate(-90 ${cx} ${cy})`} strokeLinecap="butt"/>;
                                                    offset+=dash;
                                                    return el;
                                                })}
                                                <text x={cx} y={cy-5} textAnchor="middle" className="text-[10px] fill-slate-400 dark:fill-slate-500" fontSize="10">Total</text>
                                                <text x={cx} y={cy+12} textAnchor="middle" className="fill-slate-800 dark:fill-white" fontSize="18" fontWeight="bold">{orgs.length}</text>
                                            </svg>
                                        </div>
                                        <div className="space-y-2">
                                            {modes.map(m=>(
                                                <div key={m.label} className={`flex items-center justify-between p-2.5 rounded-xl ${m.bg} cursor-pointer hover:opacity-80 transition`}
                                                    onClick={()=>setTopOrgsBillingFilter(topOrgsBillingFilter===m.label?'all':m.label)}>
                                                    <div className="flex items-center gap-2">
                                                        <div className={`w-2.5 h-2.5 rounded-full ${m.color}`}/>
                                                        <span className={`text-xs font-bold ${m.text}`}>{m.label}</span>
                                                        {topOrgsBillingFilter===m.label && <span className="text-[9px] text-slate-500">(filtered)</span>}
                                                    </div>
                                                    <div className="text-right">
                                                        <div className={`text-sm font-black ${m.text}`}>{m.count}</div>
                                                        <div className="text-[10px] text-slate-400">{m.pct}%</div>
                                                    </div>
                                                </div>
                                            ))}
                                        </div>
                                        {topOrgsBillingFilter !== 'all' && (
                                            <button onClick={()=>setTopOrgsBillingFilter('all')} className="w-full text-[10px] text-slate-500 hover:text-indigo-600 font-semibold py-1 transition cursor-pointer">
                                                ✕ Clear filter
                                            </button>
                                        )}
                                    </div>
                                );
                            })()}
                        </div>
                    </div>

                    {/* ── Top Orgs Leaderboard ── */}
                    <div className="bg-white dark:bg-slate-800 p-5 rounded-2xl border border-slate-200/80 dark:border-slate-700 shadow-sm space-y-4">
                        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                            <div>
                                <h3 className="text-base font-bold text-slate-900 dark:text-white flex items-center gap-2">
                                    <Award className="w-4 h-4 text-indigo-500"/>Top Organizations Leaderboard
                                </h3>
                                <p className="text-xs text-slate-400 mt-0.5">Highest-consuming tenant organizations. Filter and sort to identify cost leaders or at-risk tenants.</p>
                            </div>
                            <div className="flex flex-wrap items-center gap-2">
                                {/* Billing Mode Filter */}
                                <div className="flex bg-slate-100 dark:bg-slate-700/60 p-1 rounded-xl text-xs font-semibold">
                                    {['all','PAYG','Prepaid','blocked'].map(f=>(
                                        <button key={f} onClick={()=>setTopOrgsBillingFilter(f)}
                                            className={`px-2.5 py-1 rounded-lg capitalize transition cursor-pointer ${topOrgsBillingFilter===f?'bg-white dark:bg-slate-800 text-indigo-600 shadow-sm':'text-slate-500 hover:text-slate-800 dark:text-slate-300'}`}>
                                            {f==='all'?'All':f}
                                        </button>
                                    ))}
                                </div>
                                {/* Sort */}
                                <div className="flex bg-slate-100 dark:bg-slate-700/60 p-1 rounded-xl text-xs font-semibold">
                                    {[{v:'tokens',label:'Tokens'},{v:'cost',label:'Cost'},{v:'requests',label:'Requests'}].map(s=>(
                                        <button key={s.v} onClick={()=>setTopOrgsSort(s.v)}
                                            className={`px-2.5 py-1 rounded-lg transition cursor-pointer ${topOrgsSort===s.v?'bg-white dark:bg-slate-800 text-indigo-600 shadow-sm':'text-slate-500 hover:text-slate-800 dark:text-slate-300'}`}>
                                            {s.label}
                                        </button>
                                    ))}
                                </div>
                            </div>
                        </div>

                        {(() => {
                            let orgs = topOrgsSort==='cost' ? (topOrgsData?.by_cost||[]) : (topOrgsData?.by_tokens||[]);
                            if (topOrgsSort==='requests') orgs = [...orgs].sort((a,b)=>(b.request_count||0)-(a.request_count||0));
                            if (topOrgsBillingFilter==='PAYG') orgs=orgs.filter(o=>o.billing_mode==='PAYG');
                            else if (topOrgsBillingFilter==='Prepaid') orgs=orgs.filter(o=>o.billing_mode!=='PAYG');
                            else if (topOrgsBillingFilter==='blocked') orgs=orgs.filter(o=>o.is_blocked);

                            if (!orgs.length) return (
                                <div className="py-10 text-center text-slate-400 text-xs border border-dashed border-slate-200 dark:border-slate-700 rounded-xl">
                                    No organizations match the selected filter.
                                </div>
                            );

                            const maxTok = Math.max(...orgs.map(o=>o.total_tokens||0), 1);
                            return (
                                <div className="space-y-2 max-h-96 overflow-y-auto pr-1 custom-scrollbar">
                                    {orgs.map((org,rank)=>(
                                        <div key={org.organization_name} className="p-3 bg-slate-50 dark:bg-slate-900/40 rounded-xl border border-slate-100 dark:border-slate-750 hover:border-indigo-200 dark:hover:border-indigo-800 transition group">
                                            <div className="flex items-center justify-between gap-3">
                                                {/* Rank + Name */}
                                                <div className="flex items-center gap-2.5 min-w-0">
                                                    <span className={`w-7 h-7 rounded-lg text-xs font-bold flex items-center justify-center shrink-0 ${
                                                        rank===0?'bg-amber-100 text-amber-800 dark:bg-amber-950/60 dark:text-amber-300 border border-amber-300':
                                                        rank===1?'bg-slate-200 text-slate-700 dark:bg-slate-700 dark:text-slate-200':
                                                        rank===2?'bg-orange-50 text-orange-700 dark:bg-orange-950/30 dark:text-orange-400':
                                                        'bg-slate-100 text-slate-500 dark:bg-slate-800 dark:text-slate-400'
                                                    }`}>#{rank+1}</span>
                                                    <div className="min-w-0">
                                                        <div className="flex items-center gap-1.5 flex-wrap">
                                                            <span className="text-xs font-bold text-slate-900 dark:text-white truncate">{org.organization_name}</span>
                                                            <span className={`px-1.5 py-0.2 rounded text-[9px] font-semibold ${org.billing_mode==='PAYG'?'bg-amber-100 text-amber-700 dark:bg-amber-950/50 dark:text-amber-300':'bg-indigo-100 text-indigo-700 dark:bg-indigo-950/50 dark:text-indigo-300'}`}>
                                                                {org.billing_mode}
                                                            </span>
                                                            {org.is_blocked && <span className="px-1.5 py-0.2 rounded text-[9px] font-semibold bg-rose-100 text-rose-700 dark:bg-rose-950/50 dark:text-rose-300">BLOCKED</span>}
                                                        </div>
                                                        <span className="text-[10px] text-slate-400 font-mono">{Number(org.request_count).toLocaleString()} requests</span>
                                                    </div>
                                                </div>
                                                {/* Metrics */}
                                                <div className="flex items-center gap-4 shrink-0">
                                                    <div className="text-right hidden sm:block">
                                                        <div className="text-xs font-bold text-slate-900 dark:text-white font-mono">{Number(org.total_tokens).toLocaleString()} <span className="text-[10px] text-slate-400">tok</span></div>
                                                        <div className="text-[10px] text-emerald-600 dark:text-emerald-400 font-mono">${Number(org.total_cost_usd).toFixed(2)}</div>
                                                    </div>
                                                    <button onClick={()=>handleOpenOrgDrilldown(org.organization_name)}
                                                        className="p-1.5 rounded-lg text-slate-400 hover:text-indigo-600 hover:bg-indigo-50 dark:hover:bg-indigo-950/50 transition cursor-pointer" title="Inspect org telemetry">
                                                        <Eye className="w-4 h-4"/>
                                                    </button>
                                                </div>
                                            </div>
                                            {/* Consumption Bar */}
                                            <div className="mt-2.5 w-full bg-slate-200 dark:bg-slate-700 h-1.5 rounded-full overflow-hidden">
                                                <div className="h-full bg-indigo-500 transition-all duration-500 rounded-full" style={{width:`${Math.min(100,Math.max(1,(org.total_tokens/maxTok)*100))}%`}}/>
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            );
                        })()}
                    </div>

                    {/* ── Alert & Action Center ── */}
                    <div className="bg-white dark:bg-slate-800 p-5 rounded-2xl border border-slate-200/80 dark:border-slate-700 shadow-sm space-y-4">
                        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                            <div>
                                <h3 className="text-base font-bold text-slate-900 dark:text-white flex items-center gap-2">
                                    <AlertTriangle className="w-4 h-4 text-amber-500"/>Operational Health &amp; Action Center
                                </h3>
                                <p className="text-xs text-slate-400 mt-0.5">Live exceptions, limit breaches, low balance warnings, and pending quota approvals.</p>
                            </div>
                            <div className="flex items-center gap-2">
                                <span className="px-2.5 py-1 rounded-full text-xs font-bold bg-slate-100 dark:bg-slate-700 text-slate-700 dark:text-slate-300 font-mono">
                                    {alertsData?.total_alerts||0} alerts
                                </span>
                                {/* Alert Type Filter */}
                                <div className="flex bg-slate-100 dark:bg-slate-700/60 p-1 rounded-xl text-xs font-semibold">
                                    {[{v:'all',label:'All'},{v:'critical',label:'Critical'},{v:'warning',label:'Warnings'},{v:'action',label:'Actions'}].map(f=>(
                                        <button key={f.v} onClick={()=>setAlertTypeFilter(f.v)}
                                            className={`px-2.5 py-1 rounded-lg transition cursor-pointer ${alertTypeFilter===f.v?'bg-white dark:bg-slate-800 text-indigo-600 shadow-sm':'text-slate-500 hover:text-slate-800 dark:text-slate-300'}`}>
                                            {f.label}
                                        </button>
                                    ))}
                                </div>
                            </div>
                        </div>

                        {(!alertsData || alertsData.total_alerts === 0) ? (
                            <div className="p-8 text-center bg-emerald-50 dark:bg-emerald-950/20 rounded-xl border border-emerald-200 dark:border-emerald-800">
                                <CheckCircle2 className="w-8 h-8 text-emerald-500 mx-auto mb-2"/>
                                <h4 className="text-sm font-bold text-emerald-800 dark:text-emerald-200">All Tenant Operations Healthy</h4>
                                <p className="text-xs text-emerald-600 dark:text-emerald-400 mt-1">No limit breaches, blocked holds, or pending quota requests.</p>
                            </div>
                        ) : (
                            <div className="space-y-4">
                                {/* Critical */}
                                {(alertTypeFilter==='all'||alertTypeFilter==='critical') && alertsData.critical?.length>0 && (
                                    <div>
                                        <div className="flex items-center gap-2 mb-2 text-xs font-bold text-rose-600 dark:text-rose-400 uppercase tracking-wider">
                                            <Ban className="w-4 h-4"/><span>Critical ({alertsData.critical.length})</span>
                                        </div>
                                        <div className="space-y-2">
                                            {alertsData.critical.map((item,idx)=>(
                                                <div key={idx} className="p-3 bg-rose-50 dark:bg-rose-950/30 border border-rose-200 dark:border-rose-800 rounded-xl flex items-start justify-between gap-3">
                                                    <div className="min-w-0">
                                                        <div className="flex items-center gap-2 flex-wrap">
                                                            <span className="text-xs font-bold text-rose-900 dark:text-rose-200">{item.organization_name}</span>
                                                            <span className="px-1.5 py-0.2 rounded text-[9px] font-bold bg-rose-200 text-rose-800 dark:bg-rose-900 dark:text-rose-200 uppercase">{item.alert_type}</span>
                                                        </div>
                                                        <p className="text-xs text-rose-700 dark:text-rose-300 font-medium mt-1">{item.message}</p>
                                                    </div>
                                                    <button onClick={()=>{setSearchQuery(item.organization_name);setActiveTab('wallets');}}
                                                        className="shrink-0 text-[11px] text-rose-700 dark:text-rose-300 font-semibold hover:underline flex items-center gap-1 cursor-pointer whitespace-nowrap">
                                                        Manage <ChevronRight className="w-3 h-3"/>
                                                    </button>
                                                </div>
                                            ))}
                                        </div>
                                    </div>
                                )}
                                {/* Warnings */}
                                {(alertTypeFilter==='all'||alertTypeFilter==='warning') && alertsData.warning?.length>0 && (
                                    <div>
                                        <div className="flex items-center gap-2 mb-2 text-xs font-bold text-amber-600 dark:text-amber-400 uppercase tracking-wider">
                                            <AlertTriangle className="w-4 h-4"/><span>Warnings ({alertsData.warning.length})</span>
                                        </div>
                                        <div className="space-y-2">
                                            {alertsData.warning.map((item,idx)=>(
                                                <div key={idx} className="p-3 bg-amber-50 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-800 rounded-xl flex items-start justify-between gap-3">
                                                    <div className="min-w-0">
                                                        <div className="flex items-center gap-2 flex-wrap">
                                                            <span className="text-xs font-bold text-amber-900 dark:text-amber-200">{item.organization_name}</span>
                                                            <span className="px-1.5 py-0.2 rounded text-[9px] font-bold bg-amber-200 text-amber-800 dark:bg-amber-900 dark:text-amber-200 uppercase">{item.alert_type}</span>
                                                        </div>
                                                        <p className="text-xs text-amber-700 dark:text-amber-300 font-medium mt-1">{item.message}</p>
                                                    </div>
                                                    <button onClick={()=>{setSearchQuery(item.organization_name);setActiveTab('wallets');}}
                                                        className="shrink-0 text-[11px] text-amber-700 dark:text-amber-300 font-semibold hover:underline flex items-center gap-1 cursor-pointer whitespace-nowrap">
                                                        Inspect <ChevronRight className="w-3 h-3"/>
                                                    </button>
                                                </div>
                                            ))}
                                        </div>
                                    </div>
                                )}
                                {/* Action Required */}
                                {(alertTypeFilter==='all'||alertTypeFilter==='action') && alertsData.action_required?.length>0 && (
                                    <div>
                                        <div className="flex items-center gap-2 mb-2 text-xs font-bold text-indigo-600 dark:text-indigo-400 uppercase tracking-wider">
                                            <Clock className="w-4 h-4"/><span>Action Required ({alertsData.action_required.length})</span>
                                        </div>
                                        <div className="space-y-2">
                                            {alertsData.action_required.map((item,idx)=>(
                                                <div key={idx} className="p-3 bg-indigo-50 dark:bg-indigo-950/30 border border-indigo-200 dark:border-indigo-800 rounded-xl flex items-start justify-between gap-3">
                                                    <div className="min-w-0">
                                                        <div className="flex items-center gap-2 flex-wrap">
                                                            <span className="text-xs font-bold text-indigo-900 dark:text-indigo-200">{item.organization_name}</span>
                                                            <span className="px-1.5 py-0.2 rounded text-[9px] font-bold bg-indigo-200 text-indigo-800 dark:bg-indigo-900 dark:text-indigo-200 uppercase">QUOTA REQUEST</span>
                                                        </div>
                                                        <p className="text-xs text-indigo-700 dark:text-indigo-300 font-medium mt-1">{item.message}</p>
                                                    </div>
                                                    <button onClick={()=>setActiveTab('payg')}
                                                        className="shrink-0 text-[11px] text-indigo-700 dark:text-indigo-300 font-semibold hover:underline flex items-center gap-1 cursor-pointer whitespace-nowrap">
                                                        Review <ChevronRight className="w-3 h-3"/>
                                                    </button>
                                                </div>
                                            ))}
                                        </div>
                                    </div>
                                )}
                                {(alertTypeFilter!=='all') && (
                                    alertsData[alertTypeFilter==='warning'?'warning':alertTypeFilter==='critical'?'critical':'action_required']?.length===0 && (
                                        <div className="p-4 text-center text-slate-400 text-xs border border-dashed border-slate-200 dark:border-slate-700 rounded-xl">
                                            No {alertTypeFilter} alerts.
                                        </div>
                                    )
                                )}
                            </div>
                        )}
                    </div>
                </div>
            )}


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
                                                         <div className="relative group inline-block">
                                                             <span className="px-2.5 py-1 text-[11px] font-bold rounded-full bg-amber-500/10 text-amber-700 dark:text-amber-400 border border-amber-500/20 whitespace-nowrap cursor-help inline-flex items-center gap-1.5 shadow-sm">
                                                                 <span className="w-1.5 h-1.5 rounded-full bg-amber-500 animate-pulse"></span>
                                                                 PAYG Active
                                                             </span>
                                                             {/* Popover Tooltip */}
                                                             <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 w-48 p-3 bg-slate-900/95 dark:bg-slate-950/95 text-slate-200 rounded-xl shadow-xl border border-slate-700/50 dark:border-slate-800/50 opacity-0 group-hover:opacity-100 pointer-events-none transition-opacity duration-200 z-50 text-left backdrop-blur-sm space-y-2">
                                                                 <div className="text-[10px] font-bold text-slate-400 uppercase tracking-wider border-b border-slate-700/40 pb-1 mb-1">
                                                                     PAYG Spending Limits
                                                                 </div>
                                                                 <div className="space-y-1 text-xs">
                                                                     <div className="flex justify-between items-center">
                                                                         <span className="text-slate-400">Current Spend:</span>
                                                                         <span className="font-bold text-white font-mono">${Number(org.payg_current_spend_usd || 0).toFixed(2)}</span>
                                                                     </div>
                                                                     <div className="flex justify-between items-center">
                                                                         <span className="text-slate-400">Soft Limit:</span>
                                                                         <span className="font-semibold text-amber-400 font-mono">
                                                                             {org.payg_soft_limit_usd ? `$${Number(org.payg_soft_limit_usd).toFixed(2)}` : 'None'}
                                                                         </span>
                                                                     </div>
                                                                     <div className="flex justify-between items-center">
                                                                         <span className="text-slate-400">Hard Limit:</span>
                                                                         <span className="font-semibold text-rose-400 font-mono">
                                                                             {org.payg_hard_limit_usd ? `$${Number(org.payg_hard_limit_usd).toFixed(2)}` : 'None'}
                                                                         </span>
                                                                     </div>
                                                                 </div>
                                                             </div>
                                                         </div>
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
                                                                    {org.payg_soft_limit_usd ? `$${Number(org.payg_soft_limit_usd).toFixed(2)}` : '∞'} / {org.payg_hard_limit_usd ? `$${Number(org.payg_hard_limit_usd).toFixed(2)}` : '∞'}
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
                                                        {org.payg_enabled ? (
                                                            <button
                                                                onClick={() => setLimitsModal({
                                                                    open: true,
                                                                    orgName: org.organization_name,
                                                                    softLimit: org.payg_soft_limit_usd || '',
                                                                    hardLimit: org.payg_hard_limit_usd || '',
                                                                    billingEmail: org.payg_billing_email || ''
                                                                })}
                                                                className="px-2.5 py-1.5 bg-amber-600 hover:bg-amber-700 text-white rounded-lg text-xs font-semibold inline-flex items-center gap-1 transition shadow-sm shrink-0 cursor-pointer animate-in fade-in duration-200"
                                                                title="Configure PAYG soft and hard spending limits"
                                                            >
                                                                <Edit className="w-3.5 h-3.5" />
                                                                <span>Configure Limits</span>
                                                            </button>
                                                        ) : (
                                                            <button
                                                                onClick={() => setPurchaseModal({ open: true, orgName: org.organization_name, amount: '', remarks: '' })}
                                                                className="px-2.5 py-1.5 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg text-xs font-semibold inline-flex items-center gap-1 transition shadow-sm shrink-0 cursor-pointer"
                                                                title="Inject / Credit tokens to this organization"
                                                            >
                                                                <Plus className="w-3.5 h-3.5" />
                                                                <span>Inject Tokens</span>
                                                            </button>
                                                        )}
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
                                                         : req.request_type === 'PAYG_DISABLEMENT'
                                                             ? 'bg-rose-50 text-rose-700 border-rose-200 dark:bg-rose-950/40 dark:text-rose-300 dark:border-rose-800'
                                                             : 'bg-amber-50 text-amber-700 border-amber-200 dark:bg-amber-950/40 dark:text-amber-300 dark:border-amber-800'
                                                 }`}>
                                                     {req.request_type === 'TOKEN_INCREASE' ? 'Token Increase' : req.request_type === 'PAYG_DISABLEMENT' ? 'Prepaid Switch' : 'PAYG Enable'}
                                                 </span>
                                             </td>
                                             <td className="px-4 py-3 font-mono font-bold text-indigo-600 dark:text-indigo-400">
                                                 {req.request_type === 'TOKEN_INCREASE'
                                                     ? `+${Number(req.requested_tokens || 0).toLocaleString()} tokens`
                                                     : req.request_type === 'PAYG_DISABLEMENT'
                                                         ? 'Prepaid Mode'
                                                         : 'Unlimited PAYG'
                                                 }
                                             </td>
                                            <td className="px-4 py-3 text-slate-500 dark:text-slate-400 text-xs" title={req.requester_email || ''}>
                                                {req.requester_name || `User #${req.requested_by}`}
                                            </td>
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

            {/* MODAL 0: Configure PAYG Limits Modal */}
            {limitsModal.open && (
                <div className="fixed inset-0 bg-black/55 backdrop-blur-sm z-50 flex items-center justify-center p-4 animate-in fade-in duration-200">
                    <div className="bg-white dark:bg-slate-800 rounded-2xl max-w-md w-full p-6 border border-slate-200 dark:border-slate-700 shadow-2xl">
                        <h3 className="text-lg font-bold text-slate-900 dark:text-white mb-1 flex items-center gap-2">
                            <DollarSign className="w-5 h-5 text-amber-600 dark:text-amber-400" />
                            Configure PAYG Limits: {limitsModal.orgName}
                        </h3>
                        <p className="text-xs text-slate-500 dark:text-slate-400 mb-4">
                            Set spending controls and billing email for Pay As You Go post-paid consumption.
                        </p>
                        <form onSubmit={handleUpdateLimits} className="space-y-4">
                            {error && (
                                <div className="p-3 bg-rose-50 dark:bg-rose-950/40 border border-rose-200 dark:border-rose-800 rounded-xl flex items-center gap-2 text-rose-700 dark:text-rose-300 text-xs">
                                    <AlertCircle className="w-4 h-4 flex-shrink-0" />
                                    <span className="font-semibold">{error}</span>
                                </div>
                            )}
                            <div>
                                <div className="flex justify-between items-center mb-1">
                                    <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300">
                                        Soft Spending Limit (USD)
                                    </label>
                                    {limitsModal.softLimit && (
                                        <button
                                            type="button"
                                            onClick={() => setLimitsModal({ ...limitsModal, softLimit: '' })}
                                            className="text-[10px] text-rose-500 hover:text-rose-700 font-semibold cursor-pointer"
                                        >
                                            Clear Limit
                                        </button>
                                    )}
                                </div>
                                <input
                                    type="number"
                                    step="0.01"
                                    min="0"
                                    value={limitsModal.softLimit}
                                    onChange={(e) => setLimitsModal({ ...limitsModal, softLimit: e.target.value })}
                                    placeholder="e.g. 50.00"
                                    className="w-full px-4 py-2.5 rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900 text-slate-900 dark:text-white font-mono text-sm focus:ring-2 focus:ring-amber-500 focus:outline-none transition-all"
                                />
                                <p className="text-[10px] text-slate-400 mt-1">
                                    Triggers notifications when spending crosses this threshold.
                                </p>
                            </div>
                            <div>
                                <div className="flex justify-between items-center mb-1">
                                    <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300">
                                        Hard Spending Limit (USD)
                                    </label>
                                    {limitsModal.hardLimit && (
                                        <button
                                            type="button"
                                            onClick={() => setLimitsModal({ ...limitsModal, hardLimit: '' })}
                                            className="text-[10px] text-rose-500 hover:text-rose-700 font-semibold cursor-pointer"
                                        >
                                            Clear Limit
                                        </button>
                                    )}
                                </div>
                                <input
                                    type="number"
                                    step="0.01"
                                    min="0"
                                    value={limitsModal.hardLimit}
                                    onChange={(e) => setLimitsModal({ ...limitsModal, hardLimit: e.target.value })}
                                    placeholder="e.g. 100.00"
                                    className="w-full px-4 py-2.5 rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900 text-slate-900 dark:text-white font-mono text-sm focus:ring-2 focus:ring-amber-500 focus:outline-none transition-all"
                                />
                                <p className="text-[10px] text-slate-400 mt-1">
                                    Blocks all user analysis executions once spending reaches this cap.
                                </p>
                            </div>
                            <div>
                                <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                                    Billing Email Address
                                </label>
                                <input
                                    type="email"
                                    value={limitsModal.billingEmail}
                                    onChange={(e) => setLimitsModal({ ...limitsModal, billingEmail: e.target.value })}
                                    placeholder="e.g. billing@company.com"
                                    className="w-full px-4 py-2.5 rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900 text-slate-900 dark:text-white text-sm focus:ring-2 focus:ring-amber-500 focus:outline-none transition-all"
                                />
                                <p className="text-[10px] text-slate-400 mt-1">
                                    Recipient email for monthly invoices and limit alerts.
                                </p>
                            </div>
                            <div className="flex justify-end gap-3 mt-6">
                                <button
                                    type="button"
                                    onClick={() => { setError(''); setLimitsModal({ open: false, orgName: '', softLimit: '', hardLimit: '', billingEmail: '' }); }}
                                    className="px-4 py-2 text-sm font-semibold text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-700 rounded-xl transition cursor-pointer"
                                >
                                    Cancel
                                </button>
                                <button
                                    type="submit"
                                    disabled={actionLoading}
                                    className="px-4 py-2 text-sm font-semibold bg-amber-600 hover:bg-amber-700 text-white rounded-xl transition cursor-pointer"
                                >
                                    {actionLoading ? 'Saving...' : 'Save Configuration'}
                                </button>
                            </div>
                        </form>
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

            {/* MODAL 7: Organization Drill-down Modal */}
            {selectedOrgModal && (
                <div className="fixed inset-0 bg-slate-900/60 backdrop-blur-sm z-50 flex items-center justify-center p-4">
                    <div className="bg-white dark:bg-slate-800 rounded-2xl max-w-2xl w-full p-6 border border-slate-200/80 dark:border-slate-700 shadow-2xl animate-in zoom-in-95 duration-200 space-y-4">
                        <div className="flex justify-between items-start">
                            <div className="flex items-center gap-3">
                                <div className="p-2.5 rounded-xl bg-indigo-50 dark:bg-indigo-950/40 text-indigo-600 dark:text-indigo-400">
                                    <Building2 className="w-6 h-6" />
                                </div>
                                <div>
                                    <h3 className="text-lg font-bold text-slate-900 dark:text-white flex items-center gap-2">
                                        {selectedOrgModal}
                                    </h3>
                                    <p className="text-xs text-slate-500 dark:text-slate-400">
                                        Organization detailed telemetry & user consumption breakdown.
                                    </p>
                                </div>
                            </div>
                            <button
                                onClick={() => setSelectedOrgModal(null)}
                                className="text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 p-1.5 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-700 transition cursor-pointer"
                            >
                                <XCircle className="w-5 h-5" />
                            </button>
                        </div>

                        {orgDetailLoading ? (
                            <div className="py-12 flex flex-col items-center justify-center gap-2 text-slate-400 text-xs">
                                <RefreshCw className="w-5 h-5 animate-spin text-indigo-500" />
                                <span>Loading organization telemetry...</span>
                            </div>
                        ) : orgDetailData ? (
                            <div className="space-y-4">
                                {/* Key Org Metrics */}
                                <div className="grid grid-cols-3 gap-3 bg-slate-50 dark:bg-slate-900/50 p-3.5 rounded-xl border border-slate-200/60 dark:border-slate-700 text-xs">
                                    <div>
                                        <span className="text-[10px] text-slate-400 block uppercase font-bold">Remaining Balance</span>
                                        <span className="text-sm font-bold text-slate-800 dark:text-slate-100 font-mono">
                                            {Number(orgDetailData.remaining_balance).toLocaleString()} tokens
                                        </span>
                                    </div>
                                    <div>
                                        <span className="text-[10px] text-slate-400 block uppercase font-bold">Lifetime Token Burn</span>
                                        <span className="text-sm font-bold text-indigo-600 dark:text-indigo-400 font-mono">
                                            {Number(orgDetailData.token_burn).toLocaleString()} tokens
                                        </span>
                                    </div>
                                    <div>
                                        <span className="text-[10px] text-slate-400 block uppercase font-bold">Historical Cost</span>
                                        <span className="text-sm font-bold text-emerald-600 dark:text-emerald-400 font-mono">
                                            ${Number(orgDetailData.total_historical_cost).toFixed(2)}
                                        </span>
                                    </div>
                                </div>

                                {/* 7-day Mini Activity */}
                                <div>
                                    <h4 className="text-xs font-bold text-slate-800 dark:text-slate-200 uppercase tracking-wider mb-2">
                                        Recent 7-Day Activity
                                    </h4>
                                    <div className="grid grid-cols-7 gap-1 text-center">
                                        {orgDetailData.daily_usage?.map((d) => (
                                            <div key={d.date} className="p-2 bg-slate-50 dark:bg-slate-900/40 rounded-lg border border-slate-150 dark:border-slate-750">
                                                <div className="text-[9px] text-slate-400 font-mono">{d.date.slice(5)}</div>
                                                <div className="text-xs font-bold text-slate-800 dark:text-slate-200 mt-1 font-mono">
                                                    {d.tokens > 1000 ? `${(d.tokens / 1000).toFixed(1)}k` : d.tokens}
                                                </div>
                                                <div className="text-[9px] text-slate-400 font-mono">{d.requests} req</div>
                                            </div>
                                        ))}
                                    </div>
                                </div>

                                {/* Top Active Users */}
                                <div>
                                    <h4 className="text-xs font-bold text-slate-800 dark:text-slate-200 uppercase tracking-wider mb-2">
                                        Top Users by Consumption
                                    </h4>
                                    {(!orgDetailData.top_users || orgDetailData.top_users.length === 0) ? (
                                        <div className="text-xs text-slate-400 italic py-2">No user usage recorded.</div>
                                    ) : (
                                        <div className="space-y-1.5">
                                            {orgDetailData.top_users.map((u, i) => (
                                                <div key={u.user_id} className="flex justify-between items-center p-2 bg-slate-50 dark:bg-slate-900/30 rounded-lg text-xs font-mono">
                                                    <span className="font-semibold text-slate-700 dark:text-slate-300">User #{u.user_id}</span>
                                                    <span className="font-bold text-indigo-600 dark:text-indigo-400">{Number(u.tokens).toLocaleString()} tokens</span>
                                                </div>
                                            ))}
                                        </div>
                                    )}
                                </div>
                            </div>
                        ) : null}

                        <div className="flex justify-end gap-2 pt-2 border-t border-slate-200 dark:border-slate-700">
                            <button
                                onClick={() => {
                                    const targetOrg = selectedOrgModal;
                                    setSelectedOrgModal(null);
                                    setSearchQuery(targetOrg);
                                    setActiveTab('wallets');
                                }}
                                className="px-4 py-2 text-xs font-semibold bg-indigo-600 hover:bg-indigo-700 text-white rounded-xl transition cursor-pointer"
                            >
                                Manage in Wallets Tab
                            </button>
                            <button
                                onClick={() => setSelectedOrgModal(null)}
                                className="px-4 py-2 text-xs font-semibold text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-700 rounded-xl transition cursor-pointer"
                            >
                                Close
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}
