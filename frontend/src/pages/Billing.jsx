import React, { useState, useEffect, useMemo } from 'react';
import { 
    CreditCard, CheckCircle2, ShieldAlert, Sparkles, Bot, Clock, 
    DollarSign, Search, Filter, Cpu, RefreshCw, AlertCircle, Zap, 
    User, Activity, ShieldCheck, Globe, Users, FileText, ArrowUpDown,
    CheckCircle, XCircle, ExternalLink
} from 'lucide-react';
import { API_BASE_URL } from '../config';
import { getCachedTaskToken } from '../utils/tokenCache';

export default function Billing({ selectedProjectKey, projects = [], user }) {
    const [billingData, setBillingData] = useState(null);
    const [orgBillingData, setOrgBillingData] = useState(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    
    // UI state
    const [activeTab, setActiveTab] = useState('overview'); // overview, users, projects
    const [searchTerm, setSearchTerm] = useState('');
    const [agentFilter, setAgentFilter] = useState('all');
    const [refreshing, setRefreshing] = useState(false);
    
    // Sort states for user table
    const [userSortField, setUserSortField] = useState('name');
    const [userSortAsc, setUserSortAsc] = useState(true);

    // Selected user for drilldown modal
    const [selectedUserDetail, setSelectedUserDetail] = useState(null);

    const activeProject = projects.find(p => p.key === selectedProjectKey);
    const isOrgAdmin = user?.is_org_admin;

    const fetchBillingData = async (isRefresh = false) => {
        if (isRefresh) {
            setRefreshing(true);
        } else {
            setLoading(true);
        }
        setError(null);

        try {
            const token = localStorage.getItem('token');
            const headers = {
                'Authorization': `Bearer ${token}`,
                'Content-Type': 'application/json'
            };

            if (isOrgAdmin) {
                const res = await fetch(`${API_BASE_URL}/organization/billing-logs`, {
                    headers
                });

                if (!res.ok) {
                    const errData = await res.json().catch(() => ({}));
                    throw new Error(errData.detail || 'Failed to fetch organization billing and logs');
                }

                const data = await res.json();
                setOrgBillingData(data);
            } else {
                const taskToken = getCachedTaskToken(selectedProjectKey)?.token;
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
            }
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
    }, [selectedProjectKey, isOrgAdmin]);

    // Handle user sort
    const handleUserSort = (field) => {
        if (userSortField === field) {
            setUserSortAsc(!userSortAsc);
        } else {
            setUserSortField(field);
            setUserSortAsc(true);
        }
    };

    // Filter and Sort org users
    const processedUsers = useMemo(() => {
        if (!orgBillingData || !orgBillingData.user_stats) return [];
        
        let list = [...orgBillingData.user_stats];
        
        // Search
        if (searchTerm) {
            const term = searchTerm.toLowerCase();
            list = list.filter(u => 
                u.name.toLowerCase().includes(term) || 
                u.email.toLowerCase().includes(term)
            );
        }
        
        // Sort
        list.sort((a, b) => {
            let valA = a[userSortField];
            let valB = b[userSortField];
            
            if (userSortField === 'name') {
                valA = (a.name || '').toLowerCase();
                valB = (b.name || '').toLowerCase();
            } else if (userSortField === 'email') {
                valA = (a.email || '').toLowerCase();
                valB = (b.email || '').toLowerCase();
            }
            
            if (valA < valB) return userSortAsc ? -1 : 1;
            if (valA > valB) return userSortAsc ? 1 : -1;
            return 0;
        });
        
        return list;
    }, [orgBillingData, searchTerm, userSortField, userSortAsc]);

    // Filter and Sort org projects
    const processedProjects = useMemo(() => {
        if (!orgBillingData || !orgBillingData.projects_list) return [];
        
        let list = [...orgBillingData.projects_list];
        
        // Search
        if (searchTerm) {
            const term = searchTerm.toLowerCase();
            list = list.filter(p => 
                p.project_name.toLowerCase().includes(term) || 
                p.project_token.toLowerCase().includes(term) ||
                p.owner_email.toLowerCase().includes(term)
            );
        }
        
        return list;
    }, [orgBillingData, searchTerm]);

    // Filtered lists for Standard User View
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

    // Unique agents for Standard User View
    const uniqueAgentNames = useMemo(() => {
        if (!billingData || !billingData.agent_breakdown) return [];
        return billingData.agent_breakdown.map(agent => agent.agent_name);
    }, [billingData]);

    if (loading) {
        return (
            <div className="flex flex-col items-center justify-center min-h-[400px] py-12 bg-app-bg-page">
                <RefreshCw className="w-10 h-10 text-app-primary animate-spin mb-4" />
                <p className="text-app-text-muted text-sm font-medium">
                    {isOrgAdmin 
                        ? 'Fetching organization billing metrics and operational logs...' 
                        : 'Calculating agent hours and computing billing matrices...'}
                </p>
            </div>
        );
    }

    if (error) {
        return (
            <div className="max-w-2xl mx-auto px-4 py-12 text-center bg-app-bg-page">
                <div className="inline-flex p-3 bg-rose-500/10 rounded-full text-rose-400 mb-4 border border-rose-500/20">
                    <AlertCircle className="w-8 h-8" />
                </div>
                <h3 className="text-xl font-bold text-app-text-main mb-2">Billing Data Unavailable</h3>
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

    // ── RENDER 1: Organization Admin Billing & Logs Dashboard ──
    if (isOrgAdmin && orgBillingData) {
        const { organization_name, summary: orgSummary = {} } = orgBillingData;

        return (
            <div className="flex-1 overflow-y-auto h-full bg-app-bg-page custom-scrollbar">
                <div className="max-w-6xl mx-auto px-4 py-8">
                    {/* Header */}
                    <div className="flex flex-col md:flex-row md:items-center justify-between gap-6 mb-6">
                        <div>
                            <span className="px-3 py-1 text-xs font-semibold rounded-full bg-indigo-50 dark:bg-app-primary-light text-indigo-700 dark:text-app-primary-dark border border-indigo-200/50 dark:border-app-border inline-flex items-center gap-1.5 mb-3">
                                <ShieldCheck className="w-3.5 h-3.5" /> Organization Administration
                            </span>
                            <h1 className="text-2xl font-extrabold text-app-text-main sm:text-3xl">
                                Org Billing & Activity Logs
                            </h1>
                            <p className="mt-1.5 text-sm text-app-text-label font-medium">
                                Centralized tracking of costs, usage, and operations generated inside the <strong className="text-app-text-main">{organization_name}</strong> organization.
                            </p>
                        </div>
                        <button
                            onClick={() => fetchBillingData(true)}
                            disabled={refreshing}
                            className="self-start md:self-auto px-4 py-2 border border-app-border bg-app-bg-card text-app-text-label hover:bg-app-bg-hover rounded-lg transition-all text-xs font-semibold flex items-center gap-2 disabled:opacity-50 shadow-sm cursor-pointer"
                        >
                            <RefreshCw className={`w-3.5 h-3.5 ${refreshing ? 'animate-spin' : ''}`} />
                            {refreshing ? 'Refreshing...' : 'Refresh Logs'}
                        </button>
                    </div>

                    {/* Navigation Tabs */}
                    <div className="flex gap-2 mb-8 bg-app-bg-muted p-1.5 rounded-xl border border-app-border w-fit">
                        <button 
                            className={`px-5 py-2 rounded-lg text-sm font-semibold transition-all ${activeTab === 'overview' ? 'bg-app-primary text-white shadow-md' : 'text-app-text-label hover:bg-app-bg-hover dark:text-app-text-muted dark:hover:bg-app-bg-card'}`}
                            onClick={() => { setActiveTab('overview'); setSearchTerm(''); }}
                        >
                            Overview
                        </button>
                        <button 
                            className={`px-5 py-2 rounded-lg text-sm font-semibold transition-all ${activeTab === 'users' ? 'bg-app-primary text-white shadow-md' : 'text-app-text-label hover:bg-app-bg-hover dark:text-app-text-muted dark:hover:bg-app-bg-card'}`}
                            onClick={() => { setActiveTab('users'); setSearchTerm(''); }}
                        >
                            User Engagement
                        </button>
                        <button 
                            className={`px-5 py-2 rounded-lg text-sm font-semibold transition-all ${activeTab === 'projects' ? 'bg-app-primary text-white shadow-md' : 'text-app-text-label hover:bg-app-bg-hover dark:text-app-text-muted dark:hover:bg-app-bg-card'}`}
                            onClick={() => { setActiveTab('projects'); setSearchTerm(''); }}
                        >
                            Projects Hub
                        </button>
                    </div>

                    {/* OVERVIEW TAB */}
                    {activeTab === 'overview' && (
                        <div className="space-y-8 animate-fade-in">
                            {/* KPI Grid */}
                            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
                                {/* Total Cost */}
                                <div className="bg-app-bg-card border border-app-border rounded-xl p-5 hover:border-app-primary-dark transition-all shadow-sm relative overflow-hidden">
                                    <div className="flex items-center justify-between mb-3">
                                        <span className="text-xs font-semibold text-app-text-muted uppercase tracking-wider">Total Organization Cost</span>
                                        <div className="p-2 bg-emerald-50 dark:bg-app-status-successBg rounded-lg text-emerald-600 dark:text-emerald-400 border border-emerald-200/20">
                                            <DollarSign className="w-4 h-4" />
                                        </div>
                                    </div>
                                    <h3 className="text-2xl font-black text-app-text-main">
                                        ${orgSummary.total_cost?.toLocaleString(undefined, { minimumFractionDigits: 2 })}
                                    </h3>
                                    <p className="text-[10px] text-emerald-600 dark:text-emerald-400 mt-1 flex items-center gap-1 font-semibold">
                                        <CheckCircle2 className="w-3 h-3" /> Cost generated by all members
                                    </p>
                                    <div className="absolute top-0 left-0 w-1 h-full bg-emerald-500" />
                                </div>

                                {/* Prompt Tokens */}
                                <div className="bg-app-bg-card border border-app-border rounded-xl p-5 hover:border-app-primary-dark transition-all shadow-sm relative overflow-hidden">
                                    <div className="flex items-center justify-between mb-3">
                                        <span className="text-xs font-semibold text-app-text-muted uppercase tracking-wider">Prompt Tokens</span>
                                        <div className="p-2 bg-blue-50 dark:bg-app-primary-light rounded-lg text-blue-600 dark:text-blue-450 border border-blue-200/20">
                                            <FileText className="w-4 h-4" />
                                        </div>
                                    </div>
                                    <h3 className="text-2xl font-black text-app-text-main">
                                        {orgSummary.total_prompt_tokens?.toLocaleString()}
                                    </h3>
                                    <p className="text-[10px] text-app-text-label mt-1 font-medium">
                                        Tokens sent to AI models
                                    </p>
                                    <div className="absolute top-0 left-0 w-1 h-full bg-blue-500" />
                                </div>

                                {/* Completion Tokens */}
                                <div className="bg-app-bg-card border border-app-border rounded-xl p-5 hover:border-app-primary-dark transition-all shadow-sm relative overflow-hidden">
                                    <div className="flex items-center justify-between mb-3">
                                        <span className="text-xs font-semibold text-app-text-muted uppercase tracking-wider">Completion Tokens</span>
                                        <div className="p-2 bg-purple-50 dark:bg-app-primary-light rounded-lg text-purple-650 dark:text-purple-400 border border-purple-200/20">
                                            <Bot className="w-4 h-4" />
                                        </div>
                                    </div>
                                    <h3 className="text-2xl font-black text-app-text-main">
                                        {orgSummary.total_completion_tokens?.toLocaleString()}
                                    </h3>
                                    <p className="text-[10px] text-app-text-label mt-1 font-medium">
                                        Tokens generated by AI models
                                    </p>
                                    <div className="absolute top-0 left-0 w-1 h-full bg-purple-500" />
                                </div>

                                {/* Org Members */}
                                <div className="bg-app-bg-card border border-app-border rounded-xl p-5 hover:border-app-primary-dark transition-all shadow-sm relative overflow-hidden">
                                    <div className="flex items-center justify-between mb-3">
                                        <span className="text-xs font-semibold text-app-text-muted uppercase tracking-wider">Org Members</span>
                                        <div className="p-2 bg-indigo-50 dark:bg-app-primary-light rounded-lg text-indigo-600 dark:text-indigo-400 border border-indigo-200/20">
                                            <Users className="w-4 h-4" />
                                        </div>
                                    </div>
                                    <h3 className="text-2xl font-black text-app-text-main">
                                        {orgBillingData.user_stats?.length}
                                    </h3>
                                    <p className="text-[10px] text-app-text-label mt-1 font-medium">
                                        Active users in organization
                                    </p>
                                    <div className="absolute top-0 left-0 w-1 h-full bg-indigo-500" />
                                </div>
                            </div>

                            {/* Cost Breakdown by AI Model */}
                            {orgSummary.cost_by_model && Object.keys(orgSummary.cost_by_model).length > 0 && (
                                <div className="bg-app-bg-card border border-app-border rounded-xl p-6 shadow-sm">
                                    <h3 className="text-base font-bold text-app-text-main mb-4 flex items-center gap-2">
                                        <Cpu className="w-4 h-4 text-app-primary" /> Cost Breakdown by AI Model
                                    </h3>
                                    <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-4">
                                        {Object.entries(orgSummary.cost_by_model).map(([modelName, costValue]) => {
                                            const percentage = orgSummary.total_cost > 0
                                                ? Math.round((costValue / orgSummary.total_cost) * 100)
                                                : 0;
                                            return (
                                                <div key={modelName} className="p-4 rounded-xl border border-app-border bg-app-bg-muted/50">
                                                    <div className="flex justify-between items-center mb-1">
                                                        <span className="text-xs font-bold text-app-text-label font-mono truncate mr-2" title={modelName}>{modelName}</span>
                                                        <span className="text-sm font-black text-app-text-main">${costValue.toFixed(4)}</span>
                                                    </div>
                                                    <div className="w-full bg-app-bg-hover rounded-full h-1.5 overflow-hidden">
                                                        <div className="h-full bg-app-primary rounded-full" style={{ width: `${percentage}%` }} />
                                                    </div>
                                                    <div className="flex justify-between text-[10px] text-app-text-muted mt-1 font-semibold">
                                                        <span>Share</span>
                                                        <span>{percentage}%</span>
                                                    </div>
                                                </div>
                                            );
                                        })}
                                    </div>
                                </div>
                            )}
                        </div>
                    )}

                    {/* USER ENGAGEMENT TAB */}
                    {activeTab === 'users' && (
                        <div className="bg-app-bg-card border border-app-border rounded-xl p-6 shadow-sm animate-fade-in">
                            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-6">
                                <h3 className="text-base font-bold text-app-text-main flex items-center gap-2">
                                    <Users className="w-4 h-4 text-app-primary" /> User Engagement Stats
                                </h3>
                                <div className="relative">
                                    <Search className="w-3.5 h-3.5 absolute left-3 top-1/2 transform -translate-y-1/2 text-app-text-light" />
                                    <input
                                        type="text"
                                        placeholder="Search by name or email..."
                                        value={searchTerm}
                                        onChange={(e) => setSearchTerm(e.target.value)}
                                        className="pl-9 pr-4 py-1.5 bg-app-bg-muted border border-app-border hover:border-app-border-active focus:border-app-primary text-xs text-app-text-main rounded-lg focus:outline-none transition-all w-[220px]"
                                    />
                                </div>
                            </div>

                            <div className="overflow-x-auto rounded-lg border border-app-border">
                                <table className="w-full text-left border-collapse text-xs">
                                    <thead>
                                        <tr className="border-b border-app-border bg-app-bg-muted/70 text-app-text-label uppercase font-bold tracking-wider text-[10px] select-none">
                                            <th className="py-3.5 px-4 font-bold cursor-pointer hover:text-app-primary" onClick={() => handleUserSort('name')}>
                                                Name {userSortField === 'name' ? (userSortAsc ? '▲' : '▼') : '⇅'}
                                            </th>
                                            <th className="py-3.5 px-4 font-bold cursor-pointer hover:text-app-primary" onClick={() => handleUserSort('email')}>
                                                Email {userSortField === 'email' ? (userSortAsc ? '▲' : '▼') : '⇅'}
                                            </th>
                                            <th className="py-3.5 px-4 font-bold">Status</th>
                                            <th className="py-3.5 px-4 font-bold cursor-pointer hover:text-app-primary" onClick={() => handleUserSort('last_login')}>
                                                Last Login {userSortField === 'last_login' ? (userSortAsc ? '▲' : '▼') : '⇅'}
                                            </th>
                                            <th className="py-3.5 px-4 font-bold text-right cursor-pointer hover:text-app-primary" onClick={() => handleUserSort('projects_count')}>
                                                Projects {userSortField === 'projects_count' ? (userSortAsc ? '▲' : '▼') : '⇅'}
                                            </th>
                                            <th className="py-3.5 px-4 font-bold text-right cursor-pointer hover:text-app-primary" onClick={() => handleUserSort('session_count')}>
                                                Sessions {userSortField === 'session_count' ? (userSortAsc ? '▲' : '▼') : '⇅'}
                                            </th>
                                            <th className="py-3.5 px-4 font-bold text-right cursor-pointer hover:text-app-primary" onClick={() => handleUserSort('total_duration_hours')}>
                                                Total Time (Hrs) {userSortField === 'total_duration_hours' ? (userSortAsc ? '▲' : '▼') : '⇅'}
                                            </th>
                                            <th className="py-3.5 px-4 font-bold text-right cursor-pointer hover:text-app-primary" onClick={() => handleUserSort('ai_tokens')}>
                                                AI Tokens {userSortField === 'ai_tokens' ? (userSortAsc ? '▲' : '▼') : '⇅'}
                                            </th>
                                            <th className="py-3.5 px-4 font-bold text-right cursor-pointer hover:text-app-primary" onClick={() => handleUserSort('total_cost')}>
                                                AI Cost {userSortField === 'total_cost' ? (userSortAsc ? '▲' : '▼') : '⇅'}
                                            </th>
                                        </tr>
                                    </thead>
                                    <tbody className="divide-y divide-app-border bg-app-bg-card text-app-text-main">
                                        {processedUsers.length === 0 ? (
                                            <tr>
                                                <td colSpan="9" className="py-8 px-4 text-center text-app-text-muted font-semibold">
                                                    No organization members found matching your search.
                                                </td>
                                            </tr>
                                        ) : (
                                            processedUsers.map((u) => (
                                                <tr 
                                                    key={u.id} 
                                                    onClick={() => setSelectedUserDetail(u)}
                                                    className="hover:bg-app-bg-hover transition-colors cursor-pointer"
                                                >
                                                    <td className="py-3.5 px-4 font-bold flex items-center gap-1.5">
                                                        <User className="w-3.5 h-3.5 text-app-text-muted" />
                                                        {u.name}
                                                    </td>
                                                    <td className="py-3.5 px-4 text-app-text-label font-mono font-semibold">{u.email}</td>
                                                    <td className="py-3.5 px-4">
                                                        {u.is_active ? (
                                                            <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-emerald-50 dark:bg-app-status-successBg text-emerald-700 dark:text-emerald-350 border border-emerald-250/20 inline-flex items-center gap-1">
                                                                <span className="w-1.5 h-1.5 bg-emerald-500 rounded-full" /> Active
                                                            </span>
                                                        ) : (
                                                            <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-app-bg-muted text-app-text-muted border border-app-border inline-flex items-center gap-1">
                                                                <span className="w-1.5 h-1.5 bg-app-text-light rounded-full" /> Inactive
                                                            </span>
                                                        )}
                                                    </td>
                                                    <td className="py-3.5 px-4 text-app-text-muted font-semibold">
                                                        {u.last_login ? new Date(u.last_login).toLocaleString() : 'Never'}
                                                    </td>
                                                    <td className="py-3.5 px-4 text-right font-mono font-bold">
                                                        {u.projects_count}
                                                    </td>
                                                    <td className="py-3.5 px-4 text-right font-mono font-bold">
                                                        {u.session_count}
                                                    </td>
                                                    <td className="py-3.5 px-4 text-right font-mono font-bold">
                                                        {u.total_duration_hours} hrs
                                                    </td>
                                                    <td className="py-3.5 px-4 text-right font-mono font-semibold text-app-text-label">
                                                        {u.ai_tokens?.toLocaleString()}
                                                    </td>
                                                    <td className="py-3.5 px-4 text-right font-mono font-bold text-emerald-600 dark:text-emerald-450">
                                                        ${u.total_cost?.toLocaleString(undefined, { minimumFractionDigits: 4 })}
                                                    </td>
                                                </tr>
                                            ))
                                        )}
                                    </tbody>
                                </table>
                            </div>
                        </div>
                    )}

                    {/* PROJECTS HUB TAB */}
                    {activeTab === 'projects' && (
                        <div className="bg-app-bg-card border border-app-border rounded-xl p-6 shadow-sm animate-fade-in">
                            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-6">
                                <h3 className="text-base font-bold text-app-text-main flex items-center gap-2">
                                    <Globe className="w-4 h-4 text-app-primary" /> Projects Hub
                                </h3>
                                <div className="relative">
                                    <Search className="w-3.5 h-3.5 absolute left-3 top-1/2 transform -translate-y-1/2 text-app-text-light" />
                                    <input
                                        type="text"
                                        placeholder="Search projects..."
                                        value={searchTerm}
                                        onChange={(e) => setSearchTerm(e.target.value)}
                                        className="pl-9 pr-4 py-1.5 bg-app-bg-muted border border-app-border hover:border-app-border-active focus:border-app-primary text-xs text-app-text-main rounded-lg focus:outline-none transition-all w-[220px]"
                                    />
                                </div>
                            </div>

                            <div className="overflow-x-auto rounded-lg border border-app-border">
                                <table className="w-full text-left border-collapse text-xs">
                                    <thead>
                                        <tr className="border-b border-app-border bg-app-bg-muted/70 text-app-text-label uppercase font-bold tracking-wider text-[10px]">
                                            <th className="py-3.5 px-4 font-bold">Project Name</th>
                                            <th className="py-3.5 px-4 font-bold">Project Token</th>
                                            <th className="py-3.5 px-4 font-bold">Owner Email</th>
                                            <th className="py-3.5 px-4 font-bold">Classification</th>
                                            <th className="py-3.5 px-4 font-bold text-right">Runs</th>
                                            <th className="py-3.5 px-4 font-bold text-center">Status</th>
                                            <th className="py-3.5 px-4 font-bold text-center">Created At</th>
                                        </tr>
                                    </thead>
                                    <tbody className="divide-y divide-app-border bg-app-bg-card text-app-text-main">
                                        {processedProjects.length === 0 ? (
                                            <tr>
                                                <td colSpan="7" className="py-8 px-4 text-center text-app-text-muted font-semibold">
                                                    No projects found in organization.
                                                </td>
                                            </tr>
                                        ) : (
                                            processedProjects.map((p) => (
                                                <tr key={p.project_token} className="hover:bg-app-bg-hover transition-colors">
                                                    <td className="py-3.5 px-4 font-bold">
                                                        {p.project_name}
                                                    </td>
                                                    <td className="py-3.5 px-4 font-mono text-app-text-muted font-semibold">{p.project_token}</td>
                                                    <td className="py-3.5 px-4 text-app-text-label font-mono font-semibold">{p.owner_email}</td>
                                                    <td className="py-3.5 px-4 font-semibold text-app-text-label">
                                                        {p.classification}
                                                    </td>
                                                    <td className="py-3.5 px-4 text-right font-mono font-bold">
                                                        {p.total_runs}
                                                    </td>
                                                    <td className="py-3.5 px-4 text-center">
                                                        <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                                                            p.run_status === 'success' ? 'bg-emerald-50 dark:bg-app-status-successBg text-emerald-700 dark:text-emerald-350 border border-emerald-250/20' :
                                                            p.run_status === 'failed' ? 'bg-rose-50 dark:bg-app-status-errorBg text-rose-700 dark:text-rose-400 border border-rose-250/20' :
                                                            'bg-amber-50 dark:bg-app-status-warningBg text-amber-700 dark:text-amber-450 border border-amber-250/20'
                                                        }`}>
                                                            {p.run_status}
                                                        </span>
                                                    </td>
                                                    <td className="py-3.5 px-4 text-center text-app-text-muted font-semibold">
                                                        {p.submission_date ? new Date(p.submission_date).toLocaleDateString() : '—'}
                                                    </td>
                                                </tr>
                                            ))
                                        )}
                                    </tbody>
                                </table>
                            </div>
                        </div>
                    )}
                </div>

                {/* ── DRILLDOWN MODAL ── */}
                {selectedUserDetail && (
                    <div 
                        className="fixed inset-0 bg-slate-900/60 dark:bg-black/70 backdrop-blur-sm flex items-center justify-center p-4 z-[9999]"
                        onClick={() => setSelectedUserDetail(null)}
                    >
                        <div 
                            className="bg-app-bg-card border border-app-border rounded-2xl w-full max-w-3xl overflow-hidden shadow-2xl animate-scale-up"
                            onClick={(e) => e.stopPropagation()}
                        >
                            {/* Modal Header */}
                            <div className="flex justify-between items-center px-6 py-4 border-b border-app-border bg-app-bg-muted/50">
                                <div>
                                    <h2 className="text-lg font-bold text-app-text-main">
                                        User Engagement Detail
                                    </h2>
                                    <p className="text-[11px] text-app-text-muted font-mono mt-0.5">
                                        {selectedUserDetail.name} • {selectedUserDetail.email}
                                    </p>
                                </div>
                                <button 
                                    className="p-1.5 rounded-lg hover:bg-app-bg-hover text-app-text-label hover:text-app-text-main transition-colors"
                                    onClick={() => setSelectedUserDetail(null)}
                                >
                                    ✕
                                </button>
                            </div>

                            {/* Modal Body */}
                            <div className="p-6 overflow-y-auto max-h-[75vh] space-y-6 custom-scrollbar text-xs">
                                {/* Roles & Integrations Row */}
                                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                    <div className="p-4 rounded-xl border border-app-border bg-app-bg-muted/30">
                                        <div className="font-bold text-app-text-muted mb-2 uppercase tracking-wider text-[10px]">App Roles & Org</div>
                                        <div className="flex items-center gap-2">
                                            <ShieldCheck className="w-4 h-4 text-app-primary" />
                                            <div>
                                                <span className="font-bold text-app-text-main">
                                                    {selectedUserDetail.is_org_admin ? 'Organization Admin' : 'Member'}
                                                </span>
                                                <span className="block text-[10px] text-app-text-muted font-semibold">{organization_name}</span>
                                            </div>
                                        </div>
                                    </div>
                                    <div className="p-4 rounded-xl border border-app-border bg-app-bg-muted/30">
                                        <div className="font-bold text-app-text-muted mb-2 uppercase tracking-wider text-[10px]">Connected Integrations</div>
                                        <div className="space-y-1.5 font-semibold text-app-text-label">
                                            <div className="flex justify-between">
                                                <span>GitHub Username:</span>
                                                <span className="font-mono text-app-text-main font-bold">{selectedUserDetail.github_username}</span>
                                            </div>
                                            <div className="flex justify-between">
                                                <span>Azure DevOps Username:</span>
                                                <span className="font-mono text-app-text-main font-bold">{selectedUserDetail.azure_devops_username}</span>
                                            </div>
                                        </div>
                                    </div>
                                </div>

                                {/* AI Token Breakdown Table */}
                                <div className="p-4 rounded-xl border border-app-border bg-app-bg-card">
                                    <div className="font-bold text-app-text-muted mb-3 uppercase tracking-wider text-[10px]">AI Token Usage & Cost Breakdown</div>
                                    <div className="overflow-x-auto rounded-lg border border-app-border">
                                        <table className="w-full text-left border-collapse">
                                            <thead>
                                                <tr className="bg-app-bg-muted border-b border-app-border text-[10px] font-bold text-app-text-label uppercase tracking-wider">
                                                    <th className="py-2.5 px-3">Model</th>
                                                    <th className="py-2.5 px-3 text-right">Requests</th>
                                                    <th className="py-2.5 px-3 text-right">Prompt Tokens</th>
                                                    <th className="py-2.5 px-3 text-right">Completion Tokens</th>
                                                    <th className="py-2.5 px-3 text-right">Total Tokens</th>
                                                    <th className="py-2.5 px-3 text-right">Cost (USD)</th>
                                                </tr>
                                            </thead>
                                            <tbody className="divide-y divide-app-border font-mono text-app-text-main">
                                                {selectedUserDetail.ai_usage?.length === 0 ? (
                                                    <tr>
                                                        <td colSpan="6" className="py-4 text-center font-sans text-app-text-muted">
                                                            No AI usage logs recorded for this user.
                                                        </td>
                                                    </tr>
                                                ) : (
                                                    selectedUserDetail.ai_usage?.map(uai => (
                                                        <tr key={uai.model} className="hover:bg-app-bg-hover">
                                                            <td className="py-2.5 px-3 font-sans font-bold text-app-text-main">{uai.model}</td>
                                                            <td className="py-2.5 px-3 text-right font-bold">{uai.requests}</td>
                                                            <td className="py-2.5 px-3 text-right text-app-text-muted">{uai.prompt.toLocaleString()}</td>
                                                            <td className="py-2.5 px-3 text-right text-app-text-muted">{uai.completion.toLocaleString()}</td>
                                                            <td className="py-2.5 px-3 text-right font-bold text-app-text-label">{(uai.prompt + uai.completion).toLocaleString()}</td>
                                                            <td className="py-2.5 px-3 text-right font-bold text-emerald-600 dark:text-emerald-450">${uai.cost.toFixed(4)}</td>
                                                        </tr>
                                                    ))
                                                )}
                                            </tbody>
                                        </table>
                                    </div>
                                </div>

                                {/* Permissions Paths */}
                                <div className="p-4 rounded-xl border border-app-border bg-app-bg-muted/30">
                                    <div className="font-bold text-app-text-muted mb-2 uppercase tracking-wider text-[10px]">Permissions Paths</div>
                                    <div className="flex flex-wrap gap-1.5 max-h-[120px] overflow-y-auto">
                                        {selectedUserDetail.permissions?.length === 0 ? (
                                            <span className="text-app-text-muted font-semibold italic">None (No organization roles mapped)</span>
                                        ) : (
                                            selectedUserDetail.permissions?.map(p => (
                                                <span key={p} className="px-2 py-0.5 rounded font-mono font-bold bg-app-bg-card border border-app-border text-app-text-label">
                                                    {p}
                                                </span>
                                            ))
                                        )}
                                    </div>
                                </div>

                                {/* Projects Created */}
                                <div className="p-4 rounded-xl border border-app-border bg-app-bg-card">
                                    <div className="font-bold text-app-text-muted mb-3 uppercase tracking-wider text-[10px]">Projects Created By User</div>
                                    <div className="overflow-x-auto rounded-lg border border-app-border">
                                        <table className="w-full text-left border-collapse">
                                            <thead>
                                                <tr className="bg-app-bg-muted border-b border-app-border text-[10px] font-bold text-app-text-label uppercase tracking-wider">
                                                    <th className="py-2.5 px-3">Project Name</th>
                                                    <th className="py-2.5 px-3">Classification</th>
                                                    <th className="py-2.5 px-3 text-center">Last Build Status</th>
                                                </tr>
                                            </thead>
                                            <tbody className="divide-y divide-app-border text-app-text-main">
                                                {selectedUserDetail.projects?.length === 0 ? (
                                                    <tr>
                                                        <td colSpan="3" className="py-4 text-center text-app-text-muted">
                                                            No projects created by this user yet.
                                                        </td>
                                                    </tr>
                                                ) : (
                                                    selectedUserDetail.projects?.map(p => (
                                                        <tr key={p.project_name} className="hover:bg-app-bg-hover">
                                                            <td className="py-2.5 px-3 font-bold text-app-text-main">{p.project_name}</td>
                                                            <td className="py-2.5 px-3 font-semibold text-app-text-label">{p.classification}</td>
                                                            <td className="py-2.5 px-3 text-center">
                                                                <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                                                                    p.status === 'success' ? 'bg-emerald-50 dark:bg-app-status-successBg text-emerald-700 dark:text-emerald-350 border border-emerald-250/20' :
                                                                    p.status === 'failed' ? 'bg-rose-50 dark:bg-app-status-errorBg text-rose-700 dark:text-rose-400 border border-rose-250/20' :
                                                                    'bg-amber-50 dark:bg-app-status-warningBg text-amber-700 dark:text-amber-450 border border-amber-250/20'
                                                                }`}>
                                                                    {p.status}
                                                                </span>
                                                            </td>
                                                        </tr>
                                                    ))
                                                )}
                                            </tbody>
                                        </table>
                                    </div>
                                </div>

                                {/* Recent Activity / Session Logs */}
                                <div className="p-4 rounded-xl border border-app-border bg-app-bg-card">
                                    <div className="font-bold text-app-text-muted mb-3 uppercase tracking-wider text-[10px]">Recent Session / Activity Logs</div>
                                    <div className="overflow-x-auto rounded-lg border border-app-border">
                                        <table className="w-full text-left border-collapse">
                                            <thead>
                                                <tr className="bg-app-bg-muted border-b border-app-border text-[10px] font-bold text-app-text-label uppercase tracking-wider">
                                                    <th className="py-2.5 px-3">Date / Time</th>
                                                    <th className="py-2.5 px-3">Action</th>
                                                    <th className="py-2.5 px-3">Path</th>
                                                    <th className="py-2.5 px-3">IP Address</th>
                                                    <th className="py-2.5 px-3">User Agent</th>
                                                </tr>
                                            </thead>
                                            <tbody className="divide-y divide-app-border font-mono text-[11px] text-app-text-main">
                                                {selectedUserDetail.recent_sessions?.length === 0 ? (
                                                    <tr>
                                                        <td colSpan="5" className="py-4 text-center font-sans text-app-text-muted">
                                                            No operational logs recorded for this user.
                                                        </td>
                                                    </tr>
                                                ) : (
                                                    selectedUserDetail.recent_sessions?.map(act => (
                                                        <tr key={act.created_at + act.path} className="hover:bg-app-bg-hover">
                                                            <td className="py-2.5 px-3 text-app-text-muted font-sans">{new Date(act.created_at).toLocaleString()}</td>
                                                            <td className="py-2.5 px-3 font-bold text-app-text-main">{act.action}</td>
                                                            <td className="py-2.5 px-3 text-app-text-muted max-w-[120px] truncate" title={act.path}>{act.path}</td>
                                                            <td className="py-2.5 px-3 text-app-text-label">{act.ip_address}</td>
                                                            <td className="py-2.5 px-3 text-app-text-muted truncate max-w-[150px]" title={act.user_agent}>{act.user_agent}</td>
                                                        </tr>
                                                    ))
                                                )}
                                            </tbody>
                                        </table>
                                    </div>
                                </div>
                            </div>

                            {/* Modal Footer */}
                            <div className="flex justify-end gap-3 px-6 py-4 border-t border-app-border bg-app-bg-muted/50">
                                <button 
                                    className="px-4 py-2 border border-app-border hover:bg-app-bg-hover rounded-lg text-app-text-label font-semibold"
                                    onClick={() => setSelectedUserDetail(null)}
                                >
                                    Close Detail Profile
                                </button>
                            </div>
                        </div>
                    </div>
                )}
            </div>
        );
    }

    // ── RENDER 2: Standard User Agent Billing Dashboard ──
    const { summary, agent_breakdown = [] } = billingData || {};

    return (
        <div className="flex-1 overflow-y-auto h-full bg-app-bg-page custom-scrollbar">
            <div className="max-w-6xl mx-auto px-4 py-8">
                {/* Header */}
                <div className="flex flex-col md:flex-row md:items-center justify-between gap-6 mb-8">
                    <div>
                        <span className="px-3 py-1 text-xs font-semibold rounded-full bg-blue-50 dark:bg-app-primary-light text-blue-700 dark:text-app-primary-dark border border-blue-200/50 inline-flex items-center gap-1.5 mb-3">
                            <Sparkles className="w-3.5 h-3.5" /> Billing & Agent Metrics
                        </span>
                        <h1 className="text-2xl font-extrabold text-app-text-main sm:text-3xl">
                            Execution Billing Dashboard
                        </h1>
                        <p className="mt-1.5 text-sm text-app-text-label font-medium">
                            Real-time tracking of tasks completed, resource time logs, and computed cost share per agent.
                        </p>
                    </div>
                    <button
                        onClick={() => fetchBillingData(true)}
                        disabled={refreshing}
                        className="self-start md:self-auto px-4 py-2 border border-app-border bg-app-bg-card text-app-text-label hover:bg-app-bg-hover rounded-lg transition-all text-xs font-semibold flex items-center gap-2 disabled:opacity-50 shadow-sm cursor-pointer"
                    >
                        <RefreshCw className={`w-3.5 h-3.5 ${refreshing ? 'animate-spin' : ''}`} />
                        {refreshing ? 'Syncing...' : 'Sync Log'}
                    </button>
                </div>

                {/* Project Context Info */}
                {activeProject && (
                    <div className="mb-6 p-4 rounded-xl bg-blue-50/50 dark:bg-app-primary-light/10 border border-blue-100 dark:border-app-border flex items-center justify-between shadow-sm">
                        <div className="flex items-center gap-2">
                            <Zap className="w-4 h-4 text-blue-600 dark:text-app-primary-dark" />
                            <span className="text-xs font-semibold text-app-text-label">
                                Active Project: <strong className="text-app-text-main font-bold">{activeProject.name || selectedProjectKey}</strong>
                            </span>
                        </div>
                        <span className="text-[10px] bg-emerald-50 text-emerald-700 dark:bg-app-status-successBg dark:text-emerald-350 border border-emerald-200/50 px-2 py-0.5 rounded font-mono font-semibold uppercase tracking-wider">
                            Live Tracking
                        </span>
                    </div>
                )}

                {/* Metrics Overview Cards */}
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
                    {/* Total Cost Card */}
                    <div className="bg-app-bg-card border border-app-border rounded-xl p-5 hover:border-app-primary-dark transition-all shadow-sm">
                        <div className="flex items-center justify-between mb-3">
                            <span className="text-xs font-semibold text-app-text-muted uppercase tracking-wider">Total Costs</span>
                            <div className="p-2 bg-emerald-50 dark:bg-app-status-successBg rounded-lg text-emerald-600 dark:text-emerald-400 border border-emerald-200/20">
                                <DollarSign className="w-4 h-4" />
                            </div>
                        </div>
                        <h3 className="text-2xl font-black text-app-text-main">
                            ${summary?.total_amount_due?.toLocaleString(undefined, { minimumFractionDigits: 2 })}
                        </h3>
                        <p className="text-[10px] text-emerald-600 dark:text-emerald-400 mt-1 flex items-center gap-1 font-semibold">
                            <CheckCircle2 className="w-3 h-3" /> Fully verified executions
                        </p>
                    </div>

                    {/* Billable Hours */}
                    <div className="bg-app-bg-card border border-app-border rounded-xl p-5 hover:border-app-primary-dark transition-all shadow-sm">
                        <div className="flex items-center justify-between mb-3">
                            <span className="text-xs font-semibold text-app-text-muted uppercase tracking-wider">Billable Time</span>
                            <div className="p-2 bg-blue-50 dark:bg-app-primary-light rounded-lg text-blue-650 dark:text-blue-400 border border-blue-200/20">
                                <Clock className="w-4 h-4" />
                            </div>
                        </div>
                        <h3 className="text-2xl font-black text-app-text-main">
                            {summary?.total_hours_billed} <span className="text-xs text-app-text-muted font-normal">hrs</span>
                        </h3>
                        <p className="text-[10px] text-app-text-muted mt-1 font-medium">
                            Cumulated time spent
                        </p>
                    </div>

                    {/* Tasks Completed */}
                    <div className="bg-app-bg-card border border-app-border rounded-xl p-5 hover:border-app-primary-dark transition-all shadow-sm">
                        <div className="flex items-center justify-between mb-3">
                            <span className="text-xs font-semibold text-app-text-muted uppercase tracking-wider">Tasks Completed</span>
                            <div className="p-2 bg-indigo-50 dark:bg-app-primary-light rounded-lg text-indigo-650 dark:text-indigo-400 border border-indigo-200/20">
                                <CheckCircle2 className="w-4 h-4" />
                            </div>
                        </div>
                        <h3 className="text-2xl font-black text-app-text-main">
                            {summary?.total_tasks_completed}
                        </h3>
                        <p className="text-[10px] text-app-text-muted mt-1 font-medium">
                            Completed agent threads
                        </p>
                    </div>

                    {/* Unique Agents */}
                    <div className="bg-app-bg-card border border-app-border rounded-xl p-5 hover:border-app-primary-dark transition-all shadow-sm">
                        <div className="flex items-center justify-between mb-3">
                            <span className="text-xs font-semibold text-app-text-muted uppercase tracking-wider">Agents Used</span>
                            <div className="p-2 bg-purple-50 dark:bg-app-primary-light rounded-lg text-purple-650 dark:text-purple-400 border border-purple-200/20">
                                <Bot className="w-4 h-4" />
                            </div>
                        </div>
                        <h3 className="text-2xl font-black text-app-text-main">
                            {agent_breakdown.length}
                        </h3>
                        <p className="text-[10px] text-app-text-muted mt-1 font-medium">
                            Includes sub & master agents
                        </p>
                    </div>
                </div>

                {/* Agent-wise Fleet Utilization Breakdown */}
                <div className="mb-8">
                    <h3 className="text-base font-bold text-app-text-main mb-4 flex items-center gap-2">
                        <Cpu className="w-4 h-4 text-app-primary" /> Agent Fleet Resource Utilization
                    </h3>
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                        {agent_breakdown.map((agent) => {
                            const costPercentage = summary?.total_amount_due > 0 
                                ? Math.round((agent.total_cost / summary.total_amount_due) * 100)
                                : 0;

                            return (
                                <div 
                                    key={agent.agent_name}
                                    className="bg-app-bg-card border border-app-border rounded-xl p-5 transition-all flex flex-col justify-between shadow-sm"
                                >
                                    <div className="mb-4">
                                        <div className="flex items-center justify-between mb-2">
                                            <div className="flex items-center gap-2">
                                                <div className={`p-1.5 rounded-lg border ${
                                                    agent.agent_type === 'Master Agent' 
                                                        ? 'bg-blue-50 dark:bg-app-primary-light text-blue-600 dark:text-app-primary-dark border-blue-100 dark:border-app-border'
                                                        : 'bg-app-bg-muted text-app-text-label border-app-border'
                                                }`}>
                                                    <Bot className="w-4 h-4" />
                                                </div>
                                                <div>
                                                    <h4 className="text-sm font-bold text-app-text-main">{agent.agent_name}</h4>
                                                    <span className="text-[10px] text-app-text-muted font-semibold uppercase">{agent.agent_type}</span>
                                                </div>
                                            </div>
                                            <span className="text-xs font-mono font-bold text-emerald-600 dark:text-emerald-450">
                                                ${agent.rate_per_hour}/hr
                                            </span>
                                        </div>
                                        <p className="text-xs text-app-text-label mb-4 leading-relaxed font-semibold">
                                            Completed <strong className="text-app-text-main font-bold">{agent.tasks_completed}</strong> tasks in <strong className="text-app-text-main font-bold">{agent.total_hours}</strong> billable hours.
                                        </p>
                                    </div>

                                    <div>
                                        <div className="flex justify-between items-baseline mb-1">
                                            <span className="text-xs text-app-text-muted font-semibold">Total cost share</span>
                                            <span className="text-sm font-black text-app-text-main">${agent.total_cost.toLocaleString()}</span>
                                        </div>
                                        <div className="w-full bg-app-bg-muted rounded-full h-1.5 overflow-hidden">
                                            <div 
                                                className={`h-full rounded-full transition-all duration-500 ${
                                                    agent.agent_type === 'Master Agent'
                                                        ? 'bg-gradient-to-r from-blue-600 to-indigo-650'
                                                        : 'bg-gradient-to-r from-blue-400 to-indigo-400'
                                                }`}
                                                style={{ width: `${costPercentage}%` }}
                                            />
                                        </div>
                                        <div className="flex justify-between text-[10px] text-app-text-muted mt-1 font-semibold">
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
                <div className="bg-app-bg-card border border-app-border rounded-xl p-6 mb-8 shadow-sm">
                    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-6">
                        <h3 className="text-base font-bold text-app-text-main flex items-center gap-2">
                            <CreditCard className="w-4 h-4 text-app-primary" /> Billable Activity Log
                        </h3>
                        
                        {/* Filters */}
                        <div className="flex flex-wrap items-center gap-3">
                            {/* Search */}
                            <div className="relative">
                                <Search className="w-3.5 h-3.5 absolute left-3 top-1/2 transform -translate-y-1/2 text-app-text-light" />
                                <input
                                    type="text"
                                    placeholder="Search by ID or name..."
                                    value={searchTerm}
                                    onChange={(e) => setSearchTerm(e.target.value)}
                                    className="pl-9 pr-4 py-1.5 bg-app-bg-muted border border-app-border hover:border-app-border-active focus:border-app-primary text-xs text-app-text-main rounded-lg focus:outline-none transition-all w-[180px] sm:w-[220px] shadow-inner"
                                />
                            </div>

                            {/* Agent dropdown */}
                            <div className="relative flex items-center bg-app-bg-muted border border-app-border hover:border-app-border-active rounded-lg px-3 py-1.5 transition-all shadow-inner">
                                <Filter className="w-3.5 h-3.5 text-app-text-light mr-2" />
                                <select
                                    value={agentFilter}
                                    onChange={(e) => setAgentFilter(e.target.value)}
                                    className="bg-transparent text-xs text-app-text-main focus:outline-none cursor-pointer pr-1"
                                >
                                    <option value="all" className="bg-app-bg-card text-app-text-main">All Agents</option>
                                    {uniqueAgentNames.map(name => (
                                        <option key={name} value={name} className="bg-app-bg-card text-app-text-main">{name}</option>
                                    ))}
                                </select>
                            </div>
                        </div>
                    </div>

                    {/* Table */}
                    <div className="overflow-x-auto rounded-lg border border-app-border bg-app-bg-muted/20">
                        <table className="w-full text-left border-collapse text-xs">
                            <thead>
                                <tr className="border-b border-app-border bg-app-bg-muted/70 text-app-text-label uppercase font-bold tracking-wider select-none text-[10px]">
                                    <th className="py-3.5 px-4 font-bold">Task ID</th>
                                    <th className="py-3.5 px-4 font-bold">Task Description</th>
                                    <th className="py-3.5 px-4 font-bold">Assigned Agent</th>
                                    <th className="py-3.5 px-4 font-bold text-right">Time Spent</th>
                                    <th className="py-3.5 px-4 font-bold text-right">Hourly Rate</th>
                                    <th className="py-3.5 px-4 font-bold text-right">Total Cost</th>
                                    <th className="py-3.5 px-4 font-bold text-center">Completed At</th>
                                </tr>
                            </thead>
                            <tbody className="divide-y divide-app-border bg-app-bg-card text-app-text-main">
                                {filteredTasks.length === 0 ? (
                                    <tr>
                                        <td colSpan="7" className="py-8 px-4 text-center text-app-text-muted font-semibold">
                                            No billable activity logs matched your current filters.
                                        </td>
                                    </tr>
                                ) : (
                                    filteredTasks.map((task) => (
                                        <tr key={task.task_id} className="hover:bg-app-bg-hover transition-colors">
                                            <td className="py-3.5 px-4 font-mono font-bold text-app-primary">
                                                {task.task_id}
                                            </td>
                                            <td className="py-3.5 px-4 font-bold max-w-[280px] truncate">
                                                {task.task_name}
                                            </td>
                                            <td className="py-3.5 px-4">
                                                <div className="flex items-center gap-1.5">
                                                    <div className="p-1 rounded bg-app-bg-muted text-app-text-label">
                                                        {task.agent_type === 'Master Agent' ? <Cpu className="w-3 h-3 text-app-primary" /> : <User className="w-3 h-3" />}
                                                    </div>
                                                    <div>
                                                        <span className="font-bold">{task.agent_name}</span>
                                                        <span className="block text-[9px] text-app-text-muted uppercase font-semibold">{task.agent_type}</span>
                                                    </div>
                                                </div>
                                            </td>
                                            <td className="py-3.5 px-4 text-right font-mono font-bold">
                                                {task.time_taken_hours} hrs
                                            </td>
                                            <td className="py-3.5 px-4 text-right font-mono font-semibold text-app-text-muted">
                                                ${task.rate_per_hour}/hr
                                            </td>
                                            <td className="py-3.5 px-4 text-right font-mono font-bold text-emerald-600 dark:text-emerald-450">
                                                ${task.cost.toLocaleString(undefined, { minimumFractionDigits: 2 })}
                                            </td>
                                            <td className="py-3.5 px-4 text-center font-mono font-semibold">
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
                <div className="bg-app-bg-card border border-app-border rounded-xl p-6 flex flex-col sm:flex-row items-center gap-4 justify-between shadow-sm">
                    <div className="flex items-center gap-3">
                        <div className="p-3 bg-amber-50 dark:bg-app-status-warningBg rounded-lg text-amber-600 dark:text-amber-400 border border-amber-200/20">
                            <ShieldAlert className="w-6 h-6" />
                        </div>
                        <div>
                            <h4 className="font-bold text-app-text-main">Looking for custom security compliance?</h4>
                            <p className="text-sm text-app-text-label font-semibold">We offer SOC2 type II compliance, high-availability setups, and on-premises agent execution.</p>
                        </div>
                    </div>
                    <button className="whitespace-nowrap px-4 py-2 text-sm font-semibold text-amber-600 hover:text-amber-700 dark:text-amber-400 dark:hover:text-amber-300 border border-amber-300 hover:bg-amber-50 dark:border-amber-700/50 dark:hover:bg-amber-950/20 rounded-lg transition-colors cursor-pointer">
                        Talk to Compliance
                    </button>
                </div>
            </div>
        </div>
    );
}
