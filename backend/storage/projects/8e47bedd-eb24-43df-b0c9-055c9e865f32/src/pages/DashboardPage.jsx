import React, { useState } from 'react';
import { AlertTriangle, CheckCircle2, Clock, ShieldAlert, TrendingUp, RefreshCw, Filter } from 'lucide-react';

export default function DashboardPage() {
  const [filter, setFilter] = useState('ALL');

  const stats = [
    { title: 'Total Incidents', count: 42, change: '+12% from last week', icon: ShieldAlert, color: 'text-amber-500', bg: 'bg-amber-500/10' },
    { title: 'Active / Open', count: 8, change: '3 Critical requiring action', icon: AlertTriangle, color: 'text-rose-500', bg: 'bg-rose-500/10' },
    { title: 'Resolved Today', count: 14, change: 'Mean Time to Resolve: 18m', icon: CheckCircle2, color: 'text-emerald-500', bg: 'bg-emerald-500/10' },
    { title: 'Avg Uptime', count: '99.98%', change: 'All regional zones operational', icon: TrendingUp, color: 'text-sky-500', bg: 'bg-sky-500/10' },
  ];

  const recentIncidents = [
    { id: 'INC-1049', title: 'Payment Gateway Webhook Timeout', severity: 'CRITICAL', status: 'INVESTIGATING', service: 'Billing Service', time: '10m ago' },
    { id: 'INC-1048', title: 'High CPU on Elasticsearch Cluster 02', severity: 'HIGH', status: 'IDENTIFIED', service: 'Search Cluster', time: '35m ago' },
    { id: 'INC-1047', title: 'Redis Cache Memory Pressure in EU-West', severity: 'MEDIUM', status: 'MONITORING', service: 'Cache Layer', time: '1h 12m ago' },
    { id: 'INC-1046', title: 'Stale Read Replicas on Postgres Primary', severity: 'LOW', status: 'RESOLVED', service: 'DB Replicas', time: '3h ago' },
  ];

  const severityBadge = (sev) => {
    switch (sev) {
      case 'CRITICAL': return 'bg-rose-500/20 text-rose-400 border-rose-500/30';
      case 'HIGH': return 'bg-amber-500/20 text-amber-400 border-amber-500/30';
      case 'MEDIUM': return 'bg-yellow-500/20 text-yellow-400 border-yellow-500/30';
      default: return 'bg-sky-500/20 text-sky-400 border-sky-500/30';
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 pb-4 border-b border-slate-800">
        <div>
          <h1 className="text-2xl font-bold text-white tracking-tight">System Reliability & Incident Dashboard</h1>
          <p className="text-sm text-slate-400 mt-1">Real-time telemetry, service degradation alerts, and active incident response.</p>
        </div>
        <div className="flex items-center gap-2">
          <button className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-slate-300 bg-slate-800 hover:bg-slate-700 border border-slate-700 rounded-lg transition-colors">
            <RefreshCw className="w-3.5 h-3.5" />
            Refresh Telemetry
          </button>
        </div>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {stats.map((s, idx) => {
          const Icon = s.icon;
          return (
            <div key={idx} className="bg-slate-900 border border-slate-800 rounded-xl p-5 hover:border-slate-700 transition-all">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">{s.title}</span>
                <div className={`p-2 rounded-lg ${s.bg}`}>
                  <Icon className={`w-4 h-4 ${s.color}`} />
                </div>
              </div>
              <div className="mt-4 flex items-baseline gap-2">
                <span className="text-3xl font-bold text-white tracking-tight">{s.count}</span>
              </div>
              <p className="mt-1 text-xs text-slate-400">{s.change}</p>
            </div>
          );
        })}
      </div>

      {/* Recent Incidents Table */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden shadow-sm">
        <div className="p-4 border-b border-slate-800 flex items-center justify-between">
          <h2 className="text-sm font-semibold text-white">Active & Recent Incidents</h2>
          <div className="flex items-center gap-2">
            <Filter className="w-3.5 h-3.5 text-slate-400" />
            <select
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
              className="bg-slate-800 border border-slate-700 text-xs text-slate-300 rounded-lg px-2.5 py-1 focus:outline-none"
            >
              <option value="ALL">All Severities</option>
              <option value="CRITICAL">Critical Only</option>
              <option value="ACTIVE">Active Only</option>
            </select>
          </div>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm text-slate-300">
            <thead className="text-xs uppercase bg-slate-950/50 text-slate-400 border-b border-slate-800">
              <tr>
                <th className="px-5 py-3">Incident ID</th>
                <th className="px-5 py-3">Summary</th>
                <th className="px-5 py-3">Affected Service</th>
                <th className="px-5 py-3">Severity</th>
                <th className="px-5 py-3">Status</th>
                <th className="px-5 py-3">Reported</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60">
              {recentIncidents
                .filter(i => filter === 'ALL' || (filter === 'CRITICAL' ? i.severity === 'CRITICAL' : i.status !== 'RESOLVED'))
                .map((inc) => (
                  <tr key={inc.id} className="hover:bg-slate-800/40 transition-colors">
                    <td className="px-5 py-3.5 font-mono text-xs text-sky-400 font-semibold">{inc.id}</td>
                    <td className="px-5 py-3.5 text-white font-medium">{inc.title}</td>
                    <td className="px-5 py-3.5 text-slate-400 text-xs">{inc.service}</td>
                    <td className="px-5 py-3.5">
                      <span className={`inline-flex px-2 py-0.5 rounded-full text-[11px] font-semibold border ${severityBadge(inc.severity)}`}>
                        {inc.severity}
                      </span>
                    </td>
                    <td className="px-5 py-3.5">
                      <span className="inline-flex items-center gap-1.5 text-xs text-slate-300">
                        <span className={`w-1.5 h-1.5 rounded-full ${inc.status === 'RESOLVED' ? 'bg-emerald-400' : 'bg-rose-400 animate-pulse'}`} />
                        {inc.status}
                      </span>
                    </td>
                    <td className="px-5 py-3.5 text-xs text-slate-400">{inc.time}</td>
                  </tr>
                ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
