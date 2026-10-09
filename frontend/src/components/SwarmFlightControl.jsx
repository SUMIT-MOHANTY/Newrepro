import React from 'react';
import { 
  Bot, 
  Cpu, 
  Code2, 
  ShieldCheck, 
  FileText, 
  ArrowRight, 
  CheckCircle2, 
  AlertCircle, 
  Loader2, 
  Sparkles,
  Layers,
  Terminal,
  Activity
} from 'lucide-react';

export default function SwarmFlightControl({
  agents = [],
  activeAgentId = null,
  activeFile = null,
  activeTask = null,
  latestMilestone = null,
  contractInfo = null,
  isLive = false,
  onOpenLogs = null,
  onOpenWorkspace = null,
}) {
  // Normalize agents to standard 3 swarm roles
  const backendAgent = agents.find(a => 
    a.id?.toLowerCase().includes('agent_02') || 
    a.lane?.toLowerCase().includes('backend') || 
    a.name?.toLowerCase().includes('backend')
  );
  
  const frontendAgent = agents.find(a => 
    a.id?.toLowerCase().includes('agent_01') || 
    a.lane?.toLowerCase().includes('frontend') || 
    a.name?.toLowerCase().includes('frontend')
  );

  const qaAgent = agents.find(a => 
    a.id?.toLowerCase().includes('t_agent') || 
    a.id?.toLowerCase().includes('agent_03') || 
    a.lane?.toLowerCase().includes('qa') || 
    a.name?.toLowerCase().includes('test') || 
    a.name?.toLowerCase().includes('qa')
  );

  const personas = [
    {
      id: backendAgent?.id || 'agent_02',
      role: 'Backend Architect',
      lane: 'backend',
      subtitle: 'Data Schema, APIs & Auth',
      agent: backendAgent,
      icon: <Cpu className="w-5 h-5 text-emerald-400" />,
      color: 'emerald',
      bgGlow: 'bg-emerald-500/10 border-emerald-500/30 text-emerald-400',
      activeBorder: 'border-emerald-500 ring-2 ring-emerald-500/40 shadow-emerald-500/20',
      description: 'Generates Prisma data models, Express/FastAPI routes, JWT auth & contracts.',
    },
    {
      id: frontendAgent?.id || 'agent_01',
      role: 'Frontend Specialist',
      lane: 'frontend',
      subtitle: 'React Shell, Tailwind & Views',
      agent: frontendAgent,
      icon: <Code2 className="w-5 h-5 text-sky-400" />,
      color: 'sky',
      bgGlow: 'bg-sky-500/10 border-sky-500/30 text-sky-400',
      activeBorder: 'border-sky-500 ring-2 ring-sky-500/40 shadow-sky-500/20',
      description: 'Builds modular React components, layouts, state stores & wires API client.',
    },
    {
      id: qaAgent?.id || 'T_agent_01',
      role: 'QA Verification Gate',
      lane: 'qa',
      subtitle: 'Testing & Build Validation',
      agent: qaAgent,
      icon: <ShieldCheck className="w-5 h-5 text-purple-400" />,
      color: 'purple',
      bgGlow: 'bg-purple-500/10 border-purple-500/30 text-purple-400',
      activeBorder: 'border-purple-500 ring-2 ring-purple-500/40 shadow-purple-500/20',
      description: 'Executes compiler verification, syntax validation & end-to-end sanity tests.',
    },
  ];

  const getStatusBadge = (agent) => {
    if (!agent) return <span className="text-[10px] font-semibold text-slate-400">Standby</span>;
    if (agent.status === 'running') {
      return (
        <span className="flex items-center gap-1.5 px-2 py-0.5 rounded-full bg-emerald-500/20 text-emerald-400 border border-emerald-500/40 text-[10px] font-bold tracking-wide uppercase">
          <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-ping" />
          Active
        </span>
      );
    }
    if (agent.status === 'completed') {
      return (
        <span className="flex items-center gap-1 px-2 py-0.5 rounded-full bg-slate-800 text-emerald-400 border border-emerald-500/30 text-[10px] font-semibold">
          <CheckCircle2 className="w-3 h-3 text-emerald-400" /> Done
        </span>
      );
    }
    if (agent.status === 'error') {
      return (
        <span className="flex items-center gap-1 px-2 py-0.5 rounded-full bg-red-500/20 text-red-400 border border-red-500/30 text-[10px] font-semibold">
          <AlertCircle className="w-3 h-3 text-red-400" /> Attention
        </span>
      );
    }
    return <span className="text-[10px] font-semibold text-slate-400">Idle</span>;
  };

  const currentActiveAgent = personas.find(p => p.agent?.status === 'running' || p.id === activeAgentId);

  return (
    <div className="w-full bg-gradient-to-br from-slate-900 via-slate-900/95 to-slate-950 border border-slate-800/80 rounded-2xl p-5 shadow-2xl relative overflow-hidden mb-6 text-slate-100">
      {/* Background ambient lighting */}
      <div className="absolute -top-24 -left-24 w-72 h-72 bg-indigo-500/10 rounded-full blur-3xl pointer-events-none" />
      <div className="absolute -bottom-24 -right-24 w-72 h-72 bg-purple-500/10 rounded-full blur-3xl pointer-events-none" />

      {/* Header bar */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-4 border-b border-slate-800/80">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-tr from-indigo-500 to-purple-600 flex items-center justify-center shadow-lg shadow-indigo-500/20">
            <Layers className="w-5 h-5 text-white" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h3 className="text-base font-bold text-white tracking-tight">Autonomous Swarm Flight Control</h3>
              <span className="px-2 py-0.5 rounded-full bg-indigo-500/20 text-indigo-300 border border-indigo-500/30 text-[10px] font-bold uppercase tracking-wider flex items-center gap-1">
                <Sparkles className="w-3 h-3 text-indigo-400" />
                Multi-Agent DAG
              </span>
            </div>
            <p className="text-xs text-slate-400 mt-0.5">
              Coordinated AI agents autonomously implementing Business Requirements (BRD)
            </p>
          </div>
        </div>

        {/* Live Active Status Pill & In-Flight Workspace Trigger */}
        <div className="flex items-center gap-2.5 flex-wrap">
          {onOpenWorkspace && (
            <button
              onClick={onOpenWorkspace}
              className="flex items-center gap-2 px-3.5 py-1.5 rounded-xl bg-gradient-to-r from-indigo-600 via-purple-600 to-sky-600 hover:from-indigo-500 hover:via-purple-500 hover:to-sky-500 text-white text-xs font-bold shadow-lg shadow-indigo-500/30 border border-indigo-400/40 transition-all transform hover:scale-[1.03] active:scale-[0.98] ring-2 ring-indigo-500/20"
            >
              <Sparkles className="w-4 h-4 text-amber-300 animate-spin" />
              <span>Launch Swarm Flight Deck</span>
              <span className="px-1.5 py-0.2 rounded-full bg-emerald-500/20 text-emerald-300 text-[10px] font-mono border border-emerald-500/30">
                :8085 Live
              </span>
            </button>
          )}

          {currentActiveAgent ? (
            <div className="flex items-center gap-2 bg-slate-800/90 border border-emerald-500/40 rounded-xl px-3 py-1.5 shadow-sm">
              <span className="relative flex h-2.5 w-2.5">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-emerald-500"></span>
              </span>
              <span className="text-xs font-semibold text-slate-200">
                <span className="text-emerald-400 font-bold">{currentActiveAgent.role}</span> is executing
              </span>
            </div>
          ) : (
            <div className="flex items-center gap-2 bg-slate-800/60 border border-slate-700/60 rounded-xl px-3 py-1.5 text-xs text-slate-400">
              <span className="w-2 h-2 rounded-full bg-slate-500" />
              <span>Swarm Standby</span>
            </div>
          )}
        </div>
      </div>

      {/* Personas Cards Grid */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3.5 my-4">
        {personas.map((persona, idx) => {
          const isCurrent = persona.agent?.status === 'running' || persona.id === activeAgentId;
          return (
            <div
              key={persona.id}
              className={`rounded-xl p-4 transition-all duration-300 border bg-slate-900/60 backdrop-blur-sm relative flex flex-col justify-between ${
                isCurrent 
                  ? `${persona.activeBorder} shadow-lg` 
                  : 'border-slate-800/70 hover:border-slate-700'
              }`}
            >
              <div>
                <div className="flex items-start justify-between mb-2.5">
                  <div className="flex items-center gap-2.5">
                    <div className={`p-2 rounded-lg border ${persona.bgGlow}`}>
                      {persona.icon}
                    </div>
                    <div>
                      <h4 className="text-sm font-bold text-white leading-tight">{persona.role}</h4>
                      <p className="text-[11px] text-slate-400 font-medium">{persona.subtitle}</p>
                    </div>
                  </div>
                  <div>{getStatusBadge(persona.agent)}</div>
                </div>
                <p className="text-[11.5px] text-slate-400 leading-relaxed mb-3">
                  {persona.description}
                </p>
              </div>

              {/* Persona Footer / Progress */}
              <div className="pt-2 border-t border-slate-800/60 flex items-center justify-between text-[11px]">
                <span className="text-slate-500 font-medium">Lane: <strong className="text-slate-300 font-semibold uppercase">{persona.lane}</strong></span>
                {onOpenLogs && persona.agent && (
                  <button
                    onClick={() => onOpenLogs(persona.agent.id)}
                    className="inline-flex items-center gap-1 text-slate-400 hover:text-indigo-400 font-medium transition-colors"
                  >
                    <Terminal className="w-3 h-3" /> Logs
                  </button>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {/* Live Workspace Context / Activity Bar */}
      <div className="bg-slate-950/70 border border-slate-800/80 rounded-xl p-3 flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-xs">
        {/* Active File Indicator */}
        <div className="flex items-center gap-2 min-w-0">
          <FileText className="w-4 h-4 text-indigo-400 flex-shrink-0" />
          <span className="text-slate-400 flex-shrink-0">Active File:</span>
          {activeFile ? (
            <code className="px-2 py-0.5 bg-indigo-950/60 border border-indigo-500/30 text-indigo-300 font-mono text-[11px] rounded truncate max-w-md">
              {activeFile}
            </code>
          ) : (
            <span className="text-slate-500 italic">No file write in flight</span>
          )}
        </div>

        {/* Inter-Agent Contract Badge */}
        <div className="flex items-center gap-2 flex-shrink-0">
          <span className="text-slate-400">IPC Contract:</span>
          {contractInfo ? (
            <span className="px-2 py-0.5 rounded bg-emerald-950/60 border border-emerald-500/30 text-emerald-300 font-mono text-[11px]">
              {contractInfo.routes_count || 0} routes, {contractInfo.models_count || 0} models verified
            </span>
          ) : (
            <span className="px-2 py-0.5 rounded bg-slate-800 text-slate-400 text-[11px]">
              .agent/contracts/api_contract.json
            </span>
          )}
        </div>
      </div>
    </div>
  );
}
