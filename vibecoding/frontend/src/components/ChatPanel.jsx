import React, { useRef } from 'react';
import { Sparkles, Bot, RefreshCw, MoreHorizontal } from 'lucide-react';
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
  onImageUpload, // New prop for handling image uploads
}) => {
  const messagesEndRef = useRef(null);
  const [suggestionIndex, setSuggestionIndex] = React.useState(0);
  const rotationTimeoutRef = useRef(null);

  const inferredCheckpointCount = React.useMemo(() => {
    const fromCommits = Array.isArray(codeVersions) ? codeVersions.length : 0;
    if (fromCommits > 0) return fromCommits;
    const ids = new Set((messages || []).map(m => m?.versionId).filter(Boolean));
    return ids.size;
  }, [codeVersions, messages]);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  React.useEffect(() => {
    scrollToBottom();
  }, [messages]);

  React.useEffect(() => {
    return () => {
      if (rotationTimeoutRef.current) clearTimeout(rotationTimeoutRef.current);
    };
  }, []);

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
            <span className={cn(
              'text-sm font-semibold block',
              darkMode ? 'text-white' : 'text-gray-900'
            )}>Vibe Assistant</span>
            <span className={cn(
              'text-xs',
              darkMode ? 'text-gray-400' : 'text-gray-500'
            )}>{inferredCheckpointCount} session snapshots</span>
          </div>
        </div>
        <div className="flex items-center gap-1">
          {/* {messages.length > 0 && (
            <Button
              onClick={onClearHistory}
              variant="ghost"
              size="icon"
              className={cn(
                'rounded-lg',
                darkMode
                  ? 'hover:bg-white/10 text-gray-400 hover:text-white'
                  : 'hover:bg-gray-100 text-gray-500 hover:text-gray-700'
              )}
              title="Clear history"
            >
              <RefreshCw className="w-4 h-4" />
            </Button>
          )} */}
          {/* <Button
            variant="ghost"
            size="icon"
            className={cn(
              'rounded-lg',
              darkMode
                ? 'hover:bg-white/10 text-gray-400 hover:text-white'
                : 'hover:bg-gray-100 text-gray-600'
            )}
          >
            <MoreHorizontal className="w-4 h-4" />
          </Button> */}
        </div>
      </div>

      {/* Messages - Fixed height with scroll */}
      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-4 custom-scrollbar min-h-0">
        {messages.length === 0 && suggestions && (
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

        {messages.map((message, idx) => (
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
          />
        ))}

        {loading && (
          <div className="flex gap-3">
            <div className={`flex-shrink-0 w-8 h-8 rounded-lg flex items-center justify-center ${darkMode ? 'bg-white/5' : 'bg-gray-100'
              }`}>
              <Bot className={`w-4 h-4 ${darkMode ? 'text-gray-400' : 'text-gray-600'}`} />
            </div>
            <div className={`px-4 py-3 rounded-lg ${darkMode ? 'bg-white/5' : 'bg-gray-100'
              }`}>
              <div className="flex gap-1.5">
                <span className={`w-2 h-2 rounded-full animate-bounce ${darkMode ? 'bg-purple-500' : 'bg-gray-400'
                  }`} style={{ animationDelay: '0ms' }}></span>
                <span className={`w-2 h-2 rounded-full animate-bounce ${darkMode ? 'bg-purple-500' : 'bg-gray-400'
                  }`} style={{ animationDelay: '150ms' }}></span>
                <span className={`w-2 h-2 rounded-full animate-bounce ${darkMode ? 'bg-purple-500' : 'bg-gray-400'
                  }`} style={{ animationDelay: '300ms' }}></span>
              </div>
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Input - Fixed at bottom */}
      <div className="flex-shrink-0">
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
