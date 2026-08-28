import React from 'react';
import { Coins, DollarSign, Activity, X, Sparkles, Zap, Clock } from 'lucide-react';

export default function UserTokenDetailModal({ isOpen, onClose, data, onRefresh, loading }) {
    if (!isOpen || !data) return null;

    const allocated = Number(data.allocated_tokens || 0);
    const consumed = Number(data.consumed_tokens || 0);
    const remaining = Number(data.remaining_tokens || 0);
    const isPayg = Boolean(data.is_payg);
    const totalCostUsd = Number(data.total_cost_usd || 0);
    const recentLogs = data.recent_usage || [];

    const usagePercent = allocated > 0 ? Math.min(100, Math.round((consumed / allocated) * 100)) : (consumed > 0 ? 100 : 0);

    return (
        <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-[9999] flex items-center justify-center p-4">
            <div className="bg-white dark:bg-slate-900 rounded-3xl max-w-2xl w-full border border-slate-200 dark:border-slate-800 shadow-2xl overflow-hidden flex flex-col max-h-[90vh]">
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
                        className="p-2 text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 rounded-xl hover:bg-slate-100 dark:hover:bg-slate-800 transition"
                    >
                        <X className="w-5 h-5" />
                    </button>
                </div>

                {/* Body scroll */}
                <div className="p-6 overflow-y-auto space-y-6 flex-1">
                    {/* Top Stats Cards */}
                    <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                        <div className="p-4 rounded-2xl bg-slate-50 dark:bg-slate-800/60 border border-slate-200/70 dark:border-slate-700/60">
                            <div className="flex items-center justify-between text-xs font-semibold text-slate-500 dark:text-slate-400">
                                <span>Tokens Remaining</span>
                                <Sparkles className="w-4 h-4 text-indigo-500" />
                            </div>
                            <div className="text-2xl font-bold text-indigo-600 dark:text-indigo-400 mt-2 font-mono">
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
                                {usagePercent}% quota utilized
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
                                            <th className="px-4 py-3">Timestamp</th>
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
                    <button
                        onClick={onClose}
                        className="px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-xl text-xs font-semibold shadow-sm transition cursor-pointer"
                    >
                        Close
                    </button>
                </div>
            </div>
        </div>
    );
}
