import React, { useState } from 'react';
import { Radio, Users, MessageSquare, Send, CheckCircle, Flame } from 'lucide-react';

export default function WarRoomPage() {
  const [messages, setMessages] = useState([
    { sender: 'Master Agent', text: 'Scaffold and runtime playground initialized.', time: '14:30' },
    { sender: 'Backend Developer', text: 'Incident API routes and models verified in container sandbox.', time: '14:32' },
    { sender: 'Frontend Developer', text: 'Incident Dashboard and HashRouter pages mounted.', time: '14:35' },
    { sender: 'QA Specialist', text: 'Executing test assertions in container test runner.', time: '14:36' },
  ]);
  const [input, setInput] = useState('');

  const sendMessage = (e) => {
    e.preventDefault();
    if (!input.trim()) return;
    setMessages([...messages, { sender: 'Site Reliability Lead', text: input.trim(), time: 'Just now' }]);
    setInput('');
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between pb-4 border-b border-slate-800">
        <div className="flex items-center gap-3">
          <div className="p-2 bg-rose-500/20 text-rose-400 rounded-xl border border-rose-500/30 animate-pulse">
            <Radio className="w-5 h-5" />
          </div>
          <div>
            <h1 className="text-xl font-bold text-white">Active War Room — Incident Swarm</h1>
            <p className="text-xs text-slate-400">Live operational command center and multi-agent coordination.</p>
          </div>
        </div>
        <div className="flex items-center gap-2 px-3 py-1 bg-slate-800 text-xs text-slate-300 rounded-lg">
          <Users className="w-3.5 h-3.5 text-sky-400" />
          <span>4 Specialized Agents Active</span>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 bg-slate-900 border border-slate-800 rounded-xl flex flex-col h-[520px]">
          <div className="p-3 border-b border-slate-800 bg-slate-950/40 text-xs font-semibold text-slate-400">
            Real-time Resolution Chat & Audit Log
          </div>
          <div className="flex-1 p-4 overflow-y-auto space-y-3">
            {messages.map((m, idx) => (
              <div key={idx} className="bg-slate-950/60 border border-slate-800/80 rounded-lg p-3">
                <div className="flex items-center justify-between text-xs mb-1">
                  <span className="font-semibold text-sky-400">{m.sender}</span>
                  <span className="text-slate-500">{m.time}</span>
                </div>
                <p className="text-xs text-slate-200">{m.text}</p>
              </div>
            ))}
          </div>
          <form onSubmit={sendMessage} className="p-3 border-t border-slate-800 flex gap-2">
            <input
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Send instruction or update to swarm..."
              className="flex-1 bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-white focus:outline-none focus:border-sky-500"
            />
            <button type="submit" className="p-2 bg-sky-600 hover:bg-sky-500 text-white rounded-lg">
              <Send className="w-4 h-4" />
            </button>
          </form>
        </div>

        <div className="space-y-4">
          <div className="bg-slate-900 border border-slate-800 rounded-xl p-4">
            <h3 className="text-xs font-bold text-white uppercase tracking-wider mb-3">Active Roles</h3>
            <ul className="space-y-2 text-xs text-slate-300">
              <li className="flex items-center gap-2">
                <span className="w-2 h-2 rounded-full bg-emerald-400" />
                <strong>Master Agent</strong> — System Orchestration
              </li>
              <li className="flex items-center gap-2">
                <span className="w-2 h-2 rounded-full bg-emerald-400" />
                <strong>Frontend Developer</strong> — UI & Routing
              </li>
              <li className="flex items-center gap-2">
                <span className="w-2 h-2 rounded-full bg-emerald-400" />
                <strong>Backend Developer</strong> — API & Models
              </li>
              <li className="flex items-center gap-2">
                <span className="w-2 h-2 rounded-full bg-emerald-400" />
                <strong>QA Specialist</strong> — Test Assertion Gate
              </li>
            </ul>
          </div>
        </div>
      </div>
    </div>
  );
}
