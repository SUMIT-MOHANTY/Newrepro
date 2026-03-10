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

  const [sharedDevRequested, setSharedDevRequested] = useState(0);
  const [sharedTestRequested, setSharedTestRequested] = useState(0);
  const [dedicatedDevRequested, setDedicatedDevRequested] = useState(0);
  const [dedicatedTestRequested, setDedicatedTestRequested] = useState(0);

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
        const parse = (json) => Array.isArray(json?.agents) ? json.agents : (Array.isArray(json) ? json : []);

        const fetchAgentList = (kind, projectToken) => {
          const url = new URL(API_ENDPOINTS.AGENTS);
          url.searchParams.set('kind', kind);
          url.searchParams.set('include_defaults', 'false');
          if (projectToken) url.searchParams.set('project_token', projectToken);
          return fetch(url.toString(), { headers, signal: controller.signal })
            .then(r => r.ok ? r.json().then(parse) : [])
            .catch(() => []);
        };

        // Project-level: agents used by THIS project
        const [projShared, projDedicated] = await Promise.all([
          fetchAgentList('shared', selectedProjectKey),
          fetchAgentList('dedicated', selectedProjectKey),
        ]);

        if (!isMounted) return;
        setExistingSharedAgents(projShared);
        setExistingDedicatedAgents(projDedicated);
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
      const sDevCount = clampCount(sharedDevRequested);
      const sTestCount = clampCount(sharedTestRequested);
      const dDevCount = clampCount(dedicatedDevRequested);
      const dTestCount = clampCount(dedicatedTestRequested);

      const totalToCreate = sDevCount + sTestCount + dDevCount + dTestCount;

      if (quota) {
        const sDevAvail = Math.max(0, Number(quota.shared_dev_quota ?? 0) - existingSharedAgents.filter(a => !a.sub_type || a.sub_type === 'dev').length);
        const sTestAvail = Math.max(0, Number(quota.shared_test_quota ?? 0) - existingSharedAgents.filter(a => a.sub_type === 'test').length);
        const dDevAvail = Math.max(0, Number(quota.dedicated_dev_quota ?? 0) - existingDedicatedAgents.filter(a => !a.sub_type || a.sub_type === 'dev').length);
        const dTestAvail = Math.max(0, Number(quota.dedicated_test_quota ?? 0) - existingDedicatedAgents.filter(a => a.sub_type === 'test').length);

        if (sDevCount > sDevAvail) {
          setSubmitError(`Shared Dev capacity exceeded. Available: ${sDevAvail}.`);
          setIsSubmitting(false);
          return;
        }
        if (sTestCount > sTestAvail) {
          setSubmitError(`Shared Test capacity exceeded. Available: ${sTestAvail}.`);
          setIsSubmitting(false);
          return;
        }
        if (dDevCount > dDevAvail) {
          setSubmitError(`Dedicated Dev capacity exceeded. Available: ${dDevAvail}.`);
          setIsSubmitting(false);
          return;
        }
        if (dTestCount > dTestAvail) {
          setSubmitError(`Dedicated Test capacity exceeded. Available: ${dTestAvail}.`);
          setIsSubmitting(false);
          return;
        }
      }

      if (totalToCreate === 0 && existingSharedCount === 0 && existingDedicatedCount === 0) {
        setSubmitError('Please select agents to add.');
        setIsSubmitting(false);
        return;
      }

      if (totalToCreate > 0 && !selectedProjectKey) {
        setSubmitError('Select a project before creating dev agents.');
        setIsSubmitting(false);
        return;
      }

      if (!token) {
        setSubmitError('You are not logged in. Please login again.');
        setIsSubmitting(false);
        return;
      }

      const headers = {
        Authorization: `Bearer ${token}`,
        'Content-Type': 'application/json',
      };

      if (hasValidTaskToken) {
        headers['x-task-token'] = taskToken;
      }

      const createOne = async (kind, subType, projectToken) => {
        const url = new URL(API_ENDPOINTS.AGENT_ADD);
        if (projectToken) url.searchParams.set('project_token', projectToken);
        try {
          const res = await fetch(url.toString(), {
            method: 'POST',
            headers,
            body: JSON.stringify({ name: null, kind, sub_type: subType }),
          });
          const json = await res.json().catch(() => ({}));
          if (!res.ok) {
            const errorMsg = json?.detail || json?.error || '';
            // If agent already exists, that's fine - just continue silently
            if (errorMsg.toLowerCase().includes('already exists') || 
                errorMsg.toLowerCase().includes('user with username')) {
              return json?.agent || null;
            }
            // For other errors, log but don't fail the whole process
            console.warn(`Agent creation warning: ${errorMsg}`);
            return json?.agent || null;
          }
          return json?.agent || null;
        } catch (err) {
          // Log but don't fail - agent might already exist or other non-critical issue
          console.warn(`Agent creation warning: ${err.message}`);
          return null;
        }
      };

      // Create agents sequentially
      for (let i = 0; i < sDevCount; i++) await createOne('shared', 'dev', selectedProjectKey);
      for (let i = 0; i < sTestCount; i++) await createOne('shared', 'test', selectedProjectKey);
      for (let i = 0; i < dDevCount; i++) await createOne('dedicated', 'dev', selectedProjectKey);
      for (let i = 0; i < dTestCount; i++) await createOne('dedicated', 'test', selectedProjectKey);

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
    <div className="h-full overflow-y-auto bg-gradient-to-br from-app-bg-page via-app-bg-page to-app-primary-light/30">
      <div className="max-w-3xl mx-auto px-4 py-10">
        <div className="bg-app-bg-card rounded-2xl border border-app-border-light shadow-sm p-6 sm:p-8 space-y-6">
          <div className="flex items-start justify-between gap-4">
            <div>
              <p className="text-xs font-semibold uppercase tracking-widest text-app-text-muted">AI Resource Setup</p>
              <h2 className="text-2xl sm:text-3xl font-extrabold text-app-text-main mt-1">Resource Onboarding</h2>
              <p className="text-sm sm:text-base text-app-text-muted mt-2 max-w-2xl">
                Select how many dev agents you want for this project. Shared and dedicated capacity both create dev agents, while Master Agent and Git Manager stay available by default.
              </p>
            </div>
            <div className="hidden sm:flex flex-col items-end gap-1 text-xs text-app-text-muted">
              <span className="inline-flex items-center gap-1 px-2 py-1 rounded-full bg-app-status-successBg border border-emerald-200 text-app-status-success font-semibold">
                <Bot className="w-3 h-3" />
                {processMode === 'ai_assist' ? 'AI Assist Mode' : 'AI First Mode'}
              </span>
            </div>
          </div>

          {/* Capacity selection – grouped by Dev vs Test, each showing Shared & Dedicated */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {/* Dev Agents card */}
            <div className="w-full text-left rounded-xl border px-4 py-4 flex flex-col gap-4 transition-all border-app-border-light bg-app-bg-muted">
              <div className="flex items-center gap-2">
                <Users className="w-5 h-5 text-app-status-success" />
                <p className="font-semibold text-app-text-main">Dev Agents</p>
                <div className="ml-auto flex gap-1">
                  <span className="text-[10px] bg-app-bg-card border border-app-border-light px-2 py-0.5 rounded-full text-app-text-muted">
                    Shared Avail: {quotaLoading ? '…' : Math.max(0, (quota?.shared_dev_quota ?? 0) - existingSharedAgents.filter(a => !a.sub_type || a.sub_type === 'dev').length)}
                  </span>
                  <span className="text-[10px] bg-app-bg-card border border-app-border-light px-2 py-0.5 rounded-full text-app-text-muted">
                    Dedicated Avail: {quotaLoading ? '…' : Math.max(0, (quota?.dedicated_dev_quota ?? 0) - existingDedicatedAgents.filter(a => !a.sub_type || a.sub_type === 'dev').length)}
                  </span>
                </div>
              </div>

              <div className="space-y-3">
                {/* Shared Dev Counter */}
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <div className="w-2 h-2 rounded-full bg-emerald-500"></div>
                    <span className="text-xs font-medium text-app-text-main">Shared Dev Agents</span>
                  </div>
                  <div className="inline-flex items-center gap-2">
                    <button
                      type="button"
                      onClick={() => setSharedDevRequested(v => clampCount(v - 1))}
                      className="w-8 h-8 flex items-center justify-center rounded-lg border border-app-border-light bg-app-bg-card hover:bg-app-bg-hover transition-colors"
                    >
                      <Minus className="w-4 h-4" />
                    </button>
                    <input
                      value={sharedDevRequested}
                      onChange={e => setSharedDevRequested(clampCount(e.target.value))}
                      className="w-12 h-8 text-center rounded-lg border border-app-border-light bg-app-bg-card text-sm font-bold"
                    />
                    <button
                      type="button"
                      onClick={() => setSharedDevRequested(v => clampCount(v + 1))}
                      className="w-8 h-8 flex items-center justify-center rounded-lg border border-app-border-light bg-app-bg-card hover:bg-app-bg-hover transition-colors"
                    >
                      <Plus className="w-4 h-4" />
                    </button>
                  </div>
                </div>

                {/* Dedicated Dev Counter */}
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <div className="w-2 h-2 rounded-full bg-cyan-500"></div>
                    <span className="text-xs font-medium text-app-text-main">Dedicated Dev Agents</span>
                  </div>
                  <div className="inline-flex items-center gap-2">
                    <button
                      type="button"
                      onClick={() => setDedicatedDevRequested(v => clampCount(v - 1))}
                      className="w-8 h-8 flex items-center justify-center rounded-lg border border-app-border-light bg-app-bg-card hover:bg-app-bg-hover transition-colors"
                    >
                      <Minus className="w-4 h-4" />
                    </button>
                    <input
                      value={dedicatedDevRequested}
                      onChange={e => setDedicatedDevRequested(clampCount(e.target.value))}
                      className="w-12 h-8 text-center rounded-lg border border-app-border-light bg-app-bg-card text-sm font-bold"
                    />
                    <button
                      type="button"
                      onClick={() => setDedicatedDevRequested(v => clampCount(v + 1))}
                      className="w-8 h-8 flex items-center justify-center rounded-lg border border-app-border-light bg-app-bg-card hover:bg-app-bg-hover transition-colors"
                    >
                      <Plus className="w-4 h-4" />
                    </button>
                  </div>
                </div>
              </div>
            </div>

            {/* Test Agents card */}
            <div className="w-full text-left rounded-xl border px-4 py-4 flex flex-col gap-4 transition-all border-app-border-light bg-app-bg-muted">
              <div className="flex items-center gap-2">
                <Bot className="w-5 h-5 text-app-status-success" />
                <p className="font-semibold text-app-text-main">Test Agents</p>
                <div className="ml-auto flex gap-1">
                  <span className="text-[10px] bg-app-bg-card border border-app-border-light px-2 py-0.5 rounded-full text-app-text-muted">
                    Shared Avail: {quotaLoading ? '…' : Math.max(0, (quota?.shared_test_quota ?? 0) - existingSharedAgents.filter(a => a.sub_type === 'test').length)}
                  </span>
                  <span className="text-[10px] bg-app-bg-card border border-app-border-light px-2 py-0.5 rounded-full text-app-text-muted">
                    Dedicated Avail: {quotaLoading ? '…' : Math.max(0, (quota?.dedicated_test_quota ?? 0) - existingDedicatedAgents.filter(a => a.sub_type === 'test').length)}
                  </span>
                </div>
              </div>

              <div className="space-y-3">
                {/* Shared Test Counter */}
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <div className="w-2 h-2 rounded-full bg-emerald-500"></div>
                    <span className="text-xs font-medium text-app-text-main">Shared Test Agents</span>
                  </div>
                  <div className="inline-flex items-center gap-2">
                    <button
                      type="button"
                      onClick={() => setSharedTestRequested(v => clampCount(v - 1))}
                      className="w-8 h-8 flex items-center justify-center rounded-lg border border-app-border-light bg-app-bg-card hover:bg-app-bg-hover transition-colors"
                    >
                      <Minus className="w-4 h-4" />
                    </button>
                    <input
                      value={sharedTestRequested}
                      onChange={e => setSharedTestRequested(clampCount(e.target.value))}
                      className="w-12 h-8 text-center rounded-lg border border-app-border-light bg-app-bg-card text-sm font-bold"
                    />
                    <button
                      type="button"
                      onClick={() => setSharedTestRequested(v => clampCount(v + 1))}
                      className="w-8 h-8 flex items-center justify-center rounded-lg border border-app-border-light bg-app-bg-card hover:bg-app-bg-hover transition-colors"
                    >
                      <Plus className="w-4 h-4" />
                    </button>
                  </div>
                </div>

                {/* Dedicated Test Counter */}
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <div className="w-2 h-2 rounded-full bg-cyan-500"></div>
                    <span className="text-xs font-medium text-app-text-main">Dedicated Test Agents</span>
                  </div>
                  <div className="inline-flex items-center gap-2">
                    <button
                      type="button"
                      onClick={() => setDedicatedTestRequested(v => clampCount(v - 1))}
                      className="w-8 h-8 flex items-center justify-center rounded-lg border border-app-border-light bg-app-bg-card hover:bg-app-bg-hover transition-colors"
                    >
                      <Minus className="w-4 h-4" />
                    </button>
                    <input
                      value={dedicatedTestRequested}
                      onChange={e => setDedicatedTestRequested(clampCount(e.target.value))}
                      className="w-12 h-8 text-center rounded-lg border border-app-border-light bg-app-bg-card text-sm font-bold"
                    />
                    <button
                      type="button"
                      onClick={() => setDedicatedTestRequested(v => clampCount(v + 1))}
                      className="w-8 h-8 flex items-center justify-center rounded-lg border border-app-border-light bg-app-bg-card hover:bg-app-bg-hover transition-colors"
                    >
                      <Plus className="w-4 h-4" />
                    </button>
                  </div>
                </div>
              </div>
            </div>
          </div>

          {existingError && (
            <div className="text-xs text-amber-800 bg-app-status-warningBg border border-amber-200 rounded-lg px-3 py-2 flex items-start gap-2">
              <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" />
              <span>{existingError}</span>
            </div>
          )}

          {/* Organization capacity summary removed on request */}

          {existingSharedCount > 0 && (
            <div className="rounded-xl border border-app-border-light bg-app-bg-muted px-4 py-3">
              <p className="text-xs font-bold text-app-text-main">Shared agents already created (org-wide)</p>
              <p className="text-[11px] text-app-text-muted mt-1">
                These shared agents can work across <span className="font-semibold text-app-text-main">all projects</span> in this organization.
              </p>
              <div className="mt-2 flex flex-wrap gap-2">
                {existingSharedAgents.slice(0, 12).map((agent) => (
                  <span
                    key={agent.id}
                    className="text-[11px] font-semibold px-2 py-1 rounded-full border border-app-border-light bg-app-bg-card text-app-text-main"
                    title={agent.status ? `Status: ${agent.status}` : undefined}
                  >
                    {agent.name || agent.id}
                  </span>
                ))}
                {existingSharedAgents.length > 12 && (
                  <span className="text-[11px] font-semibold px-2 py-1 rounded-full border border-app-border-light bg-app-bg-card text-app-text-muted">
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
              className={`inline-flex items-center justify-center gap-2 px-5 py-2.5 text-sm font-bold text-white bg-gradient-to-r from-app-status-success to-app-status-success rounded-lg shadow hover:shadow-lg transition-all ${
                isSubmitting ? 'opacity-50 cursor-not-allowed' : ''
              }`}
            >
              {isSubmitting ? <Loader2 className="w-4 h-4 animate-spin" /> : <CheckCircle2 className="w-4 h-4" />}
              {isSubmitting ? 'Onboarding...' : 'Complete Onboarding'}
              <ArrowRight className="w-4 h-4" />
            </button>
          </div>

          {submitError && (
            <div className="text-xs text-app-status-error bg-app-status-errorBg border border-red-200 rounded-lg px-3 py-2">
              {submitError}
            </div>
          )}
          {submitWarning && (
            <div className="text-xs text-amber-800 bg-app-status-warningBg border border-amber-200 rounded-lg px-3 py-2 flex items-start gap-2">
              <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" />
              <span>{submitWarning}</span>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
