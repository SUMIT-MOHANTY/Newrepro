import React, { useState, useEffect } from 'react';
import { User, Sparkles, History, CheckCircle2, Copy, RefreshCw, FileText, FileCode, Search, Globe, ChevronDown, ChevronRight } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Button } from './ui/button';
import { cn } from '@/lib/utils';
import TaskBreakdown from './TaskBreakdown';
import ThinkingBlock from './ThinkingBlock';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '/vibecoding';

// Extract functional summary from content (business logic context)
const extractFunctionalSummary = (content) => {
  if (!content) return '';

  // Extract everything before the first file marker or code block
  let summary = content.split(/(?:\/\/|#|<!--)\s*FILE:/i)[0];

  // Also split by common code block markers if there are no FILE markers
  if (summary.includes('```')) {
    summary = summary.split('```')[0];
  }

  // Clean up any trailing headers that might define the technical section
  summary = summary.replace(/###?\s*(Updates?|Technicals?|Implementation|Code|Changes|Files).*$/i, '');

  // Strip common generic success messages that aren't useful as summaries
  summary = summary.replace(/^(Done|Success|Updated|Changes applied|Implemented|Successfully implemented)[!.]*\s*(Your request has been incorporated|The changes are complete|your requested changes with a focus on functional stability)[!.]*/i, '');

  return summary.trim();
};

// Extract file structure from code — deduped and cleaned
const extractFileStructure = (code) => {
  if (!code) return [];

  const isPatchResponse = /\/\/\s*PATCH:\s*/.test(code);

  // For patch responses, extract patched file names from PATCH headers
  if (isPatchResponse) {
    const patchFiles = new Map();
    const patchRegex = /\/\/\s*PATCH:\s*([^\n<]+)/g;
    let match;
    while ((match = patchRegex.exec(code)) !== null) {
      const raw = match[1].trim();
      const cleaned = raw.replace(/\s*\(Updated\)\s*$/i, '').trim();
      if (cleaned && !patchFiles.has(cleaned)) {
        const ext = cleaned.split('.').pop().toLowerCase();
        patchFiles.set(cleaned, {
          name: cleaned,
          type: ext === 'html' ? 'html' : (ext === 'js' || ext === 'jsx') ? 'js' : 'text'
        });
      }
    }
    if (patchFiles.size > 0) return [...patchFiles.values()];
  }

  // For FILE-based responses, extract and deduplicate
  const fileMap = new Map();
  const fileMarkerRegex = /\/\/\s*FILE:\s*([^\n]+)|#\s*FILE:\s*([^\n]+)|<!--\s*FILE:\s*([^\n]+)\s*-->/g;
  let match;

  while ((match = fileMarkerRegex.exec(code)) !== null) {
    const raw = (match[1] || match[2] || match[3]).trim();
    const cleaned = raw.replace(/\s*\(Updated\)\s*$/i, '').trim();
    if (!cleaned || cleaned === 'metadata.json') continue;
    const extension = cleaned.split('.').pop().toLowerCase();
    fileMap.set(cleaned, {
      name: cleaned,
      type: extension === 'html' ? 'html' : (extension === 'js' || extension === 'jsx') ? 'js' : 'text'
    });
  }

  if (fileMap.size > 0) return [...fileMap.values()];

  // Fallback to old logic if no markers found (legacy support)
  if (code.includes('<!DOCTYPE html>') || code.includes('<html')) {
    return [{ name: 'index.html', type: 'html' }];
  }

  return [];
};

// Tool Calls Display Component
const ToolCallsDisplay = ({ toolCalls, darkMode }) => {
  const [expandedIdx, setExpandedIdx] = useState(null);

  const getToolInfo = (tool) => {
    switch (tool.tool) {
      case 'web_search':
        return {
          icon: <Globe className="w-3.5 h-3.5" />,
          label: 'Web Search',
          detail: tool.arguments?.query || '',
          color: darkMode ? 'text-purple-400' : 'text-purple-600',
          bgColor: darkMode ? 'bg-purple-500/10 border-purple-500/20' : 'bg-purple-50 border-purple-200'
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
                  <>
                    <div className="flex items-start justify-between gap-3 px-1 pb-2">
                      <div className="min-w-0">
                        <div className="flex items-center gap-2">
                          <Globe className={`w-4 h-4 ${darkMode ? 'text-purple-400' : 'text-purple-600'} flex-shrink-0`} />
                          <span className={`text-xs font-semibold ${darkMode ? 'text-purple-300' : 'text-purple-800'} truncate`}>
                            Web search:
                          </span>
                          <span className={`text-xs ${darkMode ? 'text-gray-300' : 'text-gray-600'} truncate`}>
                            {parsed.query || tc.arguments?.query || info.detail || ''}
                          </span>
                        </div>
                      </div>
                      {typeof parsed.results_count === 'number' && (
                        <span className={`text-xs ${darkMode ? 'text-gray-500' : 'text-gray-500'} whitespace-nowrap`}>
                          {parsed.results_count} results
                        </span>
                      )}
                    </div>

                    <div className="space-y-1">
                      {parsed.results.slice(0, 3).map((r, i) => (
                        <div key={i} className={`rounded-md px-2 py-1 ${darkMode ? 'bg-white/5' : 'bg-black/5'}`}>
                          <span className={`block text-xs font-semibold ${darkMode ? 'text-purple-300' : 'text-purple-700'} leading-snug`}>
                            {r.title}
                          </span>
                          {r.snippet && (
                            <p className={`${darkMode ? 'text-purple-200/80' : 'text-purple-900/70'} text-xs line-clamp-2`}>
                              {r.snippet}
                            </p>
                          )}
                        </div>
                      ))}
                      {parsed.results_count > 3 && (
                        <p className={`${darkMode ? 'text-gray-500' : 'text-gray-400'} italic text-xs px-1`}>
                          +{parsed.results_count - 3} more results
                        </p>
                      )}
                    </div>
                  </>
                ) : parsed?.title ? (
                  <div className={darkMode ? 'text-gray-300' : 'text-gray-600'}>
                    <p className="font-medium">{parsed.title}</p>
                    {parsed.description && <p className={`${darkMode ? 'text-gray-500' : 'text-gray-400'} line-clamp-2`}>{parsed.description}</p>}
                  </div>
                ) : (
                  tc.tool === 'web_search' ? (
                    <p className={`${darkMode ? 'text-gray-500' : 'text-gray-400'} line-clamp-3`}>
                      Web search results unavailable.
                    </p>
                  ) : tc.tool === 'fetch_page_content' ? (
                    <p className={`${darkMode ? 'text-gray-500' : 'text-gray-400'} line-clamp-3`}>
                      Reading page preview unavailable.
                    </p>
                  ) : (
                    <p className={`${darkMode ? 'text-gray-500' : 'text-gray-400'} line-clamp-3`}>
                      {tc.result_preview}
                    </p>
                  )
                )}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
};


// In-memory cache to prevent re-summarizing same message on re-mounts
const summaryCache = new Map();

const ChatMessage = ({
  message,
  darkMode,
  codeVersions,
  selectedVersion,
  onLoadVersion,
  onCopyMessage,
  onRegenerate,
  onSuggestionClick,
  onExecuteTask,
  onExecuteAllTasks,
  onEditTask,
  executingTaskId
}) => {
  // Debug: Log message to see what we're receiving
  if (!message.role || message.role === 'assistant') {
    console.log('ChatMessage rendering:', {
      role: message.role,
      hasMetadata: !!message.metadata,
      hasTaskPlan: !!message.metadata?.task_plan,
      metadataType: message.metadata?.type,
      content: message.content?.substring(0, 100)
    });
  }
  // Dynamic time formatter (e.g., "just now", "5 mins ago")
  const getRelativeTime = (timestamp) => {
    if (!timestamp) return '';
    try {
      const date = new Date(timestamp);
      const now = new Date();
      const diffMs = now - date;
      const diffSecs = Math.floor(diffMs / 1000);
      const diffMins = Math.floor(diffSecs / 60);
      const diffHours = Math.floor(diffMins / 60);
      const diffDays = Math.floor(diffHours / 24);

      if (diffSecs < 10) return 'just now';
      if (diffSecs < 60) return `${diffSecs}s ago`;
      if (diffMins < 60) return `${diffMins}m ago`;
      if (diffHours < 24) return `${diffHours}h ago`;
      if (diffDays < 7) return `${diffDays}d ago`;
      return date.toLocaleDateString();
    } catch (e) {
      return '';
    }
  };

  const isUser = message.role === 'user';
  const [msgVersion, setMsgVersion] = useState(null);
  // Normalise summary from multiple possible fields (DB snake_case or Frontend camelCase)
  const initialSummary = message.summary || message.ai_summary || summaryCache.get(message.id) || '';
  const [aiSummary, setAiSummary] = useState(initialSummary);
  const [showOriginal, setShowOriginal] = useState(false);
  const [isSummarizing, setIsSummarizing] = useState(false);
  const [relativeTime, setRelativeTime] = useState(getRelativeTime(message.timestamp));

  // Keep aiSummary in sync with message props (CRITICAL for immediate reflection after API response)
  useEffect(() => {
    const currentSummary = message.summary || message.ai_summary;
    if (currentSummary && currentSummary !== aiSummary) {
      setAiSummary(currentSummary);
    }
  }, [message.summary, message.ai_summary]);

  // Update relative time periodically (every minute)
  useEffect(() => {
    if (!message.timestamp) return;
    const interval = setInterval(() => {
      setRelativeTime(getRelativeTime(message.timestamp));
    }, 60000); // refresh every minute
    return () => clearInterval(interval);
  }, [message.timestamp]);

  // AI Summary is now provided by the backend automatically when messages are fetched.
  // The frontend no longer needs to call /api/summarize manually.

  // Find the commit that matches this message's versionId (commit hash)
  // Ensure we check both versionId and version_id for compatibility
  useEffect(() => {
    const vId = message.versionId || message.version_id;
    if (vId && codeVersions) {
      const commit = codeVersions.find(c => c.hash === vId);
      if (commit) setMsgVersion(commit);
    }
  }, [message.versionId, message.version_id, codeVersions]);


  // Function to clean message content for non-technical users
  const cleanMessageContent = (content) => {
    if (!content || isUser) return content;

    // 1. Remove anything starting from the first // FILE: or // PATCH: marker
    let cleaned = content.split(/\/\/\s*FILE:|\/\*\s*FILE:|#\s*FILE:|<!--\s*FILE:|\/\/\s*PATCH:/i)[0];

    // 2. Strip any stray patch syntax (<<<SEARCH, >>>, <<<REPLACE)
    cleaned = cleaned.replace(/<<<SEARCH[\s\S]*?>>>/g, '');
    cleaned = cleaned.replace(/<<<REPLACE[\s\S]*?>>>/g, '');

    // 3. Remove task lists (bullet points) since we display them separately
    const lines = cleaned.split('\n');
    const nonTaskLines = [];
    for (const line of lines) {
      const trimmed = line.trim();
      // Skip bullet points and numbered lists
      if (!trimmed.match(/^[•\-\*]\s+/) && !trimmed.match(/^\d+\.\s+/)) {
        nonTaskLines.push(line);
      }
    }
    cleaned = nonTaskLines.join('\n');

    // 4. Remove code blocks that look like full file contents
    cleaned = cleaned.replace(/```[\s\S]*?```/g, (match) => {
      if (match.split('\n').length > 10) return '';
      if (match.includes('// FILE:')) return '';
      return match;
    });

    // 5. Strip common technical placeholders and generic success messages
    cleaned = cleaned.replace(/^(Done|Success|Updated|Changes applied|Implemented|Successfully implemented)[!.]*\s*(Your request has been incorporated|The changes are complete|your requested changes with a focus on functional stability)[!.]*/i, '');

    return cleaned.trim();
  };

  const displayContent = cleanMessageContent(message.content);

  // If summary is the same as content, we'll only show it in the Outcome box
  const functionalSummary = extractFunctionalSummary(message.content);

  // Decide what to show in the main markdown area to avoid redundancy (Assistant messages only)
  let markdownContent = displayContent;
  if (!isUser && message.code) { // Only hide if we have an Outcome box (code mode)
    if (markdownContent === functionalSummary) {
      markdownContent = ''; // No need to repeat the summary
    } else if (markdownContent.startsWith(functionalSummary)) {
      markdownContent = markdownContent.substring(functionalSummary.length).trim();
    }
  }

  const successTitle = "Implementation complete";
  const availableSummary = aiSummary || functionalSummary;

  // Decide what to show as the primary content
  let finalContent = markdownContent;
  const hasCodeOrVersion = message.code || message.versionId || message.version_id;
  
  if (!isUser && hasCodeOrVersion) {
    // If we have a curated AI summary, use it as the primary content to avoid boilerplates.
    if (aiSummary) {
      finalContent = aiSummary;
    } else if (!finalContent?.trim() || finalContent === functionalSummary || finalContent.length < 5) {
      finalContent = functionalSummary || successTitle;
    }
  }

  // Only show the internal summary box if we have a summary that isn't already the main content.
  const showSummaryBox = isSummarizing || (availableSummary && finalContent !== availableSummary && finalContent !== aiSummary);

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
            <Sparkles className={cn('w-4 h-4', darkMode ? 'text-gray-400' : 'text-gray-600')} />
          )}
        </div>
        <div className="flex-1 min-w-0 max-w-full overflow-hidden">
          <div className={cn(
            'rounded-lg px-4 py-3 break-words overflow-hidden',
            isUser
              ? darkMode ? 'bg-gradient-to-r from-purple-600 to-pink-600 text-white' : 'bg-blue-500 text-white'
              : darkMode ? 'bg-white/5 text-gray-200' : 'bg-gray-100 text-gray-900'
          )}>
            {/* Attached Images */}
            {isUser && message.images && message.images.length > 0 && (
              <div className="mb-2 flex flex-wrap gap-2">
                {message.images.map((src, idx) => (
                  <img
                    key={idx}
                    src={src}
                    alt={`Attachment ${idx + 1}`}
                    className="max-w-[200px] max-h-[160px] rounded-md object-cover border border-white/20"
                  />
                ))}
              </div>
            )}
            {/* Tool Calls Display */}
            {!isUser && message.toolCalls && message.toolCalls.length > 0 && (
              <ToolCallsDisplay toolCalls={message.toolCalls} darkMode={darkMode} />
            )}
            
            {/* Inline Thinking Block - Shows accumulated thinking logs */}
            {!isUser && message.thinkingLogs && message.thinkingLogs.length > 0 && (
              <div className="mb-3">
                <ThinkingBlock
                  logs={message.thinkingLogs}
                  status={message.isThinking ? 'thinking' : 'success'}
                  title={message.isThinking ? 'Building you app...' : 'Background execution completed'}
                  darkMode={darkMode}
                  autoScroll={message.isThinking}
                />
              </div>
            )}
            
            {/* Task Breakdown Display */}
            {!isUser && message.metadata?.task_plan && (
              <>
                {console.log('TaskBreakdown metadata:', message.metadata)}
                <TaskBreakdown
                  taskPlan={message.metadata.task_plan}
                  darkMode={darkMode}
                  onExecuteTask={onExecuteTask}
                  onExecuteAll={onExecuteAllTasks}
                  onEditTask={onEditTask}
                  executingTaskId={executingTaskId}
                />
              </>
            )}
            
            {/* Task Breakdown Display - for planning/thinking messages */}
            {!isUser && !message.metadata?.task_plan && (() => {
              // Parse content for task lists
              const lines = (message.content || '').split('\n');
              const tasks = [];
              let introText = '';
              let foundTasks = false;
              
              for (const line of lines) {
                const trimmed = line.trim();
                if (trimmed.match(/^[•\-\*]\s+/) || trimmed.match(/^\d+\.\s+/)) {
                  foundTasks = true;
                  const taskText = trimmed.replace(/^[•\-\*]\s+/, '').replace(/^\d+\.\s+/, '');
                  tasks.push(taskText);
                } else if (trimmed && !foundTasks) {
                  introText += (introText ? ' ' : '') + trimmed;
                }
              }
              
              // Only show task breakdown if we have tasks
              if (tasks.length > 0) {
                return (
                  <div className="mb-3">
                    {introText && (
                      <p className={cn(
                        "text-sm mb-3 font-medium",
                        darkMode ? "text-gray-300" : "text-gray-700"
                      )}>
                        {introText}
                      </p>
                    )}
                    <div className={cn(
                      "rounded-lg border p-3 space-y-2",
                      darkMode 
                        ? "bg-purple-500/5 border-purple-500/20" 
                        : "bg-purple-50 border-purple-200"
                    )}>
                      {tasks.map((task, idx) => (
                        <div key={idx} className="flex items-start gap-2">
                          <CheckCircle2 className={cn(
                            "w-4 h-4 mt-0.5 flex-shrink-0",
                            darkMode ? "text-purple-400" : "text-purple-600"
                          )} />
                          <span className={cn(
                            "text-sm",
                            darkMode ? "text-gray-200" : "text-gray-800"
                          )}>
                            {task}
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                );
              }
              return null;
            })()}
            
            {/* Chat Content */}
            {!isUser && aiSummary && !showOriginal && hasCodeOrVersion && !message.metadata?.task_plan ? (
              <div className="flex flex-col gap-3 py-1">
                <div className="flex items-center gap-2 text-xs font-semibold text-blue-500/80 uppercase tracking-wider">
                  <Sparkles className="w-3 h-3" />
                  <span>Agent Outcome Summary</span>
                </div>
                <p className={cn(
                  "text-[0.95rem] leading-relaxed font-medium italic",
                  darkMode ? "text-blue-100/90" : "text-blue-900/90"
                )}>
                  {aiSummary}
                </p>
                <button
                  onClick={() => setShowOriginal(true)}
                  className={cn(
                    "w-fit text-[10px] font-medium uppercase tracking-tighter opacity-40 hover:opacity-100 transition-opacity flex items-center gap-1 mt-1",
                    darkMode ? "text-gray-400" : "text-gray-600"
                  )}
                >
                  <ChevronDown className="w-2.5 h-2.5" />
                  View Raw AI Log
                </button>
              </div>
            ) : (
              <div className="text-sm leading-relaxed whitespace-pre-wrap break-words markdown-body overflow-x-hidden">
                {!isUser && aiSummary && showOriginal && hasCodeOrVersion && (
                  <button
                    onClick={() => setShowOriginal(false)}
                    className={cn(
                      "mb-3 text-[10px] font-medium uppercase tracking-tighter opacity-60 hover:opacity-100 transition-opacity flex items-center gap-1",
                      darkMode ? "text-blue-400" : "text-blue-600"
                    )}
                  >
                    <Sparkles className="w-2.5 h-2.5" />
                    Back to Summary
                  </button>
                )}
                <ReactMarkdown
                remarkPlugins={[remarkGfm]}
                components={{
                  p: ({ node, ...props }) => <div className="mb-3 last:mb-0 break-words" {...props} />,
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
                      <code className={`rounded px-1.5 py-0.5 text-[0.85em] font-mono break-words ${darkMode ? 'bg-white/10 text-gray-200' : 'bg-black/5 text-gray-800'
                        }`} {...props}>
                        {children}
                      </code>
                    ) : (
                      <div className={`relative mb-4 rounded-lg overflow-hidden border ${darkMode ? 'bg-[#1E1E2E] border-white/10' : 'bg-[#f8f8f8] border-gray-200'
                        }`}>
                        {match && (
                          <div className={`flex px-3 py-1.5 border-b text-xs font-medium truncate ${darkMode ? 'bg-[#181825] border-white/10 text-gray-400' : 'bg-gray-100 border-gray-200 text-gray-500'
                            }`}>
                            {match[1]}
                          </div>
                        )}
                        <pre className={`p-3 overflow-x-auto text-[0.85em] leading-relaxed ${darkMode ? 'text-gray-300' : 'text-gray-700'
                          }`}>
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
                {showOriginal ? message.content : finalContent}
              </ReactMarkdown>
            </div>
          )}
          {message.code && (
              <>
                {/* File Structure Display */}
                {(() => {
                  const fileStructure = extractFileStructure(message.code);
                  if (fileStructure.length === 0) return null;
                  return (
                    <div className={`mt-3 ${message.role === 'user' ? '' : ''}`}>
                      {showSummaryBox && (
                        <div className={`mt-3 overflow-hidden rounded-2xl border transition-all duration-500 group/insights ${darkMode
                          ? 'bg-gradient-to-br from-purple-500/10 via-purple-500/5 to-transparent border-purple-500/20 shadow-[0_4px_20px_rgba(168,85,247,0.1)]'
                          : 'bg-gradient-to-br from-blue-50/80 via-white to-white border-blue-100 shadow-[0_4px_15px_rgba(59,130,246,0.05)]'
                          }`}>
                          <div className="p-4 px-5">
                            {isSummarizing ? (
                              <div className="space-y-2">
                                <div className={`h-3 w-3/4 rounded animate-pulse ${darkMode ? 'bg-white/5' : 'bg-gray-100'}`} />
                                <div className={`h-3 w-full rounded animate-pulse ${darkMode ? 'bg-white/5' : 'bg-gray-100'}`} />
                                <div className={`h-3 w-1/2 rounded animate-pulse ${darkMode ? 'bg-white/5' : 'bg-gray-100'}`} />
                              </div>
                            ) : (
                              <p className={`text-sm leading-relaxed font-medium transition-colors ${darkMode ? 'text-gray-300 group-hover/insights:text-white' : 'text-gray-700 group-hover/insights:text-gray-900'
                                }`}>
                                {aiSummary || functionalSummary}
                              </p>
                            )}
                          </div>
                        </div>
                      )}

                      <details className="group">
                        <summary className={`flex items-center gap-2 text-[10px] font-bold uppercase tracking-widest cursor-pointer select-none mb-2 ${message.role === 'user' ? 'text-white/60' : 'text-gray-500'
                          }`}>
                          <ChevronRight className="w-3 h-3 transition-transform group-open:rotate-90" />
                          System Trace ({fileStructure.length} components updated)
                        </summary>
                        <div className={`flex flex-wrap gap-2 ${message.role === 'user'
                          ? 'text-white/90'
                          : darkMode ? 'text-[#cccccc]' : 'text-gray-700'
                          }`}>
                          {fileStructure.map((file, idx) => (
                            <div
                              key={idx}
                              className={`flex items-center gap-1.5 text-xs px-2.5 py-1.5 rounded-lg font-medium transition-all ${message.role === 'user'
                                ? 'bg-white/10 text-white'
                                : darkMode
                                  ? 'bg-[#0A0A0F] text-gray-300 border border-white/5'
                                  : 'bg-gray-50 text-gray-700 border border-gray-200 shadow-sm'
                                }`}
                            >
                              {file.type === 'html' || file.type === 'js' ? (
                                <FileCode className={`w-3.5 h-3.5 flex-shrink-0 ${darkMode ? 'text-purple-400' : 'text-purple-600'}`} />
                              ) : (
                                <FileText className={`w-3.5 h-3.5 flex-shrink-0 ${darkMode ? 'text-blue-400' : 'text-blue-600'}`} />
                              )}
                              <span className="break-all">Updated <span className="font-bold">{file.name}</span></span>
                            </div>
                          ))}
                        </div>
                      </details>
                    </div>
                  );
                })()}

                {/* Code Generated Badge */}
                <div className={`mt-3 pt-3 border-t flex items-center justify-end ${message.role === 'user'
                  ? 'border-white/20'
                  : darkMode ? 'border-white/10' : 'border-gray-200'
                  }`}>
                  {(msgVersion || message.versionId || message.version_id) && (
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => onLoadVersion(msgVersion?.hash || message.versionId || message.version_id)}
                      className={`text-xs px-3 py-1.5 h-auto rounded-lg font-bold transition-all shadow-sm ${selectedVersion === (msgVersion?.hash || message.versionId || message.version_id)
                        ? (darkMode ? 'bg-purple-500/20 text-purple-400 border border-purple-500/30' : 'bg-blue-50 text-blue-600 border border-blue-200')
                        : (darkMode ? 'bg-white/5 text-gray-400 hover:text-white border border-white/10 hover:border-white/20' : 'bg-gray-50 text-gray-600 hover:bg-gray-100 border border-gray-200')
                        }`}
                    >
                      <History className="w-3.5 h-3.5 mr-2 opacity-70" />
                      {selectedVersion === (msgVersion?.hash || message.versionId || message.version_id) ? 'Active Version' : 'View Version'}
                    </Button>
                  )}
                </div>
              </>
            )}
          </div>
        </div>
      </div>

      {/* Suggestions - Only show for assistant messages */}
      {!isUser && message.suggestions && message.suggestions.length > 0 && (
        <div className="mt-3 ml-11 space-y-2">
          <div className={cn(
            'text-xs font-medium mb-2',
            darkMode ? 'text-gray-400' : 'text-gray-500'
          )}>
            Try these next:
          </div>
          <div className="flex flex-col gap-2">
            {message.suggestions.map((suggestion, idx) => {
              // Handle both string and object suggestions
              const suggestionText = typeof suggestion === 'string' ? suggestion : suggestion.text;
              const suggestionIcon = typeof suggestion === 'object' && suggestion.icon ? suggestion.icon : null;
              const suggestionPrompt = typeof suggestion === 'object' && suggestion.prompt ? suggestion.prompt : suggestionText;
              
              return (
                <button
                  key={idx}
                  onClick={() => onSuggestionClick && onSuggestionClick(suggestionPrompt)}
                  className={cn(
                    'text-left px-3 py-2.5 rounded-lg text-xs transition-all border shadow-sm',
                    darkMode
                      ? 'bg-white/5 hover:bg-white/10 text-gray-300 border-white/10 hover:border-purple-500/50'
                      : 'bg-white hover:bg-gray-50 text-gray-900 border-gray-200 hover:border-blue-400'
                  )}
                >
                  <div className="flex items-center gap-2.5">
                    <div className={`w-6 h-6 rounded-md flex items-center justify-center ${darkMode ? 'bg-purple-500/20 text-purple-400' : 'bg-blue-500/10 text-blue-600'
                      }`}>
                      {suggestionIcon ? (
                        <span className="text-sm">{suggestionIcon}</span>
                      ) : (
                        <Sparkles className="w-3.5 h-3.5" />
                      )}
                    </div>
                    <span className="leading-relaxed font-medium">{suggestionText}</span>
                  </div>
                </button>
              );
            })}
          </div>
        </div>
      )}

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
