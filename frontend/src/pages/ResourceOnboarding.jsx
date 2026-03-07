// Resource Onboarding page
import React, { useEffect, useMemo, useState } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { ArrowRight, CheckCircle2, Loader2, Bot, Users, AlertTriangle, Minus, Plus } from 'lucide-react';
import { API_ENDPOINTS } from '../config';

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
    // Best effort: decode expiry if missing.
    const exp = decodeJwtExpiry(entry.token);
    if (exp && exp <= Math.floor(Date.now() / 1000)) return null;
  }
  return entry.token;
}

export default function ResourceOnboarding({ selectedProjectKey, fetchHistory }) {
  const navigate = useNavigate();
  const location = useLocation();
  const processMode = location.state?.processMode || 'ai_first';
  const token = localStorage.getItem('token');

  const [agentType, setAgentType] = useState('shared'); // shared or dedicated (UI emphasis)
  const [sharedRequested, setSharedRequested] = useState(0);
  const [dedicatedRequested, setDedicatedRequested] = useState(0);

  const [_isLoadingExisting, setIsLoadingExisting] = useState(false);
  const [existingError, setExistingError] = useState('');
  const [existingSharedAgents, setExistingSharedAgents] = useState([]);
  const [existingDedicatedAgents, setExistingDedicatedAgents] = useState([]);

  const [submitError, setSubmitError] = useState('');
  const [submitWarning, setSubmitWarning] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [quota, setQuota] = useState(null);
  const [quotaError, setQuotaError] = useState('');
  const [quotaLoading, setQuotaLoading] = useState(false);

  const taskToken = useMemo(() => getCachedTaskToken(selectedProjectKey), [selectedProjectKey]);
  const hasValidTaskToken = Boolean(taskToken);

  const existingSharedCount = existingSharedAgents.length;
  const existingDedicatedCount = existingDedicatedAgents.length;
  const sharedAvailableCount = Number(quota?.shared_available ?? 0);
  const dedicatedQuotaCount = Number(quota?.dedicated_quota ?? 0);
  const dedicatedAvailableCount = selectedProjectKey
    ? Math.max(0, dedicatedQuotaCount - existingDedicatedCount)
    : Number(quota?.dedicated_available ?? 0);

  const clampCount = (value) => {
    const n = Number(value);
    if (!Number.isFinite(n)) return 0;
    return Math.max(0, Math.min(50, Math.floor(n)));
  };

  useEffect(() => {
    let isMounted = true;
    const controller = new AbortController();

    const fetchExisting = async () => {
      if (!token) return;
      setIsLoadingExisting(true);
      setExistingError('');
      try {
        const headers = { Authorization: `Bearer ${token}` };

        const sharedUrl = new URL(API_ENDPOINTS.AGENTS);
        const dedicatedUrl = new URL(API_ENDPOINTS.AGENTS);
        sharedUrl.searchParams.set('include_defaults', 'false');
        sharedUrl.searchParams.set('kind', 'shared');
        dedicatedUrl.searchParams.set('include_defaults', 'false');
        dedicatedUrl.searchParams.set('kind', 'dedicated');
        if (selectedProjectKey) sharedUrl.searchParams.set('project_token', selectedProjectKey);
        if (selectedProjectKey) dedicatedUrl.searchParams.set('project_token', selectedProjectKey);

        const [sharedRes, dedicatedRes] = await Promise.all([
          fetch(sharedUrl.toString(), { headers, signal: controller.signal }),
          fetch(dedicatedUrl.toString(), { headers, signal: controller.signal }),
        ]);

        if (!sharedRes.ok) throw new Error('Failed to load shared agents');
        if (!dedicatedRes.ok) throw new Error('Failed to load dedicated agents');

        const sharedJson = await sharedRes.json();
        const dedicatedJson = await dedicatedRes.json();

        if (!isMounted) return;
        setExistingSharedAgents(Array.isArray(sharedJson?.agents) ? sharedJson.agents : []);
        setExistingDedicatedAgents(Array.isArray(dedicatedJson?.agents) ? dedicatedJson.agents : []);
      } catch (e) {
        if (!isMounted) return;
        if (e?.name === 'AbortError') return;
        setExistingError(e?.message || 'Failed to load existing agents');
      } finally {
        if (isMounted) setIsLoadingExisting(false);
      }
    };

    fetchExisting();
    return () => {
      isMounted = false;
      controller.abort();
    };
  }, [token, selectedProjectKey]);

  useEffect(() => {
    let isMounted = true;
    const controller = new AbortController();

    const fetchQuota = async () => {
      if (!token) return;
      setQuotaLoading(true);
      setQuotaError('');
      try {
        const res = await fetch(API_ENDPOINTS.ORG_AGENT_QUOTA, {
          headers: { Authorization: `Bearer ${token}` },
          signal: controller.signal,
        });
        const json = await res.json().catch(() => ({}));
        if (!res.ok) {
          throw new Error(json.detail || 'Failed to load organization capacity');
        }
        if (isMounted) setQuota(json);
      } catch (e) {
        if (!isMounted) return;
        if (e?.name === 'AbortError') return;
        setQuotaError(e?.message || 'Failed to load organization capacity');
      } finally {
        if (isMounted) setQuotaLoading(false);
      }
    };

    fetchQuota();
    return () => {
      isMounted = false;
      controller.abort();
    };
  }, [token]);

  const handleSubmit = async () => {
    setIsSubmitting(true);
    setSubmitError('');
    setSubmitWarning('');

    try {
      const sharedToCreate = clampCount(sharedRequested);
      const dedicatedToCreate = clampCount(dedicatedRequested);

      if (quota) {
        const sharedAvailable = Number(quota.shared_available ?? 0);
        const dedicatedAvailable = dedicatedAvailableCount;
        if (sharedToCreate > sharedAvailable) {
          setSubmitError(`Shared agent capacity exceeded. Available: ${sharedAvailable}. Please add more Shared agents from Agents page.`);
          return;
        }
        if (dedicatedToCreate > dedicatedAvailable) {
          setSubmitError(`Dedicated agent capacity exceeded. Available: ${dedicatedAvailable}. Please add more Dedicated agents from Agents page.`);
          return;
        }
      }

      // Only show error if no agents selected AND no agents already exist for this project
      if (sharedToCreate === 0 && dedicatedToCreate === 0 && existingSharedCount === 0 && existingDedicatedCount === 0) {
        setSubmitError('Please select how many Shared and/or Dedicated agents you want to add.');
        return;
      }

      if ((sharedToCreate > 0 || dedicatedToCreate > 0) && !selectedProjectKey) {
        setSubmitError('Select a project before creating dev agents.');
        return;
      }

      if (!token) {
        setSubmitError('You are not logged in. Please login again.');
        return;
      }

      const headers = {
        Authorization: `Bearer ${token}`,
        'Content-Type': 'application/json',
      };

      if (hasValidTaskToken) {
        headers['x-task-token'] = taskToken;
      } else {
        setSubmitWarning('Task token is not ready. Agents will still be created locally, but upstream agent provisioning may be delayed.');
      }

      const warnings = [];

      const createOne = async (kind, projectToken) => {
        const url = new URL(API_ENDPOINTS.AGENT_ADD);
        if (projectToken) url.searchParams.set('project_token', projectToken);
        const res = await fetch(url.toString(), {
          method: 'POST',
          headers,
          body: JSON.stringify({ name: null, kind }),
        });
        const json = await res.json().catch(() => ({}));
        if (!res.ok) {
          const msg = json?.detail || json?.error || 'Failed to create agent';
          throw new Error(msg);
        }
        if (json?.external_agent_warning) warnings.push(json.external_agent_warning);
        return json?.agent || null;
      };

      // Create shared-capacity dev agents for this project.
      for (let i = 0; i < sharedToCreate; i += 1) {
        await createOne('shared', selectedProjectKey);
      }
      // Create dedicated-capacity dev agents for this project.
      for (let i = 0; i < dedicatedToCreate; i += 1) {
        await createOne('dedicated', selectedProjectKey);
      }

      if (warnings.length > 0) {
        setSubmitWarning((prev) => prev || `Created agents, but upstream provisioning returned warnings: ${warnings.slice(0, 2).join(' | ')}${warnings.length > 2 ? '…' : ''}`);
      }

      // Refresh existing counts and quota for the UI, then go to dashboard.
      try {
        const agentsHeaders = { Authorization: `Bearer ${token}` };
        const sharedUrl = new URL(API_ENDPOINTS.AGENTS);
        const dedicatedUrl = new URL(API_ENDPOINTS.AGENTS);
        sharedUrl.searchParams.set('include_defaults', 'false');
        sharedUrl.searchParams.set('kind', 'shared');
        dedicatedUrl.searchParams.set('include_defaults', 'false');
        dedicatedUrl.searchParams.set('kind', 'dedicated');
        if (selectedProjectKey) sharedUrl.searchParams.set('project_token', selectedProjectKey);
        if (selectedProjectKey) dedicatedUrl.searchParams.set('project_token', selectedProjectKey);
        const [sharedRes, dedicatedRes, quotaRes] = await Promise.all([
          fetch(sharedUrl.toString(), { headers: agentsHeaders }),
          fetch(dedicatedUrl.toString(), { headers: agentsHeaders }),
          fetch(API_ENDPOINTS.ORG_AGENT_QUOTA, { headers: agentsHeaders }),
        ]);
        const sharedJson = sharedRes.ok ? await sharedRes.json() : null;
        const dedicatedJson = dedicatedRes.ok ? await dedicatedRes.json() : null;
        const quotaJson = quotaRes.ok ? await quotaRes.json() : null;
        setExistingSharedAgents(Array.isArray(sharedJson?.agents) ? sharedJson.agents : existingSharedAgents);
        setExistingDedicatedAgents(Array.isArray(dedicatedJson?.agents) ? dedicatedJson.agents : existingDedicatedAgents);
        if (quotaJson) setQuota(quotaJson);
      } catch {
        // ignore refresh errors
      }

      if (typeof fetchHistory === 'function') {
        fetchHistory();
      }
      navigate('/status-dashboard', { state: { processMode } });
    } catch (e) {
      setSubmitError(e?.message || 'Failed to complete onboarding');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="h-full overflow-y-auto bg-gradient-to-br from-slate-50 via-gray-50 to-blue-50/30">
      <div className="max-w-3xl mx-auto px-4 py-10">
        <div className="bg-white rounded-2xl border border-app-border-light shadow-sm p-6 sm:p-8 space-y-6">
          <div className="flex items-start justify-between gap-4">
            <div>
              <p className="text-xs font-semibold uppercase tracking-widest text-app-text-muted">AI Resource Setup</p>
              <h2 className="text-2xl sm:text-3xl font-extrabold text-app-text-main mt-1">Resource Onboarding</h2>
              <p className="text-sm sm:text-base text-app-text-muted mt-2 max-w-2xl">
                Select how many dev agents you want for this project. Shared and dedicated capacity both create dev agents, while Master Agent and Git Manager stay available by default.
              </p>
            </div>
            <div className="hidden sm:flex flex-col items-end gap-1 text-xs text-app-text-muted">
              <span className="inline-flex items-center gap-1 px-2 py-1 rounded-full bg-emerald-50 border border-emerald-200 text-emerald-700 font-semibold">
                <Bot className="w-3 h-3" />
                {processMode === 'ai_assist' ? 'AI Assist Mode' : 'AI First Mode'}
              </span>
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <button
              type="button"
              onClick={() => setAgentType('shared')}
              className={`w-full text-left rounded-xl border px-4 py-4 flex flex-col gap-2 transition-all ${
                agentType === 'shared'
                  ? 'border-emerald-500 bg-emerald-50/60 shadow-[0_0_0_1px_rgba(16,185,129,0.35)]'
                  : 'border-app-border-light bg-app-bg-muted hover:border-emerald-400 hover:bg-emerald-50/40'
              }`}
            >
              <div className="flex items-center gap-2">
                <Users className={`w-5 h-5 ${agentType === 'shared' ? 'text-emerald-600' : 'text-app-text-muted'}`} />
                <p className="font-semibold text-app-text-main">Shared Agent</p>
                <span className="ml-auto text-[11px] font-bold px-2 py-1 rounded-full border border-app-border-light bg-white text-app-text-muted">
                  Available: {quotaLoading ? '…' : sharedAvailableCount}
                </span>
              </div>
              <p className="text-xs text-app-text-muted">
                Uses shared organization capacity to add dev agents that can be reused across projects.
              </p>
              {existingSharedCount > 0 && (
                <p className="text-[11px] font-semibold text-emerald-700 mt-1">
                  {existingSharedCount} already added for this project
                </p>
              )}
              <div className="mt-1 flex items-center justify-between">
                <p className="text-[11px] font-semibold text-app-text-muted">Add more shared agents</p>
                <div className="inline-flex items-center gap-2">
                  <button
                    type="button"
                    onClick={(e) => {
                      e.preventDefault();
                      e.stopPropagation();
                      setSharedRequested((v) => clampCount(v - 1));
                    }}
                    className="w-8 h-8 inline-flex items-center justify-center rounded-lg border border-app-border-light bg-white hover:bg-app-bg-hover text-app-text-main"
                    aria-label="Decrease shared agent count"
                  >
                    <Minus className="w-4 h-4" />
                  </button>
                  <input
                    value={sharedRequested}
                    onChange={(e) => setSharedRequested(clampCount(e.target.value))}
                    onClick={(e) => {
                      e.preventDefault();
                      e.stopPropagation();
                    }}
                    className="w-16 h-8 text-center rounded-lg border border-app-border-light bg-white text-sm font-bold text-app-text-main"
                    inputMode="numeric"
                  />
                  <button
                    type="button"
                    onClick={(e) => {
                      e.preventDefault();
                      e.stopPropagation();
                      setSharedRequested((v) => clampCount(v + 1));
                    }}
                    className="w-8 h-8 inline-flex items-center justify-center rounded-lg border border-app-border-light bg-white hover:bg-app-bg-hover text-app-text-main"
                    aria-label="Increase shared agent count"
                  >
                    <Plus className="w-4 h-4" />
                  </button>
                </div>
              </div>
            </button>

            <button
              type="button"
              onClick={() => setAgentType('dedicated')}
              className={`w-full text-left rounded-xl border px-4 py-4 flex flex-col gap-2 transition-all ${
                agentType === 'dedicated'
                  ? 'border-emerald-500 bg-emerald-50/60 shadow-[0_0_0_1px_rgba(16,185,129,0.35)]'
                  : 'border-app-border-light bg-app-bg-muted hover:border-emerald-400 hover:bg-emerald-50/40'
              }`}
            >
              <div className="flex items-center gap-2">
                <Bot className={`w-5 h-5 ${agentType === 'dedicated' ? 'text-emerald-600' : 'text-app-text-muted'}`} />
                <p className="font-semibold text-app-text-main">Dedicated Agent</p>
                <span className="ml-auto text-[11px] font-bold px-2 py-1 rounded-full border border-app-border-light bg-white text-app-text-muted">
                  Available: {quotaLoading ? '…' : dedicatedAvailableCount}
                </span>
              </div>
              <p className="text-xs text-app-text-muted">
                Uses dedicated organization capacity to add dev agents only for this project.
              </p>
              {existingDedicatedCount > 0 && (
                <p className="text-[11px] font-semibold text-blue-700 mt-1">
                  {existingDedicatedCount} already added for this project
                </p>
              )}
              <div className="mt-1 flex items-center justify-between">
                <p className="text-[11px] font-semibold text-app-text-muted">Add more dedicated agents</p>
                <div className="inline-flex items-center gap-2">
                  <button
                    type="button"
                    onClick={(e) => {
                      e.preventDefault();
                      e.stopPropagation();
                      setDedicatedRequested((v) => clampCount(v - 1));
                    }}
                    className="w-8 h-8 inline-flex items-center justify-center rounded-lg border border-app-border-light bg-white hover:bg-app-bg-hover text-app-text-main"
                    aria-label="Decrease dedicated agent count"
                  >
                    <Minus className="w-4 h-4" />
                  </button>
                  <input
                    value={dedicatedRequested}
                    onChange={(e) => setDedicatedRequested(clampCount(e.target.value))}
                    onClick={(e) => {
                      e.preventDefault();
                      e.stopPropagation();
                    }}
                    className="w-16 h-8 text-center rounded-lg border border-app-border-light bg-white text-sm font-bold text-app-text-main"
                    inputMode="numeric"
                  />
                  <button
                    type="button"
                    onClick={(e) => {
                      e.preventDefault();
                      e.stopPropagation();
                      setDedicatedRequested((v) => clampCount(v + 1));
                    }}
                    className="w-8 h-8 inline-flex items-center justify-center rounded-lg border border-app-border-light bg-white hover:bg-app-bg-hover text-app-text-main"
                    aria-label="Increase dedicated agent count"
                  >
                    <Plus className="w-4 h-4" />
                  </button>
                </div>
              </div>
            </button>
          </div>

          {existingError && (
            <div className="text-xs text-amber-800 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2 flex items-start gap-2">
              <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" />
              <span>{existingError}</span>
            </div>
          )}

          {(quotaLoading || quotaError || quota) && (
            <div className="rounded-xl border border-app-border-light bg-app-bg-muted px-4 py-3">
              <p className="text-xs font-bold text-app-text-main">Organization capacity</p>
              {quotaLoading && (
                <p className="text-[11px] text-app-text-muted mt-1">Loading capacity…</p>
              )}
              {quotaError && !quotaLoading && (
                <p className="text-[11px] text-amber-700 mt-1">{quotaError}</p>
              )}
              {quota && !quotaLoading && (
                <p className="text-[11px] text-app-text-muted mt-1">
                  Shared available: <span className="font-semibold text-app-text-main">{quota.shared_available ?? 0}</span> · Dedicated available:{' '}
                  <span className="font-semibold text-app-text-main">{dedicatedAvailableCount}</span>
                </p>
              )}
              <div className="mt-2">
                <button
                  type="button"
                  onClick={() => navigate('/agents')}
                  className="text-xs font-bold text-app-primary hover:underline"
                >
                  Add more agents in Organization →
                </button>
              </div>
            </div>
          )}

          {agentType === 'shared' && existingSharedCount > 0 && (
            <div className="rounded-xl border border-app-border-light bg-app-bg-muted px-4 py-3">
              <p className="text-xs font-bold text-app-text-main">Shared agents already created (org-wide)</p>
              <p className="text-[11px] text-app-text-muted mt-1">
                These shared agents can work across <span className="font-semibold text-app-text-main">all projects</span> in this organization.
              </p>
              <div className="mt-2 flex flex-wrap gap-2">
                {existingSharedAgents.slice(0, 12).map((agent) => (
                  <span
                    key={agent.id}
                    className="text-[11px] font-semibold px-2 py-1 rounded-full border border-app-border-light bg-white text-app-text-main"
                    title={agent.status ? `Status: ${agent.status}` : undefined}
                  >
                    {agent.name || agent.id}
                  </span>
                ))}
                {existingSharedAgents.length > 12 && (
                  <span className="text-[11px] font-semibold px-2 py-1 rounded-full border border-app-border-light bg-white text-app-text-muted">
                    +{existingSharedAgents.length - 12} more
                  </span>
                )}
              </div>
            </div>
          )}

          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pt-2 border-t border-app-border-light">
            <div className="text-xs text-app-text-muted space-y-1">
              <p className="font-semibold text-app-text-main">What happens next?</p>
              <ul className="list-disc list-inside space-y-0.5">
                <li>We create exactly the number of dev agents you selected, as long as it is within available capacity.</li>
                <li>The Status Dashboard will use this configuration for all future runs.</li>
              </ul>
            </div>
            <button
              onClick={handleSubmit}
              disabled={isSubmitting}
              className={`inline-flex items-center justify-center gap-2 px-5 py-2.5 text-sm font-bold text-white bg-gradient-to-r from-emerald-500 to-green-600 rounded-lg shadow hover:shadow-lg transition-all ${
                isSubmitting ? 'opacity-50 cursor-not-allowed' : ''
              }`}
            >
              {isSubmitting ? <Loader2 className="w-4 h-4 animate-spin" /> : <CheckCircle2 className="w-4 h-4" />}
              {isSubmitting ? 'Onboarding...' : 'Complete Onboarding'}
              <ArrowRight className="w-4 h-4" />
            </button>
          </div>

          {submitError && (
            <div className="text-xs text-red-700 bg-red-50 border border-red-200 rounded-lg px-3 py-2">
              {submitError}
            </div>
          )}
          {submitWarning && (
            <div className="text-xs text-amber-800 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2 flex items-start gap-2">
              <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" />
              <span>{submitWarning}</span>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
