import React, { useState, useEffect } from 'react';
import { 
  FileCheck, CheckCircle2, XCircle, Clock, Building2, 
  RefreshCw, AlertCircle, Search, ChevronLeft, ChevronRight, MessageSquare 
} from 'lucide-react';
import { API_ENDPOINTS } from '../config';

export default function SuperAdminCapacityRequests() {
  const [requests, setRequests] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [filterStatus, setFilterStatus] = useState('ALL');
  
  // Review modal state
  const [selectedReq, setSelectedReq] = useState(null);
  const [reviewAction, setReviewAction] = useState(''); // 'APPROVE' | 'REJECT'
  const [approvedCapIncrease, setApprovedCapIncrease] = useState(1);
  const [reviewComment, setReviewComment] = useState('');
  const [submittingReview, setSubmittingReview] = useState(false);

  const [currentPage, setCurrentPage] = useState(1);
  const itemsPerPage = 8;

  const token = localStorage.getItem('token');

  const fetchRequests = async () => {
    setLoading(true);
    setError('');
    try {
      const res = await fetch(API_ENDPOINTS.SUPERADMIN_CAPACITY_REQUESTS, {
        headers: { Authorization: `Bearer ${token}` }
      });
      if (!res.ok) throw new Error('Failed to load capacity requests');
      const data = await res.json();
      setRequests(data);
    } catch (err) {
      setError(err.message || 'Error fetching requests');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchRequests();
  }, []);

  const handleReviewSubmit = async () => {
    if (!selectedReq || !reviewAction) return;
    setSubmittingReview(true);
    try {
      const endpoint = reviewAction === 'APPROVE'
        ? API_ENDPOINTS.SUPERADMIN_CAPACITY_REQUEST_APPROVE(selectedReq.id)
        : API_ENDPOINTS.SUPERADMIN_CAPACITY_REQUEST_REJECT(selectedReq.id);

      const body = {
        status: reviewAction === 'APPROVE' ? 'APPROVED' : 'REJECTED',
        approved_total_capacity: reviewAction === 'APPROVE' ? Number(approvedCapIncrease) : null,
        review_comment: reviewComment
      };

      const res = await fetch(endpoint, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify(body)
      });
      if (!res.ok) throw new Error('Action failed');
      setSelectedReq(null);
      fetchRequests();
    } catch (err) {
      alert(err.message);
    } finally {
      setSubmittingReview(false);
    }
  };

  const filteredRequests = requests.filter(r => {
    if (filterStatus === 'ALL') return true;
    return r.status === filterStatus;
  });

  const totalPages = Math.ceil(filteredRequests.length / itemsPerPage) || 1;
  const paginatedReqs = filteredRequests.slice((currentPage - 1) * itemsPerPage, currentPage * itemsPerPage);

  return (
    <div className="h-full overflow-y-auto bg-gradient-to-br from-slate-950 via-slate-900 to-purple-950/30 p-4 sm:p-6 text-slate-100">
      <div className="max-w-7xl mx-auto space-y-6">
        
        {/* Header */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-purple-500/20 pb-4">
          <div>
            <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-purple-500/20 text-purple-300 border border-purple-500/30">
              Capacity Governance
            </span>
            <h1 className="text-xl sm:text-2xl font-extrabold text-white mt-1 flex items-center gap-2">
              <FileCheck className="w-6 h-6 text-purple-400" />
              Agent Capacity Increase Requests
            </h1>
            <p className="text-xs text-slate-400 mt-1">
              Review project-level requested breakdowns (Shared & Dedicated counts) and approve overall organization agent cap increases.
            </p>
          </div>
          <button
            onClick={fetchRequests}
            className="inline-flex items-center gap-2 px-3 py-1.5 rounded-lg bg-purple-900/40 hover:bg-purple-800/60 border border-purple-500/30 text-xs font-semibold text-purple-200"
          >
            <RefreshCw className="w-3.5 h-3.5" />
            Refresh Requests
          </button>
        </div>

        {/* Filter bar */}
        <div className="flex items-center gap-2">
          {['ALL', 'PENDING', 'APPROVED', 'REJECTED'].map(st => (
            <button
              key={st}
              onClick={() => { setFilterStatus(st); setCurrentPage(1); }}
              className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-all ${filterStatus === st ? 'bg-purple-600 text-white shadow-md' : 'bg-slate-800/60 text-slate-400 hover:text-slate-200 border border-slate-700'}`}
            >
              {st}
            </button>
          ))}
        </div>

        {error && (
          <div className="p-3 rounded-lg bg-red-500/10 border border-red-500/30 text-red-400 text-xs flex items-center gap-2">
            <AlertCircle className="w-4 h-4" />
            {error}
          </div>
        )}

        {/* Table */}
        <div className="bg-slate-900/90 backdrop-blur-md rounded-xl border border-purple-500/20 p-4 shadow-lg space-y-4">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-slate-800/40 text-slate-400 font-semibold uppercase text-[10px] tracking-wider border-b border-slate-800">
                <tr>
                  <th className="py-2.5 px-3">Organization / User</th>
                  <th className="py-2.5 px-3">Project Breakdown</th>
                  <th className="py-2.5 px-3">Total Requested</th>
                  <th className="py-2.5 px-3">Reason</th>
                  <th className="py-2.5 px-3">Status</th>
                  <th className="py-2.5 px-3">Date</th>
                  <th className="py-2.5 px-3 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60 text-slate-200">
                {paginatedReqs.length === 0 ? (
                  <tr>
                    <td colSpan={7} className="py-6 text-center text-slate-400 italic">
                      No capacity requests found.
                    </td>
                  </tr>
                ) : (
                  paginatedReqs.map(req => (
                    <tr key={req.id} className="hover:bg-slate-800/30 transition-colors">
                      <td className="py-3 px-3">
                        <p className="font-bold text-white">{req.organization_name}</p>
                        <p className="text-[11px] text-slate-400">{req.requested_by_email || `User #${req.requested_by_user_id}`}</p>
                      </td>
                      <td className="py-3 px-3">
                        <div className="flex items-center gap-2">
                          <span className="px-2 py-0.5 rounded bg-blue-500/10 border border-blue-500/20 text-blue-400 font-bold text-[11px]">
                            {req.requested_shared_count} Shared
                          </span>
                          <span className="px-2 py-0.5 rounded bg-indigo-500/10 border border-indigo-500/20 text-indigo-400 font-bold text-[11px]">
                            {req.requested_dedicated_count} Dedicated
                          </span>
                        </div>
                      </td>
                      <td className="py-3 px-3 font-extrabold text-purple-300">
                        +{req.total_requested_increase} Total Slots
                      </td>
                      <td className="py-3 px-3 text-slate-300 max-w-xs truncate" title={req.reason}>
                        {req.reason || 'N/A'}
                      </td>
                      <td className="py-3 px-3">
                        {req.status === 'PENDING' && (
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-amber-500/10 text-amber-400 border border-amber-500/20 font-bold text-[10px]">
                            <Clock className="w-3 h-3" /> PENDING
                          </span>
                        )}
                        {req.status === 'APPROVED' && (
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 font-bold text-[10px]">
                            <CheckCircle2 className="w-3 h-3" /> APPROVED (+{req.approved_total_capacity || req.total_requested_increase})
                          </span>
                        )}
                        {req.status === 'REJECTED' && (
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-rose-500/10 text-rose-400 border border-rose-500/20 font-bold text-[10px]">
                            <XCircle className="w-3 h-3" /> REJECTED
                          </span>
                        )}
                      </td>
                      <td className="py-3 px-3 text-slate-400 text-[11px]">
                        {req.created_at ? new Date(req.created_at).toLocaleDateString() : 'N/A'}
                      </td>
                      <td className="py-3 px-3 text-right">
                        {req.status === 'PENDING' ? (
                          <div className="flex items-center justify-end gap-1.5">
                            <button
                              onClick={() => {
                                setSelectedReq(req);
                                setReviewAction('APPROVE');
                                setApprovedCapIncrease(req.total_requested_increase || 1);
                              }}
                              className="px-2.5 py-1 rounded bg-emerald-600 hover:bg-emerald-500 text-white font-bold text-xs shadow transition-all"
                            >
                              Approve
                            </button>
                            <button
                              onClick={() => {
                                setSelectedReq(req);
                                setReviewAction('REJECT');
                              }}
                              className="px-2.5 py-1 rounded bg-rose-600/80 hover:bg-rose-500 text-white font-bold text-xs transition-all"
                            >
                              Reject
                            </button>
                          </div>
                        ) : (
                          <span className="text-slate-500 italic text-[11px]">Reviewed</span>
                        )}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>

          {/* Pagination */}
          <div className="flex items-center justify-between pt-2 border-t border-slate-800 text-xs text-slate-400">
            <span>
              Page {currentPage} of {totalPages} ({filteredRequests.length} requests)
            </span>
            <div className="flex items-center gap-1">
              <button
                onClick={() => setCurrentPage(p => Math.max(1, p - 1))}
                disabled={currentPage === 1}
                className="p-1 rounded bg-slate-800 hover:bg-slate-700 disabled:opacity-30 text-slate-300"
              >
                <ChevronLeft className="w-4 h-4" />
              </button>
              <button
                onClick={() => setCurrentPage(p => Math.min(totalPages, p + 1))}
                disabled={currentPage === totalPages}
                className="p-1 rounded bg-slate-800 hover:bg-slate-700 disabled:opacity-30 text-slate-300"
              >
                <ChevronRight className="w-4 h-4" />
              </button>
            </div>
          </div>
        </div>

        {/* Review Modal */}
        {selectedReq && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4">
            <div className="bg-slate-900 border border-purple-500/30 rounded-xl p-5 max-w-md w-full shadow-2xl space-y-4">
              <div className="flex items-center justify-between border-b border-slate-800 pb-3">
                <h3 className="font-bold text-white text-base">
                  {reviewAction === 'APPROVE' ? 'Approve Agent Capacity' : 'Reject Capacity Request'}
                </h3>
                <button onClick={() => setSelectedReq(null)} className="text-slate-400 hover:text-white">✕</button>
              </div>

              <div className="text-xs space-y-2 text-slate-300">
                <p><strong>Organization:</strong> {selectedReq.organization_name}</p>
                <p><strong>Breakdown Requested:</strong> {selectedReq.requested_shared_count} Shared / {selectedReq.requested_dedicated_count} Dedicated</p>

                {reviewAction === 'APPROVE' && (
                  <div className="mt-3 space-y-1">
                    <label className="block text-[11px] font-bold text-purple-300 uppercase">
                      Approved Increase in Overall Total Agent Cap:
                    </label>
                    <input
                      type="number"
                      min="1"
                      value={approvedCapIncrease}
                      onChange={e => setApprovedCapIncrease(e.target.value)}
                      className="w-full px-3 py-1.5 bg-slate-800 border border-purple-500/40 rounded text-xs text-white"
                    />
                    <p className="text-[10px] text-slate-400">
                      Note: Super Admin increases the overall total cap. The Org Admin allocates shared/dedicated agents within this total limit.
                    </p>
                  </div>
                )}

                <div className="space-y-1 mt-3">
                  <label className="block text-[11px] font-bold text-slate-400 uppercase">
                    Review Feedback / Comment:
                  </label>
                  <textarea
                    rows={3}
                    value={reviewComment}
                    onChange={e => setReviewComment(e.target.value)}
                    placeholder="Optional feedback for the Organization Admin..."
                    className="w-full px-3 py-2 bg-slate-800 border border-slate-700 rounded text-xs text-white placeholder-slate-500"
                  />
                </div>
              </div>

              <div className="flex justify-end gap-2 border-t border-slate-800 pt-3">
                <button
                  onClick={() => setSelectedReq(null)}
                  className="px-3 py-1.5 rounded bg-slate-800 text-slate-300 text-xs font-semibold hover:bg-slate-700"
                >
                  Cancel
                </button>
                <button
                  onClick={handleReviewSubmit}
                  disabled={submittingReview}
                  className={`px-4 py-1.5 rounded text-white text-xs font-bold shadow ${reviewAction === 'APPROVE' ? 'bg-purple-600 hover:bg-purple-500' : 'bg-rose-600 hover:bg-rose-500'}`}
                >
                  {submittingReview ? 'Processing...' : (reviewAction === 'APPROVE' ? 'Confirm Approval' : 'Confirm Rejection')}
                </button>
              </div>
            </div>
          </div>
        )}

      </div>
    </div>
  );
}
