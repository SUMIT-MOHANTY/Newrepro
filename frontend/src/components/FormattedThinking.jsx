import React, { useState, useEffect, useRef } from 'react';
import { Brain, ChevronRight, ChevronDown } from 'lucide-react';

/**
 * Parses inline markdown:
 * - Bold: **text**
 * - Inline code: `code`
 */
function renderInline(text) {
  if (!text) return null;

  const parts = [];
  const codeRegex = /`([^`]+)`/g;
  let lastIdx = 0;
  let match;

  while ((match = codeRegex.exec(text)) !== null) {
    if (match.index > lastIdx) {
      parts.push({ type: 'text', content: text.substring(lastIdx, match.index) });
    }
    parts.push({ type: 'code', content: match[1] });
    lastIdx = match.index + match[0].length;
  }
  if (lastIdx < text.length) {
    parts.push({ type: 'text', content: text.substring(lastIdx) });
  }

  return parts.map((part, pIdx) => {
    if (part.type === 'code') {
      return (
        <code
          key={pIdx}
          className="font-mono text-[10px] text-slate-500 dark:text-slate-400 bg-slate-100 dark:bg-slate-800/80 px-1 py-0.5 rounded border border-slate-200/60 dark:border-slate-700/60 mx-0.5"
        >
          {part.content}
        </code>
      );
    }

    const boldParts = [];
    const boldRegex = /\*\*([^*]+)\*\*/g;
    let bLastIdx = 0;
    let bMatch;

    while ((bMatch = boldRegex.exec(part.content)) !== null) {
      if (bMatch.index > bLastIdx) {
        boldParts.push({ type: 'plain', content: part.content.substring(bLastIdx, bMatch.index) });
      }
      boldParts.push({ type: 'bold', content: bMatch[1] });
      bLastIdx = bMatch.index + bMatch[0].length;
    }
    if (bLastIdx < part.content.length) {
      boldParts.push({ type: 'plain', content: part.content.substring(bLastIdx) });
    }

    return boldParts.map((bPart, bIdx) => {
      if (bPart.type === 'bold') {
        return (
          <span key={`${pIdx}-${bIdx}`} className="font-semibold text-slate-600 dark:text-slate-300">
            {bPart.content}
          </span>
        );
      }
      return <span key={`${pIdx}-${bIdx}`}>{bPart.content}</span>;
    });
  });
}

/**
 * Minimalist FormattedThinking Component
 * Displays 'Thinking...' during generation and 'Thought for Xs' once completed.
 * Features quiet grayed-out light text with structured bullet points and lists.
 */
export default function FormattedThinking({ text, isLive = false, defaultExpanded = false }) {
  const [isExpanded, setIsExpanded] = useState(defaultExpanded);
  const [duration, setDuration] = useState(() => {
    return Math.min(8, Math.max(1, Math.round((text || '').length / 150)));
  });
  const startTimeRef = useRef(Date.now());

  useEffect(() => {
    if (isLive) {
      startTimeRef.current = Date.now();
      const interval = setInterval(() => {
        const secs = Math.max(1, Math.round((Date.now() - startTimeRef.current) / 1000));
        setDuration(secs);
      }, 1000);
      return () => clearInterval(interval);
    } else {
      setDuration((prev) => {
        if (prev && prev > 0) return prev;
        return Math.min(8, Math.max(1, Math.round((text || '').length / 150)));
      });
    }
  }, [isLive, text]);

  if (!text || !text.trim()) return null;

  // Pre-process inline numbered items and bullet points into distinct lines
  const normalizedText = text
    .replace(/([^\n])\s+(\d+\.\s+(?:\*\*)?)/g, '$1\n$2')
    .replace(/([^\n])\s+([–—-]\s+)/g, '$1\n- ')
    .replace(/([^\n])\s+(•\s+)/g, '$1\n- ');

  const rawLines = normalizedText.split('\n');
  const blocks = [];
  let currentList = null;

  rawLines.forEach((rawLine) => {
    const line = rawLine.trim();
    if (!line) {
      if (currentList) {
        blocks.push(currentList);
        currentList = null;
      }
      return;
    }

    // Numbered List: e.g. "1. **Problem**: text" or "1. text"
    const numMatch = line.match(/^(\d+)\.\s+(.*)$/);
    if (numMatch) {
      if (!currentList || currentList.type !== 'numbered') {
        if (currentList) blocks.push(currentList);
        currentList = { type: 'numbered', items: [] };
      }
      currentList.items.push({ num: numMatch[1], content: numMatch[2] });
      return;
    }

    // Bullet Point: e.g. "- item" or "* item" or "• item"
    const bulletMatch = line.match(/^[-*•]\s+(.*)$/);
    if (bulletMatch) {
      if (!currentList || currentList.type !== 'bullet') {
        if (currentList) blocks.push(currentList);
        currentList = { type: 'bullet', items: [] };
      }
      currentList.items.push(bulletMatch[1]);
      return;
    }

    // Headers or Normal Paragraphs
    if (currentList) {
      blocks.push(currentList);
      currentList = null;
    }

    if (line.startsWith('#')) {
      blocks.push({ type: 'header', content: line.replace(/^#{1,3}\s+/, '') });
    } else {
      blocks.push({ type: 'paragraph', content: line });
    }
  });

  if (currentList) {
    blocks.push(currentList);
  }

  const label = isLive ? 'Thinking...' : `Thought for ${duration}s`;

  return (
    <div className="w-full my-1 font-sans">
      {/* Simple Subtle Header */}
      <button
        type="button"
        onClick={() => setIsExpanded(!isExpanded)}
        className="flex items-center gap-1.5 py-0.5 text-[11px] font-medium text-slate-400 dark:text-slate-500 hover:text-slate-600 dark:hover:text-slate-300 transition-colors cursor-pointer select-none bg-transparent border-0 p-0"
      >
        <Brain className={`w-3.5 h-3.5 text-amber-500/80 shrink-0 ${isLive ? 'animate-pulse' : ''}`} />
        <span className="italic">{label}</span>
        {isExpanded ? (
          <ChevronDown className="w-3 h-3 text-slate-400 shrink-0" />
        ) : (
          <ChevronRight className="w-3 h-3 text-slate-400 shrink-0" />
        )}
      </button>

      {/* Clean Grayed-Out Formatted Content */}
      {isExpanded && (
        <div className="mt-1.5 ml-1 pl-2.5 border-l-2 border-slate-200 dark:border-slate-800 space-y-1.5 text-[11px] text-slate-400 dark:text-slate-500 leading-relaxed">
          {blocks.map((block, idx) => {
            switch (block.type) {
              case 'header':
                return (
                  <div key={idx} className="font-semibold text-slate-500 dark:text-slate-400 pt-1">
                    {renderInline(block.content)}
                  </div>
                );

              case 'numbered':
                return (
                  <div key={idx} className="space-y-1 my-0.5">
                    {block.items.map((item, iIdx) => (
                      <div key={iIdx} className="flex items-start gap-1.5">
                        <span className="font-mono text-slate-400 dark:text-slate-500 shrink-0 select-none">
                          {item.num}.
                        </span>
                        <div className="flex-1 leading-relaxed">
                          {renderInline(item.content)}
                        </div>
                      </div>
                    ))}
                  </div>
                );

              case 'bullet':
                return (
                  <div key={idx} className="space-y-0.5 my-0.5">
                    {block.items.map((item, bIdx) => (
                      <div key={bIdx} className="flex items-start gap-2 pl-1">
                        <span className="text-slate-300 dark:text-slate-600 select-none shrink-0">•</span>
                        <div className="flex-1 leading-relaxed">
                          {renderInline(item)}
                        </div>
                      </div>
                    ))}
                  </div>
                );

              case 'paragraph':
              default:
                return (
                  <p key={idx} className="leading-relaxed">
                    {renderInline(block.content)}
                  </p>
                );
            }
          })}
        </div>
      )}
    </div>
  );
}
