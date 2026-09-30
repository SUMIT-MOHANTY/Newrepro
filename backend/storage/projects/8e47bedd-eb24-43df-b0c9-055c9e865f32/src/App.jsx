import React from 'react';
import { HashRouter, Routes, Route, Link } from 'react-router-dom';
import { Shield, Terminal, Activity } from 'lucide-react';
import DashboardPage from './pages/DashboardPage';
import AuthPage from './pages/AuthPage';
import IncidentsPage from './pages/IncidentsPage';
import WarRoomPage from './pages/WarRoomPage';

export default function App() {
  return (
    <HashRouter>
      <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col font-sans">
        {/* Navigation Bar */}
        <header className="border-b border-slate-800 bg-slate-900/80 backdrop-blur sticky top-0 z-50">
          <div className="max-w-7xl mx-auto px-4 h-14 flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="p-1.5 bg-sky-500/20 text-sky-400 rounded-lg border border-sky-500/30">
                <Shield className="w-5 h-5" />
              </div>
              <span className="font-bold text-white text-sm tracking-wide">DSuite Incident Platform</span>
              <span className="hidden sm:inline-block px-2 py-0.5 text-[10px] font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 rounded-full">
                Live Swarm Build
              </span>
            </div>

            <nav className="flex items-center gap-1">
            <Link to="/" className="px-3 py-1.5 text-xs font-semibold text-slate-300 hover:text-white hover:bg-slate-800 rounded-lg transition-colors">
              Dashboard
            </Link>
            <Link to="/auth" className="px-3 py-1.5 text-xs font-semibold text-slate-300 hover:text-white hover:bg-slate-800 rounded-lg transition-colors">
              Access Portal
            </Link>
            <Link to="/incidents" className="px-3 py-1.5 text-xs font-semibold text-slate-300 hover:text-white hover:bg-slate-800 rounded-lg transition-colors">
              Incidents
            </Link>
            <Link to="/war-room" className="px-3 py-1.5 text-xs font-semibold text-slate-300 hover:text-white hover:bg-slate-800 rounded-lg transition-colors">
              War Room
            </Link>
            </nav>
          </div>
        </header>

        {/* Main Content Area */}
        <main className="flex-1 max-w-7xl mx-auto px-4 py-6 w-full">
          <Routes>
            <Route path="/" element={<DashboardPage />} />
          <Route path="/auth" element={<AuthPage />} />
          <Route path="/incidents" element={<IncidentsPage />} />
          <Route path="/war-room" element={<WarRoomPage />} />
          </Routes>
        </main>

        {/* Footer */}
        <footer className="border-t border-slate-800/80 py-4 bg-slate-950 text-center text-xs text-slate-500">
          Built with Autonomous Agent Swarm & Container Playgrounds · Bourntec DSuite
        </footer>
      </div>
    </HashRouter>
  );
}
