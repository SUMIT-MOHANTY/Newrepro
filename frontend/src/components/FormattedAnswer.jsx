import React, { useState } from 'react';
import { Check, Copy, PauseCircle, Play } from 'lucide-react';

/**
 * Parses markdown inline formatting:
 * - Bold: **text**
 * - Inline code / tags: `code`
 * - Color chips for hex codes: `#f97316`
 */
function renderInline(text) {
  if (!text) return null;

  // Split by inline code first
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
      const isHexColor = /^#(?:[0-9a-fA-F]{3}){1,2}$/.test(part.content.trim());
      return (
        <span
          key={pIdx}
          className="inline-flex items-center gap-1 font-mono text-[11px] bg-slate-100 dark:bg-slate-800 text-indigo-600 dark:text-indigo-300 px-1.5 py-0.5 rounded-md border border-slate-200 dark:border-slate-700 mx-0.5"
        >
          {isHexColor && (
            <span
              className="inline-block w-2.5 h-2.5 rounded-full border border-black/10 shrink-0"
              style={{ backgroundColor: part.content.trim() }}
            />
          )}
          <span>{part.content}</span>
        </span>
      );
    }

    // Process bold within plain text
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
          <strong key={`${pIdx}-${bIdx}`} className="font-semibold text-slate-900 dark:text-white">
            {bPart.content}
          </strong>
        );
      }
      return <span key={`${pIdx}-${bIdx}`}>{bPart.content}</span>;
    });
  });
}

export default function FormattedAnswer({ text, onContinue = null }) {
  const [copied, setCopied] = useState(false);

  if (!text) return null;

  // Normalize legacy or raw iteration limit stops to clean markdown
  let normalizedText = (text || '').trim();
  const legacyMatch = normalizedText.match(/\[Agent stopped:\s*reached max iterations\s*\((\d+)\)\]/i);
  if (legacyMatch) {
    const maxIter = legacyMatch[1];
    normalizedText = `### Agent Paused — Reached Iteration Limit\n\nThe agent reached the maximum iteration limit (${maxIter} steps) for this task turn.\n\nPlease click the **Continue** button below or enter 'continue' to resume and complete the remaining work.`;
  }

  // Detect whether this is an iteration limit or paused/stopped message asking to continue
  const isStoppedOrLimit =
    normalizedText.includes('Iteration Limit') ||
    normalizedText.includes('reached max iterations') ||
    normalizedText.includes('Execution Paused') ||
    normalizedText.includes('Execution Stopped') ||
    normalizedText.includes('[Agent stopped') ||
    normalizedText.toLowerCase().includes('click the continue button') ||
    normalizedText.toLowerCase().includes('click the **continue** button') ||
    normalizedText.toLowerCase().includes('enter continue') ||
    normalizedText.toLowerCase().includes('type continue');

  const handleCopy = () => {
    navigator.clipboard.writeText(normalizedText);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

// Clean fancy emojis from headers or text to maintain a crisp, straightforward look
function cleanEmojis(str) {
  if (!str) return '';
  return str
    .replace(/[\u{1F300}-\u{1F9FF}]|[\u{2600}-\u{26FF}]|[\u{2700}-\u{27BF}]|[\u{1FA70}-\u{1FAFF}]|[\u{200D}\u{FE0F}]/gu, '')
    .replace(/\s{2,}/g, ' ')
    .trim();
}

// Clean technical file path prefixes from list items (e.g. `**`src/index.css`** - `)
// so bullet points read as high-level functional sentences
function cleanTechnicalFilePrefix(str) {
  if (!str) return '';
  return str
    .replace(/^(?:\*{1,2})?`?(?:src\/[a-zA-Z0-9_\-./]+|[a-zA-Z0-9_\-./]+\.(?:jsx?|tsx?|css|json|html))`?(?:\*{1,2})?\s*[-:–—]\s*/i, '')
    .trim();
}

  // Split lines and group into structured blocks
  const lines = normalizedText.split('\n');
  const blocks = [];
  let currentList = null;

  lines.forEach((rawLine) => {
    const line = rawLine.trim();

    if (!line) {
      if (currentList) {
        blocks.push(currentList);
        currentList = null;
      }
      return;
    }

    // Header 1 / 2 / 3
    if (line.startsWith('### ')) {
      if (currentList) {
        blocks.push(currentList);
        currentList = null;
      }
      blocks.push({ type: 'h3', content: cleanEmojis(line.replace(/^###\s+/, '')) });
      return;
    }
    if (line.startsWith('## ')) {
      if (currentList) {
        blocks.push(currentList);
        currentList = null;
      }
      blocks.push({ type: 'h2', content: cleanEmojis(line.replace(/^##\s+/, '')) });
      return;
    }
    if (line.startsWith('# ')) {
      if (currentList) {
        blocks.push(currentList);
        currentList = null;
      }
      blocks.push({ type: 'h1', content: cleanEmojis(line.replace(/^#\s+/, '')) });
      return;
    }

    // Numbered list item: e.g. "1. **Title**: Description"
    const numMatch = line.match(/^(\d+)\.\s+(.*)$/);
    if (numMatch) {
      if (!currentList || currentList.type !== 'numbered') {
        if (currentList) blocks.push(currentList);
        currentList = { type: 'numbered', items: [] };
      }
      const cleanContent = cleanTechnicalFilePrefix(cleanEmojis(numMatch[2]));
      currentList.items.push({ num: numMatch[1], content: cleanContent });
      return;
    }

    // Bullet item: e.g. "- Item" or "* Item"
    const bulletMatch = line.match(/^[-*]\s+(.*)$/);
    if (bulletMatch) {
      if (!currentList || currentList.type !== 'bullet') {
        if (currentList) blocks.push(currentList);
        currentList = { type: 'bullet', items: [] };
      }
      const cleanContent = cleanTechnicalFilePrefix(cleanEmojis(bulletMatch[1]));
      currentList.items.push(cleanContent);
      return;
    }

    // Standard paragraph
    if (currentList) {
      blocks.push(currentList);
      currentList = null;
    }
    blocks.push({ type: 'p', content: cleanEmojis(line) });
  });

  if (currentList) {
    blocks.push(currentList);
  }

  return (
    <div className="relative group/ans">
      {/* Header bar */}
      <div className="flex items-center justify-between gap-2 pb-1.5 mb-2 border-b border-slate-100 dark:border-slate-800 text-[11px] text-slate-500 dark:text-slate-400">
        <span className="font-semibold text-slate-700 dark:text-slate-300">Summary</span>
        <button
          onClick={handleCopy}
          title="Copy summary"
          className="flex items-center gap-1 text-[10px] px-2 py-0.5 rounded hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-500 dark:text-slate-400 transition-colors cursor-pointer"
        >
          {copied ? <Check className="w-3 h-3 text-emerald-500 shrink-0" /> : <Copy className="w-3 h-3 shrink-0" />}
          <span>{copied ? 'Copied' : 'Copy'}</span>
        </button>
      </div>

      {/* Rendered content */}
      <div className="space-y-2 text-xs text-slate-700 dark:text-slate-200 leading-relaxed font-sans">
        {blocks.map((block, idx) => {
          switch (block.type) {
            case 'h1':
            case 'h2':
              return (
                <h4
                  key={idx}
                  className="font-bold text-[13px] text-slate-900 dark:text-white pt-1 pb-0.5"
                >
                  {renderInline(block.content)}
                </h4>
              );
            case 'h3':
              return (
                <h5
                  key={idx}
                  className="font-semibold text-xs text-slate-800 dark:text-slate-200 pt-0.5"
                >
                  {renderInline(block.content)}
                </h5>
              );
            case 'numbered':
              return (
                <ol key={idx} className="space-y-1 my-1 pl-1">
                  {block.items.map((item, iIdx) => (
                    <li key={iIdx} className="flex items-start gap-2 text-[11.5px]">
                      <span className="w-4 h-4 rounded bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300 font-mono font-medium text-[9px] flex items-center justify-center shrink-0 mt-0.5 border border-slate-200 dark:border-slate-700">
                        {item.num}
                      </span>
                      <div className="flex-1 leading-snug">{renderInline(item.content)}</div>
                    </li>
                  ))}
                </ol>
              );
            case 'bullet':
              return (
                <ul key={idx} className="space-y-1 my-1 pl-1">
                  {block.items.map((item, bIdx) => (
                    <li key={bIdx} className="flex items-start gap-2 text-[11.5px]">
                      <span className="w-1.5 h-1.5 rounded-full bg-slate-400 dark:bg-slate-500 shrink-0 mt-1.5"></span>
                      <div className="flex-1 leading-snug">{renderInline(item)}</div>
                    </li>
                  ))}
                </ul>
              );
            case 'p':
            default:
              return (
                <p key={idx} className="text-[11.5px] leading-relaxed break-words">
                  {renderInline(block.content)}
                </p>
              );
          }
        })}
      </div>

      {/* Interactive Continue Action Banner when Agent Stopped / Reached Limit */}
      {isStoppedOrLimit && (
        <div className="mt-3 p-2.5 rounded-xl border border-amber-300/80 dark:border-amber-700/60 bg-white dark:bg-slate-800/80 shadow-xs flex items-center justify-between gap-2.5 animate-fade-in">
          <div className="flex items-center gap-2 min-w-0">
            <PauseCircle className="w-4 h-4 text-amber-500 shrink-0" />
            <div className="flex flex-col min-w-0">
              <span className="text-[11px] font-bold text-amber-950 dark:text-amber-200 leading-tight">Execution paused at iteration limit</span>
              <span className="text-[9.5px] text-slate-500 dark:text-slate-400 truncate">Click Continue or enter 'continue' to resume</span>
            </div>
          </div>
          <button
            type="button"
            onClick={() => {
              if (typeof onContinue === 'function') onContinue();
              else if (typeof window !== 'undefined') window.__vibeContinueExecution?.();
            }}
            className="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg bg-amber-500 hover:bg-amber-600 active:scale-95 text-white text-[11px] font-semibold transition cursor-pointer shrink-0 shadow-2xs"
          >
            <Play className="w-3.5 h-3.5 shrink-0" />
            <span>Continue</span>
          </button>
        </div>
      )}
    </div>
  );
}
