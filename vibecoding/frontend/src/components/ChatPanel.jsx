import React, { useRef } from 'react';
import { Sparkles, Bot, RefreshCw, MoreHorizontal, X } from 'lucide-react';
import { Button } from './ui/button';
import { cn } from '@/lib/utils';
import ChatMessage from './ChatMessage';
import ChatInput from './ChatInput';
import Typewriter from './Typewriter';

const ChatPanel = ({
  messages,
  loading,
  input,
  setInput,
  onSend,
  darkMode,
  codeVersions,
  selectedVersion,
  onLoadVersion,
  onCopyMessage,
  onRegenerate,
  onClearHistory,
  suggestions,
  disabled = false,
  discussMode = false,
  onToggleDiscuss,
  onImageUpload,
  onExecuteTask,
  onExecuteAllTasks,
  onEditTask,
  executingTaskId,
  wsConnected = false,
  onRestore,
  isRestoring = false,
}) => {
  const messagesEndRef = useRef(null);
  const messagesContainerRef = useRef(null);
  const [suggestionIndex, setSuggestionIndex] = React.useState(0);
  const rotationTimeoutRef = useRef(null);
  const [isUserScrolling, setIsUserScrolling] = React.useState(false);
  const lastMessageCountRef = useRef(0);

  const inferredCheckpointCount = React.useMemo(() => {
    const fromCommits = Array.isArray(codeVersions) ? codeVersions.length : 0;
    if (fromCommits > 0) return fromCommits;
    const ids = new Set((messages || []).map(m => m?.versionId).filter(Boolean));
    return ids.size;
  }, [codeVersions, messages]);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  // Detect if user is manually scrolling
  const handleScroll = React.useCallback(() => {
    if (!messagesContainerRef.current) return;

    const { scrollTop, scrollHeight, clientHeight } = messagesContainerRef.current;
    const isAtBottom = scrollHeight - scrollTop - clientHeight < 50; // 50px threshold

    setIsUserScrolling(!isAtBottom);
  }, []);

  // Only auto-scroll when new messages arrive AND user is not manually scrolling
  React.useEffect(() => {
    const messageCount = messages.length;
    const hasNewMessages = messageCount > lastMessageCountRef.current;

    if (hasNewMessages && !isUserScrolling) {
      scrollToBottom();
    }

    lastMessageCountRef.current = messageCount;
  }, [messages, isUserScrolling]);

  React.useEffect(() => {
    return () => {
      if (rotationTimeoutRef.current) clearTimeout(rotationTimeoutRef.current);
    };
  }, []);

  // Persist the last known thinking logs across renders so the ThinkingBlock
  // stays visible during the long AI-generation gap (when no new log messages
  // arrive but loading is still true).
  const lastThinkingLogsRef = React.useRef([]);

  // Group messages: attach thinking logs to the next non-thinking message
  // NOTE: Messages from WebSocket already have thinkingLogs accumulated in App.jsx
  // We only need to process messages that don't already have thinkingLogs
  const processedMessages = React.useMemo(() => {
    const result = [];
    let pendingThinkingLogs = [];

    messages.forEach((message) => {
      // If message already has thinkingLogs (from WebSocket handler), use it as-is
      if (message.thinkingLogs && message.thinkingLogs.length > 0) {
        result.push(message);
        return;
      }

      // Check if this is a thinking/background log message
      const isThinkingMsg = message.metadata?.is_background_log || message.metadata?.type === 'thinking';

      if (isThinkingMsg) {
        // Accumulate thinking logs
        pendingThinkingLogs.push({
          message: message.content,
          timestamp: message.timestamp,
          level: message.metadata?.level || 'info'
        });
      } else {
        // Non-thinking message - attach any pending thinking logs BEFORE this message
        const processedMsg = {
          ...message,
          thinkingLogs: pendingThinkingLogs.length > 0 ? [...pendingThinkingLogs] : [],
          isThinking: false
        };
        result.push(processedMsg);
        pendingThinkingLogs = []; // Clear after attaching
      }
    });

    if (loading) {
      // Keep the last known thinking logs alive even when pendingThinkingLogs is
      // temporarily empty (the backend is generating code, not sending log msgs).
      if (pendingThinkingLogs.length > 0) {
        lastThinkingLogsRef.current = [...pendingThinkingLogs];
      }

      const logsToShow = lastThinkingLogsRef.current;
      if (logsToShow.length > 0) {
        // Check if the last result item is already a thinking placeholder to avoid duplicates
        const lastItem = result[result.length - 1];
        const alreadyHasThinking = lastItem?.isThinking === true;

        if (!alreadyHasThinking) {
          result.push({
            role: 'assistant',
            content: '',
            thinkingLogs: logsToShow,
            isThinking: true,
            metadata: { is_background_log: true, type: 'thinking' },
            timestamp: new Date().toISOString()
          });
        }
      }
    } else {
      // Reset persisted logs once loading finishes so stale logs don't bleed
      // into the next request.
      lastThinkingLogsRef.current = [];
    }

    return result;
  }, [messages, loading]);

  const [dismissedAttachmentKey, setDismissedAttachmentKey] = React.useState(null);
  const [width, setWidth] = React.useState(384); // Default 96 tailwind class is 384px
  const isResizing = useRef(false);

  const handleMouseMove = React.useCallback((e) => {
    if (!isResizing.current) return;

    // Use requestAnimationFrame for smoother UI updates
    requestAnimationFrame(() => {
      if (!isResizing.current) return;
      // Calculate new width: viewport width - mouse X position
      let newWidth = window.innerWidth - e.clientX;
      if (newWidth < 300) newWidth = 300; // min width
      if (newWidth > 1200) newWidth = 1200; // increased max width for better large-screen experience
      setWidth(newWidth);
    });
  }, []);

  const startResizing = React.useCallback((e) => {
    isResizing.current = true;
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
    document.body.classList.add('resizing-active'); // Add class to body to handle global pointer-events
    document.addEventListener('mousemove', handleMouseMove);
    document.addEventListener('mouseup', stopResizing);
  }, [handleMouseMove]);

  const stopResizing = React.useCallback(() => {
    isResizing.current = false;
    document.body.style.cursor = '';
    document.body.style.userSelect = '';
    document.body.classList.remove('resizing-active');
    document.removeEventListener('mousemove', handleMouseMove);
    document.removeEventListener('mouseup', stopResizing);
  }, [handleMouseMove]);

  return (
    <div
      className={cn(
        'flex flex-col h-full border-l relative',
        darkMode ? 'bg-[#0F0F14] border-white/10' : 'bg-white border-gray-200'
      )}
      style={{ width: `${width}px` }}
    >
      {/* Drag handle */}
      <div
        className="absolute left-0 top-0 bottom-0 w-1.5 cursor-col-resize hover:bg-purple-500/50 active:bg-purple-500 transition-colors z-50 -translate-x-1/2"
        onMouseDown={startResizing}
      />
      {/* Chat Header */}
      <div className={`flex-shrink-0 flex items-center justify-between px-4 h-14 border-b ${darkMode ? 'border-white/10' : 'border-gray-200'
        }`}>
        <div className="flex items-center gap-2">
          <div className={cn(
            'p-2 rounded-lg',
            darkMode ? 'bg-gradient-to-br from-purple-500 to-pink-500' : 'bg-blue-500'
          )}>
            <Sparkles className="w-4 h-4 text-white" />
          </div>
          <div>
            <div className="flex items-center gap-1.5">
              <span className={cn(
                'text-sm font-semibold',
                darkMode ? 'text-white' : 'text-gray-900'
              )}>Vibe Assistant</span>
              {/* Live connection indicator */}
              <span
                title={wsConnected ? 'Live updates active' : 'Reconnecting to live updates…'}
                className={cn(
                  'inline-block w-2 h-2 rounded-full flex-shrink-0 transition-colors duration-500',
                  wsConnected ? 'bg-green-400' : 'bg-gray-500'
                )}
              />
            </div>
            <span className={cn(
              'text-xs',
              darkMode ? 'text-gray-400' : 'text-gray-500'
            )}>{inferredCheckpointCount} session snapshots</span>
          </div>
        </div>
        <div className="flex items-center gap-1">
        </div>
      </div>

      {/* Messages - Fixed height with scroll */}
      <div
        ref={messagesContainerRef}
        onScroll={handleScroll}
        className="flex-1 overflow-y-auto px-4 py-4 space-y-4 custom-scrollbar min-h-0"
      >
        {messages.length === 0 && suggestions && !loading && (
          <div className="space-y-4 ">
            <div className={`text-center py-8 ${darkMode ? 'text-gray-400' : 'text-gray-500'
              }`}>
              <Sparkles className="w-10 h-10 mx-auto mb-3 opacity-50" />
              <p className="text-sm font-medium mb-1">Start Building</p>
              <p className="text-xs">Describe what you want to create</p>
            </div>

            {/* Suggestions */}
            <div>
              <div className="flex items-center gap-2 mb-3 px-2 pt-24" >
                <div className={`w-1 h-4 rounded-full ${darkMode ? 'bg-purple-500' : 'bg-blue-500'
                  }`} />
                <span className={`text-xs font-semibold uppercase tracking-wide ${darkMode ? 'text-gray-500' : 'text-gray-500'
                  }`}>Suggestions</span>
              </div>
              <div className="space-y-2">
                {suggestions && suggestions.length > 0 && (
                  <Button
                    variant="ghost"
                    onClick={() => setInput(suggestions[suggestionIndex])}
                    className={`w-full text-left px-4 py-4 h-auto rounded-xl text-sm transition-all duration-500 flex items-start ${darkMode
                      ? 'bg-white/5 hover:bg-white/10 text-gray-200 border border-white/10 hover:border-purple-500/50'
                      : 'bg-white hover:bg-gray-50 text-gray-900 border border-gray-200 hover:border-blue-400 shadow-sm'
                      }`}
                  >
                    <div className="flex items-center gap-3 w-full">
                      <Sparkles className={cn(
                        "w-4 h-4 opacity-70 mt-0.5 flex-shrink-0",
                        darkMode ? "text-purple-400" : "text-blue-500"
                      )} />
                      <div className="flex-1 min-w-0 break-words whitespace-normal leading-relaxed text-balance">
                        <Typewriter
                          key={suggestionIndex}
                          text={suggestions[suggestionIndex]}
                          delay={40}
                          waitBeforeDelete={2000}
                          onComplete={() => {
                            setSuggestionIndex((prev) => (prev + 1) % suggestions.length);
                          }}
                        />
                      </div>
                    </div>
                  </Button>
                )}
              </div>
            </div>
          </div>
        )}

        {processedMessages.map((message, idx) => {
          return (
            <ChatMessage
              key={idx}
              message={message}
              darkMode={darkMode}
              codeVersions={codeVersions}
              selectedVersion={selectedVersion}
              onLoadVersion={onLoadVersion}
              onCopyMessage={onCopyMessage}
              onRegenerate={onRegenerate}
              onSuggestionClick={setInput}
              onExecuteTask={onExecuteTask}
              onExecuteAllTasks={onExecuteAllTasks}
              onEditTask={onEditTask}
              onRestore={onRestore}
              messageIndex={idx}
              executingTaskId={executingTaskId}
              onRestore={onRestore}
              messageIndex={idx}
            />
          );
        })}

        {/* Loading indicator with dotted animation — only show when there are no
            thinking logs yet (very start of a request before any logs arrive) */}
        {loading && (processedMessages.length === 0 || (
          !processedMessages[processedMessages.length - 1]?.isThinking &&
          lastThinkingLogsRef.current.length === 0
        )) && (
          <div className="flex gap-3">
            <div className={cn(
              'flex-shrink-0 w-8 h-8 rounded-lg flex items-center justify-center',
              darkMode ? 'bg-white/5' : 'bg-gray-100'
            )}>
              <Sparkles className={cn('w-4 h-4', darkMode ? 'text-gray-400' : 'text-gray-600')} />
            </div>
            <div className="flex-1 min-w-0">
              <div className={cn(
                'rounded-lg px-4 py-3',
                isRestoring
                  ? (darkMode ? 'bg-amber-500/10 text-amber-300 border border-amber-500/20' : 'bg-amber-50 text-amber-700 border border-amber-200')
                  : (darkMode ? 'bg-white/5 text-gray-200' : 'bg-gray-100 text-gray-900')
              )}>
                <div className="flex items-center gap-2">
                  {isRestoring ? (
                    <>
                      <div className="flex gap-1">
                        <span className="w-2 h-2 bg-amber-500 rounded-full animate-bounce" style={{ animationDelay: '0ms' }}></span>
                        <span className="w-2 h-2 bg-amber-500 rounded-full animate-bounce" style={{ animationDelay: '150ms' }}></span>
                        <span className="w-2 h-2 bg-amber-500 rounded-full animate-bounce" style={{ animationDelay: '300ms' }}></span>
                      </div>
                      <span className="text-xs font-semibold">Restoring...</span>
                    </>
                  ) : (
                    <div className="flex gap-1">
                      <span className="w-2 h-2 bg-purple-500 rounded-full animate-bounce" style={{ animationDelay: '0ms' }}></span>
                      <span className="w-2 h-2 bg-purple-500 rounded-full animate-bounce" style={{ animationDelay: '150ms' }}></span>
                      <span className="w-2 h-2 bg-purple-500 rounded-full animate-bounce" style={{ animationDelay: '300ms' }}></span>
                    </div>
                  )}
                </div>
              </div>
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Input - Fixed at bottom */}
      <div className="flex-shrink-0">
        {/* File Attachments Display - Clean dismissible bar above input */}
        {(() => {
          const lastMessage = [...processedMessages].reverse().find(m => m.role === "assistant");
          const fileAttachments = lastMessage?.metadata?.file_attachments;

          if (!fileAttachments?.files?.length) return null;

          const files = fileAttachments.files;
          const diffData = fileAttachments.diff || []; // rich data with line counts
          // Build a stable key from the file list so dismissal resets when new files arrive
          const attachmentKey = files.join('|');
          if (attachmentKey === dismissedAttachmentKey) return null;

          // Build display: all files with line counts, no triangle
          const displayItems = diffData.length > 0
            ? diffData.map(f => `${f.name} +${f.lines}`)
            : files.map(f => f.split('/').pop());

          return (
            <div className={cn(
              "flex items-center justify-between gap-2 px-4 py-1.5 border-b",
              darkMode ? "border-white/10" : "border-gray-200"
            )}>
              <span className={cn(
                "text-[11px] font-medium tracking-tight",
                darkMode ? "text-green-400" : "text-green-600"
              )}>
                {displayItems.map((item, i) => (
                  <span key={i}>
                    {i > 0 && <span className={cn("mx-1.5 opacity-30", darkMode ? "text-green-400" : "text-green-600")}>·</span>}
                    {item}
                  </span>
                ))}
              </span>
              <button
                onClick={() => setDismissedAttachmentKey(attachmentKey)}
                className={cn(
                  "flex-shrink-0 rounded p-0.5 transition-colors",
                  darkMode
                    ? "text-gray-500 hover:text-gray-300 hover:bg-white/10"
                    : "text-gray-400 hover:text-gray-600 hover:bg-gray-100"
                )}
                title="Dismiss"
              >
                <X className="w-3 h-3" />
              </button>
            </div>
          );
        })()}

        <ChatInput
          input={input}
          setInput={setInput}
          onSend={onSend}
          loading={loading}
          darkMode={darkMode}
          disabled={disabled}
          discussMode={discussMode}
          onToggleDiscuss={onToggleDiscuss}
          onImageUpload={onImageUpload}
        />
      </div>
    </div>
  );
};

export default ChatPanel;