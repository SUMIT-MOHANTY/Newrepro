import React, { useState } from 'react';
import { X, Shield, Layers, Bot, Send, AlertCircle, Building2, FolderKanban } from 'lucide-react';
import { API_ENDPOINTS } from '../config';

export default function RequestCapacityModal({
  isOpen,
  onClose,
  projects = [],
  selectedProjectKey = '',
  isOrgAdmin = false,
  onSuccess
}) {
  const [projectKey, setProjectKey] = useState(selectedProjectKey || (projects[0]?.key || ''));
  const [sharedCount, setSharedCount] = useState(1);
  const [dedicatedCount, setDedicatedCount] = useState(0);
  const [reason, setReason] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');

  if (!isOpen) return null;

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!reason.trim()) {
      setError('Please provide a business justification for your request.');
      return;
    }
    if (sharedCount <= 0 && dedicatedCount <= 0) {
      setError('Please request at least 1 Shared or Dedicated agent.');
      return;
    }

    setSubmitting(true);
    setError('');

    const token = localStorage.getItem('token');
    const selectedProj = projects.find(p => p.key === projectKey);
    const projectName = selectedProj ? selectedProj.name : projectKey;

    try {
      if (isOrgAdmin) {
        // Org Admin requesting total capacity increase from Super Admin
        const res = await fetch(API_ENDPOINTS.AGENT_CAPACITY_INCREASE_REQUEST, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${token}`
          },
          body: JSON.stringify({
            project_token: projectKey || null,
            project_name: projectName || null,
            requested_shared_count: Number(sharedCount),
            requested_dedicated_count: Number(dedicatedCount),
            total_requested_increase: Number(sharedCount) + Number(dedicatedCount),
            reason: reason.trim()
          })
        });

        if (!res.ok) {
          const errData = await res.json().catch(() => ({}));
          throw new Error(errData.detail || 'Failed to submit request to Super Admin');
        }
      } else {
        // End User requesting agents for a specific project from Org Admin
        const res = await fetch(API_ENDPOINTS.AGENT_PROJECT_REQUESTS, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${token}`
          },
          body: JSON.stringify({
            project_token: projectKey,
            project_name: projectName,
            requested_shared_count: Number(sharedCount),
            requested_dedicated_count: Number(dedicatedCount),
            reason: reason.trim()
          })
        });

        if (!res.ok) {
          const errData = await res.json().catch(() => ({}));
          throw new Error(errData.detail || 'Failed to submit request to Organization Admin');
        }
      }

      setReason('');
      setSharedCount(1);
      setDedicatedCount(0);
      onClose();
      if (onSuccess) onSuccess();
    } catch (err) {
      setError(err.message || 'An error occurred during submission.');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-[9999] flex items-center justify-center p-4 bg-black/80 backdrop-blur-md animate-in fade-in duration-200">
      <div className="w-full max-w-lg bg-slate-900 border border-purple-500/30 rounded-2xl p-6 shadow-2xl space-y-5">
        
        {/* Header */}
        <div className="flex items-center justify-between border-b border-slate-800 pb-4">
          <div className="flex items-center gap-3">
            <div className="p-2.5 rounded-xl bg-purple-500/10 border border-purple-500/20 text-purple-400">
              <Shield className="w-5 h-5" />
            </div>
            <div>
              <span className="text-[10px] font-bold uppercase tracking-wider text-purple-400">
                {isOrgAdmin ? 'Escalate to Super Admin' : 'Submit Request to Org Admin'}
              </span>
              <h3 className="text-lg font-bold text-white">
                {isOrgAdmin ? 'Request Capacity Increase' : 'Request Agents for Project'}
              </h3>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-400 hover:text-white transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {error && (
          <div className="p-3 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-300 text-xs flex items-center gap-2">
            <AlertCircle className="w-4 h-4 shrink-0" />
            <span>{error}</span>
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4">
          
          {/* Target Project Dropdown */}
          <div className="space-y-1.5">
            <label className="text-xs font-bold text-slate-300 flex items-center gap-1.5">
              <FolderKanban className="w-3.5 h-3.5 text-purple-400" />
              Target Project
            </label>
            {projects && projects.length > 0 ? (
              <select
                value={projectKey}
                onChange={e => setProjectKey(e.target.value)}
                className="w-full px-3 py-2 bg-slate-800/80 border border-slate-700 rounded-xl text-xs text-white focus:outline-none focus:border-purple-500"
              >
                {projects.map(p => (
                  <option key={p.key} value={p.key}>
                    {p.name} ({p.key})
                  </option>
                ))}
              </select>
            ) : (
              <input
                type="text"
                placeholder="Enter project name or token..."
                value={projectKey}
                onChange={e => setProjectKey(e.target.value)}
                className="w-full px-3 py-2 bg-slate-800/80 border border-slate-700 rounded-xl text-xs text-white focus:outline-none focus:border-purple-500"
              />
            )}
          </div>

          {/* Requested Agent Quantities */}
          <div className="grid grid-cols-2 gap-3">
            <div className="p-3 bg-slate-800/50 border border-slate-700/60 rounded-xl space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-xs font-bold text-emerald-400 flex items-center gap-1">
                  <Layers className="w-3.5 h-3.5" />
                  Shared Agents
                </span>
              </div>
              <div className="flex items-center justify-between gap-2">
                <button
                  type="button"
                  onClick={() => setSharedCount(Math.max(0, sharedCount - 1))}
                  className="w-8 h-8 rounded-lg bg-slate-800 hover:bg-slate-700 text-white font-bold border border-slate-700 text-sm"
                >
                  -
                </button>
                <input
                  type="number"
                  min="0"
                  value={sharedCount}
                  onChange={e => setSharedCount(Number(e.target.value))}
                  className="w-16 text-center py-1 bg-slate-900 border border-purple-500/40 rounded text-xs font-bold text-white"
                />
                <button
                  type="button"
                  onClick={() => setSharedCount(sharedCount + 1)}
                  className="w-8 h-8 rounded-lg bg-slate-800 hover:bg-slate-700 text-white font-bold border border-slate-700 text-sm"
                >
                  +
                </button>
              </div>
            </div>

            <div className="p-3 bg-slate-800/50 border border-slate-700/60 rounded-xl space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-xs font-bold text-blue-400 flex items-center gap-1">
                  <Bot className="w-3.5 h-3.5" />
                  Dedicated Agents
                </span>
              </div>
              <div className="flex items-center justify-between gap-2">
                <button
                  type="button"
                  onClick={() => setDedicatedCount(Math.max(0, dedicatedCount - 1))}
                  className="w-8 h-8 rounded-lg bg-slate-800 hover:bg-slate-700 text-white font-bold border border-slate-700 text-sm"
                >
                  -
                </button>
                <input
                  type="number"
                  min="0"
                  value={dedicatedCount}
                  onChange={e => setDedicatedCount(Number(e.target.value))}
                  className="w-16 text-center py-1 bg-slate-900 border border-purple-500/40 rounded text-xs font-bold text-white"
                />
                <button
                  type="button"
                  onClick={() => setDedicatedCount(dedicatedCount + 1)}
                  className="w-8 h-8 rounded-lg bg-slate-800 hover:bg-slate-700 text-white font-bold border border-slate-700 text-sm"
                >
                  +
                </button>
              </div>
            </div>
          </div>

          {/* Reason Textarea */}
          <div className="space-y-1.5">
            <label className="text-xs font-bold text-slate-300">
              Business Justification / Reason <span className="text-rose-400">*</span>
            </label>
            <textarea
              rows={3}
              placeholder={
                isOrgAdmin
                  ? "Explain why the organization needs a higher total capacity limit from Super Admin..."
                  : "Explain why this project requires additional shared or dedicated agents..."
              }
              value={reason}
              onChange={e => setReason(e.target.value)}
              className="w-full p-3 bg-slate-800/80 border border-slate-700 rounded-xl text-xs text-white placeholder-slate-400 focus:outline-none focus:border-purple-500"
            />
          </div>

          {/* Action Buttons */}
          <div className="flex items-center justify-end gap-2 pt-2 border-t border-slate-800">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-300 font-semibold rounded-xl text-xs"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={submitting}
              className="flex items-center gap-1.5 px-4 py-2 bg-purple-600 hover:bg-purple-500 text-white font-bold rounded-xl text-xs shadow-lg shadow-purple-600/30 transition-all disabled:opacity-50"
            >
              <Send className="w-3.5 h-3.5" />
              <span>{submitting ? 'Submitting...' : isOrgAdmin ? 'Request Super Admin' : 'Submit Request'}</span>
            </button>
          </div>
        </form>

      </div>
    </div>
  );
}
