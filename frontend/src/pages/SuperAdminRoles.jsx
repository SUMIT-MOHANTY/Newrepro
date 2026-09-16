import React, { useState, useEffect } from 'react';
import { ShieldCheck, Shield, Users, Lock, CheckCircle2, RefreshCw, AlertCircle } from 'lucide-react';
import { API_ENDPOINTS } from '../config';

export default function SuperAdminRoles() {
  const [loading, setLoading] = useState(false);

  const globalRoles = [
    {
      id: 'super_admin',
      name: 'Super Admin (Platform Level)',
      badge: 'SUPER ADMIN',
      badgeColor: 'bg-purple-100 dark:bg-purple-500/20 text-purple-700 dark:text-purple-300 border-purple-300 dark:border-purple-500/30',
      description: 'Global administrator with cross-organization visibility, capacity enforcement, billing telemetry, and system control.',
      permissions: [
        'Platform Analytics & Telemetry',
        'Cross-Organization Billing & Token Cost Monitoring',
        'Organization Agent Onboarding Capacity Enforcement',
        'Capacity Increase Request Approvals / Rejections',
        'System-wide Audit Logs & Activity Inspection',
        'All Organization & User Management Rights'
      ]
    },
    {
      id: 'org_admin',
      name: 'Organization Admin',
      badge: 'TENANT ADMIN',
      badgeColor: 'bg-blue-100 dark:bg-blue-500/20 text-blue-700 dark:text-blue-300 border-blue-300 dark:border-blue-500/30',
      description: 'Administrator for a single organization. Can invite team members, allocate agents from approved quota, and manage RBAC roles.',
      permissions: [
        'Organization Member Invites & Management',
        'Resource Onboarding within Super-Admin Approved Capacity',
        'Project Assignment & Governance Management',
        'Organization Role & Permission Definitions',
        'Single Organization Billing & Activity Logs'
      ]
    },
    {
      id: 'org_member',
      name: 'Organization Member',
      badge: 'STANDARD USER',
      badgeColor: 'bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300 border-slate-300 dark:border-slate-700',
      description: 'Standard team member within an organization with access to assigned project pages and agent execution tools.',
      permissions: [
        'Project Initiation & Requirement Screening',
        'Governance & Prerequisite Classification',
        'Task Creation & Execution',
        'Agent Analysis & Progress View'
      ]
    }
  ];

  return (
    <div className="h-full overflow-y-auto bg-slate-50 dark:bg-slate-950 p-4 sm:p-6 text-slate-900 dark:text-slate-100 transition-colors">
      <div className="max-w-7xl mx-auto space-y-6">
        
        {/* Sub-header Context Note */}
        <div className="flex items-center justify-between border-b border-slate-200 dark:border-purple-500/20 pb-3">
          <span className="text-xs text-slate-600 dark:text-slate-400 font-medium">
            Platform security roles, permission boundaries, and privilege levels across all organizations
          </span>
          <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-purple-100 dark:bg-purple-500/20 text-purple-700 dark:text-purple-300 border border-purple-300 dark:border-purple-500/30">
            Multi-Tenant Access Model
          </span>
        </div>

        {/* Roles List */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
          {globalRoles.map((role) => (
            <div key={role.id} className="p-5 rounded-2xl bg-white dark:bg-slate-900/80 border border-slate-200 dark:border-purple-500/20 shadow-sm dark:shadow-none flex flex-col justify-between space-y-4 transition-colors">
              <div>
                <div className="flex items-center justify-between gap-2 mb-2">
                  <h3 className="text-base font-bold text-slate-900 dark:text-white flex items-center gap-2">
                    <Shield className="w-4 h-4 text-purple-600 dark:text-purple-400" />
                    {role.name}
                  </h3>
                  <span className={`px-2 py-0.5 rounded text-[10px] font-bold border ${role.badgeColor}`}>
                    {role.badge}
                  </span>
                </div>
                <p className="text-xs text-slate-600 dark:text-slate-300 leading-relaxed mb-4">
                  {role.description}
                </p>

                <div className="space-y-2">
                  <h4 className="text-[11px] font-bold uppercase tracking-wider text-purple-600 dark:text-purple-400">Granted Capabilities:</h4>
                  <ul className="space-y-1.5 text-xs text-slate-600 dark:text-slate-300">
                    {role.permissions.map((perm, idx) => (
                      <li key={idx} className="flex items-start gap-2">
                        <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600 dark:text-emerald-400 shrink-0 mt-0.5" />
                        <span>{perm}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              </div>
            </div>
          ))}
        </div>

      </div>
    </div>
  );
}
