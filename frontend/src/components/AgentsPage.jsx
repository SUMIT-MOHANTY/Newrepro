import React, { useState, useEffect, useMemo } from 'react';
import { Users, Trash2, Activity, Clock, CheckCircle, AlertCircle, RefreshCw, Filter, Server, Database, GitBranch, Bot, Globe, Plus, Upload } from 'lucide-react';
import { API_ENDPOINTS } from '../config';
import { getNeutralAgentName, getNeutralAgentLabel } from '../utils/agentNames';
import kaktoxLogo from '../assets/Kaktox.png';
import nModLogo from '../assets/N-Mod-icon.png';
import masterLogo from '../assets/logo1.png';
import cloudIcon from '../assets/cloud-icon.png';

/**
 * AgentsPage – Full‑screen view of all agents for the current organization.
 * It lists system and custom agents and allows creation/deletion of custom agents globally.
 */
export default function AgentsPage({ projects = [] }) {
  const [sharedAgents, setSharedAgents] = useState([]);        // Development custom agents
  const [dedicatedAgents, setDedicatedAgents] = useState([]);   // Testing custom agents
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [deletingId, setDeletingId] = useState(null);
  const [filter, setFilter] = useState('all');
  const [quota, setQuota] = useState(null);
  const [quotaError, setQuotaError] = useState('');
  const [quotaLoading, setQuotaLoading] = useState(false);
  const [sharedDevToAdd, setSharedDevToAdd] = useState(0);
  const [dedicatedDevToAdd, setDedicatedDevToAdd] = useState(0);
  const [quotaUpdatingKind, setQuotaUpdatingKind] = useState('');

  const [showAddAgentModal, setShowAddAgentModal] = useState(false);
  const [newAgentName, setNewAgentName] = useState('');
  const [skillsContent, setSkillsContent] = useState('');
  const [skillsFileName, setSkillsFileName] = useState('');
  const [newAgentFace, setNewAgentFace] = useState('');
  const [newAgentTags, setNewAgentTags] = useState('');
  const [addingAgent, setAddingAgent] = useState(false);
  const [addAgentError, setAddAgentError] = useState('');

  // Handle markdown file selection and parse content inside the browser
  const handleFileChange = (e) => {
    const file = e.target.files[0];

    if (file) {
      if (!file.name.endsWith('.md')) {
        setAddAgentError('Please upload a markdown (.md) file.');
        return;
      }
      setSkillsFileName(file.name);
      setAddAgentError('');

      const reader = new FileReader();
      reader.onload = (event) => {
        setSkillsContent(event.target.result);
      };
      reader.onerror = () => {
        setAddAgentError('Failed to read the file.');
      };
      reader.readAsText(file);
    }
  };

  // Handle agent icon (face) file selection and convert to Base64
  const handleFaceChange = (e) => {
    const file = e.target.files[0];
    if (file) {
      if (!file.type.startsWith('image/')) {
        setAddAgentError('Please upload an image file for the agent icon.');
        return;
      }
      const reader = new FileReader();
      reader.onload = (event) => {
        setNewAgentFace(event.target.result);
      };
      reader.onerror = () => {
        setAddAgentError('Failed to read the image file.');
      };
      reader.readAsDataURL(file);
    }
  };

  // Submit custom agent details to backend 
  const handleAddAgentSubmit = async (e) => {
    e.preventDefault();
    if (!newAgentName.trim() || !skillsContent) return;
    setAddingAgent(true);
    setAddAgentError('');
    const token = localStorage.getItem('token');
    try {
      const res = await fetch(`${API_ENDPOINTS.AGENTS}/skills/add`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({
          name: newAgentName.trim(),
          skills_content: skillsContent,
          face: newAgentFace || null,
          tags: newAgentTags.trim() || null
        })
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || 'Failed to create custom agent');
      }

      // Reset form and modal
      setShowAddAgentModal(false);
      setNewAgentName('');
      setSkillsContent('');
      setSkillsFileName('');
      setNewAgentFace('');
      setNewAgentTags('');

      // Refresh lists
      await fetchAgents();
      await fetchQuota();
    } catch (err) {
      setAddAgentError(err.message || 'Failed to add custom agent');
    } finally {
      setAddingAgent(false);
    }
  };

  const fetchAgents = async () => {
    setLoading(true);
    setError(null);
    const token = localStorage.getItem('token');
    try {
      const headers = { Authorization: `Bearer ${token}` };
      const parse = (data) => Array.isArray(data) ? data : (data?.agents || data?.results || data?.data || []);

      const url = new URL(API_ENDPOINTS.AGENTS);
      url.searchParams.set('include_defaults', 'false');

      const res = await fetch(url.toString(), { headers });
      const data = await res.json();
      const customList = parse(data);

      // Classify custom agents based on specialization:
      // 'Testing' specialists mapped to dedicatedAgents, others to sharedAgents
      const devAgents = customList
        .filter(a => a.specialization !== 'Testing')
        .map(a => ({ ...a, agentType: 'shared' }));
      const testAgents = customList
        .filter(a => a.specialization === 'Testing')
        .map(a => ({ ...a, agentType: 'dedicated' }));

      setSharedAgents(devAgents);
      setDedicatedAgents(testAgents);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchAgents();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

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
      const res = await fetch(deleteUrl.toString(), {
        method: 'DELETE',
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) throw new Error('Failed to delete agent');

      // Remove from states and refetch
      setSharedAgents((prev) => prev.filter((a) => a.id !== agentId));
      setDedicatedAgents((prev) => prev.filter((a) => a.id !== agentId));
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
    const sharedUsed = Number(quota.shared_used ?? 0);
    const sharedAvailable = Math.max(0, sharedQuota - sharedUsed);

    const dedicatedQuota = Number(quota.dedicated_quota ?? 0);
    const dedicatedUsed = Number(quota.dedicated_used ?? 0);
    const dedicatedAvailable = Math.max(0, dedicatedQuota - dedicatedUsed);

    return {
      sharedQuota,
      sharedUsed,
      sharedAvailable,
      dedicatedQuota,
      dedicatedUsed,
      dedicatedAvailable,
    };
  }, [quota]);

  return (
    <div className="h-full w-full flex flex-col bg-app-bg-page text-app-text-main">
      {/* Header */}
      <div className="flex-shrink-0 flex items-center justify-between px-6 py-4 border-b border-app-border-light bg-app-bg-card/50">
        <h1 className="text-2xl font-bold flex items-center">
          <Users className="w-6 h-6 mr-2 animate-pulse" /> Agents
        </h1>
        <div className="flex items-center space-x-3">
          <span className="text-sm text-app-text-muted">
            {totalAgents} agent{totalAgents !== 1 ? 's' : ''} ({defaultAgents.length} system, {sharedAgents.length} dev, {dedicatedAgents.length} test)
          </span>
          <button
            onClick={async () => {
              await fetchAgents();
              await fetchQuota();
            }}
            disabled={loading}
            className="flex items-center px-4 py-2 text-sm font-medium text-app-text-main bg-app-text-label/20 rounded-lg hover:bg-app-text-label/30 transition-colors disabled:opacity-50"
          >
            <RefreshCw className={`w-4 h-4 mr-2 ${loading ? 'animate-spin' : ''}`} />
            Refresh
          </button>
        </div>
      </div>

      {/* Organization Capacity */}
      <div className="flex-shrink-0 px-4 md:px-6 py-4 border-b border-app-border-light bg-gradient-to-br from-app-bg-card/50 to-app-bg-card/30">
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
          <div>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
              {/* ── Left Card: Shared Agent Capacity ── */}
              <div className="rounded-xl border border-emerald-500/25 bg-gradient-to-br from-emerald-500/10 to-teal-500/5 p-4 shadow-sm hover:shadow-lg hover:border-emerald-500/40 transition-all duration-300">
                <div className="flex items-center justify-between mb-3">
                  <div className="flex items-center gap-2">
                    <div className="p-1.5 rounded-lg bg-emerald-500/20 text-emerald-400">
                      <Bot className="w-4 h-4" />
                    </div>
                    <span className="text-sm font-bold text-app-text-main">Shared Agent Capacity</span>
                  </div>
                  <span className="text-xs text-app-text-muted font-semibold">{quotaSummary.sharedUsed}/{quotaSummary.sharedQuota} used</span>
                </div>
                <div className="relative h-2 bg-app-bg-muted/60 rounded-full overflow-hidden mb-4">
                  <div className="absolute inset-y-0 left-0 bg-gradient-to-r from-emerald-500 to-teal-500 rounded-full transition-all duration-500"
                    style={{ width: `${quotaSummary.sharedQuota > 0 ? Math.min(100, (quotaSummary.sharedUsed / quotaSummary.sharedQuota) * 100) : 0}%` }} />
                </div>
                <div className="space-y-2">
                  <div className="flex items-center justify-between text-xs">
                    <span className="text-app-text-muted">Total Shared Quota</span>
                    <span className="px-2 py-0.5 rounded-md font-bold bg-emerald-500/15 text-emerald-400 border border-emerald-500/20">
                      {quotaSummary.sharedQuota} Slots
                    </span>
                  </div>
                  <div className="flex items-center justify-between text-xs">
                    <span className="text-app-text-muted">Available Shared Slots</span>
                    <span className="px-2 py-0.5 rounded-md font-bold bg-teal-500/20 text-teal-300 border border-teal-500/30">
                      {quotaSummary.sharedAvailable} Slots
                    </span>
                  </div>
                </div>
              </div>

              {/* ── Middle Card: Dedicated Agent Capacity ── */}
              <div className="rounded-xl border border-purple-500/25 bg-gradient-to-br from-purple-500/10 to-pink-500/5 p-4 shadow-sm hover:shadow-lg hover:border-purple-500/40 transition-all duration-300">
                <div className="flex items-center justify-between mb-3">
                  <div className="flex items-center gap-2">
                    <div className="p-1.5 rounded-lg bg-purple-500/20 text-purple-400">
                      <Activity className="w-4 h-4" />
                    </div>
                    <span className="text-sm font-bold text-app-text-main">Dedicated Agent Capacity</span>
                  </div>
                  <span className="text-xs text-app-text-muted font-semibold">{quotaSummary.dedicatedUsed}/{quotaSummary.dedicatedQuota} used</span>
                </div>
                <div className="relative h-2 bg-app-bg-muted/60 rounded-full overflow-hidden mb-4">
                  <div className="absolute inset-y-0 left-0 bg-gradient-to-r from-purple-500 to-pink-500 rounded-full transition-all duration-500"
                    style={{ width: `${quotaSummary.dedicatedQuota > 0 ? Math.min(100, (quotaSummary.dedicatedUsed / quotaSummary.dedicatedQuota) * 100) : 0}%` }} />
                </div>
                <div className="space-y-2">
                  <div className="flex items-center justify-between text-xs">
                    <span className="text-app-text-muted">Total Dedicated Quota</span>
                    <span className="px-2 py-0.5 rounded-md font-bold bg-purple-500/15 text-purple-400 border border-purple-500/20">
                      {quotaSummary.dedicatedQuota} Slots
                    </span>
                  </div>
                  <div className="flex items-center justify-between text-xs">
                    <span className="text-app-text-muted">Available Dedicated Slots</span>
                    <span className="px-2 py-0.5 rounded-md font-bold bg-pink-500/20 text-pink-300 border border-pink-500/30">
                      {quotaSummary.dedicatedAvailable} Slots
                    </span>
                  </div>
                </div>
              </div>

              {/* ── Right Card: Agent Capacity Adjuster ── */}
              <div className="rounded-xl border border-blue-500/25 bg-gradient-to-br from-blue-500/10 to-indigo-500/5 p-4 shadow-sm hover:shadow-lg hover:border-blue-500/40 transition-all duration-300 flex flex-col justify-between">
                <div className="space-y-3">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <div className="p-1.5 rounded-lg bg-blue-500/20 text-blue-400">
                        <Server className="w-4 h-4" />
                      </div>
                      <span className="text-sm font-bold text-app-text-main">Agents Capacity</span>
                    </div>
                  </div>

                  {/* Shared Adjuster */}
                  <div className="flex items-center gap-2 py-1 border-t border-app-border-light/30">
                    <span className="text-[11px] font-semibold text-app-text-muted">Add Shared:</span>
                    <div className="flex items-center gap-1.5 ml-auto">
                      <button
                        type="button"
                        onClick={() => setSharedDevToAdd(v => Math.max(0, v - 1))}
                        className="w-6 h-6 flex items-center justify-center rounded bg-app-bg-muted text-app-text-muted hover:text-emerald-400 border border-app-border-light text-xs font-bold transition-colors"
                      >
                        -
                      </button>
                      <input
                        value={sharedDevToAdd}
                        onChange={e => setSharedDevToAdd(clampPositiveInt(e.target.value))}
                        className="w-10 h-6 text-center bg-app-bg-card border border-app-border-light rounded text-xs font-bold text-app-text-main focus:outline-none focus:border-emerald-500"
                      />
                      <button
                        type="button"
                        onClick={() => setSharedDevToAdd(v => v + 1)}
                        className="w-6 h-6 flex items-center justify-center rounded bg-app-bg-muted text-app-text-muted hover:text-emerald-400 border border-app-border-light text-xs font-bold transition-colors"
                      >
                        +
                      </button>
                    </div>
                  </div>

                  {/* Dedicated Adjuster */}
                  <div className="flex items-center gap-2 py-1 border-t border-app-border-light/30">
                    <span className="text-[11px] font-semibold text-app-text-muted">Add Dedicated:</span>
                    <div className="flex items-center gap-1.5 ml-auto">
                      <button
                        type="button"
                        onClick={() => setDedicatedDevToAdd(v => Math.max(0, v - 1))}
                        className="w-6 h-6 flex items-center justify-center rounded bg-app-bg-muted text-app-text-muted hover:text-purple-400 border border-app-border-light text-xs font-bold transition-colors"
                      >
                        -
                      </button>
                      <input
                        value={dedicatedDevToAdd}
                        onChange={e => setDedicatedDevToAdd(clampPositiveInt(e.target.value))}
                        className="w-10 h-6 text-center bg-app-bg-card border border-app-border-light rounded text-xs font-bold text-app-text-main focus:outline-none focus:border-purple-500"
                      />
                      <button
                        type="button"
                        onClick={() => setDedicatedDevToAdd(v => v + 1)}
                        className="w-6 h-6 flex items-center justify-center rounded bg-app-bg-muted text-app-text-muted hover:text-purple-400 border border-app-border-light text-xs font-bold transition-colors"
                      >
                        +
                      </button>
                    </div>
                  </div>
                </div>
              </div>
            </div>

            {/* Apply quota changes button */}
            {(sharedDevToAdd > 0 || dedicatedDevToAdd > 0) && (
              <div className="mt-4 flex justify-end animate-in fade-in slide-in-from-top-2 duration-200">
                <button
                  type="button"
                  onClick={async () => {
                    if (sharedDevToAdd > 0) await increaseQuota('shared', 'dev', sharedDevToAdd);
                    if (dedicatedDevToAdd > 0) await increaseQuota('dedicated', 'dev', dedicatedDevToAdd);
                    setSharedDevToAdd(0);
                    setDedicatedDevToAdd(0);
                  }}
                  disabled={quotaUpdatingKind === 'shared' || quotaUpdatingKind === 'dedicated' || quotaLoading}
                  className="px-6 py-2 rounded-lg bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-700 hover:to-indigo-700 text-white text-xs font-bold transition-all shadow-md hover:shadow-lg flex items-center gap-2"
                >
                  {quotaUpdatingKind ? (
                    <>
                      <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                      <span>Updating Quota...</span>
                    </>
                  ) : (
                    <>
                      <CheckCircle className="w-3.5 h-3.5" />
                      <span>Apply Licensed Capacity Changes (+{sharedDevToAdd + dedicatedDevToAdd} Agents)</span>
                    </>
                  )}
                </button>
              </div>
            )}
          </div>
        ) : (
          <div className="p-2 rounded-lg bg-app-bg-muted/50 border border-app-border-light">
            <p className="text-xs text-app-text-muted">Capacity not available.</p>
          </div>
        )}
      </div>

      {/* Filter Buttons */}
      <div className="flex-shrink-0 px-6 py-2 border-b border-app-border-light bg-app-bg-card/30">
        <div className="flex items-center justify-between">
          <div className="flex items-center space-x-2">
            <Filter className="w-4 h-4 text-app-text-muted" />
            <span className="text-sm font-medium text-app-text-muted mr-2">Filter:</span>
            <button
              onClick={() => setFilter('all')}
              className={`px-3 py-1 text-sm font-medium rounded-lg transition-colors ${filter === 'all'
                ? 'bg-app-primary text-white'
                : 'bg-app-text-label/20 text-app-text-main hover:bg-app-text-label/30'
                }`}
            >
              All ({totalAgents})
            </button>
            <button
              onClick={() => setFilter('shared')}
              className={`px-3 py-1 text-sm font-medium rounded-lg transition-colors ${filter === 'shared'
                ? 'bg-app-primary text-white'
                : 'bg-app-text-label/20 text-app-text-main hover:bg-app-text-label/30'
                }`}
            >
              Development ({sharedAgents.length})
            </button>
            <button
              onClick={() => setFilter('dedicated')}
              className={`px-3 py-1 text-sm font-medium rounded-lg transition-colors ${filter === 'dedicated'
                ? 'bg-app-primary text-white'
                : 'bg-app-text-label/20 text-app-text-main hover:bg-app-text-label/30'
                }`}
            >
              Testing ({dedicatedAgents.length})
            </button>
          </div>

          <button
            onClick={() => setShowAddAgentModal(true)}
            className="flex items-center gap-1.5 px-3 py-1 text-sm font-semibold rounded-lg bg-gradient-to-r from-app-primary to-blue-600 hover:from-blue-600 hover:to-blue-700 text-white shadow-sm transition-all duration-200"
          >
            <Plus className="w-4 h-4" />
            <span>Add Agent</span>
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
                  const isDeployAgent = agent.id === 'deploy_agent';
                  const isTestAgent = agent.sub_type === 'test' || agent.specialization === 'Testing';
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
                  } else if (isTestAgent && isSystem) {
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
                    accentColor = isShared ? 'from-emerald-400 to-teal-500' : 'from-purple-400 to-pink-500';
                    statusColor = isShared ? 'emerald' : 'purple';
                    useLogo = true;
                    logoSrc = agent.face || agent.logo || nModLogo;
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
                          <div className={`w-10 h-10 rounded-xl ${useLogo ? 'bg-app-bg-page border border-app-border' : `bg-gradient-to-br ${isGitManager ? 'from-app-primary to-app-primary' :
                            isMasterAgent ? 'from-fuchsia-500 to-app-status-error' :
                              isTestAgent ? 'from-app-status-warning to-orange-600' :
                                isDeployAgent ? 'from-violet-500 to-purple-600' :
                                  isShared ? 'from-emerald-400 to-app-status-success' :
                                    'from-app-primary to-app-primary'
                            }`} flex items-center justify-center shadow-lg ${isGitManager ? 'shadow-app-primary-ring' :
                              isMasterAgent ? 'shadow-app-bg-hover' :
                                isTestAgent ? 'shadow-app-bg-hover' :
                                  isDeployAgent ? 'shadow-app-bg-hover' :
                                    isShared ? 'shadow-emerald-200' :
                                      'shadow-app-primary-ring'
                            } ${useLogo && !agent.face ? 'p-1.5' : ''}`}>
                            {useLogo && logoSrc ? (
                              <img src={logoSrc} alt={agent.name || getNeutralAgentName(agent)} className={`w-full h-full ${agent.face ? 'object-cover rounded-lg' : 'object-contain'}`} />
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
                              {agent.specialization && (
                                <span className={`px-2 py-0.5 text-[9px] font-bold rounded-full uppercase tracking-wider ${
                                  agent.specialization === 'Testing'
                                    ? 'bg-purple-500/10 text-purple-400 border border-purple-500/20'
                                    : 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20'
                                }`}>
                                  {agent.specialization}
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
                          {/* Delete Button - Available for all custom agents */}
                          {(isShared || isDedicated) && (
                            <button
                              onClick={() => handleDeleteAgent(agent.id)}
                              disabled={deletingId === agent.id}
                              className="p-1.5 rounded-lg bg-app-bg-card/50 text-red-400 hover:text-red-300 hover:bg-app-status-error/10 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
                              title="Delete custom agent"
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

                      {/* Skills Summary for Custom Agents */}
                      {agent.skills_summary && (
                        <div className="mt-3 p-2.5 rounded-lg bg-app-bg-muted/50 border border-app-border-light/40 flex-1 flex flex-col justify-between">
                          <div>
                            <p className="text-xs font-semibold text-app-text-muted mb-1 flex items-center gap-1">
                              <Bot className="w-3.5 h-3.5 text-app-primary" />
                              AI Skills Summary
                            </p>
                            <p className="text-xs text-app-text-main leading-relaxed italic mb-2">
                              "{agent.skills_summary}"
                            </p>
                          </div>

                          {/* Skills Tags Rendering */}
                          {agent.skills_tags && Array.isArray(agent.skills_tags) && agent.skills_tags.length > 0 && (
                            <div className="mt-2 flex flex-wrap gap-1">
                              {agent.skills_tags.map((tag, idx) => (
                                <span
                                  key={idx}
                                  className="px-1.5 py-0.5 rounded text-[9px] font-semibold bg-app-bg-page text-app-text-muted border border-app-border-light"
                                >
                                  {tag}
                                </span>
                              ))}
                            </div>
                          )}
                        </div>
                      )}

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
                          Last run: {new Date(agent.last_run).toLocaleString('en-IN')}
                        </div>
                      )}
                    </div>
                  );
                })
              ) : (
                <div className="col-span-full flex flex-col items-center justify-center py-20 text-app-text-muted">
                  <Users className="w-16 h-16 mb-4 opacity-30 animate-bounce" />
                  <p className="text-lg font-bold">No agents available</p>
                  <p className="text-sm mt-1 max-w-sm text-center">
                    {filter === 'shared' && 'No Development custom agents found'}
                    {filter === 'dedicated' && 'No Testing custom agents found'}
                    {filter === 'all' && 'Custom agents will appear here once configured and uploaded'}
                  </p>
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Add Agent Modal */}
      {showAddAgentModal && (
        <div className="fixed inset-0 z-[300] flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm">
          <div className="relative w-full max-w-md bg-app-bg-card border border-app-border rounded-xl shadow-2xl overflow-hidden flex flex-col max-h-[85vh] animate-in fade-in zoom-in duration-200">
            <div className="absolute top-0 left-0 right-0 h-1 bg-gradient-to-r from-app-primary to-blue-600"></div>
            
            {/* Header */}
            <div className="p-6 pb-4 flex-shrink-0">
              <h3 className="text-lg font-bold text-app-text-main flex items-center gap-2 mb-1">
                <Bot className="w-5 h-5 text-app-primary" />
                Add Custom Agent
              </h3>
              <p className="text-xs text-app-text-muted">
                Create a custom dynamic agent by providing their name and uploading their skills file.
              </p>
            </div>

            {/* Form */}
            <form onSubmit={handleAddAgentSubmit} className="flex-1 flex flex-col min-h-0">
              {/* Scrollable Fields area */}
              <div className="flex-1 overflow-y-auto px-6 pb-4 space-y-4 scrollbar-thin scrollbar-thumb-app-border">
                <div>
                  <label className="block text-xs font-bold text-app-text-muted uppercase tracking-wider mb-1.5">
                    Agent Name
                  </label>
                  <input
                    type="text"
                    value={newAgentName}
                    onChange={(e) => setNewAgentName(e.target.value)}
                    placeholder="e.g. Frontend Architect, QA Specialist"
                    className="w-full px-3 py-2 bg-app-bg-muted/50 border border-app-border-light rounded-lg text-sm text-app-text-main focus:outline-none focus:border-app-primary placeholder:text-app-text-muted/60 transition-colors"
                    disabled={addingAgent}
                  />
                </div>

                <div>
                  <label className="block text-xs font-bold text-app-text-muted uppercase tracking-wider mb-1.5">
                    Agent Icon / Avatar
                  </label>
                  <div className="flex items-center gap-3">
                    {newAgentFace ? (
                      <div className="relative w-12 h-12 rounded-lg border border-app-border bg-app-bg-muted overflow-hidden shrink-0 group">
                        <img src={newAgentFace} alt="Agent icon preview" className="w-full h-full object-cover" />
                        <button
                          type="button"
                          onClick={() => setNewAgentFace('')}
                          className="absolute inset-0 bg-black/60 opacity-0 group-hover:opacity-100 flex items-center justify-center text-white transition-opacity duration-200"
                        >
                          <span className="text-[10px] font-bold">Remove</span>
                        </button>
                      </div>
                    ) : (
                      <div className="w-12 h-12 rounded-lg border border-dashed border-app-border-light bg-app-bg-muted/30 flex items-center justify-center text-app-text-muted/40 shrink-0">
                        <Users className="w-5 h-5" />
                      </div>
                    )}
                    <div className="flex-1">
                      <input
                        type="file"
                        accept="image/*"
                        id="agent-face-upload"
                        onChange={handleFaceChange}
                        className="hidden"
                        disabled={addingAgent}
                      />
                      <label
                        htmlFor="agent-face-upload"
                        className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold bg-app-bg-muted/70 hover:bg-app-bg-muted border border-app-border-light rounded-lg text-app-text-main cursor-pointer hover:border-app-primary transition-colors"
                      >
                        <Upload className="w-3.5 h-3.5" />
                        Upload Image
                      </label>
                      <p className="text-[10px] text-app-text-muted mt-1">PNG, JPG or SVG</p>
                    </div>
                  </div>
                </div>

                <div>
                  <label className="block text-xs font-bold text-app-text-muted uppercase tracking-wider mb-1.5">
                    Specialization Tags
                  </label>
                  <input
                    type="text"
                    value={newAgentTags}
                    onChange={(e) => setNewAgentTags(e.target.value)}
                    placeholder="e.g. React, FastApi, PostgreSQL, Pytest (comma-separated)"
                    className="w-full px-3 py-2 bg-app-bg-muted/50 border border-app-border-light rounded-lg text-sm text-app-text-main focus:outline-none focus:border-app-primary placeholder:text-app-text-muted/60 transition-colors"
                    disabled={addingAgent}
                  />
                  <p className="text-[10px] text-app-text-muted mt-1">Used by Master Agent to match task capabilities.</p>
                </div>

                <div>
                  <label className="block text-xs font-bold text-app-text-muted uppercase tracking-wider mb-1.5">
                    Upload Skills File (skills.md)
                  </label>
                  <div className="relative">
                    <input
                      type="file"
                      accept=".md"
                      id="skills-file-upload"
                      onChange={handleFileChange}
                      className="hidden"
                      disabled={addingAgent}
                    />
                    <label
                      htmlFor="skills-file-upload"
                      className="flex flex-col items-center justify-center w-full h-32 border-2 border-dashed border-app-border-light rounded-lg cursor-pointer bg-app-bg-muted/20 hover:bg-app-bg-muted/40 transition-colors"
                    >
                      <div className="flex flex-col items-center justify-center pt-5 pb-6">
                        <Upload className="w-8 h-8 text-app-text-muted mb-2" />
                        <p className="text-sm font-semibold text-app-text-main">
                          {skillsFileName || 'Click to select skills.md'}
                        </p>
                        <p className="text-xs text-app-text-muted mt-1">
                          Markdown file (.md) only
                        </p>
                      </div>
                    </label>
                  </div>
                </div>

                {addAgentError && (
                  <div className="p-3 text-xs rounded-lg bg-app-status-error/10 border border-app-status-error/20 text-red-400">
                    {addAgentError}
                  </div>
                )}
              </div>

              {/* Actions Footer */}
              <div className="p-6 pt-4 border-t border-app-border-light flex items-center justify-end gap-2 flex-shrink-0 bg-app-bg-card">
                <button
                  type="button"
                  onClick={() => {
                    setShowAddAgentModal(false);
                    setNewAgentName('');
                    setSkillsContent('');
                    setSkillsFileName('');
                    setNewAgentFace('');
                    setNewAgentTags('');
                    setAddAgentError('');
                  }}
                  disabled={addingAgent}
                  className="px-4 py-2 text-xs font-bold text-app-text-muted hover:text-app-text-main bg-app-text-label/10 hover:bg-app-text-label/20 rounded-lg transition-colors"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={addingAgent || !newAgentName.trim() || !skillsContent}
                  className="flex items-center gap-1.5 px-4 py-2 text-xs font-bold text-white bg-gradient-to-r from-app-primary to-blue-600 hover:from-blue-600 hover:to-blue-700 disabled:opacity-50 disabled:cursor-not-allowed rounded-lg shadow transition-all"
                >
                  {addingAgent ? (
                    <>
                      <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                      <span>Adding...</span>
                    </>
                  ) : (
                    <>
                      <Plus className="w-3.5 h-3.5" />
                      <span>Create Agent</span>
                    </>
                  )}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
