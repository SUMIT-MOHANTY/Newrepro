// components/ThinkingBlock.jsx
import React, { useState, useRef, useEffect } from 'react';
import { ChevronDown, ChevronUp, Loader2, CheckCircle2, XCircle } from 'lucide-react';
import { cn } from '@/lib/utils';

const ThinkingBlock = ({ logs, status, title, darkMode, autoScroll = false }) => {
  const [isExpanded, setIsExpanded] = useState(false);
  const logsEndRef = useRef(null);

  useEffect(() => {
    if (autoScroll && isExpanded && logsEndRef.current) {
      logsEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [logs, autoScroll, isExpanded]);

  const isThinking = status === 'thinking';
  const hasError = status === 'error' || logs.some(l => l.level === 'error');

  return (
    <div className={cn(
      "rounded-lg border overflow-hidden",
      darkMode 
        ? "bg-white/5 border-white/10" 
        : "bg-gray-50 border-gray-200"
    )}>
      {/* Header - Always visible, clickable to expand */}
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className={cn(
          "w-full flex items-center justify-between px-3 py-2.5 text-left transition-colors",
          darkMode ? "hover:bg-white/5" : "hover:bg-gray-100"
        )}
      >
        <div className="flex items-center gap-2">
          {isThinking ? (
            <Loader2 className={cn(
              "w-4 h-4 animate-spin",
              darkMode ? "text-purple-400" : "text-blue-500"
            )} />
          ) : hasError ? (
            <XCircle className="w-4 h-4 text-red-500" />
          ) : (
            <CheckCircle2 className="w-4 h-4 text-green-500" />
          )}
          <span className={cn(
            "text-sm font-medium",
            darkMode ? "text-gray-200" : "text-gray-700"
          )}>
            {title || (isThinking ? 'Thinking...' : 'Thinking completed')}
          </span>
          <span className={cn(
            "text-xs",
            darkMode ? "text-gray-500" : "text-gray-400"
          )}>
            ({logs.length} {logs.length === 1 ? 'step' : 'steps'})
          </span>
        </div>
        {isExpanded ? (
          <ChevronUp className={cn(
            "w-4 h-4",
            darkMode ? "text-gray-400" : "text-gray-500"
          )} />
        ) : (
          <ChevronDown className={cn(
            "w-4 h-4",
            darkMode ? "text-gray-400" : "text-gray-500"
          )} />
        )}
      </button>

      {/* Expanded logs */}
      {isExpanded && (
        <div className={cn(
          "border-t max-h-64 overflow-y-auto",
          darkMode ? "border-white/10" : "border-gray-200"
        )}>
          <div className="p-3 space-y-2">
            {logs.map((log, idx) => (
              <div key={idx} className="flex items-start gap-2">
                <span className={cn(
                  "w-1.5 h-1.5 rounded-full mt-1.5 flex-shrink-0",
                  log.level === 'success' ? "bg-green-500" :
                  log.level === 'error' ? "bg-red-500" :
                  "bg-blue-500"
                )} />
                <div className="flex-1 min-w-0">
                  <p className={cn(
                    "text-xs leading-relaxed break-words",
                    darkMode ? "text-gray-300" : "text-gray-600"
                  )}>
                    {log.message}
                  </p>
                  {log.timestamp && (
                    <p className={cn(
                      "text-[10px] mt-0.5",
                      darkMode ? "text-gray-600" : "text-gray-400"
                    )}>
                      {new Date(log.timestamp).toLocaleTimeString()}
                    </p>
                  )}
                </div>
              </div>
            ))}
            <div ref={logsEndRef} />
          </div>
        </div>
      )}
    </div>
  );
};

export default ThinkingBlock;