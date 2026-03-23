import React, { useState, useEffect, useRef } from 'react';
import { API_BASE_URL } from '../config';
import { Bot, Wifi, WifiOff, AlertCircle, CheckCircle, Hammer, MessageCircle, Info, Lock, Zap, Clock } from 'lucide-react';

const MSG_COLORS = {
  BLOCKED:      { bg: 'bg-red-500/10',    border: 'border-red-500/30',    accent: 'bg-red-500', textAccent: 'text-red-400', icon: AlertCircle, label: 'BLOCKED', glow: 'shadow-red-500/20' },
  OFFERING:     { bg: 'bg-blue-500/10',   border: 'border-blue-500/30',   accent: 'bg-blue-500', textAccent: 'text-blue-400', icon: Hammer, label: 'BUILDING', glow: 'shadow-blue-500/20' },
  READY:        { bg: 'bg-green-500/10',  border: 'border-green-500/30',  accent: 'bg-green-500', textAccent: 'text-green-400', icon: CheckCircle, label: 'READY', glow: 'shadow-green-500/20' },
  HELP_REQUEST: { bg: 'bg-yellow-500/10', border: 'border-yellow-500/30', accent: 'bg-yellow-500', textAccent: 'text-yellow-400', icon: Zap, label: 'HELP', glow: 'shadow-yellow-500/20' },
  RESPONSE:     { bg: 'bg-purple-500/10', border: 'border-purple-500/30', accent: 'bg-purple-500', textAccent: 'text-purple-400', icon: MessageCircle, label: 'RESPONSE', glow: 'shadow-purple-500/20' },
  RESOLVED:     { bg: 'bg-teal-500/10',   border: 'border-teal-500/30',   accent: 'bg-teal-500', textAccent: 'text-teal-400', icon: Lock, label: 'RESOLVED', glow: 'shadow-teal-500/20' },
  INFO:         { bg: 'bg-slate-500/10',   border: 'border-slate-500/30',   accent: 'bg-slate-500', textAccent: 'text-slate-400', icon: Info, label: 'INFO', glow: 'shadow-slate-500/20' },
};

// Agent avatar colors based on agent ID
const getAgentColor = (agentId) => {
  const colors = [
    { bg: 'from-blue-500 to-blue-600', ring: 'ring-blue-500/30' },
    { bg: 'from-purple-500 to-purple-600', ring: 'ring-purple-500/30' },
    { bg: 'from-green-500 to-green-600', ring: 'ring-green-500/30' },
    { bg: 'from-orange-500 to-orange-600', ring: 'ring-orange-500/30' },
    { bg: 'from-pink-500 to-pink-600', ring: 'ring-pink-500/30' },
    { bg: 'from-indigo-500 to-indigo-600', ring: 'ring-indigo-500/30' },
    { bg: 'from-teal-500 to-teal-600', ring: 'ring-teal-500/30' },
    { bg: 'from-red-500 to-red-600', ring: 'ring-red-500/30' },
  ];
  const hash = agentId.split('').reduce((acc, char) => acc + char.charCodeAt(0), 0);
  return colors[hash % colors.length];
};

function ChatMessage({ msg, isFirst }) {
  const style = MSG_COLORS[msg.msg_type] || MSG_COLORS.INFO;
  const Icon = style.icon;
  const time = new Date(msg.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  const agentColor = getAgentColor(msg.from_agent);

  return (
    <div className={`group hover:bg-slate-800/30 transition-all duration-200 ${isFirst ? 'mt-3' : 'mt-1'}`}>
      <div className="flex gap-3 px-4 py-3">
        {/* Agent Avatar */}
        <div className={`flex-shrink-0 w-10 h-10 rounded-full bg-gradient-to-br ${agentColor.bg} flex items-center justify-center shadow-lg ring-2 ${agentColor.ring}`}>
          <Bot className="w-5 h-5 text-white" strokeWidth={2.5} />
        </div>

        {/* Message Content */}
        <div className="flex-1 min-w-0">
          {/* Header */}
          <div className="flex items-center gap-2 mb-1.5">
            <span className="text-sm font-bold text-white">{msg.from_agent}</span>
            {msg.to_agent && (
              <>
                <span className="text-slate-500">→</span>
                <span className="text-sm font-medium text-slate-300">{msg.to_agent}</span>
              </>
            )}
            <span className="flex items-center gap-1 text-xs text-slate-500">
              <Clock className="w-3 h-3" />
              {time}
            </span>
            {msg.resolved && (
              <span className="text-xs text-teal-400 flex items-center gap-1 ml-auto">
                <CheckCircle className="w-3 h-3" />
                resolved by {msg.resolved_by}
              </span>
            )}
          </div>

          {/* Message Bubble */}
          <div className={`rounded-xl border ${style.border} ${style.bg} backdrop-blur-sm px-4 py-3 shadow-lg ${style.glow} ${msg.resolved ? 'opacity-50' : ''} transition-all duration-200`}>
            {/* Status Badge */}
            <div className="flex items-center gap-2 mb-2">
              <div className={`flex items-center gap-1.5 px-2.5 py-1 rounded-full ${style.accent} shadow-md`}>
                <Icon className="w-3.5 h-3.5 text-white" strokeWidth={2.5} />
                <span className="text-xs font-bold text-white uppercase tracking-wider">
                  {style.label}
                </span>
              </div>
            </div>

            {/* Message Text */}
            <p className="text-sm text-slate-200 leading-relaxed break-words whitespace-pre-wrap">
              {msg.message}
            </p>

            {/* Task ID */}
            {msg.related_task_id && (
              <div className="mt-3 pt-2 border-t border-slate-700/50">
                <span className="text-xs text-slate-400 font-mono flex items-center gap-1.5">
                  <span className="text-slate-500">#</span>
                  Task {msg.related_task_id}
                </span>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

export default function AgentChatPanel({ projectToken }) {
  const [messages, setMessages] = useState([]);
  const [blockers, setBlockers] = useState([]);
  const [filter, setFilter] = useState('ALL');
  const [connected, setConnected] = useState(false);
  const bottomRef = useRef(null);
  const esRef = useRef(null);

  // SSE stream for real-time messages
  useEffect(() => {
    if (!projectToken) return;

    const url = `${API_BASE_URL}/coordination/chat/${projectToken}/stream`;
    const es = new EventSource(url);
    esRef.current = es;

    es.onopen = () => setConnected(true);
    es.onerror = () => setConnected(false);

    es.onmessage = (e) => {
      try {
        const data = JSON.parse(e.data);
        if (data._ping) return;
        setMessages(prev => {
          // Avoid duplicates
          if (prev.find(m => m.id === data.id)) {
            // Update if resolved state changed
            return prev.map(m => m.id === data.id ? data : m);
          }
          return [...prev, data];
        });
        // Update blockers list
        if (data.msg_type === 'BLOCKED' && !data.resolved) {
          setBlockers(prev => [...prev.filter(b => b.id !== data.id), data]);
        } else if (data._event === 'resolved' || data.resolved) {
          setBlockers(prev => prev.filter(b => b.id !== data.id));
        }
      } catch (_) {}
    };

    return () => {
      es.close();
      setConnected(false);
    };
  }, [projectToken]);

  // Auto-scroll to bottom on new messages
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const filtered = filter === 'ALL'
    ? messages
    : messages.filter(m => m.msg_type === filter);

  const activeBlockers = blockers.filter(b => !b.resolved);

  // Group messages by agent for better readability
  const groupedMessages = filtered.reduce((acc, msg, idx) => {
    const prevMsg = filtered[idx - 1];
    const isFirst = !prevMsg || prevMsg.from_agent !== msg.from_agent;
    acc.push({ ...msg, isFirst });
    return acc;
  }, []);

  return (
    <div className="flex flex-col bg-slate-900 rounded-2xl border border-slate-700 shadow-2xl overflow-hidden" style={{ height: '600px' }}>
      {/* Header */}
      <div className="flex items-center justify-between px-5 py-4 border-b border-slate-700 bg-gradient-to-r from-slate-800 via-slate-900 to-slate-800">
        <div className="flex items-center gap-3">
          <div className="w-11 h-11 rounded-xl bg-gradient-to-br from-indigo-500 via-purple-500 to-pink-500 flex items-center justify-center shadow-lg shadow-indigo-500/30 ring-2 ring-indigo-500/20">
            <MessageCircle className="w-6 h-6 text-white" strokeWidth={2.5} />
          </div>
          <div>
            <h3 className="text-base font-bold text-white">Agent Communication</h3>
            <div className="flex items-center gap-2 mt-0.5">
              {connected ? (
                <>
                  <div className="relative">
                    <Wifi className="w-3.5 h-3.5 text-green-400" />
                    <div className="absolute inset-0 animate-ping">
                      <Wifi className="w-3.5 h-3.5 text-green-400 opacity-75" />
                    </div>
                  </div>
                  <span className="text-xs text-green-400 font-semibold">Live</span>
                </>
              ) : (
                <>
                  <WifiOff className="w-3.5 h-3.5 text-red-400" />
                  <span className="text-xs text-red-400 font-semibold">Disconnected</span>
                </>
              )}
            </div>
          </div>
        </div>
        {activeBlockers.length > 0 && (
          <div className="flex items-center gap-2 px-3 py-1.5 bg-red-500/20 border border-red-500/50 rounded-full shadow-lg shadow-red-500/20 animate-pulse">
            <AlertCircle className="w-4 h-4 text-red-400" />
            <span className="text-xs font-bold text-red-300">
              {activeBlockers.length} blocked
            </span>
          </div>
        )}
      </div>

      {/* Active blockers banner */}
      {activeBlockers.length > 0 && (
        <div className="bg-red-500/10 border-b border-red-500/30 px-5 py-3 backdrop-blur-sm">
          <div className="flex items-center gap-2 mb-2">
            <AlertCircle className="w-4 h-4 text-red-400" />
            <p className="text-xs font-bold text-red-300 uppercase tracking-wider">Active Blockers</p>
          </div>
          <div className="space-y-2">
            {activeBlockers.map(b => (
              <div key={b.id} className="flex items-start gap-2 text-xs bg-red-500/10 border border-red-500/20 rounded-lg px-3 py-2">
                <span className="font-bold shrink-0 text-red-300">{b.from_agent}:</span>
                <span className="flex-1 text-red-200">{b.message.replace('🚫 BLOCKED: ', '')}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Filter tabs */}
      <div className="flex gap-2 px-4 py-3 border-b border-slate-700 bg-slate-800/50 overflow-x-auto">
        {['ALL', 'INFO', 'OFFERING', 'READY', 'BLOCKED', 'RESPONSE', 'RESOLVED'].map(f => {
          const count = f === 'ALL' ? messages.length : messages.filter(m => m.msg_type === f).length;
          const isActive = filter === f;
          return (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className={`text-xs px-3 py-2 rounded-lg whitespace-nowrap font-bold transition-all duration-200 ${
                isActive
                  ? 'bg-gradient-to-r from-indigo-500 to-purple-500 text-white shadow-lg shadow-indigo-500/30 scale-105'
                  : 'text-slate-400 hover:text-white hover:bg-slate-700 hover:scale-105'
              }`}
            >
              {f === 'ALL' ? `All (${count})` : `${f} (${count})`}
            </button>
          );
        })}
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto bg-slate-900 scrollbar-thin scrollbar-thumb-slate-700 scrollbar-track-slate-900">
        {filtered.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full text-slate-500 px-4">
            <div className="w-20 h-20 rounded-full bg-slate-800 flex items-center justify-center mb-4 shadow-lg">
              <Bot className="w-10 h-10 text-slate-600" />
            </div>
            <p className="text-sm font-semibold mb-1 text-slate-400">No messages yet</p>
            <p className="text-xs text-center text-slate-600">Agents will communicate here when they start working</p>
          </div>
        ) : (
          <div className="pb-4">
            {groupedMessages.map(msg => (
              <ChatMessage key={msg.id} msg={msg} isFirst={msg.isFirst} />
            ))}
            <div ref={bottomRef} />
          </div>
        )}
      </div>

      {/* Stats footer */}
      <div className="px-5 py-3 border-t border-slate-700 bg-slate-800 flex items-center gap-6 text-xs">
        <div className="flex items-center gap-2">
          <div className="w-2 h-2 rounded-full bg-red-500 shadow-lg shadow-red-500/50"></div>
          <span className="text-slate-400">
            <span className="font-bold text-white">{messages.filter(m => m.msg_type === 'BLOCKED' && !m.resolved).length}</span> blocked
          </span>
        </div>
        <div className="flex items-center gap-2">
          <div className="w-2 h-2 rounded-full bg-green-500 shadow-lg shadow-green-500/50"></div>
          <span className="text-slate-400">
            <span className="font-bold text-white">{messages.filter(m => m.msg_type === 'READY').length}</span> ready
          </span>
        </div>
        <div className="flex items-center gap-2">
          <div className="w-2 h-2 rounded-full bg-teal-500 shadow-lg shadow-teal-500/50"></div>
          <span className="text-slate-400">
            <span className="font-bold text-white">{messages.filter(m => m.resolved).length}</span> resolved
          </span>
        </div>
        <div className="ml-auto text-slate-500 font-semibold">
          {messages.length} total
        </div>
      </div>
    </div>
  );
}
