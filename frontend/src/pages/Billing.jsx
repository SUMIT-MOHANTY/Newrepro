import React, { useState, useEffect, useMemo } from 'react';
import { 
    CreditCard, CheckCircle2, Sparkles, Bot, Clock, 
    DollarSign, Search, Filter, Cpu, RefreshCw, AlertCircle, Zap, 
    User, Activity, ShieldCheck, Globe, Users, FileText, ArrowUpDown,
    CheckCircle, XCircle, ExternalLink, FileSpreadsheet, Coins
} from 'lucide-react';
import { API_BASE_URL } from '../config';
import { getCachedTaskToken } from '../utils/tokenCache';
import { jsPDF } from 'jspdf';
import OrgTokenOpsPanel from '../components/OrgTokenOpsPanel';

export default function Billing({ selectedProjectKey, projects = [], user }) {
    const [billingData, setBillingData] = useState(null);
    const [orgBillingData, setOrgBillingData] = useState(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    
    // UI state
    const [activeTab, setActiveTab] = useState('overview'); // overview, users, projects
    const [searchTerm, setSearchTerm] = useState('');
    const [agentFilter, setAgentFilter] = useState('all');
    const [refreshing, setRefreshing] = useState(false);
    
    // Date Range filters
    const [startDate, setStartDate] = useState('');
    const [endDate, setEndDate] = useState('');
    
    // Sort states for user table
    const [userSortField, setUserSortField] = useState('name');
    const [userSortAsc, setUserSortAsc] = useState(true);

    // Selected user for drilldown modal
    const [selectedUserDetail, setSelectedUserDetail] = useState(null);

    const activeProject = projects.find(p => p.key === selectedProjectKey);
    const isOrgAdmin = user?.is_org_admin;

    const fetchBillingData = async (isRefresh = false) => {
        if (isRefresh) {
            setRefreshing(true);
        } else {
            setLoading(true);
        }
        setError(null);

        try {
            const token = localStorage.getItem('token');
            const headers = {
                'Authorization': `Bearer ${token}`,
                'Content-Type': 'application/json'
            };

            if (isOrgAdmin) {
                let logsUrl = `${API_BASE_URL}/organization/billing-logs`;
                const params = [];
                if (startDate) params.push(`start_date=${startDate}`);
                if (endDate) params.push(`end_date=${endDate}`);
                if (params.length > 0) {
                    logsUrl += `?${params.join('&')}`;
                }
                
                const res = await fetch(logsUrl, {
                    headers
                });

                if (!res.ok) {
                    const errData = await res.json().catch(() => ({}));
                    throw new Error(errData.detail || 'Failed to fetch organization billing and logs');
                }

                const data = await res.json();
                setOrgBillingData(data);
            } else {
                const taskToken = getCachedTaskToken(selectedProjectKey)?.token;
                if (taskToken) {
                    headers['x-task-token'] = taskToken;
                }

                const res = await fetch(`${API_BASE_URL}/api/agent/billing-dashboard/`, {
                    headers
                });

                if (!res.ok) {
                    const errData = await res.json().catch(() => ({}));
                    throw new Error(errData.detail || 'Failed to fetch billing dashboard');
                }

                const data = await res.json();
                setBillingData(data);
            }
        } catch (err) {
            console.error('Error fetching billing data:', err);
            setError(err.message);
        } finally {
            setLoading(false);
            setRefreshing(false);
        }
    };

    const handleDownloadReport = () => {
        if (!orgBillingData) return;
        
        try {
            const doc = new jsPDF({
                orientation: 'p',
                unit: 'mm',
                format: 'a4'
            });
            
            // Filtered lists matching current search
            const filteredUsers = processedUsers;
            const filteredProjects = processedProjects;
            
            // Dynamic sums based on filters
            const totalCost = filteredUsers.reduce((sum, u) => sum + (u.total_cost || 0), 0);
            const totalTokenCost = filteredUsers.reduce((sum, u) => sum + (u.token_cost || 0), 0);
            const totalInfraCost = filteredUsers.reduce((sum, u) => sum + (u.infra_cost || 0), 0);
            const totalPromptTokens = filteredUsers.reduce((sum, u) => sum + (u.ai_usage?.reduce((s, a) => s + (a.prompt || 0), 0) || 0), 0);
            const totalCompletionTokens = filteredUsers.reduce((sum, u) => sum + (u.ai_usage?.reduce((s, a) => s + (a.completion || 0), 0) || 0), 0);
            
            const costByModel = {};
            filteredUsers.forEach(u => {
                u.ai_usage?.forEach(a => {
                    costByModel[a.model] = (costByModel[a.model] || 0) + (a.cost || 0);
                });
            });
            
            // Page dimension metrics
            const pageWidth = 210;
            const pageHeight = 297;
            const margin = 15;
            const contentWidth = pageWidth - (margin * 2);
            let cursorY = 20;
            
            const checkSpace = (heightNeeded) => {
                if (cursorY + heightNeeded > pageHeight - 15) {
                    doc.addPage();
                    cursorY = 20;
                    drawHeader();
                }
            };
            
            const drawHeader = () => {
                // Draw small top page band
                doc.setFillColor(30, 58, 138); // primary dark blue
                doc.rect(margin, cursorY, contentWidth, 8, 'F');
                doc.setFont('helvetica', 'bold');
                doc.setFontSize(9);
                doc.setTextColor(255, 255, 255);
                doc.text("DSuite Organization Billing & Utilization Report", margin + 3, cursorY + 5.5);
                
                doc.setFont('helvetica', 'normal');
                doc.setFontSize(8);
                doc.setTextColor(100, 116, 139); // Slate-500
                const dateStr = `Generated: ${new Date().toLocaleDateString()}`;
                doc.text(dateStr, pageWidth - margin - doc.getTextWidth(dateStr), cursorY + 5.5);
                
                cursorY += 12;
            };
            
            // COVER PAGE OR HEADER
            doc.setFillColor(30, 58, 138);
            doc.rect(0, 0, pageWidth, 50, 'F');
            
            doc.setFont('helvetica', 'bold');
            doc.setFontSize(20);
            doc.setTextColor(255, 255, 255);
            doc.text("Organization Utilization Report", margin, 24);
            
            doc.setFont('helvetica', 'normal');
            doc.setFontSize(11);
            doc.setTextColor(226, 232, 240);
            doc.text(`Organization: ${orgBillingData.organization_name || 'Biourntec'}`, margin, 32);
            
            const periodStr = startDate || endDate 
                ? `Period: ${startDate || 'Beginning'} to ${endDate || 'Present'}`
                : `Period: All-Time`;
            doc.text(periodStr, margin, 38);
            
            doc.setFontSize(9);
            doc.text(`Exported By: ${user?.email || 'Admin'}`, margin, 44);
            
            cursorY = 60;
            
            // SECTION 1: SUMMARY KPIs
            doc.setFont('helvetica', 'bold');
            doc.setFontSize(12);
            doc.setTextColor(15, 23, 42); // Slate-900
            doc.text("1. Executive Summary KPIs", margin, cursorY);
            cursorY += 6;
            
            // Draw KPI Boxes (4 boxes)
            const kpiWidth = (contentWidth - 9) / 4;
            const kpiHeight = 18;
            
            // Total cost box
            doc.setFillColor(248, 250, 252);
            doc.setDrawColor(226, 232, 240);
            doc.roundedRect(margin, cursorY, kpiWidth, kpiHeight, 1, 1, 'FD');
            doc.setFont('helvetica', 'bold');
            doc.setFontSize(7.5);
            doc.setTextColor(100, 116, 139);
            doc.text("TOTAL SPEND (USD)", margin + 3, cursorY + 5);
            doc.setFontSize(11);
            doc.setTextColor(16, 185, 129); // Emerald-500
            doc.text(`$${totalCost?.toFixed(2)}`, margin + 3, cursorY + 12);
            
            // Token cost box
            doc.setFillColor(248, 250, 252);
            doc.roundedRect(margin + kpiWidth + 3, cursorY, kpiWidth, kpiHeight, 1, 1, 'FD');
            doc.setFont('helvetica', 'bold');
            doc.setFontSize(7.5);
            doc.setTextColor(100, 116, 139);
            doc.text("TOKEN COST (USD)", margin + kpiWidth + 6, cursorY + 5);
            doc.setFontSize(11);
            doc.setTextColor(59, 130, 246); // Blue-500
            doc.text(`$${totalTokenCost?.toFixed(2)}`, margin + kpiWidth + 6, cursorY + 12);

            // Infra cost box
            doc.setFillColor(248, 250, 252);
            doc.roundedRect(margin + (kpiWidth * 2) + 6, cursorY, kpiWidth, kpiHeight, 1, 1, 'FD');
            doc.setFont('helvetica', 'bold');
            doc.setFontSize(7.5);
            doc.setTextColor(100, 116, 139);
            doc.text("INFRA COST ($0.70/HR)", margin + (kpiWidth * 2) + 9, cursorY + 5);
            doc.setFontSize(11);
            doc.setTextColor(168, 85, 247); // Purple-500
            doc.text(`$${totalInfraCost?.toFixed(2)}`, margin + (kpiWidth * 2) + 9, cursorY + 12);

            // Total Tokens box
            doc.setFillColor(248, 250, 252);
            doc.roundedRect(margin + (kpiWidth * 3) + 9, cursorY, kpiWidth, kpiHeight, 1, 1, 'FD');
            doc.setFont('helvetica', 'bold');
            doc.setFontSize(7.5);
            doc.setTextColor(100, 116, 139);
            doc.text("TOTAL TOKENS", margin + (kpiWidth * 3) + 12, cursorY + 5);
            doc.setFontSize(11);
            doc.setTextColor(15, 23, 42);
            doc.text((totalPromptTokens + totalCompletionTokens)?.toLocaleString() || "0", margin + (kpiWidth * 3) + 12, cursorY + 12);
            
            cursorY += kpiHeight + 10;
            
            // Model breakdown
            if (costByModel && Object.keys(costByModel).length > 0) {
                doc.setFont('helvetica', 'bold');
                doc.setFontSize(10);
                doc.setTextColor(15, 23, 42);
                doc.text("Model Utilization Breakdown", margin, cursorY);
                cursorY += 5;
                
                doc.setFont('helvetica', 'normal');
                doc.setFontSize(8.5);
                doc.setTextColor(71, 85, 105);
                
                Object.entries(costByModel).forEach(([model, cost]) => {
                    checkSpace(6);
                    doc.text(`• ${model}:`, margin + 3, cursorY);
                    doc.setFont('helvetica', 'bold');
                    doc.text(`$${cost.toFixed(4)}`, margin + 85, cursorY);
                    doc.setFont('helvetica', 'normal');
                    cursorY += 5.5;
                });
                cursorY += 4;
            }
            
            // SECTION 2: USER ENGAGEMENT TABLE
            checkSpace(30);
            doc.setFont('helvetica', 'bold');
            doc.setFontSize(12);
            doc.setTextColor(15, 23, 42);
            doc.text("2. User Engagement & Spend Stats", margin, cursorY);
            cursorY += 6;
            
            // Draw table header
            doc.setFillColor(30, 58, 138);
            doc.rect(margin, cursorY, contentWidth, 7, 'F');
            doc.setFont('helvetica', 'bold');
            doc.setFontSize(7.5);
            doc.setTextColor(255, 255, 255);
            
            doc.text("Name / Email", margin + 2, cursorY + 5);
            doc.text("Status", margin + 45, cursorY + 5);
            doc.text("Sessions", margin + 63, cursorY + 5);
            doc.text("Total Time", margin + 81, cursorY + 5);
            doc.text("AI Tokens", margin + 102, cursorY + 5);
            doc.text("Token Cost", margin + 125, cursorY + 5);
            doc.text("Infra Cost", margin + 148, cursorY + 5);
            doc.text("Total Cost", margin + 168, cursorY + 5);
            
            cursorY += 7;
            
            // Populate user rows
            doc.setFont('helvetica', 'normal');
            doc.setFontSize(7);
            doc.setTextColor(51, 65, 85);
            
            (filteredUsers || []).forEach((u, i) => {
                checkSpace(11);
                if (i % 2 === 1) {
                    doc.setFillColor(248, 250, 252);
                    doc.rect(margin, cursorY, contentWidth, 9, 'F');
                }
                
                doc.setFont('helvetica', 'bold');
                doc.setTextColor(15, 23, 42);
                doc.text((u.name || u.email.split('@')[0]).slice(0, 20), margin + 2, cursorY + 4);
                doc.setFont('helvetica', 'normal');
                doc.setTextColor(100, 116, 139);
                doc.text(u.email.slice(0, 24), margin + 2, cursorY + 7.5);
                
                doc.setTextColor(51, 65, 85);
                doc.text(u.is_active ? "Active" : "Inactive", margin + 45, cursorY + 5.5);
                doc.text(String(u.session_count || 0), margin + 63, cursorY + 5.5);
                doc.text(`${u.total_duration_hours} hrs`, margin + 81, cursorY + 5.5);
                doc.text(u.ai_tokens?.toLocaleString() || "0", margin + 102, cursorY + 5.5);
                doc.text(`$${(u.token_cost || 0).toFixed(4)}`, margin + 125, cursorY + 5.5);
                doc.text(`$${(u.infra_cost || 0).toFixed(4)}`, margin + 148, cursorY + 5.5);
                doc.text(`$${(u.total_cost || 0).toFixed(4)}`, margin + 168, cursorY + 5.5);
                
                // Draw bottom row border
                doc.setDrawColor(241, 245, 249);
                doc.line(margin, cursorY + 9, pageWidth - margin, cursorY + 9);
                
                cursorY += 9.5;
            });
            
            cursorY += 5;
            
            // SECTION 3: PROJECTS HUB
            checkSpace(35);
            doc.setFont('helvetica', 'bold');
            doc.setFontSize(12);
            doc.setTextColor(15, 23, 42);
            doc.text("3. Projects Hub Status", margin, cursorY);
            cursorY += 6;
            
            // Draw Projects Table Header
            doc.setFillColor(30, 58, 138);
            doc.rect(margin, cursorY, contentWidth, 7, 'F');
            doc.setFont('helvetica', 'bold');
            doc.setFontSize(8);
            doc.setTextColor(255, 255, 255);
            
            doc.text("Project Name", margin + 3, cursorY + 5);
            doc.text("Owner", margin + 50, cursorY + 5);
            doc.text("Classification", margin + 100, cursorY + 5);
            doc.text("Runs", margin + 130, cursorY + 5);
            doc.text("Build Status", margin + 148, cursorY + 5);
            doc.text("Submission Date", margin + 168, cursorY + 5);
            
            cursorY += 7;
            
            // Projects Rows
            doc.setFont('helvetica', 'normal');
            doc.setFontSize(7.5);
            doc.setTextColor(51, 65, 85);
            
            (filteredProjects || []).forEach((p, i) => {
                checkSpace(11);
                if (i % 2 === 1) {
                    doc.setFillColor(248, 250, 252);
                    doc.rect(margin, cursorY, contentWidth, 10, 'F');
                }
                
                doc.setFont('helvetica', 'bold');
                doc.setTextColor(15, 23, 42);
                doc.text(p.project_name.slice(0, 28), margin + 3, cursorY + 4);
                doc.setFont('helvetica', 'normal');
                doc.setTextColor(100, 116, 139);
                doc.text(p.project_token.slice(0, 24) + "...", margin + 3, cursorY + 7.5);
                
                doc.setTextColor(51, 65, 85);
                doc.text(p.owner_email, margin + 50, cursorY + 5.5);
                doc.text(p.classification, margin + 100, cursorY + 5.5);
                doc.text(String(p.total_runs), margin + 130, cursorY + 5.5);
                doc.text(p.run_status, margin + 148, cursorY + 5.5);
                
                const subDate = p.submission_date ? new Date(p.submission_date).toLocaleDateString() : "—";
                doc.text(subDate, margin + 168, cursorY + 5.5);
                
                doc.setDrawColor(241, 245, 249);
                doc.line(margin, cursorY + 10, pageWidth - margin, cursorY + 10);
                cursorY += 10.5;
            });
            
            // Draw footer indicators
            const totalPages = doc.getNumberOfPages();
            for (let page = 1; page <= totalPages; page += 1) {
                doc.setPage(page);
                doc.setFont('helvetica', 'normal');
                doc.setFontSize(7.5);
                doc.setTextColor(148, 163, 184); // Slate-400
                const pageLabel = `Page ${page} of ${totalPages}`;
                doc.text(pageLabel, pageWidth - margin - doc.getTextWidth(pageLabel), pageHeight - 8);
                doc.text("Confidential • Internal Organization Analytics", margin, pageHeight - 8);
            }
            
            doc.save(`${(orgBillingData.organization_name || 'Organization').replace(/\s+/g, '_')}_utilization_report.pdf`);
        } catch (pdfErr) {
            console.error('Failed to generate PDF:', pdfErr);
            alert('Failed to generate PDF: ' + pdfErr.message);
        }
    };

    const handleExportExcel = () => {
        if (!orgBillingData) return;

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

            // Header
            rows.push(['ORGANIZATION UTILIZATION & BILLING REPORT']);
            rows.push(['Organization:', orgBillingData.organization_name || '—']);
            rows.push(['Generated At:', new Date().toLocaleString()]);
            rows.push([]);

            // Executive Summary
            rows.push(['EXECUTIVE SUMMARY']);
            rows.push(['Total Token Cost (USD)', orgBillingData.summary?.total_token_cost || 0]);
            rows.push(['Total Infra Cost (USD, $0.70/hr)', orgBillingData.summary?.total_infra_cost || 0]);
            rows.push(['Total Combined Cost (USD)', orgBillingData.summary?.total_cost || 0]);
            rows.push(['Total Prompt Tokens', orgBillingData.summary?.total_prompt_tokens || 0]);
            rows.push(['Total Completion Tokens', orgBillingData.summary?.total_completion_tokens || 0]);
            rows.push(['Total Requests', orgBillingData.detailed_ai_logs?.length || 0]);
            rows.push([]);

            // 2. Cost By Model
            rows.push(['2. COST BY MODEL']);
            rows.push(['Model', 'Total Cost (USD)']);
            if (orgBillingData.summary?.cost_by_model) {
                Object.entries(orgBillingData.summary.cost_by_model).forEach(([model, cost]) => {
                    rows.push([model, `$${cost}`]);
                });
            } else {
                rows.push(['None', '$0.00']);
            }
            rows.push([]);

            // 4. User Stats
            rows.push(['3. USER UTILIZATION BREAKDOWN']);
            rows.push([
                'User Name',
                'Email',
                'Is Active',
                'Is Org Admin',
                'Session Count',
                'Session Duration (Hours)',
                'AI Tokens',
                'Projects Created',
                'Token Cost (USD)',
                'Infra Cost (USD, $0.70/hr)',
                'Total Cost (USD)',
                'Last Login'
            ]);
            if (orgBillingData.user_stats) {
                orgBillingData.user_stats.forEach(u => {
                    rows.push([
                        u.name || '',
                        u.email || '',
                        u.is_active ? 'Yes' : 'No',
                        u.is_org_admin ? 'Yes' : 'No',
                        u.session_count || 0,
                        u.total_duration_hours || 0,
                        u.ai_tokens || 0,
                        u.projects_count || 0,
                        u.token_cost || 0,
                        u.infra_cost || 0,
                        u.total_cost || 0,
                        u.last_login || '—'
                    ]);
                });
            }
            rows.push([]);

            // Convert to CSV string
            const csvContent = rows
                .map(row => row.map(cell => escapeCSV(cell)).join(','))
                .join('\n');

            // Trigger file download
            const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
            const url = URL.createObjectURL(blob);
            const link = document.createElement('a');
            const fileName = `${(orgBillingData.organization_name || 'Organization').replace(/\s+/g, '_')}_utilization_report.csv`;
            
            link.setAttribute('href', url);
            link.setAttribute('download', fileName);
            link.style.visibility = 'hidden';
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
            
            URL.revokeObjectURL(url);
        } catch (csvErr) {
            console.error('Failed to export Excel CSV:', csvErr);
            alert('Failed to export Excel CSV: ' + csvErr.message);
        }
    };

    useEffect(() => {
        fetchBillingData();
    }, [selectedProjectKey, isOrgAdmin, startDate, endDate]);

    // Handle user sort
    const handleUserSort = (field) => {
        if (userSortField === field) {
            setUserSortAsc(!userSortAsc);
        } else {
            setUserSortField(field);
            setUserSortAsc(true);
        }
    };

    // Filter and Sort org users
    const processedUsers = useMemo(() => {
        if (!orgBillingData || !orgBillingData.user_stats) return [];
        
        let list = orgBillingData.user_stats.map(u => {
            const bournaiUsage = u.ai_usage?.filter(a => (a.model || '').toLowerCase() === 'bournai') || [];
            const bournaiTokenCost = bournaiUsage.reduce((s, a) => s + (a.cost || 0), 0);
            const bournaiTokens = bournaiUsage.reduce((s, a) => s + (a.prompt || 0) + (a.completion || 0), 0);
            const tokenCost = u.token_cost ?? bournaiTokenCost;
            const infraCost = u.infra_cost ?? Math.max(0, (u.total_cost || 0) - (u.token_cost ?? u.ai_usage?.reduce((s, a) => s + (a.cost || 0), 0)));
            return {
                ...u,
                token_cost: tokenCost,
                infra_cost: infraCost,
                total_cost: u.total_cost ?? (tokenCost + infraCost),
                ai_tokens: u.ai_tokens ?? bournaiTokens
            };
        });
        
        // Search
        if (searchTerm) {
            const term = searchTerm.toLowerCase();
            list = list.filter(u => 
                (u.name || '').toLowerCase().includes(term) || 
                (u.email || '').toLowerCase().includes(term)
            );
        }
        
        // Sort
        list.sort((a, b) => {
            let valA = a[userSortField];
            let valB = b[userSortField];
            
            if (userSortField === 'name') {
                valA = (a.name || '').toLowerCase();
                valB = (b.name || '').toLowerCase();
            } else if (userSortField === 'email') {
                valA = (a.email || '').toLowerCase();
                valB = (b.email || '').toLowerCase();
            }
            
            if (valA < valB) return userSortAsc ? -1 : 1;
            if (valA > valB) return userSortAsc ? 1 : -1;
            return 0;
        });
        
        return list;
    }, [orgBillingData, searchTerm, userSortField, userSortAsc]);

    // Filter and Sort org projects
    const processedProjects = useMemo(() => {
        if (!orgBillingData || !orgBillingData.projects_list) return [];
        
        let list = [...orgBillingData.projects_list];
        
        // Search
        if (searchTerm) {
            const term = searchTerm.toLowerCase();
            list = list.filter(p => 
                p.project_name.toLowerCase().includes(term) || 
                p.project_token.toLowerCase().includes(term) ||
                p.owner_email.toLowerCase().includes(term)
            );
        }
        
        return list;
    }, [orgBillingData, searchTerm]);

    const derivedSummary = useMemo(() => {
        if (!orgBillingData) return {};
        const rawSummary = orgBillingData.summary || {};

        const calcTokenCost = processedUsers.reduce((sum, u) => sum + (u.token_cost || 0), 0);
        const calcInfraCost = processedUsers.reduce((sum, u) => sum + (u.infra_cost || 0), 0);
        const calcTotalCost = processedUsers.reduce((sum, u) => sum + (u.total_cost || 0), 0);
        
        if (!searchTerm) {
            return {
                ...rawSummary,
                total_token_cost: rawSummary.total_token_cost ?? calcTokenCost,
                total_infra_cost: rawSummary.total_infra_cost ?? calcInfraCost,
                total_cost: rawSummary.total_cost ?? calcTotalCost,
                total_prompt_tokens: rawSummary.total_prompt_tokens || 0,
                total_completion_tokens: rawSummary.total_completion_tokens || 0,
            };
        }
        
        let totalPrompt = 0;
        let totalCompletion = 0;
        const costByModel = {};
        
        processedUsers.forEach(u => {
            u.ai_usage?.forEach(a => {
                if ((a.model || '').toLowerCase() === 'bournai') {
                    totalPrompt += (a.prompt || 0);
                    totalCompletion += (a.completion || 0);
                }
                costByModel[a.model] = (costByModel[a.model] || 0) + (a.cost || 0);
            });
        });
        
        return {
            total_token_cost: calcTokenCost,
            total_infra_cost: calcInfraCost,
            total_cost: calcTotalCost,
            total_prompt_tokens: totalPrompt,
            total_completion_tokens: totalCompletion,
            cost_by_model: costByModel
        };
    }, [orgBillingData, processedUsers, searchTerm]);

    // Filtered lists for Standard User View
    const filteredTasks = useMemo(() => {
        if (!billingData || !billingData.tasks) return [];
        return billingData.tasks.filter(task => {
            const matchesSearch =
                task.task_id.toLowerCase().includes(searchTerm.toLowerCase()) ||
                task.task_name.toLowerCase().includes(searchTerm.toLowerCase());

            const matchesAgent =
                agentFilter === 'all' ||
                task.agent_name === agentFilter;

            return matchesSearch && matchesAgent;
        });
    }, [billingData, searchTerm, agentFilter]);

    // Unique agents for Standard User View
    const uniqueAgentNames = useMemo(() => {
        if (!billingData || !billingData.agent_breakdown) return [];
        return billingData.agent_breakdown.map(agent => agent.agent_name);
    }, [billingData]);

    if (loading) {
        return (
            <div className="flex flex-col items-center justify-center min-h-[400px] py-12 bg-app-bg-page">
                <RefreshCw className="w-10 h-10 text-app-primary animate-spin mb-4" />
                <p className="text-app-text-muted text-sm font-medium">
                    {isOrgAdmin 
                        ? 'Fetching organization billing metrics and operational logs...' 
                        : 'Calculating agent hours and computing billing matrices...'}
                </p>
            </div>
        );
    }

    if (error) {
        return (
            <div className="max-w-2xl mx-auto px-4 py-12 text-center bg-app-bg-page">
                <div className="inline-flex p-3 bg-rose-500/10 rounded-full text-rose-400 mb-4 border border-rose-500/20">
                    <AlertCircle className="w-8 h-8" />
                </div>
                <h3 className="text-xl font-bold text-app-text-main mb-2">Billing Data Unavailable</h3>
                <p className="text-app-text-muted mb-6 text-sm">{error}</p>
                <button
                    onClick={() => fetchBillingData()}
                    className="px-5 py-2.5 bg-app-primary hover:bg-app-primary-hover text-white font-medium rounded-lg transition-colors inline-flex items-center gap-2"
                >
                    <RefreshCw className="w-4 h-4" /> Retry Connection
                </button>
            </div>
        );
    }

    // ── RENDER 1: Organization Admin Billing & Logs Dashboard ──
    if (isOrgAdmin && orgBillingData) {
        const { organization_name } = orgBillingData;
        const orgSummary = derivedSummary;

        return (
            <div className="flex-1 overflow-y-auto h-full bg-app-bg-page custom-scrollbar">
                <style dangerouslySetInnerHTML={{__html: `
                    @media print {
                        aside, nav, .no-print, button, input, select {
                            display: none !important;
                        }
                        body, html, #root {
                            background: white !important;
                            color: black !important;
                        }
                        .flex-1, main {
                            overflow: visible !important;
                            height: auto !important;
                            padding: 0 !important;
                            margin: 0 !important;
                        }
                    }
                `}} />
                <div className="max-w-7xl mx-auto px-4 sm:px-6 py-6 space-y-6">
                    {/* Header */}
                    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-5 border-b border-app-border/80">
                        <div className="space-y-1">
                            <div className="flex items-center gap-2.5 flex-wrap">
                                <h1 className="text-2xl sm:text-3xl font-bold tracking-tight text-app-text-main">
                                    Org Billing & Activity Logs
                                </h1>
                                <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 text-xs font-semibold rounded-full bg-indigo-50 dark:bg-indigo-950/50 text-indigo-700 dark:text-indigo-400 border border-indigo-200/60 dark:border-indigo-800/60 shadow-xs">
                                    <ShieldCheck className="w-3.5 h-3.5" /> Org Admin
                                </span>
                            </div>
                            <p className="text-xs sm:text-sm text-app-text-muted">
                                Centralized tracking of costs, usage, and operations generated inside <span className="font-semibold text-app-text-main">{organization_name}</span>.
                            </p>
                        </div>
                        <div className="flex items-center gap-2 self-start md:self-auto flex-nowrap shrink-0 overflow-x-auto no-print">
                            <button
                                onClick={handleDownloadReport}
                                className="h-9 px-3.5 bg-app-bg-card hover:bg-app-bg-hover text-app-text-main border border-app-border rounded-lg text-xs font-semibold inline-flex items-center gap-2 shadow-xs transition-colors cursor-pointer whitespace-nowrap shrink-0"
                                title="Download PDF Report"
                            >
                                <ExternalLink className="w-3.5 h-3.5 text-app-text-muted" />
                                Download Report
                            </button>
                            <button
                                onClick={handleExportExcel}
                                className="h-9 px-3.5 bg-app-bg-card hover:bg-app-bg-hover text-app-text-main border border-app-border rounded-lg text-xs font-semibold inline-flex items-center gap-2 shadow-xs transition-colors cursor-pointer whitespace-nowrap shrink-0"
                                title="Export Excel Spreadsheet"
                            >
                                <FileSpreadsheet className="w-3.5 h-3.5 text-emerald-600 dark:text-emerald-400" />
                                Export Excel
                            </button>
                            <button
                                onClick={() => fetchBillingData(true)}
                                disabled={refreshing}
                                className="h-9 px-3.5 bg-app-bg-card hover:bg-app-bg-hover text-app-text-main border border-app-border rounded-lg text-xs font-semibold inline-flex items-center gap-2 disabled:opacity-50 shadow-xs transition-colors cursor-pointer whitespace-nowrap shrink-0"
                                title="Refresh Logs"
                            >
                                <RefreshCw className={`w-3.5 h-3.5 text-app-text-muted ${refreshing ? 'animate-spin' : ''}`} />
                                {refreshing ? 'Refreshing...' : 'Refresh Logs'}
                            </button>
                        </div>
                    </div>

                    {/* Unified Controls Toolbar: Navigation Tabs & Date Range Filter */}
                    <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-3 no-print">
                        {/* Navigation Tabs */}
                        <div className="inline-flex p-1 rounded-xl bg-slate-100 dark:bg-slate-800/80 border border-slate-200/80 dark:border-slate-700/80 shadow-xs max-w-full overflow-x-auto custom-scrollbar md:no-scrollbar">
                            <button 
                                className={`px-3.5 py-1.5 rounded-lg text-xs sm:text-sm font-semibold transition-all flex items-center gap-2 cursor-pointer whitespace-nowrap ${
                                    activeTab === 'overview' 
                                        ? 'bg-white dark:bg-slate-900 text-indigo-600 dark:text-indigo-400 shadow-xs' 
                                        : 'text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-200'
                                }`}
                                onClick={() => { setActiveTab('overview'); setSearchTerm(''); }}
                            >
                                <Activity className="w-3.5 h-3.5" />
                                Overview
                            </button>
                            <button 
                                className={`px-3.5 py-1.5 rounded-lg text-xs sm:text-sm font-semibold transition-all flex items-center gap-2 cursor-pointer whitespace-nowrap ${
                                    activeTab === 'users' 
                                        ? 'bg-white dark:bg-slate-900 text-indigo-600 dark:text-indigo-400 shadow-xs' 
                                        : 'text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-200'
                                }`}
                                onClick={() => { setActiveTab('users'); setSearchTerm(''); }}
                            >
                                <Users className="w-3.5 h-3.5" />
                                User Engagement
                            </button>
                            <button 
                                className={`px-3.5 py-1.5 rounded-lg text-xs sm:text-sm font-semibold transition-all flex items-center gap-2 cursor-pointer whitespace-nowrap ${
                                    activeTab === 'projects' 
                                        ? 'bg-white dark:bg-slate-900 text-indigo-600 dark:text-indigo-400 shadow-xs' 
                                        : 'text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-200'
                                }`}
                                onClick={() => { setActiveTab('projects'); setSearchTerm(''); }}
                            >
                                <Globe className="w-3.5 h-3.5" />
                                Projects Hub
                            </button>
                            {isOrgAdmin && (
                                <button 
                                    className={`px-3.5 py-1.5 rounded-lg text-xs sm:text-sm font-semibold transition-all flex items-center gap-2 cursor-pointer whitespace-nowrap ${
                                        activeTab === 'tokenops' 
                                            ? 'bg-white dark:bg-slate-900 text-indigo-600 dark:text-indigo-400 shadow-xs' 
                                            : 'text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-200'
                                    }`}
                                    onClick={() => { setActiveTab('tokenops'); setSearchTerm(''); }}
                                >
                                    <Coins className="w-3.5 h-3.5" />
                                    TokenOps Quotas
                                </button>
                            )}
                        </div>

                        {/* Compact Date Range Filter */}
                        <div className="flex items-center gap-2.5 bg-app-bg-card border border-app-border rounded-xl px-3 py-1.5 shadow-xs self-start lg:self-auto flex-nowrap shrink-0 whitespace-nowrap overflow-x-auto">
                            <div className="flex items-center gap-1.5 text-app-text-muted text-xs font-semibold shrink-0">
                                <Clock className="w-3.5 h-3.5 text-indigo-500 shrink-0" />
                                <span className="uppercase tracking-wider text-[10px] whitespace-nowrap">Range:</span>
                            </div>
                            <div className="flex items-center gap-1.5 text-xs shrink-0 whitespace-nowrap">
                                <input
                                    type="date"
                                    value={startDate}
                                    onChange={(e) => setStartDate(e.target.value)}
                                    aria-label="Start Date"
                                    className="h-7 px-2 bg-app-bg-muted border border-app-border hover:border-slate-400 dark:hover:border-slate-500 text-[11px] text-app-text-main rounded-md focus:outline-none focus:ring-1 focus:ring-indigo-500 cursor-pointer"
                                />
                                <span className="text-app-text-muted text-[11px] font-medium shrink-0">to</span>
                                <input
                                    type="date"
                                    value={endDate}
                                    onChange={(e) => setEndDate(e.target.value)}
                                    aria-label="End Date"
                                    className="h-7 px-2 bg-app-bg-muted border border-app-border hover:border-slate-400 dark:hover:border-slate-500 text-[11px] text-app-text-main rounded-md focus:outline-none focus:ring-1 focus:ring-indigo-500 cursor-pointer"
                                />
                            </div>
                            {(startDate || endDate) && (
                                <button
                                    onClick={() => { setStartDate(''); setEndDate(''); }}
                                    className="h-6 px-2 bg-rose-50 hover:bg-rose-100 dark:bg-rose-950/40 dark:hover:bg-rose-900/60 border border-rose-200 dark:border-rose-800/60 text-rose-600 dark:text-rose-400 text-[10px] font-bold rounded-md transition-colors cursor-pointer shrink-0 whitespace-nowrap"
                                >
                                    Clear
                                </button>
                            )}
                        </div>
                    </div>

                    {/* OVERVIEW TAB */}
                    {activeTab === 'overview' && (
                        <div className="space-y-6 animate-fade-in">
                            {/* KPI Grid */}
                            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3.5">
                                {/* Total Cost */}
                                <div className="bg-app-bg-card border border-app-border hover:border-slate-300 dark:hover:border-slate-600 rounded-xl p-3 sm:p-3.5 transition-all shadow-xs hover:shadow-md flex flex-col justify-between">
                                    <div className="flex items-center justify-between gap-2">
                                        <span className="text-[10px] sm:text-[11px] font-semibold text-app-text-muted uppercase tracking-wider">
                                            Total Organization Cost
                                        </span>
                                        <div className="w-7 h-7 rounded-lg bg-emerald-50 dark:bg-emerald-950/40 text-emerald-600 dark:text-emerald-400 flex items-center justify-center shrink-0">
                                            <DollarSign className="w-3.5 h-3.5" />
                                        </div>
                                    </div>
                                    <div className="mt-1.5">
                                        <div className="text-xl sm:text-2xl font-bold tracking-tight text-app-text-main">
                                            ${(orgSummary.total_cost ?? 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 3 })}
                                        </div>
                                        <p className="text-[10px] sm:text-[11px] text-emerald-600 dark:text-emerald-400 mt-0.5 flex items-center gap-1 font-medium">
                                            <CheckCircle2 className="w-3 h-3 shrink-0" /> Token + Infra Cost ($0.70/hr)
                                        </p>
                                    </div>
                                </div>

                                {/* Token Cost */}
                                <div className="bg-app-bg-card border border-app-border hover:border-slate-300 dark:hover:border-slate-600 rounded-xl p-3 sm:p-3.5 transition-all shadow-xs hover:shadow-md flex flex-col justify-between">
                                    <div className="flex items-center justify-between gap-2">
                                        <span className="text-[10px] sm:text-[11px] font-semibold text-app-text-muted uppercase tracking-wider">
                                            Token Cost (AI Usage)
                                        </span>
                                        <div className="w-7 h-7 rounded-lg bg-blue-50 dark:bg-blue-950/40 text-blue-600 dark:text-blue-400 flex items-center justify-center shrink-0">
                                            <FileText className="w-3.5 h-3.5" />
                                        </div>
                                    </div>
                                    <div className="mt-1.5">
                                        <div className="text-xl sm:text-2xl font-bold tracking-tight text-app-text-main">
                                            ${(orgSummary.total_token_cost ?? 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 3 })}
                                        </div>
                                        <p className="text-[10px] sm:text-[11px] text-app-text-muted mt-0.5 font-medium">
                                            Prompt + Completion token spend
                                        </p>
                                    </div>
                                </div>

                                {/* Infra Cost */}
                                <div className="bg-app-bg-card border border-app-border hover:border-slate-300 dark:hover:border-slate-600 rounded-xl p-3 sm:p-3.5 transition-all shadow-xs hover:shadow-md flex flex-col justify-between">
                                    <div className="flex items-center justify-between gap-2">
                                        <span className="text-[10px] sm:text-[11px] font-semibold text-app-text-muted uppercase tracking-wider">
                                            Infra Cost
                                        </span>
                                        <div className="w-7 h-7 rounded-lg bg-purple-50 dark:bg-purple-950/40 text-purple-600 dark:text-purple-400 flex items-center justify-center shrink-0">
                                            <Clock className="w-3.5 h-3.5" />
                                        </div>
                                    </div>
                                    <div className="mt-1.5">
                                        <div className="text-xl sm:text-2xl font-bold tracking-tight text-app-text-main">
                                            ${(orgSummary.total_infra_cost ?? 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 3 })}
                                        </div>
                                        <p className="text-[10px] sm:text-[11px] text-app-text-muted mt-0.5 font-medium">
                                            Active user compute hours ($0.70/hr)
                                        </p>
                                    </div>
                                </div>

                                {/* Prompt Tokens */}
                                <div className="bg-app-bg-card border border-app-border hover:border-slate-300 dark:hover:border-slate-600 rounded-xl p-3 sm:p-3.5 transition-all shadow-xs hover:shadow-md flex flex-col justify-between">
                                    <div className="flex items-center justify-between gap-2">
                                        <span className="text-[10px] sm:text-[11px] font-semibold text-app-text-muted uppercase tracking-wider">
                                            Prompt Tokens
                                        </span>
                                        <div className="w-7 h-7 rounded-lg bg-indigo-50 dark:bg-indigo-950/40 text-indigo-600 dark:text-indigo-400 flex items-center justify-center shrink-0">
                                            <Zap className="w-3.5 h-3.5" />
                                        </div>
                                    </div>
                                    <div className="mt-1.5">
                                        <div className="text-xl sm:text-2xl font-bold tracking-tight text-app-text-main">
                                            {orgSummary.total_prompt_tokens?.toLocaleString() || 0}
                                        </div>
                                        <p className="text-[10px] sm:text-[11px] text-app-text-muted mt-0.5 font-medium">
                                            Input tokens sent to AI models
                                        </p>
                                    </div>
                                </div>

                                {/* Completion Tokens */}
                                <div className="bg-app-bg-card border border-app-border hover:border-slate-300 dark:hover:border-slate-600 rounded-xl p-3 sm:p-3.5 transition-all shadow-xs hover:shadow-md flex flex-col justify-between">
                                    <div className="flex items-center justify-between gap-2">
                                        <span className="text-[10px] sm:text-[11px] font-semibold text-app-text-muted uppercase tracking-wider">
                                            Completion Tokens
                                        </span>
                                        <div className="w-7 h-7 rounded-lg bg-pink-50 dark:bg-pink-950/40 text-pink-600 dark:text-pink-400 flex items-center justify-center shrink-0">
                                            <Bot className="w-3.5 h-3.5" />
                                        </div>
                                    </div>
                                    <div className="mt-1.5">
                                        <div className="text-xl sm:text-2xl font-bold tracking-tight text-app-text-main">
                                            {orgSummary.total_completion_tokens?.toLocaleString() || 0}
                                        </div>
                                        <p className="text-[10px] sm:text-[11px] text-app-text-muted mt-0.5 font-medium">
                                            Output tokens generated by models
                                        </p>
                                    </div>
                                </div>

                                {/* Org Members */}
                                <div className="bg-app-bg-card border border-app-border hover:border-slate-300 dark:hover:border-slate-600 rounded-xl p-3 sm:p-3.5 transition-all shadow-xs hover:shadow-md flex flex-col justify-between">
                                    <div className="flex items-center justify-between gap-2">
                                        <span className="text-[10px] sm:text-[11px] font-semibold text-app-text-muted uppercase tracking-wider">
                                            Org Members
                                        </span>
                                        <div className="w-7 h-7 rounded-lg bg-teal-50 dark:bg-teal-950/40 text-teal-600 dark:text-teal-400 flex items-center justify-center shrink-0">
                                            <Users className="w-3.5 h-3.5" />
                                        </div>
                                    </div>
                                    <div className="mt-1.5">
                                        <div className="text-xl sm:text-2xl font-bold tracking-tight text-app-text-main">
                                            {processedUsers.length}
                                        </div>
                                        <p className="text-[10px] sm:text-[11px] text-app-text-muted mt-0.5 font-medium">
                                            Active members in organization
                                        </p>
                                    </div>
                                </div>
                            </div>

                            {/* Cost Breakdown by AI Model */}
                            {orgSummary.cost_by_model && Object.keys(orgSummary.cost_by_model).length > 0 && (
                                <div className="bg-app-bg-card border border-app-border rounded-xl p-5 sm:p-6 shadow-xs">
                                    <div className="flex items-center justify-between mb-4">
                                        <h3 className="text-sm sm:text-base font-bold text-app-text-main flex items-center gap-2">
                                            <Cpu className="w-4 h-4 text-indigo-500" /> Cost Breakdown by AI Model
                                        </h3>
                                        <span className="text-[11px] font-semibold text-app-text-muted bg-app-bg-muted px-2.5 py-0.5 rounded-full border border-app-border">
                                            {Object.keys(orgSummary.cost_by_model).length} {Object.keys(orgSummary.cost_by_model).length === 1 ? 'Model' : 'Models'}
                                        </span>
                                    </div>
                                    <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-3.5">
                                        {Object.entries(orgSummary.cost_by_model).map(([modelName, costValue]) => {
                                            const percentage = orgSummary.total_cost > 0
                                                ? Math.round((costValue / orgSummary.total_cost) * 100)
                                                : 0;
                                            return (
                                                <div key={modelName} className="p-3.5 rounded-xl border border-app-border/80 bg-app-bg-muted/40 hover:bg-app-bg-muted/70 transition-colors">
                                                    <div className="flex justify-between items-center mb-1.5">
                                                        <span className="text-xs font-bold text-app-text-main font-mono truncate mr-2" title={modelName}>{modelName}</span>
                                                        <span className="text-xs font-bold text-app-text-main">${costValue.toFixed(4)}</span>
                                                    </div>
                                                    <div className="w-full bg-slate-200 dark:bg-slate-700 rounded-full h-1.5 overflow-hidden">
                                                        <div className="h-full bg-indigo-500 rounded-full transition-all duration-300" style={{ width: `${percentage}%` }} />
                                                    </div>
                                                    <div className="flex justify-between text-[10px] text-app-text-muted mt-1.5 font-medium">
                                                        <span>Share</span>
                                                        <span className="font-semibold text-app-text-main">{percentage}%</span>
                                                    </div>
                                                </div>
                                            );
                                        })}
                                    </div>
                                </div>
                            )}
                        </div>
                    )}

                    {/* USER ENGAGEMENT TAB */}
                    {activeTab === 'users' && (
                        <div className="bg-app-bg-card border border-app-border rounded-xl p-5 sm:p-6 shadow-xs animate-fade-in space-y-4">
                            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                                <div className="flex items-center gap-2">
                                    <h3 className="text-base font-bold text-app-text-main flex items-center gap-2">
                                        <Users className="w-4 h-4 text-indigo-500" /> User Engagement Stats
                                    </h3>
                                    <span className="text-[11px] font-semibold text-app-text-muted bg-app-bg-muted px-2.5 py-0.5 rounded-full border border-app-border">
                                        {processedUsers.length} {processedUsers.length === 1 ? 'User' : 'Users'}
                                    </span>
                                </div>
                                <div className="relative no-print">
                                    <Search className="w-3.5 h-3.5 absolute left-3 top-1/2 transform -translate-y-1/2 text-app-text-muted" />
                                    <input
                                        type="text"
                                        placeholder="Search by name or email..."
                                        value={searchTerm}
                                        onChange={(e) => setSearchTerm(e.target.value)}
                                        className="pl-9 pr-3.5 py-1.5 bg-app-bg-muted border border-app-border hover:border-slate-400 dark:hover:border-slate-500 focus:border-indigo-500 text-xs text-app-text-main rounded-lg focus:outline-none transition-all w-[220px] shadow-xs"
                                    />
                                </div>
                            </div>

                            <div className="overflow-x-auto rounded-xl border border-app-border/80 shadow-2xs">
                                <table className="w-full text-left border-collapse text-xs">
                                    <thead>
                                        <tr className="border-b border-app-border bg-slate-50/80 dark:bg-slate-800/60 text-app-text-muted uppercase font-bold tracking-wider text-[10px] select-none">
                                            <th className="py-3 px-4 font-bold text-left align-middle cursor-pointer hover:text-app-text-main transition-colors" onClick={() => handleUserSort('name')}>
                                                <div className="inline-flex items-center gap-1">
                                                    <span>Name</span>
                                                    <span className="text-[10px] text-slate-400">{userSortField === 'name' ? (userSortAsc ? '↑' : '↓') : '↕'}</span>
                                                </div>
                                            </th>
                                            <th className="py-3 px-4 font-bold text-left align-middle cursor-pointer hover:text-app-text-main transition-colors" onClick={() => handleUserSort('email')}>
                                                <div className="inline-flex items-center gap-1">
                                                    <span>Email</span>
                                                    <span className="text-[10px] text-slate-400">{userSortField === 'email' ? (userSortAsc ? '↑' : '↓') : '↕'}</span>
                                                </div>
                                            </th>
                                            <th className="py-3 px-3.5 font-bold text-center align-middle">
                                                Status
                                            </th>
                                            <th className="py-3 px-3.5 font-bold text-center align-middle cursor-pointer hover:text-app-text-main transition-colors" onClick={() => handleUserSort('last_login')}>
                                                <div className="flex items-center justify-center gap-1">
                                                    <span>Last Login</span>
                                                    <span className="text-[10px] text-slate-400">{userSortField === 'last_login' ? (userSortAsc ? '↑' : '↓') : '↕'}</span>
                                                </div>
                                            </th>
                                            <th className="py-3 px-3 font-bold text-center align-middle cursor-pointer hover:text-app-text-main transition-colors" onClick={() => handleUserSort('projects_count')}>
                                                <div className="flex items-center justify-center gap-1">
                                                    <span>Projects</span>
                                                    <span className="text-[10px] text-slate-400">{userSortField === 'projects_count' ? (userSortAsc ? '↑' : '↓') : '↕'}</span>
                                                </div>
                                            </th>
                                            <th className="py-3 px-3 font-bold text-center align-middle cursor-pointer hover:text-app-text-main transition-colors" onClick={() => handleUserSort('session_count')}>
                                                <div className="flex items-center justify-center gap-1">
                                                    <span>Sessions</span>
                                                    <span className="text-[10px] text-slate-400">{userSortField === 'session_count' ? (userSortAsc ? '↑' : '↓') : '↕'}</span>
                                                </div>
                                            </th>
                                            <th className="py-3 px-3.5 font-bold text-center align-middle cursor-pointer hover:text-app-text-main transition-colors" onClick={() => handleUserSort('total_duration_hours')}>
                                                <div className="flex items-center justify-center gap-1">
                                                    <span>Session Time</span>
                                                    <span className="text-[10px] text-slate-400">{userSortField === 'total_duration_hours' ? (userSortAsc ? '↑' : '↓') : '↕'}</span>
                                                </div>
                                            </th>
                                            <th className="py-3 px-3.5 font-bold text-center align-middle cursor-pointer hover:text-app-text-main transition-colors" onClick={() => handleUserSort('ai_tokens')}>
                                                <div className="flex items-center justify-center gap-1">
                                                    <span>AI Tokens</span>
                                                    <span className="text-[10px] text-slate-400">{userSortField === 'ai_tokens' ? (userSortAsc ? '↑' : '↓') : '↕'}</span>
                                                </div>
                                            </th>
                                            <th className="py-3 px-3.5 font-bold text-center align-middle cursor-pointer hover:text-app-text-main transition-colors" onClick={() => handleUserSort('token_cost')}>
                                                <div className="flex items-center justify-center gap-1">
                                                    <span>Token Cost</span>
                                                    <span className="text-[10px] text-slate-400">{userSortField === 'token_cost' ? (userSortAsc ? '↑' : '↓') : '↕'}</span>
                                                </div>
                                            </th>
                                            <th className="py-3 px-3.5 font-bold text-center align-middle cursor-pointer hover:text-app-text-main transition-colors" onClick={() => handleUserSort('infra_cost')}>
                                                <div className="flex items-center justify-center gap-1">
                                                    <span>Infra Cost</span>
                                                    <span className="text-[10px] text-slate-400">{userSortField === 'infra_cost' ? (userSortAsc ? '↑' : '↓') : '↕'}</span>
                                                </div>
                                            </th>
                                            <th className="py-3 px-3.5 font-bold text-center align-middle cursor-pointer hover:text-app-text-main transition-colors" onClick={() => handleUserSort('total_cost')}>
                                                <div className="flex items-center justify-center gap-1">
                                                    <span>Total Cost</span>
                                                    <span className="text-[10px] text-slate-400">{userSortField === 'total_cost' ? (userSortAsc ? '↑' : '↓') : '↕'}</span>
                                                </div>
                                            </th>
                                        </tr>
                                    </thead>
                                    <tbody className="divide-y divide-app-border bg-app-bg-card text-app-text-main">
                                        {processedUsers.length === 0 ? (
                                            <tr>
                                                <td colSpan="11" className="py-8 px-4 text-center text-app-text-muted font-semibold align-middle">
                                                    No organization members found matching your search.
                                                </td>
                                            </tr>
                                        ) : (
                                            processedUsers.map((u) => (
                                                <tr 
                                                    key={u.id} 
                                                    onClick={() => setSelectedUserDetail(u)}
                                                    className="hover:bg-slate-50/80 dark:hover:bg-slate-800/40 transition-colors cursor-pointer"
                                                >
                                                    <td className="py-3.5 px-4 font-bold text-left align-middle">
                                                        <div className="flex items-center gap-2">
                                                            <div className="w-7 h-7 rounded-full bg-slate-100 dark:bg-slate-800 flex items-center justify-center text-slate-500 shrink-0">
                                                                <User className="w-3.5 h-3.5" />
                                                            </div>
                                                            <span className="truncate max-w-[160px]">{u.name}</span>
                                                        </div>
                                                    </td>
                                                    <td className="py-3.5 px-4 text-left align-middle font-mono text-[11px] text-app-text-muted">
                                                        {u.email}
                                                    </td>
                                                    <td className="py-3.5 px-3.5 text-center align-middle">
                                                        <div className="flex items-center justify-center">
                                                            {u.is_active ? (
                                                                <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-50 dark:bg-emerald-950/40 text-emerald-700 dark:text-emerald-400 border border-emerald-200/60 dark:border-emerald-800/60 inline-flex items-center gap-1">
                                                                    <span className="w-1.5 h-1.5 bg-emerald-500 rounded-full" /> Active
                                                                </span>
                                                            ) : (
                                                                <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-slate-100 dark:bg-slate-800 text-slate-500 border border-slate-200 dark:border-slate-700 inline-flex items-center gap-1">
                                                                    <span className="w-1.5 h-1.5 bg-slate-400 rounded-full" /> Inactive
                                                                </span>
                                                            )}
                                                        </div>
                                                    </td>
                                                    <td className="py-3.5 px-3.5 text-center align-middle text-[11px] text-app-text-muted whitespace-nowrap font-medium">
                                                        {u.last_login ? new Date(u.last_login).toLocaleString() : 'Never'}
                                                    </td>
                                                    <td className="py-3.5 px-3 text-center align-middle font-mono font-bold text-app-text-main">
                                                        {u.projects_count}
                                                    </td>
                                                    <td className="py-3.5 px-3 text-center align-middle font-mono font-bold text-app-text-main">
                                                        {u.session_count}
                                                    </td>
                                                    <td className="py-3.5 px-3.5 text-center align-middle font-mono font-bold text-app-text-main whitespace-nowrap">
                                                        {u.total_duration_hours} <span className="text-[10px] text-app-text-muted font-normal">hrs</span>
                                                    </td>
                                                    <td className="py-3.5 px-3.5 text-center align-middle font-mono font-semibold text-app-text-main">
                                                        {u.ai_tokens ? u.ai_tokens.toLocaleString() : '0'}
                                                    </td>
                                                    <td className="py-3.5 px-3.5 text-center align-middle font-mono font-semibold text-blue-600 dark:text-blue-400">
                                                        ${(u.token_cost || 0).toLocaleString(undefined, { minimumFractionDigits: 4, maximumFractionDigits: 4 })}
                                                    </td>
                                                    <td className="py-3.5 px-3.5 text-center align-middle font-mono font-semibold text-purple-600 dark:text-purple-400">
                                                        ${(u.infra_cost || 0).toLocaleString(undefined, { minimumFractionDigits: 4, maximumFractionDigits: 4 })}
                                                    </td>
                                                    <td className="py-3.5 px-3.5 text-center align-middle font-mono font-bold text-emerald-600 dark:text-emerald-450">
                                                        ${(u.total_cost || 0).toLocaleString(undefined, { minimumFractionDigits: 4, maximumFractionDigits: 4 })}
                                                    </td>
                                                </tr>
                                            ))
                                        )}
                                    </tbody>
                                </table>
                            </div>
                        </div>
                    )}

                    {/* PROJECTS HUB TAB */}
                    {activeTab === 'projects' && (
                        <div className="bg-app-bg-card border border-app-border rounded-xl p-5 sm:p-6 shadow-xs animate-fade-in space-y-4">
                            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                                <div className="flex items-center gap-2">
                                    <h3 className="text-base font-bold text-app-text-main flex items-center gap-2">
                                        <Globe className="w-4 h-4 text-indigo-500" /> Projects Hub
                                    </h3>
                                    <span className="text-[11px] font-semibold text-app-text-muted bg-app-bg-muted px-2.5 py-0.5 rounded-full border border-app-border">
                                        {processedProjects.length} {processedProjects.length === 1 ? 'Project' : 'Projects'}
                                    </span>
                                </div>
                                <div className="relative no-print">
                                    <Search className="w-3.5 h-3.5 absolute left-3 top-1/2 transform -translate-y-1/2 text-app-text-muted" />
                                    <input
                                        type="text"
                                        placeholder="Search projects..."
                                        value={searchTerm}
                                        onChange={(e) => setSearchTerm(e.target.value)}
                                        className="pl-9 pr-3.5 py-1.5 bg-app-bg-muted border border-app-border hover:border-slate-400 dark:hover:border-slate-500 focus:border-indigo-500 text-xs text-app-text-main rounded-lg focus:outline-none transition-all w-[220px] shadow-xs"
                                    />
                                </div>
                            </div>

                            <div className="overflow-x-auto rounded-xl border border-app-border/80 shadow-2xs">
                                <table className="w-full text-left border-collapse text-xs">
                                    <thead>
                                        <tr className="border-b border-app-border bg-slate-50/80 dark:bg-slate-800/60 text-app-text-muted uppercase font-bold tracking-wider text-[10px]">
                                            <th className="py-3 px-4 font-bold text-left align-middle">Project Name</th>
                                            <th className="py-3 px-4 font-bold text-left align-middle">Project Token</th>
                                            <th className="py-3 px-4 font-bold text-left align-middle">Owner Email</th>
                                            <th className="py-3 px-4 font-bold text-center align-middle">Classification</th>
                                            <th className="py-3 px-4 font-bold text-center align-middle">Runs</th>
                                            <th className="py-3 px-4 font-bold text-center align-middle">Status</th>
                                            <th className="py-3 px-4 font-bold text-center align-middle">Created At</th>
                                        </tr>
                                    </thead>
                                    <tbody className="divide-y divide-app-border bg-app-bg-card text-app-text-main">
                                        {processedProjects.length === 0 ? (
                                            <tr>
                                                <td colSpan="7" className="py-8 px-4 text-center text-app-text-muted font-semibold align-middle">
                                                    No projects found in organization.
                                                </td>
                                            </tr>
                                        ) : (
                                            processedProjects.map((p) => (
                                                <tr key={p.project_token} className="hover:bg-slate-50/80 dark:hover:bg-slate-800/40 transition-colors">
                                                    <td className="py-3.5 px-4 font-bold text-left align-middle text-app-text-main">
                                                        <div className="flex items-center gap-2">
                                                            <div className="w-7 h-7 rounded-lg bg-indigo-50 dark:bg-indigo-950/40 text-indigo-600 dark:text-indigo-400 flex items-center justify-center shrink-0">
                                                                <Globe className="w-3.5 h-3.5" />
                                                            </div>
                                                            <span className="truncate max-w-[200px]">{p.project_name}</span>
                                                        </div>
                                                    </td>
                                                    <td className="py-3.5 px-4 text-left align-middle">
                                                        <span className="px-2 py-0.5 rounded-md bg-app-bg-muted/80 border border-app-border/80 font-mono text-[11px] text-app-text-muted">
                                                            {p.project_token}
                                                        </span>
                                                    </td>
                                                    <td className="py-3.5 px-4 text-left align-middle text-app-text-label font-mono text-[11px]">
                                                        {p.owner_email}
                                                    </td>
                                                    <td className="py-3.5 px-4 text-center align-middle">
                                                        <span className="px-2.5 py-0.5 rounded-full text-[10px] font-bold bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300 border border-slate-200/80 dark:border-slate-700/80 uppercase tracking-wider">
                                                            {p.classification}
                                                        </span>
                                                    </td>
                                                    <td className="py-3.5 px-4 text-center align-middle font-mono font-bold text-app-text-main">
                                                        {p.total_runs}
                                                    </td>
                                                    <td className="py-3.5 px-4 text-center align-middle">
                                                        <div className="flex items-center justify-center">
                                                            <span className={`px-2.5 py-0.5 rounded-full text-[10px] font-bold inline-flex items-center gap-1 ${
                                                                p.run_status === 'success' ? 'bg-emerald-50 dark:bg-emerald-950/40 text-emerald-700 dark:text-emerald-350 border border-emerald-200/50' :
                                                                p.run_status === 'failed' ? 'bg-rose-50 dark:bg-rose-950/40 text-rose-700 dark:text-rose-400 border border-rose-200/50' :
                                                                'bg-amber-50 dark:bg-amber-950/40 text-amber-700 dark:text-amber-400 border border-amber-200/50'
                                                            }`}>
                                                                <span className={`w-1.5 h-1.5 rounded-full ${
                                                                    p.run_status === 'success' ? 'bg-emerald-500' :
                                                                    p.run_status === 'failed' ? 'bg-rose-500' :
                                                                    'bg-amber-500'
                                                                }`} />
                                                                {p.run_status}
                                                            </span>
                                                        </div>
                                                    </td>
                                                    <td className="py-3.5 px-4 text-center align-middle text-app-text-muted text-[11px] font-medium whitespace-nowrap">
                                                        {p.submission_date ? new Date(p.submission_date).toLocaleDateString() : '—'}
                                                    </td>
                                                </tr>
                                            ))
                                        )}
                                    </tbody>
                                </table>
                            </div>
                        </div>
                    )}

                    {/* TOKENOPS QUOTA MANAGEMENT TAB */}
                    {activeTab === 'tokenops' && (
                        <div className="animate-fade-in">
                            <OrgTokenOpsPanel user={user} />
                        </div>
                    )}
                </div>

                {/* ── DRILLDOWN MODAL ── */}
                {selectedUserDetail && (
                    <div 
                        className="fixed inset-0 bg-slate-900/60 dark:bg-black/70 backdrop-blur-sm flex items-center justify-center p-4 z-[9999]"
                        onClick={() => setSelectedUserDetail(null)}
                    >
                        <div 
                            className="bg-app-bg-card border border-app-border rounded-2xl w-full max-w-3xl overflow-hidden shadow-2xl animate-scale-up"
                            onClick={(e) => e.stopPropagation()}
                        >
                            {/* Modal Header */}
                            <div className="flex justify-between items-center px-6 py-4 border-b border-app-border bg-app-bg-muted/50">
                                <div>
                                    <h2 className="text-lg font-bold text-app-text-main">
                                        User Engagement Detail
                                    </h2>
                                    <p className="text-[11px] text-app-text-muted font-mono mt-0.5">
                                        {selectedUserDetail.name} • {selectedUserDetail.email}
                                    </p>
                                </div>
                                <button 
                                    className="p-1.5 rounded-lg hover:bg-app-bg-hover text-app-text-label hover:text-app-text-main transition-colors"
                                    onClick={() => setSelectedUserDetail(null)}
                                >
                                    ✕
                                </button>
                            </div>

                            {/* Modal Body */}
                            <div className="p-6 overflow-y-auto max-h-[75vh] space-y-6 custom-scrollbar text-xs">
                                {/* Roles & Integrations Row */}
                                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                    <div className="p-4 rounded-xl border border-app-border bg-app-bg-muted/30">
                                        <div className="font-bold text-app-text-muted mb-2 uppercase tracking-wider text-[10px]">App Roles & Org</div>
                                        <div className="flex items-center gap-2">
                                            <ShieldCheck className="w-4 h-4 text-app-primary" />
                                            <div>
                                                <span className="font-bold text-app-text-main">
                                                    {selectedUserDetail.is_org_admin ? 'Organization Admin' : 'Member'}
                                                </span>
                                                <span className="block text-[10px] text-app-text-muted font-semibold">{organization_name}</span>
                                            </div>
                                        </div>
                                    </div>
                                    <div className="p-4 rounded-xl border border-app-border bg-app-bg-muted/30">
                                        <div className="font-bold text-app-text-muted mb-2 uppercase tracking-wider text-[10px]">Connected Integrations</div>
                                        <div className="space-y-1.5 font-semibold text-app-text-label">
                                            <div className="flex justify-between">
                                                <span>GitHub Username:</span>
                                                <span className="font-mono text-app-text-main font-bold">{selectedUserDetail.github_username}</span>
                                            </div>
                                            <div className="flex justify-between">
                                                <span>Azure DevOps Username:</span>
                                                <span className="font-mono text-app-text-main font-bold">{selectedUserDetail.azure_devops_username}</span>
                                            </div>
                                        </div>
                                    </div>
                                </div>

                                {/* User Cost Breakdown Cards */}
                                <div className="grid grid-cols-3 gap-3">
                                    <div className="p-3 rounded-xl border border-app-border bg-blue-50/50 dark:bg-blue-950/20">
                                        <div className="text-[10px] font-bold text-blue-600 dark:text-blue-400 uppercase tracking-wider">Token Cost</div>
                                        <div className="text-base font-black text-blue-700 dark:text-blue-300 mt-0.5">
                                            ${(selectedUserDetail.token_cost ?? 0).toFixed(4)}
                                        </div>
                                    </div>
                                    <div className="p-3 rounded-xl border border-app-border bg-purple-50/50 dark:bg-purple-950/20">
                                        <div className="text-[10px] font-bold text-purple-600 dark:text-purple-400 uppercase tracking-wider">Infra Cost ($0.70/hr)</div>
                                        <div className="text-base font-black text-purple-700 dark:text-purple-300 mt-0.5">
                                            ${(selectedUserDetail.infra_cost ?? 0).toFixed(4)}
                                        </div>
                                    </div>
                                    <div className="p-3 rounded-xl border border-app-border bg-emerald-50/50 dark:bg-emerald-950/20">
                                        <div className="text-[10px] font-bold text-emerald-600 dark:text-emerald-400 uppercase tracking-wider">Total User Cost</div>
                                        <div className="text-base font-black text-emerald-700 dark:text-emerald-300 mt-0.5">
                                            ${(selectedUserDetail.total_cost ?? 0).toFixed(4)}
                                        </div>
                                    </div>
                                </div>

                                {/* AI Token Breakdown Table */}
                                <div className="p-4 rounded-xl border border-app-border bg-app-bg-card">
                                    <div className="font-bold text-app-text-muted mb-3 uppercase tracking-wider text-[10px]">AI Token Usage & Cost Breakdown</div>
                                    <div className="overflow-x-auto rounded-lg border border-app-border">
                                        <table className="w-full text-left border-collapse">
                                            <thead>
                                                <tr className="bg-app-bg-muted border-b border-app-border text-[10px] font-bold text-app-text-label uppercase tracking-wider">
                                                    <th className="py-2.5 px-3">Model</th>
                                                    <th className="py-2.5 px-3 text-right">Requests</th>
                                                    <th className="py-2.5 px-3 text-right">Prompt Tokens</th>
                                                    <th className="py-2.5 px-3 text-right">Completion Tokens</th>
                                                    <th className="py-2.5 px-3 text-right">Total Tokens</th>
                                                    <th className="py-2.5 px-3 text-right">Cost (USD)</th>
                                                </tr>
                                            </thead>
                                            <tbody className="divide-y divide-app-border font-mono text-app-text-main">
                                                {selectedUserDetail.ai_usage?.length === 0 ? (
                                                    <tr>
                                                        <td colSpan="6" className="py-4 text-center font-sans text-app-text-muted">
                                                            No AI usage logs recorded for this user.
                                                        </td>
                                                    </tr>
                                                ) : (
                                                    selectedUserDetail.ai_usage?.map(uai => (
                                                        <tr key={uai.model} className="hover:bg-app-bg-hover">
                                                            <td className="py-2.5 px-3 font-sans font-bold text-app-text-main">{uai.model}</td>
                                                            <td className="py-2.5 px-3 text-right font-bold">{uai.requests}</td>
                                                            <td className="py-2.5 px-3 text-right text-app-text-muted">{uai.prompt.toLocaleString()}</td>
                                                            <td className="py-2.5 px-3 text-right text-app-text-muted">{uai.completion.toLocaleString()}</td>
                                                            <td className="py-2.5 px-3 text-right font-bold text-app-text-label">{(uai.prompt + uai.completion).toLocaleString()}</td>
                                                            <td className="py-2.5 px-3 text-right font-bold text-emerald-600 dark:text-emerald-450">${uai.cost.toFixed(4)}</td>
                                                        </tr>
                                                    ))
                                                )}
                                            </tbody>
                                        </table>
                                    </div>
                                </div>

                                {/* Permissions Paths */}
                                <div className="p-4 rounded-xl border border-app-border bg-app-bg-muted/30">
                                    <div className="font-bold text-app-text-muted mb-2 uppercase tracking-wider text-[10px]">Permissions Paths</div>
                                    <div className="flex flex-wrap gap-1.5 max-h-[120px] overflow-y-auto">
                                        {selectedUserDetail.permissions?.length === 0 ? (
                                            <span className="text-app-text-muted font-semibold italic">None (No organization roles mapped)</span>
                                        ) : (
                                            selectedUserDetail.permissions?.map(p => (
                                                <span key={p} className="px-2 py-0.5 rounded font-mono font-bold bg-app-bg-card border border-app-border text-app-text-label">
                                                    {p}
                                                </span>
                                            ))
                                        )}
                                    </div>
                                </div>

                                {/* Projects Created */}
                                <div className="p-4 rounded-xl border border-app-border bg-app-bg-card">
                                    <div className="font-bold text-app-text-muted mb-3 uppercase tracking-wider text-[10px]">Projects Created By User</div>
                                    <div className="overflow-x-auto rounded-lg border border-app-border">
                                        <table className="w-full text-left border-collapse">
                                            <thead>
                                                <tr className="bg-app-bg-muted border-b border-app-border text-[10px] font-bold text-app-text-label uppercase tracking-wider">
                                                    <th className="py-2.5 px-3">Project Name</th>
                                                    <th className="py-2.5 px-3">Classification</th>
                                                    <th className="py-2.5 px-3 text-center">Last Build Status</th>
                                                </tr>
                                            </thead>
                                            <tbody className="divide-y divide-app-border text-app-text-main">
                                                {selectedUserDetail.projects?.length === 0 ? (
                                                    <tr>
                                                        <td colSpan="3" className="py-4 text-center text-app-text-muted">
                                                            No projects created by this user yet.
                                                        </td>
                                                    </tr>
                                                ) : (
                                                    selectedUserDetail.projects?.map(p => (
                                                        <tr key={p.project_name} className="hover:bg-app-bg-hover">
                                                            <td className="py-2.5 px-3 font-bold text-app-text-main">{p.project_name}</td>
                                                            <td className="py-2.5 px-3 font-semibold text-app-text-label">{p.classification}</td>
                                                            <td className="py-2.5 px-3 text-center">
                                                                <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                                                                    p.status === 'success' ? 'bg-emerald-50 dark:bg-app-status-successBg text-emerald-700 dark:text-emerald-350 border border-emerald-250/20' :
                                                                    p.status === 'failed' ? 'bg-rose-50 dark:bg-app-status-errorBg text-rose-700 dark:text-rose-400 border border-rose-250/20' :
                                                                    'bg-amber-50 dark:bg-app-status-warningBg text-amber-700 dark:text-amber-450 border border-amber-250/20'
                                                                }`}>
                                                                    {p.status}
                                                                </span>
                                                            </td>
                                                        </tr>
                                                    ))
                                                )}
                                            </tbody>
                                        </table>
                                    </div>
                                </div>

                                {/* Recent Activity / Session Logs */}
                                <div className="p-4 rounded-xl border border-app-border bg-app-bg-card">
                                    <div className="font-bold text-app-text-muted mb-3 uppercase tracking-wider text-[10px]">Recent Session / Activity Logs</div>
                                    <div className="overflow-x-auto rounded-lg border border-app-border">
                                        <table className="w-full text-left border-collapse">
                                            <thead>
                                                <tr className="bg-app-bg-muted border-b border-app-border text-[10px] font-bold text-app-text-label uppercase tracking-wider">
                                                    <th className="py-2.5 px-3">Date / Time</th>
                                                    <th className="py-2.5 px-3">Action</th>
                                                    <th className="py-2.5 px-3">Path</th>
                                                    <th className="py-2.5 px-3">IP Address</th>
                                                    <th className="py-2.5 px-3">User Agent</th>
                                                </tr>
                                            </thead>
                                            <tbody className="divide-y divide-app-border font-mono text-[11px] text-app-text-main">
                                                {selectedUserDetail.recent_sessions?.length === 0 ? (
                                                    <tr>
                                                        <td colSpan="5" className="py-4 text-center font-sans text-app-text-muted">
                                                            No operational logs recorded for this user.
                                                        </td>
                                                    </tr>
                                                ) : (
                                                    selectedUserDetail.recent_sessions?.map(act => (
                                                        <tr key={act.created_at + act.path} className="hover:bg-app-bg-hover">
                                                            <td className="py-2.5 px-3 text-app-text-muted font-sans">{new Date(act.created_at).toLocaleString()}</td>
                                                            <td className="py-2.5 px-3 font-bold text-app-text-main">{act.action}</td>
                                                            <td className="py-2.5 px-3 text-app-text-muted max-w-[120px] truncate" title={act.path}>{act.path}</td>
                                                            <td className="py-2.5 px-3 text-app-text-label">{act.ip_address}</td>
                                                            <td className="py-2.5 px-3 text-app-text-muted truncate max-w-[150px]" title={act.user_agent}>{act.user_agent}</td>
                                                        </tr>
                                                    ))
                                                )}
                                            </tbody>
                                        </table>
                                    </div>
                                </div>
                            </div>

                            {/* Modal Footer */}
                            <div className="flex justify-end gap-3 px-6 py-4 border-t border-app-border bg-app-bg-muted/50">
                                <button 
                                    className="px-4 py-2 border border-app-border hover:bg-app-bg-hover rounded-lg text-app-text-label font-semibold"
                                    onClick={() => setSelectedUserDetail(null)}
                                >
                                    Close Detail Profile
                                </button>
                            </div>
                        </div>
                    </div>
                )}
            </div>
        );
    }

    // ── RENDER 2: Standard User Agent Billing Dashboard ──
    const { summary, agent_breakdown = [] } = billingData || {};

    return (
        <div className="flex-1 overflow-y-auto h-full bg-app-bg-page custom-scrollbar">
            <div className="max-w-7xl mx-auto px-4 sm:px-6 py-6 space-y-6">
                {/* Header */}
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-5 border-b border-app-border/80">
                    <div className="space-y-1">
                        <div className="flex items-center gap-2.5 flex-wrap">
                            <h1 className="text-2xl sm:text-3xl font-bold tracking-tight text-app-text-main">
                                Execution Billing Dashboard
                            </h1>
                            <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 text-xs font-semibold rounded-full bg-blue-50 dark:bg-blue-950/50 text-blue-700 dark:text-blue-400 border border-blue-200/60 dark:border-blue-800/60 shadow-xs">
                                <Sparkles className="w-3.5 h-3.5" /> Agent Metrics
                            </span>
                        </div>
                        <p className="text-xs sm:text-sm text-app-text-muted">
                            Real-time tracking of tasks completed, resource time logs, and computed cost share per agent.
                        </p>
                    </div>
                    <button
                        onClick={() => fetchBillingData(true)}
                        disabled={refreshing}
                        className="h-9 px-3.5 bg-app-bg-card hover:bg-app-bg-hover text-app-text-main border border-app-border rounded-lg text-xs font-semibold inline-flex items-center gap-2 disabled:opacity-50 shadow-xs transition-colors self-start sm:self-auto cursor-pointer"
                        title="Sync Log"
                    >
                        <RefreshCw className={`w-3.5 h-3.5 text-app-text-muted ${refreshing ? 'animate-spin' : ''}`} />
                        {refreshing ? 'Syncing...' : 'Sync Log'}
                    </button>
                </div>

                {/* Project Context Info */}
                {activeProject && (
                    <div className="p-3.5 rounded-xl bg-blue-50/50 dark:bg-app-primary-light/10 border border-blue-100 dark:border-app-border flex items-center justify-between shadow-xs">
                        <div className="flex items-center gap-2">
                            <Zap className="w-4 h-4 text-blue-600 dark:text-app-primary-dark" />
                            <span className="text-xs text-app-text-label">
                                Active Project: <strong className="text-app-text-main font-bold">{activeProject.name || selectedProjectKey}</strong>
                            </span>
                        </div>
                        <span className="text-[10px] bg-emerald-50 text-emerald-700 dark:bg-app-status-successBg dark:text-emerald-350 border border-emerald-200/50 px-2 py-0.5 rounded font-mono font-semibold uppercase tracking-wider">
                            Live Tracking
                        </span>
                    </div>
                )}

                {/* Metrics Overview Cards */}
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
                    {/* Total Cost Card */}
                    <div className="bg-app-bg-card border border-app-border hover:border-slate-300 dark:hover:border-slate-600 rounded-xl p-4 sm:p-5 transition-all shadow-xs hover:shadow-md flex flex-col justify-between">
                        <div className="flex items-center justify-between gap-2">
                            <span className="text-[11px] font-semibold text-app-text-muted uppercase tracking-wider">Total Costs</span>
                            <div className="w-8 h-8 rounded-lg bg-emerald-50 dark:bg-emerald-950/40 text-emerald-600 dark:text-emerald-400 flex items-center justify-center shrink-0">
                                <DollarSign className="w-4 h-4" />
                            </div>
                        </div>
                        <div className="mt-3">
                            <div className="text-2xl font-bold tracking-tight text-app-text-main">
                                ${summary?.total_amount_due?.toLocaleString(undefined, { minimumFractionDigits: 2 })}
                            </div>
                            <p className="text-[11px] text-emerald-600 dark:text-emerald-400 mt-1 flex items-center gap-1 font-medium">
                                <CheckCircle2 className="w-3 h-3 shrink-0" /> Fully verified executions
                            </p>
                        </div>
                    </div>

                    {/* Billable Hours */}
                    <div className="bg-app-bg-card border border-app-border hover:border-slate-300 dark:hover:border-slate-600 rounded-xl p-4 sm:p-5 transition-all shadow-xs hover:shadow-md flex flex-col justify-between">
                        <div className="flex items-center justify-between gap-2">
                            <span className="text-[11px] font-semibold text-app-text-muted uppercase tracking-wider">Billable Time</span>
                            <div className="w-8 h-8 rounded-lg bg-blue-50 dark:bg-blue-950/40 text-blue-600 dark:text-blue-400 flex items-center justify-center shrink-0">
                                <Clock className="w-4 h-4" />
                            </div>
                        </div>
                        <div className="mt-3">
                            <div className="text-2xl font-bold tracking-tight text-app-text-main">
                                {summary?.total_hours_billed} <span className="text-xs text-app-text-muted font-normal">hrs</span>
                            </div>
                            <p className="text-[11px] text-app-text-muted mt-1 font-medium">
                                Cumulated time spent
                            </p>
                        </div>
                    </div>

                    {/* Tasks Completed */}
                    <div className="bg-app-bg-card border border-app-border hover:border-slate-300 dark:hover:border-slate-600 rounded-xl p-4 sm:p-5 transition-all shadow-xs hover:shadow-md flex flex-col justify-between">
                        <div className="flex items-center justify-between gap-2">
                            <span className="text-[11px] font-semibold text-app-text-muted uppercase tracking-wider">Tasks Completed</span>
                            <div className="w-8 h-8 rounded-lg bg-indigo-50 dark:bg-indigo-950/40 text-indigo-600 dark:text-indigo-400 flex items-center justify-center shrink-0">
                                <CheckCircle2 className="w-4 h-4" />
                            </div>
                        </div>
                        <div className="mt-3">
                            <div className="text-2xl font-bold tracking-tight text-app-text-main">
                                {summary?.total_tasks_completed}
                            </div>
                            <p className="text-[11px] text-app-text-muted mt-1 font-medium">
                                Completed agent threads
                            </p>
                        </div>
                    </div>

                    {/* Unique Agents */}
                    <div className="bg-app-bg-card border border-app-border hover:border-slate-300 dark:hover:border-slate-600 rounded-xl p-4 sm:p-5 transition-all shadow-xs hover:shadow-md flex flex-col justify-between">
                        <div className="flex items-center justify-between gap-2">
                            <span className="text-[11px] font-semibold text-app-text-muted uppercase tracking-wider">Agents Used</span>
                            <div className="w-8 h-8 rounded-lg bg-purple-50 dark:bg-purple-950/40 text-purple-600 dark:text-purple-400 flex items-center justify-center shrink-0">
                                <Bot className="w-4 h-4" />
                            </div>
                        </div>
                        <div className="mt-3">
                            <div className="text-2xl font-bold tracking-tight text-app-text-main">
                                {agent_breakdown.length}
                            </div>
                            <p className="text-[11px] text-app-text-muted mt-1 font-medium">
                                Includes sub & master agents
                            </p>
                        </div>
                    </div>
                </div>

                {/* Agent-wise Fleet Utilization Breakdown */}
                <div className="mb-8">
                    <h3 className="text-base font-bold text-app-text-main mb-4 flex items-center gap-2">
                        <Cpu className="w-4 h-4 text-app-primary" /> Agent Fleet Resource Utilization
                    </h3>
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                        {agent_breakdown.map((agent) => {
                            const costPercentage = summary?.total_amount_due > 0 
                                ? Math.round((agent.total_cost / summary.total_amount_due) * 100)
                                : 0;

                            return (
                                <div 
                                    key={agent.agent_name}
                                    className="bg-app-bg-card border border-app-border rounded-xl p-5 transition-all flex flex-col justify-between shadow-sm"
                                >
                                    <div className="mb-4">
                                        <div className="flex items-center justify-between mb-2">
                                            <div className="flex items-center gap-2">
                                                <div className={`p-1.5 rounded-lg border ${
                                                    agent.agent_type === 'Master Agent' 
                                                        ? 'bg-blue-50 dark:bg-app-primary-light text-blue-600 dark:text-app-primary-dark border-blue-100 dark:border-app-border'
                                                        : 'bg-app-bg-muted text-app-text-label border-app-border'
                                                }`}>
                                                    <Bot className="w-4 h-4" />
                                                </div>
                                                <div>
                                                    <h4 className="text-sm font-bold text-app-text-main">{agent.agent_name}</h4>
                                                    <span className="text-[10px] text-app-text-muted font-semibold uppercase">{agent.agent_type}</span>
                                                </div>
                                            </div>
                                            <span className="text-xs font-mono font-bold text-emerald-600 dark:text-emerald-450">
                                                ${agent.rate_per_hour}/hr
                                            </span>
                                        </div>
                                        <p className="text-xs text-app-text-label mb-4 leading-relaxed font-semibold">
                                            Completed <strong className="text-app-text-main font-bold">{agent.tasks_completed}</strong> tasks in <strong className="text-app-text-main font-bold">{agent.total_hours}</strong> billable hours.
                                        </p>
                                    </div>

                                    <div>
                                        <div className="flex justify-between items-baseline mb-1">
                                            <span className="text-xs text-app-text-muted font-semibold">Total cost share</span>
                                            <span className="text-sm font-black text-app-text-main">${agent.total_cost.toLocaleString()}</span>
                                        </div>
                                        <div className="w-full bg-app-bg-muted rounded-full h-1.5 overflow-hidden">
                                            <div 
                                                className={`h-full rounded-full transition-all duration-500 ${
                                                    agent.agent_type === 'Master Agent'
                                                        ? 'bg-gradient-to-r from-blue-600 to-indigo-650'
                                                        : 'bg-gradient-to-r from-blue-400 to-indigo-400'
                                                }`}
                                                style={{ width: `${costPercentage}%` }}
                                            />
                                        </div>
                                        <div className="flex justify-between text-[10px] text-app-text-muted mt-1 font-semibold">
                                            <span>Share</span>
                                            <span>{costPercentage}%</span>
                                        </div>
                                    </div>
                                </div>
                            );
                        })}
                    </div>
                </div>

                {/* Billable Activity Log (Completed Tasks List) */}
                <div className="bg-app-bg-card border border-app-border rounded-xl p-6 mb-8 shadow-sm">
                    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-6">
                        <h3 className="text-base font-bold text-app-text-main flex items-center gap-2">
                            <CreditCard className="w-4 h-4 text-app-primary" /> Billable Activity Log
                        </h3>
                        
                        {/* Filters */}
                        <div className="flex flex-wrap items-center gap-3">
                            {/* Search */}
                            <div className="relative">
                                <Search className="w-3.5 h-3.5 absolute left-3 top-1/2 transform -translate-y-1/2 text-app-text-light" />
                                <input
                                    type="text"
                                    placeholder="Search by ID or name..."
                                    value={searchTerm}
                                    onChange={(e) => setSearchTerm(e.target.value)}
                                    className="pl-9 pr-4 py-1.5 bg-app-bg-muted border border-app-border hover:border-app-border-active focus:border-app-primary text-xs text-app-text-main rounded-lg focus:outline-none transition-all w-[180px] sm:w-[220px] shadow-inner"
                                />
                            </div>

                            {/* Agent dropdown */}
                            <div className="relative flex items-center bg-app-bg-muted border border-app-border hover:border-app-border-active rounded-lg px-3 py-1.5 transition-all shadow-inner">
                                <Filter className="w-3.5 h-3.5 text-app-text-light mr-2" />
                                <select
                                    value={agentFilter}
                                    onChange={(e) => setAgentFilter(e.target.value)}
                                    className="bg-transparent text-xs text-app-text-main focus:outline-none cursor-pointer pr-1"
                                >
                                    <option value="all" className="bg-app-bg-card text-app-text-main">All Agents</option>
                                    {uniqueAgentNames.map(name => (
                                        <option key={name} value={name} className="bg-app-bg-card text-app-text-main">{name}</option>
                                    ))}
                                </select>
                            </div>
                        </div>
                    </div>

                    {/* Table */}
                    <div className="overflow-x-auto rounded-lg border border-app-border bg-app-bg-muted/20">
                        <table className="w-full text-left border-collapse text-xs">
                            <thead>
                                <tr className="border-b border-app-border bg-app-bg-muted/70 text-app-text-label uppercase font-bold tracking-wider select-none text-[10px]">
                                    <th className="py-3.5 px-4 font-bold">Task ID</th>
                                    <th className="py-3.5 px-4 font-bold">Task Description</th>
                                    <th className="py-3.5 px-4 font-bold">Assigned Agent</th>
                                    <th className="py-3.5 px-4 font-bold text-right">Time Spent</th>
                                    <th className="py-3.5 px-4 font-bold text-right">Hourly Rate</th>
                                    <th className="py-3.5 px-4 font-bold text-right">Total Cost</th>
                                    <th className="py-3.5 px-4 font-bold text-center">Completed At</th>
                                </tr>
                            </thead>
                            <tbody className="divide-y divide-app-border bg-app-bg-card text-app-text-main">
                                {filteredTasks.length === 0 ? (
                                    <tr>
                                        <td colSpan="7" className="py-8 px-4 text-center text-app-text-muted font-semibold">
                                            No billable activity logs matched your current filters.
                                        </td>
                                    </tr>
                                ) : (
                                    filteredTasks.map((task) => (
                                        <tr key={task.task_id} className="hover:bg-app-bg-hover transition-colors">
                                            <td className="py-3.5 px-4 font-mono font-bold text-app-primary">
                                                {task.task_id}
                                            </td>
                                            <td className="py-3.5 px-4 font-bold max-w-[280px] truncate">
                                                {task.task_name}
                                            </td>
                                            <td className="py-3.5 px-4">
                                                <div className="flex items-center gap-1.5">
                                                    <div className="p-1 rounded bg-app-bg-muted text-app-text-label">
                                                        {task.agent_type === 'Master Agent' ? <Cpu className="w-3 h-3 text-app-primary" /> : <User className="w-3 h-3" />}
                                                    </div>
                                                    <div>
                                                        <span className="font-bold">{task.agent_name}</span>
                                                        <span className="block text-[9px] text-app-text-muted uppercase font-semibold">{task.agent_type}</span>
                                                    </div>
                                                </div>
                                            </td>
                                            <td className="py-3.5 px-4 text-right font-mono font-bold">
                                                {task.time_taken_hours} hrs
                                            </td>
                                            <td className="py-3.5 px-4 text-right font-mono font-semibold text-app-text-muted">
                                                ${task.rate_per_hour}/hr
                                            </td>
                                            <td className="py-3.5 px-4 text-right font-mono font-bold text-emerald-600 dark:text-emerald-450">
                                                ${task.cost.toLocaleString(undefined, { minimumFractionDigits: 2 })}
                                            </td>
                                            <td className="py-3.5 px-4 text-center font-mono font-semibold">
                                                {task.completed_at}
                                            </td>
                                        </tr>
                                    ))
                                )}
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>
        </div>
    );
}
