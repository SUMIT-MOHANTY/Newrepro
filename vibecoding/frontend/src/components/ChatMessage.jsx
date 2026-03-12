import React from 'react';
import { User, Bot, CheckCircle2, Copy, RefreshCw } from 'lucide-react';
import { Button } from './ui/button';
import { cn } from '@/lib/utils';

const ChatMessage = ({ 
  message, 
  darkMode, 
  codeVersions, 
  selectedVersion, 
  onLoadVersion, 
  onCopyMessage, 
  onRegenerate 
}) => {
  const msgVersion = message.code ? codeVersions.find(v => 
    Math.abs(new Date(v.timestamp).getTime() - new Date(message.timestamp).getTime()) < 1000
  ) : null;

  const isUser = message.role === 'user';

  return (
    <div className="message-item">
      <div className={cn(
        'flex gap-3',
        isUser ? 'flex-row-reverse' : 'flex-row'
      )}>
        <div className={cn(
          'flex-shrink-0 w-8 h-8 rounded-lg flex items-center justify-center',
          isUser
            ? darkMode ? 'bg-[#0e639c]' : 'bg-blue-500'
            : darkMode ? 'bg-[#2d2d30]' : 'bg-gray-100'
        )}>
          {isUser ? (
            <User className="w-4 h-4 text-white" />
          ) : (
            <Bot className={cn('w-4 h-4', darkMode ? 'text-[#cccccc]' : 'text-gray-600')} />
          )}
        </div>
        <div className="flex-1">
          <div className={cn(
            'rounded-lg px-4 py-3',
            isUser
              ? darkMode ? 'bg-[#0e639c] text-white' : 'bg-blue-500 text-white'
              : darkMode ? 'bg-[#2d2d30] text-[#cccccc]' : 'bg-gray-100 text-gray-900'
          )}>
            <p className="text-sm leading-relaxed whitespace-pre-wrap">{message.content}</p>
            {message.code && (
              <div className={cn(
                'mt-3 pt-3 border-t flex items-center justify-between',
                isUser ? 'border-white/20' : darkMode ? 'border-[#3e3e42]' : 'border-gray-200'
              )}>
                <div className={cn(
                  'flex items-center gap-2 text-xs',
                  isUser
                    ? 'text-white/80'
                    : darkMode ? 'text-[#858585]' : 'text-gray-500'
                )}>
                  <CheckCircle2 className="w-3.5 h-3.5" />
                  <span>Code generated</span>
                </div>
                {msgVersion && (
                  <Button
                    onClick={() => onLoadVersion(msgVersion.id)}
                    variant={selectedVersion === msgVersion.id ? 'default' : 'ghost'}
                    size="sm"
                    className="h-6 text-xs px-2"
                  >
                    {selectedVersion === msgVersion.id ? 'Current' : 'View'}
                  </Button>
                )}
              </div>
            )}
          </div>
          {message.timestamp && (
            <div className={cn(
              'text-xs mt-1',
              isUser ? 'text-right' : 'text-left',
              darkMode ? 'text-[#858585]' : 'text-gray-400'
            )}>
              {new Date(message.timestamp).toLocaleTimeString()}
            </div>
          )}
        </div>
      </div>
      {!isUser && (
        <div className="flex items-center gap-2 mt-2 ml-11">
          <Button
            onClick={() => onCopyMessage(message.content)}
            variant="ghost"
            size="sm"
            className="h-8 text-xs px-2"
          >
            <Copy className="w-3 h-3 mr-1" />
            Copy
          </Button>
          <Button
            onClick={() => onRegenerate(message)}
            variant="ghost"
            size="sm"
            className="h-8 text-xs px-2"
          >
            <RefreshCw className="w-3 h-3 mr-1" />
            Regenerate
          </Button>
        </div>
      )}
    </div>
  );
};

export default ChatMessage;
