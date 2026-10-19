/**
 * AgentToolPicker
 * ---------------
 * Inline popover that lets the user view and update an agent's allowed_tools.
 * Shows only the *gap* tools (missing required or recommended) by default, with
 * an option to expand and see the full registry.
 *
 * Props:
 *   agentId       {string}   – agent DB id
 *   agentName     {string}   – display name
 *   currentTools  {string[]} – already-assigned tool list
 *   missingTools  {string[]} – subset to highlight (missing required/recommended)
 *   onUpdate      {fn}       – called with the new tools array after a successful PUT
 *   onClose       {fn}       – called when the picker is closed
 *   token         {string}   – JWT Bearer token
 */
import React, { useState } from 'react';
import { API_ENDPOINTS } from '../config';
import { Loader2, Wrench, CheckCircle2, AlertTriangle, X } from 'lucide-react';

// Full canonical tool registry with labels and descriptions
const ALL_TOOLS = [
  { id: 'filesystem',  label: 'File System',  desc: 'Read/write files in the workspace' },
  { id: 'git',         label: 'Git',          desc: 'Clone, commit, push, branch operations' },
  { id: 'terminal',    label: 'Terminal',     desc: 'Execute shell commands' },
  { id: 'build_tool',  label: 'Build Tool',   desc: 'Compile, bundle and package code' },
  { id: 'test_runner', label: 'Test Runner',  desc: 'Run unit, integration and e2e tests' },
  { id: 'visual_qa',   label: 'Visual QA',    desc: 'Browser screenshot / pixel comparison' },
  { id: 'database',    label: 'Database',     desc: 'Query and migrate SQL/NoSQL databases' },
  { id: 'browser',     label: 'Browser',      desc: 'Headless browser automation (Playwright)' },
  { id: 'docker',      label: 'Docker',       desc: 'Build and run Docker containers' },
  { id: 'cloud_cli',   label: 'Cloud CLI',    desc: 'AWS/GCP/Azure CLI operations' },
  { id: 'web_search',  label: 'Web Search',   desc: 'Search the web for documentation / context' },
];

export default function AgentToolPicker({
  agentId,
  agentName,
  currentTools = [],
  missingTools = [],
  onUpdate,
  onClose,
  token,
}) {
  const [selected, setSelected] = useState(() => new Set(currentTools.map(t => t.toLowerCase())));
  const [saving, setSaving] = useState(false);
  const [error, setError]   = useState('');
  const [showAll, setShowAll] = useState(false);

  // Decide which tools to show: gap tools first; full registry if showAll
  const missingSet = new Set(missingTools.map(t => t.toLowerCase()));
  const displayTools = showAll
    ? ALL_TOOLS
    : ALL_TOOLS.filter(t => missingSet.has(t.id) || selected.has(t.id));

  const toggle = (toolId) => {
    setSelected(prev => {
      const next = new Set(prev);
      if (next.has(toolId)) next.delete(toolId); else next.add(toolId);
      return next;
    });
  };

  const handleSave = async () => {
    setSaving(true);
    setError('');
    const newTools = [...selected];
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
    <div className="absolute z-50 top-full left-0 mt-1 w-72 bg-app-bg-card border border-app-border-light rounded-xl shadow-xl p-3 animate-in fade-in slide-in-from-top-2 duration-150">
      {/* Header */}
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-1.5">
          <Wrench className="w-3.5 h-3.5 text-app-primary" />
          <span className="text-[11px] font-bold text-app-text-main">
            Tool Assignment — <span className="text-app-primary">{agentName}</span>
          </span>
        </div>
        <button
          type="button"
          onClick={onClose}
          className="p-0.5 rounded hover:bg-app-bg-muted text-app-text-muted transition-colors"
        >
          <X className="w-3 h-3" />
        </button>
      </div>

      {/* Tool list */}
      <div className="space-y-1 max-h-56 overflow-y-auto pr-0.5">
        {displayTools.map(tool => {
          const isChecked  = selected.has(tool.id);
          const isMissing  = missingSet.has(tool.id);
          return (
            <label
              key={tool.id}
              className={`flex items-start gap-2 p-1.5 rounded-lg cursor-pointer transition-colors border ${
                isChecked
                  ? 'bg-app-primary/8 border-app-primary/25'
                  : isMissing
                  ? 'bg-red-500/5 border-red-500/20 hover:bg-red-500/10'
                  : 'border-transparent hover:bg-app-bg-muted/30'
              }`}
            >
              <input
                type="checkbox"
                className="mt-0.5 accent-app-primary shrink-0"
                checked={isChecked}
                onChange={() => toggle(tool.id)}
              />
              <div className="min-w-0">
                <div className="flex items-center gap-1">
                  <span className="text-[11px] font-semibold text-app-text-main">
                    {tool.label}
                  </span>
                  {isMissing && !isChecked && (
                    <span className="px-1 py-0.5 text-[8px] font-bold rounded bg-red-500/15 text-red-400 border border-red-500/20 uppercase">
                      Missing
                    </span>
                  )}
                </div>
                <p className="text-[9px] text-app-text-muted leading-snug">{tool.desc}</p>
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
