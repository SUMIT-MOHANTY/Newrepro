import React, { useState, useEffect, useRef, useMemo } from 'react';
import {
  Terminal,
  X,
  Check,
  Brain,
  ChevronDown,
  ChevronRight,
  FileText,
  AlertTriangle,
  ArrowDown,
  Copy,
} from 'lucide-react';
import { streamAgentEvents, fetchBufferedAgentLogs } from '../utils/agentEventStream';

/**
 * Parses inline markdown:
 * - Bold: **text**
 * - Inline code: `code`
 */
function renderInline(text) {
  if (!text) return null;

  const parts = [];
  const codeRegex = /`([^`]+)`/g;
  let lastIdx = 0;
  let match;

  while ((match = codeRegex.exec(text)) !== null) {
    if (match.index > lastIdx) {
      parts.push({ type: 'text', content: text.substring(lastIdx, match.index) });
    }
    parts.push({ type: 'code', content: match[1] });
    lastIdx = match.index + match[0].length;
  }
  if (lastIdx < text.length) {
    parts.push({ type: 'text', content: text.substring(lastIdx) });
  }

  return parts.map((part, pIdx) => {
    if (part.type === 'code') {
      return (
        <code
          key={pIdx}
          className="font-mono text-[10.5px] text-slate-700 dark:text-slate-300 bg-slate-100 dark:bg-slate-800 px-1 py-0.5 rounded border border-slate-200 dark:border-slate-700 mx-0.5"
        >
          {part.content}
        </code>
      );
    }

    const boldParts = [];
    const boldRegex = /\*\*([^*]+)\*\*/g;
    let bLastIdx = 0;
    let bMatch;

    while ((bMatch = boldRegex.exec(part.content)) !== null) {
      if (bMatch.index > bLastIdx) {
        boldParts.push({ type: 'plain', content: part.content.substring(bLastIdx, bMatch.index) });
      }
      boldParts.push({ type: 'bold', content: bMatch[1] });
      bLastIdx = bMatch.index + bMatch[0].length;
    }
    if (bLastIdx < part.content.length) {
      boldParts.push({ type: 'plain', content: part.content.substring(bLastIdx) });
    }

    return boldParts.map((bPart, bIdx) => {
      if (bPart.type === 'bold') {
        return (
          <span key={`${pIdx}-${bIdx}`} className="font-semibold text-slate-800 dark:text-slate-200">
            {bPart.content}
          </span>
        );
      }
      return <span key={`${pIdx}-${bIdx}`}>{bPart.content}</span>;
    });
  });
}

/**
 * Thinking Row matching Image 1:
 * - Amber Brain icon
 * - "Thought for Xs" (or "Thinking...")
 * - Expandable / collapsible chevron
 * - Indented vertical line with formatted thinking text
 */
function ThinkingRow({ text, isLive = false, defaultExpanded = true }) {
  const [isExpanded, setIsExpanded] = useState(defaultExpanded);
  const [duration, setDuration] = useState(() => {
    return Math.min(8, Math.max(1, Math.round((text || '').length / 140)));
  });
  const startTimeRef = useRef(Date.now());

  useEffect(() => {
    if (isLive) {
      startTimeRef.current = Date.now();
      const interval = setInterval(() => {
        const secs = Math.max(1, Math.round((Date.now() - startTimeRef.current) / 1000));
        setDuration(secs);
      }, 1000);
      return () => clearInterval(interval);
    } else {
      setDuration((prev) => {
        if (prev && prev > 0) return prev;
        return Math.min(8, Math.max(1, Math.round((text || '').length / 140)));
      });
    }
  }, [isLive, text]);

  if (!text || !text.trim()) return null;

  const rawLines = text.split('\n');
  const label = isLive ? 'Thinking...' : `Thought for ${duration}s`;

  return (
    <div className="w-full my-1 font-sans">
      <button
        type="button"
        onClick={() => setIsExpanded(!isExpanded)}
        className="flex items-center gap-1.5 py-0.5 text-xs font-medium text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-200 transition-colors cursor-pointer select-none bg-transparent border-0 p-0"
      >
        <Brain className={`w-3.5 h-3.5 text-amber-500 shrink-0 ${isLive ? 'animate-pulse' : ''}`} />
        <span className="italic">{label}</span>
        {isExpanded ? (
          <ChevronDown className="w-3.5 h-3.5 text-slate-400" />
        ) : (
          <ChevronRight className="w-3.5 h-3.5 text-slate-400" />
        )}
      </button>

      {isExpanded && (
        <div className="mt-1 ml-2.5 pl-3 border-l-2 border-slate-200 dark:border-slate-700 space-y-1 text-xs text-slate-500 dark:text-slate-400 leading-relaxed">
          {rawLines.map((line, idx) => {
            const trimmed = line.trim();
            if (!trimmed) return <div key={idx} className="h-1" />;
            const isBullet = trimmed.startsWith('- ') || trimmed.startsWith('* ') || trimmed.startsWith('• ');
            const numMatch = trimmed.match(/^(\d+)\.\s+(.*)$/);

            if (isBullet) {
              return (
                <div key={idx} className="flex items-start gap-1.5 pl-1">
                  <span className="text-slate-400 select-none">•</span>
                  <div className="flex-1">{renderInline(trimmed.replace(/^[-*•]\s+/, ''))}</div>
                </div>
              );
            }
            if (numMatch) {
              return (
                <div key={idx} className="flex items-start gap-1.5">
                  <span className="font-mono text-slate-400 shrink-0 select-none">{numMatch[1]}.</span>
                  <div className="flex-1">{renderInline(numMatch[2])}</div>
                </div>
              );
            }
            return (
              <p key={idx} className="leading-relaxed">
                {renderInline(trimmed)}
              </p>
            );
          })}
        </div>
      )}
    </div>
  );
}

/**
 * Filter events specifically for this agent
 */
function isEventForAgent(ev, agent) {
  if (!agent) return true;
  const agentId = String(agent.id || '').toLowerCase();
  const agentName = String(agent.name || '').toLowerCase();
  const agentSub = String(agent.sub_type || agent.specialization || '').toLowerCase();

  // Master Agent / Supervisor
  if (agentId.includes('master') || agentId === 'm_agent_01' || agentName.includes('master')) {
    const evAgent = String(ev.agent_name || ev.agent_id || ev.payload?.agent || '').toLowerCase();
    const evLane = String(ev.lane || ev.payload?.lane || '').toLowerCase();
    return (
      evAgent.includes('supervisor') ||
      evAgent.includes('master') ||
      evAgent.includes('orchestrator') ||
      evLane.includes('system') ||
      (ev.event_type && ev.event_type.includes('supervisor'))
    );
  }

  // Test Agent / QA
  if (agentId.includes('test') || agentId === 't_agent_01' || agentName.includes('test') || agentSub.includes('test') || agentSub.includes('qa')) {
    const evAgent = String(ev.agent_name || ev.agent_id || ev.payload?.agent || '').toLowerCase();
    const evLane = String(ev.lane || ev.payload?.lane || '').toLowerCase();
    return evAgent.includes('qa') || evAgent.includes('test') || evLane.includes('qa') || evLane.includes('test');
  }

  // Frontend Developer
  if (agentName.includes('front') || agentSub.includes('front') || agentId.includes('front')) {
    const evAgent = String(ev.agent_name || ev.agent_id || ev.payload?.agent || '').toLowerCase();
    const evLane = String(ev.lane || ev.payload?.lane || '').toLowerCase();
    return evAgent.includes('front') || evLane.includes('front');
  }

  // Backend Developer
  if (agentName.includes('back') || agentSub.includes('back') || agentId.includes('back')) {
    const evAgent = String(ev.agent_name || ev.agent_id || ev.payload?.agent || '').toLowerCase();
    const evLane = String(ev.lane || ev.payload?.lane || '').toLowerCase();
    return evAgent.includes('back') || evLane.includes('back');
  }

  // Generic match
  const evAgent = String(ev.agent_name || ev.agent_id || ev.payload?.agent || '').toLowerCase();
  return !evAgent || evAgent.includes(agentId) || agentId.includes(evAgent) || evAgent.includes(agentName);
}

/**
 * Normalize an event or raw static log into Image 1 step item
 */
function normalizeEvent(item) {
  if (!item) return null;

  // Structured SSE event
  if (item.event_type || item.type) {
    const type = item.event_type || item.type;
    const payload = item.payload || {};

    if (type === 'thinking' || payload.reasoning || payload.thought_summary) {
      return {
        id: item._clientId || Math.random().toString(),
        kind: 'thinking',
        text: payload.reasoning || payload.thought_summary || item.message || '',
        time: item.timestamp,
      };
    }

    if (type === 'tool_called') {
      const toolName = payload.tool || 'tool_called';
      const desc = payload.description || item.message || toolName;
      return {
        id: item._clientId || Math.random().toString(),
        kind: 'tool',
        label: toolName,
        desc: desc,
        input: payload.input,
        time: item.timestamp,
      };
    }

    if (type === 'files_changed') {
      return {
        id: item._clientId || Math.random().toString(),
        kind: 'files',
        label: 'files_changed',
        time: item.timestamp,
      };
    }

    if (type === 'task_completed') {
      return {
        id: item._clientId || Math.random().toString(),
        kind: 'check',
        label: `task_completed: ${payload.task_title || payload.title || payload.task_id || ''}`.trim(),
        time: item.timestamp,
      };
    }

    if (type === 'llm_call_completed' || type === 'coding_completed') {
      return {
        id: item._clientId || Math.random().toString(),
        kind: 'check',
        label: 'llm_call_completed',
        time: item.timestamp,
      };
    }
  }

  // Parse raw text string / static log line
  const rawMsg = typeof item === 'string' ? item : (item.message || item.content || '');
  const time = item.time || item.timestamp;

  if (rawMsg.startsWith('Thinking:') || rawMsg.includes('[Thinking]') || rawMsg.startsWith('Thought for')) {
    return {
      id: Math.random().toString(),
      kind: 'thinking',
      text: rawMsg.replace(/^(Thinking:\s*|\[Thinking\]\s*)/, ''),
      time,
    };
  }

  if (rawMsg.includes('tool_called') || rawMsg.includes('Tool called:') || rawMsg.includes('[SingleFileGen Tool]') || rawMsg.startsWith('Writing') || rawMsg.startsWith('Editing')) {
    return {
      id: Math.random().toString(),
      kind: 'tool',
      label: 'tool_called',
      desc: rawMsg,
      time,
    };
  }

  if (rawMsg.includes('files_changed') || rawMsg.includes('files committed') || rawMsg.includes('Generated file')) {
    return {
      id: Math.random().toString(),
      kind: 'files',
      label: 'files_changed',
      time,
    };
  }

  if (rawMsg.includes('llm_call_completed') || rawMsg.includes('LLM turn completed') || rawMsg.includes('Preparing prompt')) {
    return {
      id: Math.random().toString(),
      kind: 'check',
      label: 'llm_call_completed',
      time,
    };
  }

  return {
    id: Math.random().toString(),
    kind: item.type === 'error' || rawMsg.toLowerCase().includes('error') ? 'error' : 'check',
    label: rawMsg,
    time,
  };
}

/**
 * AgentDedicatedLogModal Component
 * Dedicated solely to the selected agent and styled exactly like Image 1.
 */
export default function AgentDedicatedLogModal({
  agent,
  projectToken,
  token,
  onClose,
  initialStaticLogs = [],
}) {
  const [streamEvents, setStreamEvents] = useState([]);
  const [autoScroll, setAutoScroll] = useState(true);
  const [isCopied, setIsCopied] = useState(false);
  const [connectionStatus, setConnectionStatus] = useState('connecting');
  const scrollRef = useRef(null);
  const userScrolledUpRef = useRef(false);

  const agentDisplayName = agent?.name || agent?.title || 'Agent';
  const isRunning = agent?.status === 'running' || connectionStatus === 'live';

  // ── Step 1: Initial load of buffered events ────────────────────────
  useEffect(() => {
    let active = true;
    const loadBuffered = async () => {
      if (projectToken) {
        const buffered = await fetchBufferedAgentLogs(projectToken, token);
        if (active && buffered && buffered.length > 0) {
          setStreamEvents(buffered);
        }
      }
    };
    loadBuffered();
    return () => {
      active = false;
    };
  }, [projectToken, token]);

  // ── Step 2: Live SSE Event Stream ──────────────────────────────────
  useEffect(() => {
    if (!projectToken) return;

    setConnectionStatus('connecting');
    const cleanup = streamAgentEvents(projectToken, {
      token,
      onEvent: (event) => {
        if (!event || event.type === 'ping') return;
        setConnectionStatus('live');
        setStreamEvents((prev) => {
          const isDup = prev.some((e) =>
            (event._clientId && e._clientId === event._clientId) ||
            (e.timestamp === event.timestamp && e.event_type === event.event_type && e.message === event.message)
          );
          if (isDup) return prev;
          return [...prev, event];
        });
      },
      onReconnect: () => setConnectionStatus('live'),
      onError: () => setConnectionStatus('offline'),
      onDone: () => setConnectionStatus('offline'),
    });

    return () => {
      cleanup();
    };
  }, [projectToken, token]);

  // ── Step 3: Combine & filter dedicated steps for this agent ────────
  const dedicatedSteps = useMemo(() => {
    // 1. Filter stream events matching this agent
    const matchingStream = streamEvents.filter((ev) => isEventForAgent(ev, agent));

    if (matchingStream.length > 0) {
      return matchingStream.map(normalizeEvent).filter(Boolean);
    }

    // 2. Fall back to agent's own static output_log if available
    if (initialStaticLogs && initialStaticLogs.length > 0) {
      return initialStaticLogs.map(normalizeEvent).filter(Boolean);
    }

    return [];
  }, [streamEvents, initialStaticLogs, agent]);

  // Auto-scroll
  useEffect(() => {
    if (autoScroll && scrollRef.current && !userScrolledUpRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [dedicatedSteps, autoScroll]);

  const handleScroll = (e) => {
    const { scrollTop, scrollHeight, clientHeight } = e.currentTarget;
    const isAtBottom = scrollHeight - scrollTop - clientHeight < 40;
    userScrolledUpRef.current = !isAtBottom;
    if (isAtBottom && !autoScroll) setAutoScroll(true);
    else if (!isAtBottom && autoScroll) setAutoScroll(false);
  };

  // Close on Escape key
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [onClose]);

  // Copy logs
  const handleCopy = () => {
    const text = dedicatedSteps
      .map((s) => (s.kind === 'thinking' ? `[Thinking] ${s.text}` : `[${s.kind}] ${s.label || s.desc || ''}`))
      .join('\n');
    navigator.clipboard.writeText(text);
    setIsCopied(true);
    setTimeout(() => setIsCopied(false), 2000);
  };

  return (
    <div className="fixed inset-0 bg-slate-950/65 backdrop-blur-xs flex items-center justify-center p-3 sm:p-5 z-[300] animate-in fade-in duration-150">
      <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl shadow-2xl w-full max-w-2xl h-[82vh] flex flex-col overflow-hidden text-slate-800 dark:text-slate-100">

        {/* ── Header Bar ─────────────────────────────────────────────── */}
        <div className="px-5 py-3.5 border-b border-slate-200 dark:border-slate-800 flex items-center justify-between bg-slate-50/70 dark:bg-slate-900/90 shrink-0">
          <div className="flex items-center gap-2.5 min-w-0">
            <Terminal className="w-4 h-4 text-emerald-500 shrink-0" />
            <h3 className="font-bold text-sm text-slate-900 dark:text-white truncate">
              {agentDisplayName} — Execution Log
            </h3>
            {isRunning ? (
              <span className="flex items-center gap-1 text-[10px] text-emerald-600 dark:text-emerald-400 font-bold ml-1">
                <span className="relative flex h-2 w-2">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                  <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
                </span>
                LIVE
              </span>
            ) : (
              <span className="text-[10px] text-slate-400 font-medium">IDLE</span>
            )}
          </div>

          <div className="flex items-center gap-1.5 shrink-0">
            {/* Auto-scroll toggle */}
            <button
              type="button"
              onClick={() => setAutoScroll((prev) => !prev)}
              title={autoScroll ? 'Following output' : 'Scroll paused'}
              className={`p-1.5 rounded-lg text-xs transition-colors cursor-pointer ${
                autoScroll
                  ? 'text-sky-600 dark:text-sky-400 bg-sky-50 dark:bg-sky-950/50'
                  : 'text-slate-400 hover:text-slate-600 dark:hover:text-slate-200'
              }`}
            >
              <ArrowDown className={`w-3.5 h-3.5 ${autoScroll ? 'animate-bounce' : ''}`} />
            </button>

            {/* Copy button */}
            <button
              type="button"
              onClick={handleCopy}
              title="Copy log to clipboard"
              className="p-1.5 rounded-lg text-slate-400 hover:text-slate-700 dark:hover:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors cursor-pointer"
            >
              {isCopied ? <Check className="w-3.5 h-3.5 text-emerald-500" /> : <Copy className="w-3.5 h-3.5" />}
            </button>

            {/* Close button */}
            <button
              type="button"
              onClick={onClose}
              className="p-1.5 rounded-lg text-slate-400 hover:text-slate-700 dark:hover:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors cursor-pointer"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* ── Image 1 Styled Execution Trace Stream ─────────────────── */}
        <div
          ref={scrollRef}
          onScroll={handleScroll}
          className="flex-1 overflow-y-auto p-4 sm:p-5 space-y-1.5 font-mono select-text bg-white dark:bg-slate-900"
        >
          {dedicatedSteps.length === 0 ? (
            <div className="h-full flex flex-col items-center justify-center text-slate-400 text-center py-16">
              <Terminal className="w-8 h-8 text-slate-300 dark:text-slate-700 mb-2" />
              <p className="text-xs text-slate-500 dark:text-slate-400">
                {isRunning ? 'Listening for agent execution stream...' : 'No logs recorded for this agent yet.'}
              </p>
            </div>
          ) : (
            dedicatedSteps.map((step, idx) => {
              const isLast = idx === dedicatedSteps.length - 1;

              // 1. Checkmark row: llm_call_completed / task_completed / files_changed
              if (step.kind === 'check' || step.kind === 'files') {
                return (
                  <div key={step.id || idx} className="flex items-center gap-2 py-0.5">
                    <Check className="w-3.5 h-3.5 text-emerald-500 shrink-0" strokeWidth={2.5} />
                    <span className="font-mono text-xs text-slate-600 dark:text-slate-300">
                      {step.label}
                    </span>
                  </div>
                );
              }

              // 2. Thinking row: Thought for Xs ▾
              if (step.kind === 'thinking') {
                return (
                  <ThinkingRow
                    key={step.id || idx}
                    text={step.text}
                    isLive={isRunning && isLast}
                    defaultExpanded={true}
                  />
                );
              }

              // 3. Tool call row: 📄 tool_called
              if (step.kind === 'tool') {
                return (
                  <div key={step.id || idx} className="my-1 flex items-center gap-2">
                    <FileText className="w-3.5 h-3.5 text-sky-500 shrink-0" />
                    <div className="bg-sky-50/80 dark:bg-sky-950/40 border border-sky-200/80 dark:border-sky-800/80 text-sky-700 dark:text-sky-300 px-2.5 py-0.5 rounded-md font-mono text-xs font-medium inline-flex items-center gap-1.5">
                      <span>{step.label || 'tool_called'}</span>
                      {step.desc && step.desc !== step.label && (
                        <span className="text-slate-500 dark:text-slate-400 text-[11px] font-normal">
                          • {step.desc}
                        </span>
                      )}
                    </div>
                  </div>
                );
              }

              // 4. Error row
              if (step.kind === 'error') {
                return (
                  <div key={step.id || idx} className="flex items-start gap-2 py-1 text-red-500 font-mono text-xs">
                    <AlertTriangle className="w-3.5 h-3.5 shrink-0 mt-0.5" />
                    <span>{step.label}</span>
                  </div>
                );
              }

              // 5. Normal log line fallback
              return (
                <div key={step.id || idx} className="text-slate-600 dark:text-slate-400 font-mono text-xs py-0.5 pl-5">
                  {step.label}
                </div>
              );
            })
          )}
        </div>

        {/* ── Minimalist Footer ──────────────────────────────────────── */}
        <div className="px-5 py-2 border-t border-slate-100 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-900/60 flex items-center justify-between text-[11px] text-slate-400 shrink-0 font-sans">
          <span>{dedicatedSteps.length} trace step{dedicatedSteps.length !== 1 ? 's' : ''}</span>
          <span>Press Esc to close</span>
        </div>

      </div>
    </div>
  );
}
