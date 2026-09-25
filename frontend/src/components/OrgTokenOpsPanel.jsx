import React, { useState, useEffect } from 'react';
import { 
    Coins, Users, ShieldAlert, ArrowRightLeft, PlusCircle, MinusCircle, 
    RefreshCw, AlertCircle, CheckCircle2, DollarSign, Activity, FileText, Ban, Check, MoreVertical, Info,
    Folder, Sparkles, Bot, Search, Scale, GitPullRequest, MessageSquare, Compass, CreditCard, RotateCcw, Sliders, CheckSquare, Zap, ArrowUpDown, ChevronUp, ChevronDown, ChevronLeft, ChevronRight, Cpu
} from 'lucide-react';
import { API_ENDPOINTS } from '../config';

export default function OrgTokenOpsPanel({ user }) {
    const [reserve, setReserve] = useState(null);
    const [usersList, setUsersList] = useState([]);
    const [ledger, setLedger] = useState([]);
    const [dailyUsage, setDailyUsage] = useState([]);
    const [quotaRequests, setQuotaRequests] = useState([]);
    const [memberRequests, setMemberRequests] = useState([]);
    const [memberRequestStatusFilter, setMemberRequestStatusFilter] = useState('ALL');
    const [loading, setLoading] = useState(true);
    const [actionLoading, setActionLoading] = useState(false);
    const [error, setError] = useState('');
    const [successMessage, setSuccessMessage] = useState('');
    const [openDropdownUserId, setOpenDropdownUserId] = useState(null);
    const [activeSubTab, setActiveSubTab] = useState('users'); // 'users' | 'member_requests' | 'requests' | 'ledger' | 'reports'
    const [viewDropdownOpen, setViewDropdownOpen] = useState(false);

    // Financial Ledger Filters, Sorting & Pagination State
    const [ledgerFilter, setLedgerFilter] = useState('ALL'); // 'ALL' | 'AI_CONSUMPTION' | 'ALLOCATION' | 'REVOCATION' | 'INFLOW' | 'OUTFLOW'
    const [ledgerSearch, setLedgerSearch] = useState('');
    const [ledgerSortKey, setLedgerSortKey] = useState('created_at'); // 'transaction_id' | 'token_delta' | 'balance_after' | 'created_at'
    const [ledgerSortOrder, setLedgerSortOrder] = useState('desc'); // 'asc' | 'desc'
    const [ledgerPage, setLedgerPage] = useState(1);
    const [ledgerPageSize, setLedgerPageSize] = useState(10);
    const [ledgerTotal, setLedgerTotal] = useState(0);
    const [allLedgerTotal, setAllLedgerTotal] = useState(0);
    const [ledgerLoading, setLedgerLoading] = useState(false);
    const [ledgerFilterDropdownOpen, setLedgerFilterDropdownOpen] = useState(false);

    // Modal States
    const [allocateModal, setAllocateModal] = useState({ open: false, userId: null, userName: '', amount: '', remarks: '' });
    const [reallocateModal, setReallocateModal] = useState({ open: false, fromUserId: null, fromUserName: '', toUserId: '', amount: '' });
    const [revokeModal, setRevokeModal] = useState({ open: false, userId: null, userName: '', amount: '' });
    const [requestModal, setRequestModal] = useState({ open: false, requestType: 'TOKEN_INCREASE', amount: '', remarks: '' });
    const [reviewMemberModal, setReviewMemberModal] = useState({ open: false, request: null, action: 'APPROVE', approvedTokens: '', adminNotes: '' });

    const token = localStorage.getItem('token');
    const orgName = user?.organization_name || localStorage.getItem('active_org') || '';

    const localTimezone = (() => {
        try {
            return new Intl.DateTimeFormat(undefined, { timeZoneName: 'short' })
                .formatToParts(new Date())
                .find(part => part.type === 'timeZoneName')?.value || '';
        } catch (e) {
            return '';
        }
    })();

    const formatTimestamp = (ts) => {
        if (!ts) return '—';
        let s = String(ts).trim();
        // If naive timestamp without timezone, append Z so browser parses as UTC
        if (!s.endsWith('Z') && !/[+-]\d{2}:?\d{2}$/.test(s)) {
            s = s.includes('T') ? `${s}Z` : `${s.replace(' ', 'T')}Z`;
        }
        const d = new Date(s);
        return isNaN(d.getTime()) ? ts : d.toLocaleString();
    };

    const formatDateOnly = (ts) => {
        if (!ts) return '—';
        let s = String(ts).trim();
        if (!s.endsWith('Z') && !/[+-]\d{2}:?\d{2}$/.test(s)) {
            s = s.includes('T') ? `${s}Z` : `${s.replace(' ', 'T')}Z`;
        }
        const d = new Date(s);
        return isNaN(d.getTime()) ? ts : d.toLocaleDateString();
    };

    const formatCurrency = (amount, pricePerToken = 0.000007) => {
        const val = (amount || 0) * pricePerToken;
        if (Math.abs(val) > 0 && Math.abs(val) < 0.01) {
            return val < 0 ? '< -$0.01' : '< $0.01';
        }
        if (val === 0) return '$0.00';
        return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(val);
    };

    const extractModelFromRemarks = (remarks) => {
        if (!remarks) return null;
        const match = remarks.match(/Model:\s*([^\s,(]+)/i);
        return match ? match[1] : null;
    };

    const renderPurposeBadge = (purpose, type) => {
        const fullPurpose = purpose || (
            type === 'ALLOCATION' ? 'Admin Quota Allocation' : 
            type === 'PURCHASE' ? 'Token Pack Purchase' : 
            type === 'REALLOCATION' ? 'User Wallet Reallocation' : 
            type === 'REVOCATION' ? 'Quota Revocation' : 
            type === 'MANUAL_ADJUSTMENT' ? 'Manual Balance Adjustment' : 
            'AI Consumption'
        );

        let mainCategory = fullPurpose;
        let subAction = null;
        if (fullPurpose.includes(':')) {
            const parts = fullPurpose.split(':');
            mainCategory = parts[0].trim();
            subAction = parts.slice(1).join(':').trim();
        } else if (mainCategory === 'Autonomous Coding Agent') {
            subAction = 'On-Flight Execution';
        }
        
        let badgeStyle = "bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300 border-slate-200 dark:border-slate-700";
        let iconElement = <Zap className="w-3 h-3 text-amber-500 shrink-0" />;

        if (mainCategory.includes('Screening')) {
            badgeStyle = "bg-purple-50 dark:bg-purple-950/40 text-purple-700 dark:text-purple-300 border-purple-200 dark:border-purple-800/60";
            iconElement = <CheckSquare className="w-3 h-3 text-purple-500 shrink-0" />;
        } else if (mainCategory.includes('Analysis') || mainCategory.includes('Architecture')) {
            badgeStyle = "bg-indigo-50 dark:bg-indigo-950/40 text-indigo-700 dark:text-indigo-300 border-indigo-200 dark:border-indigo-800/60";
            iconElement = <Search className="w-3 h-3 text-indigo-500 shrink-0" />;
        } else if (mainCategory.includes('Gap')) {
            badgeStyle = "bg-amber-50 dark:bg-amber-950/40 text-amber-700 dark:text-amber-300 border-amber-200 dark:border-amber-800/60";
            iconElement = <Scale className="w-3 h-3 text-amber-500 shrink-0" />;
        } else if (mainCategory.includes('Test')) {
            badgeStyle = "bg-cyan-50 dark:bg-cyan-950/40 text-cyan-700 dark:text-cyan-300 border-cyan-200 dark:border-cyan-800/60";
            iconElement = <Sparkles className="w-3 h-3 text-cyan-500 shrink-0" />;
        } else if (mainCategory.includes('Agent') || mainCategory.includes('Coding') || mainCategory.includes('Playground')) {
            badgeStyle = "bg-rose-50 dark:bg-rose-950/40 text-rose-700 dark:text-rose-300 border-rose-200 dark:border-rose-800/60";
            iconElement = <Bot className="w-3 h-3 text-rose-500 shrink-0" />;
        } else if (mainCategory.includes('PR') || mainCategory.includes('Commit')) {
            badgeStyle = "bg-teal-50 dark:bg-teal-950/40 text-teal-700 dark:text-teal-300 border-teal-200 dark:border-teal-800/60";
            iconElement = <GitPullRequest className="w-3 h-3 text-teal-500 shrink-0" />;
        } else if (mainCategory.includes('Ingestion') || mainCategory.includes('OCR')) {
            badgeStyle = "bg-sky-50 dark:bg-sky-950/40 text-sky-700 dark:text-sky-300 border-sky-200 dark:border-sky-800/60";
            iconElement = <FileText className="w-3 h-3 text-sky-500 shrink-0" />;
        } else if (mainCategory.includes('Chat') || mainCategory.includes('Copilot') || mainCategory.includes('Assistant')) {
            badgeStyle = "bg-emerald-50 dark:bg-emerald-950/40 text-emerald-700 dark:text-emerald-300 border-emerald-200 dark:border-emerald-800/60";
            iconElement = <MessageSquare className="w-3 h-3 text-emerald-500 shrink-0" />;
        } else if (mainCategory.includes('Decomposition') || mainCategory.includes('Checklist') || mainCategory.includes('Planning')) {
            badgeStyle = "bg-blue-50 dark:bg-blue-950/40 text-blue-700 dark:text-blue-300 border-blue-200 dark:border-blue-800/60";
            iconElement = <Compass className="w-3 h-3 text-blue-500 shrink-0" />;
        } else if (mainCategory.includes('Revocation')) {
            badgeStyle = "bg-rose-50 dark:bg-rose-950/40 text-rose-700 dark:text-rose-300 border-rose-200 dark:border-rose-800/60";
            iconElement = <RotateCcw className="w-3 h-3 text-rose-500 shrink-0" />;
        } else if (mainCategory.includes('Reallocation')) {
            badgeStyle = "bg-sky-50 dark:bg-sky-950/40 text-sky-700 dark:text-sky-300 border-sky-200 dark:border-sky-800/60";
            iconElement = <ArrowRightLeft className="w-3 h-3 text-sky-500 shrink-0" />;
        } else if (mainCategory.includes('Allocation') || mainCategory.includes('Purchase')) {
            badgeStyle = "bg-emerald-50 dark:bg-emerald-950/40 text-emerald-700 dark:text-emerald-300 border-emerald-200 dark:border-emerald-800/60";
            iconElement = <CreditCard className="w-3 h-3 text-emerald-500 shrink-0" />;
        } else if (mainCategory.includes('Manual')) {
            badgeStyle = "bg-amber-50 dark:bg-amber-950/40 text-amber-700 dark:text-amber-300 border-amber-200 dark:border-amber-800/60";
            iconElement = <Sliders className="w-3 h-3 text-amber-500 shrink-0" />;
        }

        return (
            <div className="flex flex-col items-start gap-1">
                <span 
                    className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-semibold border ${badgeStyle}`}
                    title={subAction ? `${mainCategory} — ${subAction}` : mainCategory}
                >
                    {iconElement}
                    <span className="font-medium whitespace-nowrap">{mainCategory}</span>
                </span>
                {subAction && (
                    <span 
                        className="inline-flex items-center gap-1 text-[10px] font-semibold text-rose-600 dark:text-rose-400 pl-0.5"
                        title={`Action executed by agent: ${subAction}`}
                    >
                        <span className="w-1.5 h-1.5 rounded-full bg-rose-400 shrink-0"></span>
                        <span className="truncate max-w-[210px]">{subAction}</span>
                    </span>
                )}
            </div>
        );
    };

    const getHeaders = () => {
        const headers = {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json'
        };
        if (orgName) {
            headers['X-Organization'] = orgName;
        }
        return headers;
    };

    const getAvailableReserve = () => {
        if (!reserve) return 0;
        if (reserve.reserved_tokens !== undefined && reserve.reserved_tokens !== null && reserve.reserved_tokens > 0) {
            return reserve.reserved_tokens;
        }
        const calc = (reserve.purchased_tokens || 0) - (reserve.allocated_tokens || 0);
        return Math.max(0, calc);
    };

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
                    if (data.success && data.data) {
                        setReserve(data.data);
                    } else if (data.error) {
                        console.error('Reserve API returned error:', data.error);
                        setError(prev => prev || data.error?.message || 'Failed to load organization reserve.');
                    }
                } else {
                    console.error('Reserve API HTTP status:', resReserve.status);
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
                    } else if (data.error) {
                        console.error('Users API returned error:', data.error);
                        setError(prev => prev || data.error?.message || 'Failed to load organization users.');
                    }
                } else {
                    console.error('Users API HTTP status:', resUsers.status);
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
            await fetchLedgerData(1, ledgerPageSize, ledgerFilter, ledgerSearch);

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

            // 6. Fetch Member Top-Up Requests
            try {
                const resMember = await fetch(API_ENDPOINTS.TOKENOPS_ORG_MEMBER_REQUESTS, { headers });
                if (resMember.ok) {
                    const data = await resMember.json();
                    if (data.success && data.data) {
                        setMemberRequests(data.data);
                    }
                }
            } catch (e) {
                console.warn('Failed to load member requests:', e);
            }
        } catch (err) {
            setError(err.message || 'Failed to load organization token operational data.');
        } finally {
            setLoading(false);
        }
    };

    const fetchLedgerData = async (page = ledgerPage, size = ledgerPageSize, filter = ledgerFilter, search = ledgerSearch) => {
        setLedgerLoading(true);
        try {
            let url = `${API_ENDPOINTS.TOKENOPS_ORG_REPORTS_LEDGER}?page=${page}&size=${size}`;
            if (filter && filter !== 'ALL') {
                url += `&transaction_type=${encodeURIComponent(filter)}`;
            }
            if (search && search.trim()) {
                url += `&search=${encodeURIComponent(search.trim())}`;
            }
            const res = await fetch(url, { headers: getHeaders() });
            if (res.ok) {
                const data = await res.json();
                if (data.success && data.data) {
                    const totalCount = data.data.total !== undefined ? data.data.total : (data.data.items || []).length;
                    setLedger(data.data.items || []);
                    setLedgerTotal(totalCount);
                    if ((!filter || filter === 'ALL') && (!search || !search.trim())) {
                        setAllLedgerTotal(totalCount);
                    }
                    setLedgerPage(data.data.page || page);
                    setLedgerPageSize(data.data.size || size);
                }
            }
        } catch (e) {
            console.warn('Failed to load ledger:', e);
        } finally {
            setLedgerLoading(false);
        }
    };

    useEffect(() => {
        fetchData();
    }, [orgName]);

    useEffect(() => {
        if (activeSubTab !== 'ledger') return;
        const timer = setTimeout(() => {
            setLedgerPage(1);
            fetchLedgerData(1, ledgerPageSize, ledgerFilter, ledgerSearch);
        }, 350);
        return () => clearTimeout(timer);
    }, [ledgerSearch]);

    useEffect(() => {
        if (activeSubTab === 'ledger') {
            fetchLedgerData(ledgerPage, ledgerPageSize, ledgerFilter, ledgerSearch);
        }
    }, [activeSubTab]);

    // Handle Reviewing Member Top-Up Request
    const handleReviewMemberRequest = async (requestId, action, approvedTokens = null, adminNotes = '') => {
        setActionLoading(true);
        setError('');
        setSuccessMessage('');
        try {
            const res = await fetch(API_ENDPOINTS.TOKENOPS_ORG_REVIEW_MEMBER_REQUEST(requestId), {
                method: 'POST',
                headers: getHeaders(),
                body: JSON.stringify({
                    action,
                    approved_tokens: approvedTokens ? parseInt(approvedTokens, 10) : undefined,
                    admin_notes: adminNotes || undefined,
                }),
            });
            const data = await res.json();
            if (res.ok && data.success) {
                setSuccessMessage(
                    action === 'APPROVE'
                        ? `Member request approved! Tokens successfully allocated from organization reserve.`
                        : `Member request rejected.`
                );
                setReviewMemberModal({ open: false, request: null, action: 'APPROVE', approvedTokens: '', adminNotes: '' });
                await fetchData();
            } else {
                throw new Error(data.detail || data.error?.message || 'Failed to review member request.');
            }
        } catch (err) {
            setError(err.message);
        } finally {
            setActionLoading(false);
        }
    };

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
                    : requestModal.requestType === 'PAYG_DISABLEMENT'
                        ? 'Request to switch back to prepaid mode submitted! Waiting for Super Admin approval.'
                        : 'PAYG Enablement request submitted! Waiting for Super Admin approval.'
            );
            setRequestModal({ open: false, requestType: reserve?.payg_enabled ? 'PAYG_DISABLEMENT' : 'TOKEN_INCREASE', amount: '', remarks: '' });
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
        const availReserved = getAvailableReserve();
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
        <div className="space-y-4">
            {/* Header & Refresh */}
            <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-3 bg-app-bg-card p-4 sm:p-5 rounded-xl border border-app-border shadow-xs">
                <div className="flex items-center gap-3">
                    <div className="w-10 h-10 rounded-xl bg-indigo-50 dark:bg-indigo-950/60 border border-indigo-100 dark:border-indigo-900/50 flex items-center justify-center text-indigo-600 dark:text-indigo-400 shrink-0 shadow-xs">
                        <Coins className="w-5 h-5" />
                    </div>
                    <div>
                        <h2 className="text-lg sm:text-xl font-bold text-app-text-main flex items-center gap-2">
                            TokenOps Quota & Reserve Management
                        </h2>
                        <p className="text-xs text-app-text-muted mt-0.5">
                            Control token quotas, divide reserve tokens among users, and request quota increases for <span className="font-semibold text-app-text-main">{orgName}</span>.
                        </p>
                    </div>
                </div>
                <div className="flex items-center gap-2 self-start sm:self-auto shrink-0">
                    <button
                        onClick={() => { setError(''); setRequestModal({ open: true, requestType: reserve?.payg_enabled ? 'PAYG_DISABLEMENT' : 'TOKEN_INCREASE', amount: '', remarks: '' }); }}
                        className="h-9 px-3.5 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg transition-colors text-xs font-semibold shadow-xs inline-flex items-center gap-2 cursor-pointer"
                    >
                        <PlusCircle className="w-3.5 h-3.5" />
                        {reserve?.payg_enabled ? 'Request Prepaid Switch' : 'Request Quota / PAYG'}
                    </button>
                    <button 
                        onClick={fetchData} 
                        disabled={loading}
                        className="h-9 px-3.5 bg-app-bg-card hover:bg-app-bg-hover text-app-text-main border border-app-border rounded-lg transition-colors text-xs font-semibold shadow-xs inline-flex items-center gap-2 cursor-pointer disabled:opacity-50"
                    >
                        <RefreshCw className={`w-3.5 h-3.5 text-app-text-muted ${loading ? 'animate-spin' : ''}`} />
                        Refresh
                    </button>
                </div>
            </div>

            {/* Pending Requests Alert Banner */}
            {quotaRequests.some(r => r.status === 'REQUESTED') && (
                <div className="p-3 sm:p-3.5 bg-amber-50 dark:bg-amber-950/40 border border-amber-200 dark:border-amber-800 rounded-xl flex items-center gap-3 text-amber-800 dark:text-amber-300 text-xs sm:text-sm">
                    <AlertCircle className="w-4 h-4 sm:w-5 sm:h-5 shrink-0" />
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
                <div className="p-3 sm:p-3.5 bg-rose-50 dark:bg-rose-950/40 border border-rose-200 dark:border-rose-800 rounded-xl flex items-center gap-3 text-rose-700 dark:text-rose-300 text-xs sm:text-sm">
                    <AlertCircle className="w-4 h-4 sm:w-5 sm:h-5 shrink-0" />
                    <span>{error}</span>
                </div>
            )}
            {successMessage && (
                <div className="p-3 sm:p-3.5 bg-emerald-50 dark:bg-emerald-950/40 border border-emerald-200 dark:border-emerald-800 rounded-xl flex items-center gap-3 text-emerald-700 dark:text-emerald-300 text-xs sm:text-sm">
                    <CheckCircle2 className="w-4 h-4 sm:w-5 sm:h-5 shrink-0" />
                    <span>{successMessage}</span>
                </div>
            )}

            {/* KPI Cards: Organization Current Limits */}
            {reserve && (
                reserve.payg_enabled ? (
                    /* PAYG KPI CARDS */
                    <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-2.5 sm:gap-3">
                        {/* Card 1: Billing Mode */}
                        <div className="bg-amber-50/40 dark:bg-amber-950/20 p-3 rounded-xl border border-amber-200/80 dark:border-amber-800/60 shadow-xs relative flex flex-col justify-between hover:border-amber-300 dark:hover:border-amber-700 transition-colors">
                            <div className="flex items-center justify-between gap-1">
                                <span className="text-[10px] font-bold text-amber-700 dark:text-amber-400 uppercase tracking-wider">Billing Mode</span>
                                <div className="relative group">
                                    <Info className="w-3.5 h-3.5 text-amber-400 dark:text-amber-500 hover:text-amber-600 transition-colors cursor-help" />
                                    <div className="absolute bottom-full right-0 mb-2 w-56 p-2.5 bg-slate-900/95 dark:bg-slate-950/95 text-slate-200 text-[10px] leading-normal rounded-lg shadow-lg border border-slate-700/50 opacity-0 group-hover:opacity-100 pointer-events-none transition-opacity duration-200 z-50 text-left font-medium backdrop-blur-sm">
                                        Your organization is billed dynamically based on actual usage, instead of paying in advance.
                                    </div>
                                </div>
                            </div>
                            <div className="text-lg sm:text-xl font-bold text-amber-700 dark:text-amber-400 mt-1.5 flex items-center gap-1.5 whitespace-nowrap">
                                <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse shrink-0 inline-block"></span>
                                <span>PAYG Active</span>
                            </div>
                            <span className="text-[11px] text-app-text-muted mt-1 block font-medium truncate">Billed monthly post-paid</span>
                        </div>

                        {/* Card 2: MTD Spend */}
                        <div className="bg-app-bg-card p-3 rounded-xl border border-app-border shadow-xs relative flex flex-col justify-between hover:border-slate-300 dark:hover:border-slate-600 transition-colors">
                            <div className="flex items-center justify-between gap-1">
                                <span className="text-[10px] font-bold text-app-text-muted uppercase tracking-wider">Current MTD Spend</span>
                                <div className="relative group">
                                    <Info className="w-3.5 h-3.5 text-slate-400 hover:text-slate-600 dark:hover:text-slate-300 transition-colors cursor-help" />
                                    <div className="absolute bottom-full right-0 mb-2 w-56 p-2.5 bg-slate-900/95 dark:bg-slate-950/95 text-slate-200 text-[10px] leading-normal rounded-lg shadow-lg border border-slate-700/50 opacity-0 group-hover:opacity-100 pointer-events-none transition-opacity duration-200 z-50 text-left font-medium backdrop-blur-sm">
                                        The total cost incurred by your organization's members during the current monthly billing cycle.
                                    </div>
                                </div>
                            </div>
                            <div className="text-lg sm:text-xl font-bold text-app-text-main mt-1.5 whitespace-nowrap">
                                {new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', minimumFractionDigits: 2 }).format(reserve.payg_current_spend_usd || 0)}
                            </div>
                            <span className="text-[11px] text-app-text-muted mt-1 block font-medium truncate">
                                {Number(Math.round((reserve.payg_current_spend_usd || 0) / (reserve.reference_price || 0.000007))).toLocaleString()} MTD tokens
                            </span>
                        </div>

                        {/* Card 3: Soft Limit */}
                        <div className="bg-app-bg-card p-3 rounded-xl border border-app-border shadow-xs relative flex flex-col justify-between hover:border-slate-300 dark:hover:border-slate-600 transition-colors">
                            <div className="flex items-center justify-between gap-1">
                                <span className="text-[10px] font-bold text-app-text-muted uppercase tracking-wider">Soft Limit</span>
                                <div className="relative group">
                                    <Info className="w-3.5 h-3.5 text-slate-400 hover:text-slate-600 dark:hover:text-slate-300 transition-colors cursor-help" />
                                    <div className="absolute bottom-full right-0 mb-2 w-56 p-2.5 bg-slate-900/95 dark:bg-slate-950/95 text-slate-200 text-[10px] leading-normal rounded-lg shadow-lg border border-slate-700/50 opacity-0 group-hover:opacity-100 pointer-events-none transition-opacity duration-200 z-50 text-left font-medium backdrop-blur-sm">
                                        An alert threshold. If spending crosses this value, warning notifications are sent to organization administrators.
                                    </div>
                                </div>
                            </div>
                            <div className="text-lg sm:text-xl font-bold text-amber-600 dark:text-amber-400 mt-1.5 whitespace-nowrap">
                                {reserve.payg_soft_limit_usd ? new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(reserve.payg_soft_limit_usd) : 'No Limit'}
                            </div>
                            <span className="text-[11px] text-app-text-muted mt-1 block font-medium truncate">Alert notification trigger</span>
                        </div>

                        {/* Card 4: Hard Limit */}
                        <div className="bg-app-bg-card p-3 rounded-xl border border-app-border shadow-xs relative flex flex-col justify-between hover:border-slate-300 dark:hover:border-slate-600 transition-colors">
                            <div className="flex items-center justify-between gap-1">
                                <span className="text-[10px] font-bold text-app-text-muted uppercase tracking-wider">Hard Limit</span>
                                <div className="relative group">
                                    <Info className="w-3.5 h-3.5 text-slate-400 hover:text-slate-600 dark:hover:text-slate-300 transition-colors cursor-help" />
                                    <div className="absolute bottom-full right-0 mb-2 w-56 p-2.5 bg-slate-900/95 dark:bg-slate-950/95 text-slate-200 text-[10px] leading-normal rounded-lg shadow-lg border border-slate-700/50 opacity-0 group-hover:opacity-100 pointer-events-none transition-opacity duration-200 z-50 text-left font-medium backdrop-blur-sm">
                                        The absolute ceiling. All AI operations are blocked for the organization once spending reaches this cap.
                                    </div>
                                </div>
                            </div>
                            <div className="text-lg sm:text-xl font-bold text-rose-600 dark:text-rose-400 mt-1.5 whitespace-nowrap">
                                {reserve.payg_hard_limit_usd ? new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(reserve.payg_hard_limit_usd) : 'No Limit'}
                            </div>
                            <span className="text-[11px] text-app-text-muted mt-1 block font-medium truncate">Hard execution block</span>
                        </div>

                        {/* Card 5: Total Consumed */}
                        <div className="bg-emerald-50/40 dark:bg-emerald-950/20 p-3 rounded-xl border border-emerald-200/80 dark:border-emerald-800/60 shadow-xs relative flex flex-col justify-between hover:border-emerald-300 dark:hover:border-emerald-700 transition-colors col-span-2 sm:col-span-1">
                            <div className="flex items-center justify-between gap-1">
                                <span className="text-[10px] font-bold text-emerald-700 dark:text-emerald-400 uppercase tracking-wider">Total Consumed</span>
                                <div className="relative group">
                                    <Info className="w-3.5 h-3.5 text-emerald-400 hover:text-emerald-600 transition-colors cursor-help" />
                                    <div className="absolute bottom-full right-0 mb-2 w-56 p-2.5 bg-slate-900/95 dark:bg-slate-950/95 text-slate-200 text-[10px] leading-normal rounded-lg shadow-lg border border-slate-700/50 opacity-0 group-hover:opacity-100 pointer-events-none transition-opacity duration-200 z-50 text-left font-medium backdrop-blur-sm">
                                        The total cost equivalent of all tokens consumed since organization inception across both Prepaid and PAYG billing modes.
                                    </div>
                                </div>
                            </div>
                            <div className="text-lg sm:text-xl font-bold text-emerald-700 dark:text-emerald-300 mt-1.5 whitespace-nowrap">
                                {formatCurrency(reserve.consumed_tokens, reserve.reference_price)}
                            </div>
                            <span className="text-[11px] text-emerald-600 dark:text-emerald-400 mt-1 block font-medium truncate">
                                {Number(reserve.consumed_tokens || 0).toLocaleString()} total tokens
                            </span>
                        </div>
                    </div>
                ) : (
                    /* PREPAID KPI CARDS */
                    <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-2.5 sm:gap-3">
                        {/* Total Approved */}
                        <div className="bg-app-bg-card p-3 rounded-xl border border-app-border shadow-xs relative flex flex-col justify-between hover:border-slate-300 dark:hover:border-slate-600 transition-colors">
                            <div className="flex items-center justify-between gap-1">
                                <span className="text-[10px] font-bold text-app-text-muted uppercase tracking-wider">Total Approved Value</span>
                                <div className="relative group">
                                    <Info className="w-3.5 h-3.5 text-slate-400 hover:text-slate-600 dark:hover:text-slate-300 transition-colors cursor-help" />
                                    <div className="absolute bottom-full right-0 mb-2 w-56 p-2.5 bg-slate-900/95 dark:bg-slate-950/95 text-slate-200 text-[10px] leading-normal rounded-lg shadow-lg border border-slate-700/50 dark:border-slate-800/50 opacity-0 group-hover:opacity-100 pointer-events-none transition-opacity duration-200 z-50 text-left font-medium backdrop-blur-sm">
                                        The total quantity of tokens approved for your organization by the platform Super Admin through quota requests.
                                    </div>
                                </div>
                            </div>
                            <div className="text-lg sm:text-xl font-bold tracking-tight text-app-text-main mt-1.5 font-mono whitespace-nowrap">
                                {formatCurrency(reserve.purchased_tokens, reserve.reference_price)}
                            </div>
                            <span className="text-[11px] text-app-text-muted mt-1 block font-mono truncate">
                                {Number(reserve.purchased_tokens || 0).toLocaleString()} tokens
                            </span>
                        </div>

                        {/* In Org Reserve */}
                        <div className="bg-indigo-50/40 dark:bg-indigo-950/20 p-3 rounded-xl border border-indigo-200/80 dark:border-indigo-800/60 shadow-xs relative flex flex-col justify-between hover:border-indigo-300 dark:hover:border-indigo-700 transition-colors">
                            <div className="flex items-center justify-between gap-1">
                                <span className="text-[10px] font-bold text-indigo-700 dark:text-indigo-400 uppercase tracking-wider">In Org Reserve</span>
                                <div className="relative group">
                                    <Info className="w-3.5 h-3.5 text-indigo-400 hover:text-indigo-600 dark:hover:text-indigo-300 transition-colors cursor-help" />
                                    <div className="absolute bottom-full right-0 mb-2 w-56 p-2.5 bg-slate-900/95 dark:bg-slate-950/95 text-slate-200 text-[10px] leading-normal rounded-lg shadow-lg border border-slate-700/50 dark:border-slate-800/50 opacity-0 group-hover:opacity-100 pointer-events-none transition-opacity duration-200 z-50 text-left font-medium backdrop-blur-sm">
                                        Unallocated tokens currently held in your organization's central pool. Ready to be divided among team members.
                                    </div>
                                </div>
                            </div>
                            <div className="text-lg sm:text-xl font-bold tracking-tight text-indigo-700 dark:text-indigo-300 mt-1.5 font-mono whitespace-nowrap">
                                {formatCurrency(reserve.reserved_tokens, reserve.reference_price)}
                            </div>
                            <span className="text-[11px] text-indigo-600 dark:text-indigo-400 mt-1 block font-medium font-mono truncate">
                                {Number(reserve.reserved_tokens || 0).toLocaleString()} tokens
                            </span>
                        </div>

                        {/* Allocated Value */}
                        <div className="bg-app-bg-card p-3 rounded-xl border border-app-border shadow-xs relative flex flex-col justify-between hover:border-slate-300 dark:hover:border-slate-600 transition-colors">
                            <div className="flex items-center justify-between gap-1">
                                <span className="text-[10px] font-bold text-app-text-muted uppercase tracking-wider">Allocated Value</span>
                                <div className="relative group">
                                    <Info className="w-3.5 h-3.5 text-slate-400 hover:text-slate-600 dark:hover:text-slate-300 transition-colors cursor-help" />
                                    <div className="absolute bottom-full right-0 mb-2 w-56 p-2.5 bg-slate-900/95 dark:bg-slate-950/95 text-slate-200 text-[10px] leading-normal rounded-lg shadow-lg border border-slate-700/50 dark:border-slate-800/50 opacity-0 group-hover:opacity-100 pointer-events-none transition-opacity duration-200 z-50 text-left font-medium backdrop-blur-sm">
                                        The sum of all tokens currently allocated across your team members' individual wallets.
                                    </div>
                                </div>
                            </div>
                            <div className="text-lg sm:text-xl font-bold tracking-tight text-app-text-main mt-1.5 font-mono whitespace-nowrap">
                                {formatCurrency(reserve.allocated_tokens, reserve.reference_price)}
                            </div>
                            <span className="text-[11px] text-app-text-muted mt-1 block font-mono truncate">
                                {Number(reserve.allocated_tokens || 0).toLocaleString()} tokens
                            </span>
                        </div>

                        {/* Consumed Value */}
                        <div className="bg-app-bg-card p-3 rounded-xl border border-app-border shadow-xs relative flex flex-col justify-between hover:border-slate-300 dark:hover:border-slate-600 transition-colors">
                            <div className="flex items-center justify-between gap-1">
                                <span className="text-[10px] font-bold text-app-text-muted uppercase tracking-wider">Consumed Value</span>
                                <div className="relative group">
                                    <Info className="w-3.5 h-3.5 text-slate-400 hover:text-slate-600 dark:hover:text-slate-300 transition-colors cursor-help" />
                                    <div className="absolute bottom-full right-0 mb-2 w-56 p-2.5 bg-slate-900/95 dark:bg-slate-950/95 text-slate-200 text-[10px] leading-normal rounded-lg shadow-lg border border-slate-700/50 dark:border-slate-800/50 opacity-0 group-hover:opacity-100 pointer-events-none transition-opacity duration-200 z-50 text-left font-medium backdrop-blur-sm">
                                        The total quantity of tokens consumed by all members of your organization during AI analysis runs.
                                    </div>
                                </div>
                            </div>
                            <div className="text-lg sm:text-xl font-bold tracking-tight text-rose-600 dark:text-rose-400 mt-1.5 font-mono whitespace-nowrap">
                                {formatCurrency(reserve.consumed_tokens, reserve.reference_price)}
                            </div>
                            <span className="text-[11px] text-app-text-muted mt-1 block font-mono truncate">
                                {Number(reserve.consumed_tokens || 0).toLocaleString()} tokens
                            </span>
                        </div>

                        {/* Net Remaining Value */}
                        <div className="bg-emerald-50/40 dark:bg-emerald-950/20 p-3 rounded-xl border border-emerald-200/80 dark:border-emerald-800/60 shadow-xs relative flex flex-col justify-between hover:border-emerald-300 dark:hover:border-emerald-700 transition-colors col-span-2 sm:col-span-1">
                            <div className="flex items-center justify-between gap-1">
                                <span className="text-[10px] font-bold text-emerald-700 dark:text-emerald-400 uppercase tracking-wider">Net Remaining Value</span>
                                <div className="relative group">
                                    <Info className="w-3.5 h-3.5 text-emerald-400 hover:text-emerald-600 dark:hover:text-slate-300 transition-colors cursor-help" />
                                    <div className="absolute bottom-full right-0 mb-2 w-56 p-2.5 bg-slate-900/95 dark:bg-slate-950/95 text-slate-200 text-[10px] leading-normal rounded-lg shadow-lg border border-slate-700/50 dark:border-slate-800/50 opacity-0 group-hover:opacity-100 pointer-events-none transition-opacity duration-200 z-50 text-left font-medium backdrop-blur-sm">
                                        The current overall balance of your organization's tokens (Total Approved Value minus Consumed Value).
                                    </div>
                                </div>
                            </div>
                            <div className="text-lg sm:text-xl font-bold tracking-tight text-emerald-700 dark:text-emerald-300 mt-1.5 font-mono whitespace-nowrap">
                                {(() => {
                                    const price = reserve.reference_price || 0.000007;
                                    const approvedUsd = Number(((reserve.purchased_tokens || 0) * price).toFixed(2));
                                    const consumedUsd = Number(((reserve.consumed_tokens || 0) * price).toFixed(2));
                                    return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(approvedUsd - consumedUsd);
                                })()}
                            </div>
                            <span className="text-[11px] text-emerald-600 dark:text-emerald-400 mt-1 block font-mono truncate">
                                {Number((reserve.purchased_tokens || 0) - (reserve.consumed_tokens || 0)).toLocaleString()} tokens
                            </span>
                        </div>
                    </div>
                )
            )}            {/* Sub Tabs / Workspaces Header Toolbar */}
            {(() => {
                const subTabsList = [
                    { id: 'users', label: 'User Quota Allocations', icon: Users, count: usersList.length },
                    { id: 'member_requests', label: 'Member Top-Up Requests', icon: Users, count: memberRequests.length, pendingCount: memberRequests.filter(r => r.status === 'PENDING').length },
                    { id: 'requests', label: 'Org Quota Requests', icon: Coins, count: quotaRequests.length },
                    { id: 'ledger', label: 'Financial Ledger', icon: FileText, count: ledger.length },
                    { id: 'reports', label: 'Daily Usage History', icon: Activity },
                ];
                const selectedTab = subTabsList.find(t => t.id === activeSubTab) || subTabsList[0];
                const SelectedIcon = selectedTab.icon;

                return (
                    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 p-3.5 rounded-2xl bg-white dark:bg-slate-900 border border-slate-200/80 dark:border-slate-800 shadow-xs relative">
                        <div>
                            <h3 className="text-sm font-bold text-slate-900 dark:text-white flex items-center gap-2">
                                <Sliders className="w-4 h-4 text-indigo-500" />
                                TokenOps Workspaces & Telemetry
                            </h3>
                            <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
                                Switch between user allocations, pending requests, audit ledgers, and usage history.
                            </p>
                        </div>

                        {/* Right side: Selected Tab Badge (left of dropdown) + View Dropdown */}
                        <div className="flex items-center gap-2.5 shrink-0 flex-wrap sm:flex-nowrap">
                            {/* Selected Active Tab Indicator */}
                            <div className="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-xl bg-indigo-50 dark:bg-indigo-950/50 text-indigo-700 dark:text-indigo-300 border border-indigo-200/80 dark:border-indigo-800/60 text-xs font-bold shadow-2xs">
                                <SelectedIcon className="w-3.5 h-3.5 text-indigo-600 dark:text-indigo-400 shrink-0" />
                                <span className="whitespace-nowrap">{selectedTab.label}</span>
                                {selectedTab.count !== undefined && (
                                    <span className="px-1.5 py-0.2 text-[10px] font-mono font-bold bg-indigo-200/70 dark:bg-indigo-900/60 text-indigo-800 dark:text-indigo-200 rounded">
                                        {selectedTab.count}
                                    </span>
                                )}
                                {selectedTab.pendingCount > 0 && (
                                    <span className="inline-flex items-center gap-1 px-1.5 py-0.2 rounded-full text-[9px] font-black uppercase bg-rose-500 text-white shadow-xs">
                                        <span className="w-1.5 h-1.5 rounded-full bg-white animate-pulse"></span>
                                        {selectedTab.pendingCount}
                                    </span>
                                )}
                            </div>

                            {/* Dropdown Menu */}
                            <div className="relative">
                                <button
                                    type="button"
                                    onClick={() => setViewDropdownOpen(prev => !prev)}
                                    className="h-8.5 px-3 rounded-xl bg-slate-50 dark:bg-slate-800 hover:bg-slate-100 dark:hover:bg-slate-700/80 text-slate-700 dark:text-slate-200 border border-slate-300 dark:border-slate-700 text-xs font-semibold flex items-center gap-2 shadow-2xs transition-colors cursor-pointer whitespace-nowrap"
                                >
                                    <span>Switch Workspace</span>
                                    <ChevronDown className={`w-3.5 h-3.5 text-slate-400 transition-transform duration-150 ${viewDropdownOpen ? 'rotate-180' : ''}`} />
                                </button>

                                {viewDropdownOpen && (
                                    <>
                                        <div 
                                            className="fixed inset-0 z-40" 
                                            onClick={() => setViewDropdownOpen(false)} 
                                        />
                                        <div className="absolute right-0 mt-1.5 w-64 p-1.5 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl shadow-xl z-50 divide-y divide-slate-100 dark:divide-slate-800/80 animate-in fade-in-50 zoom-in-95">
                                            <div className="px-2.5 py-1.5 text-[10px] font-bold uppercase tracking-wider text-slate-400">
                                                Available Workspaces
                                            </div>
                                            <div className="py-1 space-y-0.5">
                                                {subTabsList.map((tab) => {
                                                    const isSelected = activeSubTab === tab.id;
                                                    const Icon = tab.icon;
                                                    return (
                                                        <button
                                                            key={tab.id}
                                                            type="button"
                                                            onClick={() => {
                                                                setActiveSubTab(tab.id);
                                                                setViewDropdownOpen(false);
                                                            }}
                                                            className={`w-full flex items-center justify-between px-2.5 py-2 rounded-lg text-xs font-semibold transition-colors cursor-pointer text-left ${
                                                                isSelected
                                                                    ? 'bg-indigo-50 dark:bg-indigo-950/50 text-indigo-700 dark:text-indigo-300 font-bold'
                                                                    : 'text-slate-700 dark:text-slate-200 hover:bg-slate-50 dark:hover:bg-slate-800'
                                                            }`}
                                                        >
                                                            <div className="flex items-center gap-2 min-w-0">
                                                                <Icon className={`w-3.5 h-3.5 shrink-0 ${isSelected ? 'text-indigo-600 dark:text-indigo-400' : 'text-slate-400'}`} />
                                                                <span className="truncate">{tab.label}</span>
                                                            </div>
                                                            <div className="flex items-center gap-1.5 shrink-0 ml-2">
                                                                {tab.count !== undefined && (
                                                                    <span className="px-1.5 py-0.2 text-[10px] font-mono text-slate-500 dark:text-slate-400 bg-slate-100 dark:bg-slate-800 rounded">
                                                                        {tab.count}
                                                                    </span>
                                                                )}
                                                                {tab.pendingCount > 0 && (
                                                                    <span className="px-1.5 py-0.2 text-[9px] font-black uppercase rounded bg-rose-500 text-white">
                                                                        {tab.pendingCount}
                                                                    </span>
                                                                )}
                                                                {isSelected && (
                                                                    <Check className="w-3.5 h-3.5 text-indigo-600 dark:text-indigo-400 ml-0.5" />
                                                                )}
                                                            </div>
                                                        </button>
                                                    );
                                                })}
                                            </div>
                                        </div>
                                    </>
                                )}
                            </div>
                        </div>
                    </div>
                );
            })()}

            {/* TAB 1: User Quota Allocations Table */}
            {activeSubTab === 'users' && (
                <div className="bg-app-bg-card rounded-xl border border-app-border overflow-hidden shadow-xs">
                    <div className="p-3.5 sm:p-4 border-b border-app-border bg-app-bg-muted/30 flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                        <div>
                            <h3 className="text-sm font-bold text-app-text-main flex items-center gap-2">
                                <Users className="w-4 h-4 text-indigo-500" /> Team Member Quotas
                            </h3>
                            <p className="text-xs text-app-text-muted mt-0.5">Divide and manage token quotas allocated to individual users in your organization.</p>
                        </div>
                        {reserve?.payg_enabled ? (
                            <div className="text-xs font-semibold bg-amber-500/10 text-amber-700 dark:text-amber-400 px-3 py-1 rounded-full border border-amber-500/25">
                                Pay As You Go Active
                            </div>
                        ) : (
                            <div className="text-xs text-app-text-muted bg-app-bg-card px-3 py-1.5 rounded-lg border border-app-border">
                                Available in Org Reserve:{' '}
                                <span className="font-bold text-indigo-600 dark:text-indigo-400 font-mono">
                                    {formatCurrency(getAvailableReserve(), reserve?.reference_price || 0.000007)}
                                </span>
                                <span className="text-[10px] text-app-text-muted font-mono ml-1">
                                    ({Number(getAvailableReserve()).toLocaleString()} tokens)
                                </span>
                            </div>
                        )}
                    </div>
                    <div className="overflow-x-auto">
                        <table className="w-full text-sm border-collapse">
                            <thead className="bg-app-bg-muted/60 text-app-text-muted border-b border-app-border text-[11px] font-bold uppercase tracking-wider">
                                <tr>
                                    <th className="px-4 py-3 text-left align-middle font-bold">User</th>
                                    <th className="px-4 py-3 text-center align-middle font-bold">Role</th>
                                    <th className="px-4 py-3 text-center align-middle font-bold">Allocated Value</th>
                                    <th className="px-4 py-3 text-center align-middle font-bold">Consumed Value</th>
                                    <th className="px-4 py-3 text-center align-middle font-bold">Remaining Value</th>
                                    <th className="px-4 py-3 text-center align-middle font-bold">Status</th>
                                    <th className="px-4 py-3 text-center align-middle font-bold">Actions</th>
                                </tr>
                            </thead>
                            <tbody className="divide-y divide-app-border text-app-text-main text-xs">
                                {usersList.length === 0 ? (
                                    <tr>
                                        <td colSpan="7" className="px-4 py-8 text-center text-app-text-muted align-middle">
                                            No organization users found.
                                        </td>
                                    </tr>
                                ) : (
                                    usersList.map((u, index) => (
                                        <tr key={u.user_id} className="hover:bg-app-bg-hover transition-colors">
                                            <td className="px-4 py-3 text-left align-middle">
                                                <div className="flex items-center gap-3">
                                                    <div className="w-8 h-8 rounded-full bg-indigo-100 dark:bg-indigo-900/60 text-indigo-700 dark:text-indigo-300 flex items-center justify-center font-bold text-xs shrink-0">
                                                        {(u.name || u.email || 'U')[0].toUpperCase()}
                                                    </div>
                                                    <div className="min-w-0">
                                                        <div className="font-bold text-app-text-main truncate">
                                                            {u.name || `User #${u.user_id}`}
                                                        </div>
                                                        <div className="text-[11px] text-app-text-muted font-mono truncate">
                                                            {u.email || `ID: ${u.user_id}`}
                                                        </div>
                                                    </div>
                                                </div>
                                            </td>
                                            <td className="px-4 py-3 text-center align-middle">
                                                <span className="inline-flex items-center px-2 py-0.5 text-[10px] font-bold rounded-md bg-app-bg-muted border border-app-border text-app-text-muted uppercase tracking-wider">
                                                    {u.role || 'member'}
                                                </span>
                                            </td>
                                            <td className="px-4 py-3 text-center align-middle">
                                                {reserve?.payg_enabled ? (
                                                    <span className="text-app-text-muted font-medium text-xs">N/A (PAYG)</span>
                                                ) : (
                                                    <div className="inline-flex flex-col items-center">
                                                        <span className="font-bold font-mono text-app-text-main">{formatCurrency(u.allocated_tokens, u.reference_price)}</span>
                                                        <span className="text-[10px] text-app-text-muted font-mono">{Number(u.allocated_tokens || 0).toLocaleString()} tokens</span>
                                                    </div>
                                                )}
                                            </td>
                                            <td className="px-4 py-3 text-center align-middle">
                                                <div className="inline-flex flex-col items-center">
                                                    <span className="text-rose-600 dark:text-rose-400 font-bold font-mono">{formatCurrency(u.consumed_tokens, u.reference_price)}</span>
                                                    <span className="text-[10px] text-app-text-muted font-mono">{Number(u.consumed_tokens || 0).toLocaleString()} tokens</span>
                                                </div>
                                            </td>
                                            <td className="px-4 py-3 text-center align-middle">
                                                {reserve?.payg_enabled ? (
                                                    <span className="text-emerald-600 dark:text-emerald-400 font-bold text-xs">Unlimited</span>
                                                ) : (
                                                    <div className="inline-flex flex-col items-center">
                                                        <span className="font-bold font-mono text-indigo-600 dark:text-indigo-400">
                                                            {(() => {
                                                                const price = u.reference_price || 0.000007;
                                                                const allocatedUsd = Number(((u.allocated_tokens || 0) * price).toFixed(2));
                                                                const consumedUsd = Number(((u.consumed_tokens || 0) * price).toFixed(2));
                                                                return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(allocatedUsd - consumedUsd);
                                                            })()}
                                                        </span>
                                                        <span className="text-[10px] text-app-text-muted font-mono">{Number(u.remaining_tokens || 0).toLocaleString()} tokens</span>
                                                    </div>
                                                )}
                                            </td>
                                            <td className="px-4 py-3 text-center align-middle">
                                                {u.is_blocked ? (
                                                    <span className="inline-flex items-center px-2.5 py-0.5 text-xs font-semibold rounded-full bg-rose-50 text-rose-700 dark:bg-rose-950/50 dark:text-rose-400 border border-rose-200/60 dark:border-rose-800/60">
                                                        Blocked
                                                    </span>
                                                ) : (
                                                    <span className="inline-flex items-center px-2.5 py-0.5 text-xs font-semibold rounded-full bg-emerald-50 text-emerald-700 dark:bg-emerald-950/50 dark:text-emerald-400 border border-emerald-200/60 dark:border-emerald-800/60">
                                                        Active
                                                    </span>
                                                )}
                                            </td>
                                            <td className="px-4 py-3 text-center align-middle whitespace-nowrap">
                                                {reserve?.payg_enabled ? (
                                                    <div className="inline-flex items-center justify-center">
                                                        <button
                                                            onClick={() => handleToggleBlock(u.user_id, u.is_blocked)}
                                                            className={`h-7 px-2.5 rounded-lg text-xs font-semibold inline-flex items-center gap-1 transition-colors border shrink-0 cursor-pointer ${
                                                                u.is_blocked
                                                                    ? 'bg-emerald-50 hover:bg-emerald-100 text-emerald-700 border-emerald-300 dark:bg-emerald-950/60 dark:text-emerald-300 dark:border-emerald-800'
                                                                    : 'bg-rose-50 hover:bg-rose-100 text-rose-700 border-rose-200 dark:bg-rose-950/60 dark:text-rose-300 dark:border-rose-800'
                                                            }`}
                                                        >
                                                            {u.is_blocked ? <Check className="w-3.5 h-3.5 text-emerald-500" /> : <Ban className="w-3.5 h-3.5 text-rose-500" />}
                                                            <span>{u.is_blocked ? 'Unblock' : 'Block'}</span>
                                                        </button>
                                                    </div>
                                                ) : (
                                                    <div className="inline-flex items-center justify-center gap-1.5 relative">
                                                        <button
                                                            onClick={() => { setError(''); setAllocateModal({ open: true, userId: u.user_id, userName: u.name || u.email, amount: '', remarks: '' }); }}
                                                            className="h-7 px-2.5 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg text-xs font-semibold inline-flex items-center gap-1 transition-colors shadow-xs cursor-pointer"
                                                        >
                                                            <PlusCircle className="w-3 h-3" />
                                                            Allocate
                                                        </button>
                                                        <div className="relative">
                                                            <button
                                                                onClick={() => setOpenDropdownUserId(openDropdownUserId === u.user_id ? null : u.user_id)}
                                                                className="w-7 h-7 flex items-center justify-center hover:bg-app-bg-hover text-app-text-muted hover:text-app-text-main rounded-lg border border-app-border transition-colors cursor-pointer"
                                                                title="More options"
                                                            >
                                                                <MoreVertical className="w-3.5 h-3.5" />
                                                            </button>
                                                            {openDropdownUserId === u.user_id && (
                                                                <>
                                                                    <div 
                                                                        className="fixed inset-0 z-10" 
                                                                        onClick={() => setOpenDropdownUserId(null)} 
                                                                    />
                                                                    <div className={`absolute right-0 w-44 bg-app-bg-card rounded-xl border border-app-border shadow-lg py-1.5 z-20 text-left ${
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
                                                                            className="w-full px-3.5 py-1.5 text-xs font-semibold text-app-text-main hover:bg-app-bg-hover flex items-center gap-2 transition-colors cursor-pointer"
                                                                        >
                                                                            <ArrowRightLeft className="w-3.5 h-3.5 text-app-text-muted" />
                                                                            Transfer Quota
                                                                        </button>
                                                                        <button
                                                                            onClick={() => {
                                                                                setError('');
                                                                                setOpenDropdownUserId(null);
                                                                                setRevokeModal({ open: true, userId: u.user_id, userName: u.name || u.email, amount: u.remaining_tokens || '' });
                                                                            }}
                                                                            className="w-full px-3.5 py-1.5 text-xs font-semibold text-amber-600 dark:text-amber-400 hover:bg-amber-50 dark:hover:bg-amber-950/20 flex items-center gap-2 transition-colors cursor-pointer"
                                                                        >
                                                                            <MinusCircle className="w-3.5 h-3.5 text-amber-500" />
                                                                            Revoke Quota
                                                                        </button>
                                                                        <div className="border-t border-app-border my-1" />
                                                                        <button
                                                                            onClick={() => {
                                                                                setOpenDropdownUserId(null);
                                                                                handleToggleBlock(u.user_id, u.is_blocked);
                                                                            }}
                                                                            className={`w-full px-3.5 py-1.5 text-xs font-semibold flex items-center gap-2 transition-colors cursor-pointer ${
                                                                                u.is_blocked
                                                                                    ? 'text-emerald-600 dark:text-emerald-400 hover:bg-emerald-50 dark:hover:bg-emerald-950/20'
                                                                                    : 'text-rose-600 dark:text-rose-400 hover:bg-rose-50 dark:hover:bg-rose-950/20'
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

            {/* TAB 2: Member Token Top-Up Requests */}
            {activeSubTab === 'member_requests' && (
                <div className="bg-app-bg-card rounded-xl border border-app-border overflow-hidden shadow-xs">
                    <div className="p-3.5 sm:p-4 border-b border-app-border bg-app-bg-muted/30 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                        <div>
                            <h3 className="text-sm font-bold text-app-text-main flex items-center gap-2">
                                <Users className="w-4 h-4 text-indigo-500" /> Member Token Top-Up Requests
                            </h3>
                            <p className="text-xs text-app-text-muted mt-0.5">
                                Review and approve additional token requests from organization members whose quotas are exhausted.
                            </p>
                        </div>
                        <div className="flex items-center gap-1.5 bg-app-bg-muted p-1 rounded-lg text-xs font-semibold border border-app-border">
                            {['ALL', 'PENDING', 'APPROVED', 'REJECTED'].map((st) => (
                                <button
                                    key={st}
                                    onClick={() => setMemberRequestStatusFilter(st)}
                                    className={`px-2.5 py-1 rounded-md transition-colors cursor-pointer ${
                                        memberRequestStatusFilter === st
                                            ? 'bg-app-bg-card text-indigo-600 dark:text-indigo-400 shadow-xs font-bold'
                                            : 'text-app-text-muted hover:text-app-text-main'
                                    }`}
                                >
                                    {st === 'ALL' ? 'All' : st.charAt(0) + st.slice(1).toLowerCase()}
                                    {st === 'PENDING' && memberRequests.filter(r => r.status === 'PENDING').length > 0 && (
                                        <span className="ml-1.5 px-1.5 py-0.5 rounded-full bg-rose-500 text-white text-[10px] font-bold font-mono inline-flex items-center justify-center min-w-[18px] shadow-2xs">
                                            {memberRequests.filter(r => r.status === 'PENDING').length}
                                        </span>
                                    )}
                                </button>
                            ))}
                        </div>
                    </div>
                    <div className="overflow-x-auto">
                        <table className="w-full text-sm border-collapse">
                            <thead className="bg-app-bg-muted/60 text-app-text-muted border-b border-app-border text-[11px] font-bold uppercase tracking-wider">
                                <tr>
                                    <th className="px-4 py-3 text-left align-middle font-bold">Member</th>
                                    <th className="px-4 py-3 text-center align-middle font-bold">Current Balance</th>
                                    <th className="px-4 py-3 text-center align-middle font-bold">Requested Tokens</th>
                                    <th className="px-4 py-3 text-left align-middle font-bold">Reason / Context</th>
                                    <th className="px-4 py-3 text-center align-middle font-bold">Submitted</th>
                                    <th className="px-4 py-3 text-center align-middle font-bold">Status</th>
                                    <th className="px-4 py-3 text-center align-middle font-bold">Actions</th>
                                </tr>
                            </thead>
                            <tbody className="divide-y divide-app-border text-app-text-main text-xs">
                                {memberRequests.filter(r => memberRequestStatusFilter === 'ALL' || r.status === memberRequestStatusFilter).length === 0 ? (
                                    <tr>
                                        <td colSpan="7" className="px-4 py-8 text-center text-app-text-muted align-middle">
                                            No {memberRequestStatusFilter !== 'ALL' ? memberRequestStatusFilter.toLowerCase() : ''} member top-up requests found.
                                        </td>
                                    </tr>
                                ) : (
                                    memberRequests
                                        .filter(r => memberRequestStatusFilter === 'ALL' || r.status === memberRequestStatusFilter)
                                        .map((r) => (
                                            <tr key={r.id} className="hover:bg-app-bg-hover transition-colors">
                                                <td className="px-4 py-3 text-left align-middle">
                                                    <div className="font-semibold text-app-text-main">{r.user_name}</div>
                                                    {r.user_email && <div className="text-[11px] text-app-text-muted font-mono mt-0.5">{r.user_email}</div>}
                                                </td>
                                                <td className="px-4 py-3 text-center align-middle font-mono text-xs">
                                                    <span className={r.current_remaining_tokens <= 0 ? 'text-rose-600 dark:text-rose-400 font-bold' : 'text-app-text-main'}>
                                                        {Number(r.current_remaining_tokens || 0).toLocaleString()} tokens
                                                    </span>
                                                </td>
                                                <td className="px-4 py-3 text-center align-middle">
                                                    <div className="font-bold text-indigo-600 dark:text-indigo-400 font-mono">
                                                        +{Number(r.requested_tokens || 0).toLocaleString()}
                                                    </div>
                                                    <div className="text-[10px] text-app-text-muted mt-0.5 font-mono">
                                                        {formatCurrency(Number(r.requested_tokens || 0), reserve?.reference_price || 0.000007)}
                                                    </div>
                                                </td>
                                                <td className="px-4 py-3 text-left align-middle text-xs text-app-text-main max-w-xs">
                                                    <p className="line-clamp-2" title={r.reason || ''}>
                                                        {r.reason || <span className="text-app-text-muted italic">No notes provided</span>}
                                                    </p>
                                                    {r.admin_notes && (
                                                        <div className="mt-1 text-[11px] text-app-text-muted italic bg-app-bg-muted p-1.5 rounded">
                                                            Admin note: {r.admin_notes}
                                                        </div>
                                                    )}
                                                </td>
                                                <td className="px-4 py-3 text-center align-middle text-xs text-app-text-muted font-mono whitespace-nowrap">
                                                    {formatDateOnly(r.created_at)}
                                                </td>
                                                <td className="px-4 py-3 text-center align-middle">
                                                    <span className={`inline-flex items-center px-2.5 py-0.5 text-xs font-semibold rounded-full border ${
                                                        r.status === 'APPROVED'
                                                            ? 'bg-emerald-50 text-emerald-700 dark:bg-emerald-950/50 dark:text-emerald-400 border-emerald-200/60 dark:border-emerald-800/60'
                                                            : r.status === 'REJECTED'
                                                            ? 'bg-rose-50 text-rose-700 dark:bg-rose-950/50 dark:text-rose-400 border-rose-200/60 dark:border-rose-800/60'
                                                            : 'bg-amber-50 text-amber-700 dark:bg-amber-950/50 dark:text-amber-400 border-amber-200/60 dark:border-amber-800/60'
                                                    }`}>
                                                        {r.status}
                                                    </span>
                                                </td>
                                                <td className="px-4 py-3 text-center align-middle whitespace-nowrap">
                                                    {r.status === 'PENDING' ? (
                                                        <div className="inline-flex items-center justify-center gap-1.5">
                                                            <button
                                                                onClick={() => setReviewMemberModal({
                                                                    open: true,
                                                                    request: r,
                                                                    action: 'APPROVE',
                                                                    approvedTokens: String(r.requested_tokens),
                                                                    adminNotes: '',
                                                                })}
                                                                disabled={actionLoading}
                                                                className="h-7 px-2.5 bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg text-xs font-semibold shadow-xs transition-colors flex items-center gap-1 cursor-pointer"
                                                            >
                                                                <Check className="w-3 h-3" />
                                                                Approve
                                                            </button>
                                                            <button
                                                                onClick={() => setReviewMemberModal({
                                                                    open: true,
                                                                    request: r,
                                                                    action: 'REJECT',
                                                                    approvedTokens: '',
                                                                    adminNotes: '',
                                                                })}
                                                                disabled={actionLoading}
                                                                className="h-7 px-2.5 bg-rose-50 hover:bg-rose-100 text-rose-700 dark:bg-rose-950/40 dark:hover:bg-rose-900/60 dark:text-rose-300 rounded-lg text-xs font-semibold transition-colors cursor-pointer border border-rose-200 dark:border-rose-800/60"
                                                            >
                                                                <Ban className="w-3 h-3" />
                                                                Reject
                                                            </button>
                                                        </div>
                                                    ) : (
                                                        <span className="text-xs text-app-text-muted">
                                                            {r.reviewed_at ? `Reviewed ${formatDateOnly(r.reviewed_at)}` : '—'}
                                                        </span>
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

            {/* TAB 3: Quota Requests History */}
            {activeSubTab === 'requests' && (
                <div className="bg-app-bg-card rounded-xl border border-app-border overflow-hidden shadow-xs">
                    <div className="p-3.5 sm:p-4 border-b border-app-border bg-app-bg-muted/30 flex items-center justify-between gap-3">
                        <div>
                            <h3 className="text-sm font-bold text-app-text-main flex items-center gap-2">
                                <Coins className="w-4 h-4 text-indigo-500" /> Quota Requests to Super Admin
                            </h3>
                            <p className="text-xs text-app-text-muted mt-0.5">Track submitted token increases and PAYG requests for your organization.</p>
                        </div>
                        <button
                            onClick={() => { setError(''); setRequestModal({ open: true, requestType: 'TOKEN_INCREASE', amount: '', remarks: '' }); }}
                            className="h-8 px-3 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg text-xs font-semibold inline-flex items-center gap-1.5 shadow-xs transition-colors cursor-pointer"
                        >
                            <PlusCircle className="w-3 h-3" />
                            New Quota Request
                        </button>
                    </div>
                    <div className="overflow-x-auto">
                        <table className="w-full text-sm border-collapse">
                            <thead className="bg-app-bg-muted/60 text-app-text-muted border-b border-app-border text-[11px] font-bold uppercase tracking-wider">
                                <tr>
                                    <th className="px-4 py-3 text-center align-middle font-bold whitespace-nowrap">Req #</th>
                                    <th className="px-4 py-3 text-center align-middle font-bold whitespace-nowrap">Type</th>
                                    <th className="px-4 py-3 text-center align-middle font-bold whitespace-nowrap">Requested Quota</th>
                                    <th className="px-4 py-3 text-center align-middle font-bold whitespace-nowrap">Reason</th>
                                    <th className="px-4 py-3 text-center align-middle font-bold whitespace-nowrap">Admin Feedback</th>
                                    <th className="px-4 py-3 text-center align-middle font-bold whitespace-nowrap">Status</th>
                                    <th className="px-4 py-3 text-center align-middle font-bold whitespace-nowrap">Submitted</th>
                                </tr>
                            </thead>
                            <tbody className="divide-y divide-app-border text-app-text-main text-xs">
                                {quotaRequests.length === 0 ? (
                                    <tr>
                                        <td colSpan="7" className="px-4 py-8 text-center text-app-text-muted align-middle whitespace-nowrap">
                                            No quota requests submitted yet.
                                        </td>
                                    </tr>
                                ) : (
                                    quotaRequests.map((r, index) => {
                                        const reqNum = r.request_number || (quotaRequests.length - index);
                                        return (
                                            <tr key={r.id} className="hover:bg-app-bg-hover transition-colors">
                                                <td className="px-4 py-3 text-center align-middle font-mono text-xs font-semibold text-app-text-muted whitespace-nowrap">#{reqNum}</td>
                                                <td className="px-4 py-3 text-center align-middle whitespace-nowrap">
                                                    <span className={`inline-flex items-center px-2 py-0.5 text-[10px] font-bold rounded-md uppercase tracking-wider border whitespace-nowrap ${
                                                        r.request_type === 'TOKEN_INCREASE'
                                                            ? 'bg-indigo-50 text-indigo-700 dark:bg-indigo-950/50 dark:text-indigo-400 border-indigo-200/60 dark:border-indigo-800/60'
                                                            : 'bg-purple-50 text-purple-700 dark:bg-purple-950/50 dark:text-purple-400 border-purple-200/60 dark:border-purple-800/60'
                                                    }`}>
                                                        {r.request_type === 'TOKEN_INCREASE' ? 'Token Increase' : 'PAYG Enablement'}
                                                    </span>
                                                </td>
                                                <td className="px-4 py-3 text-center align-middle font-semibold font-mono whitespace-nowrap">
                                                    {r.request_type === 'TOKEN_INCREASE'
                                                        ? `+${Number(r.requested_tokens || 0).toLocaleString()} Tokens`
                                                        : 'Unlimited PAYG'}
                                                </td>
                                                <td className="px-4 py-3 text-center align-middle text-xs text-app-text-muted">
                                                    {(() => {
                                                        if (!r.remarks) return '—';
                                                        const text = r.remarks.trim();
                                                        if (text.length <= 30) {
                                                            return <span className="whitespace-nowrap">{text}</span>;
                                                        }
                                                        const words = text.split(/\s+/);
                                                        const lines = [];
                                                        let current = '';
                                                        for (const word of words) {
                                                            if ((current ? current + ' ' + word : word).length <= 30) {
                                                                current = current ? current + ' ' + word : word;
                                                            } else {
                                                                if (current) lines.push(current);
                                                                if (word.length > 30) {
                                                                    let rem = word;
                                                                    while (rem.length > 30) {
                                                                        lines.push(rem.slice(0, 30));
                                                                        rem = rem.slice(30);
                                                                    }
                                                                    current = rem;
                                                                } else {
                                                                    current = word;
                                                                }
                                                            }
                                                        }
                                                        if (current) lines.push(current);
                                                        return (
                                                            <div className="flex flex-col items-center justify-center text-center leading-snug">
                                                                {lines.map((line, lIdx) => (
                                                                    <span key={lIdx} className="whitespace-nowrap">{line}</span>
                                                                ))}
                                                            </div>
                                                        );
                                                    })()}
                                                </td>
                                                <td className="px-4 py-3 text-center align-middle text-xs text-app-text-muted whitespace-nowrap">
                                                    {r.admin_notes || '—'}
                                                </td>
                                                <td className="px-4 py-3 text-center align-middle whitespace-nowrap">
                                                    <span className={`inline-flex items-center px-2.5 py-0.5 text-xs font-semibold rounded-full border whitespace-nowrap ${
                                                        r.status === 'APPROVED'
                                                            ? 'bg-emerald-50 text-emerald-700 dark:bg-emerald-950/50 dark:text-emerald-400 border-emerald-200/60 dark:border-emerald-800/60'
                                                            : r.status === 'REJECTED'
                                                            ? 'bg-rose-50 text-rose-700 dark:bg-rose-950/50 dark:text-rose-400 border-rose-200/60 dark:border-rose-800/60'
                                                            : 'bg-amber-50 text-amber-700 dark:bg-amber-950/50 dark:text-amber-400 border-amber-200/60 dark:border-amber-800/60'
                                                    }`}>
                                                        {r.status}
                                                    </span>
                                                </td>
                                                <td className="px-4 py-3 text-center align-middle text-xs text-app-text-muted font-mono whitespace-nowrap">
                                                    {formatDateOnly(r.created_at)}
                                                </td>
                                            </tr>
                                        );
                                    })
                                )}
                            </tbody>
                        </table>
                    </div>
                </div>
            )}

            {/* TAB 4: Financial Ledger */}
            {activeSubTab === 'ledger' && (() => {
                const handleLedgerSort = (key) => {
                    if (ledgerSortKey === key) {
                        setLedgerSortOrder(prev => prev === 'asc' ? 'desc' : 'asc');
                    } else {
                        setLedgerSortKey(key);
                        setLedgerSortOrder('desc');
                    }
                };

                const handleFilterChange = (filterId) => {
                    setLedgerFilter(filterId);
                    setLedgerPage(1);
                    fetchLedgerData(1, ledgerPageSize, filterId, ledgerSearch);
                };

                const handlePageChange = (newPage) => {
                    if (newPage < 1 || newPage === ledgerPage) return;
                    setLedgerPage(newPage);
                    fetchLedgerData(newPage, ledgerPageSize, ledgerFilter, ledgerSearch);
                };

                const handlePageSizeChange = (newSize) => {
                    setLedgerPageSize(newSize);
                    setLedgerPage(1);
                    fetchLedgerData(1, newSize, ledgerFilter, ledgerSearch);
                };

                const sortedLedger = [...ledger].sort((a, b) => {
                    let valA = a[ledgerSortKey];
                    let valB = b[ledgerSortKey];
                    if (ledgerSortKey === 'created_at') {
                        valA = new Date(a.created_at || 0).getTime();
                        valB = new Date(b.created_at || 0).getTime();
                    } else if (ledgerSortKey === 'transaction_id' || ledgerSortKey === 'token_delta' || ledgerSortKey === 'balance_after') {
                        valA = Number(valA || 0);
                        valB = Number(valB || 0);
                    }
                    if (valA < valB) return ledgerSortOrder === 'asc' ? -1 : 1;
                    if (valA > valB) return ledgerSortOrder === 'asc' ? 1 : -1;
                    return 0;
                });

                const totalPages = Math.max(1, Math.ceil(ledgerTotal / ledgerPageSize));

                return (
                    <div className="bg-app-bg-card rounded-xl border border-app-border overflow-hidden shadow-xs">
                        {/* Ledger Header & Quick Filters Bar */}
                        <div className="p-3.5 sm:p-4 border-b border-app-border bg-app-bg-muted/30 flex flex-col lg:flex-row lg:items-center justify-between gap-3">
                            <div>
                                <h3 className="text-sm font-bold text-app-text-main flex items-center gap-2">
                                    <FileText className="w-4 h-4 text-indigo-500" /> Organization Financial Ledger
                                    {ledgerLoading && <RefreshCw className="w-3.5 h-3.5 animate-spin text-indigo-500" />}
                                </h3>
                                <p className="text-xs text-app-text-muted mt-0.5">
                                    Audited token allocations, revocations, and AI usage.
                                </p>
                            </div>

                            <div className="flex items-center gap-2.5 flex-nowrap shrink-0">
                                {/* Active Ledger Filter Badge (left to the dropdown) */}
                                {(() => {
                                    const ledgerFilterOptions = [
                                        { id: 'ALL', label: `All (${allLedgerTotal || ledgerTotal || 0})` },
                                        { id: 'AI_CONSUMPTION', label: 'AI Consumption' },
                                        { id: 'ALLOCATION', label: 'Allocations / Top-ups' },
                                        { id: 'REVOCATION', label: 'Revocations' }
                                    ];
                                    const currentFilter = ledgerFilterOptions.find(f => f.id === ledgerFilter) || ledgerFilterOptions[0];

                                    return (
                                        <>
                                            <div className="inline-flex items-center px-3 py-1.5 rounded-lg bg-indigo-50 dark:bg-indigo-950/50 text-indigo-700 dark:text-indigo-300 border border-indigo-200/80 dark:border-indigo-800/60 text-xs font-bold shadow-2xs shrink-0 whitespace-nowrap">
                                                <span>{currentFilter.label}</span>
                                            </div>

                                            {/* Filter Dropdown Menu */}
                                            <div className="relative shrink-0">
                                                <button
                                                    type="button"
                                                    onClick={() => setLedgerFilterDropdownOpen(prev => !prev)}
                                                    className="h-8.5 px-3 rounded-lg bg-slate-50 dark:bg-slate-800 hover:bg-slate-100 dark:hover:bg-slate-700/80 text-slate-700 dark:text-slate-200 border border-slate-300 dark:border-slate-700 text-xs font-semibold flex items-center gap-1.5 shadow-2xs transition-colors cursor-pointer whitespace-nowrap"
                                                >
                                                    <span>Filter Type</span>
                                                    <ChevronDown className={`w-3.5 h-3.5 text-slate-400 transition-transform duration-150 ${ledgerFilterDropdownOpen ? 'rotate-180' : ''}`} />
                                                </button>

                                                {ledgerFilterDropdownOpen && (
                                                    <>
                                                        <div 
                                                            className="fixed inset-0 z-40" 
                                                            onClick={() => setLedgerFilterDropdownOpen(false)} 
                                                        />
                                                        <div className="absolute right-0 mt-1.5 w-52 p-1.5 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl shadow-xl z-50 animate-in fade-in-50 zoom-in-95 space-y-0.5">
                                                            <div className="px-2.5 py-1 text-[10px] font-bold uppercase tracking-wider text-slate-400">
                                                                Filter Records
                                                            </div>
                                                            {ledgerFilterOptions.map(f => {
                                                                const isSelected = ledgerFilter === f.id;
                                                                return (
                                                                    <button
                                                                        key={f.id}
                                                                        type="button"
                                                                        onClick={() => {
                                                                            handleFilterChange(f.id);
                                                                            setLedgerFilterDropdownOpen(false);
                                                                        }}
                                                                        className={`w-full flex items-center justify-between px-2.5 py-1.5 rounded-lg text-xs font-medium text-left transition-colors cursor-pointer ${
                                                                            isSelected
                                                                                ? 'bg-indigo-50 dark:bg-indigo-950/60 text-indigo-600 dark:text-indigo-400 font-semibold'
                                                                                : 'text-slate-700 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800'
                                                                        }`}
                                                                    >
                                                                        <span>{f.label}</span>
                                                                        {isSelected && <Check className="w-3.5 h-3.5 text-indigo-600 dark:text-indigo-400" />}
                                                                    </button>
                                                                );
                                                            })}
                                                        </div>
                                                    </>
                                                )}
                                            </div>
                                        </>
                                    );
                                })()}

                                {/* Search Input */}
                                <div className="relative shrink-0">
                                    <Search className="w-3.5 h-3.5 text-slate-400 absolute left-2.5 top-1/2 -translate-y-1/2" />
                                    <input
                                        type="text"
                                        value={ledgerSearch}
                                        onChange={(e) => setLedgerSearch(e.target.value)}
                                        placeholder="Search user, ref..."
                                        className="pl-8 pr-2.5 py-1.5 text-xs rounded-lg border border-app-border bg-app-bg-card text-app-text-main focus:outline-hidden focus:ring-1 focus:ring-indigo-500 w-36 sm:w-44 h-8.5"
                                    />
                                </div>
                            </div>
                        </div>

                        <div className="overflow-x-auto">
                            <table className="w-full text-sm border-collapse">
                                <thead className="bg-app-bg-muted/60 text-app-text-muted border-b border-app-border text-[11px] font-bold uppercase tracking-wider">
                                    <tr>
                                        <th 
                                            onClick={() => handleLedgerSort('transaction_id')} 
                                            className="px-4 py-3 text-center align-middle font-bold cursor-pointer hover:bg-app-bg-hover transition-colors select-none group"
                                            title="Click to sort by Transaction ID"
                                        >
                                            <div className="inline-flex items-center justify-center gap-1">
                                                <span>Tx #</span>
                                                {ledgerSortKey === 'transaction_id' ? (
                                                    ledgerSortOrder === 'asc' ? <ChevronUp className="w-3.5 h-3.5 text-indigo-500" /> : <ChevronDown className="w-3.5 h-3.5 text-indigo-500" />
                                                ) : (
                                                    <ArrowUpDown className="w-3 h-3 text-slate-400 opacity-40 group-hover:opacity-100 transition-opacity" />
                                                )}
                                            </div>
                                        </th>
                                        <th className="px-4 py-3 text-center align-middle font-bold">Type</th>
                                        <th className="px-4 py-3 text-left align-middle font-bold">User</th>
                                        <th className="px-4 py-3 text-left align-middle font-bold">Circumstance / Purpose</th>
                                        <th 
                                            onClick={() => handleLedgerSort('token_delta')} 
                                            className="px-4 py-3 text-center align-middle font-bold cursor-pointer hover:bg-app-bg-hover transition-colors select-none group"
                                            title="Click to sort by Token Delta"
                                        >
                                            <div className="inline-flex items-center justify-center gap-1">
                                                <span>Token Delta</span>
                                                {ledgerSortKey === 'token_delta' ? (
                                                    ledgerSortOrder === 'asc' ? <ChevronUp className="w-3.5 h-3.5 text-indigo-500" /> : <ChevronDown className="w-3.5 h-3.5 text-indigo-500" />
                                                ) : (
                                                    <ArrowUpDown className="w-3 h-3 text-slate-400 opacity-40 group-hover:opacity-100 transition-opacity" />
                                                )}
                                            </div>
                                        </th>
                                        <th 
                                            onClick={() => handleLedgerSort('balance_after')} 
                                            className="px-4 py-3 text-center align-middle font-bold cursor-pointer hover:bg-app-bg-hover transition-colors select-none group"
                                            title="Click to sort by Balance After (Tokens)"
                                        >
                                            <div className="inline-flex items-center justify-center gap-1">
                                                <span>Balance After (Tokens)</span>
                                                {ledgerSortKey === 'balance_after' ? (
                                                    ledgerSortOrder === 'asc' ? <ChevronUp className="w-3.5 h-3.5 text-indigo-500" /> : <ChevronDown className="w-3.5 h-3.5 text-indigo-500" />
                                                ) : (
                                                    <ArrowUpDown className="w-3 h-3 text-slate-400 opacity-40 group-hover:opacity-100 transition-opacity" />
                                                )}
                                            </div>
                                        </th>
                                        <th className="px-4 py-3 text-center align-middle font-bold whitespace-nowrap">PAYG Cost (USD)</th>
                                        <th className="px-4 py-3 text-left align-middle font-bold">Remarks / Ref</th>
                                        <th 
                                            onClick={() => handleLedgerSort('created_at')} 
                                            className="px-4 py-3 text-center align-middle font-bold cursor-pointer hover:bg-app-bg-hover transition-colors select-none group whitespace-nowrap"
                                            title="Click to sort by Timestamp"
                                        >
                                            <div className="inline-flex items-center justify-center gap-1">
                                                <span>Timestamp {localTimezone ? `(${localTimezone})` : ''}</span>
                                                {ledgerSortKey === 'created_at' ? (
                                                    ledgerSortOrder === 'asc' ? <ChevronUp className="w-3.5 h-3.5 text-indigo-500" /> : <ChevronDown className="w-3.5 h-3.5 text-indigo-500" />
                                                ) : (
                                                    <ArrowUpDown className="w-3 h-3 text-slate-400 opacity-40 group-hover:opacity-100 transition-opacity" />
                                                )}
                                            </div>
                                        </th>
                                    </tr>
                                </thead>
                                <tbody className="divide-y divide-app-border text-app-text-main text-xs">
                                    {sortedLedger.length === 0 ? (
                                        <tr>
                                            <td colSpan="9" className="px-4 py-8 text-center text-app-text-muted align-middle">
                                                {ledgerLoading ? (
                                                    <div className="flex items-center justify-center gap-2">
                                                        <RefreshCw className="w-4 h-4 animate-spin text-indigo-500" />
                                                        <span>Loading transactions...</span>
                                                    </div>
                                                ) : (
                                                    ledgerTotal === 0 ? 'No transaction entries recorded yet.' : 'No transactions match the selected filter.'
                                                )}
                                            </td>
                                        </tr>
                                    ) : (
                                        sortedLedger.map((tx) => (
                                            <tr key={tx.global_transaction_id || tx.transaction_id} className="hover:bg-app-bg-hover transition-colors">
                                                <td className="px-4 py-3 text-center align-middle font-mono text-xs text-app-text-muted">
                                                    <span 
                                                        className="font-semibold text-app-text-main bg-slate-100 dark:bg-slate-800 px-2 py-0.5 rounded border border-app-border"
                                                        title={tx.global_transaction_id ? `Platform Audit Ref: #${tx.global_transaction_id}` : undefined}
                                                    >
                                                        #{tx.transaction_id}
                                                    </span>
                                                </td>
                                                <td className="px-4 py-3 text-center align-middle">
                                                    <span className="inline-flex items-center px-2 py-0.5 text-[10px] font-bold rounded-md bg-app-bg-muted border border-app-border text-app-text-muted uppercase tracking-wider">
                                                        {tx.transaction_type}
                                                    </span>
                                                </td>
                                                <td className="px-4 py-3 text-left align-middle text-app-text-main">
                                                    {tx.user_name ? (
                                                        <div>
                                                            <div className="font-semibold text-app-text-main">{tx.user_name}</div>
                                                            {tx.user_email && <div className="text-[10px] text-app-text-muted font-mono mt-0.5">{tx.user_email}</div>}
                                                        </div>
                                                    ) : (
                                                        tx.user_id ? `User #${tx.user_id}` : 'Organization'
                                                    )}
                                                </td>
                                                <td className="px-4 py-3 text-left align-middle">
                                                    <div className="flex flex-col items-start gap-1.5">
                                                        {renderPurposeBadge(tx.purpose, tx.transaction_type)}
                                                        <div className="flex items-center gap-1.5 flex-wrap">
                                                            {tx.project_name && (
                                                                <div 
                                                                    className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[10px] font-medium bg-app-bg-muted text-app-text-muted border border-app-border max-w-[180px] truncate" 
                                                                    title={`Project: ${tx.project_name}`}
                                                                >
                                                                    <Folder className="w-3 h-3 text-indigo-500 shrink-0" />
                                                                    <span className="truncate">{tx.project_name}</span>
                                                                </div>
                                                            )}
                                                            {extractModelFromRemarks(tx.remarks) && (
                                                                <div
                                                                    className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-md text-[9px] font-medium bg-indigo-50/70 dark:bg-indigo-950/40 text-indigo-600 dark:text-indigo-400 border border-indigo-200/50 dark:border-indigo-800/40"
                                                                    title={`AI Model: ${extractModelFromRemarks(tx.remarks)}`}
                                                                >
                                                                    <Cpu className="w-2.5 h-2.5 text-indigo-500 shrink-0" />
                                                                    <span>{extractModelFromRemarks(tx.remarks)}</span>
                                                                </div>
                                                            )}
                                                        </div>
                                                    </div>
                                                </td>
                                                <td className={`px-4 py-3 text-center align-middle font-bold ${tx.token_delta >= 0 ? 'text-emerald-600 dark:text-emerald-400' : 'text-rose-600 dark:text-rose-400'}`}>
                                                    <div className="font-semibold font-mono text-xs">
                                                        {tx.token_delta >= 0 ? '+' : ''}
                                                        {Number(tx.token_delta).toLocaleString()}
                                                    </div>
                                                    <div className="text-[10px] text-app-text-muted font-mono mt-0.5">
                                                        {tx.token_delta >= 0 ? '+' : ''}
                                                        {formatCurrency(tx.token_delta, reserve?.reference_price || 0.000007)}
                                                    </div>
                                                </td>
                                                <td className="px-4 py-3 text-center align-middle font-mono text-xs text-app-text-main font-semibold">
                                                    {tx.balance_after !== null && tx.balance_after !== undefined
                                                        ? Number(tx.balance_after).toLocaleString()
                                                        : '—'}
                                                </td>
                                                <td className="px-4 py-3 text-center align-middle font-mono text-xs text-emerald-600 dark:text-emerald-400 font-semibold">
                                                    {tx.payg_cost_usd !== null && tx.payg_cost_usd !== undefined
                                                        ? `$${Number(tx.payg_cost_usd).toFixed(4)}`
                                                        : '—'}
                                                </td>
                                                <td className="px-4 py-3 text-left align-middle text-xs text-app-text-muted truncate max-w-xs">
                                                    {tx.remarks || tx.reference_id || '—'}
                                                </td>
                                                <td className="px-4 py-3 text-center align-middle text-xs text-app-text-muted font-mono whitespace-nowrap">
                                                    {formatTimestamp(tx.created_at)}
                                                </td>
                                            </tr>
                                        ))
                                    )}
                                </tbody>
                            </table>
                        </div>

                        {/* Pagination Footer */}
                        <div className="p-3.5 sm:p-4 border-t border-app-border bg-app-bg-muted/20 flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-xs">
                            <div className="flex items-center gap-1.5 text-app-text-muted">
                                <span>Showing</span>
                                <span className="font-bold text-app-text-main font-mono">
                                    {ledgerTotal === 0 ? 0 : (ledgerPage - 1) * ledgerPageSize + 1}
                                </span>
                                <span>to</span>
                                <span className="font-bold text-app-text-main font-mono">
                                    {Math.min(ledgerPage * ledgerPageSize, ledgerTotal)}
                                </span>
                                <span>of</span>
                                <span className="font-bold text-app-text-main font-mono">
                                    {Number(ledgerTotal).toLocaleString()}
                                </span>
                                <span>entries</span>
                                {ledgerLoading && (
                                    <RefreshCw className="w-3.5 h-3.5 animate-spin text-indigo-500 ml-2" />
                                )}
                            </div>

                            <div className="flex flex-wrap items-center gap-3">
                                {/* Rows Per Page Selector */}
                                <div className="flex items-center gap-1.5 text-app-text-muted">
                                    <span className="whitespace-nowrap">Rows per page:</span>
                                    <select
                                        value={ledgerPageSize}
                                        onChange={(e) => handlePageSizeChange(Number(e.target.value))}
                                        className="px-2 py-1 bg-app-bg-card border border-app-border rounded-lg text-xs font-semibold text-app-text-main focus:ring-1 focus:ring-indigo-500 cursor-pointer"
                                    >
                                        <option value={10}>10</option>
                                        <option value={25}>25</option>
                                        <option value={50}>50</option>
                                        <option value={100}>100</option>
                                    </select>
                                </div>

                                {/* Page Navigation Buttons */}
                                <div className="inline-flex items-center gap-1">
                                    <button
                                        type="button"
                                        disabled={ledgerPage <= 1 || ledgerLoading}
                                        onClick={() => handlePageChange(ledgerPage - 1)}
                                        className="px-2.5 py-1.5 rounded-lg border border-app-border bg-app-bg-card hover:bg-app-bg-hover text-app-text-main disabled:opacity-40 disabled:cursor-not-allowed transition-colors font-medium flex items-center gap-1 cursor-pointer"
                                        title="Previous Page"
                                    >
                                        <ChevronLeft className="w-3.5 h-3.5" />
                                        <span>Prev</span>
                                    </button>

                                    {/* Numbered Page Buttons */}
                                    {(() => {
                                        const pages = [];
                                        for (let p = 1; p <= totalPages; p++) {
                                            if (p === 1 || p === totalPages || (p >= ledgerPage - 1 && p <= ledgerPage + 1)) {
                                                pages.push(p);
                                            } else if (pages[pages.length - 1] !== '...') {
                                                pages.push('...');
                                            }
                                        }
                                        return pages.map((p, idx) => {
                                            if (p === '...') {
                                                return <span key={`ellipsis-${idx}`} className="px-1 text-app-text-muted select-none">...</span>;
                                            }
                                            const isCurrent = p === ledgerPage;
                                            return (
                                                <button
                                                    key={p}
                                                    type="button"
                                                    disabled={ledgerLoading}
                                                    onClick={() => handlePageChange(p)}
                                                    className={`min-w-[28px] h-7 px-1.5 rounded-lg text-xs font-semibold transition-colors cursor-pointer ${
                                                        isCurrent
                                                            ? 'bg-indigo-600 text-white shadow-xs'
                                                            : 'border border-app-border bg-app-bg-card hover:bg-app-bg-hover text-app-text-main'
                                                    }`}
                                                >
                                                    {p}
                                                </button>
                                            );
                                        });
                                    })()}

                                    <button
                                        type="button"
                                        disabled={ledgerPage >= totalPages || ledgerLoading}
                                        onClick={() => handlePageChange(ledgerPage + 1)}
                                        className="px-2.5 py-1.5 rounded-lg border border-app-border bg-app-bg-card hover:bg-app-bg-hover text-app-text-main disabled:opacity-40 disabled:cursor-not-allowed transition-colors font-medium flex items-center gap-1 cursor-pointer"
                                        title="Next Page"
                                    >
                                        <span>Next</span>
                                        <ChevronRight className="w-3.5 h-3.5" />
                                    </button>
                                </div>
                            </div>
                        </div>
                    </div>
                );
            })()}

            {/* TAB 5: Daily Usage History */}
            {activeSubTab === 'reports' && (
                <div className="bg-app-bg-card rounded-xl border border-app-border overflow-hidden shadow-xs">
                    <div className="overflow-x-auto">
                        <table className="w-full text-sm border-collapse">
                            <thead className="bg-app-bg-muted/60 text-app-text-muted border-b border-app-border text-[11px] font-bold uppercase tracking-wider">
                                <tr>
                                    <th className="px-4 py-3 text-center align-middle font-bold">Date</th>
                                    <th className="px-4 py-3 text-center align-middle font-bold">Tokens Consumed</th>
                                    <th className="px-4 py-3 text-center align-middle font-bold">Total Requests</th>
                                </tr>
                            </thead>
                            <tbody className="divide-y divide-app-border text-app-text-main text-xs">
                                {dailyUsage.length === 0 ? (
                                    <tr>
                                        <td colSpan="3" className="px-4 py-8 text-center text-app-text-muted align-middle">
                                            No daily usage records available.
                                        </td>
                                    </tr>
                                ) : (
                                    dailyUsage.map((d, idx) => (
                                        <tr key={idx} className="hover:bg-app-bg-hover transition-colors">
                                            <td className="px-4 py-3 text-center align-middle font-medium font-mono">{d.date}</td>
                                            <td className="px-4 py-3 text-center align-middle font-bold font-mono text-rose-600 dark:text-rose-400">
                                                {Number(d.tokens || 0).toLocaleString()}
                                            </td>
                                            <td className="px-4 py-3 text-center align-middle font-medium">{d.requests || 0}</td>
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
                            {reserve?.payg_enabled ? (
                                <div className="space-y-4">
                                    <div className="p-4 bg-indigo-50 dark:bg-indigo-950/40 border border-indigo-200 dark:border-indigo-800 rounded-xl animate-in fade-in slide-in-from-top-2 duration-200">
                                        <div className="font-bold text-sm text-indigo-700 dark:text-indigo-300 flex items-center gap-1.5">
                                            <Coins className="w-4.5 h-4.5 text-indigo-500" />
                                            Switch to Prepaid Mode
                                        </div>
                                        <p className="text-xs text-slate-600 dark:text-slate-400 mt-1.5 leading-relaxed font-medium">
                                            Request the platform Super Admin to disable Pay As You Go (PAYG) billing. This will revert your organization back to static prepaid token pool allocations.
                                        </p>
                                    </div>
                                </div>
                            ) : (
                                <>
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
                                                <div className="text-[11px] text-slate-400 font-normal mt-0.5">Pay As You Go (Post-paid)</div>
                                            </button>
                                        </div>
                                    </div>

                                    {requestModal.requestType === 'PAYG_ENABLEMENT' && (
                                        <div className="p-3 bg-amber-50 dark:bg-amber-950/20 border border-amber-200 dark:border-amber-900/50 rounded-xl text-amber-800 dark:text-amber-300 space-y-1.5 animate-in fade-in slide-in-from-top-2 duration-200">
                                            <div className="text-xs font-bold flex items-center gap-1.5">
                                                <AlertCircle className="w-4 h-4 text-amber-500 flex-shrink-0" />
                                                PAYG (Pay As You Go) Mode Disclaimer
                                            </div>
                                            <p className="text-[10px] leading-relaxed font-medium">
                                                Enabling Pay As You Go (PAYG) mode shifts your organization to post-paid billing. 
                                                <strong className="block mt-1 text-amber-900 dark:text-amber-200">
                                                    ⚠️ Note: Any tokens currently remaining in your prepaid organization reserve or user wallets will be locked. Platform calculations and usage limits will be based entirely on Pay As You Go consumption rates.
                                                </strong>
                                            </p>
                                        </div>
                                    )}

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
                                </>
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

            {/* MODAL 5: Review Member Top-Up Request Modal */}
            {reviewMemberModal.open && reviewMemberModal.request && (
                <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-[9999] flex items-center justify-center p-4">
                    <div className="bg-white dark:bg-slate-800 rounded-2xl max-w-md w-full p-6 border border-slate-200 dark:border-slate-700 shadow-2xl animate-in fade-in zoom-in-95 duration-200">
                        <div className="flex items-center gap-2 mb-2">
                            {reviewMemberModal.action === 'APPROVE' ? (
                                <div className="p-2 rounded-xl bg-emerald-100 dark:bg-emerald-950/60 text-emerald-600 dark:text-emerald-400">
                                    <CheckCircle2 className="w-5 h-5" />
                                </div>
                            ) : (
                                <div className="p-2 rounded-xl bg-rose-100 dark:bg-rose-950/60 text-rose-600 dark:text-rose-400">
                                    <AlertCircle className="w-5 h-5" />
                                </div>
                            )}
                            <div>
                                <h3 className="text-lg font-bold text-slate-900 dark:text-white">
                                    {reviewMemberModal.action === 'APPROVE' ? 'Approve Member Top-Up' : 'Reject Member Request'}
                                </h3>
                                <p className="text-xs text-slate-500">
                                    Request from <span className="font-semibold text-slate-800 dark:text-slate-200">{reviewMemberModal.request.user_name}</span>
                                </p>
                            </div>
                        </div>

                        {error && (
                            <div className="p-3 my-3 bg-rose-50 dark:bg-rose-950/40 border border-rose-200 dark:border-rose-800 rounded-xl flex items-center gap-2 text-rose-700 dark:text-rose-300 text-xs">
                                <AlertCircle className="w-4 h-4 flex-shrink-0" />
                                <span className="font-semibold">{error}</span>
                            </div>
                        )}

                        <div className="my-4 p-3 bg-slate-50 dark:bg-slate-900/60 border border-slate-100 dark:border-slate-800 rounded-xl space-y-2 text-xs">
                            <div className="flex justify-between">
                                <span className="text-slate-500">Requested Amount:</span>
                                <span className="font-mono font-bold text-indigo-600 dark:text-indigo-400">
                                    +{Number(reviewMemberModal.request.requested_tokens).toLocaleString()} tokens
                                </span>
                            </div>
                            <div className="flex justify-between">
                                <span className="text-slate-500">Current User Balance:</span>
                                <span className="font-mono font-semibold text-rose-500">
                                    {Number(reviewMemberModal.request.current_remaining_tokens || 0).toLocaleString()} tokens
                                </span>
                            </div>
                            {reviewMemberModal.action === 'APPROVE' && (
                                <div className="flex justify-between pt-1 border-t border-slate-200 dark:border-slate-700">
                                    <span className="text-slate-500">Available in Org Reserve:</span>
                                    <span className="font-mono font-bold text-emerald-600 dark:text-emerald-400">
                                        {Number(reserve?.reserved_tokens || 0).toLocaleString()} tokens
                                    </span>
                                </div>
                            )}
                            {reviewMemberModal.request.reason && (
                                <div className="pt-2 border-t border-slate-200 dark:border-slate-700">
                                    <span className="text-slate-500 block mb-0.5">Member's Reason:</span>
                                    <p className="text-slate-700 dark:text-slate-300 italic">{reviewMemberModal.request.reason}</p>
                                </div>
                            )}
                        </div>

                        <form
                            onSubmit={(e) => {
                                e.preventDefault();
                                handleReviewMemberRequest(
                                    reviewMemberModal.request.id,
                                    reviewMemberModal.action,
                                    reviewMemberModal.action === 'APPROVE' ? reviewMemberModal.approvedTokens : undefined,
                                    reviewMemberModal.adminNotes
                                );
                            }}
                            className="space-y-4"
                        >
                            {reviewMemberModal.action === 'APPROVE' && (
                                <div>
                                    <div className="flex items-center justify-between mb-1">
                                        <label className="text-xs font-semibold text-slate-700 dark:text-slate-300">
                                            Approved Token Amount
                                        </label>
                                        <span className="text-[11px] text-indigo-600 dark:text-indigo-400 font-semibold font-mono">
                                            {formatCurrency(Number(reviewMemberModal.approvedTokens || 0), reserve?.reference_price || 0.000007)}
                                        </span>
                                    </div>
                                    <input
                                        type="number"
                                        min="1"
                                        max={reserve?.reserved_tokens || 99999999}
                                        required
                                        value={reviewMemberModal.approvedTokens}
                                        onChange={(e) => setReviewMemberModal({ ...reviewMemberModal, approvedTokens: e.target.value })}
                                        placeholder="e.g. 25000"
                                        className="w-full px-4 py-2.5 rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900 text-slate-900 dark:text-white text-sm focus:ring-2 focus:ring-emerald-500 focus:outline-none transition-all font-mono"
                                    />
                                    {Number(reviewMemberModal.approvedTokens) > (reserve?.reserved_tokens || 0) && (
                                        <p className="text-[11px] text-rose-500 font-semibold mt-1">
                                            Warning: Exceeds currently available org reserve ({Number(reserve?.reserved_tokens || 0).toLocaleString()} tokens).
                                        </p>
                                    )}
                                </div>
                            )}

                            <div>
                                <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                                    Admin Note / Remarks {reviewMemberModal.action === 'REJECT' && <span className="text-rose-500">*</span>}
                                </label>
                                <textarea
                                    rows="2"
                                    required={reviewMemberModal.action === 'REJECT'}
                                    value={reviewMemberModal.adminNotes}
                                    onChange={(e) => setReviewMemberModal({ ...reviewMemberModal, adminNotes: e.target.value })}
                                    placeholder={
                                        reviewMemberModal.action === 'APPROVE'
                                            ? 'e.g. Approved for sprint project analysis...'
                                            : 'e.g. Please coordinate with team lead or reduce test file size...'
                                    }
                                    className="w-full px-4 py-2 rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900 text-slate-900 dark:text-white text-xs focus:ring-2 focus:ring-indigo-500 focus:outline-none transition-all"
                                />
                            </div>

                            <div className="flex justify-end gap-3 mt-6">
                                <button
                                    type="button"
                                    onClick={() => { setError(''); setReviewMemberModal({ open: false, request: null, action: 'APPROVE', approvedTokens: '', adminNotes: '' }); }}
                                    className="px-4 py-2 text-sm font-semibold text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-700 rounded-xl transition"
                                >
                                    Cancel
                                </button>
                                <button
                                    type="submit"
                                    disabled={actionLoading || (reviewMemberModal.action === 'APPROVE' && Number(reviewMemberModal.approvedTokens) > (reserve?.reserved_tokens || 0))}
                                    className={`px-4 py-2 text-sm font-semibold text-white rounded-xl shadow-md transition ${
                                        reviewMemberModal.action === 'APPROVE'
                                            ? 'bg-emerald-600 hover:bg-emerald-700'
                                            : 'bg-rose-600 hover:bg-rose-700'
                                    }`}
                                >
                                    {actionLoading ? 'Processing...' : reviewMemberModal.action === 'APPROVE' ? 'Approve & Allocate' : 'Reject Request'}
                                </button>
                            </div>
                        </form>
                    </div>
                </div>
            )}
        </div>
    );
}
