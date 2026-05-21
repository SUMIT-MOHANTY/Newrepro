import React, { useState, useEffect, useMemo } from 'react';
import { CreditCard, CheckCircle2, ShieldAlert, Sparkles, Bot, Clock, DollarSign, Search, Filter, Cpu, RefreshCw, AlertCircle, Zap, User } from 'lucide-react';
import { API_BASE_URL } from '../config';
import { getCachedTaskToken } from '../utils/tokenCache';

export default function Billing({ selectedProjectKey, projects = [] }) {
    const [billingData, setBillingData] = useState(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [searchTerm, setSearchTerm] = useState('');
    const [agentFilter, setAgentFilter] = useState('all');
    const [refreshing, setRefreshing] = useState(false);

    const activeProject = projects.find(p => p.key === selectedProjectKey);

    const fetchBillingData = async (isRefresh = false) => {
        if (isRefresh) {
            setRefreshing(true);
        } else {
            setLoading(true);
        }
        setError(null);

        try {
            const token = localStorage.getItem('token');
            const taskToken = getCachedTaskToken(selectedProjectKey)?.token;

            const headers = {
                'Authorization': `Bearer ${token}`,
                'Content-Type': 'application/json'
            };
            if (taskToken) {
                headers['x-task-token'] = taskToken;
            }

            const res = await fetch(`${API_BASE_URL}/api/agent/billing-dashboard/`, {
                headers
            });

            if (!res.ok) {
                const errData = await res.json().catch(() => ({}));
                throw new Error(errData.detail || 'Failed to fetch billing dashboard');
            }

            const data = await res.json();
            setBillingData(data);
        } catch (err) {
            console.error('Error fetching billing data:', err);
            setError(err.message);
        } finally {
            setLoading(false);
            setRefreshing(false);
        }
    };

    useEffect(() => {
        fetchBillingData();
    }, [selectedProjectKey]);

    // Filtered lists
    const filteredTasks = useMemo(() => {
        if (!billingData || !billingData.tasks) return [];
        return billingData.tasks.filter(task => {
            const matchesSearch =
                task.task_id.toLowerCase().includes(searchTerm.toLowerCase()) ||
                task.task_name.toLowerCase().includes(searchTerm.toLowerCase());

            const matchesAgent =
                agentFilter === 'all' ||
                task.agent_name === agentFilter;

            return matchesSearch && matchesAgent;
        });
    }, [billingData, searchTerm, agentFilter]);

    // Unique agents for dropdown filter
    const uniqueAgentNames = useMemo(() => {
        if (!billingData || !billingData.agent_breakdown) return [];
        return billingData.agent_breakdown.map(agent => agent.agent_name);
    }, [billingData]);

    if (loading) {
        return (
            <div className="flex flex-col items-center justify-center min-h-[400px] py-12">
                <RefreshCw className="w-10 h-10 text-app-primary animate-spin mb-4" />
                <p className="text-app-text-muted text-sm font-medium">Calculating agent hours and computing billing matrices...</p>
            </div>
        );
    }

    if (error) {
        return (
            <div className="max-w-2xl mx-auto px-4 py-12 text-center">
                <div className="inline-flex p-3 bg-rose-500/10 rounded-full text-rose-400 mb-4 border border-rose-500/20">
                    <AlertCircle className="w-8 h-8" />
                </div>
                <h3 className="text-xl font-bold text-white mb-2">Billing Data Unavailable</h3>
                <p className="text-app-text-muted mb-6 text-sm">{error}</p>
                <button
                    onClick={() => fetchBillingData()}
                    className="px-5 py-2.5 bg-app-primary hover:bg-app-primary-hover text-white font-medium rounded-lg transition-colors inline-flex items-center gap-2"
                >
                    <RefreshCw className="w-4 h-4" /> Retry Connection
                </button>
            </div>
        );
    }

    const { summary, agent_breakdown = [] } = billingData || {};

    return (
        <div className="flex-1 overflow-y-auto h-full bg-slate-50 dark:bg-slate-950 custom-scrollbar">
            <div className="max-w-6xl mx-auto px-4 py-8">
                {/* Header */}
                <div className="flex flex-col md:flex-row md:items-center justify-between gap-6 mb-8">
                    <div>
                        <span className="px-3 py-1 text-xs font-semibold rounded-full bg-blue-50 text-blue-700 dark:bg-blue-950/40 dark:text-blue-400 border border-blue-200/50 inline-flex items-center gap-1.5 mb-3">
                            <Sparkles className="w-3.5 h-3.5" /> Billing & Agent Metrics
                        </span>
                        <h1 className="text-2xl font-extrabold text-slate-900 dark:text-white sm:text-3xl">
                            Execution Billing Dashboard
                        </h1>
                        <p className="mt-1.5 text-sm text-slate-600 dark:text-slate-400 font-medium">
                            Real-time tracking of tasks completed, resource time logs, and computed cost share per agent.
                        </p>
                    </div>
                    <button
                        onClick={() => fetchBillingData(true)}
                        disabled={refreshing}
                        className="self-start md:self-auto px-4 py-2 border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 text-slate-700 dark:text-slate-200 hover:bg-slate-50 dark:hover:bg-slate-800 rounded-lg transition-all text-xs font-semibold flex items-center gap-2 disabled:opacity-50 shadow-sm cursor-pointer"
                    >
                        <RefreshCw className={`w-3.5 h-3.5 ${refreshing ? 'animate-spin' : ''}`} />
                        {refreshing ? 'Syncing...' : 'Sync Log'}
                    </button>
                </div>

                {/* Project Context Info */}
                {activeProject && (
                    <div className="mb-6 p-4 rounded-xl bg-blue-50/50 dark:bg-blue-950/20 border border-blue-100 dark:border-blue-900/30 flex items-center justify-between shadow-sm">
                        <div className="flex items-center gap-2">
                            <Zap className="w-4 h-4 text-blue-600 dark:text-blue-400" />
                            <span className="text-xs font-semibold text-slate-700 dark:text-slate-300">
                                Active Project: <strong className="text-slate-900 dark:text-white font-bold">{activeProject.name || selectedProjectKey}</strong>
                            </span>
                        </div>
                        <span className="text-[10px] bg-emerald-50 text-emerald-700 dark:bg-emerald-950/30 dark:text-emerald-400 border border-emerald-200/50 px-2 py-0.5 rounded font-mono font-semibold uppercase tracking-wider">
                            Live Tracking
                        </span>
                    </div>
                )}

                {/* Metrics Overview Cards */}
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
                    {/* Total Cost Card */}
                    <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-5 hover:border-slate-300 dark:hover:border-slate-700 transition-all shadow-sm">
                        <div className="flex items-center justify-between mb-3">
                            <span className="text-xs font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wider">Total Costs</span>
                            <div className="p-2 bg-emerald-50 dark:bg-emerald-950/30 rounded-lg text-emerald-600 dark:text-emerald-400 border border-emerald-200/20">
                                <DollarSign className="w-4 h-4" />
                            </div>
                        </div>
                        <h3 className="text-2xl font-black text-slate-900 dark:text-white">
                            ${summary?.total_amount_due?.toLocaleString(undefined, { minimumFractionDigits: 2 })}
                        </h3>
                        <p className="text-[10px] text-emerald-600 dark:text-emerald-400 mt-1 flex items-center gap-1 font-semibold">
                            <CheckCircle2 className="w-3 h-3" /> Fully verified executions
                        </p>
                    </div>

                    {/* Billable Hours */}
                    <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-5 hover:border-slate-300 dark:hover:border-slate-700 transition-all shadow-sm">
                        <div className="flex items-center justify-between mb-3">
                            <span className="text-xs font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wider">Billable Time</span>
                            <div className="p-2 bg-blue-50 dark:bg-blue-950/30 rounded-lg text-blue-600 dark:text-blue-400 border border-blue-200/20">
                                <Clock className="w-4 h-4" />
                            </div>
                        </div>
                        <h3 className="text-2xl font-black text-slate-900 dark:text-white">
                            {summary?.total_hours_billed} <span className="text-xs text-slate-500 dark:text-slate-400 font-normal">hrs</span>
                        </h3>
                        <p className="text-[10px] text-slate-500 dark:text-slate-400 mt-1 font-medium">
                            Cumulated time spent
                        </p>
                    </div>

                    {/* Tasks Completed */}
                    <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-5 hover:border-slate-300 dark:hover:border-slate-700 transition-all shadow-sm">
                        <div className="flex items-center justify-between mb-3">
                            <span className="text-xs font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wider">Tasks Completed</span>
                            <div className="p-2 bg-indigo-50 dark:bg-indigo-950/30 rounded-lg text-indigo-600 dark:text-indigo-400 border border-indigo-200/20">
                                <CheckCircle2 className="w-4 h-4" />
                            </div>
                        </div>
                        <h3 className="text-2xl font-black text-slate-900 dark:text-white">
                            {summary?.total_tasks_completed}
                        </h3>
                        <p className="text-[10px] text-slate-500 dark:text-slate-400 mt-1 font-medium">
                            Completed agent threads
                        </p>
                    </div>

                    {/* Unique Agents */}
                    <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-5 hover:border-slate-300 dark:hover:border-slate-700 transition-all shadow-sm">
                        <div className="flex items-center justify-between mb-3">
                            <span className="text-xs font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wider">Agents Used</span>
                            <div className="p-2 bg-purple-50 dark:bg-purple-950/30 rounded-lg text-purple-600 dark:text-purple-400 border border-purple-200/20">
                                <Bot className="w-4 h-4" />
                            </div>
                        </div>
                        <h3 className="text-2xl font-black text-slate-900 dark:text-white">
                            {agent_breakdown.length}
                        </h3>
                        <p className="text-[10px] text-slate-500 dark:text-slate-400 mt-1 font-medium">
                            Includes sub & master agents
                        </p>
                    </div>
                </div>

                {/* Agent-wise Fleet Utilization Breakdown */}
                <div className="mb-8">
                    <h3 className="text-base font-bold text-slate-900 dark:text-white mb-4 flex items-center gap-2">
                        <Cpu className="w-4 h-4 text-blue-600 dark:text-blue-400" /> Agent Fleet Resource Utilization
                    </h3>
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                        {agent_breakdown.map((agent) => {
                            const costPercentage = summary?.total_amount_due > 0 
                                ? Math.round((agent.total_cost / summary.total_amount_due) * 100)
                                : 0;

                            return (
                                <div 
                                    key={agent.agent_name}
                                    className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-5 transition-all flex flex-col justify-between shadow-sm"
                                >
                                    <div className="mb-4">
                                        <div className="flex items-center justify-between mb-2">
                                            <div className="flex items-center gap-2">
                                                <div className={`p-1.5 rounded-lg border ${
                                                    agent.agent_type === 'Master Agent' 
                                                        ? 'bg-blue-50 text-blue-600 border-blue-100 dark:bg-blue-950/30 dark:text-blue-400 dark:border-blue-900/30'
                                                        : 'bg-slate-50 text-slate-650 border-slate-100 dark:bg-slate-805 dark:text-slate-300 dark:border-slate-700'
                                                }`}>
                                                    <Bot className="w-4 h-4" />
                                                </div>
                                                <div>
                                                    <h4 className="text-sm font-bold text-slate-900 dark:text-white">{agent.agent_name}</h4>
                                                    <span className="text-[10px] text-slate-550 dark:text-slate-400 font-semibold uppercase">{agent.agent_type}</span>
                                                </div>
                                            </div>
                                            <span className="text-xs font-mono font-bold text-emerald-600 dark:text-emerald-400">
                                                ${agent.rate_per_hour}/hr
                                            </span>
                                        </div>
                                        <p className="text-xs text-slate-650 dark:text-slate-400 mb-4 leading-relaxed font-semibold">
                                            Completed <strong className="text-slate-900 dark:text-white font-bold">{agent.tasks_completed}</strong> tasks in <strong className="text-slate-900 dark:text-white font-bold">{agent.total_hours}</strong> billable hours.
                                        </p>
                                    </div>

                                    <div>
                                        <div className="flex justify-between items-baseline mb-1">
                                            <span className="text-xs text-slate-500 dark:text-slate-400 font-semibold">Total cost share</span>
                                            <span className="text-sm font-black text-slate-900 dark:text-white">${agent.total_cost.toLocaleString()}</span>
                                        </div>
                                        <div className="w-full bg-slate-100 dark:bg-slate-800 rounded-full h-1.5 overflow-hidden">
                                            <div 
                                                className={`h-full rounded-full transition-all duration-500 ${
                                                    agent.agent_type === 'Master Agent'
                                                        ? 'bg-gradient-to-r from-blue-600 to-indigo-600'
                                                        : 'bg-gradient-to-r from-blue-400 to-indigo-400'
                                                }`}
                                                style={{ width: `${costPercentage}%` }}
                                            />
                                        </div>
                                        <div className="flex justify-between text-[10px] text-slate-550 dark:text-slate-400 mt-1 font-semibold">
                                            <span>Share</span>
                                            <span>{costPercentage}%</span>
                                        </div>
                                    </div>
                                </div>
                            );
                        })}
                    </div>
                </div>

                {/* Billable Activity Log (Completed Tasks List) */}
                <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-6 mb-8 shadow-sm">
                    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-6">
                        <h3 className="text-base font-bold text-slate-900 dark:text-white flex items-center gap-2">
                            <CreditCard className="w-4 h-4 text-blue-600 dark:text-blue-400" /> Billable Activity Log
                        </h3>
                        
                        {/* Filters */}
                        <div className="flex flex-wrap items-center gap-3">
                            {/* Search */}
                            <div className="relative">
                                <Search className="w-3.5 h-3.5 absolute left-3 top-1/2 transform -translate-y-1/2 text-slate-400 dark:text-slate-500" />
                                <input
                                    type="text"
                                    placeholder="Search by ID or name..."
                                    value={searchTerm}
                                    onChange={(e) => setSearchTerm(e.target.value)}
                                    className="pl-9 pr-4 py-1.5 bg-slate-50 border border-slate-200 dark:bg-slate-800 dark:border-slate-700 hover:border-slate-300 dark:hover:border-slate-650 focus:border-blue-500 dark:focus:border-blue-400 text-xs text-slate-900 dark:text-white rounded-lg focus:outline-none transition-all w-[180px] sm:w-[220px] shadow-inner"
                                />
                            </div>

                            {/* Agent dropdown */}
                            <div className="relative flex items-center bg-slate-50 border border-slate-200 dark:bg-slate-800 dark:border-slate-700 hover:border-slate-300 dark:hover:border-slate-650 rounded-lg px-3 py-1.5 transition-all shadow-inner">
                                <Filter className="w-3.5 h-3.5 text-slate-400 dark:text-slate-500 mr-2" />
                                <select
                                    value={agentFilter}
                                    onChange={(e) => setAgentFilter(e.target.value)}
                                    className="bg-transparent text-xs text-slate-900 dark:text-white focus:outline-none cursor-pointer pr-1"
                                >
                                    <option value="all" className="bg-white text-slate-900 dark:bg-slate-900 dark:text-white">All Agents</option>
                                    {uniqueAgentNames.map(name => (
                                        <option key={name} value={name} className="bg-white text-slate-900 dark:bg-slate-900 dark:text-white">{name}</option>
                                    ))}
                                </select>
                            </div>
                        </div>
                    </div>

                    {/* Table */}
                    <div className="overflow-x-auto rounded-lg border border-slate-200 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-950/40">
                        <table className="w-full text-left border-collapse text-xs">
                            <thead>
                                <tr className="border-b border-slate-200 dark:border-slate-800 bg-slate-100/70 dark:bg-slate-900/60 text-slate-700 dark:text-slate-300 uppercase font-bold tracking-wider select-none text-[10px]">
                                    <th className="py-3.5 px-4 font-bold">Task ID</th>
                                    <th className="py-3.5 px-4 font-bold">Task Description</th>
                                    <th className="py-3.5 px-4 font-bold">Assigned Agent</th>
                                    <th className="py-3.5 px-4 font-bold text-right">Time Spent</th>
                                    <th className="py-3.5 px-4 font-bold text-right">Hourly Rate</th>
                                    <th className="py-3.5 px-4 font-bold text-right">Total Cost</th>
                                    <th className="py-3.5 px-4 font-bold text-center">Completed At</th>
                                </tr>
                            </thead>
                            <tbody className="divide-y divide-slate-200 dark:divide-slate-800/80">
                                {filteredTasks.length === 0 ? (
                                    <tr>
                                        <td colSpan="7" className="py-8 px-4 text-center text-slate-550 dark:text-slate-400 font-semibold">
                                            No billable activity logs matched your current filters.
                                        </td>
                                    </tr>
                                ) : (
                                    filteredTasks.map((task) => (
                                        <tr key={task.task_id} className="hover:bg-slate-100/50 dark:hover:bg-slate-800/40 transition-colors">
                                            <td className="py-3.5 px-4 font-mono font-bold text-blue-650 dark:text-blue-400">
                                                {task.task_id}
                                            </td>
                                            <td className="py-3.5 px-4 font-bold text-slate-800 dark:text-slate-200 max-w-[280px] truncate">
                                                {task.task_name}
                                            </td>
                                            <td className="py-3.5 px-4">
                                                <div className="flex items-center gap-1.5">
                                                    <div className="p-1 rounded bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300">
                                                        {task.agent_type === 'Master Agent' ? <Cpu className="w-3 h-3 text-blue-650 dark:text-blue-400" /> : <User className="w-3 h-3" />}
                                                    </div>
                                                    <div>
                                                        <span className="font-bold text-slate-900 dark:text-slate-100">{task.agent_name}</span>
                                                        <span className="block text-[9px] text-slate-550 dark:text-slate-400 uppercase font-semibold">{task.agent_type}</span>
                                                    </div>
                                                </div>
                                            </td>
                                            <td className="py-3.5 px-4 text-right font-mono font-bold text-slate-850 dark:text-slate-100">
                                                {task.time_taken_hours} hrs
                                            </td>
                                            <td className="py-3.5 px-4 text-right font-mono font-semibold text-slate-550 dark:text-slate-400">
                                                ${task.rate_per_hour}/hr
                                            </td>
                                            <td className="py-3.5 px-4 text-right font-mono font-bold text-emerald-600 dark:text-emerald-400">
                                                ${task.cost.toLocaleString(undefined, { minimumFractionDigits: 2 })}
                                            </td>
                                            <td className="py-3.5 px-4 text-center font-mono text-slate-850 dark:text-slate-200 font-semibold">
                                                {task.completed_at}
                                            </td>
                                        </tr>
                                    ))
                                )}
                            </tbody>
                        </table>
                    </div>
                </div>

                {/* Security/FAQ Compliance Badge */}
                <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-6 flex flex-col sm:flex-row items-center gap-4 justify-between shadow-sm">
                    <div className="flex items-center gap-3">
                        <div className="p-3 bg-amber-50 dark:bg-amber-950/30 rounded-lg text-amber-600 dark:text-amber-400 border border-amber-200/20">
                            <ShieldAlert className="w-6 h-6" />
                        </div>
                        <div>
                            <h4 className="font-bold text-slate-900 dark:text-white">Looking for custom security compliance?</h4>
                            <p className="text-sm text-slate-650 dark:text-slate-400 font-semibold">We offer SOC2 type II compliance, high-availability setups, and on-premises agent execution.</p>
                        </div>
                    </div>
                    <button className="whitespace-nowrap px-4 py-2 text-sm font-semibold text-amber-650 hover:text-amber-700 dark:text-amber-400 dark:hover:text-amber-300 border border-amber-300 hover:bg-amber-50 dark:border-amber-700/50 dark:hover:bg-amber-950/20 rounded-lg transition-colors cursor-pointer">
                        Talk to Compliance
                    </button>
                </div>
            </div>
        </div>
    );
}
