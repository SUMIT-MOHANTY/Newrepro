import React, { useState } from 'react';
import { User, Bot, CheckCircle2, Copy, RefreshCw, FileText, FileCode, Search, Globe, ChevronDown, ChevronRight } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

// Extract file structure from code
const extractFileStructure = (code) => {
  if (!code) return [];

  const files = [];
  // Match file markers like // FILE: path/to/file.ext
  const fileMarkerRegex = /\/\/\s*FILE:\s*([^\n]+)|#\s*FILE:\s*([^\n]+)|<!--\s*FILE:\s*([^\n]+)\s*-->/g;
  let match;

  while ((match = fileMarkerRegex.exec(code)) !== null) {
    const fileName = (match[1] || match[2] || match[3]).trim();
    const extension = fileName.split('.').pop().toLowerCase();
    files.push({
      name: fileName,
      type: extension === 'html' ? 'html' : extension === 'js' || extension === 'jsx' ? 'js' : 'text'
    });
  }

  // Fallback to old logic if no markers found (legacy support)
  if (files.length === 0) {
    if (code.includes('<!DOCTYPE html>') || code.includes('<html')) {
      files.push({ name: 'index', type: 'html' });
    }
  }

  return files;
};

// Tool Calls Display Component
const ToolCallsDisplay = ({ toolCalls, darkMode }) => {
  const [expandedIdx, setExpandedIdx] = useState(null);

  const getToolInfo = (tool) => {
    switch (tool.tool) {
      case 'web_search':
        return {
          icon: <Search className="w-3.5 h-3.5" />,
          label: 'Web Search',
          detail: tool.arguments?.query || '',
          color: darkMode ? 'text-blue-400' : 'text-blue-600',
          bgColor: darkMode ? 'bg-blue-500/10 border-blue-500/20' : 'bg-blue-50 border-blue-200'
        };
      case 'fetch_page_content':
        return {
          icon: <Globe className="w-3.5 h-3.5" />,
          label: 'Reading Page',
          detail: tool.arguments?.url || '',
          color: darkMode ? 'text-emerald-400' : 'text-emerald-600',
          bgColor: darkMode ? 'bg-emerald-500/10 border-emerald-500/20' : 'bg-emerald-50 border-emerald-200'
        };
      default:
        return {
          icon: <Search className="w-3.5 h-3.5" />,
          label: tool.tool,
          detail: JSON.stringify(tool.arguments || {}),
          color: darkMode ? 'text-gray-400' : 'text-gray-600',
          bgColor: darkMode ? 'bg-gray-500/10 border-gray-500/20' : 'bg-gray-50 border-gray-200'
        };
    }
  };

  // Try to parse result preview for richer display
  const parseResultPreview = (preview) => {
    try {
      const data = JSON.parse(preview.replace(/\.\.\.$/, ''));
      return data;
    } catch {
      return null;
    }
  };

  return (
    <div className="mb-3 space-y-1.5">
      {toolCalls.map((tc, idx) => {
        const info = getToolInfo(tc);
        const isExpanded = expandedIdx === idx;
        const parsed = parseResultPreview(tc.result_preview || '');

        return (
          <div key={idx} className={`rounded-md border text-xs ${info.bgColor}`}>
            <button
              onClick={() => setExpandedIdx(isExpanded ? null : idx)}
              className="w-full flex items-center gap-2 px-2.5 py-1.5 text-left"
            >
              <span className={info.color}>{info.icon}</span>
              <span className={`font-medium ${info.color}`}>{info.label}</span>
              <span className={`flex-1 truncate ${darkMode ? 'text-gray-400' : 'text-gray-500'}`}>
                {info.detail}
              </span>
              {parsed?.status === 'success' && (
                <CheckCircle2 className="w-3 h-3 text-green-500 flex-shrink-0" />
              )}
              {isExpanded
                ? <ChevronDown className={`w-3 h-3 flex-shrink-0 ${darkMode ? 'text-gray-500' : 'text-gray-400'}`} />
                : <ChevronRight className={`w-3 h-3 flex-shrink-0 ${darkMode ? 'text-gray-500' : 'text-gray-400'}`} />
              }
            </button>
            {isExpanded && (
              <div className={`px-2.5 pb-2 pt-1 border-t ${darkMode ? 'border-white/5' : 'border-black/5'}`}>
                {parsed?.results ? (
                  <div className="space-y-1">
                    {parsed.results.slice(0, 3).map((r, i) => (
                      <div key={i} className={`${darkMode ? 'text-gray-300' : 'text-gray-600'}`}>
                        <span className="font-medium">{r.title}</span>
                        {r.snippet && <p className={`${darkMode ? 'text-gray-500' : 'text-gray-400'} line-clamp-1`}>{r.snippet}</p>}
                      </div>
                    ))}
                    {parsed.results_count > 3 && (
                      <p className={`${darkMode ? 'text-gray-500' : 'text-gray-400'} italic`}>
                        +{parsed.results_count - 3} more results
                      </p>
                    )}
                  </div>
                ) : parsed?.title ? (
                  <div className={darkMode ? 'text-gray-300' : 'text-gray-600'}>
                    <p className="font-medium">{parsed.title}</p>
                    {parsed.description && <p className={`${darkMode ? 'text-gray-500' : 'text-gray-400'} line-clamp-2`}>{parsed.description}</p>}
                  </div>
                ) : (
                  <p className={`${darkMode ? 'text-gray-500' : 'text-gray-400'} line-clamp-3`}>
                    {tc.result_preview}
                  </p>
                )}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
};

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

  // Function to clean message content for non-technical users
  const cleanMessageContent = (content) => {
    if (!content || isUser) return content;

    // 1. Remove anything starting from the first // FILE: marker
    let cleaned = content.split(/\/\/\s*FILE:|\/\*\s*FILE:|#\s*FILE:|<!--\s*FILE:/i)[0];

    // 2. Remove code blocks that look like full file contents
    // Usually these are inside the // FILE: sections we already split, 
    // but just in case they aren't, we can do some extra cleaning
    cleaned = cleaned.replace(/```[\s\S]*?```/g, (match) => {
      // If the code block is very long (more than 10 lines), it's probably file content
      if (match.split('\n').length > 10) return '';
      // If it contains markers, it's definitely file content
      if (match.includes('// FILE:')) return '';
      return match;
    });

    return cleaned.trim();
  };

  const displayContent = cleanMessageContent(message.content);

  // If we cleaned EVERYTHING out and there's no narrative, show a default success message
  const finalContent = (!isUser && !displayContent && message.code)
    ? "I've built the application according to your requirements. You can see the preview on the preview section."
    : displayContent;

  return (
    <div className="message-item">
      <div className={cn(
        'flex gap-3',
        isUser ? 'flex-row-reverse' : 'flex-row'
      )}>
        <div className={cn(
          'flex-shrink-0 w-8 h-8 rounded-lg flex items-center justify-center',
          isUser
            ? darkMode ? 'bg-gradient-to-r from-purple-600 to-pink-600' : 'bg-blue-500'
            : darkMode ? 'bg-white/5' : 'bg-gray-100'
        )}>
          {isUser ? (
            <User className="w-4 h-4 text-white" />
          ) : (
            <Bot className={cn('w-4 h-4', darkMode ? 'text-gray-400' : 'text-gray-600')} />
          )}
        </div>
        <div className="flex-1 min-w-0">
          <div className={cn(
            'rounded-lg px-4 py-3',
            isUser
              ? darkMode ? 'bg-gradient-to-r from-purple-600 to-pink-600 text-white' : 'bg-blue-500 text-white'
              : darkMode ? 'bg-white/5 text-gray-200' : 'bg-gray-100 text-gray-900'
          )}>
            {/* Tool Calls Display */}
            {!isUser && message.toolCalls && message.toolCalls.length > 0 && (
              <ToolCallsDisplay toolCalls={message.toolCalls} darkMode={darkMode} />
            )}
            <div className="text-sm leading-relaxed whitespace-pre-wrap break-words markdown-body overflow-x-hidden">
              <ReactMarkdown
                remarkPlugins={[remarkGfm]}
                components={{
                  p: ({ node, ...props }) => <p className="mb-3 last:mb-0 break-words" {...props} />,
                  a: ({ node, ...props }) => <a className="text-blue-500 hover:text-blue-400 hover:underline transition-colors break-words [word-break:break-word]" target="_blank" rel="noreferrer" {...props} />,
                  ul: ({ node, ...props }) => <ul className="list-disc list-outside ml-4 mb-3 space-y-1 break-words" {...props} />,
                  ol: ({ node, ...props }) => <ol className="list-decimal list-outside ml-4 mb-3 space-y-1 break-words" {...props} />,
                  li: ({ node, ...props }) => <li className="pl-1 break-words" {...props} />,
                  h1: ({ node, ...props }) => <h1 className="text-xl font-bold mb-3 mt-5 break-words" {...props} />,
                  h2: ({ node, ...props }) => <h2 className="text-lg font-bold mb-3 mt-4 break-words" {...props} />,
                  h3: ({ node, ...props }) => <h3 className="text-md font-semibold mb-2 mt-3 break-words" {...props} />,
                  strong: ({ node, ...props }) => <strong className="font-semibold" {...props} />,
                  table: ({ node, ...props }) => (
                    <div className="overflow-x-auto mb-4 border rounded-lg border-white/10 dark:border-white/10 border-black/10">
                      <table className="w-full text-sm text-left divide-y divide-white/10 dark:divide-white/10 divide-black/10 break-words" {...props} />
                    </div>
                  ),
                  thead: ({ node, ...props }) => <thead className="bg-black/5 dark:bg-white/5" {...props} />,
                  th: ({ node, ...props }) => <th className="px-4 py-3 font-medium" {...props} />,
                  td: ({ node, ...props }) => <td className="px-4 py-3 border-t border-white/10 dark:border-white/10 border-black/10" {...props} />,
                  code: ({ node, inline, className, children, ...props }) => {
                    const match = /language-(\w+)/.exec(className || '');
                    return inline ? (
                      <code className="bg-black/10 dark:bg-white/10 rounded px-1.5 py-0.5 text-[0.85em] font-mono break-words" {...props}>
                        {children}
                      </code>
                    ) : (
                      <div className="relative mb-4 rounded-lg overflow-hidden bg-[#1E1E2E] dark:bg-[#1E1E2E] border border-white/10">
                        {match && (
                          <div className="flex px-3 py-1.5 bg-[#181825] border-b border-white/10 text-xs text-gray-400 font-medium truncate">
                            {match[1]}
                          </div>
                        )}
                        <pre className="p-3 overflow-x-auto text-[0.85em] leading-relaxed text-gray-300">
                          <code className={className} {...props}>
                            {children}
                          </code>
                        </pre>
                      </div>
                    );
                  },
                  blockquote: ({ node, ...props }) => (
                    <blockquote className="border-l-4 border-blue-500/50 pl-4 py-2 mb-3 text-gray-700 dark:text-gray-300 italic bg-blue-500/5 dark:bg-blue-500/10 rounded-r-lg break-words [word-break:break-word]" {...props} />
                  ),
                  hr: ({ node, ...props }) => <hr className="my-4 border-white/10 dark:border-white/10 border-black/10" {...props} />
                }}
              >
                {finalContent}
              </ReactMarkdown>
            </div>
            {message.code && (
              <>
                {/* File Structure Display */}
                {(() => {
                  const fileStructure = extractFileStructure(message.code);
                  return fileStructure.length > 0 && (
                    <div className={`mt-3 pt-3 border-t ${message.role === 'user'
                      ? 'border-white/20'
                      : darkMode ? 'border-white/10' : 'border-gray-200'
                      }`}>
                      <div className={`flex flex-wrap gap-2 ${message.role === 'user'
                        ? 'text-white/90'
                        : darkMode ? 'text-[#cccccc]' : 'text-gray-700'
                        }`}>
                        {fileStructure.map((file, idx) => (
                          <div
                            key={idx}
                            className={`flex items-center gap-1.5 text-xs px-2 py-1 rounded ${message.role === 'user'
                              ? 'bg-white/10'
                              : darkMode
                                ? 'bg-[#0A0A0F]'
                                : 'bg-white border border-gray-200'
                              }`}
                          >
                            {file.type === 'html' || file.type === 'js' ? (
                              <FileCode className="w-3 h-3" />
                            ) : (
                              <FileText className="w-3 h-3" />
                            )}
                            <span className="font-medium">
                              Wrote {file.name}
                            </span>
                          </div>
                        ))}
                      </div>
                    </div>
                  );
                })()}

                {/* Code Generated Badge */}
                <div className={`mt-3 pt-3 border-t flex items-center justify-between ${message.role === 'user'
                  ? 'border-white/20'
                  : darkMode ? 'border-white/10' : 'border-gray-200'
                  }`}>
                  <div className={`flex items-center gap-2 text-xs ${message.role === 'user'
                    ? 'text-white/80'
                    : darkMode ? 'text-gray-500' : 'text-gray-500'
                    }`}>
                    <CheckCircle2 className="w-3.5 h-3.5" />
                    <span>Code generated</span>
                  </div>
                  {msgVersion && (
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => onLoadVersion(msgVersion.id)}
                      className={`text-xs px-2 py-1 h-auto ${selectedVersion === msgVersion.id
                        ? darkMode
                          ? 'bg-purple-600 text-white hover:bg-purple-700'
                          : 'bg-blue-500 text-white hover:bg-blue-600'
                        : message.role === 'user'
                          ? 'text-white/80 hover:bg-white/10'
                          : darkMode
                            ? 'text-gray-500 hover:bg-white/10'
                            : 'text-gray-500 hover:bg-gray-200'
                        }`}
                    >
                      {selectedVersion === msgVersion.id ? 'Current' : 'View'}
                    </Button>
                  )}
                </div>
              </>
            )}
          </div>
          {message.timestamp && (
            <div className={cn(
              'text-xs mt-1',
              isUser ? 'text-right' : 'text-left',
              darkMode ? 'text-gray-500' : 'text-gray-400'
            )}>
              {new Date(message.timestamp).toLocaleTimeString()}
            </div>
          )}
        </div>
      </div>
      {!isUser && (
        <div className="flex items-center gap-2 mt-2 ml-11">
          {/* <Button
            onClick={() => onCopyMessage(message.content)}
            variant="ghost"
            size="sm"
            className="h-8 text-xs px-2"
          >
            <Copy className="w-3 h-3 mr-1" />
            Copy
          </Button> */}
          {/* <Button
            onClick={() => onRegenerate(message)}
            variant="ghost"
            size="sm"
            className="h-8 text-xs px-2"
          >
            <RefreshCw className="w-3 h-3 mr-1" />
            Regenerate
          </Button> */}
        </div>
      )}
    </div>
  );
};

export default ChatMessage;
