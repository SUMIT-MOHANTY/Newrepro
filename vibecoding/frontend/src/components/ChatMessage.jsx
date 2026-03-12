import React from 'react';
import { User, Bot, CheckCircle2, Copy, RefreshCw } from 'lucide-react';

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

  return (
    <div className="message-item">
      <div className={`flex gap-3 ${message.role === 'user' ? 'flex-row-reverse' : 'flex-row'}`}>
        <div className={`flex-shrink-0 w-8 h-8 rounded-lg flex items-center justify-center ${
          message.role === 'user'
            ? darkMode ? 'bg-[#0e639c]' : 'bg-blue-500'
            : darkMode ? 'bg-[#2d2d30]' : 'bg-gray-100'
        }`}>
          {message.role === 'user' ? (
            <User className="w-4 h-4 text-white" />
          ) : (
            <Bot className={`w-4 h-4 ${darkMode ? 'text-[#cccccc]' : 'text-gray-600'}`} />
          )}
        </div>
        <div className="flex-1">
          <div className={`${
            message.role === 'user'
              ? darkMode
                ? 'bg-[#0e639c] text-white'
                : 'bg-blue-500 text-white'
              : darkMode
                ? 'bg-[#2d2d30] text-[#cccccc]'
                : 'bg-gray-100 text-gray-900'
          } rounded-lg px-4 py-3`}>
            <p className="text-sm leading-relaxed whitespace-pre-wrap">{message.content}</p>
            {message.code && (
              <div className={`mt-3 pt-3 border-t flex items-center justify-between ${
                message.role === 'user'
                  ? 'border-white/20'
                  : darkMode ? 'border-[#3e3e42]' : 'border-gray-200'
              }`}>
                <div className={`flex items-center gap-2 text-xs ${
                  message.role === 'user'
                    ? 'text-white/80'
                    : darkMode ? 'text-[#858585]' : 'text-gray-500'
                }`}>
                  <CheckCircle2 className="w-3.5 h-3.5" />
                  <span>Code generated</span>
                </div>
                {msgVersion && (
                  <button
                    onClick={() => onLoadVersion(msgVersion.id)}
                    className={`text-xs px-2 py-1 rounded transition-colors ${
                      selectedVersion === msgVersion.id
                        ? darkMode
                          ? 'bg-[#0e639c] text-white'
                          : 'bg-blue-500 text-white'
                        : message.role === 'user'
                          ? 'text-white/80 hover:bg-white/10'
                          : darkMode
                            ? 'text-[#858585] hover:bg-[#3e3e42]'
                            : 'text-gray-500 hover:bg-gray-200'
                    }`}
                  >
                    {selectedVersion === msgVersion.id ? 'Current' : 'View'}
                  </button>
                )}
              </div>
            )}
          </div>
          {message.timestamp && (
            <div className={`text-xs mt-1 ${
              message.role === 'user' ? 'text-right' : 'text-left'
            } ${darkMode ? 'text-[#858585]' : 'text-gray-400'}`}>
              {new Date(message.timestamp).toLocaleTimeString()}
            </div>
          )}
        </div>
      </div>
      {message.role === 'assistant' && (
        <div className="flex items-center gap-2 mt-2 ml-11">
          <button 
            onClick={() => onCopyMessage(message.content)}
            className={`text-xs px-2 py-1 rounded-md transition-colors ${
              darkMode 
                ? 'text-[#858585] hover:text-[#cccccc] hover:bg-[#2d2d30]' 
                : 'text-gray-500 hover:text-gray-700 hover:bg-gray-100'
            }`}
          >
            <Copy className="w-3 h-3 inline mr-1" />
            Copy
          </button>
          <button 
            onClick={() => onRegenerate(message)}
            className={`text-xs px-2 py-1 rounded-md transition-colors ${
              darkMode 
                ? 'text-[#858585] hover:text-[#cccccc] hover:bg-[#2d2d30]' 
                : 'text-gray-500 hover:text-gray-700 hover:bg-gray-100'
            }`}
          >
            <RefreshCw className="w-3 h-3 inline mr-1" />
            Regenerate
          </button>
        </div>
      )}
    </div>
  );
};

export default ChatMessage;
