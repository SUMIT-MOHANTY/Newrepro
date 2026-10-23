// Resource Onboarding page
import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { ArrowRight, CheckCircle2, Loader2, Bot, AlertTriangle, Minus, Plus, Info, Zap, Lock, Shield, Wand2, Sparkles, Wrench, FileText, Edit3, X, Cpu } from 'lucide-react';
import { API_ENDPOINTS } from '../config';
import RequestCapacityModal from '../components/RequestCapacityModal';
import AgentToolPicker, { ALL_TOOLS } from '../components/AgentToolPicker';
import { getMandatoryToolsForAgent, fetchMandatoryToolsMatrix } from '../utils/agentToolsHelper';


function getLaneBadgeColor(lane) {
  switch ((lane || '').toLowerCase()) {
    case 'backend':
      return 'bg-blue-500/10 text-blue-400 border-blue-500/20';
    case 'frontend':
      return 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20';
    case 'devops':
      return 'bg-amber-500/10 text-amber-400 border-amber-500/20';
    case 'qa':
    case 'test':
      return 'bg-purple-500/10 text-purple-400 border-purple-500/20';
    default:
      return 'bg-cyan-500/10 text-cyan-400 border-cyan-500/20';
  }
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
  const currentProjectToken = selectedProjectKey || location.state?.projectToken;
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

  // ─── Tool Adequacy state ────────────────────────────────────────────────────
  // toolAdequacy: { [agentId]: { status, missing_required, missing_recommended, verdict, suggested_tools } }
  const [toolAdequacy, setToolAdequacy] = useState({});
  const [toolPickerOpen, setToolPickerOpen] = useState(null); // agentId or null
  const adequacyFetchedRef = useRef({}); // tracks which agentIds we've already fetched

  // ─── Auto-create recommendations state ─────────────────────────────────────
  const [recommendations, setRecommendations] = useState(null); // null = not loaded
  const [loadingRecommendations, setLoadingRecommendations] = useState(false);
  const [autoCreateLoading, setAutoCreateLoading] = useState(false);
  const [autoCreateError, setAutoCreateError] = useState('');
  // Incrementing this counter re-triggers the agent fetch useEffect after auto-create
  const [autoCreateDone, setAutoCreateDone] = useState(0);

  useEffect(() => {
    if (!token) return;
    fetchMandatoryToolsMatrix(token);
    fetch(API_ENDPOINTS.ORG_RBAC_ME, {
      headers: { Authorization: `Bearer ${token}` }
    })
      .then(res => res.json())
      .then(data => setUserRbac(data))
      .catch(() => {});
  }, [token]);

  const [selectedPromptAgentIndex, setSelectedPromptAgentIndex] = useState(null);
  const [editingPromptText, setEditingPromptText] = useState('');
  const [addingToolRecIndex, setAddingToolRecIndex] = useState(null);

  // ─── Quota helpers ──────────────────────────────────────────────────────────
  const maxAgentCap = quota?.max_agent_capacity ?? 0;
  const sharedAllowed = quota?.shared_quota || maxAgentCap;
  const dedicatedAllowed = quota?.dedicated_quota || maxAgentCap;
  const physicalOnboarded = quota?.physical_workers_onboarded || (quota?.total_onboarded_agents || 0);
  const virtualSharedCount = quota?.virtual_shared_onboarded || 0;
  const freePhysicalSlots = quota?.available_capacity ?? Math.max(0, maxAgentCap - physicalOnboarded);

  // Usage by other projects
  const thisProjectCurrentShared = useMemo(() =>
    agents.filter(a => a.project_token === currentProjectToken && (a.agent_kind === 'shared' || !a.agent_kind)).length,
    [agents, currentProjectToken]
  );
  const thisProjectCurrentDedicated = useMemo(() =>
    agents.filter(a => a.project_token === currentProjectToken && a.agent_kind === 'dedicated').length,
    [agents, currentProjectToken]
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

  const [capacityRequestNotice, setCapacityRequestNotice] = useState('');

  // Dedicated agents require physical container capacity for NEW requested slots
  const newDedicatedRequested = Math.max(0, thisProjectUiDedicatedTotal - thisProjectCurrentDedicated);
  const dedicatedExceeded = maxAgentCap > 0
    ? newDedicatedRequested > freePhysicalSlots
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
          const isThisProject = agent.project_token === currentProjectToken;
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

    fetchCustomAgents().then(() => {
      // After a successful auto-create re-fetch, clear recommendations panel
      if (autoCreateDone > 0) setRecommendations(null);
    });

    return () => {
      isMounted = false;
      controller.abort();
    };
  }, [token, currentProjectToken, autoCreateDone]);


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

    if (!currentProjectToken) {
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
      project_token: currentProjectToken,
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

      // After successful onboard, auto-trigger agent execution
      try {
        const runHeaders = { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' };
        if (currentProjectToken) runHeaders['x-project-token'] = currentProjectToken;
        await fetch(`${API_ENDPOINTS.AGENTS}/run-all?project_token=${encodeURIComponent(currentProjectToken)}`, {
          method: 'POST',
          headers: runHeaders,
          body: JSON.stringify({}),
        });
      } catch (runErr) {
        console.warn('Auto-trigger agents failed, user can manually start from dashboard:', runErr);
      }

      navigate('/status-dashboard', { state: { processMode, projectToken: currentProjectToken, autoStarted: true } });
    } catch (err) {
      setSubmitError(err.message || 'Failed to complete onboarding');
    } finally {
      setIsSubmitting(false);
    }
  };

  // ─── Derived counts ──────────────────────────────────────────────────────────
  const totalAllocated = thisProjectUiSharedTotal + thisProjectUiDedicatedTotal;

  // hasCriticalToolGap: true if any *active* (allocated) agent has a critical tool gap
  const hasCriticalToolGap = useMemo(() =>
    Object.entries(toolAdequacy).some(([agentId, adequacy]) => {
      const alloc = allocations[agentId] || { shared: 0, dedicated: 0 };
      const isActive = (alloc.shared || 0) + (alloc.dedicated || 0) > 0;
      return isActive && adequacy?.status === 'critical';
    }),
    [toolAdequacy, allocations]
  );
  // Note: hasCriticalToolGap does NOT block the submit button (per spec — hard block is at runtime).
  const canSubmit = !isSubmitting && !quotaExceeded && agents.length > 0;

  // ─── Fetch tool adequacy for a single active agent ────────────────────────
  const fetchToolAdequacy = useCallback(async (agentId) => {
    if (!token || adequacyFetchedRef.current[agentId]) return;
    adequacyFetchedRef.current[agentId] = true;
    try {
      const res = await fetch(
        API_ENDPOINTS.AGENT_TOOL_CHECK(agentId, currentProjectToken),
        { headers: { Authorization: `Bearer ${token}` } }
      );
      if (!res.ok) return;
      const data = await res.json();
      setToolAdequacy(prev => ({ ...prev, [agentId]: data }));
    } catch (_) {
      // silently ignore — tool check is non-blocking
    }
  }, [token, currentProjectToken]);

  // ─── Fetch recommendations for empty state ────────────────────────────────
  const fetchRecommendations = useCallback(async () => {
    if (!token || !currentProjectToken) return;
    setLoadingRecommendations(true);
    try {
      const res = await fetch(API_ENDPOINTS.AGENT_RECOMMEND, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ project_token: currentProjectToken }),
      });
      if (!res.ok) return;
      const data = await res.json();
      const recs = (data.recommendations || []).map(r => {
        const mandatory = getMandatoryToolsForAgent(r);
        return {
          ...r,
          tools: Array.from(new Set([...(r.tools || []), ...mandatory]))
        };
      });
      setRecommendations(recs);
    } catch (_) {
      setRecommendations([]);
    } finally {
      setLoadingRecommendations(false);
    }
  }, [token, currentProjectToken]);

  // ─── Auto-create agents from recommendations ──────────────────────────────
  const handleAutoCreate = useCallback(async () => {
    if (!token || !recommendations || recommendations.length === 0) return;
    setAutoCreateLoading(true);
    setAutoCreateError('');
    try {
      // Ensure mandatory tools (such as filesystem for frontend) are guaranteed before auto-create
      const sanitizedRecommendations = recommendations.map(rec => {
        const mandatory = getMandatoryToolsForAgent(rec);
        return {
          ...rec,
          tools: Array.from(new Set([...(rec.tools || []), ...mandatory]))
        };
      });
      const res = await fetch(API_ENDPOINTS.AGENT_AUTO_CREATE, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          project_token: currentProjectToken,
          agents: sanitizedRecommendations,
        }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || 'Auto-create failed');
      // Refresh agent list so the new agents appear
      adequacyFetchedRef.current = {};
      setAllocations({});
      setAgents([]);
      setAutoCreateDone(prev => prev + 1);
    } catch (err) {
      setAutoCreateError(err.message || 'Auto-create failed');
    } finally {
      setAutoCreateLoading(false);
    }
  }, [token, currentProjectToken, recommendations]);

  const handleRemoveRecTool = useCallback((idx, toolId) => {
    if (!recommendations || !recommendations[idx]) return;
    const rec = recommendations[idx];
    const mandatory = getMandatoryToolsForAgent(rec);
    if (mandatory.includes(toolId.toLowerCase())) {
      // Mandatory tool cannot be removed!
      return;
    }
    const updated = [...recommendations];
    updated[idx] = {
      ...rec,
      tools: (rec.tools || []).filter(t => t.toLowerCase() !== toolId.toLowerCase()),
    };
    setRecommendations(updated);
  }, [recommendations]);

  const handleAddRecTool = useCallback((idx, toolId) => {
    if (!recommendations || !recommendations[idx]) return;
    const rec = recommendations[idx];
    const updated = [...recommendations];
    updated[idx] = {
      ...rec,
      tools: Array.from(new Set([...(rec.tools || []), toolId])),
    };
    setRecommendations(updated);
    setAddingToolRecIndex(null);
  }, [recommendations]);

  const handleOpenPromptModal = useCallback((idx) => {
    setSelectedPromptAgentIndex(idx);
    setEditingPromptText(recommendations?.[idx]?.skills_content || '');
  }, [recommendations]);

  const handleSavePrompt = useCallback(() => {
    if (selectedPromptAgentIndex !== null && recommendations) {
      const updated = [...recommendations];
      updated[selectedPromptAgentIndex] = {
        ...updated[selectedPromptAgentIndex],
        skills_content: editingPromptText,
      };
      setRecommendations(updated);
      setSelectedPromptAgentIndex(null);
    }
  }, [selectedPromptAgentIndex, recommendations, editingPromptText]);

  const handleUpdateModel = useCallback((idx, newModel) => {
    if (recommendations) {
      const updated = [...recommendations];
      updated[idx] = {
        ...updated[idx],
        model_name: newModel,
      };
      setRecommendations(updated);
    }
  }, [recommendations]);

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

          {/* Central Pool Status & Org-Wide Capacity Limit Bar */}
          <div className="p-2.5 rounded-lg border border-app-border-light bg-app-bg-muted/15 space-y-2.5">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-[9.5px] font-bold uppercase tracking-wider text-app-text-muted">Central Capacity Pool & Limits</p>
                <p className="text-[11px] font-semibold text-app-text-main mt-0.5">
                  Org-Wide Capacity Limit: <span className="font-extrabold text-purple-400">{maxAgentCap} Max Agents</span>
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
                    style={{ width: `${Math.min(100, (totalSharedRequested / Math.max(1, sharedAllowed)) * 100)}%` }}
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
                    style={{ width: `${Math.min(100, (totalDedicatedRequested / Math.max(1, dedicatedAllowed)) * 100)}%` }}
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

          {/* Capacity Request Submitted Success Banner */}
          {capacityRequestNotice && (
            <div className="p-2 text-[11px] text-emerald-300 bg-emerald-500/10 border border-emerald-500/20 rounded-lg flex items-center justify-between gap-2 animate-in fade-in duration-200">
              <div className="flex items-center gap-2">
                <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
                <span className="font-semibold">{capacityRequestNotice}</span>
              </div>
              <button
                type="button"
                onClick={() => setCapacityRequestNotice('')}
                className="text-emerald-400 hover:text-emerald-200 text-xs font-bold px-1.5"
              >
                ✕
              </button>
            </div>
          )}

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

          {/* Agents List & AI Recommendations */}
          <div className="space-y-3">
            <div className="flex items-center justify-between border-b border-app-border-light pb-1.5">
              <div className="flex items-center gap-2">
                <h3 className="text-[9px] font-bold uppercase tracking-wider text-app-text-muted">
                  Custom Project Agents
                </h3>
                <span className="text-[9px] text-app-text-muted font-semibold">
                  ({agents.length} in Pool)
                </span>
              </div>
              <button
                type="button"
                onClick={fetchRecommendations}
                disabled={loadingRecommendations || !currentProjectToken}
                className="inline-flex items-center gap-1.5 px-2.5 py-1 text-[10.5px] font-bold rounded-lg bg-gradient-to-r from-indigo-500 to-purple-600 text-white hover:from-indigo-600 hover:to-purple-700 disabled:opacity-60 transition-all shadow-sm"
              >
                {loadingRecommendations ? (
                  <Loader2 className="w-3 h-3 animate-spin" />
                ) : (
                  <Sparkles className="w-3 h-3 text-amber-300" />
                )}
                <span>{loadingRecommendations ? 'Synthesizing...' : 'AI-Recommend'}</span>
              </button>
            </div>

            {/* AI-Synthesized Swarm Recommendations Panel */}
            {recommendations && recommendations.length > 0 && (
              <div className="p-3.5 rounded-xl border border-indigo-500/30 bg-indigo-500/5 space-y-3">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <Sparkles className="w-4 h-4 text-indigo-400" />
                    <div>
                      <h4 className="text-xs font-bold text-app-text-main">
                        AI-Synthesized Project Team ({recommendations.length} Specialized Roles)
                      </h4>
                      <p className="text-[10px] text-app-text-muted">
                        Review roles, customize AI models or system prompts, and onboard into project pool.
                      </p>
                    </div>
                  </div>
                  <button
                    type="button"
                    onClick={() => setRecommendations(null)}
                    className="p-1 text-app-text-muted hover:text-app-text-main text-xs rounded hover:bg-app-bg-muted"
                    title="Dismiss"
                  >
                    <X className="w-3.5 h-3.5" />
                  </button>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-2.5">
                  {recommendations.map((rec, idx) => (
                    <div key={idx} className="p-3 rounded-lg border border-app-border-light bg-app-bg-card flex flex-col justify-between space-y-2">
                      <div className="space-y-1">
                        <div className="flex items-start justify-between gap-1.5">
                          <div>
                            <span className={`inline-block px-1.5 py-0.5 text-[8px] font-bold uppercase rounded border mb-1 ${getLaneBadgeColor(rec.lane)}`}>
                              {rec.lane || 'general'}
                            </span>
                            <h5 className="text-xs font-bold text-app-text-main leading-tight">{rec.role}</h5>
                          </div>
                          <span className="text-[9px] font-semibold text-app-text-muted shrink-0">
                            {rec.task_count || 0} task{rec.task_count !== 1 ? 's' : ''}
                          </span>
                        </div>
                        <p className="text-[10px] text-app-text-muted line-clamp-2">
                          {rec.skills_summary || rec.justification || rec.specialization}
                        </p>
                      </div>

                      {/* Tool tags with mandatory enforcement & optional controls */}
                      {(() => {
                        const recMandatoryTools = getMandatoryToolsForAgent(rec);
                        return (
                          <div className="space-y-1">
                            <div className="flex items-center justify-between text-[9px] text-app-text-muted">
                              <span className="font-semibold uppercase tracking-wider">Authorized Tools:</span>
                              <span className="text-[8px] text-amber-400 font-medium flex items-center gap-0.5">
                                <Lock className="w-2.5 h-2.5" />
                                {recMandatoryTools.length} mandatory
                              </span>
                            </div>
                            <div className="flex flex-wrap items-center gap-1">
                              {(rec.tools || []).map((t, ti) => {
                                const isMandatory = recMandatoryTools.includes(t.toLowerCase());
                                return isMandatory ? (
                                  <span
                                    key={ti}
                                    className="inline-flex items-center gap-1 px-1.5 py-0.5 text-[8.5px] font-mono rounded bg-amber-500/10 text-amber-400 border border-amber-500/30 font-semibold cursor-default select-none shadow-2xs"
                                    title={`${t} is mandatory for ${rec.role} and cannot be removed.`}
                                  >
                                    <Lock className="w-2.5 h-2.5 text-amber-400 shrink-0" />
                                    <span>{t}</span>
                                    <span className="text-[7px] uppercase tracking-wide opacity-80 font-sans font-bold">(Mandatory)</span>
                                  </span>
                                ) : (
                                  <span
                                    key={ti}
                                    className="inline-flex items-center gap-1 px-1.5 py-0.5 text-[8.5px] font-mono rounded bg-app-bg-muted/70 text-app-text-main border border-app-border-light group hover:border-red-500/30 transition-colors"
                                  >
                                    <span>{t}</span>
                                    <button
                                      type="button"
                                      onClick={() => handleRemoveRecTool(idx, t)}
                                      className="text-app-text-muted hover:text-red-400 p-0.5 rounded transition-colors"
                                      title={`Remove optional tool ${t}`}
                                    >
                                      <X className="w-2.5 h-2.5" />
                                    </button>
                                  </span>
                                );
                              })}

                              {/* Add optional tool dropdown */}
                              <div className="relative inline-block">
                                <button
                                  type="button"
                                  onClick={() => setAddingToolRecIndex(addingToolRecIndex === idx ? null : idx)}
                                  className="inline-flex items-center gap-0.5 px-1.5 py-0.5 text-[8.5px] font-semibold rounded border border-dashed border-app-border-light text-app-text-muted hover:text-app-primary hover:border-app-primary/40 transition-colors"
                                  title="Add an optional tool"
                                >
                                  <Plus className="w-2.5 h-2.5" />
                                  <span>Tool</span>
                                </button>

                                {addingToolRecIndex === idx && (
                                  <div className="absolute left-0 bottom-full mb-1 z-30 w-48 bg-app-bg-card border border-app-border-light rounded-lg shadow-xl p-1.5 space-y-1 animate-in fade-in duration-150">
                                    <div className="text-[9px] font-bold text-app-text-muted uppercase px-1 pb-1 border-b border-app-border-light flex items-center justify-between">
                                      <span>Add Tool</span>
                                      <button
                                        type="button"
                                        onClick={() => setAddingToolRecIndex(null)}
                                        className="p-0.5 hover:text-app-text-main"
                                      >
                                        <X className="w-2.5 h-2.5" />
                                      </button>
                                    </div>
                                    <div className="max-h-36 overflow-y-auto space-y-0.5">
                                      {ALL_TOOLS.filter(tool => !(rec.tools || []).map(x => x.toLowerCase()).includes(tool.id.toLowerCase())).map(tool => (
                                        <button
                                          key={tool.id}
                                          type="button"
                                          onClick={() => handleAddRecTool(idx, tool.id)}
                                          className="w-full text-left px-1.5 py-1 text-[10px] rounded hover:bg-app-bg-muted text-app-text-main flex items-center justify-between transition-colors"
                                        >
                                          <span>{tool.label}</span>
                                          <Plus className="w-2.5 h-2.5 text-app-primary" />
                                        </button>
                                      ))}
                                    </div>
                                  </div>
                                )}
                              </div>
                            </div>
                          </div>
                        );
                      })()}

                      {/* Model Selector & System Prompt Button */}
                      <div className="flex items-center justify-between pt-1 border-t border-app-border-light gap-2">
                        <div className="flex items-center gap-1">
                          <Cpu className="w-3 h-3 text-app-text-muted" />
                          <select
                            value={rec.model_name || 'claude'}
                            onChange={(e) => handleUpdateModel(idx, e.target.value)}
                            className="text-[10px] font-medium bg-app-bg-muted border border-app-border-light rounded px-1.5 py-0.5 text-app-text-main focus:outline-none"
                          >
                            <option value="claude">Claude</option>
                            <option value="kimi">Kimi</option>
                            <option value="deepseek">DeepSeek</option>
                          </select>
                        </div>
                        <button
                          type="button"
                          onClick={() => handleOpenPromptModal(idx)}
                          className="inline-flex items-center gap-1 px-2 py-0.5 text-[10px] font-semibold rounded bg-app-bg-muted hover:bg-app-primary/10 text-app-primary border border-app-primary/30 transition-colors"
                        >
                          <FileText className="w-3 h-3" />
                          <span>System Prompt</span>
                        </button>
                      </div>
                    </div>
                  ))}
                </div>

                {autoCreateError && (
                  <div className="flex items-center gap-1.5 text-xs text-red-400 p-2 rounded bg-red-500/10 border border-red-500/20">
                    <AlertTriangle className="w-3.5 h-3.5 shrink-0" />
                    <span>{autoCreateError}</span>
                  </div>
                )}

                <div className="flex justify-end pt-1">
                  <button
                    type="button"
                    onClick={handleAutoCreate}
                    disabled={autoCreateLoading}
                    className="inline-flex items-center gap-1.5 px-4 py-2 text-xs font-bold rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white disabled:opacity-60 transition-colors shadow-sm"
                  >
                    {autoCreateLoading ? (
                      <Loader2 className="w-3.5 h-3.5 animate-spin" />
                    ) : (
                      <CheckCircle2 className="w-3.5 h-3.5" />
                    )}
                    <span>
                      {autoCreateLoading
                        ? 'Creating Agents...'
                        : `Create & Onboard ${recommendations.length} Recommended Agent${recommendations.length !== 1 ? 's' : ''}`}
                    </span>
                  </button>
                </div>
              </div>
            )}

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
              /* ── Smart Empty State: Prompt to use AI-Recommend ── */
              <div className="space-y-3">
                <div className="flex flex-col items-center justify-center py-6 border border-dashed border-app-border-light rounded-xl bg-app-bg-muted/5">
                  <Bot className="w-8 h-8 text-app-text-muted/30 mb-2 animate-bounce" />
                  <p className="text-xs font-semibold text-app-text-muted">No custom agents added yet</p>
                  <p className="text-[10px] text-app-text-muted/60 mt-0.5 max-w-xs text-center mb-3">
                    Click "AI-Recommend" above to automatically generate specialized agents and handcrafted system prompts based on this project's BRD and blueprints.
                  </p>
                </div>
              </div>
            ) : (
              <div className="space-y-1.5">
                {agents.map(agent => {
                  const alloc = allocations[agent.id] || { shared: 0, dedicated: 0 };
                  const sharedVal = alloc.shared || 0;
                  const dedicatedVal = alloc.dedicated || 0;
                  const totalForAgent = sharedVal + dedicatedVal;
                  const isActive = totalForAgent > 0;

                  // Trigger tool adequacy fetch lazily when an agent becomes active
                  if (isActive && token && !adequacyFetchedRef.current[agent.id]) {
                    fetchToolAdequacy(agent.id);
                  }

                  // Determine if we can still increase each type
                  const canAddShared = sharedRemaining > 0;
                  const canAddDedicated = dedicatedRemaining > 0;

                  const spec = agent.specialization || 'Development';
                  const adequacy = toolAdequacy[agent.id];



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

                            {/* Tool Adequacy Status Badge & Picker */}
                            <div className="relative inline-flex items-center gap-1">
                              {isActive && (
                                !adequacy ? (
                                  <span className="inline-flex items-center gap-1 px-1.5 py-0.5 text-[8px] font-medium rounded-full bg-app-bg-muted text-app-text-muted border border-app-border-light">
                                    <Loader2 className="w-2.5 h-2.5 animate-spin" /> Checking tools...
                                  </span>
                                ) : adequacy.status === 'sufficient' ? (
                                  <span className="inline-flex items-center gap-1 px-1.5 py-0.5 text-[8px] font-bold rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20" title={adequacy.verdict}>
                                    <CheckCircle2 className="w-2.5 h-2.5" /> Tools Verified
                                  </span>
                                ) : adequacy.status === 'warning' ? (
                                  <span className="inline-flex items-center gap-1 px-1.5 py-0.5 text-[8px] font-bold rounded-full bg-amber-500/10 text-amber-400 border border-amber-500/20" title={adequacy.verdict}>
                                    <AlertTriangle className="w-2.5 h-2.5" /> Missing: {(adequacy.missing_recommended || []).join(', ')}
                                  </span>
                                ) : (
                                  <span className="inline-flex items-center gap-1 px-1.5 py-0.5 text-[8px] font-bold rounded-full bg-red-500/10 text-red-400 border border-red-500/20 animate-pulse" title={adequacy.verdict}>
                                    <AlertTriangle className="w-2.5 h-2.5" /> Critical Missing: {(adequacy.missing_required || []).join(', ')}
                                  </span>
                                )
                              )}

                              <button
                                type="button"
                                onClick={() => setToolPickerOpen(toolPickerOpen === agent.id ? null : agent.id)}
                                className={`inline-flex items-center gap-0.5 px-1.5 py-0.5 text-[8px] font-bold rounded border transition-colors ${
                                  isActive && adequacy?.status === 'critical'
                                    ? 'border-red-500/30 bg-red-500/15 text-red-300 hover:bg-red-500/25'
                                    : isActive && adequacy?.status === 'warning'
                                    ? 'border-amber-500/30 bg-amber-500/15 text-amber-300 hover:bg-amber-500/25'
                                    : 'border-app-border-light bg-app-bg-muted/40 text-app-text-muted hover:text-app-text-main hover:bg-app-bg-muted'
                                }`}
                                title="Assign or modify agent tools"
                              >
                                <Wrench className="w-2.5 h-2.5" />
                                {isActive && adequacy?.status === 'critical'
                                  ? 'Add Missing Tools'
                                  : isActive && adequacy?.status === 'warning'
                                  ? 'Add Tools'
                                  : 'Tools'}
                              </button>

                              {toolPickerOpen === agent.id && (
                                <AgentToolPicker
                                  agentId={agent.id}
                                  agentName={agent.name}
                                  agentLane={agent.lane || (agent.skills_tags && agent.skills_tags[0])}
                                  agentRole={agent.name || agent.role}
                                  currentTools={agent.allowed_tools || []}
                                  missingTools={
                                    adequacy?.status === 'critical'
                                      ? (adequacy.missing_required || [])
                                      : (adequacy?.missing_recommended || [])
                                  }
                                  mandatoryTools={
                                    adequacy?.required_tools ||
                                    getMandatoryToolsForAgent(agent)
                                  }
                                  token={token}
                                  onClose={() => setToolPickerOpen(null)}
                                  onUpdate={(newTools) => {
                                    setAgents(prev => prev.map(a => a.id === agent.id ? { ...a, allowed_tools: newTools } : a));
                                    delete adequacyFetchedRef.current[agent.id];
                                    fetchToolAdequacy(agent.id);
                                  }}
                                />
                              )}
                            </div>
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

          {/* Critical Tool Gap Advisory Notice */}
          {hasCriticalToolGap && (
            <div className="p-2.5 rounded-lg bg-red-500/10 border border-red-500/30 flex items-start gap-2 text-xs text-red-400 animate-in fade-in duration-200 shadow-xs">
              <AlertTriangle className="w-4 h-4 shrink-0 text-red-400 mt-0.5" />
              <div>
                <p className="font-bold">Missing Required Tools Detected</p>
                <p className="text-[10px] text-red-300 mt-0.5 leading-relaxed">
                  One or more allocated agents are missing required tools for their tasks. Use the <span className="font-semibold underline">"Add Missing Tools"</span> button on the agent card to attach them. The Master Agent will abort container execution at runtime if critical tools remain missing.
                </p>
              </div>
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
          setCapacityRequestNotice(
            isOrgAdmin
              ? 'Capacity Increase Request submitted to Super Admin successfully.'
              : 'Capacity notification submitted to Organization Admin successfully.'
          );
        }}
      />
      {/* System Prompt Inspection & Editing Modal */}
      {selectedPromptAgentIndex !== null && recommendations && recommendations[selectedPromptAgentIndex] && (
        <div className="fixed inset-0 z-[500] flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm animate-in fade-in duration-200">
          <div className="bg-app-bg-card border border-app-border-light rounded-xl shadow-2xl w-full max-w-2xl flex flex-col max-h-[85vh] overflow-hidden">
            {/* Header */}
            <div className="flex items-center justify-between p-4 border-b border-app-border-light">
              <div className="flex items-center gap-2">
                <FileText className="w-4 h-4 text-app-primary" />
                <div>
                  <h3 className="text-sm font-bold text-app-text-main">
                    {recommendations[selectedPromptAgentIndex].role} — System Prompt
                  </h3>
                  <p className="text-[11px] text-app-text-muted">
                    Bespoke role instructions synthesized by AI based on BRD & architecture blueprints
                  </p>
                </div>
              </div>
              <button
                type="button"
                onClick={() => setSelectedPromptAgentIndex(null)}
                className="p-1 rounded-md text-app-text-muted hover:text-app-text-main hover:bg-app-bg-muted transition-colors"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            {/* Content */}
            <div className="p-4 flex-1 overflow-y-auto space-y-3">
              <div className="flex items-center justify-between text-[11px] text-app-text-muted">
                <span>Markdown instructions injected into container at startup:</span>
                <span className="font-mono text-[10px] px-1.5 py-0.5 rounded bg-app-bg-muted border border-app-border-light">
                  Lane: {recommendations[selectedPromptAgentIndex].lane}
                </span>
              </div>
              <textarea
                value={editingPromptText}
                onChange={(e) => setEditingPromptText(e.target.value)}
                rows={16}
                className="w-full p-3 font-mono text-xs rounded-lg border border-app-border-light bg-app-bg-muted/40 text-app-text-main focus:outline-none focus:ring-1 focus:ring-app-primary resize-y"
                placeholder="# System Prompt..."
              />
            </div>

            {/* Footer */}
            <div className="flex items-center justify-end gap-2 p-3 border-t border-app-border-light bg-app-bg-muted/10">
              <button
                type="button"
                onClick={() => setSelectedPromptAgentIndex(null)}
                className="px-3 py-1.5 text-xs font-medium rounded-lg text-app-text-muted hover:text-app-text-main hover:bg-app-bg-card transition-colors"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleSavePrompt}
                className="inline-flex items-center gap-1.5 px-3.5 py-1.5 text-xs font-bold rounded-lg bg-app-primary text-white hover:bg-app-primary/90 transition-colors shadow-sm"
              >
                <CheckCircle2 className="w-3.5 h-3.5" />
                Save Instructions
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}