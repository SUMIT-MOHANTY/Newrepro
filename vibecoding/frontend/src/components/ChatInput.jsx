import React from 'react';
import { Send, Plus } from 'lucide-react';
import { Button } from './ui/button';
import { cn } from '@/lib/utils';

const ChatInput = ({ 
  input, 
  setInput, 
  onSend, 
  loading, 
  darkMode,
  onKeyPress,
  suggestions 
}) => {
  return (
    <div className={cn(
      'p-4 border-t',
      darkMode ? 'border-[#3e3e42]' : 'border-gray-200'
    )}>
      {/* Suggestions */}
      {suggestions && suggestions.length > 0 && (
        <div className={cn(
          'px-4 py-3 border-b mb-4',
          darkMode ? 'border-[#3e3e42]' : 'border-gray-200'
        )}>
          <div className="flex items-center gap-2 mb-3">
            <span className={cn(
              'text-xs font-medium',
              darkMode ? 'text-[#858585]' : 'text-gray-500'
            )}>Suggestions</span>
          </div>
          <div className="space-y-2">
            {suggestions.map((suggestion, idx) => (
              <button
                key={idx}
                onClick={() => setInput(suggestion)}
                className={cn(
                  'w-full text-left px-3 py-2.5 rounded-lg text-sm transition-all',
                  darkMode 
                    ? 'bg-[#2d2d30] hover:bg-[#3e3e42] text-[#cccccc] border border-[#3e3e42]' 
                    : 'bg-gray-50 hover:bg-gray-100 text-gray-700 border border-gray-200'
                )}
              >
                {suggestion}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Input Area */}
      <div className="relative">
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyPress={onKeyPress}
          placeholder="What would you like to change?"
          disabled={loading}
          rows="3"
          className={cn(
            'w-full px-4 py-3 pr-12 rounded-lg text-sm resize-none transition-colors focus:outline-none focus:ring-2 border max-h-24 overflow-y-auto',
            darkMode 
              ? 'bg-[#2d2d30] text-[#cccccc] placeholder-[#858585] focus:ring-[#0e639c] border-[#3e3e42]' 
              : 'bg-gray-50 text-gray-900 placeholder-gray-400 focus:ring-blue-500 border-gray-200'
          )}
        />
        <Button
          onClick={onSend}
          disabled={loading || !input.trim()}
          size="icon"
          className="absolute right-3 bottom-3"
        >
          <Send className="w-4 h-4" />
        </Button>
      </div>
      <div className={cn(
        'flex items-center justify-between mt-2 text-xs',
        darkMode ? 'text-[#858585]' : 'text-gray-400'
      )}>
        <div className="flex items-center gap-3">
          <Button 
            variant="ghost"
            size="sm"
            className={cn(
              'flex items-center gap-1 h-6 px-2 text-xs',
              darkMode ? 'hover:text-[#cccccc]' : 'hover:text-gray-600'
            )}
          >
            <Plus className="w-3.5 h-3.5" />
            <span>Attach</span>
          </Button>
        </div>
        <span>Press Enter to send</span>
      </div>
    </div>
  );
};

export default ChatInput;
