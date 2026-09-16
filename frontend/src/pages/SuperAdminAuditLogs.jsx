import React, { useState, useEffect } from 'react';
import { Activity, RefreshCw, AlertCircle, Search, Building2, User, Clock, ChevronLeft, ChevronRight } from 'lucide-react';
import { API_ENDPOINTS } from '../config';

const TOKENOPS_ACTIONS = new Set([
  'PURCHASE_TOKENS',
  'ALLOCATE_TOKENS',
  'REALLOCATE_TOKENS',
  'REVOKE_TOKENS',
  'REQUEST_QUOTA',
  'APPROVE_QUOTA_REQUEST',
  'REJECT_QUOTA_REQUEST',
  'ENABLE_PAYG',
  'DISABLE_PAYG',
  'UPDATE_PAYG_LIMITS',
  'UPDATE_MODEL_PRICING',
  'CREATE_MODEL_PRICING',
  'BLOCK_ORG',
  'UNBLOCK_ORG',
  'BLOCK_USER',
  'UNBLOCK_USER',
  'SET_GRACE_PERIOD',
  'BULK_SET_GRACE_PERIOD'
]);

export default function SuperAdminAuditLogs() {
  const [logs, setLogs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [searchQuery, setSearchQuery] = useState('');
  const [categoryFilter, setCategoryFilter] = useState('ALL'); // 'ALL' | 'TOKENOPS'

  const [currentPage, setCurrentPage] = useState(1);
  const itemsPerPage = 12;

  const token = localStorage.getItem('token');

  const fetchLogs = async () => {
    setLoading(true);
    setError('');
    try {
      const res = await fetch(API_ENDPOINTS.SUPERADMIN_AUDIT_LOGS, {
        headers: { Authorization: `Bearer ${token}` }
      });
      if (!res.ok) throw new Error('Failed to load global audit logs');
      const data = await res.json();
      setLogs(data);
    } catch (err) {
      setError(err.message || 'Error fetching audit logs');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchLogs();
  }, []);

  const isTokenOpsLog = (log) => {
    const act = (log.action || '').toUpperCase();
    const pth = (log.path || '').toLowerCase();
    return TOKENOPS_ACTIONS.has(act) || pth.includes('/tokenops') || act.includes('TOKEN') || act.includes('PAYG') || act.includes('QUOTA') || act.includes('PRICING');
  };

  const filteredLogs = logs.filter(l => {
    if (categoryFilter === 'TOKENOPS' && !isTokenOpsLog(l)) return false;
    const matchesSearch = (
      (l.email || '').toLowerCase().includes(searchQuery.toLowerCase()) ||
      (l.organization_name || '').toLowerCase().includes(searchQuery.toLowerCase()) ||
      (l.action || '').toLowerCase().includes(searchQuery.toLowerCase()) ||
      (l.path || '').toLowerCase().includes(searchQuery.toLowerCase())
    );
    return matchesSearch;
  });

  const totalPages = Math.ceil(filteredLogs.length / itemsPerPage) || 1;
  const paginatedLogs = filteredLogs.slice((currentPage - 1) * itemsPerPage, currentPage * itemsPerPage);

  if (loading) {
    return (
      <div className="h-full flex items-center justify-center bg-app-bg-page text-app-text-muted">
        <div className="flex items-center gap-3">
          <RefreshCw className="w-5 h-5 animate-spin text-purple-400" />
          <span className="text-sm font-medium">Loading Global Audit Logs...</span>
        </div>
      </div>
    );
  }

  return (
    <div className="h-full overflow-y-auto bg-slate-50 dark:bg-slate-950 p-4 sm:p-6 text-slate-900 dark:text-slate-100 transition-colors">
      <div className="max-w-7xl mx-auto space-y-6">
        
        {/* Actions Toolbar */}
        <div className="flex justify-end items-center border-b border-slate-200 dark:border-purple-500/20 pb-3">
          <button
            onClick={fetchLogs}
            className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-white dark:bg-purple-900/40 hover:bg-slate-100 dark:hover:bg-purple-800/50 border border-slate-200 dark:border-purple-500/30 text-purple-700 dark:text-purple-200 text-xs font-semibold transition-all shadow-sm cursor-pointer"
          >
            <RefreshCw className="w-3.5 h-3.5" />
            Refresh Logs
          </button>
        </div>

        {error && (
          <div className="p-3 rounded-lg bg-rose-500/10 border border-rose-500/30 text-rose-300 text-xs flex items-center gap-2">
            <AlertCircle className="w-4 h-4 shrink-0" />
            <span>{error}</span>
          </div>
        )}

        {/* Audit Log Table */}
        <div className="p-5 rounded-2xl bg-white dark:bg-slate-900/80 border border-slate-200 dark:border-purple-500/20 shadow-sm space-y-4">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <div>
              <h2 className="text-base font-bold text-slate-900 dark:text-white flex items-center gap-2">
                <Activity className="w-4 h-4 text-purple-400" />
                Cross-Organization User Activity
              </h2>
              <p className="text-xs text-slate-500 dark:text-slate-400">
                Real-time security and operations log across all platform organizations.
              </p>
            </div>
            <div className="flex flex-wrap items-center gap-3">
              <div className="flex items-center rounded-lg bg-slate-100 dark:bg-slate-800/80 p-0.5 border border-slate-200 dark:border-slate-700">
                <button
                  onClick={() => { setCategoryFilter('ALL'); setCurrentPage(1); }}
                  className={`px-3 py-1 text-xs font-semibold rounded-md transition-all ${
                    categoryFilter === 'ALL'
                      ? 'bg-purple-600 text-white shadow-sm'
                      : 'text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-200'
                  }`}
                >
                  All Activity
                </button>
                <button
                  onClick={() => { setCategoryFilter('TOKENOPS'); setCurrentPage(1); }}
                  className={`px-3 py-1 text-xs font-semibold rounded-md transition-all flex items-center gap-1.5 ${
                    categoryFilter === 'TOKENOPS'
                      ? 'bg-purple-600 text-white shadow-sm'
                      : 'text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-200'
                  }`}
                >
                  <span>🪙</span>
                  Token Operations
                </button>
              </div>

              <div className="relative w-full sm:w-64">
                <Search className="w-3.5 h-3.5 absolute left-3 top-2.5 text-slate-400" />
                <input
                  type="text"
                  placeholder="Search by user, org, action..."
                  value={searchQuery}
                  onChange={e => { setSearchQuery(e.target.value); setCurrentPage(1); }}
                  className="w-full pl-8 pr-3 py-1.5 bg-slate-50 dark:bg-slate-800/60 border border-slate-200 dark:border-slate-700 rounded-lg text-xs text-slate-900 dark:text-white placeholder-slate-400 focus:outline-none focus:border-purple-500"
                />
              </div>
            </div>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-slate-50 dark:bg-slate-800/40 text-slate-500 dark:text-slate-400 font-semibold uppercase text-[10px] tracking-wider border-b border-slate-200 dark:border-slate-800">
                <tr>
                  <th className="py-2.5 px-3">Timestamp</th>
                  <th className="py-2.5 px-3">User</th>
                  <th className="py-2.5 px-3">Organization</th>
                  <th className="py-2.5 px-3">Action</th>
                  <th className="py-2.5 px-3">Method</th>
                  <th className="py-2.5 px-3">Path</th>
                  <th className="py-2.5 px-3">IP Address</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-200 dark:divide-slate-800/60 text-slate-700 dark:text-slate-200">
                {paginatedLogs.length === 0 ? (
                  <tr>
                    <td colSpan={7} className="py-6 text-center text-slate-400 dark:text-slate-500 italic">
                      No audit log entries found.
                    </td>
                  </tr>
                ) : (
                  paginatedLogs.map((log) => (
                    <tr key={log.id} className="hover:bg-slate-50/80 dark:hover:bg-slate-800/30 transition-colors">
                      <td className="py-2.5 px-3 font-mono text-[11px] text-slate-500 dark:text-slate-400">
                        {log.created_at ? new Date(log.created_at).toLocaleString() : '—'}
                      </td>
                      <td className="py-2.5 px-3 font-semibold text-slate-900 dark:text-white">
                        {log.email}
                      </td>
                      <td className="py-2.5 px-3 text-purple-700 dark:text-purple-300 font-medium">
                        {log.organization_name}
                      </td>
                      <td className="py-2.5 px-3 text-slate-600 dark:text-slate-300 font-medium">
                        {log.action}
                      </td>
                      <td className="py-2.5 px-3">
                        <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-purple-50 dark:bg-slate-800 text-purple-700 dark:text-purple-300 border border-purple-200 dark:border-slate-700">
                          {log.method || 'GET'}
                        </span>
                      </td>
                      <td className="py-2.5 px-3 font-mono text-[11px] text-slate-500 dark:text-slate-400">
                        {log.path || '—'}
                      </td>
                      <td className="py-2.5 px-3 font-mono text-[11px] text-slate-500 dark:text-slate-400">
                        {log.ip_address || '—'}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>

          {/* Pagination Controls */}
          <div className="flex items-center justify-between pt-2 border-t border-slate-200 dark:border-slate-800 text-xs text-slate-500 dark:text-slate-400">
            <span>
              Page {currentPage} of {totalPages} ({filteredLogs.length} entries)
            </span>
            <div className="flex items-center gap-1">
              <button
                onClick={() => setCurrentPage(p => Math.max(1, p - 1))}
                disabled={currentPage === 1}
                className="p-1 rounded bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 dark:hover:bg-slate-700 disabled:opacity-30 text-slate-600 dark:text-slate-300 cursor-pointer"
              >
                <ChevronLeft className="w-4 h-4" />
              </button>
              <button
                onClick={() => setCurrentPage(p => Math.min(totalPages, p + 1))}
                disabled={currentPage === totalPages}
                className="p-1 rounded bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 dark:hover:bg-slate-700 disabled:opacity-30 text-slate-600 dark:text-slate-300 cursor-pointer"
              >
                <ChevronRight className="w-4 h-4" />
              </button>
            </div>
          </div>
        </div>

      </div>
    </div>
  );
}
