import React, { useState, useEffect } from 'react';
import { Layout, Code2, Server, CheckCircle2, ArrowRight, ShieldCheck, Terminal, Layers } from 'lucide-react';
import Header from './components/Header.jsx';
import Dashboard from './components/Dashboard.jsx';

export default function App() {
  const [backendHealth, setBackendHealth] = useState(null);

  useEffect(() => {
    fetch('/api/health')
      .then((res) => res.json())
      .then((data) => setBackendHealth(data))
      .catch(() => setBackendHealth({ status: 'standby', message: 'Backend service connecting...' }));
  }, []);

  return (
    <div className="min-h-screen bg-[#0d1117] text-slate-100 flex flex-col">
      <Header projectName="NexusDesk" backendHealth={backendHealth} />

      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-8 flex flex-col gap-8">
        <Dashboard projectName="NexusDesk" />
      </main>

      <footer className="border-t border-slate-800/80 bg-slate-950/40 py-6 text-center text-xs text-slate-500">
        <p>Built with D-Suite Autonomous Multi-Agent Orchestration • Vibecoding Architecture</p>
      </footer>
    </div>
  );
}
