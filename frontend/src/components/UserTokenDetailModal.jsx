import React, { useState } from 'react';
import { Coins, DollarSign, Activity, X, Sparkles, Zap, Clock, AlertCircle, CheckCircle2, Send, HelpCircle } from 'lucide-react';
import { API_ENDPOINTS } from '../config';

const localTimezone = (() => {
    try {
        return new Intl.DateTimeFormat(undefined, { timeZoneName: 'short' })
            .formatToParts(new Date())
            .find(part => part.type === 'timeZoneName')?.value || '';
    } catch (e) {
        return '';
    }
})();

export default function UserTokenDetailModal({ isOpen, onClose, data, onRefresh, loading }) {
    const [showRequestModal, setShowRequestModal] = useState(false);
    const [requestAmount, setRequestAmount] = useState(10000);
    const [customAmount, setCustomAmount] = useState('');
    const [isCustom, setIsCustom] = useState(false);
    const [requestReason, setRequestReason] = useState('');
    const [submitting, setSubmitting] = useState(false);
    const [submitError, setSubmitError] = useState('');
    const [submitSuccess, setSubmitSuccess] = useState('');

    if (!isOpen || !data) return null;

    const allocated = Number(data.allocated_tokens || 0);
    const consumed = Number(data.consumed_tokens || 0);
    const remaining = Number(data.remaining_tokens || 0);
    const isPayg = Boolean(data.is_payg);
    const totalCostUsd = Number(data.total_cost_usd || 0);
    const recentLogs = data.recent_usage || [];
    const latestRequest = data.latest_request || null;
    const isPending = latestRequest && latestRequest.status === 'PENDING';
    const isExhausted = !isPayg && remaining <= 0;
    const referencePrice = Number(data.reference_price || 0.000007);

    const usagePercent = allocated > 0 ? Math.min(100, Math.round((consumed / allocated) * 100)) : (consumed > 0 ? 100 : 0);

    const effectiveAmount = isCustom ? (parseInt(customAmount, 10) || 0) : requestAmount;
    const estimatedValue = effectiveAmount * referencePrice;

    const handlePresetClick = (amount) => {
        setIsCustom(false);
        setRequestAmount(amount);
    };

    const handleCustomClick = () => {
        setIsCustom(true);
        if (!customAmount) setCustomAmount(String(requestAmount || 15000));
    };

    const handleSubmitTopUp = async (e) => {
        e.preventDefault();
        setSubmitError('');
        setSubmitSuccess('');

        if (effectiveAmount <= 0) {
            setSubmitError('Please enter a valid token amount greater than 0.');
            return;
        }

        const token = localStorage.getItem('token');
        if (!token) {
            setSubmitError('You must be logged in to submit a quota request.');
            return;
        }

        setSubmitting(true);
        try {
            const res = await fetch(API_ENDPOINTS.TOKENOPS_USER_REQUEST_QUOTA, {
                method: 'POST',
                headers: {
                    'Authorization': `Bearer ${token}`,
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    requested_tokens: effectiveAmount,
                    reason: requestReason.trim() || undefined,
                }),
            });

            const resData = await res.json();
            if (res.ok && resData.success) {
                setSubmitSuccess('Token top-up request submitted successfully! Your Org Admin has been notified.');
                setTimeout(() => {
                    setShowRequestModal(false);
                    setSubmitSuccess('');
                    setRequestReason('');
                    if (onRefresh) onRefresh();
                }, 1500);
            } else {
                setSubmitError(resData.detail || resData.error?.message || 'Failed to submit quota request.');
            }
        } catch (err) {
            setSubmitError(err.message || 'An unexpected network error occurred.');
        } finally {
            setSubmitting(false);
        }
    };

    return (
        <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-[9999] flex items-center justify-center p-4">
            <div className="bg-white dark:bg-slate-900 rounded-3xl max-w-2xl w-full border border-slate-200 dark:border-slate-800 shadow-2xl overflow-hidden flex flex-col max-h-[90vh] relative">
                {/* Header */}
                <div className="p-6 border-b border-slate-100 dark:border-slate-800 flex items-center justify-between bg-slate-50/50 dark:bg-slate-800/30">
                    <div className="flex items-center gap-3">
                        <div className="w-10 h-10 rounded-2xl bg-indigo-600/10 dark:bg-indigo-400/10 text-indigo-600 dark:text-indigo-400 flex items-center justify-center">
                            <Coins className="w-5 h-5" />
                        </div>
                        <div>
                            <h2 className="text-lg font-bold text-slate-900 dark:text-white flex items-center gap-2">
                                Token Quota & Cost Breakdown
                                {isPayg && (
                                    <span className="px-2 py-0.5 text-[11px] font-bold rounded-full bg-purple-100 dark:bg-purple-900/50 text-purple-700 dark:text-purple-300">
                                        PAYG Active
                                    </span>
                                )}
                            </h2>
                            <p className="text-xs text-slate-500 dark:text-slate-400">
                                Organization: <strong className="text-slate-700 dark:text-slate-200">{data.organization_name}</strong>
                            </p>
                        </div>
                    </div>
                    <button
                        onClick={onClose}
                        className="p-2 text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 rounded-xl hover:bg-slate-100 dark:hover:bg-slate-800 transition cursor-pointer"
                    >
                        <X className="w-5 h-5" />
                    </button>
                </div>

                {/* Body scroll */}
                <div className="p-6 overflow-y-auto space-y-6 flex-1">
                    {/* Top Stats Cards */}
                    <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                        <div className={`p-4 rounded-2xl border ${isExhausted ? 'bg-rose-50/50 dark:bg-rose-950/20 border-rose-200 dark:border-rose-900/40' : 'bg-slate-50 dark:bg-slate-800/60 border-slate-200/70 dark:border-slate-700/60'}`}>
                            <div className="flex items-center justify-between text-xs font-semibold text-slate-500 dark:text-slate-400">
                                <span>Tokens Remaining</span>
                                <Sparkles className={`w-4 h-4 ${isExhausted ? 'text-rose-500' : 'text-indigo-500'}`} />
                            </div>
                            <div className={`text-2xl font-bold mt-2 font-mono ${isExhausted ? 'text-rose-600 dark:text-rose-400' : 'text-indigo-600 dark:text-indigo-400'}`}>
                                {isPayg ? 'Unlimited' : remaining.toLocaleString()}
                            </div>
                            <div className="text-[11px] text-slate-400 mt-1">
                                {isPayg ? 'Billed via PAYG rate' : `of ${allocated.toLocaleString()} allocated`}
                            </div>
                        </div>

                        <div className="p-4 rounded-2xl bg-slate-50 dark:bg-slate-800/60 border border-slate-200/70 dark:border-slate-700/60">
                            <div className="flex items-center justify-between text-xs font-semibold text-slate-500 dark:text-slate-400">
                                <span>Tokens Consumed</span>
                                <Activity className="w-4 h-4 text-rose-500" />
                            </div>
                            <div className="text-2xl font-bold text-rose-600 dark:text-rose-400 mt-2 font-mono">
                                {consumed.toLocaleString()}
                            </div>
                            <div className="text-[11px] text-slate-400 mt-1">
                                {isPayg ? 'Pay As You Go active' : `${usagePercent}% quota utilized`}
                            </div>
                        </div>

                        <div className="p-4 rounded-2xl bg-emerald-50/60 dark:bg-emerald-950/20 border border-emerald-200 dark:border-emerald-800/50">
                            <div className="flex items-center justify-between text-xs font-semibold text-emerald-700 dark:text-emerald-400">
                                <span>Total Cost (USD)</span>
                                <DollarSign className="w-4 h-4 text-emerald-600 dark:text-emerald-400" />
                            </div>
                            <div className="text-2xl font-bold text-emerald-700 dark:text-emerald-300 mt-2 font-mono">
                                ${totalCostUsd.toFixed(4)}
                            </div>
                            <div className="text-[11px] text-emerald-600/80 dark:text-emerald-400/80 mt-1">
                                Across all AI operations
                            </div>
                        </div>
                    </div>

                    {/* Pending Request Banner */}
                    {isPending && (
                        <div className="p-4 rounded-2xl bg-amber-50/90 dark:bg-amber-950/40 border border-amber-200 dark:border-amber-800/70 flex items-start gap-3.5 shadow-sm">
                            <div className="p-2 rounded-xl bg-amber-500/10 text-amber-600 dark:text-amber-400 mt-0.5">
                                <Clock className="w-5 h-5" />
                            </div>
                            <div className="flex-1">
                                <div className="flex items-center justify-between">
                                    <h4 className="text-sm font-bold text-amber-900 dark:text-amber-200">
                                        Token Top-Up Request Under Review
                                    </h4>
                                    <span className="px-2.5 py-0.5 text-[10px] font-bold rounded-full bg-amber-100 dark:bg-amber-900/70 text-amber-800 dark:text-amber-300 uppercase tracking-wide">
                                        Pending Org Admin
                                    </span>
                                </div>
                                <p className="text-xs text-amber-800 dark:text-amber-300/90 mt-1">
                                    You requested <strong className="font-bold">+{Number(latestRequest.requested_tokens).toLocaleString()} tokens</strong> on {latestRequest.created_at ? new Date(latestRequest.created_at).toLocaleDateString() : 'recently'}. Your Organization Admin will review and allocate your tokens shortly.
                                </p>
                                {latestRequest.reason && (
                                    <p className="text-[11px] text-amber-700 dark:text-amber-400/80 mt-1.5 italic bg-amber-100/50 dark:bg-amber-900/30 p-2 rounded-lg border border-amber-200/50 dark:border-amber-800/40">
                                        Note: "{latestRequest.reason}"
                                    </p>
                                )}
                            </div>
                        </div>
                    )}

                    {/* Quota Exhaustion & Top-Up CTA (Only visible when exhausted & not pending) */}
                    {isExhausted && !isPending && (
                        <div className="p-4 rounded-2xl bg-rose-50/80 dark:bg-rose-950/30 border border-rose-200 dark:border-rose-900/50 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 shadow-sm">
                            <div className="flex items-center gap-3">
                                <div className="p-2 rounded-xl bg-rose-500/10 text-rose-600 dark:text-rose-400">
                                    <AlertCircle className="w-5 h-5" />
                                </div>
                                <div>
                                    <h4 className="text-sm font-bold text-rose-900 dark:text-rose-200">
                                        Token Quota Exhausted
                                    </h4>
                                    <p className="text-xs text-rose-700 dark:text-rose-300/80 mt-0.5">
                                        Your tokens are depleted. Request additional tokens from your Org Admin to continue.
                                    </p>
                                </div>
                            </div>
                            <button
                                onClick={() => { setSubmitError(''); setShowRequestModal(true); }}
                                className="px-4 py-2 bg-gradient-to-r from-indigo-600 to-violet-600 hover:from-indigo-700 hover:to-violet-700 text-white rounded-xl text-xs font-bold shadow-md shadow-indigo-500/20 transition flex items-center gap-1.5 whitespace-nowrap cursor-pointer hover:scale-[1.02] active:scale-[0.98]"
                            >
                                <Sparkles className="w-3.5 h-3.5" />
                                Request More Tokens
                            </button>
                        </div>
                    )}

                    {/* Progress Bar */}
                    {!isPayg && allocated > 0 && (
                        <div className="space-y-1.5">
                            <div className="flex justify-between text-xs font-semibold text-slate-600 dark:text-slate-300">
                                <span>Quota Consumption Progress</span>
                                <span>{usagePercent}% Used</span>
                            </div>
                            <div className="w-full h-2.5 bg-slate-100 dark:bg-slate-800 rounded-full overflow-hidden">
                                <div
                                    className={`h-full rounded-full transition-all duration-500 ${
                                        usagePercent > 90
                                            ? 'bg-rose-500'
                                            : usagePercent > 75
                                            ? 'bg-amber-500'
                                            : 'bg-indigo-600'
                                    }`}
                                    style={{ width: `${usagePercent}%` }}
                                />
                            </div>
                        </div>
                    )}

                    {/* AI Usage Logs */}
                    <div className="space-y-3">
                        <div className="flex items-center justify-between">
                            <h3 className="text-sm font-bold text-slate-900 dark:text-white flex items-center gap-2">
                                <Clock className="w-4 h-4 text-indigo-600" />
                                Recent AI Operations & Token Consumption
                            </h3>
                            <span className="text-xs text-slate-400">Showing last {recentLogs.length} runs</span>
                        </div>

                        {recentLogs.length === 0 ? (
                            <div className="p-8 text-center bg-slate-50 dark:bg-slate-800/40 rounded-2xl border border-slate-200 dark:border-slate-800 text-slate-400 text-xs">
                                No AI operations recorded for your account yet.
                            </div>
                        ) : (
                            <div className="border border-slate-200 dark:border-slate-800 rounded-2xl overflow-hidden shadow-sm">
                                <table className="w-full text-left text-xs">
                                    <thead className="bg-slate-50 dark:bg-slate-800 text-slate-600 dark:text-slate-300 border-b border-slate-200 dark:border-slate-800 font-semibold">
                                        <tr>
                                            <th className="px-4 py-3">Timestamp {localTimezone ? `(${localTimezone})` : ''}</th>
                                            <th className="px-4 py-3">Model</th>
                                            <th className="px-4 py-3 text-right">Prompt</th>
                                            <th className="px-4 py-3 text-right">Completion</th>
                                            <th className="px-4 py-3 text-right">Total Tokens</th>
                                            <th className="px-4 py-3 text-right">Cost (USD)</th>
                                        </tr>
                                    </thead>
                                    <tbody className="divide-y divide-slate-100 dark:divide-slate-800 text-slate-800 dark:text-slate-200">
                                        {recentLogs.map((log) => (
                                            <tr key={log.id} className="hover:bg-slate-50 dark:hover:bg-slate-800/40 transition">
                                                <td className="px-4 py-3 text-slate-400 font-mono text-[11px]">
                                                    {log.created_at ? new Date(log.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }) : '—'}
                                                </td>
                                                <td className="px-4 py-3 font-semibold text-slate-700 dark:text-slate-300">
                                                    {log.model || 'BournAI'}
                                                </td>
                                                <td className="px-4 py-3 text-right font-mono text-slate-500">
                                                    {Number(log.prompt_tokens || 0).toLocaleString()}
                                                </td>
                                                <td className="px-4 py-3 text-right font-mono text-slate-500">
                                                    {Number(log.completion_tokens || 0).toLocaleString()}
                                                </td>
                                                <td className="px-4 py-3 text-right font-mono font-bold text-indigo-600 dark:text-indigo-400">
                                                    {Number(log.total_tokens || 0).toLocaleString()}
                                                </td>
                                                <td className="px-4 py-3 text-right font-mono font-semibold text-emerald-600 dark:text-emerald-400">
                                                    ${Number(log.cost || 0).toFixed(4)}
                                                </td>
                                            </tr>
                                        ))}
                                    </tbody>
                                </table>
                            </div>
                        )}
                    </div>
                </div>

                {/* Footer */}
                <div className="p-4 border-t border-slate-100 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-800/30 flex justify-between items-center">
                    <button
                        onClick={onRefresh}
                        disabled={loading}
                        className="px-3 py-1.5 text-xs text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-700 rounded-xl transition flex items-center gap-1 font-medium cursor-pointer"
                    >
                        <Zap className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
                        Refresh Live Balance
                    </button>
                    <div className="flex items-center gap-2">
                        {isExhausted && !isPending && (
                            <button
                                onClick={() => { setSubmitError(''); setShowRequestModal(true); }}
                                className="px-3 py-2 bg-indigo-50 dark:bg-indigo-950/40 text-indigo-600 dark:text-indigo-400 hover:bg-indigo-100 dark:hover:bg-indigo-900/60 rounded-xl text-xs font-semibold transition flex items-center gap-1 cursor-pointer"
                            >
                                <Sparkles className="w-3.5 h-3.5" />
                                Request Top-Up
                            </button>
                        )}
                        <button
                            onClick={onClose}
                            className="px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-xl text-xs font-semibold shadow-sm transition cursor-pointer"
                        >
                            Close
                        </button>
                    </div>
                </div>

                {/* Top-Up Request Sub-Modal Drawer */}
                {showRequestModal && (
                    <div className="absolute inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-center justify-center p-4">
                        <div className="bg-white dark:bg-slate-900 rounded-2xl max-w-md w-full border border-slate-200 dark:border-slate-800 shadow-2xl overflow-hidden p-6 space-y-5 animate-in fade-in zoom-in-95 duration-150">
                            <div className="flex items-center justify-between border-b border-slate-100 dark:border-slate-800 pb-3">
                                <div className="flex items-center gap-2.5">
                                    <div className="p-2 rounded-xl bg-indigo-600/10 text-indigo-600 dark:text-indigo-400">
                                        <Sparkles className="w-4 h-4" />
                                    </div>
                                    <div>
                                        <h3 className="text-sm font-bold text-slate-900 dark:text-white">
                                            Request Token Top-Up
                                        </h3>
                                        <p className="text-[11px] text-slate-500">
                                            For Organization: <strong className="text-slate-700 dark:text-slate-300">{data.organization_name}</strong>
                                        </p>
                                    </div>
                                </div>
                                <button
                                    onClick={() => setShowRequestModal(false)}
                                    className="p-1.5 text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-800 transition cursor-pointer"
                                >
                                    <X className="w-4 h-4" />
                                </button>
                            </div>

                            {submitError && (
                                <div className="p-3 rounded-xl bg-rose-50 dark:bg-rose-950/40 border border-rose-200 dark:border-rose-800 text-rose-700 dark:text-rose-300 text-xs flex items-center gap-2">
                                    <AlertCircle className="w-4 h-4 shrink-0" />
                                    <span>{submitError}</span>
                                </div>
                            )}

                            {submitSuccess && (
                                <div className="p-3 rounded-xl bg-emerald-50 dark:bg-emerald-950/40 border border-emerald-200 dark:border-emerald-800 text-emerald-700 dark:text-emerald-300 text-xs flex items-center gap-2">
                                    <CheckCircle2 className="w-4 h-4 shrink-0" />
                                    <span>{submitSuccess}</span>
                                </div>
                            )}

                            <form onSubmit={handleSubmitTopUp} className="space-y-4">
                                <div>
                                    <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-2">
                                        Select Token Amount
                                    </label>
                                    <div className="grid grid-cols-3 gap-2">
                                        {[5000, 10000, 25000, 50000].map((amt) => (
                                            <button
                                                type="button"
                                                key={amt}
                                                onClick={() => handlePresetClick(amt)}
                                                className={`py-2 px-2.5 rounded-xl text-xs font-bold border transition cursor-pointer ${
                                                    !isCustom && requestAmount === amt
                                                        ? 'bg-indigo-600 text-white border-indigo-600 shadow-sm'
                                                        : 'bg-slate-50 dark:bg-slate-800 text-slate-700 dark:text-slate-300 border-slate-200 dark:border-slate-700 hover:border-indigo-400'
                                                }`}
                                            >
                                                +{amt.toLocaleString()}
                                            </button>
                                        ))}
                                        <button
                                            type="button"
                                            onClick={handleCustomClick}
                                            className={`col-span-2 py-2 px-2.5 rounded-xl text-xs font-bold border transition cursor-pointer ${
                                                isCustom
                                                    ? 'bg-indigo-600 text-white border-indigo-600 shadow-sm'
                                                    : 'bg-slate-50 dark:bg-slate-800 text-slate-700 dark:text-slate-300 border-slate-200 dark:border-slate-700 hover:border-indigo-400'
                                            }`}
                                        >
                                            Custom Amount
                                        </button>
                                    </div>
                                </div>

                                {isCustom && (
                                    <div>
                                        <label className="block text-[11px] font-medium text-slate-600 dark:text-slate-400 mb-1">
                                            Enter Custom Token Quantity
                                        </label>
                                        <input
                                            type="number"
                                            min="100"
                                            step="100"
                                            value={customAmount}
                                            onChange={(e) => setCustomAmount(e.target.value)}
                                            placeholder="e.g. 15000"
                                            className="w-full px-3 py-2 text-xs rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-900 dark:text-white font-mono focus:outline-none focus:ring-2 focus:ring-indigo-500"
                                            required
                                        />
                                    </div>
                                )}

                                <div className="p-2.5 rounded-xl bg-indigo-50/70 dark:bg-indigo-950/30 border border-indigo-100 dark:border-indigo-900/40 flex items-center justify-between text-xs">
                                    <span className="text-indigo-900 dark:text-indigo-300 font-medium">Estimated Value:</span>
                                    <span className="font-mono font-bold text-indigo-700 dark:text-indigo-400">
                                        ${estimatedValue.toFixed(4)} USD
                                    </span>
                                </div>

                                <div>
                                    <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                                        Reason / Context (Optional)
                                    </label>
                                    <textarea
                                        rows={3}
                                        value={requestReason}
                                        onChange={(e) => setRequestReason(e.target.value)}
                                        placeholder="e.g. Continuing architecture analysis and test case generation for project..."
                                        className="w-full px-3 py-2 text-xs rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-indigo-500 resize-none"
                                    />
                                </div>

                                <div className="flex items-center justify-end gap-2 pt-2 border-t border-slate-100 dark:border-slate-800">
                                    <button
                                        type="button"
                                        onClick={() => setShowRequestModal(false)}
                                        className="px-3.5 py-2 text-xs text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800 rounded-xl transition cursor-pointer font-medium"
                                    >
                                        Cancel
                                    </button>
                                    <button
                                        type="submit"
                                        disabled={submitting || effectiveAmount <= 0}
                                        className="px-4 py-2 bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white rounded-xl text-xs font-bold shadow-md shadow-indigo-500/20 transition flex items-center gap-1.5 cursor-pointer"
                                    >
                                        {submitting ? (
                                            <>
                                                <div className="w-3.5 h-3.5 border-2 border-white border-t-transparent rounded-full animate-spin" />
                                                Submitting...
                                            </>
                                        ) : (
                                            <>
                                                <Send className="w-3.5 h-3.5" />
                                                Submit Request
                                            </>
                                        )}
                                    </button>
                                </div>
                            </form>
                        </div>
                    </div>
                )}
            </div>
        </div>
    );
}
