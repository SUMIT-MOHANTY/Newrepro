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
  onKeyPress
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
          placeholder="Describe your app..."
          disabled={loading}
          rows="3"
          className={cn(
            'w-full px-4 py-3 pr-12 rounded-xl text-sm resize-none transition-colors focus:outline-none focus:ring-2 border max-h-24 overflow-y-auto',
            darkMode 
              ? 'bg-white/5 text-gray-200 placeholder-gray-500 focus:ring-purple-500/50 border-white/10' 
              : 'bg-gray-50 text-gray-900 placeholder-gray-400 focus:ring-blue-500 border-gray-200'
          )}
        />
        <Button
          onClick={onSend}
          disabled={loading || !input.trim()}
          size="icon"
          className={cn(
            'absolute right-3 bottom-3 w-8 h-8 rounded-lg transition-all',
            darkMode
              ? 'bg-gradient-to-r from-purple-600 to-pink-600 hover:from-purple-700 hover:to-pink-700'
              : 'bg-blue-500 hover:bg-blue-600'
          )}
        >
          <Send className="w-4 h-4" />
        </Button>
      </div>
      <div className={cn(
        'flex items-center justify-between mt-2 text-xs',
        darkMode ? 'text-gray-500' : 'text-gray-400'
      )}>
        <div className="flex items-center gap-3">
          <Button 
            variant="ghost"
            size="sm"
            className={cn(
              'flex items-center gap-1 h-6 px-2 text-xs',
              darkMode ? 'hover:text-gray-300' : 'hover:text-gray-600'
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
