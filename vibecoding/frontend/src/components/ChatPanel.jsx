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
      'w-[380px] flex flex-col h-screen border-l',
      darkMode ? 'bg-[#252526] border-[#3e3e42]' : 'bg-white border-gray-200'
    )}>
      {/* Chat Header */}
      <div className={`flex items-center justify-between px-4 py-3 border-b ${
        darkMode ? 'border-[#3e3e42]' : 'border-gray-200'
      }`}>
        <div className="flex items-center gap-2">
          <div className={cn(
            'p-2 rounded-lg',
            darkMode ? 'bg-[#0e639c]' : 'bg-blue-500'
          )}>
            <Sparkles className="w-4 h-4 text-white" />
          </div>
          <div>
            <span className={cn(
              'text-sm font-semibold block',
              darkMode ? 'text-[#cccccc]' : 'text-gray-900'
            )}>AI Assistant</span>
            <span className={cn(
              'text-xs',
              darkMode ? 'text-[#858585]' : 'text-gray-500'
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
                  ? 'hover:bg-[#2d2d30] text-[#858585] hover:text-[#cccccc]' 
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
                ? 'hover:bg-[#2d2d30] text-[#cccccc]' 
                : 'hover:bg-gray-100 text-gray-600'
            )}
          >
            <MoreHorizontal className="w-4 h-4" />
          </Button>
        </div>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-4 custom-scrollbar">
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
              darkMode ? 'bg-[#2d2d30]' : 'bg-gray-100'
            }`}>
              <Bot className={`w-4 h-4 ${darkMode ? 'text-[#cccccc]' : 'text-gray-600'}`} />
            </div>
            <div className={`px-4 py-3 rounded-lg ${
              darkMode ? 'bg-[#2d2d30]' : 'bg-gray-100'
            }`}>
              <div className="flex gap-1.5">
                <span className={`w-2 h-2 rounded-full animate-bounce ${
                  darkMode ? 'bg-[#858585]' : 'bg-gray-400'
                }`} style={{ animationDelay: '0ms' }}></span>
                <span className={`w-2 h-2 rounded-full animate-bounce ${
                  darkMode ? 'bg-[#858585]' : 'bg-gray-400'
                }`} style={{ animationDelay: '150ms' }}></span>
                <span className={`w-2 h-2 rounded-full animate-bounce ${
                  darkMode ? 'bg-[#858585]' : 'bg-gray-400'
                }`} style={{ animationDelay: '300ms' }}></span>
              </div>
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <ChatInput
        input={input}
        setInput={setInput}
        onSend={onSend}
        loading={loading}
        darkMode={darkMode}
        onKeyPress={onKeyPress}
        suggestions={messages.length === 0 ? suggestions : null}
      />
    </div>
  );
};

export default ChatPanel;
