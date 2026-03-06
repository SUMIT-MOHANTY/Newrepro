import React, { useState, useEffect } from 'react';
import { GitPullRequest, GitMerge, Loader2, GitCommit, ShieldCheck } from 'lucide-react';
import { API_BASE_URL } from '../config';

const PrStatusCard = ({ selectedProjectKey }) => {
    const [status, setStatus] = useState({
        merged_branches: [],
        merge_queue_length: 0,
        is_merging: false
    });
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        let isMounted = true;
        let timeoutId;

        const fetchData = async () => {
            if (!selectedProjectKey) {
                if (isMounted) setLoading(false);
                return;
            }

            try {
                const token = localStorage.getItem('token');
                const res = await fetch(`${API_BASE_URL}/api/github/pr-status/${selectedProjectKey}`, {
                    headers: { 'Authorization': `Bearer ${token}` }
                });

                if (res.ok) {
                    const data = await res.json();
                    if (isMounted) {
                        setStatus(data);
                        setLoading(false);
                    }
                }
            } catch (err) {
                console.error("Failed to fetch PR status", err);
            }

            if (isMounted) {
                timeoutId = setTimeout(fetchData, 3000); // Polling every 3s
            }
        };

        fetchData();

        return () => {
            isMounted = false;
            clearTimeout(timeoutId);
        };
    }, [selectedProjectKey]);

    if (!selectedProjectKey) return null;

    const mergedCount = status.merged_branches?.length || 0;
    const hasQueue = status.merge_queue_length > 0;

    return (
        <div className="bg-white col-span-1 rounded-[12px] border border-gray-100 shadow-sm overflow-hidden flex flex-col hover:border-[#f27a24]/30 transition-colors h-full">
            <div className="flex border-b border-gray-100/60 bg-gradient-to-r from-gray-50/50 to-white px-4 py-3 items-center justify-between">
                <div className="flex items-center gap-2.5">
                    <div className="p-1.5 bg-[#f27a24]/10 rounded-md text-[#f27a24]">
                        <GitPullRequest className="w-4 h-4" />
                    </div>
                    <h3 className="font-bold text-[13px] text-gray-800 uppercase tracking-wide">CI/CD Pipeline</h3>
                </div>
                {status.is_merging && (
                    <span className="flex items-center gap-1.5 text-[10px] font-bold text-blue-600 bg-blue-50 px-2 py-0.5 rounded uppercase tracking-wider">
                        <Loader2 className="w-3 h-3 animate-spin inline" /> Merge in Progress
                    </span>
                )}
            </div>

            <div className="p-4 flex-1 flex flex-col gap-4">
                {/* Linting status */}
                <div className="flex items-center gap-3 pb-3 border-b border-gray-50">
                    <div className="flex-shrink-0 w-8 h-8 rounded-full bg-emerald-50 text-emerald-600 flex items-center justify-center">
                        <ShieldCheck className="w-4 h-4" />
                    </div>
                    <div className="flex-1">
                        <div className="text-xs font-bold text-gray-800">Pre-Compilation & Linting</div>
                        <div className="text-[11px] text-gray-500 mt-0.5">Continuous validation active via Agent Self-Healing loops</div>
                    </div>
                </div>

                {/* GitHub PR stats */}
                <div className="grid grid-cols-2 gap-3 mt-1">
                    <div className="bg-gray-50/80 rounded border border-gray-100 p-3">
                        <div className="flex items-center gap-2 mb-1">
                            <GitMerge className="w-3.5 h-3.5 text-indigo-500" />
                            <span className="text-[10px] font-bold text-gray-500 uppercase">Merged Branches</span>
                        </div>
                        <div className="text-xl font-bold text-gray-800">{mergedCount}</div>
                    </div>

                    <div className="bg-gray-50/80 rounded border border-gray-100 p-3">
                        <div className="flex items-center gap-2 mb-1">
                            <GitCommit className="w-3.5 h-3.5 text-amber-500" />
                            <span className="text-[10px] font-bold text-gray-500 uppercase">Queue</span>
                        </div>
                        <div className="text-xl font-bold text-gray-800">{status.merge_queue_length}</div>
                    </div>
                </div>

                {mergedCount === 0 && !hasQueue && !loading && (
                    <div className="mt-2 text-center text-gray-400 text-xs py-2 bg-gray-50/50 rounded italic">
                        Waiting for initial agent builds...
                    </div>
                )}
            </div>

            <div className="px-4 py-2 bg-slate-50 border-t border-gray-100 flex items-center justify-between">
                <span className="text-[10px] text-slate-500 font-medium">Automatic PR creation → Main</span>
                <span className="text-[10px] font-bold text-emerald-600">Active</span>
            </div>
        </div>
    );
};

export default PrStatusCard;
