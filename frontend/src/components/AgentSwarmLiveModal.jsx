import React, { useState, useEffect, useRef, useMemo } from 'react';
import {
  Terminal,
  X,
  Copy,
  Check,
  Brain,
  Wrench,
  FileCode2,
  CheckCircle2,
  AlertTriangle,
  PlayCircle,
  Search,
  ArrowDown,
  RefreshCw,
  GitCommit,
  Layers,
  ChevronDown,
  ChevronRight,
  ShieldCheck,
  Cpu,
} from 'lucide-react';
import FormattedThinking from './FormattedThinking';
import { streamAgentEvents, fetchBufferedAgentLogs } from '../utils/agentEventStream';

/**
 * Filter categories for container sub-agents
 */
const AGENT_FILTERS = [
  { id: 'all', label: 'All Swarm Activity', icon: Layers },
  { id: 'backend', label: 'Backend Agent', icon: Cpu, match: ['backend', 'backendagent', 'backend_developer'] },
  { id: 'frontend', label: 'Frontend Agent', icon: FileCode2, match: ['frontend', 'frontendagent', 'frontend_developer'] },
  { id: 'qa', label: 'QA Engineer', icon: ShieldCheck, match: ['qa', 'qaagent', 'test', 'tester', 'test_engineer'] },
  { id: 'supervisor', label: 'Supervisor & Git', icon: GitCommit, match: ['supervisor', 'orchestrator', 'git', 'platform'] },
];

function formatTime(isoOrTimestamp) {
  if (!isoOrTimestamp) return '';
  try {
    const d = new Date(isoOrTimestamp);
    if (isNaN(d.getTime())) return '';
    return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false });
  } catch {
    return '';
  }
}

export default function AgentSwarmLiveModal({
  agent,
  projectToken,
  token,
  onClose,
  initialStaticLogs = [],
}) {
  const [events, setEvents] = useState([]);
  const [selectedFilter, setSelectedFilter] = useState('all');
  const [searchQuery, setSearchQuery] = useState('');
  const [isCopied, setIsCopied] = useState(false);
  const [autoScroll, setAutoScroll] = useState(true);
  const [connectionStatus, setConnectionStatus] = useState('connecting'); // connecting, live, offline, reconnecting
  const [reconnectAttempts, setReconnectAttempts] = useState(0);

  const scrollContainerRef = useRef(null);
  const userScrolledUpRef = useRef(false);

  const agentDisplayName = agent?.name || agent?.title || 'Swarm Runtime';
  const isAgentActive = agent?.status === 'running' || connectionStatus === 'live';

  // ── Step 1: Initial Load of Buffered Logs ──────────────────────────
  useEffect(() => {
    let isMounted = true;
    const loadInitial = async () => {
      if (projectToken) {
        const buffered = await fetchBufferedAgentLogs(projectToken, token);
        if (isMounted && buffered.length > 0) {
          setEvents(buffered);
        }
      }
    };
    loadInitial();
    return () => {
      isMounted = false;
    };
  }, [projectToken, token]);

  // ── Step 2: Establish SSE Event Stream ──────────────────────────────
  useEffect(() => {
    if (!projectToken) return;

    setConnectionStatus('connecting');
    const abortStream = streamAgentEvents(projectToken, {
      token,
      onEvent: (event) => {
        if (!event || event.type === 'ping') return;
        setConnectionStatus('live');
        setEvents((prev) => {
          // Deduplicate by _clientId or matching event attributes
          const isDup = prev.some((e) =>
            (event._clientId && e._clientId === event._clientId) ||
            (e.timestamp === event.timestamp && e.event_type === event.event_type && e.message === event.message)
          );
          if (isDup) return prev;
          return [...prev, event];
        });
      },
      onReconnect: () => {
        setConnectionStatus('live');
        setReconnectAttempts(0);
      },
      onReconnecting: (attempt) => {
        setConnectionStatus('reconnecting');
        setReconnectAttempts(attempt);
      },
      onError: () => {
        setConnectionStatus('offline');
      },
      onDone: () => {
        setConnectionStatus('offline');
      },
    });

    return () => {
      abortStream();
    };
  }, [projectToken, token]);

  // ── Auto-scroll behavior ───────────────────────────────────────────
  useEffect(() => {
    if (autoScroll && scrollContainerRef.current && !userScrolledUpRef.current) {
      scrollContainerRef.current.scrollTop = scrollContainerRef.current.scrollHeight;
    }
  }, [events, autoScroll]);

  const handleScroll = (e) => {
    const { scrollTop, scrollHeight, clientHeight } = e.currentTarget;
    const isAtBottom = scrollHeight - scrollTop - clientHeight < 50;
    userScrolledUpRef.current = !isAtBottom;
    if (isAtBottom && !autoScroll) {
      setAutoScroll(true);
    } else if (!isAtBottom && autoScroll) {
      setAutoScroll(false);
    }
  };

  // Close on Escape key
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [onClose]);

  // ── Map static logs into events if no SSE events yet ───────────────
  const allEvents = useMemo(() => {
    if (events.length > 0) return events;
    if (initialStaticLogs.length > 0) {
      return initialStaticLogs.map((log, idx) => ({
        id: `static-${idx}`,
        event_type: log.type === 'error' ? 'log_error' : log.type === 'output' ? 'log_output' : 'log_info',
        agent_id: agent?.id || 'backend_developer',
        agent_name: agent?.name || 'Agent',
        message: log.message,
        timestamp: log.time || log.timestamp,
        payload: { message: log.message },
      }));
    }
    return [];
  }, [events, initialStaticLogs, agent]);

  // ── Event categorization counts for tabs ───────────────────────────
  const counts = useMemo(() => {
    const res = { all: allEvents.length, backend: 0, frontend: 0, qa: 0, supervisor: 0 };
    for (const ev of allEvents) {
      const a = (ev.agent_id || ev.agent_name || ev.payload?.agent || ev.payload?.lane || '').toLowerCase();
      if (a.includes('back')) res.backend++;
      else if (a.includes('front')) res.frontend++;
      else if (a.includes('qa') || a.includes('test')) res.qa++;
      else res.supervisor++;
    }
    return res;
  }, [allEvents]);

  // ── Filtered & Searched Events ─────────────────────────────────────
  const filteredEvents = useMemo(() => {
    return allEvents.filter((ev) => {
      // 1. Agent filter
      if (selectedFilter !== 'all') {
        const target = AGENT_FILTERS.find((f) => f.id === selectedFilter);
        if (target && target.match) {
          const a = (ev.agent_id || ev.agent_name || ev.payload?.agent || ev.payload?.lane || '').toLowerCase();
          const match = target.match.some((m) => a.includes(m));
          if (!match) return false;
        }
      }

      // 2. Search query filter
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase();
        const msg = (ev.message || ev.content || '').toLowerCase();
        const tool = (ev.payload?.tool || ev.payload?.description || '').toLowerCase();
        const thought = (ev.payload?.reasoning || ev.payload?.thought_summary || '').toLowerCase();
        const taskTitle = (ev.task_title || ev.payload?.task_title || '').toLowerCase();
        return msg.includes(q) || tool.includes(q) || thought.includes(q) || taskTitle.includes(q);
      }

      return true;
    });
  }, [allEvents, selectedFilter, searchQuery]);

  // Copy full logs to clipboard
  const handleCopyLogs = () => {
    const lines = filteredEvents.map((ev) => {
      const time = formatTime(ev.timestamp);
      const agentTag = ev.agent_name || ev.agent_id || 'Swarm';
      const type = ev.event_type || 'log';
      const content = ev.message || ev.payload?.thought_summary || JSON.stringify(ev.payload || {});
      return `[${time}] [${agentTag}] [${type}] ${content}`;
    });
    navigator.clipboard.writeText(lines.join('\n'));
    setIsCopied(true);
    setTimeout(() => setIsCopied(false), 2000);
  };

  return (
    <div className="fixed inset-0 bg-slate-950/75 backdrop-blur-md flex items-center justify-center p-3 sm:p-5 z-[350] animate-in fade-in duration-200">
      <div className="bg-slate-900 border border-slate-800 rounded-2xl shadow-2xl w-full max-w-5xl h-[88vh] flex flex-col overflow-hidden text-slate-100">

        {/* ── Header Bar ─────────────────────────────────────────────── */}
        <div className="px-5 py-3.5 border-b border-slate-800/80 bg-slate-900/90 flex items-center justify-between gap-3 shrink-0">
          <div className="flex items-center gap-3 min-w-0">
            <div className="w-8 h-8 rounded-lg bg-sky-500/10 border border-sky-500/30 flex items-center justify-center text-sky-400 shrink-0">
              <Terminal className="w-4 h-4" />
            </div>
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <h3 className="font-bold text-sm text-white truncate">{agentDisplayName}</h3>
                <span className="text-xs text-slate-400 hidden sm:inline">• Enterprise Swarm Inspector</span>

                {/* Live / Status Indicator */}
                {isAgentActive ? (
                  <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-500/10 text-emerald-400 border border-emerald-500/30 animate-pulse">
                    <span className="w-1.5 h-1.5 rounded-full bg-emerald-500"></span>
                    LIVE STREAM
                  </span>
                ) : (
                  <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold bg-slate-800 text-slate-400 border border-slate-700">
                    IDLE / COMPLETE
                  </span>
                )}

                {/* SSE Reconnecting pill */}
                {connectionStatus === 'reconnecting' && (
                  <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold bg-amber-500/10 text-amber-400 border border-amber-500/30 animate-pulse">
                    <RefreshCw className="w-2.5 h-2.5 animate-spin" />
                    Tunnel Reconnecting ({reconnectAttempts})
                  </span>
                )}
              </div>
              <p className="text-[11px] text-slate-400 truncate">
                Sub-agent orchestration • Live reasoning stream • Tool execution telemetry
              </p>
            </div>
          </div>

          {/* Action buttons */}
          <div className="flex items-center gap-1.5 shrink-0">
            {/* Auto-scroll toggle */}
            <button
              type="button"
              onClick={() => setAutoScroll((prev) => !prev)}
              title={autoScroll ? 'Auto-scroll enabled (click to pause)' : 'Auto-scroll paused (click to follow)'}
              className={`flex items-center gap-1 px-2 py-1 rounded-lg text-xs font-medium border transition-colors cursor-pointer ${
                autoScroll
                  ? 'bg-sky-500/10 text-sky-400 border-sky-500/30'
                  : 'bg-slate-800/80 text-slate-400 border-slate-700 hover:text-slate-200'
              }`}
            >
              <ArrowDown className={`w-3.5 h-3.5 ${autoScroll ? 'animate-bounce' : ''}`} />
              <span className="hidden sm:inline">{autoScroll ? 'Following' : 'Paused'}</span>
            </button>

            {/* Copy logs */}
            <button
              type="button"
              onClick={handleCopyLogs}
              title="Copy visible logs to clipboard"
              className="p-1.5 rounded-lg text-slate-400 hover:text-slate-100 hover:bg-slate-800 transition-colors cursor-pointer"
            >
              {isCopied ? <Check className="w-4 h-4 text-emerald-400" /> : <Copy className="w-4 h-4" />}
            </button>

            {/* Close button */}
            <button
              type="button"
              onClick={onClose}
              className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition-colors cursor-pointer"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
        </div>

        {/* ── Sub-Agent Filter Tabs & Search Bar ──────────────────────── */}
        <div className="px-5 py-2.5 border-b border-slate-800 bg-slate-900/60 flex flex-wrap items-center justify-between gap-2.5 shrink-0">
          {/* Filter Pills */}
          <div className="flex items-center gap-1.5 overflow-x-auto no-scrollbar py-0.5">
            {AGENT_FILTERS.map((f) => {
              const Icon = f.icon;
              const isSelected = selectedFilter === f.id;
              const count = counts[f.id] || 0;
              return (
                <button
                  key={f.id}
                  type="button"
                  onClick={() => setSelectedFilter(f.id)}
                  className={`flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-semibold whitespace-nowrap transition-all cursor-pointer ${
                    isSelected
                      ? 'bg-sky-500 text-white shadow-sm shadow-sky-500/20'
                      : 'bg-slate-800/90 text-slate-300 hover:bg-slate-700/80 hover:text-white border border-slate-700/60'
                  }`}
                >
                  <Icon className="w-3.5 h-3.5" />
                  <span>{f.label}</span>
                  <span
                    className={`ml-1 px-1.5 py-0.2 rounded-full text-[10px] font-mono ${
                      isSelected ? 'bg-white/20 text-white' : 'bg-slate-700 text-slate-300'
                    }`}
                  >
                    {count}
                  </span>
                </button>
              );
            })}
          </div>

          {/* Quick Search Input */}
          <div className="relative w-full sm:w-60">
            <Search className="w-3.5 h-3.5 text-slate-400 absolute left-2.5 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search actions, files, thinking..."
              className="w-full pl-8 pr-2.5 py-1 text-xs bg-slate-950/70 border border-slate-800 rounded-lg text-slate-200 placeholder-slate-500 focus:outline-hidden focus:border-sky-500/70"
            />
            {searchQuery && (
              <button
                type="button"
                onClick={() => setSearchQuery('')}
                className="absolute right-2 top-1/2 -translate-y-1/2 text-slate-400 hover:text-white"
              >
                <X className="w-3 h-3" />
              </button>
            )}
          </div>
        </div>

        {/* ── Main Log Event Stream Body ─────────────────────────────── */}
        <div
          ref={scrollContainerRef}
          onScroll={handleScroll}
          className="flex-1 overflow-y-auto p-4 space-y-2 font-mono text-xs leading-relaxed select-text bg-slate-950/50"
        >
          {filteredEvents.length === 0 ? (
            <div className="h-full flex flex-col items-center justify-center text-slate-400 text-center py-16">
              <div className="w-12 h-12 rounded-2xl bg-slate-800/60 border border-slate-700/50 flex items-center justify-center mb-3 text-slate-400">
                <Terminal className="w-6 h-6" />
              </div>
              <p className="text-sm font-semibold text-slate-300">No events found</p>
              <p className="text-xs text-slate-500 max-w-sm mt-1">
                {searchQuery
                  ? `No logs match "${searchQuery}" under ${selectedFilter} filter.`
                  : 'Waiting for agent swarm execution events to stream through the tunnel...'}
              </p>
            </div>
          ) : (
            filteredEvents.map((ev, idx) => (
              <EventRow key={ev._clientId || ev.id || idx} event={ev} isLive={isAgentActive} />
            ))
          )}
        </div>

        {/* ── Footer Status Bar ──────────────────────────────────────── */}
        <div className="px-5 py-2.5 border-t border-slate-800 bg-slate-900/90 flex items-center justify-between text-[11px] text-slate-400 shrink-0">
          <div className="flex items-center gap-3">
            <span className="flex items-center gap-1.5">
              <span className={`w-2 h-2 rounded-full ${connectionStatus === 'live' ? 'bg-emerald-400' : 'bg-slate-500'}`} />
              <span className="font-semibold capitalize text-slate-300">SSE Tunnel: {connectionStatus}</span>
            </span>
            <span className="text-slate-600">|</span>
            <span>Total Events: <strong className="text-slate-200">{filteredEvents.length}</strong></span>
          </div>

          <div className="flex items-center gap-2 text-slate-500">
            <span>Press <kbd className="px-1.5 py-0.5 rounded bg-slate-800 border border-slate-700 text-[10px] text-slate-300">Esc</kbd> to exit</span>
          </div>
        </div>

      </div>
    </div>
  );
}

/**
 * Individual Event Row in the Stream
 */
function EventRow({ event, isLive }) {
  const [isExpanded, setIsExpanded] = useState(false);
  const type = event.event_type || event.type || 'log';
  const payload = event.payload || {};
  const time = formatTime(event.timestamp);

  // Sub-agent badge label & color
  const agentLabel = event.agent_name || event.agent_id || payload.agent || 'Swarm';
  const lane = (event.lane || payload.lane || '').toLowerCase();

  const getAgentColor = () => {
    if (lane.includes('back') || agentLabel.toLowerCase().includes('back')) return 'text-sky-400 border-sky-500/30 bg-sky-500/10';
    if (lane.includes('front') || agentLabel.toLowerCase().includes('front')) return 'text-violet-400 border-violet-500/30 bg-violet-500/10';
    if (lane.includes('test') || lane.includes('qa') || agentLabel.toLowerCase().includes('qa')) return 'text-emerald-400 border-emerald-500/30 bg-emerald-500/10';
    return 'text-amber-400 border-amber-500/30 bg-amber-500/10';
  };

  // ── Render 1: Thinking / Reasoning Block ────────────────────────────
  if (type === 'thinking' || payload.reasoning || payload.thought_summary) {
    const thoughtText = payload.reasoning || payload.thought_summary || event.message || '';
    return (
      <div className="rounded-xl border border-amber-500/20 bg-amber-950/15 p-2.5 my-1">
        <div className="flex items-center justify-between mb-1 text-[10px] text-slate-400">
          <div className="flex items-center gap-1.5">
            <span className={`px-1.5 py-0.2 rounded border text-[9.5px] font-semibold ${getAgentColor()}`}>
              {agentLabel}
            </span>
            <span className="text-amber-400/90 font-semibold flex items-center gap-1">
              <Brain className="w-3 h-3 text-amber-400" />
              Reasoning & Plan Turn
            </span>
          </div>
          {time && <span className="text-slate-500">{time}</span>}
        </div>
        <FormattedThinking text={thoughtText} isLive={isLive} defaultExpanded={true} />
      </div>
    );
  }

  // ── Render 2: Tool Execution ────────────────────────────────────────
  if (type === 'tool_called') {
    const toolName = payload.tool || 'tool';
    const toolDesc = payload.description || event.message || '';
    const isFile = payload.is_file || toolName.includes('file');

    return (
      <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-2.5 my-1 hover:border-slate-700/80 transition-colors">
        <div className="flex items-center justify-between gap-2 text-[11px]">
          <div className="flex items-center gap-2 min-w-0 flex-1">
            <span className={`px-1.5 py-0.2 rounded border text-[9.5px] font-semibold shrink-0 ${getAgentColor()}`}>
              {agentLabel}
            </span>
            <span className="flex items-center gap-1 font-semibold text-sky-400 shrink-0">
              <Wrench className="w-3 h-3 text-sky-400" />
              {toolName}
            </span>
            <span className="text-slate-300 truncate font-mono text-[10.5px]">
              {toolDesc}
            </span>
          </div>

          <div className="flex items-center gap-1.5 shrink-0">
            {time && <span className="text-[10px] text-slate-500">{time}</span>}
            {payload.input && (
              <button
                type="button"
                onClick={() => setIsExpanded(!isExpanded)}
                className="text-slate-400 hover:text-white p-0.5 rounded cursor-pointer"
              >
                {isExpanded ? <ChevronDown className="w-3.5 h-3.5" /> : <ChevronRight className="w-3.5 h-3.5" />}
              </button>
            )}
          </div>
        </div>

        {/* Expandable tool arguments / parameters */}
        {isExpanded && payload.input && (
          <div className="mt-2 pt-2 border-t border-slate-800/80">
            <pre className="text-[10px] text-slate-300 bg-slate-950 p-2 rounded-lg overflow-x-auto whitespace-pre-wrap max-h-40">
              {typeof payload.input === 'string' ? payload.input : JSON.stringify(payload.input, null, 2)}
            </pre>
          </div>
        )}
      </div>
    );
  }

  // ── Render 3: Files Changed / Generated ─────────────────────────────
  if (type === 'files_changed') {
    const created = payload.created || [];
    const modified = payload.modified || [];
    return (
      <div className="rounded-xl border border-sky-500/20 bg-sky-950/15 p-2.5 my-1">
        <div className="flex items-center justify-between text-[11px] mb-1.5">
          <div className="flex items-center gap-2">
            <span className={`px-1.5 py-0.2 rounded border text-[9.5px] font-semibold ${getAgentColor()}`}>
              {agentLabel}
            </span>
            <span className="font-semibold text-sky-300 flex items-center gap-1">
              <FileCode2 className="w-3.5 h-3.5 text-sky-400" />
              Files Committed to Disk
            </span>
          </div>
          {time && <span className="text-[10px] text-slate-500">{time}</span>}
        </div>
        <div className="flex flex-wrap gap-1.5 pl-1">
          {created.map((f, i) => (
            <span key={i} className="px-1.5 py-0.5 rounded bg-emerald-500/10 border border-emerald-500/30 text-emerald-300 text-[10px] font-mono">
              + {f}
            </span>
          ))}
          {modified.map((f, i) => (
            <span key={i} className="px-1.5 py-0.5 rounded bg-sky-500/10 border border-sky-500/30 text-sky-300 text-[10px] font-mono">
              ~ {f}
            </span>
          ))}
        </div>
      </div>
    );
  }

  // ── Render 4: Task Lifecycle (Started / Completed / Failed) ─────────
  if (type === 'task_started' || type === 'task_completed' || type === 'task_failed') {
    const isCompleted = type === 'task_completed';
    const isFailed = type === 'task_failed';
    const taskTitle = event.task_title || payload.title || payload.task_title || event.task_id || 'Task Scope';

    return (
      <div
        className={`rounded-xl border p-3 my-1.5 ${
          isCompleted
            ? 'border-emerald-500/30 bg-emerald-950/20'
            : isFailed
              ? 'border-red-500/30 bg-red-950/20'
              : 'border-sky-500/30 bg-sky-950/20'
        }`}
      >
        <div className="flex items-start justify-between gap-2">
          <div className="flex items-start gap-2.5 min-w-0">
            {isCompleted ? (
              <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" />
            ) : isFailed ? (
              <AlertTriangle className="w-4 h-4 text-red-400 shrink-0 mt-0.5" />
            ) : (
              <PlayCircle className="w-4 h-4 text-sky-400 shrink-0 mt-0.5" />
            )}
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <span className={`px-1.5 py-0.2 rounded border text-[9.5px] font-semibold ${getAgentColor()}`}>
                  {agentLabel}
                </span>
                <span className="font-bold text-xs text-white">
                  {isCompleted ? 'Task Completed' : isFailed ? 'Task Failed' : 'Task Dispatched'}
                </span>
                {payload.commit_hash && (
                  <span className="px-1.5 py-0.2 rounded bg-slate-800 text-slate-300 text-[10px] font-mono border border-slate-700">
                    {String(payload.commit_hash).slice(0, 7)}
                  </span>
                )}
              </div>
              <p className="text-[11px] text-slate-300 font-medium mt-0.5 leading-snug">
                {taskTitle}
              </p>
              {payload.push_message && (
                <p className="text-[10px] text-slate-400 mt-1 flex items-center gap-1 font-mono">
                  <GitCommit className="w-3 h-3 text-slate-400" />
                  {payload.push_message}
                </p>
              )}
            </div>
          </div>
          {time && <span className="text-[10px] text-slate-500 shrink-0">{time}</span>}
        </div>
      </div>
    );
  }

  // ── Render 5: General Output & Log Lines ────────────────────────────
  const isErr = type.includes('error') || type.includes('fail');
  const isSuccess = type.includes('complete') || type.includes('ready') || type.includes('success');
  const msg = event.message || event.content || (typeof payload === 'string' ? payload : JSON.stringify(payload));

  return (
    <div className="flex items-start gap-2 py-0.5 px-1 hover:bg-slate-900/50 rounded transition-colors text-[11px]">
      {time && <span className="text-slate-500 select-none text-[10px] shrink-0 font-mono">[{time}]</span>}
      <span className={`px-1 py-0.2 rounded border text-[9px] font-semibold shrink-0 select-none ${getAgentColor()}`}>
        {agentLabel}
      </span>
      <span className="text-slate-600 select-none shrink-0 font-mono">[{type}]</span>
      <span
        className={`break-words break-all flex-1 ${
          isErr ? 'text-red-400 font-medium' : isSuccess ? 'text-emerald-300' : 'text-slate-300'
        }`}
      >
        {msg}
      </span>
    </div>
  );
}
