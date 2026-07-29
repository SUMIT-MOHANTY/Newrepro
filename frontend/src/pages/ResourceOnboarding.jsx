// Resource Onboarding page
import React, { useEffect, useMemo, useState } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { ArrowRight, CheckCircle2, Loader2, Bot, AlertTriangle, Minus, Plus, Info, Zap, Lock, Shield } from 'lucide-react';
import { API_ENDPOINTS } from '../config';
import RequestCapacityModal from '../components/RequestCapacityModal';

const TASK_TOKEN_STORAGE_KEY = 'status_dashboard_task_token_cache';

function decodeJwtExpiry(token) {
  try {
    const parts = token.split('.');
    if (parts.length < 2) return null;
    const payloadB64 = parts[1].replace(/-/g, '+').replace(/_/g, '/');
    const padded = payloadB64 + '='.repeat((4 - (payloadB64.length % 4)) % 4);
    const payload = JSON.parse(atob(padded));
    return typeof payload.exp === 'number' ? payload.exp : null;
  } catch {
    return null;
  }
}

function readTaskTokenCache() {
  try {
    const raw = localStorage.getItem(TASK_TOKEN_STORAGE_KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw);
    return parsed && typeof parsed === 'object' ? parsed : {};
  } catch {
    return {};
  }
}

function getCachedTaskToken(projectKey) {
  if (!projectKey) return null;
  const cache = readTaskTokenCache();
  const entry = cache[projectKey];
  if (!entry || !entry.token) return null;
  if (entry.expiresAt) {
    const now = Math.floor(Date.now() / 1000);
    if (entry.expiresAt <= now) return null;
  } else {
    const exp = decodeJwtExpiry(entry.token);
    if (exp && exp <= Math.floor(Date.now() / 1000)) return null;
  }
  return entry.token;
}

/**
 * Returns specialization badge classes.
 */
function getSpecBadgeClasses(spec) {
  if (spec === 'Testing') {
    return 'bg-purple-500/10 text-purple-400 border-purple-500/20';
  }
  return 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20';
}

/**
 * Counter component for shared/dedicated allocation per agent.
 */
function AllocationCounter({ label, value, onDecrement, onIncrement, disabled, exceeded }) {
  return (
    <div className="flex items-center gap-1.5 shrink-0">
      <span className={`inline-flex items-center justify-end gap-1 text-[10.5px] font-semibold w-[82px] shrink-0 select-none ${exceeded ? 'text-red-400' : 'text-app-text-muted'}`}>
        {label}
      </span>
      <div className={`flex items-center gap-0.5 rounded border p-0.5 transition-colors ${
        exceeded
          ? 'bg-red-500/10 border-red-500/30'
          : 'bg-app-bg-muted/40 border-app-border-light'
      }`}>
        <button
          type="button"
          onClick={onDecrement}
          disabled={value === 0}
          className="p-0.5 rounded hover:bg-app-bg-card disabled:opacity-20 text-app-text-muted hover:text-app-text-main transition-all"
        >
          <Minus className="w-2.5 h-2.5" />
        </button>
        <span className={`text-[11px] font-bold w-4 text-center ${exceeded ? 'text-red-400' : 'text-app-text-main'}`}>
          {value}
        </span>
        <button
          type="button"
          onClick={onIncrement}
          disabled={disabled}
          className="p-0.5 rounded hover:bg-app-bg-card disabled:opacity-20 text-app-text-muted hover:text-app-text-main transition-all"
        >
          <Plus className="w-2.5 h-2.5" />
        </button>
      </div>
    </div>
  );
}

export default function ResourceOnboarding({ selectedProjectKey, fetchHistory }) {
  const navigate = useNavigate();
  const location = useLocation();
  const processMode = location.state?.processMode || 'ai_first';
  const token = localStorage.getItem('token');

  // agents: flat list of all custom org agents from the backend
  const [agents, setAgents] = useState([]);
  // allocations: { [agentId]: { shared: number, dedicated: number } }
  const [allocations, setAllocations] = useState({});
  const [isLoadingAgents, setIsLoadingAgents] = useState(false);
  const [agentsError, setAgentsError] = useState('');

  const [submitError, setSubmitError] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [quota, setQuota] = useState(null);
  const [quotaLoading, setQuotaLoading] = useState(false);

  const [showNotifyModal, setShowNotifyModal] = useState(false);
  const [userRbac, setUserRbac] = useState(null);
  const isOrgAdmin = Boolean(userRbac?.is_org_admin);

  useEffect(() => {
    if (!token) return;
    fetch(API_ENDPOINTS.ORG_RBAC_ME, {
      headers: { Authorization: `Bearer ${token}` }
    })
      .then(res => res.json())
      .then(data => setUserRbac(data))
      .catch(() => {});
  }, [token]);

  const taskToken = useMemo(() => getCachedTaskToken(selectedProjectKey), [selectedProjectKey]);
  const hasValidTaskToken = Boolean(taskToken);

  // ─── Quota helpers ──────────────────────────────────────────────────────────
  const maxAgentCap = quota?.max_agent_capacity ?? 0;
  const sharedAllowed = quota?.shared_quota || maxAgentCap;
  const dedicatedAllowed = quota?.dedicated_quota || maxAgentCap;
  const physicalOnboarded = quota?.physical_workers_onboarded || (quota?.total_onboarded_agents || 0);
  const virtualSharedCount = quota?.virtual_shared_onboarded || 0;
  const freePhysicalSlots = quota?.available_capacity ?? Math.max(0, maxAgentCap - physicalOnboarded);

  // Usage by other projects
  const thisProjectCurrentShared = useMemo(() =>
    agents.filter(a => a.project_token === selectedProjectKey && (a.agent_kind === 'shared' || !a.agent_kind)).length,
    [agents, selectedProjectKey]
  );
  const thisProjectCurrentDedicated = useMemo(() =>
    agents.filter(a => a.project_token === selectedProjectKey && a.agent_kind === 'dedicated').length,
    [agents, selectedProjectKey]
  );

  const otherProjectsSharedUsage = Math.max(0, (quota?.shared_used || 0) - thisProjectCurrentShared);
  const otherProjectsDedicatedUsage = Math.max(0, (quota?.dedicated_used || 0) - thisProjectCurrentDedicated);

  // Total requested by UI for THIS project
  const thisProjectUiSharedTotal = useMemo(() =>
    Object.values(allocations).reduce((sum, a) => sum + (a?.shared || 0), 0),
    [allocations]
  );
  const thisProjectUiDedicatedTotal = useMemo(() =>
    Object.values(allocations).reduce((sum, a) => sum + (a?.dedicated || 0), 0),
    [allocations]
  );

  const totalSharedRequested = otherProjectsSharedUsage + thisProjectUiSharedTotal;
  const totalDedicatedRequested = otherProjectsDedicatedUsage + thisProjectUiDedicatedTotal;

  // Dedicated agents require physical container capacity
  const dedicatedExceeded = maxAgentCap > 0
    ? totalDedicatedRequested > freePhysicalSlots + thisProjectCurrentDedicated
    : true;
  
  // Shared agents can exceed physical cap if virtual shared worker reuse is available
  const sharedExceeded = maxAgentCap === 0;
  const quotaExceeded = maxAgentCap === 0 || dedicatedExceeded;

  const sharedRemaining = Math.max(0, sharedAllowed - totalSharedRequested);
  const dedicatedRemaining = Math.max(0, freePhysicalSlots);

  // ─── Fetch agents ───────────────────────────────────────────────────────────
  useEffect(() => {
    let isMounted = true;
    const controller = new AbortController();

    const fetchCustomAgents = async () => {
      if (!token) return;
      setIsLoadingAgents(true);
      setAgentsError('');
      try {
        const headers = { Authorization: `Bearer ${token}` };
        const url = new URL(API_ENDPOINTS.AGENTS);
        url.searchParams.set('include_defaults', 'false');

        const res = await fetch(url.toString(), { headers, signal: controller.signal });
        const json = await res.json();
        const parse = (data) => Array.isArray(data) ? data : (data?.agents || data?.results || data?.data || []);
        const combined = parse(json);

        if (!isMounted) return;

        setAgents(combined);

        // Initialize allocations: check if agent was already allocated to this project
        const initial = {};
        combined.forEach(agent => {
          const isThisProject = agent.project_token === selectedProjectKey;
          initial[agent.id] = {
            shared: isThisProject && (agent.agent_kind === 'shared' || !agent.agent_kind) ? 1 : 0,
            dedicated: isThisProject && agent.agent_kind === 'dedicated' ? 1 : 0,
          };
        });
        setAllocations(initial);
      } catch (err) {
        if (!isMounted) return;
        if (err.name === 'AbortError') return;
        setAgentsError(err.message || 'Failed to fetch custom agents');
      } finally {
        if (isMounted) setIsLoadingAgents(false);
      }
    };

    fetchCustomAgents();

    return () => {
      isMounted = false;
      controller.abort();
    };
  }, [token, selectedProjectKey]);

  // ─── Fetch quota ────────────────────────────────────────────────────────────
  useEffect(() => {
    let isMounted = true;
    const controller = new AbortController();
    const fetchQuota = async () => {
      if (!token) return;
      setQuotaLoading(true);
      try {
        const res = await fetch(API_ENDPOINTS.ORG_AGENT_QUOTA, {
          headers: { Authorization: `Bearer ${token}` },
          signal: controller.signal,
        });
        const json = await res.json().catch(() => ({}));
        if (isMounted && res.ok) setQuota(json);
      } catch (e) {
        if (!isMounted || e?.name === 'AbortError') return;
      } finally {
        if (isMounted) setQuotaLoading(false);
      }
    };
    fetchQuota();
    return () => { isMounted = false; controller.abort(); };
  }, [token]);

  // ─── Allocation change handlers ─────────────────────────────────────────────
  const handleSharedChange = (agentId, delta) => {
    setAllocations(prev => {
      const current = prev[agentId] || { shared: 0, dedicated: 0 };
      const newShared = Math.max(0, current.shared + delta);
      // Prevent exceeding org quota
      if (delta > 0) {
        const projectedTotal = otherProjectsSharedUsage + thisProjectUiSharedTotal - current.shared + newShared;
        if (projectedTotal > sharedAllowed) return prev;
      }
      return { ...prev, [agentId]: { ...current, shared: newShared } };
    });
  };

  const handleDedicatedChange = (agentId, delta) => {
    setAllocations(prev => {
      const current = prev[agentId] || { shared: 0, dedicated: 0 };
      const newDedicated = Math.max(0, current.dedicated + delta);
      // Prevent exceeding org quota
      if (delta > 0) {
        const projectedTotal = otherProjectsDedicatedUsage + thisProjectUiDedicatedTotal - current.dedicated + newDedicated;
        if (projectedTotal > dedicatedAllowed) return prev;
      }
      return { ...prev, [agentId]: { ...current, dedicated: newDedicated } };
    });
  };

  // ─── Submit ─────────────────────────────────────────────────────────────────
  const handleSubmit = async () => {
    setIsSubmitting(true);
    setSubmitError('');

    if (quotaExceeded) {
      let errStr = 'Organization capacity limit exceeded. ';
      if (sharedExceeded) errStr += `Shared: ${totalSharedRequested}/${sharedAllowed} used. `;
      if (dedicatedExceeded) errStr += `Dedicated: ${totalDedicatedRequested}/${dedicatedAllowed} used. `;
      setSubmitError(errStr);
      setIsSubmitting(false);
      return;
    }

    if (!selectedProjectKey) {
      setSubmitError('Please select a project before allocating agents.');
      setIsSubmitting(false);
      return;
    }

    // Build assignments: one entry per agent with shared_count + dedicated_count
    const assignments = Object.entries(allocations)
      .filter(([, alloc]) => (alloc?.shared || 0) > 0 || (alloc?.dedicated || 0) > 0)
      .map(([agentId, alloc]) => ({
        agent_id: agentId,
        shared_count: alloc?.shared || 0,
        dedicated_count: alloc?.dedicated || 0,
      }));

    // Also include agents explicitly set to 0 (unassign them)
    const unassignments = Object.entries(allocations)
      .filter(([, alloc]) => (alloc?.shared || 0) === 0 && (alloc?.dedicated || 0) === 0)
      .map(([agentId]) => ({
        agent_id: agentId,
        shared_count: 0,
        dedicated_count: 0,
      }));

    const payload = {
      project_token: selectedProjectKey,
      assignments: [...assignments, ...unassignments],
    };

    try {
      const response = await fetch(`${API_ENDPOINTS.AGENTS}/onboard`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify(payload)
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.detail || 'Failed to complete resource onboarding');
      }

      if (typeof fetchHistory === 'function') {
        fetchHistory();
      }

      navigate('/status-dashboard', { state: { processMode } });
    } catch (err) {
      setSubmitError(err.message || 'Failed to complete onboarding');
    } finally {
      setIsSubmitting(false);
    }
  };

  // ─── Derived counts ──────────────────────────────────────────────────────────
  const totalAllocated = thisProjectUiSharedTotal + thisProjectUiDedicatedTotal;
  const canSubmit = !isSubmitting && !quotaExceeded && agents.length > 0;

  return (
    <div className="h-full overflow-y-auto bg-gradient-to-br from-app-bg-page via-app-bg-page to-app-primary-light/30">
      <div className="max-w-4xl mx-auto px-3 py-3 sm:py-4">
        <div className="bg-app-bg-card/95 backdrop-blur-md rounded-xl border border-app-border-light shadow-md p-3 sm:p-4 space-y-3">

          {/* Header */}
          <div className="flex items-start justify-between gap-4 border-b border-app-border-light pb-2">
            <div>
              <p className="text-[9px] font-bold uppercase tracking-wider text-app-text-muted">AI Resource Setup</p>
              <h2 className="text-lg sm:text-xl font-extrabold text-app-text-main mt-0.5">Resource Onboarding</h2>
              <p className="text-xs text-app-text-muted mt-0.5 max-w-2xl">
                Allocate Shared or Dedicated agents to your project from the central capacity pool. Unassigned agents remain idle.
              </p>
            </div>
            <div className="shrink-0">
              <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full bg-app-status-successBg border border-emerald-500/20 text-app-status-success text-[10px] font-bold shadow-xs">
                <Bot className="w-3 h-3 animate-pulse" />
                {processMode === 'ai_assist' ? 'AI Assist Mode' : 'AI First Mode'}
              </span>
            </div>
          </div>

          {/* Central Pool Status & Super Admin Cap Bar */}
          <div className="p-2.5 rounded-lg border border-app-border-light bg-app-bg-muted/15 space-y-2.5">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-[9.5px] font-bold uppercase tracking-wider text-app-text-muted">Central Capacity Pool & Limits</p>
                <p className="text-[11px] font-semibold text-app-text-main mt-0.5">
                  Super Admin Approved Cap: <span className="font-extrabold text-purple-400">{maxAgentCap} Max Agents</span>
                </p>
              </div>
              <div className="flex items-center gap-2 flex-wrap">
                <span className="text-[10px] font-bold px-2 py-0.5 rounded bg-purple-500/10 border border-purple-500/20 text-purple-300">
                  {physicalOnboarded} Physical Workers / {freePhysicalSlots} Free Slots {virtualSharedCount > 0 && `(${virtualSharedCount} Virtual Shared)`}
                </span>
                <button
                  type="button"
                  onClick={() => setShowNotifyModal(true)}
                  className="inline-flex items-center gap-1.5 px-3 py-1 rounded-lg bg-purple-600 hover:bg-purple-500 text-white text-xs font-bold transition-all shadow-sm"
                >
                  <Shield className="w-3.5 h-3.5" />
                  <span>{isOrgAdmin ? 'Request Capacity Increase (Super Admin)' : 'Notify Org Admin for Agent Capacity'}</span>
                </button>
              </div>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
              {/* Shared Pool */}
              <div className="p-2 rounded-md bg-app-bg-card border border-app-border-light/60 flex flex-col justify-between gap-1 shadow-sm">
                <div className="flex justify-between items-center">
                  <span className="text-xs font-semibold text-app-text-main flex items-center gap-1.5">
                    <span className="w-2 h-2 rounded-full bg-blue-500/80"></span>
                    Shared Agents Pool
                  </span>
                  <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded border ${sharedExceeded ? 'bg-red-500/10 text-red-400 border-red-500/20 animate-pulse' : 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20'}`}>
                    {totalSharedRequested} / {sharedAllowed} Used
                  </span>
                </div>
                <div className="w-full h-1 rounded-full bg-app-bg-muted/60 overflow-hidden">
                  <div
                    className={`h-full rounded-full transition-all duration-500 ${sharedExceeded ? 'bg-red-500' : 'bg-gradient-to-r from-blue-500 to-indigo-400'}`}
                    style={{ width: `${Math.min(100, (totalSharedRequested / max(1, sharedAllowed)) * 100)}%` }}
                  />
                </div>
                <div className="flex justify-between text-[9.5px] text-app-text-muted px-0.5">
                  <span>Other Projects: <span className="font-semibold text-amber-500">{otherProjectsSharedUsage}</span></span>
                  <span>Here: <span className="font-semibold text-emerald-500">+{thisProjectUiSharedTotal}</span></span>
                  <span className="flex items-center gap-0.5">
                    <Info className="w-3 h-3 text-blue-400 inline shrink-0" />
                    <span><span className="font-bold text-blue-400">{sharedRemaining}</span> remaining</span>
                  </span>
                </div>
              </div>

              {/* Dedicated Pool */}
              <div className="p-2 rounded-md bg-app-bg-card border border-app-border-light/60 flex flex-col justify-between gap-1 shadow-sm">
                <div className="flex justify-between items-center">
                  <span className="text-xs font-semibold text-app-text-main flex items-center gap-1.5">
                    <span className="w-2 h-2 rounded-full bg-purple-500/80"></span>
                    Dedicated Agents Pool
                  </span>
                  <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded border ${dedicatedExceeded ? 'bg-red-500/10 text-red-400 border-red-500/20 animate-pulse' : 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20'}`}>
                    {totalDedicatedRequested} / {dedicatedAllowed} Used
                  </span>
                </div>
                <div className="w-full h-1 rounded-full bg-app-bg-muted/60 overflow-hidden">
                  <div
                    className={`h-full rounded-full transition-all duration-500 ${dedicatedExceeded ? 'bg-red-500' : 'bg-gradient-to-r from-purple-500 to-pink-400'}`}
                    style={{ width: `${Math.min(100, (totalDedicatedRequested / max(1, dedicatedAllowed)) * 100)}%` }}
                  />
                </div>
                <div className="flex justify-between text-[9.5px] text-app-text-muted px-0.5">
                  <span>Other Projects: <span className="font-semibold text-amber-500">{otherProjectsDedicatedUsage}</span></span>
                  <span>Here: <span className="font-semibold text-purple-400">+{thisProjectUiDedicatedTotal}</span></span>
                  <span className="flex items-center gap-0.5">
                    <Lock className="w-3 h-3 text-purple-400 inline shrink-0" />
                    <span><span className="font-bold text-purple-400">{dedicatedRemaining}</span> remaining</span>
                  </span>
                </div>
              </div>
            </div>
          </div>

          {/* Quota Exceeded Alert */}
          {quotaExceeded && (
            <div className="p-2 text-[11px] text-red-400 bg-app-status-error/10 border border-app-status-error/20 rounded-lg flex items-start gap-2 animate-in fade-in slide-in-from-top-1 duration-150">
              <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5 text-red-400" />
              <div>
                <p className="font-bold">Capacity Limit Exceeded!</p>
                <p className="mt-0.5 text-app-text-muted leading-relaxed">
                  {sharedExceeded && `Shared agent capacity limit exceeded (Allocated: ${totalSharedRequested}, Limit: ${sharedAllowed}). `}
                  {dedicatedExceeded && `Dedicated agent capacity limit exceeded (Allocated: ${totalDedicatedRequested}, Limit: ${dedicatedAllowed}). `}
                  Please reduce allocations using the counter buttons below.
                </p>
              </div>
            </div>
          )}

          {/* Agents List */}
          <div className="space-y-2">
            <div className="flex items-center justify-between border-b border-app-border-light pb-1">
              <h3 className="text-[9px] font-bold uppercase tracking-wider text-app-text-muted">
                Available Custom Agents
              </h3>
              <span className="text-[9px] text-app-text-muted font-semibold">
                {agents.length} in Pool
              </span>
            </div>

            {isLoadingAgents ? (
              <div className="flex flex-col items-center justify-center py-6">
                <Loader2 className="w-6 h-6 text-app-primary animate-spin mb-1.5" />
                <p className="text-[10px] text-app-text-muted">Loading custom agents...</p>
              </div>
            ) : agentsError ? (
              <div className="p-2.5 rounded-lg bg-app-status-error/10 border border-app-status-error/20 text-xs text-red-400">
                {agentsError}
              </div>
            ) : agents.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-8 border border-dashed border-app-border-light rounded-xl bg-app-bg-muted/5">
                <Bot className="w-8 h-8 text-app-text-muted/30 mb-2 animate-bounce" />
                <p className="text-xs font-semibold text-app-text-muted">No custom agents added yet</p>
                <p className="text-[10px] text-app-text-muted/60 mt-0.5 max-w-xs text-center">
                  Add custom skills-based agents under the Agents dashboard first.
                </p>
              </div>
            ) : (
              <div className="space-y-1.5">
                {agents.map(agent => {
                  const alloc = allocations[agent.id] || { shared: 0, dedicated: 0 };
                  const sharedVal = alloc.shared || 0;
                  const dedicatedVal = alloc.dedicated || 0;
                  const totalForAgent = sharedVal + dedicatedVal;
                  const isActive = totalForAgent > 0;

                  // Determine if we can still increase each type
                  const canAddShared = sharedRemaining > 0;
                  const canAddDedicated = dedicatedRemaining > 0;

                  const spec = agent.specialization || 'Development';

                  return (
                    <div
                      key={agent.id}
                      className={`flex flex-col sm:flex-row sm:items-center justify-between p-2 sm:py-2.5 sm:px-3 rounded-lg border transition-all duration-200 gap-2 shadow-xs ${
                        isActive
                          ? 'border-app-primary/30 bg-app-primary/5'
                          : 'border-app-border-light bg-app-bg-card hover:border-app-primary-light/40'
                      }`}
                    >
                      {/* Left: Agent Info */}
                      <div className="flex items-start gap-2 flex-1 min-w-0">
                        <div className={`rounded-lg shrink-0 mt-0.5 overflow-hidden flex items-center justify-center ${
                          agent.face 
                            ? 'w-7 h-7 border border-app-border' 
                            : `p-1 ${isActive ? 'bg-app-primary/20 border border-app-primary/30' : 'bg-app-primary/10 border border-app-primary/20'}`
                        }`}>
                          {agent.face ? (
                            <img src={agent.face} alt={agent.name} className="w-full h-full object-cover" />
                          ) : (
                            <Bot className={`w-3.5 h-3.5 ${isActive ? 'text-app-primary' : 'text-app-primary/70'}`} />
                          )}
                        </div>
                        <div className="min-w-0 flex-1">
                          <div className="flex items-center gap-1.5 flex-wrap">
                            <h4 className="text-xs font-bold text-app-text-main">{agent.name}</h4>
                            <span className={`px-1.5 py-0.5 text-[8px] font-bold rounded uppercase tracking-wider border ${getSpecBadgeClasses(spec)}`}>
                              {spec}
                            </span>
                            {isActive && (
                              <span className="px-1.5 py-0.5 text-[8px] font-bold rounded-full uppercase bg-app-primary/15 text-app-primary border border-app-primary/20 animate-in fade-in duration-200">
                                Allocated
                              </span>
                            )}
                          </div>
                          {agent.skills_summary && (
                            <p className="text-[10px] text-app-text-muted mt-0.5 leading-relaxed truncate max-w-md sm:max-w-lg" title={agent.skills_summary}>
                              {agent.skills_summary}
                            </p>
                          )}
                          {agent.skills_tags && Array.isArray(agent.skills_tags) && agent.skills_tags.length > 0 && (
                            <div className="flex flex-wrap gap-1 mt-0.5">
                              {agent.skills_tags.slice(0, 5).map((tag, idx) => (
                                <span key={idx} className="px-1 py-0.5 text-[8px] font-medium rounded bg-app-bg-muted text-app-text-muted border border-app-border-light">
                                  {tag}
                                </span>
                              ))}
                            </div>
                          )}
                        </div>
                      </div>

                      {/* Right: Counters */}
                      <div className="flex items-center gap-3 justify-between sm:justify-end shrink-0">
                        {/* Shared Counter */}
                        <AllocationCounter
                          label="Shared:"
                          value={sharedVal}
                          onDecrement={() => handleSharedChange(agent.id, -1)}
                          onIncrement={() => handleSharedChange(agent.id, 1)}
                          disabled={!canAddShared}
                          exceeded={sharedExceeded && sharedVal > 0}
                        />

                        {/* Dedicated Counter */}
                        <AllocationCounter
                          label={
                            <>
                              <Lock className="w-2.5 h-2.5 text-purple-400/80 shrink-0" />
                              <span>Dedicated:</span>
                            </>
                          }
                          value={dedicatedVal}
                          onDecrement={() => handleDedicatedChange(agent.id, -1)}
                          onIncrement={() => handleDedicatedChange(agent.id, 1)}
                          disabled={!canAddDedicated}
                          exceeded={dedicatedExceeded && dedicatedVal > 0}
                        />
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>

          {/* Summary row */}
          {totalAllocated > 0 && (
            <div className="p-1.5 rounded-lg bg-app-bg-muted/20 border border-app-border-light/50 flex items-center gap-2 text-[10px] text-app-text-muted animate-in fade-in slide-in-from-bottom-1 duration-200">
              <Zap className="w-3 h-3 text-app-primary shrink-0" />
              <span>
                <span className="font-bold text-app-text-main">{totalAllocated}</span> agent instance{totalAllocated !== 1 ? 's' : ''} allocated for this project
                {thisProjectUiSharedTotal > 0 && (
                  <span className="text-blue-400"> · {thisProjectUiSharedTotal} shared</span>
                )}
                {thisProjectUiDedicatedTotal > 0 && (
                  <span className="text-purple-400"> · {thisProjectUiDedicatedTotal} dedicated</span>
                )}
              </span>
            </div>
          )}

          {/* Bottom Notice & Action */}
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pt-2.5 border-t border-app-border-light">
            <div className="p-1.5 text-[9.5px] text-app-text-muted bg-app-primary/5 border border-app-primary/10 rounded-lg flex items-start gap-1.5 max-w-xl">
              <Bot className="w-3.5 h-3.5 text-app-primary shrink-0 mt-0.5" />
              <div>
                <span className="font-bold text-app-text-main">Skill-Based Orchestration: </span>
                <span>
                  Allocated agents are managed by the <strong className="text-app-primary">Master Agent</strong> and assigned
                  dynamically based on skills.{' '}
                  <span className="text-purple-400 font-semibold">Dedicated agents</span> serve only this project.{' '}
                  <span className="text-blue-400 font-semibold">Shared agents</span> are available org-wide.
                </span>
              </div>
            </div>

            <button
              onClick={handleSubmit}
              disabled={!canSubmit}
              className="inline-flex items-center justify-center gap-1.5 px-4 py-2 text-xs font-bold text-white bg-gradient-to-r from-app-primary to-blue-600 hover:from-blue-600 hover:to-blue-700 rounded-lg shadow-sm hover:shadow transition-all disabled:opacity-50 disabled:cursor-not-allowed shrink-0"
            >
              {isSubmitting ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <CheckCircle2 className="w-3.5 h-3.5" />}
              <span>{isSubmitting ? 'Onboarding...' : 'Complete Onboarding'}</span>
              <ArrowRight className="w-3.5 h-3.5" />
            </button>
          </div>

          {/* Submit Error */}
          {submitError && (
            <div className="text-xs text-app-status-error bg-app-status-errorBg border border-red-200 rounded-lg px-2.5 py-1.5">
              {submitError}
            </div>
          )}

        </div>
      </div>

      {/* Capacity Notification / Request Modal */}
      <RequestCapacityModal
        isOpen={showNotifyModal}
        onClose={() => setShowNotifyModal(false)}
        selectedProjectKey={selectedProjectKey}
        isOrgAdmin={isOrgAdmin}
        onSuccess={() => {
          alert(
            isOrgAdmin
              ? 'Capacity Increase Request submitted to Super Admin!'
              : 'Capacity notification submitted to Organization Admin!'
          );
        }}
      />
    </div>
  );
}
