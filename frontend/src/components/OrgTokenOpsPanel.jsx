import React, { useState, useEffect } from 'react';
import { 
    Coins, Users, ShieldAlert, ArrowRightLeft, PlusCircle, MinusCircle, 
    RefreshCw, AlertCircle, CheckCircle2, DollarSign, Activity, FileText, Ban, Check, MoreVertical
} from 'lucide-react';
import { API_ENDPOINTS } from '../config';

export default function OrgTokenOpsPanel({ user }) {
    const [reserve, setReserve] = useState(null);
    const [usersList, setUsersList] = useState([]);
    const [ledger, setLedger] = useState([]);
    const [dailyUsage, setDailyUsage] = useState([]);
    const [quotaRequests, setQuotaRequests] = useState([]);
    const [loading, setLoading] = useState(true);
    const [actionLoading, setActionLoading] = useState(false);
    const [error, setError] = useState('');
    const [successMessage, setSuccessMessage] = useState('');
    const [openDropdownUserId, setOpenDropdownUserId] = useState(null);
    const [activeSubTab, setActiveSubTab] = useState('users'); // 'users' | 'requests' | 'ledger' | 'reports'

    // Modal States
    const [allocateModal, setAllocateModal] = useState({ open: false, userId: null, userName: '', amount: '', remarks: '' });
    const [reallocateModal, setReallocateModal] = useState({ open: false, fromUserId: null, fromUserName: '', toUserId: '', amount: '' });
    const [revokeModal, setRevokeModal] = useState({ open: false, userId: null, userName: '', amount: '' });
    const [requestModal, setRequestModal] = useState({ open: false, requestType: 'TOKEN_INCREASE', amount: '', remarks: '' });

    const token = localStorage.getItem('token');
    const orgName = user?.organization_name || localStorage.getItem('active_org') || '';

    const formatCurrency = (amount, pricePerToken = 0.000007) => {
        return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format((amount || 0) * pricePerToken);
    };

    const getHeaders = () => ({
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json',
        'X-Organization': orgName
    });

    const fetchData = async () => {
        setLoading(true);
        setError('');
        try {
            const headers = getHeaders();

            // 1. Fetch Org Reserve
            try {
                const resReserve = await fetch(API_ENDPOINTS.TOKENOPS_ORG_RESERVE, { headers });
                if (resReserve.ok) {
                    const data = await resReserve.json();
                    if (data.success) setReserve(data.data);
                }
            } catch (e) {
                console.warn('Failed to load reserve:', e);
            }

            // 2. Fetch User Allocations
            try {
                const resUsers = await fetch(API_ENDPOINTS.TOKENOPS_ORG_USERS, { headers });
                if (resUsers.ok) {
                    const data = await resUsers.json();
                    if (data.success && data.data?.items) {
                        setUsersList(data.data.items);
                    }
                }
            } catch (e) {
                console.warn('Failed to load users:', e);
            }

            // 3. Fetch Quota Requests
            try {
                const resQuota = await fetch(API_ENDPOINTS.TOKENOPS_ORG_QUOTA_REQUESTS, { headers });
                if (resQuota.ok) {
                    const data = await resQuota.json();
                    if (data.success && data.data) {
                        setQuotaRequests(data.data);
                    }
                }
            } catch (e) {
                console.warn('Failed to load quota requests:', e);
            }

            // 4. Fetch Ledger
            try {
                const resLedger = await fetch(API_ENDPOINTS.TOKENOPS_ORG_REPORTS_LEDGER, { headers });
                if (resLedger.ok) {
                    const data = await resLedger.json();
                    if (data.success && data.data?.items) {
                        setLedger(data.data.items);
                    }
                }
            } catch (e) {
                console.warn('Failed to load ledger:', e);
            }

            // 5. Fetch Daily Reports
            try {
                const resDaily = await fetch(API_ENDPOINTS.TOKENOPS_ORG_REPORTS_DAILY, { headers });
                if (resDaily.ok) {
                    const data = await resDaily.json();
                    if (data.success && data.data?.daily_usage) {
                        setDailyUsage(data.data.daily_usage);
                    }
                }
            } catch (e) {
                console.warn('Failed to load daily usage:', e);
            }
        } catch (err) {
            setError(err.message || 'Failed to load organization token operational data.');
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchData();
    }, [orgName]);

    // Handle Submit Quota Request to Super Admin
    const handleQuotaRequest = async (e) => {
        e.preventDefault();
        setActionLoading(true);
        setError('');
        setSuccessMessage('');
        try {
            const body = {
                request_type: requestModal.requestType,
                requested_tokens: requestModal.requestType === 'TOKEN_INCREASE' ? parseInt(requestModal.amount, 10) : 0,
                remarks: requestModal.remarks
            };
            const res = await fetch(API_ENDPOINTS.TOKENOPS_ORG_REQUEST_QUOTA, {
                method: 'POST',
                headers: getHeaders(),
                body: JSON.stringify(body)
            });
            const data = await res.json();
            if (!res.ok || !data.success) {
                throw new Error(data.error?.message || 'Failed to submit quota request.');
            }
            setSuccessMessage(
                requestModal.requestType === 'TOKEN_INCREASE'
                    ? `Token Increase request for ${Number(requestModal.amount).toLocaleString()} tokens submitted! Waiting for Super Admin approval.`
                    : 'PAYG Enablement request submitted! Waiting for Super Admin approval.'
            );
            setRequestModal({ open: false, requestType: 'TOKEN_INCREASE', amount: '', remarks: '' });
            fetchData();
        } catch (err) {
            setError(err.message);
        } finally {
            setActionLoading(false);
        }
    };

    // Handle Allocate
    const handleAllocate = async (e) => {
        e.preventDefault();
        setActionLoading(true);
        setError('');
        setSuccessMessage('');
        const reqAmount = parseInt(allocateModal.amount, 10);
        const availReserved = reserve?.reserved_tokens || 0;
        if (reqAmount > availReserved) {
            setError(`Cannot allocate ${reqAmount.toLocaleString()} tokens. Only ${availReserved.toLocaleString()} tokens are available in your organization's reserve.`);
            setActionLoading(false);
            return;
        }
        try {
            const res = await fetch(API_ENDPOINTS.TOKENOPS_ORG_ALLOCATE, {
                method: 'POST',
                headers: getHeaders(),
                body: JSON.stringify({
                    user_id: parseInt(allocateModal.userId, 10),
                    token_amount: reqAmount,
                    remarks: allocateModal.remarks
                })
            });
            const data = await res.json();
            if (!res.ok || !data.success) {
                throw new Error(data.error?.message || 'Failed to allocate tokens.');
            }
            const targetName = allocateModal.userName || usersList.find(u => String(u.user_id) === String(allocateModal.userId))?.name || `User #${allocateModal.userId}`;
            setSuccessMessage(`Successfully allocated ${Number(allocateModal.amount).toLocaleString()} tokens to ${targetName}`);
            setAllocateModal({ open: false, userId: null, userName: '', amount: '', remarks: '' });
            fetchData();
        } catch (err) {
            setError(err.message);
        } finally {
            setActionLoading(false);
        }
    };

    // Handle Reallocate
    const handleReallocate = async (e) => {
        e.preventDefault();
        setActionLoading(true);
        setError('');
        setSuccessMessage('');
        const reqAmount = parseInt(reallocateModal.amount, 10);
        const sourceUser = usersList.find(u => String(u.user_id) === String(reallocateModal.fromUserId));
        const sourceRemaining = sourceUser?.remaining_tokens || 0;
        const sourceName = reallocateModal.fromUserName || sourceUser?.name || `User #${reallocateModal.fromUserId}`;
        if (reqAmount > sourceRemaining) {
            setError(`Cannot transfer ${reqAmount.toLocaleString()} tokens. ${sourceName} only has ${sourceRemaining.toLocaleString()} tokens remaining.`);
            setActionLoading(false);
            return;
        }
        try {
            const res = await fetch(API_ENDPOINTS.TOKENOPS_ORG_REALLOCATE, {
                method: 'PUT',
                headers: getHeaders(),
                body: JSON.stringify({
                    source_user_id: parseInt(reallocateModal.fromUserId, 10),
                    destination_user_id: parseInt(reallocateModal.toUserId, 10),
                    token_amount: reqAmount
                })
            });
            const data = await res.json();
            if (!res.ok || !data.success) {
                throw new Error(data.error?.message || 'Failed to transfer tokens.');
            }
            const destUser = usersList.find(u => String(u.user_id) === String(reallocateModal.toUserId));
            const destName = destUser ? (destUser.name || destUser.email) : `User #${reallocateModal.toUserId}`;
            setSuccessMessage(`Successfully transferred ${Number(reallocateModal.amount).toLocaleString()} tokens from ${sourceName} to ${destName}`);
            setReallocateModal({ open: false, fromUserId: null, fromUserName: '', toUserId: '', amount: '' });
            fetchData();
        } catch (err) {
            setError(err.message);
        } finally {
            setActionLoading(false);
        }
    };

    // Handle Revoke
    const handleRevoke = async (e) => {
        e.preventDefault();
        setActionLoading(true);
        setError('');
        setSuccessMessage('');
        const reqAmount = parseInt(revokeModal.amount, 10);
        const targetUser = usersList.find(u => String(u.user_id) === String(revokeModal.userId));
        const userRemaining = targetUser?.remaining_tokens || 0;
        const targetName = revokeModal.userName || targetUser?.name || `User #${revokeModal.userId}`;
        if (reqAmount > userRemaining) {
            setError(`Cannot revoke ${reqAmount.toLocaleString()} tokens. ${targetName} only has ${userRemaining.toLocaleString()} tokens remaining.`);
            setActionLoading(false);
            return;
        }
        try {
            const res = await fetch(API_ENDPOINTS.TOKENOPS_ORG_REVOKE, {
                method: 'POST',
                headers: getHeaders(),
                body: JSON.stringify({
                    user_id: parseInt(revokeModal.userId, 10),
                    token_amount: reqAmount
                })
            });
            const data = await res.json();
            if (!res.ok || !data.success) {
                throw new Error(data.error?.message || 'Failed to revoke tokens.');
            }
            setSuccessMessage(`Successfully revoked ${Number(revokeModal.amount).toLocaleString()} tokens from ${targetName} back to Org Reserve.`);
            setRevokeModal({ open: false, userId: null, userName: '', amount: '' });
            fetchData();
        } catch (err) {
            setError(err.message);
        } finally {
            setActionLoading(false);
        }
    };

    // Handle Block/Unblock User
    const handleToggleBlock = async (userId, currentBlocked) => {
        setActionLoading(true);
        setError('');
        try {
            const endpoint = currentBlocked
                ? API_ENDPOINTS.TOKENOPS_ORG_UNBLOCK_USER
                : API_ENDPOINTS.TOKENOPS_ORG_BLOCK_USER;
            const res = await fetch(endpoint, {
                method: 'POST',
                headers: getHeaders(),
                body: JSON.stringify({ user_id: userId })
            });
            const data = await res.json();
            if (!res.ok || !data.success) {
                throw new Error(data.error?.message || 'Failed to toggle block status.');
            }
            const targetUser = usersList.find(u => String(u.user_id) === String(userId));
            const userName = targetUser ? (targetUser.name || targetUser.email) : `User #${userId}`;
            const actionStr = currentBlocked ? 'unblocked' : 'blocked';
            setSuccessMessage(`Successfully ${actionStr} ${userName}.`);
            fetchData();
        } catch (err) {
            setError(err.message);
        } finally {
            setActionLoading(false);
        }
    };

    return (
        <div className="space-y-6">
            {/* Header & Refresh */}
            <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 bg-white dark:bg-slate-800 p-6 rounded-2xl border border-slate-200 dark:border-slate-700 shadow-sm">
                <div>
                    <h2 className="text-xl font-bold text-slate-900 dark:text-white flex items-center gap-2">
                        <Coins className="w-6 h-6 text-indigo-600 dark:text-indigo-400" />
                        TokenOps Quota & Reserve Management
                    </h2>
                    <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
                        Control token quotas, divide reserve tokens among users, and request quota increases for <span className="font-semibold text-slate-700 dark:text-slate-300">{orgName}</span>.
                    </p>
                </div>
                <div className="flex items-center gap-2">
                    <button
                        onClick={() => { setError(''); setRequestModal({ open: true, requestType: 'TOKEN_INCREASE', amount: '', remarks: '' }); }}
                        className="flex items-center gap-2 px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-xl transition text-sm font-semibold shadow-sm cursor-pointer"
                    >
                        <PlusCircle className="w-4 h-4" />
                        Request Quota / PAYG
                    </button>
                    <button 
                        onClick={fetchData} 
                        disabled={loading}
                        className="flex items-center gap-2 px-4 py-2 bg-slate-100 hover:bg-slate-200 dark:bg-slate-700 dark:hover:bg-slate-600 text-slate-700 dark:text-slate-200 rounded-xl transition text-sm font-medium"
                    >
                        <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
                        Refresh
                    </button>
                </div>
            </div>

            {/* Pending Requests Alert Banner */}
            {quotaRequests.some(r => r.status === 'REQUESTED') && (
                <div className="p-4 bg-amber-50 dark:bg-amber-950/40 border border-amber-200 dark:border-amber-800 rounded-xl flex items-center gap-3 text-amber-800 dark:text-amber-300 text-sm">
                    <AlertCircle className="w-5 h-5 flex-shrink-0" />
                    <span>
                        <strong>Pending Quota Request:</strong> A request for{' '}
                        {quotaRequests.find(r => r.status === 'REQUESTED')?.request_type === 'TOKEN_INCREASE'
                            ? `+${Number(quotaRequests.find(r => r.status === 'REQUESTED')?.requested_tokens || 0).toLocaleString()} tokens`
                            : 'PAYG Enablement'}{' '}
                        is currently awaiting Super Admin approval.
                    </span>
                </div>
            )}

            {/* Error & Success Alerts */}
            {error && (
                <div className="p-4 bg-rose-50 dark:bg-rose-950/40 border border-rose-200 dark:border-rose-800 rounded-xl flex items-center gap-3 text-rose-700 dark:text-rose-300 text-sm">
                    <AlertCircle className="w-5 h-5 flex-shrink-0" />
                    <span>{error}</span>
                </div>
            )}
            {successMessage && (
                <div className="p-4 bg-emerald-50 dark:bg-emerald-950/40 border border-emerald-200 dark:border-emerald-800 rounded-xl flex items-center gap-3 text-emerald-700 dark:text-emerald-300 text-sm">
                    <CheckCircle2 className="w-5 h-5 flex-shrink-0" />
                    <span>{successMessage}</span>
                </div>
            )}

            {/* KPI Cards: Organization Current Limits */}
            {reserve && (
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4">
                    <div className="bg-white dark:bg-slate-800 p-5 rounded-xl border border-slate-200 dark:border-slate-700 shadow-sm">
                        <span className="text-xs font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wider">Total Approved Value</span>
                        <div className="text-2xl font-bold text-slate-900 dark:text-white mt-2">
                            {formatCurrency(reserve.purchased_tokens, reserve.reference_price)}
                        </div>
                        <span className="text-[11px] text-slate-400 mt-1 block font-mono">{Number(reserve.purchased_tokens || 0).toLocaleString()} tokens</span>
                    </div>
                    <div className="bg-indigo-50/50 dark:bg-indigo-950/20 p-5 rounded-xl border border-indigo-200 dark:border-indigo-800 shadow-sm">
                        <span className="text-xs font-semibold text-indigo-600 dark:text-indigo-400 uppercase tracking-wider">In Org Reserve</span>
                        <div className="text-2xl font-bold text-indigo-700 dark:text-indigo-300 mt-2">
                            {formatCurrency(reserve.reserved_tokens, reserve.reference_price)}
                        </div>
                        <span className="text-[11px] text-indigo-500 mt-1 block font-medium font-mono">{Number(reserve.reserved_tokens || 0).toLocaleString()} tokens</span>
                    </div>
                    <div className="bg-white dark:bg-slate-800 p-5 rounded-xl border border-slate-200 dark:border-slate-700 shadow-sm">
                        <span className="text-xs font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wider">Allocated Value</span>
                        <div className="text-2xl font-bold text-slate-900 dark:text-white mt-2">
                            {formatCurrency(reserve.allocated_tokens, reserve.reference_price)}
                        </div>
                        <span className="text-[11px] text-slate-400 mt-1 block font-mono">{Number(reserve.allocated_tokens || 0).toLocaleString()} tokens</span>
                    </div>
                    <div className="bg-white dark:bg-slate-800 p-5 rounded-xl border border-slate-200 dark:border-slate-700 shadow-sm">
                        <span className="text-xs font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wider">Consumed Value</span>
                        <div className="text-2xl font-bold text-rose-600 dark:text-rose-400 mt-2">
                            {formatCurrency(reserve.consumed_tokens, reserve.reference_price)}
                        </div>
                        <span className="text-[11px] text-slate-400 mt-1 block font-mono">{Number(reserve.consumed_tokens || 0).toLocaleString()} tokens</span>
                    </div>
                    <div className="bg-emerald-50/50 dark:bg-emerald-950/20 p-5 rounded-xl border border-emerald-200 dark:border-emerald-800 shadow-sm">
                        <span className="text-xs font-semibold text-emerald-600 dark:text-emerald-400 uppercase tracking-wider">Net Remaining Value</span>
                        <div className="text-2xl font-bold text-emerald-700 dark:text-emerald-300 mt-2">
                            {formatCurrency(reserve.remaining_tokens, reserve.reference_price)}
                        </div>
                        <span className="text-[11px] text-emerald-600 dark:text-emerald-400 mt-1 block font-mono">{Number(reserve.remaining_tokens || 0).toLocaleString()} tokens</span>
                    </div>
                </div>
            )}

            {/* Sub Tabs */}
            <div className="flex border-b border-slate-200 dark:border-slate-700">
                <button
                    onClick={() => setActiveSubTab('users')}
                    className={`px-5 py-3 text-sm font-semibold flex items-center gap-2 border-b-2 transition ${
                        activeSubTab === 'users'
                            ? 'border-indigo-600 text-indigo-600 dark:text-indigo-400 dark:border-indigo-400'
                            : 'border-transparent text-slate-500 hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-300'
                    }`}
                >
                    <Users className="w-4 h-4" />
                    User Quota Allocations ({usersList.length})
                </button>
                <button
                    onClick={() => setActiveSubTab('requests')}
                    className={`px-5 py-3 text-sm font-semibold flex items-center gap-2 border-b-2 transition ${
                        activeSubTab === 'requests'
                            ? 'border-indigo-600 text-indigo-600 dark:text-indigo-400 dark:border-indigo-400'
                            : 'border-transparent text-slate-500 hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-300'
                    }`}
                >
                    <Coins className="w-4 h-4" />
                    Quota Requests ({quotaRequests.length})
                </button>
                <button
                    onClick={() => setActiveSubTab('ledger')}
                    className={`px-5 py-3 text-sm font-semibold flex items-center gap-2 border-b-2 transition ${
                        activeSubTab === 'ledger'
                            ? 'border-indigo-600 text-indigo-600 dark:text-indigo-400 dark:border-indigo-400'
                            : 'border-transparent text-slate-500 hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-300'
                    }`}
                >
                    <FileText className="w-4 h-4" />
                    Financial Ledger ({ledger.length})
                </button>
                <button
                    onClick={() => setActiveSubTab('reports')}
                    className={`px-5 py-3 text-sm font-semibold flex items-center gap-2 border-b-2 transition ${
                        activeSubTab === 'reports'
                            ? 'border-indigo-600 text-indigo-600 dark:text-indigo-400 dark:border-indigo-400'
                            : 'border-transparent text-slate-500 hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-300'
                    }`}
                >
                    <Activity className="w-4 h-4" />
                    Daily Usage History
                </button>
            </div>

            {/* TAB 1: User Quota Allocations Table */}
            {activeSubTab === 'users' && (
                <div className="bg-white dark:bg-slate-800 rounded-2xl border border-slate-200 dark:border-slate-700 overflow-hidden shadow-sm">
                    <div className="p-4 border-b border-slate-200 dark:border-slate-700 bg-slate-50/50 dark:bg-slate-800/50 flex items-center justify-between">
                        <div>
                            <h3 className="text-sm font-bold text-slate-800 dark:text-slate-200">Team Member Quotas</h3>
                            <p className="text-xs text-slate-500 mt-0.5">Divide and manage token quotas allocated to individual users in your organization.</p>
                        </div>
                        <div className="text-xs text-slate-500 dark:text-slate-400">
                            Available in Org Reserve:{' '}
                            <span className="font-bold text-indigo-600 dark:text-indigo-400 font-mono">
                                {formatCurrency(reserve?.reserved_tokens || 0, reserve?.reference_price || 0.000007)}
                            </span>
                            <span className="text-[10px] text-slate-400 dark:text-slate-500 font-mono ml-1">
                                ({Number(reserve?.reserved_tokens || 0).toLocaleString()} tokens)
                            </span>
                        </div>
                    </div>
                    <div className="overflow-x-auto">
                        <table className="w-full text-left text-sm">
                            <thead className="bg-slate-50 dark:bg-slate-700/50 text-slate-600 dark:text-slate-300 border-b border-slate-200 dark:border-slate-700">
                                <tr>
                                    <th className="px-6 py-4 font-semibold">User</th>
                                    <th className="px-6 py-4 font-semibold">Role</th>
                                    <th className="px-6 py-4 font-semibold">Allocated Value</th>
                                    <th className="px-6 py-4 font-semibold">Consumed Value</th>
                                    <th className="px-6 py-4 font-semibold">Remaining Value</th>
                                    <th className="px-6 py-4 font-semibold">Status</th>
                                    <th className="px-6 py-4 font-semibold text-right">Actions</th>
                                </tr>
                            </thead>
                            <tbody className="divide-y divide-slate-100 dark:divide-slate-700 text-slate-800 dark:text-slate-200">
                                {usersList.length === 0 ? (
                                    <tr>
                                        <td colSpan="7" className="px-6 py-8 text-center text-slate-400">
                                            No organization users found.
                                        </td>
                                    </tr>
                                ) : (
                                    usersList.map((u, index) => (
                                        <tr key={u.user_id} className="hover:bg-slate-50 dark:hover:bg-slate-700/30 transition">
                                            <td className="px-6 py-4">
                                                <div className="flex items-center gap-3">
                                                    <div className="w-8 h-8 rounded-full bg-indigo-100 dark:bg-indigo-900 text-indigo-700 dark:text-indigo-300 flex items-center justify-center font-bold text-xs">
                                                        {(u.name || u.email || 'U')[0].toUpperCase()}
                                                    </div>
                                                    <div>
                                                        <div className="font-bold text-slate-900 dark:text-white">
                                                            {u.name || `User #${u.user_id}`}
                                                        </div>
                                                        <div className="text-xs text-slate-500 dark:text-slate-400">
                                                            {u.email || `ID: ${u.user_id}`}
                                                        </div>
                                                    </div>
                                                </div>
                                            </td>
                                            <td className="px-6 py-4">
                                                <span className="px-2 py-0.5 text-[10px] font-bold rounded bg-slate-100 dark:bg-slate-700 text-slate-600 dark:text-slate-300 uppercase">
                                                    {u.role || 'member'}
                                                </span>
                                            </td>
                                            <td className="px-6 py-4">
                                                <div className="font-semibold">{formatCurrency(u.allocated_tokens, u.reference_price)}</div>
                                                <div className="text-[10px] text-slate-500 font-mono">{Number(u.allocated_tokens || 0).toLocaleString()} tokens</div>
                                            </td>
                                            <td className="px-6 py-4">
                                                <div className="text-rose-600 dark:text-rose-400">{formatCurrency(u.consumed_tokens, u.reference_price)}</div>
                                                <div className="text-[10px] text-slate-500 font-mono">{Number(u.consumed_tokens || 0).toLocaleString()} tokens</div>
                                            </td>
                                            <td className="px-6 py-4">
                                                <div className="font-semibold text-indigo-600 dark:text-indigo-400">{formatCurrency(u.remaining_tokens, u.reference_price)}</div>
                                                <div className="text-[10px] text-slate-500 font-mono">{Number(u.remaining_tokens || 0).toLocaleString()} tokens</div>
                                            </td>
                                            <td className="px-6 py-4">
                                                {u.is_blocked ? (
                                                    <span className="px-2.5 py-1 text-xs font-semibold rounded-full bg-rose-100 text-rose-700 dark:bg-rose-900/40 dark:text-rose-400">
                                                        Blocked
                                                    </span>
                                                ) : (
                                                    <span className="px-2.5 py-1 text-xs font-semibold rounded-full bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-400">
                                                        Active
                                                    </span>
                                                )}
                                            </td>
                                             <td className="px-6 py-4 text-right whitespace-nowrap relative">
                                                <div className="flex items-center justify-end gap-1.5">
                                                    <button
                                                        onClick={() => { setError(''); setAllocateModal({ open: true, userId: u.user_id, userName: u.name || u.email, amount: '', remarks: '' }); }}
                                                        className="px-2.5 py-1.5 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg text-xs font-semibold inline-flex items-center gap-1 transition shadow-sm"
                                                    >
                                                        <PlusCircle className="w-3.5 h-3.5" />
                                                        Allocate
                                                    </button>
                                                    <div className="relative">
                                                        <button
                                                            onClick={() => setOpenDropdownUserId(openDropdownUserId === u.user_id ? null : u.user_id)}
                                                            className="p-1.5 hover:bg-slate-100 dark:hover:bg-slate-700 text-slate-500 dark:text-slate-400 rounded-lg transition"
                                                        >
                                                            <MoreVertical className="w-4 h-4" />
                                                        </button>
                                                        {openDropdownUserId === u.user_id && (
                                                            <>
                                                                <div 
                                                                    className="fixed inset-0 z-10" 
                                                                    onClick={() => setOpenDropdownUserId(null)} 
                                                                />
                                                                <div className={`absolute right-0 w-44 bg-white dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-700 shadow-lg py-1.5 z-20 text-left ${
                                                                    index >= usersList.length - 2
                                                                        ? 'bottom-full mb-1'
                                                                        : 'mt-1'
                                                                }`}>
                                                                    <button
                                                                        onClick={() => {
                                                                            setError('');
                                                                            setOpenDropdownUserId(null);
                                                                            setReallocateModal({ open: true, fromUserId: u.user_id, fromUserName: u.name || u.email, toUserId: '', amount: '' });
                                                                        }}
                                                                        className="w-full px-4 py-2 text-xs font-semibold text-slate-700 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-700/50 flex items-center gap-2 transition"
                                                                    >
                                                                        <ArrowRightLeft className="w-3.5 h-3.5 text-slate-500" />
                                                                        Transfer Quota
                                                                    </button>
                                                                    <button
                                                                        onClick={() => {
                                                                            setError('');
                                                                            setOpenDropdownUserId(null);
                                                                            setRevokeModal({ open: true, userId: u.user_id, userName: u.name || u.email, amount: u.remaining_tokens || '' });
                                                                        }}
                                                                        className="w-full px-4 py-2 text-xs font-semibold text-amber-700 dark:text-amber-400 hover:bg-amber-50 dark:hover:bg-amber-950/20 flex items-center gap-2 transition"
                                                                    >
                                                                        <MinusCircle className="w-3.5 h-3.5 text-amber-500" />
                                                                        Revoke Quota
                                                                    </button>
                                                                    <div className="border-t border-slate-100 dark:border-slate-700 my-1" />
                                                                    <button
                                                                        onClick={() => {
                                                                            setOpenDropdownUserId(null);
                                                                            handleToggleBlock(u.user_id, u.is_blocked);
                                                                        }}
                                                                        className={`w-full px-4 py-2 text-xs font-semibold flex items-center gap-2 transition ${
                                                                            u.is_blocked
                                                                                ? 'text-emerald-700 dark:text-emerald-400 hover:bg-emerald-50 dark:hover:bg-emerald-950/20'
                                                                                : 'text-rose-700 dark:text-rose-400 hover:bg-rose-50 dark:hover:bg-rose-950/20'
                                                                        }`}
                                                                    >
                                                                        {u.is_blocked ? <Check className="w-3.5 h-3.5 text-emerald-500" /> : <Ban className="w-3.5 h-3.5 text-rose-500" />}
                                                                        {u.is_blocked ? 'Unblock User' : 'Block User'}
                                                                    </button>
                                                                </div>
                                                            </>
                                                        )}
                                                    </div>
                                                </div>
                                            </td>
                                        </tr>
                                    ))
                                )}
                            </tbody>
                        </table>
                    </div>
                </div>
            )}

            {/* TAB 2: Quota Requests History */}
            {activeSubTab === 'requests' && (
                <div className="bg-white dark:bg-slate-800 rounded-2xl border border-slate-200 dark:border-slate-700 overflow-hidden shadow-sm">
                    <div className="p-4 border-b border-slate-200 dark:border-slate-700 bg-slate-50/50 dark:bg-slate-800/50 flex items-center justify-between">
                        <div>
                            <h3 className="text-sm font-bold text-slate-800 dark:text-slate-200">Quota Requests to Super Admin</h3>
                            <p className="text-xs text-slate-500 mt-0.5">Track submitted token increases and PAYG requests for your organization.</p>
                        </div>
                        <button
                            onClick={() => { setError(''); setRequestModal({ open: true, requestType: 'TOKEN_INCREASE', amount: '', remarks: '' }); }}
                            className="px-3 py-1.5 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg text-xs font-semibold inline-flex items-center gap-1 shadow-sm"
                        >
                            <PlusCircle className="w-3.5 h-3.5" />
                            New Quota Request
                        </button>
                    </div>
                    <div className="overflow-x-auto">
                        <table className="w-full text-left text-sm">
                            <thead className="bg-slate-50 dark:bg-slate-700/50 text-slate-600 dark:text-slate-300 border-b border-slate-200 dark:border-slate-700">
                                <tr>
                                    <th className="px-6 py-4 font-semibold">Req #</th>
                                    <th className="px-6 py-4 font-semibold">Type</th>
                                    <th className="px-6 py-4 font-semibold">Requested Quota</th>
                                    <th className="px-6 py-4 font-semibold">Reason</th>
                                    <th className="px-6 py-4 font-semibold">Admin Feedback</th>
                                    <th className="px-6 py-4 font-semibold">Status</th>
                                    <th className="px-6 py-4 font-semibold">Submitted</th>
                                </tr>
                            </thead>
                            <tbody className="divide-y divide-slate-100 dark:divide-slate-700 text-slate-800 dark:text-slate-200">
                                {quotaRequests.length === 0 ? (
                                    <tr>
                                        <td colSpan="7" className="px-6 py-8 text-center text-slate-400">
                                            No quota requests submitted yet.
                                        </td>
                                    </tr>
                                ) : (
                                    quotaRequests.map((r) => (
                                        <tr key={r.id} className="hover:bg-slate-50 dark:hover:bg-slate-700/30 transition">
                                            <td className="px-6 py-4 font-mono text-xs text-slate-500">#{r.id}</td>
                                            <td className="px-6 py-4">
                                                <span className={`px-2.5 py-1 text-[11px] font-bold rounded-full uppercase ${
                                                    r.request_type === 'TOKEN_INCREASE'
                                                        ? 'bg-indigo-100 text-indigo-800 dark:bg-indigo-900/40 dark:text-indigo-300'
                                                        : 'bg-purple-100 text-purple-800 dark:bg-purple-900/40 dark:text-purple-300'
                                                }`}>
                                                    {r.request_type === 'TOKEN_INCREASE' ? 'Token Increase' : 'PAYG Enablement'}
                                                </span>
                                            </td>
                                            <td className="px-6 py-4 font-semibold">
                                                {r.request_type === 'TOKEN_INCREASE'
                                                    ? `+${Number(r.requested_tokens || 0).toLocaleString()} Tokens`
                                                    : 'Unlimited PAYG'}
                                            </td>
                                            <td className="px-6 py-4 text-xs text-slate-600 dark:text-slate-300 max-w-xs truncate">
                                                {r.remarks || '—'}
                                            </td>
                                            <td className="px-6 py-4 text-xs text-slate-500 max-w-xs truncate">
                                                {r.admin_notes || '—'}
                                            </td>
                                            <td className="px-6 py-4">
                                                <span className={`px-2.5 py-1 text-xs font-semibold rounded-full ${
                                                    r.status === 'APPROVED'
                                                        ? 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300'
                                                        : r.status === 'REJECTED'
                                                        ? 'bg-rose-100 text-rose-800 dark:bg-rose-900/40 dark:text-rose-300'
                                                        : 'bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300'
                                                }`}>
                                                    {r.status}
                                                </span>
                                            </td>
                                            <td className="px-6 py-4 text-xs text-slate-400">
                                                {r.created_at ? new Date(r.created_at).toLocaleDateString() : '—'}
                                            </td>
                                        </tr>
                                    ))
                                )}
                            </tbody>
                        </table>
                    </div>
                </div>
            )}

            {/* TAB 2: Financial Ledger */}
            {activeSubTab === 'ledger' && (
                <div className="bg-white dark:bg-slate-800 rounded-2xl border border-slate-200 dark:border-slate-700 overflow-hidden shadow-sm">
                    <div className="overflow-x-auto">
                        <table className="w-full text-left text-sm">
                            <thead className="bg-slate-50 dark:bg-slate-700/50 text-slate-600 dark:text-slate-300 border-b border-slate-200 dark:border-slate-700">
                                <tr>
                                    <th className="px-6 py-4 font-semibold">Tx ID</th>
                                    <th className="px-6 py-4 font-semibold">Type</th>
                                    <th className="px-6 py-4 font-semibold">User</th>
                                    <th className="px-6 py-4 font-semibold">Token Delta</th>
                                    <th className="px-6 py-4 font-semibold">Remarks / Ref</th>
                                    <th className="px-6 py-4 font-semibold">Timestamp</th>
                                </tr>
                            </thead>
                            <tbody className="divide-y divide-slate-100 dark:divide-slate-700 text-slate-800 dark:text-slate-200">
                                {ledger.length === 0 ? (
                                    <tr>
                                        <td colSpan="6" className="px-6 py-8 text-center text-slate-400">
                                            No transaction entries recorded yet.
                                        </td>
                                    </tr>
                                ) : (
                                    ledger.map((tx) => (
                                        <tr key={tx.transaction_id} className="hover:bg-slate-50 dark:hover:bg-slate-700/30 transition">
                                            <td className="px-6 py-4 font-mono text-xs text-slate-500">
                                                #{tx.transaction_id}
                                            </td>
                                            <td className="px-6 py-4">
                                                <span className="px-2.5 py-1 text-xs font-semibold rounded-full bg-slate-100 dark:bg-slate-700 text-slate-700 dark:text-slate-300">
                                                    {tx.transaction_type}
                                                </span>
                                            </td>
                                            <td className="px-6 py-4 text-slate-600 dark:text-slate-400">
                                                {tx.user_name ? (
                                                    <div>
                                                        <div className="font-semibold text-slate-800 dark:text-slate-200">{tx.user_name}</div>
                                                        {tx.user_email && <div className="text-[10px] text-slate-500 mt-0.5">{tx.user_email}</div>}
                                                    </div>
                                                ) : (
                                                    tx.user_id ? `User #${tx.user_id}` : 'Organization'
                                                )}
                                            </td>
                                            <td className={`px-6 py-4 font-bold ${tx.token_delta >= 0 ? 'text-emerald-600 dark:text-emerald-400' : 'text-rose-600 dark:text-rose-400'}`}>
                                                <div className="font-semibold text-sm">
                                                    {tx.token_delta >= 0 ? '+' : ''}
                                                    {formatCurrency(tx.token_delta, reserve?.reference_price || 0.000007)}
                                                </div>
                                                <div className="text-[10px] text-slate-500 font-mono mt-0.5">
                                                    {tx.token_delta >= 0 ? '+' : ''}
                                                    {Number(tx.token_delta).toLocaleString()} tokens
                                                </div>
                                            </td>
                                            <td className="px-6 py-4 text-xs text-slate-500 truncate max-w-xs">
                                                {tx.remarks || tx.reference_id || '—'}
                                            </td>
                                            <td className="px-6 py-4 text-xs text-slate-400">
                                                {new Date(tx.created_at).toLocaleString()}
                                            </td>
                                        </tr>
                                    ))
                                )}
                            </tbody>
                        </table>
                    </div>
                </div>
            )}

            {/* TAB 3: Daily Reports */}
            {activeSubTab === 'reports' && (
                <div className="bg-white dark:bg-slate-800 rounded-2xl border border-slate-200 dark:border-slate-700 overflow-hidden shadow-sm">
                    <div className="overflow-x-auto">
                        <table className="w-full text-left text-sm">
                            <thead className="bg-slate-50 dark:bg-slate-700/50 text-slate-600 dark:text-slate-300 border-b border-slate-200 dark:border-slate-700">
                                <tr>
                                    <th className="px-6 py-4 font-semibold">Date</th>
                                    <th className="px-6 py-4 font-semibold">Tokens Consumed</th>
                                    <th className="px-6 py-4 font-semibold">Total Requests</th>
                                </tr>
                            </thead>
                            <tbody className="divide-y divide-slate-100 dark:divide-slate-700 text-slate-800 dark:text-slate-200">
                                {dailyUsage.length === 0 ? (
                                    <tr>
                                        <td colSpan="3" className="px-6 py-8 text-center text-slate-400">
                                            No daily usage records available.
                                        </td>
                                    </tr>
                                ) : (
                                    dailyUsage.map((d, idx) => (
                                        <tr key={idx} className="hover:bg-slate-50 dark:hover:bg-slate-700/30 transition">
                                            <td className="px-6 py-4 font-medium">{d.date}</td>
                                            <td className="px-6 py-4 font-bold text-rose-600 dark:text-rose-400">
                                                {Number(d.tokens || 0).toLocaleString()}
                                            </td>
                                            <td className="px-6 py-4 font-medium">{d.requests || 0}</td>
                                        </tr>
                                    ))
                                )}
                            </tbody>
                        </table>
                    </div>
                </div>
            )}

            {/* MODAL 1: Allocate Modal */}
            {allocateModal.open && (
                <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-[9999] flex items-center justify-center p-4">
                    <div className="bg-white dark:bg-slate-800 rounded-2xl max-w-md w-full p-6 border border-slate-200 dark:border-slate-700 shadow-2xl animate-in fade-in zoom-in-95 duration-200">
                        <h3 className="text-lg font-bold text-slate-900 dark:text-white mb-2">
                            Allocate Tokens from Reserve
                        </h3>
                        <p className="text-sm text-slate-500 mb-4">
                            Assign token quota to <span className="font-semibold text-slate-800 dark:text-slate-200">{allocateModal.userName || `User #${allocateModal.userId}`}</span>.
                            <span className="block text-xs mt-1 text-slate-400">
                                Available in Reserve: <span className="font-semibold">{formatCurrency(reserve?.reserved_tokens || 0, reserve?.reference_price || 0.000007)}</span> ({Number(reserve?.reserved_tokens || 0).toLocaleString()} tokens)
                            </span>
                        </p>
                        <form onSubmit={handleAllocate} className="space-y-4">
                            {error && (
                                <div className="p-3 bg-rose-50 dark:bg-rose-950/40 border border-rose-200 dark:border-rose-800 rounded-xl flex items-center gap-2 text-rose-700 dark:text-rose-300 text-xs">
                                    <AlertCircle className="w-4 h-4 flex-shrink-0" />
                                    <span className="font-semibold">{error}</span>
                                </div>
                            )}
                            <div>
                                <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                                    Token Amount
                                </label>
                                <input
                                    type="number"
                                    min="1"
                                    required
                                    value={allocateModal.amount}
                                    onChange={(e) => setAllocateModal({ ...allocateModal, amount: e.target.value })}
                                    placeholder="e.g. 50000"
                                    className="w-full px-4 py-2.5 rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900 text-slate-900 dark:text-white text-sm focus:ring-2 focus:ring-indigo-500 focus:outline-none transition-all font-mono"
                                />
                                {allocateModal.amount && (
                                    <div className="text-[11px] text-indigo-600 dark:text-indigo-400 font-semibold mt-1">
                                        Value: {formatCurrency(Number(allocateModal.amount), reserve?.reference_price || 0.000007)}
                                    </div>
                                )}
                            </div>
                            <div>
                                <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                                    Remarks (Optional)
                                </label>
                                <input
                                    type="text"
                                    value={allocateModal.remarks}
                                    onChange={(e) => setAllocateModal({ ...allocateModal, remarks: e.target.value })}
                                    placeholder="Monthly sprint quota"
                                    className="w-full px-4 py-2.5 rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900 text-slate-900 dark:text-white text-sm focus:ring-2 focus:ring-indigo-500 focus:outline-none transition-all"
                                />
                            </div>
                            <div className="flex justify-end gap-3 mt-6">
                                <button
                                    type="button"
                                    onClick={() => { setError(''); setAllocateModal({ open: false, userId: null, userName: '', amount: '', remarks: '' }); }}
                                    className="px-4 py-2 text-sm font-semibold text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-700 rounded-xl transition"
                                >
                                    Cancel
                                </button>
                                <button
                                    type="submit"
                                    disabled={actionLoading}
                                    className="px-4 py-2 text-sm font-semibold bg-indigo-600 hover:bg-indigo-700 text-white rounded-xl shadow-md transition"
                                >
                                    {actionLoading ? 'Allocating...' : 'Confirm Allocation'}
                                </button>
                            </div>
                        </form>
                    </div>
                </div>
            )}

            {/* MODAL 2: Reallocate / Transfer Modal */}
            {reallocateModal.open && (
                <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-[9999] flex items-center justify-center p-4">
                    <div className="bg-white dark:bg-slate-800 rounded-2xl max-w-md w-full p-6 border border-slate-200 dark:border-slate-700 shadow-2xl animate-in fade-in zoom-in-95 duration-200">
                        <h3 className="text-lg font-bold text-slate-900 dark:text-white mb-2">
                            Transfer Token Quota
                        </h3>
                        <p className="text-sm text-slate-500 mb-4">
                            Transfer tokens from <span className="font-semibold text-slate-800 dark:text-slate-200">{reallocateModal.fromUserName || `User #${reallocateModal.fromUserId}`}</span> to another team member.
                        </p>
                        <form onSubmit={handleReallocate} className="space-y-4">
                            {error && (
                                <div className="p-3 bg-rose-50 dark:bg-rose-950/40 border border-rose-200 dark:border-rose-800 rounded-xl flex items-center gap-2 text-rose-700 dark:text-rose-300 text-xs">
                                    <AlertCircle className="w-4 h-4 flex-shrink-0" />
                                    <span className="font-semibold">{error}</span>
                                </div>
                            )}
                            <div>
                                <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                                    Target Organization Member
                                </label>
                                <select
                                    required
                                    value={reallocateModal.toUserId}
                                    onChange={(e) => setReallocateModal({ ...reallocateModal, toUserId: e.target.value })}
                                    className="w-full px-4 py-2.5 rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900 text-slate-900 dark:text-white text-sm focus:ring-2 focus:ring-indigo-500 focus:outline-none transition-all"
                                >
                                    <option value="" disabled>Select target member...</option>
                                    {usersList
                                        .filter(user => user.user_id !== reallocateModal.fromUserId)
                                        .map(user => (
                                            <option key={user.user_id} value={user.user_id}>
                                                {user.name || user.email || `User #${user.user_id}`} ({user.email})
                                            </option>
                                        ))}
                                </select>
                            </div>
                            <div>
                                <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                                    Token Amount
                                </label>
                                <input
                                    type="number"
                                    min="1"
                                    required
                                    value={reallocateModal.amount}
                                    onChange={(e) => setReallocateModal({ ...reallocateModal, amount: e.target.value })}
                                    placeholder="e.g. 10000"
                                    className="w-full px-4 py-2.5 rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900 text-slate-900 dark:text-white text-sm focus:ring-2 focus:ring-indigo-500 focus:outline-none transition-all font-mono"
                                />
                                {reallocateModal.amount && (
                                    <div className="text-[11px] text-indigo-600 dark:text-indigo-400 font-semibold mt-1">
                                        Value: {formatCurrency(Number(reallocateModal.amount), reserve?.reference_price || 0.000007)}
                                    </div>
                                )}
                            </div>
                            <div className="flex justify-end gap-3 mt-6">
                                <button
                                    type="button"
                                    onClick={() => { setError(''); setReallocateModal({ open: false, fromUserId: null, fromUserName: '', toUserId: '', amount: '' }); }}
                                    className="px-4 py-2 text-sm font-semibold text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-700 rounded-xl transition"
                                >
                                    Cancel
                                </button>
                                <button
                                    type="submit"
                                    disabled={actionLoading}
                                    className="px-4 py-2 text-sm font-semibold bg-indigo-600 hover:bg-indigo-700 text-white rounded-xl shadow-md transition"
                                >
                                    {actionLoading ? 'Transferring...' : 'Confirm Transfer'}
                                </button>
                            </div>
                        </form>
                    </div>
                </div>
            )}

            {/* MODAL 3: Revoke Modal */}
            {revokeModal.open && (
                <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-[9999] flex items-center justify-center p-4">
                    <div className="bg-white dark:bg-slate-800 rounded-2xl max-w-md w-full p-6 border border-slate-200 dark:border-slate-700 shadow-2xl animate-in fade-in zoom-in-95 duration-200">
                        <h3 className="text-lg font-bold text-slate-900 dark:text-white mb-2">
                            Revoke Tokens to Org Reserve
                        </h3>
                        <p className="text-sm text-slate-500 mb-4">
                            Reclaim unused token quota from <span className="font-semibold text-slate-800 dark:text-slate-200">{revokeModal.userName || `User #${revokeModal.userId}`}</span> back to the organization reserve.
                        </p>
                        <form onSubmit={handleRevoke} className="space-y-4">
                            {error && (
                                <div className="p-3 bg-rose-50 dark:bg-rose-950/40 border border-rose-200 dark:border-rose-800 rounded-xl flex items-center gap-2 text-rose-700 dark:text-rose-300 text-xs">
                                    <AlertCircle className="w-4 h-4 flex-shrink-0" />
                                    <span className="font-semibold">{error}</span>
                                </div>
                            )}
                            <div>
                                <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                                    Token Amount to Revoke
                                </label>
                                <input
                                    type="number"
                                    min="1"
                                    required
                                    value={revokeModal.amount}
                                    onChange={(e) => setRevokeModal({ ...revokeModal, amount: e.target.value })}
                                    placeholder="e.g. 15000"
                                    className="w-full px-4 py-2.5 rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900 text-slate-900 dark:text-white text-sm focus:ring-2 focus:ring-amber-500 focus:outline-none transition-all font-mono"
                                />
                                {revokeModal.amount && (
                                    <div className="text-[11px] text-amber-600 dark:text-amber-400 font-semibold mt-1">
                                        Value: {formatCurrency(Number(revokeModal.amount), reserve?.reference_price || 0.000007)}
                                    </div>
                                )}
                            </div>
                            <div className="flex justify-end gap-3 mt-6">
                                <button
                                    type="button"
                                    onClick={() => { setError(''); setRevokeModal({ open: false, userId: null, userName: '', amount: '' }); }}
                                    className="px-4 py-2 text-sm font-semibold text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-700 rounded-xl transition"
                                >
                                    Cancel
                                </button>
                                <button
                                    type="submit"
                                    disabled={actionLoading}
                                    className="px-4 py-2 text-sm font-semibold bg-amber-600 hover:bg-amber-700 text-white rounded-xl shadow-md transition"
                                >
                                    {actionLoading ? 'Revoking...' : 'Confirm Revocation'}
                                </button>
                            </div>
                        </form>
                    </div>
                </div>
            )}

            {/* MODAL 4: Submit Quota Request Modal */}
            {requestModal.open && (
                <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-[9999] flex items-center justify-center p-4">
                    <div className="bg-white dark:bg-slate-800 rounded-2xl max-w-md w-full p-6 border border-slate-200 dark:border-slate-700 shadow-2xl animate-in fade-in zoom-in-95 duration-200">
                        <h3 className="text-lg font-bold text-slate-900 dark:text-white mb-1 flex items-center gap-2">
                            <Coins className="w-5 h-5 text-indigo-600 dark:text-indigo-400" />
                            Request Token Quota from Super Admin
                        </h3>
                        <p className="text-xs text-slate-500 mb-4">
                            Submit a request for token increase or PAYG enablement for <strong>{orgName}</strong>.
                        </p>
                        <form onSubmit={handleQuotaRequest} className="space-y-4">
                            {error && (
                                <div className="p-3 bg-rose-50 dark:bg-rose-950/40 border border-rose-200 dark:border-rose-800 rounded-xl flex items-center gap-2 text-rose-700 dark:text-rose-300 text-xs">
                                    <AlertCircle className="w-4 h-4 flex-shrink-0" />
                                    <span className="font-semibold">{error}</span>
                                </div>
                            )}
                            <div>
                                <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                                    Request Type
                                </label>
                                <div className="grid grid-cols-2 gap-2">
                                    <button
                                        type="button"
                                        onClick={() => setRequestModal({ ...requestModal, requestType: 'TOKEN_INCREASE' })}
                                        className={`p-3 rounded-xl border text-xs font-semibold text-left transition ${
                                            requestModal.requestType === 'TOKEN_INCREASE'
                                                ? 'border-indigo-600 bg-indigo-50 dark:bg-indigo-950/40 text-indigo-700 dark:text-indigo-300 ring-2 ring-indigo-600/20'
                                                : 'border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-400 hover:bg-slate-50 dark:hover:bg-slate-700/50'
                                        }`}
                                    >
                                        <div className="font-bold">Token Increase</div>
                                        <div className="text-[11px] text-slate-400 font-normal mt-0.5">Prepaid token pool increase</div>
                                    </button>
                                    <button
                                        type="button"
                                        onClick={() => setRequestModal({ ...requestModal, requestType: 'PAYG_ENABLEMENT' })}
                                        className={`p-3 rounded-xl border text-xs font-semibold text-left transition ${
                                            requestModal.requestType === 'PAYG_ENABLEMENT'
                                                ? 'border-purple-600 bg-purple-50 dark:bg-purple-950/40 text-purple-700 dark:text-purple-300 ring-2 ring-purple-600/20'
                                                : 'border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-400 hover:bg-slate-50 dark:hover:bg-slate-700/50'
                                        }`}
                                    >
                                        <div className="font-bold">PAYG Enablement</div>
                                        <div className="text-[11px] text-slate-400 font-normal mt-0.5">Post-paid consumption</div>
                                    </button>
                                </div>
                            </div>

                            {requestModal.requestType === 'TOKEN_INCREASE' && (
                                <div>
                                    <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                                        Requested Token Count (Total Input + Output)
                                    </label>
                                    <input
                                        type="number"
                                        min="1"
                                        required
                                        value={requestModal.amount}
                                        onChange={(e) => setRequestModal({ ...requestModal, amount: e.target.value })}
                                        placeholder="e.g. 500000"
                                        className="w-full px-4 py-2.5 rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900 text-slate-900 dark:text-white font-mono text-sm focus:ring-2 focus:ring-indigo-500 focus:outline-none transition-all"
                                    />
                                    {requestModal.amount && (
                                        <div className="text-[11px] text-indigo-600 dark:text-indigo-400 font-semibold mt-1">
                                            Value: {formatCurrency(Number(requestModal.amount), reserve?.reference_price || 0.000007)}
                                        </div>
                                    )}
                                    <p className="text-[11px] text-slate-400 mt-1">
                                        Upon Super Admin approval, this amount will be credited to your Org Reserve for you to divide to users.
                                    </p>
                                </div>
                            )}

                            <div>
                                <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                                    Justification / Business Purpose
                                </label>
                                <textarea
                                    rows="3"
                                    required
                                    value={requestModal.remarks}
                                    onChange={(e) => setRequestModal({ ...requestModal, remarks: e.target.value })}
                                    placeholder="e.g. Onboarding 5 new analysts for BRD reviews..."
                                    className="w-full px-4 py-2 rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900 text-slate-900 dark:text-white text-xs focus:ring-2 focus:ring-indigo-500 focus:outline-none transition-all"
                                />
                            </div>

                            <div className="flex justify-end gap-3 mt-6">
                                <button
                                    type="button"
                                    onClick={() => { setError(''); setRequestModal({ open: false, requestType: 'TOKEN_INCREASE', amount: '', remarks: '' }); }}
                                    className="px-4 py-2 text-sm font-semibold text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-700 rounded-xl transition"
                                >
                                    Cancel
                                </button>
                                <button
                                    type="submit"
                                    disabled={actionLoading}
                                    className="px-4 py-2 text-sm font-semibold bg-indigo-600 hover:bg-indigo-700 text-white rounded-xl shadow-md transition"
                                >
                                    {actionLoading ? 'Submitting...' : 'Submit Request'}
                                </button>
                            </div>
                        </form>
                    </div>
                </div>
            )}
        </div>
    );
}
