import React, { useState, useEffect } from 'react';
import { 
  Building2, Users, Bot, Container, Layers, RefreshCw, 
  AlertCircle, DollarSign, Cpu, FolderKanban, UserCheck, 
  Percent, ArrowRight, CheckCircle2, Shield, Settings, Search, 
  ChevronLeft, ChevronRight, Activity, Eye, X, Coins, FileText, FileSpreadsheet, Calendar
} from 'lucide-react';
import { generateSuperAdminPDF } from './superAdminPdfGenerator';
import { API_ENDPOINTS } from '../config';

export default function SuperAdminDashboard() {
  const [stats, setStats] = useState(null);
  const [orgs, setOrgs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  // Main Tabs State
  const [activeMainTab, setActiveMainTab] = useState('platform'); // 'platform' | 'vibecoding'

  // Vibecoding Telemetry State
  const [vibeData, setVibeData] = useState(null);
  const [vibeLoading, setVibeLoading] = useState(false);
  const [vibeError, setVibeError] = useState('');
  const [vibeSubTab, setVibeSubTab] = useState('orgs'); // 'orgs' | 'projects' | 'users'
  const [vibeSearchQuery, setVibeSearchQuery] = useState('');
  const [vibePage, setVibePage] = useState(1);
  const [vibeSelectedOrg, setVibeSelectedOrg] = useState(null);
  const [vibeSelectedUser, setVibeSelectedUser] = useState(null);

  // Date Filters
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');
  
  // Selected Org for detailed inspection modal
  const [selectedOrgModal, setSelectedOrgModal] = useState(null);
  const [selectedOrgProjModal, setSelectedOrgProjModal] = useState(null);

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
      let vibeUrl = API_ENDPOINTS.SUPERADMIN_VIBECODING_COSTS;

      const queryParams = [];
      if (startDate) queryParams.push(`start_date=${startDate}`);
      if (endDate) queryParams.push(`end_date=${endDate}`);
      if (queryParams.length > 0) {
        const queryStr = `?${queryParams.join('&')}`;
        statsUrl += queryStr;
        orgsUrl += queryStr;
        vibeUrl += queryStr;
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

      // Fetch Vibecoding Costs
      setVibeLoading(true);
      const vibeRes = await fetch(vibeUrl, { headers });
      if (vibeRes.ok) {
        const vData = await vibeRes.json();
        setVibeData(vData);
      } else {
        setVibeError('Failed to fetch Vibecoding costs');
      }
    } catch (err) {
      setError(err.message || 'Error loading Super Admin telemetry');
    } finally {
      setLoading(false);
      setVibeLoading(false);
    }
  };

  useEffect(() => {
    const isSuper = localStorage.getItem('is_super_admin') === 'true';
    if (!isSuper) {
      window.location.replace('/status-dashboard');
      return;
    }
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

  const handleExportMasterExcel = async () => {
    try {
      const headers = { Authorization: `Bearer ${token}` };
      let downloadUrl = API_ENDPOINTS.SUPERADMIN_MASTER_REPORT_EXPORT || '/api/superadmin/master-report/export';
      const params = [];
      if (startDate) params.push(`start_date=${startDate}`);
      if (endDate) params.push(`end_date=${endDate}`);
      if (params.length > 0) downloadUrl += `?${params.join('&')}`;

      const res = await fetch(downloadUrl, { headers });
      if (!res.ok) {
        const errText = await res.text();
        throw new Error(errText || 'Failed to download Master Excel Report');
      }

      const blob = await res.blob();
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute(
        'download',
        `Dsuite_Vibecoding_Master_Report_${new Date().toISOString().split('T')[0]}.xlsx`
      );
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      window.URL.revokeObjectURL(url);
    } catch (e) {
      alert('Failed to export Master Excel Report: ' + e.message);
    }
  };

  const handleExportVibeExcel = () => {
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
      rows.push(['VIBECODING COSTS & USAGE TELEMETRY REPORT']);
      rows.push(['Generated At:', new Date().toLocaleString()]);
      if (startDate || endDate) {
        rows.push(['Filter Date Range:', `${startDate || 'Start'} to ${endDate || 'Present'}`]);
      }
      rows.push([]);

      rows.push(['EXECUTIVE VIBECODING SUMMARY']);
      rows.push(['Total Organizations', vibeData?.summary?.total_organizations || 0]);
      rows.push(['Total Active Projects', vibeData?.summary?.total_projects || 0]);
      rows.push(['Total Onboarded Users', vibeData?.summary?.total_users || 0]);
      rows.push(['Total Prompts Logged', vibeData?.summary?.total_prompts || 0]);
      rows.push(['Prompt Tokens', vibeData?.summary?.prompt_tokens || 0]);
      rows.push(['Completion Tokens', vibeData?.summary?.completion_tokens || 0]);
      rows.push(['Total Tokens Consumed', vibeData?.summary?.total_tokens || 0]);
      rows.push(['Total Vibecoding Cost ($)', vibeData?.summary?.total_cost || 0]);
      rows.push([]);

      rows.push(['ORGANIZATION-WISE VIBECODING BREAKDOWN']);
      rows.push(['Organization Name', 'Users', 'Projects', 'Prompts', 'Prompt Tokens', 'Completion Tokens', 'Total Tokens', 'Total Cost (USD)']);
      (vibeData?.organization_breakdown || []).forEach(o => {
        rows.push([
          o.organization_name,
          o.user_count,
          o.project_count,
          o.log_count,
          o.prompt_tokens,
          o.completion_tokens,
          o.total_tokens,
          o.total_cost
        ]);
      });

      rows.push([]);
      rows.push(['PROJECT-WISE VIBECODING BREAKDOWN']);
      rows.push(['Project ID', 'Project Name', 'Organization', 'User Email', 'Prompts', 'Prompt Tokens', 'Completion Tokens', 'Total Tokens', 'Total Cost (USD)']);
      (vibeData?.project_breakdown || []).forEach(p => {
        rows.push([
          p.project_id,
          p.project_name,
          p.organization_name,
          p.email,
          p.log_count,
          p.prompt_tokens,
          p.completion_tokens,
          p.total_tokens,
          p.total_cost
        ]);
      });

      rows.push([]);
      rows.push(['USER-WISE VIBECODING BREAKDOWN']);
      rows.push(['Username', 'Email', 'Full Name', 'Organization', 'Projects', 'Prompts', 'Prompt Tokens', 'Completion Tokens', 'Total Tokens', 'Total Cost (USD)']);
      (vibeData?.user_breakdown || []).forEach(u => {
        rows.push([
          u.username,
          u.email,
          u.full_name,
          u.organization_name,
          u.project_count,
          u.log_count,
          u.prompt_tokens,
          u.completion_tokens,
          u.total_tokens,
          u.total_cost
        ]);
      });

      const csvContent = rows
        .map(row => row.map(cell => escapeCSV(cell)).join(','))
        .join('\n');

      const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      const fileName = `Vibecoding_Costs_Report_${new Date().toISOString().split('T')[0]}.csv`;

      link.setAttribute('href', url);
      link.setAttribute('download', fileName);
      link.style.visibility = 'hidden';
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);
    } catch (e) {
      alert('Failed to export Vibecoding CSV: ' + e.message);
    }
  };

  const handleDownloadPDF = () => {
    const range = (startDate || endDate) ? `${startDate || 'Start'} to ${endDate || 'Present'}` : 'All-Time';
    generateSuperAdminPDF(
      orgs, 
      stats, 
      "Global Organizations Telemetry & Capacity Report", 
      "Executive dashboard tracking capacity, onboarded agents, members, and spend",
      `Organizations_Telemetry_Report_${new Date().toISOString().split('T')[0]}.pdf`,
      range
    );
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
          <span className="text-sm font-medium">Loading Super Admin Dashboard...</span>
        </div>
      </div>
    );
  }

  return (
    <div className="h-full overflow-y-auto bg-slate-50 dark:bg-slate-950 p-4 sm:p-6 text-slate-900 dark:text-slate-100 transition-colors">
      <div className="max-w-7xl mx-auto space-y-6">
        
        {/* Actions Toolbar */}
        <div className="flex flex-wrap items-center justify-end gap-2 border-b border-slate-200 dark:border-purple-500/20 pb-3">
          <div className="flex flex-wrap items-center gap-2 ml-auto">
            {activeMainTab === 'platform' ? (
              <>
                <button
                  onClick={handleDownloadPDF}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-white dark:bg-purple-900/40 hover:bg-slate-100 dark:hover:bg-purple-800/60 border border-slate-200 dark:border-purple-500/30 text-purple-700 dark:text-purple-200 text-xs font-semibold transition-all shadow-sm cursor-pointer"
                >
                  <FileText className="w-3.5 h-3.5 text-purple-300" />
                  Download PDF Report
                </button>

                <button
                  onClick={handleExportExcel}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-white dark:bg-emerald-950/60 hover:bg-slate-100 dark:hover:bg-emerald-900/70 border border-slate-200 dark:border-emerald-500/30 text-emerald-700 dark:text-emerald-300 text-xs font-semibold transition-all shadow-sm cursor-pointer"
                  title="Export Dsuite Platform Governance CSV"
                >
                  <FileSpreadsheet className="w-3.5 h-3.5 text-emerald-400" />
                  Export Dsuite CSV
                </button>
              </>
            ) : (
              <button
                onClick={handleExportVibeExcel}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-white dark:bg-cyan-950/80 hover:bg-slate-100 dark:hover:bg-cyan-900/90 border border-slate-200 dark:border-cyan-500/40 text-cyan-700 dark:text-cyan-300 text-xs font-bold transition-all shadow-sm cursor-pointer"
                title="Export Vibecoding Telemetry CSV"
              >
                <FileSpreadsheet className="w-3.5 h-3.5 text-cyan-400" />
                Export Vibecoding CSV
              </button>
            )}

            <button
              onClick={handleExportMasterExcel}
              className="flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg bg-gradient-to-r from-purple-600 to-cyan-600 hover:from-purple-700 hover:to-cyan-700 border border-purple-500/40 text-white text-xs font-bold transition-all shadow-md cursor-pointer"
              title="Export Multi-Sheet Master Report (.xlsx) for both Dsuite & Vibecoding"
            >
              <FileSpreadsheet className="w-4 h-4 text-cyan-400" />
              Master Report (.xlsx)
            </button>

            <button
              onClick={fetchData}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-white dark:bg-slate-800 hover:bg-slate-100 dark:hover:bg-slate-700 border border-slate-200 dark:border-slate-700 text-slate-700 dark:text-slate-300 text-xs font-semibold transition-all shadow-sm cursor-pointer"
            >
              <RefreshCw className="w-3.5 h-3.5" />
              Refresh
            </button>
          </div>
        </div>

        {/* Date Filter Bar */}
        <div className="p-3.5 rounded-xl bg-white dark:bg-slate-900/60 border border-slate-200 dark:border-purple-500/20 shadow-sm backdrop-blur flex flex-wrap items-center justify-between gap-3 text-xs">
          <div className="flex items-center gap-2 font-semibold text-slate-700 dark:text-slate-300">
            <Calendar className="w-4 h-4 text-purple-400" />
            <span>Filter Telemetry by Date Range:</span>
          </div>

          <div className="flex flex-wrap items-center gap-3">
            <div className="flex items-center gap-2">
              <span className="text-slate-500 dark:text-slate-400 text-[11px]">Start:</span>
              <input
                type="date"
                value={startDate}
                onChange={e => setStartDate(e.target.value)}
                className="px-2.5 py-1 bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded text-xs text-slate-900 dark:text-white focus:outline-none focus:border-purple-500"
              />
            </div>

            <div className="flex items-center gap-2">
              <span className="text-slate-500 dark:text-slate-400 text-[11px]">End:</span>
              <input
                type="date"
                value={endDate}
                onChange={e => setEndDate(e.target.value)}
                className="px-2.5 py-1 bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded text-xs text-slate-900 dark:text-white focus:outline-none focus:border-purple-500"
              />
            </div>

            {(startDate || endDate) && (
              <button
                onClick={() => { setStartDate(''); setEndDate(''); }}
                className="px-2 py-1 bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-300 rounded text-[11px] cursor-pointer"
              >
                Clear Dates
              </button>
            )}
          </div>
        </div>

        {/* Main Tab Navigation Bar */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-slate-200 dark:border-purple-500/20 pb-3">
          <div className="flex items-center gap-3">
            <button
              onClick={() => setActiveMainTab('platform')}
              className={`flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-extrabold transition-all border ${
                activeMainTab === 'platform'
                  ? 'bg-purple-600/90 text-white border-purple-500 shadow-lg shadow-purple-600/30'
                  : 'bg-white dark:bg-slate-900/60 text-slate-600 dark:text-slate-400 border-slate-200 dark:border-slate-800 hover:bg-slate-100 dark:hover:bg-slate-800 hover:text-slate-900 dark:hover:text-slate-200 shadow-sm'
              }`}
            >
              <Shield className="w-4 h-4 text-purple-300" />
              <span>DSuite Analytics & Costs</span>
            </button>

            <button
              onClick={() => setActiveMainTab('vibecoding')}
              className={`flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-extrabold transition-all border ${
                activeMainTab === 'vibecoding'
                  ? 'bg-cyan-600/90 text-white border-cyan-500 shadow-lg shadow-cyan-600/30'
                  : 'bg-white dark:bg-slate-900/60 text-slate-600 dark:text-slate-400 border-slate-200 dark:border-slate-800 hover:bg-slate-100 dark:hover:bg-slate-800 hover:text-slate-900 dark:hover:text-slate-200 shadow-sm'
              }`}
            >
              <Coins className="w-4 h-4 text-cyan-300" />
              <span>Vibecoding Analytics & Costs</span>
              {vibeData?.status === 'not_available' ? (
                <span className="px-2 py-0.5 rounded text-[10px] bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400 border border-slate-300 dark:border-slate-700 font-mono font-bold">
                  Not Available
                </span>
              ) : (
                vibeData?.summary?.total_cost > 0 && (
                  <span className="px-2 py-0.5 rounded text-[10px] bg-emerald-500/20 text-emerald-300 border border-emerald-500/30 font-mono font-bold">
                    ${vibeData.summary.total_cost}
                  </span>
                )
              )}
            </button>
          </div>

          {activeMainTab === 'vibecoding' && (
            <button
              onClick={handleExportVibeExcel}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-white dark:bg-emerald-950/60 hover:bg-slate-100 dark:hover:bg-emerald-900/70 border border-slate-200 dark:border-emerald-500/30 text-emerald-700 dark:text-emerald-300 text-xs font-semibold transition-all shadow-sm cursor-pointer"
            >
              <FileSpreadsheet className="w-3.5 h-3.5 text-emerald-400" />
              Export Vibecoding CSV
            </button>
          )}
        </div>

        {activeMainTab === 'platform' && (
          <>
        {/* Metric Cards Grid (Compact & Responsive) */}
        {stats && (
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
            
            <div className="p-3.5 rounded-xl bg-white dark:bg-slate-900/60 border border-slate-200 dark:border-purple-500/20 shadow-sm backdrop-blur">
              <div className="flex items-center justify-between text-slate-500 dark:text-slate-400 text-xs mb-1">
                <span className="font-semibold uppercase tracking-wider text-[10px]">Organizations</span>
                <Building2 className="w-4 h-4 text-purple-400" />
              </div>
              <div className="text-xl font-bold text-slate-900 dark:text-white">{stats.total_organizations}</div>
              <div className="text-[10px] text-slate-500 dark:text-slate-400 mt-0.5">Registered tenant accounts</div>
            </div>

            <div className="p-3.5 rounded-xl bg-white dark:bg-slate-900/60 border border-slate-200 dark:border-purple-500/20 shadow-sm backdrop-blur">
              <div className="flex items-center justify-between text-slate-500 dark:text-slate-400 text-xs mb-1">
                <span className="font-semibold uppercase tracking-wider text-[10px]">Onboarded Agents</span>
                <Bot className="w-4 h-4 text-emerald-400" />
              </div>
              <div className="text-xl font-bold text-slate-900 dark:text-white">{stats.total_onboarded_agents}</div>
              <div className="text-[10px] text-emerald-400 mt-0.5">Across all organizations</div>
            </div>

            <div className="p-3.5 rounded-xl bg-white dark:bg-slate-900/60 border border-slate-200 dark:border-purple-500/20 shadow-sm backdrop-blur">
              <div className="flex items-center justify-between text-slate-500 dark:text-slate-400 text-xs mb-1">
                <span className="font-semibold uppercase tracking-wider text-[10px]">Docker Containers</span>
                <Container className="w-4 h-4 text-cyan-400" />
              </div>
              <div className="text-xl font-bold text-slate-900 dark:text-white">{stats.total_running_containers}</div>
              <div className="text-[10px] text-cyan-400 mt-0.5">Active worker environments</div>
            </div>

            <div className="p-3.5 rounded-xl bg-white dark:bg-slate-900/60 border border-slate-200 dark:border-purple-500/20 shadow-sm backdrop-blur">
              <div className="flex items-center justify-between text-slate-500 dark:text-slate-400 text-xs mb-1">
                <span className="font-semibold uppercase tracking-wider text-[10px]">Dedicated Agents</span>
                <Users className="w-4 h-4 text-blue-400" />
              </div>
              <div className="text-xl font-bold text-slate-900 dark:text-white">{stats.dedicated_agents}</div>
              <div className="text-[10px] text-blue-400 mt-0.5">Project-exclusive agents</div>
            </div>

            <div className="p-3.5 rounded-xl bg-white dark:bg-slate-900/60 border border-slate-200 dark:border-purple-500/20 shadow-sm backdrop-blur">
              <div className="flex items-center justify-between text-slate-500 dark:text-slate-400 text-xs mb-1">
                <span className="font-semibold uppercase tracking-wider text-[10px]">Shared Agents</span>
                <Layers className="w-4 h-4 text-indigo-400" />
              </div>
              <div className="text-xl font-bold text-slate-900 dark:text-white">{stats.shared_agents}</div>
              <div className="text-[10px] text-indigo-400 mt-0.5">Central capacity pool</div>
            </div>

            <div className="p-3.5 rounded-xl bg-white dark:bg-slate-900/60 border border-slate-200 dark:border-purple-500/20 shadow-sm backdrop-blur">
              <div className="flex items-center justify-between text-slate-500 dark:text-slate-400 text-xs mb-1">
                <span className="font-semibold uppercase tracking-wider text-[10px]">Borrowed Dedicated</span>
                <Activity className="w-4 h-4 text-amber-400" />
              </div>
              <div className="text-xl font-bold text-slate-900 dark:text-white">{stats.borrowed_dedicated_agents}</div>
              <div className="text-[10px] text-amber-400 mt-0.5">Serving shared tasks (preemptable)</div>
            </div>

            <div className="p-3.5 rounded-xl bg-white dark:bg-slate-900/60 border border-slate-200 dark:border-purple-500/20 shadow-sm backdrop-blur">
              <div className="flex items-center justify-between text-slate-500 dark:text-slate-400 text-xs mb-1">
                <span className="font-semibold uppercase tracking-wider text-[10px]">Pending Requests</span>
                <AlertCircle className="w-4 h-4 text-rose-400" />
              </div>
              <div className="text-xl font-bold text-slate-900 dark:text-white">{stats.pending_capacity_requests}</div>
              <div className="text-[10px] text-rose-400 mt-0.5">Awaiting Super Admin approval</div>
            </div>

            <div className="p-3.5 rounded-xl bg-white dark:bg-slate-900/60 border border-slate-200 dark:border-purple-500/20 shadow-sm backdrop-blur">
              <div className="flex items-center justify-between text-slate-500 dark:text-slate-400 text-xs mb-1">
                <span className="font-semibold uppercase tracking-wider text-[10px]">Dsuite Billing</span>
                <DollarSign className="w-4 h-4 text-purple-400" />
              </div>
              <div className="text-xl font-bold text-purple-700 dark:text-purple-300">
                ${(stats.dsuite_billing !== undefined ? stats.dsuite_billing : (stats.platform_billing || 0)).toFixed(2)}
              </div>
              <div className="text-[10px] text-purple-600 dark:text-purple-400 mt-0.5">Dsuite AI Governance cost</div>
            </div>

            <div className="p-3.5 rounded-xl bg-white dark:bg-slate-900/60 border border-slate-200 dark:border-cyan-500/20 shadow-sm backdrop-blur">
              <div className="flex items-center justify-between text-slate-500 dark:text-slate-400 text-xs mb-1">
                <span className="font-semibold uppercase tracking-wider text-[10px]">Vibecoding Billing</span>
                <Coins className="w-4 h-4 text-cyan-400" />
              </div>
              <div className="text-xl font-bold text-cyan-700 dark:text-cyan-300">
                ${(stats.vibecoding_billing !== undefined ? stats.vibecoding_billing : (vibeData?.summary?.total_cost || 0)).toFixed(2)}
              </div>
              <div className="text-[10px] text-cyan-400 mt-0.5">Vibecoding AI inference cost</div>
            </div>

            <div className="p-3.5 rounded-xl bg-white dark:bg-slate-900/60 border border-slate-200 dark:border-emerald-500/20 shadow-sm backdrop-blur">
              <div className="flex items-center justify-between text-slate-500 dark:text-slate-400 text-xs mb-1">
                <span className="font-semibold uppercase tracking-wider text-[10px]">Total Combined Billing</span>
                <DollarSign className="w-4 h-4 text-emerald-400" />
              </div>
              <div className="text-xl font-bold text-emerald-600 dark:text-emerald-400">${stats.platform_billing}</div>
              <div className="text-[10px] text-emerald-400 mt-0.5">Dsuite + Vibecoding total</div>
            </div>

            <div className="p-3.5 rounded-xl bg-white dark:bg-slate-900/60 border border-slate-200 dark:border-purple-500/20 shadow-sm backdrop-blur">
              <div className="flex items-center justify-between text-slate-500 dark:text-slate-400 text-xs mb-1">
                <span className="font-semibold uppercase tracking-wider text-[10px]">AI Tokens Consumed</span>
                <Cpu className="w-4 h-4 text-purple-400" />
              </div>
              <div className="text-xl font-bold text-slate-900 dark:text-white">{stats.ai_tokens_consumed.toLocaleString()}</div>
              <div className="text-[10px] text-purple-600 dark:text-purple-400 mt-0.5">Prompt + completion tokens</div>
            </div>

            <div className="p-3.5 rounded-xl bg-white dark:bg-slate-900/60 border border-slate-200 dark:border-purple-500/20 shadow-sm backdrop-blur">
              <div className="flex items-center justify-between text-slate-500 dark:text-slate-400 text-xs mb-1">
                <span className="font-semibold uppercase tracking-wider text-[10px]">Project Telemetry</span>
                <FolderKanban className="w-4 h-4 text-cyan-400" />
              </div>
              <div className="text-xl font-bold text-slate-900 dark:text-white">
                {stats.project_telemetry?.active} / {stats.project_telemetry?.total}
              </div>
              <div className="text-[10px] text-cyan-400 mt-0.5">Active / total registered</div>
            </div>

            <div className="p-3.5 rounded-xl bg-white dark:bg-slate-900/60 border border-slate-200 dark:border-purple-500/20 shadow-sm backdrop-blur">
              <div className="flex items-center justify-between text-slate-500 dark:text-slate-400 text-xs mb-1">
                <span className="font-semibold uppercase tracking-wider text-[10px]">Active Users</span>
                <UserCheck className="w-4 h-4 text-sky-400" />
              </div>
              <div className="text-xl font-bold text-slate-900 dark:text-white">{stats.active_users}</div>
              <div className="text-[10px] text-sky-400 mt-0.5">Validated accounts</div>
            </div>

            <div className="p-3.5 rounded-xl bg-white dark:bg-slate-900/60 border border-slate-200 dark:border-purple-500/20 shadow-sm backdrop-blur">
              <div className="flex items-center justify-between text-slate-500 dark:text-slate-400 text-xs mb-1">
                <span className="font-semibold uppercase tracking-wider text-[10px]">Agent Utilization</span>
                <Percent className="w-4 h-4 text-purple-400" />
              </div>
              <div className="text-xl font-bold text-slate-900 dark:text-white">{stats.agent_utilization}%</div>
              <div className="text-[10px] text-purple-600 dark:text-purple-400 mt-0.5">Execution capacity active</div>
            </div>

          </div>
        )}

        {/* Organizations Capacity Management Table */}
        <div className="p-5 rounded-2xl bg-white dark:bg-slate-900/80 border border-slate-200 dark:border-purple-500/20 shadow-sm space-y-4">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <div>
              <h2 className="text-base font-bold text-slate-900 dark:text-white flex items-center gap-2">
                <Building2 className="w-4 h-4 text-purple-400" />
                Global Organizations Telemetry & Capacity
              </h2>
              <p className="text-xs text-slate-500 dark:text-slate-400">
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
                className="w-full pl-8 pr-3 py-1.5 bg-slate-50 dark:bg-slate-800/60 border border-slate-200 dark:border-slate-700 rounded-lg text-xs text-slate-900 dark:text-white placeholder-slate-400 focus:outline-none focus:border-purple-500"
              />
            </div>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-slate-50 dark:bg-slate-800/40 text-slate-500 dark:text-slate-400 font-semibold uppercase text-[10px] tracking-wider border-b border-slate-200 dark:border-slate-800">
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
              <tbody className="divide-y divide-slate-200 dark:divide-slate-800/60 text-slate-700 dark:text-slate-200">
                {paginatedOrgs.length === 0 ? (
                  <tr>
                    <td colSpan={8} className="py-6 text-center text-slate-400 dark:text-slate-500 italic">
                      No organizations found.
                    </td>
                  </tr>
                ) : (
                  paginatedOrgs.map((org) => (
                    <tr key={org.organization_name} className="hover:bg-slate-50/80 dark:hover:bg-slate-800/30 transition-colors">
                      <td className="py-3 px-3 font-semibold text-slate-900 dark:text-white">
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
                              className="w-16 px-2 py-0.5 bg-slate-50 dark:bg-slate-800 border border-purple-500 rounded text-xs text-slate-900 dark:text-white"
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
                              className="px-2 py-0.5 bg-slate-200 dark:bg-slate-700 text-slate-700 dark:text-slate-300 rounded text-[11px] cursor-pointer"
                            >
                              Cancel
                            </button>
                          </div>
                        ) : (
                          <span className="inline-flex items-center gap-1 font-bold text-purple-700 dark:text-purple-300 bg-purple-50 dark:bg-purple-500/10 px-2 py-0.5 rounded border border-purple-200 dark:border-purple-500/20">
                            {org.max_agent_capacity} Agents Max
                          </span>
                        )}
                      </td>
                      <td className="py-3 px-3 font-medium text-slate-600 dark:text-slate-300">
                        {org.total_onboarded_agents}
                      </td>
                      <td className="py-3 px-3">
                        <span className={`font-semibold ${org.available_capacity > 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                          {org.available_capacity} slots remaining
                        </span>
                      </td>
                      <td className="py-3 px-3 text-slate-600 dark:text-slate-300 font-medium">
                        {org.user_count} users
                      </td>
                      <td className="py-3 px-3 text-purple-700 dark:text-purple-300 font-mono font-semibold">
                        {(org.total_tokens_consumed || 0).toLocaleString()}
                      </td>
                      <td className="py-3 px-3 text-emerald-600 dark:text-emerald-400 font-mono font-bold">
                        ${org.total_cost || 0}
                      </td>
                      <td className="py-3 px-3 text-right">
                        <div className="flex items-center justify-end gap-2">
                          <button
                            onClick={() => setSelectedOrgModal(org)}
                            className="inline-flex items-center gap-1 px-2 py-1 rounded bg-purple-50 dark:bg-purple-900/40 hover:bg-purple-100 dark:hover:bg-purple-800/60 border border-purple-200 dark:border-purple-500/30 text-xs font-semibold text-purple-700 dark:text-purple-200 transition-colors cursor-pointer"
                          >
                            <Eye className="w-3 h-3" />
                            Inspect Users
                          </button>
                          <button
                            onClick={() => setSelectedOrgProjModal(org)}
                            className="inline-flex items-center gap-1 px-2 py-1 rounded bg-blue-50 dark:bg-blue-900/40 hover:bg-blue-100 dark:hover:bg-blue-800/60 border border-blue-200 dark:border-blue-500/30 text-xs font-semibold text-blue-700 dark:text-blue-200 transition-colors cursor-pointer"
                          >
                            <Layers className="w-3 h-3" />
                            Inspect Projects
                          </button>
                          <button
                            onClick={() => {
                              setEditingOrg(org.organization_name);
                              setNewCapacity(org.max_agent_capacity);
                            }}
                            className="inline-flex items-center gap-1 px-2.5 py-1 rounded bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 dark:hover:bg-slate-700 border border-slate-200 dark:border-slate-700 text-xs font-semibold text-slate-700 dark:text-slate-300 transition-colors cursor-pointer"
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
          <div className="flex items-center justify-between pt-2 border-t border-slate-200 dark:border-slate-800 text-xs text-slate-500 dark:text-slate-400">
            <span>
              Page {currentPage} of {totalPages} ({filteredOrgs.length} organizations)
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
      </>
    )}

        {activeMainTab === 'vibecoding' && (
          <div className="space-y-6">
            {vibeData?.status === 'not_available' && (
              <div className="p-4 rounded-xl bg-amber-50 dark:bg-slate-900/80 border border-amber-300 dark:border-amber-500/30 text-amber-800 dark:text-amber-300 text-xs flex items-center justify-between gap-3 shadow-sm backdrop-blur">
                <div className="flex items-center gap-2.5">
                  <Coins className="w-5 h-5 text-amber-400 flex-shrink-0" />
                  <div>
                    <span className="font-bold text-slate-900 dark:text-white">Vibecoding API Not Available:</span> The Vibecoding telemetry endpoint (/vibecoding/api/telemetry/usage-costs) is unreachable. No telemetry data is available.
                  </div>
                </div>
                <span className="px-2.5 py-1 rounded-md bg-amber-500/20 text-amber-300 text-[11px] font-mono font-semibold border border-amber-500/30 whitespace-nowrap">
                  Not Available
                </span>
              </div>
            )}

            {/* Vibecoding Executive Metric Cards */}
            {vibeData?.summary && (
              <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
                <div className="p-3.5 rounded-xl bg-white dark:bg-slate-900/60 border border-slate-200 dark:border-cyan-500/20 shadow-sm backdrop-blur">
                  <div className="flex items-center justify-between text-slate-500 dark:text-slate-400 text-xs mb-1">
                    <span className="font-semibold uppercase tracking-wider text-[10px]">Organizations</span>
                    <Building2 className="w-4 h-4 text-cyan-400" />
                  </div>
                  <div className="text-xl font-bold text-slate-900 dark:text-white">{vibeData.summary.total_organizations}</div>
                  <div className="text-[10px] text-cyan-400 mt-0.5">Active Tenants</div>
                </div>

                <div className="p-3.5 rounded-xl bg-white dark:bg-slate-900/60 border border-slate-200 dark:border-purple-500/20 shadow-sm backdrop-blur">
                  <div className="flex items-center justify-between text-slate-500 dark:text-slate-400 text-xs mb-1">
                    <span className="font-semibold uppercase tracking-wider text-[10px]">Active Projects</span>
                    <FolderKanban className="w-4 h-4 text-purple-400" />
                  </div>
                  <div className="text-xl font-bold text-slate-900 dark:text-white">{vibeData.summary.total_projects}</div>
                  <div className="text-[10px] text-purple-600 dark:text-purple-400 mt-0.5">Vibecoding Workspaces</div>
                </div>

                <div className="p-3.5 rounded-xl bg-white dark:bg-slate-900/60 border border-slate-200 dark:border-blue-500/20 shadow-sm backdrop-blur">
                  <div className="flex items-center justify-between text-slate-500 dark:text-slate-400 text-xs mb-1">
                    <span className="font-semibold uppercase tracking-wider text-[10px]">Active Users</span>
                    <Users className="w-4 h-4 text-blue-400" />
                  </div>
                  <div className="text-xl font-bold text-slate-900 dark:text-white">{vibeData.summary.total_users}</div>
                  <div className="text-[10px] text-blue-400 mt-0.5">Registered Developers</div>
                </div>

                <div className="p-3.5 rounded-xl bg-white dark:bg-slate-900/60 border border-slate-200 dark:border-amber-500/20 shadow-sm backdrop-blur">
                  <div className="flex items-center justify-between text-slate-500 dark:text-slate-400 text-xs mb-1">
                    <span className="font-semibold uppercase tracking-wider text-[10px]">AI Prompts</span>
                    <Activity className="w-4 h-4 text-amber-400" />
                  </div>
                  <div className="text-xl font-bold text-slate-900 dark:text-white">{vibeData.summary.total_prompts}</div>
                  <div className="text-[10px] text-amber-400 mt-0.5">Generations Logged</div>
                </div>

                <div className="p-3.5 rounded-xl bg-white dark:bg-slate-900/60 border border-slate-200 dark:border-indigo-500/20 shadow-sm backdrop-blur">
                  <div className="flex items-center justify-between text-slate-500 dark:text-slate-400 text-xs mb-1">
                    <span className="font-semibold uppercase tracking-wider text-[10px]">Tokens Consumed</span>
                    <Cpu className="w-4 h-4 text-indigo-400" />
                  </div>
                  <div className="text-xl font-bold text-slate-900 dark:text-white">{(vibeData.summary.total_tokens || 0).toLocaleString()}</div>
                  <div className="text-[10px] text-indigo-400 mt-0.5">Prompt + Completion</div>
                </div>

                <div className="p-3.5 rounded-xl bg-white dark:bg-slate-900/60 border border-slate-200 dark:border-emerald-500/20 shadow-sm backdrop-blur">
                  <div className="flex items-center justify-between text-slate-500 dark:text-slate-400 text-xs mb-1">
                    <span className="font-semibold uppercase tracking-wider text-[10px]">Total Costs</span>
                    <Coins className="w-4 h-4 text-emerald-400" />
                  </div>
                  <div className="text-xl font-bold text-emerald-600 dark:text-emerald-400">${vibeData.summary.total_cost}</div>
                  <div className="text-[10px] text-emerald-400 mt-0.5">Calculated Usage Cost</div>
                </div>
              </div>
            )}

            {/* Vibecoding Breakdown Table Container */}
            <div className="p-5 rounded-2xl bg-white dark:bg-slate-900/80 border border-slate-200 dark:border-cyan-500/20 shadow-sm space-y-4">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-slate-800 pb-3">
                <div>
                  <h2 className="text-base font-bold text-slate-900 dark:text-white flex items-center gap-2">
                    <Coins className="w-4 h-4 text-cyan-400" />
                    Vibecoding Cost Breakdown Telemetry
                  </h2>
                  <p className="text-xs text-slate-500 dark:text-slate-400">
                    Detailed token usage and calculated platform costs categorized by Organization, Project, and User.
                  </p>
                </div>

                {/* Sub-Tabs Switcher */}
                <div className="flex items-center gap-1.5 p-1 bg-slate-100 dark:bg-slate-950/80 border border-slate-200 dark:border-slate-800 rounded-xl text-xs">
                  <button
                    onClick={() => { setVibeSubTab('orgs'); setVibePage(1); }}
                    className={`px-3 py-1 rounded-lg font-bold transition-colors ${
                      vibeSubTab === 'orgs'
                        ? 'bg-cyan-600 text-white'
                        : 'text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white hover:bg-slate-200 dark:hover:bg-slate-800'
                    }`}
                  >
                    Organization-Wise
                  </button>
                  <button
                    onClick={() => { setVibeSubTab('projects'); setVibePage(1); }}
                    className={`px-3 py-1 rounded-lg font-bold transition-colors ${
                      vibeSubTab === 'projects'
                        ? 'bg-cyan-600 text-white'
                        : 'text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white hover:bg-slate-200 dark:hover:bg-slate-800'
                    }`}
                  >
                    Project-Wise
                  </button>
                  <button
                    onClick={() => { setVibeSubTab('users'); setVibePage(1); }}
                    className={`px-3 py-1 rounded-lg font-bold transition-colors ${
                      vibeSubTab === 'users'
                        ? 'bg-cyan-600 text-white'
                        : 'text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white hover:bg-slate-200 dark:hover:bg-slate-800'
                    }`}
                  >
                    User-Wise
                  </button>
                </div>
              </div>

              {/* Filter & Search Bar */}
              <div className="flex items-center justify-between gap-3">
                <div className="relative w-full sm:w-80">
                  <Search className="w-3.5 h-3.5 absolute left-3 top-2.5 text-slate-400" />
                  <input
                    type="text"
                    placeholder={`Search ${vibeSubTab}...`}
                    value={vibeSearchQuery}
                    onChange={e => { setVibeSearchQuery(e.target.value); setVibePage(1); }}
                    className="w-full pl-8 pr-3 py-1.5 bg-slate-50 dark:bg-slate-800/60 border border-slate-200 dark:border-slate-700 rounded-lg text-xs text-slate-900 dark:text-white placeholder-slate-400 focus:outline-none focus:border-cyan-500"
                  />
                </div>
                {vibeLoading && (
                  <div className="flex items-center gap-2 text-xs text-cyan-400">
                    <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                    <span>Loading...</span>
                  </div>
                )}
              </div>

              {/* Sub-Tab 1: Organization-Wise Breakdown */}
              {vibeSubTab === 'orgs' && (
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-xs">
                    <thead className="bg-slate-50 dark:bg-slate-800/40 text-slate-500 dark:text-slate-400 font-semibold uppercase text-[10px] tracking-wider border-b border-slate-200 dark:border-slate-800">
                      <tr>
                        <th className="py-2.5 px-3">Organization</th>
                        <th className="py-2.5 px-3">Active Users</th>
                        <th className="py-2.5 px-3">Active Projects</th>
                        <th className="py-2.5 px-3">Prompts Logged</th>
                        <th className="py-2.5 px-3">Prompt Tokens</th>
                        <th className="py-2.5 px-3">Completion Tokens</th>
                        <th className="py-2.5 px-3">Total Tokens</th>
                        <th className="py-2.5 px-3">Total Cost</th>
                        <th className="py-2.5 px-3 text-right">Actions</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-200 dark:divide-slate-800/60 text-slate-700 dark:text-slate-200">
                      {vibeData?.organization_breakdown?.filter(o =>
                        o.organization_name.toLowerCase().includes(vibeSearchQuery.toLowerCase())
                      ).length === 0 ? (
                        <tr>
                          <td colSpan={9} className="py-6 text-center text-slate-400 dark:text-slate-500 italic">
                            No Organization telemetry records found.
                          </td>
                        </tr>
                      ) : (
                        vibeData?.organization_breakdown?.filter(o =>
                          o.organization_name.toLowerCase().includes(vibeSearchQuery.toLowerCase())
                        ).map(org => (
                          <tr key={org.organization_name} className="hover:bg-slate-50/80 dark:hover:bg-slate-800/30 transition-colors">
                            <td className="py-3 px-3 font-semibold text-slate-900 dark:text-white">
                              {org.organization_name}
                            </td>
                            <td className="py-3 px-3 text-slate-600 dark:text-slate-300">
                              {org.user_count} users
                            </td>
                            <td className="py-3 px-3 text-slate-600 dark:text-slate-300">
                              {org.project_count} projects
                            </td>
                            <td className="py-3 px-3 font-mono text-cyan-300">
                              {org.log_count}
                            </td>
                            <td className="py-3 px-3 font-mono text-slate-500 dark:text-slate-400">
                              {(org.prompt_tokens || 0).toLocaleString()}
                            </td>
                            <td className="py-3 px-3 font-mono text-slate-500 dark:text-slate-400">
                              {(org.completion_tokens || 0).toLocaleString()}
                            </td>
                            <td className="py-3 px-3 font-mono text-purple-300 font-semibold">
                              {(org.total_tokens || 0).toLocaleString()}
                            </td>
                            <td className="py-3 px-3 font-mono text-emerald-400 font-bold">
                              ${org.total_cost || 0}
                            </td>
                            <td className="py-3 px-3 text-right">
                              <button
                                onClick={() => setVibeSelectedOrg(org)}
                                className="inline-flex items-center gap-1 px-2.5 py-1 rounded bg-cyan-50 dark:bg-cyan-900/40 hover:bg-cyan-100 dark:hover:bg-cyan-800/60 border border-cyan-200 dark:border-cyan-500/30 text-xs font-semibold text-cyan-700 dark:text-cyan-200 transition-colors cursor-pointer"
                              >
                                <Eye className="w-3 h-3" />
                                Inspect Details
                              </button>
                            </td>
                          </tr>
                        ))
                      )}
                    </tbody>
                  </table>
                </div>
              )}

              {/* Sub-Tab 2: Project-Wise Breakdown */}
              {vibeSubTab === 'projects' && (
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-xs">
                    <thead className="bg-slate-50 dark:bg-slate-800/40 text-slate-500 dark:text-slate-400 font-semibold uppercase text-[10px] tracking-wider border-b border-slate-200 dark:border-slate-800">
                      <tr>
                        <th className="py-2.5 px-3">Project Name</th>
                        <th className="py-2.5 px-3">Project ID</th>
                        <th className="py-2.5 px-3">Organization</th>
                        <th className="py-2.5 px-3">User Email</th>
                        <th className="py-2.5 px-3">Prompts Logged</th>
                        <th className="py-2.5 px-3">Prompt Tokens</th>
                        <th className="py-2.5 px-3">Completion Tokens</th>
                        <th className="py-2.5 px-3">Total Tokens</th>
                        <th className="py-2.5 px-3 text-right">Total Cost</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-200 dark:divide-slate-800/60 text-slate-700 dark:text-slate-200">
                      {vibeData?.project_breakdown?.filter(p =>
                        p.project_name.toLowerCase().includes(vibeSearchQuery.toLowerCase()) ||
                        p.project_id.toLowerCase().includes(vibeSearchQuery.toLowerCase()) ||
                        p.organization_name.toLowerCase().includes(vibeSearchQuery.toLowerCase()) ||
                        p.email.toLowerCase().includes(vibeSearchQuery.toLowerCase())
                      ).length === 0 ? (
                        <tr>
                          <td colSpan={9} className="py-6 text-center text-slate-400 dark:text-slate-500 italic">
                            No Project telemetry records found.
                          </td>
                        </tr>
                      ) : (
                        vibeData?.project_breakdown?.filter(p =>
                          p.project_name.toLowerCase().includes(vibeSearchQuery.toLowerCase()) ||
                          p.project_id.toLowerCase().includes(vibeSearchQuery.toLowerCase()) ||
                          p.organization_name.toLowerCase().includes(vibeSearchQuery.toLowerCase()) ||
                          p.email.toLowerCase().includes(vibeSearchQuery.toLowerCase())
                        ).map(proj => (
                          <tr key={proj.project_id} className="hover:bg-slate-50/80 dark:hover:bg-slate-800/30 transition-colors">
                            <td className="py-3 px-3 font-semibold text-slate-900 dark:text-white">
                              {proj.project_name}
                            </td>
                            <td className="py-3 px-3 text-slate-500 dark:text-slate-400 font-mono">
                              {proj.project_id}
                            </td>
                            <td className="py-3 px-3 text-slate-600 dark:text-slate-300">
                              {proj.organization_name}
                            </td>
                            <td className="py-3 px-3 text-slate-600 dark:text-slate-300">
                              {proj.email}
                            </td>
                            <td className="py-3 px-3 font-mono text-cyan-300">
                              {proj.log_count}
                            </td>
                            <td className="py-3 px-3 font-mono text-slate-500 dark:text-slate-400">
                              {(proj.prompt_tokens || 0).toLocaleString()}
                            </td>
                            <td className="py-3 px-3 font-mono text-slate-500 dark:text-slate-400">
                              {(proj.completion_tokens || 0).toLocaleString()}
                            </td>
                            <td className="py-3 px-3 font-mono text-purple-300 font-semibold">
                              {(proj.total_tokens || 0).toLocaleString()}
                            </td>
                            <td className="py-3 px-3 text-right font-mono text-emerald-400 font-bold">
                              ${proj.total_cost || 0}
                            </td>
                          </tr>
                        ))
                      )}
                    </tbody>
                  </table>
                </div>
              )}

              {/* Sub-Tab 3: User-Wise Breakdown */}
              {vibeSubTab === 'users' && (
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-xs">
                    <thead className="bg-slate-50 dark:bg-slate-800/40 text-slate-500 dark:text-slate-400 font-semibold uppercase text-[10px] tracking-wider border-b border-slate-200 dark:border-slate-800">
                      <tr>
                        <th className="py-2.5 px-3">User Email / Username</th>
                        <th className="py-2.5 px-3">Full Name</th>
                        <th className="py-2.5 px-3">Organization</th>
                        <th className="py-2.5 px-3">Projects</th>
                        <th className="py-2.5 px-3">Prompts Logged</th>
                        <th className="py-2.5 px-3">Prompt Tokens</th>
                        <th className="py-2.5 px-3">Completion Tokens</th>
                        <th className="py-2.5 px-3">Total Tokens</th>
                        <th className="py-2.5 px-3">Total Cost</th>
                        <th className="py-2.5 px-3 text-right">Actions</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-200 dark:divide-slate-800/60 text-slate-700 dark:text-slate-200">
                      {vibeData?.user_breakdown?.filter(u =>
                        u.email.toLowerCase().includes(vibeSearchQuery.toLowerCase()) ||
                        u.username.toLowerCase().includes(vibeSearchQuery.toLowerCase()) ||
                        (u.full_name && u.full_name.toLowerCase().includes(vibeSearchQuery.toLowerCase())) ||
                        u.organization_name.toLowerCase().includes(vibeSearchQuery.toLowerCase())
                      ).length === 0 ? (
                        <tr>
                          <td colSpan={10} className="py-6 text-center text-slate-400 dark:text-slate-500 italic">
                            No User telemetry records found.
                          </td>
                        </tr>
                      ) : (
                        vibeData?.user_breakdown?.filter(u =>
                          u.email.toLowerCase().includes(vibeSearchQuery.toLowerCase()) ||
                          u.username.toLowerCase().includes(vibeSearchQuery.toLowerCase()) ||
                          (u.full_name && u.full_name.toLowerCase().includes(vibeSearchQuery.toLowerCase())) ||
                          u.organization_name.toLowerCase().includes(vibeSearchQuery.toLowerCase())
                        ).map(user => (
                          <tr key={user.username} className="hover:bg-slate-50/80 dark:hover:bg-slate-800/30 transition-colors">
                            <td className="py-3 px-3 font-semibold text-slate-900 dark:text-white">
                              {user.email || user.username}
                            </td>
                            <td className="py-3 px-3 text-slate-600 dark:text-slate-300">
                              {user.full_name || '—'}
                            </td>
                            <td className="py-3 px-3 text-slate-600 dark:text-slate-300">
                              {user.organization_name}
                            </td>
                            <td className="py-3 px-3 text-slate-600 dark:text-slate-300">
                              {user.project_count} projects
                            </td>
                            <td className="py-3 px-3 font-mono text-cyan-300">
                              {user.log_count}
                            </td>
                            <td className="py-3 px-3 font-mono text-slate-500 dark:text-slate-400">
                              {(user.prompt_tokens || 0).toLocaleString()}
                            </td>
                            <td className="py-3 px-3 font-mono text-slate-500 dark:text-slate-400">
                              {(user.completion_tokens || 0).toLocaleString()}
                            </td>
                            <td className="py-3 px-3 font-mono text-purple-300 font-semibold">
                              {(user.total_tokens || 0).toLocaleString()}
                            </td>
                            <td className="py-3 px-3 font-mono text-emerald-400 font-bold">
                              ${user.total_cost || 0}
                            </td>
                            <td className="py-3 px-3 text-right">
                              <button
                                onClick={() => setVibeSelectedUser(user)}
                                className="inline-flex items-center gap-1 px-2.5 py-1 rounded bg-purple-900/40 hover:bg-purple-800/60 border border-purple-500/30 text-xs font-semibold text-purple-200 transition-colors"
                              >
                                <Eye className="w-3 h-3" />
                                Inspect User
                              </button>
                            </td>
                          </tr>
                        ))
                      )}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </div>
        )}

      {/* Organization Detailed Inspection Modal */}
      {selectedOrgModal && (
        <div className="fixed inset-0 z-[9999] flex items-center justify-center p-4 bg-black/60 backdrop-blur-md">
          <div className="w-full max-w-4xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-purple-500/30 rounded-2xl p-6 shadow-2xl space-y-4 max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between border-b border-slate-200 dark:border-slate-800 pb-3">
              <div>
                <span className="text-[10px] uppercase tracking-wider font-bold text-purple-400">Organization Telemetry</span>
                <h3 className="text-xl font-bold text-slate-900 dark:text-white flex items-center gap-2">
                  <Building2 className="w-5 h-5 text-purple-400" />
                  {selectedOrgModal.organization_name}
                </h3>
              </div>
              <button
                onClick={() => setSelectedOrgModal(null)}
                className="p-1 rounded-lg bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 dark:hover:bg-slate-700 text-slate-500 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white cursor-pointer"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Summary Row */}
            <div className="grid grid-cols-4 gap-3 text-xs">
              <div className="p-3 bg-slate-50 dark:bg-slate-800/50 rounded-xl border border-slate-200 dark:border-slate-700/50">
                <span className="text-slate-500 dark:text-slate-400">Max Capacity Cap</span>
                <div className="text-lg font-bold text-purple-300">{selectedOrgModal.max_agent_capacity} Agents</div>
              </div>
              <div className="p-3 bg-slate-50 dark:bg-slate-800/50 rounded-xl border border-slate-200 dark:border-slate-700/50">
                <span className="text-slate-500 dark:text-slate-400">Onboarded Agents</span>
                <div className="text-lg font-bold text-emerald-400">{selectedOrgModal.total_onboarded_agents} Active</div>
              </div>
              <div className="p-3 bg-slate-50 dark:bg-slate-800/50 rounded-xl border border-slate-200 dark:border-slate-700/50">
                <span className="text-slate-500 dark:text-slate-400">Total AI Tokens</span>
                <div className="text-lg font-bold text-indigo-300">{(selectedOrgModal.total_tokens_consumed || 0).toLocaleString()}</div>
              </div>
              <div className="p-3 bg-slate-50 dark:bg-slate-800/50 rounded-xl border border-slate-200 dark:border-slate-700/50">
                <span className="text-slate-500 dark:text-slate-400">Total Usage Cost</span>
                <div className="text-lg font-bold text-emerald-400">${selectedOrgModal.total_cost || 0}</div>
              </div>
            </div>

            {/* User Breakdown Table */}
            <div>
              <h4 className="text-sm font-bold text-slate-900 dark:text-white mb-2 flex items-center gap-2">
                <Users className="w-4 h-4 text-purple-400" />
                Organization Users & Token Usage Breakdown
              </h4>
              <div className="overflow-x-auto rounded-xl border border-slate-200 dark:border-slate-800">
                <table className="w-full text-left text-xs">
                  <thead className="bg-slate-100 dark:bg-slate-800/80 text-slate-600 dark:text-slate-300 uppercase text-[10px] font-semibold">
                    <tr>
                      <th className="py-2.5 px-3">User Email</th>
                      <th className="py-2.5 px-3">Name</th>
                      <th className="py-2.5 px-3">Role</th>
                      <th className="py-2.5 px-3 text-right">AI Tokens</th>
                      <th className="py-2.5 px-3 text-right">Calculated Cost</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-200 dark:divide-slate-800 text-slate-700 dark:text-slate-200">
                    {(selectedOrgModal.users || []).map((u) => (
                      <tr key={u.id} className="hover:bg-slate-50 dark:hover:bg-slate-800/40">
                        <td className="py-2.5 px-3 font-semibold text-slate-900 dark:text-white">{u.email}</td>
                        <td className="py-2.5 px-3 text-slate-600 dark:text-slate-300">
                          {(u.first_name || u.last_name) ? `${u.first_name || ''} ${u.last_name || ''}`.trim() : '—'}
                        </td>
                        <td className="py-2.5 px-3">
                          <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                            u.is_super_admin
                              ? 'bg-purple-500/20 text-purple-300 border border-purple-500/30'
                              : u.is_org_admin
                              ? 'bg-blue-500/20 text-blue-300 border border-blue-500/30'
                              : 'bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400 border border-slate-200 dark:border-slate-700'
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
                className="px-4 py-2 bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 dark:hover:bg-slate-700 text-slate-700 dark:text-white font-bold rounded-xl text-xs cursor-pointer"
              >
                Close Inspection
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Project Breakdown Modal */}
      {selectedOrgProjModal && (
        <div className="fixed inset-0 z-[9999] flex items-center justify-center p-4 bg-black/60 backdrop-blur-md">
          <div className="w-full max-w-4xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-blue-500/30 rounded-2xl p-6 shadow-2xl space-y-4 max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between border-b border-slate-200 dark:border-slate-800 pb-3">
              <div>
                <span className="text-[10px] uppercase tracking-wider font-bold text-blue-400">Organization Telemetry</span>
                <h3 className="text-xl font-bold text-slate-900 dark:text-white flex items-center gap-2">
                  <Building2 className="w-5 h-5 text-blue-400" />
                  {selectedOrgProjModal.organization_name} — Project Usage Breakdown
                </h3>
              </div>
              <button
                onClick={() => setSelectedOrgProjModal(null)}
                className="p-1 rounded-lg bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 dark:hover:bg-slate-700 text-slate-500 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white cursor-pointer"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="grid grid-cols-3 gap-3 text-xs">
              <div className="p-3 bg-slate-50 dark:bg-slate-800/50 rounded-xl border border-slate-200 dark:border-slate-700/50">
                <span className="text-slate-500 dark:text-slate-400">Total Projects</span>
                <div className="text-lg font-bold text-slate-900 dark:text-white">{(selectedOrgProjModal.projects || []).length}</div>
              </div>
              <div className="p-3 bg-slate-50 dark:bg-slate-800/50 rounded-xl border border-slate-200 dark:border-slate-700/50">
                <span className="text-slate-500 dark:text-slate-400">Organization Tokens</span>
                <div className="text-lg font-bold text-blue-300">{(selectedOrgProjModal.total_tokens_consumed || 0).toLocaleString()}</div>
              </div>
              <div className="p-3 bg-slate-50 dark:bg-slate-800/50 rounded-xl border border-slate-200 dark:border-slate-700/50">
                <span className="text-slate-500 dark:text-slate-400">Organization Total Cost</span>
                <div className="text-lg font-bold text-emerald-400">${selectedOrgProjModal.total_cost || 0}</div>
              </div>
            </div>

            <div className="overflow-x-auto rounded-xl border border-slate-200 dark:border-slate-800">
              <table className="w-full text-left text-xs">
                <thead className="bg-slate-100 dark:bg-slate-800/80 text-slate-600 dark:text-slate-300 uppercase text-[10px] font-semibold">
                  <tr>
                    <th className="py-2.5 px-3">Project Name</th>
                    <th className="py-2.5 px-3">Project Token / ID</th>
                    <th className="py-2.5 px-3 text-right">AI Tokens</th>
                    <th className="py-2.5 px-3 text-right">Usage Cost</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-200 dark:divide-slate-800 text-slate-700 dark:text-slate-200">
                  {selectedOrgProjModal.projects && selectedOrgProjModal.projects.length > 0 ? (
                    selectedOrgProjModal.projects.map((proj) => {
                      const rawName = proj.project_name || 'Direct API / Custom Workspace';
                      const isJwt = rawName.startsWith('eyJ') || (proj.project_token && proj.project_token.startsWith('eyJ'));
                      const formattedName = isJwt && rawName.startsWith('eyJ') 
                        ? `Project (${rawName.substring(0, 12)}...${rawName.substring(rawName.length - 6)})` 
                        : rawName;
                      const formattedToken = proj.project_token 
                        ? (proj.project_token.startsWith('eyJ') 
                          ? `${proj.project_token.substring(0, 12)}...${proj.project_token.substring(proj.project_token.length - 6)}` 
                          : proj.project_token)
                        : '—';

                      return (
                        <tr key={proj.project_token} className="hover:bg-slate-50 dark:hover:bg-slate-800/40">
                          <td className="py-2.5 px-3 font-semibold text-slate-900 dark:text-white">{formattedName}</td>
                          <td className="py-2.5 px-3 font-mono text-slate-500 dark:text-slate-400 text-[11px]" title={proj.project_token}>
                            {formattedToken}
                          </td>
                          <td className="py-2.5 px-3 text-right font-mono text-blue-300 font-semibold">
                            {(proj.total_tokens || 0).toLocaleString()}
                          </td>
                          <td className="py-2.5 px-3 text-right font-mono text-emerald-400 font-bold">
                            ${(proj.total_cost || 0).toFixed(4)}
                          </td>
                        </tr>
                      );
                    })
                  ) : (
                    <tr>
                      <td colSpan={4} className="py-6 text-center text-slate-400 dark:text-slate-500 italic">
                        No active project tokens recorded (Direct API or idle)
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>

            <div className="flex justify-end pt-2">
              <button
                onClick={() => setSelectedOrgProjModal(null)}
                className="px-4 py-2 bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 dark:hover:bg-slate-700 text-slate-700 dark:text-white font-bold rounded-xl text-xs cursor-pointer"
              >
                Close Inspection
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Vibecoding Organization Inspection Modal */}
      {vibeSelectedOrg && (
        <div className="fixed inset-0 z-[9999] flex items-center justify-center p-4 bg-black/60 backdrop-blur-md">
          <div className="w-full max-w-4xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-cyan-500/30 rounded-2xl p-6 shadow-2xl space-y-4 max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between border-b border-slate-200 dark:border-slate-800 pb-3">
              <div>
                <span className="text-[10px] uppercase tracking-wider font-bold text-cyan-400">Vibecoding Organization Telemetry</span>
                <h3 className="text-xl font-bold text-slate-900 dark:text-white flex items-center gap-2">
                  <Building2 className="w-5 h-5 text-cyan-400" />
                  {vibeSelectedOrg.organization_name}
                </h3>
              </div>
              <button
                onClick={() => setVibeSelectedOrg(null)}
                className="p-1 rounded-lg bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 dark:hover:bg-slate-700 text-slate-500 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white cursor-pointer"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="grid grid-cols-4 gap-3 text-xs">
              <div className="p-3 bg-slate-50 dark:bg-slate-800/50 rounded-xl border border-slate-200 dark:border-slate-700/50">
                <span className="text-slate-500 dark:text-slate-400">Total Users</span>
                <div className="text-lg font-bold text-cyan-300">{vibeSelectedOrg.user_count} Users</div>
              </div>
              <div className="p-3 bg-slate-50 dark:bg-slate-800/50 rounded-xl border border-slate-200 dark:border-slate-700/50">
                <span className="text-slate-500 dark:text-slate-400">Total Projects</span>
                <div className="text-lg font-bold text-purple-300">{vibeSelectedOrg.project_count} Projects</div>
              </div>
              <div className="p-3 bg-slate-50 dark:bg-slate-800/50 rounded-xl border border-slate-200 dark:border-slate-700/50">
                <span className="text-slate-500 dark:text-slate-400">Total AI Tokens</span>
                <div className="text-lg font-bold text-indigo-300">{(vibeSelectedOrg.total_tokens || 0).toLocaleString()}</div>
              </div>
              <div className="p-3 bg-slate-50 dark:bg-slate-800/50 rounded-xl border border-slate-200 dark:border-slate-700/50">
                <span className="text-slate-500 dark:text-slate-400">Total Usage Cost</span>
                <div className="text-lg font-bold text-emerald-400">${vibeSelectedOrg.total_cost || 0}</div>
              </div>
            </div>

            {/* Users in Org */}
            <div>
              <h4 className="text-sm font-bold text-slate-900 dark:text-white mb-2 flex items-center gap-2">
                <Users className="w-4 h-4 text-cyan-400" />
                Users in Organization
              </h4>
              <div className="flex flex-wrap gap-2">
                {(vibeSelectedOrg.users || []).map(u => (
                  <span key={u} className="px-2.5 py-1 rounded-lg bg-slate-100 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 text-xs font-mono text-cyan-700 dark:text-cyan-200">
                    {u}
                  </span>
                ))}
              </div>
            </div>

            {/* Projects in Org */}
            <div>
              <h4 className="text-sm font-bold text-slate-900 dark:text-white mb-2 flex items-center gap-2">
                <FolderKanban className="w-4 h-4 text-purple-400" />
                Projects in Organization
              </h4>
              <div className="flex flex-wrap gap-2">
                {(vibeSelectedOrg.projects || []).map(p => (
                  <span key={p} className="px-2.5 py-1 rounded-lg bg-slate-100 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 text-xs font-mono text-purple-700 dark:text-purple-200">
                    {p}
                  </span>
                ))}
              </div>
            </div>

            <div className="flex justify-end pt-2">
              <button
                onClick={() => setVibeSelectedOrg(null)}
                className="px-4 py-2 bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 dark:hover:bg-slate-700 text-slate-700 dark:text-white font-bold rounded-xl text-xs cursor-pointer"
              >
                Close Inspection
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Vibecoding User Inspection Modal */}
      {vibeSelectedUser && (
        <div className="fixed inset-0 z-[9999] flex items-center justify-center p-4 bg-black/60 backdrop-blur-md">
          <div className="w-full max-w-4xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-purple-500/30 rounded-2xl p-6 shadow-2xl space-y-4 max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between border-b border-slate-200 dark:border-slate-800 pb-3">
              <div>
                <span className="text-[10px] uppercase tracking-wider font-bold text-purple-400">Vibecoding User Telemetry</span>
                <h3 className="text-xl font-bold text-slate-900 dark:text-white flex items-center gap-2">
                  <Users className="w-5 h-5 text-purple-400" />
                  {vibeSelectedUser.email || vibeSelectedUser.username}
                </h3>
              </div>
              <button
                onClick={() => setVibeSelectedUser(null)}
                className="p-1 rounded-lg bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 dark:hover:bg-slate-700 text-slate-500 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white cursor-pointer"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="grid grid-cols-4 gap-3 text-xs">
              <div className="p-3 bg-slate-50 dark:bg-slate-800/50 rounded-xl border border-slate-200 dark:border-slate-700/50">
                <span className="text-slate-500 dark:text-slate-400">Full Name</span>
                <div className="text-base font-bold text-slate-900 dark:text-white">{vibeSelectedUser.full_name || '—'}</div>
              </div>
              <div className="p-3 bg-slate-50 dark:bg-slate-800/50 rounded-xl border border-slate-200 dark:border-slate-700/50">
                <span className="text-slate-500 dark:text-slate-400">Organization</span>
                <div className="text-base font-bold text-cyan-300">{vibeSelectedUser.organization_name}</div>
              </div>
              <div className="p-3 bg-slate-50 dark:bg-slate-800/50 rounded-xl border border-slate-200 dark:border-slate-700/50">
                <span className="text-slate-500 dark:text-slate-400">Total Tokens</span>
                <div className="text-base font-bold text-indigo-300">{(vibeSelectedUser.total_tokens || 0).toLocaleString()}</div>
              </div>
              <div className="p-3 bg-slate-50 dark:bg-slate-800/50 rounded-xl border border-slate-200 dark:border-slate-700/50">
                <span className="text-slate-500 dark:text-slate-400">Total Usage Cost</span>
                <div className="text-base font-bold text-emerald-400">${vibeSelectedUser.total_cost || 0}</div>
              </div>
            </div>

            <div>
              <h4 className="text-sm font-bold text-slate-900 dark:text-white mb-2 flex items-center gap-2">
                <FolderKanban className="w-4 h-4 text-purple-400" />
                User Projects ({vibeSelectedUser.project_count})
              </h4>
              <div className="flex flex-wrap gap-2">
                {(vibeSelectedUser.projects || []).map(p => {
                  const isJwt = p && p.startsWith('eyJ');
                  const displayStr = isJwt ? `Project (${p.substring(0, 10)}...${p.substring(p.length - 5)})` : p;
                  return (
                    <span key={p} className="px-2.5 py-1 rounded-lg bg-slate-100 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 text-xs font-mono text-purple-700 dark:text-purple-200" title={p}>
                      {displayStr}
                    </span>
                  );
                })}
              </div>
            </div>

            <div className="flex justify-end pt-2">
              <button
                onClick={() => setVibeSelectedUser(null)}
                className="px-4 py-2 bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 dark:hover:bg-slate-700 text-slate-700 dark:text-white font-bold rounded-xl text-xs cursor-pointer"
              >
                Close Inspection
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  </div>
);
}
