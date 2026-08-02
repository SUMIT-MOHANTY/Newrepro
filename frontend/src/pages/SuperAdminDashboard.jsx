import React, { useState, useEffect } from 'react';
import { 
  Building2, Users, Bot, Container, Layers, RefreshCw, 
  AlertCircle, DollarSign, Cpu, FolderKanban, UserCheck, 
  Percent, ArrowRight, CheckCircle2, Shield, Settings, Search, 
  ChevronLeft, ChevronRight, Activity, Eye, X, Coins, FileText, FileSpreadsheet, Calendar
} from 'lucide-react';
import { jsPDF } from 'jspdf';
import { API_ENDPOINTS } from '../config';

export default function SuperAdminDashboard() {
  const [stats, setStats] = useState(null);
  const [orgs, setOrgs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  // Date Filters
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');
  
  // Selected Org for detailed inspection modal
  const [selectedOrgModal, setSelectedOrgModal] = useState(null);

  // Organization table editing & pagination
  const [editingOrg, setEditingOrg] = useState(null);
  const [newCapacity, setNewCapacity] = useState(10);
  const [updatingCap, setUpdatingCap] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [currentPage, setCurrentPage] = useState(1);
  const itemsPerPage = 5;

  const token = localStorage.getItem('token');

  const fetchData = async () => {
    setLoading(true);
    setError('');
    try {
      const headers = { Authorization: `Bearer ${token}` };
      
      let statsUrl = API_ENDPOINTS.SUPERADMIN_DASHBOARD_STATS;
      let orgsUrl = API_ENDPOINTS.SUPERADMIN_ORGANIZATIONS;
      const queryParams = [];
      if (startDate) queryParams.push(`start_date=${startDate}`);
      if (endDate) queryParams.push(`end_date=${endDate}`);
      if (queryParams.length > 0) {
        const queryStr = `?${queryParams.join('&')}`;
        statsUrl += queryStr;
        orgsUrl += queryStr;
      }

      const statsRes = await fetch(statsUrl, { headers });
      if (!statsRes.ok) throw new Error('Failed to fetch dashboard telemetry');
      const statsData = await statsRes.json();
      setStats(statsData);

      const orgsRes = await fetch(orgsUrl, { headers });
      if (orgsRes.ok) {
        const orgsData = await orgsRes.json();
        setOrgs(orgsData);
      }
    } catch (err) {
      setError(err.message || 'Error loading Super Admin telemetry');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, [startDate, endDate]);

  const handleUpdateCapacity = async (orgName) => {
    setUpdatingCap(true);
    try {
      const res = await fetch(API_ENDPOINTS.SUPERADMIN_ORG_CAPACITY(orgName), {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({ max_agent_capacity: Number(newCapacity) })
      });
      if (!res.ok) throw new Error('Failed to update capacity limit');
      setEditingOrg(null);
      fetchData();
    } catch (e) {
      alert(e.message);
    } finally {
      setUpdatingCap(false);
    }
  };

  const handleExportExcel = () => {
    try {
      const escapeCSV = (val) => {
        if (val === null || val === undefined) return '';
        const str = String(val);
        if (str.includes(',') || str.includes('"') || str.includes('\n')) {
          return `"${str.replace(/"/g, '""')}"`;
        }
        return str;
      };

      const rows = [];
      rows.push(['GLOBAL ORGANIZATIONS TELEMETRY & CAPACITY REPORT']);
      rows.push(['Generated At:', new Date().toLocaleString()]);
      if (startDate || endDate) {
        rows.push(['Filter Date Range:', `${startDate || 'Start'} to ${endDate || 'Present'}`]);
      }
      rows.push([]);

      rows.push(['EXECUTIVE TELEMETRY SUMMARY']);
      rows.push(['Total Organizations', stats?.total_organizations || orgs.length]);
      rows.push(['Total Onboarded Agents', stats?.total_onboarded_agents || 0]);
      rows.push(['Running Docker Containers', stats?.total_running_containers || 0]);
      rows.push(['Total AI Tokens Consumed', stats?.ai_tokens_consumed || 0]);
      rows.push(['Total Platform Billing ($)', stats?.platform_billing || 0]);
      rows.push([]);

      rows.push(['ORGANIZATION CAPACITY & UTILIZATION BREAKDOWN']);
      rows.push([
        'Organization Name',
        'Max Agent Capacity',
        'Onboarded Agents',
        'Available Capacity Slots',
        'Total Members',
        'AI Tokens Consumed',
        'Total Cost (USD)'
      ]);

      orgs.forEach(o => {
        rows.push([
          o.organization_name,
          o.max_agent_capacity,
          o.total_onboarded_agents,
          o.available_capacity,
          o.user_count,
          o.total_tokens_consumed || 0,
          o.total_cost || 0
        ]);
      });

      rows.push([]);
      rows.push(['USER BREAKDOWN PER ORGANIZATION']);
      rows.push(['Organization', 'User Email', 'Name', 'Role', 'AI Tokens Consumed', 'Total Cost (USD)']);

      orgs.forEach(o => {
        (o.users || []).forEach(u => {
          rows.push([
            o.organization_name,
            u.email,
            (u.first_name || u.last_name) ? `${u.first_name || ''} ${u.last_name || ''}`.trim() : '—',
            u.is_super_admin ? 'Super Admin' : u.is_org_admin ? 'Org Admin' : 'Member',
            u.ai_tokens || 0,
            u.total_cost || 0
          ]);
        });
      });

      const csvContent = rows
        .map(row => row.map(cell => escapeCSV(cell)).join(','))
        .join('\n');

      const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      const fileName = `Global_Organizations_Capacity_Report_${new Date().toISOString().split('T')[0]}.csv`;

      link.setAttribute('href', url);
      link.setAttribute('download', fileName);
      link.style.visibility = 'hidden';
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);
    } catch (e) {
      alert('Failed to export Excel CSV: ' + e.message);
    }
  };

  const handleDownloadPDF = () => {
    try {
      const doc = new jsPDF();
      doc.setFontSize(16);
      doc.text("Global Organizations Telemetry & Capacity Report", 14, 20);
      doc.setFontSize(10);
      doc.text(`Generated: ${new Date().toLocaleString()}`, 14, 28);
      if (startDate || endDate) {
        doc.text(`Date Range: ${startDate || 'Start'} to ${endDate || 'Present'}`, 14, 34);
      }

      let y = startDate || endDate ? 44 : 38;
      doc.setFontSize(12);
      doc.text("Executive Summary:", 14, y);
      y += 8;
      doc.setFontSize(10);
      doc.text(`Total Organizations: ${stats?.total_organizations || orgs.length}`, 14, y); y += 6;
      doc.text(`Total Onboarded Agents: ${stats?.total_onboarded_agents || 0}`, 14, y); y += 6;
      doc.text(`Total AI Tokens Consumed: ${(stats?.ai_tokens_consumed || 0).toLocaleString()}`, 14, y); y += 6;
      doc.text(`Total Billing Cost: $${stats?.platform_billing || 0}`, 14, y); y += 12;

      doc.setFontSize(12);
      doc.text("Organization Breakdown:", 14, y);
      y += 8;
      doc.setFontSize(9);
      doc.text("Org Name", 14, y);
      doc.text("Cap Limit", 70, y);
      doc.text("Agents", 100, y);
      doc.text("Users", 125, y);
      doc.text("Tokens", 145, y);
      doc.text("Cost ($)", 180, y);
      y += 4;
      doc.line(14, y, 195, y);
      y += 6;

      orgs.forEach(o => {
        if (y > 270) {
          doc.addPage();
          y = 20;
        }
        doc.text(String(o.organization_name).substring(0, 25), 14, y);
        doc.text(String(o.max_agent_capacity), 70, y);
        doc.text(String(o.total_onboarded_agents), 100, y);
        doc.text(String(o.user_count), 125, y);
        doc.text((o.total_tokens_consumed || 0).toLocaleString(), 145, y);
        doc.text(`$${o.total_cost || 0}`, 180, y);
        y += 7;
      });

      doc.save(`Organizations_Telemetry_Report_${new Date().toISOString().split('T')[0]}.pdf`);
    } catch (e) {
      alert('Failed to generate PDF: ' + e.message);
    }
  };

  const filteredOrgs = orgs.filter(o => 
    o.organization_name.toLowerCase().includes(searchQuery.toLowerCase())
  );
  
  const totalPages = Math.ceil(filteredOrgs.length / itemsPerPage) || 1;
  const paginatedOrgs = filteredOrgs.slice((currentPage - 1) * itemsPerPage, currentPage * itemsPerPage);

  if (loading) {
    return (
      <div className="h-full flex items-center justify-center bg-app-bg-page text-app-text-muted">
        <div className="flex items-center gap-3">
          <RefreshCw className="w-5 h-5 animate-spin text-purple-400" />
          <span className="text-sm font-medium">Loading Super Admin God's View...</span>
        </div>
      </div>
    );
  }

  return (
    <div className="h-full overflow-y-auto bg-gradient-to-br from-slate-950 via-slate-900 to-purple-950/30 p-4 sm:p-6 text-slate-100">
      <div className="max-w-7xl mx-auto space-y-6">
        
        {/* Header */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-purple-500/20 pb-4">
          <div>
            <div className="flex items-center gap-2">
              <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-purple-500/20 text-purple-300 border border-purple-500/30">
                God's View Control Center
              </span>
              <span className="text-xs text-slate-400">• Super Admin Access</span>
            </div>
            <h1 className="text-xl sm:text-2xl font-extrabold text-white mt-1 flex items-center gap-2">
              <Shield className="w-6 h-6 text-purple-400" />
              Global Platform Governance & Organizations
            </h1>
          </div>
          
          <div className="flex flex-wrap items-center gap-2">
            <button
              onClick={handleDownloadPDF}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-purple-900/40 hover:bg-purple-800/60 border border-purple-500/30 text-purple-200 text-xs font-semibold transition-all"
            >
              <FileText className="w-3.5 h-3.5 text-purple-300" />
              Download PDF Report
            </button>

            <button
              onClick={handleExportExcel}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-emerald-950/60 hover:bg-emerald-900/70 border border-emerald-500/30 text-emerald-300 text-xs font-semibold transition-all"
            >
              <FileSpreadsheet className="w-3.5 h-3.5 text-emerald-400" />
              Export Excel
            </button>

            <button
              onClick={fetchData}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-300 text-xs font-semibold transition-all"
            >
              <RefreshCw className="w-3.5 h-3.5" />
              Refresh
            </button>
          </div>
        </div>

        {/* Date Filter Bar */}
        <div className="p-3.5 rounded-xl bg-slate-900/60 border border-purple-500/20 backdrop-blur flex flex-wrap items-center justify-between gap-3 text-xs">
          <div className="flex items-center gap-2 font-semibold text-slate-300">
            <Calendar className="w-4 h-4 text-purple-400" />
            <span>Filter Telemetry by Date Range:</span>
          </div>

          <div className="flex flex-wrap items-center gap-3">
            <div className="flex items-center gap-2">
              <span className="text-slate-400 text-[11px]">Start:</span>
              <input
                type="date"
                value={startDate}
                onChange={e => setStartDate(e.target.value)}
                className="px-2.5 py-1 bg-slate-800 border border-slate-700 rounded text-xs text-white focus:outline-none focus:border-purple-500"
              />
            </div>

            <div className="flex items-center gap-2">
              <span className="text-slate-400 text-[11px]">End:</span>
              <input
                type="date"
                value={endDate}
                onChange={e => setEndDate(e.target.value)}
                className="px-2.5 py-1 bg-slate-800 border border-slate-700 rounded text-xs text-white focus:outline-none focus:border-purple-500"
              />
            </div>

            {(startDate || endDate) && (
              <button
                onClick={() => { setStartDate(''); setEndDate(''); }}
                className="px-2 py-1 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded text-[11px]"
              >
                Clear Dates
              </button>
            )}
          </div>
        </div>

        {error && (
          <div className="p-3 rounded-lg bg-rose-500/10 border border-rose-500/30 text-rose-300 text-xs flex items-center gap-2">
            <AlertCircle className="w-4 h-4 shrink-0" />
            <span>{error}</span>
          </div>
        )}

        {/* Metric Cards Grid (Compact & Responsive) */}
        {stats && (
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
            
            <div className="p-3.5 rounded-xl bg-slate-900/60 border border-purple-500/20 backdrop-blur">
              <div className="flex items-center justify-between text-slate-400 text-xs mb-1">
                <span className="font-semibold uppercase tracking-wider text-[10px]">Organizations</span>
                <Building2 className="w-4 h-4 text-purple-400" />
              </div>
              <div className="text-xl font-bold text-white">{stats.total_organizations}</div>
              <div className="text-[10px] text-slate-400 mt-0.5">Registered tenant accounts</div>
            </div>

            <div className="p-3.5 rounded-xl bg-slate-900/60 border border-purple-500/20 backdrop-blur">
              <div className="flex items-center justify-between text-slate-400 text-xs mb-1">
                <span className="font-semibold uppercase tracking-wider text-[10px]">Onboarded Agents</span>
                <Bot className="w-4 h-4 text-emerald-400" />
              </div>
              <div className="text-xl font-bold text-white">{stats.total_onboarded_agents}</div>
              <div className="text-[10px] text-emerald-400 mt-0.5">Across all organizations</div>
            </div>

            <div className="p-3.5 rounded-xl bg-slate-900/60 border border-purple-500/20 backdrop-blur">
              <div className="flex items-center justify-between text-slate-400 text-xs mb-1">
                <span className="font-semibold uppercase tracking-wider text-[10px]">Docker Containers</span>
                <Container className="w-4 h-4 text-cyan-400" />
              </div>
              <div className="text-xl font-bold text-white">{stats.total_running_containers}</div>
              <div className="text-[10px] text-cyan-400 mt-0.5">Active worker environments</div>
            </div>

            <div className="p-3.5 rounded-xl bg-slate-900/60 border border-purple-500/20 backdrop-blur">
              <div className="flex items-center justify-between text-slate-400 text-xs mb-1">
                <span className="font-semibold uppercase tracking-wider text-[10px]">Dedicated Agents</span>
                <Users className="w-4 h-4 text-blue-400" />
              </div>
              <div className="text-xl font-bold text-white">{stats.dedicated_agents}</div>
              <div className="text-[10px] text-blue-400 mt-0.5">Project-exclusive agents</div>
            </div>

            <div className="p-3.5 rounded-xl bg-slate-900/60 border border-purple-500/20 backdrop-blur">
              <div className="flex items-center justify-between text-slate-400 text-xs mb-1">
                <span className="font-semibold uppercase tracking-wider text-[10px]">Shared Agents</span>
                <Layers className="w-4 h-4 text-indigo-400" />
              </div>
              <div className="text-xl font-bold text-white">{stats.shared_agents}</div>
              <div className="text-[10px] text-indigo-400 mt-0.5">Central capacity pool</div>
            </div>

            <div className="p-3.5 rounded-xl bg-slate-900/60 border border-purple-500/20 backdrop-blur">
              <div className="flex items-center justify-between text-slate-400 text-xs mb-1">
                <span className="font-semibold uppercase tracking-wider text-[10px]">Borrowed Dedicated</span>
                <Activity className="w-4 h-4 text-amber-400" />
              </div>
              <div className="text-xl font-bold text-white">{stats.borrowed_dedicated_agents}</div>
              <div className="text-[10px] text-amber-400 mt-0.5">Serving shared tasks (preemptable)</div>
            </div>

            <div className="p-3.5 rounded-xl bg-slate-900/60 border border-purple-500/20 backdrop-blur">
              <div className="flex items-center justify-between text-slate-400 text-xs mb-1">
                <span className="font-semibold uppercase tracking-wider text-[10px]">Pending Requests</span>
                <AlertCircle className="w-4 h-4 text-rose-400" />
              </div>
              <div className="text-xl font-bold text-white">{stats.pending_capacity_requests}</div>
              <div className="text-[10px] text-rose-400 mt-0.5">Awaiting Super Admin approval</div>
            </div>

            <div className="p-3.5 rounded-xl bg-slate-900/60 border border-purple-500/20 backdrop-blur">
              <div className="flex items-center justify-between text-slate-400 text-xs mb-1">
                <span className="font-semibold uppercase tracking-wider text-[10px]">Platform Billing</span>
                <DollarSign className="w-4 h-4 text-emerald-400" />
              </div>
              <div className="text-xl font-bold text-white">${stats.platform_billing}</div>
              <div className="text-[10px] text-emerald-400 mt-0.5">Calculated AI inference cost</div>
            </div>

            <div className="p-3.5 rounded-xl bg-slate-900/60 border border-purple-500/20 backdrop-blur">
              <div className="flex items-center justify-between text-slate-400 text-xs mb-1">
                <span className="font-semibold uppercase tracking-wider text-[10px]">AI Tokens Consumed</span>
                <Cpu className="w-4 h-4 text-purple-400" />
              </div>
              <div className="text-xl font-bold text-white">{stats.ai_tokens_consumed.toLocaleString()}</div>
              <div className="text-[10px] text-purple-400 mt-0.5">Prompt + completion tokens</div>
            </div>

            <div className="p-3.5 rounded-xl bg-slate-900/60 border border-purple-500/20 backdrop-blur">
              <div className="flex items-center justify-between text-slate-400 text-xs mb-1">
                <span className="font-semibold uppercase tracking-wider text-[10px]">Project Telemetry</span>
                <FolderKanban className="w-4 h-4 text-cyan-400" />
              </div>
              <div className="text-xl font-bold text-white">
                {stats.project_telemetry?.active} / {stats.project_telemetry?.total}
              </div>
              <div className="text-[10px] text-cyan-400 mt-0.5">Active / total registered</div>
            </div>

            <div className="p-3.5 rounded-xl bg-slate-900/60 border border-purple-500/20 backdrop-blur">
              <div className="flex items-center justify-between text-slate-400 text-xs mb-1">
                <span className="font-semibold uppercase tracking-wider text-[10px]">Active Users</span>
                <UserCheck className="w-4 h-4 text-sky-400" />
              </div>
              <div className="text-xl font-bold text-white">{stats.active_users}</div>
              <div className="text-[10px] text-sky-400 mt-0.5">Validated accounts</div>
            </div>

            <div className="p-3.5 rounded-xl bg-slate-900/60 border border-purple-500/20 backdrop-blur">
              <div className="flex items-center justify-between text-slate-400 text-xs mb-1">
                <span className="font-semibold uppercase tracking-wider text-[10px]">Agent Utilization</span>
                <Percent className="w-4 h-4 text-purple-400" />
              </div>
              <div className="text-xl font-bold text-white">{stats.agent_utilization}%</div>
              <div className="text-[10px] text-purple-400 mt-0.5">Execution capacity active</div>
            </div>

          </div>
        )}

        {/* Organizations Capacity Management Table */}
        <div className="p-5 rounded-2xl bg-slate-900/80 border border-purple-500/20 space-y-4">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <div>
              <h2 className="text-base font-bold text-white flex items-center gap-2">
                <Building2 className="w-4 h-4 text-purple-400" />
                Global Organizations Telemetry & Capacity
              </h2>
              <p className="text-xs text-slate-400">
                Inspect organization tokens, user details, and enforce total agent onboarding capacity limits across all projects.
              </p>
            </div>
            <div className="relative w-full sm:w-64">
              <Search className="w-3.5 h-3.5 absolute left-3 top-2.5 text-slate-400" />
              <input
                type="text"
                placeholder="Search organizations..."
                value={searchQuery}
                onChange={e => { setSearchQuery(e.target.value); setCurrentPage(1); }}
                className="w-full pl-8 pr-3 py-1.5 bg-slate-800/60 border border-slate-700 rounded-lg text-xs text-white placeholder-slate-400 focus:outline-none focus:border-purple-500"
              />
            </div>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-slate-800/40 text-slate-400 font-semibold uppercase text-[10px] tracking-wider border-b border-slate-800">
                <tr>
                  <th className="py-2.5 px-3">Organization</th>
                  <th className="py-2.5 px-3">Max Agent Capacity</th>
                  <th className="py-2.5 px-3">Onboarded Agents</th>
                  <th className="py-2.5 px-3">Available Slots</th>
                  <th className="py-2.5 px-3">Users</th>
                  <th className="py-2.5 px-3">Tokens Consumed</th>
                  <th className="py-2.5 px-3">Total Cost</th>
                  <th className="py-2.5 px-3 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60 text-slate-200">
                {paginatedOrgs.length === 0 ? (
                  <tr>
                    <td colSpan={8} className="py-6 text-center text-slate-400 italic">
                      No organizations found.
                    </td>
                  </tr>
                ) : (
                  paginatedOrgs.map((org) => (
                    <tr key={org.organization_name} className="hover:bg-slate-800/30 transition-colors">
                      <td className="py-3 px-3 font-semibold text-white">
                        {org.organization_name}
                      </td>
                      <td className="py-3 px-3">
                        {editingOrg === org.organization_name ? (
                          <div className="flex items-center gap-1.5">
                            <input
                              type="number"
                              min="1"
                              value={newCapacity}
                              onChange={e => setNewCapacity(e.target.value)}
                              className="w-16 px-2 py-0.5 bg-slate-800 border border-purple-500 rounded text-xs text-white"
                            />
                            <button
                              onClick={() => handleUpdateCapacity(org.organization_name)}
                              disabled={updatingCap}
                              className="px-2 py-0.5 bg-purple-600 hover:bg-purple-500 text-white font-bold rounded text-[11px]"
                            >
                              Save
                            </button>
                            <button
                              onClick={() => setEditingOrg(null)}
                              className="px-2 py-0.5 bg-slate-700 text-slate-300 rounded text-[11px]"
                            >
                              Cancel
                            </button>
                          </div>
                        ) : (
                          <span className="inline-flex items-center gap-1 font-bold text-purple-300 bg-purple-500/10 px-2 py-0.5 rounded border border-purple-500/20">
                            {org.max_agent_capacity} Agents Max
                          </span>
                        )}
                      </td>
                      <td className="py-3 px-3 font-medium text-slate-300">
                        {org.total_onboarded_agents}
                      </td>
                      <td className="py-3 px-3">
                        <span className={`font-semibold ${org.available_capacity > 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                          {org.available_capacity} slots remaining
                        </span>
                      </td>
                      <td className="py-3 px-3 text-slate-300 font-medium">
                        {org.user_count} users
                      </td>
                      <td className="py-3 px-3 text-purple-300 font-mono font-semibold">
                        {(org.total_tokens_consumed || 0).toLocaleString()}
                      </td>
                      <td className="py-3 px-3 text-emerald-400 font-mono font-bold">
                        ${org.total_cost || 0}
                      </td>
                      <td className="py-3 px-3 text-right">
                        <div className="flex items-center justify-end gap-2">
                          <button
                            onClick={() => setSelectedOrgModal(org)}
                            className="inline-flex items-center gap-1 px-2 py-1 rounded bg-purple-900/40 hover:bg-purple-800/60 border border-purple-500/30 text-xs font-semibold text-purple-200 transition-colors"
                          >
                            <Eye className="w-3 h-3" />
                            Inspect Users
                          </button>
                          <button
                            onClick={() => {
                              setEditingOrg(org.organization_name);
                              setNewCapacity(org.max_agent_capacity);
                            }}
                            className="inline-flex items-center gap-1 px-2.5 py-1 rounded bg-slate-800 hover:bg-slate-700 border border-slate-700 text-xs font-semibold text-slate-300 transition-colors"
                          >
                            <Settings className="w-3 h-3" />
                            Cap Limit
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>

          {/* Pagination Controls */}
          <div className="flex items-center justify-between pt-2 border-t border-slate-800 text-xs text-slate-400">
            <span>
              Page {currentPage} of {totalPages} ({filteredOrgs.length} organizations)
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

      </div>

      {/* Organization Detailed Inspection Modal */}
      {selectedOrgModal && (
        <div className="fixed inset-0 z-[9999] flex items-center justify-center p-4 bg-black/80 backdrop-blur-md">
          <div className="w-full max-w-4xl bg-slate-900 border border-purple-500/30 rounded-2xl p-6 shadow-2xl space-y-4 max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <div>
                <span className="text-[10px] uppercase tracking-wider font-bold text-purple-400">Organization Telemetry</span>
                <h3 className="text-xl font-bold text-white flex items-center gap-2">
                  <Building2 className="w-5 h-5 text-purple-400" />
                  {selectedOrgModal.organization_name}
                </h3>
              </div>
              <button
                onClick={() => setSelectedOrgModal(null)}
                className="p-1 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-400 hover:text-white"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Summary Row */}
            <div className="grid grid-cols-4 gap-3 text-xs">
              <div className="p-3 bg-slate-800/50 rounded-xl border border-slate-700/50">
                <span className="text-slate-400">Max Capacity Cap</span>
                <div className="text-lg font-bold text-purple-300">{selectedOrgModal.max_agent_capacity} Agents</div>
              </div>
              <div className="p-3 bg-slate-800/50 rounded-xl border border-slate-700/50">
                <span className="text-slate-400">Onboarded Agents</span>
                <div className="text-lg font-bold text-emerald-400">{selectedOrgModal.total_onboarded_agents} Active</div>
              </div>
              <div className="p-3 bg-slate-800/50 rounded-xl border border-slate-700/50">
                <span className="text-slate-400">Total AI Tokens</span>
                <div className="text-lg font-bold text-indigo-300">{(selectedOrgModal.total_tokens_consumed || 0).toLocaleString()}</div>
              </div>
              <div className="p-3 bg-slate-800/50 rounded-xl border border-slate-700/50">
                <span className="text-slate-400">Total Usage Cost</span>
                <div className="text-lg font-bold text-emerald-400">${selectedOrgModal.total_cost || 0}</div>
              </div>
            </div>

            {/* User Breakdown Table */}
            <div>
              <h4 className="text-sm font-bold text-white mb-2 flex items-center gap-2">
                <Users className="w-4 h-4 text-purple-400" />
                Organization Users & Token Usage Breakdown
              </h4>
              <div className="overflow-x-auto rounded-xl border border-slate-800">
                <table className="w-full text-left text-xs">
                  <thead className="bg-slate-800/80 text-slate-300 uppercase text-[10px] font-semibold">
                    <tr>
                      <th className="py-2.5 px-3">User Email</th>
                      <th className="py-2.5 px-3">Name</th>
                      <th className="py-2.5 px-3">Role</th>
                      <th className="py-2.5 px-3 text-right">AI Tokens</th>
                      <th className="py-2.5 px-3 text-right">Calculated Cost</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800 text-slate-200">
                    {(selectedOrgModal.users || []).map((u) => (
                      <tr key={u.id} className="hover:bg-slate-800/40">
                        <td className="py-2.5 px-3 font-semibold text-white">{u.email}</td>
                        <td className="py-2.5 px-3 text-slate-300">
                          {(u.first_name || u.last_name) ? `${u.first_name || ''} ${u.last_name || ''}`.trim() : '—'}
                        </td>
                        <td className="py-2.5 px-3">
                          <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                            u.is_super_admin
                              ? 'bg-purple-500/20 text-purple-300 border border-purple-500/30'
                              : u.is_org_admin
                              ? 'bg-blue-500/20 text-blue-300 border border-blue-500/30'
                              : 'bg-slate-800 text-slate-400'
                          }`}>
                            {u.is_super_admin ? 'SUPER ADMIN' : u.is_org_admin ? 'ORG ADMIN' : 'MEMBER'}
                          </span>
                        </td>
                        <td className="py-2.5 px-3 text-right font-mono text-purple-300 font-semibold">
                          {(u.ai_tokens || 0).toLocaleString()}
                        </td>
                        <td className="py-2.5 px-3 text-right font-mono text-emerald-400 font-bold">
                          ${u.total_cost || 0}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            <div className="flex justify-end pt-2">
              <button
                onClick={() => setSelectedOrgModal(null)}
                className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-white font-bold rounded-xl text-xs"
              >
                Close Inspection
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
