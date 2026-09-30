import React from 'react';
import { Layers, Activity, CheckCircle, Clock } from 'lucide-react';

export default function Header({ projectName, backendHealth }) {
  const isHealthy = backendHealth?.status === 'ok';

  return (
    <header className="sticky top-0 z-40 w-full backdrop-blur-md bg-slate-950/80 border-b border-slate-800/80 px-6 py-4">
      <div className="max-w-7xl mx-auto flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl bg-gradient-to-tr from-indigo-600 to-violet-500 flex items-center justify-center text-white shadow-md shadow-indigo-500/20">
            <Layers className="w-5 h-5" />
          </div>
          <div>
            <h1 className="text-base font-bold tracking-tight text-white">{projectName}</h1>
            <p className="text-[11px] text-slate-400 font-mono">D-Suite Autonomous Scaffold v1.0</p>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-slate-900 border border-slate-800 text-xs">
            <span className={`w-2 h-2 rounded-full ${isHealthy ? 'bg-emerald-400 animate-pulse' : 'bg-amber-400'}`} />
            <span className="text-slate-300 font-medium">API: {backendHealth?.status || 'Connecting'}</span>
          </div>
        </div>
      </div>
    </header>
  );
}
