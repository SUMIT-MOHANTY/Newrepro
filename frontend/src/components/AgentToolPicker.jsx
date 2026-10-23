/**
 * AgentToolPicker
 * ---------------
 * Inline popover that lets the user view and update an agent's allowed_tools.
 * Shows only the *gap* tools (missing required or recommended) by default, with
 * an option to expand and see the full registry.
 *
 * Mandatory tools (such as filesystem / Read & Write tool for frontend/dev agents)
 * are locked as checked, marked with a lock badge, and cannot be unchecked.
 *
 * Props:
 *   agentId        {string}   – agent DB id
 *   agentName      {string}   – display name
 *   agentLane      {string}   – agent execution lane (frontend, backend, qa, etc.)
 *   agentRole      {string}   – agent role title
 *   currentTools   {string[]} – already-assigned tool list
 *   missingTools   {string[]} – subset to highlight (missing required/recommended)
 *   mandatoryTools {string[]} – tools that cannot be disabled
 *   onUpdate       {fn}       – called with the new tools array after a successful PUT
 *   onClose        {fn}       – called when the picker is closed
 *   token          {string}   – JWT Bearer token
 */
import React, { useState, useMemo, useEffect } from 'react';
import { API_ENDPOINTS } from '../config';
import { Loader2, Wrench, CheckCircle2, AlertTriangle, X, Lock } from 'lucide-react';
import { getMandatoryToolsForAgent } from '../utils/agentToolsHelper';

// Full canonical tool registry with labels and descriptions
export const ALL_TOOLS = [
  { id: 'filesystem',  label: 'File System (Read & Write)',  desc: 'Read/write and edit files across the workspace' },
  { id: 'git',         label: 'Git',                         desc: 'Clone, commit, push, branch operations' },
  { id: 'terminal',    label: 'Terminal',                    desc: 'Execute shell commands' },
  { id: 'build_tool',  label: 'Build Tool',                  desc: 'Compile, bundle and package code' },
  { id: 'test_runner', label: 'Test Runner',                 desc: 'Run unit, integration and e2e tests' },
  { id: 'visual_qa',   label: 'Visual QA',                   desc: 'Browser screenshot / pixel comparison' },
  { id: 'database',    label: 'Database',                    desc: 'Query and migrate SQL/NoSQL databases' },
  { id: 'browser',     label: 'Browser',                     desc: 'Headless browser automation (Playwright)' },
  { id: 'docker',      label: 'Docker',                      desc: 'Build and run Docker containers' },
  { id: 'cloud_cli',   label: 'Cloud CLI',                   desc: 'AWS/GCP/Azure CLI operations' },
  { id: 'web_search',  label: 'Web Search',                  desc: 'Search the web for documentation / context' },
];

export default function AgentToolPicker({
  agentId,
  agentName,
  agentLane,
  agentRole,
  currentTools = [],
  missingTools = [],
  mandatoryTools = [],
  onUpdate,
  onClose,
  token,
}) {
  const mandatorySet = useMemo(() => {
    const list = [
      ...(mandatoryTools || []),
      ...getMandatoryToolsForAgent({ name: agentName, role: agentRole || agentName, lane: agentLane })
    ].map(t => String(t).toLowerCase());
    return new Set(list);
  }, [mandatoryTools, agentName, agentRole, agentLane]);

  const [selected, setSelected] = useState(() => {
    const s = new Set((currentTools || []).map(t => String(t).toLowerCase()));
    mandatorySet.forEach(t => s.add(t));
    return s;
  });
  const [saving, setSaving] = useState(false);
  const [error, setError]   = useState('');
  const [showAll, setShowAll] = useState(false);

  // Keep mandatory tools selected whenever mandatorySet changes
  useEffect(() => {
    setSelected(prev => {
      let changed = false;
      const next = new Set(prev);
      mandatorySet.forEach(t => {
        if (!next.has(t)) {
          next.add(t);
          changed = true;
        }
      });
      return changed ? next : prev;
    });
  }, [mandatorySet]);

  // Decide which tools to show: gap tools & mandatory first; full registry if showAll
  const missingSet = new Set(missingTools.map(t => t.toLowerCase()));
  const displayTools = showAll
    ? ALL_TOOLS
    : ALL_TOOLS.filter(t => missingSet.has(t.id) || selected.has(t.id) || mandatorySet.has(t.id));

  const toggle = (toolId) => {
    const norm = toolId.toLowerCase();
    if (mandatorySet.has(norm)) {
      // Cannot uncheck mandatory tool!
      return;
    }
    setSelected(prev => {
      const next = new Set(prev);
      if (next.has(norm)) next.delete(norm); else next.add(norm);
      return next;
    });
  };

  const handleSave = async () => {
    setSaving(true);
    setError('');
    // Guarantee all mandatory tools are included
    const newTools = Array.from(new Set([...selected, ...mandatorySet]));
    try {
      const res = await fetch(API_ENDPOINTS.AGENT_UPDATE(agentId), {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
        body: JSON.stringify({ tools: newTools }),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || 'Failed to update tools');
      }
      if (typeof onUpdate === 'function') onUpdate(newTools);
      if (typeof onClose === 'function') onClose();
    } catch (err) {
      setError(err.message || 'Update failed');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="absolute z-50 top-full left-0 mt-1 w-80 bg-app-bg-card border border-app-border-light rounded-xl shadow-xl p-3 animate-in fade-in slide-in-from-top-2 duration-150">
      {/* Header */}
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-1.5 min-w-0">
          <Wrench className="w-3.5 h-3.5 text-app-primary shrink-0" />
          <span className="text-[11px] font-bold text-app-text-main truncate">
            Tool Assignment — <span className="text-app-primary">{agentName}</span>
          </span>
        </div>
        <button
          type="button"
          onClick={onClose}
          className="p-0.5 rounded hover:bg-app-bg-muted text-app-text-muted transition-colors shrink-0"
        >
          <X className="w-3 h-3" />
        </button>
      </div>

      {/* Tool list */}
      <div className="space-y-1.5 max-h-60 overflow-y-auto pr-0.5">
        {displayTools.map(tool => {
          const isMandatory = mandatorySet.has(tool.id.toLowerCase());
          const isChecked  = isMandatory || selected.has(tool.id.toLowerCase());
          const isMissing  = missingSet.has(tool.id.toLowerCase());
          return (
            <label
              key={tool.id}
              onClick={(e) => {
                if (isMandatory) {
                  e.preventDefault();
                }
              }}
              className={`flex items-start gap-2 p-1.5 rounded-lg transition-colors border select-none ${
                isMandatory
                  ? 'bg-amber-500/10 border-amber-500/30 cursor-not-allowed'
                  : isChecked
                  ? 'bg-app-primary/8 border-app-primary/25 cursor-pointer'
                  : isMissing
                  ? 'bg-red-500/5 border-red-500/20 hover:bg-red-500/10 cursor-pointer'
                  : 'border-transparent hover:bg-app-bg-muted/30 cursor-pointer'
              }`}
            >
              <input
                type="checkbox"
                className={`mt-0.5 accent-app-primary shrink-0 ${isMandatory ? 'cursor-not-allowed opacity-80' : ''}`}
                checked={isChecked}
                disabled={isMandatory}
                onChange={() => !isMandatory && toggle(tool.id)}
              />
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-1.5 flex-wrap">
                  <span className="text-[11px] font-semibold text-app-text-main">
                    {tool.label}
                  </span>
                  {isMandatory && (
                    <span className="inline-flex items-center gap-0.5 px-1 py-0.2 text-[7.5px] font-bold rounded bg-amber-500/15 text-amber-400 border border-amber-500/30 uppercase tracking-wide">
                      <Lock className="w-2.5 h-2.5" />
                      Mandatory
                    </span>
                  )}
                  {isMissing && !isChecked && (
                    <span className="px-1 py-0.5 text-[8px] font-bold rounded bg-red-500/15 text-red-400 border border-red-500/20 uppercase">
                      Missing
                    </span>
                  )}
                </div>
                <p className="text-[9px] text-app-text-muted leading-snug">
                  {tool.desc}
                  {isMandatory && (
                    <span className="text-amber-400/90 font-medium ml-1">
                      — Required for this role
                    </span>
                  )}
                </p>
              </div>
            </label>
          );
        })}
      </div>

      {/* Toggle show-all */}
      {!showAll && (
        <button
          type="button"
          onClick={() => setShowAll(true)}
          className="mt-1.5 text-[10px] text-app-primary/70 hover:text-app-primary transition-colors w-full text-center"
        >
          Show all {ALL_TOOLS.length} tools
        </button>
      )}

      {/* Error */}
      {error && (
        <div className="mt-2 flex items-center gap-1.5 text-[10px] text-red-400">
          <AlertTriangle className="w-3 h-3 shrink-0" />
          {error}
        </div>
      )}

      {/* Actions */}
      <div className="mt-2.5 flex gap-2">
        <button
          type="button"
          onClick={onClose}
          className="flex-1 py-1 text-[11px] font-semibold rounded-lg border border-app-border-light text-app-text-muted hover:bg-app-bg-muted/30 transition-colors"
        >
          Cancel
        </button>
        <button
          type="button"
          onClick={handleSave}
          disabled={saving}
          className="flex-1 py-1 text-[11px] font-semibold rounded-lg bg-app-primary text-white hover:bg-app-primary/90 disabled:opacity-60 transition-colors flex items-center justify-center gap-1"
        >
          {saving ? (
            <Loader2 className="w-3 h-3 animate-spin" />
          ) : (
            <CheckCircle2 className="w-3 h-3" />
          )}
          {saving ? 'Saving…' : 'Save Tools'}
        </button>
      </div>
    </div>
  );
}
