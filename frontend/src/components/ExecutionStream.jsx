import React, { useState, useEffect, useRef, useMemo } from 'react';
import {
  FileText,
  Check,
  CheckCircle2,
  Loader2,
  ChevronDown,
  ChevronUp,
  Camera,
  ZoomIn,
  Brain,
  X,
  GitBranch,
  History,
  AlertCircle
} from 'lucide-react';
import FormattedAnswer from './FormattedAnswer';

export function safeParseUtcDate(val) {
  if (!val) return null;
  if (val instanceof Date) return isNaN(val.getTime()) ? null : val;
  if (typeof val === 'number') {
    const d = new Date(val);
    return isNaN(d.getTime()) ? null : d;
  }
  let str = String(val).trim();
  if (str.includes(' ') && !str.includes('T')) {
    str = str.replace(' ', 'T');
  }
  if (!str.endsWith('Z') && !/[+-]\d{2}(:\d{2})?$/.test(str)) {
    str += 'Z';
  }
  const d = new Date(str);
  return isNaN(d.getTime()) ? null : d;
}

// Strip DeepSeek DSML tags from text
const cleanDSML = (text) => {
  if (!text) return '';
  return text
    .replace(/<｜DSML｜[^>]*>/g, '')
    .replace(/<\|DSML\|function_calls?>/g, '')
    .replace(/<\|DSML\|/g, '')
    .replace(/\|>/g, '')
    .replace(/<｜/g, '')
    .replace(/DSML[｜|]function_call[s]?/g, '')
    .replace(/DSML[｜|][^\s]*/g, '')
    .trim();
};
import FormattedThinking from './FormattedThinking';

const normalizePreviewUrl = (url) => {
  if (!url || typeof url !== 'string') return '';
  const trimmed = url.trim();
  const apiSessionIndex = trimmed.indexOf('/api/v1/sessions/');
  if (apiSessionIndex !== -1) {
    return `${window.location.origin}${trimmed.slice(apiSessionIndex)}`;
  }
  if (trimmed.startsWith('/')) {
    return `${window.location.origin}${trimmed}`;
  }
  return trimmed;
};

/** Single animated log row — slides in from the left and fades in when mounted. */
function LogRow({ step, isActive }) {
  const [visible, setVisible] = useState(false);
  useEffect(() => {
    // Defer one frame so CSS transition fires
    const id = requestAnimationFrame(() => setVisible(true));
    return () => cancelAnimationFrame(id);
  }, []);

  const cleanedLabel = cleanDSML(step.label || '');

  return (
    <div
      className={`w-full min-w-0 transition duration-300 ease-out ${
        visible ? 'opacity-100 translate-x-0' : 'opacity-0 -translate-x-3'
      }`}
    >
      {step.kind === 'thinking' ? (
        <FormattedThinking text={step.label} isLive={isActive} defaultExpanded={false} />
      ) : (
        <div className="flex items-start gap-1.5 text-[10.5px] text-slate-600 dark:text-slate-400 py-0.5 min-w-0">
          {step.status === 'loading' ? (
            <span className="w-2.5 h-2.5 rounded-full border-1.5 border-sky-500 border-t-transparent animate-spin shrink-0 mt-1" />
          ) : step.isFile || step.kind === 'file' ? (
            <FileText className="w-3 h-3 text-sky-500 shrink-0 mt-0.5" />
          ) : (
            <Check className="w-3 h-3 text-emerald-500 shrink-0 mt-0.5" />
          )}
          <span
            className={`break-words break-all min-w-0 flex-1 leading-tight ${
              step.isFile || step.kind === 'file'
                ? 'font-mono text-sky-700 dark:text-sky-300 font-medium bg-sky-50/70 dark:bg-slate-800 px-1.5 py-0.5 rounded border border-sky-200/50 dark:border-slate-700/50'
                : ''
            }`}
          >
            {cleanedLabel}
          </span>
        </div>
      )}
    </div>
  );
}

function VisualQASnapshotCard({ step }) {
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [showCritique, setShowCritique] = useState(true);
  const [imgError, setImgError] = useState(false);

  const fullUrl = step.screenshotUrl
    ? (step.screenshotUrl.startsWith('http') || step.screenshotUrl.startsWith('data:'))
      ? step.screenshotUrl
      : `${window.location.origin}${step.screenshotUrl}`
    : '';

  return (
    <div className="my-2 rounded-xl border border-sky-200/80 dark:border-sky-800/60 bg-gradient-to-br from-sky-50/50 via-white to-indigo-50/30 dark:from-slate-900/90 dark:via-slate-900/80 dark:to-slate-800/60 overflow-hidden shadow-xs animate-fade-in transition">
      {/* Header Bar */}
      <div className="px-3 py-2 flex items-center justify-between border-b border-sky-100/80 dark:border-sky-900/40">
        <div className="flex items-center gap-1.5">
          <Camera className="w-4 h-4 text-sky-500 animate-pulse shrink-0" />
          <span className="text-[11px] font-bold text-slate-800 dark:text-slate-200 flex items-center gap-1.5">
            Visual QA Snapshot
            {step.hasIssues ? (
              <span className="px-1.5 py-0.5 rounded text-[9px] bg-amber-100 dark:bg-amber-950/60 text-amber-700 dark:text-amber-400 font-semibold border border-amber-300/40">
                Needs Refinement
              </span>
            ) : (
              <span className="px-1.5 py-0.5 rounded text-[9px] bg-emerald-100 dark:bg-emerald-950/60 text-emerald-700 dark:text-emerald-400 font-semibold border border-emerald-300/40">
                Verified
              </span>
            )}
          </span>
        </div>
        {step.critique && (
          <button
            type="button"
            onClick={() => setShowCritique(!showCritique)}
            className="text-[9.5px] font-semibold text-sky-600 dark:text-sky-400 hover:text-sky-700 dark:hover:text-sky-300 flex items-center gap-0.5 cursor-pointer"
          >
            <span>{showCritique ? 'Hide Analysis' : 'Vision Analysis'}</span>
            {showCritique ? (
              <ChevronUp className="w-3 h-3 shrink-0" />
            ) : (
              <ChevronDown className="w-3 h-3 shrink-0" />
            )}
          </button>
        )}
      </div>

      {/* Snapshot Thumbnail Preview */}
      <div className="p-2.5 flex flex-col gap-2">
        {fullUrl && !imgError ? (
          <div
            onClick={() => setIsModalOpen(true)}
            className="relative group cursor-pointer overflow-hidden rounded-lg border border-slate-200/80 dark:border-slate-800 bg-slate-100 dark:bg-slate-950 aspect-[16/10] max-h-48 flex items-center justify-center"
            title="Click to view full-resolution screenshot"
          >
            <img
              src={fullUrl}
              alt="Visual Preview Snapshot"
              onError={() => setImgError(true)}
              className="w-full h-full object-cover object-top transition-transform duration-300 group-hover:scale-102"
              loading="lazy"
            />
            <div className="absolute inset-0 bg-slate-950/20 group-hover:bg-slate-950/40 transition-colors flex items-center justify-center opacity-0 group-hover:opacity-100">
              <span className="px-2.5 py-1 rounded-lg bg-slate-900/80 text-white text-[10px] font-medium flex items-center gap-1 backdrop-blur-xs shadow-md">
                <ZoomIn className="w-3.5 h-3.5 shrink-0" />
                View Fullscreen
              </span>
            </div>
          </div>
        ) : (
          <div className="p-3 text-center text-[10.5px] text-slate-400 dark:text-slate-500 italic">
            Visual inspection snapshot captured.
          </div>
        )}

        {/* Vision AI Critique text */}
        {showCritique && step.critique && (
          <div className="p-2.5 rounded-lg bg-white/90 dark:bg-slate-800/90 border border-sky-100 dark:border-slate-700/80 text-[10.5px] text-slate-700 dark:text-slate-200 leading-relaxed shadow-2xs animate-fade-in">
            <div className="flex items-center gap-1.5 font-bold text-sky-600 dark:text-sky-400 text-[10px] uppercase tracking-wider mb-1.5">
              <Brain className="w-3.5 h-3.5 text-sky-600 dark:text-sky-400 shrink-0" />
              <span>Vision AI Layout Assessment</span>
            </div>
            <div className="whitespace-pre-wrap font-sans text-slate-600 dark:text-slate-300">
              {step.critique}
            </div>
          </div>
        )}
      </div>

      {/* Fullscreen Lightbox Modal */}
      {isModalOpen && fullUrl && (
        <div
          className="fixed inset-0 z-[500] bg-slate-950/80 flex items-center justify-center p-4 animate-fade-in"
          onClick={() => setIsModalOpen(false)}
        >
          <div
            className="relative max-w-5xl w-full max-h-[90vh] bg-slate-900 rounded-2xl border border-slate-800 shadow-2xl overflow-hidden flex flex-col"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="px-4 py-3 border-b border-slate-800 flex items-center justify-between text-white">
              <div className="flex items-center gap-2">
                <Camera className="w-4 h-4 text-sky-400 shrink-0" />
                <span className="text-xs font-bold">Visual QA Full Snapshot (1280x800)</span>
              </div>
              <button
                type="button"
                onClick={() => setIsModalOpen(false)}
                className="p-1 rounded-lg hover:bg-slate-800 text-slate-400 hover:text-white transition-colors cursor-pointer"
              >
                <X className="w-4 h-4 shrink-0" />
              </button>
            </div>
            <div className="flex-1 overflow-auto p-3 flex items-center justify-center bg-slate-950">
              <img
                src={fullUrl}
                alt="Full Preview Screenshot"
                className="max-w-full max-h-[75vh] object-contain rounded-lg shadow-lg"
              />
            </div>
            {step.critique && (
              <div className="px-4 py-2.5 bg-slate-900 border-t border-slate-800 text-[11px] text-slate-300">
                <span className="font-semibold text-sky-400">Vision Model Assessment: </span>
                <span>{step.critique}</span>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

export default function ExecutionStream({
  steps = [],
  timestamp = null,
  completedAt = null,
  promptTimestamp = null,
  isLive = false,
  checkpoint = null,
  onRevert = null,
  onContinue = null,
  sseReconnecting = false,
}) {
  // Only expand during active live streaming; automatically collapse once done to prevent clutter
  const [isExpanded, setIsExpanded] = useState(isLive);
  // Track previously seen step count to animate only new items
  const prevStepCountRef = useRef(0);

  // Automatically adjust accordion state based on live status
  useEffect(() => {
    setIsExpanded(isLive);
  }, [isLive]);

  const effectiveCompletedAt = completedAt || (!isLive && timestamp ? timestamp : null);
  const formattedCompletedTime = useMemo(() => {
    if (!effectiveCompletedAt) return null;
    try {
      const d = safeParseUtcDate(effectiveCompletedAt);
      if (!d) return null;
      return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: true });
    } catch {
      return null;
    }
  }, [effectiveCompletedAt]);

  const durationText = useMemo(() => {
    if (!promptTimestamp || !effectiveCompletedAt) return null;
    const startD = safeParseUtcDate(promptTimestamp);
    const endD = safeParseUtcDate(effectiveCompletedAt);
    if (!startD || !endD) return null;
    const start = startD.getTime();
    const end = endD.getTime();
    if (isNaN(start) || isNaN(end) || end < start) return null;
    const totalSecs = Math.max(1, Math.round((end - start) / 1000));
    if (totalSecs < 60) return `${totalSecs}s`;
    const mins = Math.floor(totalSecs / 60);
    const secs = totalSecs % 60;
    return secs > 0 ? `${mins}m ${secs}s` : `${mins}m`;
  }, [promptTimestamp, effectiveCompletedAt]);

  if (!steps || (steps.length === 0 && !isLive && !checkpoint)) return null;

  // Separate intermediate steps from the final answer / visual QA / live preview
  const answerSteps = steps.filter((s) => s.kind === 'answer' || s.status === 'answer');
  const visualQaSteps = steps.filter((s) => s.kind === 'visual_qa');
  const previewSteps = steps.filter(
    (s) => typeof s.label === 'string' && s.label.startsWith('Live preview ready:')
  );
  const intermediateSteps = steps.filter(
    (s) =>
      s.kind !== 'answer' &&
      s.status !== 'answer' &&
      s.kind !== 'visual_qa' &&
      !(typeof s.label === 'string' && s.label.startsWith('Live preview ready:'))
  );

  const fileCount = intermediateSteps.filter((s) => s.isFile || s.kind === 'file').length;
  const latestStep = intermediateSteps.length > 0 ? intermediateSteps[intermediateSteps.length - 1] : null;

  // Changed files from the runtime snapshot diff
  const changedFiles = checkpoint?.changedFiles || [];
  const createdFiles = checkpoint?.createdFiles || [];
  const modifiedFiles = checkpoint?.modifiedFiles || [];
  const hasCheckpoint = checkpoint?.commitHash && changedFiles.length > 0;
  const isReverting = checkpoint?.isReverting || false;

  // Mark which steps are "new" (beyond previous count) for animation
  const prevCount = prevStepCountRef.current;
  prevStepCountRef.current = intermediateSteps.length;

  return (
    <div className="w-full flex flex-col gap-2 my-1">
      {/* Intermediate Steps Accordion (Thinking & Compact Contained Logs) */}
      {(intermediateSteps.length > 0 || isLive) && (
        <div className={`rounded-xl bg-white/90 dark:bg-slate-900/90 border overflow-hidden shadow-2xs transition duration-300 ${
          isLive ? 'border-sky-400/60 dark:border-sky-500/60' : 'border-slate-200 dark:border-slate-800'
        }`}>
          {/* Stream Summary Header / Toggle */}
          <button
            type="button"
            onClick={() => setIsExpanded(!isExpanded)}
            className="w-full px-3 py-2 flex items-center justify-between gap-2 hover:bg-slate-50 dark:hover:bg-slate-800/60 transition-colors cursor-pointer text-left select-none"
          >
            <div className="flex items-center gap-2 min-w-0 flex-1">
              {isLive ? (
                <Loader2 className="w-4 h-4 text-sky-500 animate-spin shrink-0" />
              ) : (
                <CheckCircle2 className="w-4 h-4 text-emerald-500 shrink-0" />
              )}

              <div className="flex items-center gap-1.5 min-w-0 truncate text-[11px]">
                <span className="font-semibold text-slate-800 dark:text-slate-200 truncate">
                  {isLive ? 'Building Application' : 'Build Completed'}
                </span>
                <span className="text-slate-400 dark:text-slate-500 font-mono text-[10px]">
                  • {fileCount > 0 ? `${fileCount} files` : `${intermediateSteps.length} steps`}
                </span>
                {isLive && (
                  <span className="px-1.5 py-0.2 rounded-full text-[8.5px] bg-sky-500 text-white font-bold animate-pulse ml-0.5">
                    LIVE
                  </span>
                )}
                {/* SSE reconnecting indicator */}
                {sseReconnecting && (
                  <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-full text-[8px] bg-amber-500/20 text-amber-600 dark:text-amber-400 border border-amber-400/30 font-semibold animate-pulse ml-0.5">
                    <span className="w-1.5 h-1.5 rounded-full bg-amber-500 animate-ping shrink-0" />
                    Reconnecting
                  </span>
                )}
              </div>
            </div>

            <div className="flex items-center gap-1.5 shrink-0 text-slate-400">
              <span className="text-[10px] hover:text-slate-600 dark:hover:text-slate-300 font-medium">
                {isExpanded ? 'Hide logs' : 'View logs'}
              </span>
              <ChevronDown className={`w-3.5 h-3.5 text-slate-400 transition-transform duration-200 shrink-0 ${
                isExpanded ? 'rotate-180' : ''
              }`} />
            </div>
          </button>

          {/* Live Single-line Status Ribbon when collapsed during build */}
          {isLive && !isExpanded && latestStep && (
            <div className="px-3 py-1 bg-sky-50/50 dark:bg-sky-950/30 border-t border-sky-100 dark:border-sky-900/40 text-[10.5px] text-sky-700 dark:text-sky-300 truncate flex items-center gap-1.5 transition duration-300">
              <span className="w-1.5 h-1.5 rounded-full bg-sky-500 animate-ping shrink-0" />
              <span className="truncate font-mono">{latestStep.label}</span>
            </div>
          )}

          {/* Steps Stream List */}
          {isExpanded && (
            <div className="px-3 pb-2.5 pt-1 border-t border-slate-100 dark:border-slate-800/80 flex flex-col gap-1">
              {intermediateSteps.length === 0 && isLive && (
                <div className="flex items-center gap-2 text-[10.5px] text-slate-500 dark:text-slate-400 py-1 font-mono animate-fade-in">
                  <span className="w-2.5 h-2.5 rounded-full border-1.5 border-sky-500 border-t-transparent animate-spin shrink-0" />
                  <span>Building application...</span>
                </div>
              )}
              {intermediateSteps.map((step, idx) => {
                const isLatest = idx === intermediateSteps.length - 1;
                const isStepActive = isLive && isLatest && step.status !== 'done';
                // Animate items that appeared since last render
                const isNewItem = idx >= prevCount;
                return (
                  <LogRow
                    key={step.id || idx}
                    step={step}
                    isActive={isStepActive}
                    isNew={isNewItem}
                  />
                );
              })}
            </div>
          )}
        </div>
      )}

      {/* ── Changed Files Card & Revert Button ── */}
      {hasCheckpoint && !isLive && (
        <div className="rounded-xl border border-indigo-200/60 dark:border-indigo-800/50 bg-indigo-50/60 dark:bg-indigo-950/30 overflow-hidden animate-fade-in shadow-xs">
          {/* Header */}
          <div className="px-3 py-2 flex items-center justify-between gap-2 border-b border-indigo-100/60 dark:border-indigo-900/40">
            <div className="flex items-center gap-1.5">
              <GitBranch className="w-4 h-4 text-indigo-500 shrink-0" />
              <span className="text-[11px] font-bold text-indigo-700 dark:text-indigo-300">
                {changedFiles.length} file{changedFiles.length !== 1 ? 's' : ''} changed
              </span>
              <span className="text-[9px] font-mono bg-indigo-100 dark:bg-indigo-900/50 text-indigo-500 dark:text-indigo-400 px-1.5 py-0.5 rounded border border-indigo-200/50 dark:border-indigo-800/50">
                {checkpoint.commitHash.slice(0, 8)}
              </span>
            </div>
            {/* Revert Button */}
            {onRevert && (
              <button
                type="button"
                onClick={onRevert}
                disabled={isReverting}
                title="Revert workspace to this checkpoint and regenerate preview"
                className={`flex items-center gap-1 text-[9.5px] font-bold px-2 py-1 rounded-lg border transition cursor-pointer ${
                  isReverting
                    ? 'bg-slate-100 dark:bg-slate-800 text-slate-400 border-slate-200 dark:border-slate-700 cursor-not-allowed'
                    : 'bg-white dark:bg-slate-800/80 hover:bg-indigo-50 dark:hover:bg-indigo-950/60 text-indigo-600 dark:text-indigo-400 border-indigo-300/60 dark:border-indigo-700/60 hover:border-indigo-400 shadow-xs'
                }`}
              >
                {isReverting ? (
                  <>
                    <span className="w-2.5 h-2.5 rounded-full border-1.5 border-indigo-400 border-t-transparent animate-spin" />
                    <span>Reverting...</span>
                  </>
                ) : (
                  <>
                    <History className="w-3 h-3 shrink-0" />
                    <span>Revert to this version</span>
                  </>
                )}
              </button>
            )}
          </div>
          {/* File List */}
          <div className="px-3 py-2 flex flex-col gap-0.5 max-h-36 overflow-y-auto">
            {changedFiles.slice(0, 20).map((f) => {
              const isCreated = createdFiles.includes(f);
              const isModified = modifiedFiles.includes(f);
              const shortPath = f.replace(/^(src\/|\/workspace\/src\/)/, '');
              return (
                <div key={f} className="flex items-center gap-1.5 text-[10px] animate-fade-in">
                  <span className={`w-3.5 h-3.5 rounded text-[8px] font-bold flex items-center justify-center shrink-0 ${
                    isCreated
                      ? 'bg-emerald-100 dark:bg-emerald-900/50 text-emerald-700 dark:text-emerald-300 border border-emerald-300/50'
                      : isModified
                        ? 'bg-amber-100 dark:bg-amber-900/50 text-amber-700 dark:text-amber-300 border border-amber-300/50'
                        : 'bg-rose-100 dark:bg-rose-900/50 text-rose-700 dark:text-rose-300 border border-rose-300/50'
                  }`}>
                    {isCreated ? '+' : isModified ? '~' : '-'}
                  </span>
                  <span className="font-mono text-slate-700 dark:text-slate-300 truncate">
                    {shortPath}
                  </span>
                </div>
              );
            })}
            {changedFiles.length > 20 && (
              <span className="text-[9.5px] text-slate-400 pl-5">
                +{changedFiles.length - 20} more files...
              </span>
            )}
          </div>
        </div>
      )}

      {/* Visual QA Snapshot Cards */}
      {visualQaSteps.map((step) => (
        <VisualQASnapshotCard key={step.id} step={step} />
      ))}

      {/* Prominently Rendered AI Assistant Answer Card */}
      {answerSteps.map((step) => (
        <div
          key={step.id}
          className="p-3.5 bg-white dark:bg-slate-900 border border-slate-200/90 dark:border-slate-800/90 rounded-2xl shadow-xs animate-fade-in"
        >
          <FormattedAnswer text={step.label} onContinue={onContinue} />

          {/* Answer Card Footer: Deployment status & exact completion time */}
          {!isLive && (durationText || formattedCompletedTime) && (
            <div className="mt-3 pt-2.5 border-t border-slate-100 dark:border-slate-800/80 flex items-center justify-between text-[10.5px] select-none">
              <span className="flex items-center gap-1.5 text-emerald-600 dark:text-emerald-400 font-medium">
                <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500 shrink-0" />
                <span>App built & Live</span>
              </span>
              <div className="flex items-center gap-1.5 font-mono text-[10px] text-slate-500 dark:text-slate-400">
                {durationText && <span>Took {durationText}</span>}
                {durationText && formattedCompletedTime && <span>•</span>}
                {formattedCompletedTime && <span>Deployed at {formattedCompletedTime}</span>}
              </div>
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
