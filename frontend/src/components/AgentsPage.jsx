import React, { useState, useEffect, useMemo } from 'react';
import { Users, Trash2, Activity, Clock, CheckCircle, AlertCircle, RefreshCw, Filter, Server, Database, GitBranch, Bot, Globe } from 'lucide-react';
import { API_ENDPOINTS } from '../config';
import ProjectDropdown from './ProjectDropdown';
import { getNeutralAgentName, getNeutralAgentLabel } from '../utils/agentNames';
import kaktoxLogo from '../assets/Kaktox.png';
import nModLogo from '../assets/N-Mod-icon.png';
import masterLogo from '../assets/logo1.png';
import cloudIcon from '../assets/cloud-icon.png';

/**
 * AgentsPage – Full‑screen view of all agents for the current organization / project.
 * It lists shared and dedicated agents separately and allows deletion of dedicated agents only.
 */
export default function AgentsPage({ selectedProjectKey, setSelectedProjectKey, projects = [] }) {
  const [sharedAgents, setSharedAgents] = useState([]);        // this project's agents
  const [dedicatedAgents, setDedicatedAgents] = useState([]);   // this project's agents
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [deletingId, setDeletingId] = useState(null);
  const [filter, setFilter] = useState('all');
  const [quota, setQuota] = useState(null);
  const [quotaError, setQuotaError] = useState('');
  const [quotaLoading, setQuotaLoading] = useState(false);
  const [sharedDevToAdd, setSharedDevToAdd] = useState(0);
  const [sharedTestToAdd, setSharedTestToAdd] = useState(0);
  const [dedicatedDevToAdd, setDedicatedDevToAdd] = useState(0);
  const [dedicatedTestToAdd, setDedicatedTestToAdd] = useState(0);
  const [quotaUpdatingKind, setQuotaUpdatingKind] = useState('');

  const fetchAgents = async () => {
    setLoading(true);
    setError(null);
    const token = localStorage.getItem('token');
    try {
      const headers = { Authorization: `Bearer ${token}` };
      const parse = (data) => Array.isArray(data) ? data : (data?.agents || data?.results || data?.data || []);

      const fetchKind = (kind, projectToken) => {
        const url = new URL(API_ENDPOINTS.AGENTS);
        url.searchParams.set('include_defaults', 'false');
        url.searchParams.set('kind', kind);
        if (projectToken) url.searchParams.set('project_token', projectToken);
        return fetch(url.toString(), { headers })
          .then(r => r.ok ? r.json().then(parse) : [])
          .catch(() => []);
      };

      // Project-level: agents onboarded to THIS project
      const [projShared, projDedicated] = await Promise.all([
        fetchKind('shared', selectedProjectKey),
        selectedProjectKey ? fetchKind('dedicated', selectedProjectKey) : Promise.resolve([]),
      ]);
      setSharedAgents(projShared.map(a => ({ ...a, agentType: 'shared' })));
      setDedicatedAgents(projDedicated.map(a => ({ ...a, agentType: 'dedicated' })));

    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchAgents();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedProjectKey]);

  const fetchQuota = async () => {
    const token = localStorage.getItem('token');
    if (!token) return;
    setQuotaLoading(true);
    setQuotaError('');
    try {
      const res = await fetch(API_ENDPOINTS.ORG_AGENT_QUOTA, {
        headers: { Authorization: `Bearer ${token}` },
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        throw new Error(data.detail || 'Failed to load organization agent quota');
      }
      setQuota(data);
    } catch (e) {
      setQuotaError(e?.message || 'Failed to load organization agent quota');
    } finally {
      setQuotaLoading(false);
    }
  };

  useEffect(() => {
    fetchQuota();
  }, []);

  const clampPositiveInt = (value, max = 1000) => {
    const n = Number(value);
    if (!Number.isFinite(n)) return 1;
    return Math.max(1, Math.min(max, Math.floor(n)));
  };

  const increaseQuota = async (kind, subType, amount) => {
    const token = localStorage.getItem('token');
    if (!token) return;
    setQuotaUpdatingKind(kind);
    setQuotaError('');
    try {
      const res = await fetch(API_ENDPOINTS.ORG_AGENT_QUOTA_INCREASE, {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ kind, sub_type: subType, amount }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        throw new Error(data.detail || 'Failed to update agent quota');
      }
      setQuota(data);
      await fetchAgents();
      await fetchQuota();
    } catch (e) {
      setQuotaError(e?.message || 'Failed to update agent quota');
    } finally {
      setQuotaUpdatingKind('');
    }
  };

  const handleDeleteAgent = async (agentId) => {
    setDeletingId(agentId);
    const token = localStorage.getItem('token');
    try {
      const deleteUrl = new URL(API_ENDPOINTS.AGENT_REMOVE(agentId));
      if (selectedProjectKey) {
        deleteUrl.searchParams.set('project_token', selectedProjectKey);
      }
      const res = await fetch(deleteUrl.toString(), {
        method: 'DELETE',
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) throw new Error('Failed to delete agent');

      // Remove from dedicated agents list and refetch
      setDedicatedAgents((prev) => prev.filter((a) => a.id !== agentId));
      // Refetch to ensure consistency
      await fetchAgents();
      await fetchQuota();
    } catch (e) {
      setError(e.message);
    } finally {
      setDeletingId(null);
    }
  };

  const getStatusIcon = (status) => {
    switch (status) {
      case 'running':
        return <Activity className="w-4 h-4 text-cyan-500 animate-pulse" />;
      case 'idle':
        return <CheckCircle className="w-4 h-4 text-app-primary" />;
      case 'error':
      case 'failed':
        return <AlertCircle className="w-4 h-4 text-app-status-error" />;
      default:
        return <Clock className="w-4 h-4 text-app-text-light" />;
    }
  };

  const getStatusColor = (status) => {
    switch (status) {
      case 'running':
        return 'bg-cyan-500/10 border-cyan-500/30 text-cyan-400';
      case 'idle':
        return 'bg-app-primary/10 border-app-primary/30 text-blue-400';
      case 'error':
      case 'failed':
        return 'bg-app-status-error/10 border-app-status-error/30 text-red-400';
      default:
        return 'bg-app-text-muted/10 border-app-text-muted/30 text-app-text-light';
    }
  };

  const getTypeColor = (type) => {
    const colors = {
      validator: 'bg-purple-500/20 text-purple-400',
      risk: 'bg-app-status-warning/20 text-amber-400',
      estimator: 'bg-cyan-500/20 text-cyan-400',
    };
    return colors[type] || 'bg-app-text-muted/20 text-app-text-light';
  };

  // Default system agents that appear in all projects
  const defaultAgents = useMemo(() => {
    return [
      {
        id: 'agent_03',
        name: 'Git Manager',
        status: 'idle',
        agentType: 'system',
        type: 'system',
        logo: null,
        icon: GitBranch,
      },
      {
        id: 'agent_04',
        name: 'Master Agent',
        status: 'idle',
        agentType: 'system',
        type: 'system',
        logo: masterLogo,
        icon: Bot,
      },

      {
        id: 'deploy_agent',
        name: 'Deploy Agent',
        status: 'idle',
        agentType: 'system',
        type: 'system',
        icon: Globe,
      },
    ];
  }, []);

  // Filter agents based on selected filter
  const getFilteredAgents = () => {
    const allAgents = [...defaultAgents, ...sharedAgents, ...dedicatedAgents];
    switch (filter) {
      case 'shared':
        return sharedAgents;
      case 'dedicated':
        return dedicatedAgents;
      default:
        return allAgents;
    }
  };

  const filteredAgents = getFilteredAgents();
  const totalAgents = defaultAgents.length + sharedAgents.length + dedicatedAgents.length;

  const quotaSummary = useMemo(() => {
    if (!quota) return null;
    const sharedQuota = Number(quota.shared_quota ?? 0);
    const dedicatedQuota = Number(quota.dedicated_quota ?? 0);
    const sharedUsed = selectedProjectKey
      ? sharedAgents.length
      : Number(quota.shared_used ?? 0);
    const dedicatedUsed = selectedProjectKey
      ? dedicatedAgents.length
      : Number(quota.dedicated_used ?? 0);
    const sharedAvailable = Math.max(0, sharedQuota - sharedUsed);
    const dedicatedAvailable = Math.max(0, dedicatedQuota - dedicatedUsed);

    // This project's dev/test used
    const sharedDevCount = sharedAgents.filter(a => !a.sub_type || a.sub_type === 'dev').length;
    const sharedTestCount = sharedAgents.filter(a => a.sub_type === 'test').length;
    const dedicatedDevCount = dedicatedAgents.filter(a => !a.sub_type || a.sub_type === 'dev').length;
    const dedicatedTestCount = dedicatedAgents.filter(a => a.sub_type === 'test').length;

    // Org-wide pool totals: from quota API sub_type fields (source of truth)
    const orgSharedDevTotal = Number(quota.shared_dev_quota ?? 0);
    const orgSharedTestTotal = Number(quota.shared_test_quota ?? 0);
    const orgDedicatedDevTotal = Number(quota.dedicated_dev_quota ?? 0);
    const orgDedicatedTestTotal = Number(quota.dedicated_test_quota ?? 0);

    // Available for this project = org sub_type quota − this project's sub_type usage
    const sharedDevAvailable = Math.max(0, orgSharedDevTotal - sharedDevCount);
    const sharedTestAvailable = Math.max(0, orgSharedTestTotal - sharedTestCount);
    const dedicatedDevAvailable = Math.max(0, orgDedicatedDevTotal - dedicatedDevCount);
    const dedicatedTestAvailable = Math.max(0, orgDedicatedTestTotal - dedicatedTestCount);

    return {
      sharedQuota, dedicatedQuota,
      sharedUsed, dedicatedUsed,
      sharedAvailable, dedicatedAvailable,
      sharedDevCount, sharedTestCount,
      dedicatedDevCount, dedicatedTestCount,
      orgSharedDevTotal, orgSharedTestTotal,
      orgDedicatedDevTotal, orgDedicatedTestTotal,
      sharedDevAvailable, sharedTestAvailable,
      dedicatedDevAvailable, dedicatedTestAvailable,
    };
  }, [quota, selectedProjectKey, sharedAgents, dedicatedAgents]);

  return (
    <div className="h-full w-full flex flex-col bg-app-bg-page text-app-text-main">
      {/* Header */}
      <div className="flex-shrink-0 flex items-center justify-between px-6 py-4 border-b border-app-border-light bg-app-bg-card/50">
        <h1 className="text-2xl font-bold flex items-center">
          <Users className="w-6 h-6 mr-2" /> Agents
        </h1>
        <div className="flex items-center space-x-3">
          <div className="w-56">
            <ProjectDropdown
              projects={projects}
              selectedKey={selectedProjectKey}
              onSelect={(project) => {
                if (!project?.key || project.key === selectedProjectKey || typeof setSelectedProjectKey !== 'function') return;
                setSelectedProjectKey(project.key);
              }}
            />
          </div>
          <span className="text-sm text-app-text-muted">
            {totalAgents} agent{totalAgents !== 1 ? 's' : ''} ({defaultAgents.length} system, {sharedAgents.length} shared, {dedicatedAgents.length} dedicated)
          </span>
          <button
            onClick={fetchAgents}
            disabled={loading}
            className="flex items-center px-4 py-2 text-sm font-medium text-app-text-main bg-app-text-label/20 rounded-lg hover:bg-app-text-label/30 transition-colors disabled:opacity-50"
          >
            <RefreshCw className={`w-4 h-4 mr-2 ${loading ? 'animate-spin' : ''}`} />
            Refresh
          </button>
        </div>
      </div>

      {/* Organization Capacity */}
      <div className="flex-shrink-0 px-4 md:px-6 py-2 border-b border-app-border-light bg-gradient-to-br from-app-bg-card/50 to-app-bg-card/30">
        {quotaLoading ? (
          <div className="flex items-center gap-2 text-xs text-app-text-muted py-1">
            <RefreshCw className="w-3 h-3 animate-spin" />
            <span>Loading capacity…</span>
          </div>
        ) : quotaError ? (
          <div className="p-2 rounded-lg bg-app-status-error/10 border border-app-status-error/30">
            <p className="text-xs text-red-400 flex items-center gap-2">
              <AlertCircle className="w-3 h-3" />
              {quotaError}
            </p>
          </div>
        ) : quotaSummary ? (
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">

            {/* ── Shared Capacity Card ── */}
            <div className="rounded-xl border border-cyan-500/25 bg-gradient-to-br from-cyan-500/8 to-cyan-400/4 p-3 shadow-sm hover:shadow-lg hover:border-cyan-500/40 transition-all duration-200">
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2">
                  <div className="p-1 rounded-lg bg-cyan-500/20"><Users className="w-3.5 h-3.5 text-cyan-400" /></div>
                  <span className="text-xs font-bold text-app-text-main">Shared</span>
                </div>
                <span className="text-[10px] text-app-text-muted font-medium">{quotaSummary.sharedUsed}/{quotaSummary.sharedQuota} used</span>
              </div>
              <div className="relative h-1.5 bg-app-bg-muted/60 rounded-full overflow-hidden mb-3">
                <div className="absolute inset-y-0 left-0 bg-gradient-to-r from-cyan-500 to-cyan-400 rounded-full transition-all duration-500"
                  style={{ width: `${quotaSummary.sharedQuota > 0 ? Math.min(100, (quotaSummary.sharedUsed / quotaSummary.sharedQuota) * 100) : 0}%` }} />
              </div>
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-[10px] font-semibold text-app-text-muted uppercase tracking-widest">Org Pool</span>
                  <div className="flex gap-1.5">
                    <span className="px-2 py-0.5 rounded-md text-[10px] font-bold bg-emerald-500/15 text-emerald-400 border border-emerald-500/20">Dev {quotaSummary.orgSharedDevTotal}</span>
                    <span className="px-2 py-0.5 rounded-md text-[10px] font-bold bg-sky-500/15 text-sky-400 border border-sky-500/20">Test {quotaSummary.orgSharedTestTotal}</span>
                  </div>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-[10px] font-semibold text-app-text-muted uppercase tracking-widest">Used</span>
                  <div className="flex gap-1.5">
                    <span className="px-2 py-0.5 rounded-md text-[10px] font-bold bg-amber-500/15 text-amber-400 border border-amber-500/20">Dev {quotaSummary.sharedDevCount}</span>
                    <span className="px-2 py-0.5 rounded-md text-[10px] font-bold bg-amber-500/15 text-amber-400 border border-amber-500/20">Test {quotaSummary.sharedTestCount}</span>
                  </div>
                </div>
                <div className="flex items-center justify-between pt-1.5 border-t border-cyan-500/15">
                  <span className="text-[10px] font-bold text-cyan-400 uppercase tracking-widest">Available</span>
                  <div className="flex gap-1.5">
                    <span className="px-2 py-0.5 rounded-md text-[10px] font-bold bg-emerald-500/20 text-emerald-300 border border-emerald-500/30">Dev {quotaSummary.sharedDevAvailable}</span>
                    <span className="px-2 py-0.5 rounded-md text-[10px] font-bold bg-sky-500/20 text-sky-300 border border-sky-500/30">Test {quotaSummary.sharedTestAvailable}</span>
                  </div>
                </div>
              </div>
            </div>

            {/* ── Dedicated Capacity Card ── */}
            <div className="rounded-xl border border-indigo-500/25 bg-gradient-to-br from-indigo-500/8 to-purple-500/4 p-3 shadow-sm hover:shadow-lg hover:border-indigo-500/40 transition-all duration-200">
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2">
                  <div className="p-1 rounded-lg bg-indigo-500/20"><Database className="w-3.5 h-3.5 text-indigo-400" /></div>
                  <span className="text-xs font-bold text-app-text-main">Dedicated</span>
                </div>
                <span className="text-[10px] text-app-text-muted font-medium">{quotaSummary.dedicatedUsed}/{quotaSummary.dedicatedQuota} used</span>
              </div>
              <div className="relative h-1.5 bg-app-bg-muted/60 rounded-full overflow-hidden mb-3">
                <div className="absolute inset-y-0 left-0 bg-gradient-to-r from-indigo-500 to-purple-500 rounded-full transition-all duration-500"
                  style={{ width: `${quotaSummary.dedicatedQuota > 0 ? Math.min(100, (quotaSummary.dedicatedUsed / quotaSummary.dedicatedQuota) * 100) : 0}%` }} />
              </div>
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-[10px] font-semibold text-app-text-muted uppercase tracking-widest">Org Pool</span>
                  <div className="flex gap-1.5">
                    <span className="px-2 py-0.5 rounded-md text-[10px] font-bold bg-emerald-500/15 text-emerald-400 border border-emerald-500/20">Dev {quotaSummary.orgDedicatedDevTotal}</span>
                    <span className="px-2 py-0.5 rounded-md text-[10px] font-bold bg-sky-500/15 text-sky-400 border border-sky-500/20">Test {quotaSummary.orgDedicatedTestTotal}</span>
                  </div>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-[10px] font-semibold text-app-text-muted uppercase tracking-widest">Used</span>
                  <div className="flex gap-1.5">
                    <span className="px-2 py-0.5 rounded-md text-[10px] font-bold bg-amber-500/15 text-amber-400 border border-amber-500/20">Dev {quotaSummary.dedicatedDevCount}</span>
                    <span className="px-2 py-0.5 rounded-md text-[10px] font-bold bg-amber-500/15 text-amber-400 border border-amber-500/20">Test {quotaSummary.dedicatedTestCount}</span>
                  </div>
                </div>
                <div className="flex items-center justify-between pt-1.5 border-t border-indigo-500/15">
                  <span className="text-[10px] font-bold text-indigo-400 uppercase tracking-widest">Available</span>
                  <div className="flex gap-1.5">
                    <span className="px-2 py-0.5 rounded-md text-[10px] font-bold bg-emerald-500/20 text-emerald-300 border border-emerald-500/30">Dev {quotaSummary.dedicatedDevAvailable}</span>
                    <span className="px-2 py-0.5 rounded-md text-[10px] font-bold bg-sky-500/20 text-sky-300 border border-sky-500/30">Test {quotaSummary.dedicatedTestAvailable}</span>
                  </div>
                </div>
              </div>
            </div>

            {/* ── Dev Capacity (Shared + Dedicated) ── */}
            <div className="rounded-xl border border-emerald-500/30 bg-gradient-to-br from-emerald-500/10 to-emerald-500/5 p-3 shadow-sm hover:shadow-lg hover:border-emerald-500/50 transition-all duration-200">
              <div className="flex items-center gap-2 mb-3">
                <div className="p-1 rounded-lg bg-emerald-500/20"><Users className="w-3.5 h-3.5 text-emerald-400" /></div>
                <span className="text-xs font-bold text-app-text-main">Dev Capacity</span>
              </div>
              
              <div className="space-y-3 mb-3">
                <div className="flex items-center justify-between">
                  <span className="text-[10px] font-bold text-emerald-400">Shared Dev</span>
                  <div className="flex items-center gap-2">
                    <button onClick={() => setSharedDevToAdd(v => Math.max(0, v - 1))} className="w-6 h-6 flex items-center justify-center rounded bg-app-bg-muted text-app-text-muted hover:text-emerald-400 border border-app-border-light">-</button>
                    <input value={sharedDevToAdd} onChange={e => setSharedDevToAdd(clampPositiveInt(e.target.value))} className="w-10 h-6 text-center bg-app-bg-card border border-app-border-light rounded text-[11px] font-bold" />
                    <button onClick={() => setSharedDevToAdd(v => v + 1)} className="w-6 h-6 flex items-center justify-center rounded bg-app-bg-muted text-app-text-muted hover:text-emerald-400 border border-app-border-light">+</button>
                  </div>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-[10px] font-bold text-indigo-400">Dedicated Dev</span>
                  <div className="flex items-center gap-2">
                    <button onClick={() => setDedicatedDevToAdd(v => Math.max(0, v - 1))} className="w-6 h-6 flex items-center justify-center rounded bg-app-bg-muted text-app-text-muted hover:text-indigo-400 border border-app-border-light">-</button>
                    <input value={dedicatedDevToAdd} onChange={e => setDedicatedDevToAdd(clampPositiveInt(e.target.value))} className="w-10 h-6 text-center bg-app-bg-card border border-app-border-light rounded text-[11px] font-bold" />
                    <button onClick={() => setDedicatedDevToAdd(v => v + 1)} className="w-6 h-6 flex items-center justify-center rounded bg-app-bg-muted text-app-text-muted hover:text-indigo-400 border border-app-border-light">+</button>
                  </div>
                </div>
              </div>

              <button type="button" 
                onClick={async () => {
                  if (sharedDevToAdd > 0) await increaseQuota('shared', 'dev', sharedDevToAdd);
                  if (dedicatedDevToAdd > 0) await increaseQuota('dedicated', 'dev', dedicatedDevToAdd);
                  setSharedDevToAdd(0); setDedicatedDevToAdd(0);
                }}
                disabled={quotaUpdatingKind === 'shared' || quotaUpdatingKind === 'dedicated' || quotaLoading || (sharedDevToAdd === 0 && dedicatedDevToAdd === 0)}
                className="w-full h-8 rounded-lg bg-gradient-to-r from-emerald-600 to-emerald-500 text-white text-[11px] font-bold hover:from-emerald-700 hover:to-emerald-600 disabled:opacity-50 disabled:cursor-not-allowed transition-all shadow-sm hover:shadow-md flex items-center justify-center gap-1.5">
                {quotaUpdatingKind === 'shared' || quotaUpdatingKind === 'dedicated' ? <RefreshCw className="w-3 h-3 animate-spin" /> : <span>Add Capacity</span>}
              </button>
            </div>

            {/* ── Test Capacity (Shared + Dedicated) ── */}
            <div className="rounded-xl border border-cyan-500/30 bg-gradient-to-br from-cyan-500/10 to-cyan-500/5 p-3 shadow-sm hover:shadow-lg hover:border-cyan-500/50 transition-all duration-200">
              <div className="flex items-center gap-2 mb-3">
                <div className="p-1 rounded-lg bg-cyan-500/20"><Database className="w-3.5 h-3.5 text-cyan-400" /></div>
                <span className="text-xs font-bold text-app-text-main">Test Capacity</span>
              </div>

              <div className="space-y-3 mb-3">
                <div className="flex items-center justify-between">
                  <span className="text-[10px] font-bold text-emerald-400">Shared Test</span>
                  <div className="flex items-center gap-2">
                    <button onClick={() => setSharedTestToAdd(v => Math.max(0, v - 1))} className="w-6 h-6 flex items-center justify-center rounded bg-app-bg-muted text-app-text-muted hover:text-cyan-400 border border-app-border-light">-</button>
                    <input value={sharedTestToAdd} onChange={e => setSharedTestToAdd(clampPositiveInt(e.target.value))} className="w-10 h-6 text-center bg-app-bg-card border border-app-border-light rounded text-[11px] font-bold" />
                    <button onClick={() => setSharedTestToAdd(v => v + 1)} className="w-6 h-6 flex items-center justify-center rounded bg-app-bg-muted text-app-text-muted hover:text-cyan-400 border border-app-border-light">+</button>
                  </div>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-[10px] font-bold text-indigo-400">Dedicated Test</span>
                  <div className="flex items-center gap-2">
                    <button onClick={() => setDedicatedTestToAdd(v => Math.max(0, v - 1))} className="w-6 h-6 flex items-center justify-center rounded bg-app-bg-muted text-app-text-muted hover:text-indigo-400 border border-app-border-light">-</button>
                    <input value={dedicatedTestToAdd} onChange={e => setDedicatedTestToAdd(clampPositiveInt(e.target.value))} className="w-10 h-6 text-center bg-app-bg-card border border-app-border-light rounded text-[11px] font-bold" />
                    <button onClick={() => setDedicatedTestToAdd(v => v + 1)} className="w-6 h-6 flex items-center justify-center rounded bg-app-bg-muted text-app-text-muted hover:text-indigo-400 border border-app-border-light">+</button>
                  </div>
                </div>
              </div>

              <button type="button" 
                onClick={async () => {
                  if (sharedTestToAdd > 0) await increaseQuota('shared', 'test', sharedTestToAdd);
                  if (dedicatedTestToAdd > 0) await increaseQuota('dedicated', 'test', dedicatedTestToAdd);
                  setSharedTestToAdd(0); setDedicatedTestToAdd(0);
                }}
                disabled={quotaUpdatingKind === 'shared' || quotaUpdatingKind === 'dedicated' || quotaLoading || (sharedTestToAdd === 0 && dedicatedTestToAdd === 0)}
                className="w-full h-8 rounded-lg bg-gradient-to-r from-cyan-600 to-cyan-500 text-white text-[11px] font-bold hover:from-cyan-700 hover:to-cyan-600 disabled:opacity-50 disabled:cursor-not-allowed transition-all shadow-sm hover:shadow-md flex items-center justify-center gap-1.5">
                {quotaUpdatingKind === 'shared' || quotaUpdatingKind === 'dedicated' ? <RefreshCw className="w-3 h-3 animate-spin" /> : <span>Add Capacity</span>}
              </button>
            </div>
          </div>
          ) : (
            <div className="p-2 rounded-lg bg-app-bg-muted/50 border border-app-border-light">
              <p className="text-xs text-app-text-muted">Capacity not available.</p>
            </div>
          )}
      </div>

      {/* Filter Buttons */}
      <div className="flex-shrink-0 px-6 py-2 border-b border-app-border-light bg-app-bg-card/30">
        <div className="flex items-center space-x-2">
          <Filter className="w-4 h-4 text-app-text-muted" />
          <span className="text-sm font-medium text-app-text-muted mr-2">Filter:</span>
          <button
            onClick={() => setFilter('all')}
            className={`px-3 py-1 text-sm font-medium rounded-lg transition-colors ${
              filter === 'all'
                ? 'bg-app-primary text-white'
                : 'bg-app-text-label/20 text-app-text-main hover:bg-app-text-label/30'
            }`}
          >
            All ({totalAgents})
          </button>
          <button
            onClick={() => setFilter('shared')}
            className={`px-3 py-1 text-sm font-medium rounded-lg transition-colors ${
              filter === 'shared'
                ? 'bg-app-primary text-white'
                : 'bg-app-text-label/20 text-app-text-main hover:bg-app-text-label/30'
            }`}
          >
            Shared ({sharedAgents.length})
          </button>
          <button
            onClick={() => setFilter('dedicated')}
            className={`px-3 py-1 text-sm font-medium rounded-lg transition-colors ${
              filter === 'dedicated'
                ? 'bg-app-primary text-white'
                : 'bg-app-text-label/20 text-app-text-main hover:bg-app-text-label/30'
            }`}
          >
            Dedicated ({dedicatedAgents.length})
          </button>
        </div>
      </div>

      {/* Main Content Area */}
      <div className="flex-1 flex min-h-0">
        {/* Agents List - Scrollable */}
        <div className="flex-1 overflow-y-auto overflow-x-hidden p-6">
          {/* Loading State */}
          {loading && filteredAgents.length === 0 && (
            <div className="flex items-center justify-center h-full">
              <div className="flex flex-col items-center">
                <RefreshCw className="w-8 h-8 text-app-primary animate-spin mb-4" />
                <p className="text-app-text-muted">Loading agents...</p>
              </div>
            </div>
          )}

          {/* Error State */}
          {error && (
            <div className="mb-6 p-4 bg-app-status-error/10 border border-app-status-error/30 rounded-lg">
              <p className="text-red-400 flex items-center">
                <AlertCircle className="w-5 h-5 mr-2" />
                {error}
              </p>
            </div>
          )}

          {/* Agents List */}
          {!loading && !error && (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {filteredAgents.length > 0 ? (
                filteredAgents.map((agent) => {
                  const isSystem = agent.agentType === 'system';
                  const isShared = agent.agentType === 'shared';
                  const isDedicated = agent.agentType === 'dedicated';
                  const isGitManager = agent.id === 'agent_03';
                  const isMasterAgent = agent.id === 'agent_04';
                  const isTestAgent = agent.sub_type === 'test';
                  const isDeployAgent = agent.id === 'deploy_agent';
                  const isRunning = agent.status === 'running';
                  const isCompleted = agent.status === 'completed';
                  const isError = agent.status === 'error';
                  const isIdle = agent.status === 'idle';

                  // Determine agent config based on ID
                  let accentColor = 'from-app-text-light to-app-text-muted';
                  let statusColor = 'gray';
                  let useLogo = false;
                  let logoSrc = null;

                  if (isGitManager) {
                    accentColor = 'from-app-primary to-app-primary';
                    statusColor = 'indigo';
                  } else if (isMasterAgent) {
                    accentColor = 'from-fuchsia-500 to-app-status-error';
                    statusColor = 'fuchsia';
                    useLogo = true;
                    logoSrc = agent.logo || masterLogo;
                  } else if (isTestAgent) {
                    accentColor = 'from-app-status-warning to-orange-500';
                    statusColor = 'amber';
                    useLogo = true;
                    logoSrc = agent.logo || kaktoxLogo;
                  } else if (isDeployAgent) {
                    accentColor = 'from-violet-500 to-purple-600';
                    statusColor = 'violet';
                    useLogo = true;
                    logoSrc = cloudIcon;
                  } else if (isShared || isDedicated) {
                    accentColor = isShared ? 'from-emerald-400 to-app-status-success' : 'from-app-primary to-app-primary';
                    statusColor = isShared ? 'emerald' : 'blue';
                    useLogo = true;
                    logoSrc = nModLogo;
                  }

                  const finalStatusColor = isRunning ? statusColor : isCompleted ? 'emerald' : isError ? 'red' : 'gray';

                  return (
                    <div
                      key={agent.id}
                      className="bg-app-bg-card rounded-xl shadow border border-app-border-light p-4 flex flex-col relative overflow-hidden group hover:shadow-lg transition-shadow"
                    >
                      {/* Top accent bar */}
                      <div className={`absolute top-0 left-0 right-0 h-1 bg-gradient-to-r ${accentColor}`}></div>

                    <div className="flex items-start justify-between mb-4">
                      <div className="flex items-center gap-3">
                        {/* Agent Icon/Logo */}
                        <div className={`w-10 h-10 rounded-xl ${useLogo ? 'bg-app-bg-page border border-app-border' : `bg-gradient-to-br ${
                          isGitManager ? 'from-app-primary to-app-primary' :
                          isMasterAgent ? 'from-fuchsia-500 to-app-status-error' :
                          isTestAgent ? 'from-app-status-warning to-orange-600' :
                          isDeployAgent ? 'from-violet-500 to-purple-600' :
                          isShared ? 'from-emerald-400 to-app-status-success' :
                          'from-app-primary to-app-primary'
                        }`} flex items-center justify-center shadow-lg ${
                          isGitManager ? 'shadow-app-primary-ring' :
                          isMasterAgent ? 'shadow-app-bg-hover' :
                          isTestAgent ? 'shadow-app-bg-hover' :
                          isDeployAgent ? 'shadow-app-bg-hover' :
                          isShared ? 'shadow-emerald-200' :
                          'shadow-app-primary-ring'
                        } ${useLogo ? 'p-1.5' : ''}`}>
                          {useLogo && logoSrc ? (
                            <img src={logoSrc} alt={agent.name || getNeutralAgentName(agent)} className="w-full h-full object-contain" />
                          ) : isGitManager ? (
                            <GitBranch className="w-5 h-5 text-white" />
                          ) : isMasterAgent ? (
                            <Bot className="w-5 h-5 text-white" />
                          ) : isTestAgent ? (
                            <Activity className="w-5 h-5 text-white" />
                          ) : isDeployAgent ? (
                            <Globe className="w-5 h-5 text-white" />
                          ) : (
                            getStatusIcon(agent.status)
                          )}
                        </div>
                        <div>
                          <div className="flex items-center gap-2">
                            <h4 className="text-sm font-bold text-app-text-main">
                              {agent.name || getNeutralAgentName(agent)}
                            </h4>
                            {(isShared || isDedicated) && (
                              <span className={`px-2 py-0.5 text-[9px] font-bold rounded-full uppercase tracking-wider ${
                                isShared
                                  ? 'bg-app-status-successBg text-app-status-success border border-emerald-200'
                                  : 'bg-app-primary-light text-app-primary-hover border border-app-primary-ring'
                              }`}>
                                {isShared ? 'Shared' : 'Dedicated'}
                              </span>
                            )}
                          </div>
                          <p className="text-[10px] text-app-text-light uppercase tracking-wider font-semibold">{getNeutralAgentLabel(agent)}</p>
                        </div>
                      </div>
                      <div className="flex items-center gap-2">
                        <div className="flex items-center gap-1.5">
                          {isRunning && (
                            <span className="relative flex h-2.5 w-2.5">
                              <span className={`animate-ping absolute inline-flex h-full w-full rounded-full bg-${finalStatusColor}-400 opacity-75`}></span>
                              <span className={`relative inline-flex rounded-full h-2.5 w-2.5 bg-${finalStatusColor}-500`}></span>
                            </span>
                          )}
                          <span className={`text-[10px] font-bold text-${finalStatusColor}-${isIdle ? '500' : '600'}`}>
                            {agent.status?.toUpperCase() || 'IDLE'}
                          </span>
                        </div>
                        {/* Delete Button - Only for dedicated agents */}
                        {isDedicated && (
                          <button
                            onClick={() => handleDeleteAgent(agent.id)}
                            disabled={deletingId === agent.id}
                            className="p-1.5 rounded-lg bg-app-bg-card/50 text-red-400 hover:text-red-300 hover:bg-app-status-error/10 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
                            title="Delete dedicated agent"
                          >
                            {deletingId === agent.id ? (
                              <RefreshCw className="w-4 h-4 animate-spin" />
                            ) : (
                              <Trash2 className="w-4 h-4" />
                            )}
                          </button>
                        )}
                      </div>
                    </div>

                      {/* Progress indicator if running */}
                      {isRunning && agent.progress > 0 && (
                        <div className="mb-3">
                          <div className="flex justify-between text-[10px] text-app-text-light mb-1">
                            <span className="truncate max-w-[180px]">{agent.progress_message || 'Processing...'}</span>
                            <span className={`font-bold text-${statusColor}-600`}>{agent.progress}%</span>
                          </div>
                          <div className="w-full bg-app-bg-muted rounded-full h-1.5 overflow-hidden">
                            <div className={`bg-gradient-to-r ${accentColor} h-1.5 rounded-full transition-all duration-1000 ease-out`} style={{ width: `${agent.progress}%` }}></div>
                          </div>
                        </div>
                      )}

                      {/* Additional Details */}
                      {agent.progress_message && !isRunning && (
                        <div className="mt-3 pt-3 border-t border-app-border-light/30">
                          <p className="text-sm text-app-text-muted flex items-center">
                            <Activity className="w-3 h-3 mr-2" />
                            {agent.progress_message}
                          </p>
                        </div>
                      )}

                      {/* Last Run Info */}
                      {agent.last_run && (
                        <div className="mt-2 text-xs text-app-text-muted flex items-center">
                          <Clock className="w-3 h-3 mr-1" />
                          Last run: {new Date(agent.last_run).toLocaleString()}
                        </div>
                      )}
                    </div>
                  );
                })
              ) : (
                <div className="flex flex-col items-center justify-center h-full text-app-text-muted">
                  <Users className="w-16 h-16 mb-4 opacity-30" />
                  <p className="text-lg">No agents available</p>
                  <p className="text-sm mt-1">
                    {filter === 'shared' && 'No shared agents found'}
                    {filter === 'dedicated' && 'No dedicated agents found'}
                    {filter === 'all' && 'Agents will appear here once configured'}
                  </p>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Summary Stats Sidebar */}
        {filteredAgents.length > 0 && (
          <div className="w-64 flex-shrink-0 border-l border-app-border-light p-4 overflow-y-auto bg-app-bg-card/30">
            <h3 className="font-semibold mb-4 text-sm text-app-text-muted uppercase tracking-wider">
              Summary
            </h3>
            <div className="space-y-3">
              <div className="p-3 bg-app-text-label/10 rounded-lg border border-app-border-light/30">
                <p className="text-2xl font-bold">{filteredAgents.length}</p>
                <p className="text-xs text-app-text-muted">Showing</p>
              </div>
              <div className="p-3 bg-cyan-500/10 rounded-lg border border-cyan-500/30">
                <p className="text-2xl font-bold text-cyan-400">
                  {filteredAgents.filter((a) => a.status === 'running').length}
                </p>
                <p className="text-xs text-cyan-400/70">Running</p>
              </div>
              <div className="p-3 bg-app-primary/10 rounded-lg border border-app-primary/30">
                <p className="text-2xl font-bold text-blue-400">
                  {filteredAgents.filter((a) => a.status === 'idle').length}
                </p>
                <p className="text-xs text-blue-400/70">Idle</p>
              </div>
              <div className="p-3 bg-app-status-error/10 rounded-lg border border-app-status-error/30">
                <p className="text-2xl font-bold text-red-400">
                  {filteredAgents.filter((a) => a.status === 'error' || a.status === 'failed').length}
                </p>
                <p className="text-xs text-red-400/70">Error</p>
              </div>
              <div className="p-3 bg-purple-500/10 rounded-lg border border-purple-500/30">
                <p className="text-2xl font-bold text-purple-400">
                  {filteredAgents.filter((a) => a.agentType === 'shared').length}
                </p>
                <p className="text-xs text-purple-400/70">Shared</p>
              </div>
              <div className="p-3 bg-orange-500/10 rounded-lg border border-orange-500/30">
                <p className="text-2xl font-bold text-orange-400">
                  {filteredAgents.filter((a) => a.agentType === 'dedicated').length}
                </p>
                <p className="text-xs text-orange-400/70">Dedicated</p>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
