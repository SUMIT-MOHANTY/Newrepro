import React from 'react';
import { Code2, Server, CheckCircle2, ShieldCheck, Terminal, Sparkles } from 'lucide-react';

export default function Dashboard({ projectName }) {
  return (
    <div className="space-y-6">
      {/* Hero Banner */}
      <div className="relative overflow-hidden rounded-2xl border border-indigo-500/20 bg-gradient-to-br from-indigo-950/40 via-slate-900/60 to-purple-950/30 p-8 shadow-2xl">
        <div className="relative z-10 max-w-2xl space-y-3">
          <div className="inline-flex items-center gap-2 px-2.5 py-1 rounded-full bg-indigo-500/10 border border-indigo-500/30 text-indigo-300 text-xs font-medium">
            <Sparkles className="w-3.5 h-3.5 text-indigo-400" />
            <span>Master Agent Seeded Scaffold</span>
          </div>
          <h2 className="text-2xl sm:text-3xl font-extrabold text-white tracking-tight">
            {projectName} Workspace
          </h2>
          <p className="text-sm text-slate-300 leading-relaxed">
            Starter architecture generated and validated. Autonomous specialized agents (Frontend, Backend, and QA) are equipped to build application features phase-by-phase.
          </p>
        </div>
      </div>

      {/* Architecture Tiles */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="p-5 rounded-xl border border-slate-800 bg-slate-900/50 space-y-3">
          <div className="w-10 h-10 rounded-lg bg-sky-500/10 border border-sky-500/20 text-sky-400 flex items-center justify-center">
            <Code2 className="w-5 h-5" />
          </div>
          <h3 className="text-sm font-semibold text-white">Frontend Stack</h3>
          <p className="text-xs text-slate-400">Vite 5, React 18, Tailwind CSS, Lucide icons, React Router ready for UI components.</p>
        </div>

        <div className="p-5 rounded-xl border border-slate-800 bg-slate-900/50 space-y-3">
          <div className="w-10 h-10 rounded-lg bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 flex items-center justify-center">
            <Server className="w-5 h-5" />
          </div>
          <h3 className="text-sm font-semibold text-white">Backend APIs</h3>
          <p className="text-xs text-slate-400">FastAPI backend runtime on port 8000 with CORS middleware and schema validation.</p>
        </div>

        <div className="p-5 rounded-xl border border-slate-800 bg-slate-900/50 space-y-3">
          <div className="w-10 h-10 rounded-lg bg-amber-500/10 border border-amber-500/20 text-amber-400 flex items-center justify-center">
            <ShieldCheck className="w-5 h-5" />
          </div>
          <h3 className="text-sm font-semibold text-white">Zero-Error Gate</h3>
          <p className="text-xs text-slate-400">Continuous ESLint verification, syntax tests, and unit test validations before signoff.</p>
        </div>
      </div>
    </div>
  );
}
