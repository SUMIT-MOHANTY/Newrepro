import React, { useState, useEffect, useMemo } from 'react';
import { 
  DollarSign, Cpu, Building2, Users, RefreshCw, AlertCircle, 
  Search, Shield, Eye, X, Layers, CreditCard, ChevronLeft, ChevronRight, Activity, ArrowUpRight,
  FileText, FileSpreadsheet, Calendar
} from 'lucide-react';
import { generateSuperAdminPDF } from './superAdminPdfGenerator';
import { API_ENDPOINTS } from '../config';

export default function SuperAdminGlobalBilling() {
  const [stats, setStats] = useState(null);
  const [orgs, setOrgs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedOrg, setSelectedOrg] = useState(null);
  const [selectedOrgProj, setSelectedOrgProj] = useState(null);
  const [selectedOrgTags, setSelectedOrgTags] = useState([]);
  const [selectedProjTags, setSelectedProjTags] = useState([]);
  const [expandedTags, setExpandedTags] = useState({});
  const [orgTagDropdownOpen, setOrgTagDropdownOpen] = useState(false);
  const [projTagDropdownOpen, setProjTagDropdownOpen] = useState(false);

  // Date Filters
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');

  const allOrgTags = useMemo(() => {
    const setTags = new Set();
    orgs.forEach(o => {
      if (o.organization_tags) {
        o.organization_tags.forEach(t => setTags.add(t));
      }
    });
    return Array.from(setTags).sort();
  }, [orgs]);

  const allProjectTags = useMemo(() => {
    if (!selectedOrgProj || !selectedOrgProj.projects) return [];
    const setTags = new Set();
    selectedOrgProj.projects.forEach(p => {
      if (p.tags) {
        p.tags.forEach(t => setTags.add(t));
      }
    });
    return Array.from(setTags).sort();
  }, [selectedOrgProj]);

  const filteredProjects = useMemo(() => {
    if (!selectedOrgProj || !selectedOrgProj.projects) return [];
    if (selectedProjTags.length === 0) return selectedOrgProj.projects;
    return selectedOrgProj.projects.filter(p => p.tags && selectedProjTags.some(t => p.tags.includes(t)));
  }, [selectedOrgProj, selectedProjTags]);

  const [currentPage, setCurrentPage] = useState(1);
  const itemsPerPage = 8;

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
      if (!statsRes.ok) throw new Error('Failed to fetch global billing telemetry');
      const statsData = await statsRes.json();
      setStats(statsData);

      const orgsRes = await fetch(orgsUrl, { headers });
      if (orgsRes.ok) {
        const orgsData = await orgsRes.json();
        setOrgs(orgsData);
      }
    } catch (err) {
      setError(err.message || 'Error loading global platform billing data');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, [startDate, endDate]);

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
      rows.push(['GLOBAL PLATFORM BILLING & TOKEN CONSUMPTION REPORT']);
      rows.push(['Generated At:', new Date().toLocaleString()]);
      if (startDate || endDate) {
        rows.push(['Filter Date Range:', `${startDate || 'Start'} to ${endDate || 'Present'}`]);
      }
      rows.push([]);

      rows.push(['EXECUTIVE FINANCIAL SUMMARY']);
      rows.push(['Total Platform Cost (USD)', stats?.platform_billing || 0]);
      rows.push(['Total AI Tokens Consumed', stats?.ai_tokens_consumed || 0]);
      rows.push(['Active Organizations', orgs.length]);
      rows.push(['Active Platform Users', stats?.active_users || 0]);
      rows.push([]);

      rows.push(['ORGANIZATION FINANCIAL BREAKDOWN']);
      rows.push([
        'Organization Name',
        'Total Members',
        'Max Agent Capacity',
        'Onboarded Agents',
        'Organization Tags',
        'AI Tokens Consumed',
        'Total Usage Cost (USD)'
      ]);

      orgs.forEach(o => {
        rows.push([
          o.organization_name,
          o.user_count,
          o.max_agent_capacity,
          o.total_onboarded_agents,
          o.organization_tags ? o.organization_tags.join('; ') : '',
          o.total_tokens_consumed || 0,
          o.total_cost || 0
        ]);
      });

      rows.push([]);
      rows.push(['PROJECT BREAKDOWN WITH TAGS']);
      rows.push([
        'Organization Name',
        'Project Name',
        'Project Tags',
        'AI Tokens',
        'Usage Cost (USD)'
      ]);

      orgs.forEach(o => {
        (o.projects || []).forEach(p => {
          rows.push([
            o.organization_name,
            p.project_name || 'Direct API / Custom Workspace',
            p.tags && p.tags.length > 0 ? p.tags.join('; ') : '',
            p.total_tokens || 0,
            p.total_cost || 0
          ]);
        });
      });

      const csvContent = rows
        .map(row => row.map(cell => escapeCSV(cell)).join(','))
        .join('\n');

      const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      const fileName = `Global_Platform_Billing_Report_${new Date().toISOString().split('T')[0]}.csv`;

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
    const range = (startDate || endDate) ? `${startDate || 'Start'} to ${endDate || 'Present'}` : 'All-Time';
    generateSuperAdminPDF(
      orgs, 
      stats, 
      "Global Platform Billing & Financial Report", 
      "Executive overview of organization spends, token usage, and user activity logs",
      `Global_Platform_Billing_Report_${new Date().toISOString().split('T')[0]}.pdf`,
      range
    );
  };

  const filteredOrgs = orgs.filter(o => {
    const matchesSearch = o.organization_name.toLowerCase().includes(searchQuery.toLowerCase());
    if (selectedOrgTags.length === 0) return matchesSearch;
    return matchesSearch && o.organization_tags && selectedOrgTags.some(t => o.organization_tags.includes(t));
  });

  const totalPages = Math.ceil(filteredOrgs.length / itemsPerPage) || 1;
  const paginatedOrgs = filteredOrgs.slice((currentPage - 1) * itemsPerPage, currentPage * itemsPerPage);

  const totalPlatformCost = orgs.reduce((acc, o) => acc + (o.total_cost || 0), 0);
  const totalTokensConsumed = orgs.reduce((acc, o) => acc + (o.total_tokens_consumed || 0), 0);
  const totalUsersAcrossOrgs = orgs.reduce((acc, o) => acc + (o.user_count || 0), 0);

  if (loading) {
    return (
      <div className="h-full flex items-center justify-center bg-app-bg-page text-app-text-muted">
        <div className="flex items-center gap-3">
          <RefreshCw className="w-5 h-5 animate-spin text-purple-400" />
          <span className="text-sm font-medium">Loading Global Platform Billing Dashboard...</span>
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
                Platform Control Center
              </span>
              <span className="text-xs text-slate-400">• Multi-Tenant Platform Billing</span>
            </div>
            <h1 className="text-xl sm:text-2xl font-extrabold text-white mt-1 flex items-center gap-2">
              <CreditCard className="w-6 h-6 text-purple-400" />
              Global Platform Billing Dashboard
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
            <span>Filter Billing Data by Date Range:</span>
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

        {/* Global Financial KPI Cards */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
          <div className="p-4 rounded-xl bg-slate-900/70 border border-purple-500/20 backdrop-blur">
            <div className="flex items-center justify-between text-slate-400 text-xs mb-1">
              <span className="font-semibold uppercase tracking-wider text-[10px]">Total Platform Cost</span>
              <DollarSign className="w-4 h-4 text-emerald-400" />
            </div>
            <div className="text-2xl font-black text-emerald-400">${(stats?.platform_billing || totalPlatformCost).toFixed(2)}</div>
            <div className="text-[10px] text-slate-400 mt-1">Token inference + compute across all orgs</div>
          </div>

          <div className="p-4 rounded-xl bg-slate-900/70 border border-purple-500/20 backdrop-blur">
            <div className="flex items-center justify-between text-slate-400 text-xs mb-1">
              <span className="font-semibold uppercase tracking-wider text-[10px]">Total AI Tokens</span>
              <Cpu className="w-4 h-4 text-purple-400" />
            </div>
            <div className="text-2xl font-black text-purple-300">{(stats?.ai_tokens_consumed || totalTokensConsumed).toLocaleString()}</div>
            <div className="text-[10px] text-purple-400 mt-1">Prompt + completion tokens</div>
          </div>

          <div className="p-4 rounded-xl bg-slate-900/70 border border-purple-500/20 backdrop-blur">
            <div className="flex items-center justify-between text-slate-400 text-xs mb-1">
              <span className="font-semibold uppercase tracking-wider text-[10px]">Active Organizations</span>
              <Building2 className="w-4 h-4 text-cyan-400" />
            </div>
            <div className="text-2xl font-black text-white">{orgs.length}</div>
            <div className="text-[10px] text-cyan-400 mt-1">Registered tenant accounts</div>
          </div>

          <div className="p-4 rounded-xl bg-slate-900/70 border border-purple-500/20 backdrop-blur">
            <div className="flex items-center justify-between text-slate-400 text-xs mb-1">
              <span className="font-semibold uppercase tracking-wider text-[10px]">Total Active Users</span>
              <Users className="w-4 h-4 text-sky-400" />
            </div>
            <div className="text-2xl font-black text-white">{stats?.active_users || totalUsersAcrossOrgs}</div>
            <div className="text-[10px] text-sky-400 mt-1">Consuming platform capacity</div>
          </div>
        </div>

        {/* Organization Financial Telemetry Table */}
        <div className="p-5 rounded-2xl bg-slate-900/80 border border-purple-500/20 space-y-4">
          {/* Toolbar: Search + Tag Filter inline */}
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <div>
              <h2 className="text-base font-bold text-white flex items-center gap-2">
                <Building2 className="w-4 h-4 text-purple-400" />
                Cross-Organization Billing Breakdown
              </h2>
              <p className="text-xs text-slate-400">
                View real-time token consumption, compute costs, and member counts for every organization.
              </p>
            </div>
            <div className="flex items-center gap-2 flex-shrink-0">
              {/* Search */}
              <div className="relative">
                <Search className="w-3.5 h-3.5 absolute left-3 top-2.5 text-slate-400" />
                <input
                  type="text"
                  placeholder="Search organizations..."
                  value={searchQuery}
                  onChange={e => { setSearchQuery(e.target.value); setCurrentPage(1); }}
                  className="pl-8 pr-3 py-1.5 bg-slate-800/60 border border-slate-700 rounded-lg text-xs text-white placeholder-slate-400 focus:outline-none focus:border-purple-500 w-48"
                />
              </div>

              {/* Org Tag Filter Dropdown */}
              {allOrgTags.length > 0 && (
                <div className="relative">
                  <button
                    onClick={() => setOrgTagDropdownOpen(o => !o)}
                    className="flex items-center gap-2 px-3 py-1.5 bg-slate-800/70 hover:bg-slate-700/80 border border-slate-700 hover:border-purple-500/50 rounded-lg text-xs font-semibold text-slate-300 transition-all whitespace-nowrap"
                  >
                    <svg className="w-3.5 h-3.5 text-purple-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 4a1 1 0 011-1h16a1 1 0 011 1v2a1 1 0 01-.293.707L13 13.414V19a1 1 0 01-.553.894l-4 2A1 1 0 017 21v-7.586L3.293 6.707A1 1 0 013 6V4z" /></svg>
                    Filter by Tag
                    {selectedOrgTags.length > 0 && (
                      <span className="px-1.5 py-0.5 rounded-full bg-purple-500 text-white text-[9px] font-bold leading-none">
                        {selectedOrgTags.length}
                      </span>
                    )}
                    <svg className={`w-3 h-3 text-slate-400 transition-transform ${orgTagDropdownOpen ? 'rotate-180' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" /></svg>
                  </button>

                  {orgTagDropdownOpen && (
                    <div className="absolute right-0 top-full mt-1.5 z-50 w-60 bg-slate-900 border border-purple-500/30 rounded-xl shadow-2xl shadow-black/50 overflow-hidden">
                      <div className="px-3 py-2 border-b border-slate-800 flex items-center justify-between">
                        <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Organization Tags</span>
                        {selectedOrgTags.length > 0 && (
                          <button
                            onClick={() => { setSelectedOrgTags([]); setCurrentPage(1); }}
                            className="text-[10px] text-purple-400 hover:text-purple-300 font-semibold transition-colors"
                          >
                            Clear all
                          </button>
                        )}
                      </div>
                      <div className="max-h-52 overflow-y-auto py-1">
                        {allOrgTags.map(tag => {
                          const isSelected = selectedOrgTags.includes(tag);
                          const count = orgs.filter(o => o.organization_tags && o.organization_tags.includes(tag)).length;
                          return (
                            <button
                              key={tag}
                              onClick={() => {
                                setSelectedOrgTags(prev => prev.includes(tag) ? prev.filter(t => t !== tag) : [...prev, tag]);
                                setCurrentPage(1);
                              }}
                              className="w-full flex items-center justify-between px-3 py-2 text-xs hover:bg-slate-800/80 transition-colors group"
                            >
                              <span className="flex items-center gap-2">
                                <span className={`w-4 h-4 rounded border flex items-center justify-center flex-shrink-0 transition-all ${
                                  isSelected ? 'bg-purple-500 border-purple-500' : 'border-slate-600 group-hover:border-slate-400'
                                }`}>
                                  {isSelected && (
                                    <svg className="w-2.5 h-2.5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" /></svg>
                                  )}
                                </span>
                                <span className={isSelected ? 'text-purple-200 font-semibold' : 'text-slate-300'}>{tag}</span>
                              </span>
                              <span className="text-[10px] text-slate-500">{count} org{count !== 1 ? 's' : ''}</span>
                            </button>
                          );
                        })}
                      </div>
                      {selectedOrgTags.length > 0 && (
                        <div className="px-3 py-2 border-t border-slate-800">
                          <div className="flex flex-wrap gap-1">
                            {selectedOrgTags.map(t => (
                              <span key={t} className="flex items-center gap-1 px-1.5 py-0.5 rounded bg-purple-500/20 text-purple-300 border border-purple-500/30 text-[9px] font-semibold">
                                {t}
                                <button onClick={() => setSelectedOrgTags(prev => prev.filter(x => x !== t))} className="hover:text-white">
                                  <X className="w-2.5 h-2.5" />
                                </button>
                              </span>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-slate-800/40 text-slate-400 font-semibold uppercase text-[10px] tracking-wider border-b border-slate-800">
                <tr>
                  <th className="py-3 px-3">Organization</th>
                  <th className="py-3 px-3">Members</th>
                  <th className="py-3 px-3">Max Capacity</th>
                  <th className="py-3 px-3">Onboarded Agents</th>
                  <th className="py-3 px-3">Tags</th>
                  <th className="py-3 px-3">AI Tokens Consumed</th>
                  <th className="py-3 px-3">Total Usage Cost</th>
                  <th className="py-3 px-3 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60 text-slate-200">
                {paginatedOrgs.length === 0 ? (
                  <tr>
                    <td colSpan={8} className="py-6 text-center text-slate-400 italic">
                      No organization billing data found.
                    </td>
                  </tr>
                ) : (
                  paginatedOrgs.map((org) => (
                    <tr key={org.organization_name} className="hover:bg-slate-800/30 transition-colors">
                      <td className="py-3.5 px-3 font-bold text-white flex items-center gap-2">
                        <Building2 className="w-4 h-4 text-purple-400 shrink-0" />
                        {org.organization_name}
                      </td>
                      <td className="py-3.5 px-3 text-slate-300 font-medium">
                        {org.user_count} members
                      </td>
                      <td className="py-3.5 px-3">
                        <span className="px-2 py-0.5 rounded text-[11px] font-bold bg-purple-500/10 text-purple-300 border border-purple-500/20">
                          {org.max_agent_capacity} Agents
                        </span>
                      </td>
                      <td className="py-3.5 px-3 text-slate-300 font-medium">
                        {org.total_onboarded_agents}
                      </td>
                      <td className="py-3.5 px-3">
                        <div className="flex flex-wrap gap-1 max-w-[150px]">
                          {org.organization_tags && org.organization_tags.length > 0 ? (
                            <>
                              {org.organization_tags.slice(0, expandedTags[org.organization_name] ? undefined : 2).map(t => (
                                <span key={t} className="px-1.5 py-0.5 rounded bg-indigo-500/10 text-indigo-300 border border-indigo-500/20 text-[9px] font-semibold">
                                  {t}
                                </span>
                              ))}
                              {org.organization_tags.length > 2 && (
                                <button
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    setExpandedTags(prev => ({ ...prev, [org.organization_name]: !prev[org.organization_name] }));
                                  }}
                                  className="px-1.5 py-0.5 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700 text-[9px] font-semibold transition-all hover:scale-105"
                                >
                                  {expandedTags[org.organization_name] ? 'show less' : `+${org.organization_tags.length - 2} more`}
                                </button>
                              )}
                            </>
                          ) : (
                            <span className="text-slate-500 italic text-[10px]">No tags</span>
                          )}
                        </div>
                      </td>
                      <td className="py-3.5 px-3 font-mono font-semibold text-indigo-300">
                        {(org.total_tokens_consumed || 0).toLocaleString()}
                      </td>
                      <td className="py-3.5 px-3 font-mono font-bold text-emerald-400">
                        ${org.total_cost || 0}
                      </td>
                      <td className="py-3.5 px-3 text-right">
                        <div className="flex items-center justify-end gap-2">
                          <button
                            onClick={() => setSelectedOrg(org)}
                            className="inline-flex items-center gap-1.5 px-3 py-1 rounded-lg bg-purple-900/40 hover:bg-purple-800/60 border border-purple-500/30 text-xs font-semibold text-purple-200 transition-colors"
                          >
                            <Eye className="w-3.5 h-3.5" />
                            View User Breakdown
                          </button>
                          <button
                            onClick={() => setSelectedOrgProj(org)}
                            className="inline-flex items-center gap-1.5 px-3 py-1 rounded-lg bg-blue-900/40 hover:bg-blue-800/60 border border-blue-500/30 text-xs font-semibold text-blue-200 transition-colors"
                          >
                            <Layers className="w-3.5 h-3.5" />
                            View Project Breakdown
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

      {/* User Breakdown Modal */}
      {selectedOrg && (
        <div className="fixed inset-0 z-[9999] flex items-center justify-center p-4 bg-black/80 backdrop-blur-md">
          <div className="w-full max-w-4xl bg-slate-900 border border-purple-500/30 rounded-2xl p-6 shadow-2xl space-y-4 max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <div>
                <span className="text-[10px] uppercase tracking-wider font-bold text-purple-400">Super Admin Financial Drilldown</span>
                <h3 className="text-xl font-bold text-white flex items-center gap-2">
                  <Building2 className="w-5 h-5 text-purple-400" />
                  {selectedOrg.organization_name} — Member Usage Breakdown
                </h3>
              </div>
              <button
                onClick={() => setSelectedOrg(null)}
                className="p-1 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-400 hover:text-white"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="grid grid-cols-3 gap-3 text-xs">
              <div className="p-3 bg-slate-800/50 rounded-xl border border-slate-700/50">
                <span className="text-slate-400">Total Members</span>
                <div className="text-lg font-bold text-white">{selectedOrg.user_count}</div>
              </div>
              <div className="p-3 bg-slate-800/50 rounded-xl border border-slate-700/50">
                <span className="text-slate-400">Organization Tokens</span>
                <div className="text-lg font-bold text-purple-300">{(selectedOrg.total_tokens_consumed || 0).toLocaleString()}</div>
              </div>
              <div className="p-3 bg-slate-800/50 rounded-xl border border-slate-700/50">
                <span className="text-slate-400">Organization Total Cost</span>
                <div className="text-lg font-bold text-emerald-400">${selectedOrg.total_cost || 0}</div>
              </div>
            </div>

            <div className="overflow-x-auto rounded-xl border border-slate-800">
              <table className="w-full text-left text-xs">
                <thead className="bg-slate-800/80 text-slate-300 uppercase text-[10px] font-semibold">
                  <tr>
                    <th className="py-2.5 px-3">User Email</th>
                    <th className="py-2.5 px-3">Name</th>
                    <th className="py-2.5 px-3">Role</th>
                    <th className="py-2.5 px-3 text-right">AI Tokens</th>
                    <th className="py-2.5 px-3 text-right">Usage Cost</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800 text-slate-200">
                  {(selectedOrg.users || []).map((u) => (
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

            <div className="flex justify-end pt-2">
              <button
                onClick={() => setSelectedOrg(null)}
                className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-white font-bold rounded-xl text-xs"
              >
                Close Drilldown
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Project Breakdown Modal */}
      {selectedOrgProj && (
        <div className="fixed inset-0 z-[9999] flex items-center justify-center p-4 bg-black/80 backdrop-blur-md">
          <div className="w-full max-w-4xl bg-slate-900 border border-blue-500/30 rounded-2xl p-6 shadow-2xl space-y-4 max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <div>
                <span className="text-[10px] uppercase tracking-wider font-bold text-blue-400">Super Admin Financial Drilldown</span>
                <h3 className="text-xl font-bold text-white flex items-center gap-2">
                  <Building2 className="w-5 h-5 text-blue-400" />
                  {selectedOrgProj.organization_name} — Project Usage Breakdown
                </h3>
              </div>
              <button
                onClick={() => { setSelectedOrgProj(null); setSelectedProjTags([]); setExpandedTags({}); }}
                className="p-1 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-400 hover:text-white"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="grid grid-cols-3 gap-3 text-xs">
              <div className="p-3 bg-slate-800/50 rounded-xl border border-slate-700/50">
                <span className="text-slate-400">Total Projects</span>
                <div className="text-lg font-bold text-white">{(selectedOrgProj.projects || []).length}</div>
              </div>
              <div className="p-3 bg-slate-800/50 rounded-xl border border-slate-700/50">
                <span className="text-slate-400">Organization Tokens</span>
                <div className="text-lg font-bold text-blue-300">{(selectedOrgProj.total_tokens_consumed || 0).toLocaleString()}</div>
              </div>
              <div className="p-3 bg-slate-800/50 rounded-xl border border-slate-700/50">
                <span className="text-slate-400">Organization Total Cost</span>
                <div className="text-lg font-bold text-emerald-400">${selectedOrgProj.total_cost || 0}</div>
              </div>
            </div>

            {/* Project Tag Filter — Multi-Select Dropdown */}
            {allProjectTags.length > 0 && (
              <div className="relative">
                <button
                  onClick={() => setProjTagDropdownOpen(o => !o)}
                  className="flex items-center gap-2 px-3 py-1.5 bg-slate-800/70 hover:bg-slate-700/80 border border-slate-700 hover:border-blue-500/50 rounded-lg text-xs font-semibold text-slate-300 transition-all"
                >
                  <svg className="w-3.5 h-3.5 text-blue-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 4a1 1 0 011-1h16a1 1 0 011 1v2a1 1 0 01-.293.707L13 13.414V19a1 1 0 01-.553.894l-4 2A1 1 0 017 21v-7.586L3.293 6.707A1 1 0 013 6V4z" /></svg>
                  Filter by Tag
                  {selectedProjTags.length > 0 && (
                    <span className="ml-1 px-1.5 py-0.5 rounded-full bg-blue-500 text-white text-[9px] font-bold leading-none">
                      {selectedProjTags.length}
                    </span>
                  )}
                  <svg className={`w-3 h-3 text-slate-400 transition-transform ${projTagDropdownOpen ? 'rotate-180' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" /></svg>
                </button>

                {projTagDropdownOpen && (
                  <div className="absolute left-0 top-full mt-1.5 z-50 w-56 bg-slate-900 border border-blue-500/30 rounded-xl shadow-2xl shadow-black/40 overflow-hidden">
                    <div className="px-3 py-2 border-b border-slate-800 flex items-center justify-between">
                      <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Project Tags</span>
                      {selectedProjTags.length > 0 && (
                        <button
                          onClick={() => setSelectedProjTags([])}
                          className="text-[10px] text-blue-400 hover:text-blue-300 font-semibold transition-colors"
                        >
                          Clear all
                        </button>
                      )}
                    </div>
                    <div className="max-h-52 overflow-y-auto py-1">
                      {allProjectTags.map(tag => {
                        const isSelected = selectedProjTags.includes(tag);
                        const count = selectedOrgProj.projects.filter(p => p.tags && p.tags.includes(tag)).length;
                        return (
                          <button
                            key={tag}
                            onClick={() => setSelectedProjTags(prev => prev.includes(tag) ? prev.filter(t => t !== tag) : [...prev, tag])}
                            className="w-full flex items-center justify-between px-3 py-2 text-xs hover:bg-slate-800/80 transition-colors group"
                          >
                            <span className="flex items-center gap-2">
                              <span className={`w-4 h-4 rounded border flex items-center justify-center flex-shrink-0 transition-all ${
                                isSelected ? 'bg-blue-500 border-blue-500' : 'border-slate-600 group-hover:border-slate-400'
                              }`}>
                                {isSelected && (
                                  <svg className="w-2.5 h-2.5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" /></svg>
                                )}
                              </span>
                              <span className={isSelected ? 'text-blue-200 font-semibold' : 'text-slate-300'}>{tag}</span>
                            </span>
                            <span className="text-[10px] text-slate-500">{count} project{count !== 1 ? 's' : ''}</span>
                          </button>
                        );
                      })}
                    </div>
                    {selectedProjTags.length > 0 && (
                      <div className="px-3 py-2 border-t border-slate-800">
                        <div className="flex flex-wrap gap-1">
                          {selectedProjTags.map(t => (
                            <span key={t} className="flex items-center gap-1 px-1.5 py-0.5 rounded bg-blue-500/20 text-blue-300 border border-blue-500/30 text-[9px] font-semibold">
                              {t}
                              <button onClick={() => setSelectedProjTags(prev => prev.filter(x => x !== t))} className="hover:text-white">
                                <X className="w-2.5 h-2.5" />
                              </button>
                            </span>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                )}
              </div>
            )}

            <div className="overflow-x-auto rounded-xl border border-slate-800">
              <table className="w-full text-left text-xs">
                <thead className="bg-slate-800/80 text-slate-300 uppercase text-[10px] font-semibold">
                  <tr>
                    <th className="py-2.5 px-3">Project Name</th>
                    <th className="py-2.5 px-3">Tags</th>
                    <th className="py-2.5 px-3 text-right">AI Tokens</th>
                    <th className="py-2.5 px-3 text-right">Usage Cost</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800 text-slate-200">
                  {filteredProjects.length > 0 ? (
                    filteredProjects.map((proj) => (
                      <tr key={proj.project_token} className="hover:bg-slate-800/40">
                        <td className="py-2.5 px-3 font-semibold text-white">{proj.project_name || 'Direct API / Custom Workspace'}</td>
                        <td className="py-2.5 px-3">
                          <div className="flex flex-wrap gap-1 max-w-[180px]">
                            {proj.tags && proj.tags.length > 0 ? (
                              <>
                                {proj.tags.slice(0, expandedTags[proj.project_token] ? undefined : 2).map(t => (
                                  <span key={t} className="px-1.5 py-0.5 rounded bg-indigo-500/10 text-indigo-300 border border-indigo-500/20 text-[9px] font-semibold">
                                    {t}
                                  </span>
                                ))}
                                {proj.tags.length > 2 && (
                                  <button
                                    onClick={(e) => {
                                      e.stopPropagation();
                                      setExpandedTags(prev => ({ ...prev, [proj.project_token]: !prev[proj.project_token] }));
                                    }}
                                    className="px-1.5 py-0.5 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700 text-[9px] font-semibold transition-all hover:scale-105"
                                  >
                                    {expandedTags[proj.project_token] ? 'show less' : `+${proj.tags.length - 2} more`}
                                  </button>
                                )}
                              </>
                            ) : (
                              <span className="text-slate-500 italic text-[10px]">—</span>
                            )}
                          </div>
                        </td>
                        <td className="py-2.5 px-3 text-right font-mono text-blue-300 font-semibold">
                          {(proj.total_tokens || 0).toLocaleString()}
                        </td>
                        <td className="py-2.5 px-3 text-right font-mono text-emerald-400 font-bold">
                          ${(proj.total_cost || 0).toFixed(4)}
                        </td>
                      </tr>
                    ))
                  ) : (
                    <tr>
                      <td colSpan={4} className="py-6 text-center text-slate-400 italic">
                        No projects found matching the selected tag.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>

            <div className="flex justify-end pt-2">
              <button
                onClick={() => { setSelectedOrgProj(null); setSelectedProjTags([]); setExpandedTags({}); }}
                className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-white font-bold rounded-xl text-xs"
              >
                Close Drilldown
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
