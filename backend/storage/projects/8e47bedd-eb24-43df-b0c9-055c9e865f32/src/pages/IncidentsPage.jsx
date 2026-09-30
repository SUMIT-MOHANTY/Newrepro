import React, { useState } from 'react';
import { AlertCircle, Plus, Search, Shield, ArrowUpDown, ChevronRight, CheckCircle2 } from 'lucide-react';

export default function IncidentsPage() {
  const [search, setSearch] = useState('');
  const [selectedIncident, setSelectedIncident] = useState(null);

  const incidents = [
    { id: 'INC-1049', title: 'Payment Gateway Webhook Timeout', severity: 'CRITICAL', status: 'INVESTIGATING', owner: 'Alex Rivera', updated: '8m ago', desc: 'Downstream provider Stripe reporting 504 timeouts on webhook callbacks.' },
    { id: 'INC-1048', title: 'High CPU on Elasticsearch Cluster 02', severity: 'HIGH', status: 'IDENTIFIED', owner: 'Devon Lee', updated: '28m ago', desc: 'Heavy index shard balancing causing 92% CPU spike on data node 4.' },
    { id: 'INC-1047', title: 'Redis Cache Memory Pressure in EU-West', severity: 'MEDIUM', status: 'MONITORING', owner: 'Sarah Connor', updated: '1h ago', desc: 'Eviction policy LRU kicking in; hit ratio dropped by 18%.' },
    { id: 'INC-1046', title: 'Stale Read Replicas on Postgres Primary', severity: 'LOW', status: 'RESOLVED', owner: 'System Auto', updated: '4h ago', desc: 'Replication lag cleared after WAL archiving vacuum executed.' },
  ];

  const filtered = incidents.filter(i =>
    i.title.toLowerCase().includes(search.toLowerCase()) ||
    i.id.toLowerCase().includes(search.toLowerCase()) ||
    i.owner.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 pb-4 border-b border-slate-800">
        <div>
          <h1 className="text-2xl font-bold text-white tracking-tight">Incident Management & Response</h1>
          <p className="text-sm text-slate-400 mt-1">Audit, escalate, and resolve production incidents with real-time audit trails.</p>
        </div>
        <button className="flex items-center gap-2 px-4 py-2 bg-rose-600 hover:bg-rose-500 text-white text-xs font-semibold rounded-lg shadow-lg shadow-rose-600/20 transition-all">
          <Plus className="w-4 h-4" />
          Declare New Incident
        </button>
      </div>

      <div className="flex items-center gap-3">
        <div className="relative flex-1">
          <Search className="w-4 h-4 absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400" />
          <input
            type="text"
            placeholder="Search by ID, title, or assignee..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full bg-slate-900 border border-slate-800 rounded-lg pl-10 pr-4 py-2 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-sky-500"
          />
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 space-y-3">
          {filtered.map((inc) => (
            <div
              key={inc.id}
              onClick={() => setSelectedIncident(inc)}
              className={`p-4 bg-slate-900 border rounded-xl cursor-pointer transition-all ${
                selectedIncident?.id === inc.id ? 'border-sky-500 ring-1 ring-sky-500' : 'border-slate-800 hover:border-slate-700'
              }`}
            >
              <div className="flex items-start justify-between gap-3">
                <div className="flex items-center gap-2">
                  <span className="text-xs font-mono font-bold text-sky-400">{inc.id}</span>
                  <span className={`px-2 py-0.5 text-[10px] font-bold rounded-full ${
                    inc.severity === 'CRITICAL' ? 'bg-rose-500/20 text-rose-400 border border-rose-500/30' : 'bg-amber-500/20 text-amber-400'
                  }`}>
                    {inc.severity}
                  </span>
                </div>
                <span className="text-xs text-slate-400">{inc.updated}</span>
              </div>
              <h3 className="text-base font-semibold text-white mt-2">{inc.title}</h3>
              <p className="text-xs text-slate-400 mt-1 line-clamp-1">{inc.desc}</p>
              <div className="mt-3 flex items-center justify-between text-xs text-slate-400 border-t border-slate-800/80 pt-2.5">
                <span>Assignee: <strong className="text-slate-300">{inc.owner}</strong></span>
                <span className="flex items-center gap-1 text-slate-300">
                  Status: <strong className="text-emerald-400">{inc.status}</strong>
                  <ChevronRight className="w-3.5 h-3.5 text-slate-500" />
                </span>
              </div>
            </div>
          ))}
        </div>

        {/* Detail Panel */}
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 h-fit sticky top-6">
          {selectedIncident ? (
            <div className="space-y-4">
              <div className="flex items-center justify-between pb-3 border-b border-slate-800">
                <span className="font-mono text-xs text-sky-400 font-bold">{selectedIncident.id}</span>
                <span className="text-xs text-emerald-400 font-medium">{selectedIncident.status}</span>
              </div>
              <div>
                <h4 className="text-base font-bold text-white">{selectedIncident.title}</h4>
                <p className="text-xs text-slate-400 mt-2 leading-relaxed">{selectedIncident.desc}</p>
              </div>
              <div className="space-y-2 pt-2 border-t border-slate-800 text-xs text-slate-300">
                <div className="flex justify-between"><span>Owner:</span> <strong className="text-white">{selectedIncident.owner}</strong></div>
                <div className="flex justify-between"><span>Severity:</span> <strong className="text-rose-400">{selectedIncident.severity}</strong></div>
                <div className="flex justify-between"><span>Last Activity:</span> <strong className="text-white">{selectedIncident.updated}</strong></div>
              </div>
              <div className="pt-3">
                <button className="w-full py-2 bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-semibold rounded-lg transition-colors">
                  Resolve Incident
                </button>
              </div>
            </div>
          ) : (
            <div className="text-center py-12 text-slate-500 text-xs">
              <AlertCircle className="w-8 h-8 mx-auto mb-2 text-slate-600" />
              Select an incident from the list to view resolution timeline and telemetry.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
