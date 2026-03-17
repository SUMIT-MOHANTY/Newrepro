import React from 'react';
import { Send, Plus, MessageSquare, Code2 } from 'lucide-react';
import { Button } from './ui/button';
import { cn } from '@/lib/utils';

const ChatInput = ({ 
  input, 
  setInput, 
  onSend, 
  loading, 
  darkMode,
  onKeyPress,
  disabled = false,
  discussMode = false,
  onToggleDiscuss,
}) => {
  return (
    <div className={cn(
      'p-4 border-t',
      darkMode ? 'border-white/10' : 'border-gray-200'
    )}>
      {/* Input Area */}
      <div className="relative">
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyPress={onKeyPress}
          placeholder={disabled ? "Select or create a project to start..." : discussMode ? "Ask anything, discuss ideas..." : "Describe your app..."}
          disabled={loading || disabled}
          rows="3"
          className={cn(
            'w-full px-4 py-3 pr-12 rounded-xl text-sm resize-none transition-colors focus:outline-none focus:ring-2 border max-h-24 overflow-y-auto',
            darkMode 
              ? 'bg-white/5 text-gray-200 placeholder-gray-500 border-white/10' 
              : 'bg-gray-50 text-gray-900 placeholder-gray-400 border-gray-200',
            discussMode
              ? 'focus:ring-blue-500/50'
              : 'focus:ring-purple-500/50',
            (loading || disabled) && 'opacity-50 cursor-not-allowed'
          )}
        />
        <Button
          onClick={onSend}
          disabled={loading || !input.trim() || disabled}
          size="icon"
          className={cn(
            'absolute right-3 bottom-3 w-8 h-8 rounded-lg transition-all',
            discussMode
              ? 'bg-gradient-to-r from-blue-500 to-cyan-500 hover:from-blue-600 hover:to-cyan-600'
              : darkMode
                ? 'bg-gradient-to-r from-purple-600 to-pink-600 hover:from-purple-700 hover:to-pink-700'
                : 'bg-blue-500 hover:bg-blue-600'
          )}
        >
          <Send className="w-4 h-4" />
        </Button>
      </div>

      {/* Bottom bar */}
      <div className={cn(
        'flex items-center justify-between mt-2 text-xs',
        darkMode ? 'text-gray-500' : 'text-gray-400'
      )}>
        <div className="flex items-center gap-2">
          {/* <Button 
            variant="ghost"
            size="sm"
            disabled={disabled}
            className={cn(
              'flex items-center gap-1 h-6 px-2 text-xs',
              darkMode ? 'hover:text-gray-300' : 'hover:text-gray-600'
            )}
          >
            <Plus className="w-3.5 h-3.5" />
            <span>Attach</span>
          </Button> */}

          {/* Discuss mode toggle */}
          <button
            onClick={onToggleDiscuss}
            disabled={disabled}
            title={discussMode ? 'Switch to Build mode' : 'Switch to Discuss mode'}
            className={cn(
              'flex items-center gap-1.5 h-6 px-2.5 rounded-full text-xs font-medium transition-all border',
              discussMode
                ? 'bg-blue-500/15 border-blue-500/40 text-blue-400 hover:bg-blue-500/25'
                : darkMode
                  ? 'bg-white/5 border-white/10 text-gray-500 hover:text-gray-300 hover:bg-white/10'
                  : 'bg-gray-100 border-gray-200 text-gray-400 hover:text-gray-600',
              disabled && 'opacity-40 cursor-not-allowed'
            )}
          >
            {discussMode
              ? <><MessageSquare className="w-3 h-3" /><span>Discuss</span></>
              : <><Code2 className="w-3 h-3" /><span>Build</span></>
            }
          </button>
        </div>
        <span>{disabled ? 'Select a project first' : 'Press Enter to send'}</span>
      </div>
    </div>
  );
};

export default ChatInput;
