import React, { useState, useRef, useEffect } from 'react';

/**
 * ContextTracker Component
 * 
 * Displays a live radial SVG progress circle tracking agent dynamic context tokens.
 * On hover/click, shows a minimal, clean tooltip with strictly:
 * - Completed/Used tokens
 * - Remaining tokens
 * - Usage percentage & Tier
 */
export default function ContextTracker({ tokenUsage, size = 'md', align = 'center' }) {
  const [isOpen, setIsOpen] = useState(false);
  const containerRef = useRef(null);

  const inputTokens = tokenUsage?.inputTokens || tokenUsage?.input_tokens || tokenUsage?.prompt_tokens || 0;
  const contextWindow = Math.max(tokenUsage?.contextWindow || tokenUsage?.context_window || 128000, 128000);

  // Ground truth context usage ratio
  const usageRatio = Math.min(Math.max(inputTokens / contextWindow, 0), 1);
  const percentage = Math.round(usageRatio * 100);

  // SVG circular geometry
  const radius = 14;
  const circumference = 2 * Math.PI * radius;
  const strokeDashoffset = circumference - (usageRatio * circumference);
  const strokeDasharray = usageRatio === 0 ? `0 ${circumference}` : `${circumference}`;

  // Status color logic for the progress ring
  let strokeColor = '#10b981'; // Emerald (<50%)
  if (percentage >= 80) {
    strokeColor = '#ef4444'; // Rose (>=80%)
  } else if (percentage >= 50) {
    strokeColor = '#f59e0b'; // Amber (50%-79%)
  }

  // Close when clicking outside
  useEffect(() => {
    const handleClickOutside = (e) => {
      if (containerRef.current && !containerRef.current.contains(e.target)) {
        setIsOpen(false);
      }
    };
    if (isOpen) {
      document.addEventListener('mousedown', handleClickOutside);
    }
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [isOpen]);

  const remainingTokens = Math.max(contextWindow - inputTokens, 0);

  const dimensionClasses = size === 'sm' 
    ? 'w-[28px] h-[28px]' 
    : size === 'xs' 
      ? 'w-5 h-5' 
      : 'w-[34px] h-[34px]';
  const textClasses = size === 'sm' 
    ? 'text-[8px]' 
    : size === 'xs' 
      ? 'text-[7px]' 
      : 'text-[9.5px]';

  return (
    <div
      ref={containerRef}
      className="relative inline-flex items-center shrink-0"
      onMouseEnter={() => setIsOpen(true)}
      onMouseLeave={() => setIsOpen(false)}
    >
      {/* Interactive Radial Meter Circle */}
      <button
        type="button"
        onClick={() => setIsOpen(!isOpen)}
        className={`relative ${dimensionClasses} rounded-full flex items-center justify-center transition-transform duration-200 hover:scale-105 active:scale-95 cursor-pointer shadow-2xs group ${
          percentage >= 85 ? 'animate-pulse' : ''
        }`}
        title={`Context Window: ${percentage}% (${inputTokens.toLocaleString()} / ${contextWindow.toLocaleString()} tokens)`}
      >
        {/* SVG Circle: starts at North (12 o'clock / top) and grows clockwise: East -> South -> West */}
        <svg
          className="w-full h-full"
          viewBox="0 0 36 36"
        >
          {/* Subtle inner circular fill */}
          <circle
            cx="18"
            cy="18"
            r={radius - 1.5}
            className="fill-slate-50 dark:fill-[#121620]"
          />
          {/* Background Track Circle */}
          <circle
            cx="18"
            cy="18"
            r={radius}
            fill="none"
            stroke="currentColor"
            strokeWidth="2.8"
            className="text-slate-200 dark:text-slate-700/80"
          />
          {/* Active Context Usage Stroke */}
          <circle
            cx="18"
            cy="18"
            r={radius}
            fill="none"
            stroke={strokeColor}
            strokeWidth="3"
            strokeLinecap="round"
            strokeDasharray={strokeDasharray}
            strokeDashoffset={strokeDashoffset}
            transform="rotate(-90 18 18)"
            className="transition-all duration-700 ease-out"
          />
        </svg>

        {/* Center Percentage Display */}
        <span
          className={`absolute inset-0 flex items-center justify-center font-mono font-bold leading-none select-none tabular-nums tracking-tighter ${textClasses}`}
          style={{ color: strokeColor }}
        >
          {percentage > 0 ? `${percentage}%` : '•'}
        </span>
      </button>

      {/* Sleek Floating Popover */}
      {isOpen && (
        <div
          className={`absolute top-full mt-2 whitespace-nowrap px-3.5 py-2.5 rounded-xl bg-white/95 dark:bg-[#161922]/95 backdrop-blur-md border border-slate-200 dark:border-slate-800 shadow-xl z-50 animate-in fade-in zoom-in-95 duration-150 text-[11px] text-slate-800 dark:text-slate-100 flex flex-col gap-1.5 pointer-events-none min-w-[170px] ${
            align === 'right'
              ? 'right-0'
              : align === 'left'
                ? 'left-0'
                : 'left-1/2 -translate-x-1/2'
          }`}
        >
          <div className="flex items-center justify-between gap-4 font-semibold pb-1.5 border-b border-slate-100 dark:border-slate-800 text-[10px] text-slate-400 uppercase tracking-wider">
            <span>Context Window</span>
            <span style={{ color: strokeColor }} className="font-bold">{percentage}%</span>
          </div>
          <div className="flex items-center justify-between gap-4 font-mono">
            <span className="text-slate-500 dark:text-slate-400 font-sans">Used Tokens:</span>
            <span className="font-bold tabular-nums">{inputTokens.toLocaleString()}</span>
          </div>
          <div className="flex items-center justify-between gap-4 font-mono">
            <span className="text-slate-500 dark:text-slate-400 font-sans">Remaining:</span>
            <span className="font-bold text-emerald-600 dark:text-emerald-400 tabular-nums">
              {remainingTokens.toLocaleString()}
            </span>
          </div>
          <div className="flex items-center justify-between gap-4 text-[10px] text-slate-400 pt-1 border-t border-slate-100 dark:border-slate-800/80">
            <span>Context Tier:</span>
            <span className="font-semibold text-indigo-500 dark:text-indigo-400 font-mono">
              Tier {tokenUsage?.tier || 1} ({tokenUsage?.tier === 3 ? 'Manifest' : tokenUsage?.tier === 2 ? 'Signatures' : 'Full Source'})
            </span>
          </div>
        </div>
      )}
    </div>
  );
}
