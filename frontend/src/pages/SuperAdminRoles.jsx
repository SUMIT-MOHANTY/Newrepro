import React from 'react';
import { Shield, Users, Lock, CheckCircle2, UserCog, Building2 } from 'lucide-react';

export default function SuperAdminRoles() {
  const globalRoles = [
    {
      id: 'super_admin',
      title: 'Super Admin',
      subtitle: '(Platform Level)',
      badgeLine1: 'SUPER',
      badgeLine2: 'ADMIN',
      badgeClass: 'bg-[#6366f1] text-white border border-indigo-400/30',
      headerGradient: 'bg-gradient-to-r from-[#1e2749] via-[#2a377d] to-[#3b49a2] dark:from-[#0f172a] dark:via-[#1e1b4b] dark:to-[#312e81]',
      icon: UserCog,
      themeColor: 'purple',
      accentText: 'text-purple-600 dark:text-purple-400',
      checkIcon: 'text-purple-600 dark:text-purple-400',
      glowBg: 'bg-purple-500/10 dark:bg-purple-500/5',
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
      title: 'Organization',
      subtitle: 'Admin',
      badgeLine1: 'TENANT',
      badgeLine2: 'ADMIN',
      badgeClass: 'bg-[#0284c7] text-white border border-sky-300/30',
      headerGradient: 'bg-gradient-to-r from-[#0d4a75] via-[#0284c7] to-[#0ea5e9] dark:from-[#082f49] dark:via-[#0369a1] dark:to-[#0284c7]',
      icon: Building2,
      themeColor: 'sky',
      accentText: 'text-sky-600 dark:text-sky-400',
      checkIcon: 'text-sky-600 dark:text-sky-400',
      glowBg: 'bg-sky-500/10 dark:bg-sky-500/5',
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
      title: 'Organization',
      subtitle: 'Member',
      badgeLine1: 'STANDARD',
      badgeLine2: 'USER',
      badgeClass: 'bg-[#059669] text-white border border-emerald-300/30',
      headerGradient: 'bg-gradient-to-r from-[#065f46] via-[#059669] to-[#10b981] dark:from-[#064e3b] dark:via-[#047857] dark:to-[#059669]',
      icon: Users,
      themeColor: 'emerald',
      accentText: 'text-emerald-600 dark:text-emerald-400',
      checkIcon: 'text-emerald-600 dark:text-emerald-400',
      glowBg: 'bg-emerald-500/10 dark:bg-emerald-500/5',
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
    <div className="h-full overflow-y-auto bg-slate-50/70 dark:bg-slate-950 p-4 sm:p-8 text-slate-900 dark:text-slate-100 transition-colors">
      <div className="max-w-7xl mx-auto space-y-8">
        
        {/* Top Header Section */}
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 pb-2">
          <div className="flex items-start gap-4">
            <div className="w-12 h-12 rounded-2xl bg-blue-50/80 dark:bg-blue-950/40 border-2 border-blue-500/30 dark:border-blue-500/20 flex items-center justify-center shrink-0 text-blue-600 dark:text-blue-400 shadow-sm mt-0.5">
              <div className="relative flex items-center justify-center">
                <Shield className="w-7 h-7 stroke-[2]" />
                <Lock className="w-3 h-3 absolute stroke-[2.5]" />
              </div>
            </div>
            <div>
              <h1 className="text-xl sm:text-2xl font-bold text-slate-900 dark:text-white tracking-tight leading-snug">
                Platform security roles, permission boundaries, and privilege levels across all organizations
              </h1>
              <p className="text-xs sm:text-sm text-slate-500 dark:text-slate-400 mt-1 font-normal">
                Ensure secure access, control, and compliance with role-based permissions across your multi-tenant environment.
              </p>
            </div>
          </div>

          <div className="shrink-0 self-start md:self-center">
            <div className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full text-xs font-semibold bg-purple-100/70 dark:bg-purple-950/40 text-purple-700 dark:text-purple-300 border border-purple-200 dark:border-purple-800/50 shadow-sm">
              <Users className="w-3.5 h-3.5 text-purple-600 dark:text-purple-400" />
              <span>Multi-Tenant Access Model</span>
            </div>
          </div>
        </div>

        {/* Roles 3-Column Grid */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 sm:gap-5 items-stretch">
          {globalRoles.map((role) => {
            const IconComponent = role.icon;
            return (
              <div 
                key={role.id} 
                className="rounded-3xl bg-white dark:bg-slate-900 border border-slate-200/80 dark:border-slate-800 shadow-sm hover:shadow-md transition-shadow flex flex-col justify-between overflow-hidden relative"
              >
                {/* Background decorative glow */}
                <div className={`absolute -bottom-12 -right-12 w-44 h-44 ${role.glowBg} rounded-full blur-3xl pointer-events-none`} />

                <div>
                  {/* Card Header Banner */}
                  <div className={`${role.headerGradient} px-4 py-3.5 sm:px-4.5 sm:py-4 text-white flex items-center justify-between gap-2.5 shadow-inner`}>
                    <div className="flex items-center gap-2.5 sm:gap-3 min-w-0 flex-1">
                      <div className="w-10 h-10 sm:w-11 sm:h-11 rounded-xl bg-white/20 backdrop-blur-sm border border-white/25 flex items-center justify-center shrink-0 shadow-sm">
                        <IconComponent className="w-5 h-5 text-white" />
                      </div>
                      <div className="min-w-0 flex-1">
                        {role.id === 'super_admin' ? (
                          <>
                            <h3 className="text-[15px] sm:text-base font-bold text-white leading-tight whitespace-nowrap">
                              Super Admin
                            </h3>
                            <div className="text-[11px] text-indigo-200 dark:text-indigo-300 font-medium mt-0.5 whitespace-nowrap">
                              {role.subtitle}
                            </div>
                          </>
                        ) : (
                          <>
                            <h3 className="text-[15px] sm:text-base font-bold text-white leading-tight whitespace-nowrap">
                              {role.title}
                            </h3>
                            <div className="text-[15px] sm:text-base font-bold text-white leading-tight whitespace-nowrap">
                              {role.subtitle}
                            </div>
                          </>
                        )}
                      </div>
                    </div>

                    {/* 2-line compact badge pill */}
                    <div className="shrink-0">
                      <div className={`px-2.5 py-1 rounded-xl flex flex-col items-center justify-center text-center shadow-sm ${role.badgeClass}`}>
                        <span className="text-[9px] font-black uppercase tracking-wider leading-tight whitespace-nowrap">{role.badgeLine1}</span>
                        <span className="text-[9px] font-black uppercase tracking-wider leading-tight whitespace-nowrap">{role.badgeLine2}</span>
                      </div>
                    </div>
                  </div>

                  {/* Card Description */}
                  <div className="p-5 sm:p-6 pb-4">
                    <p className="text-xs text-slate-600 dark:text-slate-300 leading-relaxed min-h-[48px]">
                      {role.description}
                    </p>
                  </div>

                  <div className="mx-5 sm:mx-6 border-t border-slate-100 dark:border-slate-800/80" />

                  {/* Capabilities List */}
                  <div className="p-6 pt-4 space-y-4">
                    <div className="flex items-center gap-2">
                      <Shield className={`w-4 h-4 ${role.accentText} stroke-[2.2]`} />
                      <h4 className={`text-xs font-extrabold uppercase tracking-wider ${role.accentText}`}>
                        GRANTED CAPABILITIES
                      </h4>
                    </div>

                    <ul className="space-y-3">
                      {role.permissions.map((perm, idx) => (
                        <li key={idx} className="flex items-start gap-2.5">
                          <CheckCircle2 className={`w-4 h-4 ${role.checkIcon} shrink-0 mt-0.5`} />
                          <span className="text-xs text-slate-700 dark:text-slate-200 font-medium leading-normal">
                            {perm}
                          </span>
                        </li>
                      ))}
                    </ul>
                  </div>
                </div>

                {/* Bottom padding anchor */}
                <div className="h-4" />
              </div>
            );
          })}
        </div>

      </div>
    </div>
  );
}
