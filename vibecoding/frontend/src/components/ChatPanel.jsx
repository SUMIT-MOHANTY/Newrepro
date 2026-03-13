import React, { useRef } from 'react';
import { Sparkles, Bot, RefreshCw, MoreHorizontal } from 'lucide-react';
import { Button } from './ui/button';
import { cn } from '@/lib/utils';
import ChatMessage from './ChatMessage';
import ChatInput from './ChatInput';

const ChatPanel = ({ 
  messages, 
  loading, 
  input, 
  setInput, 
  onSend, 
  onKeyPress, 
  darkMode, 
  codeVersions, 
  selectedVersion, 
  onLoadVersion, 
  onCopyMessage, 
  onRegenerate, 
  onClearHistory,
  suggestions 
}) => {
  const messagesEndRef = useRef(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  React.useEffect(() => {
    scrollToBottom();
  }, [messages]);

  return (
    <div className={cn(
      'w-96 flex flex-col h-screen border-l',
      darkMode ? 'bg-[#0F0F14] border-white/10' : 'bg-white border-gray-200'
    )}>
      {/* Chat Header */}
      <div className={`flex-shrink-0 flex items-center justify-between px-4 py-3 border-b ${
        darkMode ? 'border-white/10' : 'border-gray-200'
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
            )}>AI Assistant</span>
            <span className={cn(
              'text-xs',
              darkMode ? 'text-gray-400' : 'text-gray-500'
            )}>{messages.length} messages</span>
          </div>
        </div>
        <div className="flex items-center gap-1">
          {messages.length > 0 && (
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
          )}
          <Button 
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
          </Button>
        </div>
      </div>

      {/* Messages - Fixed height with scroll */}
      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-4 custom-scrollbar min-h-0">
        {messages.length === 0 && suggestions && (
          <div className="space-y-4">
            <div className={`text-center py-8 ${
              darkMode ? 'text-gray-400' : 'text-gray-500'
            }`}>
              <Sparkles className="w-10 h-10 mx-auto mb-3 opacity-50" />
              <p className="text-sm font-medium mb-1">Start Building</p>
              <p className="text-xs">Describe what you want to create</p>
            </div>
            
            {/* Suggestions */}
            <div>
              <div className="flex items-center gap-2 mb-3 px-2">
                <div className={`w-1 h-4 rounded-full ${
                  darkMode ? 'bg-purple-500' : 'bg-blue-500'
                }`} />
                <span className={`text-xs font-semibold uppercase tracking-wide ${
                  darkMode ? 'text-gray-500' : 'text-gray-500'
                }`}>Suggestions</span>
              </div>
              <div className="space-y-2">
                {suggestions.map((suggestion, idx) => (
                  <button
                    key={idx}
                    onClick={() => setInput(suggestion)}
                    className={`w-full text-left px-4 py-3 rounded-lg text-sm transition-all ${
                      darkMode 
                        ? 'bg-white/5 hover:bg-white/10 text-gray-200 border border-white/10 hover:border-purple-500/50' 
                        : 'bg-gray-50 hover:bg-gray-100 text-gray-700 border border-gray-200 hover:border-blue-300'
                    }`}
                  >
                    {suggestion}
                  </button>
                ))}
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
          />
        ))}

        {loading && (
          <div className="flex gap-3">
            <div className={`flex-shrink-0 w-8 h-8 rounded-lg flex items-center justify-center ${
              darkMode ? 'bg-white/5' : 'bg-gray-100'
            }`}>
              <Bot className={`w-4 h-4 ${darkMode ? 'text-gray-400' : 'text-gray-600'}`} />
            </div>
            <div className={`px-4 py-3 rounded-lg ${
              darkMode ? 'bg-white/5' : 'bg-gray-100'
            }`}>
              <div className="flex gap-1.5">
                <span className={`w-2 h-2 rounded-full animate-bounce ${
                  darkMode ? 'bg-purple-500' : 'bg-gray-400'
                }`} style={{ animationDelay: '0ms' }}></span>
                <span className={`w-2 h-2 rounded-full animate-bounce ${
                  darkMode ? 'bg-purple-500' : 'bg-gray-400'
                }`} style={{ animationDelay: '150ms' }}></span>
                <span className={`w-2 h-2 rounded-full animate-bounce ${
                  darkMode ? 'bg-purple-500' : 'bg-gray-400'
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
          onKeyPress={onKeyPress}
        />
      </div>
    </div>
  );
};

export default ChatPanel;
