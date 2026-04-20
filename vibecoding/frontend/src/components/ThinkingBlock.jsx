import React, { useState, useEffect, useRef } from 'react';
import { ChevronDown, ChevronRight, Loader2, CheckCircle2, XCircle, RotateCw } from 'lucide-react';
import { cn } from '@/lib/utils';

/**
 * ThinkingBlock - Inline AI thinking/background execution component
 * Appears as a normal chat message with expandable logs
 */
const ThinkingBlock = ({ 
  logs = [], 
  status = 'thinking', // 'thinking', 'success', 'error', 'retrying'
  title = 'Thinking...',
  darkMode = false,
  autoScroll = true
}) => {
  const [isExpanded, setIsExpanded] = useState(false);
  const logsEndRef = useRef(null);
  const logsContainerRef = useRef(null);

  // Auto-scroll to bottom when new logs arrive (if expanded)
  useEffect(() => {
    if (isExpanded && autoScroll && logsEndRef.current) {
      logsEndRef.current.scrollIntoView({ behavior: 'smooth', block: 'end' });
    }
  }, [logs, isExpanded, autoScroll]);

  // Get status icon and color
  const getStatusIcon = () => {
    switch (status) {
      case 'success':
        return <CheckCircle2 className="w-4 h-4 text-green-500" />;
      case 'error':
        return <XCircle className="w-4 h-4 text-red-500" />;
      case 'retrying':
        return <RotateCw className="w-4 h-4 text-yellow-500 animate-spin" />;
      case 'thinking':
      default:
        return <Loader2 className="w-4 h-4 text-purple-500 animate-spin" />;
    }
  };

  const getStatusTitle = () => {
    switch (status) {
      case 'success':
        return title.replace('Thinking', 'Completed').replace('Executing', 'Completed');
      case 'error':
        return title.replace('Thinking', 'Failed').replace('Executing', 'Failed');
      case 'retrying':
        return title.replace('Thinking', 'Retrying').replace('Executing', 'Retrying');
      default:
        return title;
    }
  };

  return (
    <div className={cn(
      'rounded-lg border transition-all duration-300',
      darkMode 
        ? 'bg-white/5 border-white/10' 
        : 'bg-gray-50 border-gray-200'
    )}>
      {/* Collapsed Bar */}
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className={cn(
          'w-full flex items-center gap-3 px-4 py-3 text-left transition-colors',
          darkMode 
            ? 'hover:bg-white/5' 
            : 'hover:bg-gray-100'
        )}
      >
        {/* Status Icon */}
        <div className="flex-shrink-0">
          {getStatusIcon()}
        </div>

        {/* Title */}
        <div className="flex-1 min-w-0">
          <span className={cn(
            'text-sm font-medium',
            darkMode ? 'text-gray-300' : 'text-gray-700'
          )}>
            {getStatusTitle()}
          </span>
          {logs.length > 0 && (
            <span className={cn(
              'ml-2 text-xs',
              darkMode ? 'text-gray-500' : 'text-gray-400'
            )}>
              ({logs.length} log{logs.length !== 1 ? 's' : ''})
            </span>
          )}
        </div>

        {/* Expand/Collapse Icon */}
        <div className="flex-shrink-0">
          {isExpanded ? (
            <ChevronDown className={cn(
              'w-4 h-4',
              darkMode ? 'text-gray-400' : 'text-gray-500'
            )} />
          ) : (
            <ChevronRight className={cn(
              'w-4 h-4',
              darkMode ? 'text-gray-400' : 'text-gray-500'
            )} />
          )}
        </div>
      </button>

      {/* Expanded Logs Panel */}
      {isExpanded && (
        <div 
          ref={logsContainerRef}
          className={cn(
            'border-t overflow-y-auto transition-all duration-300',
            darkMode 
              ? 'border-white/10 bg-black/20' 
              : 'border-gray-200 bg-gray-100',
            'max-h-[400px]'
          )}
        >
          {logs.length === 0 ? (
            <div className={cn(
              'px-4 py-8 text-center text-sm',
              darkMode ? 'text-gray-500' : 'text-gray-400'
            )}>
              No logs yet...
            </div>
          ) : (
            <div className="px-4 py-3 space-y-1">
              {logs.map((log, idx) => (
                <div 
                  key={idx}
                  className={cn(
                    'font-mono text-xs leading-relaxed',
                    darkMode ? 'text-gray-400' : 'text-gray-600'
                  )}
                >
                  {log.timestamp && (
                    <span className={cn(
                      'mr-2',
                      darkMode ? 'text-gray-600' : 'text-gray-400'
                    )}>
                      [{new Date(log.timestamp).toLocaleTimeString()}]
                    </span>
                  )}
                  <span className={cn(
                    log.level === 'error' && 'text-red-500',
                    log.level === 'warning' && 'text-yellow-500',
                    log.level === 'success' && 'text-green-500'
                  )}>
                    {log.message || log}
                  </span>
                </div>
              ))}
              <div ref={logsEndRef} />
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default ThinkingBlock;
